"""Issues located in the files of a repository, and the report of one check, shared by every subpackage.

An issue names its file, its kind and, through its locus and its discriminator, the place of its
defect inside the file. These three values form the identity of the issue in a findings log, so
none of them depends on the line or on the wording of the detail. The locus takes one of three
forms: the empty locus for the whole file, a JSON Pointer for a key of the metadata, or a typed
locus such as ``link:<target as written>``.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class IssueKind:
    """One kind of issue that a section can report, with its description and default level."""

    kind: str
    description: str
    #: Whether an issue of the kind gates a commit by default.
    blocking: bool = True
    #: Whether a non-blocking issue of the kind is a note, which records a fact for the gate to
    #: weigh, rather than a warning.
    note: bool = False

    @property
    def level(self) -> str:
        """Return the level of the kind: ``error``, ``warning`` or ``note``."""
        return level(self.blocking, self.note)


@dataclass(frozen=True)
class Issue:
    """One issue of a file, at its line when it has one, and placed inside the file by its locus."""

    rel: str
    #: The line of the defect; None for an issue of the whole file or of a key of the metadata,
    #: which the text report prints at line 1.
    line: int | None
    kind: str
    detail: str
    #: Whether the issue gates a commit. A non-blocking issue is reported as a warning, or as a note
    #: when :attr:`note` is set.
    blocking: bool = True
    #: The place of the defect inside the file; empty for the whole file.
    locus: str = ""
    #: The offending content separating two issues of one kind at one locus; empty when the locus
    #: suffices. It derives from the issue alone, never from its line.
    discriminator: str = ""
    #: Whether a non-blocking issue is a note rather than a warning.
    note: bool = False

    @property
    def level(self) -> str:
        """Return the level of the issue: ``error``, ``warning`` or ``note``."""
        return level(self.blocking, self.note)

    def format(self) -> str:
        """Return the line printed for the issue: ``path:line: [warning: |note: ]kind: detail``.

        Examples
        --------
        >>> Issue("a.md", 3, "broken", "b.md: names no file", blocking=False).format()
        'a.md:3: warning: broken: b.md: names no file'
        >>> Issue("a.md", None, "stale-block", "a block differs").format()
        'a.md:1: stale-block: a block differs'
        >>> Issue("a.md", None, "unverified-target", "x", blocking=False, note=True).format()
        'a.md:1: note: unverified-target: x'
        """
        marker = "" if self.blocking else f"{self.level}: "
        return f"{self.rel}:{self.line or 1}: {marker}{self.kind}: {self.detail}"


def level(blocking: bool, note: bool = False) -> str:
    """Return the level of an issue: ``error`` when it blocks, else ``note`` or ``warning``.

    Examples
    --------
    >>> level(True), level(False), level(False, note=True)
    ('error', 'warning', 'note')
    """
    if blocking:
        return "error"
    return "note" if note else "warning"


def pointer(*keys: str | int) -> str:
    """Return the JSON Pointer of a key path, escaping ``~`` and then ``/`` in each key.

    Examples
    --------
    >>> pointer("groups")
    '/groups'
    >>> pointer("a/b", "c~d", 0)
    '/a~1b/c~0d/0'
    """
    return "".join("/" + str(key).replace("~", "~0").replace("/", "~1") for key in keys)


def link(target: str) -> str:
    """Return the locus of a pointer, written as its file writes the target.

    Examples
    --------
    >>> link("../notes/a.md#^claim")
    'link:../notes/a.md#^claim'
    """
    return f"link:{target}"


@dataclass(frozen=True)
class Report:
    """The outcome of one check: the files it processed and the issues it found."""

    processed: int
    issues: tuple[Issue, ...]

    @property
    def blocking_count(self) -> int:
        """Return the number of issues that fail the command."""
        return sum(issue.blocking for issue in self.issues)

    @property
    def warning_count(self) -> int:
        """Return the number of warnings: the non-blocking issues that are not notes."""
        return sum(issue.level == "warning" for issue in self.issues)

    @property
    def note_count(self) -> int:
        """Return the number of notes."""
        return sum(issue.level == "note" for issue in self.issues)

    def kinds(self) -> Counter[str]:
        """Return the number of issues of each kind, in the order of their first report."""
        return Counter(issue.kind for issue in self.issues)
