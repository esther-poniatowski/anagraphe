"""
The declarations that the schema of a contract makes for the logical targets.

The walk of :mod:`anagraphe_read._core.schemas` reads five keywords on the nodes of the schema, each node
taken with the key path of the values that it describes:

- ``x-identifier`` on a node of the root, reached through ``allOf`` and ``$ref``, names the field
  holding the identifier of the record, as a dotted path of property names;
- ``x-identifier`` on a definition reached as the items of an array names the field holding the
  identifier of each item, and makes each item a unit of the record;
- a ``$ref`` equal to the URI of the definition ``target`` makes its value a target field, and
  ``x-target-contract`` on a node of the same key path lists the contracts that its record must
  satisfy;
- ``x-implements`` on a node of the root names the contracts that the records of the contract also
  implement;
- ``x-units`` on a node lists the field paths, from the root of the record, of the arrays whose
  units its values name, each array holding items that ``x-identifier`` declares as units.

A node reached through ``anyOf`` or ``oneOf`` describes only the values matching its branch. Its
``x-identifier`` is therefore not read, and a value of its target field is read as a target only
when the value is a mapping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from anagraphe_read._core.issues import pointer
from anagraphe_read._core.schemas import (
    Items,
    Property,
    SchemaNode,
    SchemaProblem,
    SchemaReader,
    Step,
)
from anagraphe_read._targets.field_paths import FieldPath, FieldPathError, parse_field_path
from anagraphe_read._targets.kinds import (
    INVALID_IDENTIFIER_DECLARATION,
    INVALID_TARGET_CONTRACT,
    INVALID_UNITS_DECLARATION,
)
from anagraphe_read._targets.model import parse_contracts
from anagraphe_read._targets.resource import ADDRESSING_ID, TARGET_REFERENCE, matches

#: The keyword naming the field of an identifier.
IDENTIFIER = "x-identifier"
#: The keyword typing a target field by the contracts of its record.
TARGET_CONTRACT = "x-target-contract"
#: The keyword naming the contracts that a root schema implements.
IMPLEMENTS = "x-implements"
#: The keyword naming the arrays of units of the same record that the values of a field name.
UNITS = "x-units"


@dataclass(frozen=True)
class TargetField:
    """A field of a record whose values are logical targets."""

    path: tuple[Step, ...]
    #: Whether every node reaching the definition does so through ``anyOf`` or ``oneOf``, so that a
    #: value is a target only when it is a mapping.
    conditional: bool
    #: The valid declarations of ``x-target-contract`` at the key path of the field; the record of
    #: a target satisfies each of them.
    contracts: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class UnitDeclaration:
    """The items of an array of a record that form its units, with the field of their identifier."""

    #: The key path of the items, its last step naming every item.
    path: tuple[Step, ...]
    identifier: tuple[str, ...]


@dataclass(frozen=True)
class UnitList:
    """An array of units of a record, named by an entry of ``x-units``."""

    #: The entry as written, a field path from the root of the record.
    text: str
    path: FieldPath
    #: The field of the identifier of each item, from its declaration of units.
    identifier: tuple[str, ...]


@dataclass(frozen=True)
class UnitReference:
    """A field of a record whose values name units of the same record, in the arrays of one
    declaration of ``x-units``."""

    path: tuple[Step, ...]
    lists: tuple[UnitList, ...]


@dataclass(frozen=True)
class ContractSchema:
    """What the schema of one contract declares for the targets."""

    contract: str
    #: The field of the identifier of a record; None when the schema declares none, so that the
    #: default applies.
    identifier: tuple[str, ...] | None = None
    units: tuple[UnitDeclaration, ...] = ()
    targets: tuple[TargetField, ...] = ()
    #: The contracts named by ``x-implements`` at the root.
    implements: tuple[str, ...] = ()
    #: The fields declaring ``x-units``, one entry per valid declaration; a value of the field
    #: names a unit of the arrays of each of its declarations.
    references: tuple[UnitReference, ...] = ()


@dataclass
class Declarations:
    """The declarations of each contract of a registry, read from its schema once.

    The invalid declarations met are recorded under :attr:`problems`, each once.
    """

    reader: SchemaReader
    problems: list[SchemaProblem] = field(default_factory=list, init=False)
    _schemas: dict[str, ContractSchema | None] = field(default_factory=dict, init=False)

    def of(self, contract: str) -> ContractSchema | None:
        """Return the declarations of a contract, None when the registry holds no readable schema
        for it."""
        if contract not in self._schemas:
            start = self.reader.root_of(contract)
            self._schemas[contract] = None if start is None else self._read(contract, start)
        return self._schemas[contract]

    def _read(self, contract: str, start: SchemaNode) -> ContractSchema:
        """Read the declarations of a contract from the nodes of its schema."""
        nodes = [
            node
            for node in self.reader.walk(start, opaque=frozenset({ADDRESSING_ID}))
            if node.path is not None
        ]
        paths = {node.path for node in nodes}
        identifier: tuple[str, ...] | None = None
        units: dict[UnitDeclaration, None] = {}
        targets: dict[tuple[Step, ...], bool] = {}
        contracts: dict[tuple[Step, ...], list[tuple[str, ...]]] = {}
        implements: dict[str, None] = {}
        referencing: list[SchemaNode] = []
        for node in nodes:
            assert node.path is not None
            value = node.value
            if IDENTIFIER in value and not node.conditional:
                if not node.path or isinstance(node.path[-1], Items):
                    segments = self._identifier(node, paths)
                    if segments is not None and not node.path:
                        identifier = identifier or segments
                    elif segments is not None:
                        units[UnitDeclaration(node.path, segments)] = None
            if TARGET_CONTRACT in value:
                entries = self._contracts(node)
                if entries is not None and entries not in contracts.setdefault(node.path, []):
                    contracts[node.path].append(entries)
            if value.get("$ref") == TARGET_REFERENCE:
                targets[node.path] = targets.get(node.path, True) and node.conditional
            if IMPLEMENTS in value and not node.path and not node.conditional:
                implements.update(dict.fromkeys(_names(value[IMPLEMENTS])))
            if UNITS in value:
                referencing.append(node)
        references: dict[UnitReference, None] = {}
        for node in referencing:
            lists = self._unit_lists(node, {unit.path: unit.identifier for unit in units})
            if lists is not None:
                assert node.path is not None
                references[UnitReference(node.path, lists)] = None
        return ContractSchema(
            contract,
            identifier,
            tuple(units),
            tuple(
                TargetField(path, conditional, tuple(contracts.get(path, ())))
                for path, conditional in targets.items()
            ),
            tuple(implements),
            tuple(references),
        )

    def _identifier(
        self, node: SchemaNode, paths: set[tuple[Step, ...] | None]
    ) -> tuple[str, ...] | None:
        """Return the field named by the ``x-identifier`` of a node, None after recording why the
        declaration is invalid."""
        value: Any = node.value[IDENTIFIER]
        at = node.at + pointer(IDENTIFIER)
        if not matches("property-path", value):
            self._problem(
                INVALID_IDENTIFIER_DECLARATION,
                node,
                at,
                f"{IDENTIFIER} {value!r} is not a dotted path of property names, such as "
                "identity.id",
            )
            return None
        segments = tuple(value.split("."))
        assert node.path is not None
        if (*node.path, *(Property(name) for name in segments)) not in paths:
            self._problem(
                INVALID_IDENTIFIER_DECLARATION,
                node,
                at,
                f"{IDENTIFIER} {value} names no property of its schema",
            )
            return None
        return segments

    def _unit_lists(
        self, node: SchemaNode, units: dict[tuple[Step, ...], tuple[str, ...]]
    ) -> tuple[UnitList, ...] | None:
        """Return the arrays of units named by the ``x-units`` of a node, None after recording why
        the declaration is invalid.

        Each entry is a field path from the root of the record. A key of the path steps into a
        property, and a position into the items of an array, so the path names the array whose
        items a declaration of units covers.
        """
        value: Any = node.value[UNITS]
        at = node.at + pointer(UNITS)
        if not isinstance(value, list) or not value:
            self._problem(
                INVALID_UNITS_DECLARATION,
                node,
                at,
                f"{UNITS} must be a non-empty list of field paths, not {value!r}",
            )
            return None
        lists: list[UnitList] = []
        for entry in value:
            try:
                path = parse_field_path(entry) if isinstance(entry, str) else None
            except FieldPathError as error:
                self._problem(
                    INVALID_UNITS_DECLARATION, node, at, f"{UNITS} entry {entry!r}: {error}"
                )
                return None
            if path is None:
                self._problem(
                    INVALID_UNITS_DECLARATION,
                    node,
                    at,
                    f"{UNITS} entry {entry!r} is not a field path",
                )
                return None
            steps = tuple(Items() if isinstance(part, int) else Property(part) for part in path)
            identifier = units.get((*steps, Items()))
            if identifier is None:
                self._problem(
                    INVALID_UNITS_DECLARATION,
                    node,
                    at,
                    f"{UNITS} entry {entry} names no array of the record whose items declare "
                    f"{IDENTIFIER}",
                )
                return None
            lists.append(UnitList(entry, path, identifier))
        return tuple(lists)

    def _contracts(self, node: SchemaNode) -> tuple[str, ...] | None:
        """Return the entries of the ``x-target-contract`` of a node, None after recording why the
        declaration is invalid."""
        try:
            return parse_contracts(node.value[TARGET_CONTRACT])
        except ValueError as error:
            self._problem(
                INVALID_TARGET_CONTRACT, node, node.at + pointer(TARGET_CONTRACT), str(error)
            )
            return None

    def _problem(self, kind: str, node: SchemaNode, at: str, detail: str) -> None:
        """Record an invalid declaration, once."""
        problem = SchemaProblem(kind, node.rel, at, detail)
        if problem not in self.problems:
            self.problems.append(problem)


def _names(value: Any) -> tuple[str, ...]:
    """Return the contracts named by ``x-implements``: a string, or a list of strings."""
    items = [value] if isinstance(value, str) else value if isinstance(value, list) else []
    return tuple(item for item in items if isinstance(item, str))
