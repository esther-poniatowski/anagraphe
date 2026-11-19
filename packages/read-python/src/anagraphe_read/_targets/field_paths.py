"""
Field paths: the text naming one node of a document, its parsing and its canonical printing, its
conversions to and from a JSON Pointer, and the expansion of a field-path pattern.

A key follows a dot, except at the start of the path; a position in a sequence stands between
brackets, counted from zero; a key that a bare key cannot hold stands between brackets as a JSON
string. The empty text names the root. A pattern may also hold the wildcards ``[*]``, every item of
a sequence, and ``*``, every key of a mapping.

The definitions ``field-path`` and ``field-path-pattern`` of the resource ``addressing.v1`` state
the grammar once. The parser tests each bare key and each bracket against the pattern of
``field-path``, so it restates no class of characters, and it reports the reason and the offset of
the first defect from the left. The specification ``docs/specification/field-paths.md`` states each
reading, and the TypeScript package ``@anagraphe/read`` implements the same readings.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from enum import Enum, StrEnum
from typing import Any, Callable, Iterable, NoReturn, Sequence, TypeAlias, TypeGuard

from anagraphe_read._core.issues import pointer
from anagraphe_read._targets.resource import matches


class Wildcard(Enum):
    """A wildcard of a field-path pattern, by its written form."""

    ITEM = "[*]"
    KEY = "*"


#: The wildcard naming every item of a sequence.
ANY_ITEM = Wildcard.ITEM
#: The wildcard naming every key of a mapping.
ANY_KEY = Wildcard.KEY
#: A key of a mapping, or a position in a sequence.
Segment: TypeAlias = str | int
#: The segments of a field path, from the root.
FieldPath: TypeAlias = tuple[Segment, ...]
#: A segment of a field-path pattern.
PatternSegment: TypeAlias = str | int | Wildcard

#: A position admitted by the grammar: at most 15 digits, so that it is exact in a double.
POSITIONS = 10**15
#: The canonical decimal form of a position in a JSON Pointer.
DECIMAL = re.compile("0|[1-9][0-9]*")
#: The lone surrogates, which JSON writes as escapes.
SURROGATE = re.compile(f"[{chr(0xD800)}-{chr(0xDFFF)}]")


class FieldPathReason(StrEnum):
    """Why a text is not a field path, or not a field-path pattern."""

    EMPTY_KEY = "empty-key"
    INVALID_CHARACTER = "invalid-character"
    WILDCARD = "wildcard"
    UNCLOSED_BRACKET = "unclosed-bracket"
    INVALID_INDEX = "invalid-index"
    INVALID_QUOTED_KEY = "invalid-quoted-key"
    INVALID_BRACKET = "invalid-bracket"


class PointerReason(StrEnum):
    """Why a JSON Pointer converts to no field path within a document."""

    NOT_A_POINTER = "not-a-pointer"
    INVALID_ESCAPE = "invalid-escape"
    INVALID_INDEX = "invalid-index"
    INDEX_OUT_OF_RANGE = "index-out-of-range"
    NO_NODE = "no-node"


MESSAGES: Mapping[str, str] = {
    FieldPathReason.EMPTY_KEY: 'a key holds at least one character; write the empty key [""]',
    FieldPathReason.INVALID_CHARACTER: (
        "a bare key holds no dot, bracket, quote, star, space or control character, and a segment "
        "is followed by a dot, a bracket or the end; write such a key in brackets as a JSON string"
    ),
    FieldPathReason.WILDCARD: "a field path names one node and holds no wildcard; write a key * "
    'as ["*"]',
    FieldPathReason.UNCLOSED_BRACKET: "no bracket closes this bracket",
    # The two reasons invalid-index are one string, so they share one message.
    FieldPathReason.INVALID_INDEX: (
        "a position is 0 or a decimal of at most 15 digits without a leading zero; below a "
        "sequence, a token of a JSON Pointer is a decimal without a leading zero"
    ),
    FieldPathReason.INVALID_QUOTED_KEY: "a quoted key is one JSON string",
    FieldPathReason.INVALID_BRACKET: "a bracket holds a position or a JSON string",
    PointerReason.NOT_A_POINTER: "a JSON Pointer is empty or opens on /",
    PointerReason.INVALID_ESCAPE: "a ~ is followed by 0 or 1",
    PointerReason.INDEX_OUT_OF_RANGE: "the sequence holds no item at this position",
    PointerReason.NO_NODE: "the token descends from no mapping or sequence of the document",
}


class FieldPathError(ValueError):
    """Report a text that is not a field path, with the reason and the offset of its defect."""

    def __init__(self, text: str, reason: FieldPathReason, offset: int) -> None:
        super().__init__(f"invalid field path {text!r} at offset {offset}: {MESSAGES[reason]}")
        self.text, self.reason, self.offset = text, reason, offset


class PointerError(ValueError):
    """Report a JSON Pointer that converts to no field path, with the reason and its offset."""

    def __init__(self, text: str, reason: PointerReason, offset: int) -> None:
        super().__init__(f"JSON Pointer {text!r} at offset {offset}: {MESSAGES[reason]}")
        self.text, self.reason, self.offset = text, reason, offset


def is_field_path(text: Any) -> bool:
    """Whether a value is a field path, as the definition ``field-path`` admits it."""
    return matches("field-path", text)


def is_field_path_pattern(text: Any) -> bool:
    """Whether a value is a field-path pattern, as the definition ``field-path-pattern`` admits it."""
    return matches("field-path-pattern", text)


def parse_field_path(text: str) -> FieldPath:
    """Return the segments of a field path.

    Raises
    ------
    FieldPathError
        If the text is not a field path, at the first defect from the left.

    Examples
    --------
    >>> parse_field_path('subject.foils[1].symbol')
    ('subject', 'foils', 1, 'symbol')
    >>> try:
    ...     parse_field_path('a[01]')
    ... except FieldPathError as error:
    ...     print(error.reason, error.offset)
    invalid-index 1
    """
    return tuple(segment for segment in _parse(text, False) if not isinstance(segment, Wildcard))


def parse_field_path_pattern(text: str) -> tuple[PatternSegment, ...]:
    """Return the segments of a field-path pattern, its wildcards included.

    Examples
    --------
    >>> parse_field_path_pattern('terms.*.label') == ('terms', ANY_KEY, 'label')
    True
    """
    return tuple(_parse(text, True))


def _parse(text: str, wildcards: bool) -> list[PatternSegment]:
    """Read the segments of a text from the left, failing at the first defect."""

    def fail(reason: FieldPathReason, at: int) -> NoReturn:
        raise FieldPathError(text, reason, at)

    segments: list[PatternSegment] = []
    index = 0
    while index < len(text):
        if text[index] == "[":
            close = _closing_bracket(text, index)
            if close < 0:
                fail(FieldPathReason.UNCLOSED_BRACKET, index)
            segments.append(_bracket(text, index, close, wildcards, fail))
            index = close + 1
            continue
        if index > 0:
            if text[index] != ".":
                fail(FieldPathReason.INVALID_CHARACTER, index)
            index += 1
        end = index
        while end < len(text) and is_field_path(text[end]):
            end += 1
        if end > index:
            segments.append(text[index:end])
        elif text[index : index + 1] == "*" and wildcards:
            segments.append(ANY_KEY)
            end += 1
        elif text[index : index + 1] == "*":
            fail(FieldPathReason.WILDCARD, index)
        elif text[index : index + 1] in ("", ".", "["):
            fail(FieldPathReason.EMPTY_KEY, index)
        else:
            fail(FieldPathReason.INVALID_CHARACTER, index)
        index = end
    return segments


def _closing_bracket(text: str, start: int) -> int:
    """Return the offset of the bracket closing the one at ``start``, skipping the content of a
    JSON string; -1 when none closes it."""
    quoted = False
    index = start + 1
    while index < len(text):
        char = text[index]
        if quoted and char == "\\":
            index += 1
        elif char == '"':
            quoted = not quoted
        elif char == "]" and not quoted:
            return index
        index += 1
    return -1


def _bracket(
    text: str,
    start: int,
    close: int,
    wildcards: bool,
    fail: Callable[[FieldPathReason, int], NoReturn],
) -> PatternSegment:
    """Return the segment of the bracket ``text[start:close + 1]``, or fail at its start."""
    content = text[start + 1 : close]
    if content == "*":
        if wildcards:
            return ANY_ITEM
        fail(FieldPathReason.WILDCARD, start)
    if is_field_path(f"[{content}]"):
        # Validated by the pattern: a JSON string or a canonical decimal.
        return str(json.loads(content)) if content.startswith('"') else int(content)
    if content.startswith('"'):
        fail(FieldPathReason.INVALID_QUOTED_KEY, start)
    if content[:1] and content[0] in "-0123456789":
        fail(FieldPathReason.INVALID_INDEX, start)
    fail(FieldPathReason.INVALID_BRACKET, start)


def print_field_path(segments: Iterable[PatternSegment]) -> str:
    """Return the canonical text of a field path or of a pattern: each key bare whenever a bare
    key can hold it, and quoted as a JSON string otherwise.

    Raises
    ------
    ValueError
        If a segment is neither a string, a position of the grammar nor a wildcard.

    Examples
    --------
    >>> print_field_path(('maturity', 'task.aim', 0, ''))
    'maturity["task.aim"][0][""]'
    >>> print_field_path(parse_field_path('["abc"].d'))
    'abc.d'
    """
    parts: list[str] = []
    for position, segment in enumerate(segments):
        if isinstance(segment, Wildcard):
            parts.append("." + segment.value if segment is ANY_KEY and position else segment.value)
        elif isinstance(segment, str):
            bare = "." not in segment and "[" not in segment and segment != ""
            if bare and is_field_path(segment):
                parts.append("." + segment if position else segment)
            else:
                parts.append(f"[{_quote(segment)}]")
        else:
            parts.append(f"[{_position(segment)}]")
    return "".join(parts)


def _quote(key: str) -> str:
    """Return a key as a JSON string: the escapes of JSON for the quote, the backslash and the
    controls, and each lone surrogate as an escape, every other character as itself."""
    text = json.dumps(key, ensure_ascii=False)
    return SURROGATE.sub(lambda found: chr(92) + f"u{ord(found.group()):04x}", text)


def _position(segment: Any) -> int:
    """Return a position of the grammar, or raise."""
    if isinstance(segment, bool) or not isinstance(segment, int) or not 0 <= segment < POSITIONS:
        raise ValueError(f"{segment!r} is no key and no position of a field path")
    return segment


def to_pointer(path: Sequence[Segment]) -> str:
    """Return the JSON Pointer of a field path, converted segment by segment.

    Examples
    --------
    >>> to_pointer(parse_field_path('relations[2].target'))
    '/relations/2/target'
    >>> to_pointer(('a/b', 'c~1d', ''))
    '/a~1b/c~01d/'
    """
    return pointer(*(key if isinstance(key, str) else _position(key) for key in path))


def pointer_tokens(text: str) -> tuple[str, ...]:
    """Return the tokens of a JSON Pointer, each unescaped: ``~1`` read as ``/``, then ``~0`` as
    ``~``.

    Raises
    ------
    PointerError
        If the text is neither empty nor opens on ``/``, or holds a ``~`` followed by neither ``0``
        nor ``1``.

    Examples
    --------
    >>> pointer_tokens('/a~1b/c~01d/')
    ('a/b', 'c~1d', '')
    """
    return tuple(token for _, token in _tokens(text))


def _tokens(text: str) -> list[tuple[int, str]]:
    """Return the tokens of a JSON Pointer, each with the offset of the slash opening it."""
    if text and not text.startswith("/"):
        raise PointerError(text, PointerReason.NOT_A_POINTER, 0)
    escape = re.search("~(?![01])", text)
    if escape is not None:
        raise PointerError(text, PointerReason.INVALID_ESCAPE, escape.start())
    tokens: list[tuple[int, str]] = []
    offset = 0
    for raw in text.split("/")[1:]:
        tokens.append((offset, raw.replace("~1", "/").replace("~0", "~")))
        offset += len(raw) + 1
    return tokens


def from_pointer(text: str, document: Any) -> FieldPath:
    """Return the field path of a JSON Pointer within a document.

    A token is a position exactly when its parent node is a sequence, and it then names
    an item of that sequence in canonical decimal. A token below a mapping is a key, present or
    absent. A token descending from an absent key or from a scalar fails, since its node, and thus
    its kind, is unknown.

    Raises
    ------
    PointerError
        If the text is no JSON Pointer, holds an invalid escape, or names a position or a node that
        the document does not hold, at the offset of the escape or of the slash opening the token.

    Examples
    --------
    >>> from_pointer('/items/0', {'items': ['x']}), from_pointer('/items/0', {'items': {'0': 'x'}})
    (('items', 0), ('items', '0'))
    >>> from_pointer('/identity/id', {'identity': {}})
    ('identity', 'id')
    """
    path: list[Segment] = []
    node, present = document, True
    for offset, token in _tokens(text):
        if not present or not isinstance(node, (Mapping, list)):
            raise PointerError(text, PointerReason.NO_NODE, offset)
        if isinstance(node, list):
            if not DECIMAL.fullmatch(token):
                raise PointerError(text, PointerReason.INVALID_INDEX, offset)
            if int(token) >= len(node):
                raise PointerError(text, PointerReason.INDEX_OUT_OF_RANGE, offset)
            path.append(int(token))
            node = node[int(token)]
        else:
            path.append(token)
            present, node = token in node, node.get(token)
    return tuple(path)


def match_nodes(pattern: Sequence[PatternSegment], document: Any) -> list[tuple[FieldPath, Any]]:
    """Return each node of a document that a pattern names, with its field path, in document order.

    A key names the value of a mapping holding it, a position the item of a sequence holding it,
    ``*`` every value of a mapping under a string key, and ``[*]`` every item of a sequence.

    Examples
    --------
    >>> match_nodes(parse_field_path_pattern('a[*]'), {'a': ['x', 'y']})
    [(('a', 0), 'x'), (('a', 1), 'y')]
    """
    found: list[tuple[FieldPath, Any]] = [((), document)]
    for segment in pattern:
        below: list[tuple[FieldPath, Any]] = []
        for path, node in found:
            if isinstance(node, list) and segment is ANY_ITEM:
                below.extend(((*path, index), item) for index, item in enumerate(node))
            elif isinstance(node, Mapping) and segment is ANY_KEY:
                below.extend(
                    ((*path, key), item) for key, item in node.items() if isinstance(key, str)
                )
            elif isinstance(node, list) and _is_position(segment) and 0 <= segment < len(node):
                below.append(((*path, segment), node[segment]))
            elif isinstance(node, Mapping) and isinstance(segment, str) and segment in node:
                below.append(((*path, segment), node[segment]))
        found = below
    return found


def _is_position(segment: Any) -> TypeGuard[int]:
    """Whether a segment is a position, a boolean excluded."""
    return isinstance(segment, int) and not isinstance(segment, bool)


def expand(pattern: Sequence[PatternSegment], document: Any) -> list[FieldPath]:
    """Return the field paths of the nodes of a document that a pattern names, in document order.

    Examples
    --------
    >>> document = {'subject': {'foils': [{'symbol': 'L'}, {'symbol': 'G'}]}}
    >>> [print_field_path(path) for path in expand(
    ...     parse_field_path_pattern('subject.foils[*].symbol'), document)]
    ['subject.foils[0].symbol', 'subject.foils[1].symbol']
    """
    return [path for path, _ in match_nodes(pattern, document)]
