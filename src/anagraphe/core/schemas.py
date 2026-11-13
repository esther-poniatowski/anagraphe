"""
The schemas of the record contracts of a repository, read through the schema registry of Kleisis.

A record names its contract under its binding key, ``_schema`` by default. The schema registry maps
each contract to its schema file under ``schemas``, and each absolute ``$id`` to its file under
``resources``. The capabilities read the keywords of these schemas, such as ``x-binds`` or
``x-identifier``, through one walk.

The walk visits each node of a schema with the key path of the values that the node describes. The
path grows through three keywords: ``properties``, whose names form its steps, ``items``, whose
step names every item of an array, and ``additionalProperties``, whose step names every value of a
mapping under a key that ``properties`` does not declare. The walk also enters the subschemas of
``allOf``, ``anyOf`` and ``oneOf``, which describe the same value as their schema, and every
``$ref``. A ``$ref`` names a fragment of the same file, an absolute ``$id`` of the registry when it
opens on a URI scheme, a path from the root of the repository when it opens on ``/``, or a path
relative to the referring file. Under any other applicator, such as ``not`` or ``patternProperties``,
a node describes no value of a single key path, so the walk visits it without a path.
"""

from __future__ import annotations

import json
import posixpath
import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Mapping

import yaml

from anagraphe.core.configuration import ConfigurationError, known_keys, mapping, repository_path
from anagraphe.core.issues import pointer

#: The keywords whose subschemas describe the same value as their schema.
COMPOSITIONS = ("allOf", "anyOf", "oneOf")
#: The compositions whose subschemas describe the value only when it matches them.
CONDITIONAL = frozenset({"anyOf", "oneOf"})
#: The applicators other than ``properties`` and the compositions, in the order of the walk. The
#: walk extends the key path through ``items`` and ``additionalProperties``, and through no other.
APPLICATORS = (
    "items",
    "prefixItems",
    "contains",
    "additionalProperties",
    "patternProperties",
    "propertyNames",
    "unevaluatedProperties",
    "unevaluatedItems",
    "dependentSchemas",
    "if",
    "then",
    "else",
    "not",
)
#: A URI scheme, which makes a reference an absolute ``$id``.
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
#: The identifier of the format of the schema registry that Kleisis writes, under ``_schema``.
REGISTRY_FORMAT = "kleisis:schema-registry@2"
#: The legacy versions of the registry under ``schema_version``, still read because a repository
#: regenerates its registry only when it raises its pin of Kleisis.
LEGACY_REGISTRY_VERSIONS = frozenset({1, 2})
#: The key of a record naming its contract, as the schema registry of Kleisis writes it by default.
DEFAULT_BINDING = "_schema"
#: The keys of the declaration of records in a section of ``anagraphe.yml``.
RECORD_KEYS = frozenset({"registry", "binding"})
#: A ``$ref`` naming no readable schema node inside the repository.
UNRESOLVED_REFERENCE = "unresolved-schema-reference"
#: A schema named by the registry that cannot be read, which leaves its records unanalyzed.
UNREADABLE_SCHEMA = "unreadable-schema"


def parse_document(rel: str, text: str) -> Any:
    """Parse a document as JSON for a suffix ``.json``, and as YAML otherwise.

    Raises
    ------
    ValueError
        If the document does not parse; a YAML error is converted.
    """
    if rel.endswith(".json"):
        return json.loads(text)
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ValueError(str(error)) from error


def check_registry_format(raw: Mapping[Any, Any], registry: Path) -> None:
    """Accept a registry marked by ``_schema: kleisis:schema-registry@2``, or by the legacy
    ``schema_version: 1`` or ``schema_version: 2``.

    Raises
    ------
    ConfigurationError
        If the registry carries neither key, both keys, or another value; the message names the
        value to write.

    Examples
    --------
    >>> check_registry_format({"_schema": "kleisis:schema-registry@2"}, Path("r.yml"))
    >>> check_registry_format({"schema_version": 1}, Path("r.yml"))
    >>> check_registry_format({"schema_version": 3}, Path("r.yml"))
    Traceback (most recent call last):
    ...
    anagraphe.core.configuration.ConfigurationError: the schema registry r.yml has schema_version: 3; write _schema: kleisis:schema-registry@2
    """
    expected = f"write _schema: {REGISTRY_FORMAT}"
    if "_schema" in raw and "schema_version" in raw:
        raise ConfigurationError(
            f"the schema registry {registry} has both _schema and schema_version; {expected} alone"
        )
    if "_schema" in raw:
        if raw["_schema"] != REGISTRY_FORMAT:
            raise ConfigurationError(
                f"the schema registry {registry} has _schema: {raw['_schema']}; {expected}"
            )
        return
    if "schema_version" in raw:
        version = raw["schema_version"]
        # A boolean equals 0 or 1 in Python, so the type is compared before the value.
        if type(version) is not int or version not in LEGACY_REGISTRY_VERSIONS:
            raise ConfigurationError(
                f"the schema registry {registry} has schema_version: {version!r}; {expected}"
            )
        return
    raise ConfigurationError(f"the schema registry {registry} names no format; {expected}")


@dataclass(frozen=True)
class RecordSchemas:
    """The schema registry of the records, and the key of a record naming its contract."""

    registry: Path
    binding: str = DEFAULT_BINDING


def parse_records(root: Path, value: Any, field_name: str) -> RecordSchemas | None:
    """Parse the declaration of records of a section, None when the section declares none."""
    if value is None:
        return None
    raw = mapping(value, field_name)
    known_keys(raw, RECORD_KEYS, field_name)
    registry = repository_path(root, raw.get("registry"), f"{field_name}.registry")
    if not registry.is_file():
        raise ConfigurationError(f"{field_name}.registry names no file: {raw.get('registry')}")
    binding = raw.get("binding", DEFAULT_BINDING)
    if not isinstance(binding, str) or not binding:
        raise ConfigurationError(f"{field_name}.binding must name the key of a record's contract")
    return RecordSchemas(registry, binding)


@dataclass(frozen=True)
class Property:
    """The step from a mapping to the value of one of its keys."""

    name: str


@dataclass(frozen=True)
class Items:
    """The step from an array to each of its items, from the position ``start`` on."""

    start: int = 0


@dataclass(frozen=True)
class Values:
    """The step from a mapping to each value under a key outside ``declared``."""

    declared: frozenset[str] = frozenset()


#: One step of a key path.
Step = Property | Items | Values


def values_at(data: Any, path: tuple[Step, ...]) -> Iterator[tuple[tuple[str | int, ...], Any]]:
    """Yield the keys and the value of each value of a document at a key path.

    Examples
    --------
    >>> data = {"ideas": [{"id": "a"}, {"id": "b"}], "other": 1}
    >>> list(values_at(data, (Property("ideas"), Items(), Property("id"))))
    [(('ideas', 0, 'id'), 'a'), (('ideas', 1, 'id'), 'b')]
    >>> list(values_at({"id": 1, "x": 2, "y": 3}, (Values(frozenset({"id"})),)))
    [(('x',), 2), (('y',), 3)]
    """
    if not path:
        yield (), data
        return
    step, rest = path[0], path[1:]
    if isinstance(step, Property):
        if isinstance(data, Mapping) and step.name in data:
            for keys, value in values_at(data[step.name], rest):
                yield (step.name, *keys), value
    elif isinstance(step, Items):
        if isinstance(data, list):
            for number in range(step.start, len(data)):
                for keys, value in values_at(data[number], rest):
                    yield (number, *keys), value
    elif isinstance(data, Mapping):
        for name, item in data.items():
            if str(name) not in step.declared:
                for keys, value in values_at(item, rest):
                    yield (str(name), *keys), value


@dataclass(frozen=True)
class SchemaNode:
    """A node of a schema, with the values of a record that it describes."""

    value: Mapping[str, Any]
    #: The repository-relative path of the schema file.
    rel: str
    #: The JSON Pointer of the node in its file.
    at: str
    #: The key path of the values that the node describes; None under an applicator through which
    #: the walk extends no path, such as ``not``.
    path: tuple[Step, ...] | None
    #: The innermost applicator crossed on the way to the node, other than ``properties`` and the
    #: compositions; None when the walk crossed none.
    under: str | None = None
    #: Whether the walk crossed ``anyOf`` or ``oneOf`` since the last step of the path, so that the
    #: node describes only the values that match its branch.
    conditional: bool = False


@dataclass(frozen=True)
class SchemaProblem:
    """A defect of a schema met by a walk: its kind, its file and its node."""

    kind: str
    #: The repository-relative path of the schema file.
    rel: str
    #: The JSON Pointer of the offending node in the file; empty for the whole file.
    pointer: str
    detail: str


@dataclass
class SchemaReader:
    """Read the schemas of the contracts of a registry, each file once.

    The reader records the references that name no readable node, and the schemas of the registry
    that cannot be read, under :attr:`problems`.
    """

    root: Path
    registry: Path
    problems: list[SchemaProblem] = field(default_factory=list, init=False)
    _schemas: dict[str, str] = field(default_factory=dict, init=False)
    _resources: dict[str, str] = field(default_factory=dict, init=False)
    _documents: dict[str, Any] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        try:
            raw = yaml.safe_load(self.registry.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as error:
            raise ConfigurationError(
                f"cannot read the schema registry {self.registry}: {error}"
            ) from error
        if not isinstance(raw, Mapping):
            raise ConfigurationError(f"the schema registry {self.registry} is not a mapping")
        check_registry_format(raw, self.registry)
        for key, target in (("schemas", self._schemas), ("resources", self._resources)):
            entries = raw.get(key) or {}
            if not isinstance(entries, Mapping):
                raise ConfigurationError(f"the key {key} of {self.registry} is not a mapping")
            target.update({str(name): str(path) for name, path in entries.items()})

    def contracts(self) -> tuple[str, ...]:
        """Return the contracts of the registry, in sorted order."""
        return tuple(sorted(self._schemas))

    def root_of(self, contract: str) -> SchemaNode | None:
        """Return the root node of the schema of a contract, None when the registry holds no such
        contract, or after recording that its schema cannot be read."""
        if contract not in self._schemas:
            return None
        rel = posixpath.normpath(self._schemas[contract])
        document = self.document(rel)
        if document is None:
            problem = SchemaProblem(
                UNREADABLE_SCHEMA, rel, "", f"the schema of {contract} cannot be read"
            )
            if problem not in self.problems:
                self.problems.append(problem)
            return None
        # A document that parses to another value than a mapping describes no field.
        return SchemaNode(document, rel, "", ()) if isinstance(document, Mapping) else None

    def document(self, rel: str) -> Any:
        """Return a parsed schema file inside the repository, None when it cannot be read."""
        if rel not in self._documents:
            try:
                if rel == ".." or rel.startswith(("../", "/")):
                    raise ValueError("the file lies outside the repository")
                self._documents[rel] = parse_document(
                    rel, (self.root / rel).read_text(encoding="utf-8")
                )
            except (OSError, UnicodeDecodeError, ValueError):
                self._documents[rel] = None
        return self._documents[rel]

    def walk(self, start: SchemaNode, opaque: frozenset[str] = frozenset()) -> Iterator[SchemaNode]:
        """Yield every node reached from a node, the node itself first.

        A ``$ref`` whose address, the part before ``#``, lies in ``opaque`` is not followed, so that a
        capability recognizes a definition by its URI without reading its file. A recursive schema
        stops where it re-enters a node.
        """
        yield from self._walk(start, opaque, frozenset())

    def _walk(
        self, node: SchemaNode, opaque: frozenset[str], stack: frozenset[tuple[str, str]]
    ) -> Iterator[SchemaNode]:
        """Yield a node, then the nodes below it, in the order of the keywords."""
        if (node.rel, node.at) in stack:
            return
        stack = stack | {(node.rel, node.at)}
        yield node
        value = node.value
        for keyword in COMPOSITIONS:
            subschemas = value.get(keyword)
            if isinstance(subschemas, list):
                for number, subschema in enumerate(subschemas):
                    yield from self._child(
                        node,
                        subschema,
                        pointer(keyword, number),
                        node.path,
                        node.under,
                        node.conditional or keyword in CONDITIONAL,
                        opaque,
                        stack,
                    )
        properties = value.get("properties")
        if isinstance(properties, Mapping):
            for name, subschema in properties.items():
                yield from self._child(
                    node,
                    subschema,
                    pointer("properties", str(name)),
                    _extend(node.path, Property(str(name))),
                    node.under,
                    False,
                    opaque,
                    stack,
                )
        for keyword in APPLICATORS:
            yield from self._applicator(node, keyword, opaque, stack)
        reference = value.get("$ref")
        if isinstance(reference, str) and reference.partition("#")[0] not in opaque:
            target = self.resolve(reference, node.rel, node.at + pointer("$ref"))
            if target is not None and isinstance(target[0], Mapping):
                yield from self._walk(
                    SchemaNode(
                        target[0], target[1], target[2], node.path, node.under, node.conditional
                    ),
                    opaque,
                    stack,
                )

    def _applicator(
        self,
        node: SchemaNode,
        keyword: str,
        opaque: frozenset[str],
        stack: frozenset[tuple[str, str]],
    ) -> Iterator[SchemaNode]:
        """Walk the subschemas of one applicator, extending the path through ``items`` and
        ``additionalProperties``."""
        value = node.value.get(keyword)
        at = pointer(keyword)
        if keyword == "items" and isinstance(value, Mapping):
            prefix = node.value.get("prefixItems")
            start = len(prefix) if isinstance(prefix, list) else 0
            yield from self._child(
                node, value, at, _extend(node.path, Items(start)), keyword, False, opaque, stack
            )
        elif keyword == "additionalProperties" and isinstance(value, Mapping):
            properties = node.value.get("properties")
            declared = frozenset(
                str(name) for name in (properties if isinstance(properties, Mapping) else ())
            )
            yield from self._child(
                node, value, at, _extend(node.path, Values(declared)), keyword, False, opaque, stack
            )
        elif isinstance(value, list):
            for number, item in enumerate(value):
                yield from self._child(
                    node, item, at + pointer(number), None, keyword, False, opaque, stack
                )
        elif isinstance(value, Mapping) and keyword in ("patternProperties", "dependentSchemas"):
            for name, item in value.items():
                yield from self._child(
                    node, item, at + pointer(str(name)), None, keyword, False, opaque, stack
                )
        else:
            yield from self._child(node, value, at, None, keyword, False, opaque, stack)

    def _child(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        parent: SchemaNode,
        value: Any,
        at: str,
        path: tuple[Step, ...] | None,
        under: str | None,
        conditional: bool,
        opaque: frozenset[str],
        stack: frozenset[tuple[str, str]],
    ) -> Iterator[SchemaNode]:
        """Walk a subschema of a node, placed at a pointer relative to that node."""
        if isinstance(value, Mapping):
            yield from self._walk(
                SchemaNode(value, parent.rel, parent.at + at, path, under, conditional),
                opaque,
                stack,
            )

    def resolve(self, reference: str, rel: str, at: str) -> tuple[Any, str, str] | None:
        """Return the node named by a ``$ref``, its file and its pointer, None after recording why
        the reference names no readable node of the repository."""
        address, _, fragment = reference.partition("#")
        if not address:
            target = rel
        elif SCHEME.match(address):
            if address not in self._resources:
                self._unresolved(rel, at, f"the registry maps no $id {address}")
                return None
            target = posixpath.normpath(self._resources[address])
        elif address.startswith("/"):
            target = posixpath.normpath(address.lstrip("/"))
        else:
            target = posixpath.normpath(posixpath.join(posixpath.dirname(rel), address))
        document = self.document(target)
        if document is None:
            self._unresolved(rel, at, f"{reference} names no readable schema: {target}")
            return None
        node = document
        fragment = urllib.parse.unquote(fragment)
        for part in [part for part in fragment.split("/") if part]:
            key = part.replace("~1", "/").replace("~0", "~")
            if isinstance(node, Mapping) and key in node:
                node = node[key]
            elif isinstance(node, list) and key.isdigit() and int(key) < len(node):
                node = node[int(key)]
            else:
                self._unresolved(rel, at, f"{reference} names no node of {target}")
                return None
        return node, target, fragment

    def _unresolved(self, rel: str, at: str, detail: str) -> None:
        """Record a reference naming no readable node of the repository, once."""
        problem = SchemaProblem(UNRESOLVED_REFERENCE, rel, at, detail)
        if problem not in self.problems:
            self.problems.append(problem)


def _extend(path: tuple[Step, ...] | None, step: Step) -> tuple[Step, ...] | None:
    """Return a key path followed by one step, None when the path is None."""
    return None if path is None else (*path, step)
