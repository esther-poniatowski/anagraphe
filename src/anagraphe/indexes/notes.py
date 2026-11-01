"""
Reading of the files that an index lists: their entry fields, their title and their slots.

A file carries its fields where its declared metadata source writes them: by default, a Markdown
note in its frontmatter, and a YAML record at its top level overridden by its block ``metadata``.
Every member is read into one record, :class:`Note`, so the ordering, the rendering and the checks
treat them alike. A file without a metadata source, such as a PDF, is read from its path alone. A note
holds only its intrinsic properties (ADR 0002): the order, the nesting and the grouping of the
members are read from the index of their collection. A :class:`NoteReader` reads each file once
and caches the record, since a child index is read both as a member and as an index.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from anagraphe.core.links import value_link
from anagraphe.core.metadata import MetadataReader, SourceKind, split_frontmatter
from anagraphe.indexes.slots import (
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
    #: Whether a metadata source is declared for the file, so that it can declare its entry fields.
    reads_metadata: bool = True
    #: Why the metadata of the file cannot be parsed, None when it can; its fields are then empty.
    metadata_problem: str | None = None


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
    """Read repository files into :class:`Note` records, each file once, through their sources."""

    def __init__(self, root: Path, metadata: MetadataReader | None = None) -> None:
        self.root = root
        self.metadata = metadata or MetadataReader(root)
        self._cache: dict[str, Note | None] = {}

    def read(self, rel: str) -> Note | None:
        """Return a repository-relative record, or none when the file does not exist."""
        if rel not in self._cache:
            path = self.root / rel
            self._cache[rel] = self._load(rel, path) if path.is_file() else None
        return self._cache[rel]

    def _load(self, rel: str, path: Path) -> Note:
        source = self.metadata.source_of(rel)
        if source.kind is SourceKind.NONE:
            # A file holding no metadata, such as a PDF, is never read.
            return self._record(rel, {}, None, reads_metadata=False)
        text = path.read_text(encoding="utf-8", errors="replace")
        heading = None
        if source.kind is SourceKind.FRONTMATTER:
            found = HEADING.search(split_frontmatter(text)[1])
            heading = found.group(1) if found else None
        data, problem = source.parse(text)
        return self._record(rel, data, heading, problem=problem)

    @staticmethod
    def _record(
        rel: str,
        data: dict[str, Any],
        heading: str | None,
        reads_metadata: bool = True,
        problem: str | None = None,
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
            data=data,
            reads_metadata=reads_metadata,
            metadata_problem=problem,
        )
