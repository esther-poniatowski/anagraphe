"""
The check of the logical targets of a repository, within that repository.

The check derives the identity of the repository, as :mod:`anagraphe_read._targets.identity` states,
then reads the identifier of every record of the repository, so that a target resolves whichever files the command selects. A file of a nested
repository, such as a submodule, belongs to that repository, so the check reads none of them. For
each selected record, the check reports its identifier, then each value of its target fields:

1. a value that is not a logical target is reported as ``invalid-target``;
2. a target into another repository is resolved and read by the record resolver of
   :mod:`anagraphe_read._resolution`, at the state that the resolution context of the root selects, and
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
:mod:`anagraphe_read._targets.read_sides` states. The check writes no file.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Mapping

from anagraphe_read._core.configuration import ConfigurationError
from anagraphe_read._core.files import select
from anagraphe_read._core.issues import Issue, Report, distinct, pointer
from anagraphe_read._core.schemas import values_at
from anagraphe_read._repository import Composition
from anagraphe_read._resolution.resolver import Outcome, RecordResolver
from anagraphe_read._targets.configuration import TargetConfig
from anagraphe_read._targets.declarations import Declarations, TargetField
from anagraphe_read._targets.identity import Identity
from anagraphe_read._targets.kinds import (
    INVALID_TARGET,
    KINDS,
    RENAMED_TARGET,
    RETIRED_TARGET,
    UNKNOWN_RECORD,
    UNREADABLE_RECORD,
)
from anagraphe_read._targets.model import InvalidTarget, Target
from anagraphe_read._targets.read_sides import check_read_sides
from anagraphe_read._targets.records import Record
from anagraphe_read._targets.registry.contract import Retirement, follow, read_registry
from anagraphe_read._targets.verification import Finding, held_findings
from anagraphe_read._targets.walk import RecordWalk, identifier_issues, unit_issues

__all__ = ["KINDS", "TargetChecker"]

#: The catalogue entry of each kind, which fixes the level of a finding of the resolver.
_CATALOGUE = {kind.kind: kind for kind in KINDS}


@dataclass
class TargetChecker:
    """Check the logical targets of one repository against its records.

    Parameters
    ----------
    reading : Composition
        The composition of the read side of the repository: its sections ``targets``, ``records``,
        ``resolution`` and ``repository``, its identity, the walk of its records and its record
        resolver, which reads the states of other repositories through its provider.

    Raises
    ------
    ConfigurationError
        If the configuration declares no section ``targets``, or the former identifiers list the
        derived identifier.
    """

    reading: Composition
    root: Path = field(init=False)
    #: The section ``targets``.
    config: TargetConfig = field(init=False)
    identity: Identity = field(init=False)
    walk: RecordWalk = field(init=False)
    #: The retired identifiers of the registry, empty without a valid registry.
    retired: Mapping[str, Retirement] = field(init=False)

    def __post_init__(self) -> None:
        configuration = self.reading.configuration
        walk = self.reading.walk
        if configuration.targets is None or walk is None:
            raise ConfigurationError("anagraphe.yml declares no section targets")
        self.root = self.reading.root
        self.config = configuration.targets
        self.identity = self.reading.identity
        self.walk = walk
        registry = configuration.records
        reading = read_registry(registry.path, registry.rel) if registry is not None else None
        self.retired = (
            reading.registry.retired if reading is not None and reading.registry is not None else {}
        )

    @property
    def declarations(self) -> Declarations | None:
        """Return the declarations of the contracts of the schema registry, None without one."""
        return self.walk.declarations

    @property
    def repository(self) -> str | None:
        """Return the identifier of the checked repository, None when it has no identity."""
        return self.identity.id

    @property
    def resolver(self) -> RecordResolver:
        """Return the record resolver of the root, its context built on the first target into
        another repository.

        Raises
        ------
        ConfigurationError
            If two entries of the context select states of one repository.
        """
        return self.reading.resolver

    def covers(self, rel: str) -> bool:
        """Whether a file is a record of the checked repository; a retired manifest is none."""
        return self.walk.covers(rel)

    def check(self, paths: tuple[Path, ...] = (), strict: bool = True) -> Report:
        """Check the records below the given targets, the whole repository without a target."""
        selected = select(self.root, paths, self.config.exemptions, self.covers, strict)
        issues = self._identity_issues()
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
        issues = [*identifier_issues(record, self.walk.table), *unit_issues(record)]
        for target_field in record.schema.targets if record.schema is not None else ():
            for keys, value in values_at(record.data, target_field.path):
                issues.extend(self._target_issues(record, target_field, pointer(*keys), value))
        return issues

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

    def _identity_issues(self) -> list[Issue]:
        """Return the warnings of the identity of the repository."""
        return [
            Issue(problem.rel or "", None, problem.kind, problem.detail, blocking=False)
            for problem in self.identity.problems
        ]

    def _schema_issues(self) -> list[Issue]:
        """Return the defects of the schemas of the registry, every contract read once."""
        return self.walk.schema_issues()
