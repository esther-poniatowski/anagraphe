"""
Fields that describe a file in its index entry, and the rules that each value obeys.

The decision on generated index entries assigns its entry fields to the metadata of a file: its
purpose, its contributions, and the tasks blocking its status (``blocked_by``). The vocabulary of
the repository declares the frames of the prose fields under ``schema.frames``, the closed value
sets of the categorical keys under ``key_values``, the relations admitted by the table
``context_relations`` of an index under ``context_relations``, and the statuses of an archived
note under ``archived_statuses``. This module reads those
declarations once and validates one value at a time, so the frontmatter checker and the index
generator apply one definition of each field.

Every validator returns a list of problems, each a short lowercase clause, and an empty list for
a valid value. The caller attaches the file and the kind of issue.

Examples
--------
>>> rules = FieldRules.from_vocabulary({
...     "schema": {"frames": {"purpose": {"forbidden_openings": ["to"]}}},
...     "key_values": {"kind": {"keynote": "a plenary lecture", "talk": "a contributed talk"}},
...     "context_relations": ["contrasts"],
...     "archived_statuses": ["archived"],
... })
>>> rules.values["kind"], sorted(rules.relations), rules.archived
(('keynote', 'talk'), ['contrasts'], ('archived',))
>>> rules.check_purpose("To classify the outputs.")
['opens with a capital', 'closes with a period', 'opens on "to"']
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from anagraphe.slots import scalar

#: A task identifier, declared by ``🆔`` on a checklist line.
TASK_ID = re.compile(r"^[A-Za-z0-9_-]+$")
#: Abbreviations whose period ends no sentence, removed before searching a sentence boundary.
ABBREVIATIONS = re.compile(r"\b(?:e\.g|i\.e|cf|vs|et al|resp)\.", re.IGNORECASE)
#: A period followed by a space, which separates two sentences.
SENTENCE_BREAK = re.compile(r"\.\s")


@dataclass(frozen=True)
class Frame:
    """The frame of one prose field: one clause, in lowercase, without a terminal period."""

    #: Openings breaking the frame, compared in lowercase and word by word.
    forbidden_openings: tuple[str, ...] = ()

    def check(self, text: str) -> list[str]:
        """Return the ways in which one clause breaks the frame.

        Examples
        --------
        >>> Frame(("this note",)).check("this note derives the bound. it holds")
        ['holds more than one sentence', 'opens on "this note"']
        >>> Frame().check("the bound holds, e.g. for small steps")
        []
        """
        problems: list[str] = []
        stripped = text.strip()
        if not stripped:
            return ["is empty"]
        if stripped[0].isupper():
            problems.append("opens with a capital")
        if stripped.endswith("."):
            problems.append("closes with a period")
        if SENTENCE_BREAK.search(ABBREVIATIONS.sub("", stripped)):
            problems.append("holds more than one sentence")
        lowered = stripped.lower()
        problems.extend(
            f'opens on "{opening}"'
            for opening in self.forbidden_openings
            if re.match(rf"{re.escape(opening)}\b", lowered)
        )
        return problems


def frame_of(frames: Mapping[str, Any], name: str) -> Frame:
    """Return the frame declared for one prose field, an empty frame when undeclared."""
    return Frame(
        tuple(str(item) for item in (frames.get(name) or {}).get("forbidden_openings", ()))
    )


def declared_values(value: Any) -> tuple[str, ...]:
    """Return the values of one closed set, in their declared order.

    A set is written either as a list of values or as a mapping from each value to its gloss.
    Each value is compared in the form that a filter compares, so a boolean reads in lowercase.

    Examples
    --------
    >>> declared_values({"keynote": "a lecture", "talk": "a talk"}), declared_values([True, 2])
    (('keynote', 'talk'), ('true', '2'))
    """
    items = value.keys() if isinstance(value, Mapping) else value or ()
    return tuple(scalar(item) for item in items)


@dataclass(frozen=True)
class FieldRules:
    """The rules of the entry fields, loaded from the vocabulary."""

    #: The declared values of each categorical key, in their declared order.
    values: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    #: The relations admitted by the table ``context_relations`` of an index.
    relations: frozenset[str] = frozenset()
    #: The statuses of an archived note, the only notes that may declare ``superseded_by``.
    archived: tuple[str, ...] = ()
    purpose: Frame = Frame()
    contribution: Frame = Frame()
    use: Frame = Frame()

    @classmethod
    def from_vocabulary(cls, raw: Mapping[str, Any]) -> FieldRules:
        """Build the rules from the parsed vocabulary, tolerating absent sections."""
        frames = (raw.get("schema") or {}).get("frames") or {}
        relations = raw.get("context_relations") or ()
        return cls(
            values={
                str(key): declared_values(spec)
                for key, spec in (raw.get("key_values") or {}).items()
            },
            relations=frozenset(str(name) for name in relations),
            archived=tuple(scalar(status) for status in raw.get("archived_statuses") or ()),
            purpose=frame_of(frames, "purpose"),
            contribution=frame_of(frames, "contribution"),
            use=frame_of(frames, "for"),
        )

    def check_purpose(self, value: Any) -> list[str]:
        """Return the problems of a ``purpose`` value, which must be one string in its frame."""
        if not isinstance(value, str):
            return ["must be one string"]
        return self.purpose.check(value)

    def check_superseded(self, status: str | None) -> list[str]:
        """Return the problems of a note declaring ``superseded_by``, whose status must be archived.

        Examples
        --------
        >>> rules = FieldRules(archived=("archived",))
        >>> rules.check_superseded("archived"), rules.check_superseded("wip")
        ([], ['the status wip is not declared under archived_statuses: archived'])
        >>> FieldRules().check_superseded(None)
        ['the file declares no status']
        """
        if status is None:
            return ["the file declares no status"]
        if status in self.archived:
            return []
        declared = ", ".join(self.archived) if self.archived else "none declared"
        return [f"the status {status} is not declared under archived_statuses: {declared}"]

    def check_contribution(self, value: Any) -> list[str]:
        """Return the problems of a ``contribution`` value, a list of clauses in their frame.

        Examples
        --------
        >>> rules = FieldRules(contribution=Frame(("this note",)))
        >>> rules.check_contribution(["the gain decays", "This note derives the bound"])
        ['item 2 opens with a capital', 'item 2 opens on "this note"']
        """
        if not isinstance(value, list):
            return ["must be a list of clauses"]
        return [
            f"item {number} {problem}"
            for number, item in enumerate(value, start=1)
            for problem in (
                self.contribution.check(item) if isinstance(item, str) else ["must be one string"]
            )
        ]

    @staticmethod
    def check_blocked_by(value: Any) -> list[str]:
        """Return the problems of a ``blocked_by`` value, a list of task identifiers.

        Examples
        --------
        >>> FieldRules.check_blocked_by(["brief-draft", "two words"])
        ['not a task identifier: two words']
        >>> FieldRules.check_blocked_by("brief-draft")
        ['must be a list of task identifiers']
        """
        if not isinstance(value, list):
            return ["must be a list of task identifiers"]
        return [f"not a task identifier: {item}" for item in value if not TASK_ID.match(str(item))]
