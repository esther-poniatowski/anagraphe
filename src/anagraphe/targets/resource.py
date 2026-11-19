"""
The schema resources of the addressing, published as package data: the resource ``addressing.v1``
and the contract ``anagraphe:repository@1`` of ``repository.yml``. That manifest is retired, since
the identity of a repository is derived; the contract stays published until the files bound to it
migrate.

The patterns of the identifiers, of the entries of ``x-target-contract`` and of the paths of
``x-identifier`` are read from the resource itself, so the read side states no pattern of its own. A consumer schema references the definition ``target`` by its absolute URI,
:data:`TARGET_REFERENCE`, and Anagraphe recognizes a target field by that URI without loading the
copy that Kleisis materializes in the consumer.
"""

from __future__ import annotations

import re
from functools import cache
from importlib.resources import files
from typing import Any

import yaml

#: The absolute ``$id`` of the resource, which carries its major version.
ADDRESSING_ID = "https://github.com/esther-poniatowski/anagraphe/schemas/addressing.v1.schema.yml"
#: The reference to the definition of a logical target.
TARGET_REFERENCE = f"{ADDRESSING_ID}#/$defs/target"
#: The contract of the retired manifest ``repository.yml``.
REPOSITORY_CONTRACT = "anagraphe:repository@1"
#: The package files of the two schemas.
ADDRESSING_FILE = "addressing.v1.schema.yml"
REPOSITORY_FILE = "repository.schema.yml"


@cache
def schema(name: str) -> dict[str, Any]:
    """Return a schema of the package data, parsed once.

    Examples
    --------
    >>> schema(ADDRESSING_FILE)["$id"] == ADDRESSING_ID
    True
    """
    text = files("anagraphe").joinpath("data", "schemas", name).read_text(encoding="utf-8")
    parsed = yaml.safe_load(text)
    assert isinstance(parsed, dict)
    return parsed


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
    return re.compile(schema(ADDRESSING_FILE)["$defs"][definition]["pattern"])


def matches(definition: str, value: Any) -> bool:
    """Whether a value is a string that the pattern of a string definition admits whole."""
    return isinstance(value, str) and pattern(definition).fullmatch(value) is not None
