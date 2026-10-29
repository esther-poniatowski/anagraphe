"""Repository-relative paths, and the links of a frontmatter that name them."""

from __future__ import annotations

import re
import urllib.parse
from pathlib import PurePath, PurePosixPath
from typing import Any

#: A whole value written as one Markdown link, capturing its target.
VALUE_LINK = re.compile(r"^\[[^\]\n]*\]\(([^)\s]+)\)$")


def normalize(path: PurePath) -> str:
    """Return a repository-relative path with dot segments resolved, in POSIX form.

    Examples
    --------
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


def value_link(value: Any) -> str | None:
    """Return the target of a frontmatter value written as one link, or None."""
    match = VALUE_LINK.match(str(value)) if isinstance(value, str) else None
    return urllib.parse.unquote(match.group(1)) if match else None


def link_target(value: Any) -> str | None:
    """Return the repository-relative file named by a frontmatter link, its anchor removed.

    A frontmatter link names its file from the repository root, so the path is normalized but
    never resolved against the folder of the file holding the link.

    Examples
    --------
    >>> link_target("[Lemma](notes/a%20b.md#^proof)"), link_target("notes/a.md")
    ('notes/a b.md', None)
    """
    target = value_link(value)
    if target is None:
        return None
    path = target.split("#", 1)[0]
    return normalize(PurePosixPath(path)) if path else None
