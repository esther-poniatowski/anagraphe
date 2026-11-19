"""
The identity of a repository: the identifier that a logical target names, and its former
identifiers.

The identifier is derived, in this order:

1. the override ``repository.id`` of ``anagraphe.yml``, when the configuration declares it;
2. the name of the remote ``origin`` of the root: the last segment of its address, after ``/`` or
   the ``:`` of an scp-like address, without a final ``/`` and ``.git``, when the pattern
   ``repository-id`` of the resource ``addressing.v1`` admits it;
3. the name of the folder of the root, under the same pattern;
4. otherwise, the repository has no identity.

The former identifiers come from ``repository.retired`` of ``anagraphe.yml``, and none of them is
the identifier. Without an override, a remote name and a folder name that are two different
identifiers raise the warning ``identity-disagreement``; an override settles it, as a fork does.
A file ``repository.yml`` left at the root, the manifest that declared the identity before, is
reported as ``retired-repository-manifest``, and the report names the override that keeps its
identifier.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping

import yaml

from anagraphe.core.configuration import (
    CONFIG_FILE,
    CONFIG_LOCATIONS,
    ConfigurationError,
    known_keys,
    mapping,
)
from anagraphe.core.git_state import origin_url
from anagraphe.targets.kinds import IDENTITY_DISAGREEMENT, RETIRED_REPOSITORY_MANIFEST
from anagraphe.targets.resource import matches

#: The section of ``anagraphe.yml`` declaring the identity, and its keys.
SECTION = "repository"
SECTION_KEYS = frozenset({"id", "retired"})
#: The retired manifest of a repository, at its root.
MANIFEST_FILE = "repository.yml"


class IdentitySource(StrEnum):
    """Where the identifier of a repository comes from."""

    OVERRIDE = "override"
    REMOTE = "remote"
    FOLDER = "folder"
    NONE = "none"


@dataclass(frozen=True)
class DeclaredIdentity:
    """The section ``repository`` of ``anagraphe.yml``: the override and the former identifiers."""

    #: The override of the identifier, None when the section declares none.
    id: str | None = None
    retired: tuple[str, ...] = ()


@dataclass(frozen=True)
class IdentityProblem:
    """A warning of the identity: its kind, why, and the file that a repair edits."""

    kind: str
    detail: str
    #: The file of the problem relative to the root; None for a problem of the derivation alone.
    rel: str | None = None


@dataclass(frozen=True)
class Identity:
    """The identity of a repository, the source of its identifier, and its warnings."""

    #: The identifier, None when the repository has no identity.
    id: str | None
    source: IdentitySource
    #: The former identifiers of the repository.
    retired: tuple[str, ...] = ()
    problems: tuple[IdentityProblem, ...] = ()


def parse_section(raw: Mapping[str, Any], field: str = SECTION) -> DeclaredIdentity:
    """Validate the section ``repository`` of ``anagraphe.yml``.

    Raises
    ------
    ConfigurationError
        If the section holds an unknown key, an identifier outside the pattern ``repository-id``,
        a retired identifier twice, or the override among the retired identifiers.

    Examples
    --------
    >>> parse_section({"id": "lab", "retired": ["old-lab"]})
    DeclaredIdentity(id='lab', retired=('old-lab',))
    >>> parse_section({"id": "Lab"})
    Traceback (most recent call last):
    ...
    anagraphe.core.configuration.ConfigurationError: repository.id: 'Lab' lies outside the pattern of repository-id
    """
    known_keys(raw, SECTION_KEYS, field)
    identifier = raw.get("id")
    if "id" in raw and not matches("repository-id", identifier):
        raise ConfigurationError(
            f"{field}.id: {identifier!r} lies outside the pattern of repository-id"
        )
    retired = raw.get("retired")
    retired = [] if retired is None else retired
    if not isinstance(retired, list):
        raise ConfigurationError(f"{field}.retired must be a list of repository identifiers")
    for item in retired:
        if not matches("repository-id", item):
            raise ConfigurationError(
                f"{field}.retired: {item!r} lies outside the pattern of repository-id"
            )
    twice = sorted({item for item in retired if retired.count(item) > 1})
    if twice:
        raise ConfigurationError(f"{field}.retired lists {', '.join(twice)} more than once")
    if identifier in retired:
        raise ConfigurationError(
            f"{field}.retired lists the identifier {identifier}, and a retired identifier is "
            "never reused"
        )
    return DeclaredIdentity(identifier, tuple(retired))


def remote_name(url: str | None) -> str | None:
    """Return the name of a remote address: its last segment, after ``/`` or the ``:`` of an
    scp-like address, without a final ``/`` and ``.git``; None for an absent or empty name.

    Examples
    --------
    >>> remote_name("https://github.com/lab/geonexus.git")
    'geonexus'
    >>> remote_name("git@github.com:lab/geonexus.git/")
    'geonexus'
    >>> remote_name("git@host:geonexus")
    'geonexus'
    >>> remote_name(None) is None
    True
    """
    if url is None:
        return None
    name = url.strip().rstrip("/").removesuffix(".git").rstrip("/")
    segment = name.replace(":", "/").rsplit("/", 1)[-1]
    return segment or None


def derive_identity(
    remote_url: str | None, folder: str | None, declared: DeclaredIdentity | None
) -> Identity:
    """Derive the identity from the remote address, the folder name and the declared section.

    A folder of None names no identifier, as for a state of another repository.

    Raises
    ------
    ConfigurationError
        If the retired identifiers list the derived identifier.

    Examples
    --------
    >>> derive_identity("git@github.com:lab/geonexus.git", "geonexus", None).id
    'geonexus'
    >>> derive_identity(None, "Notes", None).source
    <IdentitySource.NONE: 'none'>
    >>> [p.kind for p in derive_identity("https://h.org/a.git", "b", None).problems]
    ['identity-disagreement']
    """
    retired = declared.retired if declared is not None else ()
    if declared is not None and declared.id is not None:
        return _unreused(Identity(declared.id, IdentitySource.OVERRIDE, retired))
    remote = remote_name(remote_url)
    remote = remote if matches("repository-id", remote) else None
    folder = folder if matches("repository-id", folder) else None
    problems: tuple[IdentityProblem, ...] = ()
    if remote is not None and folder is not None and remote != folder:
        problems = (
            IdentityProblem(
                IDENTITY_DISAGREEMENT,
                f"the remote origin names the repository {remote}, and its folder names it "
                f"{folder}; the identifier is {remote}. Declare repository: {{id: <identifier>}} "
                f"in {CONFIG_FILE} to settle it",
            ),
        )
    if remote is not None:
        return _unreused(Identity(remote, IdentitySource.REMOTE, retired, problems))
    if folder is not None:
        return _unreused(Identity(folder, IdentitySource.FOLDER, retired, problems))
    return Identity(None, IdentitySource.NONE, retired, problems)


def _unreused(identity: Identity) -> Identity:
    """Return an identity whose identifier is none of its retired identifiers, or raise."""
    if identity.id in identity.retired:
        repair = "" if identity.source is IdentitySource.OVERRIDE else "; declare repository.id"
        raise ConfigurationError(
            f"repository.retired lists {identity.id}, the identifier of the "
            f"{identity.source.value}, and a retired identifier is never reused{repair}"
        )
    return identity


def state_identity(remote_url: str | None, configuration: Mapping[str, Any] | None) -> Identity:
    """Derive the identity of a selected state of another repository: the override of its
    configuration, else the name of its remote. A state has no folder of its own.

    Raises
    ------
    ConfigurationError
        If the section ``repository`` of the configuration is invalid.

    Examples
    --------
    >>> state_identity("https://h.org/lab/notes.git", None).id
    'notes'
    >>> state_identity(None, {"repository": {"id": "lab", "retired": ["old-lab"]}}).retired
    ('old-lab',)
    """
    section = configuration.get(SECTION) if configuration is not None else None
    declared = (
        parse_section(mapping(section, SECTION))
        if configuration is not None and SECTION in configuration
        else None
    )
    return derive_identity(remote_url, None, declared)


def repository_identity(root: Path, declared: DeclaredIdentity | None) -> Identity:
    """Return the identity of the repository at ``root``, from the section ``repository``, the
    remote ``origin`` and the folder of the root, with the report of a retired manifest.

    Raises
    ------
    ConfigurationError
        If the retired identifiers list the derived identifier.
    """
    root = root.resolve()
    identity = derive_identity(origin_url(root), root.name, declared)
    rel = configuration_rel(root)
    problems = [replace(problem, rel=rel) for problem in identity.problems]
    if (root / MANIFEST_FILE).is_file():
        problems.append(_retired_manifest(root, identity))
    return replace(identity, problems=tuple(problems))


def configuration_rel(root: Path) -> str:
    """Return the path of the configuration below the root, the first place of the search that
    holds a file, else ``anagraphe.yml``."""
    for location in CONFIG_LOCATIONS:
        if (root / location).is_file():
            return location.as_posix()
    return CONFIG_FILE


def _retired_manifest(root: Path, identity: Identity) -> IdentityProblem:
    """Return the report of the manifest left at the root, naming the override that keeps the
    identifier it declares when the derivation yields another one."""
    declared, retired = _manifest_identity(root / MANIFEST_FILE)
    config = configuration_rel(root)
    current = (
        f"{identity.id}, from the {identity.source.value}"
        if identity.id is not None
        else "none, since no identifier is derived"
    )
    lost = (
        declared
        if declared not in (None, identity.id) and identity.source is not IdentitySource.OVERRIDE
        else None
    )
    kept = [
        item for item in retired if item not in identity.retired and item != (lost or identity.id)
    ]
    written = ([f"id: {lost}"] if lost is not None else []) + (
        [f"retired: [{', '.join(kept)}]"] if kept else []
    )
    detail = f"{MANIFEST_FILE} is retired by the section repository of {config}; " + (
        f"it declares {declared}, and " if declared is not None else ""
    )
    if not written:
        return IdentityProblem(
            RETIRED_REPOSITORY_MANIFEST,
            f"{detail}the identity of the repository is {current}; delete {MANIFEST_FILE}",
            MANIFEST_FILE,
        )
    return IdentityProblem(
        RETIRED_REPOSITORY_MANIFEST,
        f"{detail}the identity of the repository is {current}. Write repository: "
        f"{{{', '.join(written)}}} in {config} to keep its identifiers, then delete "
        f"{MANIFEST_FILE}",
        MANIFEST_FILE,
    )


def _manifest_identity(path: Path) -> tuple[str | None, tuple[str, ...]]:
    """Return the identifier and the former identifiers that a retired manifest declares, read
    leniently: a value that is not an identifier is left out."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, yaml.YAMLError):
        # ValueError covers an undecodable file and a timestamp naming an impossible date.
        return None, ()
    block = data.get("repository") if isinstance(data, dict) else None
    if not isinstance(block, dict):
        return None, ()
    identifier = block.get("id")
    retired = block.get("retired")
    items = tuple(
        item
        for item in (retired if isinstance(retired, list) else [])
        if matches("repository-id", item)
    )
    return (identifier if matches("repository-id", identifier) else None), items
