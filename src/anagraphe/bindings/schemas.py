"""
The fields of a record that bind it, as the schema of its contract marks them by ``x-binds``.

The keyword ``x-binds`` sits on a property of the schema and names the role that the property binds,
such as ``onomasia.glossary``. The marks are read by the walk of :mod:`anagraphe.core.schemas`,
through ``properties``, whose names form the key path of a field, the subschemas of ``allOf``,
``anyOf`` and ``oneOf``, and every ``$ref``. A mark reached under another applicator, ``items``
included, is reported, since its field has no single key path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Mapping

from anagraphe.bindings.kinds import INVALID_MARK
from anagraphe.bindings.model import ROLE_PATTERN
from anagraphe.core.issues import pointer
from anagraphe.core.schemas import (
    Property,
    SchemaNode,
    SchemaProblem,
    SchemaReader,
    parse_document,
)

__all__ = ["KEYWORD", "SchemaBindings", "parse_document"]

#: The keyword marking a property that binds its record.
KEYWORD = "x-binds"


@dataclass
class SchemaBindings:
    """The binding fields of each contract of a registry, read from its schemas once."""

    root: Path
    registry: Path
    reader: SchemaReader = field(init=False)
    _marks: list[SchemaProblem] = field(default_factory=list, init=False)
    _fields: dict[str, dict[str, tuple[tuple[str, ...], ...]]] = field(
        default_factory=dict, init=False
    )

    def __post_init__(self) -> None:
        self.reader = SchemaReader(self.root, self.registry)

    @property
    def problems(self) -> list[SchemaProblem]:
        """Return the defects of the schemas met so far: the unreadable schemas and references,
        then the invalid marks."""
        return [*self.reader.problems, *self._marks]

    def contracts(self) -> tuple[str, ...]:
        """Return the contracts of the registry, in sorted order."""
        return self.reader.contracts()

    def fields(self, contract: str) -> Mapping[str, tuple[tuple[str, ...], ...]] | None:
        """Return the key paths binding each role in the records of a contract, in the order of the
        schema; None when the registry holds no such contract."""
        if contract not in self.reader.contracts():
            return None
        if contract not in self._fields:
            found: dict[str, list[tuple[str, ...]]] = {}
            start = self.reader.root_of(contract)
            for node in self.reader.walk(start) if start is not None else ():
                if KEYWORD in node.value:
                    for role, path in self._mark(node):
                        if path not in found.setdefault(role, []):
                            found[role].append(path)
            self._fields[contract] = {role: tuple(paths) for role, paths in found.items()}
        return self._fields[contract]

    def _mark(self, node: SchemaNode) -> Iterator[tuple[str, tuple[str, ...]]]:
        """Yield the role and the key path of a valid mark, or record why the mark is invalid."""
        role: Any = node.value[KEYWORD]
        if not isinstance(role, str) or not ROLE_PATTERN.fullmatch(role):
            detail = f"{KEYWORD} must name a role as <tool>.<name>"
        elif node.under is not None or node.path is None:
            detail = f"{KEYWORD} sits under {node.under}, where a field has no single key path"
        elif not node.path:
            detail = f"{KEYWORD} marks a property, not a whole record"
        else:
            yield role, tuple(step.name for step in node.path if isinstance(step, Property))
            return
        problem = SchemaProblem(INVALID_MARK, node.rel, node.at + pointer(KEYWORD), detail)
        if problem not in self._marks:
            self._marks.append(problem)
