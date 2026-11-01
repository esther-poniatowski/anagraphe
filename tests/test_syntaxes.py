"""Behavioral tests for the declared syntaxes and metadata sources (ADR 0003)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from anagraphe.configuration import load_config
from anagraphe.references.service import ReferenceChecker
from anagraphe.refactor import MoveService

#: The files cited by every case.
TARGETS = {
    "b/target.md": "# Target\n",
    "sections/intro.tex": "Intro.\n",
    "fig/plot.png": "png",
    "data/x.csv": "a,b\n",
}


def _write(root: Path, files: dict[str, str]) -> None:
    """Write fixture files below a repository root."""
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _repository(
    root: Path, files: dict[str, str], top: dict[str, Any] | None = None, **section: Any
) -> None:
    """Write the targets, the given files, and a configuration with the section references."""
    _write(root, {**TARGETS, **files})
    declared = {"schema_version": 2, **(top or {}), "references": section}
    _write(root, {"anagraphe.yml": yaml.safe_dump(declared)})


def _issues(root: Path) -> list[tuple[str, str, str]]:
    """Return the file, the kind and the target of each issue of the fixture repository."""
    config = load_config(root, root / "anagraphe.yml").references
    assert config is not None
    return [
        (issue.rel, issue.kind, issue.detail.split(": ")[0])
        for issue in ReferenceChecker(root, config).check().issues
    ]


class FileMover:
    """Rename with the file system."""

    def move(self, root: Path, old: str, new: str) -> None:
        (root / new).parent.mkdir(parents=True, exist_ok=True)
        (root / old).rename(root / new)


def _move(root: Path, old: str, new: str) -> None:
    """Move a file of the fixture repository."""
    service = MoveService(
        root, load_config(root, root / "anagraphe.yml"), "anagraphe.yml", FileMover()
    )
    service.apply(service.plan(old, new))


def test_code_paths_are_pointers_when_they_resolve(tmp_path: Path) -> None:
    """A backticked path naming a file follows the format convention; one naming none is ignored."""
    _repository(
        tmp_path,
        {"notes/a.md": "See `../b/target.md` and `path/to/example.md`.\n"},
        conventions=[{"format": "markdown"}],
    )
    assert _issues(tmp_path) == [("notes/a.md", "link-format", "../b/target.md")]


def test_code_paths_are_strict_where_a_rule_says_so(tmp_path: Path) -> None:
    """A rule declaring the syntax code strict reports a backticked path that names no file."""
    _repository(
        tmp_path,
        {"docs/a.md": "Run `utils/gone.py`.\n", "notes/a.md": "Run `utils/gone.py`.\n"},
        conventions=[{"when": {"paths": ["/docs/"]}, "strict": ["markdown", "wikilink", "code"]}],
    )
    assert _issues(tmp_path) == [("docs/a.md", "broken", "utils/gone.py")]


def test_several_formats_may_be_admitted(tmp_path: Path) -> None:
    """A convention admitting Markdown links and backticked paths accepts both."""
    _repository(
        tmp_path,
        {"notes/a.md": "[T](../b/target.md) and `../b/target.md`, not [[target]].\n"},
        conventions=[{"format": ["markdown", "code"], "path": ["relative", "shortest"]}],
    )
    assert _issues(tmp_path) == [("notes/a.md", "link-format", "target")]


def test_latex_targets_omit_their_suffix(tmp_path: Path) -> None:
    """LaTeX commands name files without suffix, outside comments, and a missing one is reported."""
    _repository(
        tmp_path,
        {
            "main.tex": (
                "\\input{sections/intro}\n\\includegraphics[width=3cm]{fig/plot}\n"
                "% \\input{commented}\n\\input{sections/missing}\n\\input{\\macro}\n"
            )
        },
    )
    assert _issues(tmp_path) == [("main.tex", "broken", "sections/missing")]


def test_latex_syntax_can_be_disabled(tmp_path: Path) -> None:
    """A repository disables a built-in syntax, which then reads no file."""
    _repository(tmp_path, {"main.tex": "\\input{gone}\n"}, syntaxes={"latex": {"enabled": False}})
    assert _issues(tmp_path) == []


def test_pattern_syntax_reads_code(tmp_path: Path) -> None:
    """A declared pattern reads the string paths of Python files, outside comments."""
    _repository(
        tmp_path,
        {"tools/load.py": 'DATA = "data/x.csv"\nOTHER = "data/gone.csv"  # "data/old.csv"\n'},
        syntaxes={
            "python": {
                "when": {"types": ["py"]},
                "pattern": "[\"'](?P<target>[\\w./-]+/[\\w.-]+)[\"']",
                "comment": "#",
            }
        },
        conventions=[{"when": {"types": ["py"]}, "path": "root"}],
    )
    assert _issues(tmp_path) == [("tools/load.py", "broken", "data/gone.csv")]


def test_key_syntax_reads_json_and_toml(tmp_path: Path) -> None:
    """A syntax of keys reads the values of JSON and TOML documents."""
    _repository(
        tmp_path,
        {
            "config/app.json": '{"inputs": {"source": "data/x.csv"}, "other": {"source": "data/gone.csv"}}',
            "config/tool.toml": '[tool]\nsource = "b/target.md"\n',
        },
        syntaxes={"sources": {"when": {"types": ["json", "toml"]}, "keys": ["source"]}},
        conventions=[{"when": {"types": ["json", "toml"]}, "path": "root"}],
    )
    assert _issues(tmp_path) == [("config/app.json", "broken", "data/gone.csv")]


def test_metadata_sources_are_declared_by_type(tmp_path: Path) -> None:
    """Exclusions read the fields of TOML and JSON files at declared paths, and none where declared."""
    _repository(
        tmp_path,
        {
            "a.toml": '[project]\nstatus = "archived"\nsource = "gone.md"\n',
            "b.json": '{"meta": {"status": "archived"}, "source": "gone.md"}',
            "c.json": '{"meta": {"status": "live"}, "source": "gone.md"}',
            "legacy/old.md": "---\nstatus: archived\n---\n[gone](gone.md)\n",
        },
        top={
            "metadata": [
                {"when": {"types": ["toml"]}, "from": {"toml": ["project"]}},
                {"when": {"types": ["json"]}, "from": {"json": ["meta"]}},
                {"when": {"paths": ["/legacy/"]}, "from": "none"},
            ],
            "exclude": {"where": [{"status": "archived"}]},
        },
        syntaxes={"sources": {"when": {"types": ["json", "toml"]}, "keys": ["source"]}},
    )
    assert sorted(_issues(tmp_path)) == [
        ("c.json", "broken", "gone.md"),
        ("legacy/old.md", "broken", "gone.md"),
    ]


def test_regions_follow_the_declared_source(tmp_path: Path) -> None:
    """A YAML source at the path metadata makes that block the metadata, and the rest the content."""
    _repository(
        tmp_path,
        {
            "specs/record.yml": (
                "metadata: {index: '[T](b/target.md)'}\nsummary: 'See [T](../b/target.md).'\n"
            )
        },
        top={"metadata": [{"when": {"types": ["yml"]}, "from": {"yaml": ["metadata"]}}]},
        syntaxes={"markdown": {"when": {"types": ["md", "yml"]}}},
    )
    assert _issues(tmp_path) == []


def test_move_keeps_each_syntax(tmp_path: Path) -> None:
    """A move rewrites LaTeX, backticked, pattern and key pointers, each in its own spelling."""
    _repository(
        tmp_path,
        {
            "main.tex": "\\input{sections/intro}\n",
            "notes/a.md": "See `../sections/intro.tex`.\n",
            "tools/load.py": 'PATH = "sections/intro.tex"\n',
            "config/app.json": '{"source": "sections/intro.tex"}',
        },
        syntaxes={"sources": {"when": {"types": ["json"]}, "keys": ["source"]}},
    )
    _move(tmp_path, "sections/intro.tex", "chapters/opening.tex")
    assert (tmp_path / "main.tex").read_text(encoding="utf-8") == "\\input{chapters/opening}\n"
    assert (tmp_path / "notes/a.md").read_text(
        encoding="utf-8"
    ) == "See `../chapters/opening.tex`.\n"
    assert (tmp_path / "tools/load.py").read_text(
        encoding="utf-8"
    ) == 'PATH = "chapters/opening.tex"\n'
    assert (tmp_path / "config/app.json").read_text(
        encoding="utf-8"
    ) == '{"source": "chapters/opening.tex"}'
