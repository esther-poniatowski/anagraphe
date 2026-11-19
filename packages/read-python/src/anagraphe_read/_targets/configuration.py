"""
The section ``targets`` of ``anagraphe.yml``, which enables the check of the logical targets.

The section declares three optional keys:

- ``records``, the schema registry through which a record reaches the schema of its contract, and
  the key of a record naming its contract, ``_schema`` by default, as the section ``bindings``
  declares them. Without it, the check reads the identifiers of the records and the identity of the
  repository, and finds no target field;
- ``exclude``, the files left unread by the check, after the shared exclusions;
- ``read_sides``, the declarations of the versions implemented by the other read sides of the
  repository, each a JSON or YAML file and the JSON Pointer of the mapping in it.

The section also keeps the metadata reader of the configuration, whose sources give the default
identifier of each record and make a TOML document with a ``toml`` source a record.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from anagraphe_read._core.configuration import ConfigurationError, known_keys, repository_path
from anagraphe_read._core.exclusions import Exemptions, exemptions
from anagraphe_read._core.metadata import MetadataReader
from anagraphe_read._core.schemas import RecordSchemas, parse_records
from anagraphe_read._targets.field_paths import PointerError, pointer_tokens

#: The keys of the section ``targets``.
SECTION_KEYS = frozenset({"records", "exclude", "read_sides"})
#: The keys of one declaration of a read side.
READ_SIDE_KEYS = frozenset({"path", "pointer"})


@dataclass(frozen=True)
class ReadSide:
    """The place where another read side of the repository declares its implemented versions."""

    #: The repository-relative POSIX path of the JSON or YAML file holding the declaration.
    rel: str
    path: Path
    #: The JSON Pointer of the declaration in the file.
    pointer: str


@dataclass(frozen=True)
class TargetConfig:
    """The resolved declaration of the check of the targets of one repository."""

    records: RecordSchemas | None = None
    exemptions: Exemptions = Exemptions()
    read_sides: tuple[ReadSide, ...] = ()
    #: The metadata of each file, read from the source that the repository declares for it; None
    #: for the built-in sources.
    metadata: MetadataReader | None = None


def parse_section(
    root: Path,
    raw: Mapping[str, Any],
    shared: Exemptions,
    metadata: MetadataReader | None = None,
    field_name: str = "targets",
) -> TargetConfig:
    """Validate and resolve the section ``targets``, its exemptions added to the shared ones."""
    known_keys(raw, SECTION_KEYS, field_name)
    return TargetConfig(
        records=parse_records(root, raw.get("records"), f"{field_name}.records"),
        exemptions=shared.union(
            exemptions(raw.get("exclude"), f"{field_name}.exclude", root, metadata)
        ),
        read_sides=parse_read_sides(root, raw.get("read_sides"), f"{field_name}.read_sides"),
        metadata=metadata,
    )


def parse_read_sides(root: Path, raw: Any, field_name: str) -> tuple[ReadSide, ...]:
    """Validate the declarations of the read sides: a list of mappings ``{path, pointer}``, each
    path inside the repository and each pointer a JSON Pointer."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ConfigurationError(f"{field_name} must be a list of mappings {{path, pointer}}")
    sides: list[ReadSide] = []
    for position, item in enumerate(raw):
        at = f"{field_name}[{position}]"
        if not isinstance(item, Mapping) or set(item) != READ_SIDE_KEYS:
            raise ConfigurationError(f"{at} must be a mapping with the keys path and pointer")
        path = repository_path(root, item["path"], f"{at}.path")
        if not isinstance(item["pointer"], str):
            raise ConfigurationError(f"{at}.pointer must be a JSON Pointer, such as /anagrapheRead")
        try:
            pointer_tokens(item["pointer"])
        except PointerError as error:
            raise ConfigurationError(f"{at}.pointer: {error}") from error
        sides.append(ReadSide(path.relative_to(root).as_posix(), path, item["pointer"]))
    return tuple(sides)
