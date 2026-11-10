"""
The configuration of a repository, ``anagraphe.yml``, composed of one section per subpackage.

The file lies at ``config/tools/anagraphe.yml`` or at ``anagraphe.yml`` below the root, and both
places holding a file is an error, unless the command line names another file. The root of a
command is the folder given by ``--root``, else by the variable ``ANAGRAPHE_ROOT``, else the
nearest folder, from the current one upwards, that holds the file at one of its places, else the
current folder. The file declares its ``schema_version``, the sources of the metadata of its files
under ``metadata``, the files that every subpackage excludes under ``exclude``, then the section of
each subpackage that the repository uses:

- ``indexes``, parsed by :mod:`anagraphe.indexes.configuration`;
- ``references``, parsed by :mod:`anagraphe.references.configuration`;
- ``bindings``, parsed by :mod:`anagraphe.bindings.configuration`.

A section left out disables its subpackage, so a repository adopts each one apart.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from anagraphe.core.configuration import (
    ConfigurationError,
    known_keys,
    load_yaml,
    mapping,
)
from anagraphe.core.exclusions import exemptions
from anagraphe.core.metadata import MetadataReader, parse_metadata
from anagraphe.bindings import configuration as bindings
from anagraphe.indexes import configuration as indexes
from anagraphe.references import configuration as references

#: The name of the configuration file.
CONFIG_FILE = "anagraphe.yml"
#: The places of the configuration below the root.
CONFIG_LOCATIONS = (Path("config/tools") / CONFIG_FILE, Path(CONFIG_FILE))
#: The environment variable naming the root, read when the command line gives none.
ROOT_VARIABLE = "ANAGRAPHE_ROOT"
#: The version of the layout of ``anagraphe.yml`` read by this release.
SCHEMA_VERSION = 2
#: The top-level keys of ``anagraphe.yml``.
TOP_LEVEL_KEYS = frozenset(
    {"schema_version", "metadata", "exclude", "indexes", "references", "bindings"}
)


@dataclass(frozen=True)
class RepositoryConfig:
    """The resolved configuration of one repository, None for each section left out."""

    indexes: indexes.IndexConfig | None = None
    references: references.ReferenceConfig | None = None
    bindings: bindings.BindingConfig | None = None
    #: The metadata of each file, read from the source that the repository declares for it.
    metadata: MetadataReader | None = None


def find_root(start: Path) -> Path:
    """Return the root of a command that names none: the nearest folder holding a configuration.

    The search runs from ``start`` up to the top of the file system, and stops at the first folder
    holding a file at one of :data:`CONFIG_LOCATIONS`. Without such a folder, the root is
    ``start``.
    """
    start = start.resolve()
    for folder in (start, *start.parents):
        if any((folder / location).is_file() for location in CONFIG_LOCATIONS):
            return folder
    return start


def locate_config(root: Path, path: Path | None = None) -> Path:
    """Return the configuration file of the repository at ``root``.

    A given ``path`` is read from the current folder, unless it is absolute, and must name a file.
    Without one, the file is the one of ``config/tools/anagraphe.yml`` and ``anagraphe.yml`` that
    exists below the root; both existing is an error that names both.
    """
    if path is not None:
        given = path.absolute()
        if not given.is_file():
            raise ConfigurationError(f"no configuration file at {path}")
        return given
    found = [root / location for location in CONFIG_LOCATIONS if (root / location).is_file()]
    if len(found) > 1:
        raise ConfigurationError(
            "two configuration files: " + " and ".join(str(item) for item in found) + "; keep one"
        )
    if found:
        return found[0]
    places = " or ".join(location.as_posix() for location in CONFIG_LOCATIONS)
    raise ConfigurationError(f"no configuration file at {places} below {root}")


def load_config(root: Path, path: Path) -> RepositoryConfig:
    """Validate and resolve the configuration of a repository."""
    root = root.resolve()
    config_path = path.resolve()
    try:
        config_path.relative_to(root)
    except ValueError as error:
        raise ConfigurationError("configuration path must stay inside the repository") from error
    raw = load_yaml(config_path)
    version = raw.get("schema_version")
    if version == 1:
        raise ConfigurationError(
            "schema_version 1 is retired: version 2 holds the index keys under the section "
            "indexes, and the shared exclude at the top level"
        )
    if version != SCHEMA_VERSION:
        raise ConfigurationError(f"schema_version must equal {SCHEMA_VERSION}")
    known_keys(raw, TOP_LEVEL_KEYS, "anagraphe.yml")
    reader = MetadataReader(root, parse_metadata(raw.get("metadata"), "metadata"))
    shared = exemptions(raw.get("exclude"), "exclude", root, reader)
    config = RepositoryConfig(
        indexes=(
            indexes.parse_section(root, mapping(raw["indexes"], "indexes"), shared, reader)
            if "indexes" in raw
            else None
        ),
        references=(
            references.parse_section(root, mapping(raw["references"], "references"), shared, reader)
            if "references" in raw
            else None
        ),
        bindings=(
            bindings.parse_section(root, mapping(raw["bindings"], "bindings"), shared, reader)
            if "bindings" in raw
            else None
        ),
        metadata=reader,
    )
    if config.indexes is None and config.references is None and config.bindings is None:
        raise ConfigurationError("anagraphe.yml declares no section: indexes, references, bindings")
    return config
