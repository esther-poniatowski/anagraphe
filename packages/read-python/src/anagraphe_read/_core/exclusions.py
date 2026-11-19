"""
Exclusions: the files kept out of a capability, by path pattern and by metadata.

The patterns follow the syntax of ``.gitignore``, read by the library ``pathspec``, and the metadata
filters take the form of the filter ``where`` of a group, applied to the metadata that the declared
sources read. Under the key ``git_ignored``, the files that Git ignores without tracking them are
excluded too, so that a file listed in ``.git/info/exclude`` stays out of every check of the clone
until Git tracks it. The rules are those of the ``.gitignore`` files and of ``.git/info/exclude``,
never the global excludes file of a machine, and each file that a rule of ``.git/info/exclude``
alone excludes is reported as a note, of the kind :data:`LOCALLY_EXCLUDED`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping

import pathspec

from anagraphe_read._core.configuration import (
    ConfigurationError,
    known_keys,
    mapping,
    strings_in_order,
)
from anagraphe_read._core.filters import Filter, parse_filter
from anagraphe_read._core.git_state import IgnoredPaths, ignored_untracked
from anagraphe_read._core.issues import Issue, IssueKind

#: A file that a rule of ``.git/info/exclude`` alone excludes from every check.
LOCALLY_EXCLUDED = "locally-excluded"
#: Every kind of issue that the exclusions report.
KINDS: tuple[IssueKind, ...] = (
    IssueKind(
        LOCALLY_EXCLUDED,
        "A rule of .git/info/exclude, which no commit records, excludes a file from every check.",
        blocking=False,
        note=True,
    ),
)

#: The patterns excluded before any declared one: the hidden files and folders, which hold the state
#: of a tool. A declared exception, such as ``!.github/``, admits one of them again.
HIDDEN = (".*",)


@dataclass(frozen=True)
class Exemptions:
    """The files excluded from every walk of the repository, by path and by metadata.

    The patterns follow the syntax of ``.gitignore``, read by the library ``pathspec``, after the
    pattern ``.*`` of the hidden paths. A later pattern prevails over an earlier one, so an
    exception opening on ``!`` admits a path again. The filters exclude each file whose metadata
    one of them selects. The paths that Git ignores without tracking them, a folder written with a
    final ``/``, are excluded with all they hold. The folder ``.git`` is never read.

    Examples
    --------
    >>> exemptions = Exemptions(("vendor/", "/build/", "utils/macros/*", "!utils/macros/_index.md"))
    >>> [exemptions.contains(PurePosixPath(path)) for path in ("a/vendor/x.md", "build/x.md",
    ...  "a/build/x.md", "utils/macros/x.md", "utils/macros/_index.md", ".venv/x.md", "a.md")]
    [True, True, False, True, False, True, False]
    >>> ignored = Exemptions(ignored=frozenset({"notes/draft.md", "scratch/"}))
    >>> [ignored.contains(PurePosixPath(path)) for path in ("notes/draft.md", "scratch/a/b.md",
    ...  "notes/a.md")]
    [True, True, False]
    """

    #: The declared patterns, in their order, after the hidden paths.
    patterns: tuple[str, ...] = ()
    filters: tuple[Filter, ...] = ()
    #: Return the metadata of a repository-relative file, read only when a filter is declared.
    metadata: Callable[[str], Mapping[str, Any]] | None = field(default=None, compare=False)
    #: The paths that Git ignores without tracking them, each folder with a final ``/``.
    ignored: frozenset[str] = frozenset()
    #: The paths of :attr:`ignored` that a rule of ``.git/info/exclude`` alone ignores, which the
    #: commands report, since no commit records that rule.
    local: frozenset[str] = frozenset()
    spec: pathspec.GitIgnoreSpec = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "spec", pathspec.GitIgnoreSpec.from_lines([*HIDDEN, *self.patterns])
        )

    def excludes_directory(self, folder: PurePosixPath) -> bool:
        """Return whether a repository-relative folder, and all it holds, is excluded by path."""
        posix = folder.as_posix()
        if posix in ("", "."):
            return False
        return (
            ".git" in folder.parts
            or self.spec.match_file(f"{posix}/")
            or self._ignored(PurePosixPath(posix), folder=True)
        )

    def excludes_path(self, path: PurePosixPath | Path) -> bool:
        """Return whether a repository-relative file is excluded by its path alone."""
        posix = PurePosixPath(path.as_posix())
        return (
            ".git" in posix.parts
            or self.spec.match_file(posix.as_posix())
            or self._ignored(posix, folder=False)
        )

    def locally_excluded(self) -> frozenset[str]:
        """Return the paths that a rule of ``.git/info/exclude`` alone keeps out of the checks.

        A path of :attr:`local` that a hidden name or a declared pattern already excludes stays out
        of the checks without that rule, so it is left out.

        Examples
        --------
        >>> exemptions = Exemptions(("vendor/",), local=frozenset({"a.md", "vendor/b.md", ".w/"}))
        >>> sorted(exemptions.locally_excluded())
        ['a.md']
        """
        return frozenset(path for path in self.local if not self.spec.match_file(path))

    def _ignored(self, path: PurePosixPath, folder: bool) -> bool:
        """Return whether Git ignores a path without tracking it, or one of its folders."""
        if not self.ignored:
            return False
        if (f"{path.as_posix()}/" if folder else path.as_posix()) in self.ignored:
            return True
        return any(
            f"{parent.as_posix()}/" in self.ignored
            for parent in path.parents
            if parent != PurePosixPath(".")
        )

    def contains(self, path: PurePosixPath | Path) -> bool:
        """Return whether a repository-relative file is excluded, by its path or by its metadata."""
        posix = PurePosixPath(path.as_posix())
        if self.excludes_path(posix):
            return True
        if not self.filters or self.metadata is None:
            return False
        data = self.metadata(posix.as_posix())
        return bool(data) and any(selected.selects(data) for selected in self.filters)

    def union(self, other: Exemptions) -> Exemptions:
        """Return the exemptions of a section added to the shared ones, the section patterns last.

        A pattern of the section therefore prevails over a shared one, as a later line of a
        ``.gitignore`` does, and the filters of both apply.
        """
        return Exemptions(
            (*self.patterns, *other.patterns),
            (*self.filters, *other.filters),
            self.metadata or other.metadata,
            self.ignored | other.ignored,
            self.local | other.local,
        )


#: The keys of an exclusion, and the retired keys with the pattern that replaces each of them.
EXCLUDE_KEYS = frozenset({"paths", "where", "gitignore", "git_ignored"})
RETIRED_EXCLUDE_KEYS = {
    "directories": "a folder name as `vendor/`, or one folder from the root as `/build/`",
    "files": "one file from the root as `/docs/private.md`",
    "basenames": "a file name at any depth as `README.md`",
}


def _patterns(root: Path, raw: Mapping[str, Any], field_name: str) -> tuple[str, ...]:
    """Return the declared patterns, after those of the root ``.gitignore`` when it is read."""
    declared = list(strings_in_order(raw.get("paths"), f"{field_name}.paths"))
    gitignore = raw.get("gitignore", False)
    if not isinstance(gitignore, bool):
        raise ConfigurationError(f"{field_name}.gitignore must be a boolean")
    if gitignore:
        path = root / ".gitignore"
        lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
        declared = [*lines, *declared]
    try:
        pathspec.GitIgnoreSpec.from_lines(declared)
    except (ValueError, TypeError) as error:
        raise ConfigurationError(f"{field_name}.paths holds an invalid pattern: {error}") from error
    return tuple(declared)


def _filters(raw: Mapping[str, Any], field_name: str) -> tuple[Filter, ...]:
    """Return the declared metadata filters, a file being excluded when one of them selects it."""
    value = raw.get("where")
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ConfigurationError(
            f"{field_name}.where must be a list of filters, such as {{status: archived}}"
        )
    filters: list[Filter] = []
    for number, entry in enumerate(value, start=1):
        parsed, problems = parse_filter(entry)
        if problems:
            raise ConfigurationError(f"{field_name}.where[{number}] {problems[0]}")
        filters.append(parsed)
    return tuple(filters)


def exemptions(
    value: Any,
    field_name: str,
    root: Path,
    metadata: Callable[[str], Mapping[str, Any]] | None = None,
) -> Exemptions:
    """Parse one ``exclude`` mapping: its patterns, its metadata filters, the reading of
    ``.gitignore``, and the exclusion of the files that Git ignores without tracking them.

    The metadata reader is the one declared for the repository, so that a filter tests the fields
    of a file where its source writes them.
    """
    raw = mapping(value, field_name)
    for key, replacement in RETIRED_EXCLUDE_KEYS.items():
        if key in raw:
            raise ConfigurationError(
                f"{field_name}.{key} is retired: list patterns in .gitignore syntax under "
                f"{field_name}.paths, writing {replacement}"
            )
    known_keys(raw, EXCLUDE_KEYS, field_name)
    filters = _filters(raw, field_name)
    ignored = _ignored(root, raw, field_name)
    return Exemptions(
        _patterns(root, raw, field_name),
        filters,
        metadata if filters else None,
        ignored.every,
        ignored.local,
    )


def _ignored(root: Path, raw: Mapping[str, Any], field_name: str) -> IgnoredPaths:
    """Return the paths that Git ignores without tracking them, when ``git_ignored`` is true.

    Raises
    ------
    ConfigurationError
        If the key is not a Boolean, or if it is true and ``root`` lies in no Git work tree.
    """
    declared = raw.get("git_ignored", False)
    if not isinstance(declared, bool):
        raise ConfigurationError(f"{field_name}.git_ignored must be a boolean")
    if not declared:
        return IgnoredPaths(frozenset(), frozenset())
    ignored = ignored_untracked(root)
    if ignored is None:
        raise ConfigurationError(
            f"{field_name}.git_ignored reads the files that Git ignores, but git ls-files fails "
            f"in {root}"
        )
    return ignored


def local_issues(local: frozenset[str]) -> list[Issue]:
    """Return one note for each path that a rule of ``.git/info/exclude`` alone excludes.

    Examples
    --------
    >>> [issue.format() for issue in local_issues(frozenset({"notes/draft.md"}))]
    ['notes/draft.md:1: note: locally-excluded: a rule of .git/info/exclude leaves the file out of \
every check, until Git tracks it']
    """
    return [
        Issue(
            path,
            None,
            LOCALLY_EXCLUDED,
            f"a rule of .git/info/exclude leaves the {'folder' if path.endswith('/') else 'file'} "
            "out of every check, until Git tracks it",
            blocking=False,
            note=True,
        )
        for path in sorted(local)
    ]
