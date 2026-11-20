"""
The rename of a repository identifier, as ADR 0012 decides it: the record of the rename in the
renamed repository, and the rewriting of its citers in every repository checked out under the root.

The command runs at a root, often a composing repository, and its scope is that root with each of
its submodules checked out in its folder, as the gitlinks of the index list them. The renamed
repository is one member of the scope. A rename from ``OLD`` to ``NEW`` plans four kinds of edit:

1. in the configuration of the renamed repository, an override ``repository.id`` equal to ``OLD``
   becomes ``NEW``, and ``OLD`` joins ``repository.retired``; the list, the section and the file
   are created when absent;
2. the key ``repository`` of the record registry of the renamed repository, when it names ``OLD``;
3. in each member, the key ``OLD`` of ``resolution.repositories``;
4. in each member, the component ``repository`` of every logical target naming ``OLD``, in the
   target fields that the schema registry of the member declares.

Each edit replaces or inserts the characters of one value, located by the marks of the YAML
parser, so every other byte of the file is kept. Each edited file is parsed again and must read as
the file before with the planned values. An edit of steps 1 to 3 that fails this test refuses the
rename, since the identity, the registry that a resolver compares with it, and the context must
change together; a registry that cannot be read at all is left as it is, with a warning. A target
that cannot be rewritten only keeps ``OLD``, which a resolver follows with a warning once ``OLD``
is retired, so it is reported as a warning. The rename also refuses an identifier already retired by the renamed
repository, a renamed repository identified as neither ``OLD`` nor ``NEW``, another member
identified as ``OLD`` or ``NEW``, and a context already naming ``NEW``. A refused plan writes no
file; an accepted plan replaces every changed file at once, and restores them all when one
replacement fails.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

from anagraphe_read._configuration import CONFIGURATION_FORMAT, Configuration, load_configuration
from anagraphe_read._core.configuration import (
    CONFIG_FILE,
    ConfigurationError,
    discover_configuration,
)
from anagraphe_read._core.files import TargetError
from anagraphe_read._core.git_state import gitlinks, origin_url
from anagraphe_read._core.issues import Issue, pointer
from anagraphe_read._core.schemas import values_at
from anagraphe_read._targets.identity import DeclaredIdentity, IdentitySource, derive_identity
from anagraphe_read._targets.kinds import INVALID_RECORD_REGISTRY, UNREADABLE_RECORD
from anagraphe_read._targets.model import InvalidTarget, Target
from anagraphe_read._targets.records import NOTE_SUFFIX, TOML_SUFFIX, Record, parse_record
from anagraphe_read._targets.registry.contract import parse_registry
from anagraphe_read._targets.resource import matches
from anagraphe_read._targets.walk import GIT_ENTRY, RecordWalk

from anagraphe.core.structured import (
    Edit,
    add_entry,
    append_item,
    apply_edits,
    compose,
    frontmatter_span,
    node_at,
    quoted,
    replace_scalar,
)
from anagraphe.core.writes import write_atomically

#: The version of the JSON form of a plan, raised when a key changes its meaning or disappears.
PLAN_VERSION = 1
#: The path of a member, and of the root among the members, relative to the root.
ROOT_PATH = "."

#: A member whose configuration cannot be loaded, so that none of its citers is rewritten.
UNREAD_REPOSITORY = "unread-repository"
#: A target naming the former identifier that cannot be rewritten in place.
UNREWRITABLE_TARGET = "unrewritable-target"
#: A machine file mapping the former identifier to a local clone, which the rename keeps.
KEPT_CLONE = "kept-clone"
#: A renamed repository deriving the former identifier from its remote or its folder.
DERIVED_IDENTITY = "derived-identity"


class EditKind(StrEnum):
    """The value that an edit of a rename changes."""

    IDENTIFIER = "identifier"
    RETIRED = "retired"
    REGISTRY = "registry"
    RESOLUTION = "resolution"
    TARGET = "target"


@dataclass(frozen=True)
class ValueEdit:
    """One value of a file changed by a rename."""

    kind: EditKind
    #: The JSON Pointer of the value in the file, or of the key for an edit of ``resolution``.
    pointer: str
    #: The line of the value in the file after the rename, counted from 1.
    line: int
    #: The value before the rename; None for an inserted item.
    old: str | None
    new: str


@dataclass(frozen=True)
class FileChange:
    """The new text of one file of a member, and the values that it changes."""

    #: The path of the file, relative to the root of its member.
    path: str
    text: str
    edits: tuple[ValueEdit, ...]
    #: Whether the file does not exist before the rename.
    created: bool = False


@dataclass(frozen=True)
class Member:
    """One repository of the scope of a rename: the root, or a submodule checked out under it."""

    #: The path of the member relative to the root, ``.`` for the root.
    path: str
    #: The identifier of the member before the rename, derived without its former identifiers;
    #: None when the member has no identity.
    identifier: str | None
    changes: tuple[FileChange, ...] = ()
    #: The warnings of the member, each at a path relative to the member.
    warnings: tuple[Issue, ...] = ()

    def at_root(self, rel: str) -> str:
        """Return a path of the member relative to the root."""
        return _at_root(self.path, rel)


@dataclass(frozen=True)
class RenamePlan:
    """The edits of a rename, planned before any file changes, and the reasons that refuse it."""

    old: str
    new: str
    #: The path of the renamed repository relative to the root, ``.`` for the root.
    renamed: str
    members: tuple[Member, ...]
    refusals: tuple[str, ...] = ()

    @property
    def texts(self) -> dict[str, str]:
        """Return the new text of each changed file, keyed by its path relative to the root."""
        return {
            member.at_root(change.path): change.text
            for member in self.members
            for change in member.changes
        }

    @property
    def edit_count(self) -> int:
        """Return the number of values that the rename changes."""
        return sum(len(change.edits) for member in self.members for change in member.changes)

    def as_json(self, applied: bool) -> dict[str, Any]:
        """Return the JSON form of the plan, which the command prints under ``--format json``."""
        return {
            "version": PLAN_VERSION,
            "old": self.old,
            "new": self.new,
            "renamed": self.renamed,
            "applied": applied,
            "refusals": list(self.refusals),
            "repositories": [
                {
                    "path": member.path,
                    "identifier": member.identifier,
                    "files": [
                        {
                            "path": change.path,
                            "created": change.created,
                            "edits": [
                                {
                                    "kind": edit.kind.value,
                                    "pointer": edit.pointer,
                                    "line": edit.line,
                                    "old": edit.old,
                                    "new": edit.new,
                                }
                                for edit in change.edits
                            ],
                        }
                        for change in member.changes
                    ],
                    "warnings": [
                        {
                            "path": issue.rel,
                            "line": issue.line,
                            "kind": issue.kind,
                            "detail": issue.detail,
                        }
                        for issue in member.warnings
                    ],
                }
                for member in self.members
            ],
        }


class Unrewritable(ValueError):
    """Report a file whose values cannot be rewritten in place, and why."""


@dataclass
class _Checkout:  # pylint: disable=too-many-instance-attributes
    """A member of the scope as the plan reads it: its root, its configuration and its edits."""

    path: str
    root: Path
    #: The configuration file, absolute; None when no place of the member holds one.
    config_path: Path | None = None
    configuration: Configuration | None = None
    identifier: str | None = None
    source: IdentitySource = IdentitySource.NONE
    changes: list[FileChange] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)

    @property
    def config_rel(self) -> str | None:
        """Return the configuration file relative to the member, None without one."""
        if self.config_path is None:
            return None
        return self.config_path.resolve().relative_to(self.root).as_posix()

    def at_root(self, rel: str) -> str:
        """Return a path of the member relative to the root."""
        return _at_root(self.path, rel)

    def member(self) -> Member:
        """Return the member of the plan."""
        return Member(self.path, self.identifier, tuple(self.changes), tuple(self.warnings))


@dataclass
class RenameService:
    """Plan and apply the rename of a repository identifier in the repositories under a root.

    Parameters
    ----------
    root : Path
        The root of the command: the composing repository, or the renamed repository alone.
    config : Path | None
        The configuration file of the root, absolute; None when the root holds none.
    """

    root: Path
    config: Path | None = None

    def __post_init__(self) -> None:
        self.root = self.root.resolve()

    def plan(self, old: str, new: str, renamed: Path | None = None) -> RenamePlan:
        """Return the plan of renaming ``old`` to ``new``, changing no file.

        Parameters
        ----------
        old, new : str
            The former and the new identifier, each a ``repository-id``.
        renamed : Path | None
            The folder of the renamed repository, absolute; the root by default.

        Raises
        ------
        TargetError
            If an identifier lies outside the pattern of ``repository-id``, the two are equal, or
            the folder is neither the root nor a submodule checked out under it.
        ConfigurationError
            If the configuration of the root or of the renamed repository cannot be loaded.
        """
        for label, value in (("OLD", old), ("NEW", new)):
            if not matches("repository-id", value):
                raise TargetError(f"{label} {value!r} lies outside the pattern of repository-id")
        if old == new:
            raise TargetError(f"OLD and NEW are both {old}")
        members = self._scope()
        target = (renamed or self.root).resolve()
        chosen = next((item for item in members if item.root == target), None)
        if chosen is None:
            raise TargetError(f"{renamed} is neither the root nor a submodule checked out under it")
        for item in members:
            self._load(item, required=item is chosen or item.path == ROOT_PATH)
        refusals = self._identity_refusals(members, chosen, old, new)
        for item in members:
            refusals.extend(self._configuration_change(item, item is chosen, old, new))
            if item is chosen:
                refusals.extend(self._registry_change(item, old, new))
            self._target_changes(item, old, new)
            self._clone_warnings(item, old)
        return RenamePlan(
            old, new, chosen.path, tuple(item.member() for item in members), tuple(refusals)
        )

    def apply(self, plan: RenamePlan) -> bool:
        """Write the changed files at once, unless the plan is refused; return whether they were
        written."""
        if plan.refusals:
            return False
        write_atomically(self.root, plan.texts)
        return True

    # --- The scope.

    def _scope(self) -> list[_Checkout]:
        """Return the root, then each submodule of its index whose folder holds a checkout."""
        members = [_Checkout(ROOT_PATH, self.root, self.config)]
        for link in gitlinks(self.root) or ():
            folder = self.root / link.path
            if (folder / GIT_ENTRY).exists():
                members.append(_Checkout(link.path, folder.resolve()))
        return members

    def _load(self, item: _Checkout, required: bool) -> None:
        """Load the configuration and derive the identifier of a member.

        A member that the rename must edit, the root or the renamed repository, stops the plan when
        its configuration cannot be loaded; any other member is reported and left unchanged.
        """
        try:
            if item.path != ROOT_PATH:
                _, item.config_path = discover_configuration(item.root)
            if item.config_path is not None:
                item.configuration = load_configuration(item.root, item.config_path)
        except ConfigurationError as error:
            if required:
                raise ConfigurationError(f"{item.path}: {error}") from error
            item.config_path, item.configuration = None, None
            item.warnings.append(
                _warning(
                    "",
                    UNREAD_REPOSITORY,
                    f"the configuration cannot be loaded, so no citer is rewritten: {error}",
                )
            )
        declared = item.configuration.repository if item.configuration is not None else None
        # The former identifiers are left out, so that a list holding the derived identifier
        # still yields the identifier to compare.
        identity = derive_identity(
            origin_url(item.root),
            item.root.name,
            DeclaredIdentity(declared.id, ()) if declared is not None else None,
        )
        item.identifier, item.source = identity.id, identity.source

    @staticmethod
    def _identity_refusals(
        members: list[_Checkout], chosen: _Checkout, old: str, new: str
    ) -> list[str]:
        """Return the reasons refusing the rename from the identities of the members."""
        refusals: list[str] = []
        if chosen.identifier not in (old, new):
            named = (
                f"{chosen.identifier}, from its {chosen.source.value}"
                if chosen.identifier is not None
                else "nothing, since it has no identity"
            )
            refusals.append(
                f"the repository {chosen.path} is identified as {named}, neither {old} nor {new}"
            )
        declared = chosen.configuration.repository if chosen.configuration is not None else None
        if declared is not None and new in declared.retired:
            refusals.append(
                f"{new} is a former identifier of the repository {chosen.path}, and a retired "
                "identifier is never reused"
            )
        for item in members:
            if item is not chosen and item.identifier in (old, new):
                refusals.append(
                    f"the repository {item.path} is also identified as {item.identifier}"
                )
        return refusals

    # --- The configuration: the identity and the resolution context.

    def _configuration_change(
        self, item: _Checkout, renamed: bool, old: str, new: str
    ) -> list[str]:
        """Plan the edits of the configuration of a member, and return the reasons refusing them:
        the identity for the renamed repository, and the key of the context in every member."""
        configuration = item.configuration
        resolution = configuration.document.get("resolution") if configuration is not None else None
        declared = resolution.get("repositories") if isinstance(resolution, dict) else None
        keyed = isinstance(declared, dict) and old in declared
        if isinstance(declared, dict) and new in declared:
            return [
                f"{item.at_root(item.config_rel or CONFIG_FILE)} already declares {new} under "
                "resolution.repositories, so the rename would select two states of one repository"
            ]
        if not renamed and not keyed:
            return []
        if item.config_path is None or configuration is None:
            # Only the renamed repository reaches here without a file, and it gains one.
            change = _created_configuration(old)
        else:
            try:
                text = item.config_path.read_bytes().decode("utf-8")
                change = self._edit_configuration(
                    str(item.config_rel), text, renamed, keyed, old, new
                )
            # A ValueError also reports a timestamp naming an impossible date.
            except (OSError, ValueError, yaml.YAMLError) as error:
                return [
                    f"{item.at_root(str(item.config_rel))} cannot be rewritten in place: {error}"
                ]
        # An identity already recording the rename leaves the file unchanged.
        if change.edits:
            item.changes.append(change)
        rel = change.path
        if renamed and item.source is not IdentitySource.OVERRIDE and item.identifier == old:
            item.warnings.append(
                _warning(
                    rel,
                    DERIVED_IDENTITY,
                    f"the repository derives {old} from its {item.source.value}, which "
                    f"repository.retired now lists; until its remote origin names {new}, or its "
                    f"folder without a remote, every command in it stops on its identity",
                )
            )
        return []

    @staticmethod
    def _edit_configuration(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        rel: str, text: str, renamed: bool, keyed: bool, old: str, new: str
    ) -> FileChange:
        """Return the change of a configuration file, checked by parsing it again.

        Raises
        ------
        Unrewritable
            If a value cannot be located, or the new text reads otherwise than planned.
        """
        document = compose(text)
        if not isinstance(document, yaml.MappingNode):
            raise Unrewritable("the file holds no mapping")
        before = yaml.safe_load(text)
        expected = copy.deepcopy(before)
        located: list[tuple[Edit, EditKind, str, str | None, str]] = []
        if keyed:
            repositories = node_at(document, ["resolution", "repositories"])
            key = _key_node(repositories, old)
            located.append(
                (
                    replace_scalar(key, new),
                    EditKind.RESOLUTION,
                    pointer("resolution", "repositories", old),
                    old,
                    new,
                )
            )
            entries = expected["resolution"]["repositories"]
            expected["resolution"]["repositories"] = {
                (new if name == old else name): value for name, value in entries.items()
            }
        if renamed:
            located.extend(_identity_edits(text, document, expected, old, new))
        edits = [entry[0] for entry in located]
        rewritten = apply_edits(text, edits)
        if yaml.safe_load(rewritten) != expected:
            raise Unrewritable("the rewritten file does not read as the file with its new values")
        ordered = sorted(located, key=lambda entry: entry[0].start)
        lines = _lines(text, [entry[0] for entry in ordered])
        return FileChange(
            rel,
            rewritten,
            tuple(
                ValueEdit(kind, at, line, before_value, after_value)
                for (_, kind, at, before_value, after_value), line in zip(ordered, lines)
            ),
        )

    # --- The record registry.

    @staticmethod
    def _registry_change(item: _Checkout, old: str, new: str) -> list[str]:
        """Plan the edit of the key ``repository`` of the record registry of the renamed
        repository, when the registry names ``old``, and return the reason refusing it.

        A registry that cannot be read is already invalid for every resolver, so it is reported and
        left as it is. A readable registry whose key cannot be rewritten refuses the rename, since
        a resolver compares that key with the new identity.
        """
        records = item.configuration.records if item.configuration is not None else None
        if records is None or not records.path.is_file():
            return []
        reading, problem = None, ""
        try:
            text = records.path.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError) as error:
            problem = str(error)
        else:
            reading = parse_registry(text, records.rel)
            if reading.problems:
                problem = reading.problems[0].detail
        if reading is None or reading.registry is None:
            item.warnings.append(
                _warning(
                    records.rel,
                    INVALID_RECORD_REGISTRY,
                    f"the registry cannot be read, so its key repository is not rewritten: "
                    f"{problem}",
                )
            )
            return []
        if reading.registry.repository != old:
            return []
        node = node_at(compose(text), ["repository"])
        assert isinstance(node, yaml.ScalarNode)
        edit = replace_scalar(node, new)
        rewritten = apply_edits(text, [edit])
        after = parse_registry(rewritten, records.rel).registry
        if after is None or (after.repository, after.records, after.retired) != (
            new,
            reading.registry.records,
            reading.registry.retired,
        ):
            return [f"{item.at_root(records.rel)}: the key repository cannot be rewritten in place"]
        item.changes.append(
            FileChange(
                records.rel,
                rewritten,
                (
                    ValueEdit(
                        EditKind.REGISTRY, pointer("repository"), _lines(text, [edit])[0], old, new
                    ),
                ),
            )
        )
        return []

    # --- The logical targets.

    def _target_changes(self, item: _Checkout, old: str, new: str) -> None:
        """Plan the rewriting of every target of a member naming ``old``, and report the records
        that the walk cannot read and the targets that cannot be rewritten."""
        configuration = item.configuration
        if configuration is None or configuration.targets is None:
            return
        reserved = {rel for rel in (item.config_rel,) if rel is not None}
        if configuration.records is not None:
            reserved.add(configuration.records.rel)
        walk = RecordWalk(item.root, configuration.targets, frozenset(reserved))
        binding = (
            configuration.targets.records.binding
            if configuration.targets.records is not None
            else "_schema"
        )
        for record in walk.records():
            if record.problem is not None:
                item.warnings.append(
                    _warning(
                        record.rel,
                        UNREADABLE_RECORD,
                        f"{record.problem}, so whether it names {old} is unknown",
                    )
                )
                continue
            places = _citing_places(record, old)
            if not places:
                continue
            try:
                item.changes.append(
                    _rewrite_record(item.root, record, places, binding, walk, old, new)
                )
            except Unrewritable as error:
                item.warnings.extend(
                    _warning(
                        record.rel,
                        UNREWRITABLE_TARGET,
                        f"{pointer(*keys)}: the target keeps {old}: {error}",
                    )
                    for keys in places
                )
        item.warnings.extend(
            _warning(issue.rel, issue.kind, issue.detail) for issue in walk.schema_issues()
        )

    @staticmethod
    def _clone_warnings(item: _Checkout, old: str) -> None:
        """Report a machine file mapping ``old`` to a local clone, which the rename leaves."""
        configuration = item.configuration
        if configuration is None or old not in configuration.resolution.clones:
            return
        machine = configuration.resolution.machine_file
        assert machine is not None
        resolved = machine.resolve()
        rel = (
            resolved.relative_to(item.root).as_posix()
            if resolved.is_relative_to(item.root)
            else str(resolved)
        )
        item.warnings.append(
            _warning(
                rel,
                KEPT_CLONE,
                f"the machine file maps {old} to a local clone; it belongs to one machine and no "
                "commit records it, so the rename leaves it",
            )
        )


def _at_root(member: str, rel: str) -> str:
    """Return a path of a member, ``member`` being its path from the root, relative to the root."""
    return rel if member == ROOT_PATH else f"{member}/{rel}"


def _warning(rel: str, kind: str, detail: str) -> Issue:
    """Return a warning of a rename, at a path relative to its member."""
    return Issue(rel, None, kind, detail, blocking=False)


def _lines(text: str, edits: list[Edit]) -> list[int]:
    """Return the line, counted from 1, of each edited value in the text after the rename.

    The line of an edit counts the line breaks that the edits before it insert or remove. An
    insertion opening on a line break writes its value on the next line.

    Examples
    --------
    >>> text = "a:\\n  - x\\nb: y\\n"
    >>> _lines(text, [Edit(8, 8, "\\n  - z"), Edit(12, 13, "w")])
    [3, 4]
    """
    lines: list[int] = []
    for edit in edits:
        shift = sum(
            other.new.count("\n") - text.count("\n", other.start, other.end)
            for other in edits
            if other is not edit and other.end <= edit.start
        )
        own = 1 if edit.new.startswith(("\n", "\r\n")) else 0
        lines.append(text.count("\n", 0, edit.start) + 1 + shift + own)
    return lines


def _key_node(mapping: yaml.Node | None, key: str) -> yaml.ScalarNode:
    """Return the node of a key of a mapping.

    Raises
    ------
    Unrewritable
        If the node is no mapping, or holds no such key.
    """
    if isinstance(mapping, yaml.MappingNode):
        for name, _ in mapping.value:
            if isinstance(name, yaml.ScalarNode) and name.value == key:
                return name
    raise Unrewritable(f"the key {key} cannot be located")


def _identity_edits(
    text: str, document: yaml.MappingNode, expected: dict[str, Any], old: str, new: str
) -> list[tuple[Edit, EditKind, str, str | None, str]]:
    """Return the edits of the section ``repository``: the override ``old`` becomes ``new``, and
    ``old`` joins the former identifiers; ``expected`` receives the same values."""
    listed = f"[{quoted(old, None)}]"
    section = node_at(document, ["repository"])
    if section is None:
        expected["repository"] = {"retired": [old]}
        return [
            (
                add_entry(text, document, "repository", f"{{retired: {listed}}}"),
                EditKind.RETIRED,
                pointer("repository", "retired", 0),
                None,
                old,
            )
        ]
    if isinstance(section, yaml.ScalarNode):
        # A section left empty reads as null.
        expected["repository"] = {"retired": [old]}
        return [
            (
                _fill(text, section, f"{{retired: {listed}}}"),
                EditKind.RETIRED,
                pointer("repository", "retired", 0),
                None,
                old,
            )
        ]
    if not isinstance(section, yaml.MappingNode):
        raise Unrewritable("the section repository is no mapping")
    edits: list[tuple[Edit, EditKind, str, str | None, str]] = []
    values = expected["repository"]
    if values.get("id") == old:
        node = node_at(section, ["id"])
        assert isinstance(node, yaml.ScalarNode)
        values["id"] = new
        edits.append(
            (replace_scalar(node, new), EditKind.IDENTIFIER, pointer("repository", "id"), old, new)
        )
    retired = node_at(section, ["retired"])
    current = values.get("retired") or []
    if old in current:
        return edits
    at = pointer("repository", "retired", len(current))
    values["retired"] = [*current, old]
    if retired is None:
        edit = add_entry(text, section, "retired", listed)
    elif isinstance(retired, yaml.SequenceNode):
        edit = append_item(text, retired, old)
    elif isinstance(retired, yaml.ScalarNode):
        edit = _fill(text, retired, listed)
    else:
        raise Unrewritable("repository.retired is no list")
    edits.append((edit, EditKind.RETIRED, at, None, old))
    return edits


def _fill(text: str, node: yaml.ScalarNode, value: str) -> Edit:
    """Return the edit replacing a null scalar by a value; an empty null gains a space before."""
    if node.start_mark.index == node.end_mark.index:
        return Edit(node.start_mark.index, node.end_mark.index, f" {value}")
    if text[node.start_mark.index : node.end_mark.index] in ("null", "Null", "NULL", "~"):
        return Edit(node.start_mark.index, node.end_mark.index, value)
    raise Unrewritable("the value is neither a list nor empty")


def _created_configuration(old: str) -> FileChange:
    """Return the configuration created in a renamed repository that holds none."""
    text = f"_schema: {CONFIGURATION_FORMAT}\nrepository:\n  retired: [{quoted(old, None)}]\n"
    return FileChange(
        CONFIG_FILE,
        text,
        (ValueEdit(EditKind.RETIRED, pointer("repository", "retired", 0), 3, None, old),),
        created=True,
    )


def _citing_places(record: Record, old: str) -> list[tuple[str | int, ...]]:
    """Return the key path of each value of a target field of a record that is a logical target
    naming the repository ``old``."""
    places: list[tuple[str | int, ...]] = []
    for target_field in record.schema.targets if record.schema is not None else ():
        for keys, value in values_at(record.data, target_field.path):
            if target_field.conditional and not isinstance(value, dict):
                continue
            try:
                target = Target.parse(value)
            except InvalidTarget:
                continue
            if target.repository == old:
                places.append(keys)
    return places


def _rewrite_record(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    root: Path,
    record: Record,
    places: list[tuple[str | int, ...]],
    binding: str,
    walk: RecordWalk,
    old: str,
    new: str,
) -> FileChange:
    """Return the change of a record whose targets at ``places`` name ``new`` in place of
    ``old``, checked by reading the record again.

    Raises
    ------
    Unrewritable
        If the record is a TOML document, its frontmatter or a value cannot be located, or the new
        text reads otherwise than the record with its new targets.
    """
    if record.rel.endswith(TOML_SUFFIX):
        raise Unrewritable("a TOML document is not rewritten in place")
    try:
        # The bytes are decoded without translating line breaks, so each one is kept.
        text = (root / record.rel).read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise Unrewritable(f"the record cannot be read: {error}") from error
    offset, end = 0, len(text)
    if record.rel.endswith(NOTE_SUFFIX):
        span = frontmatter_span(text)
        if span is None:
            raise Unrewritable("the frontmatter cannot be located")
        offset, end = span
    try:
        block = compose(text[offset:end])
    except yaml.YAMLError as error:
        raise Unrewritable("the record cannot be composed") from error
    expected = copy.deepcopy(dict(record.data))
    edits: list[tuple[Edit, str]] = []
    for keys in places:
        node = node_at(block, [*keys, "repository"])
        if not isinstance(node, yaml.ScalarNode) or node.value != old:
            raise Unrewritable(f"the value at {pointer(*keys, 'repository')} cannot be located")
        edits.append((replace_scalar(node, new, offset), pointer(*keys, "repository")))
        _set(expected, (*keys, "repository"), new)
    rewritten = apply_edits(text, [edit for edit, _ in edits])
    ordered = sorted(edits, key=lambda entry: entry[0].start)
    source = walk.metadata.source_of(record.rel)
    after = parse_record(record.rel, rewritten.replace("\r\n", "\n"), binding, None, source)
    if after.problem is not None or dict(after.data) != expected:
        raise Unrewritable("the rewritten record does not read as the record with its new targets")
    return FileChange(
        record.rel,
        rewritten,
        tuple(
            ValueEdit(EditKind.TARGET, at, line, old, new)
            for (_, at), line in zip(ordered, _lines(text, [edit for edit, _ in ordered]))
        ),
    )


def _set(data: Any, keys: tuple[str | int, ...], value: str) -> None:
    """Set the value at a key path of nested mappings and lists."""
    node = data
    for key in keys[:-1]:
        node = node[key]
    node[keys[-1]] = value
