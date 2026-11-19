"""
The fetch of the selected states of ADR 0010 into the cache of the machine, for the command
``anagraphe states fetch``.

The fetch is the only operation of Anagraphe that uses the network. It fetches a commit with its
tree alone, by its full identifier, from the address that the context supplies. It runs with
``fetch.fsckObjects``, records no remote in the cache, and keeps each fetched commit under a
reference, so that a garbage collection of the cache keeps it. Credentials come from the
configuration of Git on the machine, and Git never prompts for one. The Git provider of the read
side then reads the fetched states from the cache.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Iterable

from anagraphe_read._core.git_state import isolated_environment
from anagraphe_read._resolution.git import GitProvider
from anagraphe_read._resolution.provider import State

#: The prefix of the references keeping the fetched commits in the cache.
STATE_REFERENCES = "refs/anagraphe/states"


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
