"""
The Git provider of ADR 0010: the states read from Git object stores, and their fetch.

Each test builds small repositories with Git. A state is read from the clone of its entry, then
from the cache, through the object database alone, and every object read is verified against its
identifier. The last tests run the commands ``states fetch`` and ``targets check`` on a root whose
submodule holds the cited record.
"""

from __future__ import annotations

import os
import subprocess
import zlib
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from anagraphe.cli import app
from anagraphe.resolution import Availability, Blob, Escaping, Missing, Mode, State, Unavailable
from anagraphe.resolution import MemoryProvider, build_context
from anagraphe.resolution.git import STATE_REFERENCES, FetchStatus, GitProvider, fetch_states
from anagraphe.targets.identity import Identity, IdentitySource
from anagraphe.targets.resource import TARGET_REFERENCE

#: A commit that no repository of the tests holds.
ABSENT = "3" * 40


def _git(root: Path, *args: str) -> str:
    """Run a Git command in a repository, and return its output; fail the test when Git fails."""
    return subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.org", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repository(root: Path, files: dict[str, str], links: dict[str, str] | None = None) -> str:
    """Create a repository holding files and symbolic links, commit them, and return the commit."""
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    for rel, target in (links or {}).items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        os.symlink(target, root / rel)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "state")
    return _git(root, "rev-parse", "HEAD")


@pytest.fixture(name="clone")
def _clone(tmp_path: Path) -> tuple[Path, str]:
    """Return a repository holding a file, a nested folder, a link to a folder, a link to a file
    and a gitlink, with its commit."""
    root = tmp_path / "clone"
    _repository(
        root,
        {"people/ada.yml": "identity: {id: ada}\n", "notes/deep/n.md": "# Note\n"},
        {"linked": "people", "alias.yml": "people/ada.yml"},
    )
    _git(root, "update-index", "--add", "--cacheinfo", f"160000,{'4' * 40},vendor/lib")
    _git(root, "commit", "-q", "-m", "gitlink")
    return root, _git(root, "rev-parse", "HEAD")


# --- Reading a state.


def test_a_file_is_read_from_the_objects_of_the_commit(clone: tuple[Path, str]) -> None:
    root, commit = clone
    (root / "people" / "ada.yml").write_text("identity: {id: edited}\n", encoding="utf-8")
    reading = GitProvider().read(State(commit, clone=root), "people/ada.yml")
    assert reading == Blob(b"identity: {id: ada}\n", Mode.FILE)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("alias.yml", Blob(b"people/ada.yml", Mode.LINK)),
        ("notes/deep", Blob(b"", Mode.DIRECTORY)),
        ("vendor/lib", Blob(b"", Mode.SUBMODULE)),
        ("people/zed.yml", Missing()),
        ("people/ada.yml/x", Missing()),
        ("linked/ada.yml", Escaping()),
        ("../outside.yml", Escaping()),
    ],
)
def test_each_entry_of_a_tree_is_read_with_its_mode(
    clone: tuple[Path, str], path: str, expected: object
) -> None:
    root, commit = clone
    assert GitProvider().read(State(commit, clone=root), path) == expected


def test_a_commit_held_by_no_store_is_absent(clone: tuple[Path, str], tmp_path: Path) -> None:
    root, _ = clone
    reading = GitProvider(tmp_path / "no-cache").read(State(ABSENT, clone=root), "a.yml")
    assert isinstance(reading, Unavailable)
    assert reading.availability is Availability.ABSENT
    assert "anagraphe states fetch" in reading.detail


def test_an_object_whose_bytes_change_fails_its_verification(tmp_path: Path) -> None:
    root = tmp_path / "clone"
    commit = _repository(root, {"a.yml": "kept\n"})
    blob = _git(root, "rev-parse", f"{commit}:a.yml")
    loose = root / ".git" / "objects" / blob[:2] / blob[2:]
    loose.chmod(0o644)
    loose.write_bytes(zlib.compress(b"blob 8\0changed\n"))
    reading = GitProvider().read(State(commit, clone=root), "a.yml")
    assert isinstance(reading, Unavailable)
    assert reading.availability is Availability.INVALID


def test_the_repository_of_a_hook_does_not_replace_the_clone(
    clone: tuple[Path, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, commit = clone
    other = tmp_path / "other"
    _repository(other, {"x.yml": "x\n"})
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(other / ".git" / "index"))
    reading = GitProvider().read(State(commit, clone=root), "people/ada.yml")
    assert reading == Blob(b"identity: {id: ada}\n", Mode.FILE)


# --- Fetching a state.


def test_a_fetched_state_is_read_from_the_cache(clone: tuple[Path, str], tmp_path: Path) -> None:
    root, commit = clone
    cache = tmp_path / "cache"
    state = State(commit, f"file://{root}")
    (first,) = fetch_states([("x-lab", state)], cache)
    assert first.status is FetchStatus.FETCHED, first.detail
    (second,) = fetch_states([("x-lab", state)], cache)
    assert second.status is FetchStatus.HELD
    assert GitProvider(cache).read(state, "people/ada.yml") == Blob(b"identity: {id: ada}\n")
    assert f"{STATE_REFERENCES}/{commit}" in _git(cache, "show-ref")
    assert "remote" not in (cache / "config").read_text(encoding="utf-8")


def test_a_commit_that_the_remote_lacks_stays_absent(
    clone: tuple[Path, str], tmp_path: Path
) -> None:
    root, _ = clone
    (result,) = fetch_states([("x-lab", State(ABSENT, f"file://{root}"))], tmp_path / "cache")
    assert result.failed
    assert result.status is FetchStatus.UNAVAILABLE, result.detail


def test_a_state_without_remote_is_reported(tmp_path: Path) -> None:
    (result,) = fetch_states([("x-lab", State(ABSENT))], tmp_path / "cache")
    assert (result.status, result.failed) == (FetchStatus.NO_REMOTE, True)


# --- The context and the commands.


def _configuration_text(identifier: str, sections: str = "") -> str:
    """Return a configuration overriding the identifier of a repository, with further sections."""
    return f"_schema: anagraphe:configuration@2\nrepository: {{id: {identifier}}}\n{sections}"


def test_a_relative_submodule_address_resolves_against_the_remote_of_the_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    _repository(root, {".gitmodules": '[submodule "x"]\n\tpath = projects/x\n\turl = ../x.git\n'})
    _git(root, "remote", "add", "origin", "https://h.org/lab/vault.git")
    _git(root, "update-index", "--add", "--cacheinfo", f"160000,{'5' * 40},projects/x")
    provider = MemoryProvider(
        {"5" * 40: {"anagraphe.yml": Blob(_configuration_text("x-lab").encode())}}
    )
    context = build_context(root, Identity("lab", IdentitySource.OVERRIDE), None, provider)
    assert context.entries["x-lab"].state.remote == "https://h.org/lab/x.git"


def _workspace(tmp_path: Path) -> Path:
    """Return a root whose submodule ``projects/x``, the repository x-lab, holds the record ada,
    and whose record cite.yml targets it."""
    sub = tmp_path / "root" / "projects" / "x"
    sub_commit = _repository(
        sub,
        {
            "anagraphe.yml": _configuration_text("x-lab", "records: {}\n"),
            "record-registry.yml": (
                "_schema: anagraphe:record-registry@1\nrepository: x-lab\n"
                "records:\n  ada: {path: people/ada.yml, format: yaml}\nretired: {}\n"
            ),
            "people/ada.yml": "_schema: test:person@1\nidentity: {id: ada}\n",
        },
    )
    root = tmp_path / "root"
    _git(root, "init", "-q")
    files = {
        "specs/schema-registry.yml": (
            "_schema: kleisis:schema-registry@2\nschemas:\n"
            "  test:person@1: schemas/person.schema.yml\n"
            "  test:citing@1: schemas/citing.schema.yml\nexports: []\n"
        ),
        "schemas/person.schema.yml": (
            "x-identifier: identity.id\nproperties:\n  identity:\n    properties:\n"
            "      id: {type: string}\n"
        ),
        "schemas/citing.schema.yml": (
            f"properties:\n  profile:\n    $ref: {TARGET_REFERENCE}\n"
            "    x-target-contract: ['test:person']\n"
        ),
        "cite.yml": "_schema: test:citing@1\nprofile: {repository: x-lab, id: ada}\n",
        "anagraphe.yml": yaml.safe_dump(
            {
                "_schema": "anagraphe:configuration@2",
                "repository": {"id": "lab"},
                "targets": {"records": {"registry": "specs/schema-registry.yml"}},
            }
        ),
    }
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    _git(root, "update-index", "--add", "--cacheinfo", f"160000,{sub_commit},projects/x")
    return root


def test_the_check_verifies_a_target_into_a_submodule(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    result = CliRunner().invoke(app, ["targets", "check", "--root", str(root)])
    assert result.exit_code == 0, result.output
    assert "0 violations, 0 warnings" in result.output


def test_the_check_reports_a_unit_absent_from_a_submodule_record(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    (root / "cite.yml").write_text(
        "_schema: test:citing@1\nprofile: {repository: x-lab, id: ada, unit: ghost}\n",
        encoding="utf-8",
    )
    result = CliRunner().invoke(app, ["targets", "check", "--root", str(root)])
    assert result.exit_code == 1, result.output
    assert "unknown-unit" in result.output


def test_states_fetch_reports_a_state_held_by_its_submodule(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    result = CliRunner().invoke(app, ["states", "fetch", "--root", str(root)])
    assert result.exit_code == 0, result.output
    assert "held: x-lab (submodule projects/x)" in result.output


def test_states_fetch_exits_with_one_when_a_state_stays_absent(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    _git(root, "update-index", "--add", "--cacheinfo", f"160000,{ABSENT},projects/y")
    result = CliRunner().invoke(app, ["states", "fetch", "--root", str(root)])
    assert result.exit_code == 1, result.output
    assert f"no-remote: submodule projects/y at {ABSENT}" in result.output
