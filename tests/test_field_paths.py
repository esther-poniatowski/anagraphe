"""Behavioral tests of the field paths of ADR 0008.

The conformance cases of ``specs/conformance/field-paths.yml`` fix the parsing and the printing of
field paths and patterns, their rejections, the conversions to and from a JSON Pointer, and the
expansion of patterns. The tests below run every case, show that the parser and the pattern of the
resource accept the same texts, on every case and on generated texts, and cover what the cases
cannot state: the lone surrogates and the segments outside the grammar.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import pytest
import yaml

from anagraphe.targets import (
    ADDRESSING_ID,
    ANY_ITEM,
    ANY_KEY,
    FieldPathError,
    PointerError,
    expand,
    from_pointer,
    is_field_path,
    is_field_path_pattern,
    parse_field_path,
    parse_field_path_pattern,
    print_field_path,
    to_pointer,
)
from anagraphe.targets.field_paths import PatternSegment
from anagraphe.targets.resource import matches

PROJECT = Path(__file__).resolve().parent.parent
SUITE: dict[str, Any] = yaml.safe_load(
    (PROJECT / "specs" / "conformance" / "field-paths.yml").read_text(encoding="utf-8")
)
WILDCARDS = {"item": ANY_ITEM, "key": ANY_KEY}


def _ids(section: str) -> dict[str, dict[str, Any]]:
    return {case["id"]: case for case in SUITE[section]}


def _segments(written: list[Any]) -> tuple[PatternSegment, ...]:
    """Return the segments of a case, each wildcard written as {any: item} or {any: key}."""
    return tuple(WILDCARDS[item["any"]] if isinstance(item, dict) else item for item in written)


def _accepts(parse: Any, text: str) -> bool:
    try:
        parse(text)
    except FieldPathError:
        return False
    return True


def test_cases_name_the_resource_and_its_definitions() -> None:
    assert SUITE["resource"] == ADDRESSING_ID
    assert SUITE["definitions"] == {"path": "field-path", "pattern": "field-path-pattern"}


@pytest.mark.parametrize("case_id", sorted(_ids("paths")))
def test_path_conforms(case_id: str) -> None:
    case = _ids("paths")[case_id]
    segments = parse_field_path(case["text"])
    assert segments == tuple(case["segments"])
    assert print_field_path(segments) == case["printed"]
    assert parse_field_path(case["printed"]) == segments


@pytest.mark.parametrize("case_id", sorted(_ids("invalid-paths")))
def test_invalid_path_conforms(case_id: str) -> None:
    case = _ids("invalid-paths")[case_id]
    with pytest.raises(FieldPathError) as raised:
        parse_field_path(case["text"])
    assert (raised.value.reason, raised.value.offset) == (case["reason"], case["offset"])


@pytest.mark.parametrize("case_id", sorted(_ids("patterns")))
def test_pattern_conforms(case_id: str) -> None:
    case = _ids("patterns")[case_id]
    segments = parse_field_path_pattern(case["text"])
    assert segments == _segments(case["segments"])
    assert print_field_path(segments) == case["printed"]


@pytest.mark.parametrize("case_id", sorted(_ids("invalid-patterns")))
def test_invalid_pattern_conforms(case_id: str) -> None:
    case = _ids("invalid-patterns")[case_id]
    with pytest.raises(FieldPathError) as raised:
        parse_field_path_pattern(case["text"])
    assert (raised.value.reason, raised.value.offset) == (case["reason"], case["offset"])


def _texts() -> list[str]:
    """Return every text of the parse cases, printed forms included."""
    sections = ("paths", "invalid-paths", "patterns", "invalid-patterns")
    texts = {case[key] for section in sections for case in SUITE[section] for key in ("text",)}
    texts |= {case["printed"] for section in ("paths", "patterns") for case in SUITE[section]}
    texts |= {case["pattern"] for case in SUITE["expansions"]}
    texts |= {case["path"] for case in SUITE["from-pointer"] if "path" in case}
    return sorted(texts)


@pytest.mark.parametrize("text", _texts())
def test_the_patterns_of_the_resource_accept_what_the_parsers_accept(text: str) -> None:
    assert is_field_path(text) == _accepts(parse_field_path, text)
    assert is_field_path_pattern(text) == _accepts(parse_field_path_pattern, text)


def test_the_patterns_and_the_parsers_agree_on_generated_texts() -> None:
    """Texts drawn from the characters that the grammar distinguishes, with a fixed seed."""
    alphabet = list("a0159.[]\"\\*-u/~ 'tbnfA") + [chr(0x09), chr(0xA0), chr(0x2028), "é", "𝛼"]
    draw = random.Random(8)
    for _ in range(20000):
        text = "".join(draw.choice(alphabet) for _ in range(draw.randint(0, 9)))
        assert is_field_path(text) == _accepts(parse_field_path, text), text
        assert is_field_path_pattern(text) == _accepts(parse_field_path_pattern, text), text


@pytest.mark.parametrize("path", SUITE["property-paths"])
def test_every_property_path_is_a_field_path_of_the_same_meaning(path: str) -> None:
    assert matches("property-path", path)
    assert parse_field_path(path) == tuple(path.split("."))
    assert print_field_path(parse_field_path(path)) == path


@pytest.mark.parametrize("case_id", sorted(_ids("to-pointer")))
def test_to_pointer_conforms(case_id: str) -> None:
    case = _ids("to-pointer")[case_id]
    assert to_pointer(tuple(case["segments"])) == case["pointer"]


@pytest.mark.parametrize("case_id", sorted(_ids("from-pointer")))
def test_from_pointer_conforms(case_id: str) -> None:
    case = _ids("from-pointer")[case_id]
    if "reason" in case:
        with pytest.raises(PointerError) as raised:
            from_pointer(case["pointer"], case["document"])
        assert (raised.value.reason, raised.value.offset) == (case["reason"], case["offset"])
    else:
        path = from_pointer(case["pointer"], case["document"])
        assert print_field_path(path) == case["path"]
        assert to_pointer(path) == case["pointer"]


@pytest.mark.parametrize("case_id", sorted(_ids("expansions")))
def test_expansion_conforms(case_id: str) -> None:
    case = _ids("expansions")[case_id]
    paths = expand(parse_field_path_pattern(case["pattern"]), case["document"])
    assert [print_field_path(path) for path in paths] == case["paths"]


def test_a_lone_surrogate_of_a_quoted_key_is_printed_as_an_escape() -> None:
    """JSON writes a lone surrogate as an escape; a bare key holds it as itself."""
    assert print_field_path((chr(0xD800),)) == chr(0xD800)
    key = "a " + chr(0xD800)
    printed = print_field_path((key,))
    assert printed == '["a ' + chr(92) + 'ud800"]'
    assert parse_field_path(printed) == (key,)


@pytest.mark.parametrize("segment", [True, -1, 10**15, 1.5, None])
def test_a_segment_outside_the_grammar_is_refused(segment: Any) -> None:
    with pytest.raises(ValueError):
        print_field_path(("a", segment))
    with pytest.raises(ValueError):
        to_pointer(("a", segment))
