"""
The check of the logical targets of a repository, within that repository.

The check reads the manifest ``repository.yml`` at the root, then the identifier of every record of
the repository, so that a target resolves whichever files the command selects. A file of a nested
repository, such as a submodule, belongs to that repository, so the check reads none of them. For
each selected record, the check reports its identifier, then each value of its target fields:

1. a value that is not a logical target is reported as ``invalid-target``;
2. a target into another repository is resolved and read by the record resolver of
   :mod:`anagraphe.resolution`, at the state that the resolution context of the root selects, and
   each finding of the resolver is reported. Until a provider reads the states of other
   repositories, each such target receives the warning ``unreadable-target-state``. A target naming
   a former identifier of the root is reported as ``renamed-repository``, then checked as a target
   of the same repository;
3. a target of the same repository names a record of the repository, then a unit of that record,
   and its record satisfies each ``x-target-contract`` of the field.

When the section ``records`` is declared, the check also reads the retired identifiers of the
record registry. A target naming an identifier retired with a successor is reported as
``renamed-target``, a warning, and the check follows the successors to the record holding the last
one, against which it checks the unit and the contract. A target naming an identifier retired
without a successor, or whose successors reach no record, is reported as ``retired-target``. A
registry that is absent or invalid supplies no retired identifier; the check of the registry
reports it.

A target naming a duplicated identifier receives no finding of its own, since
``duplicate-identifier`` reports its cause. Whatever the selected files, the check also compares
the versions declared by the read sides of the key ``read_sides`` with those of Anagraphe, as
:mod:`anagraphe.targets.read_sides` states. The check writes no file.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from functools import cached_property
from pathlib import Path
from typing import Mapping

from anagraphe.core.files import select
from anagraphe.core.issues import Issue, Report, distinct, pointer
from anagraphe.core.schemas import values_at
from anagraphe.resolution.configuration import ResolutionConfig
from anagraphe.resolution.context import build_context
from anagraphe.resolution.provider import EmptyProvider, StateProvider
from anagraphe.resolution.resolver import Outcome, RecordResolver
from anagraphe.targets.configuration import TargetConfig
from anagraphe.targets.declarations import Declarations, TargetField
from anagraphe.targets.kinds import (
    DUPLICATE_IDENTIFIER,
    INVALID_IDENTIFIER,
    INVALID_TARGET,
    KINDS,
    LEGACY_REPOSITORY_MANIFEST,
    MISSING_IDENTIFIER,
    RENAMED_TARGET,
    RETIRED_TARGET,
    UNKNOWN_RECORD,
    UNREADABLE_RECORD,
)
from anagraphe.targets.manifest import MANIFEST_FILE, ManifestReading, read_manifest
from anagraphe.targets.model import InvalidTarget, Target
from anagraphe.targets.read_sides import check_read_sides
from anagraphe.targets.records import Record
from anagraphe.targets.registry.configuration import RecordsConfig
from anagraphe.targets.registry.contract import Retirement, follow, read_registry
from anagraphe.targets.resource import matches
from anagraphe.targets.verification import Finding, held_findings
from anagraphe.targets.walk import RecordWalk

__all__ = ["KINDS", "TargetChecker"]

#: The catalogue entry of each kind, which fixes the level of a finding of the resolver.
_CATALOGUE = {kind.kind: kind for kind in KINDS}


@dataclass
class TargetChecker:
    """Check the logical targets of one repository against its records.

    Parameters
    ----------
    root : Path
        The root of the repository.
    config : TargetConfig
        The section ``targets``.
    registry : RecordsConfig or None
        The section ``records``, whose registry supplies the retired identifiers; None when the
        repository declares no registry.
    resolution : ResolutionConfig or None
        The section ``resolution``, which declares the repositories named besides the submodules;
        None when the repository declares none.
    provider : StateProvider
        The reader of the states of other repositories; by default, none is read.
    """

    root: Path
    config: TargetConfig
    registry: RecordsConfig | None = None
    resolution: ResolutionConfig | None = None
    provider: StateProvider = field(default_factory=EmptyProvider)
    manifest: ManifestReading = field(init=False)
    walk: RecordWalk = field(init=False)
    #: The retired identifiers of the registry, empty without a valid registry.
    retired: Mapping[str, Retirement] = field(init=False)

    def __post_init__(self) -> None:
        self.root = self.root.resolve()
        self.manifest = read_manifest(self.root)
        reserved = frozenset({self.registry.rel}) if self.registry is not None else frozenset()
        self.walk = RecordWalk(self.root, self.config, reserved)
        reading = (
            read_registry(self.registry.path, self.registry.rel)
            if self.registry is not None
            else None
        )
        self.retired = (
            reading.registry.retired if reading is not None and reading.registry is not None else {}
        )

    @property
    def declarations(self) -> Declarations | None:
        """Return the declarations of the contracts of the schema registry, None without one."""
        return self.walk.declarations

    @property
    def repository(self) -> str | None:
        """Return the identifier of the checked repository, None when it declares none."""
        return self.manifest.manifest.id if self.manifest.manifest is not None else None

    @cached_property
    def resolver(self) -> RecordResolver:
        """Return the record resolver of the root, its context built on the first target into
        another repository.

        Raises
        ------
        ConfigurationError
            If two entries of the context select states of one repository.
        """
        context = build_context(self.root, self.manifest.manifest, self.resolution, self.provider)
        binding = self.config.records.binding if self.config.records is not None else "_schema"
        return RecordResolver(context, self.provider, self.declarations, binding)

    def covers(self, rel: str) -> bool:
        """Whether a file is a record of the checked repository; the manifest is none."""
        return self.walk.covers(rel)

    def check(self, paths: tuple[Path, ...] = (), strict: bool = True) -> Report:
        """Check the records below the given targets, the whole repository without a target."""
        selected = select(self.root, paths, self.config.exemptions, self.covers, strict)
        issues = self._manifest_issues()
        issues.extend(check_read_sides(self.config.read_sides))
        for rel in selected:
            issues.extend(self.check_record(self.walk.record(rel)))
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
        holders = self.walk.table.get(record.identifier, [])
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
        issues: list[Issue] = []
        if target.repository is not None and target.repository != self.repository:
            resolution = self.resolver.resolve(target)
            issues.extend(self._finding_issue(record, at, item) for item in resolution.findings)
            if resolution.outcome is Outcome.RECORD:
                read = self.resolver.read(resolution, target_field.contracts)
                issues.extend(self._finding_issue(record, at, item) for item in read.findings)
            if resolution.outcome is not Outcome.LOCAL:
                return issues
            target = resolution.target
        return issues + self._local_issues(record, target_field, at, target)

    def _local_issues(
        self, record: Record, target_field: TargetField, at: str, target: Target
    ) -> list[Issue]:
        """Return the issues of a target of the same repository."""
        if target.id is None:
            return []
        holders = self.walk.table.get(target.id, [])
        if holders:
            if len(holders) > 1:
                return []
            return self._resolved_issues(record, target_field, at, target, holders[0])
        if target.id in self.retired:
            return self._retired_issues(record, target_field, at, target)
        return [
            Issue(
                record.rel,
                None,
                UNKNOWN_RECORD,
                f"{target}: no record of the repository holds the identifier {target.id}",
                locus=at,
            )
        ]

    @staticmethod
    def _finding_issue(record: Record, at: str, finding: Finding) -> Issue:
        """Return the issue of a finding on a target of a record, at the level of its kind."""
        kind = _CATALOGUE[finding.kind]
        return Issue(
            record.rel,
            None,
            finding.kind,
            finding.detail,
            blocking=kind.blocking,
            locus=at,
            note=kind.note,
        )

    def _retired_issues(
        self, record: Record, target_field: TargetField, at: str, target: Target
    ) -> list[Issue]:
        """Return the issues of a target naming a retired identifier: the rename followed to the
        record of its last successor, then the issues of that record; or the retirement."""
        assert target.id is not None
        written = str(target)
        table = self.walk.table
        chain = follow(self.retired, target.id, table.__contains__)
        if chain is None:
            successor = self.retired[target.id].replaced_by
            reason = (
                f"replaced by {successor}, whose successors reach no record"
                if successor is not None
                else "without a successor"
            )
            return [
                Issue(
                    record.rel,
                    None,
                    RETIRED_TARGET,
                    f"{written}: the identifier {target.id} is retired {reason}",
                    locus=at,
                )
            ]
        live = chain[-1]
        holders = table[live]
        followed = replace(target, id=live)
        renamed = Issue(
            record.rel,
            None,
            RENAMED_TARGET,
            f"{written}: the identifier {target.id} is retired and replaced by {live}"
            + (f" through {', '.join(chain[:-1])}" if len(chain) > 1 else "")
            + f"; write {followed}",
            blocking=False,
            locus=at,
        )
        if len(holders) > 1:
            return [renamed]
        return [renamed, *self._resolved_issues(record, target_field, at, followed, holders[0])]

    def _resolved_issues(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self, record: Record, target_field: TargetField, at: str, target: Target, held: Record
    ) -> list[Issue]:
        """Return the issues of a target whose record is found: its unit and its contract."""
        return [
            self._finding_issue(record, at, finding)
            for finding in held_findings(target, target_field.contracts, held)
        ]

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
        return self.walk.schema_issues()
