"""
Slots of an index: its groups, its contextual relations, and the units written outside the slots.

The decision on index slots admits five slots in an index. The groups are declared in the key
``groups`` of the index, and the generator renders them inside one region ``<!-- index groups -->``.
The distinctions between two members are declared in the key ``context_relations``. Outside the
frontmatter and the generated regions, an index admits only its H1 heading, callouts
``[!IMPORTANT]`` and ``[!WARNING]``, and embedded views. :func:`prose_units` lists every other
unit, so that the generator reports it until it moves to its owner.

Examples
--------
>>> groups, problems = parse_groups([{"id": "core", "heading": "Core", "show": ["purpose"]},
...                                  {"id": "*"}])
>>> [(group.id, group.heading, group.show) for group in groups], problems
([('core', 'Core', ('purpose',)), ('*', None, ())], [])
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

#: The keys of one group, the id alone being required.
GROUP_KEYS = frozenset(
    {
        "id",
        "heading",
        "description",
        "mode",
        "sort",
        "strategy",
        "show",
        "where",
        "nest",
    }
)
#: The keys of one file listed by an index without being a note, the group alone being optional.
FILE_KEYS = frozenset({"file", "title", "purpose", "group"})
#: The keys of one contextual relation, ``for`` alone being optional.
RELATION_KEYS = frozenset({"source", "relation", "target", "for"})
#: The callouts that an index may hold: a convention binding in the folder, and a caveat.
ADMITTED_CALLOUTS = frozenset({"IMPORTANT", "WARNING"})
#: The code blocks embedding a view, which an index may hold beside its slots.
VIEW_LANGUAGES = frozenset({"base", "dataview"})
#: A whole value written as one Markdown link, capturing its target.
LINK = re.compile(r"^\[[^\]\n]*\]\(([^)\s]+)\)$")
#: The opening of a callout, capturing its type and its title.
CALLOUT = re.compile(r"^>\s*\[!(?P<type>[A-Za-z]+)\][-+]?\s*(?P<title>.*)$")
#: The most words that the title of a callout may hold.
TITLE_WORDS = 6
#: The opening of a fenced code block, capturing its language.
FENCE = re.compile(r"^```(?P<language>\S*)")


@dataclass(frozen=True)
class GroupSpec:
    """One group of an index, as its frontmatter declares it."""

    id: str
    heading: str | None = None
    #: One sentence describing the group, written under its heading.
    description: str | None = None
    mode: str | None = None
    sort: str = "title"
    strategy: tuple[str, ...] = ()
    show: tuple[str, ...] = ()
    #: The key values selecting the members of the group, each key admitting a set of values.
    where: tuple[tuple[str, tuple[str, ...]], ...] = ()
    #: The key, as a dotted path, naming the parent of each member within the group.
    nest: str | None = None

    def selects(self, data: Mapping[str, Any]) -> bool:
        """Whether the frontmatter of a member matches every key value of the group.

        Examples
        --------
        >>> GroupSpec("keynotes", where=(("kind", ("keynote",)),)).selects({"kind": "keynote"})
        True
        >>> GroupSpec("missed", where=(("attended", ("false",)),)).selects({"attended": False})
        True
        """
        return bool(self.where) and all(
            scalar(data.get(key)) in values for key, values in self.where
        )


@dataclass(frozen=True)
class FileSpec:
    """A file that an index lists without reading it, such as a PDF, with its declared entry."""

    file: str
    title: str
    purpose: str | None = None
    group: str = "*"


def scalar(value: Any) -> str:
    """Return a frontmatter value in the form that a filter compares, booleans in lowercase."""
    if isinstance(value, bool):
        return str(value).lower()
    return "" if value is None else str(value)


@dataclass(frozen=True)
class ContextRelation:
    """A relation between two members, holding only within the collection of one index."""

    source: str
    relation: str
    target: str
    #: The criterion of the relation, such as the property separating two notes.
    use: str | None = None


def as_strings(value: Any) -> tuple[str, ...]:
    """Return a list or a comma-separated string as a tuple of strings."""
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(item.strip() for item in value.split(",") if item.strip())
    return tuple(str(item) for item in value)


def parse_groups(value: Any) -> tuple[tuple[GroupSpec, ...], list[str]]:
    """Parse the key ``groups`` of an index, and list its problems.

    Examples
    --------
    >>> parse_groups([{"id": "core"}, {"id": "core", "colour": "red"}, "loose"])[1]
    ['group 2: unknown keys: colour', 'group 2: the id core is declared twice', 'group 3: must be a mapping with an id']
    """
    if value is None:
        return ((), [])
    if not isinstance(value, list):
        return ((), ["groups must be a list of mappings"])
    groups: list[GroupSpec] = []
    problems: list[str] = []
    for number, entry in enumerate(value, start=1):
        if not isinstance(entry, Mapping) or "id" not in entry:
            problems.append(f"group {number}: must be a mapping with an id")
            continue
        unknown = sorted(set(entry) - GROUP_KEYS)
        if unknown:
            problems.append(f"group {number}: unknown keys: {', '.join(unknown)}")
        if any(group.id == str(entry["id"]) for group in groups):
            problems.append(f"group {number}: the id {entry['id']} is declared twice")
            continue
        groups.append(
            GroupSpec(
                id=str(entry["id"]),
                heading=str(entry["heading"]) if entry.get("heading") else None,
                description=(str(entry["description"]) if entry.get("description") else None),
                mode=str(entry["mode"]) if entry.get("mode") else None,
                sort=str(entry.get("sort") or "title"),
                strategy=as_strings(entry.get("strategy")),
                show=as_strings(entry.get("show")),
                nest=str(entry["nest"]) if entry.get("nest") else None,
                where=(
                    tuple(
                        (
                            str(key),
                            tuple(
                                scalar(item)
                                for item in (values if isinstance(values, list) else [values])
                            ),
                        )
                        for key, values in (entry.get("where") or {}).items()
                    )
                    if isinstance(entry.get("where"), Mapping)
                    else ()
                ),
            )
        )
        if "where" in entry and not isinstance(entry["where"], Mapping):
            problems.append(f"group {number}: where must map keys to values")
    return (tuple(groups), problems)


def parse_files(value: Any) -> tuple[tuple[FileSpec, ...], list[str]]:
    """Parse the key ``files`` of an index, and list its problems.

    Examples
    --------
    >>> parse_files([{"file": "program.pdf", "title": "Workshop program"}, {"file": "x.pdf"}])
    ((FileSpec(file='program.pdf', title='Workshop program', purpose=None, group='*'),), ['file 2: must be a mapping with a file and a title'])
    """
    if value is None:
        return ((), [])
    if not isinstance(value, list):
        return ((), ["files must be a list of mappings"])
    files: list[FileSpec] = []
    problems: list[str] = []
    for number, entry in enumerate(value, start=1):
        if not isinstance(entry, Mapping) or not {"file", "title"} <= set(entry):
            problems.append(f"file {number}: must be a mapping with a file and a title")
            continue
        unknown = sorted(set(entry) - FILE_KEYS)
        if unknown:
            problems.append(f"file {number}: unknown keys: {', '.join(unknown)}")
        files.append(
            FileSpec(
                str(entry["file"]),
                str(entry["title"]),
                str(entry["purpose"]) if entry.get("purpose") else None,
                str(entry.get("group") or "*"),
            )
        )
    return (tuple(files), problems)


def parse_context_relations(
    value: Any,
) -> tuple[tuple[ContextRelation, ...], list[str]]:
    """Parse the key ``context_relations`` of an index, and list its problems.

    Examples
    --------
    >>> relations, problems = parse_context_relations([
    ...     {"source": "[A](m/a.md)", "relation": "contrasts", "target": "[B](m/b.md)",
    ...      "for": "the scale of the claim"}, {"source": "m/a.md"}])
    >>> relations[0].target, problems
    ('m/b.md', ['relation 2: keys must be source, relation, target and optionally for', 'relation 2: source is not a link [Title](path.md): m/a.md', 'relation 2: target is not a link [Title](path.md): '])
    """
    if value is None:
        return ((), [])
    if not isinstance(value, list):
        return ((), ["context_relations must be a list of mappings"])
    relations: list[ContextRelation] = []
    problems: list[str] = []
    for number, entry in enumerate(value, start=1):
        if not isinstance(entry, Mapping):
            problems.append(f"relation {number}: must be a mapping")
            continue
        entry_problems = []
        if not {"source", "relation", "target"} <= set(entry) or not set(entry) <= RELATION_KEYS:
            entry_problems.append("keys must be source, relation, target and optionally for")
        ends = {}
        for end in ("source", "target"):
            match = LINK.match(str(entry.get(end, "")))
            if match is None:
                entry_problems.append(f"{end} is not a link [Title](path.md): {entry.get(end, '')}")
            else:
                ends[end] = match.group(1).split("#", 1)[0]
        problems.extend(f"relation {number}: {problem}" for problem in entry_problems)
        if not entry_problems:
            relations.append(
                ContextRelation(
                    ends["source"],
                    str(entry["relation"]),
                    ends["target"],
                    str(entry["for"]) if entry.get("for") else None,
                )
            )
    return (tuple(relations), problems)


def prose_units(text: str) -> list[tuple[int, str]]:
    """Return the units of an index written outside its slots, as ``(line, description)``.

    The frontmatter, the generated regions, the H1 heading, the admitted callouts and the embedded
    views are skipped, and so is the heading of a control block, which belongs to that block. An
    admitted callout needs a brief title naming its topic, and a body. Each other unit, a run of
    lines without a blank line, is reported once.

    Examples
    --------
    >>> text = ("---\\nrole: index\\n---\\n\\n# Module\\n\\nA paragraph.\\n\\n> [!WARNING] Kept\\n"
    ...         "> body\\n\\n> [!NOTE] Moved\\n\\n<!-- index groups -->\\n## A\\n<!-- /index -->\\n"
    ...         "\\n- [Loose](loose.md)\\n\\n> [!IMPORTANT] A rule stated as its title.\\n")
    >>> [line for line, _description in prose_units(text)]
    [7, 12, 18, 20]
    """
    lines = text.split("\n")
    start = 0
    if lines and lines[0] == "---":
        start = next((number for number in range(1, len(lines)) if lines[number] == "---"), 0) + 1
    units: list[tuple[int, str]] = []
    in_block = False
    fence: str | None = None
    unit_open = False
    heading_seen = False
    for number in range(start, len(lines)):
        line = lines[number]
        if in_block:
            in_block = not line.startswith("<!-- /index -->")
            continue
        if fence is not None:
            if line.startswith("```"):
                fence = None
            continue
        if line.startswith("<!-- index"):
            in_block, unit_open = True, False
            continue
        if not line.strip():
            unit_open = False
            continue
        fenced = FENCE.match(line)
        if fenced:
            fence = fenced.group("language")
            if fence not in VIEW_LANGUAGES:
                units.append((number + 1, f"code block: {line}"))
            unit_open = False
            continue
        if unit_open:
            continue
        unit_open = True
        if line.startswith("# ") and not heading_seen:
            heading_seen = True
            unit_open = False
            continue
        following = next((later for later in lines[number + 1 :] if later.strip()), "")
        view = FENCE.match(following)
        # The heading of a control block or of an embedded view belongs to that block or view.
        if line.startswith("#") and (
            following.startswith("<!-- index control")
            or (view is not None and view.group("language") in VIEW_LANGUAGES)
        ):
            unit_open = False
            continue
        callout = CALLOUT.match(line)
        if callout:
            kind = callout.group("type").upper()
            title = callout.group("title").strip()
            has_body = number + 1 < len(lines) and lines[number + 1].startswith(">")
            if kind not in ADMITTED_CALLOUTS:
                units.append((number + 1, f"callout {kind}: {line[:60]}"))
            elif (
                not title or len(title.split()) > TITLE_WORDS or title.endswith(".") or not has_body
            ):
                units.append(
                    (
                        number + 1,
                        f"callout {kind} without a brief title and a body: " f"{line[:60]}",
                    )
                )
            continue
        kind = (
            "heading"
            if line.startswith("#")
            else (
                "list"
                if re.match(r"^\s*([-*+]|\d+\.)\s", line)
                else (
                    "table"
                    if line.startswith("|")
                    else "quote" if line.startswith(">") else "paragraph"
                )
            )
        )
        units.append((number + 1, f"{kind}: {line[:60]}"))
    return units
