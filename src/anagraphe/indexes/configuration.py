"""
The section ``indexes`` of ``anagraphe.yml``, and the vocabulary that it names.

The section names the vocabulary and the index-type schemas of the repository, and declares the
types of the files that an index lists, the task states, the build manifests and the migration
classes. Its paths are exempted in addition to the paths that the whole configuration exempts.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from anagraphe.core.configuration import (
    ConfigurationError,
    known_keys,
    load_yaml,
    mapping,
    repository_path,
    strings,
)
from anagraphe.core.conditions import Condition, parse_condition
from anagraphe.core.exclusions import Exemptions, exemptions
from anagraphe.core.filters import scalar
from anagraphe.core.metadata import MetadataReader
from anagraphe.indexes.fields import declared_values
from anagraphe.indexes.retired import MIGRATABLE_KEYS, RETIRED_VOCABULARY, MigrationClass

#: The keys of the section ``indexes``.
SECTION_KEYS = frozenset(
    {
        "vocabulary",
        "index_types",
        "exclude",
        "task_states",
        "sequences",
        "migrations",
        "inspect_git",
        "members",
    }
)
#: The files that an index lists by default: its Markdown notes and its YAML records.
DEFAULT_MEMBERS = (Condition(types=frozenset({"md", "yml", "yaml"})),)


@dataclass(frozen=True)
class IndexConfig:
    """The resolved inputs of the index generator, supplied by one consuming repository."""

    vocabulary: Path
    index_types: Path
    #: The paths excluded from member discovery and index processing.
    exemptions: Exemptions
    task_states: Mapping[str, bool]
    #: The build manifest of each folder: its member paths in order, relative to the folder.
    sequences: Mapping[str, tuple[str, ...]]
    #: The files tolerating a retired key until a declared migration.
    migrations: tuple[MigrationClass, ...] = ()
    inspect_git: bool = True
    #: The conditions selecting the files that an index lists; one holding condition suffices.
    members: tuple[Condition, ...] = DEFAULT_MEMBERS
    #: The metadata of each file, read from its declared source.
    metadata: MetadataReader | None = None

    def is_member(self, rel: str) -> bool:
        """Whether an index lists a file of its folder, by the type, path or metadata of the file."""
        return any(condition.holds(rel, self.metadata) for condition in self.members)

    def sequence_for(self, root: Path, folder: Path) -> tuple[str, ...] | None:
        """Return the build manifest of a folder, whose key is relative to the repository root."""
        key = folder.relative_to(root).as_posix()
        return self.sequences.get("" if key == "." else key)


def load_vocabulary(path: Path) -> dict[str, Any]:
    """Load one vocabulary file or merge the YAML files of one directory."""
    if path.is_file():
        return load_yaml(path)
    if not path.is_dir():
        raise ConfigurationError(f"vocabulary path does not exist: {path}")
    merged: dict[str, Any] = {}
    files = sorted((*path.glob("*.yml"), *path.glob("*.yaml")))
    if not files:
        raise ConfigurationError(f"vocabulary directory contains no YAML files: {path}")
    for file in files:
        part = load_yaml(file)
        for key, value in part.items():
            if key not in merged:
                merged[key] = value
                continue
            if not isinstance(merged[key], dict) or not isinstance(value, dict):
                raise ConfigurationError(f"{file.name} declares {key} again")
            for subkey, subvalue in value.items():
                if subkey in merged[key]:
                    raise ConfigurationError(f"{file.name} declares {key}.{subkey} again")
                merged[key][subkey] = subvalue
    return merged


def validate_vocabulary(raw: Mapping[str, Any], path: Path) -> None:
    """Require the vocabulary fields consumed by the generic renderer, and no retired section."""
    for section, replacement in RETIRED_VOCABULARY.items():
        if section in raw:
            raise ConfigurationError(
                f"{path} declares the retired section {section}: {replacement}"
            )
    schema = raw.get("schema")
    if not isinstance(schema, Mapping):
        raise ConfigurationError(f"{path} must declare schema as a mapping")
    entry_point = schema.get("entry_point")
    if not isinstance(entry_point, str) or not entry_point:
        raise ConfigurationError(f"{path} must declare schema.entry_point as a non-empty string")
    roles = raw.get("roles", {})
    if not isinstance(roles, Mapping) or any(
        not isinstance(name, str) or not isinstance(spec, Mapping) for name, spec in roles.items()
    ):
        raise ConfigurationError(f"{path} roles must map names to mappings")
    key_values = raw.get("key_values", {})
    if not isinstance(key_values, Mapping) or any(
        not isinstance(values, (Mapping, list)) for values in key_values.values()
    ):
        raise ConfigurationError(
            f"{path} key_values must map each key to a list of values or to a mapping of glosses"
        )
    relations = raw.get("context_relations", [])
    if not isinstance(relations, (Mapping, list)):
        raise ConfigurationError(
            f"{path} context_relations must list relation names or map them to glosses"
        )
    _validate_archived(raw, path)


def _validate_archived(raw: Mapping[str, Any], path: Path) -> None:
    """Require the archived statuses to be a list, each among the declared statuses if any."""
    archived = raw.get("archived_statuses", [])
    if not isinstance(archived, list) or any(
        isinstance(item, (list, Mapping)) for item in archived
    ):
        raise ConfigurationError(f"{path} archived_statuses must list status values")
    statuses = (raw.get("key_values") or {}).get("status")
    if statuses is None:
        return
    declared = set(declared_values(statuses))
    undeclared = [str(item) for item in archived if scalar(item) not in declared]
    if undeclared:
        raise ConfigurationError(
            f"{path} archived_statuses names a status outside key_values.status: "
            f"{', '.join(undeclared)}"
        )


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


def parse_section(
    root: Path,
    raw: Mapping[str, Any],
    shared: Exemptions,
    metadata: MetadataReader | None = None,
    field: str = "indexes",
) -> IndexConfig:
    """Validate and resolve the section ``indexes``, its exemptions added to the shared ones."""
    known_keys(raw, SECTION_KEYS, field)
    inspect_git = raw.get("inspect_git", True)
    if not isinstance(inspect_git, bool):
        raise ConfigurationError(f"{field}.inspect_git must be a boolean")
    return IndexConfig(
        vocabulary=repository_path(root, raw.get("vocabulary"), f"{field}.vocabulary"),
        index_types=repository_path(root, raw.get("index_types"), f"{field}.index_types"),
        exemptions=shared.union(exemptions(raw.get("exclude"), f"{field}.exclude", root, metadata)),
        task_states=_task_states(root, raw.get("task_states"), f"{field}.task_states"),
        sequences=_sequences(raw.get("sequences"), f"{field}.sequences"),
        migrations=_migrations(raw.get("migrations"), f"{field}.migrations"),
        inspect_git=inspect_git,
        members=_members(raw.get("members"), f"{field}.members"),
        metadata=metadata,
    )


def _members(value: Any, field: str) -> tuple[Condition, ...]:
    """Parse the conditions selecting the files that an index lists, the default when absent."""
    if value is None:
        return DEFAULT_MEMBERS
    if not isinstance(value, list) or not value:
        raise ConfigurationError(
            f"{field} must list at least one condition, such as {{types: [md, yml, yaml]}}"
        )
    return tuple(
        parse_condition(entry, f"{field}[{number}]")[0]
        for number, entry in enumerate(value, start=1)
    )
