"""
The schemas that the package publishes as data, and the patterns of the string definitions of the
resource ``addressing.v1``.

The core reads them so that a primitive of the core, such as the block anchor of
:mod:`anagraphe_read._core.anchors`, derives its syntax from the resource instead of repeating it.
The subpackage :mod:`anagraphe_read._targets` names the resource and its contracts in
:mod:`anagraphe_read._targets.resource`. The package data holds every schema that Anagraphe
publishes, the contract ``anagraphe:migration-plan@1`` of the command line included, since Kleisis
reads the owned schemas of the repository from one folder.
"""

from __future__ import annotations

import re
from functools import cache
from importlib.resources import files
from typing import Any

import yaml

#: The package file of the resource of the addressing.
ADDRESSING_FILE = "addressing.v1.schema.yml"
#: The anchors closing a pattern of the resource, which admits a whole string without a final line
#: break under the reading of ECMA-262.
_OPENING = "^"
_CLOSING = "$(?!\\n)"


@cache
def schema(name: str) -> dict[str, Any]:
    """Return a schema of the package data, parsed once.

    Examples
    --------
    >>> schema(ADDRESSING_FILE)["$id"].endswith("addressing.v1.schema.yml")
    True
    """
    text = files("anagraphe_read").joinpath("data", "schemas", name).read_text(encoding="utf-8")
    parsed = yaml.safe_load(text)
    assert isinstance(parsed, dict)
    return parsed


def source(definition: str) -> str:
    """Return the pattern of a string definition of the resource, as the resource writes it."""
    written = schema(ADDRESSING_FILE)["$defs"][definition]["pattern"]
    assert isinstance(written, str)
    return written


@cache
def pattern(definition: str) -> re.Pattern[str]:
    """Return the pattern of a string definition of the resource: the identifiers ``repository-id``,
    ``record-id`` and ``unit-id``, the entry ``contract-entry`` of ``x-target-contract``, and the
    path ``property-path`` of ``x-identifier``.

    Examples
    --------
    >>> bool(pattern("record-id").fullmatch("quest.grokking.explain-delay"))
    True
    >>> bool(pattern("unit-id").fullmatch("eta.rep"))
    False
    >>> bool(pattern("contract-entry").fullmatch("geonexus:contact@17"))
    True
    """
    return re.compile(source(definition))


def body(definition: str) -> str:
    """Return the pattern of a string definition without its opening and closing anchors, so that
    another pattern can read the identifier inside a line.

    Examples
    --------
    >>> body("unit-id")
    '[A-Za-z0-9][A-Za-z0-9_-]*'
    """
    written = source(definition)
    assert written.startswith(_OPENING) and written.endswith(_CLOSING), written
    return written[len(_OPENING) : -len(_CLOSING)]


def matches(definition: str, value: Any) -> bool:
    """Whether a value is a string that the pattern of a string definition admits whole."""
    return isinstance(value, str) and pattern(definition).fullmatch(value) is not None
