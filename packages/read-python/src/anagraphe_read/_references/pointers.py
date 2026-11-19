"""
The pointers of one file: each target that a syntax finds there, resolved to the file it names.

A candidate that names a file is a pointer. A candidate that names no file is a pointer only when
its syntax reports unresolved targets for that file, as ``anagraphe refs check`` decides, since a
code span or a string of code may hold a path that is an example or a command.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from pathlib import Path

from anagraphe_read._core.exclusions import Exemptions
from anagraphe_read._core.files import walk
from anagraphe_read._core.links import Target
from anagraphe_read._core.metadata import MetadataReader
from anagraphe_read._references.configuration import ReadReferences
from anagraphe_read._references.model import SHORTEST, WIKILINK, Reference, Style, StyleKind
from anagraphe_read._references.resolution import FileIndex, Resolver
from anagraphe_read._references.syntaxes import references_of


@dataclass(frozen=True)
class Pointer:
    """One target written in a file, and the file of the repository that it names.

    Attributes
    ----------
    source : str
        The repository-relative POSIX path of the file holding the pointer.
    line : int
        The line of the target, counted from 1.
    column : int
        The column of the first character of the target, counted from 1, in code points.
    raw : str
        The target as written.
    syntax : str
        The syntax that found it: ``markdown``, ``wikilink``, ``code``, ``latex``, or a syntax
        declared under ``references.syntaxes``.
    region : str
        ``metadata`` when the target lies where the source of the file writes its metadata, such as
        a frontmatter, ``content`` otherwise.
    target : str | None
        The repository-relative POSIX path of the file named, without fragment; None when the
        target names no file of the repository, carries a URL scheme, or lies outside it.
    named : str | None
        The repository-relative POSIX path that the target names under the conventions of the
        repository, whether or not a file lies there: equal to ``target`` for an existing file;
        otherwise the path read under the first admitted style that applies, such as the path from
        the folder of the citing file for a relative link, normalized, or the path from the root for
        a root link. None for a URL, a path that leaves the repository, or a shortest-path link,
        such as a wikilink, that names no existing file.
    """

    source: str
    line: int
    column: int
    raw: str
    syntax: str
    region: str
    target: str | None
    named: str | None = None


class PointerReader:
    """Find and resolve the pointers of the files of one repository, the file index built once."""

    def __init__(self, root: Path, section: ReadReferences) -> None:
        self.root = root.resolve()
        self.section = section
        self.metadata = section.metadata or MetadataReader(self.root)
        self.resolver = Resolver(self.root, section.conventions.bases())

    def _index(self) -> None:
        """Build the index of the ends of the paths, for the first pointer that needs it."""
        if self.resolver.index is None:
            self.resolver.index = FileIndex(walk(self.root, self.root, Exemptions()))

    def pointers(self, rel: str) -> tuple[Pointer, ...]:
        """Return the pointers of one repository-relative file, in the order of its syntaxes.

        A file that cannot be read, or that a syntax of keys cannot parse, holds no pointer of
        that syntax.
        """
        try:
            text = (self.root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return ()
        regions = self.metadata.region(rel, text)
        found: list[Pointer] = []
        for syntax in self.section.syntaxes.covering(rel):
            try:
                items = list(references_of(rel, text, [syntax], regions))
            except ValueError:
                continue
            for item in items:
                pointer = self._pointer(item.reference, item.syntax, item.reports_unresolved)
                if pointer is not None:
                    found.append(pointer)
        return tuple(found)

    def _pointer(self, reference: Reference, syntax: str, default: bool) -> Pointer | None:
        """Return the pointer of one candidate, or None for a candidate that is no pointer."""
        target = Target.parse(reference.raw, decode=reference.encoded)
        convention = self.section.conventions.of(reference.holder, reference.region, syntax)
        strict = default if convention.strict is None else syntax in convention.strict
        named: str | None = None
        if not target.scheme:
            if reference.format == WIKILINK or SHORTEST in convention.styles:
                self._index()
            cited = self.resolver.resolve(reference, target, convention.styles).cited
            if cited is not None:
                named = cited.relative_to(self.root).as_posix()
        if named is None and not strict:
            return None
        path = named
        if path is None and not target.scheme and reference.format != WIKILINK:
            path = _named(reference.holder, target.path, convention.styles)
        return Pointer(
            reference.holder,
            reference.line,
            reference.column,
            reference.raw,
            syntax,
            str(reference.region),
            named,
            path,
        )


def _inside(path: str) -> str | None:
    """Return a path normalized below the root, or None when it leaves the repository."""
    normal = posixpath.normpath(path)
    return None if normal in (".", "") or normal.split("/")[0] == ".." else normal


def _named(holder: str, path: str, styles: tuple[Style, ...]) -> str | None:
    """Return the path that a target naming no file names, under the first admitted style that
    applies to it; a path that no admitted style reads is read from the folder of the holder, or
    from the root when it opens on ``/``.

    Examples
    --------
    >>> from anagraphe_read._references.model import RELATIVE, ROOT
    >>> _named("a/b/note.md", "../../c/gone.md", (RELATIVE,))
    'c/gone.md'
    >>> _named("a/note.md", "c/gone.md", (ROOT, RELATIVE)), _named("a/note.md", "/c/gone.md", (RELATIVE,))
    ('c/gone.md', 'c/gone.md')
    >>> _named("note.md", "../outside.md", (RELATIVE,)) is None
    True
    """
    folder = posixpath.dirname(holder)
    rooted = path[2:] if path.startswith("./") else path
    climbs = path.startswith("../")
    for style in styles:
        if style.kind is StyleKind.RELATIVE and not path.startswith("/"):
            return _inside(posixpath.join(folder, path))
        if style.kind is StyleKind.ABSOLUTE and path.startswith("/"):
            return _inside(path.lstrip("/"))
        if style.kind is StyleKind.ROOT and not climbs and not path.startswith("/"):
            return _inside(rooted)
        if style.kind is StyleKind.BASE and not climbs and not path.startswith("/"):
            return _inside(posixpath.join(style.folder, rooted))
    if path.startswith("/"):
        return _inside(path.lstrip("/"))
    return _inside(posixpath.join(folder, path))
