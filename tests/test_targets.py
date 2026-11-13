"""Behavioral tests of the logical targets of ADR 0006.

The conformance cases of ``specs/conformance/targets.yml`` fix the readings of a target, the
matching of ``x-target-contract`` and one planted case per finding of the check, with a valid
repository on which every finding stays silent. The tests below run them, show that the reader
agrees with the definition ``target`` of the packaged resource, and cover what the cases cannot
state: the packaged schemas and registry, the schema defects, and the command line.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from typer.testing import CliRunner

from anagraphe.cli import app
from anagraphe.configuration import load_config
from anagraphe.core.configuration import ConfigurationError
from anagraphe.targets import (
    ADDRESSING_ID,
    REPOSITORY_CONTRACT,
    InvalidTarget,
    Target,
    TargetChecker,
    admits,
)
from anagraphe.targets import kinds as target_kinds
from anagraphe.targets.kinds import KINDS
from anagraphe.targets.resource import ADDRESSING_FILE, REPOSITORY_FILE, schema

PROJECT = Path(__file__).resolve().parent.parent
CASES_FILE = PROJECT / "specs" / "conformance" / "targets.yml"
SUITE: dict[str, Any] = yaml.safe_load(CASES_FILE.read_text(encoding="utf-8"))
READINGS = {case["id"]: case for case in SUITE["readings"]}
CONTRACTS = {case["id"]: case for case in SUITE["contracts"]}
CASES = {case["id"]: case for case in SUITE["cases"]}
#: The findings of the first version of ADR 0006, each with a planted case.
FIRST_VERSION = (
    "invalid-target",
    "invalid-identifier-declaration",
    "invalid-target-contract",
    "missing-identifier",
    "invalid-identifier",
    "duplicate-identifier",
    "invalid-repository-manifest",
    "legacy-repository-manifest",
    "unknown-record",
    "unknown-unit",
    "ambiguous-unit",
    "target-contract-mismatch",
    "unbound-target",
    "unverified-target",
)


def test_cases_name_the_resource_and_the_contract_of_the_package() -> None:
    assert (SUITE["resource"], SUITE["manifest"]) == (ADDRESSING_ID, REPOSITORY_CONTRACT)


# --- Readings and contracts.


@pytest.mark.parametrize("case_id", sorted(READINGS))
def test_reading_conforms(case_id: str) -> None:
    case = READINGS[case_id]
    if "invalid" in case:
        with pytest.raises(InvalidTarget) as raised:
            Target.parse(case["value"])
        assert raised.value.reason == case["invalid"]
    else:
        target = Target.parse(case["value"]).normalized(case["repository"])
        assert target.as_mapping() == case["normalized"]
        assert target == Target.parse(case["normalized"])


@pytest.mark.parametrize("case_id", sorted(READINGS))
def test_reader_agrees_with_the_definition_of_the_resource(case_id: str) -> None:
    """A value is a target exactly when the definition target of the resource validates it."""
    resource = schema(ADDRESSING_FILE)
    validator = Draft202012Validator({**resource, "$ref": "#/$defs/target"})
    assert validator.is_valid(READINGS[case_id]["value"]) == ("invalid" not in READINGS[case_id])


@pytest.mark.parametrize("case_id", sorted(CONTRACTS))
def test_contract_conforms(case_id: str) -> None:
    case = CONTRACTS[case_id]
    assert admits(case["entries"], case["contracts"]) is case["admits"]


# --- Check cases.


def _write(root: Path, files: dict[str, str]) -> None:
    """Write files below a root, creating their folders."""
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _check(root: Path, section: dict[str, Any] | None = None) -> list[list[str]]:
    """Check a repository under the section targets, and return its sorted issues."""
    declared = {
        "_schema": "anagraphe:configuration@2",
        "targets": SUITE["section"] if section is None else section,
    }
    (root / "anagraphe.yml").write_text(yaml.safe_dump(declared), encoding="utf-8")
    config = load_config(root, root / "anagraphe.yml").targets
    assert config is not None
    return sorted(
        [issue.rel, issue.kind, issue.locus] for issue in TargetChecker(root, config).check().issues
    )


@pytest.mark.parametrize("case_id", sorted(CASES))
def test_case_conforms(tmp_path: Path, case_id: str) -> None:
    case = CASES[case_id]
    shared = {
        rel: text for rel, text in SUITE["files"].items() if rel not in case.get("remove", [])
    }
    _write(tmp_path, {**shared, **case["files"]})
    assert _check(tmp_path) == case["issues"]


def test_every_first_version_finding_has_a_planted_case() -> None:
    planted = {issue[1] for case in CASES.values() for issue in case["issues"]}
    assert set(FIRST_VERSION) <= planted
    assert CASES["valid-repository"]["issues"] == []


def test_every_kind_constant_is_in_the_catalogue() -> None:
    constants = {
        value
        for name, value in vars(target_kinds).items()
        if name.isupper() and isinstance(value, str)
    }
    assert constants == {kind.kind for kind in KINDS}
    assert set(FIRST_VERSION) <= constants
    levels = {kind.kind: kind.level for kind in KINDS}
    assert (levels["legacy-repository-manifest"], levels["unverified-target"]) == (
        "warning",
        "note",
    )


def test_schema_defects_are_reported(tmp_path: Path) -> None:
    """An unresolved reference and an unreadable schema leave fields unread, so both are reported."""
    _write(
        tmp_path,
        {
            "registry.yml": (
                "_schema: kleisis:schema-registry@2\nschemas:\n"
                "  test:a@1: a.schema.yml\n  test:b@1: missing.schema.yml\n"
            ),
            "a.schema.yml": "properties:\n  x: {$ref: 'https://example.org/absent.yml'}\n",
        },
    )
    assert _check(tmp_path, {"records": {"registry": "registry.yml"}}) == [
        ["a.schema.yml", "unresolved-schema-reference", "/properties/x/$ref"],
        ["missing.schema.yml", "unreadable-schema", ""],
    ]


def test_a_check_without_registry_reads_identifiers_and_the_manifest(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "repository.yml": "schema_version: 1\nrepository: {id: lab}\n",
            "a.md": "---\nid: same\n---\n",
            "b.md": "---\nid: same\n---\n",
        },
    )
    assert _check(tmp_path, {}) == [
        ["a.md", "duplicate-identifier", "/id"],
        ["b.md", "duplicate-identifier", "/id"],
        ["repository.yml", "legacy-repository-manifest", "/schema_version"],
    ]


def test_a_misspelled_key_of_the_section_fails(tmp_path: Path) -> None:
    (tmp_path / "anagraphe.yml").write_text(
        "_schema: anagraphe:configuration@2\ntargets: {registry: r.yml}\n", encoding="utf-8"
    )
    with pytest.raises(ConfigurationError, match="targets declares unknown keys: registry"):
        load_config(tmp_path, tmp_path / "anagraphe.yml")


# --- Packaged schemas and registry.


def test_packaged_schemas_are_valid_and_identified() -> None:
    for name in (ADDRESSING_FILE, REPOSITORY_FILE):
        Draft202012Validator.check_schema(schema(name))
    assert schema(ADDRESSING_FILE)["$id"] == ADDRESSING_ID
    assert set(schema(ADDRESSING_FILE)["$defs"]) == {
        "repository-id",
        "record-id",
        "unit-id",
        "target",
    }
    assert schema(REPOSITORY_FILE)["properties"]["_schema"]["const"] == REPOSITORY_CONTRACT


def test_registry_maps_the_resource_and_the_contract_to_package_files() -> None:
    registry = yaml.safe_load((PROJECT / "specs" / "schema-registry.yml").read_text("utf-8"))
    assert registry["_schema"] == "kleisis:schema-registry@2"
    resource = PROJECT / registry["resources"][ADDRESSING_ID]
    assert yaml.safe_load(resource.read_text("utf-8"))["$id"] == ADDRESSING_ID
    contract = PROJECT / registry["schemas"][REPOSITORY_CONTRACT]
    assert contract.name == REPOSITORY_FILE and contract.parent == resource.parent
    assert registry["exports"] == [REPOSITORY_CONTRACT]


# --- The command line.


def _cli_repository(root: Path) -> None:
    """Write a repository holding one verified target, one target into another repository and a
    legacy manifest."""
    _write(root, SUITE["files"])
    _write(
        root,
        {
            "repository.yml": "schema_version: 1\nrepository: {id: lab}\n",
            "cite.yml": (
                "_schema: test:citing@1\nsource: {id: ada}\n"
                "cites:\n  - {repository: other-lab, id: x}\n"
            ),
            "anagraphe.yml": yaml.safe_dump(
                {"_schema": "anagraphe:configuration@2", "targets": SUITE["section"]}
            ),
        },
    )


def test_cli_prints_a_note_and_exits_cleanly_without_an_error(tmp_path: Path) -> None:
    _cli_repository(tmp_path)
    result = CliRunner().invoke(app, ["targets", "check", "--root", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert (
        "cite.yml:1: note: unverified-target: /cites/0: {repository: other-lab, id: x}"
        in result.output
    )
    assert "repository.yml:1: warning: legacy-repository-manifest:" in result.output
    assert "0 violations, 1 warnings, 1 notes" in result.output


def test_cli_check_writes_the_levels_of_the_targets(tmp_path: Path) -> None:
    _cli_repository(tmp_path)
    (tmp_path / "people" / "dup.md").write_text("---\nid: ada\n---\n", encoding="utf-8")
    result = CliRunner().invoke(app, ["check", "--root", str(tmp_path), "--format", "sarif"])
    assert result.exit_code == 1
    log = json.loads(result.stdout)
    levels = sorted(
        (item["ruleId"], item["level"], item["locations"][0]["logicalLocations"][0]["name"])
        for item in log["runs"][0]["results"]
    )
    assert levels == [
        ("targets/duplicate-identifier", "error", "path:people/ada.yml#/identity/id"),
        ("targets/duplicate-identifier", "error", "path:people/dup.md#/id"),
        ("targets/legacy-repository-manifest", "warning", "path:repository.yml#/schema_version"),
        ("targets/unverified-target", "note", "path:cite.yml#/cites/0"),
    ]
