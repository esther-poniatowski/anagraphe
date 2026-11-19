"""The position in its file of a node of a record, given by its positional path.

A reader that reports a finding on a node of a record, such as the validator of a schema, names the
node by its keys and indexes from the root of the data of the record. This module finds where that
node is written: in the frontmatter of a note, or in a YAML or JSON document.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import yaml

from anagraphe_read._targets.records import NOTE_SUFFIX

#: The opening fence of a frontmatter, on the first line of a note.
_FENCE = "---\n"


def _root_node(rel: str, text: str) -> tuple[yaml.Node | None, int]:
    """Return the composed node of the data of a record, and the line on which its text opens."""
    offset = 0
    if rel.endswith(NOTE_SUFFIX):
        if not text.startswith(_FENCE):
            return None, 0
        end = text.find("\n---", len(_FENCE) - 1)
        if end == -1:
            return None, 0
        text, offset = text[len(_FENCE) : end + 1], 1
    try:
        return yaml.compose(text, Loader=yaml.SafeLoader), offset
    except yaml.YAMLError:
        return None, 0


def _child(node: yaml.Node, step: str | int) -> yaml.Node | None:
    """Return the node of a mapping under a key, or of a sequence at an index, None when absent."""
    if isinstance(node, yaml.MappingNode):
        return next(
            (
                value
                for key, value in node.value
                if isinstance(key, yaml.ScalarNode) and key.value == str(step)
            ),
            None,
        )
    if (
        isinstance(node, yaml.SequenceNode)
        and isinstance(step, int)
        and 0 <= step < len(node.value)
    ):
        child: yaml.Node = node.value[step]
        return child
    return None


def position(root: Path, rel: str, path: Sequence[str | int]) -> tuple[int, int] | None:
    """Return the line and the column, from 1, where the node at ``path`` of a record opens.

    A step that leaves the data, such as the name of a missing field, stops the search at the
    closest existing ancestor. The data of the record as a whole, and a file that cannot be read or
    composed, have no position.

    Examples
    --------
    >>> import tempfile
    >>> folder = Path(tempfile.mkdtemp())
    >>> _ = (folder / "a.yml").write_text("name: x\\nitems:\\n  - id: p\\n")
    >>> position(folder, "a.yml", ["items", 0, "id"]), position(folder, "a.yml", ["items", 0, "x"])
    ((3, 9), (3, 5))
    >>> _ = (folder / "n.md").write_text("---\\ntitle: t\\n---\\nbody\\n")
    >>> position(folder, "n.md", ["title"]), position(folder, "n.md", [])
    ((2, 8), None)
    """
    try:
        text = (root / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    node, offset = _root_node(rel, text)
    if node is None:
        return None
    reached = node
    for step in path:
        child = _child(reached, step)
        if child is None:
            break
        reached = child
    if reached is node:
        return None
    return reached.start_mark.line + 1 + offset, reached.start_mark.column + 1
