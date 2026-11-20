"""Behavioral tests of the identity of a repository, as ADR 0006 derives it since 2026-11-19.

The conformance cases of ``specs/conformance/identity.yml`` fix the validation of the section
``repository`` and the pure derivation. The tests below cover what the cases cannot state: the
remote ``origin`` read from Git, the files at which the check places the warnings of the identity,
the override that the report of a retired manifest names, and the configuration errors.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from anagraphe_read._core.configuration import ConfigurationError
from anagraphe_read._core.git_state import origin_url
from anagraphe_read._targets.identity import (
    DeclaredIdentity,
    IdentitySource,
    derive_identity,
    parse_section,
    repository_identity,
)
from anagraphe_read._targets.resource import schema

from anagraphe.cli import app
from anagraphe.configuration import load_config
from anagraphe.targets.service import TargetChecker

PROJECT = Path(__file__).resolve().parent.parent
CASES_FILE = PROJECT / "specs" / "conformance" / "identity.yml"
SUITE: dict[str, Any] = yaml.safe_load(CASES_FILE.read_text(encoding="utf-8"))
SECTIONS = {case["id"]: case for case in SUITE["sections"]}
DERIVATIONS = {case["id"]: case for case in SUITE["derivations"]}


# --- Conformance cases.


@pytest.mark.parametrize("case_id", sorted(SECTIONS))
def test_section_conforms(case_id: str) -> None:
    case = SECTIONS[case_id]
    if case["valid"]:
        parse_section(case["section"])
    else:
        with pytest.raises(ConfigurationError):
            parse_section(case["section"])


@pytest.mark.parametrize("case_id", sorted(DERIVATIONS))
def test_derivation_conforms(case_id: str) -> None:
    case = DERIVATIONS[case_id]
    declared = parse_section(case["declared"]) if case["declared"] is not None else None
    if case.get("error"):
        with pytest.raises(ConfigurationError, match="never reused"):
            derive_identity(case["remote"], case["folder"], declared)
        return
    identity = derive_identity(case["remote"], case["folder"], declared)
    assert identity.id == case["identity"]
    assert list(identity.retired) == case["retired"]
    assert identity.source.value == case["source"]
    assert [problem.kind for problem in identity.problems] == case["warnings"]


def test_cases_cover_every_source_and_the_warning() -> None:
    derived = [case for case in DERIVATIONS.values() if not case.get("error")]
    assert {case["source"] for case in derived} == {source.value for source in IdentitySource}
    assert any(case["warnings"] == ["identity-disagreement"] for case in derived)


def test_the_pattern_is_the_one_of_the_resource() -> None:
    """The derivation admits a name exactly when the pattern repository-id of the resource does."""
    resource = schema("addressing.v1.schema.yml")["$defs"]["repository-id"]["pattern"]
    assert resource.startswith("^[a-z0-9]")
    for name in ("lab", "lab-notes", "Lab", "lab_notes", "lab.notes", "-lab", "lab\n"):
        derived = derive_identity(None, name, None).id
        assert (derived == name) is (name in ("lab", "lab-notes"))


# --- The repository on disk.


def _git(root: Path, *args: str) -> None:
    """Run a Git command in a repository, failing the test when Git fails."""
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _repository(folder: Path, remote: str | None) -> Path:
    """Initialize a Git repository in a folder, with a remote origin when one is given."""
    folder.mkdir(parents=True)
    _git(folder, "init", "-q")
    if remote is not None:
        _git(folder, "remote", "add", "origin", remote)
    return folder


def test_the_remote_origin_is_read_at_the_top_of_a_work_tree(tmp_path: Path) -> None:
    root = _repository(tmp_path / "notes", "git@github.com:lab/lab-notes.git")
    (root / "inner").mkdir()
    assert origin_url(root) == "git@github.com:lab/lab-notes.git"
    assert origin_url(root / "inner") is None
    assert origin_url(tmp_path) is None


def test_the_identity_of_a_root_derives_from_its_remote_then_its_folder(tmp_path: Path) -> None:
    root = _repository(tmp_path / "notes", "https://github.com/lab/notes.git")
    identity = repository_identity(root, None)
    assert (identity.id, identity.source, identity.problems) == ("notes", "remote", ())
    plain = _repository(tmp_path / "lab-two", None)
    assert repository_identity(plain, None).source is IdentitySource.FOLDER


def test_a_disagreement_is_placed_at_the_configuration(tmp_path: Path) -> None:
    root = _repository(tmp_path / "notes", "https://github.com/lab/lab-notes.git")
    (root / ".config").mkdir()
    (root / ".config" / "anagraphe.yml").write_text("", encoding="utf-8")
    (problem,) = repository_identity(root, None).problems
    assert (problem.kind, problem.rel) == ("identity-disagreement", ".config/anagraphe.yml")
    assert "the identifier is lab-notes" in problem.detail
    assert repository_identity(root, DeclaredIdentity("notes")).problems == ()


def test_a_retired_manifest_names_the_override_that_keeps_its_identifier(tmp_path: Path) -> None:
    root = _repository(tmp_path / "notes", None)
    (root / "repository.yml").write_text(
        "_schema: anagraphe:repository@1\nrepository: {id: lab, retired: [old-lab]}\n",
        encoding="utf-8",
    )
    (problem,) = repository_identity(root, None).problems
    assert problem.rel == "repository.yml"
    assert "Write repository: {id: lab, retired: [old-lab]} in anagraphe.yml" in problem.detail
    kept = repository_identity(root, DeclaredIdentity("lab", ("old-lab",))).problems[0]
    assert "Write" not in kept.detail and "delete repository.yml" in kept.detail
    retired = repository_identity(root, DeclaredIdentity("lab")).problems[0]
    assert "Write repository: {retired: [old-lab]}" in retired.detail


def test_retired_identifiers_listing_the_derived_one_are_a_configuration_error(
    tmp_path: Path,
) -> None:
    root = _repository(tmp_path / "old-lab", None)
    with pytest.raises(ConfigurationError, match="the identifier of the folder"):
        repository_identity(root, DeclaredIdentity(None, ("old-lab",)))


# --- The configuration.


def _configure(root: Path, section: object) -> Path:
    """Write a configuration declaring the section targets and the given section repository."""
    root.mkdir(parents=True, exist_ok=True)
    path = root / "anagraphe.yml"
    path.write_text(
        yaml.safe_dump(
            {"_schema": "anagraphe:configuration@3", "targets": {}, "repository": section}
        ),
        encoding="utf-8",
    )
    return path


def test_the_section_is_read_by_the_configuration(tmp_path: Path) -> None:
    config = load_config(tmp_path, _configure(tmp_path, {"id": "lab", "retired": ["old-lab"]}))
    assert config.repository == DeclaredIdentity("lab", ("old-lab",))
    assert config.targets is not None
    checker = TargetChecker(config.reading)
    assert (checker.repository, checker.identity.retired) == ("lab", ("old-lab",))


@pytest.mark.parametrize(
    ("section", "message"),
    [
        ({"id": "lab", "name": "Lab"}, "repository declares unknown keys: name"),
        ({"id": "Lab"}, "repository.id: 'Lab' lies outside the pattern"),
        ({"retired": ["a", "a"]}, "repository.retired lists a more than once"),
        ({"id": "lab", "retired": ["lab"]}, "never reused"),
        (["lab"], "repository must be a mapping"),
    ],
)
def test_an_invalid_section_is_a_configuration_error(
    tmp_path: Path, section: object, message: str
) -> None:
    with pytest.raises(ConfigurationError, match=message):
        load_config(tmp_path, _configure(tmp_path, section))


def test_the_command_line_stops_on_an_invalid_section(tmp_path: Path) -> None:
    _configure(tmp_path, {"id": "Lab"})
    result = CliRunner().invoke(app, ["targets", "check", "--root", str(tmp_path)])
    assert result.exit_code == 2
    assert "configuration: repository.id: 'Lab' lies outside the pattern" in result.output
