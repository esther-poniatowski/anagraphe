"""Repository-owned configuration for Anagraphe."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

import yaml


class ConfigurationError(ValueError):
    """Report an invalid Anagraphe configuration with an actionable message."""


@dataclass(frozen=True)
class Exemptions:
    """Paths excluded from member discovery and index processing."""

    directories: frozenset[str] = frozenset()
    files: frozenset[str] = frozenset()
    basenames: frozenset[str] = frozenset()

    def contains(self, path: Path) -> bool:
        """Return whether a repository-relative path is excluded."""
        posix = PurePosixPath(path.as_posix())
        return (
            posix.as_posix() in self.files
            or posix.name in self.basenames
            or posix.name.startswith(".")
            or any(part in self.directories for part in posix.parts)
        )


@dataclass(frozen=True)
class RepositoryConfig:
    """Resolved inputs supplied by one consuming repository."""

    vocabulary: Path
    index_types: Path
    exemptions: Exemptions
    task_states: Mapping[str, bool]
    sequences: Mapping[str, tuple[str, ...]]
    inspect_git: bool = True

    def sequence_for(self, root: Path, folder: Path) -> tuple[str, ...] | None:
        """Return the sequence configured for a folder, relative to the repository root."""
        key = folder.relative_to(root).as_posix()
        return self.sequences.get("" if key == "." else key)


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    """Return a mapping field or raise a configuration error."""
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"{field} must be a mapping")
    return value


def _strings(value: Any, field: str) -> frozenset[str]:
    """Return a sequence of strings as a frozen set."""
    if value is None:
        return frozenset()
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ConfigurationError(f"{field} must be a list of strings")
    return frozenset(value)


def _repository_path(root: Path, value: str, field: str) -> Path:
    """Resolve a declared path and require it to remain inside the repository."""
    relative = Path(value)
    if relative.is_absolute():
        raise ConfigurationError(f"{field} must be a repository-relative path")
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ConfigurationError(f"{field} must stay inside the repository: {value}") from error
    return resolved


def load_yaml(path: Path) -> dict[str, Any]:
    """Load one YAML mapping from disk."""
    try:
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ConfigurationError(f"cannot read {path}: {error}") from error
    except yaml.YAMLError as error:
        raise ConfigurationError(f"cannot parse {path}: {error}") from error
    if not isinstance(parsed, dict):
        raise ConfigurationError(f"{path} must contain a YAML mapping")
    return parsed


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
    """Require the vocabulary fields consumed by the generic renderer."""
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


def load_config(root: Path, path: Path) -> RepositoryConfig:
    """Validate and resolve an Anagraphe configuration."""
    root = root.resolve()
    config_path = path.resolve()
    try:
        config_path.relative_to(root)
    except ValueError as error:
        raise ConfigurationError("configuration path must stay inside the repository") from error
    raw = load_yaml(config_path)
    if raw.get("schema_version") != 1:
        raise ConfigurationError("schema_version must equal 1")
    for field in ("vocabulary", "index_types"):
        if not isinstance(raw.get(field), str) or not raw[field]:
            raise ConfigurationError(f"{field} must be a non-empty repository-relative path")

    exclusions = _mapping(raw.get("exclude"), "exclude")
    exemptions = Exemptions(
        directories=_strings(exclusions.get("directories"), "exclude.directories"),
        files=_strings(exclusions.get("files"), "exclude.files"),
        basenames=_strings(exclusions.get("basenames"), "exclude.basenames"),
    )

    task_states: dict[str, bool] = {}
    task_path = raw.get("task_states")
    if task_path is not None:
        if not isinstance(task_path, str):
            raise ConfigurationError("task_states must be a repository-relative path")
        task_raw = load_yaml(_repository_path(root, task_path, "task_states"))
        if any(
            not isinstance(key, str) or not isinstance(value, bool)
            for key, value in task_raw.items()
        ):
            raise ConfigurationError("task_states must map string identifiers to booleans")
        task_states = dict(task_raw)

    sequence_raw = _mapping(raw.get("sequences"), "sequences")
    sequences: dict[str, tuple[str, ...]] = {}
    for folder, members in sequence_raw.items():
        if not isinstance(folder, str):
            raise ConfigurationError("each sequences key must be a repository-relative folder")
        if not isinstance(members, list) or any(not isinstance(item, str) for item in members):
            raise ConfigurationError(f"sequences.{folder} must be a list of member paths")
        sequences[folder.rstrip("/")] = tuple(members)

    inspect_git = raw.get("inspect_git", True)
    if not isinstance(inspect_git, bool):
        raise ConfigurationError("inspect_git must be a boolean")
    return RepositoryConfig(
        vocabulary=_repository_path(root, raw["vocabulary"], "vocabulary"),
        index_types=_repository_path(root, raw["index_types"], "index_types"),
        exemptions=exemptions,
        task_states=task_states,
        sequences=sequences,
        inspect_git=inspect_git,
    )
