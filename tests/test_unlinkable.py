"""Behavioral tests for the files that the other files must not cite, ``references.unlinkable``.

The cases follow the rule of the frontmatter checker of the Geonexus vault: a superseded note is a
violation to cite, an unfiled note a warning, an index cites freely, and a note that is itself
unlinkable may cite its own kind.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from anagraphe.cli import app
from anagraphe.configuration import load_config
from anagraphe.core.configuration import ConfigurationError
from anagraphe.core.issues import Issue
from anagraphe.references.service import ReferenceChecker

#: Superseded notes block, unfiled notes warn, and an index may cite a superseded note.
UNLINKABLE: list[dict[str, Any]] = [
    {
        "target": {"where": [{"status": ["archived", "deprecated"]}]},
        "unless": {"where": [{"role": "index"}]},
    },
    {"target": {"where": [{"status": "inbox"}]}, "blocking": False},
]

FILES = {
    "notes/stable.md": (
        "---\nstatus: stable\n---\n# Stable\n\n"
        "[old](archived.md), [[archived]], [new](inbox.md), [peer](peer.md) and `archived.md`.\n"
    ),
    "notes/peer.md": "---\nstatus: stable\n---\n# Peer\n",
    "notes/archived.md": "---\nstatus: archived\n---\n# Archived\n\n[unfiled](inbox.md)\n",
    "notes/inbox.md": "---\nstatus: inbox\n---\n# Inbox\n",
    "notes/_index.md": "---\nrole: index\n---\n# Notes\n\n[old](archived.md), [new](inbox.md)\n",
}


def _repository(root: Path, unlinkable: Any = UNLINKABLE, **section: Any) -> None:
    """Write the fixture notes and a configuration declaring the unlinkable files."""
    files = {
        "anagraphe.yml": yaml.safe_dump(
            {"schema_version": 2, "references": {"unlinkable": unlinkable, **section}}
        ),
        **FILES,
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _unlinkable(root: Path) -> list[Issue]:
    """Return the issues of kind unlinkable-target in the fixture repository."""
    config = load_config(root, root / "anagraphe.yml").references
    assert config is not None
    return [
        issue
        for issue in ReferenceChecker(root, config).check().issues
        if issue.kind == "unlinkable-target"
    ]


def test_superseded_and_unfiled_targets_are_reported(tmp_path: Path) -> None:
    """Each citing link of a declared syntax is reported, at the level of its entry."""
    _repository(tmp_path)
    found = {(issue.rel, issue.detail, issue.blocking) for issue in _unlinkable(tmp_path)}
    assert found == {
        (
            "notes/stable.md",
            "archived.md: notes/archived.md has status archived, so it must not be cited",
            True,
        ),
        (
            "notes/stable.md",
            "archived: notes/archived.md has status archived, so it must not be cited",
            True,
        ),
        (
            "notes/stable.md",
            "inbox.md: notes/inbox.md has status inbox, so it must not be cited",
            False,
        ),
        (
            "notes/_index.md",
            "inbox.md: notes/inbox.md has status inbox, so it must not be cited",
            False,
        ),
    }


def test_an_unlinkable_file_cites_its_own_kind(tmp_path: Path) -> None:
    """An archived note may cite an unfiled note, since it is unlinkable itself."""
    _repository(tmp_path)
    assert not [issue for issue in _unlinkable(tmp_path) if issue.rel == "notes/archived.md"]


def test_declared_syntaxes_select_the_pointers(tmp_path: Path) -> None:
    """An entry limited to wikilinks leaves the Markdown links and the code spans unreported."""
    entry = {**UNLINKABLE[0], "syntaxes": ["wikilink"]}
    _repository(tmp_path, [entry])
    assert [issue.detail.split(":")[0] for issue in _unlinkable(tmp_path)] == ["archived"]


def test_without_declaration_nothing_is_unlinkable(tmp_path: Path) -> None:
    """A section declaring no unlinkable files reports no issue of the kind."""
    _repository(tmp_path, None)
    assert _unlinkable(tmp_path) == []


def test_the_kind_can_be_ignored(tmp_path: Path) -> None:
    """The kind is silenced under ignore, as every other kind of the section."""
    _repository(tmp_path, ignore=["unlinkable-target"])
    assert _unlinkable(tmp_path) == []


@pytest.mark.parametrize(
    ("unlinkable", "message"),
    [
        ({"target": {}}, r"references.unlinkable must list entries"),
        ([{"blocking": False}], r"unlinkable\[1\] must declare target"),
        ([{"target": {}}], r"unlinkable\[1\].target must restrict the files"),
        ([{"target": {"types": ["md"]}, "blocking": "no"}], r"blocking must be true or false"),
        ([{"target": {"types": ["md"]}, "syntaxes": ["html"]}], r"unknown syntaxes: html"),
        ([{"target": {"types": ["md"]}, "level": "warn"}], r"unknown keys: level"),
    ],
)
def test_malformed_declarations_are_rejected(tmp_path: Path, unlinkable: Any, message: str) -> None:
    """A malformed entry fails with a message naming its field."""
    _repository(tmp_path, unlinkable)
    with pytest.raises(ConfigurationError, match=message):
        load_config(tmp_path, tmp_path / "anagraphe.yml")


def test_findings_log_locates_the_link(tmp_path: Path) -> None:
    """The log names the rule references/unlinkable-target and the target as written."""
    _repository(tmp_path)
    result = CliRunner().invoke(
        app, ["refs", "check", "--root", str(tmp_path), "--format", "sarif"]
    )
    assert result.exit_code == 1
    found = {
        (
            item["ruleId"],
            item["level"],
            item["locations"][0]["logicalLocations"][0]["name"],
        )
        for item in json.loads(result.stdout)["runs"][0]["results"]
        if item["ruleId"] == "references/unlinkable-target"
    }
    assert found == {
        ("references/unlinkable-target", "error", "path:notes/stable.md#link:archived.md"),
        ("references/unlinkable-target", "error", "path:notes/stable.md#link:archived"),
        ("references/unlinkable-target", "warning", "path:notes/stable.md#link:inbox.md"),
        ("references/unlinkable-target", "warning", "path:notes/_index.md#link:inbox.md"),
    }


def test_a_target_excluded_by_path_is_linkable(tmp_path: Path) -> None:
    """A template excluded by path holds the metadata of its instances, so citing it is no breach."""
    _repository(tmp_path, exclude={"paths": ["templates/"]})
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates/capture.md").write_text("---\nstatus: inbox\n---\n", encoding="utf-8")
    (tmp_path / "notes/peer.md").write_text(
        "---\nstatus: stable\n---\n# Peer\n\n[skeleton](../templates/capture.md)\n",
        encoding="utf-8",
    )
    assert not [issue for issue in _unlinkable(tmp_path) if issue.rel == "notes/peer.md"]


def test_a_target_excluded_by_metadata_stays_unlinkable(tmp_path: Path) -> None:
    """An archived note left unchecked by an exclusion on its status is still unlinkable."""
    _repository(tmp_path, exclude={"where": [{"status": "archived"}]})
    cited = {issue.detail.split(":")[0] for issue in _unlinkable(tmp_path)}
    assert {"archived.md", "archived"} <= cited
