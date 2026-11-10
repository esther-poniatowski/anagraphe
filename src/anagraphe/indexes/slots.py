"""
Slots of an index: its groups, its dependencies, its contextual relations, and the units written
outside the slots.

The index of a collection is the specification of that collection (ADR 0002). Its key ``groups``
declares each group: its membership, its ordering mode and its order, its nesting, and the keys
displayed after each entry. The generator renders the groups inside one region
``<!-- index groups -->``. The key ``external`` lists the files outside the folder on which the
index depends, each with its use in ``for``, and the key ``context_relations`` states the
distinctions between two members. Outside the frontmatter and the generated regions, an index
admits only its H1 heading, callouts ``[!IMPORTANT]`` and ``[!WARNING]``, and embedded views.
:func:`prose_units` lists every other unit, so that the generator reports it until it moves to
its owner.

Every link of a slot names its file from the repository root.

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

from anagraphe.core.filters import Filter, parse_filter, scalar, scalars
from anagraphe.core.links import Target, link_target, value_link
from anagraphe.core.regions import fenced_blocks
from anagraphe.indexes.retired import RETIRED_MODES, retired_keys, retired_mode

#: The keys of one group, the id alone being required.
GROUP_KEYS = frozenset(
    {
        "id",
        "heading",
        "description",
        "where",
        "members",
        "mode",
        "sort",
        "order",
        "sequence",
        "nest",
        "show",
    }
)
#: The ordering modes that a group may name with ``mode``.
MODES = ("registry", "sequence")
#: The sort keys handled apart from the keys of the members, the first being the default.
SORT_KEYS = ("title", "file", "date")
#: The keys of one file listed by an index without being a note, the group alone being optional.
FILE_KEYS = frozenset({"file", "title", "purpose", "group"})
#: The keys of one contextual relation, ``for`` alone being optional.
RELATION_KEYS = frozenset({"source", "relation", "target", "for"})
#: The keys of one dependency listed by ``external``, both required.
EXTERNAL_KEYS = frozenset({"target", "for"})
#: The callouts that an index may hold: a convention binding in the folder, and a caveat.
ADMITTED_CALLOUTS = frozenset({"IMPORTANT", "WARNING"})
#: The code blocks embedding a view, which an index may hold beside its slots.
VIEW_LANGUAGES = frozenset({"base", "dataview"})
#: The opening of a callout, capturing its type and its title.
CALLOUT = re.compile(r"^>\s*\[!(?P<type>[A-Za-z]+)\][-+]?\s*(?P<title>.*)$")
#: The most words that the title of a callout may hold.
TITLE_WORDS = 6


@dataclass(frozen=True)
class GroupSpec:
    """One group of an index, as its frontmatter declares it."""

    id: str
    heading: str | None = None
    #: One sentence describing the group, written under its heading.
    description: str | None = None
    #: The declared ordering mode, among ``MODES``, or None for the default mode of the type.
    mode: str | None = None
    #: The keys of the order, the first deciding, each later one breaking the ties of the former.
    sort: tuple[str, ...] = (SORT_KEYS[0],)
    #: The order of the values of the first sort key, overriding its declared values.
    order: tuple[str, ...] = ()
    show: tuple[str, ...] = ()
    #: The key values selecting the members of the group, each key admitting a set of values.
    where: tuple[tuple[str, tuple[str, ...]], ...] = ()
    #: The files listed explicitly as members, or None when the group lists none.
    members: tuple[str, ...] | None = None
    #: The files giving the order of a sequence, or None when the group declares none.
    sequence: tuple[str, ...] | None = None
    #: The key, as a dotted path, naming the parent of each member within the group.
    nest: str | None = None

    @property
    def links(self) -> tuple[str, ...]:
        """The files that the group holds by name: its members, else the sequence of a group
        declaring no filter.

        Examples
        --------
        >>> GroupSpec("parts", sequence=("m/a.md", "m/b.md")).links
        ('m/a.md', 'm/b.md')
        >>> GroupSpec("talks", where=(("kind", ("talk",)),), sequence=("m/a.md",)).links
        ()
        """
        if self.members is not None:
            return self.members
        if self.sequence is not None and not self.where:
            return self.sequence
        return ()

    def selects(self, data: Mapping[str, Any]) -> bool:
        """Whether the frontmatter of a member matches every key value of the group.

        Examples
        --------
        >>> GroupSpec("keynotes", where=(("kind", ("keynote",)),)).selects({"kind": "keynote"})
        True
        >>> GroupSpec("missed", where=(("attended", ("false",)),)).selects({"attended": False})
        True
        >>> GroupSpec("tagged", where=(("tags", ("x",)),)).selects({"tags": ["y", "x"]})
        True
        """
        return Filter(self.where).selects(data)


@dataclass(frozen=True)
class FileSpec:
    """A file that an index lists without reading it, such as a PDF, with its declared entry."""

    file: str
    title: str
    purpose: str | None = None
    group: str = "*"


@dataclass(frozen=True)
class ExternalSpec:
    """A file outside the folder of an index, on which the index depends.

    The file lies in the repository, or elsewhere when its link is a URL, such as the permalink of
    a file of another repository.

    Examples
    --------
    >>> ExternalSpec("https://example.org/a.md", "the bound").remote
    True
    >>> ExternalSpec("shared/a.md", "the bound").remote
    False
    """

    #: The repository-relative path of the file, or the whole URL of a remote file.
    target: str
    #: The use of the file by the index, stated under ``for``.
    use: str

    @property
    def remote(self) -> bool:
        """Whether the file lies outside the repository, named by a URL."""
        return Target.parse(self.target).scheme is not None


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


def _links(entry: Mapping[str, Any], key: str) -> tuple[tuple[str, ...] | None, list[str]]:
    """Return the files named by a list of links of a group, None when the key is absent."""
    if key not in entry:
        return (None, [])
    value = entry[key]
    if not isinstance(value, list):
        return ((), [f"{key} must be a list of links [Title](path.md)"])
    targets: list[str] = []
    problems: list[str] = []
    for number, item in enumerate(value, start=1):
        target = link_target(item)
        if target is None:
            problems.append(f"{key} item {number} is not a link [Title](path.md): {item}")
        else:
            targets.append(target)
    return (tuple(targets), problems)


def _mode(value: Any) -> tuple[str | None, list[str]]:
    """Return a declared mode, None for an absent or invalid one, and its problems."""
    if not value:
        return (None, [])
    mode = str(value)
    if mode in RETIRED_MODES:
        return (None, [retired_mode(mode)])
    if mode not in MODES:
        return (None, [f"unknown mode: {mode}"])
    return (mode, [])


def _where(value: Any) -> tuple[tuple[tuple[str, tuple[str, ...]], ...], list[str]]:
    """Return the key values of a filter, each key admitting one value or a list of values."""
    if value is None:
        return ((), [])
    parsed, problems = parse_filter(value)
    return (parsed.conditions, [f"where {problem}" for problem in problems])


def parse_groups(value: Any) -> tuple[tuple[GroupSpec, ...], list[str]]:
    """Parse the key ``groups`` of an index, and list its problems.

    Examples
    --------
    >>> parse_groups([{"id": "core"}, {"id": "core", "colour": "red"}, "loose"])[1]
    ['group 2: unknown keys: colour', 'group 2: the id core is declared twice', 'group 3: must be a mapping with an id']
    >>> groups, problems = parse_groups([{"id": "parts", "mode": "construction",
    ...     "sort": ["kind", "date"], "sequence": ["[A](m/a.md)", "m/b.md"]}])
    >>> groups[0].sort, groups[0].sequence, groups[0].mode
    (('kind', 'date'), ('m/a.md',), None)
    >>> problems
    ['group 1: the mode construction is retired: use registry, sorted by a key, or sequence, ordered by a list of links', 'group 1: sequence item 2 is not a link [Title](path.md): m/b.md']
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
        retired = retired_keys("group", entry)
        entry_problems = [retired_key.message() for retired_key in retired]
        show = as_strings(entry.get("show"))
        # A retired member key displays nothing, so its place in show is reported, not dropped.
        entry_problems.extend(
            f"show: {retired_key.message()}"
            for retired_key in retired_keys("note", dict.fromkeys(show))
        )
        unknown = sorted(set(entry) - GROUP_KEYS - {retired_key.key for retired_key in retired})
        if unknown:
            entry_problems.append(f"unknown keys: {', '.join(unknown)}")
        if any(group.id == str(entry["id"]) for group in groups):
            entry_problems.append(f"the id {entry['id']} is declared twice")
            problems.extend(f"group {number}: {problem}" for problem in entry_problems)
            continue
        mode, mode_problems = _mode(entry.get("mode"))
        where, where_problems = _where(entry.get("where"))
        members, member_problems = _links(entry, "members")
        sequence, sequence_problems = _links(entry, "sequence")
        order = entry.get("order")
        order_problems = (
            ["order must be a list of values"]
            if order is not None and not isinstance(order, list)
            else []
        )
        if members is not None and where:
            entry_problems.append("members prevails over where, so where selects nothing")
        entry_problems.extend(
            mode_problems + where_problems + member_problems + sequence_problems + order_problems
        )
        problems.extend(f"group {number}: {problem}" for problem in entry_problems)
        groups.append(
            GroupSpec(
                id=str(entry["id"]),
                heading=str(entry["heading"]) if entry.get("heading") else None,
                description=(str(entry["description"]) if entry.get("description") else None),
                mode=mode,
                sort=as_strings(entry.get("sort")) or (SORT_KEYS[0],),
                order=tuple(scalar(item) for item in order) if isinstance(order, list) else (),
                show=show,
                where=where,
                members=members,
                sequence=sequence,
                nest=str(entry["nest"]) if entry.get("nest") else None,
            )
        )
    return (tuple(groups), problems)


def parse_external(value: Any) -> tuple[tuple[ExternalSpec, ...], list[str]]:
    """Parse the key ``external`` of an index, and list its problems.

    Examples
    --------
    >>> parse_external([{"target": "[Kernels](foundations/kernels.md)", "for": "the kernel"},
    ...                 {"target": "foundations/x.md"}])
    ((ExternalSpec(target='foundations/kernels.md', use='the kernel'),), ['external 2: keys must be target and for', 'external 2: target is not a link [Title](path.md): foundations/x.md'])
    >>> parse_external([{"target": "[Rule](https://example.org/r.md)", "for": "the rule"}])[0]
    (ExternalSpec(target='https://example.org/r.md', use='the rule'),)
    """
    if value is None:
        return ((), [])
    if not isinstance(value, list):
        return ((), ["external must be a list of mappings {target, for}"])
    entries: list[ExternalSpec] = []
    problems: list[str] = []
    for number, entry in enumerate(value, start=1):
        if not isinstance(entry, Mapping):
            problems.append(f"external {number}: must be a mapping {{target, for}}")
            continue
        entry_problems: list[str] = []
        if set(entry) != EXTERNAL_KEYS:
            entry_problems.append("keys must be target and for")
        # A URL names a remote file, kept whole; any other target is a path from the root.
        raw = value_link(entry.get("target"))
        remote = raw is not None and Target.parse(raw).scheme is not None
        target = raw if remote else link_target(entry.get("target"))
        if target is None:
            entry_problems.append(
                f"target is not a link [Title](path.md): {entry.get('target', '')}"
            )
        use = entry.get("for")
        if "for" in entry and (not isinstance(use, str) or not use.strip()):
            entry_problems.append("for must state the use of the file in one clause")
        problems.extend(f"external {number}: {problem}" for problem in entry_problems)
        if not entry_problems and target is not None and isinstance(use, str):
            entries.append(ExternalSpec(target, use))
    return (tuple(entries), problems)


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
            target = link_target(entry.get(end))
            if target is None:
                entry_problems.append(f"{end} is not a link [Title](path.md): {entry.get(end, '')}")
            else:
                ends[end] = target
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
    # A code block inside a quotation or indented in a list item belongs to the enclosing unit.
    blocks = {
        block.first: block
        for block in fenced_blocks(text)
        if not block.quoted and not block.indented
    }
    in_block = False
    inside_code_until = -1
    unit_open = False
    heading_seen = False
    for number in range(start, len(lines)):
        line = lines[number]
        if in_block:
            in_block = not line.startswith("<!-- /index -->")
            continue
        if number <= inside_code_until:
            continue
        if line.startswith("<!-- index"):
            in_block, unit_open = True, False
            continue
        if not line.strip():
            unit_open = False
            continue
        block = blocks.get(number)
        if block is not None:
            inside_code_until = block.last
            if block.language not in VIEW_LANGUAGES:
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
        following_number = next(
            (later for later in range(number + 1, len(lines)) if lines[later].strip()), None
        )
        following = lines[following_number] if following_number is not None else ""
        view = blocks.get(following_number) if following_number is not None else None
        # The heading of a control block or of an embedded view belongs to that block or view.
        if line.startswith("#") and (
            following.startswith("<!-- index control")
            or (view is not None and view.language in VIEW_LANGUAGES)
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
