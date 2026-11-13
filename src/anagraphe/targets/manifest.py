"""
The manifest of a repository, ``repository.yml`` at its root, which declares its identifier.

The manifest names its format ``_schema: anagraphe:repository@1``, and the contract fixes its block
``repository``: the identifier ``id``, and the optional list ``retired`` of the former identifiers,
none of them reused. Every other root key stays open, such as the block ``project`` of the project
specification. During the migration, the form ``schema_version: 1`` is still read, and reported.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from referencing import Registry, Resource

from anagraphe.core.issues import pointer
from anagraphe.targets.kinds import INVALID_REPOSITORY_MANIFEST, LEGACY_REPOSITORY_MANIFEST
from anagraphe.targets.resource import (
    ADDRESSING_FILE,
    ADDRESSING_ID,
    REPOSITORY_CONTRACT,
    REPOSITORY_FILE,
    schema,
)

#: The file of the manifest, at the root of the repository.
MANIFEST_FILE = "repository.yml"
#: The key of the legacy form, and the only version of that form.
LEGACY_KEY = "schema_version"
LEGACY_VERSION = 1


@dataclass(frozen=True)
class Manifest:
    """The identity of a repository, read from its manifest."""

    id: str
    #: The former identifiers of the repository.
    retired: tuple[str, ...] = ()
    #: Whether the manifest is written in the legacy form ``schema_version: 1``.
    legacy: bool = False


@dataclass(frozen=True)
class ManifestProblem:
    """A defect of the manifest: its kind, the JSON Pointer of its key, and why."""

    kind: str
    pointer: str
    detail: str


@dataclass(frozen=True)
class ManifestReading:
    """The manifest of a repository, None when it holds none or an invalid one, and its defects."""

    manifest: Manifest | None
    problems: tuple[ManifestProblem, ...] = ()


@cache
def _validator() -> Draft202012Validator:
    """Return the validator of the contract, which resolves the resource from the package data."""
    registry: Registry[Any] = Registry().with_resource(
        ADDRESSING_ID, Resource.from_contents(schema(ADDRESSING_FILE))
    )
    return Draft202012Validator(schema(REPOSITORY_FILE), registry=registry)


def read_manifest(root: Path) -> ManifestReading:
    """Read the manifest at the root of a repository.

    A repository without ``repository.yml`` holds no manifest and no defect. A manifest that
    violates the contract is reported and read as no manifest, so its repository declares no
    identifier.
    """
    path = root / MANIFEST_FILE
    if not path.is_file():
        return ManifestReading(None)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        first = str(error).strip().splitlines()[0] if str(error).strip() else type(error).__name__
        return _invalid("", f"{MANIFEST_FILE} cannot be parsed: {first}")
    if not isinstance(data, dict):
        return _invalid("", f"{MANIFEST_FILE} is not a mapping")
    return check_manifest(data)


def check_manifest(data: dict[str, Any]) -> ManifestReading:
    """Check the content of a manifest against ``anagraphe:repository@1``, or its legacy form.

    Examples
    --------
    >>> check_manifest({"_schema": "anagraphe:repository@1", "repository": {"id": "geonexus"}})
    ManifestReading(manifest=Manifest(id='geonexus', retired=(), legacy=False), problems=())
    >>> check_manifest({"schema_version": 1, "repository": {"id": "geonexus"}}).problems[0].kind
    'legacy-repository-manifest'
    """
    problems: list[ManifestProblem] = []
    legacy = LEGACY_KEY in data
    if legacy:
        if "_schema" in data:
            return _invalid(
                pointer(LEGACY_KEY),
                f"{MANIFEST_FILE} holds both _schema and {LEGACY_KEY}; "
                f"write _schema: {REPOSITORY_CONTRACT} alone",
            )
        version = data[LEGACY_KEY]
        if type(version) is not int or version != LEGACY_VERSION:
            return _invalid(
                pointer(LEGACY_KEY),
                f"{LEGACY_KEY}: {version!r} is no form of the manifest; "
                f"write _schema: {REPOSITORY_CONTRACT}",
            )
        problems.append(
            ManifestProblem(
                LEGACY_REPOSITORY_MANIFEST,
                pointer(LEGACY_KEY),
                f"{MANIFEST_FILE} writes {LEGACY_KEY}: 1; write _schema: {REPOSITORY_CONTRACT}",
            )
        )
        data = {
            "_schema": REPOSITORY_CONTRACT,
            **{key: value for key, value in data.items() if key != LEGACY_KEY},
        }
    invalid: dict[str, ManifestProblem] = {}
    for error in _validator().iter_errors(data):
        at = pointer(*error.absolute_path)
        invalid.setdefault(
            at,
            ManifestProblem(
                INVALID_REPOSITORY_MANIFEST,
                at,
                f"{MANIFEST_FILE} violates {REPOSITORY_CONTRACT}: {error.message}",
            ),
        )
    repository = data.get("repository")
    if not invalid and isinstance(repository, dict):
        retired = tuple(repository.get("retired") or ())
        if repository["id"] in retired:
            at = pointer("repository", "retired")
            invalid[at] = ManifestProblem(
                INVALID_REPOSITORY_MANIFEST,
                at,
                f"repository.retired lists the current identifier {repository['id']}, "
                "and a retired identifier is never reused",
            )
        else:
            return ManifestReading(Manifest(repository["id"], retired, legacy), tuple(problems))
    return ManifestReading(None, (*problems, *(invalid[at] for at in sorted(invalid))))


def _invalid(at: str, detail: str) -> ManifestReading:
    """Return the reading of a manifest that holds one defect and no identifier."""
    return ManifestReading(None, (ManifestProblem(INVALID_REPOSITORY_MANIFEST, at, detail),))
