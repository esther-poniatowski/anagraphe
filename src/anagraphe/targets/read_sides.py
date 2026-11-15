"""
The comparison of the versions of the specification declared by the other read sides of a
repository with the versions that Anagraphe implements.

A repository may bundle another read side of the addressing, such as the TypeScript package
``@anagraphe/read`` inside an Obsidian plugin, which writes its ``IMPLEMENTED_SPECIFICATION`` into
a file of the repository. The key ``read_sides`` of the section ``targets`` names each such file
and the JSON Pointer of the declaration in it. The check reads each declaration and compares it,
key by key, with :data:`anagraphe.targets.IMPLEMENTED_SPECIFICATION`:

- a declaration that differs is reported as ``read-side-mismatch``, naming each differing key with
  the declared and the implemented value;
- a file that cannot be read or parsed, a pointer naming no value, and a value that is not a
  mapping of strings are reported as ``unreadable-read-side``.

Each finding names the declared file, and the declared pointer as its locus.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Sequence

import yaml

from anagraphe.core.issues import Issue
from anagraphe.core.json_text import load_json
from anagraphe.targets.configuration import ReadSide
from anagraphe.targets.field_paths import PointerError, from_pointer, match_nodes
from anagraphe.targets.kinds import READ_SIDE_MISMATCH, UNREADABLE_READ_SIDE
from anagraphe.targets.specification import IMPLEMENTED_SPECIFICATION


class Unreadable(ValueError):
    """Report a declaration of a read side that yields no mapping of strings."""


def check_read_sides(
    sides: Sequence[ReadSide], implemented: Mapping[str, str] = IMPLEMENTED_SPECIFICATION
) -> list[Issue]:
    """Return the issues of the declarations of the read sides, compared with ``implemented``."""
    issues: list[Issue] = []
    for side in sides:
        try:
            declared = read_declaration(side)
        except Unreadable as error:
            issues.append(_issue(side, UNREADABLE_READ_SIDE, str(error)))
            continue
        differences = compare(declared, implemented)
        if differences:
            issues.append(
                _issue(
                    side,
                    READ_SIDE_MISMATCH,
                    "the read side implements other versions of the specification than "
                    f"Anagraphe: {'; '.join(differences)}",
                )
            )
    return issues


def read_declaration(side: ReadSide) -> Mapping[str, str]:
    """Return the declaration of a read side: the mapping of strings at its pointer.

    Raises
    ------
    Unreadable
        If the file cannot be read or parsed, the pointer names no value, or the value is not a
        mapping of strings.
    """
    try:
        text = side.path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise Unreadable(f"the file {side.rel} cannot be read: {error}") from error
    try:
        document = load_json(text) if side.rel.endswith(".json") else yaml.safe_load(text)
    except (yaml.YAMLError, ValueError) as error:
        # A JSON or YAML error, or a YAML timestamp naming an impossible date.
        raise Unreadable(f"the file {side.rel} cannot be parsed: {error}") from error
    try:
        found = match_nodes(from_pointer(side.pointer, document), document)
    except PointerError as error:
        raise Unreadable(
            f"the file {side.rel} holds no value at {side.pointer}: {error}"
        ) from error
    if not found:
        raise Unreadable(f"the file {side.rel} holds no value at {side.pointer}")
    value: Any = found[0][1]
    if not isinstance(value, Mapping) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    ):
        raise Unreadable(f"the value at {side.pointer} is not a mapping of strings to strings")
    return value


def compare(declared: Mapping[str, str], implemented: Mapping[str, str]) -> list[str]:
    """Return each key on which two declarations differ, with both values, in the order of keys.

    Examples
    --------
    >>> for line in compare({"addressing": "a.v1", "x": "y"}, {"addressing": "a.v2", "r": "r@1"}):
    ...     print(line)
    addressing: declared a.v1, implemented a.v2
    r: declared absent, implemented r@1
    x: declared y, implemented absent
    """
    return [
        f"{key}: declared {declared.get(key, 'absent')}, implemented {implemented.get(key, 'absent')}"
        for key in sorted({*declared, *implemented})
        if declared.get(key) != implemented.get(key)
    ]


def _issue(side: ReadSide, kind: str, detail: str) -> Issue:
    """Return an issue of a read side, located at its pointer in its file."""
    return Issue(side.rel, None, kind, detail, locus=side.pointer)
