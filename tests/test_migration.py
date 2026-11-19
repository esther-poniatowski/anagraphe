"""Behavioral tests of ``anagraphe records migrate``: the plan, the rewriting of the binding key in
each form of record, its byte-for-byte preservation, and the three modes of the command.

Each rejection of a plan, and each issue that blocks a migration, has a planted case; a valid
repository with records in every form migrates without any issue.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from typer.testing import CliRunner

from anagraphe.cli import CATALOGUES, app
from anagraphe.configuration import load_config
from anagraphe.core.configuration import ConfigurationError
from anagraphe.targets.migration import (
    KINDS,
    PLAN_CONTRACT,
    PLAN_FILE,
    PLAN_ID,
    MigrationService,
    PlanError,
    check_plan,
    read_plan,
)
from anagraphe.targets.resource import schema

PROJECT = Path(__file__).resolve().parent.parent
REGISTRY = (
    "_schema: kleisis:schema-registry@2\n"
    "schemas:\n"
    "  tool:note@2: schemas/note.schema.yml\n"
    "  tool:item@2: schemas/item.schema.yml\n"
    "exports: []\n"
)
#: The records of every form, each naming a contract that the plan replaces, with its comments,
#: its quoting and its order of keys.
RECORDS = {
    "notes/a.md": "---\n# the contract\nid: note-a\n_schema: tool:note@1  # kept\n---\n# A\n",
    "data/b.yml": "id: item-b\n_schema: 'tool:item@1'\nfields: [x, y]\n",
    "data/c.yaml": 'metadata: {id: item-c}\n_schema: "tool:item@1"\n',
    "data/d.json": '{\n  "_schema": "tool:item@1",\n  "metadata": {"id": "item-d"}\n}\n',
    "data/e.toml": '# a record\n_schema = "tool:item@1"\n\n[record]\nid = "item-e"\n',
    "data/kept.yml": "_schema: tool:other@1\nid: kept\n",
    "notes/plain.md": "# No frontmatter\n",
}
PLAN = (
    f"_schema: {PLAN_CONTRACT}\n"
    "contracts:\n"
    "  - {from: 'tool:note@1', to: 'tool:note@2'}\n"
    "  - {from: 'tool:item@1', to: 'tool:item@2'}\n"
)


def _write(root: Path, files: dict[str, str]) -> None:
    """Write files below a root, creating their folders, without translating line breaks."""
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))


def _repository(root: Path, files: dict[str, str] | None = None, records: bool = True) -> None:
    """Write a repository whose section targets declares the schema registry and a toml source."""
    declared: dict[str, Any] = {
        "_schema": "anagraphe:configuration@3",
        "metadata": [{"when": {"types": ["toml"]}, "from": {"toml": ["record"]}}],
        "targets": {"records": {"registry": "specs/schema-registry.yml"}} if records else {},
        "records": {},
        "repository": {"id": "lab"},
    }
    _write(
        root,
        {
            "anagraphe.yml": yaml.safe_dump(declared),
            "specs/schema-registry.yml": REGISTRY,
            "schemas/note.schema.yml": "properties:\n  _schema: {const: 'tool:note@2'}\n",
            "schemas/item.schema.yml": "properties:\n  _schema: {const: 'tool:item@2'}\n",
            "plan.yml": PLAN,
            **RECORDS,
            **(files or {}),
        },
    )


def _service(root: Path) -> MigrationService:
    config = load_config(root, root / "anagraphe.yml")
    assert config.targets is not None
    return MigrationService(root, config.targets, frozenset({"plan.yml", "record-registry.yml"}))


def _texts(root: Path) -> dict[str, bytes]:
    """Return the bytes of every file of a repository."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


# --- The plan.


def test_the_schema_of_the_plan_is_valid_and_identified() -> None:
    document = schema(PLAN_FILE)
    Draft202012Validator.check_schema(document)
    assert document["$id"] == PLAN_ID
    assert document["properties"]["_schema"]["const"] == PLAN_CONTRACT


def test_the_registry_of_anagraphe_exports_the_plan() -> None:
    registry = yaml.safe_load((PROJECT / "specs" / "schema-registry.yml").read_text("utf-8"))
    assert PLAN_CONTRACT in registry["exports"]
    assert (PROJECT / registry["schemas"][PLAN_CONTRACT]).name == PLAN_FILE


@pytest.mark.parametrize(
    ("contracts", "message"),
    [
        pytest.param([], "/contracts: [] should be non-empty", id="no-mapping"),
        pytest.param([{"from": "a:b@1"}], "/contracts/0: 'to' is a required", id="no-to"),
        pytest.param(
            [{"from": "a:b@1", "to": "a:b@2", "by": "x"}], "/contracts/0", id="another-key"
        ),
        pytest.param(
            [{"from": "A B", "to": "a:b@2"}],
            "/contracts/0/from: 'A B' is not a contract identifier",
            id="outside-the-grammar",
        ),
        pytest.param(
            [{"from": "a:b@1", "to": "a:b@1"}], "/contracts/0/from: a:b@1 maps to itself", id="same"
        ),
        pytest.param(
            [{"from": "a:b@1", "to": "a:b@2"}, {"from": "a:b@1", "to": "a:b@3"}],
            "/contracts/1/from: a:b@1 is listed twice",
            id="from-twice",
        ),
        pytest.param(
            [{"from": "a:b@2", "to": "a:b@3"}, {"from": "a:b@1", "to": "a:b@2"}],
            "/contracts/0/from: a:b@2 is the to of another mapping",
            id="to-also-from",
        ),
    ],
)
def test_an_invalid_plan_is_rejected(contracts: list[dict[str, str]], message: str) -> None:
    with pytest.raises(PlanError, match="the plan p.yml is invalid: ") as raised:
        check_plan({"_schema": PLAN_CONTRACT, "contracts": contracts}, "p.yml")
    assert message in str(raised.value)


def test_a_plan_of_another_contract_is_rejected() -> None:
    with pytest.raises(PlanError, match="/_schema: 'anagraphe:migration-plan@1' was expected"):
        check_plan({"_schema": "anagraphe:migration-plan@2", "contracts": []}, "p.yml")


def test_an_unparsable_plan_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "p.yml").write_text("contracts: [unclosed\n", encoding="utf-8")
    with pytest.raises(PlanError, match="the plan p.yml cannot be parsed"):
        read_plan(tmp_path / "p.yml", "p.yml")
    with pytest.raises(PlanError, match="the plan absent.yml cannot be read"):
        read_plan(tmp_path / "absent.yml", "absent.yml")


def test_a_to_absent_from_the_schema_registry_is_rejected(tmp_path: Path) -> None:
    _repository(tmp_path)
    plan = check_plan(
        {"_schema": PLAN_CONTRACT, "contracts": [{"from": "tool:note@1", "to": "tool:note@3"}]},
        "p.yml",
    )
    with pytest.raises(
        PlanError, match="/contracts/0/to: tool:note@3 is no contract of the schema registry"
    ):
        _service(tmp_path).plan(plan)


def test_a_migration_requires_a_schema_registry(tmp_path: Path) -> None:
    _repository(tmp_path, records=False)
    config = load_config(tmp_path, tmp_path / "anagraphe.yml")
    assert config.targets is not None
    with pytest.raises(ConfigurationError, match="declare targets.records.registry"):
        MigrationService(tmp_path, config.targets)


# --- The rewriting.


def test_every_form_of_record_is_rewritten_and_every_other_byte_kept(tmp_path: Path) -> None:
    _repository(tmp_path)
    before = _texts(tmp_path)
    service = _service(tmp_path)
    migration = service.plan(read_plan(tmp_path / "plan.yml", "plan.yml"))
    assert migration.issues == ()
    assert [(change.rel, change.line, change.old, change.new) for change in migration.changes] == [
        ("data/b.yml", 2, "tool:item@1", "tool:item@2"),
        ("data/c.yaml", 2, "tool:item@1", "tool:item@2"),
        ("data/d.json", 2, "tool:item@1", "tool:item@2"),
        ("data/e.toml", 2, "tool:item@1", "tool:item@2"),
        ("notes/a.md", 4, "tool:note@1", "tool:note@2"),
    ]
    assert service.apply(migration)
    after = _texts(tmp_path)
    changed = {rel for rel in before if before[rel] != after[rel]}
    assert changed == {"notes/a.md", "data/b.yml", "data/c.yaml", "data/d.json", "data/e.toml"}
    for rel in changed:
        old = "tool:note@1" if rel.endswith(".md") else "tool:item@1"
        expected = before[rel].replace(old.encode(), old.replace("@1", "@2").encode())
        assert after[rel] == expected, rel
    assert json.loads(after["data/d.json"])["_schema"] == "tool:item@2"


def test_the_mappings_apply_simultaneously(tmp_path: Path) -> None:
    """Each record takes the to of the contract that it names before the migration."""
    plan = (
        f"_schema: {PLAN_CONTRACT}\ncontracts:\n"
        "  - {from: 'tool:item@1', to: 'tool:note@2'}\n"
        "  - {from: 'tool:note@1', to: 'tool:item@2'}\n"
    )
    _repository(tmp_path, {"plan.yml": plan})
    service = _service(tmp_path)
    migration = service.plan(read_plan(tmp_path / "plan.yml", "plan.yml"))
    assert {change.rel: change.new for change in migration.changes}["notes/a.md"] == "tool:item@2"
    assert {change.rel: change.new for change in migration.changes}["data/b.yml"] == "tool:note@2"


def test_line_breaks_of_a_windows_file_are_kept(tmp_path: Path) -> None:
    _repository(tmp_path, {"data/b.yml": "id: item-b\r\n_schema: tool:item@1\r\nx: 1\r\n"})
    service = _service(tmp_path)
    assert service.apply(service.plan(read_plan(tmp_path / "plan.yml", "plan.yml")))
    assert (
        tmp_path / "data/b.yml"
    ).read_bytes() == b"id: item-b\r\n_schema: tool:item@2\r\nx: 1\r\n"


def test_the_plan_and_the_record_registry_are_never_rewritten(tmp_path: Path) -> None:
    plan = (
        f"_schema: {PLAN_CONTRACT}\ncontracts:\n"
        "  - {from: 'anagraphe:migration-plan@1', to: 'tool:note@2'}\n"
    )
    _repository(tmp_path, {"plan.yml": plan})
    migration = _service(tmp_path).plan(read_plan(tmp_path / "plan.yml", "plan.yml"))
    assert migration.changes == ()


@pytest.mark.parametrize(
    ("rel", "text", "reason"),
    [
        pytest.param(
            "notes/a.md",
            "---\r\nid: note-a\r\n_schema: tool:note@1\r\n---\r\n",
            "the frontmatter cannot be located",
            id="frontmatter-with-windows-line-breaks",
        ),
        pytest.param(
            "data/b.yml",
            "_schema: tool:other@1\n_schema: tool:item@1\n",
            "does not read as the record with its new contract",
            id="duplicate-key",
        ),
        pytest.param(
            "data/e.toml",
            "_schema = '''tool:item@1'''\n",
            "the value cannot be located at the top level",
            id="toml-multiline-literal",
        ),
    ],
)
def test_an_unmigratable_record_blocks_every_write(
    tmp_path: Path, rel: str, text: str, reason: str
) -> None:
    _repository(tmp_path, {rel: text})
    before = _texts(tmp_path)
    service = _service(tmp_path)
    migration = service.plan(read_plan(tmp_path / "plan.yml", "plan.yml"))
    assert [(issue.rel, issue.kind) for issue in migration.issues] == [(rel, "unmigratable-record")]
    assert reason in migration.issues[0].detail
    assert not service.apply(migration)
    assert _texts(tmp_path) == before


def test_an_unreadable_record_blocks_every_write(tmp_path: Path) -> None:
    _repository(tmp_path, {"data/broken.yml": "key: [unclosed\n"})
    before = _texts(tmp_path)
    service = _service(tmp_path)
    migration = service.plan(read_plan(tmp_path / "plan.yml", "plan.yml"))
    assert [(issue.rel, issue.kind) for issue in migration.issues] == [
        ("data/broken.yml", "unreadable-record")
    ]
    assert not service.apply(migration)
    assert _texts(tmp_path) == before


# --- The command line.


def _invoke(root: Path, *options: str) -> Any:
    return CliRunner().invoke(
        app, ["records", "migrate", "--plan", str(root / "plan.yml"), "--root", str(root), *options]
    )


def test_cli_applies_the_plan_and_reports_each_file(tmp_path: Path) -> None:
    _repository(tmp_path)
    result = _invoke(tmp_path)
    assert result.exit_code == 0, result.output
    assert "notes/a.md:4: _schema: tool:note@1 -> tool:note@2" in result.output
    assert "data/e.toml:2: _schema: tool:item@1 -> tool:item@2" in result.output
    assert "migrated 5 records" in result.output
    assert "_schema: tool:note@2  # kept" in (tmp_path / "notes/a.md").read_text(encoding="utf-8")
    again = _invoke(tmp_path, "--check")
    assert again.exit_code == 0, again.output


def test_cli_never_rewrites_the_plan_or_the_record_registry(tmp_path: Path) -> None:
    plan = (
        f"_schema: {PLAN_CONTRACT}\ncontracts:\n"
        "  - {from: 'anagraphe:migration-plan@1', to: 'tool:note@2'}\n"
        "  - {from: 'anagraphe:record-registry@1', to: 'tool:item@2'}\n"
    )
    registry = "_schema: anagraphe:record-registry@1\nrepository: lab\nrecords: {}\nretired: {}\n"
    _repository(tmp_path, {"plan.yml": plan, "record-registry.yml": registry})
    result = _invoke(tmp_path, "--dry-run")
    assert result.exit_code == 0, result.output
    assert "0 records to migrate in 0 files" in result.output


def test_cli_dry_run_lists_the_changes_and_writes_nothing(tmp_path: Path) -> None:
    _repository(tmp_path)
    before = _texts(tmp_path)
    result = _invoke(tmp_path, "--dry-run")
    assert result.exit_code == 0, result.output
    assert "data/d.json:2: _schema: tool:item@1 -> tool:item@2" in result.output
    assert "5 records to migrate in 5 files; dry run, no file changed" in result.output
    assert _texts(tmp_path) == before


def test_cli_check_fails_on_a_record_to_migrate(tmp_path: Path) -> None:
    _repository(tmp_path)
    before = _texts(tmp_path)
    result = _invoke(tmp_path, "--check", "--format", "sarif")
    assert result.exit_code == 1, result.output
    assert _texts(tmp_path) == before
    log = json.loads(result.stdout)
    found = sorted(
        (item["ruleId"], item["locations"][0]["logicalLocations"][0]["name"])
        for item in log["runs"][0]["results"]
    )
    assert found[0] == ("migration/pending-migration", "path:data/b.yml#/_schema")
    assert len(found) == 5


def test_cli_refuses_a_blocked_migration_and_an_invalid_plan(tmp_path: Path) -> None:
    _repository(tmp_path, {"data/broken.yml": "key: [unclosed\n"})
    before = _texts(tmp_path)
    blocked = _invoke(tmp_path)
    assert blocked.exit_code == 1, blocked.output
    assert "no file changed, since issues block the migration" in blocked.output
    assert _texts(tmp_path) == before
    (tmp_path / "plan.yml").write_text(f"_schema: {PLAN_CONTRACT}\ncontracts: []\n", "utf-8")
    invalid = _invoke(tmp_path)
    assert invalid.exit_code == 2
    assert "configuration: the plan " in invalid.output


@pytest.mark.parametrize(
    "options", [("--dry-run", "--check"), ("--format", "sarif")], ids=["two-modes", "sarif"]
)
def test_cli_refuses_conflicting_options(tmp_path: Path, options: tuple[str, ...]) -> None:
    _repository(tmp_path)
    assert _invoke(tmp_path, *options).exit_code == 2


def test_the_kinds_of_the_migration_are_in_the_catalogue() -> None:
    assert CATALOGUES["migration"] == KINDS
    assert {kind.kind for kind in KINDS} == {
        "pending-migration",
        "unmigratable-record",
        "unreadable-record",
    }
