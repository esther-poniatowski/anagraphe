"""Behavioral tests for the Anagraphe application boundary."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

import anagraphe.application as application
from anagraphe.application import run
from anagraphe.cli import app
from anagraphe.configuration import ConfigurationError, load_config


def _write(path: Path, text: str) -> None:
    """Write one fixture file after creating its parent directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _repository(root: Path) -> None:
    """Create the smallest repository that exercises registry rendering."""
    vocabulary = {
        "schema": {"entry_point": "_index.md"},
        "roles": {"index": {}, "note": {}},
        "cites": {"relations": {"uses-definition-from": {}}},
    }
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
    _write(root / "config" / "vocabulary.yml", yaml.safe_dump(vocabulary))
    _write(root / "config" / "index-types" / "module.schema.yaml", yaml.safe_dump(schema))
    _write(
        root / "anagraphe.yml",
        "schema_version: 1\nvocabulary: config/vocabulary.yml\n"
        "index_types: config/index-types\ninspect_git: false\n",
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
    result = run(tmp_path, load_config(tmp_path, tmp_path / "anagraphe.yml"), "check")
    assert result.blocking_count == 1
    assert result.issues[-1].kind == "stale-block"
    assert index.read_text(encoding="utf-8") == before


def test_write_is_deterministic(tmp_path: Path) -> None:
    """A second write must produce no changed index."""
    _repository(tmp_path)
    config = load_config(tmp_path, tmp_path / "anagraphe.yml")
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
    written = runner.invoke(app, ["write", "--root", str(tmp_path)])
    clean = runner.invoke(app, ["check", "--root", str(tmp_path)])
    repeated = runner.invoke(app, ["write", "--root", str(tmp_path)])
    assert stale.exit_code == 1
    assert "stale-block" in stale.stdout
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
    result = run(tmp_path, load_config(tmp_path, tmp_path / "anagraphe.yml"), "write")
    assert result.blocking_count > 0
    assert index.read_text(encoding="utf-8") == before


def test_external_url_citation_is_not_resolved_as_local_file(tmp_path: Path) -> None:
    """An HTTP citation must retain body evidence without requiring a repository file."""
    _repository(tmp_path)
    _write(
        tmp_path / "notes" / "entry.md",
        "---\nrole: note\nstatus: stable\nindex: '[Notes](notes/_index.md)'\n"
        "aliases: [Entry]\ntags: []\npurpose: records one entry\n"
        "cites:\n"
        "  - relation: uses-definition-from\n"
        "    target: '[External definition](https://example.org/definition)'\n"
        "---\n\n# Entry\n\n"
        "The [external definition](https://example.org/definition) fixes the terms.\n",
    )
    result = run(tmp_path, load_config(tmp_path, tmp_path / "anagraphe.yml"), "check")
    kinds = {issue.kind for issue in result.issues}
    assert "unknown-target" not in kinds
    assert "missing-evidence" not in kinds


def test_missing_local_citation_target_remains_blocking(tmp_path: Path) -> None:
    """A missing repository citation must still fail after external links are admitted."""
    _repository(tmp_path)
    _write(
        tmp_path / "notes" / "entry.md",
        "---\nrole: note\nstatus: stable\nindex: '[Notes](notes/_index.md)'\n"
        "aliases: [Entry]\ntags: []\npurpose: records one entry\n"
        "cites:\n"
        "  - relation: uses-definition-from\n"
        "    target: '[Missing](notes/missing.md)'\n"
        "---\n\n# Entry\n\nThe [missing note](missing.md) fixes the terms.\n",
    )
    result = run(tmp_path, load_config(tmp_path, tmp_path / "anagraphe.yml"), "check")
    assert any(issue.kind == "unknown-target" and issue.blocking for issue in result.issues)


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
    replace = application.os.replace
    calls = 0

    def fail_second_replacement(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected replacement failure")
        replace(source, target)

    monkeypatch.setattr(application.os, "replace", fail_second_replacement)
    with pytest.raises(OSError, match="injected replacement failure"):
        run(tmp_path, load_config(tmp_path, tmp_path / "anagraphe.yml"), "write")
    assert {index: index.read_bytes() for index in indexes} == before


def test_configuration_requires_version_one(tmp_path: Path) -> None:
    """An unsupported configuration version must fail before repository access."""
    _write(tmp_path / "anagraphe.yml", "schema_version: 2\n")
    try:
        load_config(tmp_path, tmp_path / "anagraphe.yml")
    except ConfigurationError as error:
        assert str(error) == "schema_version must equal 1"
    else:
        raise AssertionError("an unsupported schema version was accepted")


def test_cli_rejects_explicit_target_without_index(tmp_path: Path) -> None:
    """An explicit target must not pass when it resolves to no index."""
    _repository(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    result = CliRunner().invoke(app, ["check", "--root", str(tmp_path), str(empty)])
    assert result.exit_code == 2
    assert "target resolves to no _index.md" in result.stderr


def test_cli_rejects_nonexistent_explicit_target(tmp_path: Path) -> None:
    """A misspelled explicit target must not produce a clean result."""
    _repository(tmp_path)
    result = CliRunner().invoke(app, ["check", "--root", str(tmp_path), "misspelled"])
    assert result.exit_code == 2
    assert "target does not exist" in result.stderr


def test_cli_rejects_incomplete_vocabulary(tmp_path: Path) -> None:
    """A missing renderer invariant must produce a configuration diagnostic."""
    _repository(tmp_path)
    _write(tmp_path / "config" / "vocabulary.yml", "roles: {}\n")
    result = CliRunner().invoke(app, ["check", "--root", str(tmp_path)])
    assert result.exit_code == 2
    assert "must declare schema as a mapping" in result.stderr


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
        "schema_version: 1\nvocabulary: ../outside.yml\nindex_types: config/index-types\n",
    )
    with pytest.raises(ConfigurationError, match="vocabulary must stay inside the repository"):
        load_config(tmp_path, tmp_path / "anagraphe.yml")
