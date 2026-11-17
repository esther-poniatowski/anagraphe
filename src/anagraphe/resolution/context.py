"""
The resolution context of a root: the selected state of each repository that its targets may name.

The context belongs to the root checked by the command, so one commit of a repository resolves
alike in every clone of it. It holds two kinds of entry:

- a derived entry for each submodule of the root. The gitlink in the index selects the commit, and
  the manifest at that commit, read through the provider, names the repository. The address of the
  submodule in ``.gitmodules`` is its remote, a relative address being resolved against the
  remote of the root. A gitlink whose manifest cannot be read names no repository, and the context
  keeps it as unnamed, with its remote, so that a fetch can supply its state;
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
from anagraphe.core.git_state import default_remote_url, gitlinks, submodule_urls
from anagraphe.resolution.configuration import ResolutionConfig, remote_problem
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
    #: The remote of the submodule, None when ``.gitmodules`` names no usable address.
    remote: str | None = None


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

    links = gitlinks(root) or ()
    urls = submodule_urls(root) if links else {}
    base = default_remote_url(root) if links else None
    for link in links:
        remote = submodule_remote(urls.get(link.path), base)
        state = State(link.commit, remote, root / link.path)
        named = _manifest_identifier(provider, state)
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
        manifest.retired if manifest is not None else (),
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
