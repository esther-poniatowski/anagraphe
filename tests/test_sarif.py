"""Behavioral tests for the findings log, the SARIF output of the findings profile of Elenchos.

Each log written by Anagraphe is checked with the profile interface ``elenchos.profile``:
``violations`` judges its conformance, and ``identities`` returns the identity that the gate builds
for each result. The rules of the profile and its test vectors belong to Elenchos, so these tests
check only the logs of Anagraphe: its rules, its loci, its discriminators and its failed runs.
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from elenchos.profile import identities, violations
from typer.testing import CliRunner

from anagraphe_read._core.issues import Issue, IssueKind, Report

from anagraphe import __version__
from anagraphe.cli import CATALOGUES, app
from anagraphe.core.sarif import Section, logical_name, sarif_log
from anagraphe.references.rules import RULES

SOURCES = Path(__file__).resolve().parents[1] / "src" / "anagraphe"


def _results(log: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the results of the one run of a log."""
    results: list[dict[str, Any]] = log["runs"][0]["results"]
    return results


# --- The writer.


def test_driver_lists_every_kind_of_every_section() -> None:
    """The driver declares each kind of both sections once, at its default level."""
    sections = [Section(name, kinds) for name, kinds in CATALOGUES.items()]
    log = sarif_log(sections, __version__)
    rules = log["runs"][0]["tool"]["driver"]["rules"]
    ids = [rule["id"] for rule in rules]
    assert len(ids) == len(set(ids)) == sum(len(kinds) for kinds in CATALOGUES.values())
    assert "references/broken" in ids and "indexes/retired-key" in ids
    level = {rule["id"]: rule["defaultConfiguration"]["level"] for rule in rules}
    assert level["indexes/missing-purpose"] == "warning"
    assert level["indexes/stale-block"] == "error"
    assert violations(log) == []


def test_result_maps_an_issue() -> None:
    """An issue maps to its rule, level, message, file, line, logical name and discriminator."""
    issue = Issue(
        "m/a #1.md",
        4,
        "unknown-task",
        "blocked_by names no declared task: t-1",
        blocking=False,
        locus="/blocked_by",
        discriminator="t-1",
    )
    log = sarif_log([Section("indexes", (IssueKind("unknown-task", "x"),), (issue,))], "1")
    (result,) = _results(log)
    assert result == {
        "ruleId": "indexes/unknown-task",
        "level": "warning",
        "message": {"text": "blocked_by names no declared task: t-1"},
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": "m/a%20%231.md", "uriBaseId": "SRCROOT"},
                    "region": {"startLine": 4},
                },
                "logicalLocations": [{"name": "path:m/a %231.md#/blocked_by"}],
            }
        ],
        "partialFingerprints": {"discriminator/v1": "t-1"},
    }
    assert violations(log) == []
    assert identities(log) == ["anagraphe|indexes/unknown-task|path:m/a #1.md|/blocked_by|t-1"]


def test_a_note_keeps_its_level_in_the_rule_and_the_result() -> None:
    """A kind and an issue marked as notes take the level note, and count as no warning."""
    kind = IssueKind("unverified-target", "x", blocking=False, note=True)
    issue = Issue("a.yml", None, "unverified-target", "d", blocking=False, note=True, locus="/t")
    log = sarif_log([Section("targets", (kind,), (issue,))], "1")
    rule = log["runs"][0]["tool"]["driver"]["rules"][0]
    assert rule["defaultConfiguration"] == {"level": "note"}
    assert [result["level"] for result in _results(log)] == ["note"]
    assert violations(log) == []
    report = Report(1, (issue, Issue("a.yml", None, "k", "d", blocking=False)))
    assert (report.blocking_count, report.warning_count, report.note_count) == (0, 1, 1)


def test_empty_discriminator_writes_no_fingerprint() -> None:
    """A result writes ``partialFingerprints`` only when its discriminator is not empty."""
    issue = Issue("a.md", 2, "broken", "b.md: names no file", locus="link:b.md")
    log = sarif_log([Section("references", (IssueKind("broken", "x"),), (issue,))], "1")
    (result,) = _results(log)
    assert "partialFingerprints" not in result
    assert violations(log) == []
    assert identities(log) == ["anagraphe|references/broken|path:a.md|link:b.md"]
    assert logical_name(Issue("a%.md", 1, "k", "d")) == "path:a%25.md"


def test_failed_runs() -> None:
    """A stopped run states why, and a run that never began omits its results."""
    stopped = sarif_log([Section("references", ())], "1", stopped="target: no file", began=False)
    run = stopped["runs"][0]
    assert "results" not in run
    assert run["invocations"] == [
        {
            "executionSuccessful": False,
            "toolExecutionNotifications": [
                {"level": "error", "message": {"text": "target: no file"}}
            ],
        }
    ]
    assert violations(stopped) == []
    with pytest.raises(ValueError, match="never began"):
        sarif_log([], "1", began=False)


def test_a_kind_outside_the_catalogue_is_refused() -> None:
    """An issue whose kind its section does not list cannot reach the log without its rule."""
    with pytest.raises(ValueError, match="lists no kind invented"):
        sarif_log([Section("indexes", (), (Issue("a.md", 1, "invented", "x"),))], "1")


# --- The catalogues against the sources.


def _written_kinds(tree: ast.AST) -> Iterator[str]:
    """Yield the literal kinds of the issues constructed in a module."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Issue":
            kind = node.args[2] if len(node.args) > 2 else None
            for constant in ast.walk(kind) if kind is not None else ():
                if isinstance(constant, ast.Constant) and isinstance(constant.value, str):
                    yield constant.value


def test_the_kind_scan_finds_a_planted_kind() -> None:
    """The scan of the sources reads a kind written in a conditional expression."""
    planted = ast.parse('Issue(rel, 1, "a" if exists else "b", detail)')
    assert set(_written_kinds(planted)) == {"a", "b"}


def test_catalogues_list_every_kind_written_in_the_sources() -> None:
    """Every kind constructed in the sources has a rule, and every rule a construction."""
    for section, package in (("indexes", "indexes"), ("references", "references")):
        written = {
            kind
            for path in sorted((SOURCES / package).glob("*.py"))
            for kind in _written_kinds(ast.parse(path.read_text(encoding="utf-8")))
        }
        if section == "references":
            written |= {rule.kind for rule in RULES} | {"unreadable-file"}
        listed = {kind.kind for kind in CATALOGUES[section]}
        assert written == listed, (section, written ^ listed)


# --- The command line.

CONFIG_INDEXES = {
    "entry_point": "_index.md",
    "index_types": "config/index-types",
    "inspect_git": False,
}
INDEX = (
    "---\naliases: [Module]\ngroups:\n  - {id: '*', heading: Entries}\n---\n\n# Module\n\n"
    "<!-- index groups -->\n<!-- /index -->\n"
)


def _repository(root: Path, files: dict[str, str], indexes: bool = False) -> None:
    """Write a repository whose configuration declares the references, and the indexes if asked."""
    config: dict[str, Any] = {"_schema": "anagraphe:configuration@3", "references": {}}
    if indexes:
        config["indexes"] = CONFIG_INDEXES
        files = {
            "config/index-types/module.schema.yaml": yaml.safe_dump(
                {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "$id": "module.schema.yaml",
                    "type": "object",
                    "x-default-mode": "registry",
                }
            ),
            **files,
        }
    files = {"anagraphe.yml": yaml.safe_dump(config), **files}
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


PLANTED_LINKS = {
    "notes/a.md": (
        "# A\n\n[gone](missing.md) and [slug](b.md#heading) and [anchor](b.md#^absent).\n"
    ),
    "notes/b.md": "# B\n\n## Heading\n",
}


def _invoke(*arguments: str) -> Any:
    """Run the command line on its arguments."""
    return CliRunner().invoke(app, list(arguments))


def test_cli_writes_the_planted_link_findings(tmp_path: Path) -> None:
    """The planted broken links map to the rules, resources and loci of the baseline mapping."""
    _repository(tmp_path, PLANTED_LINKS)
    log_path = tmp_path / "build" / "findings" / "anagraphe.sarif"
    result = _invoke(
        "refs", "check", "--root", str(tmp_path), "--format", "sarif", "--output", str(log_path)
    )
    assert result.exit_code == 1
    log = json.loads(log_path.read_text(encoding="utf-8"))
    assert violations(log) == []
    assert log["runs"][0]["invocations"] == [{"executionSuccessful": True}]
    assert set(identities(log)) == {
        "anagraphe|references/broken|path:notes/a.md|link:missing.md",
        "anagraphe|references/heading-fragment|path:notes/a.md|link:b.md#heading",
        "anagraphe|references/broken-anchor|path:notes/a.md|link:b.md#^absent",
    }


def test_cli_keeps_the_text_report_byte_identical(tmp_path: Path) -> None:
    """The text report is unchanged by the log, on standard output or on standard error."""
    _repository(tmp_path, PLANTED_LINKS)
    text = _invoke("refs", "check", "--root", str(tmp_path))
    log_path = tmp_path / "x.sarif"
    beside = _invoke(
        "refs", "check", "--root", str(tmp_path), "--format", "sarif", "--output", str(log_path)
    )
    instead = _invoke("refs", "check", "--root", str(tmp_path), "--format", "sarif")
    assert text.stdout and beside.stdout == text.stdout
    assert instead.stderr == text.stdout
    assert violations(json.loads(instead.stdout)) == []
    assert json.loads(log_path.read_text(encoding="utf-8")) == json.loads(instead.stdout)


def test_identity_ignores_the_line(tmp_path: Path) -> None:
    """Lines inserted above a finding change its region, and leave its identity unchanged."""
    _repository(tmp_path, PLANTED_LINKS)
    first = json.loads(
        _invoke("refs", "check", "--root", str(tmp_path), "--format", "sarif").stdout
    )
    (tmp_path / "notes/a.md").write_text(
        "# A\n\nA new paragraph.\n\n" + PLANTED_LINKS["notes/a.md"][5:], encoding="utf-8"
    )
    second = json.loads(
        _invoke("refs", "check", "--root", str(tmp_path), "--format", "sarif").stdout
    )
    assert identities(first) == identities(second)
    lines = {
        item["locations"][0]["physicalLocation"]["region"]["startLine"] for item in _results(second)
    }
    assert lines == {5}


def test_cli_check_writes_index_findings_with_pointers(tmp_path: Path) -> None:
    """A retired key and a missing alias are located by the JSON Pointer of their key."""
    _repository(
        tmp_path,
        {
            "m/_index.md": INDEX,
            "m/note.md": "---\nindex: '[Module](m/_index.md)'\ncites: []\n---\n\n# Note\n",
        },
        indexes=True,
    )
    result = _invoke("check", "--root", str(tmp_path), "--format", "sarif")
    assert result.exit_code == 1
    log = json.loads(result.stdout)
    assert violations(log) == []
    found = identities(log)
    assert "anagraphe|indexes/retired-key|path:m/note.md|/cites" in found
    assert "anagraphe|indexes/missing-alias|path:m/note.md|/aliases" in found
    # An issue of a key of the metadata has no line, so its location holds no region.
    assert all("region" not in item["locations"][0]["physicalLocation"] for item in _results(log))
    text = _invoke("check", "--root", str(tmp_path)).stdout
    assert "m/note.md:1: retired-key: the key cites is retired" in text


def test_a_located_issue_keeps_its_region(tmp_path: Path) -> None:
    """A reference keeps its line as the region of its location."""
    _repository(tmp_path, PLANTED_LINKS)
    log = json.loads(_invoke("refs", "check", "--root", str(tmp_path), "--format", "sarif").stdout)
    regions = [item["locations"][0]["physicalLocation"].get("region") for item in _results(log)]
    assert regions == [{"startLine": 3}] * 3


def test_cli_declares_an_unreadable_file(tmp_path: Path) -> None:
    """A document that a syntax of keys cannot parse makes the run incomplete, with its result."""
    _repository(tmp_path, {"specs/terms.yml": "terms: [unclosed\n"})
    config = {
        "_schema": "anagraphe:configuration@3",
        "references": {"syntaxes": {"sources": {"when": {"types": ["yml"]}, "keys": ["source"]}}},
    }
    (tmp_path / "anagraphe.yml").write_text(yaml.safe_dump(config), encoding="utf-8")
    result = _invoke("refs", "check", "--root", str(tmp_path), "--format", "sarif")
    log = json.loads(result.stdout)
    assert violations(log) == []
    (invocation,) = log["runs"][0]["invocations"]
    assert invocation["executionSuccessful"] is False
    assert "specs/terms.yml" in invocation["toolExecutionNotifications"][0]["message"]["text"]
    assert identities(log) == ["anagraphe|references/unreadable-file|path:specs/terms.yml"]
    assert "region" not in _results(log)[0]["locations"][0]["physicalLocation"]


def test_cli_writes_a_failed_run_for_an_invalid_configuration(tmp_path: Path) -> None:
    """A configuration that cannot be loaded yields a failed run without results, and status 2."""
    (tmp_path / "anagraphe.yml").write_text("schema_version: 1\n", encoding="utf-8")
    result = _invoke("check", "--root", str(tmp_path), "--format", "sarif")
    assert result.exit_code == 2
    log = json.loads(result.stdout)
    assert violations(log) == []
    run = log["runs"][0]
    assert "results" not in run
    assert run["invocations"][0]["executionSuccessful"] is False
    assert len(run["tool"]["driver"]["rules"]) == sum(len(kinds) for kinds in CATALOGUES.values())


def test_cli_rejects_output_without_sarif(tmp_path: Path) -> None:
    """The option ``--output`` serves the log alone."""
    _repository(tmp_path, PLANTED_LINKS)
    result = _invoke("refs", "check", "--root", str(tmp_path), "--output", str(tmp_path / "x"))
    assert result.exit_code == 2
    # A terminal admitting colours, as on a CI runner, interleaves escape codes with the message.
    assert "--output requires --format sarif" in re.sub(r"\x1b\[[0-9;]*m", "", result.stderr)
