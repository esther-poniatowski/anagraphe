"""
Order of the entries of one block, under the ordering mode of the block.

The decision on index types fixes three modes, each with its own source of order:

- a **registry** is sorted by the sort key of the block: the title, the file name, the date, or
  any other key of its members;
- a **sequence** follows a configured list of file names or the key ``sequence`` of the index,
  and the members absent from that list follow it;
- a **construction** follows the citations between its members, as the decision on typed
  citations fixes, in three steps. First, each citation between two members of the block yields
  one precedence constraint, through the order rule of its relation and the strategy tokens of
  the block. Second, the constraints are added in an order of priority: the fixed rules, then the
  pair ``support``, then the pair ``generality``. A constraint closing a cycle is dropped and
  reported. Third, a topological sort (Kahn) orders the members, and the sort key of the block
  breaks the remaining ties. A citation toward an external reference, or toward a file outside
  the block, yields no constraint.

Every sort key ends with the path of the member, compared by codepoint, so no two members tie.
The order never reads a status, so a change of status moves no entry.
"""

from __future__ import annotations

import heapq
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Mapping, Sequence

from anagraphe.fields import End, OrderRule, Relation
from anagraphe.notes import Note, normalize
from anagraphe.render import title_of
from anagraphe.slots import scalar

#: An ISO date opening a file name, by month or by day.
DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}(?:-\d{2})?)")

#: The priority of each order rule: a lower number is added first, and wins a conflict.
PRIORITY = {
    OrderRule.TARGET_FIRST: 0,
    OrderRule.SOURCE_FIRST: 0,
    OrderRule.SUPPORT: 1,
    OrderRule.GENERALITY: 2,
}
#: The tokens placing the first-named end first, one per pair.
FIRST_TOKENS = {"support": "support-first", "generality": "general-first"}


@dataclass
class Ordering:
    """The ordered members of a block, and the constraints dropped while ordering them."""

    members: list[Note] = field(default_factory=list)
    #: Constraints ``(earlier, later)`` dropped because they closed a cycle.
    conflicts: list[tuple[str, str]] = field(default_factory=list)
    #: Names of a sequence matching no member of the block.
    unknown: list[str] = field(default_factory=list)
    #: Members of a sequence block that the sequence does not list.
    unsequenced: list[Note] = field(default_factory=list)


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


def sort_key(note: Note, sort: str) -> tuple[str, ...]:
    """Return the sort key of a member under the key named by a block, ending with its path.

    A member without a date follows the dated members in a block sorted by date. Any other key is
    compared as text, so a date or a time sorts in its ISO form; a member without a single value
    for that key follows the others, and the title breaks the ties.

    Examples
    --------
    >>> notes = [Note("b.md", title="alpha"), Note("a.md", title="Beta"),
    ...          Note("2026-01-02_c.md", title="Gamma")]
    >>> [note.rel for note in sorted(notes, key=lambda note: sort_key(note, "title"))]
    ['b.md', 'a.md', '2026-01-02_c.md']
    >>> [note.rel for note in sorted(notes, key=lambda note: sort_key(note, "date"))]
    ['2026-01-02_c.md', 'a.md', 'b.md']
    >>> timed = [Note("x.md", title="X", data={"day": "2026-08-04T09:00"}), Note("y.md", title="Y"),
    ...          Note("z.md", title="Z", data={"day": "2026-08-03T17:00"})]
    >>> [note.rel for note in sorted(timed, key=lambda note: sort_key(note, "day"))]
    ['z.md', 'x.md', 'y.md']
    """
    if sort == "file":
        return (note.rel,)
    if sort == "date":
        date = date_of(note)
        return ("0" if date else "1", date or "", note.rel)
    title = title_of(note)
    if sort != "title":
        value = note.data.get(sort)
        held = value not in (None, "") and not isinstance(value, (list, dict))
        return (
            "0" if held else "1",
            scalar(value) if held else "",
            title.casefold(),
            note.rel,
        )
    return (title.casefold(), title, note.rel)


def order_registry(members: Sequence[Note], sort: str = "title") -> Ordering:
    """Order the members of a registry block by the sort key of the block alone."""
    return Ordering(members=sorted(members, key=lambda note: sort_key(note, sort)))


def order_sequence(
    members: Sequence[Note], names: Sequence[str], folder: str, sort: str = "title"
) -> Ordering:
    """Order the members of a sequence block by a list of paths relative to the folder.

    Examples
    --------
    >>> members = [Note("m/b.md"), Note("m/a.md"), Note("m/extra.md")]
    >>> ordering = order_sequence(members, ["b.md", "a.md", "gone.md"], "m")
    >>> [note.rel for note in ordering.members], ordering.unknown
    (['m/b.md', 'm/a.md', 'm/extra.md'], ['gone.md'])
    """
    by_rel = {member.rel: member for member in members}
    result = Ordering()
    for name in names:
        rel = normalize(PurePosixPath(folder) / name)
        if rel not in by_rel:
            result.unknown.append(name)
        elif by_rel[rel] not in result.members:
            result.members.append(by_rel[rel])
    result.unsequenced = sorted(
        (member for member in members if member not in result.members),
        key=lambda note: sort_key(note, sort),
    )
    result.members.extend(result.unsequenced)
    return result


def constraint(
    note: Note, target: str, relation: Relation, strategy: Mapping[str, str]
) -> tuple[int, str, str] | None:
    """Return the constraint ``(priority, earlier, later)`` of one citation, or None.

    Examples
    --------
    >>> uses = Relation("uses-definition-from", contributes=End.TARGET, order=OrderRule.SUPPORT)
    >>> constraint(Note("main.md"), "def.md", uses, {"support": "support-first"})
    (1, 'def.md', 'main.md')
    >>> constraint(Note("main.md"), "def.md", uses, {"support": "claim-first"})
    (1, 'main.md', 'def.md')
    """
    if relation.order not in PRIORITY:
        return None
    if relation.order is OrderRule.TARGET_FIRST:
        return (PRIORITY[relation.order], target, note.rel)
    if relation.order is OrderRule.SOURCE_FIRST:
        return (PRIORITY[relation.order], note.rel, target)
    pair = relation.order.value
    end = relation.contributes if relation.order is OrderRule.SUPPORT else relation.general
    if end is End.NONE:
        return None
    first, second = (target, note.rel) if end is End.TARGET else (note.rel, target)
    if strategy.get(pair, FIRST_TOKENS[pair]) != FIRST_TOKENS[pair]:
        first, second = second, first
    return (PRIORITY[relation.order], first, second)


def order_members(
    members: Sequence[Note],
    relations: Mapping[str, Relation],
    strategy: Mapping[str, str],
    sort: str = "title",
) -> Ordering:
    """Order the members of one block by the constraints of their citations.

    Examples
    --------
    >>> from anagraphe.fields import Citation
    >>> relations = {
    ...     "uses-definition-from": Relation("uses-definition-from", contributes=End.TARGET,
    ...                                      order=OrderRule.SUPPORT),
    ...     "narrows": Relation("narrows", contributes=End.TARGET, order=OrderRule.GENERALITY,
    ...                         general=End.TARGET)}
    >>> members = [Note("case.md", title="Case", cites=(Citation("narrows", "main.md"),)),
    ...            Note("main.md", title="Main", cites=(Citation("uses-definition-from", "def.md"),)),
    ...            Note("def.md", title="Definition"), Note("aside.md", title="Aside")]
    >>> [note.rel for note in order_members(members, relations, {}).members]
    ['aside.md', 'def.md', 'main.md', 'case.md']
    >>> [note.rel for note in order_members(members, relations, {"generality": "specific-first",
    ...                                                           "support": "claim-first"}).members]
    ['aside.md', 'case.md', 'main.md', 'def.md']
    >>> [note.rel for note in order_members(members, relations, {}, sort="file").members]
    ['aside.md', 'def.md', 'main.md', 'case.md']
    """
    by_rel = {member.rel: member for member in members}
    found = sorted(
        {
            rule
            for member in members
            for citation in member.cites
            if not citation.external
            and citation.target in by_rel
            and citation.target != member.rel
            and citation.relation in relations
            for rule in [
                constraint(member, citation.target, relations[citation.relation], strategy)
            ]
            if rule is not None
        }
    )
    after: dict[str, set[str]] = {rel: set() for rel in by_rel}
    result = Ordering()

    def reaches(start: str, goal: str) -> bool:
        stack, seen = [start], {start}
        while stack:
            current = stack.pop()
            if current == goal:
                return True
            for following in after[current] - seen:
                seen.add(following)
                stack.append(following)
        return False

    for _priority, earlier, later in found:
        if later in after[earlier]:
            continue
        if reaches(later, earlier):
            result.conflicts.append((earlier, later))
        else:
            after[earlier].add(later)

    def key(rel: str) -> tuple[str, ...]:
        return sort_key(by_rel[rel], sort)

    pending = {rel: 0 for rel in by_rel}
    for followers in after.values():
        for rel in followers:
            pending[rel] += 1
    ready = [key(rel) for rel, count in pending.items() if count == 0]
    heapq.heapify(ready)
    while ready:
        rel = heapq.heappop(ready)[-1]
        result.members.append(by_rel[rel])
        for following in after[rel]:
            pending[following] -= 1
            if pending[following] == 0:
                heapq.heappush(ready, key(following))
    return result
