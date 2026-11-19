"""
The configuration of a repository, ``anagraphe.yml``, as the read side reads it.

The file lies at ``config/tools/anagraphe.yml`` or at ``anagraphe.yml`` below the root, and both
places holding a file is an error, unless the caller names another file. The file declares its
format under ``_schema``, the sources of the metadata of its files under ``metadata``, and the files
that every section excludes under ``exclude``. The read side parses five sections:

- ``targets``, parsed by :mod:`anagraphe_read._targets.configuration`;
- ``records``, parsed by :mod:`anagraphe_read._targets.registry.configuration`, which names the
  record registry. Its records are those of the walk of the section ``targets``, so it requires
  that section;
- ``bindings``, parsed by :mod:`anagraphe_read._bindings.configuration`;
- ``resolution``, parsed by :mod:`anagraphe_read._resolution.configuration`, which declares the
  repositories that the targets name besides the submodules, and the machine file of their local
  clones;
- ``repository``, parsed by :mod:`anagraphe_read._targets.identity`, which declares the override of
  the identifier of the repository and its former identifiers;
- ``references``, of which :mod:`anagraphe_read._references.configuration` parses the syntaxes, the
  conventions, the schemes and the exclusions, which find and resolve the pointers of a file.

The format admits one more section, ``indexes``, which the command line of Anagraphe parses from
:attr:`Configuration.document`, as it parses the rest of ``references``. A section left out is None, so a repository
adopts each one apart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from anagraphe_read._bindings import configuration as bindings
from anagraphe_read._core.configuration import (
    CONFIG_LOCATIONS,
    ConfigurationError,
    known_keys,
    load_yaml,
    mapping,
)
from anagraphe_read._core.exclusions import Exemptions, exemptions
from anagraphe_read._core.metadata import MetadataReader, parse_metadata
from anagraphe_read._references.configuration import ReadReferences, parse_read_section
from anagraphe_read._resolution import configuration as resolution
from anagraphe_read._targets import configuration as targets
from anagraphe_read._targets import identity
from anagraphe_read._targets.registry import configuration as records

#: The key of ``anagraphe.yml`` naming its format.
FORMAT_KEY = "_schema"
#: The format of ``anagraphe.yml`` read by this release.
CONFIGURATION_FORMAT = "anagraphe:configuration@3"
#: The former format, whose section ``indexes`` named a vocabulary, with the changes to write.
FORMER_FORMAT = "anagraphe:configuration@2"
VOCABULARY_MOVES = (
    "indexes.vocabulary is removed",
    "the values of each key under key_values become the enum of properties.<key>, or of "
    "properties.<key>.items for a list, of a metadata schema named by indexes.metadata_schema, "
    "in their order",
    "the relations under context_relations become the enum of "
    "properties.context_relations.items.properties.relation of that schema",
    "schema.entry_point becomes indexes.entry_point",
    "schema.generated_index_areas becomes indexes.generated_areas",
    "archived_statuses becomes indexes.archived_statuses",
    "each role declaring listed: false under roles is listed under indexes.unlisted_roles",
    "schema.frames is checked by Hermeneia, and roles is no longer read",
)
#: The key that named the version of the layout before ``_schema``, rejected with its replacement.
RETIRED_FORMAT_KEY = "schema_version"
#: The top-level keys of the format of ``anagraphe.yml``.
TOP_LEVEL_KEYS = frozenset(
    {
        FORMAT_KEY,
        "metadata",
        "exclude",
        "indexes",
        "references",
        "bindings",
        "targets",
        "records",
        "resolution",
        identity.SECTION,
    }
)


@dataclass(frozen=True)
class Configuration:  # pylint: disable=too-many-instance-attributes
    """The sections of ``anagraphe.yml`` that the read side reads, None for each section left out.

    A repository without a configuration file reads as the empty configuration, ``Configuration()``.
    """

    #: The section ``targets``: the records whose targets are read, and their schema registry.
    targets: targets.TargetConfig | None = None
    #: The section ``bindings``: the key of each role, and the files that must be bound.
    bindings: bindings.BindingConfig | None = None
    #: The section ``records``: the place of the record registry.
    records: records.RecordsConfig | None = None
    #: The repositories that the targets name besides the submodules, and their local clones.
    resolution: resolution.ResolutionConfig = resolution.ResolutionConfig()
    #: The override of the identifier of the repository and its former identifiers; None when the
    #: section ``repository`` is left out.
    repository: identity.DeclaredIdentity | None = None
    #: The metadata of each file, read from the source that the repository declares for it.
    metadata: MetadataReader | None = None
    #: The files that every section excludes, declared under ``exclude``.
    exclusions: Exemptions | None = None
    #: The section ``references``, as far as it finds and resolves pointers.
    references: ReadReferences | None = None
    #: The mapping read from the file, which also holds the sections of the command line.
    document: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


def locate_config(root: Path, path: Path | None = None) -> Path:
    """Return the configuration file of the repository at ``root``.

    A given ``path`` is read from the current folder, unless it is absolute, and must name a file.
    Without one, the file is the one of ``config/tools/anagraphe.yml`` and ``anagraphe.yml`` that
    exists below the root; both existing is an error that names both.

    Raises
    ------
    ConfigurationError
        If no file lies at the given path or at the places of the search, or if both places hold
        one.
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


def holds_config(root: Path) -> bool:
    """Whether a configuration file lies at one of the places of the search below ``root``."""
    return any((root / location).is_file() for location in CONFIG_LOCATIONS)


def _require_format(raw: Mapping[str, Any]) -> None:
    """Require the format of ``anagraphe.yml``, or raise an error naming the value to write."""
    instruction = f"write {FORMAT_KEY}: {CONFIGURATION_FORMAT} as the first key of anagraphe.yml"
    if RETIRED_FORMAT_KEY in raw:
        layout = (
            "; this format holds the index keys under the section indexes, and the shared exclude "
            "at the top level"
            if raw[RETIRED_FORMAT_KEY] == 1
            else ""
        )
        raise ConfigurationError(f"{RETIRED_FORMAT_KEY} is retired: {instruction}{layout}")
    if FORMAT_KEY not in raw:
        raise ConfigurationError(f"anagraphe.yml declares no {FORMAT_KEY}: {instruction}")
    if raw[FORMAT_KEY] == FORMER_FORMAT:
        raise ConfigurationError(
            f"{FORMAT_KEY}: {FORMER_FORMAT} is retired: write {FORMAT_KEY}: {CONFIGURATION_FORMAT}"
            f"; this format moves the vocabulary into the section indexes: "
            + "; ".join(VOCABULARY_MOVES)
        )
    if raw[FORMAT_KEY] != CONFIGURATION_FORMAT:
        raise ConfigurationError(
            f"{FORMAT_KEY} must equal {CONFIGURATION_FORMAT}, not {raw[FORMAT_KEY]}"
        )


def load_configuration(root: Path, path: Path) -> Configuration:
    """Validate the configuration file of a repository, and parse the sections of the read side.

    Raises
    ------
    ConfigurationError
        If the file lies outside the repository, cannot be read, declares another format, holds an
        unknown top-level key, or holds an invalid section of the read side.
    """
    root = root.resolve()
    config_path = path.resolve()
    try:
        config_path.relative_to(root)
    except ValueError as error:
        raise ConfigurationError("configuration path must stay inside the repository") from error
    raw = load_yaml(config_path)
    _require_format(raw)
    known_keys(raw, TOP_LEVEL_KEYS, "anagraphe.yml")
    reader = MetadataReader(root, parse_metadata(raw.get("metadata"), "metadata"))
    shared = exemptions(raw.get("exclude"), "exclude", root, reader)
    configuration = Configuration(
        targets=(
            targets.parse_section(root, mapping(raw["targets"], "targets"), shared, reader)
            if "targets" in raw
            else None
        ),
        bindings=(
            bindings.parse_section(root, mapping(raw["bindings"], "bindings"), shared, reader)
            if "bindings" in raw
            else None
        ),
        records=(
            records.parse_section(root, mapping(raw["records"], "records"))
            if "records" in raw
            else None
        ),
        resolution=resolution.parse_section(
            root,
            mapping(raw["resolution"], "resolution") if "resolution" in raw else None,
        ),
        repository=(
            identity.parse_section(mapping(raw[identity.SECTION], identity.SECTION))
            if identity.SECTION in raw
            else None
        ),
        metadata=reader,
        exclusions=shared,
        references=(
            parse_read_section(root, mapping(raw["references"], "references"), shared, reader)
            if "references" in raw
            else None
        ),
        document=MappingProxyType(raw),
    )
    if configuration.records is not None and configuration.targets is None:
        raise ConfigurationError(
            "the section records reads its records through the walk of the section targets; "
            "declare targets"
        )
    return configuration
