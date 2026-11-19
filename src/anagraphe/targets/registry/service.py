"""
The commands of the record registry: its generation, its check, and the retirement of an
identifier.

The generation maps each identifier of the walk of the targets to the path and the format of its
record, and carries over the retired identifiers of the current file. The check compares the
registry with the records of the walk and writes nothing; every registry that a write leaves passes
the check of the same walk. The retirement moves an identifier that no record
holds any longer from ``records`` into ``retired``, with the day given by the clock and its
successor after a rename.

The findings of the check are disjoint. An entry naming no record is ``vanished-identifier`` when
it is not retired, and ``stale-registry`` when it is; a record holding a retired identifier is
``reused-identifier`` only. An identifier held by two records is left to ``duplicate-identifier``
of the check of the targets, so it is not compared.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

from anagraphe.core.files import write_atomically
from anagraphe.core.issues import Issue, Report, pointer
from anagraphe.targets.configuration import TargetConfig
from anagraphe.targets.kinds import (
    DUPLICATE_IDENTIFIER,
    INVALID_IDENTIFIER,
    INVALID_RECORD_REGISTRY,
    MISSING_IDENTIFIER,
    UNIDENTIFIED_REPOSITORY,
    UNREADABLE_RECORD,
)
from anagraphe.targets.identity import (
    DeclaredIdentity,
    Identity,
    configuration_rel,
    repository_identity,
)
from anagraphe.targets.records import Record
from anagraphe.targets.registry.configuration import RecordsConfig
from anagraphe.targets.registry.contract import (
    Entry,
    RecordRegistry,
    RegistryReading,
    Retirement,
    format_of,
    read_registry,
)
from anagraphe.targets.registry.kinds import (
    REUSED_IDENTIFIER,
    STALE_REGISTRY,
    UNKNOWN_SUCCESSOR,
    VANISHED_IDENTIFIER,
)
from anagraphe.targets.resource import matches
from anagraphe.targets.walk import RecordWalk

#: The command that regenerates the registry, named by the findings that it repairs.
WRITE = "anagraphe records write"
#: The command that retires an identifier, named by the findings that it repairs.
RETIRE = "anagraphe records retire"


class RetireRefused(ValueError):
    """Report an identifier that ``anagraphe records retire`` refuses to retire, and why."""


@dataclass(frozen=True)
class WriteResult:
    """The outcome of a write: the issues blocking it, or the registry written."""

    #: The issues of the walk or of the current file that block the write; empty when it ran.
    issues: tuple[Issue, ...]
    #: The registry generated, None when the write is blocked.
    registry: RecordRegistry | None = None
    #: Whether the write changed the file.
    changed: bool = False


@dataclass
class RegistryService:
    """Generate, check and extend the record registry of one repository.

    Parameters
    ----------
    root : Path
        The root of the repository.
    targets : TargetConfig
        The section ``targets``, whose walk supplies the records.
    records : RecordsConfig
        The section ``records``, which names the file of the registry.
    clock : Callable[[], datetime.date]
        The source of the day of a retirement, today by default.
    declared : DeclaredIdentity or None
        The section ``repository``, from which the identity that the registry names derives; None
        when the repository declares none.

    Raises
    ------
    ConfigurationError
        If the former identifiers list the derived identifier.
    """

    root: Path
    targets: TargetConfig
    records: RecordsConfig
    clock: Callable[[], datetime.date] = datetime.date.today
    declared: DeclaredIdentity | None = None
    walk: RecordWalk = field(init=False)
    identity: Identity = field(init=False)

    def __post_init__(self) -> None:
        self.root = self.root.resolve()
        self.identity = repository_identity(self.root, self.declared)
        self.walk = RecordWalk(self.root, self.targets, frozenset({self.records.rel}))

    @property
    def rel(self) -> str:
        """Return the path of the registry relative to the root, as the findings name it."""
        return self.records.rel

    def read(self) -> RegistryReading:
        """Read the current file of the registry."""
        return read_registry(self.records.path, self.rel)

    def generation(self) -> dict[str, Entry]:
        """Return the entry of each identifier held by exactly one record of the walk."""
        return {
            identifier: Entry(holders[0].rel, format_of(holders[0].rel))
            for identifier, holders in self.walk.table.items()
            if len(holders) == 1
        }

    # --- Write.

    def write(self) -> WriteResult:
        """Generate the registry and write it, unless an issue of the walk or of the current file
        blocks the write; a blocked write changes no file.

        The issues blocking a write are the unreadable records, the missing, invalid, duplicate and
        retired identifiers of the walk, the identifiers of the current file naming no record and
        not retired, the successors naming neither a record nor a retired identifier, an invalid
        current file, a repository without identity, and the defects of the schemas, which
        hide the identifiers of their records from the walk.
        """
        reading = self.read()
        # A schema that cannot be read hides the identifiers of its records from the walk.
        issues = [
            *self._walk_issues(),
            *self.walk.schema_issues(),
            *self._invalid_issues(reading),
        ]
        repository = self.identity.id
        if repository is None:
            config = configuration_rel(self.root)
            issues.append(
                Issue(
                    config,
                    None,
                    UNIDENTIFIED_REPOSITORY,
                    "the repository has no identity, which the registry names under repository: "
                    "neither its remote origin nor its folder is named by a repository "
                    f"identifier; declare repository: {{id: <identifier>}} in {config}",
                )
            )
        retired = reading.registry.retired if reading.registry is not None else {}
        table = self.walk.table
        for identifier, holders in table.items():
            if identifier in retired:
                issues.extend(
                    Issue(
                        holder.rel,
                        None,
                        REUSED_IDENTIFIER,
                        f"the identifier {identifier} is retired in {self.rel}, and a retired "
                        "identifier is never reused",
                        locus=holder.identifier_pointer,
                    )
                    for holder in holders
                )
        if reading.registry is not None:
            issues.extend(
                self._vanished(identifier)
                for identifier in sorted(reading.registry.records)
                if identifier not in table and identifier not in retired
            )
            # A write never leaves a registry that its own check rejects.
            issues.extend(self._successor_issues(reading.registry))
        if issues or repository is None:
            return WriteResult(_located(issues))
        registry = RecordRegistry(repository, self.generation(), dict(retired))
        text = registry.render()
        changed = reading.text != text
        if changed:
            self._save(text)
        return WriteResult((), registry, changed)

    def _walk_issues(self) -> list[Issue]:
        """Return the records of the walk that block a write: unreadable, or holding a missing,
        invalid or duplicate identifier."""
        issues: list[Issue] = []
        table = self.walk.table
        for record in self.walk.records():
            issue = self._walk_issue(record, table)
            if issue is not None:
                issues.append(issue)
        return issues

    @staticmethod
    def _walk_issue(record: Record, table: dict[str, list[Record]]) -> Issue | None:
        """Return the issue of one record of the walk that blocks a write, None when it has none."""
        at = record.identifier_pointer
        if record.problem is not None:
            return Issue(record.rel, None, UNREADABLE_RECORD, record.problem)
        if record.identifier is None:
            if not record.declared:
                return None
            return Issue(
                record.rel,
                None,
                MISSING_IDENTIFIER,
                f"the contract {record.contract} declares its identifier at {at}, which the "
                "record leaves empty",
                locus=at,
            )
        if not matches("record-id", record.identifier):
            return Issue(
                record.rel,
                None,
                INVALID_IDENTIFIER,
                f"the identifier {record.identifier!r} lies outside the pattern of record-id",
                locus=at,
            )
        others = [other.rel for other in table[record.identifier] if other.rel != record.rel]
        if others:
            return Issue(
                record.rel,
                None,
                DUPLICATE_IDENTIFIER,
                f"the identifier {record.identifier} is also held by {', '.join(others)}",
                locus=at,
            )
        return None

    def _save(self, text: str) -> None:
        """Replace the file of the registry, creating its folders."""
        self.records.path.parent.mkdir(parents=True, exist_ok=True)
        write_atomically(self.root, {self.rel: text})

    # --- Check.

    def check(self) -> Report:
        """Compare the registry with the generation, and write nothing.

        An absent registry is one ``stale-registry`` of the whole file. A registry that cannot be
        parsed, or that violates its contract, stops the comparisons.
        """
        reading = self.read()
        processed = sum(len(holders) for holders in self.walk.table.values())
        return Report(processed, _located(self._check_issues(reading)))

    def _check_issues(self, reading: RegistryReading) -> list[Issue]:
        """Return the findings of the check of a registry read from its file."""
        if not reading.exists:
            return [self._issue(STALE_REGISTRY, "", f"{self.rel} does not exist; run {WRITE}")]
        if reading.registry is None:
            return self._invalid_issues(reading)
        registry = reading.registry
        issues = [
            *self._repository_issues(registry),
            *self._record_issues(registry),
            *self._entry_issues(registry),
            *self._successor_issues(registry),
        ]
        if not issues and reading.text != registry.render():
            issues.append(
                self._issue(
                    STALE_REGISTRY,
                    "",
                    f"{self.rel} holds the entries of the generation, in another form than "
                    f"{WRITE} writes; run it",
                )
            )
        return issues

    def _repository_issues(self, registry: RecordRegistry) -> list[Issue]:
        """Return the issue of a registry naming another repository than the identity, which
        reports a change of the derived identifier."""
        identity = self.identity
        if identity.id == registry.repository:
            return []
        derived = (
            f"the identity of the repository is {identity.id}, from the {identity.source.value}"
            if identity.id is not None
            else "the repository has no identity; declare repository.id in "
            + configuration_rel(self.root)
        )
        return [
            self._issue(
                STALE_REGISTRY,
                pointer("repository"),
                f"the registry names the repository {registry.repository}, and {derived}; "
                f"declare repository: {{id: {registry.repository}}} to keep that identifier, or "
                f"list it under repository.retired after a rename, then run {WRITE}",
            )
        ]

    def _record_issues(self, registry: RecordRegistry) -> list[Issue]:
        """Return the issues of the identifiers held by the records of the walk."""
        issues: list[Issue] = []
        for identifier, holders in sorted(self.walk.table.items()):
            if identifier in registry.retired:
                issues.append(
                    self._issue(
                        REUSED_IDENTIFIER,
                        pointer("retired", identifier),
                        f"the identifier {identifier}, retired on "
                        f"{registry.retired[identifier].date}, is held by "
                        f"{', '.join(holder.rel for holder in holders)}; a retired identifier is "
                        "never reused",
                    )
                )
                continue
            if len(holders) > 1:
                continue
            expected = Entry(holders[0].rel, format_of(holders[0].rel))
            entry = registry.records.get(identifier)
            if entry is None:
                detail = f"the record {expected.path} holds {identifier}, which records omits"
            elif entry != expected:
                detail = (
                    f"records lists {identifier} as {_entry(entry)}, and its record is "
                    f"{_entry(expected)}"
                )
            else:
                continue
            issues.append(
                self._issue(
                    STALE_REGISTRY, pointer("records", identifier), f"{detail}; run {WRITE}"
                )
            )
        return issues

    def _entry_issues(self, registry: RecordRegistry) -> list[Issue]:
        """Return the issues of the entries of ``records`` naming no record of the walk.

        An entry whose file is a record that cannot be read is not compared, since the identifier
        of that record is unknown; the check of the targets reports the record.
        """
        table = self.walk.table
        unread = self._unreadable_entries(registry)
        issues: list[Issue] = []
        for identifier in sorted(registry.records):
            if identifier in table or identifier in unread:
                continue
            at = pointer("records", identifier)
            if identifier in registry.retired:
                issues.append(
                    self._issue(
                        STALE_REGISTRY,
                        at,
                        f"records lists {identifier}, which is retired; run {WRITE}",
                    )
                )
            else:
                issues.append(self._vanished(identifier))
        return issues

    def _successor_issues(self, registry: RecordRegistry) -> list[Issue]:
        """Return the issues of the successors naming neither a record nor a retired identifier.

        A successor listed in ``records`` whose file is a record that cannot be read is not
        compared, as its entry is not.
        """
        table = self.walk.table
        unread = self._unreadable_entries(registry)
        return [
            self._issue(
                UNKNOWN_SUCCESSOR,
                pointer("retired", identifier),
                f"{identifier} is replaced by {retirement.replaced_by}, which is neither a record "
                "of the repository nor a retired identifier",
            )
            for identifier, retirement in sorted(registry.retired.items())
            if retirement.replaced_by is not None
            and retirement.replaced_by not in table
            and retirement.replaced_by not in registry.retired
            and retirement.replaced_by not in unread
        ]

    def _unreadable_entries(self, registry: RecordRegistry) -> frozenset[str]:
        """Return the identifiers of ``records`` whose file is a record that cannot be read, so
        that the identifier that the record holds is unknown."""
        unreadable = {record.rel for record in self.walk.records() if record.problem is not None}
        return frozenset(
            identifier for identifier, entry in registry.records.items() if entry.path in unreadable
        )

    def _vanished(self, identifier: str) -> Issue:
        """Return the issue of an identifier of ``records`` that names no record, and is not
        retired."""
        return self._issue(
            VANISHED_IDENTIFIER,
            pointer("records", identifier),
            f"no record holds {identifier} any longer; retire it with {RETIRE} {identifier}, "
            "naming its successor under --replaced-by after a rename",
        )

    def _invalid_issues(self, reading: RegistryReading) -> list[Issue]:
        """Return the defects of a registry that cannot be read, or that violates its contract."""
        return [
            self._issue(INVALID_RECORD_REGISTRY, problem.pointer, problem.detail)
            for problem in reading.problems
        ]

    def _issue(self, kind: str, at: str, detail: str) -> Issue:
        """Return an issue of the registry at the JSON Pointer of its entry."""
        return Issue(self.rel, None, kind, detail, locus=at)

    # --- Retire.

    def retire(self, identifier: str, successor: str | None = None) -> RecordRegistry:
        """Move an identifier that no record holds any longer from ``records`` into ``retired``,
        with the day of the clock and its successor, and write the registry.

        Raises
        ------
        RetireRefused
            If the registry is absent or invalid; if a schema of the walk cannot be read; if a
            record still holds the identifier; if the
            identifier is already retired, or absent from ``records``; if the successor is neither
            a record nor a retired identifier; or if the chain of successors returns to the
            identifier.
        """
        reading = self.read()
        if not reading.exists:
            raise RetireRefused(f"{self.rel} does not exist; run {WRITE} first")
        if reading.registry is None:
            raise RetireRefused(
                f"{self.rel} is invalid: "
                + "; ".join(
                    f"{problem.pointer or '/'}: {problem.detail}" for problem in reading.problems
                )
            )
        registry = reading.registry
        schema_issues = self.walk.schema_issues()
        if schema_issues:
            raise RetireRefused(
                "a schema of the registry cannot be read, so a record may hold the identifier "
                "unseen: " + "; ".join(f"{issue.rel}: {issue.detail}" for issue in schema_issues)
            )
        table = self.walk.table
        if identifier in table:
            holders = ", ".join(holder.rel for holder in table[identifier])
            raise RetireRefused(
                f"{identifier} is held by {holders}; change the identifier of the record first"
            )
        if identifier in registry.retired:
            raise RetireRefused(
                f"{identifier} was already retired on {registry.retired[identifier].date}"
            )
        if identifier not in registry.records:
            raise RetireRefused(f"records lists no identifier {identifier}")
        if successor is not None:
            self._check_successor(registry, identifier, successor)
        retired = {
            **registry.retired,
            identifier: Retirement(self.clock().isoformat(), successor),
        }
        records = {key: entry for key, entry in registry.records.items() if key != identifier}
        updated = RecordRegistry(registry.repository, records, retired)
        self._save(updated.render())
        return updated

    def _check_successor(self, registry: RecordRegistry, identifier: str, successor: str) -> None:
        """Refuse a successor that is neither a record nor a retired identifier, or whose chain of
        successors returns to the identifier."""
        table = self.walk.table
        if successor not in table and successor not in registry.retired:
            raise RetireRefused(
                f"the successor {successor} is neither a record of the repository nor a retired "
                "identifier"
            )
        current: str | None = successor
        seen: set[str] = set()
        while current is not None and current not in table and current in registry.retired:
            if current in seen:
                break
            seen.add(current)
            current = registry.retired[current].replaced_by
            if current == identifier:
                raise RetireRefused(
                    f"the successors of {successor} return to {identifier}, so the rename would "
                    "close a cycle"
                )


def _located(issues: list[Issue]) -> tuple[Issue, ...]:
    """Return the issues with the detail of each located one opening on its pointer, since the text
    report prints no locus."""
    return tuple(
        replace(issue, detail=f"{issue.locus}: {issue.detail}") if issue.locus else issue
        for issue in issues
    )


def _entry(entry: Entry) -> str:
    """Return an entry as the registry writes it."""
    return f"{{path: {entry.path}, format: {entry.format.value}}}"
