"""Application service for deterministic index checking and writing."""

from __future__ import annotations

import dataclasses
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping

from anagraphe.configuration import RepositoryConfig, load_vocabulary, validate_vocabulary
from anagraphe.fields import FieldRules
from anagraphe.generator import IndexGenerator, Issue, Settings
from anagraphe.git_state import committed_files
from anagraphe.types import IndexTypes

Mode = Literal["check", "write"]


@dataclass(frozen=True)
class RunResult:
    """Outcome of processing all selected indexes."""

    processed: int
    changed: tuple[str, ...]
    issues: tuple[Issue, ...]

    @property
    def blocking_count(self) -> int:
        """Return the number of issues that fail the command."""
        return sum(issue.blocking for issue in self.issues)

    @property
    def warning_count(self) -> int:
        """Return the number of non-blocking issues."""
        return len(self.issues) - self.blocking_count


def _indexes(root: Path, paths: tuple[Path, ...], settings: Settings) -> list[Path]:
    """Resolve command targets to distinct index files."""
    indexes: list[Path] = []
    explicit = bool(paths)
    for given in paths or (root,):
        target = given if given.is_absolute() else root / given
        target = target.resolve()
        if explicit and not target.exists():
            raise ValueError(f"target does not exist: {given}")
        if target.is_dir():
            found = sorted(target.rglob(settings.entry_point))
        else:
            index = (
                target
                if target.name == settings.entry_point
                else target.parent / settings.entry_point
            )
            found = [index] if index.is_file() else []
        if explicit and not found:
            raise ValueError(f"target resolves to no {settings.entry_point}: {given}")
        for index in found:
            relative = index.relative_to(root)
            if not settings.is_exempt(relative) and index not in indexes:
                indexes.append(index)
    return indexes


def _write_atomically(root: Path, changes: Mapping[str, str]) -> None:
    """Replace all changed indexes and restore originals if one replacement fails."""
    prepared: dict[Path, Path] = {}
    backups: dict[Path, Path] = {}
    replaced: list[Path] = []
    try:
        for relative, text in changes.items():
            target = root / relative
            handle, temporary = tempfile.mkstemp(
                prefix=f".{target.name}.",
                suffix=".tmp",
                dir=target.parent,
            )
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            prepared[target] = Path(temporary)
            backup = Path(temporary).with_suffix(".bak")
            shutil.copy2(target, backup)
            backups[target] = backup
        for target, prepared_path in prepared.items():
            os.replace(prepared_path, target)
            replaced.append(target)
    except OSError:
        for target in reversed(replaced):
            os.replace(backups[target], target)
        raise
    finally:
        for path in (*prepared.values(), *backups.values()):
            path.unlink(missing_ok=True)


def run(
    root: Path, config: RepositoryConfig, mode: Mode, paths: tuple[Path, ...] = ()
) -> RunResult:
    """Render selected indexes and either report or commit their managed blocks."""
    root = root.resolve()
    vocabulary = load_vocabulary(config.vocabulary)
    validate_vocabulary(vocabulary, config.vocabulary)
    settings = Settings.from_vocabulary(
        vocabulary,
        config.exemptions.contains,
        IndexTypes.load(config.index_types),
    )
    indexes = _indexes(root, paths, settings)
    if config.inspect_git:
        committed = committed_files(root)
        if committed is not None:
            settings = dataclasses.replace(
                settings,
                new_indexes=frozenset(
                    index.relative_to(root).as_posix()
                    for index in indexes
                    if index.relative_to(root).as_posix() not in committed
                ),
            )
    generator = IndexGenerator(
        root,
        settings,
        FieldRules.from_vocabulary(vocabulary),
        config.task_states,
        lambda folder: config.sequence_for(root, folder),
    )

    issues: list[Issue] = []
    changes: dict[str, str] = {}
    processed = 0
    for index in indexes:
        relative = index.relative_to(root).as_posix()
        result = generator.generate(relative)
        if not result.issues and not result.changed and "<!-- index" not in result.text:
            continue
        processed += 1
        issues.extend(result.issues)
        if result.changed:
            changes[relative] = result.text
            if mode == "check":
                issues.append(
                    Issue(
                        relative,
                        1,
                        "stale-block",
                        "a block differs from its rendering; run anagraphe write",
                    )
                )

    if mode == "write" and not any(issue.blocking for issue in issues):
        _write_atomically(root, changes)
    return RunResult(processed, tuple(changes), tuple(issues))
