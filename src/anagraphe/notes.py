"""
Reading of the files that an index lists: their entry fields, their title and their body links.

A Markdown note carries its fields in its frontmatter, and a YAML specification in its top-level
``metadata`` block, as the decision on generated index entries fixes. Both are read into one
record, :class:`Note`, so the ordering, the rendering and the checks treat them alike. A
:class:`NoteReader` reads each file once and caches the record, since a target named by a citation
is often read again as a member of its own folder.
"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path, PurePath
from typing import Any, Mapping

import yaml

from anagraphe.fields import Citation, FieldRules
from anagraphe.slots import (
    ContextRelation,
    FileSpec,
    GroupSpec,
    parse_context_relations,
    parse_files,
    parse_groups,
)

#: A Markdown link, capturing its target.
MD_LINK = re.compile(r'\[[^\]\n]*\]\(([^)\s]+?)(?:\s+"[^"]*")?\)')
#: A frontmatter link written as one value, capturing its target.
VALUE_LINK = re.compile(r"^\[[^\]\n]*\]\(([^)\s]+)\)$")
#: A bracketed span not opening a link, which may hold the tail tags of citations.
BRACKETS = re.compile(r"(?<![!\[])\[([^\[\]\n]+)\](?![(\[])")
#: A citation key in the pattern ``authorYYYY``, as a tail tag writes it.
TAIL_KEY = re.compile(r"^[A-Za-z][\w-]*\d{4}[a-z]?$")
#: An H1 heading.
HEADING = re.compile(r"^# (.+?)\s*$", re.MULTILINE)
#: The suffixes of a YAML specification.
YAML_SUFFIXES = (".yml", ".yaml")


@dataclass(frozen=True)
class Note:
    """The fields of one file that an index entry displays or that a check reads."""

    #: Vault-relative path, in POSIX form.
    rel: str
    role: str | None = None
    status: str | None = None
    #: First alias, which is the title of the file.
    title: str | None = None
    #: H1 heading of a Markdown note, None for a YAML specification.
    heading: str | None = None
    #: Vault-relative path named by the ``index`` key.
    index: str | None = None
    group: str | None = None
    #: The valid citations of the file; a malformed entry is reported by the frontmatter checker.
    cites: tuple[Citation, ...] = ()
    purpose: str | None = None
    contribution: tuple[str, ...] = ()
    blocked_by: tuple[str, ...] = ()
    #: The type declared by an index in ``index_type``.
    index_type: str | None = None
    #: Vault-relative paths named by the ``goal`` key of an index.
    goal: tuple[str, ...] = ()
    #: Paths relative to the folder, listed by the ``sequence`` key of an index in reading order.
    sequence: tuple[str, ...] = ()
    #: The ``date`` key in ISO form, read by a block sorted by date.
    date: str | None = None
    #: The groups declared by an index, rendered in its region ``<!-- index groups -->``.
    groups: tuple[GroupSpec, ...] = ()
    #: The relations declared by an index between two of its members.
    context_relations: tuple[ContextRelation, ...] = ()
    #: The files that an index lists without reading them, each with its declared entry.
    files: tuple[FileSpec, ...] = ()
    #: The problems of the keys ``groups``, ``context_relations`` and ``files``.
    slot_problems: tuple[str, ...] = ()
    #: The whole frontmatter, read by a group filtering its members or displaying a key.
    data: Mapping[str, Any] = field(default_factory=dict, compare=False)
    #: Vault-relative paths of the files linked from the body.
    links: frozenset[str] = field(default_factory=frozenset)
    #: HTTP and HTTPS targets linked from the body.
    external_links: frozenset[str] = field(default_factory=frozenset)
    #: Citation keys written as tail tags in the body, such as ``[smith2020]``.
    tail_tags: frozenset[str] = field(default_factory=frozenset)
    #: Whether the file declares any metadata at all.
    has_metadata: bool = True


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Return the parsed frontmatter of a note and its body; an empty mapping when absent.

    Examples
    --------
    >>> split_frontmatter("---\\nrole: spec\\n---\\n# Title\\n")
    ({'role': 'spec'}, '# Title\\n')
    >>> split_frontmatter("# No frontmatter\\n")
    ({}, '# No frontmatter\\n')
    """
    if not text.startswith("---\n"):
        return ({}, text)
    end = text.find("\n---", 4)
    if end == -1:
        return ({}, text)
    try:
        parsed = yaml.safe_load(text[4:end])
    except yaml.YAMLError:
        parsed = None
    body = text[end + 4 :].lstrip("\n") if text[end + 4 : end + 5] == "\n" else text[end + 4 :]
    return (parsed if isinstance(parsed, dict) else {}, body)


def value_link(value: Any) -> str | None:
    """Return the target of a frontmatter value written as one link, or None."""
    match = VALUE_LINK.match(str(value)) if isinstance(value, str) else None
    return urllib.parse.unquote(match.group(1)) if match else None


def body_links(rel: str, body: str) -> frozenset[str]:
    """Return repository-relative paths linked from a body through file-relative links.

    Examples
    --------
    >>> sorted(body_links("notes/a.md", "See [B](b.md), [C](../c.md#^x) and [web](https://x.org)."))
    ['c.md', 'notes/b.md']
    """
    base = Path(rel).parent
    found = set()
    for target in MD_LINK.findall(body):
        if target.startswith("#") or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
            continue
        path = urllib.parse.unquote(target.split("#", 1)[0])
        if path:
            found.add(normalize(base / path))
    return frozenset(found)


def body_external_links(body: str) -> frozenset[str]:
    """Return the HTTP and HTTPS targets linked from a Markdown body.

    Examples
    --------
    >>> sorted(body_external_links("See [web](https://x.org/a) and [local](a.md)."))
    ['https://x.org/a']
    """
    return frozenset(
        target
        for target in MD_LINK.findall(body)
        if urllib.parse.urlsplit(target).scheme.lower() in {"http", "https"}
    )


def tail_tags(body: str) -> frozenset[str]:
    """Return the citation keys written as tail tags in a body, several keys per tag admitted.

    Examples
    --------
    >>> sorted(tail_tags("The gain decays [smith2020; doe2021a]. See [the lemma](l.md) and [ ] x."))
    ['doe2021a', 'smith2020']
    """
    return frozenset(
        key
        for span in BRACKETS.findall(body)
        for key in re.split(r"[;,]\s*", span.strip())
        if TAIL_KEY.match(key)
    )


def iso_date(value: Any) -> str | None:
    """Return a date value in ISO form, as YAML parses it or as written, and None when absent.

    Examples
    --------
    >>> import datetime
    >>> iso_date(datetime.date(2026, 8, 4)), iso_date("2026-08"), iso_date(None)
    ('2026-08-04', '2026-08', None)
    """
    if value is None or value == "":
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def normalize(path: PurePath) -> str:
    """Return a repository-relative path with dot segments resolved, in POSIX form."""
    parts: list[str] = []
    for part in path.as_posix().split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def as_tuple(value: Any) -> tuple[str, ...]:
    """Return a list value as a tuple of strings, and an absent value as an empty tuple."""
    if value is None:
        return ()
    if isinstance(value, list):
        return tuple(str(item) for item in value if item is not None)
    return (str(value),)


class NoteReader:
    """Read repository files into :class:`Note` records, each file once."""

    def __init__(self, root: Path, rules: FieldRules) -> None:
        self.root = root
        self.rules = rules
        self._cache: dict[str, Note | None] = {}

    def read(self, rel: str) -> Note | None:
        """Return a repository-relative record, or none when the file does not exist."""
        if rel not in self._cache:
            path = self.root / rel
            self._cache[rel] = self._load(rel, path) if path.is_file() else None
        return self._cache[rel]

    def _load(self, rel: str, path: Path) -> Note:
        text = path.read_text(encoding="utf-8", errors="replace")
        if rel.endswith(YAML_SUFFIXES):
            try:
                parsed = yaml.safe_load(text)
            except yaml.YAMLError:
                parsed = None
            metadata = parsed.get("metadata") if isinstance(parsed, dict) else None
            metadata = metadata if isinstance(metadata, dict) else {}
            # A group may read any key of the specification, whereas only its metadata lists it.
            content = (
                {key: value for key, value in parsed.items() if key != "metadata"}
                if isinstance(parsed, dict)
                else {}
            )
            return self._record(rel, metadata, None, "", content)
        frontmatter, body = split_frontmatter(text)
        heading = HEADING.search(body)
        return self._record(rel, frontmatter, heading.group(1) if heading else None, body)

    def _record(
        self,
        rel: str,
        data: dict[str, Any],
        heading: str | None,
        body: str,
        content: dict[str, Any] | None = None,
    ) -> Note:
        aliases = as_tuple(data.get("aliases"))
        cites, _problems = self.rules.parse_cites(data["cites"]) if "cites" in data else ((), [])
        groups, group_problems = parse_groups(data.get("groups"))
        relations, relation_problems = parse_context_relations(data.get("context_relations"))
        files, file_problems = parse_files(data.get("files"))
        purpose = data.get("purpose")
        return Note(
            rel=rel,
            role=str(data["role"]) if data.get("role") is not None else None,
            status=str(data["status"]) if data.get("status") is not None else None,
            title=aliases[0] if aliases else None,
            heading=heading,
            index=value_link(data.get("index")),
            group=str(data["group"]) if data.get("group") is not None else None,
            cites=cites,
            purpose=purpose if isinstance(purpose, str) else None,
            contribution=as_tuple(data.get("contribution")),
            blocked_by=as_tuple(data.get("blocked_by")),
            index_type=(str(data["index_type"]) if data.get("index_type") is not None else None),
            goal=tuple(path for path in map(value_link, as_tuple(data.get("goal"))) if path),
            sequence=as_tuple(data.get("sequence")),
            date=iso_date(data.get("date")),
            groups=groups,
            context_relations=relations,
            files=files,
            slot_problems=tuple(group_problems + relation_problems + file_problems),
            data={**(content or {}), **data},
            links=body_links(rel, body),
            external_links=body_external_links(body),
            tail_tags=tail_tags(body),
            has_metadata=bool(data),
        )

    def is_specification(self, rel: str) -> bool:
        """Whether a YAML file carries a ``metadata`` block, and is thereby listed."""
        note = self.read(rel)
        return note is not None and rel.endswith(YAML_SUFFIXES) and note.has_metadata
