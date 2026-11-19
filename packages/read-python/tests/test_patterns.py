"""The patterns of the packaged schemas give one verdict in every engine of JSON Schema.

JSON Schema reads a ``pattern`` under ECMA-262, where ``$`` matches only at the end of the string.
The validator of Python reads it with :func:`re.search`, where ``$`` also matches before a final
line break. Each pattern of the packaged schemas therefore closes on ``$(?!\\n)``, and this test
compares the two readings of every pattern on a corpus of probes.
"""

from __future__ import annotations

import re
from typing import Any, Iterator

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from anagraphe_read._core.anchors import BLOCK_ANCHOR, block_anchors
from anagraphe_read._core.published import body, pattern
from anagraphe_read._targets.registry.contract import REGISTRY_FILE
from anagraphe_read._targets.resource import ADDRESSING_FILE, REPOSITORY_FILE, schema

SCHEMAS = (ADDRESSING_FILE, REPOSITORY_FILE, REGISTRY_FILE)
#: Probes admitted or refused by some pattern, each also tried with a final line break.
PROBES = (
    "",
    "a",
    "ada",
    "geonexus",
    "a.b",
    "a-b",
    "Unit_1",
    "x:y@1",
    "identity.id",
    "a[0]",
    'a["b.c"]',
    "a[*].b",
    "notes/a.md",
    "a/..",
    "a//b",
    "2026-11-20",
)


def _patterns(node: Any) -> Iterator[str]:
    """Yield every value of a key ``pattern`` in a schema."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "pattern" and isinstance(value, str):
                yield value
            else:
                yield from _patterns(value)
    elif isinstance(node, list):
        for item in node:
            yield from _patterns(item)


PATTERNS = sorted({pattern for name in SCHEMAS for pattern in _patterns(schema(name))})


@pytest.mark.parametrize("pattern", PATTERNS)
def test_a_pattern_reads_alike_in_python_and_ecma_262(pattern: str) -> None:
    """Under ECMA-262 without the flag ``m``, ``$`` is the end of the string, ``\\Z`` in Python."""
    python = re.compile(pattern)
    ecma = re.compile(pattern.replace("$", r"\Z"))
    for probe in (*PROBES, *(probe + "\n" for probe in PROBES), "\n"):
        assert bool(python.search(probe)) == bool(ecma.search(probe)), repr(probe)


def test_the_validator_refuses_an_identifier_closed_by_a_line_break() -> None:
    resource = schema(ADDRESSING_FILE)
    validator = Draft202012Validator({**resource, "$ref": "#/$defs/record-id"})
    assert validator.is_valid("ada")
    assert not validator.is_valid("ada\n")


def test_a_block_anchor_names_exactly_a_unit_identifier() -> None:
    """The name of a block anchor is read by the pattern unit-id of the resource, so a name that
    the pattern refuses is no anchor."""
    probes = [probe for probe in PROBES if probe and " " not in probe]
    for probe in probes:
        found = block_anchors(f"A line. ^{probe}\n")
        assert (found == [probe]) == bool(pattern("unit-id").fullmatch(probe)), probe
    assert body("unit-id") in BLOCK_ANCHOR.pattern
