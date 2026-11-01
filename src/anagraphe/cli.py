"""
Command-line interface: one group of commands per subpackage, and one check of all of them.

- ``anagraphe indexes check|write`` reports or writes the generated regions of the indexes;
- ``anagraphe refs check`` reports the references that do not resolve or break a convention;
- ``anagraphe check`` runs the check of every section that ``anagraphe.yml`` declares;
- ``anagraphe move OLD NEW`` moves a file or a folder, rewriting every pointer to it and updating
  the indexes.

Every command prints one line per issue, ``path:line: [warning: ]kind: detail``, then one summary
line per check. It exits with 0 when no issue blocks, 1 when one does, and 2 when the
configuration or a target is invalid. A target error is printed after ``target:``, and every other
error after ``configuration:``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from anagraphe import __version__
from anagraphe.configuration import RepositoryConfig, load_config
from anagraphe.core.configuration import ConfigurationError
from anagraphe.core.files import TargetError
from anagraphe.core.issues import Report
from anagraphe.indexes.configuration import IndexConfig
from anagraphe.indexes.service import Mode, run
from anagraphe.references.configuration import ReferenceConfig
from anagraphe.references.service import ReferenceChecker
from anagraphe.refactor import MovePlan, MoveService

app = typer.Typer(add_completion=False, no_args_is_help=True)
indexes_app = typer.Typer(
    no_args_is_help=True, help="Generate the indexes from record metadata and check their drift."
)
refs_app = typer.Typer(
    no_args_is_help=True, help="Check the references written between the files of the repository."
)
app.add_typer(indexes_app, name="indexes")
app.add_typer(refs_app, name="refs")

Paths = Annotated[list[Path] | None, typer.Argument(help="Files or folders to process.")]
Root = Annotated[Path, typer.Option(help="Repository root.")]
Config = Annotated[Path, typer.Option(help="Configuration path, relative to the root.")]
DEFAULT_CONFIG = Path("anagraphe.yml")


def _fail(error: Exception) -> NoReturn:
    """Report an invalid configuration or target, and exit with status 2."""
    label = "target" if isinstance(error, TargetError) else "configuration"
    typer.echo(f"{label}: {error}", err=True)
    raise typer.Exit(2) from error


def _load(root: Path, config_path: Path) -> tuple[Path, RepositoryConfig]:
    """Resolve the root, and load the configuration that it holds."""
    resolved = root.resolve()
    path = config_path if config_path.is_absolute() else resolved / config_path
    try:
        return resolved, load_config(resolved, path)
    except (ConfigurationError, OSError) as error:
        _fail(error)


def _emit(report: Report, summary: str) -> None:
    """Print the issues of one check, then its summary with the count of each kind."""
    for issue in report.issues:
        typer.echo(issue.format())
    kinds = ", ".join(f"{count} {kind}" for kind, count in report.kinds().items())
    typer.echo(
        f"\n{summary}: {report.blocking_count} violations, {report.warning_count} warnings"
        + (f" ({kinds})" if kinds else "")
    )


def _indexes(
    root: Path, config: IndexConfig, mode: Mode, paths: tuple[Path, ...], strict: bool = True
) -> Report:
    """Run the indexes in one mode, and print their report."""
    try:
        report = run(root, config, mode, paths, strict)
    except (ConfigurationError, OSError, ValueError) as error:
        # The index types raise a ValueError for an invalid schema, which is a configuration error.
        _fail(error)
    _emit(report, f"indexes: processed {report.processed} indexes holding blocks")
    return report


def _references(
    root: Path, config: ReferenceConfig, paths: tuple[Path, ...], strict: bool = True
) -> Report:
    """Check the references, and print their report."""
    try:
        report = ReferenceChecker(root, config).check(paths, strict)
    except (OSError, TargetError) as error:
        _fail(error)
    _emit(report, f"references: checked {report.processed} files")
    return report


def _section[S](section: S | None, name: str) -> S:
    """Return a declared section, or exit naming the section that the command requires."""
    if section is None:
        _fail(ConfigurationError(f"anagraphe.yml declares no section {name}"))
    return section


def _exit(*reports: Report) -> None:
    """Exit with status 1 when one report holds a blocking issue."""
    if any(report.blocking_count for report in reports):
        raise typer.Exit(1)


@app.command("check")
def check(paths: Paths = None, root: Root = Path("."), config: Config = DEFAULT_CONFIG) -> None:
    """Run the check of every section that the configuration declares, and write no file.

    A target needs to be processed by one section only, so a folder of notes holding no index is
    still checked for its references.
    """
    resolved, repository = _load(root, config)
    targets = tuple(paths or ())
    reports: list[Report] = []
    if repository.indexes is not None:
        reports.append(_indexes(resolved, repository.indexes, "check", targets, strict=False))
    if repository.references is not None:
        reports.append(_references(resolved, repository.references, targets, strict=False))
    if targets and not any(report.processed for report in reports):
        _fail(TargetError("the targets hold no file that a declared section reads"))
    _exit(*reports)


@indexes_app.command("check")
def indexes_check(
    paths: Paths = None, root: Root = Path("."), config: Config = DEFAULT_CONFIG
) -> None:
    """Report the generated regions that differ from their rendering, and write no file."""
    resolved, repository = _load(root, config)
    indexes = _section(repository.indexes, "indexes")
    _exit(_indexes(resolved, indexes, "check", tuple(paths or ())))


@indexes_app.command("write")
def indexes_write(
    paths: Paths = None, root: Root = Path("."), config: Config = DEFAULT_CONFIG
) -> None:
    """Rewrite every generated region, once all the selected indexes validate."""
    resolved, repository = _load(root, config)
    indexes = _section(repository.indexes, "indexes")
    _exit(_indexes(resolved, indexes, "write", tuple(paths or ())))


@refs_app.command("check")
def refs_check(
    paths: Paths = None, root: Root = Path("."), config: Config = DEFAULT_CONFIG
) -> None:
    """Report the references that name no file or anchor, or break a convention."""
    resolved, repository = _load(root, config)
    references = _section(repository.references, "references")
    _exit(_references(resolved, references, tuple(paths or ())))


def _print_plan(plan: MovePlan) -> None:
    """Print the rename and each edit of a move, in the order of the files."""
    typer.echo(f"rename {plan.old} -> {plan.new}")
    for edit in plan.index_edits:
        typer.echo(f"index {edit.holder}:{edit.line}: {edit.description}")
    for pointer in plan.pointer_edits:
        typer.echo(f"edit {pointer.holder}:{pointer.line}: {pointer.old} -> {pointer.new}")


@app.command("move")
def move(
    old: Annotated[str, typer.Argument(help="File or folder to move.")],
    new: Annotated[str, typer.Argument(help="Path of the file or folder after the move.")],
    dry_run: Annotated[bool, typer.Option(help="Print the plan, and change no file.")] = False,
    root: Root = Path("."),
    config: Config = DEFAULT_CONFIG,
) -> None:
    """Move a file or a folder, rewrite every pointer to it, and update the affected indexes."""
    resolved, repository = _load(root, config)
    config_path = config if config.is_absolute() else resolved / config
    service = MoveService(
        resolved, repository, config_path.resolve().relative_to(resolved).as_posix()
    )
    try:
        plan = service.plan(old, new)
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
