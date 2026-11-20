"""
The resolution context of a root: the selected state of each repository that its targets may name.

The context belongs to the root checked by the command, so one commit of a repository resolves
alike in every clone of it. It holds two kinds of entry:

- a derived entry for each submodule of the root. The gitlink in the index selects the commit. The
  address of the submodule in ``.gitmodules`` is its remote, a relative address being resolved
  against the remote of the root. The identity of the state names the repository: the override
  ``repository.id`` of the configuration at that commit, read through the provider, else the name
  of its remote. A gitlink whose state cannot be read, or yields no identity, names no repository,
  and the context keeps it as unnamed, with its remote, so that a fetch can supply its state;
- a declared entry for each repository of the section ``resolution``, with its full commit, its
  remote address and, when the machine file names one, its local clone.

A derived and a declared entry of one identifier, or two derived entries of one identifier, stop
the command, since the context would select two states of one repository.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

import yaml
from hodegos import DiscoveryError
from hodegos.declaration import DECLARATION_PLACES, read_declared_folders
from hodegos.discovery import DOT_CONFIG

from anagraphe_read._core.configuration import (
    CONFIG_FILE,
    ConfigurationError,
    discover_configuration,
)
from anagraphe_read._core.git_state import default_remote_url, gitlinks, submodule_urls
from anagraphe_read._resolution.configuration import ResolutionConfig, remote_problem
from anagraphe_read._resolution.provider import (
    Blob,
    Escaping,
    Missing,
    Mode,
    State,
    StateProvider,
    Unavailable,
)
from anagraphe_read._targets.identity import Identity, state_identity


@dataclass(frozen=True)
class Entry:
    """The selected state of one repository, and where the context found it."""

    repository: str
    state: State
    #: The origin of the entry: ``submodule <path>`` or ``resolution.repositories``.
    origin: str


@dataclass(frozen=True)
class Unnamed:
    """A submodule whose state at its commit names no repository, and why."""

    path: str
    commit: str
    detail: str
    #: The remote of the submodule, None when ``.gitmodules`` names no usable address.
    remote: str | None = None


@dataclass(frozen=True)
class ResolutionContext:
    """The repositories that the targets of one root may name, each with its selected state."""

    #: The identifier of the root, None when it has no identity.
    repository: str | None = None
    #: The former identifiers of the root.
    retired: tuple[str, ...] = ()
    entries: Mapping[str, Entry] = field(default_factory=dict)
    #: The submodules naming no repository, which leave the context incomplete.
    unnamed: tuple[Unnamed, ...] = ()

    def states(self) -> list[tuple[str, State]]:
        """Return every state of the context, each with the label that a report names it by: the
        entries by their identifier, then the unnamed submodules by their path."""
        labelled = [
            (f"{identifier} ({entry.origin})", entry.state)
            for identifier, entry in sorted(self.entries.items())
        ]
        labelled.extend(
            (f"submodule {item.path}", State(item.commit, item.remote, None))
            for item in self.unnamed
        )
        return labelled


def build_context(
    root: Path,
    identity: Identity | None,
    config: ResolutionConfig | None,
    provider: StateProvider,
) -> ResolutionContext:
    """Return the context of the root, its submodules named through the provider.

    The identity of the root, None for a root without identity, supplies its identifier and its
    former identifiers.

    Raises
    ------
    ConfigurationError
        If two entries select states of one repository, or an entry names the root itself.
    """
    config = config if config is not None else ResolutionConfig()
    entries: dict[str, Entry] = {}
    unnamed: list[Unnamed] = []
    own = identity.id if identity is not None else None

    def add(entry: Entry) -> None:
        if entry.repository == own:
            raise ConfigurationError(
                f"{entry.origin} names {own}, the repository of the root itself"
            )
        if entry.repository in entries:
            raise ConfigurationError(
                f"{entries[entry.repository].origin} and {entry.origin} both select a state of "
                f"{entry.repository}; keep one"
            )
        entries[entry.repository] = entry

    links = gitlinks(root) or ()
    urls = submodule_urls(root) if links else {}
    base = default_remote_url(root) if links else None
    for link in links:
        remote = submodule_remote(urls.get(link.path), base)
        state = State(link.commit, remote, root / link.path)
        named = _state_identifier(provider, state)
        if isinstance(named, str):
            add(Entry(named, state, f"submodule {link.path}"))
        else:
            unnamed.append(Unnamed(link.path, link.commit, named.detail, remote))
    for identifier, declared in sorted(config.repositories.items()):
        add(
            Entry(
                identifier,
                State(declared.commit, declared.remote, config.clones.get(identifier)),
                "resolution.repositories",
            )
        )
    return ResolutionContext(
        own,
        identity.retired if identity is not None else (),
        entries,
        tuple(unnamed),
    )


def submodule_remote(url: str | None, base: str | None) -> str | None:
    """Return the remote of a submodule: its address, a relative one resolved against the remote of
    the root, as Git resolves it; None when no usable address results.

    Each ``../`` removes the last component of the remote of the root, and ``./`` removes none.

    Examples
    --------
    >>> submodule_remote("../notes.git", "git@github.com:lab/vault.git")
    'git@github.com:lab/notes.git'
    >>> submodule_remote("../notes.git", "https://github.com/lab/vault.git")
    'https://github.com/lab/notes.git'
    >>> submodule_remote("./notes.git", "https://github.com/lab/vault")
    'https://github.com/lab/vault/notes.git'
    >>> submodule_remote("https://h.org/a.git", None)
    'https://h.org/a.git'
    >>> submodule_remote("../../../x.git", "https://github.com/lab/vault.git") is None
    True
    """
    if url is None:
        return None
    if url.startswith(("./", "../")):
        if base is None:
            return None
        resolved = base.rstrip("/")
        separator = "/"
        while url.startswith(("./", "../")):
            if url.startswith("./"):
                url = url[2:]
                continue
            url = url[3:]
            scheme = resolved.find("://")
            floor = scheme + 3 if scheme >= 0 else 0
            # In the scp form host:path, the colon also separates a component.
            cut = max(resolved.rfind("/"), -1 if scheme >= 0 else resolved.rfind(":"))
            if cut < floor:
                return None
            separator = resolved[cut]
            resolved = resolved[:cut]
        url = f"{resolved}{separator}{url}"
    return url if remote_problem(url) is None else None


@dataclass(frozen=True)
class Unreadable:
    """Why the configuration of a state cannot be read: the reading of an unavailable state, or a
    defect of the file."""

    detail: str
    reading: Unavailable | None = None


def read_configuration(
    provider: StateProvider, state: State
) -> tuple[str, Mapping[str, Any]] | Unreadable | None:
    """Return the place and the content of the configuration of Anagraphe at a state, None when
    no place of the state holds one.

    Hodegos locates the file at the root of the state as it locates it in a working tree: at
    ``anagraphe.yml``, in ``.config/``, or in a folder that the ``hodegos.yml`` of the state
    declares. Since Hodegos reads a file system, the declarations of the state, then the files at
    the places of the state, are copied into a temporary folder, in which Hodegos applies its rules.
    Two configuration files, an invalid declaration, a folder or a link at a place, and a file that
    is not a YAML mapping in UTF-8 make the configuration unreadable.
    """
    copied: dict[str, bytes] = {}
    with tempfile.TemporaryDirectory(prefix="anagraphe-state-") as folder:
        tree = Path(folder)
        declarations = [place.as_posix() for place in DECLARATION_PLACES]
        problem = _copy(provider, state, tree, declarations, copied)
        if problem is not None:
            return problem
        try:
            bases = (PurePosixPath(), PurePosixPath(DOT_CONFIG), *read_declared_folders(tree))
            places = [(base / CONFIG_FILE).as_posix() for base in bases]
            problem = _copy(provider, state, tree, places, copied)
            if problem is not None:
                return problem
            _, found = discover_configuration(tree)
        except (ConfigurationError, DiscoveryError) as error:
            # Hodegos names the copies; the state names its own paths.
            return Unreadable(str(error).replace(f"{tree}{os.sep}", ""))
    if found is None:
        return None
    name = found.relative_to(tree).as_posix()
    data = copied[name]
    try:
        parsed = yaml.safe_load(data.decode("utf-8"))
    except (ValueError, yaml.YAMLError):
        # ValueError covers bytes that are not UTF-8, and a timestamp naming an impossible date.
        parsed = None
    if not isinstance(parsed, dict):
        return Unreadable(f"{name} cannot be parsed as a mapping")
    return name, parsed


def _copy(
    provider: StateProvider,
    state: State,
    tree: Path,
    names: list[str],
    copied: dict[str, bytes],
) -> Unreadable | None:
    """Copy the files of a state at ``names`` below ``tree``, recording their bytes in ``copied``,
    or return why the configuration of the state cannot be read."""
    for name in names:
        reading = provider.read(state, name)
        if isinstance(reading, Unavailable):
            return Unreadable(reading.detail, reading)
        if isinstance(reading, Missing):
            continue
        if isinstance(reading, Escaping):
            return Unreadable(f"{name} leaves the state")
        if reading.mode is not Mode.FILE:
            return Unreadable(f"{name} is a {reading.mode.value}, not a file")
        path = tree / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(reading.data)
        copied[name] = reading.data
    return None


@dataclass(frozen=True)
class _Unnamed:
    """Why the state of a submodule names no repository."""

    detail: str


def _state_identifier(provider: StateProvider, state: State) -> str | _Unnamed:
    """Return the identifier of the identity of a state, or why the state names no repository."""
    configuration = read_configuration(provider, state)
    if isinstance(configuration, Unreadable):
        return _Unnamed(configuration.detail)
    name, data = configuration if configuration is not None else ("", None)
    try:
        identity = state_identity(state.remote, data)
    except ConfigurationError as error:
        return _Unnamed(f"{name} of the state: {error}")
    if identity.id is None:
        return _Unnamed(
            "the configuration of the state declares no repository.id, and its remote names no "
            "repository identifier"
        )
    return identity.id
