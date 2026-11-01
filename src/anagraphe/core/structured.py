"""
Edits of a YAML text at the exact characters of one node, without serializing the text again.

A move replaces a value, or removes the item of a list, in a frontmatter or a record. Writing the
parsed data back would drop the comments, the quoting and the order of the keys, so the edits
replace characters located by the marks of the parser instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import yaml

#: The characters that open a scalar with a meaning other than a plain string.
INDICATORS = frozenset("[]{},&*!|>'\"%@`#?:-")


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


def node_at(root: yaml.Node | None, keys: Sequence[str]) -> yaml.Node | None:
    """Return the node reached from a mapping by a path of keys, None when a key is absent.

    Examples
    --------
    >>> node = node_at(compose("metadata:\\n  index: '[I](a.md)'\\n"), ["metadata", "index"])
    >>> node.value, node.start_mark.line
    ('[I](a.md)', 1)
    """
    node = root
    for key in keys:
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
    except yaml.YAMLError:
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
