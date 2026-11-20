"""
Command-line interface: one group of commands per subpackage, and one check of all of them.

- ``anagraphe indexes check|write`` reports or writes the generated regions of the indexes;
- ``anagraphe refs check`` reports the references that do not resolve or break a convention;
- ``anagraphe bindings check|show`` checks the bindings of the texts, or prints those of one file;
- ``anagraphe targets check`` reports the logical targets that do not resolve within the
  repository, the defects of the identifiers, and the warnings of the identity of the repository;
- ``anagraphe records write|check|retire`` writes the record registry, reports its differences
  from the records, or retires an identifier that no record holds any longer;
- ``anagraphe records migrate --plan PLAN`` rewrites the contract named by the binding key of the
  records under a migration plan, lists the changes under ``--dry-run``, or reports them under
  ``--check``;
- ``anagraphe check`` runs the check of every section that ``anagraphe.yml`` declares;
- ``anagraphe move OLD NEW`` moves a file or a folder, rewriting every pointer to it and updating
  the indexes, once confirmed on a terminal or by ``--yes``;
- ``anagraphe repository rename OLD NEW`` records the rename of a repository identifier in the
  renamed repository, and rewrites its citers in every repository checked out under the root, once
  confirmed on a terminal or by ``--yes``; ``--format json`` prints the plan for another tool.

Hodegos resolves the root and the configuration file. The root is the folder given by ``--root``,
else by ``ANAGRAPHE_ROOT``, else the nearest folder, from the current one upwards, holding a
configuration, else the current folder. The configuration is the file given by ``--config``, else
``anagraphe.yml`` at the one place of the root that holds it: the root itself, its subfolder
``.config/``, or a folder that the ``hodegos.yml`` of the root declares. Every path typed on the
command line, a target, ``--config`` or ``--output``, is read from the current folder.

Every command prints one line per issue, ``path:line: [warning: |note: ]kind: detail``, then one
summary line per check. It exits with 0 when no issue blocks, 1 when one does, and 2 when the
configuration or a target is invalid. A target error is printed after ``target:``, and every other
error after ``configuration:``.

The check commands also write their findings as a SARIF
log of the findings profile of Elenchos under ``--format sarif``, on standard output or at the path
of ``--output``. The text report is then printed on standard error when the log takes standard
output, and the exit status is unchanged.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from anagraphe_read._bindings.configuration import BindingConfig
from anagraphe_read._bindings.contract import CONTRACT as BINDINGS_CONTRACT
from anagraphe_read._bindings.kinds import KINDS as BINDING_KINDS
from anagraphe_read._bindings.kinds import UNANALYZED as BINDING_UNANALYZED
from anagraphe_read._bindings.model import Merge, Role
from anagraphe_read._core.configuration import (
    CONFIG_FILE,
    ConfigurationError,
    discover_configuration,
)
from anagraphe_read._core.exclusions import KINDS as EXCLUSION_KINDS
from anagraphe_read._core.exclusions import local_issues
from anagraphe_read._core.files import TargetError
from anagraphe_read._core.issues import IssueKind, Report
from anagraphe_read._repository import Composition
from anagraphe_read._resolution.git import default_cache
from anagraphe_read._targets.kinds import KINDS as TARGET_KINDS
from anagraphe_read._targets.kinds import UNANALYZED as TARGET_UNANALYZED
from anagraphe_read._targets.registry.configuration import RecordsConfig

from anagraphe import __version__
from anagraphe.bindings.service import BindingChecker
from anagraphe.configuration import RepositoryConfig, load_config
from anagraphe.core.sarif import Section, sarif_log
from anagraphe.indexes.configuration import IndexConfig
from anagraphe.indexes.kinds import KINDS as INDEX_KINDS
from anagraphe.indexes.kinds import UNREADABLE_METADATA
from anagraphe.indexes.service import Mode, run
from anagraphe.refactor import MovePlan, MoveService
from anagraphe.references.configuration import ReferenceConfig
from anagraphe.references.service import KINDS as REFERENCE_KINDS
from anagraphe.references.service import UNREADABLE, ReferenceChecker
from anagraphe.states import fetch_states
from anagraphe.targets.migration import KINDS as MIGRATION_KINDS
from anagraphe.targets.migration import UNANALYZED as MIGRATION_UNANALYZED
from anagraphe.targets.migration import Migration, MigrationService, read_plan
from anagraphe.targets.registry.kinds import KINDS as RECORD_KINDS
from anagraphe.targets.registry.kinds import UNANALYZED as RECORD_UNANALYZED
from anagraphe.targets.registry.service import RegistryService, RetireRefused
from anagraphe.targets.rename import RenamePlan, RenameService
from anagraphe.targets.service import TargetChecker

app = typer.Typer(add_completion=False, no_args_is_help=True)
indexes_app = typer.Typer(
    no_args_is_help=True, help="Generate the indexes from record metadata and check their drift."
)
refs_app = typer.Typer(
    no_args_is_help=True, help="Check the references written between the files of the repository."
)
bindings_app = typer.Typer(
    no_args_is_help=True, help="Resolve and check the bindings of the texts to the roles of tools."
)
app.add_typer(indexes_app, name="indexes")
app.add_typer(refs_app, name="refs")
targets_app = typer.Typer(
    no_args_is_help=True,
    help="Check the logical targets, the identifiers of the records and the repository identity.",
)
records_app = typer.Typer(
    no_args_is_help=True,
    help="Write and check the record registry, and retire the identifiers that it lists.",
)
app.add_typer(bindings_app, name="bindings")
app.add_typer(targets_app, name="targets")
app.add_typer(records_app, name="records")
states_app = typer.Typer(
    no_args_is_help=True,
    help="Fetch the selected states of the repositories that the targets name.",
)
app.add_typer(states_app, name="states")
repository_app = typer.Typer(
    no_args_is_help=True,
    help="Rename the identifier of a repository, and rewrite the citers that name it.",
)
app.add_typer(repository_app, name="repository")

Paths = Annotated[
    list[Path] | None,
    typer.Argument(help="Files or folders to process, relative to the current folder."),
]
Root = Annotated[
    Path | None,
    typer.Option(
        "--root",
        "-r",
        help="Repository root; by default the folder of ANAGRAPHE_ROOT, else the nearest folder, "
        "from the current one upwards, holding a configuration, else the current folder.",
    ),
]
Config = Annotated[
    Path | None,
    typer.Option(
        "--config",
        "-c",
        help="Configuration file, relative to the current folder; by default anagraphe.yml at "
        "the root, in .config/, or in a folder that hodegos.yml declares.",
    ),
]


class OutputFormat(str, Enum):
    """The form of the findings of a check."""

    TEXT = "text"
    SARIF = "sarif"


Format = Annotated[
    OutputFormat,
    typer.Option(
        "--format", help="text, or sarif for a SARIF 2.1.0 log of the findings profile of Elenchos."
    ),
]
Output = Annotated[
    Path | None,
    typer.Option(
        "--output",
        "-o",
        help="Write the SARIF log to this path, relative to the current folder, creating its "
        "folders; sarif only.",
    ),
]


class ShowFormat(str, Enum):
    """The form of the bindings printed by ``bindings show``, and of the plan of
    ``repository rename``."""

    TEXT = "text"
    JSON = "json"


#: Every section of the configuration, with every kind of issue that it can report.
CATALOGUES: dict[str, tuple[IssueKind, ...]] = {
    "exclusions": EXCLUSION_KINDS,
    "indexes": INDEX_KINDS,
    "references": REFERENCE_KINDS,
    "bindings": BINDING_KINDS,
    "targets": TARGET_KINDS,
    "records": RECORD_KINDS,
    "migration": MIGRATION_KINDS,
}

#: The kinds of each section reporting a file left unanalyzed, which makes a run incomplete.
UNANALYZED: dict[str, frozenset[str]] = {
    "exclusions": frozenset(),
    "indexes": frozenset({UNREADABLE_METADATA}),
    "references": frozenset({UNREADABLE}),
    "bindings": BINDING_UNANALYZED,
    "targets": TARGET_UNANALYZED,
    "records": RECORD_UNANALYZED,
    "migration": MIGRATION_UNANALYZED,
}


@dataclass
class Findings:
    """The destination of the text report, and the findings log of a command under sarif.

    The log is written once, when the command ends or stops. A section joins the log once its check
    has run to its end, so a run stopped before any section ran never began its analysis.
    """

    format: OutputFormat = OutputFormat.TEXT
    output: Path | None = None
    reports: dict[str, Report] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.output is not None and self.format is not OutputFormat.SARIF:
            raise typer.BadParameter("--output requires --format sarif", param_hint="--output")

    def echo(self, text: str) -> None:
        """Print a line of the text report, on standard error when the log takes standard output."""
        typer.echo(text, err=self.format is OutputFormat.SARIF and self.output is None)

    def record(self, section: str, report: Report) -> None:
        """Record the report of a section whose check ran to its end."""
        self.reports[section] = report

    def write(self, stopped: str | None = None) -> None:
        """Write the log under sarif, failed with the reason ``stopped`` when it is given.

        A file that a section could not parse leaves its pointers or its fields unchecked, so it also
        makes the run incomplete.
        """
        if self.format is not OutputFormat.SARIF:
            return
        unread = sorted(
            {
                issue.rel
                for name, report in self.reports.items()
                for issue in report.issues
                if issue.kind in UNANALYZED[name]
            }
        )
        if stopped is None and unread:
            stopped = (
                f"{len(unread)} files could not be parsed, so their pointers or fields were not "
                "checked: " + ", ".join(unread)
            )
        sections = [
            Section(name, kinds, self.reports[name].issues if name in self.reports else ())
            for name, kinds in CATALOGUES.items()
        ]
        log = sarif_log(sections, __version__, stopped, began=bool(self.reports))
        text = json.dumps(log, indent=2, ensure_ascii=False) + "\n"
        if self.output is None:
            typer.echo(text, nl=False)
            return
        try:
            self.output.parent.mkdir(parents=True, exist_ok=True)
            self.output.write_text(text, encoding="utf-8")
        except OSError as error:
            typer.echo(f"output: {error}", err=True)
            raise typer.Exit(2) from error


def _fail(error: Exception, findings: Findings | None = None) -> NoReturn:
    """Report an invalid configuration or target, write the failed log, and exit with status 2."""
    label = "target" if isinstance(error, TargetError) else "configuration"
    typer.echo(f"{label}: {error}", err=True)
    if findings is not None:
        findings.write(stopped=f"{label}: {error}")
    raise typer.Exit(2) from error


def _locate(
    root: Path | None, config: Path | None, findings: Findings | None = None
) -> tuple[Path, Path]:
    """Return the root and the configuration file of a command, located through Hodegos.

    A configuration that Hodegos rejects, and a root holding no configuration, stop the command
    with status 2.
    """
    try:
        resolved, path = discover_configuration(root, config)
    except ConfigurationError as error:
        _fail(error, findings)
    if path is None:
        _fail(
            ConfigurationError(
                f"{resolved}: no configuration: write {CONFIG_FILE} at the root, in .config/, or "
                "in a folder that hodegos.yml declares, or name it with --config"
            ),
            findings,
        )
    return resolved, path


def _here(paths: list[Path] | None) -> tuple[Path, ...]:
    """Return the targets of the command line, each read from the current folder."""
    return tuple(path.absolute() for path in paths or ())


def _load(
    root: Path | None, config_path: Path | None, findings: Findings | None = None
) -> tuple[Path, RepositoryConfig]:
    """Resolve the root, and load the configuration that it holds, or the one given.

    Each file that a rule of ``.git/info/exclude`` alone excludes is reported once, as a note: in
    the report of the command, or on standard error for a command that keeps no report.
    """
    resolved, path = _locate(root, config_path, findings)
    try:
        repository = load_config(resolved, path)
    except (ConfigurationError, OSError) as error:
        _fail(error, findings)
    issues = local_issues(_local_exclusions(repository))
    if issues and findings is not None:
        report = Report(0, tuple(issues))
        _emit(report, "exclusions: left out by .git/info/exclude", findings)
        findings.record("exclusions", report)
    for issue in issues if findings is None else ():
        typer.echo(issue.format(), err=True)
    return resolved, repository


def _local_exclusions(repository: RepositoryConfig) -> frozenset[str]:
    """Return the paths that a rule of ``.git/info/exclude`` alone excludes, in any section."""
    sections = (repository.indexes, repository.references, repository.bindings, repository.targets)
    return frozenset().union(
        *(section.exemptions.locally_excluded() for section in sections if section is not None)
    )


def _emit(report: Report, summary: str, findings: Findings | None = None) -> None:
    """Print the issues of one check, then its summary with the count of each kind."""
    echo = findings.echo if findings is not None else typer.echo
    for issue in report.issues:
        echo(issue.format())
    kinds = ", ".join(f"{count} {kind}" for kind, count in report.kinds().items())
    notes = f", {report.note_count} notes" if report.note_count else ""
    echo(
        f"\n{summary}: {report.blocking_count} violations, {report.warning_count} warnings{notes}"
        + (f" ({kinds})" if kinds else "")
    )


def _indexes(
    root: Path,
    config: IndexConfig,
    mode: Mode,
    paths: tuple[Path, ...],
    strict: bool = True,
    findings: Findings | None = None,
) -> Report:
    """Run the indexes in one mode, print their report, and record it for the log."""
    try:
        report = run(root, config, mode, paths, strict)
    except (ConfigurationError, OSError, ValueError) as error:
        # The index types raise a ValueError for an invalid schema, which is a configuration error.
        _fail(error, findings)
    _emit(report, f"indexes: processed {report.processed} indexes holding blocks", findings)
    if findings is not None:
        findings.record("indexes", report)
    return report


def _references(
    root: Path,
    config: ReferenceConfig,
    paths: tuple[Path, ...],
    strict: bool = True,
    findings: Findings | None = None,
) -> Report:
    """Check the references, print their report, and record it for the log."""
    try:
        report = ReferenceChecker(root, config).check(paths, strict)
    except (OSError, TargetError) as error:
        _fail(error, findings)
    _emit(report, f"references: checked {report.processed} files", findings)
    if findings is not None:
        findings.record("references", report)
    return report


def _bindings(
    root: Path,
    config: BindingConfig,
    paths: tuple[Path, ...],
    strict: bool = True,
    findings: Findings | None = None,
) -> Report:
    """Check the bindings, print their report, and record it for the log."""
    try:
        report = BindingChecker(root, config).check(paths, strict)
    except (ConfigurationError, OSError, TargetError) as error:
        _fail(error, findings)
    _emit(report, f"bindings: checked {report.processed} files", findings)
    if findings is not None:
        findings.record("bindings", report)
    return report


def _targets(
    reading: Composition,
    paths: tuple[Path, ...],
    strict: bool = True,
    findings: Findings | None = None,
) -> Report:
    """Check the logical targets, print their report, and record it for the log.

    The composition of the read side reads the states of other repositories through the Git
    provider of the machine.
    """
    try:
        report = TargetChecker(reading).check(paths, strict)
    except (ConfigurationError, OSError, TargetError) as error:
        _fail(error, findings)
    _emit(report, f"targets: checked {report.processed} records", findings)
    if findings is not None:
        findings.record("targets", report)
    return report


def _section[S](section: S | None, name: str, findings: Findings | None = None) -> S:
    """Return a declared section, or exit naming the section that the command requires."""
    if section is None:
        _fail(ConfigurationError(f"anagraphe.yml declares no section {name}"), findings)
    return section


def _exit(*reports: Report, findings: Findings | None = None) -> None:
    """Write the log, then exit with status 1 when one report holds a blocking issue."""
    if findings is not None:
        findings.write()
    if any(report.blocking_count for report in reports):
        raise typer.Exit(1)


@app.command("check")
def check(
    paths: Paths = None,
    root: Root = None,
    config: Config = None,
    output_format: Format = OutputFormat.TEXT,
    output: Output = None,
) -> None:
    """Run the check of every section that the configuration declares, and write no file.

    A target needs to be processed by one section only, so a folder of notes holding no index is
    still checked for its references.
    """
    findings = Findings(output_format, output)
    resolved, repository = _load(root, config, findings)
    targets = _here(paths)
    reports: list[Report] = []
    if repository.indexes is not None:
        reports.append(_indexes(resolved, repository.indexes, "check", targets, False, findings))
    if repository.references is not None:
        reports.append(_references(resolved, repository.references, targets, False, findings))
    if repository.bindings is not None:
        reports.append(_bindings(resolved, repository.bindings, targets, False, findings))
    if repository.targets is not None:
        reports.append(_targets(repository.reading, targets, False, findings))
    if targets and not any(report.processed for report in reports):
        _fail(TargetError("the targets hold no file that a declared section reads"), findings)
    # The registry is checked against the whole repository, whatever the targets.
    if repository.records is not None and repository.targets is not None:
        reports.append(_records(repository.reading, repository.records, findings))
    _exit(*reports, findings=findings)


@indexes_app.command("check")
def indexes_check(
    paths: Paths = None,
    root: Root = None,
    config: Config = None,
    output_format: Format = OutputFormat.TEXT,
    output: Output = None,
) -> None:
    """Report the generated regions that differ from their rendering, and write no file."""
    findings = Findings(output_format, output)
    resolved, repository = _load(root, config, findings)
    indexes = _section(repository.indexes, "indexes", findings)
    report = _indexes(resolved, indexes, "check", _here(paths), findings=findings)
    _exit(report, findings=findings)


@indexes_app.command("write")
def indexes_write(paths: Paths = None, root: Root = None, config: Config = None) -> None:
    """Rewrite every generated region, once all the selected indexes validate."""
    resolved, repository = _load(root, config)
    indexes = _section(repository.indexes, "indexes")
    _exit(_indexes(resolved, indexes, "write", _here(paths)))


@refs_app.command("check")
def refs_check(
    paths: Paths = None,
    root: Root = None,
    config: Config = None,
    output_format: Format = OutputFormat.TEXT,
    output: Output = None,
) -> None:
    """Report the references that name no file or anchor, or break a convention."""
    findings = Findings(output_format, output)
    resolved, repository = _load(root, config, findings)
    references = _section(repository.references, "references", findings)
    report = _references(resolved, references, _here(paths), findings=findings)
    _exit(report, findings=findings)


@bindings_app.command("check")
def bindings_check(
    paths: Paths = None,
    root: Root = None,
    config: Config = None,
    output_format: Format = OutputFormat.TEXT,
    output: Output = None,
) -> None:
    """Report the required texts bound to no value, and the invalid declarations and marks."""
    findings = Findings(output_format, output)
    resolved, repository = _load(root, config, findings)
    bindings = _section(repository.bindings, "bindings", findings)
    report = _bindings(resolved, bindings, _here(paths), findings=findings)
    _exit(report, findings=findings)


@targets_app.command("check")
def targets_check(
    paths: Paths = None,
    root: Root = None,
    config: Config = None,
    output_format: Format = OutputFormat.TEXT,
    output: Output = None,
) -> None:
    """Report the targets that do not resolve within the repository, the defects of the
    identifiers and of their declarations, and the warnings of the identity of the repository."""
    findings = Findings(output_format, output)
    resolved, repository = _load(root, config, findings)
    _section(repository.targets, "targets", findings)
    report = _targets(repository.reading, _here(paths), findings=findings)
    _exit(report, findings=findings)


def _registry(repository: RepositoryConfig, findings: Findings | None = None) -> RegistryService:
    """Return the service of the record registry, or exit naming the section that it requires."""
    _section(repository.records, "records", findings)
    try:
        return RegistryService(repository.reading)
    except ConfigurationError as error:
        _fail(error, findings)


def _records(
    reading: Composition, records: RecordsConfig, findings: Findings | None = None
) -> Report:
    """Check the record registry, print its report, and record it for the log."""
    try:
        report = RegistryService(reading).check()
    except (ConfigurationError, OSError) as error:
        _fail(error, findings)
    _emit(report, f"records: checked {records.rel} against {report.processed} records", findings)
    if findings is not None:
        findings.record("records", report)
    return report


@records_app.command("write")
def records_write(root: Root = None, config: Config = None) -> None:
    """Generate the record registry from the records of the repository, carrying over its retired
    identifiers; write nothing when the records or the registry hold a defect, or the repository has
    no identity.
    """
    resolved, repository = _load(root, config)
    service = _registry(repository)
    try:
        result = service.write()
    except (ConfigurationError, OSError) as error:
        _fail(error)
    if result.registry is None:
        report = Report(0, result.issues)
        _emit(report, f"records: wrote no {service.rel}, since issues block the write")
        _exit(report)
        return
    verb = "wrote" if result.changed else "left unchanged"
    typer.echo(
        f"records: {verb} {service.rel}, with {len(result.registry.records)} records and "
        f"{len(result.registry.retired)} retired identifiers"
    )


@records_app.command("check")
def records_check(
    root: Root = None,
    config: Config = None,
    output_format: Format = OutputFormat.TEXT,
    output: Output = None,
) -> None:
    """Report the differences between the record registry and the records, and write no file."""
    findings = Findings(output_format, output)
    _, repository = _load(root, config, findings)
    service = _registry(repository, findings)
    report = _records(repository.reading, service.records, findings)
    _exit(report, findings=findings)


@records_app.command("retire")
def records_retire(
    identifier: Annotated[
        str, typer.Argument(metavar="ID", help="Identifier of records that no record holds.")
    ],
    replaced_by: Annotated[
        str | None,
        typer.Option(
            "--replaced-by",
            metavar="NEW",
            help="Successor of a rename: a record, or another retired identifier.",
        ),
    ] = None,
    root: Root = None,
    config: Config = None,
) -> None:
    """Move an identifier that no record holds any longer from records into retired, with the day
    and its successor; a retired identifier is never reused."""
    resolved, repository = _load(root, config)
    service = _registry(repository)
    try:
        registry = service.retire(identifier, replaced_by)
    except RetireRefused as error:
        typer.echo(f"records: cannot retire {identifier}: {error}", err=True)
        raise typer.Exit(1) from error
    except (ConfigurationError, OSError) as error:
        _fail(error)
    retirement = registry.retired[identifier]
    successor = (
        f", replaced by {retirement.replaced_by}" if retirement.replaced_by is not None else ""
    )
    typer.echo(f"records: retired {identifier} on {retirement.date}{successor}, in {service.rel}")


def _print_changes(migration: Migration) -> None:
    """Print each change of a migration, in the order of the files."""
    for change in migration.changes:
        typer.echo(f"{change.rel}:{change.line}: {migration.binding}: {change.old} -> {change.new}")


@records_app.command("migrate")
def records_migrate(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    plan: Annotated[
        Path,
        typer.Option(
            "--plan",
            metavar="PATH",
            help="Migration plan in anagraphe:migration-plan@1, relative to the current folder.",
        ),
    ],
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="List the changes, and change no file.")
    ] = False,
    check_only: Annotated[
        bool,
        typer.Option(
            "--check", help="Report each record to migrate as a violation, and change no file."
        ),
    ] = False,
    root: Root = None,
    config: Config = None,
    output_format: Format = OutputFormat.TEXT,
    output: Output = None,
) -> None:
    """Rewrite the contract named by the binding key of every record whose contract the plan
    replaces, keeping every other byte of each file; write no file when a record cannot be read or
    rewritten."""
    if dry_run and check_only:
        raise typer.BadParameter("--dry-run and --check exclude each other", param_hint="--check")
    if output_format is OutputFormat.SARIF and not check_only:
        raise typer.BadParameter("--format sarif requires --check", param_hint="--format")
    findings = Findings(output_format, output)
    resolved, repository = _load(root, config, findings)
    targets = _section(repository.targets, "targets", findings)
    given = plan.absolute()
    reserved = {repository.records.rel} if repository.records is not None else set()
    if given.resolve().is_relative_to(resolved):
        reserved.add(given.resolve().relative_to(resolved).as_posix())
    try:
        service = MigrationService(resolved, targets, frozenset(reserved))
        migration = service.plan(read_plan(given, plan.as_posix()))
    except (ConfigurationError, OSError) as error:
        _fail(error, findings)
    summary = f"records: checked {migration.processed} records against {plan.as_posix()}"
    if check_only:
        report = Report(migration.processed, (*migration.pending(), *migration.issues))
        _emit(report, summary, findings)
        findings.record("migration", report)
        _exit(report, findings=findings)
        return
    _print_changes(migration)
    blocking = Report(migration.processed, migration.issues)
    for issue in migration.issues:
        typer.echo(issue.format())
    count = f"{len(migration.changes)} records to migrate in {len(migration.texts)} files"
    if dry_run:
        typer.echo(f"\n{summary}: {count}; dry run, no file changed")
        _exit(blocking)
        return
    try:
        written = service.apply(migration)
    except OSError as error:
        _fail(error)
    if not written:
        typer.echo(f"\n{summary}: {count}; no file changed, since issues block the migration")
        _exit(blocking)
        return
    typer.echo(f"\n{summary}: migrated {len(migration.changes)} records")


@bindings_app.command("show")
def bindings_show(
    path: Annotated[
        Path,
        typer.Argument(help="File whose bindings are resolved, relative to the current folder."),
    ],
    roles: Annotated[
        list[str] | None,
        typer.Option("--role", help="Role to resolve; every declared role by default."),
    ] = None,
    merge: Annotated[
        Merge, typer.Option(help="Merge rule of the resolved roles.")
    ] = Merge.OVERRIDE,
    output_format: Annotated[
        ShowFormat, typer.Option("--format", help="text, or json.")
    ] = ShowFormat.TEXT,
    root: Root = None,
    config: Config = None,
) -> None:
    """Print the values bound to a file for each role, with the declarations supplying them."""
    resolved, repository = _load(root, config)
    bindings = _section(repository.bindings, "bindings")
    target = path.resolve()
    if resolved not in target.parents or not target.is_file():
        _fail(TargetError(f"target is no file of the repository: {path}"))
    rel = target.relative_to(resolved).as_posix()
    resolver = repository.reading.binding_resolver
    try:
        results = [resolver.resolve(rel, Role(name, merge)) for name in roles or bindings.roles]
    except (ConfigurationError, ValueError) as error:
        _fail(error)
    problems = [
        {"file": item.rel, "pointer": item.pointer, "role": item.role, "kind": "invalid-binding"}
        for item in resolver.invalid
    ] + [
        {
            "file": item.rel,
            "pointer": "",
            "detail": item.detail,
            "kind": "unreadable-binding-source",
        }
        for item in resolver.unreadable
    ]
    if output_format is ShowFormat.JSON:
        data = {
            "contract": BINDINGS_CONTRACT,
            "file": rel,
            "merge": merge.value,
            "problems": problems,
            "bindings": {
                binding.role.name: {
                    "values": list(binding.values),
                    "declarations": [
                        {"file": item.rel, "pointer": item.pointer, "values": list(item.values)}
                        for item in binding.declarations
                    ],
                }
                for binding in results
            },
        }
        typer.echo(json.dumps(data, indent=2, ensure_ascii=False))
        return
    for binding in results:
        sources = ", ".join(f"{item.rel}#{item.pointer}" for item in binding.declarations)
        shown = ", ".join(binding.values) if binding.bound else "unbound"
        typer.echo(f"{binding.role.name}: {shown}" + (f" ({sources})" if sources else ""))
    for problem in problems:
        typer.echo(
            f"{problem['file']}: warning: {problem['kind']}: ignored "
            + (problem.get("detail") or f"{problem['role']} at {problem['pointer']}"),
            err=True,
        )


def _print_plan(plan: MovePlan) -> None:
    """Print the rename and each edit of a move, in the order of the files."""
    typer.echo(f"rename {plan.old} -> {plan.new}")
    for edit in plan.index_edits:
        typer.echo(f"index {edit.holder}:{edit.line}: {edit.description}")
    for pointer in plan.pointer_edits:
        typer.echo(f"edit {pointer.holder}:{pointer.line}: {pointer.old} -> {pointer.new}")


@states_app.command("fetch")
def states_fetch(root: Root = None, config: Config = None) -> None:
    """Fetch into the cache of the machine each selected state that no Git store of it holds.

    The states are those of the resolution context of the root: its submodules and the repositories
    of the section resolution. The command is the only one that uses the network. It exits with
    status 1 when a state stays absent from the machine.
    """
    resolved, repository = _load(root, config)
    # The composition reads the states through the Git provider over this cache.
    cache = default_cache()
    try:
        context = repository.reading.context
    except ConfigurationError as error:
        _fail(error)
    results = fetch_states(context.states(), cache)
    for result in results:
        detail = f": {result.detail}" if result.detail else ""
        typer.echo(f"{result.status.value}: {result.label} at {result.commit}{detail}")
    failed = sum(result.failed for result in results)
    typer.echo(f"states: {len(results)} states, {failed} absent from the machine, cache {cache}")
    if failed:
        raise typer.Exit(1)


@app.command("move")
def move(
    old: Annotated[
        Path, typer.Argument(help="File or folder to move, relative to the current folder.")
    ],
    new: Annotated[
        Path,
        typer.Argument(
            help="Path of the file or folder after the move, relative to the current folder."
        ),
    ],
    dry_run: Annotated[bool, typer.Option(help="Print the plan, and change no file.")] = False,
    yes: Annotated[
        bool, typer.Option("--yes", help="Apply the plan without asking for a confirmation.")
    ] = False,
    root: Root = None,
    config: Config = None,
) -> None:
    """Move a file or a folder, rewrite every pointer to it, and update the affected indexes.

    The move renames and edits files written by the researcher, so it asks for a confirmation on a
    terminal once the plan is printed. Without a terminal, only ``--yes`` lets it apply the plan.
    """
    if not dry_run and not yes and not sys.stdin.isatty():
        typer.echo(
            "usage: a move changes files written by the researcher; confirm it on a terminal, "
            "or pass --yes",
            err=True,
        )
        raise typer.Exit(2)
    resolved, repository = _load(root, config)
    _, config_path = _locate(root, config)
    service = MoveService(
        resolved, repository, config_path.resolve().relative_to(resolved).as_posix()
    )
    try:
        plan = service.plan(str(old.absolute()), str(new.absolute()))
    except (OSError, TargetError) as error:
        _fail(error)
    _print_plan(plan)
    files = len(plan.texts)
    summary = (
        f"move: 1 rename, {len(plan.pointer_edits)} pointer edits and "
        f"{len(plan.index_edits)} index edits in {files} files"
    )
    if dry_run:
        typer.echo(f"\n{summary}; dry run, no file changed")
        return
    if not yes and not typer.confirm(f"\n{summary}; apply the move?", default=False):
        typer.echo("move: cancelled, no file changed")
        raise typer.Exit(1)
    try:
        result = service.apply(plan)
    except (OSError, subprocess.CalledProcessError) as error:
        _fail(error)
    reports: list[Report] = []
    if result.regions is not None:
        _emit(
            result.regions,
            f"indexes: wrote {len(result.regions.changed)} of "
            f"{len(plan.affected_indexes)} affected indexes",
        )
        reports.append(result.regions)
    if result.check is not None:
        _emit(result.check, f"references: checked {result.check.processed} moved or edited files")
        reports.append(result.check)
    for residue in result.residues:
        typer.echo(f"{residue.rel}:{residue.line}: warning: residue: {residue.old} remains")
    typer.echo(f"\n{summary}; {len(result.residues)} old paths remain")
    _exit(*reports)


def _print_rename(plan: RenamePlan) -> None:
    """Print each edit, then each warning, of a rename, at their paths from the root."""
    for member in plan.members:
        for change in member.changes:
            verb = "create" if change.created else "edit"
            for edit in change.edits:
                before = f"{edit.old} -> " if edit.old is not None else "+ "
                typer.echo(
                    f"{verb} {member.at_root(change.path)}:{edit.line}: {edit.pointer}: "
                    f"{before}{edit.new}"
                )
    for member in plan.members:
        for issue in member.warnings:
            located = member.at_root(issue.rel) if issue.rel else member.path
            typer.echo(replace(issue, rel=located).format())


@repository_app.command("rename")
def repository_rename(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    old: Annotated[str, typer.Argument(metavar="OLD", help="Identifier of the repository.")],
    new: Annotated[
        str, typer.Argument(metavar="NEW", help="Identifier of the repository after the rename.")
    ],
    renamed: Annotated[
        Path | None,
        typer.Option(
            "--repository",
            metavar="PATH",
            help="Folder of the renamed repository, relative to the current folder: the root, or "
            "a submodule checked out under it; the root by default.",
        ),
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print the plan, and change no file.")
    ] = False,
    yes: Annotated[
        bool, typer.Option("--yes", help="Apply the plan without asking for a confirmation.")
    ] = False,
    output_format: Annotated[
        ShowFormat,
        typer.Option("--format", help="text, or json for the plan read by another tool."),
    ] = ShowFormat.TEXT,
    root: Root = None,
    config: Config = None,
) -> None:
    """Record the rename of a repository identifier in the renamed repository, and rewrite every
    target and every entry of the resolution context naming it, in the root and in each submodule
    checked out under it.

    The rename edits files written by the researcher, so it asks for a confirmation on a terminal
    once the plan is printed. Without a terminal, only ``--yes`` lets it apply the plan; under
    ``--format json``, the plan is printed for another tool, which passes ``--dry-run`` or
    ``--yes``. The command commits nothing.
    """
    machine = output_format is ShowFormat.JSON
    if machine and not dry_run and not yes:
        raise typer.BadParameter(
            "--format json prints the plan for another tool, which passes --dry-run or --yes",
            param_hint="--format",
        )
    if not dry_run and not yes and not sys.stdin.isatty():
        typer.echo(
            "usage: a rename changes files written by the researcher; confirm it on a terminal, "
            "or pass --yes",
            err=True,
        )
        raise typer.Exit(2)
    resolved, config_path = _discover(root, config)
    service = RenameService(resolved, config_path)
    try:
        plan = service.plan(old, new, renamed.absolute() if renamed is not None else None)
    except (ConfigurationError, OSError, TargetError) as error:
        _fail(error)
    if not machine:
        _print_rename(plan)
    if plan.refusals or dry_run:
        _end_rename(plan, machine, "refused, no file changed" if plan.refusals else None)
        return
    if not yes and not typer.confirm(f"\n{_summary(plan)}; apply the rename?", default=False):
        _end_rename(plan, machine, "cancelled, no file changed")
        return
    try:
        service.apply(plan)
    except OSError as error:
        _fail(error)
    _end_rename(plan, machine, "applied", applied=True)


def _discover(root: Path | None, config: Path | None) -> tuple[Path, Path | None]:
    """Return the root of a command and its configuration file, None when the root holds none."""
    try:
        return discover_configuration(root, config)
    except ConfigurationError as error:
        _fail(error)


def _summary(plan: RenamePlan) -> str:
    """Return the counts of a rename."""
    files = sum(len(member.changes) for member in plan.members)
    touched = sum(bool(member.changes) for member in plan.members)
    return (
        f"rename: {plan.old} -> {plan.new}: {plan.edit_count} edits in {files} files of "
        f"{touched} repositories"
    )


def _end_rename(
    plan: RenamePlan, machine: bool, outcome: str | None, applied: bool = False
) -> None:
    """Print the outcome of a rename, and exit with status 1 when it is refused or declined.

    The outcome of a dry run is None; under ``--format json``, the plan alone is printed.
    """
    if machine:
        typer.echo(json.dumps(plan.as_json(applied), indent=2, ensure_ascii=False))
    else:
        for reason in plan.refusals:
            typer.echo(f"rename: refused: {reason}", err=True)
        typer.echo(f"\n{_summary(plan)}; {outcome or 'dry run, no file changed'}")
    if plan.refusals or (outcome is not None and not applied):
        raise typer.Exit(1)


@app.callback()
def main_callback(
    version: Annotated[
        bool, typer.Option("--version", "-v", help="Show the version and exit.")
    ] = False,
) -> None:
    """Index the files of a repository, and check the references between them."""
    if version:
        typer.echo(__version__)
        raise typer.Exit()
