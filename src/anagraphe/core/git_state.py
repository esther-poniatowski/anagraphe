"""
The Git adapter of Anagraphe: the files committed in ``HEAD``, for the indexes introduced after
the last commit, and the files that Git ignores without tracking them, for the exclusions.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def ignored_untracked(root: Path) -> frozenset[str] | None:
    """Return the paths below ``root`` that Git ignores and does not track, relative to ``root``.

    The rules are those of ``git status``: every ``.gitignore``, ``.git/info/exclude`` and the
    global excludes file. A folder ignored with all it holds is listed once, with a final ``/``.
    A tracked file is never listed, whatever rule it matches. Git reads the index named by
    ``GIT_INDEX_FILE`` when it sets it for a hook; a relative value is resolved against the
    current folder, where Git set it.

    Returns
    -------
    frozenset[str] | None
        The ignored paths, or None when ``root`` lies in no Git work tree, or Git cannot run.
    """
    environment = dict(os.environ)
    index = environment.get("GIT_INDEX_FILE")
    if index and not os.path.isabs(index):
        environment["GIT_INDEX_FILE"] = os.path.abspath(index)
    try:
        listing = subprocess.run(
            ["git", "ls-files", "-z", "--others", "--ignored", "--exclude-standard", "--directory"],
            cwd=root,
            capture_output=True,
            check=False,
            env=environment,
        )
    except OSError:
        return None
    if listing.returncode != 0:
        return None
    return frozenset(
        name.decode("utf-8", errors="surrogateescape")
        for name in listing.stdout.split(b"\0")
        if name
    )


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
