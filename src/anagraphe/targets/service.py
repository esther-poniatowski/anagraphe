"""
The check of the logical targets of a repository, within that repository.

The check reads the manifest ``repository.yml`` at the root, then the identifier of every record of
the repository, so that a target resolves whichever files the command selects. A file of a nested
repository, such as a submodule, belongs to that repository, so the check reads none of them. For
each selected record, the check reports its identifier, then each value of its target fields:

1. a value that is not a logical target is reported as ``invalid-target``;
2. a target into another repository is reported as ``unverified-target``, at the level ``note``,
   since only its form is checked until the resolver exists;
3. a target of the same repository names a record of the repository, then a unit of that record,
   and its record satisfies each ``x-target-contract`` of the field.

A target naming a duplicated identifier receives no finding of its own, since
``duplicate-identifier`` reports its cause. The check writes no file.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath

from anagraphe.core.files import select, walk
from anagraphe.core.issues import Issue, Report, distinct, pointer
from anagraphe.core.schemas import SchemaReader, values_at
from anagraphe.targets.configuration import TargetConfig
from anagraphe.targets.declarations import Declarations, TargetField
from anagraphe.targets.kinds import (
    AMBIGUOUS_UNIT,
    DUPLICATE_IDENTIFIER,
    INVALID_IDENTIFIER,
    INVALID_TARGET,
    KINDS,
    LEGACY_REPOSITORY_MANIFEST,
    MISSING_IDENTIFIER,
    TARGET_CONTRACT_MISMATCH,
    UNBOUND_TARGET,
    UNKNOWN_RECORD,
    UNKNOWN_UNIT,
    UNREADABLE_RECORD,
    UNVERIFIED_TARGET,
)
from anagraphe.targets.manifest import MANIFEST_FILE, ManifestReading, read_manifest
from anagraphe.targets.model import InvalidTarget, Target, admits
from anagraphe.targets.records import Record, is_record, read_record
from anagraphe.targets.resource import matches

__all__ = ["KINDS", "TargetChecker"]

#: The entry marking the root of a Git repository, a directory or a file in a submodule.
GIT_ENTRY = ".git"


@dataclass
class TargetChecker:
    """Check the logical targets of one repository against its records."""

    root: Path
    config: TargetConfig
    manifest: ManifestReading = field(init=False)
    declarations: Declarations | None = field(init=False)
    _nested: dict[PurePosixPath, bool] = field(default_factory=dict, init=False)
    _records: dict[str, Record] = field(default_factory=dict, init=False)
    _table: dict[str, list[Record]] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self.root = self.root.resolve()
        self.manifest = read_manifest(self.root)
        records = self.config.records
        self.declarations = (
            Declarations(SchemaReader(self.root, records.registry)) if records is not None else None
        )

    @property
    def repository(self) -> str | None:
        """Return the identifier of the checked repository, None when it declares none."""
        return self.manifest.manifest.id if self.manifest.manifest is not None else None

    def covers(self, rel: str) -> bool:
        """Whether a file is a record of the checked repository; the manifest is none."""
        return is_record(rel) and rel != MANIFEST_FILE and not self._in_nested_repository(rel)

    def check(self, paths: tuple[Path, ...] = (), strict: bool = True) -> Report:
        """Check the records below the given targets, the whole repository without a target."""
        selected = select(self.root, paths, self.config.exemptions, self.covers, strict)
        for rel in walk(self.root, self.root, self.config.exemptions):
            if self.covers(rel):
                record = self._record(rel)
                if record.problem is None and matches("record-id", record.identifier):
                    self._table.setdefault(record.identifier, []).append(record)
        issues = self._manifest_issues()
        for rel in selected:
            issues.extend(self.check_record(self._record(rel)))
        issues.extend(self._schema_issues())
        # The text report prints no locus, so the detail of a located issue opens on its pointer.
        located = [
            replace(issue, detail=f"{issue.locus}: {issue.detail}") if issue.locus else issue
            for issue in distinct(issues)
        ]
        return Report(len(selected), tuple(located))

    def check_record(self, record: Record) -> list[Issue]:
        """Return the issues of one record: its identifier, then its targets."""
        if record.problem is not None:
            return [Issue(record.rel, None, UNREADABLE_RECORD, record.problem)]
        issues = self._identifier_issues(record)
        for target_field in record.schema.targets if record.schema is not None else ():
            for keys, value in values_at(record.data, target_field.path):
                issues.extend(self._target_issues(record, target_field, pointer(*keys), value))
        return issues

    def _identifier_issues(self, record: Record) -> list[Issue]:
        """Return the issues of the identifier of a record."""
        at = record.identifier_pointer
        if record.identifier is None:
            if not record.declared:
                return []
            return [
                Issue(
                    record.rel,
                    None,
                    MISSING_IDENTIFIER,
                    f"the contract {record.contract} declares its identifier at {at}, which the "
                    "record leaves empty",
                    locus=at,
                )
            ]
        if not matches("record-id", record.identifier):
            return [
                Issue(
                    record.rel,
                    None,
                    INVALID_IDENTIFIER,
                    f"the identifier {record.identifier!r} lies outside the pattern of record-id",
                    locus=at,
                )
            ]
        holders = self._table.get(record.identifier, [])
        if len(holders) > 1:
            others = ", ".join(other.rel for other in holders if other.rel != record.rel)
            return [
                Issue(
                    record.rel,
                    None,
                    DUPLICATE_IDENTIFIER,
                    f"the identifier {record.identifier} is also held by {others}",
                    locus=at,
                )
            ]
        return []

    def _target_issues(
        self, record: Record, target_field: TargetField, at: str, value: object
    ) -> list[Issue]:
        """Return the issues of one value of a target field."""
        if target_field.conditional and not isinstance(value, dict):
            return []
        try:
            target = Target.parse(value)
        except InvalidTarget as error:
            return [Issue(record.rel, None, INVALID_TARGET, str(error), locus=at)]
        written = str(target)
        if target.repository is not None and target.repository != self.repository:
            return [
                Issue(
                    record.rel,
                    None,
                    UNVERIFIED_TARGET,
                    f"{written} names the repository {target.repository}, whose records this "
                    "check does not read; only the form of the target is checked",
                    blocking=False,
                    locus=at,
                    note=True,
                )
            ]
        if target.id is None:
            return []
        holders = self._table.get(target.id, [])
        if not holders:
            return [
                Issue(
                    record.rel,
                    None,
                    UNKNOWN_RECORD,
                    f"{written}: no record of the repository holds the identifier {target.id}",
                    locus=at,
                )
            ]
        if len(holders) > 1:
            return []
        return self._resolved_issues(record, target_field, at, target, holders[0])

    def _resolved_issues(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self, record: Record, target_field: TargetField, at: str, target: Target, held: Record
    ) -> list[Issue]:
        """Return the issues of a target whose record is found: its unit and its contract."""
        issues: list[Issue] = []
        written = str(target)
        count = held.units.count(target.unit) if target.unit is not None else 1
        if count != 1:
            kind, detail = (
                (UNKNOWN_UNIT, "declares no unit")
                if not count
                else (AMBIGUOUS_UNIT, "holds two units")
            )
            issues.append(
                Issue(
                    record.rel,
                    None,
                    kind,
                    f"{written}: the record {held.rel} {detail} of the identifier {target.unit}",
                    locus=at,
                )
            )
        if target_field.contracts:
            if held.contract is None:
                issues.append(
                    Issue(
                        record.rel,
                        None,
                        UNBOUND_TARGET,
                        f"{written}: the field admits the contracts "
                        f"{_listed(target_field.contracts)}, and the record {held.rel} declares "
                        "no contract",
                        locus=at,
                    )
                )
            else:
                implemented = held.schema.implements if held.schema is not None else ()
                contracts = (held.contract, *implemented)
                failed = [
                    entries for entries in target_field.contracts if not admits(entries, contracts)
                ]
                if failed:
                    issues.append(
                        Issue(
                            record.rel,
                            None,
                            TARGET_CONTRACT_MISMATCH,
                            f"{written}: the record {held.rel} follows {', '.join(contracts)}, "
                            f"which no entry of {_listed(tuple(failed))} admits",
                            locus=at,
                        )
                    )
        return issues

    def _manifest_issues(self) -> list[Issue]:
        """Return the defects of the manifest of the repository."""
        return [
            Issue(
                MANIFEST_FILE,
                None,
                problem.kind,
                problem.detail,
                blocking=problem.kind != LEGACY_REPOSITORY_MANIFEST,
                locus=problem.pointer,
            )
            for problem in self.manifest.problems
        ]

    def _schema_issues(self) -> list[Issue]:
        """Return the defects of the schemas of the registry, every contract read once."""
        declarations = self.declarations
        if declarations is None:
            return []
        for contract in declarations.reader.contracts():
            declarations.of(contract)
        return [
            Issue(problem.rel, None, problem.kind, problem.detail, locus=problem.pointer)
            for problem in (*declarations.reader.problems, *declarations.problems)
        ]

    def _record(self, rel: str) -> Record:
        """Return a record of the repository, read once."""
        if rel not in self._records:
            binding = self.config.records.binding if self.config.records is not None else "_schema"
            self._records[rel] = read_record(self.root, rel, binding, self.declarations)
        return self._records[rel]

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


def _listed(declarations: tuple[tuple[str, ...], ...]) -> str:
    """Return the entries of declarations of ``x-target-contract``, each declaration bracketed."""
    return " and ".join(f"[{', '.join(entries)}]" for entries in declarations)
