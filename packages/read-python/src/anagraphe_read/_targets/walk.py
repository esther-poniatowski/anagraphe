"""
The walk of the records of one repository, shared by the check of the targets and by the record
registry.

The walk lists every file of the repository below its exclusions, keeps the Markdown notes, the
YAML or JSON documents and the TOML documents whose metadata source is ``toml``, and reads each of
them once, through the metadata source of the configuration, for its identifier and its units. A file of a
nested repository, such as a submodule, belongs to that repository, so the walk reads none of them.
The retired manifest ``repository.yml``, and every other reserved file such as the record registry,
is no record.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from typing import Any

from anagraphe_read._core.files import walk
from anagraphe_read._core.issues import Issue, pointer
from anagraphe_read._core.metadata import MetadataReader
from anagraphe_read._core.schemas import SchemaReader, values_at
from anagraphe_read._targets.configuration import TargetConfig
from anagraphe_read._targets.declarations import Declarations, UnitList, UnitReference
from anagraphe_read._targets.identity import MANIFEST_FILE
from anagraphe_read._targets.kinds import (
    DUPLICATE_IDENTIFIER,
    INVALID_IDENTIFIER,
    MISSING_IDENTIFIER,
    UNKNOWN_UNIT_REFERENCE,
)
from anagraphe_read._targets.records import Record, is_record, read_record
from anagraphe_read._targets.resource import matches

#: The entry marking the root of a Git repository, a directory or a file in a submodule.
GIT_ENTRY = ".git"


@dataclass
class RecordWalk:
    """The records of one repository, each read once, and the table of their identifiers.

    Parameters
    ----------
    root : Path
        The root of the repository, resolved.
    config : TargetConfig
        The section ``targets``, which supplies the exclusions and the schema registry.
    reserved : frozenset[str]
        Repository-relative paths that are never records, besides the retired manifest.
    """

    root: Path
    config: TargetConfig
    reserved: frozenset[str] = frozenset()
    declarations: Declarations | None = field(init=False)
    metadata: MetadataReader = field(init=False)
    _nested: dict[PurePosixPath, bool] = field(default_factory=dict, init=False)
    _records: dict[str, Record] = field(default_factory=dict, init=False)
    _table: dict[str, list[Record]] | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        records = self.config.records
        self.declarations = (
            Declarations(SchemaReader(self.root, records.registry)) if records is not None else None
        )
        self.metadata = self.config.metadata or MetadataReader(self.root)

    def covers(self, rel: str) -> bool:
        """Whether a file is a record of the repository: a note or a document, neither reserved
        nor in a nested repository."""
        return (
            is_record(rel, self.metadata.source_of(rel))
            and rel != MANIFEST_FILE
            and rel not in self.reserved
            and not self._in_nested_repository(rel)
        )

    def record(self, rel: str) -> Record:
        """Return a record of the repository, read once."""
        if rel not in self._records:
            binding = self.config.records.binding if self.config.records is not None else "_schema"
            self._records[rel] = read_record(
                self.root, rel, binding, self.declarations, self.metadata.source_of(rel)
            )
        return self._records[rel]

    def identifier(self, rel: str) -> Any:
        """Return the identifier of a file that may be a record, as the check reads it: the field
        declared by ``x-identifier``, else the key ``id`` of its metadata source; None for a file
        that is no record, or that cannot be read."""
        if not is_record(rel, self.metadata.source_of(rel)):
            return None
        record = self.record(rel)
        return record.identifier if record.problem is None else None

    def records(self) -> list[Record]:
        """Return every record of the walk, in the sorted order of the walk."""
        return [
            self.record(rel)
            for rel in walk(self.root, self.root, self.config.exemptions)
            if self.covers(rel)
        ]

    @property
    def table(self) -> dict[str, list[Record]]:
        """Return the records holding each valid identifier, in the order of the walk.

        An unreadable record, and a record whose identifier is absent or lies outside the pattern
        of ``record-id``, enters no entry.
        """
        if self._table is None:
            table: dict[str, list[Record]] = {}
            for record in self.records():
                if record.problem is None and matches("record-id", record.identifier):
                    table.setdefault(record.identifier, []).append(record)
            self._table = table
        return self._table

    def schema_issues(self) -> list[Issue]:
        """Return the defects of the schemas of the schema registry, every contract read once.

        A record whose schema cannot be read shows no declared identifier, so a walk with such a
        defect may leave out records.
        """
        declarations = self.declarations
        if declarations is None:
            return []
        for contract in declarations.reader.contracts():
            declarations.of(contract)
        return [
            Issue(problem.rel, None, problem.kind, problem.detail, locus=problem.pointer)
            for problem in (*declarations.reader.problems, *declarations.problems)
        ]

    def _in_nested_repository(self, rel: str) -> bool:
        """Whether a file lies below the root of a nested repository, such as a submodule."""
        for folder in PurePosixPath(rel).parents:
            if folder == PurePosixPath("."):
                return False
            if folder not in self._nested:
                self._nested[folder] = (self.root / folder / GIT_ENTRY).exists()
            if self._nested[folder]:
                return True
        return False


def identifier_issues(record: Record, table: dict[str, list[Record]]) -> list[Issue]:
    """Return the issues of the identifier of a readable record against the table of the walk.

    A declared field left empty is ``missing-identifier``; an identifier outside ``record-id``, and
    each later key path of the metadata source holding another identifier, is
    ``invalid-identifier``; an identifier that another record holds is ``duplicate-identifier``.
    """
    at = record.identifier_pointer
    issues = [
        Issue(
            record.rel,
            None,
            INVALID_IDENTIFIER,
            f"the metadata source holds the identifier {value!r} at {place}, and the record "
            f"holds {record.identifier!r} at {at}, its first key path holding id",
            locus=place,
        )
        for place, value in record.conflicts
    ]
    if record.identifier is None:
        if record.declared:
            issues.append(
                Issue(
                    record.rel,
                    None,
                    MISSING_IDENTIFIER,
                    f"the contract {record.contract} declares its identifier at {at}, which the "
                    "record leaves empty",
                    locus=at,
                )
            )
        return issues
    if not matches("record-id", record.identifier):
        issues.insert(
            0,
            Issue(
                record.rel,
                None,
                INVALID_IDENTIFIER,
                f"the identifier {record.identifier!r} lies outside the pattern of record-id",
                locus=at,
            ),
        )
        return issues
    others = [other.rel for other in table.get(record.identifier, []) if other.rel != record.rel]
    if others:
        issues.insert(
            0,
            Issue(
                record.rel,
                None,
                DUPLICATE_IDENTIFIER,
                f"the identifier {record.identifier} is also held by {', '.join(others)}",
                locus=at,
            ),
        )
    return issues


def unit_issues(record: Record) -> list[Issue]:
    """Return the issue of each declared item identifier of a record outside ``unit-id``."""
    return [
        Issue(
            record.rel,
            None,
            INVALID_IDENTIFIER,
            f"the unit identifier {value!r} lies outside the pattern of unit-id",
            locus=place,
        )
        for place, value in record.invalid_units
    ]


def unit_reference_issues(record: Record) -> list[Issue]:
    """Return the issue of each value of a field declaring ``x-units`` that names no unit of the
    arrays of a declaration of the field.

    A value is a string, or an array whose strings are each a value; any other value names no unit,
    and the validation of the record against its schema judges it.
    """
    issues: list[Issue] = []
    for reference in record.schema.references if record.schema is not None else ():
        admitted = _units_of(record, reference)
        for keys, value in values_at(record.data, reference.path):
            named = (
                [(keys, value)]
                if isinstance(value, str)
                else (
                    [((*keys, number), item) for number, item in enumerate(value)]
                    if isinstance(value, list)
                    else []
                )
            )
            issues.extend(
                Issue(
                    record.rel,
                    None,
                    UNKNOWN_UNIT_REFERENCE,
                    f"{item!r} names no unit of "
                    f"{', '.join(units.text for units in reference.lists)}",
                    locus=pointer(*place),
                )
                for place, item in named
                if isinstance(item, str) and item not in admitted
            )
    return issues


def _units_of(record: Record, reference: UnitReference) -> frozenset[str]:
    """Return the identifiers of the items of the arrays that a declaration of ``x-units`` names."""
    return frozenset(unit for units in reference.lists for unit in _identifiers(record.data, units))


def _identifiers(data: Any, units: UnitList) -> list[str]:
    """Return the identifier of each item of the array at the field path of ``units``."""
    node = data
    for part in units.path:
        if isinstance(part, int):
            node = node[part] if isinstance(node, list) and part < len(node) else None
        else:
            node = node.get(part) if isinstance(node, dict) else None
    identifiers: list[str] = []
    for item in node if isinstance(node, list) else ():
        value = item
        for key in units.identifier:
            value = value.get(key) if isinstance(value, dict) else None
        if isinstance(value, str):
            identifiers.append(value)
    return identifiers
