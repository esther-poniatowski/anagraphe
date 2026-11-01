"""Behavioral tests for the check of the references between the files of a repository (ADR 0003).

The cases of :data:`PLANTED` are those of the link checker of the Geonexus vault, ported with
their expected counts, so that the port is shown to report what the source reported.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from anagraphe.cli import app
from anagraphe.configuration import load_config
from anagraphe.core.configuration import ConfigurationError
from anagraphe.core.issues import Report
from anagraphe.references.configuration import ReferenceConfig
from anagraphe.references.service import ReferenceChecker
from anagraphe.references.syntaxes import references_of

#: The declaration of the fixture repository, the section ``references`` of ``anagraphe.yml``.
SECTION: dict[str, Any] = {
    "exclude": {"paths": ["templates/"]},
    "schemes": ["https", "mailto"],
    "syntaxes": {"glossary": {"when": {"paths": ["/specs/*.yml"]}, "keys": ["source"]}},
}

#: A repository that every case extends, holding each form of reference that resolves.
BASE = {
    "a/note.md": (
        '---\nindex: "[Target](b/target.md)"\n---\n# Note\n\n'
        "A body link is file-relative: [target](../b/target.md), "
        "[anchor](../b/target.md#^block), [same file](#^here). ^here\n"
        "A declared scheme leaves the vault: [site](https://example.org), "
        "[mail](mailto:a@example.org).\n\n"
        "```markdown\n[an example inside a fence](nowhere.md)\n```\n"
    ),
    "b/target.md": "# Target\n\nA block cited by an anchor. ^block\n",
    "specs/terms.yml": (
        "# a source value citing a block of a note, relative to the vault root\n"
        "terms:\n  claim: {label: claim, source: b/target.md#^block}\n"
    ),
    "templates/skeleton.md": "# Skeleton\n\n[placeholder](RELATED-NOTE.md)\n",
}

#: The planted cases: the files added to the base, and the count of each kind of issue expected.
PLANTED: dict[str, tuple[dict[str, str], dict[str, int]]] = {
    "broken": (
        {
            "a/broken.md": "# Broken\n\n[missing](../b/missing.md) beside [present](../b/target.md).\n",
            "specs/missing.yml": (
                "terms:\n  missing: {label: missing, source: b/missing.md#^block}\n"
                "  present: {label: present, source: b/target.md#^block}\n"
            ),
        },
        {"broken": 2},
    ),
    "broken-anchor": (
        {
            "a/anchors.md": (
                "# Anchors\n\n"
                "[closing anchor](../b/blocks.md#^claim) beside "
                "[absent anchor](../b/blocks.md#^absent).\n"
                "[token in the middle of a line](../b/blocks.md#^inline) beside "
                "[encoded](../b/blocks.md#%5Eclaim).\n"
                "[same file, present](#^local) beside [same file, absent](#^nowhere). ^local\n"
            ),
            "b/blocks.md": (
                "# Blocks\n\nA claim closing on its anchor. ^claim\n"
                "A line holding ^inline in its middle, which is no anchor.\n"
            ),
            "specs/sources.yml": (
                "# source: b/blocks.md#^commented\nterms:\n"
                "  present: {label: present, source: b/blocks.md#^claim}\n"
                '  absent:\n    label: absent\n    source: "b/blocks.md#^missing"\n'
            ),
        },
        {"broken-anchor": 4},
    ),
    "convention": (
        {
            "a/swapped.md": (
                '---\nindex: "[Target](../b/target.md)"\n---\n# Swapped\n\n'
                "[root-relative in the body](b/target.md) beside "
                "[file-relative](./../b/target.md).\n"
            ),
        },
        {"convention": 2},
    ),
    "foreign-scheme": (
        {
            "a/editor.md": (
                "# Editor\n\n[pasted address](vscode-webview://abc/note.md) beside "
                "[declared](https://example.org/note).\n"
            ),
        },
        {"foreign-scheme": 1},
    ),
    "heading-fragment": (
        {
            "a/slugs.md": (
                "# Slugs\n\n"
                "[heading slug](../b/target.md#target) beside [block anchor](../b/target.md#^block).\n"
                "[same file, heading](#slugs) beside [same file, block](#^local). ^local\n"
                "[encoded heading](../b/target.md#A%20Section) beside "
                "[encoded caret](../b/target.md#%5Eblock).\n"
                "[empty fragment](../b/target.md#) beside "
                "[external fragment](https://example.org/page#section).\n"
            ),
            "specs/slugs.yml": (
                "# source: b/target.md#commented-heading\nterms:\n"
                "  slug: {label: slug, source: 'b/target.md#target'}\n"
                "  block: {label: block, source: b/target.md#^block}\n"
            ),
        },
        {"heading-fragment": 4},
    ),
}


def _write(root: Path, files: dict[str, str]) -> None:
    """Write fixture files below a repository root."""
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _repository(root: Path, files: dict[str, str] | None = None, **section: Any) -> None:
    """Write the base repository, extra files, and a configuration with the section references."""
    _write(root, {**BASE, **(files or {})})
    declared = {"schema_version": 2, "references": {**SECTION, **section}}
    _write(root, {"anagraphe.yml": yaml.safe_dump(declared)})


def _config(root: Path) -> ReferenceConfig:
    """Load the section references of the fixture repository."""
    config = load_config(root, root / "anagraphe.yml").references
    assert config is not None
    return config


def _check(root: Path) -> Report:
    """Check the references of the whole fixture repository."""
    return ReferenceChecker(root, _config(root)).check()


def test_base_repository_is_clean(tmp_path: Path) -> None:
    """Every form of reference of the base resolves, and the excluded template is not read."""
    _repository(tmp_path)
    report = _check(tmp_path)
    assert report.issues == ()
    assert report.processed == 3


@pytest.mark.parametrize("case", sorted(PLANTED))
def test_planted_case_reports_its_kind(tmp_path: Path, case: str) -> None:
    """Each planted case reports exactly the issues of its kind, and nothing else."""
    files, expected = PLANTED[case]
    _repository(tmp_path, files)
    assert Counter(issue.kind for issue in _check(tmp_path).issues) == Counter(expected)


def test_issue_names_the_target_at_its_line(tmp_path: Path) -> None:
    """An issue is located at the line of its reference, and its detail opens on the target."""
    _repository(tmp_path, PLANTED["broken"][0])
    issues = {issue.rel: issue for issue in _check(tmp_path).issues}
    assert issues["a/broken.md"].line == 3
    assert issues["a/broken.md"].detail.startswith("../b/missing.md: names no file")
    assert issues["specs/missing.yml"].line == 2


def test_extracted_reference_records_its_column(tmp_path: Path) -> None:
    """A reference records the column of its target, which a later rewrite replaces."""
    _repository(tmp_path)
    checker = ReferenceChecker(tmp_path, _config(tmp_path))
    text = (tmp_path / "a/note.md").read_text(encoding="utf-8")
    found = references_of("a/note.md", text, checker.config.syntaxes.covering("a/note.md"), [])
    first = next(found).reference
    line = text.splitlines()[first.line - 1]
    assert line[first.column - 1 :].startswith(first.raw)


def test_record_fields_in_link_form_and_lists(tmp_path: Path) -> None:
    """A field in link form, or holding a list, yields one reference per string value."""
    _repository(
        tmp_path,
        {
            "people/ada.yml": (
                "notes: ['[Target](b/target.md)', '[Gone](b/gone.md)', 3]\n"
                "doi: 10.1016/j.neuron.2014.07.035\n"
            )
        },
        syntaxes={
            **SECTION["syntaxes"],
            "people": {"when": {"paths": ["/people/"]}, "keys": ["notes"], "form": "link"},
        },
    )
    issues = _check(tmp_path).issues
    assert [(issue.rel, issue.kind) for issue in issues] == [("people/ada.yml", "broken")]
    assert issues[0].detail.startswith("b/gone.md:")


def test_record_resolved_from_its_file(tmp_path: Path) -> None:
    """A convention of relative paths in some records resolves them from the folder of the record."""
    _repository(
        tmp_path,
        {"b/links.yml": "source: [target.md, ../b/target.md, b/target.md]\n"},
        syntaxes={"links": {"when": {"paths": ["/b/*.yml"]}, "keys": ["source"]}},
        conventions=[{"when": {"regions": ["metadata"], "paths": ["/b/"]}, "path": "relative"}],
    )
    issues = _check(tmp_path).issues
    assert [(issue.kind, issue.detail.split(":")[0]) for issue in issues] == [
        ("convention", "b/target.md")
    ]


def test_unparsable_record_is_reported(tmp_path: Path) -> None:
    """A declared record that YAML cannot parse is reported, not skipped."""
    _repository(tmp_path, {"specs/broken.yml": "terms: [\n"})
    assert [issue.kind for issue in _check(tmp_path).issues] == ["unreadable-file"]


def test_layer_bases_follow_the_declaration(tmp_path: Path) -> None:
    """A convention admitting both styles admits both forms, so no convention is reported."""
    _repository(
        tmp_path,
        PLANTED["convention"][0],
        conventions=[{"path": ["relative", "root"]}],
    )
    assert _check(tmp_path).issues == ()


def test_fragments_any_admits_heading_slugs(tmp_path: Path) -> None:
    """Under fragments any, a heading slug is admitted, and a block anchor is still checked."""
    files, _ = PLANTED["heading-fragment"]
    _repository(tmp_path, files, fragments="any")
    assert _check(tmp_path).issues == ()


def test_ignored_kind_is_not_reported(tmp_path: Path) -> None:
    """A kind listed under ignore is not reported, and the other kinds still are."""
    _repository(
        tmp_path, {**PLANTED["foreign-scheme"][0], **PLANTED["broken"][0]}, ignore=["broken"]
    )
    assert [issue.kind for issue in _check(tmp_path).issues] == ["foreign-scheme"]


@pytest.mark.parametrize(
    ("section", "message"),
    [
        ({"ignore": ["stale"]}, "references.ignore names unknown kinds: stale"),
        (
            {"markdown": {"paths": ["*.md"]}},
            "references.markdown is retired: declare the files of a syntax under syntaxes.markdown",
        ),
        ({"records": []}, "references.records is retired: declare a syntax of keys"),
        (
            {"conventions": [{"path": "folder"}]},
            r"conventions\[1\].path must name styles among: relative, root, absolute, shortest",
        ),
        (
            {"conventions": [{"when": {"regions": ["head"]}, "path": "root"}]},
            "unknown regions: head",
        ),
        (
            {"conventions": [{"when": {"types": ["md"]}}]},
            "must set a format, a path style, or a strictness",
        ),
        (
            {"conventions": [{"format": "html"}]},
            "must name syntaxes among: markdown, wikilink, code, latex",
        ),
        ({"conventions": [{"strict": ["prose"]}]}, r"conventions\[1\].strict must name syntaxes"),
        (
            {"exclude": {"directories": ["vendor"]}},
            "references.exclude.directories is retired: list patterns in .gitignore syntax",
        ),
        ({"exclude": {"basenames": ["README.md"]}}, "a file name at any depth as `README.md`"),
        ({"exclude": {"paths": ["\\"]}}, "references.exclude.paths holds an invalid pattern"),
        ({"exclude": {"where": {"status": "archived"}}}, "where must be a list of filters"),
        ({"exclude": {"where": [{}]}}, r"where\[1\] must name at least one key"),
        ({"exclude": {"gitignore": "yes"}}, "exclude.gitignore must be a boolean"),
        ({"syntaxes": {"g": {"when": {}}}}, "must declare exactly one of pattern and keys"),
        (
            {"syntaxes": {"g": {"keys": ["a"], "path": "x"}}},
            "syntaxes.g declares unknown keys: path",
        ),
        (
            {"syntaxes": {"latex": {"pattern": "x"}}},
            "syntaxes.latex declares unknown keys: pattern",
        ),
        ({"syntaxes": {"p": {"pattern": "(x)"}}}, "must capture a group named target"),
        ({"syntaxes": {"code": {"unresolved": "warn"}}}, "unresolved must be report or ignore"),
        ({"links": []}, "references declares unknown keys: links"),
    ],
)
def test_malformed_section_is_rejected(
    tmp_path: Path, section: dict[str, Any], message: str
) -> None:
    """A malformed declaration fails with a message naming its field."""
    _repository(tmp_path, **section)
    with pytest.raises(ConfigurationError, match=message):
        load_config(tmp_path, tmp_path / "anagraphe.yml")


def test_configuration_requires_a_section(tmp_path: Path) -> None:
    """A configuration declaring no section enables nothing, and is rejected."""
    _write(tmp_path, {"anagraphe.yml": "schema_version: 2\nexclude: {paths: [vendor/]}\n"})
    with pytest.raises(ConfigurationError, match="declares no section: indexes, references"):
        load_config(tmp_path, tmp_path / "anagraphe.yml")


def test_cli_refs_check_exit_status(tmp_path: Path) -> None:
    """The command exits with 1 on a violation, names its kinds, and exits with 0 once repaired."""
    _repository(tmp_path, PLANTED["broken"][0])
    runner = CliRunner()
    broken = runner.invoke(app, ["refs", "check", "--root", str(tmp_path)])
    assert broken.exit_code == 1
    assert "a/broken.md:3: broken: ../b/missing.md" in broken.stdout
    assert "references: checked 5 files: 2 violations, 0 warnings (2 broken)" in broken.stdout
    (tmp_path / "a/broken.md").unlink()
    (tmp_path / "specs/missing.yml").unlink()
    clean = runner.invoke(app, ["refs", "check", "--root", str(tmp_path)])
    assert clean.exit_code == 0


def test_cli_check_runs_the_declared_sections(tmp_path: Path) -> None:
    """The top-level check runs the references when only that section is declared."""
    _repository(tmp_path, PLANTED["foreign-scheme"][0])
    result = CliRunner().invoke(app, ["check", "--root", str(tmp_path)])
    assert result.exit_code == 1
    assert "references: checked" in result.stdout
    assert "indexes:" not in result.stdout


def test_cli_section_command_requires_its_section(tmp_path: Path) -> None:
    """A command of a subpackage whose section is absent exits with 2 and names the section."""
    _repository(tmp_path)
    result = CliRunner().invoke(app, ["indexes", "check", "--root", str(tmp_path)])
    assert result.exit_code == 2
    assert "declares no section indexes" in result.stderr


def test_cli_rejects_missing_target(tmp_path: Path) -> None:
    """A misspelled target fails with 2 instead of producing a clean check."""
    _repository(tmp_path)
    result = CliRunner().invoke(app, ["refs", "check", "--root", str(tmp_path), "misspelled"])
    assert result.exit_code == 2
    assert "target does not exist" in result.stderr


def _kinds(root: Path) -> list[tuple[str, str]]:
    """Return the file and the kind of each issue of the fixture repository."""
    return [(issue.rel, issue.kind) for issue in _check(root).issues]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("~~~\n[x](missing.md)\n~~~\n", []),
        ("````\n```\n[x](missing.md)\n````\n", []),
        ("```markdown\n~~~\n```\n\n[x](missing.md)\n", [("a/fences.md", "broken")]),
        ("Inline `[x](missing.md)` beside ``[y](gone.md)``.\n", []),
    ],
)
def test_code_blocks_and_spans_are_examples(
    tmp_path: Path, text: str, expected: list[tuple[str, str]]
) -> None:
    """A block closes only on its own marker, at least as long, and a code span is not read."""
    _repository(tmp_path, {"a/fences.md": text})
    assert _kinds(tmp_path) == expected


def test_record_values_are_read_as_written(tmp_path: Path) -> None:
    """A bare path in a record is not percent-decoded, so a file named with % resolves."""
    _repository(
        tmp_path,
        {"b/a%20b.md": "# Encoded\n", "specs/raw.yml": "source: b/a%20b.md\n"},
    )
    assert _kinds(tmp_path) == []


def test_record_locations_and_titles(tmp_path: Path) -> None:
    """A folded value is located at its text, an escaped one is inexact, a titled link is read."""
    _repository(
        tmp_path,
        {
            "specs/forms.yml": (
                'folded: >-\n  b/gone.md\nescaped: "b/\\u0067one.md"\n'
                "titled: '[Gone](b/gone.md \"A title\")'\n"
            )
        },
        syntaxes={
            "plain": {"when": {"paths": ["/specs/forms.yml"]}, "keys": ["folded", "escaped"]},
            "linked": {"when": {"paths": ["/specs/forms.yml"]}, "keys": ["titled"], "form": "link"},
        },
    )
    checker = ReferenceChecker(tmp_path, _config(tmp_path))
    text = (tmp_path / "specs/forms.yml").read_text(encoding="utf-8")
    declared = [
        syntax
        for syntax in checker.config.syntaxes.covering("specs/forms.yml")
        if syntax.name in ("plain", "linked")
    ]
    located = [
        (found.reference.line, found.reference.column, found.reference.exact)
        for found in references_of("specs/forms.yml", text, declared, [])
    ]
    assert sorted(located) == [(2, 3, True), (3, 10, False), (4, 17, True)]
    assert [issue.kind for issue in checker.check().issues] == ["broken"] * 3


def test_record_base_root_reports_a_file_relative_value(tmp_path: Path) -> None:
    """A record of base root holding a path written from its own folder breaks the convention."""
    _repository(tmp_path, {"specs/near.yml": "source: ../b/target.md\n"})
    assert _kinds(tmp_path) == [("specs/near.yml", "convention")]


def test_link_outside_the_repository_is_reported(tmp_path: Path) -> None:
    """A path naming a file outside the root resolves on one machine only, and is reported."""
    root = tmp_path / "repository"
    _write(tmp_path, {"outside.md": "# Outside\n"})
    _repository(root, {"a/out.md": "[out](../../outside.md) beside [gone](../../gone.md)\n"})
    assert sorted(_kinds(root)) == [("a/out.md", "broken"), ("a/out.md", "outside-repository")]


def test_schemes_accept_a_mapping_in_any_case(tmp_path: Path) -> None:
    """Schemes written as a mapping to glosses are compared in lowercase."""
    _repository(
        tmp_path,
        {"a/web.md": "[a](HTTPS://example.org) [b](Zotero://select/items/1)\n"},
        schemes={"https": "a web address", "mailto": "a mail", "ZOTERO": "a library item"},
    )
    assert _kinds(tmp_path) == []


def test_exclusions_combine_and_prune(tmp_path: Path) -> None:
    """The shared exclusions and those of the section both apply, and hidden folders are pruned."""
    _repository(
        tmp_path,
        {
            "vendor/x.md": "[x](gone.md)\n",
            "drafts/old/x.md": "[x](gone.md)\n",
            "keep/drafts/old/x.md": "[x](gone.md)\n",
            ".cache/x.md": "[x](gone.md)\n",
        },
        exclude={"paths": ["templates/", "/drafts/old/"]},
    )
    config = yaml.safe_load((tmp_path / "anagraphe.yml").read_text(encoding="utf-8"))
    config["exclude"] = {"paths": ["vendor/"]}
    _write(tmp_path, {"anagraphe.yml": yaml.safe_dump(config)})
    assert _kinds(tmp_path) == [("keep/drafts/old/x.md", "broken")]


def test_cli_named_targets(tmp_path: Path) -> None:
    """A named file is checked alone, and an excluded or unread target exits with 2."""
    _repository(tmp_path, PLANTED["broken"][0])
    runner = CliRunner()
    alone = runner.invoke(app, ["refs", "check", "--root", str(tmp_path), "a/broken.md"])
    assert alone.exit_code == 1
    assert "checked 1 files" in alone.stdout
    for target in ("templates/skeleton.md", "anagraphe.yml"):
        refused = runner.invoke(app, ["refs", "check", "--root", str(tmp_path), target])
        assert refused.exit_code == 2
        assert "target: target holds no file that the command reads" in refused.stderr
    outside = runner.invoke(app, ["refs", "check", "--root", str(tmp_path), "/"])
    assert outside.exit_code == 2
    assert "target lies outside the repository" in outside.stderr


def test_cli_check_runs_both_sections_on_a_folder_without_index(tmp_path: Path) -> None:
    """The top-level check reads a target holding no index through the references alone."""
    _repository(tmp_path, PLANTED["broken"][0])
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
        },
    )
    config = yaml.safe_load((tmp_path / "anagraphe.yml").read_text(encoding="utf-8"))
    config["indexes"] = {
        "vocabulary": "config/vocabulary.yml",
        "index_types": "config/index-types",
        "inspect_git": False,
    }
    _write(tmp_path, {"anagraphe.yml": yaml.safe_dump(config)})
    result = CliRunner().invoke(app, ["check", "--root", str(tmp_path), "a"])
    assert result.exit_code == 1
    assert "indexes: processed 0 indexes holding blocks" in result.stdout
    assert "a/broken.md:3: broken: ../b/missing.md" in result.stdout
