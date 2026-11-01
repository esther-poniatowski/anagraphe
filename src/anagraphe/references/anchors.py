"""Block anchors: the caret tokens ``^name`` closing a line, cited by a fragment ``#^name``."""

from __future__ import annotations

import re


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
