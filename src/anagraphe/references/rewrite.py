"""
Rewriting of the pointers to moved files, found by their syntax and by their resolution (ADR 0003).

A Markdown link is a pointer by its syntax. A bare path is a pointer to a moved file when it
resolves to that file, from the folder of its holder or from the root, in the tree before the
move. A rewritten path keeps its base, its fragment, a leading ``./`` and, in a link, its
percent-encoding. A pointer held by a moved file, and written relative to that file, is recomputed
from the new folder of the file.
"""

from __future__ import annotations

import posixpath
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Callable, Iterator, Mapping

from anagraphe.core.links import SCHEME
from anagraphe.core.structured import Edit
from anagraphe.references.model import (
    ABSOLUTE,
    BARE,
    MARKDOWN,
    RELATIVE,
    ROOT,
    SHORTEST,
    WIKILINK,
    Style,
    StyleKind,
)
from anagraphe.references.resolution import FileIndex
from anagraphe.references.syntaxes import (
    BUILT_IN,
    ExtractionError,
    Syntaxes,
    references_of,
    shaped,
)

#: A bare path, opening on no character of a path or of a URL, with an optional fragment. Each
#: segment closes on no period, so that a path closing a sentence leaves its period out.
SEGMENT = r"[\w~@+%-](?:[\w.~@+%-]*[\w~@+%-])?"
BARE_PATH = re.compile(
    rf"(?<![\w./~:%@+\\-])(?P<path>(?:\.{{1,2}}/)*{SEGMENT}(?:/{SEGMENT})*/?)"
    r"(?P<fragment>#[\w^%-]+)?"
)
#: The characters of a path written unencoded in a link.
SAFE = "/~@+-._"


@dataclass(frozen=True)
class Relocation:
    """The new path of each moved file and of each moved folder, relative to the root.

    Examples
    --------
    >>> relocation = Relocation({"m/a.md": "n/b.md"}, {"old": "new/old"})
    >>> relocation.new_path("m/a.md"), relocation.new_path("old/x/y.md"), relocation.new_path("z.md")
    ('n/b.md', 'new/old/x/y.md', 'z.md')
    """

    files: Mapping[str, str]
    folders: Mapping[str, str] = field(default_factory=dict)

    def new_path(self, rel: str) -> str:
        """Return the path of a file or a folder after the move."""
        if rel in self.files:
            return self.files[rel]
        for old, new in self.folders.items():
            if rel == old:
                return new
            if rel.startswith(f"{old}/"):
                return new + rel[len(old) :]
        return rel

    def moved(self, rel: str) -> bool:
        """Whether a file or a folder changes its path."""
        return self.new_path(rel) != rel


@dataclass(frozen=True)
class PointerEdit:
    """The rewrite of one pointer: its holder before the move, its line, and its two spellings."""

    holder: str
    line: int
    old: str
    new: str
    edit: Edit


def join(folder: str, path: str) -> str | None:
    """Return a repository-relative path joined to a folder, None when it leaves the root.

    Examples
    --------
    >>> join("a/b", "../c.md"), join("a", "../../c.md"), join("", "./c.md")
    ('a/c.md', None, 'c.md')
    """
    parts = [part for part in folder.split("/") if part]
    for part in path.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
        else:
            parts.append(part)
    return "/".join(parts)


class PointerRewriter:
    """Find the pointers to moved files in the text of one holder, and spell them anew.

    ``exists`` answers whether a repository-relative path names a file or a folder before the move.
    ``syntaxes`` finds the pointers of each holder; the links, Markdown or wikilink, are read in every
    text file, since a YAML value may hold a Markdown paragraph. ``before`` and ``after`` index the
    files before and after the move, for the style ``shortest`` of a wikilink, and ``bases`` lists
    the folders of the declared styles ``base``.
    """

    def __init__(
        self,
        relocation: Relocation,
        exists: Callable[[str], bool],
        syntaxes: Syntaxes = Syntaxes(),
        before: FileIndex | None = None,
        after: FileIndex | None = None,
        bases: tuple[str, ...] = (),
    ) -> None:
        self.relocation = relocation
        self.exists = exists
        self.syntaxes = syntaxes
        self.before = before
        self.after = after
        self.bases = bases

    def edits(self, holder: str, text: str, reserved: tuple[Edit, ...] = ()) -> list[PointerEdit]:
        """Return the rewrites of the pointers of one holder, outside the reserved spans."""
        starts = [0, *(index + 1 for index, char in enumerate(text) if char == "\n")]
        taken = [(edit.start, edit.end) for edit in reserved]
        found: list[PointerEdit] = []
        for start, raw, fmt, omit in self._pointers(holder, text, starts):
            path = raw.split("#", 1)[0]
            if not path or SCHEME.match(path) or self._overlaps(taken, start, start + len(path)):
                continue
            taken.append((start, start + len(path)))
            encoded = fmt == MARKDOWN
            decoded = urllib.parse.unquote(path) if encoded else path
            new = self._respell(holder, decoded, fmt, omit)
            if new is None:
                continue
            if encoded and (decoded != path or any(char in new for char in " ()<>")):
                new = urllib.parse.quote(new, safe=SAFE)
            found.append(self._edit(holder, text, start, path, new))
        for match in BARE_PATH.finditer(text):
            start, path = match.start("path"), match["path"]
            if not shaped(path) or self._overlaps(taken, start, match.end("path")):
                continue
            new = self._respell(holder, path, BARE, ())
            if new is not None:
                found.append(self._edit(holder, text, start, path, new))
        return sorted(found, key=lambda pointer: pointer.edit.start)

    def _pointers(
        self, holder: str, text: str, starts: list[int]
    ) -> Iterator[tuple[int, str, str, tuple[str, ...]]]:
        """Yield the offset, the raw target, the syntax and the omitted suffixes of each candidate."""
        covering = self.syntaxes.covering(holder)
        names = {syntax.name for syntax in covering}
        syntaxes = [
            *covering,
            *(BUILT_IN[name] for name in (MARKDOWN, WIKILINK) if name not in names),
        ]
        for syntax in syntaxes:
            try:
                found = list(references_of(holder, text, [syntax], []))
            except ExtractionError:
                continue
            for item in found:
                reference = item.reference
                yield (
                    starts[reference.line - 1] + reference.column - 1,
                    reference.raw,
                    reference.format,
                    reference.omit,
                )

    def _resolve(
        self, holder: str, stem: str, omit: tuple[str, ...], fmt: str
    ) -> tuple[str, Style, str] | None:
        """Return the file that a path names before the move, the style naming it, and the suffix
        added to the path to name it."""
        candidates: list[tuple[str | None, Style]] = [
            (join(posixpath.dirname(holder), stem), RELATIVE)
        ]
        if stem.startswith("/"):
            candidates.append((stem.lstrip("/"), ABSOLUTE))
        elif not stem.startswith("../"):
            rooted = stem[2:] if stem.startswith("./") else stem
            candidates.append((rooted, ROOT))
            candidates.extend(
                (posixpath.join(base, rooted), Style(StyleKind.BASE, base)) for base in self.bases
            )
        for rel, style in candidates:
            if not rel:
                continue
            if self.exists(rel):
                return rel, style, ""
            for suffix in omit:
                if self.exists(rel + suffix):
                    return rel + suffix, style, suffix
        if fmt == WIKILINK and self.before is not None and not stem.startswith(("../", "./", "/")):
            ends = self.before.ending(stem)
            if len(ends) == 1:
                added = "" if ends[0].endswith(stem) else posixpath.splitext(ends[0])[1]
                return ends[0], SHORTEST, added
        return None

    def _respell(self, holder: str, path: str, fmt: str, omit: tuple[str, ...]) -> str | None:
        """Return the new spelling of a path held by a holder, None when it needs none.

        The new spelling keeps the style by which the path named its file, a leading ``./``, a
        final slash, and a suffix omitted by the syntax.
        """
        trailing = "/" if path.endswith("/") and len(path) > 1 else ""
        stem = path.rstrip("/") or path
        resolved = self._resolve(holder, stem, omit, fmt)
        if resolved is None:
            return None
        target, style, added = resolved
        moved_target = self.relocation.moved(target)
        if not moved_target and (
            style.kind is not StyleKind.RELATIVE or not self.relocation.moved(holder)
        ):
            return None
        new = self._spell(self.relocation.new_path(target), style, holder)
        if added and new.endswith(added):
            new = new[: -len(added)]
        if stem.startswith("./") and not new.startswith(("../", "./")):
            new = f"./{new}"
        new += trailing
        return None if new == path else new

    def _spell(self, target: str, style: Style, holder: str) -> str:
        """Return the path of a file after the move, written in one style."""
        if style.kind is StyleKind.RELATIVE:
            new_folder = posixpath.dirname(self.relocation.new_path(holder)) or "."
            return posixpath.relpath(target, new_folder)
        if style.kind is StyleKind.ABSOLUTE:
            return f"/{target}"
        if style.kind is StyleKind.BASE and target.startswith(f"{style.folder}/"):
            return target[len(style.folder) + 1 :]
        if style.kind is StyleKind.SHORTEST and self.after is not None:
            parts = target.split("/")
            for start in range(len(parts) - 1, -1, -1):
                end = "/".join(parts[start:])
                if self.after.ending(end) == (target,):
                    return end
        return target

    @staticmethod
    def _overlaps(taken: list[tuple[int, int]], start: int, end: int) -> bool:
        """Whether a span overlaps one span already taken."""
        return any(start < other_end and other_start < end for other_start, other_end in taken)

    @staticmethod
    def _edit(holder: str, text: str, start: int, old: str, new: str) -> PointerEdit:
        """Return the edit replacing the characters of one path."""
        return PointerEdit(
            holder, text.count("\n", 0, start) + 1, old, new, Edit(start, start + len(old), new)
        )
