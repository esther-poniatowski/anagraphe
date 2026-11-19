"""
Access to the files of a repository: the walk of its tree, the selection of the targets of a
command, and cached reads.

The read side walks the records through this module, and the checks of the command line select
and read their files through it. The command line of Anagraphe writes its files atomically itself.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
from typing import Callable, Iterator

from anagraphe_read._core.exclusions import Exemptions


class TargetError(ValueError):
    """Report a target of a command that names no file to process."""


def walk(root: Path, start: Path, exemptions: Exemptions) -> Iterator[str]:
    """Yield the repository-relative paths of the files below a folder, in sorted order.

    An excluded folder, a hidden one included, is pruned before its files are listed, so a large
    excluded tree, such as ``.git``, costs nothing.
    """
    for folder, subfolders, files in os.walk(start):
        relative = PurePosixPath(Path(folder).relative_to(root).as_posix())
        subfolders[:] = sorted(
            name for name in subfolders if not exemptions.excludes_directory(relative / name)
        )
        for name in sorted(files):
            path = relative / name
            if not exemptions.contains(path):
                yield path.as_posix()


def select(
    root: Path,
    paths: tuple[Path, ...],
    exemptions: Exemptions,
    accepts: Callable[[str], bool],
    strict: bool = True,
) -> list[str]:
    """Resolve the targets of a command to the distinct files that it reads.

    Each target is a file or a folder, relative to the root or absolute. Without a target, the
    whole repository is read. A named target that does not exist, that lies outside the root, or,
    when ``strict``, that holds no file read by the command, raises a :class:`TargetError`.
    """
    selected: list[str] = []
    seen: set[str] = set()
    for given in paths or (root,):
        target = (given if given.is_absolute() else root / given).resolve()
        if paths and not target.exists():
            raise TargetError(f"target does not exist: {given}")
        if target != root and root not in target.parents:
            raise TargetError(f"target lies outside the repository: {given}")
        if target.is_dir():
            found = list(walk(root, target, exemptions))
        else:
            rel = target.relative_to(root).as_posix()
            found = [] if exemptions.contains(PurePosixPath(rel)) else [rel]
        accepted = [rel for rel in found if accepts(rel)]
        if paths and strict and not accepted:
            raise TargetError(f"target holds no file that the command reads: {given}")
        for rel in accepted:
            if rel not in seen:
                seen.add(rel)
                selected.append(rel)
    return selected


#: The size above which a file is not read as text, so that a data file is never scanned.
TEXT_LIMIT = 2_000_000


def is_text(path: Path, limit: int = TEXT_LIMIT) -> bool:
    """Whether a file holds text: UTF-8 without a null byte, below a size limit."""
    try:
        if path.stat().st_size > limit:
            return False
        data = path.read_bytes()
        if b"\0" in data:
            return False
        data.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return True


class TextCache:
    """Read each file of a repository once, and return its text to every later reader.

    An undecodable byte is replaced, so a binary file cited by a link is read without failing.
    """

    def __init__(self) -> None:
        self._texts: dict[Path, str] = {}

    def __call__(self, path: Path) -> str:
        if path not in self._texts:
            self._texts[path] = path.read_text(encoding="utf-8", errors="replace")
        return self._texts[path]
