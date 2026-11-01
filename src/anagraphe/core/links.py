"""
Markdown links: their syntax, and the parts of their target.

A target splits into an optional URL scheme, a path and an optional fragment. Both subpackages
read links through this module: the indexes read the links of a frontmatter, and the references
read every link of a file.
"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from anagraphe.core.paths import normalize

#: An inline link or embed in a line of text, capturing its target, an optional title excluded.
INLINE_LINK = re.compile(r'!?\[[^\]\n]*\]\((?P<target>[^)\s]*?)(?:\s+"[^"]*")?\)')
#: A wikilink or embed in a line of text, capturing its target, its alias excluded.
WIKILINK = re.compile(r"!?\[\[(?P<target>[^\[\]|\n]*?)(?:\|[^\[\]\n]*)?\]\]")
#: A whole value written as one wikilink, capturing its target.
VALUE_WIKILINK = re.compile(r"^!?\[\[([^\[\]|\n]+?)(?:\|[^\[\]\n]*)?\]\]$")
#: A whole value written as one Markdown link, capturing its target, an optional title excluded.
VALUE_LINK = re.compile(r'^\[[^\]\n]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)$')
#: A URL scheme opening a target.
SCHEME = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*):")


@dataclass(frozen=True)
class Target:
    """The parts of a link target, its percent-encoding decoded.

    Examples
    --------
    >>> Target.parse("../b/a%20b.md#%5Eclaim")
    Target(scheme=None, path='../b/a b.md', fragment='^claim')
    >>> Target.parse("https://example.org/page#section").scheme
    'https'
    >>> Target.parse("#^local")
    Target(scheme=None, path='', fragment='^local')
    >>> Target.parse("b/a%20b.md", decode=False).path
    'b/a%20b.md'
    """

    #: The URL scheme in lowercase, None for a path.
    scheme: str | None
    #: The path, empty for a fragment of the holding file.
    path: str
    #: The fragment without its ``#``, empty when absent.
    fragment: str

    @classmethod
    def parse(cls, raw: str, decode: bool = True) -> Target:
        """Split a raw target into its scheme, its path and its fragment.

        A target written as a Markdown link is percent-encoded, so it is decoded first. A bare path
        written in a record is read as written, with ``decode=False``.
        """
        scheme = SCHEME.match(raw)
        if scheme is not None:
            return cls(scheme.group(1).lower(), raw, "")
        text = urllib.parse.unquote(raw) if decode else raw
        path, _, fragment = text.partition("#")
        return cls(None, path, fragment)


def value_link(value: Any) -> str | None:
    """Return the target of a value written as one link, or None."""
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
