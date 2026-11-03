"""
The fields of a record that bind it, as the schema of its contract marks them by ``x-binds``.

A record names its contract under its binding key, ``_schema`` by default. The schema registry of
Kleisis maps the contract to its schema file under ``schemas``, and maps each absolute ``$id`` to
its file under ``resources``. The keyword ``x-binds`` sits on a property of the schema and names the
role that the property binds, such as ``onomasia.glossary``.

The marks are read through ``properties``, whose names form the key path of a field, through the
subschemas of ``allOf``, ``anyOf`` and ``oneOf``, and through every ``$ref``. A ``$ref`` names a fragment
of the same file, an absolute ``$id`` of the registry when it opens on a URI scheme, a path from the
root of the repository when it opens on ``/``, or a path relative to the referring file. A mark
reached under another applicator, such as ``items``, is reported, since its field has no single key
path.
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

from anagraphe.bindings.kinds import (
    INVALID_MARK,
    UNREADABLE_SCHEMA,
    UNRESOLVED_REFERENCE,
)
from anagraphe.bindings.model import ROLE_PATTERN
from anagraphe.core.configuration import ConfigurationError
from anagraphe.core.issues import pointer

#: The keyword marking a property that binds its record.
KEYWORD = "x-binds"
#: The keywords whose subschemas describe the same value as their schema.
COMPOSITIONS = ("allOf", "anyOf", "oneOf")
#: The applicators whose subschemas describe another value than a field of a single key path.
UNSUPPORTED = (
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
#: The format versions of the schema registry read by this release.
REGISTRY_VERSIONS = frozenset({1, 2})


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


@dataclass(frozen=True)
class SchemaProblem:
    """A defect of a schema reached by the marks: its kind, its file and its node."""

    kind: str
    #: The repository-relative path of the schema file.
    rel: str
    #: The JSON Pointer of the offending node in the file; empty for the whole file.
    pointer: str
    detail: str


@dataclass
class SchemaBindings:
    """The binding fields of each contract of a registry, read from its schemas once."""

    root: Path
    registry: Path
    problems: list[SchemaProblem] = field(default_factory=list, init=False)
    _schemas: dict[str, str] = field(default_factory=dict, init=False)
    _resources: dict[str, str] = field(default_factory=dict, init=False)
    _fields: dict[str, dict[str, tuple[tuple[str, ...], ...]]] = field(
        default_factory=dict, init=False
    )
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
        version = raw.get("schema_version", 1)
        if version not in REGISTRY_VERSIONS:
            raise ConfigurationError(
                f"the schema registry {self.registry} has the format {version}; "
                "this release reads the formats 1 and 2"
            )
        for key, target in (("schemas", self._schemas), ("resources", self._resources)):
            entries = raw.get(key) or {}
            if not isinstance(entries, Mapping):
                raise ConfigurationError(f"the key {key} of {self.registry} is not a mapping")
            target.update({str(name): str(path) for name, path in entries.items()})

    def contracts(self) -> tuple[str, ...]:
        """Return the contracts of the registry, in sorted order."""
        return tuple(sorted(self._schemas))

    def fields(self, contract: str) -> Mapping[str, tuple[tuple[str, ...], ...]] | None:
        """Return the key paths binding each role in the records of a contract, in the order of the
        schema; None when the registry holds no such contract."""
        if contract not in self._schemas:
            return None
        if contract not in self._fields:
            found: dict[str, list[tuple[str, ...]]] = {}
            rel = posixpath.normpath(self._schemas[contract])
            document = self._document(rel)
            if document is None:
                self.problems.append(
                    SchemaProblem(
                        UNREADABLE_SCHEMA, rel, "", f"the schema of {contract} cannot be read"
                    )
                )
            else:
                for role, path in self._walk(document, rel, "", (), None, frozenset()):
                    if path not in found.setdefault(role, []):
                        found[role].append(path)
            self._fields[contract] = {role: tuple(paths) for role, paths in found.items()}
        return self._fields[contract]

    def _document(self, rel: str) -> Any:
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

    def _walk(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        node: Any,
        rel: str,
        at: str,
        path: tuple[str, ...],
        under: str | None,
        stack: frozenset[tuple[str, str]],
    ) -> Iterator[tuple[str, tuple[str, ...]]]:
        """Yield the role and the key path of each property below a node marked by ``x-binds``.

        ``under`` names the unsupported applicator holding the node, None when the node describes a
        field of a single key path. ``stack`` holds the nodes being walked, so a recursive schema
        stops where it re-enters a node.
        """
        if not isinstance(node, Mapping) or (rel, at) in stack:
            return
        stack = stack | {(rel, at)}
        if KEYWORD in node:
            yield from self._mark(node[KEYWORD], rel, at + pointer(KEYWORD), path, under)
        for keyword in COMPOSITIONS:
            subschemas = node.get(keyword)
            if isinstance(subschemas, list):
                for number, subschema in enumerate(subschemas):
                    yield from self._walk(
                        subschema, rel, at + pointer(keyword, number), path, under, stack
                    )
        properties = node.get("properties")
        if isinstance(properties, Mapping):
            for name, subschema in properties.items():
                yield from self._walk(
                    subschema,
                    rel,
                    at + pointer("properties", str(name)),
                    (*path, str(name)),
                    under,
                    stack,
                )
        for keyword in UNSUPPORTED:
            yield from self._unsupported(
                node.get(keyword), rel, at + pointer(keyword), keyword, stack
            )
        reference = node.get("$ref")
        if isinstance(reference, str):
            target = self._resolve(reference, rel, at + pointer("$ref"))
            if target is not None:
                yield from self._walk(target[0], target[1], target[2], path, under, stack)

    def _unsupported(
        self, value: Any, rel: str, at: str, keyword: str, stack: frozenset[tuple[str, str]]
    ) -> Iterator[tuple[str, tuple[str, ...]]]:
        """Walk the subschemas of an unsupported applicator, so that a mark under them is reported."""
        if isinstance(value, list):
            for number, item in enumerate(value):
                yield from self._walk(item, rel, at + pointer(number), (), keyword, stack)
        elif isinstance(value, Mapping) and keyword in ("patternProperties", "dependentSchemas"):
            for name, item in value.items():
                yield from self._walk(item, rel, at + pointer(str(name)), (), keyword, stack)
        else:
            yield from self._walk(value, rel, at, (), keyword, stack)

    def _mark(
        self, role: Any, rel: str, at: str, path: tuple[str, ...], under: str | None
    ) -> Iterator[tuple[str, tuple[str, ...]]]:
        """Yield the role and the key path of a valid mark, or record why the mark is invalid."""
        if not isinstance(role, str) or not ROLE_PATTERN.fullmatch(role):
            detail = f"{KEYWORD} must name a role as <tool>.<name>"
        elif under is not None:
            detail = f"{KEYWORD} sits under {under}, where a field has no single key path"
        elif not path:
            detail = f"{KEYWORD} marks a property, not a whole record"
        else:
            yield role, path
            return
        self.problems.append(SchemaProblem(INVALID_MARK, rel, at, detail))

    def _resolve(self, reference: str, rel: str, at: str) -> tuple[Any, str, str] | None:
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
        document = self._document(target)
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
        """Record a reference naming no readable node of the repository."""
        self.problems.append(SchemaProblem(UNRESOLVED_REFERENCE, rel, at, detail))
