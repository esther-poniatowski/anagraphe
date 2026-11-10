"""Behavioral tests for the moves that preserve the pointers and the indexes (ADR 0003)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from anagraphe.cli import app
from anagraphe.configuration import load_config
from anagraphe.core.files import TargetError
from anagraphe.refactor import MoveService

SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "module.schema.yaml",
    "type": "object",
    "x-default-mode": "registry",
}


def _write(root: Path, files: dict[str, str]) -> None:
    """Write fixture files below a repository root."""
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _note(title: str, index: str, body: str = "", purpose: str = "") -> str:
    """Return a note listed by an index, with its title and an optional purpose."""
    fields = {"role": "note", "aliases": [title], "index": index}
    if purpose:
        fields["purpose"] = purpose
    return f"---\n{yaml.safe_dump(fields, sort_keys=False)}---\n\n# {title}\n{body}"


def _index(title: str, groups: str) -> str:
    """Return an index with its groups and an empty generated region."""
    return (
        f"---\nrole: index\naliases: [{title}]\ngroups:\n{groups}---\n\n# {title}\n\n"
        "<!-- index groups -->\n<!-- /index -->\n"
    )


def _repository(root: Path) -> None:
    """Write a repository of two indexed folders, a record, an excluded file and a configuration."""
    _write(
        root,
        {
            "config/vocabulary.yml": yaml.safe_dump(
                {"schema": {"entry_point": "_index.md"}, "roles": {"index": {}, "note": {}}}
            ),
            "config/index-types/module.schema.yaml": yaml.safe_dump(SCHEMA),
            "m/_index.md": _index(
                "Module",
                "  - id: listed\n    heading: Listed\n    mode: sequence\n    members:\n"
                '      - "[A](m/a.md)"\n      - "[B](m/b.md)"\n',
            ),
            "m/a.md": _note("A", "[Module](m/_index.md)", "See [B](b.md#^claim).\n"),
            "m/b.md": _note("B", "[Module](m/_index.md)", "A claim. ^claim\n"),
            "n/_index.md": _index("Next", "  - {id: '*', heading: Entries}\n"),
            "notes.md": "Read [A](m/a.md) and the file m/a.md.\n",
            "loose/keep.md": "A folder ./m/ and a path ./n/_index.md stay as written.\n",
            "specs/record.yml": "source: m/a.md#^x\ndoi: 10.1000/m/a.md\n",
            "archive/old.md": "An old pointer to m/a.md.\n",
            "anagraphe.yml": yaml.safe_dump(
                {
                    "schema_version": 2,
                    "indexes": {
                        "vocabulary": "config/vocabulary.yml",
                        "index_types": "config/index-types",
                        "inspect_git": False,
                        "sequences": {"m": ["a.md", "b.md"]},
                        "exclude": {"paths": ["archive/", "config/", "specs/"]},
                    },
                    "references": {"exclude": {"paths": ["archive/"]}},
                }
            ),
        },
    )


class FileMover:
    """Rename with the file system only, so that the tests need no Git repository."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def move(self, root: Path, old: str, new: str) -> None:
        if self.fail:
            raise OSError("injected rename failure")
        (root / new).parent.mkdir(parents=True, exist_ok=True)
        (root / old).rename(root / new)


def _service(root: Path, mover: FileMover | None = None) -> MoveService:
    """Return the move service of the fixture repository."""
    return MoveService(
        root, load_config(root, root / "anagraphe.yml"), "anagraphe.yml", mover or FileMover()
    )


def _fields(text: str) -> dict[str, object]:
    """Return the fields of the frontmatter of a note."""
    return dict(yaml.safe_load(text.split("---\n")[1]))


def _read(root: Path, rel: str) -> str:
    """Return the text of one file of the fixture repository."""
    return (root / rel).read_text(encoding="utf-8")


def test_move_rewrites_pointers_and_indexes(tmp_path: Path) -> None:
    """A moved note keeps every pointer to it, and both indexes follow the move."""
    _repository(tmp_path)
    service = _service(tmp_path)
    result = service.apply(service.plan("m/a.md", "n/a.md"))
    assert not (tmp_path / "m/a.md").exists()
    moved = _read(tmp_path, "n/a.md")
    assert _fields(moved)["index"] == "[Next](n/_index.md)"
    assert "[B](../m/b.md#^claim)" in moved
    assert _read(tmp_path, "notes.md") == "Read [A](n/a.md) and the file n/a.md.\n"
    assert _read(tmp_path, "loose/keep.md") == (
        "A folder ./m/ and a path ./n/_index.md stay as written.\n"
    )
    assert _read(tmp_path, "specs/record.yml") == "source: n/a.md#^x\ndoi: 10.1000/m/a.md\n"
    assert _fields(_read(tmp_path, "m/_index.md"))["groups"][0]["members"] == ["[B](m/b.md)"]
    sequences = yaml.safe_load(_read(tmp_path, "anagraphe.yml"))["indexes"]["sequences"]
    assert sequences == {"m": ["b.md"]}
    assert "(a.md)" in _read(tmp_path, "n/_index.md").split("<!-- index groups -->")[1]
    assert [(residue.rel, residue.line) for residue in result.residues] == [("archive/old.md", 1)]
    assert result.check is not None and result.check.blocking_count == 0


def test_rename_within_a_folder_keeps_the_lists(tmp_path: Path) -> None:
    """A member renamed inside its folder stays in its explicit list and in its manifest."""
    _repository(tmp_path)
    service = _service(tmp_path)
    service.apply(service.plan("m/a.md", "m/alpha.md"))
    assert '- "[A](m/alpha.md)"' in _read(tmp_path, "m/_index.md")
    assert yaml.safe_load(_read(tmp_path, "anagraphe.yml"))["indexes"]["sequences"] == {
        "m": ["alpha.md", "b.md"]
    }
    assert _fields(_read(tmp_path, "m/alpha.md"))["index"] == "[Module](m/_index.md)"


def test_folder_move_rewrites_every_file_below_it(tmp_path: Path) -> None:
    """A moved folder carries its index, its manifest key, and every pointer into it."""
    _repository(tmp_path)
    service = _service(tmp_path)
    service.apply(service.plan("m", "parts/m"))
    assert _read(tmp_path, "notes.md") == "Read [A](parts/m/a.md) and the file parts/m/a.md.\n"
    assert '- "[A](parts/m/a.md)"' in _read(tmp_path, "parts/m/_index.md")
    assert _fields(_read(tmp_path, "parts/m/a.md"))["index"] == "[Module](parts/m/_index.md)"
    assert "[B](b.md#^claim)" in _read(tmp_path, "parts/m/a.md")
    assert "parts/m" in yaml.safe_load(_read(tmp_path, "anagraphe.yml"))["indexes"]["sequences"]


def test_dry_run_changes_no_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The dry run prints the plan, and every file keeps its bytes."""
    _repository(tmp_path)
    monkeypatch.chdir(tmp_path)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    result = CliRunner().invoke(
        app, ["move", "m/a.md", "n/a.md", "--dry-run", "--root", str(tmp_path)]
    )
    assert result.exit_code == 0, result.stdout
    assert "rename m/a.md -> n/a.md" in result.stdout
    assert "edit notes.md:1: m/a.md -> n/a.md" in result.stdout
    assert "dry run, no file changed" in result.stdout
    assert {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before


def test_failed_rename_restores_every_file(tmp_path: Path) -> None:
    """When the rename fails, every edited file returns to its bytes before the move."""
    _repository(tmp_path)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    service = _service(tmp_path, FileMover(fail=True))
    with pytest.raises(OSError, match="injected rename failure"):
        service.apply(service.plan("m/a.md", "n/a.md"))
    assert {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("m/gone.md", "n/gone.md", "target does not exist"),
        ("m/a.md", "m/b.md", "destination already exists"),
        ("m", "m/inner", "a folder cannot move into itself"),
        ("m/a.md", "../outside.md", "target lies outside the repository"),
    ],
)
def test_invalid_moves_are_refused(tmp_path: Path, old: str, new: str, message: str) -> None:
    """A move naming no source, an existing destination, or a path outside the root is refused."""
    _repository(tmp_path)
    with pytest.raises(TargetError, match=message):
        _service(tmp_path).plan(old, new)


def test_git_mover_records_the_rename(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """In a Git repository, a tracked file is renamed with git mv, so Git records a rename."""
    _repository(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.org",
            "commit",
            "-qm",
            "init",
        ],
        cwd=tmp_path,
        check=True,
    )
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["move", "m/a.md", "n/a.md", "--yes"])
    assert result.exit_code == 0, result.stdout
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout
    assert any(
        line.startswith("R") and line.endswith("m/a.md -> n/a.md") for line in status.splitlines()
    ), status


class _Terminal:
    """A standard input that reports a terminal, so that the move asks for its confirmation."""

    def __init__(self) -> None:
        self.stdin = self

    def isatty(self) -> bool:
        return True


def _snapshot(root: Path) -> dict[Path, bytes]:
    return {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_move_without_terminal_requires_yes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without a terminal and without --yes, the move stops with status 2 and changes no file."""
    _repository(tmp_path)
    monkeypatch.chdir(tmp_path)
    before = _snapshot(tmp_path)
    result = CliRunner().invoke(app, ["move", "m/a.md", "n/a.md"])
    assert result.exit_code == 2
    assert "pass --yes" in result.output
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize(("answer", "status", "moved"), [("n\n", 1, False), ("y\n", 0, True)])
def test_move_on_a_terminal_asks_for_a_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, answer: str, status: int, moved: bool
) -> None:
    """On a terminal, the move applies its plan only once the researcher confirms it."""
    _repository(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("anagraphe.cli.sys", _Terminal())
    before = _snapshot(tmp_path)
    result = CliRunner().invoke(app, ["move", "m/a.md", "n/a.md"], input=answer)
    assert result.exit_code == status, result.output
    assert "apply the move?" in result.output
    assert (tmp_path / "n/a.md").is_file() is moved
    if not moved:
        assert _snapshot(tmp_path) == before
