"""
Fields that describe a file in its index entry, and the rules that each value obeys.

The decision on generated index entries assigns its entry fields to the metadata of a file: its
purpose, its contributions, and the tasks blocking its status (``blocked_by``). The decision on
typed citations adds the citations of the file (``cites``), each typed by a relation. Their
admissible values are declared in ``specs/vocabulary/relations.yml``: the relations and the strategy
tokens under ``cites``, and the frames of the prose fields under ``schema.frames``. This module
reads those declarations once and validates one value at a time, so the frontmatter checker and
the index generator apply one definition of each field.

Every validator returns a list of problems, each a short lowercase clause, and an empty list for
a valid value. The caller attaches the file and the kind of issue.

Examples
--------
>>> rules = FieldRules.from_vocabulary({
...     "cites": {"relations": {"uses-definition-from": {
...         "contributes": "target", "grade": "argument", "order": "support"}}},
...     "schema": {"frames": {"purpose": {"forbidden_openings": ["to"]}}},
... })
>>> rules.parse_cites([{"relation": "uses-definition-from", "target": "[Gain](notes/gain.md)"}])
((Citation(relation='uses-definition-from', target='notes/gain.md', external=False, use=None),), [])
>>> rules.parse_cites("[Project](projects/_index.md)")[1]
['must be a list of entries {relation, target, for}']
>>> rules.check_purpose("To classify the outputs.")
['opens with a capital', 'closes with a period', 'opens on "to"']
"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

#: A whole value written as one Markdown link, capturing its label and target.
LINK = re.compile(r"^\[(?P<label>[^\]\n]*)\]\((?P<target>[^)\s]+)\)$")
#: A citation key naming an external reference, written ``@authorYYYY``, capturing the key.
CITATION_KEY = re.compile(r"^@([A-Za-z][\w:-]*)$")
#: The keys of a citation entry: the first two required, the third optional.
CITE_KEYS = ("relation", "target", "for")
#: A task identifier, declared by ``🆔`` on a checklist line.
TASK_ID = re.compile(r"^[A-Za-z0-9_-]+$")
#: Abbreviations whose period ends no sentence, removed before searching a sentence boundary.
ABBREVIATIONS = re.compile(r"\b(?:e\.g|i\.e|cf|vs|et al|resp)\.", re.IGNORECASE)
#: A period followed by a space, which separates two sentences.
SENTENCE_BREAK = re.compile(r"\.\s")


class End(Enum):
    """One end of a citation: the citing note (``source``), the cited ``target``, or neither."""

    SOURCE = "source"
    TARGET = "target"
    NONE = "none"


class Grade(Enum):
    """The grade of a contribution, which bounds the chains of relevance toward a goal."""

    ARGUMENT = "argument"
    #: Admitted at most once in a chain toward a goal.
    EXPOSITION = "exposition"
    NONE = "none"


class OrderRule(Enum):
    """Which end of a citation comes first in a construction."""

    #: The contributing end first under ``support-first``, last under ``claim-first``.
    SUPPORT = "support"
    #: The general end first under ``general-first``, last under ``specific-first``.
    GENERALITY = "generality"
    TARGET_FIRST = "target-first"
    SOURCE_FIRST = "source-first"
    NONE = "none"


@dataclass(frozen=True)
class Relation:
    """One relation admitted by ``cites``, with the attributes declared in the vocabulary."""

    name: str
    family: str = ""
    contributes: End = End.NONE
    grade: Grade = Grade.NONE
    order: OrderRule = OrderRule.NONE
    #: Under the order ``generality``, the end holding the general claim.
    general: End = End.NONE
    #: The relation that the other end would declare toward the citing note.
    mirror: str | None = None


@dataclass(frozen=True)
class Citation:
    """One typed citation: a relation toward a repository note or an external reference."""

    relation: str
    #: The repository-relative path, citation key, or external URL of the target.
    target: str
    #: Whether the target is a citation key or an external URL rather than a repository note.
    external: bool = False
    #: The use of the target, stated under ``for``.
    use: str | None = None
    #: Link text of an external URL; absent for repository notes and citation keys.
    link_text: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class StrategyPair:
    """One pair of strategy tokens, of which a block chooses at most one."""

    name: str
    default: str
    tokens: frozenset[str]


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


@dataclass(frozen=True)
class FieldRules:
    """The rules of the entry fields, loaded from the vocabulary."""

    relations: Mapping[str, Relation]
    pairs: tuple[StrategyPair, ...] = ()
    purpose: Frame = Frame()
    contribution: Frame = Frame()
    use: Frame = Frame()

    @classmethod
    def from_vocabulary(cls, raw: Mapping[str, Any]) -> FieldRules:
        """Build the rules from the parsed vocabulary, tolerating absent sections."""
        cites = raw.get("cites") or {}
        frames = (raw.get("schema") or {}).get("frames") or {}
        relations = {
            name: Relation(
                name=name,
                family=str(spec.get("family", "")),
                contributes=End(spec.get("contributes", "none")),
                grade=Grade(spec.get("grade", "none")),
                order=OrderRule(spec.get("order", "none")),
                general=End(spec.get("general", "none")),
                mirror=spec.get("mirror"),
            )
            for name, spec in (cites.get("relations") or {}).items()
        }
        pairs = tuple(
            StrategyPair(
                name=name,
                default=str(spec["default"]),
                tokens=frozenset(spec.get("tokens") or ()),
            )
            for name, spec in (cites.get("strategies") or {}).items()
        )
        return cls(
            relations=relations,
            pairs=pairs,
            purpose=frame_of(frames, "purpose"),
            contribution=frame_of(frames, "contribution"),
            use=frame_of(frames, "for"),
        )

    def parse_cites(self, value: Any) -> tuple[tuple[Citation, ...], list[str]]:
        """Parse a value of ``cites`` into citations, and list its problems.

        An entry with a problem is left out of the citations, so a malformed entry never reaches
        the order or the checks of a target.

        Examples
        --------
        >>> rules = FieldRules({"extends": Relation("extends")}, use=Frame(("to",)))
        >>> rules.parse_cites([{"relation": "extends", "target": "@smith2020",
        ...                     "for": "the decay of the gain"}])[0]
        (Citation(relation='extends', target='smith2020', external=True, use='the decay of the gain'),)
        >>> rules.parse_cites([{"relation": "implies", "target": "notes/x.md", "for": "To prove"}])[1]
        ['entry 1: relation not declared: implies', 'entry 1: target is not a link [Title](path.md) or a key @authorYYYY: notes/x.md', 'entry 1: for opens with a capital', 'entry 1: for opens on "to"']
        """
        if value is None or value == []:
            return ((), ["empty value: declare citations, or remove the key"])
        if not isinstance(value, list):
            return ((), ["must be a list of entries {relation, target, for}"])
        citations: list[Citation] = []
        problems: list[str] = []
        for number, entry in enumerate(value, start=1):
            citation, entry_problems = self._parse_entry(entry)
            problems.extend(f"entry {number}: {problem}" for problem in entry_problems)
            if citation is not None:
                citations.append(citation)
        return (tuple(citations), problems)

    def _parse_entry(self, entry: Any) -> tuple[Citation | None, list[str]]:
        if not isinstance(entry, dict):
            return (None, ["must be an entry {relation, target, for}"])
        problems: list[str] = []
        if not {"relation", "target"} <= set(entry) or not set(entry) <= set(CITE_KEYS):
            problems.append(f"keys must be relation, target and optionally for: {sorted(entry)}")
        relation = str(entry.get("relation", ""))
        if relation not in self.relations:
            problems.append(f"relation not declared: {relation}")
        target = str(entry.get("target", ""))
        link, key = LINK.match(target), CITATION_KEY.match(target)
        if link is None and key is None:
            problems.append(f"target is not a link [Title](path.md) or a key @authorYYYY: {target}")
        use = entry.get("for")
        if use is not None:
            problems.extend(
                f"for {problem}"
                for problem in (
                    self.use.check(use) if isinstance(use, str) else ["must be one string"]
                )
            )
        if problems:
            return (None, problems)
        if key is not None:
            return (Citation(relation, key.group(1), external=True, use=use), [])
        assert link is not None
        raw_target = link.group("target")
        scheme = urllib.parse.urlsplit(raw_target).scheme.lower()
        if scheme in {"http", "https"}:
            return (
                Citation(
                    relation,
                    raw_target,
                    external=True,
                    use=use,
                    link_text=link.group("label"),
                ),
                [],
            )
        path = urllib.parse.unquote(raw_target).split("#", 1)[0]
        return (Citation(relation, path, external=False, use=use), [])

    def resolve_strategy(self, tokens: tuple[str, ...]) -> tuple[dict[str, str], list[str]]:
        """Return the token chosen for each pair, the default where none is given.

        Examples
        --------
        >>> rules = FieldRules({}, pairs=(
        ...     StrategyPair("support", "support-first", frozenset({"support-first", "claim-first"})),
        ...     StrategyPair("generality", "general-first",
        ...                  frozenset({"general-first", "specific-first"}))))
        >>> rules.resolve_strategy(("claim-first",))
        ({'support': 'claim-first', 'generality': 'general-first'}, [])
        >>> rules.resolve_strategy(("claim-first", "support-first", "sideways"))[1]
        ['unknown strategy token: sideways', 'two tokens of the pair support: claim-first, support-first']
        """
        problems = [
            f"unknown strategy token: {token}"
            for token in tokens
            if not any(token in pair.tokens for pair in self.pairs)
        ]
        chosen: dict[str, str] = {}
        for pair in self.pairs:
            given = [token for token in tokens if token in pair.tokens]
            if len(given) > 1:
                problems.append(f"two tokens of the pair {pair.name}: {', '.join(given)}")
            chosen[pair.name] = given[0] if given else pair.default
        return (chosen, problems)

    def check_purpose(self, value: Any) -> list[str]:
        """Return the problems of a ``purpose`` value, which must be one string in its frame."""
        if not isinstance(value, str):
            return ["must be one string"]
        return self.purpose.check(value)

    def check_contribution(self, value: Any) -> list[str]:
        """Return the problems of a ``contribution`` value, a list of clauses in their frame.

        Examples
        --------
        >>> rules = FieldRules({}, contribution=Frame(("this note",)))
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
