"""
The walk of the records of one repository, shared by the check of the targets and by the record
registry.

The walk lists every file of the repository below its exclusions, keeps the Markdown notes and the
YAML or JSON documents, and reads each of them once for its identifier and its units. A file of a
nested repository, such as a submodule, belongs to that repository, so the walk reads none of them.
The manifest ``repository.yml``, and every other reserved file such as the record registry, is no
record.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from anagraphe.core.files import walk
from anagraphe.core.issues import Issue
from anagraphe.core.schemas import SchemaReader
from anagraphe.targets.configuration import TargetConfig
from anagraphe.targets.declarations import Declarations
from anagraphe.targets.manifest import MANIFEST_FILE
from anagraphe.targets.records import Record, is_record, read_record
from anagraphe.targets.resource import matches

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
        Repository-relative paths that are never records, besides the manifest.
    """

    root: Path
    config: TargetConfig
    reserved: frozenset[str] = frozenset()
    declarations: Declarations | None = field(init=False)
    _nested: dict[PurePosixPath, bool] = field(default_factory=dict, init=False)
    _records: dict[str, Record] = field(default_factory=dict, init=False)
    _table: dict[str, list[Record]] | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        records = self.config.records
        self.declarations = (
            Declarations(SchemaReader(self.root, records.registry)) if records is not None else None
        )

    def covers(self, rel: str) -> bool:
        """Whether a file is a record of the repository: a note or a document, neither reserved
        nor in a nested repository."""
        return (
            is_record(rel)
            and rel != MANIFEST_FILE
            and rel not in self.reserved
            and not self._in_nested_repository(rel)
        )

    def record(self, rel: str) -> Record:
        """Return a record of the repository, read once."""
        if rel not in self._records:
            binding = self.config.records.binding if self.config.records is not None else "_schema"
            self._records[rel] = read_record(self.root, rel, binding, self.declarations)
        return self._records[rel]

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
