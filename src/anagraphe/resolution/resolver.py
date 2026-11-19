"""
The record resolver: the operations ``resolve`` and ``read`` on the targets of one root.

``resolve`` follows the route of the decision on cross-repository resolution:

1. normalize the target: a target naming the repository of the root, or one of its former
   identifiers, is a local target, which the check of the root resolves in its working tree;
2. select the state of the repository from the context. An identifier that the configuration of a
   state of the context lists under ``repository.retired`` resolves to the identifier of that
   state, with a warning;
3. read the configuration of Anagraphe at that state, derive the identity of the state from its
   override ``repository.id``, else from the name of its remote, and require it to equal the
   identifier naming the state; then read the registry at the path that the configuration names.
   A target naming the repository itself resolves once the identity of the state is verified;
4. look up the identifier in the registry, and follow a chain of ``replaced_by`` to a live record.

``read`` reads the registered path through the provider, never through a symbolic link, then
verifies that the record parses, holds the identifier of the target and the unit that it names,
and follows a contract that the citing field admits. The schemas of a contract come from the schema
registry of the consumer, since a selected state holds no schema closure. The default identifier of
the record is read through the metadata source that the configuration of the state declares for
its file under ``metadata``.

Each failure is a finding whose kind names it, as the table of outcomes of ADR 0009 lists them.
A finding opens on the written target, so a report places it without its locus.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from anagraphe.core.configuration import ConfigurationError
from anagraphe.core.metadata import MetadataReader, Source, parse_metadata
from anagraphe.resolution.context import Entry, ResolutionContext, Unreadable, read_configuration
from anagraphe.resolution.provider import (
    Availability,
    Blob,
    Escaping,
    Missing,
    Mode,
    StateProvider,
    Unavailable,
    confined,
)
from anagraphe.targets.declarations import Declarations
from anagraphe.targets.kinds import (
    ESCAPING_TARGET_PATH,
    INVALID_RECORD_REGISTRY,
    INVALID_TARGET_REPOSITORY,
    INVALID_TARGET_STATE,
    LINKED_TARGET_PATH,
    RENAMED_REPOSITORY,
    RENAMED_TARGET,
    RETIRED_TARGET,
    STALE_TARGET_REGISTRY,
    UNKNOWN_RECORD,
    UNKNOWN_REPOSITORY,
    UNREADABLE_RECORD,
    UNREADABLE_TARGET_STATE,
    UNVERIFIED_TARGET,
)
from anagraphe.targets.identity import Identity, state_identity
from anagraphe.targets.model import Target
from anagraphe.targets.records import Record, parse_record
from anagraphe.targets.registry.configuration import DEFAULT_PATH
from anagraphe.targets.registry.contract import (
    SUFFIX_FORMATS,
    Entry as RegistryEntry,
    RecordRegistry,
    follow,
    parse_registry,
)
from anagraphe.targets.verification import Finding, held_findings


class Outcome(StrEnum):
    """Where the resolution of a target ends."""

    #: The target names the root, so the check of the root resolves it.
    LOCAL = "local"
    #: The target names another repository itself, whose state declares its identifier.
    REPOSITORY = "repository"
    #: The registry of the state places the record of the target.
    RECORD = "record"
    #: A finding stops the resolution.
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class Provenance:
    """Where a resolved target lies: its repository, the selected commit, and the record path."""

    repository: str
    commit: str
    #: The registered path of the record, None for a target naming the repository itself.
    path: str | None = None


@dataclass(frozen=True)
class Resolution:
    """The outcome of ``resolve``: the target followed to its current names, and its findings.

    The findings of a resolved target are warnings of a rename; the finding of an unresolved
    target names why it stops.
    """

    target: Target
    outcome: Outcome
    findings: tuple[Finding, ...] = ()
    entry: Entry | None = None
    #: The registered file of the record, for the outcome ``record``.
    record: RegistryEntry | None = None

    @property
    def provenance(self) -> Provenance | None:
        """Return the repository, the commit and the path of a resolved target, None otherwise."""
        if self.entry is None or self.outcome not in (Outcome.REPOSITORY, Outcome.RECORD):
            return None
        path = self.record.path if self.record is not None else None
        return Provenance(self.entry.repository, self.entry.state.commit, path)


@dataclass(frozen=True)
class RecordRead:
    """The outcome of ``read``: the bytes of the record with their provenance, and its findings."""

    provenance: Provenance
    #: The bytes of the record, None when the provider returns no file.
    data: bytes | None
    findings: tuple[Finding, ...] = ()
    #: The record parsed from its bytes, None when they are not a readable record.
    record: Record | None = None

    @property
    def verified(self) -> bool:
        """Whether the record is read and holds the identifier, the unit and an admitted
        contract."""
        return self.data is not None and not self.findings


@dataclass
class RecordResolver:
    """Resolve and read the targets of one root into other repositories.

    Parameters
    ----------
    context : ResolutionContext
        The selected state of each repository that the targets of the root may name.
    provider : StateProvider
        The reader of the selected states.
    declarations : Declarations or None
        The declarations of the contracts of the schema registry of the consumer, None without
        one.
    binding : str
        The key of a record naming its contract.
    """

    context: ResolutionContext
    provider: StateProvider
    declarations: Declarations | None = None
    binding: str = "_schema"
    _identities: dict[str, Identity | Finding] = field(default_factory=dict, init=False)
    _registries: dict[str, RecordRegistry | Finding] = field(default_factory=dict, init=False)
    _metadata: dict[str, MetadataReader | Finding] = field(default_factory=dict, init=False)

    def resolve(self, target: Target) -> Resolution:
        """Return the state, and the registered record, of a target."""
        context = self.context
        written = str(target)
        repository = target.repository
        if repository is None or repository == context.repository:
            return Resolution(target.normalized(context.repository), Outcome.LOCAL)
        if repository in context.retired:
            current = replace(target, repository=context.repository)
            return Resolution(current, Outcome.LOCAL, (_renamed(written, repository, current),))
        warnings: list[Finding] = []
        entry = context.entries.get(repository)
        if entry is None:
            found = self._successor(repository)
            if isinstance(found, Finding):
                return _stop(target, written, found)
            entry = found
            current = replace(target, repository=entry.repository)
            warnings.append(_renamed(written, repository, current))
            target = current
        identity = self._identity(entry)
        if isinstance(identity, Finding):
            return _stop(target, written, identity, warnings, entry)
        if target.id is None:
            return Resolution(target, Outcome.REPOSITORY, tuple(warnings), entry)
        registry = self._registry(entry, identity)
        if isinstance(registry, Finding):
            return _stop(target, written, registry, warnings, entry)
        return self._lookup(target, written, entry, registry, warnings)

    def read(
        self, resolution: Resolution, contracts: tuple[tuple[str, ...], ...] = ()
    ) -> RecordRead:
        """Return the verified bytes of the record of a resolved target.

        Parameters
        ----------
        resolution : Resolution
            The resolution of the target, whose outcome is ``record``.
        contracts : tuple of tuple of str
            The entries of each ``x-target-contract`` declared on the citing field.

        Raises
        ------
        ValueError
            If the resolution places no record.
        """
        provenance = resolution.provenance
        if resolution.outcome is not Outcome.RECORD or resolution.entry is None or not provenance:
            raise ValueError("read takes the resolution of a target placed at a record")
        assert resolution.record is not None and provenance.path is not None
        target, entry, path = resolution.target, resolution.entry, provenance.path
        written = str(target)
        reading = self.provider.read(entry.state, path)
        failure: Finding | None = None
        if isinstance(reading, Unavailable):
            failure = _unavailable(entry, reading)
        elif isinstance(reading, Escaping):
            failure = Finding(
                ESCAPING_TARGET_PATH,
                f"the registry of {entry.repository} places the record at {path}, which leaves "
                "its state",
            )
        elif isinstance(reading, Missing) or reading.mode in (Mode.DIRECTORY, Mode.SUBMODULE):
            failure = Finding(
                STALE_TARGET_REGISTRY,
                f"the registry of {entry.repository} places the record at {path}, where the "
                f"state {entry.state.commit} holds no file",
            )
        elif reading.mode is Mode.LINK:
            failure = Finding(
                LINKED_TARGET_PATH,
                f"the registry of {entry.repository} places the record at {path}, a symbolic "
                "link, which the resolver never follows",
            )
        if failure is not None:
            return RecordRead(provenance, None, (_prefixed(written, failure),))
        assert isinstance(reading, Blob)
        suffix = SUFFIX_FORMATS.get(PurePosixPath(path).suffix)
        if suffix is not resolution.record.format:
            finding = Finding(
                UNREADABLE_RECORD,
                f"{written}: {entry.repository}:{path} is registered as {resolution.record.format}, "
                f"and its suffix names {suffix or 'no format of a record'}",
            )
            return RecordRead(provenance, reading.data, (finding,))
        try:
            text = reading.data.decode("utf-8")
        except UnicodeDecodeError:
            finding = Finding(
                UNREADABLE_RECORD, f"{written}: {entry.repository}:{path} is not UTF-8 text"
            )
            return RecordRead(provenance, reading.data, (finding,))
        metadata = self._metadata_of(entry)
        if isinstance(metadata, Finding):
            return RecordRead(provenance, reading.data, (_prefixed(written, metadata),))
        source: Source = metadata.source_of(path)
        record = parse_record(path, text, self.binding, self.declarations, source)
        if record.problem is not None:
            finding = Finding(
                UNREADABLE_RECORD, f"{written}: {entry.repository}:{path}: {record.problem}"
            )
            return RecordRead(provenance, reading.data, (finding,))
        return RecordRead(
            provenance, reading.data, tuple(self._verify(target, contracts, record)), record
        )

    def _verify(
        self, target: Target, contracts: tuple[tuple[str, ...], ...], record: Record
    ) -> list[Finding]:
        """Return the findings of a parsed record: its identifier, its unit and its contract."""
        written = str(target)
        schemas_known = record.contract is None or (
            self.declarations is not None and self.declarations.of(record.contract) is not None
        )
        findings: list[Finding] = []
        if record.identifier != target.id:
            if schemas_known:
                return [
                    Finding(
                        STALE_TARGET_REGISTRY,
                        f"{written}: the registry places the record at {record.rel}, which holds "
                        f"the identifier {record.identifier!r} at {record.identifier_pointer}",
                    )
                ]
            findings.append(
                Finding(
                    UNVERIFIED_TARGET,
                    f"{written}: the record {record.rel} holds {record.identifier!r} at "
                    f"{record.identifier_pointer}, and the schemas of its contract "
                    f"{record.contract}, which may declare another identifier field, are not held "
                    "by this repository",
                )
            )
        findings.extend(held_findings(target, contracts, record, schemas_known))
        return findings

    def _successor(self, repository: str) -> Entry | Finding:
        """Return the entry whose identity retires an identifier, or why none is found."""
        unread: list[str] = []
        for identifier in sorted(self.context.entries):
            entry = self.context.entries[identifier]
            identity = self._identity(entry)
            if isinstance(identity, Identity):
                if repository in identity.retired:
                    return entry
            elif identity.kind in (UNREADABLE_TARGET_STATE, INVALID_TARGET_STATE):
                unread.append(f"{identifier} at {entry.state.commit}")
        unread.extend(
            f"the submodule {link.path} at {link.commit}" for link in self.context.unnamed
        )
        if unread:
            return Finding(
                UNREADABLE_TARGET_STATE,
                f"no state of the context names the repository {repository}, and the states of "
                f"{', '.join(unread)} cannot be read",
            )
        return Finding(
            UNKNOWN_REPOSITORY,
            f"the context of this repository selects no state of {repository}; declare it under "
            "resolution.repositories, or add it as a submodule",
        )

    def _identity(self, entry: Entry) -> Identity | Finding:
        """Return the identity of the state of an entry, read once per commit."""
        commit = entry.state.commit
        if commit not in self._identities:
            self._identities[commit] = self._read_identity(entry)
        return self._identities[commit]

    def _read_identity(self, entry: Entry) -> Identity | Finding:
        """Derive the identity of a state from its configuration and its remote, and require it to
        equal the identifier of its entry."""
        at = f"the state {entry.state.commit} of {entry.repository}"
        configuration = self._configuration(entry)
        if isinstance(configuration, Finding):
            return configuration
        name, data = configuration if configuration is not None else ("", None)
        try:
            identity = state_identity(entry.state.remote, data)
        except ConfigurationError as error:
            return Finding(INVALID_TARGET_REPOSITORY, f"{at}: {name}: {error}")
        if identity.id is None:
            return Finding(
                INVALID_TARGET_REPOSITORY,
                f"{at} has no identity: its configuration declares no repository.id, and its "
                "remote names no repository identifier",
            )
        if identity.id != entry.repository:
            return Finding(
                INVALID_TARGET_REPOSITORY,
                f"{at}: the identity of the state is {identity.id}, from the "
                f"{identity.source.value}",
            )
        return identity

    def _configuration(self, entry: Entry) -> tuple[str, Mapping[str, Any]] | Finding | None:
        """Return the place and the content of the configuration of a state, None without one."""
        configuration = read_configuration(self.provider, entry.state)
        if not isinstance(configuration, Unreadable):
            return configuration
        if configuration.reading is not None:
            return _unavailable(entry, configuration.reading)
        return Finding(
            INVALID_TARGET_REPOSITORY,
            f"the state {entry.state.commit} of {entry.repository}: {configuration.detail}",
        )

    def _metadata_of(self, entry: Entry) -> MetadataReader | Finding:
        """Return the reader of the metadata sources that the configuration of a state declares,
        read once per commit; the built-in sources for a state without configuration."""
        commit = entry.state.commit
        if commit not in self._metadata:
            configuration = self._configuration(entry)
            if isinstance(configuration, Finding):
                self._metadata[commit] = configuration
            else:
                name, data = configuration if configuration is not None else ("", {})
                try:
                    rules = parse_metadata(data.get("metadata"), "metadata")
                except ConfigurationError as error:
                    self._metadata[commit] = Finding(
                        INVALID_TARGET_REPOSITORY,
                        f"the state {commit} of {entry.repository}: {name}: {error}",
                    )
                else:
                    # The reader only selects the source of a path, so it reads no file of a root.
                    self._metadata[commit] = MetadataReader(Path("."), rules)
        return self._metadata[commit]

    def _registry(self, entry: Entry, identity: Identity) -> RecordRegistry | Finding:
        """Return the record registry of the state of an entry, read once per commit."""
        commit = entry.state.commit
        if commit not in self._registries:
            self._registries[commit] = self._read_registry(entry, identity)
        return self._registries[commit]

    def _read_registry(self, entry: Entry, identity: Identity) -> RecordRegistry | Finding:
        """Read the configuration of a state, then the registry that its section ``records``
        names; a state without either holds no registry, as ADR 0007 admits."""
        at = f"the state {entry.state.commit} of {entry.repository}"
        configuration = self._configuration(entry)
        if isinstance(configuration, Finding):
            return configuration
        if configuration is None:
            return Finding(
                UNVERIFIED_TARGET,
                f"{at} holds no configuration of Anagraphe, so no record registry; only the form "
                "of the target is checked",
            )
        name, data = configuration
        if "records" not in data:
            return Finding(
                UNVERIFIED_TARGET,
                f"{at} declares no section records in {name}, so no record registry; only the "
                "form of the target is checked",
            )
        records = data.get("records") or {}
        path = records.get("path", DEFAULT_PATH) if isinstance(records, dict) else None
        normal = confined(path) if isinstance(path, str) else None
        if normal is None:
            return Finding(
                INVALID_TARGET_REPOSITORY,
                f"{at}: {name} names no registry inside the repository",
            )
        registry_text = self._text(entry, normal, INVALID_RECORD_REGISTRY)
        if isinstance(registry_text, Finding):
            return registry_text
        if registry_text is None:
            return Finding(
                UNVERIFIED_TARGET,
                f"{at} declares the record registry {normal}, which the state does not hold; only "
                "the form of the target is checked",
            )
        reading = parse_registry(registry_text, normal)
        if reading.registry is None:
            problem = reading.problems[0]
            place = f" at {problem.pointer}" if problem.pointer else ""
            return Finding(INVALID_RECORD_REGISTRY, f"{at}{place}: {problem.detail}")
        if reading.registry.repository != identity.id:
            return Finding(
                INVALID_RECORD_REGISTRY,
                f"{at}: {normal} names the repository {reading.registry.repository}, and the "
                f"identity of the state is {identity.id}",
            )
        return reading.registry

    def _text(self, entry: Entry, path: str, kind: str) -> str | Finding | None:
        """Return the text of a file of a state, None when the state holds none at the path.

        An unreadable state, an escaping path, a symbolic link, a folder and bytes that are not
        UTF-8 each yield a finding; all but the first take ``kind``.
        """
        reading = self.provider.read(entry.state, path)
        if isinstance(reading, Unavailable):
            return _unavailable(entry, reading)
        if isinstance(reading, Missing):
            return None
        at = f"the state {entry.state.commit} of {entry.repository}"
        if isinstance(reading, Escaping):
            return Finding(kind, f"{at}: {path} leaves the state")
        if reading.mode is not Mode.FILE:
            return Finding(kind, f"{at}: {path} is a {reading.mode.value}, not a file")
        try:
            return reading.data.decode("utf-8")
        except UnicodeDecodeError:
            return Finding(kind, f"{at}: {path} is not UTF-8 text")

    def _lookup(
        self,
        target: Target,
        written: str,
        entry: Entry,
        registry: RecordRegistry,
        warnings: list[Finding],
    ) -> Resolution:
        """Look up the identifier of a target in the registry, following its renames."""
        assert target.id is not None
        if target.id in registry.records:
            return Resolution(
                target, Outcome.RECORD, tuple(warnings), entry, registry.records[target.id]
            )
        at = f"{entry.repository} at {entry.state.commit}"
        if target.id not in registry.retired:
            failure = Finding(UNKNOWN_RECORD, f"no record of {at} holds the identifier {target.id}")
            return _stop(target, written, failure, warnings, entry)
        chain = follow(registry.retired, target.id, registry.records.__contains__)
        if chain is None:
            successor = registry.retired[target.id].replaced_by
            reason = (
                f"replaced by {successor}, whose successors reach no record"
                if successor is not None
                else "without a successor"
            )
            failure = Finding(
                RETIRED_TARGET, f"the identifier {target.id} is retired in {at} {reason}"
            )
            return _stop(target, written, failure, warnings, entry)
        followed = replace(target, id=chain[-1])
        warnings.append(
            Finding(
                RENAMED_TARGET,
                f"{written}: the identifier {target.id} is retired in {at} and replaced by "
                f"{chain[-1]}"
                + (f" through {', '.join(chain[:-1])}" if len(chain) > 1 else "")
                + f"; write {followed}",
            )
        )
        return Resolution(
            followed, Outcome.RECORD, tuple(warnings), entry, registry.records[chain[-1]]
        )


def _renamed(written: str, retired: str, current: Target) -> Finding:
    """Return the warning of a target naming a retired repository identifier."""
    return Finding(
        RENAMED_REPOSITORY,
        f"{written}: the repository {retired} is retired and replaced by {current.repository}; "
        f"write {current}",
    )


def _unavailable(entry: Entry, reading: Unavailable) -> Finding:
    """Return the finding of a state that the provider cannot read."""
    kind = (
        INVALID_TARGET_STATE
        if reading.availability is Availability.INVALID
        else UNREADABLE_TARGET_STATE
    )
    return Finding(
        kind,
        f"the state {entry.state.commit} of {entry.repository} cannot be read "
        f"({reading.availability.value}): {reading.detail}",
    )


def _prefixed(written: str, finding: Finding) -> Finding:
    """Return a finding whose detail opens on the written target."""
    if finding.detail.startswith(f"{written}: "):
        return finding
    return Finding(finding.kind, f"{written}: {finding.detail}")


def _stop(
    target: Target,
    written: str,
    failure: Finding,
    warnings: list[Finding] | None = None,
    entry: Entry | None = None,
) -> Resolution:
    """Return an unresolved target: its warnings, then the finding that stops it."""
    return Resolution(
        target,
        Outcome.UNRESOLVED,
        (*(warnings or ()), _prefixed(written, failure)),
        entry,
    )
