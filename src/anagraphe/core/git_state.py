"""
The Git adapter of Anagraphe: the files committed in ``HEAD``, for the indexes introduced after
the last commit, and the files that Git ignores without tracking them, for the exclusions.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class IgnoredPaths:
    """The paths that Git ignores without tracking them, each folder with a final ``/``."""

    #: Every ignored path, by the rules of the ``.gitignore`` files and of ``.git/info/exclude``.
    every: frozenset[str]
    #: The ignored paths that no rule of a ``.gitignore`` file covers: a rule of the clone alone,
    #: in ``.git/info/exclude``, ignores each of them.
    local: frozenset[str]


def ignored_untracked(root: Path) -> IgnoredPaths | None:
    """Return the paths below ``root`` that Git ignores and does not track, relative to ``root``.

    The rules are those of every ``.gitignore`` file and of ``.git/info/exclude``. The global
    excludes file of the machine is left out, so that two clones of one commit agree. A folder
    ignored with all it holds is listed once, with a final ``/``. A tracked file is never listed,
    whatever rule it matches. Git reads the index named by ``GIT_INDEX_FILE`` when it sets it for a
    hook; a relative value is resolved against the current folder, where Git set it.

    Returns
    -------
    IgnoredPaths | None
        The ignored paths, or None when ``root`` lies in no Git work tree, or Git cannot run.
    """
    environment = dict(os.environ)
    index = environment.get("GIT_INDEX_FILE")
    if index and not os.path.isabs(index):
        environment["GIT_INDEX_FILE"] = os.path.abspath(index)
    committed = _ignored(root, environment, ())
    local_file = _git_path(root, environment, "info/exclude")
    if committed is None or local_file is None:
        return None
    if not local_file.is_file():
        return IgnoredPaths(committed, frozenset())
    every = _ignored(root, environment, (f"--exclude-from={local_file}",))
    if every is None:
        return None
    return IgnoredPaths(every, frozenset(path for path in every if not _covered(path, committed)))


def _ignored(
    root: Path, environment: dict[str, str], extra: tuple[str, ...]
) -> frozenset[str] | None:
    """Return the untracked paths ignored by the ``.gitignore`` files and the extra sources."""
    listing = _git(
        root,
        environment,
        "ls-files",
        "-z",
        "--others",
        "--ignored",
        "--exclude-per-directory=.gitignore",
        *extra,
        "--directory",
    )
    if listing is None:
        return None
    return frozenset(
        name.decode("utf-8", errors="surrogateescape") for name in listing.split(b"\0") if name
    )


def _git_path(root: Path, environment: dict[str, str], name: str) -> Path | None:
    """Return the path of a file of the Git folder of ``root``, such as ``info/exclude``."""
    output = _git(root, environment, "rev-parse", "--git-path", name)
    if output is None:
        return None
    path = Path(output.decode("utf-8").strip())
    return path if path.is_absolute() else root / path


def _git(root: Path, environment: dict[str, str], *args: str) -> bytes | None:
    """Return the standard output of a Git command run in ``root``, or None when it fails."""
    try:
        result = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, check=False, env=environment
        )
    except OSError:
        return None
    return result.stdout if result.returncode == 0 else None


def _covered(path: str, ignored: frozenset[str]) -> bool:
    """Whether a path, or one of its folders, belongs to a set of ignored paths.

    Examples
    --------
    >>> _covered("build/a/b.md", frozenset({"build/"})), _covered("notes/a.md", frozenset())
    (True, False)
    """
    if path in ignored:
        return True
    parts = path.rstrip("/").split("/")[:-1]
    return any("/".join(parts[: depth + 1]) + "/" in ignored for depth in range(len(parts)))


def committed_files(root: Path) -> frozenset[str] | None:
    """Return paths tracked by ``HEAD``, including working-tree rename destinations."""
    tree = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if tree.returncode != 0:
        return None
    files = set(tree.stdout.splitlines())
    renames = subprocess.run(
        ["git", "diff", "--name-status", "-M", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    for line in renames.stdout.splitlines():
        status, *paths = line.split("\t")
        if status.startswith("R") and len(paths) == 2 and paths[0] in files:
            files.add(paths[1])
    return frozenset(files)
