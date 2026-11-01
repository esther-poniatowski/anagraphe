"""Issues located in the files of a repository, and the report of one check, shared by every subpackage."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class Issue:
    """One issue of a file, located at a line."""

    rel: str
    line: int
    kind: str
    detail: str
    #: Whether the issue gates a commit. A non-blocking issue is reported as a warning.
    blocking: bool = True

    def format(self) -> str:
        """Return the line printed for the issue: ``path:line: [warning: ]kind: detail``.

        Examples
        --------
        >>> Issue("a.md", 3, "broken", "b.md: names no file", blocking=False).format()
        'a.md:3: warning: broken: b.md: names no file'
        """
        marker = "" if self.blocking else "warning: "
        return f"{self.rel}:{self.line}: {marker}{self.kind}: {self.detail}"


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
        """Return the number of non-blocking issues."""
        return len(self.issues) - self.blocking_count

    def kinds(self) -> Counter[str]:
        """Return the number of issues of each kind, in the order of their first report."""
        return Counter(issue.kind for issue in self.issues)
