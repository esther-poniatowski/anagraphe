"""
Conditions on a file: its path, its type, and its metadata, shared by every declared rule.

The metadata sources, the syntaxes of the pointers and their conventions are each declared as a
list of rules, and each rule applies under one condition written in the same form:

- ``paths``: patterns in the syntax of ``.gitignore``, matched against the repository-relative path;
- ``types``: file suffixes, such as ``md`` or ``tex``;
- ``where``: metadata filters, one matching filter sufficing.

A part left out admits every file, and a file meets the condition when it meets every stated part.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Callable, Mapping

import pathspec

from anagraphe.core.configuration import ConfigurationError, known_keys, mapping, strings
from anagraphe.core.filters import Filter, parse_filter

#: The keys of a condition on a file.
FILE_KEYS = frozenset({"paths", "types", "where"})


@dataclass(frozen=True)
class Condition:
    """The files to which a rule applies; an absent part admits every file.

    Examples
    --------
    >>> condition = Condition(("/docs/",), frozenset({"md"}))
    >>> condition.holds("docs/a.md"), condition.holds("docs/a.tex"), condition.holds("notes/a.md")
    (True, False, False)
    """

    patterns: tuple[str, ...] = ()
    types: frozenset[str] = frozenset()
    filters: tuple[Filter, ...] = ()
    spec: pathspec.GitIgnoreSpec | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.patterns:
            object.__setattr__(self, "spec", pathspec.GitIgnoreSpec.from_lines(self.patterns))

    def holds(self, rel: str, metadata: Callable[[str], Mapping[str, Any]] | None = None) -> bool:
        """Whether a repository-relative file meets every stated part of the condition."""
        if self.types and PurePosixPath(rel).suffix.lstrip(".") not in self.types:
            return False
        if self.spec is not None and not self.spec.match_file(rel):
            return False
        if self.filters:
            data = metadata(rel) if metadata is not None else {}
            return any(selected.selects(data) for selected in self.filters)
        return True


def parse_condition(
    value: Any, field_name: str, allowed: frozenset[str] = FILE_KEYS
) -> tuple[Condition, dict[str, Any]]:
    """Parse a condition, and return it with the keys that the caller admits beyond the file keys."""
    raw = dict(mapping(value, field_name))
    known_keys(raw, allowed, field_name)
    patterns = raw.pop("paths", None)
    if patterns is not None and (
        not isinstance(patterns, list) or any(not isinstance(item, str) for item in patterns)
    ):
        raise ConfigurationError(f"{field_name}.paths must be a list of patterns")
    entries = raw.pop("where", None)
    filters: list[Filter] = []
    for number, entry in enumerate(
        entries if isinstance(entries, list) else [] if entries is None else [entries], start=1
    ):
        parsed, problems = parse_filter(entry)
        if problems:
            raise ConfigurationError(f"{field_name}.where[{number}] {problems[0]}")
        filters.append(parsed)
    types = frozenset(
        item.lstrip(".") for item in strings(raw.pop("types", None), f"{field_name}.types")
    )
    try:
        condition = Condition(tuple(patterns or ()), types, tuple(filters))
    except ValueError as error:
        raise ConfigurationError(f"{field_name}.paths holds an invalid pattern: {error}") from error
    return condition, raw
