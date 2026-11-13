"""Behavioral tests for the findings log, the SARIF output of the findings profile of Elenchos.

The validator :func:`violations` transcribes the rules of the profile that bind a producer: the log
and the run (section 3), the result and its locations (section 4), and the rejected input of the
gate (section 5.6). Each rule is planted in a broken log, so the validator is shown to fire before
it judges the logs of Anagraphe.
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
from typer.testing import CliRunner

from anagraphe import __version__
from anagraphe.cli import CATALOGUES, app
from anagraphe.core.issues import Issue, IssueKind, Report
from anagraphe.core.sarif import Section, logical_name, sarif_log
from anagraphe.references.rules import RULES

SOURCES = Path(__file__).resolve().parents[1] / "src" / "anagraphe"
RULE_ID = re.compile(r"[a-z0-9][a-z0-9._-]*(?:/[a-z0-9][a-z0-9._-]*)*")
DRIVER = re.compile(r"[a-z][a-z0-9-]*")
VERSIONED_KEY = re.compile(r"(?:[^/]+/)*v[0-9]+")
LEVELS = {"error", "warning", "note"}


def _name_violations(name: str) -> list[str]:
    """Return the breaches of a logical name ``<resource>[#<locus>]`` (profile, section 4.5)."""
    resource, _, locus = name.partition("#")
    problems = []
    if name.endswith("#"):
        problems.append(f"name ends with #: {name}")
    if re.search(r"%(?!25|23)", resource):
        problems.append(f"resource holds an escape other than %25 and %23: {name}")
    if resource.startswith("path:"):
        path = resource[len("path:") :]
        if path.startswith(("/", "./")) and path != "./":
            problems.append(f"path is not repository-relative: {name}")
        if any(segment in {"", ".", ".."} for segment in path.rstrip("/").split("/")):
            problems.append(f"path holds an empty, . or .. segment: {name}")
    elif not resource.startswith("id:"):
        problems.append(f"resource opens on neither path: nor id: {name}")
    if locus.startswith("/") and re.search(r"~(?![01])", locus):
        problems.append(f"pointer holds ~ not followed by 0 or 1: {name}")
    if (
        locus
        and not locus.startswith("/")
        and locus.split(":")[0]
        not in {
            "link",
            "task",
            "slot",
            "term",
            "symbol",
        }
    ):
        problems.append(f"locus of no admitted type: {name}")
    return problems


def violations(log: Any) -> list[str]:
    """Return every breach of the findings profile by a log, an empty list when it conforms."""
    if not isinstance(log, dict) or log.get("version") != "2.1.0":
        return ["log is not an object of version 2.1.0"]
    runs = log.get("runs")
    if not isinstance(runs, list) or not runs:
        return ["log holds no non-empty array of runs"]
    problems: list[str] = []
    for run in runs:
        driver = run.get("tool", {}).get("driver", {})
        name = driver.get("name")
        if not isinstance(name, str) or not DRIVER.fullmatch(name) or name == "elenchos":
            problems.append(f"driver name outside its form: {name!r}")
        if "version" not in driver and "semanticVersion" not in driver:
            problems.append("driver declares no version")
        rules = driver.get("rules")
        if not isinstance(rules, list):
            problems.append("driver lists no rules")
            rules = []
        declared = set()
        for rule in rules:
            if not rule.get("shortDescription", {}).get("text"):
                problems.append(f"rule without description: {rule.get('id')}")
            if rule.get("defaultConfiguration", {}).get("level") not in LEVELS:
                problems.append(f"rule without default level: {rule.get('id')}")
            declared.add(rule.get("id"))
        invocations = run.get("invocations", [])
        failed = any(
            not item.get("executionSuccessful")
            or any(
                note.get("level") == "error" for note in item.get("toolExecutionNotifications", [])
            )
            for item in invocations
        )
        if failed and (
            len(invocations) != 1
            or not any(
                note.get("level") == "error" and note.get("message", {}).get("text")
                for note in invocations[0].get("toolExecutionNotifications", [])
            )
        ):
            problems.append("incomplete run without one invocation stating its error")
        results = run.get("results")
        if results is None:
            if not failed:
                problems.append("complete run without results")
            continue
        if results and run.get("columnKind") != "unicodeCodePoints":
            problems.append("run with results declares no columnKind unicodeCodePoints")
        for result in results:
            problems.extend(_result_violations(result, declared))
    return problems


def _result_violations(result: dict[str, Any], declared: set[Any]) -> list[str]:
    """Return the breaches of one result (profile, sections 4 and 5.6)."""
    problems = []
    rule_id = result.get("ruleId")
    if not isinstance(rule_id, str) or not RULE_ID.fullmatch(rule_id):
        problems.append(f"ruleId outside its form: {rule_id!r}")
    elif rule_id not in declared:
        problems.append(f"ruleId names no rule of the driver: {rule_id}")
    if result.get("level") not in LEVELS:
        problems.append(f"result of {rule_id} has no admitted level")
    if not result.get("message", {}).get("text"):
        problems.append(f"result of {rule_id} has no message text")
    for reserved in ("suppressions", "fingerprints", "baselineState"):
        if reserved in result:
            problems.append(f"result of {rule_id} holds {reserved}, which the gate alone writes")
    locations = result.get("locations")
    if not isinstance(locations, list) or len(locations) != 1:
        return problems + [f"result of {rule_id} holds not exactly one location"]
    logical = locations[0].get("logicalLocations")
    if not isinstance(logical, list) or len(logical) != 1 or "name" not in logical[0]:
        problems.append(f"result of {rule_id} holds not exactly one named logical location")
    else:
        problems.extend(_name_violations(logical[0]["name"]))
    artifact = locations[0].get("physicalLocation", {}).get("artifactLocation", {})
    if artifact and artifact.get("uriBaseId") != "SRCROOT":
        problems.append(f"result of {rule_id} has a relative URI without SRCROOT")
    for key, value in result.get("partialFingerprints", {}).items():
        if not VERSIONED_KEY.fullmatch(key) or not isinstance(value, str) or not value:
            problems.append(f"partial fingerprint outside its form: {key}={value!r}")
    return problems


def _results(log: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the results of the one run of a log."""
    results: list[dict[str, Any]] = log["runs"][0]["results"]
    return results


def _identity(result: dict[str, Any]) -> tuple[str, str, str]:
    """Return the rule, the logical name and the discriminator of a result."""
    name = result["locations"][0]["logicalLocations"][0]["name"]
    return result["ruleId"], name, result.get("partialFingerprints", {}).get("discriminator/v1", "")


# --- The validator fires on each planted breach.

VALID = sarif_log(
    [
        Section(
            "references",
            (IssueKind("broken", "A path names no file."),),
            (Issue("a.md", 2, "broken", "b.md: names no file", locus="link:b.md"),),
        )
    ],
    "1.0.0",
)


def _planted(edit: str) -> dict[str, Any]:
    """Return a copy of the valid log with one breach."""
    log: dict[str, Any] = json.loads(json.dumps(VALID))
    run = log["runs"][0]
    result = run["results"][0]
    location = result["locations"][0]
    if edit == "driver":
        run["tool"]["driver"]["name"] = "elenchos"
    elif edit == "rule":
        result["ruleId"] = "references/unknown"
    elif edit == "level":
        result["level"] = "info"
    elif edit == "suppressions":
        result["suppressions"] = []
    elif edit == "two-locations":
        result["locations"].append(location)
    elif edit == "escape":
        location["logicalLocations"][0]["name"] = "path:a%20b.md"
    elif edit == "locus":
        location["logicalLocations"][0]["name"] = "path:a.md#href:b.md"
    elif edit == "fingerprint":
        result["partialFingerprints"] = {"discriminator": "x"}
    elif edit == "column":
        del run["columnKind"]
    elif edit == "results":
        del run["results"]
    elif edit == "failed":
        run["invocations"] = [{"executionSuccessful": False}]
    return log


@pytest.mark.parametrize(
    "edit",
    [
        "driver",
        "rule",
        "level",
        "suppressions",
        "two-locations",
        "escape",
        "locus",
        "fingerprint",
        "column",
        "results",
        "failed",
    ],
)
def test_validator_fires_on_planted_breach(edit: str) -> None:
    """Each planted breach of the profile is reported, and the unbroken log conforms."""
    assert violations(VALID) == []
    assert violations(_planted(edit))


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
    (result,) = _results(VALID)
    assert "partialFingerprints" not in result
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
    "vocabulary": "config/vocabulary.yml",
    "index_types": "config/index-types",
    "inspect_git": False,
}
INDEX = (
    "---\naliases: [Module]\ngroups:\n  - {id: '*', heading: Entries}\n---\n\n# Module\n\n"
    "<!-- index groups -->\n<!-- /index -->\n"
)


def _repository(root: Path, files: dict[str, str], indexes: bool = False) -> None:
    """Write a repository whose configuration declares the references, and the indexes if asked."""
    config: dict[str, Any] = {"_schema": "anagraphe:configuration@2", "references": {}}
    if indexes:
        config["indexes"] = CONFIG_INDEXES
        files = {
            "config/vocabulary.yml": "schema: {entry_point: _index.md}\n",
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
    assert {_identity(item) for item in _results(log)} == {
        ("references/broken", "path:notes/a.md#link:missing.md", ""),
        ("references/heading-fragment", "path:notes/a.md#link:b.md#heading", ""),
        ("references/broken-anchor", "path:notes/a.md#link:b.md#^absent", ""),
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
    assert {_identity(item) for item in _results(first)} == {
        _identity(item) for item in _results(second)
    }
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
    identities = {_identity(item) for item in _results(log)}
    assert ("indexes/retired-key", "path:m/note.md#/cites", "") in identities
    assert ("indexes/missing-alias", "path:m/note.md#/aliases", "") in identities
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
        "_schema": "anagraphe:configuration@2",
        "references": {"syntaxes": {"sources": {"when": {"types": ["yml"]}, "keys": ["source"]}}},
    }
    (tmp_path / "anagraphe.yml").write_text(yaml.safe_dump(config), encoding="utf-8")
    result = _invoke("refs", "check", "--root", str(tmp_path), "--format", "sarif")
    log = json.loads(result.stdout)
    assert violations(log) == []
    (invocation,) = log["runs"][0]["invocations"]
    assert invocation["executionSuccessful"] is False
    assert "specs/terms.yml" in invocation["toolExecutionNotifications"][0]["message"]["text"]
    assert [_identity(item) for item in _results(log)] == [
        ("references/unreadable-file", "path:specs/terms.yml", "")
    ]
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
