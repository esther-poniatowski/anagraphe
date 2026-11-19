"""Behavioral tests of the version gate of ADR 0008: the comparison of the versions declared by the
other read sides of a repository, under ``targets.read_sides``, with those of Anagraphe.

Each finding has a planted case, beside a declaration that matches and raises none. The
declaration below takes the shape that an Obsidian plugin bundling ``@anagraphe/read`` writes into
its ``manifest.json``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from anagraphe_read._core.configuration import ConfigurationError
from anagraphe_read._targets.specification import IMPLEMENTED_SPECIFICATION

from anagraphe.cli import app
from anagraphe.configuration import load_config
from anagraphe.targets.service import TargetChecker

MANIFEST = ".obsidian/plugins/ekphrasis/manifest.json"
POINTER = "/anagrapheRead"


def _repository(root: Path, files: dict[str, str], sides: Any) -> None:
    """Write files and a configuration declaring the read sides."""
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    config = {"_schema": "anagraphe:configuration@3", "targets": {"read_sides": sides}}
    (root / "anagraphe.yml").write_text(yaml.safe_dump(config), encoding="utf-8")


def _plugin(declaration: Any) -> str:
    """Return the manifest of a plugin holding a declaration under its key anagrapheRead."""
    return json.dumps({"id": "ekphrasis", "version": "1.0.0", "anagrapheRead": declaration})


def _issues(root: Path) -> list[tuple[str, str, str]]:
    config = load_config(root, root / "anagraphe.yml").targets
    assert config is not None
    return sorted(
        (issue.rel, issue.kind, issue.locus) for issue in TargetChecker(root, config).check().issues
    )


def test_a_matching_declaration_raises_no_finding(tmp_path: Path) -> None:
    _repository(
        tmp_path,
        {MANIFEST: _plugin(dict(IMPLEMENTED_SPECIFICATION))},
        [{"path": MANIFEST, "pointer": POINTER}],
    )
    assert not _issues(tmp_path)


def test_a_declaration_in_yaml_is_read(tmp_path: Path) -> None:
    text = yaml.safe_dump({"read": {"side": dict(IMPLEMENTED_SPECIFICATION)}})
    _repository(tmp_path, {"sides.yml": text}, [{"path": "sides.yml", "pointer": "/read/side"}])
    assert not _issues(tmp_path)


def test_a_differing_declaration_names_each_key_with_both_values(tmp_path: Path) -> None:
    # A read side of 0.10.0 still declares the contract of the retired manifest.
    declared = {
        **IMPLEMENTED_SPECIFICATION,
        "registry": "anagraphe:record-registry@2",
        "repository": "anagraphe:repository@1",
    }
    _repository(tmp_path, {MANIFEST: _plugin(declared)}, [{"path": MANIFEST, "pointer": POINTER}])
    config = load_config(tmp_path, tmp_path / "anagraphe.yml").targets
    assert config is not None
    (issue,) = TargetChecker(tmp_path, config).check().issues
    assert (issue.rel, issue.kind, issue.locus, issue.blocking) == (
        MANIFEST,
        "read-side-mismatch",
        POINTER,
        True,
    )
    assert "registry: declared anagraphe:record-registry@2, implemented " in issue.detail
    assert "anagraphe:record-registry@1" in issue.detail
    assert "repository: declared anagraphe:repository@1, implemented absent" in issue.detail
    assert "addressing" not in issue.detail


@pytest.mark.parametrize(
    ("files", "pointer"),
    [
        pytest.param({}, POINTER, id="missing-file"),
        pytest.param({MANIFEST: '{"anagrapheRead": '}, POINTER, id="unparsable-json"),
        pytest.param({MANIFEST: '{"anagrapheRead": NaN}'}, POINTER, id="json-outside-rfc-8259"),
        pytest.param({MANIFEST: _plugin({})}, "/anagrapheReader", id="no-value-at-the-pointer"),
        pytest.param({MANIFEST: _plugin({})}, "/version/major", id="pointer-below-a-scalar"),
        pytest.param({MANIFEST: _plugin(["addressing"])}, POINTER, id="not-a-mapping"),
        pytest.param({MANIFEST: _plugin({"addressing": 1})}, POINTER, id="not-a-string"),
    ],
)
def test_an_unreadable_declaration_is_reported_at_its_pointer(
    tmp_path: Path, files: dict[str, str], pointer: str
) -> None:
    _repository(tmp_path, files, [{"path": MANIFEST, "pointer": pointer}])
    assert _issues(tmp_path) == [(MANIFEST, "unreadable-read-side", pointer)]


def test_an_unparsable_yaml_declaration_is_reported(tmp_path: Path) -> None:
    """The walk of the check also reads the file as a record, and reports it as such."""
    _repository(
        tmp_path, {"sides.yml": "read: [unclosed\n"}, [{"path": "sides.yml", "pointer": ""}]
    )
    assert _issues(tmp_path) == [
        ("sides.yml", "unreadable-read-side", ""),
        ("sides.yml", "unreadable-record", ""),
    ]


@pytest.mark.parametrize(
    ("sides", "message"),
    [
        pytest.param({"path": MANIFEST}, "must be a list", id="not-a-list"),
        pytest.param([{"path": MANIFEST}], "keys path and pointer", id="missing-pointer"),
        pytest.param([{"path": "../x.json", "pointer": ""}], "inside the repository", id="escape"),
        pytest.param([{"path": MANIFEST, "pointer": "/a~2"}], "pointer", id="invalid-escape"),
        pytest.param([{"path": MANIFEST, "pointer": "anagrapheRead"}], "pointer", id="no-slash"),
    ],
)
def test_a_malformed_declaration_fails_the_configuration(
    tmp_path: Path, sides: Any, message: str
) -> None:
    _repository(tmp_path, {}, sides)
    with pytest.raises(ConfigurationError, match=message):
        load_config(tmp_path, tmp_path / "anagraphe.yml")


def test_cli_fails_on_a_differing_declaration(tmp_path: Path) -> None:
    declared = {**IMPLEMENTED_SPECIFICATION, "addressing": "https://example.org/addressing.v2"}
    _repository(tmp_path, {MANIFEST: _plugin(declared)}, [{"path": MANIFEST, "pointer": POINTER}])
    result = CliRunner().invoke(app, ["targets", "check", "--root", str(tmp_path)])
    assert result.exit_code == 1, result.output
    assert f"{MANIFEST}:1: read-side-mismatch: {POINTER}: " in result.output
    assert "addressing: declared https://example.org/addressing.v2, implemented" in result.output
