"""
The section ``bindings`` of ``anagraphe.yml``: where the texts of a repository declare their bindings.

The section declares three things:

- ``index``, the file name of the index of a directory, whose declarations bind every text below it;
- ``roles``, each role read by a tool, with the ``key`` holding it in the frontmatter of a text, and,
  under ``required``, a condition on the files that must be bound;
- ``records``, the schema registry through which a record finds the fields marked by ``x-binds``,
  and the key of a record naming its contract, ``_schema`` by default.

An ``exclude`` mapping adds files left unread by the check, after the shared exclusions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from anagraphe.bindings.model import ROLE_PATTERN
from anagraphe.core.conditions import Condition, parse_condition
from anagraphe.core.configuration import (
    ConfigurationError,
    known_keys,
    mapping,
    repository_path,
)
from anagraphe.core.exclusions import Exemptions, exemptions
from anagraphe.core.metadata import MetadataReader

#: The keys of the section ``bindings``.
SECTION_KEYS = frozenset({"index", "roles", "records", "exclude"})
#: The keys of one role.
ROLE_KEYS = frozenset({"key", "required"})
#: The keys of the declaration of records.
RECORD_KEYS = frozenset({"registry", "binding"})
#: The key of a record naming its contract, as the schema registry of Kleisis writes it by default.
DEFAULT_BINDING = "_schema"


@dataclass(frozen=True)
class RoleSpec:
    """Where the files of a repository declare one role, and which files must be bound."""

    #: The key holding the role in the frontmatter of a text.
    key: str
    #: The files that must be bound for the role; None when no file must be.
    required: Condition | None = None


@dataclass(frozen=True)
class RecordSchemas:
    """The schema registry of the records, and the key of a record naming its contract."""

    registry: Path
    binding: str = DEFAULT_BINDING


@dataclass(frozen=True)
class BindingConfig:
    """The resolved declaration of the bindings of one repository."""

    #: The file name of the index of a directory.
    index: str
    roles: Mapping[str, RoleSpec] = field(default_factory=dict)
    records: RecordSchemas | None = None
    exemptions: Exemptions = Exemptions()
    #: The metadata of each file, read from its declared source.
    metadata: MetadataReader | None = None


def _roles(value: Any, field_name: str) -> dict[str, RoleSpec]:
    """Parse the declared roles, each named ``<tool>.<name>``."""
    roles: dict[str, RoleSpec] = {}
    for name, entry in mapping(value, field_name).items():
        item = f"{field_name}.{name}"
        if not isinstance(name, str) or not ROLE_PATTERN.fullmatch(name):
            raise ConfigurationError(
                f"{item} must name a role as <tool>.<name>, such as onomasia.glossary"
            )
        raw = mapping(entry, item)
        known_keys(raw, ROLE_KEYS, item)
        key = raw.get("key")
        if not isinstance(key, str) or not key:
            raise ConfigurationError(f"{item}.key must name the key holding the role")
        required = (
            parse_condition(raw["required"], f"{item}.required")[0]
            if raw.get("required") is not None
            else None
        )
        roles[name] = RoleSpec(key, required)
    return roles


def _records(root: Path, value: Any, field_name: str) -> RecordSchemas | None:
    """Parse the declaration of records, None when the section declares none."""
    if value is None:
        return None
    raw = mapping(value, field_name)
    known_keys(raw, RECORD_KEYS, field_name)
    registry = repository_path(root, raw.get("registry"), f"{field_name}.registry")
    if not registry.is_file():
        raise ConfigurationError(f"{field_name}.registry names no file: {raw.get('registry')}")
    binding = raw.get("binding", DEFAULT_BINDING)
    if not isinstance(binding, str) or not binding:
        raise ConfigurationError(f"{field_name}.binding must name the key of a record's contract")
    return RecordSchemas(registry, binding)


def parse_section(
    root: Path,
    raw: Mapping[str, Any],
    shared: Exemptions,
    metadata: MetadataReader | None = None,
    field_name: str = "bindings",
) -> BindingConfig:
    """Validate and resolve the section ``bindings``, its exemptions added to the shared ones."""
    known_keys(raw, SECTION_KEYS, field_name)
    index = raw.get("index")
    if not isinstance(index, str) or not index or "/" in index:
        raise ConfigurationError(
            f"{field_name}.index must name the file of a directory index, such as _index.md"
        )
    return BindingConfig(
        index=index,
        roles=_roles(raw.get("roles"), f"{field_name}.roles"),
        records=_records(root, raw.get("records"), f"{field_name}.records"),
        exemptions=shared.union(
            exemptions(raw.get("exclude"), f"{field_name}.exclude", root, metadata)
        ),
        metadata=metadata,
    )
