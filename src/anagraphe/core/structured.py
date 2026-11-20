"""
Edits of a YAML text at the exact characters of one node, without serializing the text again.

A move replaces a value, or removes the item of a list, in a frontmatter or a record; a rename of a
repository also adds an item to a list, or a key to a mapping. Writing the parsed data back would
drop the comments, the quoting and the order of the keys, so the edits replace or insert characters
located by the marks of the parser instead. An insertion takes the style of its collection: a flow
collection gains an item after a comma, and a block collection gains a line at the indentation of
its first entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import yaml

#: The characters that open a scalar with a meaning other than a plain string.
INDICATORS = frozenset("[]{},&*!|>'\"%@`#?:-")
#: The opening line of a frontmatter, and the token closing it.
FRONTMATTER_OPENING = "---\n"
FRONTMATTER_CLOSING = "\n---"


@dataclass(frozen=True)
class Edit:
    """The replacement of the characters ``text[start:end]`` by a new text."""

    start: int
    end: int
    new: str


def apply_edits(text: str, edits: Sequence[Edit]) -> str:
    """Return a text with its edits applied, from the last position to the first.

    Edits applied in ascending order would shift the positions of every later edit, so they are
    applied from the end. Two overlapping edits raise a ``ValueError``.

    Examples
    --------
    >>> apply_edits("a b c", [Edit(0, 1, "x"), Edit(4, 5, "zz")])
    'x b zz'
    """
    ordered = sorted(edits, key=lambda edit: (edit.start, edit.end))
    for before, after in zip(ordered, ordered[1:]):
        if after.start < before.end:
            raise ValueError(f"overlapping edits at {before.start} and {after.start}")
    for edit in reversed(ordered):
        text = text[: edit.start] + edit.new + text[edit.end :]
    return text


def compose(text: str) -> yaml.Node | None:
    """Return the node tree of one YAML document, None when the text holds no document."""
    node: yaml.Node | None = yaml.compose(text, Loader=yaml.SafeLoader)
    return node


def frontmatter_span(text: str) -> tuple[int, int] | None:
    """Return the start and the end of the YAML block of a frontmatter, None when the text opens
    on no frontmatter closed by ``---``.

    Examples
    --------
    >>> text = "---\\nid: a\\n---\\n# A\\n"
    >>> start, end = frontmatter_span(text)
    >>> text[start:end]
    'id: a'
    >>> frontmatter_span("# No frontmatter\\n") is None
    True
    """
    if not text.startswith(FRONTMATTER_OPENING):
        return None
    end = text.find(FRONTMATTER_CLOSING, len(FRONTMATTER_OPENING))
    if end == -1:
        return None
    return len(FRONTMATTER_OPENING), end


def node_at(root: yaml.Node | None, keys: Sequence[str | int]) -> yaml.Node | None:
    """Return the node reached by a path of keys, each a key of a mapping or the index of an item
    of a sequence; None when a step is absent.

    Examples
    --------
    >>> node = node_at(compose("metadata:\\n  index: '[I](a.md)'\\n"), ["metadata", "index"])
    >>> node.value, node.start_mark.line
    ('[I](a.md)', 1)
    >>> node_at(compose("items: [{id: a}, {id: b}]\\n"), ["items", 1, "id"]).value
    'b'
    """
    node = root
    for key in keys:
        if isinstance(key, int):
            if not isinstance(node, yaml.SequenceNode) or not 0 <= key < len(node.value):
                return None
            node = node.value[key]
            continue
        if not isinstance(node, yaml.MappingNode):
            return None
        node = next(
            (
                value
                for name, value in node.value
                if isinstance(name, yaml.ScalarNode) and name.value == key
            ),
            None,
        )
    return node


def quoted(value: str, style: str | None) -> str:
    """Return a string scalar in the quoting style of the scalar that it replaces.

    A plain scalar is written with double quotes when the value would otherwise read as another
    type or as a mapping, as a link opening on ``[`` would.

    Examples
    --------
    >>> quoted("[I](a.md)", None), quoted("it's", "'"), quoted('a "b"', '"')
    ('"[I](a.md)"', "'it''s'", '"a \\\\"b\\\\""')
    """
    if style == "'":
        return "'" + value.replace("'", "''") + "'"
    if style == '"' or not _plain(value):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _plain(value: str) -> bool:
    """Whether a value reads back as the same string when written as a plain scalar."""
    if not value or value[:1] in INDICATORS or ": " in value or " #" in value:
        return False
    try:
        return bool(yaml.safe_load(value) == value)
    except (yaml.YAMLError, ValueError):
        # A value reading as an impossible date, such as 2026-02-30, raises a ValueError.
        return False


def replace_scalar(node: yaml.ScalarNode, value: str, offset: int = 0) -> Edit:
    """Return the edit replacing a scalar by a string value, in its quoting style.

    The offset locates the parsed text in a larger text, such as a frontmatter in its note.
    """
    return Edit(
        offset + node.start_mark.index,
        offset + node.end_mark.index,
        quoted(value, node.style if node.style in ("'", '"') else None),
    )


def remove_item(text: str, sequence: yaml.SequenceNode, item: yaml.Node, offset: int = 0) -> Edit:
    """Return the edit removing one item of a sequence, with its separator.

    A block item is removed with its whole line. A flow item is removed with the comma that
    separates it from its neighbour.

    Examples
    --------
    >>> text = "a: [x, y, z]\\nb:\\n  - x\\n  - y\\n"
    >>> root = compose(text)
    >>> flow, block = node_at(root, ["a"]), node_at(root, ["b"])
    >>> apply_edits(text, [remove_item(text, flow, flow.value[1]), remove_item(text, block, block.value[0])])
    'a: [x, z]\\nb:\\n  - y\\n'
    """
    start, end = item.start_mark.index, item.end_mark.index
    if not sequence.flow_style:
        line_start = text.rfind("\n", 0, start) + 1
        line_end = text.find("\n", end)
        return Edit(
            offset + line_start, offset + (len(text) if line_end == -1 else line_end + 1), ""
        )
    after = text[end : sequence.end_mark.index]
    comma = after.find(",")
    if comma != -1:
        following = end + comma + 1
        while following < len(text) and text[following] == " ":
            following += 1
        return Edit(offset + start, offset + following, "")
    before = text[sequence.start_mark.index : start]
    comma = before.rfind(",")
    if comma == -1:
        return Edit(offset + start, offset + end, "")
    return Edit(offset + sequence.start_mark.index + comma, offset + end, "")


def append_item(text: str, sequence: yaml.SequenceNode, value: str, offset: int = 0) -> Edit:
    """Return the edit appending a string item to a sequence, in the style of the sequence.

    A flow sequence gains the item before its closing bracket. A block sequence gains a line
    after the line of its last item, at the indentation of its first dash.

    Examples
    --------
    >>> text = "a: [x]\\nb: []\\nc:\\n  - x  # kept\\n"
    >>> root = compose(text)
    >>> edits = [append_item(text, node_at(root, [key]), "y") for key in ("a", "b", "c")]
    >>> print(apply_edits(text, edits), end="")
    a: [x, y]
    b: [y]
    c:
      - x  # kept
      - y
    """
    written = quoted(value, None)
    items = sequence.value
    if sequence.flow_style:
        if not items:
            return _insert(offset + sequence.end_mark.index - 1, written)
        return _insert(offset + items[-1].end_mark.index, f", {written}")
    line = " " * sequence.start_mark.column + f"- {written}"
    return _line_after(text, items[-1].end_mark.index, line, offset)


def add_entry(text: str, mapping: yaml.MappingNode, key: str, value: str, offset: int = 0) -> Edit:
    """Return the edit adding the entry ``key: value`` to a mapping, in the style of the mapping.

    The value is written as given, such as a flow collection. A flow mapping gains the entry before
    its closing brace. A block mapping gains a line after the line of its last value, at the
    indentation of its first key.

    Examples
    --------
    >>> text = "a: {x: 1}\\nb:\\n  x: 1\\n"
    >>> root = compose(text)
    >>> edits = [add_entry(text, node_at(root, [name]), "y", "[2]") for name in ("a", "b")]
    >>> print(apply_edits(text, edits), end="")
    a: {x: 1, y: [2]}
    b:
      x: 1
      y: [2]
    """
    entries = mapping.value
    entry = f"{quoted(key, None)}: {value}"
    if mapping.flow_style:
        if not entries:
            return _insert(offset + mapping.end_mark.index - 1, entry)
        return _insert(offset + entries[-1][1].end_mark.index, f", {entry}")
    line = " " * entries[0][0].start_mark.column + entry
    return _line_after(text, entries[-1][1].end_mark.index, line, offset)


def _insert(position: int, new: str) -> Edit:
    """Return the edit inserting a text at a position."""
    return Edit(position, position, new)


def _line_after(text: str, index: int, line: str, offset: int) -> Edit:
    """Return the edit inserting a line after the line holding ``index``, or at ``index`` when it
    opens a line, with the line breaks of the text.

    A block collection ends where the next line opens, and a scalar ends inside its line, before a
    comment that the line keeps.
    """
    newline = "\r\n" if "\r\n" in text else "\n"
    if index > 0 and text[index - 1] == "\n":
        return _insert(offset + index, line + newline)
    end = text.find("\n", index)
    if end == -1:
        return _insert(offset + len(text), newline + line)
    if end > 0 and text[end - 1] == "\r":
        end -= 1
    return _insert(offset + end, newline + line)
