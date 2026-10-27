"""
Types of index, read from their JSON Schemas, and the resolution of the type of one index.

The decision on index types composes each type from parts with ``allOf``. A part declares the keys
that it adds to the frontmatter of an index, and a type schema adds three annotations: its default
ordering mode (``x-default-mode``), its expected control files (``x-expected-files``), and the
location of the index that fixes the type (``x-location``), where one does. This module reads
those schemas once, so the frontmatter checker and the index generator apply one definition of
each type.

The type of an index is the declared ``index_type``. An index declaring none takes the type fixed
by its location, and the type ``module`` otherwise, so an index is checked before it declares its
type.

Examples
--------
>>> schema = {"$schema": "https://json-schema.org/draft/2020-12/schema",
...           "type": "object", "properties": {}}
>>> types = IndexTypes({
...     "module.schema.yaml": {**schema, "$id": "module.schema.yaml",
...                            "x-default-mode": "registry"},
...     "event.schema.yaml": {**schema, "$id": "event.schema.yaml",
...                           "x-default-mode": "sequence",
...                           "x-location": "conferences/*/_index.md",
...                           "properties": {"website": {"type": "string",
...                                                      "pattern": "^https?://\\\\S+$"}}},
...     "artifact.schema.yaml": {**schema, "$id": "artifact.schema.yaml",
...                              "x-default-mode": "sequence",
...                              "x-location": "artifacts/*/_index.md"},
... })
>>> types.resolve("conferences/2026-08-ccn/_index.md", None)[0].name
'event'
>>> types.resolve("foundations/kernels/_index.md", "event")[1]
[]
>>> types.resolve("artifacts/poster/_index.md", "module")[1]
['the location artifacts/*/_index.md fixes the type artifact']
"""

from __future__ import annotations

import datetime
import fnmatch
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from referencing import Registry, Resource
from referencing.exceptions import CannotDetermineSpecification

#: The type of an index declaring none, outside every location fixing a type.
DEFAULT_TYPE = "module"


@dataclass(frozen=True)
class ExpectedFile:
    """A control file that a type expects in the folder of its index."""

    name: str
    #: The role that the file must declare, when the role is fixed.
    role: str | None = None
    required: bool = False


@dataclass(frozen=True)
class IndexType:
    """One type of index: its keys, its default mode, its expected files and its location."""

    name: str
    version: int
    default_mode: str
    #: The keys that the parts of the type add to the frontmatter of an index.
    keys: frozenset[str]
    expected: tuple[ExpectedFile, ...] = ()
    #: The pattern of the index paths that the type is fixed for, one segment per path segment.
    location: str | None = None

    def fixed_by(self, rel: str) -> bool:
        """Whether the location of an index fixes this type.

        Examples
        --------
        >>> kind = IndexType("artifact", 1, "sequence", frozenset(), location="artifacts/*/_index.md")
        >>> kind.fixed_by("artifacts/poster/_index.md"), kind.fixed_by("artifacts/poster/md/_index.md")
        (True, False)
        """
        if self.location is None:
            return False
        parts, pattern = rel.split("/"), self.location.split("/")
        return len(parts) == len(pattern) and all(
            fnmatch.fnmatchcase(part, segment) for part, segment in zip(parts, pattern)
        )


def iso_values(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return frontmatter values with each date written in ISO form, as the schemas expect."""
    return {
        key: (value.isoformat() if isinstance(value, (datetime.date, datetime.datetime)) else value)
        for key, value in data.items()
    }


class IndexTypes:
    """The types of index declared by the schemas of one folder."""

    def __init__(self, schemas: Mapping[str, dict[str, Any]]) -> None:
        self.schemas = dict(schemas)
        self.registry: Registry = Registry().with_resources(
            [
                (identifier, Resource.from_contents(schema))
                for identifier, schema in self.schemas.items()
            ]
        )
        self.types = {
            self._name(identifier): self._type(identifier)
            for identifier, schema in self.schemas.items()
            if "x-default-mode" in schema
        }

    @classmethod
    def load(cls, folder: Path) -> IndexTypes:
        """Read every schema of a folder, keyed by its ``$id``."""
        if not folder.is_dir():
            raise ValueError(f"index-types directory does not exist: {folder}")
        schemas: dict[str, dict[str, Any]] = {}
        for path in sorted(folder.glob("*.schema.yaml")):
            try:
                parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
            except OSError as error:
                raise ValueError(f"cannot read index-type schema {path}: {error}") from error
            except yaml.YAMLError as error:
                raise ValueError(f"cannot parse index-type schema {path}: {error}") from error
            if not isinstance(parsed, dict):
                raise ValueError(f"{path} must contain a YAML mapping")
            identifier = parsed.get("$id")
            if not isinstance(identifier, str) or not identifier:
                raise ValueError(f"{path} must declare a non-empty $id")
            if identifier in schemas:
                raise ValueError(f"duplicate index-type schema identifier: {identifier}")
            schemas[identifier] = parsed
        if not schemas:
            raise ValueError(f"index-types directory contains no schema files: {folder}")
        try:
            loaded = cls(schemas)
        except (CannotDetermineSpecification, KeyError, TypeError, ValueError) as error:
            raise ValueError(f"invalid index-type schemas in {folder}: {error}") from error
        if DEFAULT_TYPE not in loaded.types:
            raise ValueError(f"index-types must declare the default type {DEFAULT_TYPE}")
        return loaded

    @staticmethod
    def _name(identifier: str) -> str:
        return Path(identifier).name.removesuffix(".schema.yaml")

    def _parts(self, identifier: str) -> list[dict[str, Any]]:
        """Return a schema and the parts that it references through ``allOf``, recursively."""
        schema = self.schemas[identifier]
        base = identifier.rsplit("/", 1)[0] + "/" if "/" in identifier else ""
        found = [schema]
        for entry in schema.get("allOf", ()):
            if "$ref" in entry:
                found.extend(self._parts(base + str(entry["$ref"])))
        return found

    def _type(self, identifier: str) -> IndexType:
        parts = self._parts(identifier)
        schema = parts[0]
        return IndexType(
            name=self._name(identifier),
            version=int(schema.get("schema_version", 1)),
            default_mode=str(schema["x-default-mode"]),
            keys=frozenset(key for part in parts for key in part.get("properties", {})),
            expected=tuple(
                ExpectedFile(
                    name=str(spec["name"]),
                    role=spec.get("role"),
                    required=bool(spec.get("required", False)),
                )
                for part in parts
                for spec in part.get("x-expected-files", ())
            ),
            location=schema.get("x-location"),
        )

    @property
    def keys(self) -> frozenset[str]:
        """The keys added by any type, admitted on an index whose type is not yet settled."""
        return frozenset(key for kind in self.types.values() for key in kind.keys)

    def resolve(self, rel: str, declared: str | None) -> tuple[IndexType, list[str]]:
        """Return the type of an index, and the problems of its declaration.

        A declared type outside the schemas, or one disagreeing with the type that the location
        fixes, is a problem. The type returned is then the one fixed by the location, or the
        default type.
        """
        located = next((kind for kind in self.types.values() if kind.fixed_by(rel)), None)
        problems: list[str] = []
        if declared is not None and declared not in self.types:
            problems.append(f"unknown index type: {declared}")
        elif declared is not None and located is not None and declared != located.name:
            problems.append(f"the location {located.location} fixes the type {located.name}")
        elif declared is not None:
            return (self.types[declared], [])
        return (located or self.types[DEFAULT_TYPE], problems)

    def validate(self, kind: IndexType, data: Mapping[str, Any]) -> list[str]:
        """Return the messages of the schema of a type, applied to a frontmatter.

        Examples
        --------
        >>> event = {"$schema": "https://json-schema.org/draft/2020-12/schema",
        ...          "$id": "event.schema.yaml", "type": "object",
        ...          "x-default-mode": "sequence",
        ...          "properties": {"website": {"type": "string",
        ...                                       "pattern": "^https?://\\\\S+$"}}}
        >>> types = IndexTypes({"event.schema.yaml": event})
        >>> types.validate(types.types["event"], {"date": datetime.date(2026, 8, 4),
        ...                                       "website": "conference.org"})
        ["website: 'conference.org' does not match '^https?://\\\\\\\\S+$'"]
        """
        identifier = next(
            identifier for identifier in self.schemas if self._name(identifier) == kind.name
        )
        validator = Draft202012Validator(self.schemas[identifier], registry=self.registry)
        return [
            f"{'.'.join(str(step) for step in error.absolute_path) or 'frontmatter'}: "
            f"{error.message}"
            for error in sorted(
                validator.iter_errors(iso_values(data)),
                key=lambda error: list(error.absolute_path),
            )
        ]
