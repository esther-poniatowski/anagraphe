"""
The resolution context of a root: the selected state of each repository that its targets may name.

The context belongs to the root checked by the command, so one commit of a repository resolves
alike in every clone of it. It holds two kinds of entry:

- a derived entry for each submodule of the root. The gitlink in the index selects the commit, and
  the manifest at that commit, read through the provider, names the repository. A gitlink whose
  manifest cannot be read names no repository, and the context keeps it as unnamed;
- a declared entry for each repository of the section ``resolution``, with its full commit, its
  remote address and, when the machine file names one, its local clone.

A derived and a declared entry of one identifier, or two derived entries of one identifier, stop
the command, since the context would select two states of one repository.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from anagraphe.core.configuration import ConfigurationError
from anagraphe.core.git_state import gitlinks
from anagraphe.resolution.configuration import ResolutionConfig
from anagraphe.resolution.provider import Blob, Mode, State, StateProvider, Unavailable
from anagraphe.targets.manifest import MANIFEST_FILE, Manifest, parse_manifest


@dataclass(frozen=True)
class Entry:
    """The selected state of one repository, and where the context found it."""

    repository: str
    state: State
    #: The origin of the entry: ``submodule <path>`` or ``resolution.repositories``.
    origin: str


@dataclass(frozen=True)
class Unnamed:
    """A submodule whose manifest at its commit names no repository, and why."""

    path: str
    commit: str
    detail: str


@dataclass(frozen=True)
class ResolutionContext:
    """The repositories that the targets of one root may name, each with its selected state."""

    #: The identifier of the root, None when it declares none.
    repository: str | None = None
    #: The former identifiers of the root.
    retired: tuple[str, ...] = ()
    entries: Mapping[str, Entry] = field(default_factory=dict)
    #: The submodules naming no repository, which leave the context incomplete.
    unnamed: tuple[Unnamed, ...] = ()


def build_context(
    root: Path,
    manifest: Manifest | None,
    config: ResolutionConfig | None,
    provider: StateProvider,
) -> ResolutionContext:
    """Return the context of the root, its submodules named through the provider.

    Raises
    ------
    ConfigurationError
        If two entries select states of one repository, or an entry names the root itself.
    """
    config = config if config is not None else ResolutionConfig()
    entries: dict[str, Entry] = {}
    unnamed: list[Unnamed] = []
    own = manifest.id if manifest is not None else None

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

    for link in gitlinks(root) or ():
        state = State(link.commit, clone=root / link.path)
        named = _manifest_identifier(provider, state)
        if isinstance(named, str):
            add(Entry(named, state, f"submodule {link.path}"))
        else:
            unnamed.append(Unnamed(link.path, link.commit, named.detail))
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
        manifest.retired if manifest is not None else (),
        entries,
        tuple(unnamed),
    )


@dataclass(frozen=True)
class _Unnamed:
    """Why the manifest of a state names no repository."""

    detail: str


def _manifest_identifier(provider: StateProvider, state: State) -> str | _Unnamed:
    """Return the identifier declared by the manifest of a state, or why it declares none."""
    reading = provider.read(state, MANIFEST_FILE)
    if isinstance(reading, Unavailable):
        return _Unnamed(reading.detail)
    if not isinstance(reading, Blob) or reading.mode is not Mode.FILE:
        return _Unnamed(f"the state holds no file {MANIFEST_FILE}")
    try:
        text = reading.data.decode("utf-8")
    except UnicodeDecodeError:
        return _Unnamed(f"{MANIFEST_FILE} of the state is not UTF-8 text")
    parsed = parse_manifest(text)
    if parsed.manifest is None:
        return _Unnamed(f"{MANIFEST_FILE} of the state is invalid")
    return parsed.manifest.id
