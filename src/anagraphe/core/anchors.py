"""Block anchors: the caret tokens ``^name`` closing a line, cited by a fragment ``#^name``."""

from __future__ import annotations

import re

#: A block anchor closing a line, after a space or a line break, with its name as its group.
BLOCK_ANCHOR = re.compile(r"(?:^|\s)\^([A-Za-z0-9][A-Za-z0-9_-]*)\s*$", re.MULTILINE)


def has_block_anchor(text: str, name: str) -> bool:
    """Whether a line of a text closes on the block anchor of a name, after a space or a line break.

    Examples
    --------
    >>> has_block_anchor("A claim. ^claim\\n", "claim"), has_block_anchor("| a |\\n^table", "table")
    (True, True)
    >>> has_block_anchor("A claim ^claim-long", "claim"), has_block_anchor("x^claim", "claim")
    (False, False)
    """
    return re.search(rf"(?:^|\s)\^{re.escape(name)}\s*$", text, re.MULTILINE) is not None


def block_anchors(text: str) -> list[str]:
    """Return the name of each block anchor of a text, in its order, a repeated name repeated.

    Examples
    --------
    >>> block_anchors("A claim. ^claim\\n| a |\\n^table\\nAgain. ^claim\\nx^not\\n")
    ['claim', 'table', 'claim']
    """
    return BLOCK_ANCHOR.findall(text)
