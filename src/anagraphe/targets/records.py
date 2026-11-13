"""
The records of a repository as targets: the identifier of each record and the units inside it.

A record is a Markdown note, read through its frontmatter, or a YAML or JSON document. The schema
of its contract, named under its binding key, may declare the field of its identifier by
``x-identifier``. Without that declaration, the identifier of a record is the key ``id`` of its
metadata source: the frontmatter of a note, or the block ``metadata`` of a document.

The units of a record are the items declared by ``x-identifier`` on the definition of the items of
an array, and, in a note, the block anchors of its body. The units of one record share one
namespace, so a repeated identifier is kept twice.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from anagraphe.core.anchors import block_anchors
from anagraphe.core.issues import pointer
from anagraphe.core.metadata import frontmatter_problem, split_frontmatter
from anagraphe.core.schemas import parse_document, values_at
from anagraphe.targets.declarations import ContractSchema, Declarations

#: The suffix of a note, read through its frontmatter.
NOTE_SUFFIX = ".md"
#: The suffixes of a document.
DOCUMENT_SUFFIXES = (".yml", ".yaml", ".json")
#: The default field of the identifier of a note and of a document.
NOTE_IDENTIFIER: tuple[str, ...] = ("id",)
DOCUMENT_IDENTIFIER: tuple[str, ...] = ("metadata", "id")


def is_record(rel: str) -> bool:
    """Whether a file may be a record: a Markdown note, or a YAML or JSON document.

    Examples
    --------
    >>> is_record("notes/a.md"), is_record("data/a.yml"), is_record("a.toml")
    (True, True, False)
    """
    return rel.endswith((NOTE_SUFFIX, *DOCUMENT_SUFFIXES))


@dataclass(frozen=True)
class Record:
    """One record of a repository, read for its identifier, its units and its targets."""

    rel: str
    #: The frontmatter of a note, or the top-level mapping of a document; empty when it holds none.
    data: Mapping[str, Any]
    #: The contract named under the binding key, None when the record names none.
    contract: str | None = None
    #: The declarations of the schema of the contract, None when the registry holds none.
    schema: ContractSchema | None = None
    #: The value of the identifier field, None when the field is absent.
    identifier: Any = None
    #: The JSON Pointer of the identifier field.
    identifier_pointer: str = ""
    #: Whether the schema declares the identifier field by ``x-identifier``.
    declared: bool = False
    units: tuple[str, ...] = ()
    #: Why the record cannot be read; None when it can.
    problem: str | None = None


def read_record(root: Path, rel: str, binding: str, declarations: Declarations | None) -> Record:
    """Read a record of a repository, its schema found through the registry when one is declared."""
    try:
        text = (root / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        return Record(rel, {}, problem=f"the record cannot be read: {error}")
    body = ""
    if rel.endswith(NOTE_SUFFIX):
        problem = frontmatter_problem(text)
        if problem is not None:
            return Record(rel, {}, problem=problem)
        data, body = split_frontmatter(text)
        default = NOTE_IDENTIFIER
    else:
        try:
            parsed = parse_document(rel, text)
        except ValueError as error:
            first = str(error).strip().splitlines()[0] if str(error).strip() else "no detail"
            return Record(rel, {}, problem=f"the document cannot be parsed: {first}")
        data = parsed if isinstance(parsed, dict) else {}
        default = DOCUMENT_IDENTIFIER
    contract = data.get(binding)
    contract = contract if isinstance(contract, str) else None
    schema = declarations.of(contract) if declarations is not None and contract else None
    declared = schema is not None and schema.identifier is not None
    field = schema.identifier if schema is not None and schema.identifier is not None else default
    units = [
        unit
        for declaration in (schema.units if schema is not None else ())
        for _, item in values_at(data, declaration.path)
        for unit in [_at(item, declaration.identifier)]
        if isinstance(unit, str)
    ]
    if body:
        units.extend(block_anchors(body))
    return Record(
        rel,
        data,
        contract,
        schema,
        _at(data, field),
        pointer(*field),
        declared,
        tuple(units),
    )


def _at(data: Any, path: tuple[str, ...]) -> Any:
    """Return the value at a key path, None when a key is absent."""
    node = data
    for key in path:
        if not isinstance(node, Mapping) or key not in node:
            return None
        node = node[key]
    return node
