"""Behavioral tests for the conventions of link formats and path styles (ADR 0003)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from anagraphe.configuration import load_config
from anagraphe.references.service import ReferenceChecker
from anagraphe.refactor import MoveService

#: The files cited by every case.
TARGETS = {
    "b/target.md": "# Target\n\nA block. ^block\n",
    "proj/notes/a.md": "# A\n",
    "old/twin.md": "# Twin\n",
    "new/twin.md": "# Twin\n",
}


def _write(root: Path, files: dict[str, str]) -> None:
    """Write fixture files below a repository root."""
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _repository(root: Path, files: dict[str, str], **section: Any) -> None:
    """Write the targets, the given files, and a configuration with the section references."""
    _write(root, {**TARGETS, **files})
    _write(root, {"anagraphe.yml": yaml.safe_dump({"_schema": "anagraphe:configuration@2", "references": section})})


def _issues(root: Path) -> list[tuple[str, str, str]]:
    """Return the file, the kind and the target of each issue of the fixture repository."""
    config = load_config(root, root / "anagraphe.yml").references
    assert config is not None
    return [
        (issue.rel, issue.kind, issue.detail.split(": ")[0])
        for issue in ReferenceChecker(root, config).check().issues
    ]


def test_wikilinks_resolve_under_each_style(tmp_path: Path) -> None:
    """A wikilink resolves by its end, from its folder or from the root, its suffix .md omitted."""
    _repository(
        tmp_path,
        {
            "a/note.md": (
                "[[target]] [[target#^block|Block]] [[../b/target]] ![[b/target.md]]\n"
                "[[missing]] [[twin]] [[target#^gone]]\n"
            )
        },
        conventions=[{"path": ["relative", "root", "shortest"]}],
    )
    assert _issues(tmp_path) == [
        ("a/note.md", "broken", "missing"),
        ("a/note.md", "ambiguous-link", "twin"),
        ("a/note.md", "broken-anchor", "target#^gone"),
    ]


def test_link_format_is_enforced_where_declared(tmp_path: Path) -> None:
    """A wikilink breaks a convention of Markdown links, except where a later rule admits it."""
    _repository(
        tmp_path,
        {
            "a/note.md": "[[target]] and [target](../b/target.md)\n",
            "journal/day.md": "[[target]]\n",
        },
        conventions=[
            {"format": "markdown"},
            {"when": {"paths": ["/journal/"]}, "format": "wikilink", "path": "shortest"},
        ],
    )
    assert _issues(tmp_path) == [
        ("a/note.md", "link-format", "target"),
        ("a/note.md", "convention", "target"),
    ]


def test_conditions_by_type_metadata_and_region(tmp_path: Path) -> None:
    """A rule applies by file type, by metadata, or by region, and the others keep the defaults."""
    _repository(
        tmp_path,
        {
            "specs/record.yml": "summary: 'See [T](../b/target.md).'\n",
            "a/decision.md": "---\nrole: decision\n---\n[T](/b/target.md)\n",
            "a/plain.md": "[T](/b/target.md)\n",
        },
        syntaxes={"markdown": {"when": {"types": ["md", "yml"]}}},
        conventions=[
            {"when": {"types": ["yml"]}, "path": "relative"},
            {"when": {"where": [{"role": "decision"}], "regions": ["content"]}, "path": "absolute"},
        ],
    )
    assert _issues(tmp_path) == [("a/plain.md", "convention", "/b/target.md")]


def test_base_style_resolves_from_a_declared_folder(tmp_path: Path) -> None:
    """A path of a project written from the root of the project resolves under its base style."""
    _repository(
        tmp_path,
        {"proj/docs/x.md": "[A](notes/a.md) beside [T](../../b/target.md)\n"},
        conventions=[{"when": {"paths": ["/proj/"]}, "path": [{"base": "proj"}, "relative"]}],
    )
    assert _issues(tmp_path) == []


def test_cascade_overrides_only_the_keys_set(tmp_path: Path) -> None:
    """A later rule setting only a format keeps the path style of an earlier rule."""
    _repository(
        tmp_path,
        {"a/note.md": "[[b/target]]\n"},
        conventions=[{"path": "root"}, {"format": "wikilink"}],
    )
    assert _issues(tmp_path) == []


class FileMover:
    """Rename with the file system."""

    def move(self, root: Path, old: str, new: str) -> None:
        (root / new).parent.mkdir(parents=True, exist_ok=True)
        (root / old).rename(root / new)


def test_move_keeps_the_format_and_the_style_of_each_pointer(tmp_path: Path) -> None:
    """A move respells a wikilink by its new shortest end, and keeps absolute and base paths."""
    _repository(
        tmp_path,
        {
            "a/note.md": (
                "[[target]] [[target#^block|B]] [[b/target]] [T](/b/target.md) "
                "[T](../b/target.md)\n"
            ),
            "proj/docs/x.md": "[A](notes/a.md)\n",
        },
        conventions=[
            {"path": ["relative", "root", "absolute", "shortest"]},
            {"when": {"paths": ["/proj/"]}, "path": {"base": "proj"}},
        ],
    )
    config = load_config(tmp_path, tmp_path / "anagraphe.yml")
    service = MoveService(tmp_path, config, "anagraphe.yml", FileMover())
    service.apply(service.plan("b/target.md", "d/goal.md"))
    assert (tmp_path / "a/note.md").read_text(encoding="utf-8") == (
        "[[goal]] [[goal#^block|B]] [[d/goal]] [T](/d/goal.md) [T](../d/goal.md)\n"
    )
    service = MoveService(
        tmp_path, load_config(tmp_path, tmp_path / "anagraphe.yml"), "anagraphe.yml", FileMover()
    )
    service.apply(service.plan("proj/notes/a.md", "proj/notes/sub/a.md"))
    assert (tmp_path / "proj/docs/x.md").read_text(encoding="utf-8") == "[A](notes/sub/a.md)\n"


def test_move_onto_a_shared_name_writes_a_longer_end(tmp_path: Path) -> None:
    """A wikilink to a note moved onto a name that other notes hold takes an end naming it alone."""
    _repository(
        tmp_path,
        {"a/note.md": "[[target]]\n"},
        conventions=[{"format": "wikilink", "path": "shortest"}],
    )
    service = MoveService(
        tmp_path, load_config(tmp_path, tmp_path / "anagraphe.yml"), "anagraphe.yml", FileMover()
    )
    service.apply(service.plan("b/target.md", "d/twin.md"))
    assert (tmp_path / "a/note.md").read_text(encoding="utf-8") == "[[d/twin]]\n"
    assert _issues(tmp_path) == []


def test_math_holds_no_link(tmp_path: Path) -> None:
    """Brackets inside inline or display math, such as a ring of power series, are no wikilink."""
    _repository(
        tmp_path,
        {"a/math.md": "The ring $V[[t]]$ costs $5 and $6 [[gone]].\n$$\nA[[x]]\n$$\n$$B[[y]]$$\n"},
    )
    assert _issues(tmp_path) == [("a/math.md", "broken", "gone")]
