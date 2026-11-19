"""
Filters on the metadata of a file: the ``where`` of a group, and the ``where`` of an exclusion.

A filter maps each key to one admitted value or to a list of admitted values. A file matches when
every key holds an admitted value, and a key holding a list matches when the list holds one. Values
compare as text, booleans in lowercase, so ``archived: false`` matches the value ``false``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


def scalar(value: Any) -> str:
    """Return a metadata value in the form that a filter compares, booleans in lowercase."""
    if isinstance(value, bool):
        return str(value).lower()
    return "" if value is None else str(value)


def scalars(value: Any) -> tuple[str, ...]:
    """Return the values that a filter compares: each element of a list, else the value itself.

    Examples
    --------
    >>> scalars(["x", True]), scalars(None)
    (('x', 'true'), ('',))
    """
    return tuple(scalar(item) for item in value) if isinstance(value, list) else (scalar(value),)


@dataclass(frozen=True)
class Filter:
    """The admitted values of each key of a filter.

    Examples
    --------
    >>> archived = Filter((("status", ("archived",)),))
    >>> archived.selects({"status": "archived"}), archived.selects({"status": "wip"})
    (True, False)
    >>> Filter((("tags", ("x",)), ("draft", ("false",)))).selects({"tags": ["y", "x"], "draft": False})
    True
    """

    conditions: tuple[tuple[str, tuple[str, ...]], ...] = ()

    def selects(self, data: Mapping[str, Any]) -> bool:
        """Whether the metadata of a file holds an admitted value of every key."""
        return bool(self.conditions) and all(
            any(item in values for item in scalars(data.get(key)))
            for key, values in self.conditions
        )


def parse_filter(value: Any) -> tuple[Filter, list[str]]:
    """Parse a filter written as a mapping from keys to a value or a list of values.

    Examples
    --------
    >>> parse_filter({"role": ["audit", "decision"]})
    (Filter(conditions=(('role', ('audit', 'decision')),)), [])
    >>> parse_filter(["role"])[1], parse_filter({})[1]
    (['must map keys to values'], ['must name at least one key'])
    """
    if not isinstance(value, Mapping):
        return Filter(), ["must map keys to values"]
    if not value:
        return Filter(), ["must name at least one key"]
    return (
        Filter(
            tuple(
                (
                    str(key),
                    tuple(
                        scalar(item) for item in (values if isinstance(values, list) else [values])
                    ),
                )
                for key, values in value.items()
            )
        ),
        [],
    )
