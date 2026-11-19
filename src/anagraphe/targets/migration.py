"""
The migration of the contracts named by the records of a repository, read from a migration plan.

When a domain tool migrates its records to a new version of their contract, the domain tool
migrates their fields, and Anagraphe rewrites the value of their binding key, ``_schema`` by
default. A plan in the contract ``anagraphe:migration-plan@1`` lists the mappings
``{from, to}``. Beyond its schema, a plan is valid when:

- every ``from`` and every ``to`` follows the grammar of a contract identifier, which Kleisis owns
  and :func:`kleisis.contracts.is_contract_identifier` reads;
- no ``from`` equals its ``to``, no ``from`` is listed twice, and no ``to`` is also a ``from``,
  since the order of two chained mappings would be ambiguous;
- every ``to`` is a contract of the schema registry of the records.

The records are those of the walk of the check of the targets. Each record whose binding key holds
a ``from`` is rewritten to the ``to`` of that mapping, read from its value before the migration, so
the mappings apply simultaneously and never chain. The rewriting replaces the characters of the
value alone, in a frontmatter, a YAML or JSON document, or a TOML document, so every other byte of
the file is kept. A rewritten record is parsed again, and must read as the record before with its
new contract. A record whose value cannot be rewritten so is ``unmigratable-record``, and a record
that cannot be read is ``unreadable-record``: either blocks the migration, which then writes no
file. Otherwise the migration replaces every changed file at once, and restores them all when one
replacement fails.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any, Collection, Mapping

import yaml
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from kleisis.contracts import is_contract_identifier

from anagraphe_read._core.configuration import ConfigurationError
from anagraphe_read._core.issues import Issue, IssueKind, pointer
from anagraphe_read._core.published import schema
from anagraphe_read._core.schemas import SchemaReader
from anagraphe_read._targets.configuration import TargetConfig
from anagraphe_read._targets.kinds import UNREADABLE_RECORD
from anagraphe_read._targets.records import NOTE_SUFFIX, TOML_SUFFIX, Record, parse_record
from anagraphe_read._targets.walk import RecordWalk

from anagraphe.core.structured import apply_edits, compose, node_at, replace_scalar
from anagraphe.core.writes import write_atomically

#: The contract of a migration plan.
PLAN_CONTRACT = "anagraphe:migration-plan@1"
#: The absolute ``$id`` of the schema of a migration plan.
PLAN_ID = "https://github.com/esther-poniatowski/anagraphe/schemas/migration-plan.v1.schema.yml"
#: The package file of the schema of a migration plan.
PLAN_FILE = "migration-plan.v1.schema.yml"

#: A record whose binding key names a contract that the plan replaces, reported under ``--check``.
PENDING_MIGRATION = "pending-migration"
#: A record whose binding key cannot be rewritten in place.
UNMIGRATABLE_RECORD = "unmigratable-record"

#: Every kind of issue that the migration can report.
KINDS: tuple[IssueKind, ...] = (
    IssueKind(PENDING_MIGRATION, "A record names a contract that the migration plan replaces."),
    IssueKind(UNMIGRATABLE_RECORD, "The binding key of a record cannot be rewritten in place."),
    IssueKind(
        UNREADABLE_RECORD,
        "A record cannot be read, so whether it names a migrated contract is unknown.",
    ),
)
#: The kinds reporting a record left unanalyzed, which makes a run incomplete.
UNANALYZED = frozenset({UNREADABLE_RECORD})

#: The opening line of a frontmatter, and the token closing it.
_OPENING = "---\n"
_CLOSING = "\n---"
#: A table header of a TOML document, which ends its top level.
_TABLE = re.compile(r"^[ \t]*\[", re.MULTILINE)


class PlanError(ConfigurationError):
    """Report a migration plan that cannot be read, or that is invalid."""


@dataclass(frozen=True)
class MigrationPlan:
    """The mappings of a valid plan, from each former contract to its successor."""

    #: The plan as the command line names it.
    rel: str
    mappings: Mapping[str, str]


@cache
def _validator() -> Draft202012Validator:
    """Return the validator of the schema of a plan."""
    return Draft202012Validator(schema(PLAN_FILE))


def check_plan(data: Any, rel: str) -> MigrationPlan:
    """Check the content of a plan, and return its mappings.

    Raises
    ------
    PlanError
        If the plan violates its schema, holds a contract outside the grammar of Kleisis, maps a
        contract to itself, lists a ``from`` twice, or lists a ``to`` that is also a ``from``.

    Examples
    --------
    >>> plan = check_plan({"_schema": PLAN_CONTRACT, "contracts": [
    ...     {"from": "tool:a@1", "to": "tool:a@2"}]}, "plan.yml")
    >>> dict(plan.mappings)
    {'tool:a@1': 'tool:a@2'}
    >>> check_plan({"_schema": PLAN_CONTRACT, "contracts": [
    ...     {"from": "tool:a@1", "to": "tool:a@2"}, {"from": "tool:a@2", "to": "tool:a@3"}]}, "p")
    Traceback (most recent call last):
    ...
    anagraphe.targets.migration.PlanError: the plan p is invalid: /contracts/1/from: tool:a@2 is the to of another mapping, so the order of the two mappings is ambiguous
    """
    problems: dict[str, str] = {}
    for error in _validator().iter_errors(data):
        problems.setdefault(pointer(*error.absolute_path), error.message)
    if problems:
        raise _invalid(rel, problems)
    entries = [(entry["from"], entry["to"]) for entry in data["contracts"]]
    targets = {to for _, to in entries}
    seen: set[str] = set()
    for number, (old, new) in enumerate(entries):
        for key, value in (("from", old), ("to", new)):
            if not is_contract_identifier(value):
                problems[pointer("contracts", number, key)] = (
                    f"{value!r} is not a contract identifier"
                )
        at = pointer("contracts", number, "from")
        if old == new:
            problems.setdefault(at, f"{old} maps to itself")
        elif old in seen:
            problems.setdefault(at, f"{old} is listed twice")
        elif old in targets:
            problems.setdefault(
                at,
                f"{old} is the to of another mapping, so the order of the two mappings is "
                "ambiguous",
            )
        seen.add(old)
    if problems:
        raise _invalid(rel, problems)
    return MigrationPlan(rel, dict(entries))


def read_plan(path: Path, rel: str) -> MigrationPlan:
    """Read and check the plan at ``path``, which the messages name ``rel``.

    Raises
    ------
    PlanError
        If the plan cannot be read or parsed, or is invalid.
    """
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as error:
        raise PlanError(f"the plan {rel} cannot be read: {error}") from error
    except (yaml.YAMLError, ValueError) as error:
        first = str(error).strip().splitlines()[0] if str(error).strip() else type(error).__name__
        raise PlanError(f"the plan {rel} cannot be parsed: {first}") from error
    return check_plan(data, rel)


def _invalid(rel: str, problems: Mapping[str, str]) -> PlanError:
    """Return the error of a plan naming each problem at its JSON Pointer."""
    listed = "; ".join(f"{at or '/'}: {problems[at]}" for at in sorted(problems))
    return PlanError(f"the plan {rel} is invalid: {listed}")


@dataclass(frozen=True)
class Change:
    """The rewriting of the binding key of one record."""

    rel: str
    #: The line of the value in the file, counted from 1.
    line: int
    old: str
    new: str


@dataclass(frozen=True)
class Migration:
    """The outcome of planning a migration: its changes, the texts to write, and its issues."""

    plan: MigrationPlan
    binding: str
    #: The number of records of the walk.
    processed: int
    changes: tuple[Change, ...] = ()
    #: The new text of each changed file.
    texts: Mapping[str, str] = field(default_factory=dict)
    #: The records that block the migration: unreadable, or unmigratable.
    issues: tuple[Issue, ...] = ()

    @property
    def blocked(self) -> bool:
        """Whether an issue blocks the migration, which then writes no file."""
        return any(issue.blocking for issue in self.issues)

    def pending(self) -> tuple[Issue, ...]:
        """Return the issue of each change, as the check of the migration reports it."""
        return tuple(
            Issue(
                change.rel,
                change.line,
                PENDING_MIGRATION,
                f"{self.binding}: {change.old} is replaced by {change.new} under {self.plan.rel}",
                locus=pointer(self.binding),
            )
            for change in self.changes
        )


class Unmigratable(ValueError):
    """Report why the binding key of a record cannot be rewritten in place."""


@dataclass
class MigrationService:
    """Rewrite the binding key of the records of one repository under a migration plan.

    Parameters
    ----------
    root : Path
        The root of the repository.
    targets : TargetConfig
        The section ``targets``, which supplies the walk, the binding key and the schema registry.
    reserved : frozenset[str]
        Repository-relative paths that are never records, such as the record registry and the
        plan itself.

    Raises
    ------
    ConfigurationError
        If the section ``targets`` declares no schema registry under ``records``.
    """

    root: Path
    targets: TargetConfig
    reserved: frozenset[str] = frozenset()
    walk: RecordWalk = field(init=False)

    def __post_init__(self) -> None:
        self.root = self.root.resolve()
        if self.targets.records is None:
            raise ConfigurationError(
                "the migration verifies each to against the schema registry of the records; "
                "declare targets.records.registry"
            )
        self.walk = RecordWalk(self.root, self.targets, self.reserved)

    @property
    def binding(self) -> str:
        """Return the key of a record naming its contract."""
        assert self.targets.records is not None
        return self.targets.records.binding

    def contracts(self) -> frozenset[str]:
        """Return the contracts of the schema registry of the records."""
        assert self.targets.records is not None
        return frozenset(SchemaReader(self.root, self.targets.records.registry).contracts())

    def require_targets(self, plan: MigrationPlan, contracts: Collection[str]) -> None:
        """Require every ``to`` of a plan to be a contract of the schema registry.

        Raises
        ------
        PlanError
            If a ``to`` names no contract of the registry.
        """
        absent = {
            pointer("contracts", number, "to"): f"{new} is no contract of the schema registry"
            for number, new in enumerate(plan.mappings.values())
            if new not in contracts
        }
        if absent:
            raise _invalid(plan.rel, absent)

    def plan(self, plan: MigrationPlan) -> Migration:
        """Return the changes of a migration, without writing any file.

        Raises
        ------
        PlanError
            If a ``to`` of the plan names no contract of the schema registry.
        """
        self.require_targets(plan, self.contracts())
        changes: list[Change] = []
        texts: dict[str, str] = {}
        issues: list[Issue] = []
        records = self.walk.records()
        for record in records:
            if record.problem is not None:
                issues.append(Issue(record.rel, None, UNREADABLE_RECORD, record.problem))
                continue
            old = record.contract
            if old is None or old not in plan.mappings:
                continue
            new = plan.mappings[old]
            try:
                text, line = self._rewrite(record, new)
            except Unmigratable as error:
                issues.append(
                    Issue(
                        record.rel,
                        None,
                        UNMIGRATABLE_RECORD,
                        f"{self.binding}: {old} cannot be replaced by {new}: {error}",
                        locus=pointer(self.binding),
                    )
                )
                continue
            changes.append(Change(record.rel, line, old, new))
            texts[record.rel] = text
        return Migration(plan, self.binding, len(records), tuple(changes), texts, tuple(issues))

    def apply(self, migration: Migration) -> bool:
        """Write the changed files at once, unless an issue blocks the migration; return whether
        the files were written."""
        if migration.blocked:
            return False
        write_atomically(self.root, migration.texts)
        return True

    def _rewrite(self, record: Record, new: str) -> tuple[str, int]:
        """Return the text of a record with its binding key rewritten, and the line of the value.

        Raises
        ------
        Unmigratable
            If the value cannot be located and replaced, or the new text reads otherwise.
        """
        path = self.root / record.rel
        try:
            # The bytes are decoded without translating line breaks, so each one is kept.
            text = path.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise Unmigratable(f"the record cannot be read: {error}") from error
        if record.rel.endswith(TOML_SUFFIX):
            rewritten, line = _toml_rewrite(text, self.binding, new)
        elif record.rel.endswith(NOTE_SUFFIX):
            if not text.startswith(_OPENING) or text.find(_CLOSING, len(_OPENING)) == -1:
                raise Unmigratable("the frontmatter cannot be located")
            end = text.find(_CLOSING, len(_OPENING))
            block, offset = text[len(_OPENING) : end], len(_OPENING)
            rewritten, line = _yaml_rewrite(text, block, offset, self.binding, new)
            line += 1
        else:
            rewritten, line = _yaml_rewrite(text, text, 0, self.binding, new)
        source = self.walk.metadata.source_of(record.rel)
        after = parse_record(
            record.rel, rewritten.replace("\r\n", "\n"), self.binding, None, source
        )
        if after.problem is not None or dict(after.data) != {**record.data, self.binding: new}:
            raise Unmigratable(
                "the rewritten record does not read as the record with its new contract"
            )
        return rewritten, line


def _yaml_rewrite(text: str, block: str, offset: int, binding: str, new: str) -> tuple[str, int]:
    """Return a text whose YAML block holds the new value at the binding key, and the line of the
    value within the block, counted from 1.

    The block is a YAML document, or the flow of a JSON document, located at ``offset`` in the
    text, such as a frontmatter in its note.
    """
    try:
        node = node_at(compose(block), [binding])
    except yaml.YAMLError as error:
        raise Unmigratable("the value cannot be located") from error
    if not isinstance(node, yaml.ScalarNode):
        raise Unmigratable("the value is no scalar")
    edit = replace_scalar(node, new, offset)
    return apply_edits(text, [edit]), node.start_mark.line + 1


def _toml_rewrite(text: str, binding: str, new: str) -> tuple[str, int]:
    """Return a TOML text whose top-level binding key holds the new value, and the line of the
    value, counted from 1.

    The key is located before the first table header, written bare or quoted, and holding a basic
    or a literal string that closes its line, before a comment.

    Examples
    --------
    >>> _toml_rewrite('_schema = "tool:a@1" # note\\n[tool]\\n_schema = "x"\\n', "_schema", "tool:a@2")
    ('_schema = "tool:a@2" # note\\n[tool]\\n_schema = "x"\\n', 1)
    """
    header = _TABLE.search(text)
    top = text[: header.start()] if header is not None else text
    key = re.escape(binding)
    found = re.search(
        rf"^[ \t]*(?:{key}|\"{key}\"|'{key}')[ \t]*=[ \t]*(?P<quote>[\"'])(?P<value>[^\"'\n]*)"
        r"(?P=quote)(?=[ \t]*(?:#[^\n]*)?$)",
        top,
        re.MULTILINE,
    )
    if found is None:
        raise Unmigratable("the value cannot be located at the top level of the document")
    start, end = found.span("value")
    return text[:start] + new + text[end:], text.count("\n", 0, start) + 1
