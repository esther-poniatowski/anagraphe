"""
The port of a repository-state provider, and the two providers of this release.

A selected state is a full commit of a repository, with the places where a provider may find it:
a remote address and the path of a local clone. A provider reads one path of a state, and returns
its bytes and its mode, or the reason why it cannot:

- the path lies outside the state, which a provider rejects before any read;
- the state holds no file or folder at the path;
- the state is absent from the machine, its access is denied, or its bytes fail the verification
  of the provider.

The in-memory provider serves the states that a test or a conformance case declares. The empty
provider serves no state, and stands in until a provider reads Git trees, caches or bundles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Mapping, Protocol


class Mode(StrEnum):
    """The kind of entry at a path of a state, as a Git tree records it."""

    FILE = "file"
    LINK = "link"
    DIRECTORY = "directory"
    SUBMODULE = "submodule"


@dataclass(frozen=True)
class State:
    """A selected state of a repository: its full commit, and the places of its bytes."""

    commit: str
    #: The remote address of the repository, without credentials; None when none is declared.
    remote: str | None = None
    #: The path of a local clone holding the commit; None when the machine names none.
    clone: Path | None = None


@dataclass(frozen=True)
class Blob:
    """The entry at a path of a state: its bytes, empty for a folder, and its mode."""

    data: bytes
    mode: Mode = Mode.FILE


@dataclass(frozen=True)
class Missing:
    """The state holds no entry at the path."""


@dataclass(frozen=True)
class Escaping:
    """The path leaves the state, so the provider reads nothing."""


class Availability(StrEnum):
    """Why a provider cannot read a state at all."""

    #: The machine holds no copy of the state.
    ABSENT = "absent"
    #: The machine holds the state, and its access is denied.
    DENIED = "denied"
    #: The bytes of the state fail the verification of the provider.
    INVALID = "invalid"


@dataclass(frozen=True)
class Unavailable:
    """The state cannot be read: the reason, and a detail naming its cause."""

    availability: Availability
    detail: str


#: The outcome of reading one path of a state.
type Reading = Blob | Missing | Escaping | Unavailable


class StateProvider(Protocol):
    """Read the paths of selected states."""

    def read(self, state: State, path: str) -> Reading:
        """Return the entry at ``path``, relative to the root of ``state``."""
        raise NotImplementedError


def confined(path: str) -> str | None:
    """Return a path relative to the root of a state in its normal form, or None when it leaves
    the state: an absolute path, an empty path, or a path whose ``..`` climbs above the root.

    Examples
    --------
    >>> confined("notes/./a.md"), confined("notes/../a.md")
    ('notes/a.md', 'a.md')
    >>> confined("../a.md") is None, confined("/a.md") is None, confined("") is None
    (True, True, True)
    """
    pure = PurePosixPath(path)
    if not path or pure.is_absolute():
        return None
    parts: list[str] = []
    for part in pure.parts:
        if part == "..":
            if not parts:
                return None
            parts.pop()
        elif part != ".":
            parts.append(part)
    return "/".join(parts) or None


@dataclass(frozen=True)
class MemoryProvider:
    """Serve the states declared in memory, each keyed by its commit.

    Parameters
    ----------
    states : Mapping[str, Mapping[str, Blob]]
        The entries of each state, keyed by their normal path. A folder holding an entry is
        served as a folder. A path through a symbolic link to a folder escapes the state, since
        the link may lead outside it.
    denied : frozenset[str]
        The commits whose access is denied.
    invalid : frozenset[str]
        The commits whose bytes fail the verification.
    """

    states: Mapping[str, Mapping[str, Blob]] = field(default_factory=dict)
    denied: frozenset[str] = frozenset()
    invalid: frozenset[str] = frozenset()

    def read(self, state: State, path: str) -> Reading:
        """Return the entry at ``path`` of the declared state."""
        normal = confined(path)
        if normal is None:
            return Escaping()
        if state.commit in self.denied:
            return Unavailable(Availability.DENIED, f"the access to {state.commit} is denied")
        if state.commit in self.invalid:
            return Unavailable(
                Availability.INVALID, f"the bytes of {state.commit} fail their verification"
            )
        entries = self.states.get(state.commit)
        if entries is None:
            return Unavailable(Availability.ABSENT, f"no copy of {state.commit} is held")
        parts = normal.split("/")
        for depth in range(1, len(parts)):
            folder = entries.get("/".join(parts[:depth]))
            if folder is not None and folder.mode is Mode.LINK:
                return Escaping()
        if normal in entries:
            return entries[normal]
        if any(name.startswith(f"{normal}/") for name in entries):
            return Blob(b"", Mode.DIRECTORY)
        return Missing()


@dataclass(frozen=True)
class EmptyProvider:
    """Serve no state: every state is absent from the machine."""

    def read(self, state: State, path: str) -> Reading:
        """Return the absence of the state, unless the path leaves it."""
        if confined(path) is None:
            return Escaping()
        return Unavailable(
            Availability.ABSENT,
            f"no provider reading the states of other repositories is installed, so {state.commit} "
            "is not read",
        )
