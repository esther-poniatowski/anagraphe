"""
Order of the members of one group, under the ordering mode of the group.

ADR 0002 admits two modes, each with one source of order:

- a **registry** sorts its members by the sort keys of the group: the title, the file name, the
  date, or any key of the members. Each later key breaks the ties of the former. A categorical
  key sorts in the order of the values that the vocabulary declares for it, or in the order that
  the group states in ``order`` for its first sort key;
- a **sequence** follows a list of files: the build manifest of the folder where one exists, else
  the sequence of the group. The members absent from that list follow it, in the order of the
  sort keys.

A key of the members compares its values by their type: the numbers, as YAML reads them, by
value, then the other values as text. A categorical key ranks its values first, and the values
that its order omits follow, compared in the same way. Every order ends with the title, then the
path of the member, compared by codepoint, so no two members tie. The order never reads a status,
so a change of status moves no entry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence

from anagraphe.notes import Note
from anagraphe.render import title_of
from anagraphe.slots import SORT_KEYS, GroupSpec, scalar

#: An ISO date opening a file name, by month or by day.
DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}(?:-\d{2})?)")


@dataclass
class Ordering:
    """The ordered members of a group, and the parts of its source of order left unused."""

    members: list[Note] = field(default_factory=list)
    #: Members of a sequence group that the sequence does not list.
    unsequenced: list[Note] = field(default_factory=list)
    #: Files listed by a sequence that the group does not hold.
    outside: list[str] = field(default_factory=list)


def date_of(note: Note) -> str | None:
    """Return the date of a member: its key ``date``, else the ISO date opening its file name.

    Examples
    --------
    >>> date_of(Note("events/2026-08-04_keynote.md")), date_of(Note("x.md", date="2026-09"))
    ('2026-08-04', '2026-09')
    """
    if note.date:
        return note.date
    match = DATE_PREFIX.match(PurePosixPath(note.rel).name)
    return match.group(1) if match else None


def held(value: Any) -> bool:
    """Whether a key holds one value that a sort can compare, a list or a mapping holding none."""
    return value not in (None, "") and not isinstance(value, (list, dict))


def typed(value: Any) -> tuple[int, float, str]:
    """Return the comparable form of one held value: a number before any text, by value.

    A boolean is no number: it compares as its text, in lowercase.

    Examples
    --------
    >>> sorted([10, "late", 2, 1.5], key=typed)
    [1.5, 2, 10, 'late']
    >>> typed(True)
    (1, 0.0, 'true')
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return (0, float(value), "")
    return (1, 0.0, scalar(value))


@dataclass(frozen=True)
class Collation:
    """The sort keys of a group, and the ranked values of each categorical key among them.

    Examples
    --------
    >>> notes = [Note("b.md", title="alpha"), Note("a.md", title="Beta"),
    ...          Note("2026-01-02_c.md", title="Gamma")]
    >>> [note.rel for note in sorted(notes, key=Collation().key)]
    ['b.md', 'a.md', '2026-01-02_c.md']
    >>> [note.rel for note in sorted(notes, key=Collation(("date",)).key)]
    ['2026-01-02_c.md', 'b.md', 'a.md']
    >>> talks = [Note("x.md", title="X", data={"kind": "talk", "day": "2"}),
    ...          Note("y.md", title="Y", data={"kind": "keynote", "day": "3"}),
    ...          Note("z.md", title="Z", data={"kind": "talk", "day": "1"})]
    >>> by_kind = Collation(("kind", "day"), {"kind": ("keynote", "talk")})
    >>> [note.rel for note in sorted(talks, key=by_kind.key)]
    ['y.md', 'z.md', 'x.md']
    """

    keys: tuple[str, ...] = (SORT_KEYS[0],)
    #: The values of each categorical key, in their order.
    ranks: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    @classmethod
    def of(cls, group: GroupSpec, values: Mapping[str, tuple[str, ...]]) -> Collation:
        """Return the collation of a group, its ``order`` overriding the declared values.

        Examples
        --------
        >>> group = GroupSpec("talks", sort=("kind", "status"), order=("talk", "keynote"))
        >>> Collation.of(group, {"kind": ("keynote", "talk"), "status": ("wip", "stable")}).ranks
        {'kind': ('talk', 'keynote'), 'status': ('wip', 'stable')}
        """
        ranks = {key: values[key] for key in group.sort if key in values and key not in SORT_KEYS}
        if group.order and group.sort[0] not in SORT_KEYS:
            ranks[group.sort[0]] = group.order
        return cls(group.sort, ranks)

    def _component(self, note: Note, name: str) -> tuple[Any, ...]:
        """Return the part of the sort key that one key contributes, absent values last."""
        if name == "file":
            return (note.rel,)
        if name == "title":
            title = title_of(note)
            return (title.casefold(), title)
        if name == "date":
            date = date_of(note)
            return (date is None, date or "")
        value = note.data.get(name)
        compared = typed(value) if held(value) else typed("")
        if name in self.ranks:
            values = self.ranks[name]
            text = scalar(value) if held(value) else ""
            rank = values.index(text) if text in values else len(values)
            return (not held(value), rank, *compared)
        return (not held(value), *compared)

    def key(self, note: Note) -> tuple[Any, ...]:
        """Return the sort key of a member, ending with its title and its path."""
        title = title_of(note)
        parts = tuple(part for name in self.keys for part in self._component(note, name))
        return (*parts, title.casefold(), title, note.rel)

    def undeclared(self, note: Note) -> list[tuple[str, str]]:
        """Return each categorical key whose value, held by a member, is absent from its order.

        Examples
        --------
        >>> Collation(("kind",), {"kind": ("talk",)}).undeclared(Note("x.md", data={"kind": "demo"}))
        [('kind', 'demo')]
        """
        return [
            (name, scalar(note.data[name]))
            for name, values in self.ranks.items()
            if held(note.data.get(name)) and scalar(note.data[name]) not in values
        ]


def order_registry(members: Sequence[Note], collation: Collation) -> Ordering:
    """Order the members of a registry group by its collation alone."""
    return Ordering(members=sorted(members, key=collation.key))


def order_sequence(
    members: Sequence[Note], sequence: Sequence[str], collation: Collation
) -> Ordering:
    """Order the members of a sequence group by a list of repository-relative paths.

    Examples
    --------
    >>> members = [Note("m/b.md"), Note("m/a.md"), Note("m/extra.md")]
    >>> ordering = order_sequence(members, ["m/b.md", "m/a.md", "m/gone.md"], Collation())
    >>> [note.rel for note in ordering.members], ordering.outside
    (['m/b.md', 'm/a.md', 'm/extra.md'], ['m/gone.md'])
    """
    by_rel = {member.rel: member for member in members}
    result = Ordering()
    for rel in sequence:
        if rel not in by_rel:
            result.outside.append(rel)
        elif by_rel[rel] not in result.members:
            result.members.append(by_rel[rel])
    result.unsequenced = sorted(
        (member for member in members if member not in result.members), key=collation.key
    )
    result.members.extend(result.unsequenced)
    return result
