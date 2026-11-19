"""Behavioral tests for the Anagraphe application boundary."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from anagraphe_read._core.configuration import ConfigurationError

from anagraphe.cli import app
from anagraphe.configuration import load_config
import anagraphe.core.writes as writes
from anagraphe.indexes.configuration import IndexConfig
from anagraphe.indexes.service import run


def _indexes(root: Path) -> IndexConfig:
    """Load the section indexes of the fixture configuration."""
    config = load_config(root, root / "anagraphe.yml").indexes
    assert config is not None
    return config


def _write(path: Path, text: str) -> None:
    """Write one fixture file after creating its parent directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _repository(root: Path) -> None:
    """Create the smallest repository that exercises registry rendering."""
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "module.schema.yaml",
        "schema_version": 1,
        "type": "object",
        "x-default-mode": "registry",
        "properties": {
            "index_type": {"type": "string"},
            "groups": {"type": "array"},
        },
    }
    _write(root / "config" / "index-types" / "module.schema.yaml", yaml.safe_dump(schema))
    _write(
        root / "anagraphe.yml",
        "_schema: anagraphe:configuration@3\nindexes:\n  entry_point: _index.md\n"
        "  index_types: config/index-types\n  inspect_git: false\n",
    )
    _write(
        root / "notes" / "_index.md",
        "---\nrole: index\nstatus: stable\naliases: [Notes]\ntags: []\n"
        "index_type: module\ngroups:\n  - {id: '*', heading: Entries}\n---\n\n"
        "# Notes\n\n<!-- index groups -->\n<!-- /index -->\n",
    )
    _write(
        root / "notes" / "entry.md",
        "---\nrole: note\nstatus: stable\nindex: '[Notes](notes/_index.md)'\n"
        "aliases: [Entry]\ntags: []\npurpose: records one entry\n---\n\n# Entry\n",
    )


def test_check_reports_drift_without_writing(tmp_path: Path) -> None:
    """Check mode must preserve stale source bytes."""
    _repository(tmp_path)
    index = tmp_path / "notes" / "_index.md"
    before = index.read_text(encoding="utf-8")
    result = run(tmp_path, _indexes(tmp_path), "check")
    assert result.blocking_count == 1
    assert result.issues[-1].kind == "stale-block"
    assert index.read_text(encoding="utf-8") == before


def test_write_is_deterministic(tmp_path: Path) -> None:
    """A second write must produce no changed index."""
    _repository(tmp_path)
    config = _indexes(tmp_path)
    first = run(tmp_path, config, "write")
    rendered = (tmp_path / "notes" / "_index.md").read_text(encoding="utf-8")
    second = run(tmp_path, config, "write")
    assert first.blocking_count == 0
    assert "- [Entry](entry.md)\n" in rendered
    assert second.changed == ()


def test_cli_check_write_check_contract(tmp_path: Path) -> None:
    """The public commands must expose drift, repair it, and become idempotent."""
    _repository(tmp_path)
    runner = CliRunner()
    stale = runner.invoke(app, ["check", "--root", str(tmp_path)])
    written = runner.invoke(app, ["indexes", "write", "--root", str(tmp_path)])
    clean = runner.invoke(app, ["check", "--root", str(tmp_path)])
    repeated = runner.invoke(app, ["indexes", "write", "--root", str(tmp_path)])
    assert stale.exit_code == 1
    assert "stale-block: a block differs from its rendering; run anagraphe indexes write" in (
        stale.stdout
    )
    assert written.exit_code == 0
    assert clean.exit_code == 0
    assert "0 violations" in clean.stdout
    assert repeated.exit_code == 0


def test_blocking_issue_prevents_every_write(tmp_path: Path) -> None:
    """Write mode must not apply a valid change when another index is invalid."""
    _repository(tmp_path)
    _write(
        tmp_path / "broken" / "_index.md",
        "---\nrole: index\nstatus: stable\naliases: [Broken]\ntags: []\n"
        "index_type: unknown\ngroups:\n  - {id: '*'}\n---\n\n"
        "# Broken\n\n<!-- index groups -->\n<!-- /index -->\n",
    )
    index = tmp_path / "notes" / "_index.md"
    before = index.read_text(encoding="utf-8")
    result = run(tmp_path, _indexes(tmp_path), "write")
    assert result.blocking_count > 0
    assert index.read_text(encoding="utf-8") == before


def test_atomic_write_restores_replaced_indexes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed replacement must restore every index already replaced."""
    _repository(tmp_path)
    _write(
        tmp_path / "other" / "_index.md",
        "---\nrole: index\nstatus: stable\naliases: [Other]\ntags: []\n"
        "index_type: module\ngroups:\n  - {id: '*', heading: Entries}\n---\n\n"
        "# Other\n\n<!-- index groups -->\n<!-- /index -->\n",
    )
    _write(
        tmp_path / "other" / "entry.md",
        "---\nrole: note\nstatus: stable\nindex: '[Other](other/_index.md)'\n"
        "aliases: [Other entry]\ntags: []\npurpose: records another entry\n---\n\n"
        "# Other entry\n",
    )
    indexes = [tmp_path / "notes" / "_index.md", tmp_path / "other" / "_index.md"]
    before = {index: index.read_bytes() for index in indexes}
    replace = writes.os.replace
    calls = 0

    def fail_second_replacement(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected replacement failure")
        replace(source, target)

    monkeypatch.setattr(writes.os, "replace", fail_second_replacement)
    with pytest.raises(OSError, match="injected replacement failure"):
        run(tmp_path, _indexes(tmp_path), "write")
    assert {index: index.read_bytes() for index in indexes} == before


def test_atomic_write_creates_a_file_and_removes_it_on_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A created file takes the mode granted by the umask, and a later failure removes it."""
    writes.write_atomically(tmp_path, {"new.yml": "a: 1\n"})
    assert (tmp_path / "new.yml").read_text(encoding="utf-8") == "a: 1\n"
    assert (tmp_path / "new.yml").stat().st_mode & 0o777 == 0o666 & ~writes._umask()
    (tmp_path / "kept.yml").write_text("b: 1\n", encoding="utf-8")
    replace = writes.os.replace
    calls = 0

    def fail_second_replacement(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected replacement failure")
        replace(source, target)

    monkeypatch.setattr(writes.os, "replace", fail_second_replacement)
    with pytest.raises(OSError, match="injected replacement failure"):
        writes.write_atomically(tmp_path, {"created.yml": "c: 1\n", "kept.yml": "b: 2\n"})
    assert not (tmp_path / "created.yml").exists()
    assert (tmp_path / "kept.yml").read_text(encoding="utf-8") == "b: 1\n"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["kept.yml", "new.yml"]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (
            "indexes: {}\n",
            "anagraphe.yml declares no _schema: write _schema: anagraphe:configuration@3",
        ),
        (
            "_schema: anagraphe:configuration@4\nindexes: {}\n",
            "_schema must equal anagraphe:configuration@3, not anagraphe:configuration@4",
        ),
        ("_schema: 2\nindexes: {}\n", "_schema must equal anagraphe:configuration@3, not 2"),
        (
            "schema_version: 2\nindexes: {}\n",
            "schema_version is retired: write _schema: anagraphe:configuration@3",
        ),
        (
            "schema_version: 1\nindexes: {}\n",
            "write _schema: anagraphe:configuration@3 .*index keys under the section indexes",
        ),
        (
            "_schema: anagraphe:configuration@3\nschema_version: 2\nindexes: {}\n",
            "schema_version is retired",
        ),
    ],
)
def test_configuration_requires_its_format(tmp_path: Path, text: str, message: str) -> None:
    """A configuration of another format must fail before repository access."""
    _write(tmp_path / "anagraphe.yml", text)
    with pytest.raises(ConfigurationError, match=message):
        load_config(tmp_path, tmp_path / "anagraphe.yml")


def test_configuration_accepts_its_format(tmp_path: Path) -> None:
    """The identifier of the format, as a plain YAML scalar, must load."""
    _write(tmp_path / "anagraphe.yml", "_schema: anagraphe:configuration@3\nreferences: {}\n")
    assert load_config(tmp_path, tmp_path / "anagraphe.yml").references is not None


def test_cli_rejects_explicit_target_without_index(tmp_path: Path) -> None:
    """An explicit target must not pass when it resolves to no index."""
    _repository(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    result = CliRunner().invoke(app, ["indexes", "check", "--root", str(tmp_path), str(empty)])
    assert result.exit_code == 2
    assert "target: target resolves to no _index.md" in result.stderr
    unread = CliRunner().invoke(app, ["check", "--root", str(tmp_path), str(empty)])
    assert unread.exit_code == 2
    assert "the targets hold no file that a declared section reads" in unread.stderr


def test_cli_rejects_nonexistent_explicit_target(tmp_path: Path) -> None:
    """A misspelled explicit target must not produce a clean result."""
    _repository(tmp_path)
    result = CliRunner().invoke(app, ["check", "--root", str(tmp_path), "misspelled"])
    assert result.exit_code == 2
    assert "target does not exist" in result.stderr


def test_cli_rejects_a_section_without_entry_point(tmp_path: Path) -> None:
    """A missing renderer invariant must produce a configuration diagnostic."""
    _repository(tmp_path)
    config = tmp_path / "anagraphe.yml"
    config.write_text(
        config.read_text(encoding="utf-8").replace("  entry_point: _index.md\n", ""), "utf-8"
    )
    result = CliRunner().invoke(app, ["check", "--root", str(tmp_path)])
    assert result.exit_code == 2
    assert "indexes.entry_point must name the file of an index" in result.stderr


def test_cli_rejects_empty_index_type_directory(tmp_path: Path) -> None:
    """An absent default index type must produce a configuration diagnostic."""
    _repository(tmp_path)
    (tmp_path / "config" / "index-types" / "module.schema.yaml").unlink()
    result = CliRunner().invoke(app, ["check", "--root", str(tmp_path)])
    assert result.exit_code == 2
    assert "contains no schema files" in result.stderr


def test_cli_rejects_malformed_index_type_yaml(tmp_path: Path) -> None:
    """Malformed schema YAML must produce a configuration diagnostic."""
    _repository(tmp_path)
    _write(tmp_path / "config" / "index-types" / "module.schema.yaml", "$schema: [\n")
    result = CliRunner().invoke(app, ["check", "--root", str(tmp_path)])
    assert result.exit_code == 2
    assert "cannot parse index-type schema" in result.stderr


def test_cli_rejects_index_type_without_dialect(tmp_path: Path) -> None:
    """A schema without a recognized dialect must produce a configuration diagnostic."""
    _repository(tmp_path)
    _write(
        tmp_path / "config" / "index-types" / "module.schema.yaml",
        "$id: module.schema.yaml\ntype: object\nx-default-mode: registry\n",
    )
    result = CliRunner().invoke(app, ["check", "--root", str(tmp_path)])
    assert result.exit_code == 2
    assert "invalid index-type schemas" in result.stderr


def test_configuration_rejects_path_outside_repository(tmp_path: Path) -> None:
    """A repository-owned input must not resolve outside the repository root."""
    _write(
        tmp_path / "anagraphe.yml",
        "_schema: anagraphe:configuration@3\nindexes:\n  entry_point: _index.md\n"
        "  metadata_schema: ../outside.yml\n  index_types: config/index-types\n",
    )
    with pytest.raises(
        ConfigurationError, match="indexes.metadata_schema must stay inside the repository"
    ):
        load_config(tmp_path, tmp_path / "anagraphe.yml")
