"""
The composition of the read side of one repository, and the facade that the interface exposes.

The composition builds, from the configuration of a repository and a state provider, the objects
that every reader of the repository needs: the identity of the repository, the walk of its records
with the declarations of their contracts, the key binding a record to its contract, the resolution
context, the record resolver and the binding resolver. Each object is built at its first use, and
once. The command line of Anagraphe and :func:`open_repository` both build their objects through
:func:`compose`, so the wiring exists once.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any

from anagraphe_read._bindings.model import Binding, Role
from anagraphe_read._bindings.resolution import BindingResolver
from anagraphe_read._configuration import (
    Configuration,
    holds_config,
    load_configuration,
    locate_config,
)
from anagraphe_read._core.configuration import ConfigurationError
from anagraphe_read._core.published import ADDRESSING_FILE, schema
from anagraphe_read._core.schemas import DEFAULT_BINDING
from anagraphe_read._resolution.context import ResolutionContext, build_context
from anagraphe_read._resolution.git import GitProvider, default_cache
from anagraphe_read._resolution.provider import StateProvider
from anagraphe_read._resolution.resolver import RecordRead, RecordResolver, Resolution
from anagraphe_read._targets.declarations import Declarations
from anagraphe_read._targets.identity import Identity, repository_identity
from anagraphe_read._targets.model import Target
from anagraphe_read._targets.positions import position
from anagraphe_read._targets.walk import RecordWalk


def git_provider(cache: Path | None = None) -> StateProvider:
    """Return the Git provider of ADR 0010, which reads the clone of each state, then the cache.

    The cache is the folder named by the variable ``ANAGRAPHE_CACHE``, else ``anagraphe/states``
    below the cache folder of the user, unless ``cache`` names another bare repository. The
    provider reads offline; ``anagraphe states fetch`` fills the cache.
    """
    return GitProvider(cache if cache is not None else default_cache())


def addressing_schema() -> dict[str, Any]:
    """Return a copy of the resource ``addressing.v1``, whose ``$id`` is ``ADDRESSING_ID``.

    A consumer registers the resource under its ``$id`` in the schema registry of its validator, so
    that a schema referencing the definition ``target`` resolves without a network access.

    Examples
    --------
    >>> addressing_schema()["$id"].endswith("addressing.v1.schema.yml")
    True
    """
    return copy.deepcopy(schema(ADDRESSING_FILE))


@dataclass(frozen=True)
class RecordFile:
    """A record of the repository read as a file: its path, the contract that it names, its data.

    Attributes
    ----------
    path : str
        The path of the file, relative to the root, written with ``/``.
    contract : str | None
        The value of the binding key of the record, None when the record names no contract.
    data : Mapping[str, Any]
        The frontmatter of a note, or the top-level mapping of a document; empty when it holds none.
    identifier : str | None
        The identifier of the record when its schema declares the field by ``x-identifier`` and
        the record holds a string there, None otherwise.
    problem : str | None
        Why the record cannot be read, None when it can.
    """

    path: str
    contract: str | None
    data: Mapping[str, Any]
    identifier: str | None = None
    problem: str | None = None
    root: Path = field(default=Path("."), repr=False, compare=False)

    def position(self, path: Sequence[str | int]) -> tuple[int, int] | None:
        """Return the line and the column, from 1, where the node at a positional path opens.

        A step that leaves the data, such as the name of a missing field, stops at the closest
        existing ancestor. The data as a whole, and a file that cannot be composed, have no
        position.
        """
        return position(self.root, self.path, path)


@dataclass
class Composition:
    """The objects of the read side of one repository, each built at its first use.

    Parameters
    ----------
    root : Path
        The root of the repository, resolved.
    configuration : Configuration
        The sections of ``anagraphe.yml`` that the read side reads.
    provider : StateProvider
        The reader of the selected states of other repositories.
    """

    root: Path
    configuration: Configuration
    provider: StateProvider

    @cached_property
    def identity(self) -> Identity:
        """Return the identity of the repository, derived from the section ``repository``, the
        remote ``origin`` and the folder of the root.

        Raises
        ------
        ConfigurationError
            If the former identifiers list the derived identifier.
        """
        return repository_identity(self.root, self.configuration.repository)

    @cached_property
    def walk(self) -> RecordWalk | None:
        """Return the walk of the records of the section ``targets``, None without the section.

        The record registry named by the section ``records`` is no record of the walk.
        """
        targets = self.configuration.targets
        if targets is None:
            return None
        registry = self.configuration.records
        reserved = frozenset({registry.rel}) if registry is not None else frozenset()
        return RecordWalk(self.root, targets, reserved)

    @property
    def declarations(self) -> Declarations | None:
        """Return the declarations of the contracts of the schema registry of the section
        ``targets``, None when the section declares no schema registry."""
        return self.walk.declarations if self.walk is not None else None

    @property
    def binding(self) -> str:
        """Return the key of a record naming its contract, ``_schema`` by default."""
        targets = self.configuration.targets
        if targets is not None and targets.records is not None:
            return targets.records.binding
        return DEFAULT_BINDING

    @cached_property
    def context(self) -> ResolutionContext:
        """Return the resolution context of the root: its submodules, named through the provider,
        and the repositories of the section ``resolution``.

        Raises
        ------
        ConfigurationError
            If two entries select states of one repository, or an entry names the root itself.
        """
        return build_context(self.root, self.identity, self.configuration.resolution, self.provider)

    @cached_property
    def resolver(self) -> RecordResolver:
        """Return the record resolver of the root, its context built at the first call."""
        return RecordResolver(self.context, self.provider, self.declarations, self.binding)

    @cached_property
    def binding_resolver(self) -> BindingResolver:
        """Return the resolver of the bindings of the texts.

        Raises
        ------
        ConfigurationError
            If the configuration declares no section ``bindings``.
        """
        if self.configuration.bindings is None:
            raise ConfigurationError("anagraphe.yml declares no section bindings")
        return BindingResolver(self.root, self.configuration.bindings)


def compose(
    root: Path, configuration: Configuration, provider: StateProvider | None = None
) -> Composition:
    """Return the composition of the read side of the repository at ``root``.

    Without a provider, the composition reads the states of other repositories through
    :func:`git_provider`.
    """
    return Composition(
        root.resolve(), configuration, provider if provider is not None else git_provider()
    )


class Repository:
    """A repository opened for reading: its identity, its targets, its records and its bindings.

    :func:`open_repository` builds a repository. Every operation reads the files of the root, or
    the selected states of other repositories through the provider; none writes a file.
    """

    def __init__(self, composition: Composition) -> None:
        self._composition = composition

    @property
    def root(self) -> Path:
        """Return the root of the repository, resolved."""
        return self._composition.root

    @property
    def identity(self) -> Identity:
        """Return the identity of the repository: its identifier, its former identifiers, the
        source of the identifier and its problems.

        Raises
        ------
        ConfigurationError
            If the former identifiers list the derived identifier.
        """
        return self._composition.identity

    @property
    def configuration(self) -> Configuration:
        """Return the sections of ``anagraphe.yml`` that the read side reads."""
        return self._composition.configuration

    @property
    def roles(self) -> tuple[str, ...]:
        """Return the roles that the section ``bindings`` declares, none without the section."""
        bindings = self._composition.configuration.bindings
        return tuple(bindings.roles) if bindings is not None else ()

    def resolve(self, target: Target) -> Resolution:
        """Return the state, and the registered record, of a target.

        A target of the repository itself, or of one of its former identifiers, resolves to the
        outcome ``local``, which the reader resolves in its own working tree.

        Raises
        ------
        ConfigurationError
            If the resolution context selects two states of one repository, or names the root.
        """
        return self._composition.resolver.resolve(target)

    def read(
        self, resolution: Resolution, contracts: tuple[tuple[str, ...], ...] = ()
    ) -> RecordRead:
        """Return the verified bytes of the record of a resolved target.

        Parameters
        ----------
        resolution : anagraphe_read.Resolution
            The resolution of the target, whose outcome is ``record``.
        contracts : tuple of tuple of str
            The entries of each ``x-target-contract`` declared on the citing field; none admits
            every contract.

        Raises
        ------
        ValueError
            If the resolution places no record.
        """
        return self._composition.resolver.read(resolution, contracts)

    def bindings(self, path: str, role: Role) -> Binding:
        """Return the values bound to a text for a role, resolved along the directory chain.

        Parameters
        ----------
        path : str
            The path of the text, relative to the root, written with ``/``.
        role : Role
            The role, with its merge rule.

        Raises
        ------
        ConfigurationError
            If the configuration declares no section ``bindings``, or no key for the role.
        ValueError
            If the path is absolute, or leaves the repository.
        """
        return self._composition.binding_resolver.resolve(path, role)

    @property
    def binding(self) -> str:
        """Return the key of a record naming its contract, ``_schema`` by default."""
        return self._composition.binding

    @property
    def schema_registry(self) -> Path | None:
        """Return the schema registry through which a record reaches the schema of its contract,
        None when the section ``targets`` declares none."""
        targets = self._composition.configuration.targets
        if targets is None or targets.records is None:
            return None
        return targets.records.registry

    def records(self) -> tuple[RecordFile, ...]:
        """Return every record of the repository, in the sorted order of the walk.

        The walk excludes the files that the configuration exempts, the record registry, and the
        files of nested repositories.

        Raises
        ------
        ConfigurationError
            If the configuration declares no section ``targets``.
        """
        walk = self._composition.walk
        if walk is None:
            raise ConfigurationError("anagraphe.yml declares no section targets")
        return tuple(
            RecordFile(
                record.rel,
                record.contract if isinstance(record.contract, str) else None,
                record.data,
                (
                    record.identifier
                    if record.declared and isinstance(record.identifier, str) and record.identifier
                    else None
                ),
                record.problem,
                self.root,
            )
            for record in walk.records()
        )


def open_repository(
    root: Path, *, config: Path | None = None, provider: StateProvider | None = None
) -> Repository:
    """Open the repository at ``root`` for reading.

    The configuration is the file ``config``, read from the current folder, else the file found at
    ``config/tools/anagraphe.yml`` or ``anagraphe.yml`` below the root. A root holding neither
    opens with the empty configuration, so that its submodules still resolve. The provider reads
    the selected states of other repositories, :func:`git_provider` by default.

    Raises
    ------
    ConfigurationError
        If the configuration is invalid, or both places of the search hold a file.
    """
    resolved = root.resolve()
    if config is None and not holds_config(resolved):
        configuration = Configuration()
    else:
        configuration = load_configuration(resolved, locate_config(resolved, config))
    return Repository(compose(resolved, configuration, provider))
