"""Block anchors: the caret tokens ``^name`` closing a line, cited by a fragment ``#^name``."""

from __future__ import annotations

import re

from anagraphe_read._core.published import body

#: A block anchor closing a line, after a space or a line break, with its name as its group. The
#: name is a unit identifier, so its characters are those of the pattern ``unit-id`` of the
#: resource of the addressing.
BLOCK_ANCHOR = re.compile(rf"(?:^|\s)\^({body('unit-id')})\s*$", re.MULTILINE)


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
