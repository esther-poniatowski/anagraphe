"""
The section ``indexes`` of ``anagraphe.yml``.

The section names the index-type schemas of the repository and, optionally, the metadata schema
whose enumerations give the closed value sets of the metadata keys, as
:mod:`anagraphe.indexes.value_sets` reads them. It declares the file name of an index under
``entry_point``, the areas whose indexes are generated, the statuses of an archived note, the roles
that an index lists in its control block alone, the types of the files that an index lists, the
task states, the build manifests and the migration classes. Its paths are exempted in addition to
the paths that the whole configuration exempts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from anagraphe_read._core.conditions import FILE_KEYS, Condition, parse_condition
from anagraphe_read._core.configuration import (
    ConfigurationError,
    known_keys,
    load_yaml,
    mapping,
    repository_path,
    strings,
    strings_in_order,
)
from anagraphe_read._core.exclusions import Exemptions, exemptions
from anagraphe_read._core.filters import scalar
from anagraphe_read._core.metadata import MetadataReader

from anagraphe.indexes.retired import MIGRATABLE_KEYS, MigrationClass
from anagraphe.indexes.value_sets import ValueSets, read_value_sets

#: The keys of the section ``indexes``.
SECTION_KEYS = frozenset(
    {
        "entry_point",
        "index_types",
        "metadata_schema",
        "generated_areas",
        "archived_statuses",
        "unlisted_roles",
        "exclude",
        "task_states",
        "sequences",
        "migrations",
        "inspect_git",
        "members",
    }
)
#: The key of the status of a note, whose enumeration bounds the archived statuses.
STATUS_KEY = "status"


@dataclass(frozen=True)
class MemberRule:
    """A condition on the files that an index lists, and the keys that each must declare."""

    condition: Condition
    #: The keys that a member declares at its top level, such as the block ``metadata``.
    keys: frozenset[str] = frozenset()


#: The keys of a member rule: the keys of a condition on a file, and the declared keys.
MEMBER_KEYS = FILE_KEYS | {"keys"}
#: The files that an index lists by default: its Markdown notes and its YAML records.
DEFAULT_MEMBERS = (MemberRule(Condition(types=frozenset({"md", "yml", "yaml"}))),)


@dataclass(frozen=True)
class IndexConfig:
    """The resolved inputs of the index generator, supplied by one consuming repository."""

    #: The file name of an index, such as ``_index.md``.
    entry_point: str
    index_types: Path
    #: The paths excluded from member discovery and index processing.
    exemptions: Exemptions
    task_states: Mapping[str, bool]
    #: The build manifest of each folder: its member paths in order, relative to the folder.
    sequences: Mapping[str, tuple[str, ...]]
    #: The closed value sets read from the metadata schema; empty without one.
    value_sets: ValueSets = field(default_factory=ValueSets)
    #: The top-level areas whose every index must hold the region of its groups.
    generated_areas: frozenset[str] = frozenset()
    #: The statuses of an archived note, the only notes that may declare ``superseded_by``.
    archived_statuses: tuple[str, ...] = ()
    #: The roles that an index lists in its control block, never as entries, such as a worklog.
    unlisted_roles: frozenset[str] = frozenset()
    #: The files tolerating a retired key until a declared migration.
    migrations: tuple[MigrationClass, ...] = ()
    inspect_git: bool = True
    #: The rules selecting the files that an index lists; one holding rule suffices.
    members: tuple[MemberRule, ...] = DEFAULT_MEMBERS
    #: The metadata of each file, read from its declared source.
    metadata: MetadataReader | None = None
    #: The identifier of a file, as the check of the targets resolves it; None for the key ``id``
    #: of the metadata source of the file.
    identifiers: Callable[[str], Any] | None = None

    def is_member(self, rel: str) -> bool:
        """Whether an index lists a file of its folder, by the type, path, metadata or declared
        keys of the file."""
        return any(
            rule.condition.holds(rel, self.metadata)
            and (
                not rule.keys
                or (self.metadata is not None and rule.keys <= self.metadata.declared_keys(rel))
            )
            for rule in self.members
        )

    def sequence_for(self, root: Path, folder: Path) -> tuple[str, ...] | None:
        """Return the build manifest of a folder, whose key is relative to the repository root."""
        key = folder.relative_to(root).as_posix()
        return self.sequences.get("" if key == "." else key)


def _archived(value: Any, sets: ValueSets, field_name: str) -> tuple[str, ...]:
    """Return the archived statuses, each among the enumerated statuses when the schema declares
    them."""
    archived = tuple(scalar(item) for item in strings_in_order(value, field_name))
    statuses = sets.values.get(STATUS_KEY)
    undeclared = [item for item in archived if statuses is not None and item not in statuses]
    if undeclared:
        raise ConfigurationError(
            f"{field_name} names a status outside the enumeration of status in the metadata "
            f"schema: {', '.join(undeclared)}"
        )
    return archived


def _entry_point(value: Any, field_name: str) -> str:
    """Return the file name of an index, a non-empty name without a folder."""
    if not isinstance(value, str) or not value or "/" in value:
        raise ConfigurationError(f"{field_name} must name the file of an index, such as _index.md")
    return value


def _migrations(value: Any, field: str) -> tuple[MigrationClass, ...]:
    """Return the declared migration classes, each tolerating one migratable retired key."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ConfigurationError(f"{field} must be a list of mappings {{key, paths, awaits}}")
    classes: list[MigrationClass] = []
    for number, entry in enumerate(value, start=1):
        item = f"{field}[{number}]"
        if not isinstance(entry, Mapping) or set(entry) != {"key", "paths", "awaits"}:
            raise ConfigurationError(f"{item} must declare exactly key, paths and awaits")
        if entry["key"] not in MIGRATABLE_KEYS:
            raise ConfigurationError(
                f"{item}.key must name a migratable retired key: "
                f"{', '.join(sorted(MIGRATABLE_KEYS))}"
            )
        patterns = strings(entry["paths"], f"{item}.paths")
        if not patterns:
            raise ConfigurationError(f"{item}.paths must list at least one pattern")
        if not isinstance(entry["awaits"], str) or not entry["awaits"].strip():
            raise ConfigurationError(f"{item}.awaits must name the migration awaited")
        classes.append(MigrationClass(str(entry["key"]), tuple(sorted(patterns)), entry["awaits"]))
    return tuple(classes)


def _task_states(root: Path, value: Any, field: str) -> dict[str, bool]:
    """Load the task states that a file maps from task identifiers to completion."""
    if value is None:
        return {}
    task_raw = load_yaml(repository_path(root, value, field))
    if any(
        not isinstance(key, str) or not isinstance(state, bool) for key, state in task_raw.items()
    ):
        raise ConfigurationError(f"{field} must map string identifiers to booleans")
    return dict(task_raw)


def _sequences(value: Any, field: str) -> dict[str, tuple[str, ...]]:
    """Return the build manifest of each folder, keyed by the folder without its final slash."""
    sequences: dict[str, tuple[str, ...]] = {}
    for folder, members in mapping(value, field).items():
        if not isinstance(folder, str):
            raise ConfigurationError(f"each {field} key must be a repository-relative folder")
        if not isinstance(members, list) or any(not isinstance(item, str) for item in members):
            raise ConfigurationError(f"{field}.{folder} must be a list of member paths")
        sequences[folder.rstrip("/")] = tuple(members)
    return sequences


def parse_section(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    root: Path,
    raw: Mapping[str, Any],
    shared: Exemptions,
    metadata: MetadataReader | None = None,
    field: str = "indexes",
    registry: Path | None = None,
) -> IndexConfig:
    """Validate and resolve the section ``indexes``, its exemptions added to the shared ones.

    The metadata schema resolves an absolute ``$ref`` through ``registry``, the schema registry of
    the records, when the configuration declares one.
    """
    known_keys(raw, SECTION_KEYS, field)
    inspect_git = raw.get("inspect_git", True)
    if not isinstance(inspect_git, bool):
        raise ConfigurationError(f"{field}.inspect_git must be a boolean")
    if "entry_point" not in raw:
        raise ConfigurationError(
            f"{field}.entry_point must name the file of an index, such as _index.md"
        )
    sets = (
        read_value_sets(
            root,
            repository_path(root, raw["metadata_schema"], f"{field}.metadata_schema"),
            registry,
        )
        if raw.get("metadata_schema") is not None
        else ValueSets()
    )
    return IndexConfig(
        entry_point=_entry_point(raw["entry_point"], f"{field}.entry_point"),
        value_sets=sets,
        generated_areas=frozenset(strings(raw.get("generated_areas"), f"{field}.generated_areas")),
        archived_statuses=_archived(
            raw.get("archived_statuses"), sets, f"{field}.archived_statuses"
        ),
        unlisted_roles=frozenset(strings(raw.get("unlisted_roles"), f"{field}.unlisted_roles")),
        index_types=repository_path(root, raw.get("index_types"), f"{field}.index_types"),
        exemptions=shared.union(exemptions(raw.get("exclude"), f"{field}.exclude", root, metadata)),
        task_states=_task_states(root, raw.get("task_states"), f"{field}.task_states"),
        sequences=_sequences(raw.get("sequences"), f"{field}.sequences"),
        migrations=_migrations(raw.get("migrations"), f"{field}.migrations"),
        inspect_git=inspect_git,
        members=_members(raw.get("members"), f"{field}.members"),
        metadata=metadata,
    )


def _members(value: Any, field: str) -> tuple[MemberRule, ...]:
    """Parse the rules selecting the files that an index lists, the default when absent."""
    if value is None:
        return DEFAULT_MEMBERS
    if not isinstance(value, list) or not value:
        raise ConfigurationError(
            f"{field} must list at least one condition, such as {{types: [md, yml, yaml]}}"
        )
    rules: list[MemberRule] = []
    for number, entry in enumerate(value, start=1):
        condition, extra = parse_condition(entry, f"{field}[{number}]", MEMBER_KEYS)
        keys = strings(extra.pop("keys", None), f"{field}[{number}].keys")
        rules.append(MemberRule(condition, frozenset(keys)))
    return tuple(rules)
