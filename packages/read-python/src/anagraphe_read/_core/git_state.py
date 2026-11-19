"""
The Git adapter of Anagraphe: the files committed in ``HEAD``, for the indexes introduced after
the last commit; the files that Git ignores without tracking them, for the exclusions; and the
gitlinks of the index, the addresses of the submodules, the default remote and the ignored state of
one path, for the record resolver; and the remote ``origin`` of a root, for its identity.
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
    environment = _environment()
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


@dataclass(frozen=True)
class Gitlink:
    """A submodule recorded in the index: its path relative to the root, and its commit."""

    path: str
    commit: str


#: The mode of a gitlink in the index.
GITLINK_MODE = "160000"


def gitlinks(root: Path) -> tuple[Gitlink, ...] | None:
    """Return the gitlinks of the index of the repository at ``root``, sorted by path.

    The index holds the state that the next commit records, so a submodule moved by
    ``git add`` and not yet committed selects its new commit. Git reads the index named by
    ``GIT_INDEX_FILE`` when it sets it for a hook.

    Returns
    -------
    tuple of Gitlink | None
        The gitlinks, or None when ``root`` lies in no Git work tree, or Git cannot run.
    """
    listing = _git(root, _environment(), "ls-files", "-z", "--stage")
    if listing is None:
        return None
    links: list[Gitlink] = []
    for line in listing.split(b"\0"):
        if not line:
            continue
        head, _, name = line.partition(b"\t")
        mode, commit, _stage = head.decode("ascii").split(" ")
        if mode == GITLINK_MODE:
            links.append(Gitlink(name.decode("utf-8", errors="surrogateescape"), commit))
    return tuple(sorted(links, key=lambda link: link.path))


def is_ignored(root: Path, rel: str) -> bool | None:
    """Whether Git ignores the path ``rel`` below ``root``, whether or not the file exists.

    A tracked path is never ignored. The rules are those of the ``.gitignore`` files and of
    ``.git/info/exclude``; the global excludes file of the machine is left out.

    Returns
    -------
    bool | None
        Whether the path is ignored, or None when ``root`` lies in no Git work tree, or Git
        cannot run.
    """
    try:
        result = subprocess.run(
            ["git", "-c", f"core.excludesFile={os.devnull}", "check-ignore", "-q", "--", rel],
            cwd=root,
            capture_output=True,
            check=False,
            env=_environment(),
        )
    except OSError:
        return None
    return {0: True, 1: False}.get(result.returncode)


def submodule_urls(root: Path) -> dict[str, str]:
    """Return the address of each submodule that ``.gitmodules`` declares, keyed by its path.

    An address may be relative to the remote of the root, such as ``../notes.git``. A root without
    ``.gitmodules``, or outside a Git work tree, declares none.
    """
    if not (root / ".gitmodules").is_file():
        return {}
    listing = _git(
        root,
        _environment(),
        "config",
        "-z",
        "--file",
        ".gitmodules",
        "--get-regexp",
        r"^submodule\..*\.(path|url)$",
    )
    if listing is None:
        return {}
    paths: dict[str, str] = {}
    urls: dict[str, str] = {}
    for record in listing.decode("utf-8", errors="surrogateescape").split("\0"):
        key, _, value = record.partition("\n")
        name, _, field = key.removeprefix("submodule.").rpartition(".")
        if field == "path":
            paths[name] = value
        elif field == "url":
            urls[name] = value
    return {paths[name]: urls[name] for name in sorted(paths) if name in urls}


def default_remote_url(root: Path) -> str | None:
    """Return the address of the default remote of the root, against which Git resolves a relative
    submodule address: the remote of the current branch, else ``origin``."""
    environment = _environment()
    branch = _git(root, environment, "symbolic-ref", "--quiet", "--short", "HEAD")
    remote = None
    if branch is not None:
        remote = _git(root, environment, "config", f"branch.{branch.decode().strip()}.remote")
    name = remote.decode().strip() if remote is not None else "origin"
    url = _git(root, environment, "config", f"remote.{name}.url")
    return url.decode("utf-8").strip() if url is not None else None


def origin_url(root: Path) -> str | None:
    """Return the address of the remote ``origin`` of the repository whose work tree has its top
    at ``root``.

    Returns
    -------
    str | None
        The address, or None when ``root`` is not the top of a Git work tree, declares no remote
        ``origin``, or Git cannot run.
    """
    environment = _environment()
    top = _git(root, environment, "rev-parse", "--show-toplevel")
    if top is None or Path(top.decode("utf-8").strip()).resolve() != root.resolve():
        return None
    url = _git(root, environment, "config", "--get", "remote.origin.url")
    address = url.decode("utf-8").strip() if url is not None else ""
    return address or None


#: The variables through which Git locates a repository, set by Git for a hook, which a command run
#: in another repository must not inherit.
REPOSITORY_VARIABLES = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
    "GIT_PREFIX",
)


def isolated_environment() -> dict[str, str]:
    """Return the environment of a Git command run in another repository than the one that runs
    the hook: the variables locating a repository removed, and no prompt for credentials."""
    environment = {
        name: value for name, value in os.environ.items() if name not in REPOSITORY_VARIABLES
    }
    environment["GIT_TERMINAL_PROMPT"] = "0"
    return environment


def _environment() -> dict[str, str]:
    """Return the environment of a Git command, its relative ``GIT_INDEX_FILE`` made absolute.

    Git sets ``GIT_INDEX_FILE`` for a hook relative to the folder where it runs the hook, which
    the commands of Anagraphe may leave.
    """
    environment = dict(os.environ)
    index = environment.get("GIT_INDEX_FILE")
    if index and not os.path.isabs(index):
        environment["GIT_INDEX_FILE"] = os.path.abspath(index)
    return environment


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
