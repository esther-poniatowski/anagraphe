"""Command-line interface for deterministic repository indexes."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from anagraphe import __version__
from anagraphe.application import Mode, run
from anagraphe.configuration import ConfigurationError, load_config

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _execute(mode: Mode, paths: tuple[Path, ...], root: Path, config_path: Path) -> None:
    """Run one command and translate its result to the stable text interface."""
    resolved_root = root.resolve()
    resolved_config = config_path if config_path.is_absolute() else resolved_root / config_path
    try:
        repository = load_config(resolved_root, resolved_config)
        result = run(resolved_root, repository, mode, paths)
    except (ConfigurationError, OSError, ValueError) as error:
        typer.echo(f"configuration: {error}", err=True)
        raise typer.Exit(2) from error
    for issue in result.issues:
        marker = "" if issue.blocking else "warning: "
        typer.echo(f"{issue.rel}:{issue.line}: {marker}{issue.kind}: {issue.detail}")
    typer.echo(
        f"\nprocessed {result.processed} indexes holding blocks: "
        f"{result.blocking_count} violations, {result.warning_count} warnings"
    )
    if result.blocking_count:
        raise typer.Exit(1)


@app.command("check")
def check(
    paths: Annotated[
        list[Path] | None, typer.Argument(help="Indexes or folders to process.")
    ] = None,
    root: Annotated[Path, typer.Option(help="Repository root.")] = Path("."),
    config: Annotated[Path, typer.Option(help="Configuration path, relative to the root.")] = Path(
        "anagraphe.yml"
    ),
) -> None:
    """Report managed index blocks that differ from their deterministic rendering."""
    _execute("check", tuple(paths or ()), root, config)


@app.command("write")
def write(
    paths: Annotated[
        list[Path] | None, typer.Argument(help="Indexes or folders to process.")
    ] = None,
    root: Annotated[Path, typer.Option(help="Repository root.")] = Path("."),
    config: Annotated[Path, typer.Option(help="Configuration path, relative to the root.")] = Path(
        "anagraphe.yml"
    ),
) -> None:
    """Rewrite every managed index block after all selected indexes validate."""
    _execute("write", tuple(paths or ()), root, config)


@app.callback()
def main_callback(
    version: Annotated[
        bool, typer.Option("--version", "-v", help="Show the version and exit.")
    ] = False,
) -> None:
    """Generate repository indexes from record metadata and check their drift."""
    if version:
        typer.echo(__version__)
        raise typer.Exit()
