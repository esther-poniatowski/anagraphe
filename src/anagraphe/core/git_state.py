"""Optional Git adapter for indexes introduced after the last commit."""

from __future__ import annotations

import subprocess
from pathlib import Path


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
