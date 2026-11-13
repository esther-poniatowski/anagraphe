"""
Command-line interface: one group of commands per subpackage, and one check of all of them.

- ``anagraphe indexes check|write`` reports or writes the generated regions of the indexes;
- ``anagraphe refs check`` reports the references that do not resolve or break a convention;
- ``anagraphe check`` runs the check of every section that ``anagraphe.yml`` declares;
- ``anagraphe move OLD NEW`` moves a file or a folder, rewriting every pointer to it and updating
  the indexes, once confirmed on a terminal or by ``--yes``.

The root is the folder given by ``--root``, else by ``ANAGRAPHE_ROOT``, else the nearest folder,
from the current one upwards, holding a configuration, else the current folder. Every path typed on
the command line, a target, ``--config`` or ``--output``, is read from the current folder.

Every command prints one line per issue, ``path:line: [warning: |note: ]kind: detail``, then one
summary line per check. It exits with 0 when no issue blocks, 1 when one does, and 2 when the
configuration or a target is invalid. A target error is printed after ``target:``, and every other
error after ``configuration:``.

The commands ``check``, ``indexes check`` and ``refs check`` also write their findings as a SARIF
log of the findings profile of Elenchos under ``--format sarif``, on standard output or at the path
of ``--output``. The text report is then printed on standard error when the log takes standard
output, and the exit status is unchanged.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from anagraphe import __version__
from anagraphe.bindings.configuration import BindingConfig
from anagraphe.bindings.model import Merge, Role
from anagraphe.bindings.resolution import BindingResolver
from anagraphe.bindings.kinds import KINDS as BINDING_KINDS
from anagraphe.bindings.kinds import UNANALYZED as BINDING_UNANALYZED
from anagraphe.bindings.service import BindingChecker
from anagraphe.bindings.contract import CONTRACT as BINDINGS_CONTRACT
from anagraphe.configuration import (
    ROOT_VARIABLE,
    RepositoryConfig,
    find_root,
    load_config,
    locate_config,
)
from anagraphe.core.configuration import ConfigurationError
from anagraphe.core.files import TargetError
from anagraphe.core.issues import IssueKind, Report
from anagraphe.core.sarif import Section, sarif_log
from anagraphe.indexes.configuration import IndexConfig
from anagraphe.indexes.kinds import KINDS as INDEX_KINDS
from anagraphe.indexes.kinds import UNREADABLE_METADATA
from anagraphe.indexes.service import Mode, run
from anagraphe.references.configuration import ReferenceConfig
from anagraphe.references.service import KINDS as REFERENCE_KINDS
from anagraphe.references.service import UNREADABLE, ReferenceChecker
from anagraphe.refactor import MovePlan, MoveService

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
app.add_typer(bindings_app, name="bindings")

Paths = Annotated[
    list[Path] | None,
    typer.Argument(help="Files or folders to process, relative to the current folder."),
]
Root = Annotated[
    Path | None,
    typer.Option(
        "--root",
        "-r",
        envvar=ROOT_VARIABLE,
        show_envvar=True,
        help="Repository root; by default the nearest folder, from the current one upwards, "
        "holding config/tools/anagraphe.yml or anagraphe.yml, else the current folder.",
    ),
]
Config = Annotated[
    Path | None,
    typer.Option(
        "--config",
        "-c",
        help="Configuration file, relative to the current folder; by default "
        "config/tools/anagraphe.yml or anagraphe.yml below the root.",
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
    """The form of the bindings printed by ``bindings show``."""

    TEXT = "text"
    JSON = "json"


#: Every section of the configuration, with every kind of issue that it can report.
CATALOGUES: dict[str, tuple[IssueKind, ...]] = {
    "indexes": INDEX_KINDS,
    "references": REFERENCE_KINDS,
    "bindings": BINDING_KINDS,
}

#: The kinds of each section reporting a file left unanalyzed, which makes a run incomplete.
UNANALYZED: dict[str, frozenset[str]] = {
    "indexes": frozenset({UNREADABLE_METADATA}),
    "references": frozenset({UNREADABLE}),
    "bindings": BINDING_UNANALYZED,
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


def _root(root: Path | None) -> Path:
    """Return the root given, or the nearest folder holding a configuration, or the current one."""
    return root.resolve() if root is not None else find_root(Path.cwd())


def _here(paths: list[Path] | None) -> tuple[Path, ...]:
    """Return the targets of the command line, each read from the current folder."""
    return tuple(path.absolute() for path in paths or ())


def _load(
    root: Path | None, config_path: Path | None, findings: Findings | None = None
) -> tuple[Path, RepositoryConfig]:
    """Resolve the root, and load the configuration that it holds, or the one given."""
    resolved = _root(root)
    try:
        return resolved, load_config(resolved, locate_config(resolved, config_path))
    except (ConfigurationError, OSError) as error:
        _fail(error, findings)


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
    if targets and not any(report.processed for report in reports):
        _fail(TargetError("the targets hold no file that a declared section reads"), findings)
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
    resolver = BindingResolver(resolved, bindings)
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
    config_path = locate_config(resolved, config)
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
