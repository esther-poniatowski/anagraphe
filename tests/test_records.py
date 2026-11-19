"""Behavioral tests of the record registry of ADR 0007.

The conformance cases of ``specs/conformance/record-registry.yml`` fix the reading of a registry
under its contract, one planted case per finding of ``anagraphe records check``, and the findings
``renamed-target`` and ``retired-target`` of ``anagraphe targets check``. The tests below run them,
and cover what the cases cannot state: the generation and its refusals, the retirement and its
refusals, the written form, the packaged schema and registry, and the command line.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from typer.testing import CliRunner

from anagraphe.cli import CATALOGUES, app
from anagraphe.configuration import RepositoryConfig, load_config
from anagraphe.core.configuration import ConfigurationError
from anagraphe.targets import TargetChecker
from anagraphe.targets.kinds import KINDS as TARGET_KINDS
from anagraphe.targets.registry import (
    REGISTRY_CONTRACT,
    REGISTRY_ID,
    Entry,
    Format,
    RecordRegistry,
    RegistryService,
    Retirement,
    RetireRefused,
)
from anagraphe.targets.registry import kinds as registry_kinds
from anagraphe.targets.registry.contract import REGISTRY_FILE, read_registry
from anagraphe.targets.registry.kinds import KINDS
from anagraphe.targets.resource import schema

PROJECT = Path(__file__).resolve().parent.parent
CASES_FILE = PROJECT / "specs" / "conformance" / "record-registry.yml"
SUITE: dict[str, Any] = yaml.safe_load(CASES_FILE.read_text(encoding="utf-8"))
DOCUMENTS = {case["id"]: case for case in SUITE["documents"]}
CASES = {case["id"]: case for case in SUITE["cases"]}
REGISTRY = "record-registry.yml"
#: The findings of ADR 0007, each with a planted case.
FINDINGS = (
    "invalid-record-registry",
    "stale-registry",
    "vanished-identifier",
    "reused-identifier",
    "unknown-successor",
    "renamed-target",
    "retired-target",
)
#: The day given by the clock of every retirement of the tests.
TODAY = datetime.date(2026, 11, 15)


def test_cases_name_the_contract_of_the_package() -> None:
    assert (SUITE["contract"], SUITE["schema"]) == (REGISTRY_CONTRACT, REGISTRY_ID)


# --- Documents.


@pytest.mark.parametrize("case_id", sorted(DOCUMENTS))
def test_document_conforms(case_id: str, tmp_path: Path) -> None:
    case = DOCUMENTS[case_id]
    (tmp_path / REGISTRY).write_text(case["text"], encoding="utf-8")
    reading = read_registry(tmp_path / REGISTRY, REGISTRY)
    assert [problem.pointer for problem in reading.problems] == case["invalid"]
    assert (reading.registry is None) == bool(case["invalid"])


def test_a_date_is_read_as_the_string_that_it_writes(tmp_path: Path) -> None:
    (tmp_path / REGISTRY).write_text(DOCUMENTS["written-form-of-the-decision"]["text"], "utf-8")
    registry = read_registry(tmp_path / REGISTRY, REGISTRY).registry
    assert registry is not None
    assert registry.retired == {
        "former-id": Retirement("2026-11-20", "mixture-input"),
        "removed-id": Retirement("2026-11-21"),
    }


def test_the_written_form_of_the_decision_is_the_rendering(tmp_path: Path) -> None:
    """The example of ADR 0007 is the exact text that the writer produces for its content."""
    text = DOCUMENTS["written-form-of-the-decision"]["text"]
    (tmp_path / REGISTRY).write_text(text, encoding="utf-8")
    registry = read_registry(tmp_path / REGISTRY, REGISTRY).registry
    assert registry is not None
    assert registry.render() == text


def test_rendering_sorts_by_characters_and_quotes_ambiguous_scalars() -> None:
    entries = {
        identifier: Entry(f"notes/{identifier}.md", Format.MARKDOWN)
        for identifier in ("ab", "a_b", "a1", "a.b", "a-b", "2024", "true")
    }
    text = RecordRegistry("lab", entries, {}).render()
    keys = [line.split(":")[0].strip() for line in text.splitlines() if line.startswith("  ")]
    assert keys == ["'2024'", "a-b", "a.b", "a1", "a_b", "ab", "'true'"]
    data = yaml.safe_load(text)
    assert all(isinstance(key, str) for key in data["records"])


# --- Check cases.


def _write(root: Path, files: dict[str, str]) -> None:
    """Write files below a root, creating their folders."""
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _configure(root: Path, sections: dict[str, Any] | None = None) -> RepositoryConfig:
    """Declare the sections of anagraphe.yml, by default those of the cases, and load them."""
    declared = {"_schema": "anagraphe:configuration@2", **(sections or SUITE["sections"])}
    (root / "anagraphe.yml").write_text(yaml.safe_dump(declared), encoding="utf-8")
    return load_config(root, root / "anagraphe.yml")


def _service(root: Path, clock: datetime.date = TODAY) -> RegistryService:
    """Return the registry service of a repository whose sections are those of the cases."""
    config = _configure(root)
    assert config.targets is not None and config.records is not None
    return RegistryService(
        root, config.targets, config.records, clock=lambda: clock, declared=config.repository
    )


def _repository(
    root: Path, files: dict[str, str] | None = None, remove: tuple[str, ...] = ()
) -> None:
    """Write the shared files of the cases, without those removed, then the given files."""
    shared = {rel: text for rel, text in SUITE["files"].items() if rel not in remove}
    _write(root, {**shared, **(files or {})})


@pytest.mark.parametrize("case_id", sorted(CASES))
def test_case_conforms(tmp_path: Path, case_id: str) -> None:
    case = CASES[case_id]
    _repository(tmp_path, case["files"], tuple(case.get("remove", ())))
    config = _configure(tmp_path, case.get("sections"))
    assert config.targets is not None
    if case["check"] == "records":
        assert config.records is not None
        report = RegistryService(
            tmp_path, config.targets, config.records, declared=config.repository
        ).check()
    else:
        report = TargetChecker(
            tmp_path, config.targets, config.records, declared=config.repository
        ).check()
    issues = sorted([issue.rel, issue.kind, issue.locus] for issue in report.issues)
    assert issues == case["issues"]


def test_every_finding_has_a_planted_case() -> None:
    planted = {issue[1] for case in CASES.values() for issue in case["issues"]}
    assert set(FINDINGS) <= planted
    assert CASES["valid-registry"]["issues"] == []


def test_every_kind_constant_is_in_the_catalogue() -> None:
    constants = {
        value
        for name, value in vars(registry_kinds).items()
        if name.isupper() and isinstance(value, str)
    }
    assert constants == {kind.kind for kind in KINDS} == set(FINDINGS[:5])
    assert all(kind.level == "error" for kind in KINDS)
    levels = {kind.kind: kind.level for kind in TARGET_KINDS}
    assert (levels["renamed-target"], levels["retired-target"]) == ("warning", "error")
    assert CATALOGUES["records"] == KINDS


def test_a_followed_rename_names_its_successor(tmp_path: Path) -> None:
    _repository(tmp_path, {"cite.yml": "_schema: test:citing@1\nsource: {id: note-old, unit: x}\n"})
    config = _configure(tmp_path)
    assert config.targets is not None
    details = {
        issue.kind: issue.detail
        for issue in TargetChecker(
            tmp_path, config.targets, config.records, declared=config.repository
        )
        .check()
        .issues
    }
    assert details["renamed-target"] == (
        "/source: {id: note-old, unit: x}: the identifier note-old is retired and replaced by "
        "note-n through note-mid; write {id: note-n, unit: x}"
    )
    assert "the record notes/n.md declares no unit of the identifier x" in details["unknown-unit"]


# --- Write.


def _bytes(path: Path) -> bytes | None:
    """Return the bytes of a file, None when it is absent."""
    return path.read_bytes() if path.is_file() else None


def test_write_generates_the_registry_and_carries_the_retired_identifiers(tmp_path: Path) -> None:
    _repository(
        tmp_path,
        {"notes/new.md": "---\nid: new\n---\n", "data/z.json": '{"metadata": {"id": "z"}}'},
    )
    result = _service(tmp_path).write()
    assert result.issues == () and result.changed
    written = (tmp_path / REGISTRY).read_text(encoding="utf-8")
    expected = SUITE["files"][REGISTRY].replace(
        "  note-n: {path: notes/n.md, format: markdown}\n",
        "  new: {path: notes/new.md, format: markdown}\n"
        "  note-n: {path: notes/n.md, format: markdown}\n"
        "  z: {path: data/z.json, format: json}\n",
    )
    assert written == expected


def test_writing_twice_yields_identical_bytes(tmp_path: Path) -> None:
    _repository(tmp_path, remove=(REGISTRY,))
    first = _service(tmp_path).write()
    written = _bytes(tmp_path / REGISTRY)
    second = _service(tmp_path).write()
    assert first.changed and not second.changed
    assert _bytes(tmp_path / REGISTRY) == written
    assert _service(tmp_path).check().issues == ()


def test_write_creates_the_folders_of_its_path(tmp_path: Path) -> None:
    _repository(tmp_path, remove=(REGISTRY,))
    sections = {**SUITE["sections"], "records": {"path": "build/registry/records.yml"}}
    config = _configure(tmp_path, sections)
    assert config.targets is not None and config.records is not None
    result = RegistryService(
        tmp_path, config.targets, config.records, declared=config.repository
    ).write()
    assert result.changed and (tmp_path / "build" / "registry" / "records.yml").is_file()


#: Each planted defect that blocks a write, with the kinds that the refused write reports.
REFUSED_WRITES: dict[str, tuple[dict[str, str], tuple[str, ...], list[str]]] = {
    "missing-identifier": (
        {"people/cy.yml": "_schema: test:person@1\nidentity: {name: Cy}\n"},
        (),
        ["missing-identifier"],
    ),
    "invalid-identifier": (
        {"notes/bad.md": "---\nid: Not Valid\n---\n"},
        (),
        ["invalid-identifier"],
    ),
    "duplicate-identifier": (
        {"notes/dup.md": "---\nid: ada\n---\n"},
        (),
        ["duplicate-identifier", "duplicate-identifier"],
    ),
    "retired-identifier": ({"notes/again.md": "---\nid: gone\n---\n"}, (), ["reused-identifier"]),
    "vanished-identifier": (
        {},
        ("notes/n.md",),
        ["unknown-successor", "vanished-identifier"],
    ),
    "unreadable-record": ({"notes/broken.md": "---\nid: broken\n"}, (), ["unreadable-record"]),
    "unknown-successor": (
        {
            REGISTRY: SUITE["files"][REGISTRY].replace(
                "  gone: {date: 2026-11-02}\n", "  gone: {date: 2026-11-02, replaced_by: nowhere}\n"
            )
        },
        (),
        ["unknown-successor"],
    ),
    "invalid-registry": ({REGISTRY: "records: [\n"}, (), ["invalid-record-registry"]),
    # The record people/ada.yml declares ada through its schema, which cannot be read, so ada
    # seems to vanish and the successor of a retired identifier seems unknown.
    "unreadable-schema": (
        {},
        ("schemas/person.schema.yml",),
        ["unknown-successor", "unreadable-schema", "vanished-identifier"],
    ),
    # The section repository is left out, and the folder of a test, named after the test, holds an
    # underscore, which the pattern repository-id rejects; the root has no remote.
    "repository-without-identity": ({}, (), ["unidentified-repository"]),
}


@pytest.mark.parametrize("defect", sorted(REFUSED_WRITES))
def test_write_refuses_a_defect_and_writes_nothing(tmp_path: Path, defect: str) -> None:
    files, remove, kinds = REFUSED_WRITES[defect]
    _repository(tmp_path, files, remove)
    before = _bytes(tmp_path / REGISTRY)
    sections = SUITE["sections"]
    if defect == "repository-without-identity":
        sections = {key: value for key, value in sections.items() if key != "repository"}
    config = _configure(tmp_path, sections)
    assert config.targets is not None and config.records is not None
    result = RegistryService(
        tmp_path, config.targets, config.records, declared=config.repository
    ).write()
    assert sorted(issue.kind for issue in result.issues) == kinds
    assert result.registry is None and not result.changed
    assert _bytes(tmp_path / REGISTRY) == before


# --- Retire.


def _rename(root: Path, old: str, new: str) -> None:
    """Change the identifier of the note holding ``old`` to ``new``."""
    path = root / "notes" / "n.md"
    path.write_text(path.read_text(encoding="utf-8").replace(f"id: {old}", f"id: {new}"), "utf-8")


def test_retire_moves_the_identifier_with_the_day_and_the_successor(tmp_path: Path) -> None:
    _repository(tmp_path)
    _rename(tmp_path, "note-n", "note-new")
    registry = _service(tmp_path).retire("note-n", "note-new")
    assert "note-n" not in registry.records
    assert registry.retired["note-n"] == Retirement("2026-11-15", "note-new")
    assert read_registry(tmp_path / REGISTRY, REGISTRY).registry == registry
    assert _service(tmp_path).write().changed
    assert _service(tmp_path).check().issues == ()
    assert "  note-n: {date: 2026-11-15, replaced_by: note-new}\n" in (
        tmp_path / REGISTRY
    ).read_text("utf-8")


def test_retire_without_a_successor(tmp_path: Path) -> None:
    _repository(tmp_path, remove=("notes/n.md",))
    registry = _service(tmp_path, datetime.date(2027, 1, 2)).retire("note-n")
    assert registry.retired["note-n"] == Retirement("2027-01-02")


def _refusal(root: Path, identifier: str, successor: str | None = None) -> str:
    """Return the reason why a retirement is refused, after checking that it wrote nothing."""
    before = _bytes(root / REGISTRY)
    with pytest.raises(RetireRefused) as raised:
        _service(root).retire(identifier, successor)
    assert _bytes(root / REGISTRY) == before
    return str(raised.value)


def test_retire_refuses_an_identifier_that_a_record_holds(tmp_path: Path) -> None:
    _repository(tmp_path)
    assert (
        _refusal(tmp_path, "ada")
        == "ada is held by people/ada.yml; change the identifier of the record first"
    )


def test_retire_refuses_an_identifier_already_retired(tmp_path: Path) -> None:
    _repository(tmp_path)
    assert _refusal(tmp_path, "gone") == "gone was already retired on 2026-11-02"


def test_retire_refuses_an_identifier_absent_from_records(tmp_path: Path) -> None:
    _repository(tmp_path)
    assert _refusal(tmp_path, "ghost") == "records lists no identifier ghost"


def test_retire_refuses_an_unknown_successor(tmp_path: Path) -> None:
    _repository(tmp_path, remove=("notes/n.md",))
    assert "the successor nowhere is neither a record" in _refusal(tmp_path, "note-n", "nowhere")


def test_retire_refuses_a_successor_closing_a_cycle(tmp_path: Path) -> None:
    """note-mid is replaced by note-n, so retiring note-n for note-mid would close a cycle."""
    _repository(tmp_path, remove=("notes/n.md",))
    assert "would close a cycle" in _refusal(tmp_path, "note-n", "note-mid")


def test_retire_admits_a_retired_successor_reaching_a_record(tmp_path: Path) -> None:
    _repository(tmp_path, remove=("people/ada.yml",))
    registry = _service(tmp_path).retire("ada", "note-mid")
    assert registry.retired["ada"] == Retirement("2026-11-15", "note-mid")


def test_retire_refuses_an_absent_or_invalid_registry(tmp_path: Path) -> None:
    _repository(tmp_path, remove=(REGISTRY,))
    assert "does not exist; run anagraphe records write first" in _refusal(tmp_path, "note-n")
    (tmp_path / REGISTRY).write_text("records: [\n", encoding="utf-8")
    assert "is invalid" in _refusal(tmp_path, "note-n")


def test_retire_refuses_while_a_schema_cannot_be_read(tmp_path: Path) -> None:
    """A schema that cannot be read hides the identifier ada, which its record still holds."""
    _repository(tmp_path, remove=("schemas/person.schema.yml",))
    assert "a schema of the registry cannot be read" in _refusal(tmp_path, "ada")


# --- Configuration.


def test_the_section_defaults_to_the_root_file(tmp_path: Path) -> None:
    config = _configure(tmp_path, {"targets": {}, "records": {}})
    assert config.records is not None
    assert (config.records.rel, config.records.path) == (REGISTRY, (tmp_path / REGISTRY).resolve())


@pytest.mark.parametrize(
    ("records", "message"),
    [
        ({"file": "r.yml"}, "records declares unknown keys: file"),
        ({"path": "../r.yml"}, "records.path must stay inside the repository"),
        ({"path": "."}, "records.path must name a file"),
    ],
)
def test_an_invalid_section_fails(tmp_path: Path, records: dict[str, str], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        _configure(tmp_path, {"targets": {}, "records": records})


def test_the_section_requires_the_section_targets(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="declare targets"):
        _configure(tmp_path, {"records": {}})


# --- Packaged schema and registry.


def test_packaged_schema_is_valid_and_identified() -> None:
    contract = schema(REGISTRY_FILE)
    Draft202012Validator.check_schema(contract)
    assert contract["$id"] == REGISTRY_ID
    assert contract["properties"]["_schema"]["const"] == REGISTRY_CONTRACT


def test_registry_of_the_package_exports_the_contract() -> None:
    registry = yaml.safe_load((PROJECT / "specs" / "schema-registry.yml").read_text("utf-8"))
    path = PROJECT / registry["schemas"][REGISTRY_CONTRACT]
    assert yaml.safe_load(path.read_text("utf-8"))["$id"] == REGISTRY_ID
    assert REGISTRY_CONTRACT in registry["exports"]
    resources = yaml.safe_load((PROJECT / "specs" / "schema-resources.yml").read_text("utf-8"))
    assert REGISTRY_CONTRACT in resources["exports"]


# --- The command line.


def _invoke(*arguments: str) -> Any:
    """Run the command line on its arguments."""
    return CliRunner().invoke(app, list(arguments))


def test_cli_write_then_check(tmp_path: Path) -> None:
    _repository(tmp_path, {"notes/new.md": "---\nid: new\n---\n"})
    _configure(tmp_path)
    checked = _invoke("records", "check", "--root", str(tmp_path))
    assert checked.exit_code == 1
    assert (
        "record-registry.yml:1: stale-registry: /records/new: the record notes/new.md holds new, "
        "which records omits; run anagraphe records write"
    ) in checked.output
    written = _invoke("records", "write", "--root", str(tmp_path))
    assert written.exit_code == 0, written.output
    assert (
        "records: wrote record-registry.yml, with 3 records and 5 retired identifiers"
        in written.output
    )
    assert _invoke("records", "check", "--root", str(tmp_path)).exit_code == 0


def test_cli_write_reports_what_blocks_it(tmp_path: Path) -> None:
    _repository(tmp_path, remove=("notes/n.md",))
    _configure(tmp_path)
    result = _invoke("records", "write", "--root", str(tmp_path))
    assert result.exit_code == 1
    assert (
        "record-registry.yml:1: vanished-identifier: /records/note-n: no record holds"
        in result.output
    )
    assert "records: wrote no record-registry.yml, since issues block the write" in result.output


def test_cli_retire_and_its_refusal(tmp_path: Path) -> None:
    _repository(tmp_path, remove=("notes/n.md",))
    _configure(tmp_path)
    refused = _invoke(
        "records", "retire", "note-n", "--replaced-by", "nowhere", "--root", str(tmp_path)
    )
    assert refused.exit_code == 1
    assert "records: cannot retire note-n: the successor nowhere" in refused.output
    retired = _invoke("records", "retire", "note-n", "--root", str(tmp_path))
    assert retired.exit_code == 0, retired.output
    assert (
        f"records: retired note-n on {datetime.date.today().isoformat()}, in record-registry.yml"
        in retired.output
    )


def test_cli_records_requires_its_section(tmp_path: Path) -> None:
    _configure(tmp_path, {"targets": {}})
    result = _invoke("records", "check", "--root", str(tmp_path))
    assert result.exit_code == 2
    assert "anagraphe.yml declares no section records" in result.output


def test_cli_writes_the_sarif_result_of_one_finding(tmp_path: Path) -> None:
    _repository(tmp_path, remove=("notes/n.md",))
    _configure(tmp_path)
    result = _invoke("records", "check", "--root", str(tmp_path), "--format", "sarif")
    assert result.exit_code == 1
    run = json.loads(result.stdout)["runs"][0]
    findings = {item["ruleId"]: item for item in run["results"]}
    vanished = findings["records/vanished-identifier"]
    assert vanished["level"] == "error"
    assert vanished["locations"][0]["logicalLocations"] == [
        {"name": "path:record-registry.yml#/records/note-n"}
    ]
    assert vanished["locations"][0]["physicalLocation"] == {
        "artifactLocation": {"uri": "record-registry.yml", "uriBaseId": "SRCROOT"}
    }
    assert run["invocations"] == [{"executionSuccessful": True}]
    rules = {rule["id"] for rule in run["tool"]["driver"]["rules"]}
    assert {f"records/{kind.kind}" for kind in KINDS} <= rules


def test_cli_declares_an_invalid_registry_incomplete(tmp_path: Path) -> None:
    _repository(tmp_path, {REGISTRY: "records: [\n"})
    _configure(tmp_path)
    result = _invoke("records", "check", "--root", str(tmp_path), "--format", "sarif")
    assert json.loads(result.stdout)["runs"][0]["invocations"][0]["executionSuccessful"] is False


def test_cli_check_runs_the_records_and_reads_the_retired_identifiers(tmp_path: Path) -> None:
    _repository(tmp_path, {"cite.yml": "_schema: test:citing@1\nprofile: {id: ada-old}\n"})
    _configure(tmp_path)
    result = _invoke("check", "--root", str(tmp_path), "--format", "sarif")
    assert result.exit_code == 0, result.output
    results = json.loads(result.stdout)["runs"][0]["results"]
    assert [(item["ruleId"], item["level"]) for item in results] == [
        ("targets/renamed-target", "warning")
    ]
    assert "records: checked record-registry.yml against 2 records" in result.stderr
