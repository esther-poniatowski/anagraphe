"""
The Git provider of ADR 0010: the selected states read from Git object stores, and their fetch.

A state is read from the first store that holds its commit: the clone of its entry, then the cache
of the machine. The cache is one bare Git repository shared by every root of the machine. Its
objects are addressed by their hashes, so the states of several repositories share it safely, and
the state of a submodule enters it before its manifest names the repository.

The provider reads the object database, never a working tree. It hashes every object that it reads,
the commit, each tree along the path and the file, and compares the hash with the identifier that
named the object. Therefore, a store returns the bytes of the selected commit or a failure, whatever
its files hold.

The fetch is the only operation that uses the network. It fetches a commit with its tree alone, by
its full identifier, from the address that the context supplies. It runs with ``fetch.fsckObjects``,
records no remote in the cache, and keeps each fetched commit under a reference, so that a garbage
collection of the cache keeps it. Credentials come from the configuration of Git on the machine, and
Git never prompts for one.
"""

from __future__ import annotations

import hashlib
import os
import platform
import re
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Callable, Iterable, Mapping

from anagraphe.core.git_state import isolated_environment
from anagraphe.resolution.provider import (
    Availability,
    Blob,
    Escaping,
    Missing,
    Mode,
    Reading,
    State,
    Unavailable,
    confined,
)

#: The environment variable naming the cache, which replaces the folder of the user.
CACHE_VARIABLE = "ANAGRAPHE_CACHE"
#: The prefix of the references keeping the fetched commits in the cache.
STATE_REFERENCES = "refs/anagraphe/states"
#: The command that fills the cache, named in the detail of an absent state.
FETCH_COMMAND = "anagraphe states fetch"
#: The mode of each kind of entry of a Git tree.
TREE_MODES = {
    b"40000": Mode.DIRECTORY,
    b"100644": Mode.FILE,
    b"100755": Mode.FILE,
    b"120000": Mode.LINK,
    b"160000": Mode.SUBMODULE,
}
#: The hash function of an object identifier, by the length of its hexadecimal form.
HASHES = {40: "sha1", 64: "sha256"}


def default_cache(environment: Mapping[str, str] | None = None) -> Path:
    """Return the cache of the machine: the folder named by ``ANAGRAPHE_CACHE``, else
    ``anagraphe/states`` below the cache folder of the user.

    The cache folder of the user is ``~/Library/Caches`` on macOS, ``%LOCALAPPDATA%`` on Windows,
    and ``$XDG_CACHE_HOME`` or ``~/.cache`` elsewhere.
    """
    variables = os.environ if environment is None else environment
    if variables.get(CACHE_VARIABLE):
        return Path(variables[CACHE_VARIABLE]).expanduser()
    system = platform.system()
    if system == "Darwin":
        base = Path.home() / "Library" / "Caches"
    elif system == "Windows" and variables.get("LOCALAPPDATA"):
        base = Path(variables["LOCALAPPDATA"])
    else:
        base = Path(variables.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "anagraphe" / "states"


class _Store:
    """One Git object store, read through ``git cat-file --batch`` and verified by hashing."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder

    def read(self, commit: str, path: str) -> Reading | None:
        """Return the entry at ``path`` of the commit, or None when the store lacks the commit."""
        return self._session(commit, lambda walk: walk.entry(path))

    def holds(self, commit: str) -> bool:
        """Whether the store holds the commit and its root tree, both verified."""
        return self._session(commit, lambda walk: walk.root()) is True

    def _session[T](self, commit: str, action: Callable[[_Walk], T]) -> T | Unavailable:
        """Run an action on the objects of a commit, through one batch process of the store."""
        try:
            process = subprocess.Popen(  # pylint: disable=consider-using-with
                ["git", "cat-file", "--batch"],
                cwd=self.folder,
                env=isolated_environment(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as error:
            return Unavailable(Availability.ABSENT, f"Git cannot run: {error}")
        try:
            return action(_Walk(process, commit))
        except _Failure as failure:
            return failure.reading
        finally:
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
            process.wait()


class _Failure(Exception):
    """Stop a walk with the reading that reports its failure."""

    def __init__(self, reading: Unavailable) -> None:
        super().__init__(reading.detail)
        self.reading = reading


class _Walk:  # pylint: disable=too-few-public-methods
    """The objects of one commit, requested in order from one batch process."""

    def __init__(self, process: subprocess.Popen[bytes], commit: str) -> None:
        self.process = process
        self.commit = commit

    def root(self) -> bool | None:
        """Return True when the store holds the commit and its root tree, None when it lacks the
        commit."""
        tree = self._root_tree()
        if tree is None:
            return None
        self._tree(tree)
        return True

    def entry(self, path: str) -> Reading | None:
        """Return the entry at a path of the commit, None when the store lacks the commit."""
        tree = self._root_tree()
        if tree is None:
            return None
        parts = path.split("/")
        for depth, part in enumerate(parts):
            entries = self._tree(tree)
            if part.encode() not in entries:
                return Missing()
            mode, identifier = entries[part.encode()]
            last = depth == len(parts) - 1
            if last:
                return self._entry(mode, identifier)
            if mode is Mode.LINK:
                return Escaping()
            if mode is not Mode.DIRECTORY:
                return Missing()
            tree = identifier
        return Missing()

    def _root_tree(self) -> str | None:
        """Return the identifier of the root tree of the commit, None when the store lacks it."""
        found = self._object(self.commit)
        if found is None:
            return None
        kind, data = found
        if kind != b"commit":
            raise _Failure(_invalid(f"{self.commit} names a {kind.decode()}, not a commit"))
        match = re.match(rb"tree ([0-9a-f]+)\n", data)
        if match is None:
            raise _Failure(_invalid(f"the commit {self.commit} names no tree"))
        return match.group(1).decode()

    def _entry(self, mode: Mode, identifier: str) -> Blob:
        """Return the entry of the last part of a path."""
        if mode in (Mode.DIRECTORY, Mode.SUBMODULE):
            return Blob(b"", mode)
        found = self._object(identifier)
        if found is None or found[0] != b"blob":
            raise _Failure(_invalid(f"the commit {self.commit} names a missing file {identifier}"))
        return Blob(found[1], mode)

    def _tree(self, identifier: str) -> dict[bytes, tuple[Mode, str]]:
        """Return the entries of a tree object, each with its mode and its identifier."""
        found = self._object(identifier)
        if found is None or found[0] != b"tree":
            raise _Failure(_invalid(f"the commit {self.commit} names a missing tree {identifier}"))
        data, size, entries = found[1], len(identifier) // 2, {}
        position = 0
        while position < len(data):
            space = data.index(b" ", position)
            end = data.index(b"\0", space)
            mode = TREE_MODES.get(data[position:space])
            if mode is None:
                raise _Failure(_invalid(f"the tree {identifier} holds an unknown mode"))
            entries[data[space + 1 : end]] = (mode, data[end + 1 : end + 1 + size].hex())
            position = end + 1 + size
        return entries

    def _object(self, identifier: str) -> tuple[bytes, bytes] | None:
        """Return the type and the content of an object, verified against its identifier; None
        when the store lacks it."""
        stdin, stdout = self.process.stdin, self.process.stdout
        assert stdin is not None and stdout is not None
        try:
            stdin.write(identifier.encode() + b"\n")
            stdin.flush()
        except (BrokenPipeError, OSError):
            raise _Failure(self._stopped()) from None
        header = stdout.readline()
        if not header:
            raise _Failure(self._stopped())
        fields = header.split()
        if fields[-1] == b"missing":
            return None
        kind, size = fields[1], int(fields[2])
        data = stdout.read(size)
        stdout.read(1)
        algorithm = HASHES.get(len(identifier))
        if algorithm is None:
            raise _Failure(_invalid(f"{identifier} is no object identifier of Git"))
        digest = hashlib.new(algorithm, b"%s %d\0" % (kind, len(data)) + data).hexdigest()
        if digest != identifier:
            raise _Failure(_invalid(f"the object {identifier} holds bytes hashing to {digest}"))
        return kind, data

    def _stopped(self) -> Unavailable:
        """Return the failure of a batch process that stopped answering."""
        assert self.process.stderr is not None
        message = self.process.stderr.read().decode("utf-8", errors="replace").strip()
        first = message.splitlines()[0] if message else "Git stopped reading the store"
        if "permission denied" in message.lower():
            return Unavailable(Availability.DENIED, first)
        return _invalid(first)


def _invalid(detail: str) -> Unavailable:
    """Return the failure of bytes that fail their verification."""
    return Unavailable(Availability.INVALID, detail)


@dataclass(frozen=True)
class GitProvider:
    """Read the selected states from the clone of each entry, then from the cache of the machine.

    Parameters
    ----------
    cache : Path or None
        The bare repository of the cache; None reads the clones alone.
    """

    cache: Path | None = None

    def read(self, state: State, path: str) -> Reading:
        """Return the entry at ``path`` of the state, from the first store holding its commit."""
        normal = confined(path)
        if normal is None:
            return Escaping()
        denied: list[str] = []
        for store in self._stores(state):
            reading = store.read(state.commit, normal)
            if reading is None:
                continue
            if isinstance(reading, Unavailable) and reading.availability is Availability.DENIED:
                denied.append(f"{store.folder}: {reading.detail}")
                continue
            return reading
        if denied:
            return Unavailable(Availability.DENIED, "; ".join(denied))
        return Unavailable(
            Availability.ABSENT,
            f"no Git store of this machine holds {state.commit}; {FETCH_COMMAND} fetches it",
        )

    def holds(self, state: State) -> bool:
        """Whether a store of the machine holds the commit of the state and its tree."""
        return any(store.holds(state.commit) for store in self._stores(state))

    def _stores(self, state: State) -> list[_Store]:
        """Return the stores of a state: its clone when it is a Git repository, then the cache."""
        stores: list[_Store] = []
        if state.clone is not None and (state.clone / ".git").exists():
            stores.append(_Store(state.clone))
        if self.cache is not None and (self.cache / "HEAD").is_file():
            stores.append(_Store(self.cache))
        return stores


class FetchStatus(StrEnum):
    """The outcome of the fetch of one state."""

    #: A store of the machine already holds the state.
    HELD = "held"
    FETCHED = "fetched"
    #: The context names no remote for the state.
    NO_REMOTE = "no-remote"
    #: The remote holds the commit no longer, or never held it.
    UNAVAILABLE = "unavailable"
    #: The remote refuses the access.
    DENIED = "denied"
    FAILED = "failed"


@dataclass(frozen=True)
class Fetched:
    """The outcome of the fetch of one state: what it is, its commit, its status and why."""

    label: str
    commit: str
    status: FetchStatus
    detail: str = ""

    @property
    def failed(self) -> bool:
        """Whether the state is absent from the machine after the fetch."""
        return self.status not in (FetchStatus.HELD, FetchStatus.FETCHED)


#: The messages of Git that report a commit absent from the remote.
_UNAVAILABLE = re.compile(r"not our ref|couldn't find remote ref|no such remote ref|bad object")
#: The messages of Git that report a refused access.
_DENIED = re.compile(
    r"authentication failed|permission denied|could not read username|terminal prompts disabled|"
    r"repository not found|403|401",
    re.IGNORECASE,
)


def fetch_states(states: Iterable[tuple[str, State]], cache: Path) -> list[Fetched]:
    """Fetch into the cache each state that no store of the machine holds.

    Parameters
    ----------
    states : iterable of (str, State)
        Each state with the label that the report names it by.
    cache : Path
        The bare repository of the cache, created when absent.
    """
    provider = GitProvider(cache)
    results: list[Fetched] = []
    for label, state in states:
        if provider.holds(state):
            results.append(Fetched(label, state.commit, FetchStatus.HELD))
        elif state.remote is None:
            results.append(
                Fetched(label, state.commit, FetchStatus.NO_REMOTE, "the context names no remote")
            )
        else:
            results.append(_fetch(label, state, cache, provider))
    return results


def _fetch(label: str, state: State, cache: Path, provider: GitProvider) -> Fetched:
    """Fetch one commit and its tree into the cache, and keep it under a reference."""
    assert state.remote is not None
    environment = isolated_environment()
    if not (cache / "HEAD").is_file():
        cache.mkdir(parents=True, exist_ok=True)
        created = _run(["git", "init", "--quiet", "--bare", str(cache)], cache, environment)
        if created.returncode:
            return Fetched(label, state.commit, FetchStatus.FAILED, _cause(created.stderr))
    fetched = _run(
        [
            "git",
            "-c",
            "fetch.fsckObjects=true",
            "fetch",
            "--quiet",
            "--no-tags",
            "--no-write-fetch-head",
            "--depth=1",
            state.remote,
            state.commit,
        ],
        cache,
        environment,
    )
    if fetched.returncode:
        message = _cause(fetched.stderr)
        status = (
            FetchStatus.UNAVAILABLE
            if _UNAVAILABLE.search(message)
            else FetchStatus.DENIED if _DENIED.search(message) else FetchStatus.FAILED
        )
        return Fetched(label, state.commit, status, message)
    reference = f"{STATE_REFERENCES}/{state.commit}"
    kept = _run(["git", "update-ref", reference, state.commit], cache, environment)
    if kept.returncode:
        return Fetched(label, state.commit, FetchStatus.FAILED, _cause(kept.stderr))
    if not provider.holds(state):
        return Fetched(
            label, state.commit, FetchStatus.FAILED, "the fetched commit fails its verification"
        )
    return Fetched(label, state.commit, FetchStatus.FETCHED, state.remote)


def _run(
    command: list[str], folder: Path, environment: dict[str, str]
) -> subprocess.CompletedProcess[bytes]:
    """Run a Git command in a folder, capturing its output."""
    try:
        return subprocess.run(
            command, cwd=folder, env=environment, capture_output=True, check=False
        )
    except OSError as error:
        return subprocess.CompletedProcess(command, 1, b"", str(error).encode())


def _cause(stderr: bytes) -> str:
    """Return the last line of the error output of Git, which names its cause."""
    lines = [line for line in stderr.decode("utf-8", errors="replace").splitlines() if line.strip()]
    return lines[-1].strip() if lines else "Git reports no cause"
