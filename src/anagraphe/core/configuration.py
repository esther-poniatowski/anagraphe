"""
Primitives of the configuration of a repository, shared by every subpackage.

Each subpackage parses its own section of ``anagraphe.yml`` with these primitives, so that a
malformed value raises the same error, with the same wording, in every section.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml


class ConfigurationError(ValueError):
    """Report an invalid Anagraphe configuration with an actionable message."""


def mapping(value: Any, field: str) -> Mapping[str, Any]:
    """Return a mapping field, an absent field as an empty mapping, or raise."""
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"{field} must be a mapping")
    return value


def strings(value: Any, field: str) -> frozenset[str]:
    """Return a list of strings as a frozen set, an absent field as an empty set, or raise."""
    if value is None:
        return frozenset()
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ConfigurationError(f"{field} must be a list of strings")
    return frozenset(value)


def strings_in_order(value: Any, field_name: str) -> tuple[str, ...]:
    """Return a list of strings in its order, an absent field as an empty tuple, or raise."""
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ConfigurationError(f"{field_name} must be a list of strings")
    return tuple(value)


def known_keys(raw: Mapping[str, Any], allowed: frozenset[str], field: str) -> None:
    """Reject a key outside the keys of a section, so that a misspelled key fails loudly."""
    unknown = sorted(str(key) for key in raw if key not in allowed)
    if unknown:
        raise ConfigurationError(
            f"{field} declares unknown keys: {', '.join(unknown)}; "
            f"admitted keys: {', '.join(sorted(allowed))}"
        )


def repository_path(root: Path, value: Any, field: str) -> Path:
    """Resolve a declared path and require it to remain inside the repository."""
    if not isinstance(value, str) or not value:
        raise ConfigurationError(f"{field} must be a non-empty repository-relative path")
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
