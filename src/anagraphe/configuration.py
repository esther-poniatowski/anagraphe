"""
The configuration of a repository for the command line: the sections of the read side, composed
by the read distribution, and the sections of the commands that write.

The read distribution locates ``anagraphe.yml``, checks its format and its top-level keys, and
parses the sections ``targets``, ``records``, ``bindings``, ``resolution`` and ``repository``, as
:mod:`anagraphe_read._configuration` states. Its composition, :func:`anagraphe_read._repository.compose`,
builds the identity of the repository, the walk of its records, its resolution context and its
resolvers. The command line adds two sections, parsed from the same file:

- ``indexes``, parsed by :mod:`anagraphe.indexes.configuration`;
- ``references``, parsed by :mod:`anagraphe.references.configuration`.

The root of a command is the folder given by ``--root``, else by the variable ``ANAGRAPHE_ROOT``,
else the nearest folder, from the current one upwards, that holds the file at one of its places,
else the current folder. A command requires one section among ``indexes``, ``references``,
``bindings``, ``targets`` and ``records``. A section left out disables its subpackage, so a
repository adopts each one apart. When the sections ``indexes`` and ``targets`` are both declared, a
nested group of an index designates a parent by the identifier that the targets resolve, so
``x-identifier`` applies there too.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from anagraphe_read._bindings.configuration import BindingConfig
from anagraphe_read._configuration import holds_config, load_configuration
from anagraphe_read._core.configuration import ConfigurationError, mapping
from anagraphe_read._core.metadata import MetadataReader
from anagraphe_read._repository import Composition, compose
from anagraphe_read._resolution.configuration import ResolutionConfig
from anagraphe_read._resolution.provider import StateProvider
from anagraphe_read._targets.configuration import TargetConfig
from anagraphe_read._targets.identity import DeclaredIdentity
from anagraphe_read._targets.registry.configuration import RecordsConfig

from anagraphe.indexes import configuration as indexes
from anagraphe.references import configuration as references

#: The environment variable naming the root, read when the command line gives none.
ROOT_VARIABLE = "ANAGRAPHE_ROOT"
#: The sections of ``anagraphe.yml`` that enable a command, one per capability.
SECTIONS = ("indexes", "references", "bindings", "targets", "records")


@dataclass(frozen=True)
class RepositoryConfig:
    """The resolved configuration of one repository, None for each section left out.

    The sections of the read side, and the objects built from them, come from the composition of
    the read distribution.
    """

    #: The composition of the read side: its sections, the identity and the resolvers.
    reading: Composition
    indexes: indexes.IndexConfig | None = None
    references: references.ReferenceConfig | None = None

    @property
    def bindings(self) -> BindingConfig | None:
        """Return the section ``bindings``."""
        return self.reading.configuration.bindings

    @property
    def targets(self) -> TargetConfig | None:
        """Return the section ``targets``."""
        return self.reading.configuration.targets

    @property
    def records(self) -> RecordsConfig | None:
        """Return the section ``records``."""
        return self.reading.configuration.records

    @property
    def resolution(self) -> ResolutionConfig:
        """Return the repositories that the targets name besides the submodules."""
        return self.reading.configuration.resolution

    @property
    def repository(self) -> DeclaredIdentity | None:
        """Return the section ``repository``: the override of the identifier and its former
        identifiers."""
        return self.reading.configuration.repository

    @property
    def metadata(self) -> MetadataReader | None:
        """Return the reader of the metadata of each file."""
        return self.reading.configuration.metadata


def find_root(start: Path) -> Path:
    """Return the root of a command that names none: the nearest folder holding a configuration.

    The search runs from ``start`` up to the top of the file system, and stops at the first folder
    holding a file at one of the places of the search. Without such a folder, the root is
    ``start``.
    """
    start = start.resolve()
    for folder in (start, *start.parents):
        if holds_config(folder):
            return folder
    return start


def load_config(root: Path, path: Path, provider: StateProvider | None = None) -> RepositoryConfig:
    """Validate and resolve the configuration of a repository.

    The provider reads the selected states of other repositories, the Git provider of the read
    distribution by default.
    """
    reading = compose(root, load_configuration(root, path), provider)
    root = reading.root
    read = reading.configuration
    raw, shared, reader = read.document, read.exclusions, read.metadata
    # A configuration loaded from a file holds its shared exclusions and its metadata reader.
    assert shared is not None and reader is not None
    # The metadata schema of the indexes resolves an absolute $ref through the schema registry of
    # the records, as the targets declare it, else as the bindings declare it.
    records_schemas = next(
        (
            section.records
            for section in (read.targets, read.bindings)
            if section is not None and section.records is not None
        ),
        None,
    )
    config = RepositoryConfig(
        reading,
        indexes=(
            indexes.parse_section(
                root,
                mapping(raw["indexes"], "indexes"),
                shared,
                reader,
                registry=records_schemas.registry if records_schemas is not None else None,
            )
            if "indexes" in raw
            else None
        ),
        references=(
            references.parse_section(root, mapping(raw["references"], "references"), shared, reader)
            if "references" in raw
            else None
        ),
    )
    if not any(name in raw for name in SECTIONS):
        raise ConfigurationError(f"anagraphe.yml declares no section: {', '.join(SECTIONS)}")
    if config.indexes is not None and reading.walk is not None:
        # A nested group designates a parent by the identifier that the targets resolve.
        config = replace(
            config, indexes=replace(config.indexes, identifiers=reading.walk.identifier)
        )
    return config
