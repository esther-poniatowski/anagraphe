"""
The section ``records`` of ``anagraphe.yml``, which enables the commands of the record registry.

The section declares one optional key, ``path``, the file of the registry relative to the root,
``record-registry.yml`` by default. The walk of the records is that of the section ``targets``,
with its exclusions and its schema registry, so the section ``records`` requires that section.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from anagraphe_read._core.configuration import ConfigurationError, known_keys, repository_path

#: The keys of the section ``records``.
SECTION_KEYS = frozenset({"path"})
#: The file of the registry when the section names none, at the root.
DEFAULT_PATH = "record-registry.yml"


@dataclass(frozen=True)
class RecordsConfig:
    """The resolved declaration of the record registry of one repository."""

    #: The file of the registry, resolved below the root.
    path: Path
    #: The same file, relative to the root, as the findings name it.
    rel: str


def parse_section(root: Path, raw: Mapping[str, Any], field_name: str = "records") -> RecordsConfig:
    """Validate and resolve the section ``records``.

    Raises
    ------
    ConfigurationError
        If the section declares another key, or a path that is empty, absolute or outside the
        repository.
    """
    known_keys(raw, SECTION_KEYS, field_name)
    path = repository_path(root, raw.get("path", DEFAULT_PATH), f"{field_name}.path")
    if path == root or path.is_dir():
        raise ConfigurationError(f"{field_name}.path must name a file, not a folder")
    return RecordsConfig(path, path.relative_to(root).as_posix())
