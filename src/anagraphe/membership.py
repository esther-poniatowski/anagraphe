"""
Membership of the groups of one index.

The index of a collection assigns each of its members to one group (ADR 0002), in three steps:

1. a group holds by name the files listed in its ``members``, else those listed in the
   ``sequence`` of a group declaring no filter. A file named by two groups belongs to the first,
   and the second name is reported;
2. a member held by no name belongs to the first group whose filter ``where`` it matches;
3. any other member belongs to the catch-all group ``*``, where the index declares one.

A member placed by none of the three steps is absent from the assignment, so that the generator
reports it. The checks of the membership are reported on the index, since the index declares it.

Examples
--------
>>> groups = (GroupSpec("parts", sequence=("m/b.md",)),
...           GroupSpec("talks", where=(("kind", ("talk",)),)), GroupSpec("*"))
>>> members = [Note("m/a.md", data={"kind": "talk"}), Note("m/b.md", data={"kind": "talk"}),
...            Note("m/c.md")]
>>> membership = assign("m/_index.md", groups, members, {}, lambda rel: True)
>>> membership.assigned, membership.issues
({'m/a.md': 'talks', 'm/b.md': 'parts', 'm/c.md': '*'}, [])
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping, Sequence

from anagraphe.issues import Issue
from anagraphe.notes import Note
from anagraphe.slots import GroupSpec


@dataclass
class Membership:
    """The group of each placed member, and the issues of the declared membership."""

    #: The id of the group holding each placed member, by repository-relative path.
    assigned: dict[str, str] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)


def _named(
    index_rel: str,
    groups: Sequence[GroupSpec],
    rels: set[str],
    exists: Callable[[str], bool],
    issues: list[Issue],
) -> dict[str, str]:
    """Return the group naming each file, reporting a name outside the members or repeated."""
    named: dict[str, str] = {}
    for group in groups:
        source = "members" if group.members is not None else "sequence"
        for target in group.links:
            if target not in rels:
                problem = (
                    f"{source} of group {group.id} names {target}, which {index_rel} does not list"
                    if exists(target)
                    else f"{source} of group {group.id} names no file: {target}"
                )
                issues.append(Issue(index_rel, 1, "invalid-link", problem))
            elif target not in named:
                named[target] = group.id
            elif named[target] == group.id:
                issues.append(
                    Issue(
                        index_rel,
                        1,
                        "duplicate-member",
                        f"{source} of group {group.id} names {target} twice",
                    )
                )
            else:
                issues.append(
                    Issue(
                        index_rel,
                        1,
                        "duplicate-member",
                        f"{target} is named by the groups {named[target]} and {group.id}; "
                        f"it belongs to {named[target]}",
                    )
                )
    return named


def _filter_issues(
    index_rel: str,
    groups: Sequence[GroupSpec],
    members: Sequence[Note],
    values: Mapping[str, tuple[str, ...]],
) -> list[Issue]:
    """Report a filter naming a key that no member declares, or a value outside its field."""
    declared = {key for note in members for key in note.data}
    issues: list[Issue] = []
    for group in groups:
        for key, wanted in group.where:
            if key not in declared:
                issues.append(
                    Issue(
                        index_rel,
                        1,
                        "unknown-filter-key",
                        f"where of group {group.id} names {key}, which no member declares",
                    )
                )
            elif key in values:
                issues.extend(
                    Issue(
                        index_rel,
                        1,
                        "undeclared-value",
                        f"where of group {group.id}: {key} admits no value {value}; "
                        f"its values are {', '.join(values[key])}",
                    )
                    for value in wanted
                    if value not in values[key]
                )
    return issues


def assign(
    index_rel: str,
    groups: Sequence[GroupSpec],
    members: Sequence[Note],
    values: Mapping[str, tuple[str, ...]],
    exists: Callable[[str], bool],
) -> Membership:
    """Assign each member of an index to one of its groups, and report the declared membership.

    Parameters
    ----------
    index_rel
        Repository-relative path of the index, where the issues are located.
    groups
        The groups declared by the index, in their order.
    members
        The files that the index lists.
    values
        The declared values of each categorical key.
    exists
        Whether a repository-relative path names a file, which separates a link naming no file
        from a link naming a file that the index does not list.
    """
    rels = {note.rel for note in members}
    issues: list[Issue] = []
    named = _named(index_rel, groups, rels, exists, issues)
    issues.extend(_filter_issues(index_rel, groups, members, values))
    catch_all = any(group.id == "*" for group in groups)
    assigned: dict[str, str] = {}
    for note in members:
        # An explicit list prevails over the filter of its own group, reported at parsing.
        group = named.get(note.rel) or next(
            (spec.id for spec in groups if spec.members is None and spec.selects(note.data)),
            "*" if catch_all else None,
        )
        if group is not None:
            assigned[note.rel] = group
    return Membership(assigned, issues)
