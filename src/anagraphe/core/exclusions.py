"""
Exclusions: the files kept out of a capability, by path pattern and by metadata.

The patterns follow the syntax of ``.gitignore``, read by the library ``pathspec``, and the metadata
filters take the form of the filter ``where`` of a group, applied to the metadata that the declared
sources read.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping

import pathspec

from anagraphe.core.configuration import (
    ConfigurationError,
    known_keys,
    mapping,
    strings_in_order,
)
from anagraphe.core.filters import Filter, parse_filter

#: The patterns excluded before any declared one: the hidden files and folders, which hold the state
#: of a tool. A declared exception, such as ``!.github/``, admits one of them again.
HIDDEN = (".*",)


@dataclass(frozen=True)
class Exemptions:
    """The files excluded from every walk of the repository, by path and by metadata.

    The patterns follow the syntax of ``.gitignore``, read by the library ``pathspec``, after the
    pattern ``.*`` of the hidden paths. A later pattern prevails over an earlier one, so an
    exception opening on ``!`` admits a path again. The filters exclude each file whose metadata
    one of them selects. The folder ``.git`` is never read.

    Examples
    --------
    >>> exemptions = Exemptions(("vendor/", "/build/", "utils/macros/*", "!utils/macros/_index.md"))
    >>> [exemptions.contains(PurePosixPath(path)) for path in ("a/vendor/x.md", "build/x.md",
    ...  "a/build/x.md", "utils/macros/x.md", "utils/macros/_index.md", ".venv/x.md", "a.md")]
    [True, True, False, True, False, True, False]
    """

    #: The declared patterns, in their order, after the hidden paths.
    patterns: tuple[str, ...] = ()
    filters: tuple[Filter, ...] = ()
    #: Return the metadata of a repository-relative file, read only when a filter is declared.
    metadata: Callable[[str], Mapping[str, Any]] | None = field(default=None, compare=False)
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
        return ".git" in folder.parts or self.spec.match_file(f"{posix}/")

    def contains(self, path: PurePosixPath | Path) -> bool:
        """Return whether a repository-relative file is excluded, by its path or by its metadata."""
        posix = PurePosixPath(path.as_posix())
        if ".git" in posix.parts or self.spec.match_file(posix.as_posix()):
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
        )


#: The keys of an exclusion, and the retired keys with the pattern that replaces each of them.
EXCLUDE_KEYS = frozenset({"paths", "where", "gitignore"})
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
    """Parse one ``exclude`` mapping of patterns, metadata filters, and the reading of ``.gitignore``.

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
    return Exemptions(_patterns(root, raw, field_name), filters, metadata if filters else None)
