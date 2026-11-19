"""
The pointers of one file: each target that a syntax finds there, resolved to the file it names.

A candidate that names a file is a pointer. A candidate that names no file is a pointer only when
its syntax reports unresolved targets for that file, as ``anagraphe refs check`` decides, since a
code span or a string of code may hold a path that is an example or a command.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from anagraphe_read._core.exclusions import Exemptions
from anagraphe_read._core.files import walk
from anagraphe_read._core.links import Target
from anagraphe_read._core.metadata import MetadataReader
from anagraphe_read._references.configuration import ReadReferences
from anagraphe_read._references.model import SHORTEST, WIKILINK, Reference
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
    """

    source: str
    line: int
    column: int
    raw: str
    syntax: str
    region: str
    target: str | None


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
        return Pointer(
            reference.holder,
            reference.line,
            reference.column,
            reference.raw,
            syntax,
            str(reference.region),
            named,
        )
