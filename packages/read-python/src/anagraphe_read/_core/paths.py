"""Repository-relative paths in POSIX form, and the patterns that select them."""

from __future__ import annotations

import fnmatch
from pathlib import PurePath
from typing import Iterable


def normalize(path: PurePath) -> str:
    """Return a repository-relative path with dot segments resolved, in POSIX form.

    Examples
    --------
    >>> from pathlib import PurePosixPath
    >>> normalize(PurePosixPath("notes/./a/../b.md"))
    'notes/b.md'
    """
    parts: list[str] = []
    for part in path.as_posix().split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def matches(rel: str, patterns: Iterable[str]) -> bool:
    """Whether a repository-relative path matches one pattern, in ``fnmatch`` syntax.

    A ``*`` crosses ``/``, so ``specs/*.yml`` also selects the files of the subfolders of
    ``specs``.

    Examples
    --------
    >>> matches("specs/glossary/terms.yml", ["specs/*.yml"]), matches("notes/a.md", ["*.yml"])
    (True, False)
    """
    return any(fnmatch.fnmatchcase(rel, pattern) for pattern in patterns)
