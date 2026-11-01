"""Behavioral tests for the declared types of the files that an index lists."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from anagraphe.cli import app
from anagraphe.configuration import load_config
from anagraphe.core.configuration import ConfigurationError
from anagraphe.indexes.service import RunResult, run
from anagraphe.refactor import MoveService

#: A rendered entry, capturing the path of its link.
ENTRY = re.compile(r"^\s*- \[[^\]]*\]\(([^)]+)\)", re.MULTILINE)
#: The index of the folder ``m``, listing every member under one heading.
INDEX = (
    "---\naliases: [Module]\ngroups:\n  - {id: '*', heading: Entries}\n---\n\n# Module\n\n"
    "<!-- index groups -->\n<!-- /index -->\n"
)
NOTE = "---\naliases: [Note]\nindex: '[Module](m/_index.md)'\n---\n\n# Note\n"


def _write(root: Path, files: dict[str, str]) -> None:
    """Write fixture files below a repository root."""
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8") if isinstance(text, str) else text)


def _repository(
    root: Path, files: dict[str, Any], top: dict[str, Any] | None = None, **section: Any
) -> None:
    """Write an indexed folder ``m``, the given files, and a configuration of the indexes."""
    _write(
        root,
        {
            "config/vocabulary.yml": "schema: {entry_point: _index.md}\n",
            "config/index-types/module.schema.yaml": yaml.safe_dump(
                {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "$id": "module.schema.yaml",
                    "type": "object",
                    "x-default-mode": "registry",
                }
            ),
            "m/_index.md": INDEX,
            "m/note.md": NOTE,
            **files,
        },
    )
    indexes = {
        "vocabulary": "config/vocabulary.yml",
        "index_types": "config/index-types",
        "inspect_git": False,
        **section,
    }
    _write(
        root,
        {"anagraphe.yml": yaml.safe_dump({"schema_version": 2, **(top or {}), "indexes": indexes})},
    )


def _write_indexes(root: Path) -> RunResult:
    """Write the regions of the fixture repository."""
    config = load_config(root, root / "anagraphe.yml").indexes
    assert config is not None
    return run(root, config, "write")


def _listed(root: Path, index: str = "m/_index.md") -> list[str]:
    """Return the links of the entries rendered by an index."""
    return ENTRY.findall(
        (root / index).read_text(encoding="utf-8").split("<!-- index groups -->")[1]
    )


def test_yaml_records_are_listed_by_default(tmp_path: Path) -> None:
    """A YAML record joins its index whether its fields stand at its top level or in metadata."""
    _repository(
        tmp_path,
        {
            "m/flat.yml": "aliases: [Flat record]\nindex: '[Module](m/_index.md)'\nvalue: 3\n",
            "m/blocked.yml": "metadata: {aliases: [Block record], index: '[Module](m/_index.md)'}\n",
        },
    )
    result = _write_indexes(tmp_path)
    assert result.blocking_count == 0, result.issues
    assert _listed(tmp_path) == ["blocked.yml", "flat.yml", "note.md"]


def test_a_yaml_file_is_excluded_by_pattern(tmp_path: Path) -> None:
    """A tool configuration in an indexed folder is kept out by an exclusion pattern."""
    _repository(
        tmp_path,
        {"m/environment.yml": "name: tool\ndependencies: [python]\n"},
        exclude={"paths": ["environment.yml"]},
    )
    assert _write_indexes(tmp_path).blocking_count == 0
    assert _listed(tmp_path) == ["note.md"]


def test_unexcluded_yaml_without_fields_is_reported(tmp_path: Path) -> None:
    """A YAML member declaring no title and no index is listed and reported, as a note would be."""
    _repository(tmp_path, {"m/environment.yml": "name: tool\n"})
    config = load_config(tmp_path, tmp_path / "anagraphe.yml").indexes
    assert config is not None
    kinds = {
        issue.kind
        for issue in run(tmp_path, config, "check").issues
        if issue.rel == "m/environment.yml"
    }
    assert {"missing-alias", "index-location"} <= kinds


def test_members_restrict_the_listed_types(tmp_path: Path) -> None:
    """Members declared as Markdown alone leave the YAML records unlisted."""
    _repository(
        tmp_path,
        {"m/flat.yml": "aliases: [Flat]\nindex: '[Module](m/_index.md)'\n"},
        members=[{"types": ["md"]}],
    )
    assert _write_indexes(tmp_path).blocking_count == 0
    assert _listed(tmp_path) == ["note.md"]


def test_a_file_without_metadata_is_listed_by_its_name(tmp_path: Path) -> None:
    """A PDF member is titled by its file name, never read, and raises no issue of its fields."""
    _repository(
        tmp_path,
        {"m/paper.pdf": b"%PDF-1.4\x00\xff binary"},
        members=[{"types": ["md", "yml", "yaml", "pdf"]}],
    )
    result = _write_indexes(tmp_path)
    assert result.blocking_count == 0, result.issues
    assert _listed(tmp_path) == ["note.md", "paper.pdf"]
    assert "[paper](paper.pdf)" in (tmp_path / "m/_index.md").read_text(encoding="utf-8")


def test_json_records_read_through_their_source(tmp_path: Path) -> None:
    """A JSON record is listed with the fields that its declared source reads."""
    _repository(
        tmp_path,
        {"m/data.json": '{"meta": {"aliases": ["Data set"], "index": "[Module](m/_index.md)"}}'},
        top={"metadata": [{"when": {"types": ["json"]}, "from": {"json": ["meta"]}}]},
        members=[{"types": ["md", "json"]}],
    )
    result = _write_indexes(tmp_path)
    assert result.blocking_count == 0, result.issues
    assert "[Data set](data.json)" in (tmp_path / "m/_index.md").read_text(encoding="utf-8")


def test_members_select_by_metadata(tmp_path: Path) -> None:
    """A member condition on metadata lists only the YAML records of a role."""
    _repository(
        tmp_path,
        {
            "m/plan.yml": "role: plan\naliases: [Plan]\nindex: '[Module](m/_index.md)'\n",
            "m/settings.yml": "role: settings\n",
        },
        members=[{"types": ["md"]}, {"types": ["yml"], "where": [{"role": "plan"}]}],
    )
    assert _write_indexes(tmp_path).blocking_count == 0
    assert _listed(tmp_path) == ["note.md", "plan.yml"]


@pytest.mark.parametrize(
    ("members", "message"),
    [
        ([], "indexes.members must list at least one condition"),
        ([{"kinds": ["md"]}], r"indexes.members\[1\] declares unknown keys: kinds"),
    ],
)
def test_malformed_members_are_rejected(tmp_path: Path, members: Any, message: str) -> None:
    """A malformed declaration of the members fails with a message naming its field."""
    _repository(tmp_path, {}, members=members)
    with pytest.raises(ConfigurationError, match=message):
        load_config(tmp_path, tmp_path / "anagraphe.yml")


class FileMover:
    """Rename with the file system."""

    def move(self, root: Path, old: str, new: str) -> None:
        (root / new).parent.mkdir(parents=True, exist_ok=True)
        (root / old).rename(root / new)


def test_move_of_a_yaml_record_updates_both_indexes(tmp_path: Path) -> None:
    """A YAML record moved to another folder names its new index, and both regions follow."""
    _repository(
        tmp_path,
        {
            "m/flat.yml": "aliases: [Flat]\nindex: '[Module](m/_index.md)'\n",
            "n/_index.md": INDEX.replace("Module", "Next"),
        },
    )
    assert _write_indexes(tmp_path).blocking_count == 0
    service = MoveService(
        tmp_path, load_config(tmp_path, tmp_path / "anagraphe.yml"), "anagraphe.yml", FileMover()
    )
    result = service.apply(service.plan("m/flat.yml", "n/flat.yml"))
    assert (
        yaml.safe_load((tmp_path / "n/flat.yml").read_text(encoding="utf-8"))["index"]
        == "[Next](n/_index.md)"
    )
    assert result.regions is not None and result.regions.blocking_count == 0, result.regions
    assert _listed(tmp_path) == ["note.md"]
    assert _listed(tmp_path, "n/_index.md") == ["flat.yml"]


def test_a_declared_file_is_listed_once(tmp_path: Path) -> None:
    """A YAML file declared under the key files takes its declared entry, not a second one."""
    index = INDEX.replace("groups:", "files:\n  - {file: data.yml, title: Data table}\ngroups:")
    _repository(tmp_path, {"m/_index.md": index, "m/data.yml": "rows: [1, 2]\n"})
    result = _write_indexes(tmp_path)
    assert result.blocking_count == 0, result.issues
    assert _listed(tmp_path) == ["note.md", "data.yml"]


@pytest.mark.parametrize(
    ("rel", "text", "problem"),
    [
        ("m/broken.md", "---\naliases: [Broken\n---\n\n# Broken\n", "is not valid YAML"),
        ("m/unclosed.md", "---\naliases: [Unclosed]\n\n# Unclosed\n", "never closes"),
        ("m/listed.md", "---\n- a\n- b\n---\n\n# Listed\n", "is not a mapping"),
        ("m/record.yml", "aliases: [Record\nindex: x\n", "is not valid YAML"),
    ],
)
def test_unreadable_metadata_is_reported_alone(
    tmp_path: Path, rel: str, text: str, problem: str
) -> None:
    """A member whose metadata cannot be parsed is reported as such, without its missing fields."""
    _repository(tmp_path, {rel: text})
    config = load_config(tmp_path, tmp_path / "anagraphe.yml").indexes
    assert config is not None
    issues = [issue for issue in run(tmp_path, config, "check").issues if issue.rel == rel]
    assert [(issue.kind, issue.line, issue.blocking) for issue in issues] == [
        ("unreadable-metadata", None, True)
    ]
    assert problem in issues[0].detail


def test_an_index_with_unreadable_metadata_keeps_its_regions(tmp_path: Path) -> None:
    """An index whose metadata cannot be parsed is reported alone, and no write changes it."""
    broken = INDEX.replace("aliases: [Module]", "aliases: [Module")
    _repository(tmp_path, {"m/_index.md": broken})
    result = _write_indexes(tmp_path)
    assert [(issue.rel, issue.kind) for issue in result.issues] == [
        ("m/_index.md", "unreadable-metadata")
    ]
    assert (tmp_path / "m/_index.md").read_text(encoding="utf-8") == broken


def test_unreadable_metadata_makes_the_findings_run_incomplete(tmp_path: Path) -> None:
    """The findings log keeps the result, and declares that a file was left unanalyzed."""
    _repository(tmp_path, {"m/broken.md": "---\naliases: [Broken\n---\n\n# Broken\n"})
    result = CliRunner().invoke(
        app, ["indexes", "check", "--root", str(tmp_path), "--format", "sarif"]
    )
    assert result.exit_code == 1
    assert "m/broken.md:1: unreadable-metadata: the frontmatter is not valid YAML" in result.stderr
    run_log = json.loads(result.stdout)["runs"][0]
    (invocation,) = run_log["invocations"]
    assert invocation["executionSuccessful"] is False
    assert "m/broken.md" in invocation["toolExecutionNotifications"][0]["message"]["text"]
    (found,) = [item for item in run_log["results"] if "broken" in json.dumps(item["locations"])]
    assert found["ruleId"] == "indexes/unreadable-metadata"
    assert "region" not in found["locations"][0]["physicalLocation"]
