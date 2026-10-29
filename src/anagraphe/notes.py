"""
Reading of the files that an index lists: their entry fields, their title and their slots.

A Markdown note carries its fields in its frontmatter, and a YAML specification in its top-level
``metadata`` block, as the decision on generated index entries fixes. Both are read into one
record, :class:`Note`, so the ordering, the rendering and the checks treat them alike. A note
holds only its intrinsic properties (ADR 0002): the order, the nesting and the grouping of the
members are read from the index of their collection. A :class:`NoteReader` reads each file once
and caches the record, since a child index is read both as a member and as an index.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

from anagraphe.paths import value_link
from anagraphe.slots import (
    ContextRelation,
    ExternalSpec,
    FileSpec,
    GroupSpec,
    parse_context_relations,
    parse_external,
    parse_files,
    parse_groups,
)

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
    purpose: str | None = None
    contribution: tuple[str, ...] = ()
    blocked_by: tuple[str, ...] = ()
    #: The type declared by an index in ``index_type``.
    index_type: str | None = None
    #: The ``date`` key in ISO form, read by a group sorted by date.
    date: str | None = None
    #: The groups declared by an index, rendered in its region ``<!-- index groups -->``.
    groups: tuple[GroupSpec, ...] = ()
    #: The relations declared by an index between two of its members.
    context_relations: tuple[ContextRelation, ...] = ()
    #: The files that an index lists without reading them, each with its declared entry.
    files: tuple[FileSpec, ...] = ()
    #: The files outside its folder on which an index depends.
    external: tuple[ExternalSpec, ...] = ()
    #: The problems of the keys ``groups``, ``context_relations``, ``files`` and ``external``.
    slot_problems: tuple[str, ...] = ()
    #: The whole frontmatter, read by a group filtering its members or displaying a key.
    data: Mapping[str, Any] = field(default_factory=dict, compare=False)
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


def as_tuple(value: Any) -> tuple[str, ...]:
    """Return a list value as a tuple of strings, and an absent value as an empty tuple."""
    if value is None:
        return ()
    if isinstance(value, list):
        return tuple(str(item) for item in value if item is not None)
    return (str(value),)


class NoteReader:
    """Read repository files into :class:`Note` records, each file once."""

    def __init__(self, root: Path) -> None:
        self.root = root
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
            return self._record(rel, metadata, None, content)
        frontmatter, body = split_frontmatter(text)
        heading = HEADING.search(body)
        return self._record(rel, frontmatter, heading.group(1) if heading else None)

    @staticmethod
    def _record(
        rel: str,
        data: dict[str, Any],
        heading: str | None,
        content: dict[str, Any] | None = None,
    ) -> Note:
        aliases = as_tuple(data.get("aliases"))
        groups, group_problems = parse_groups(data.get("groups"))
        relations, relation_problems = parse_context_relations(data.get("context_relations"))
        files, file_problems = parse_files(data.get("files"))
        external, external_problems = parse_external(data.get("external"))
        purpose = data.get("purpose")
        return Note(
            rel=rel,
            role=str(data["role"]) if data.get("role") is not None else None,
            status=str(data["status"]) if data.get("status") is not None else None,
            title=aliases[0] if aliases else None,
            heading=heading,
            index=value_link(data.get("index")),
            purpose=purpose if isinstance(purpose, str) else None,
            contribution=as_tuple(data.get("contribution")),
            blocked_by=as_tuple(data.get("blocked_by")),
            index_type=(str(data["index_type"]) if data.get("index_type") is not None else None),
            date=iso_date(data.get("date")),
            groups=groups,
            context_relations=relations,
            files=files,
            external=external,
            slot_problems=tuple(
                group_problems + relation_problems + file_problems + external_problems
            ),
            data={**(content or {}), **data},
            has_metadata=bool(data),
        )

    def is_specification(self, rel: str) -> bool:
        """Whether a YAML file carries a ``metadata`` block, and is thereby listed."""
        note = self.read(rel)
        return note is not None and rel.endswith(YAML_SUFFIXES) and note.has_metadata
