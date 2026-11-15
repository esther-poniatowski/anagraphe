"""
The reading of a JSON text under RFC 8259.

The module ``json`` of Python also reads the constants ``NaN``, ``Infinity`` and ``-Infinity``,
which RFC 8259 excludes and ``JSON.parse`` rejects. Every JSON read of Anagraphe goes through
:func:`load_json`, so the Python and TypeScript read sides read the same texts as JSON.
"""

from __future__ import annotations

import json
from typing import Any, NoReturn


def load_json(text: str) -> Any:
    """Return the value of a JSON text.

    Raises
    ------
    ValueError
        If the text is not JSON under RFC 8259, including a text holding ``NaN`` or ``Infinity``.

    Examples
    --------
    >>> load_json('{"a": [1, 2.5]}')
    {'a': [1, 2.5]}
    >>> load_json('{"a": NaN}')
    Traceback (most recent call last):
    ...
    ValueError: the constant NaN is not JSON under RFC 8259
    """
    return json.loads(text, parse_constant=_reject)


def _reject(name: str) -> NoReturn:
    """Refuse a constant that RFC 8259 excludes."""
    raise ValueError(f"the constant {name} is not JSON under RFC 8259")
