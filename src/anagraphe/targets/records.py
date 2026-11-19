"""
The records of a repository as targets: the identifier of each record and the units inside it.

A record is a Markdown note, read through its frontmatter, a YAML or JSON document, or a TOML
document whose metadata source the configuration declares as ``toml``. The schema of its contract,
named under its binding key, may declare the field of its identifier by ``x-identifier``. Without
that declaration, the identifier of a record is the key ``id`` of the metadata source that the
configuration declares for the file, read as :class:`anagraphe.core.metadata.Identifier` states:
the frontmatter of a note and, by default, the top level of a YAML document, then its block
``metadata``. A JSON document has no default metadata source, so it holds no default identifier
unless a rule of the section ``metadata`` declares one.

The units of a record are the items declared by ``x-identifier`` on the definition of the items of
an array, and, in a note, the block anchors of its body. The units of one record share one
namespace, so a repeated identifier is kept twice. A declared item identifier outside the pattern
``unit-id`` is no unit, and the record keeps it apart for the check to report.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from anagraphe.core.anchors import block_anchors
from anagraphe.core.issues import pointer
from anagraphe.core.metadata import (
    Identifier,
    MetadataReader,
    Source,
    SourceKind,
    frontmatter_problem,
    split_frontmatter,
)
from anagraphe.core.published import matches
from anagraphe.core.schemas import parse_document, values_at
from anagraphe.targets.declarations import ContractSchema, Declarations

#: The suffix of a note, read through its frontmatter.
NOTE_SUFFIX = ".md"
#: The suffixes of a document that is a record whatever its metadata source.
DOCUMENT_SUFFIXES = (".yml", ".yaml", ".json")
#: The suffix of a TOML document, a record when its metadata source is ``toml``.
TOML_SUFFIX = ".toml"
#: The reader of the built-in metadata sources, for a file read without a configuration.
_BUILT_IN = MetadataReader(Path("."))


def is_record(rel: str, source: Source | None = None) -> bool:
    """Whether a file may be a record: a Markdown note, a YAML or JSON document, or a TOML document
    whose metadata source is ``toml``.

    Examples
    --------
    >>> is_record("notes/a.md"), is_record("data/a.yml"), is_record("a.toml")
    (True, True, False)
    >>> is_record("a.toml", Source(SourceKind.TOML, ("tool.notes",)))
    True
    """
    if rel.endswith((NOTE_SUFFIX, *DOCUMENT_SUFFIXES)):
        return True
    return rel.endswith(TOML_SUFFIX) and source is not None and source.kind is SourceKind.TOML


@dataclass(frozen=True)
class Record:  # pylint: disable=too-many-instance-attributes
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
    #: The JSON Pointer and the value of each later key path of the metadata source holding
    #: another identifier than the one of the record.
    conflicts: tuple[tuple[str, Any], ...] = ()
    #: The JSON Pointer and the value of each declared item identifier outside ``unit-id``.
    invalid_units: tuple[tuple[str, Any], ...] = ()


def read_record(
    root: Path,
    rel: str,
    binding: str,
    declarations: Declarations | None,
    source: Source | None = None,
) -> Record:
    """Read a record of a repository, its schema found through the registry when one is declared,
    and its default identifier through its metadata source, the built-in one when none is given."""
    try:
        text = (root / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        return Record(rel, {}, problem=f"the record cannot be read: {error}")
    return parse_record(rel, text, binding, declarations, source)


def parse_record(
    rel: str,
    text: str,
    binding: str,
    declarations: Declarations | None,
    source: Source | None = None,
) -> Record:
    """Read the text of a record, as a file of the repository or a file of a selected state, its
    format given by the suffix of ``rel``, and its default identifier by its metadata source, the
    built-in one when none is given."""
    source = source if source is not None else _BUILT_IN.source_of(rel)
    body = ""
    if rel.endswith(NOTE_SUFFIX):
        problem = frontmatter_problem(text)
        if problem is not None:
            return Record(rel, {}, problem=problem)
        data, body = split_frontmatter(text)
    else:
        try:
            parsed = parse_document(rel, text)
        except ValueError as error:
            first = str(error).strip().splitlines()[0] if str(error).strip() else "no detail"
            return Record(rel, {}, problem=f"the document cannot be parsed: {first}")
        data = parsed if isinstance(parsed, dict) else {}
    contract = data.get(binding)
    contract = contract if isinstance(contract, str) else None
    schema = declarations.of(contract) if declarations is not None and contract else None
    conflicts: tuple[tuple[str, Any], ...] = ()
    if schema is not None and schema.identifier is not None:
        field, identifier = schema.identifier, _at(data, schema.identifier)
    else:
        default = Identifier.of(source, data)
        field, identifier = default.keys, default.value
        conflicts = tuple((pointer(*keys), value) for keys, value in default.conflicts)
    units: list[str] = []
    invalid: list[tuple[str, Any]] = []
    for declaration in schema.units if schema is not None else ():
        for keys, item in values_at(data, declaration.path):
            unit = _at(item, declaration.identifier)
            if unit is None:
                continue
            if matches("unit-id", unit):
                units.append(unit)
            else:
                invalid.append((pointer(*keys, *declaration.identifier), unit))
    if body:
        units.extend(block_anchors(body))
    return Record(
        rel,
        data,
        contract,
        schema,
        identifier,
        pointer(*field),
        schema is not None and schema.identifier is not None,
        tuple(units),
        conflicts=conflicts,
        invalid_units=tuple(invalid),
    )


def _at(data: Any, path: tuple[str, ...]) -> Any:
    """Return the value at a key path, None when a key is absent."""
    node = data
    for key in path:
        if not isinstance(node, Mapping) or key not in node:
            return None
        node = node[key]
    return node
