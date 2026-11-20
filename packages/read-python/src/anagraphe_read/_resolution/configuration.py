"""
The section ``resolution`` of ``anagraphe.yml``, and the machine file of the local clones.

The section declares two optional keys:

- ``repositories``, which maps each cited repository identifier, other than those of the
  submodules, to its selected state: ``commit``, a full commit, and ``remote``, an address without
  credentials. The optional key ``config`` names the configuration of Anagraphe inside that state,
  by its path relative to the root of the repository; without it, the accepted places of the state
  are searched;
- ``local``, the path, relative to the root, of the machine file inside the repository.

The machine file maps a repository identifier to the path of a local clone, relative to the folder
of the file or absolute. Its paths belong to one machine, so no commit records it. The environment
variable ``ANAGRAPHE_REPOSITORIES`` names a machine file, usually outside the repository, and
replaces the key ``local``. A machine file inside the repository must be ignored by Git; a file that
Git would record stops the command. A file named by ``local`` and absent from the machine maps no
clone, whereas a file named by the variable must exist.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from anagraphe_read._core.configuration import (
    ConfigurationError,
    known_keys,
    load_yaml,
    mapping,
    repository_path,
)
from anagraphe_read._core.git_state import is_ignored
from anagraphe_read._resolution.provider import confined
from anagraphe_read._targets.resource import matches

#: The keys of the section ``resolution``.
SECTION_KEYS = frozenset({"repositories", "local"})
#: The keys that one declared repository requires.
REPOSITORY_KEYS = frozenset({"commit", "remote"})
#: The keys that one declared repository may add.
OPTIONAL_REPOSITORY_KEYS = frozenset({"config"})
#: The environment variable naming the machine file, which replaces the key ``local``.
MACHINE_VARIABLE = "ANAGRAPHE_REPOSITORIES"
#: A full commit: the 40 hexadecimal digits of SHA-1, or the 64 of SHA-256.
FULL_COMMIT = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")
#: The schemes of a remote address in URL form.
REMOTE_SCHEMES = frozenset({"https", "http", "ssh", "git"})
#: A remote address in the scp form of Git, ``user@host:path``.
SCP_FORM = re.compile(r"[A-Za-z0-9._-]+@[A-Za-z0-9.-]+:[^/].*")


@dataclass(frozen=True)
class DeclaredRepository:
    """The selected state of one cited repository, as the section declares it."""

    commit: str
    remote: str
    #: The path of the configuration of Anagraphe in the state, relative to its root, in its
    #: normal form; None to search the accepted places of the state.
    config: str | None = None


@dataclass(frozen=True)
class ResolutionConfig:
    """The resolved section ``resolution`` of one repository, with the machine file read."""

    repositories: Mapping[str, DeclaredRepository] = field(default_factory=dict)
    #: The local clone of each repository identifier, read from the machine file.
    clones: Mapping[str, Path] = field(default_factory=dict)
    #: The machine file read, None when none applies.
    machine_file: Path | None = None


def parse_section(
    root: Path,
    raw: Mapping[str, Any] | None,
    environment: Mapping[str, str] | None = None,
    field_name: str = "resolution",
) -> ResolutionConfig:
    """Validate the section ``resolution``, absent when ``raw`` is None, and read the machine file.

    The variable ``ANAGRAPHE_REPOSITORIES`` is read from ``environment``, the process environment
    by default, and applies whether or not the section is declared.

    Raises
    ------
    ConfigurationError
        If the section declares another key, an identifier outside the pattern of
        ``repository-id``, an abbreviated commit, a remote address holding credentials or naming a
        local path, a configuration path leaving the repository, or a machine file that Git would record, that cannot be read, or that maps a
        key outside the pattern of ``repository-id``.
    """
    root = root.resolve()
    section = mapping(raw, field_name)
    known_keys(section, SECTION_KEYS, field_name)
    repositories = _repositories(section.get("repositories"), f"{field_name}.repositories")
    variable = (os.environ if environment is None else environment).get(MACHINE_VARIABLE)
    if variable:
        machine = Path(variable).expanduser().absolute()
        if not machine.is_file():
            raise ConfigurationError(f"{MACHINE_VARIABLE} names no file: {variable}")
        origin = MACHINE_VARIABLE
    elif "local" in section:
        machine = repository_path(root, section["local"], f"{field_name}.local")
        origin = f"{field_name}.local"
    else:
        return ResolutionConfig(repositories)
    _require_ignored(root, machine, origin)
    clones = _clones(machine) if machine.is_file() else {}
    return ResolutionConfig(repositories, clones, machine)


def _repositories(value: Any, field_name: str) -> dict[str, DeclaredRepository]:
    """Validate the declared repositories: identifier, full commit, remote address and the
    optional path of the configuration in the state."""
    declared: dict[str, DeclaredRepository] = {}
    for identifier, item in mapping(value, field_name).items():
        at = f"{field_name}.{identifier}"
        if not matches("repository-id", identifier):
            raise ConfigurationError(f"{at}: the key lies outside the pattern of repository-id")
        entry = mapping(item, at)
        if not REPOSITORY_KEYS <= set(entry) <= REPOSITORY_KEYS | OPTIONAL_REPOSITORY_KEYS:
            raise ConfigurationError(
                f"{at} must be a mapping with the keys commit and remote, and optionally config"
            )
        commit, remote = entry["commit"], entry["remote"]
        if not isinstance(commit, str) or not FULL_COMMIT.fullmatch(commit):
            raise ConfigurationError(
                f"{at}.commit must be a full commit of 40 or 64 lowercase hexadecimal digits, "
                f"not {commit!r}"
            )
        problem = remote_problem(remote)
        if problem is not None:
            raise ConfigurationError(f"{at}.remote {problem}")
        declared[identifier] = DeclaredRepository(commit, remote, _config_path(entry, at))
    return declared


def _config_path(entry: Mapping[str, Any], at: str) -> str | None:
    """Return the path of the configuration that an entry names in its state, in its normal form,
    or None when the entry names none."""
    if "config" not in entry:
        return None
    value = entry["config"]
    normal = confined(value) if isinstance(value, str) else None
    if normal is None:
        raise ConfigurationError(
            f"{at}.config must be a path relative to the root of {at.rsplit('.', 1)[-1]}, inside "
            f"that repository, not {value!r}"
        )
    return normal


def remote_problem(remote: Any) -> str | None:
    """Return why a value is no remote address without credentials, None when it is one.

    An address in URL form uses the scheme https, http, ssh or git. An address of the web holds no
    user, since a token is written there; an ssh address may name its user, without a password.
    The scp form ``user@host:path`` of Git is admitted.

    Examples
    --------
    >>> remote_problem("https://github.com/lab/notes.git") is None
    True
    >>> remote_problem("git@github.com:lab/notes.git") is None
    True
    >>> remote_problem("https://token@github.com/lab/notes.git")
    'holds credentials, which a committed file never records'
    >>> remote_problem("/Users/lab/notes")
    'names no remote address: write https://host/path, ssh://host/path or user@host:path'
    """
    if not isinstance(remote, str) or not remote:
        return "must be a remote address"
    if remote.startswith("-"):
        return "begins with -, which Git would read as an option"
    if SCP_FORM.fullmatch(remote) and "://" not in remote:
        return None
    parts = urlsplit(remote)
    if parts.scheme not in REMOTE_SCHEMES or not parts.hostname:
        return "names no remote address: write https://host/path, ssh://host/path or user@host:path"
    if parts.password is not None or (parts.username is not None and parts.scheme != "ssh"):
        return "holds credentials, which a committed file never records"
    return None


def _require_ignored(root: Path, machine: Path, origin: str) -> None:
    """Require a machine file inside the repository to be ignored by Git."""
    try:
        rel = machine.resolve().relative_to(root).as_posix()
    except ValueError:
        return
    if is_ignored(root, rel) is False:
        raise ConfigurationError(
            f"{origin} names {rel}, which Git would record; the paths of local clones belong to "
            "one machine, so list the file in .gitignore or in .git/info/exclude"
        )


def _clones(machine: Path) -> dict[str, Path]:
    """Read the machine file: a mapping of repository identifiers to the paths of local clones."""
    raw = load_yaml(machine)
    clones: dict[str, Path] = {}
    for identifier, value in raw.items():
        if not matches("repository-id", identifier):
            raise ConfigurationError(
                f"{machine}: the key {identifier!r} lies outside the pattern of repository-id"
            )
        if not isinstance(value, str) or not value:
            raise ConfigurationError(f"{machine}: {identifier} must map to the path of a clone")
        path = Path(value).expanduser()
        clones[identifier] = path if path.is_absolute() else machine.parent / path
    return clones
