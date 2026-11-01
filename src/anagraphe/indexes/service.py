"""The service of the indexes: render the selected indexes, then report or write their regions."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from anagraphe.core.files import TargetError, write_atomically
from anagraphe.core.git_state import committed_files
from anagraphe.core.issues import Issue, Report
from anagraphe.indexes.configuration import IndexConfig, load_vocabulary, validate_vocabulary
from anagraphe.indexes.fields import FieldRules
from anagraphe.indexes.generator import IndexGenerator, Settings
from anagraphe.indexes.types import IndexTypes

Mode = Literal["check", "write"]


@dataclass(frozen=True)
class RunResult(Report):
    """Outcome of processing all selected indexes, with the indexes whose regions changed."""

    changed: tuple[str, ...] = ()


def _indexes(
    root: Path, paths: tuple[Path, ...], settings: Settings, strict: bool = True
) -> list[Path]:
    """Resolve command targets to distinct index files.

    When ``strict``, a named target resolving to no index raises a :class:`TargetError`. The check
    of every section passes ``strict=False``, since such a target may hold only references.
    """
    indexes: list[Path] = []
    explicit = bool(paths)
    for given in paths or (root,):
        target = given if given.is_absolute() else root / given
        target = target.resolve()
        if explicit and not target.exists():
            raise TargetError(f"target does not exist: {given}")
        if target.is_dir():
            found = sorted(target.rglob(settings.entry_point))
        else:
            index = (
                target
                if target.name == settings.entry_point
                else target.parent / settings.entry_point
            )
            found = [index] if index.is_file() else []
        if explicit and strict and not found:
            raise TargetError(f"target resolves to no {settings.entry_point}: {given}")
        for index in found:
            relative = index.relative_to(root)
            if not settings.is_exempt(relative) and index not in indexes:
                indexes.append(index)
    return indexes


def run(
    root: Path,
    config: IndexConfig,
    mode: Mode,
    paths: tuple[Path, ...] = (),
    strict: bool = True,
) -> RunResult:
    """Render selected indexes and either report or commit their managed blocks.

    When ``strict``, a named target resolving to no index raises a :class:`TargetError`.
    """
    root = root.resolve()
    vocabulary = load_vocabulary(config.vocabulary)
    validate_vocabulary(vocabulary, config.vocabulary)
    settings = Settings.from_vocabulary(
        vocabulary,
        config.exemptions.contains,
        IndexTypes.load(config.index_types),
    )
    settings = dataclasses.replace(settings, is_member=config.is_member)
    indexes = _indexes(root, paths, settings, strict)
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
        config.migrations,
        config.metadata,
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
                        "a block differs from its rendering; run anagraphe indexes write",
                    )
                )

    if mode == "write" and not any(issue.blocking for issue in issues):
        write_atomically(root, changes)
    return RunResult(processed, tuple(issues), tuple(changes))
