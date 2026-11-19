"""
The model of a reference: one target written in one file, in one syntax, located exactly.

A reference records the place of its target in the holding file, by line and column, so that a
check reports it there and a rewrite replaces exactly those characters. The conventions of the
repository then state which formats and which path styles the reference admits.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

#: The names of the built-in syntaxes; a repository may declare further syntaxes by name.
MARKDOWN = "markdown"
WIKILINK = "wikilink"
CODE = "code"
LATEX = "latex"
#: The syntax of a bare path, read by a move in every text file.
BARE = "bare"


class StyleKind(StrEnum):
    """The starting point from which the path of a reference resolves."""

    #: The folder of the file holding the reference.
    RELATIVE = "relative"
    #: The root of the repository, without a leading slash.
    ROOT = "root"
    #: The root of the repository, with a leading slash.
    ABSOLUTE = "absolute"
    #: The shortest end of a path naming one file of the repository, as Obsidian writes wikilinks.
    SHORTEST = "shortest"
    #: A declared folder of the repository, such as the root of a project or of a build.
    BASE = "base"


@dataclass(frozen=True, order=True)
class Style:
    """One path style: its kind, and the folder of a style ``base``.

    Examples
    --------
    >>> str(Style(StyleKind.RELATIVE)), str(Style(StyleKind.BASE, "projects/mixture"))
    ('relative', 'base projects/mixture')
    """

    kind: StyleKind
    folder: str = ""

    def __str__(self) -> str:
        return f"{self.kind} {self.folder}" if self.kind is StyleKind.BASE else str(self.kind)


RELATIVE = Style(StyleKind.RELATIVE)
ROOT = Style(StyleKind.ROOT)
ABSOLUTE = Style(StyleKind.ABSOLUTE)
SHORTEST = Style(StyleKind.SHORTEST)


class Fragments(StrEnum):
    """The fragments that a reference may carry after ``#``."""

    #: Only a block anchor ``#^name``, since the slug of a heading changes with its wording.
    BLOCK = "block"
    #: Any fragment; only a block anchor is checked against its target.
    ANY = "any"


class Form(StrEnum):
    """The form of a field value holding a reference."""

    #: A bare path, with an optional fragment: ``notes/a.md#^claim``.
    PATH = "path"
    #: One link, Markdown or wikilink: ``[Claim](notes/a.md#^claim)`` or ``[[notes/a#^claim]]``.
    LINK = "link"


class Region(StrEnum):
    """The region of a file where a reference is written."""

    #: The span where the declared source of the file writes its metadata, such as a frontmatter.
    METADATA = "metadata"
    #: The rest of the file.
    CONTENT = "content"


@dataclass(frozen=True)
class Reference:
    """One target written in one file, in one syntax."""

    #: The repository-relative path of the file holding the reference, in POSIX form.
    holder: str
    #: The line of the target, counted from 1.
    line: int
    #: The column of the first character of the target, counted from 1.
    column: int
    #: The target as written, percent-encoding included, without the alias of a wikilink.
    raw: str
    region: Region = Region.CONTENT
    #: The name of the syntax of the reference, such as ``markdown`` or ``latex``.
    format: str = MARKDOWN
    #: Whether the target is percent-encoded, as a Markdown link is and a wikilink or a bare path is
    #: not.
    encoded: bool = True
    #: Whether the characters at the line and the column spell the raw target exactly, so that a
    #: rewrite may replace them. A value of a block scalar or holding an escape is not exact.
    exact: bool = True
    #: The suffixes that the syntax may omit, such as ``.md`` for a wikilink or ``.tex`` for LaTeX.
    omit: tuple[str, ...] = ()
