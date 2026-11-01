"""
Resolution of the path of a reference, under every path style.

A path is resolved under each style: from the folder of its file (``relative``), from the root
without a leading slash (``root``) or with one (``absolute``), from each declared base folder
(``base``), and as the end of the path of one file (``shortest``). The check then compares the styles
that name a file with the styles admitted by the convention of the reference: a path naming no file
under any style is ``broken``, and a path naming a file only under a style left unadmitted breaks the
convention. A target may omit the suffixes that its syntax declares, such as ``.md`` for a wikilink
or ``.tex`` for LaTeX.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from anagraphe.core.links import Target
from anagraphe.references.model import (
    ABSOLUTE,
    RELATIVE,
    ROOT,
    SHORTEST,
    WIKILINK,
    Reference,
    Style,
    StyleKind,
)

#: The suffix that a wikilink may omit.
NOTE_SUFFIX = ".md"


@dataclass(frozen=True)
class Resolution:
    """The file named by the path of a reference under each style that names one."""

    #: The cited file under each resolving style, in the order of the styles tried.
    resolved: dict[Style, Path] = field(default_factory=dict)
    #: A file named from the folder of the holding file but lying outside the repository.
    outside: Path | None = None
    #: The files named by the end of the path when it names several of them.
    ambiguous: tuple[Path, ...] = ()

    @property
    def cited(self) -> Path | None:
        """Return the cited file, under the first resolving style."""
        return next(iter(self.resolved.values()), None)

    def under(self, styles: Iterable[Style]) -> Path | None:
        """Return the file named under the first of the given styles that resolves, or None."""
        return next((self.resolved[style] for style in styles if style in self.resolved), None)


class FileIndex:
    """The files of a repository, by path and by the ends of their paths.

    Examples
    --------
    >>> index = FileIndex(["notes/a.md", "old/notes/a.md", "b.md"])
    >>> index.ending("b"), index.ending("notes/a"), index.ending("old/notes/a")
    (('b.md',), ('notes/a.md', 'old/notes/a.md'), ('old/notes/a.md',))
    """

    def __init__(self, files: Iterable[str]) -> None:
        self.files = frozenset(files)
        self._ends: dict[str, list[str]] = {}
        for rel in sorted(self.files):
            parts = rel.split("/")
            for start in range(len(parts)):
                end = "/".join(parts[start:])
                self._ends.setdefault(end, []).append(rel)
                if end.endswith(NOTE_SUFFIX):
                    self._ends.setdefault(end[: -len(NOTE_SUFFIX)], []).append(rel)

    def ending(self, path: str) -> tuple[str, ...]:
        """Return the files whose path ends with a path, the suffix ``.md`` of a note optional."""
        return tuple(dict.fromkeys(self._ends.get(path.strip("/"), ())))


class Resolver:
    """Resolve the paths of the references of one repository, under every path style.

    The root is resolved once, since a root reached through a symbolic link would otherwise
    contain none of the resolved paths. Without a file index, the style ``shortest`` names no file.
    """

    def __init__(
        self, root: Path, bases: Iterable[str] = (), index: FileIndex | None = None
    ) -> None:
        self.root = root.resolve()
        self.bases = tuple(bases)
        self.index = index

    def resolve(
        self, reference: Reference, target: Target, admitted: tuple[Style, ...] = ()
    ) -> Resolution:
        """Return the files named by the path of a target, which carries no scheme.

        The style ``shortest`` is tried for a wikilink, and for another format only when the
        convention admits it, since a Markdown viewer resolves no end of a path. A target holding
        only a fragment names its own file. A path opening on ``../`` resolves
        only from the folder of its file. A path opening on ``./`` resolves from the root without
        that prefix.

        Examples
        --------
        >>> import tempfile
        >>> root = Path(tempfile.mkdtemp()).resolve()
        >>> for rel in ("a/note.md", "b/target.md"):
        ...     (root / rel).parent.mkdir(parents=True, exist_ok=True)
        ...     _ = (root / rel).write_text("")
        >>> resolver = Resolver(root, index=FileIndex(["a/note.md", "b/target.md"]))
        >>> def styles(raw, fmt="markdown", omit=()):
        ...     reference = Reference("a/note.md", 1, 1, raw, format=fmt, omit=omit)
        ...     return [str(style) for style in resolver.resolve(reference, Target.parse(raw)).resolved]
        >>> styles("../b/target.md"), styles("b/target.md"), styles("/b/target.md")
        (['relative'], ['root'], ['absolute'])
        >>> styles("target", "wikilink", (".md",))
        ['shortest']
        """
        holder = self.root / reference.holder
        if not target.path:
            return Resolution({RELATIVE: holder})
        omit = reference.omit
        resolved: dict[Style, Path] = {}
        outside: Path | None = None
        relative = self._file((holder.parent / target.path).resolve(), omit)
        if relative is not None:
            if self.root in relative.parents:
                resolved[RELATIVE] = relative
            else:
                outside = relative
        if target.path.startswith("/"):
            found = self._inside(target.path.lstrip("/"), omit)
            if found is not None:
                resolved[ABSOLUTE] = found
        elif not target.path.startswith("../"):
            rooted = target.path[2:] if target.path.startswith("./") else target.path
            found = self._inside(rooted, omit)
            if found is not None:
                resolved[ROOT] = found
            for base in self.bases:
                found = self._inside(posixpath.join(base, rooted), omit)
                if found is not None:
                    resolved[Style(StyleKind.BASE, base)] = found
        ambiguous: tuple[Path, ...] = ()
        shortest = reference.format == WIKILINK or SHORTEST in admitted
        if shortest and self.index is not None and not target.path.startswith(("../", "./", "/")):
            ends = self.index.ending(target.path)
            if len(ends) == 1:
                resolved[SHORTEST] = self.root / ends[0]
            elif len(ends) > 1:
                ambiguous = tuple(self.root / rel for rel in ends)
        return Resolution(resolved, outside, ambiguous)

    def _inside(self, rel: str, omit: tuple[str, ...]) -> Path | None:
        """Return the file named by a path from the root, inside the repository, or None."""
        path = self._file((self.root / rel).resolve(), omit)
        return path if path is not None and self.root in path.parents else None

    @staticmethod
    def _file(path: Path, omit: tuple[str, ...]) -> Path | None:
        """Return a path naming a file, trying each suffix that the syntax may omit."""
        if path.is_file():
            return path
        for suffix in omit:
            completed = path.with_name(path.name + suffix)
            if completed.is_file():
                return completed
        return None
