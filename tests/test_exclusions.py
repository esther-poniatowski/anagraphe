"""Behavioral tests for the exclusions by pattern and by metadata (ADR 0003)."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from anagraphe.configuration import load_config
from anagraphe.core.exclusions import Exemptions
from anagraphe.core.filters import Filter
from anagraphe.indexes.service import run
from anagraphe.references.service import ReferenceChecker
from anagraphe.refactor import MoveService

BROKEN = "[gone](gone.md)\n"


def _write(root: Path, files: dict[str, str]) -> None:
    """Write fixture files below a repository root."""
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _configure(root: Path, **sections: Any) -> None:
    """Write a configuration holding the given sections."""
    _write(root, {"anagraphe.yml": yaml.safe_dump({"schema_version": 2, **sections})})


def _broken(root: Path) -> list[str]:
    """Return the files holding a broken reference, under the section references."""
    config = load_config(root, root / "anagraphe.yml").references
    assert config is not None
    return [issue.rel for issue in ReferenceChecker(root, config).check().issues]


def test_exception_keeps_the_entry_point_of_an_excluded_folder(tmp_path: Path) -> None:
    """The files of a folder are excluded, and an exception keeps its index."""
    _write(tmp_path, {"macros/rename.md": BROKEN, "macros/_index.md": BROKEN})
    _configure(tmp_path, references={"exclude": {"paths": ["macros/*", "!macros/_index.md"]}})
    assert _broken(tmp_path) == ["macros/_index.md"]


def test_hidden_paths_are_excluded_unless_admitted(tmp_path: Path) -> None:
    """A hidden folder is excluded by default, and an exception admits one of them."""
    _write(tmp_path, {".cache/x.md": BROKEN, ".github/README.md": BROKEN, ".git/x.md": BROKEN})
    _configure(tmp_path, references={"exclude": {"paths": ["!.github/", "!.git/"]}})
    assert _broken(tmp_path) == [".github/README.md"]


def test_metadata_filters_exclude_notes_and_records(tmp_path: Path) -> None:
    """A note or a record whose metadata one filter selects is excluded, at its top or in metadata."""
    _write(
        tmp_path,
        {
            "archived.md": f"---\nstatus: archived\n---\n{BROKEN}",
            "audit.md": f"---\nrole: audit\n---\n{BROKEN}",
            "live.md": f"---\nstatus: wip\nrole: note\n---\n{BROKEN}",
            "decision.yml": "role: decision\nsource: '[gone](gone.md)'\n",
            "record.yml": "metadata: {status: archived}\nsource: '[gone](gone.md)'\n",
            "kept.yml": "role: plan\nsource: '[gone](gone.md)'\n",
        },
    )
    _configure(
        tmp_path,
        references={
            "syntaxes": {"markdown": {"when": {"types": ["md", "yml"]}}},
            "exclude": {"where": [{"status": "archived"}, {"role": ["audit", "decision"]}]},
        },
    )
    assert sorted(_broken(tmp_path)) == ["kept.yml", "live.md"]


def test_excluded_file_stays_a_valid_target(tmp_path: Path) -> None:
    """A link to an excluded note resolves, since an exclusion removes holders, not targets."""
    _write(
        tmp_path,
        {"old.md": "---\nstatus: archived\n---\n# Old\n", "new.md": "[old](old.md)\n"},
    )
    _configure(tmp_path, references={"exclude": {"where": [{"status": "archived"}]}})
    assert _broken(tmp_path) == []


def test_section_patterns_prevail_over_shared_ones(tmp_path: Path) -> None:
    """A section exception admits a file that the shared patterns exclude, like a later line."""
    _write(tmp_path, {"README.md": BROKEN, "docs/README.md": BROKEN})
    _configure(
        tmp_path,
        exclude={"paths": ["README.md"]},
        references={"exclude": {"paths": ["!/README.md"]}},
    )
    assert _broken(tmp_path) == ["README.md"]


def test_gitignore_is_read_only_on_request(tmp_path: Path) -> None:
    """The root .gitignore excludes its paths only when the exclusion asks to read it."""
    _write(tmp_path, {".gitignore": "build/\n", "build/out.md": BROKEN})
    _configure(tmp_path, references={})
    assert _broken(tmp_path) == ["build/out.md"]
    _configure(tmp_path, references={"exclude": {"gitignore": True}})
    assert _broken(tmp_path) == []


def test_union_orders_the_section_patterns_last() -> None:
    """The union keeps the shared patterns first, so a section exception prevails."""
    shared = Exemptions(("*.md",), (Filter((("status", ("archived",)),)),))
    section = Exemptions(("!keep.md",))
    union = shared.union(section)
    assert union.patterns == ("*.md", "!keep.md")
    assert [union.contains(PurePosixPath(rel)) for rel in ("a.md", "keep.md")] == [True, False]


def test_indexes_leave_out_an_excluded_member(tmp_path: Path) -> None:
    """An archived note excluded from the indexes is listed by no generated region."""
    _write(
        tmp_path,
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
            "m/_index.md": (
                "---\naliases: [Module]\ngroups:\n  - {id: '*', heading: Notes}\n---\n\n# Module\n\n"
                "<!-- index groups -->\n<!-- /index -->\n"
            ),
            "m/live.md": "---\naliases: [Live]\nindex: '[Module](m/_index.md)'\n---\n\n# Live\n",
            "m/old.md": (
                "---\naliases: [Old]\nstatus: archived\nindex: '[Module](m/_index.md)'\n---\n\n# Old\n"
            ),
        },
    )
    _configure(
        tmp_path,
        indexes={
            "vocabulary": "config/vocabulary.yml",
            "index_types": "config/index-types",
            "inspect_git": False,
            "exclude": {"where": [{"status": "archived"}]},
        },
    )
    config = load_config(tmp_path, tmp_path / "anagraphe.yml").indexes
    assert config is not None
    result = run(tmp_path, config, "write")
    assert result.blocking_count == 0, result.issues
    region = (
        (tmp_path / "m/_index.md").read_text(encoding="utf-8").split("<!-- index groups -->")[1]
    )
    assert "(live.md)" in region and "old.md" not in region


def test_move_leaves_an_excluded_holder_and_reports_it(tmp_path: Path) -> None:
    """A move does not rewrite a holder excluded by its metadata, and reports its old path."""
    _write(
        tmp_path,
        {
            "a.md": "# A\n",
            "live.md": "[a](a.md)\n",
            "decision.md": "---\nrole: decision\n---\nWe moved [a](a.md).\n",
        },
    )
    _configure(tmp_path, references={"exclude": {"where": [{"role": "decision"}]}})

    class FileMover:
        """Rename with the file system."""

        def move(self, root: Path, old: str, new: str) -> None:
            (root / new).parent.mkdir(parents=True, exist_ok=True)
            (root / old).rename(root / new)

    service = MoveService(
        tmp_path, load_config(tmp_path, tmp_path / "anagraphe.yml"), "anagraphe.yml", FileMover()
    )
    result = service.apply(service.plan("a.md", "b.md"))
    assert (tmp_path / "live.md").read_text(encoding="utf-8") == "[a](b.md)\n"
    assert "[a](a.md)" in (tmp_path / "decision.md").read_text(encoding="utf-8")
    assert [residue.rel for residue in result.residues] == ["decision.md"]
