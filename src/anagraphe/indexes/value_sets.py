"""
The closed value sets of the metadata keys, read from the enumerations of a metadata schema.

The section ``indexes`` names a JSON Schema of the metadata of the files, written in YAML or JSON,
under ``metadata_schema``. The values of a key ``K`` are the ``enum`` of ``properties.K``, or of
``properties.K.items`` for a key holding a list, in their listed order, which also orders a group
sorted by that key. A key without an enumeration has no closed value set. The relations that the
key ``context_relations`` of an index may state are the ``enum`` of the field ``relation`` of its
items, ``properties.context_relations.items.properties.relation``, since each relation sits there in
the frontmatter of an index.

The schema is read through ``allOf``, ``anyOf``, ``oneOf`` and ``$ref``, as the reader of the core
reads it. A ``$ref`` by a path names a file of the repository, and an absolute ``$ref`` resolves
through the ``resources`` of the schema registry of the records, when one is configured. The first
enumeration met in the order of that walk gives the values of a key.

Examples
--------
>>> sets = value_sets({"properties": {
...     "kind": {"enum": ["keynote", "talk"]},
...     "outputs": {"type": "array", "items": {"enum": ["claim", "method"]}},
...     "context_relations": {"items": {"properties": {"relation": {"enum": ["contrasts"]}}}},
...     "title": {"type": "string"}}}, "metadata.schema.yml")
>>> dict(sets.values), sets.relations
({'kind': ('keynote', 'talk'), 'outputs': ('claim', 'method')}, frozenset({'contrasts'}))
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from anagraphe.core.configuration import ConfigurationError
from anagraphe.core.filters import scalar
from anagraphe.core.schemas import Items, Property, SchemaNode, SchemaReader

#: The key of an index stating relations between its members, and the field of each relation.
RELATIONS_KEY = "context_relations"
RELATION_FIELD = "relation"


@dataclass(frozen=True)
class ValueSets:
    """The closed value sets read from a metadata schema."""

    #: The values of each key holding an enumeration, in their listed order, each compared in the
    #: form that a filter compares, so a boolean reads in lowercase.
    values: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    #: The relations that ``context_relations`` admits; None when the schema enumerates none, so
    #: that any relation is admitted.
    relations: frozenset[str] | None = None


def value_sets(document: Any, rel: str, reader: SchemaReader | None = None) -> ValueSets:
    """Return the value sets of a parsed metadata schema, the file ``rel`` of the repository.

    Raises
    ------
    ConfigurationError
        If the schema is not a mapping, or a ``$ref`` of the walk names no readable node.
    """
    if not isinstance(document, Mapping):
        raise ConfigurationError(f"the metadata schema {rel} is not a mapping")
    reader = reader if reader is not None else SchemaReader(Path("."), None)
    values: dict[str, tuple[str, ...]] = {}
    relations: frozenset[str] | None = None
    for node in reader.walk(SchemaNode(document, rel, "", ())):
        enum = node.value.get("enum")
        if node.path is None or not isinstance(enum, list):
            continue
        listed = tuple(scalar(item) for item in enum)
        path = node.path
        if len(path) in (1, 2) and isinstance(path[0], Property):
            if len(path) == 1 or isinstance(path[1], Items):
                values.setdefault(path[0].name, listed)
        if (
            relations is None
            and len(path) == 3
            and path[0] == Property(RELATIONS_KEY)
            and isinstance(path[1], Items)
            and path[2] == Property(RELATION_FIELD)
        ):
            relations = frozenset(listed)
    if reader.problems:
        detail = "; ".join(f"{item.rel}#{item.pointer}: {item.detail}" for item in reader.problems)
        raise ConfigurationError(f"the metadata schema {rel} cannot be read: {detail}")
    return ValueSets(values, relations)


def read_value_sets(root: Path, path: Path, registry: Path | None = None) -> ValueSets:
    """Read the value sets of the metadata schema at ``path``, inside the repository at ``root``,
    its absolute references resolved through the schema registry when one is given.

    Raises
    ------
    ConfigurationError
        If the schema cannot be read or parsed, or a reference of it names no readable node.
    """
    rel = path.relative_to(root).as_posix()
    reader = SchemaReader(root, registry)
    document = reader.document(rel)
    if document is None:
        raise ConfigurationError(f"the metadata schema {rel} cannot be read or parsed")
    return value_sets(document, rel, reader)
