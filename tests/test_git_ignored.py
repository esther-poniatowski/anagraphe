"""Behavioral tests of the key ``git_ignored`` of an ``exclude`` mapping.

A session sharing a working tree with others keeps an unfinished file out of every check by listing
it in ``.git/info/exclude``. The file is then excluded from the walks, the indexes and the record
registry, and stays a valid target of a link. Git never ignores a tracked file, so the file is
checked again once it is added to Git.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from anagraphe_read._core.configuration import ConfigurationError

from anagraphe.cli import app
from anagraphe.configuration import load_config
from anagraphe.indexes.service import run
from anagraphe.references.service import ReferenceChecker
from anagraphe.targets.registry.service import RegistryService
from anagraphe.targets.service import TargetChecker

#: A rendered entry of an index, capturing the path of its link.
ENTRY = re.compile(r"^\s*- \[[^\]]*\]\(([^)]+)\)", re.MULTILINE)
#: The index of the folder ``m``, listing every member under one heading.
INDEX = (
    "---\naliases: [Module]\ngroups:\n  - {id: '*', heading: Entries}\n---\n\n# Module\n\n"
    "<!-- index groups -->\n<!-- /index -->\n"
)


def _note(identifier: str) -> str:
    """Return a Markdown note of the folder ``m`` declaring an identifier."""
    return (
        f"---\nid: {identifier}\naliases: [Note {identifier}]\nindex: '[Module](m/_index.md)'\n"
        f"---\n\n# Note {identifier}\n"
    )


def _write(root: Path, files: dict[str, str]) -> None:
    """Write files below a root, creating their folders."""
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _git(root: Path, *args: str) -> None:
    """Run a Git command in a repository, failing the test when Git fails."""
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _ignore_locally(root: Path, *patterns: str) -> None:
    """List patterns in the ignore file of the clone, which Git never commits."""
    with (root / ".git" / "info" / "exclude").open("a", encoding="utf-8") as stream:
        stream.write("".join(f"{pattern}\n" for pattern in patterns))


def _repository(root: Path, git_ignored: Any = True) -> None:
    """Write and track a repository holding the record ``note-a`` in the indexed folder ``m``."""
    _write(
        root,
        {
            "anagraphe.yml": yaml.safe_dump(
                {
                    "_schema": "anagraphe:configuration@3",
                    "exclude": {"git_ignored": git_ignored},
                    "repository": {"id": "lab"},
                    "targets": {},
                    "records": {},
                    "references": {},
                    "indexes": {
                        "entry_point": "_index.md",
                        "index_types": "config/index-types",
                        "inspect_git": False,
                    },
                }
            ),
            "config/index-types/module.schema.yaml": yaml.safe_dump(
                {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "$id": "module.schema.yaml",
                    "type": "object",
                    "x-default-mode": "registry",
                }
            ),
            "m/_index.md": INDEX,
            "m/a.md": _note("note-a"),
        },
    )
    _git(root, "init", "-q")
    _git(root, "add", ".")


def _registered(root: Path) -> list[str]:
    """Write the registry, and return the identifiers that it registers."""
    config = load_config(root, root / "anagraphe.yml")
    assert config.targets is not None and config.records is not None
    result = RegistryService(config.reading).write()
    assert result.registry is not None, result.issues
    return sorted(result.registry.records)


def _listed(root: Path) -> list[str]:
    """Write the indexes, and return the links of the entries of the index of ``m``."""
    config = load_config(root, root / "anagraphe.yml").indexes
    assert config is not None
    result = run(root, config, "write")
    assert result.blocking_count == 0, result.issues
    text = (root / "m" / "_index.md").read_text(encoding="utf-8")
    return ENTRY.findall(text.split("<!-- index groups -->")[1])


def test_a_file_ignored_by_the_clone_stays_out_of_every_generated_file(tmp_path: Path) -> None:
    _repository(tmp_path)
    _write(tmp_path, {"m/draft.md": _note("note-draft")})
    _ignore_locally(tmp_path, "m/draft.md")
    assert _registered(tmp_path) == ["note-a"]
    assert _listed(tmp_path) == ["a.md"]
    config = load_config(tmp_path, tmp_path / "anagraphe.yml")
    assert config.targets is not None and config.records is not None
    registry = RegistryService(config.reading)
    assert not registry.check().issues


def test_without_the_key_the_ignored_file_is_read(tmp_path: Path) -> None:
    _repository(tmp_path, git_ignored=False)
    _write(tmp_path, {"m/draft.md": _note("note-draft")})
    _ignore_locally(tmp_path, "m/draft.md")
    assert _registered(tmp_path) == ["note-a", "note-draft"]
    assert _listed(tmp_path) == ["a.md", "draft.md"]


def test_the_file_is_read_again_once_git_tracks_it(tmp_path: Path) -> None:
    _repository(tmp_path)
    _write(tmp_path, {"m/draft.md": _note("note-draft")})
    _ignore_locally(tmp_path, "m/draft.md")
    _git(tmp_path, "add", "-f", "m/draft.md")
    assert _registered(tmp_path) == ["note-a", "note-draft"]


def test_an_ignored_folder_is_excluded_with_all_it_holds(tmp_path: Path) -> None:
    _repository(tmp_path)
    _write(tmp_path, {"m/wip/b.md": _note("note-b"), "m/wip/c/d.md": _note("note-d")})
    _ignore_locally(tmp_path, "m/wip/")
    assert _registered(tmp_path) == ["note-a"]


def test_a_tracked_file_matching_an_ignore_rule_is_read(tmp_path: Path) -> None:
    _repository(tmp_path)
    _ignore_locally(tmp_path, "m/a.md")
    assert _registered(tmp_path) == ["note-a"]


def test_an_ignored_duplicate_is_not_reported(tmp_path: Path) -> None:
    _repository(tmp_path)
    _write(tmp_path, {"m/copy.md": _note("note-a")})
    _ignore_locally(tmp_path, "m/copy.md")
    config = load_config(tmp_path, tmp_path / "anagraphe.yml")
    assert config.targets is not None
    checker = TargetChecker(config.reading)
    assert not checker.check().issues


def test_a_link_into_an_ignored_file_stays_valid(tmp_path: Path) -> None:
    _repository(tmp_path)
    _write(
        tmp_path,
        {
            "m/draft.md": _note("note-draft"),
            "m/b.md": "See [the draft](draft.md) and [a lost note](lost.md).\n",
        },
    )
    _ignore_locally(tmp_path, "m/draft.md")
    config = load_config(tmp_path, tmp_path / "anagraphe.yml").references
    assert config is not None
    report = ReferenceChecker(tmp_path, config).check()
    # The broken link shows that the checker reads the note; the link into the draft resolves.
    reported = [issue for issue in report.issues if issue.rel == "m/b.md"]
    assert len(reported) == 1 and "lost.md" in reported[0].detail


def test_the_global_excludes_file_is_not_read(tmp_path: Path) -> None:
    """Two clones of one commit agree, whatever the global excludes file of each machine holds."""
    _repository(tmp_path)
    _write(tmp_path, {"m/draft.md": _note("note-draft"), "global-ignore": "m/draft.md\n"})
    _git(tmp_path, "config", "core.excludesFile", str(tmp_path / "global-ignore"))
    assert _registered(tmp_path) == ["note-a", "note-draft"]


def test_a_file_ignored_by_a_committed_rule_is_excluded_without_a_note(tmp_path: Path) -> None:
    _repository(tmp_path)
    _write(tmp_path, {"m/draft.md": _note("note-draft"), ".gitignore": "m/draft.md\n"})
    assert _registered(tmp_path) == ["note-a"]
    result = CliRunner().invoke(app, ["records", "check", "--root", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "locally-excluded" not in result.output


def test_a_locally_excluded_file_is_reported_as_a_note(tmp_path: Path) -> None:
    _repository(tmp_path)
    _write(tmp_path, {"m/draft.md": _note("note-draft"), "m/wip/b.md": _note("note-b")})
    _ignore_locally(tmp_path, "m/draft.md", "m/wip/")
    assert _registered(tmp_path) == ["note-a"]
    result = CliRunner().invoke(app, ["records", "check", "--root", str(tmp_path)])
    assert result.exit_code == 0, result.output
    notes = [line for line in result.output.splitlines() if ": note: locally-excluded" in line]
    assert notes == [
        "m/draft.md:1: note: locally-excluded: a rule of .git/info/exclude leaves the file out of "
        "every check, until Git tracks it",
        "m/wip/:1: note: locally-excluded: a rule of .git/info/exclude leaves the folder out of "
        "every check, until Git tracks it",
    ]
    log = tmp_path / "check.sarif"
    sarif = CliRunner().invoke(
        app,
        ["records", "check", "--root", str(tmp_path), "--format", "sarif", "--output", str(log)],
    )
    assert sarif.exit_code == 0, sarif.output
    results = json.loads(log.read_text(encoding="utf-8"))["runs"][0]["results"]
    assert (
        sorted(
            (result["ruleId"], result["level"])
            for result in results
            if "locally-excluded" in result["ruleId"]
        )
        == [("exclusions/locally-excluded", "note")] * 2
    )


def test_a_local_rule_over_an_excluded_path_raises_no_note(tmp_path: Path) -> None:
    """A hidden folder or a path of a declared pattern stays out of the checks without the rule."""
    _repository(tmp_path)
    _write(tmp_path, {".workspace/a.md": _note("note-w"), "vendor/b.md": _note("note-v")})
    _write(
        tmp_path,
        {
            "anagraphe.yml": (tmp_path / "anagraphe.yml")
            .read_text()
            .replace("git_ignored: true", "git_ignored: true\n  paths: [vendor/]")
        },
    )
    _ignore_locally(tmp_path, ".workspace/", "vendor/")
    assert _registered(tmp_path) == ["note-a"]
    result = CliRunner().invoke(app, ["records", "check", "--root", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "locally-excluded" not in result.output


def test_the_key_outside_a_work_tree_is_refused(tmp_path: Path) -> None:
    _repository(tmp_path)
    subprocess.run(["rm", "-rf", str(tmp_path / ".git")], check=True)
    with pytest.raises(ConfigurationError, match="exclude.git_ignored reads the files"):
        load_config(tmp_path, tmp_path / "anagraphe.yml")


def test_the_key_must_be_a_boolean(tmp_path: Path) -> None:
    _repository(tmp_path, git_ignored="yes")
    with pytest.raises(ConfigurationError, match="exclude.git_ignored must be a boolean"):
        load_config(tmp_path, tmp_path / "anagraphe.yml")
