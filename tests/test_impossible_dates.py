"""Behavioral tests of the YAML timestamps that name an impossible date, such as ``2026-02-30``.

PyYAML parses such a timestamp, then fails to construct it with a ``ValueError`` rather than a
``yaml.YAMLError``. Every load of a file written by a user reports the file as unreadable or
invalid, as it reports a file that does not parse, and none raises.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from anagraphe.configuration import load_config
from anagraphe.core.configuration import ConfigurationError
from anagraphe.core.metadata import frontmatter_problem, split_frontmatter
from anagraphe.core.schemas import SchemaReader
from anagraphe.core.structured import _plain
from anagraphe.targets import TargetChecker, read_manifest

IMPOSSIBLE = "2026-02-30"
NOTE = f"---\nid: note-a\ncreated: {IMPOSSIBLE}\n---\nBody\n"


def test_a_frontmatter_naming_an_impossible_date_is_a_problem() -> None:
    problem = frontmatter_problem(NOTE)
    assert problem is not None and problem.startswith("the frontmatter is not valid YAML")
    assert split_frontmatter(NOTE) == ({}, "Body\n")


def test_a_value_reading_as_an_impossible_date_is_not_plain() -> None:
    assert _plain(IMPOSSIBLE) is False


def test_a_manifest_naming_an_impossible_date_is_invalid(tmp_path: Path) -> None:
    (tmp_path / "repository.yml").write_text(
        f"_schema: anagraphe:repository@1\nrepository: {{id: lab}}\ncreated: {IMPOSSIBLE}\n",
        encoding="utf-8",
    )
    reading = read_manifest(tmp_path)
    assert reading.manifest is None
    assert [problem.detail for problem in reading.problems][0].startswith(
        "repository.yml cannot be parsed"
    )


def test_a_configuration_naming_an_impossible_date_is_a_configuration_error(
    tmp_path: Path,
) -> None:
    path = tmp_path / "anagraphe.yml"
    path.write_text(f"_schema: anagraphe:configuration@2\ncreated: {IMPOSSIBLE}\n", "utf-8")
    with pytest.raises(ConfigurationError, match="cannot parse"):
        load_config(tmp_path, path)


def test_a_schema_registry_naming_an_impossible_date_is_a_configuration_error(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry.yml"
    registry.write_text(f"_schema: kleisis:schema-registry@2\ncreated: {IMPOSSIBLE}\n", "utf-8")
    with pytest.raises(ConfigurationError, match="cannot read the schema registry"):
        SchemaReader(tmp_path, registry)


def test_the_check_of_the_targets_reports_the_note_as_unreadable(tmp_path: Path) -> None:
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "a.md").write_text(NOTE, encoding="utf-8")
    path = tmp_path / "anagraphe.yml"
    path.write_text("_schema: anagraphe:configuration@2\ntargets: {}\n", encoding="utf-8")
    config = load_config(tmp_path, path).targets
    assert config is not None
    issues = TargetChecker(tmp_path, config).check().issues
    assert [(issue.rel, issue.kind) for issue in issues] == [("notes/a.md", "unreadable-record")]
