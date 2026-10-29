"""Issues reported while generating an index, shared by the modules that detect them."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Issue:
    """One issue of an index or of one of its members, located at a file and a line."""

    rel: str
    line: int
    kind: str
    detail: str
    #: Whether the issue gates a commit. A non-blocking issue is reported as a warning.
    blocking: bool = True
