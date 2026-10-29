"""
Keys, modes and vocabulary sections retired by the decision on collection-owned order.

The order, the nesting and the grouping of the members belong to the index of their collection
(ADR 0002). Each construction that stored them elsewhere, or that derived an order from typed
citations, is retired. A leftover construction fails with a message naming its replacement,
so that a repository migrating to this version learns each edit from the report itself.

A retired key is written at one of three places:

- ``member``: any file listed by an index, a child index included;
- ``note``: a listed file that is not itself an index;
- ``index``: the index being generated, or one group of it (``group``).

A repository may tolerate a retired key in some of its files as a declared migration class. The
class names the files by pattern and the migration awaited, and each instance is then reported
as a warning instead of a violation. Only a key declared ``migratable`` admits a class.

Examples
--------
>>> [entry.key for entry in retired_keys("note", {"cites": [], "group": "core", "purpose": "x"})]
['group', 'cites']
>>> MigrationClass("cites", ("models/*",), "the research records").covers("models/a/b.md")
True
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import Any, Literal, Mapping, Sequence

Scope = Literal["member", "note", "index", "group"]


@dataclass(frozen=True)
class RetiredKey:
    """One retired key, the place where it is written, and the construction replacing it."""

    key: str
    scope: Scope
    replacement: str
    #: Whether a repository may tolerate the key in a declared migration class.
    migratable: bool = False

    def message(self) -> str:
        """Return the message reporting a leftover instance of the key."""
        return f"the key {self.key} is retired: {self.replacement}"


#: Every retired key, by the place where it is written.
RETIRED_KEYS: tuple[RetiredKey, ...] = (
    RetiredKey(
        "group",
        "member",
        "the index of the collection assigns its members through the where or the members of a "
        "group",
    ),
    RetiredKey(
        "cites",
        "note",
        "the links of the body state the dependencies of a note",
        migratable=True,
    ),
    RetiredKey(
        "cites",
        "index",
        "external lists the files outside the folder, and context_relations the distinctions "
        "between members",
        migratable=True,
    ),
    RetiredKey(
        "sequence",
        "index",
        "each group of mode sequence holds its own sequence, written as links",
    ),
    RetiredKey(
        "goal",
        "index",
        "an index checks no order against a goal: a group orders its members by a sort key or "
        "by a sequence of links, and a goal belongs to a tool of the repository",
    ),
    RetiredKey(
        "strategy",
        "group",
        "a group orders its members by a sort key or by a sequence of links",
    ),
)

#: Every retired ordering mode, with the modes replacing it.
RETIRED_MODES: Mapping[str, str] = {
    "construction": "use registry, sorted by a key, or sequence, ordered by a list of links",
}

#: Every retired section of the vocabulary, with the section replacing it.
RETIRED_VOCABULARY: Mapping[str, str] = {
    "cites": "declare the relations of context_relations under context_relations",
}

#: The keys that a repository may tolerate in a migration class.
MIGRATABLE_KEYS = frozenset(entry.key for entry in RETIRED_KEYS if entry.migratable)


def retired_mode(mode: str) -> str:
    """Return the message reporting a retired mode.

    Examples
    --------
    >>> retired_mode("construction")
    'the mode construction is retired: use registry, sorted by a key, or sequence, ordered by a list of links'
    """
    return f"the mode {mode} is retired: {RETIRED_MODES[mode]}"


def retired_keys(scope: Scope, data: Mapping[str, Any]) -> list[RetiredKey]:
    """Return the retired keys that a mapping declares at one place.

    A key retired at the place ``member`` is also retired at the place ``note``, since a note is
    a member that is not an index.
    """
    scopes = {scope, "member"} if scope == "note" else {scope}
    return [entry for entry in RETIRED_KEYS if entry.scope in scopes and entry.key in data]


@dataclass(frozen=True)
class MigrationClass:
    """Files in which a repository tolerates one retired key until a declared migration."""

    key: str
    #: Patterns of repository-relative paths, in ``fnmatch`` syntax, where ``*`` crosses ``/``.
    patterns: tuple[str, ...]
    #: The migration awaited, named in every warning of the class.
    awaits: str

    def covers(self, rel: str) -> bool:
        """Whether a repository-relative path belongs to the class."""
        return any(fnmatch.fnmatchcase(rel, pattern) for pattern in self.patterns)


def migration_of(classes: Sequence[MigrationClass], key: str, rel: str) -> MigrationClass | None:
    """Return the first migration class tolerating a key in a file, or None."""
    return next(
        (entry for entry in classes if entry.key == key and entry.covers(rel)),
        None,
    )
