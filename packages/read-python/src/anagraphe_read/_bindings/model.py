"""
The roles that a tool reads in the bindings of a text, and the bindings resolved for them.

A role names what a tool reads, such as the glossary of a text, as ``<tool>.<name>``, so that two
tools never claim one role. The tool declares the merge rule of its role: ``override`` keeps the
declaration nearest to the text, and ``union`` joins the values of every declaration, from the root
down to the text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

#: The form of a role: the name of its tool, a period, and the name of the role in that tool.
ROLE_PATTERN = re.compile(r"^[a-z][a-z0-9-]*\.[a-z][a-z0-9-]*$")


class Merge(StrEnum):
    """How the declarations of one role along the directory chain combine."""

    #: The declaration nearest to the text replaces every farther one.
    OVERRIDE = "override"
    #: The values of every declaration join, from the root down to the text, each value once.
    UNION = "union"


@dataclass(frozen=True)
class Role:
    """A role read by a tool, with its merge rule.

    Examples
    --------
    >>> Role("onomasia.glossary").merge
    <Merge.OVERRIDE: 'override'>
    >>> Role("glossary")
    Traceback (most recent call last):
    ...
    ValueError: a role is written <tool>.<name>, such as onomasia.glossary: glossary
    """

    name: str
    merge: Merge = Merge.OVERRIDE

    def __post_init__(self) -> None:
        if not ROLE_PATTERN.fullmatch(self.name):
            raise ValueError(
                f"a role is written <tool>.<name>, such as onomasia.glossary: {self.name}"
            )


@dataclass(frozen=True)
class Declaration:
    """The values that one file declares for a role, at a key path of that file."""

    #: The repository-relative path of the declaring file.
    rel: str
    #: The JSON Pointer of the declaring key in the metadata or the record of the file.
    pointer: str
    values: tuple[str, ...]


@dataclass(frozen=True)
class Binding:
    """The values bound to a text for a role, with the declarations that supply them."""

    role: Role
    values: tuple[str, ...]
    #: The declarations that supply the values: the nearest one under ``override``, every one from
    #: the root down to the text under ``union``; empty for an unbound text.
    declarations: tuple[Declaration, ...]

    @property
    def bound(self) -> bool:
        """Whether the text is bound to at least one value."""
        return bool(self.values)
