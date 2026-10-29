"""Behavioral tests for collection-owned membership, order and nesting (ADR 0002)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from anagraphe.application import RunResult, run
from anagraphe.cli import app
from anagraphe.configuration import ConfigurationError, load_config
from anagraphe.generator import nest_members
from anagraphe.issues import Issue
from anagraphe.notes import Note
from anagraphe.retired import RETIRED_KEYS

#: A rendered entry, capturing the path of its link.
ENTRY = re.compile(r"^\s*- \[[^\]]*\]\(([^)]+)\)", re.MULTILINE)


def _write(path: Path, text: str) -> None:
    """Write one fixture file after creating its parent directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _markdown(data: dict[str, Any], body: str) -> str:
    """Return a Markdown file with a frontmatter and a body."""
    return f"---\n{yaml.safe_dump(data, sort_keys=False)}---\n\n{body}"


def _repository(
    root: Path,
    vocabulary: dict[str, Any] | None = None,
    configuration: str = "",
    default_mode: str = "registry",
) -> None:
    """Create a repository whose default index type has the given default mode."""
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "module.schema.yaml",
        "type": "object",
        "x-default-mode": default_mode,
    }
    _write(
        root / "config" / "vocabulary.yml",
        yaml.safe_dump({"schema": {"entry_point": "_index.md"}, **(vocabulary or {})}),
    )
    _write(root / "config" / "index-types" / "module.schema.yaml", yaml.safe_dump(schema))
    _write(
        root / "anagraphe.yml",
        "schema_version: 1\nvocabulary: config/vocabulary.yml\n"
        f"index_types: config/index-types\ninspect_git: false\n{configuration}",
    )


def _index(root: Path, groups: list[dict[str, Any]], **keys: Any) -> None:
    """Write the index of the folder ``m`` with its groups and its region."""
    data = {"role": "index", "aliases": ["Module"], "groups": groups, **keys}
    _write(
        root / "m" / "_index.md",
        _markdown(data, "# Module\n\n<!-- index groups -->\n<!-- /index -->\n"),
    )


def _note(root: Path, name: str, **keys: Any) -> None:
    """Write one member of the folder ``m``, titled by its name."""
    title = name.removesuffix(".md").capitalize()
    data = {"role": "note", "index": "[Module](m/_index.md)", "aliases": [title], **keys}
    data.setdefault("purpose", f"records {title.lower()}")
    _write(root / "m" / name, _markdown(data, f"# {title}\n"))


def _link(name: str) -> str:
    """Return a frontmatter link to one member of the folder ``m``."""
    return f"[{name}](m/{name})"


def _run(root: Path, mode: str = "check") -> RunResult:
    """Run one command over the fixture repository."""
    return run(root, load_config(root, root / "anagraphe.yml"), mode)  # type: ignore[arg-type]


def _entries(root: Path) -> list[str]:
    """Write the indexes and return the paths of the rendered entries, in order."""
    result = _run(root, "write")
    assert result.blocking_count == 0, [issue for issue in result.issues if issue.blocking]
    return ENTRY.findall((root / "m" / "_index.md").read_text(encoding="utf-8"))


def _found(result: RunResult, kind: str) -> list[Issue]:
    """Return the issues of one kind."""
    return [issue for issue in result.issues if issue.kind == kind]


# --- Membership ----------------------------------------------------------------------------------


def test_filter_assigns_each_member_to_the_first_matching_group(tmp_path: Path) -> None:
    """A member matching two filters must belong to the first, the others to the catch-all."""
    _repository(tmp_path)
    _index(
        tmp_path,
        [
            {"id": "talks", "where": {"kind": "talk"}},
            {"id": "events", "where": {"kind": ["talk", "keynote"]}},
            {"id": "*"},
        ],
    )
    _note(tmp_path, "a.md", kind="keynote")
    _note(tmp_path, "b.md", kind="talk")
    _note(tmp_path, "c.md")
    assert _entries(tmp_path) == ["b.md", "a.md", "c.md"]


def test_explicit_members_prevail_over_the_filter_of_an_earlier_group(tmp_path: Path) -> None:
    """A member named by an explicit list must leave the group whose filter it matches."""
    _repository(tmp_path)
    _index(
        tmp_path,
        [{"id": "talks", "where": {"kind": "talk"}}, {"id": "kept", "members": [_link("a.md")]}],
    )
    _note(tmp_path, "a.md", kind="talk")
    _note(tmp_path, "b.md", kind="talk")
    assert _entries(tmp_path) == ["b.md", "a.md"]


def test_sequence_without_filter_defines_membership_and_order(tmp_path: Path) -> None:
    """The links of a sequence must give both the members of the group and their order."""
    _repository(tmp_path)
    _index(
        tmp_path,
        [
            {"id": "parts", "mode": "sequence", "sequence": [_link("c.md"), _link("a.md")]},
            {"id": "*", "heading": "Others"},
        ],
    )
    for name in ("a.md", "b.md", "c.md"):
        _note(tmp_path, name)
    assert _entries(tmp_path) == ["c.md", "a.md", "b.md"]


def test_filter_on_a_list_valued_key_matches_any_element(tmp_path: Path) -> None:
    """A member whose key holds a list must match a filter admitting one of its elements."""
    _repository(tmp_path)
    _index(tmp_path, [{"id": "tagged", "where": {"tags": "x"}}, {"id": "*", "heading": "Others"}])
    _note(tmp_path, "a.md", tags=["z"])
    _note(tmp_path, "b.md", tags=["y", "x"])
    assert _entries(tmp_path) == ["b.md", "a.md"]


@pytest.mark.parametrize(("catch_all", "placed"), [(True, True), (False, False)])
def test_member_matching_no_group_joins_only_a_declared_catch_all(
    tmp_path: Path, catch_all: bool, placed: bool
) -> None:
    """A member matching no filter must join the group * if declared, and be reported otherwise."""
    _repository(tmp_path)
    groups: list[dict[str, Any]] = [{"id": "talks", "where": {"kind": "talk"}}]
    _index(tmp_path, groups + ([{"id": "*", "heading": "Others"}] if catch_all else []))
    _note(tmp_path, "a.md", kind="talk")
    _note(tmp_path, "b.md", kind="poster")
    result = _run(tmp_path, "write")
    rendered = ENTRY.findall((tmp_path / "m" / "_index.md").read_text(encoding="utf-8"))
    unplaced = _found(result, "unplaced-member")
    if placed:
        assert rendered == ["a.md", "b.md"]
        assert not unplaced
    else:
        assert [(issue.rel, issue.blocking) for issue in unplaced] == [("m/b.md", True)]


def test_member_named_twice_by_one_group_is_a_violation(tmp_path: Path) -> None:
    """A file listed twice by the same group must be reported once, naming the group."""
    _repository(tmp_path)
    _index(tmp_path, [{"id": "one", "members": [_link("a.md"), _link("a.md")]}])
    _note(tmp_path, "a.md")
    assert [issue.detail for issue in _found(_run(tmp_path), "duplicate-member")] == [
        "members of group one names m/a.md twice"
    ]


def test_members_naming_a_file_outside_the_folder_is_a_violation(tmp_path: Path) -> None:
    """An explicit list naming an existing file that the index does not list must be reported."""
    _repository(tmp_path)
    _write(tmp_path / "x" / "b.md", "# B\n")
    _index(tmp_path, [{"id": "*", "members": ["[B](x/b.md)"]}])
    _note(tmp_path, "a.md")
    found = _found(_run(tmp_path), "invalid-link")
    assert [(issue.detail, issue.blocking) for issue in found] == [
        ("members of group * names x/b.md, which m/_index.md does not list", True)
    ]


# --- Order ---------------------------------------------------------------------------------------


def test_categorical_key_sorts_by_declared_values_then_secondary_key(tmp_path: Path) -> None:
    """A categorical key must sort in its declared order, and a second key break its ties."""
    _repository(tmp_path, {"key_values": {"kind": {"keynote": "a lecture", "talk": "a talk"}}})
    _index(tmp_path, [{"id": "*", "sort": ["kind", "day"]}])
    _note(tmp_path, "a.md", kind="talk", day="2")
    _note(tmp_path, "b.md", kind="talk", day="1")
    _note(tmp_path, "c.md", kind="keynote", day="3")
    assert _entries(tmp_path) == ["c.md", "b.md", "a.md"]


def test_order_overrides_the_declared_values(tmp_path: Path) -> None:
    """The order of a group must prevail over the declared order of its first sort key."""
    _repository(tmp_path, {"key_values": {"kind": ["keynote", "talk"]}})
    _index(tmp_path, [{"id": "*", "sort": "kind", "order": ["talk", "keynote"]}])
    _note(tmp_path, "a.md", kind="keynote")
    _note(tmp_path, "b.md", kind="talk")
    assert _entries(tmp_path) == ["b.md", "a.md"]


def test_value_missing_from_order_warns_and_sorts_after_ranked_values(tmp_path: Path) -> None:
    """A value that the order of a group omits must warn, and sort after the ranked values."""
    _repository(tmp_path)
    _index(tmp_path, [{"id": "*", "sort": "kind", "order": ["talk", "keynote"]}])
    _note(tmp_path, "a.md", kind="demo")
    _note(tmp_path, "b.md", kind="keynote")
    _note(tmp_path, "c.md", kind="talk")
    assert _entries(tmp_path) == ["c.md", "b.md", "a.md"]
    warnings = _found(_run(tmp_path), "unranked-value")
    assert [(issue.rel, issue.blocking) for issue in warnings] == [("m/a.md", False)]


def test_numeric_key_sorts_by_number_and_before_text(tmp_path: Path) -> None:
    """Numbers must compare as numbers, and precede the text values of the same key."""
    _repository(tmp_path)
    _index(tmp_path, [{"id": "*", "sort": "day"}])
    _note(tmp_path, "a.md", day=10)
    _note(tmp_path, "b.md", day=2)
    _note(tmp_path, "c.md", day=1)
    _note(tmp_path, "d.md", day="late")
    _note(tmp_path, "e.md", day=1.5)
    assert _entries(tmp_path) == ["c.md", "e.md", "b.md", "a.md", "d.md"]


def test_member_without_the_sort_key_follows_the_others(tmp_path: Path) -> None:
    """A member lacking the sort key must sort after the members holding it."""
    _repository(tmp_path)
    _index(tmp_path, [{"id": "*", "sort": "day"}])
    _note(tmp_path, "a.md")
    _note(tmp_path, "b.md", day=3)
    assert _entries(tmp_path) == ["b.md", "a.md"]


def test_sort_key_held_by_no_member_is_a_violation(tmp_path: Path) -> None:
    """A sort key that no member of the group holds must be reported as a typo."""
    _repository(tmp_path)
    _index(tmp_path, [{"id": "*", "sort": "dya"}])
    _note(tmp_path, "a.md", day=1)
    assert [issue.detail for issue in _found(_run(tmp_path), "malformed-groups")] == [
        "group *: no member holds the sort key dya"
    ]


def test_members_absent_from_a_sequence_follow_it_by_sort_key(tmp_path: Path) -> None:
    """Unsequenced members must follow the sequence in sort order, each with a warning."""
    _repository(tmp_path, default_mode="sequence")
    _index(tmp_path, [{"id": "*", "sequence": [_link("c.md")], "sort": "file"}])
    for name in ("b.md", "a.md", "c.md"):
        _note(tmp_path, name)
    assert _entries(tmp_path) == ["c.md", "a.md", "b.md"]
    warnings = _found(_run(tmp_path), "unsequenced-member")
    assert {issue.rel for issue in warnings} == {"m/a.md", "m/b.md"}
    assert not any(issue.blocking for issue in warnings)


def test_build_manifest_orders_a_sequence_group(tmp_path: Path) -> None:
    """A sequence group without its own sequence must follow the build manifest of its folder."""
    _repository(tmp_path, configuration="sequences:\n  m: [b.md, a.md]\n")
    _index(tmp_path, [{"id": "*", "mode": "sequence"}])
    _note(tmp_path, "a.md")
    _note(tmp_path, "b.md")
    assert _entries(tmp_path) == ["b.md", "a.md"]


# --- Checks of the decision ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("index_keys", "note_keys", "detail"),
    [
        (
            {"groups": [{"id": "*", "members": [_link("gone.md")]}]},
            {},
            "members of group * names no file: m/gone.md",
        ),
        (
            {"groups": [{"id": "*", "mode": "sequence", "sequence": [_link("gone.md")]}]},
            {},
            "sequence of group * names no file: m/gone.md",
        ),
        (
            {"groups": [{"id": "*"}], "external": [{"target": "[Gone](gone.md)", "for": "x"}]},
            {},
            "external names no file: gone.md",
        ),
        (
            {"groups": [{"id": "*"}]},
            {"superseded_by": "[Gone](m/gone.md)"},
            "superseded_by names no file: m/gone.md",
        ),
        (
            {"groups": [{"id": "*"}]},
            {"superseded_by": "m/a.md"},
            "superseded_by is not a link [Title](path.md): m/a.md",
        ),
    ],
)
def test_link_resolving_to_no_file_is_a_violation(
    tmp_path: Path, index_keys: dict[str, Any], note_keys: dict[str, Any], detail: str
) -> None:
    """A link of members, sequence, external or superseded_by must name an existing file."""
    _repository(tmp_path)
    _index(tmp_path, **index_keys)
    _note(tmp_path, "a.md", **note_keys)
    found = _found(_run(tmp_path), "invalid-link")
    assert [issue.detail for issue in found] == [detail]
    assert all(issue.blocking for issue in found)


def test_member_named_by_two_groups_is_a_violation(tmp_path: Path) -> None:
    """A file listed by two groups must be reported, and belong to the first."""
    _repository(tmp_path)
    _index(
        tmp_path,
        [{"id": "one", "members": [_link("a.md")]}, {"id": "two", "members": [_link("a.md")]}],
    )
    _note(tmp_path, "a.md")
    result = _run(tmp_path)
    assert [issue.detail for issue in _found(result, "duplicate-member")] == [
        "m/a.md is named by the groups one and two; it belongs to one"
    ]


def test_filter_naming_an_undeclared_key_is_a_violation(tmp_path: Path) -> None:
    """A filter on a key that no member declares must be reported as a typo."""
    _repository(tmp_path)
    _index(tmp_path, [{"id": "talks", "where": {"knid": "talk"}}, {"id": "*"}])
    _note(tmp_path, "a.md", kind="talk")
    found = _found(_run(tmp_path), "unknown-filter-key")
    assert [issue.detail for issue in found] == [
        "where of group talks names knid, which no member declares"
    ]


def test_categorical_value_outside_its_declared_values_is_a_violation(tmp_path: Path) -> None:
    """A value of a filter, of an order, or of a member must belong to the declared values.

    A declared value that the order of the group omits is only a warning.
    """
    _repository(tmp_path, {"key_values": {"kind": ["keynote", "talk"]}})
    _index(
        tmp_path,
        [
            {"id": "talks", "where": {"kind": "tlak"}},
            {"id": "*", "sort": "kind", "order": ["talk", "demo"]},
        ],
    )
    _note(tmp_path, "a.md", kind="keynote")
    _note(tmp_path, "b.md", kind="poster")
    result = _run(tmp_path)
    found = _found(result, "undeclared-value")
    assert sorted((issue.rel, issue.detail) for issue in found) == [
        (
            "m/_index.md",
            "order of group *: kind admits no value demo; its values are keynote, talk",
        ),
        (
            "m/_index.md",
            "where of group talks: kind admits no value tlak; its values are keynote, talk",
        ),
        (
            "m/b.md",
            "kind holds poster, which group * in m/_index.md sorts by, outside its declared "
            "values: keynote, talk",
        ),
    ]
    assert all(issue.blocking for issue in found)
    assert [(issue.rel, issue.blocking) for issue in _found(result, "unranked-value")] == [
        ("m/a.md", False)
    ]


@pytest.mark.parametrize(
    ("groups", "configuration", "detail"),
    [
        (
            [{"id": "*", "sequence": [_link("a.md")]}],
            "",
            "group * is a registry, so the order of its sequence is ignored: set mode sequence, "
            "or list the files under members",
        ),
        (
            [{"id": "*", "where": {"kind": "talk"}, "sequence": [_link("a.md")]}],
            "",
            "group * is a registry, so the order of its sequence is ignored: set mode sequence, "
            "or remove the sequence",
        ),
        (
            [{"id": "*", "order": ["talk"]}],
            "",
            "group * sorts first by title, so its order is ignored: sort first by the "
            "categorical key that order ranks",
        ),
        (
            [
                {"id": "first", "members": [_link("a.md")]},
                {
                    "id": "*",
                    "mode": "sequence",
                    "where": {"role": "note"},
                    "sequence": [_link("a.md")],
                },
            ],
            "",
            "sequence of group * names m/a.md, which the group does not hold",
        ),
        (
            [{"id": "*"}],
            "sequences:\n  m: [a.md]\n",
            "the build manifest of m orders m/a.md, which the registry group * sorts by title",
        ),
        (
            [{"id": "*", "mode": "sequence", "sequence": [_link("a.md")]}],
            "sequences:\n  m: [a.md]\n",
            "the build manifest of m prevails over the sequence of group *: move the links "
            "under members",
        ),
        (
            [
                {
                    "id": "*",
                    "mode": "sequence",
                    "where": {"kind": "talk"},
                    "sequence": [_link("a.md")],
                }
            ],
            "sequences:\n  m: [a.md]\n",
            "the build manifest of m prevails over the sequence of group *: remove the sequence",
        ),
    ],
)
def test_source_of_order_ignored_by_the_mode_is_a_violation(
    tmp_path: Path, groups: list[dict[str, Any]], configuration: str, detail: str
) -> None:
    """A sequence, an order or a manifest that the group cannot apply must be reported."""
    _repository(tmp_path, configuration=configuration)
    _index(tmp_path, groups)
    _note(tmp_path, "a.md", kind="talk")
    found = _found(_run(tmp_path), "ignored-order")
    assert [issue.detail for issue in found] == [detail]
    assert all(issue.blocking for issue in found)


def test_cycle_among_nested_parents_is_a_violation(tmp_path: Path) -> None:
    """Two members naming each other as parent must be reported."""
    _repository(tmp_path)
    _index(tmp_path, [{"id": "*", "nest": "parent"}])
    _note(tmp_path, "a.md", parent="b")
    _note(tmp_path, "b.md", parent="a")
    found = _found(_run(tmp_path), "nest-cycle")
    assert {issue.detail for issue in found} == {
        "group *: m/a.md closes a cycle of parent",
        "group *: m/b.md closes a cycle of parent",
    }


def test_cycle_places_its_first_member_at_the_first_level() -> None:
    """The first member of a cycle must stand at the first level, and the others beneath it."""
    members = [
        Note(f"m/{name}", data={"parent": parent})
        for name, parent in (("a.md", "c"), ("b.md", "a"), ("c.md", "b"))
    ]
    nested, depths, cycle = nest_members(members, "parent")
    assert [(note.rel, depth) for note, depth in zip(nested, depths)] == [
        ("m/a.md", 0),
        ("m/b.md", 1),
        ("m/c.md", 2),
    ]
    assert [note.rel for note in cycle] == ["m/a.md", "m/b.md", "m/c.md"]


def test_groups_of_two_modes_under_one_heading_are_a_violation(tmp_path: Path) -> None:
    """A group without heading must share the mode of the group whose heading it stands under."""
    _repository(tmp_path)
    _index(
        tmp_path,
        [
            {"id": "core", "heading": "Core", "members": [_link("a.md")]},
            {"id": "parts", "mode": "sequence", "sequence": [_link("b.md")]},
        ],
    )
    _note(tmp_path, "a.md")
    _note(tmp_path, "b.md")
    found = _found(_run(tmp_path), "mixed-modes")
    assert [(issue.detail, issue.blocking) for issue in found] == [
        ("a sequence group stands under the heading of a registry group", True)
    ]


def test_sequence_group_without_a_source_of_order_is_a_violation(tmp_path: Path) -> None:
    """A sequence group needs a sequence of links or a build manifest."""
    _repository(tmp_path, default_mode="sequence")
    _index(tmp_path, [{"id": "*"}])
    _note(tmp_path, "a.md")
    assert len(_found(_run(tmp_path), "missing-sequence")) == 1


# --- Slots ---------------------------------------------------------------------------------------


def test_external_names_files_outside_the_collection(tmp_path: Path) -> None:
    """An outside dependency must pass, and a member listed as external be reported."""
    _repository(tmp_path)
    _write(tmp_path / "shared" / "kernels.md", "# Kernels\n")
    _index(
        tmp_path,
        [{"id": "*"}],
        external=[
            {"target": "[Kernels](shared/kernels.md)", "for": "the kernel of the model"},
            {"target": _link("a.md"), "for": "the first note"},
        ],
    )
    _note(tmp_path, "a.md")
    result = _run(tmp_path)
    assert [issue.detail for issue in _found(result, "invalid-external")] == [
        "external names m/a.md, which m/_index.md lists: external holds the files outside the "
        "collection"
    ]
    assert not _found(result, "invalid-link")


def test_context_relations_are_validated_against_the_vocabulary(tmp_path: Path) -> None:
    """A relation declared by the vocabulary must pass, and another one be reported."""
    _repository(tmp_path, {"context_relations": ["contrasts"]})
    _index(
        tmp_path,
        [{"id": "*"}],
        context_relations=[
            {"source": _link("a.md"), "relation": "contrasts", "target": _link("b.md")},
            {"source": _link("a.md"), "relation": "visualizes", "target": _link("b.md")},
        ],
    )
    _note(tmp_path, "a.md")
    _note(tmp_path, "b.md")
    assert [issue.detail for issue in _found(_run(tmp_path), "invalid-context-relation")] == [
        "relation not declared under context_relations in the vocabulary: visualizes"
    ]


def test_context_relation_links_are_url_decoded(tmp_path: Path) -> None:
    """A relation linking a member whose name holds a space must resolve to that member."""
    _repository(tmp_path, {"context_relations": ["contrasts"]})
    _index(
        tmp_path,
        [{"id": "*"}],
        context_relations=[
            {"source": "[A b](m/a%20b.md)", "relation": "contrasts", "target": _link("c.md")}
        ],
    )
    _note(tmp_path, "a b.md")
    _note(tmp_path, "c.md")
    assert not _found(_run(tmp_path), "invalid-context-relation")


def test_group_declaring_members_and_where_is_reported(tmp_path: Path) -> None:
    """A filter that an explicit list of the same group overrides must not pass silently."""
    _repository(tmp_path)
    _index(tmp_path, [{"id": "*", "members": [_link("a.md")], "where": {"kind": "talk"}}])
    _note(tmp_path, "a.md", kind="talk")
    assert [issue.detail for issue in _found(_run(tmp_path), "malformed-groups")] == [
        "group 1: members prevails over where, so where selects nothing"
    ]


# --- Retired constructions -----------------------------------------------------------------------


def test_retired_default_mode_fails_the_configuration(tmp_path: Path) -> None:
    """A type defaulting to construction must fail with the modes replacing it."""
    _repository(tmp_path, default_mode="construction")
    result = CliRunner().invoke(app, ["check", "--root", str(tmp_path)])
    assert result.exit_code == 2
    assert "the mode construction is retired: use registry" in result.stderr


def test_retired_vocabulary_section_fails_the_configuration(tmp_path: Path) -> None:
    """A vocabulary declaring typed citations must fail with the section replacing it."""
    _repository(tmp_path, {"cites": {"relations": {"contrasts": {}}}})
    result = CliRunner().invoke(app, ["check", "--root", str(tmp_path)])
    assert result.exit_code == 2
    assert "declares the retired section cites" in result.stderr


@pytest.mark.parametrize(
    ("group", "detail"),
    [
        (
            {"id": "*", "mode": "construction"},
            "group 1: the mode construction is retired: use registry, sorted by a key, or "
            "sequence, ordered by a list of links",
        ),
        (
            {"id": "*", "strategy": ["claim-first"]},
            "group 1: the key strategy is retired: a group orders its members by a sort key or "
            "by a sequence of links",
        ),
        (
            {"id": "*", "show": ["purpose", "cites"]},
            "group 1: show: the key cites is retired: the links of the body state the "
            "dependencies of a note",
        ),
    ],
)
def test_retired_group_construction_is_a_violation(
    tmp_path: Path, group: dict[str, Any], detail: str
) -> None:
    """A group declaring a retired mode or key must be reported with its replacement."""
    _repository(tmp_path)
    _index(tmp_path, [group])
    _note(tmp_path, "a.md")
    found = _found(_run(tmp_path), "malformed-groups")
    assert [issue.detail for issue in found] == [detail]
    assert all(issue.blocking for issue in found)


@pytest.mark.parametrize(
    ("index_keys", "note_keys", "rel", "replacement"),
    [
        ({}, {"group": "core"}, "m/a.md", "the where or the members of a group"),
        ({}, {"cites": []}, "m/a.md", "the links of the body"),
        ({"sequence": ["a.md"]}, {}, "m/_index.md", "each group of mode sequence"),
        ({"goal": _link("a.md")}, {}, "m/_index.md", "an index checks no order against a goal"),
        ({"cites": []}, {}, "m/_index.md", "external lists the files outside the folder"),
    ],
)
def test_retired_key_is_a_violation_naming_its_replacement(
    tmp_path: Path,
    index_keys: dict[str, Any],
    note_keys: dict[str, Any],
    rel: str,
    replacement: str,
) -> None:
    """A leftover member key or index key must fail with the construction replacing it."""
    _repository(tmp_path)
    _index(tmp_path, [{"id": "*"}], **index_keys)
    _note(tmp_path, "a.md", **note_keys)
    found = _found(_run(tmp_path), "retired-key")
    assert [issue.rel for issue in found] == [rel]
    assert replacement in found[0].detail
    assert found[0].blocking


@pytest.mark.parametrize(
    "body",
    ["# Module\n", "# Module\n\n<!-- index control -->\n<!-- /index -->\n"],
)
def test_retired_key_is_reported_under_an_index_without_region(tmp_path: Path, body: str) -> None:
    """Retired keys of an index and of its members must be reported before the region exists."""
    _repository(tmp_path)
    data = {"role": "index", "aliases": ["Module"], "sequence": [_link("a.md")]}
    _write(tmp_path / "m" / "_index.md", _markdown(data, body))
    _note(tmp_path, "a.md", group="core")
    found = _found(_run(tmp_path), "retired-key")
    assert sorted(issue.rel for issue in found) == ["m/_index.md", "m/a.md"]


def test_retired_messages_name_no_consumer() -> None:
    """The replacement of a retired key must be stated without the name of a consumer."""
    assert not [entry.key for entry in RETIRED_KEYS if "Gnomon" in entry.replacement]


def test_migration_class_reports_tolerated_citations_as_warnings(tmp_path: Path) -> None:
    """Typed citations inside a declared class must warn, and outside it still fail."""
    _repository(
        tmp_path,
        configuration=(
            "migrations:\n  - key: cites\n    paths: ['m/a.md']\n"
            "    awaits: the conversion into Gnomon records\n"
        ),
    )
    _index(tmp_path, [{"id": "*"}])
    _note(tmp_path, "a.md", cites=[{"relation": "extends", "target": _link("b.md")}])
    _note(tmp_path, "b.md", cites=[])
    result = _run(tmp_path)
    warnings = _found(result, "migration-key")
    assert [(issue.rel, issue.blocking) for issue in warnings] == [("m/a.md", False)]
    assert warnings[0].detail.endswith("tolerated until the conversion into Gnomon records")
    assert [issue.rel for issue in _found(result, "retired-key")] == ["m/b.md"]


def test_migration_class_admits_only_migratable_keys(tmp_path: Path) -> None:
    """A migration class for the member key group must be rejected."""
    _repository(
        tmp_path,
        configuration="migrations:\n  - {key: group, paths: ['*'], awaits: later}\n",
    )
    with pytest.raises(ConfigurationError, match="migratable retired key: cites"):
        load_config(tmp_path, tmp_path / "anagraphe.yml")


# --- Archived notes ------------------------------------------------------------------------------


def test_superseded_note_must_hold_an_archived_status(tmp_path: Path) -> None:
    """A note declaring superseded_by must hold a status that the vocabulary declares archived.

    The check covers every member, the members that no group holds included.
    """
    _repository(tmp_path, {"archived_statuses": ["archived"]})
    _index(tmp_path, [{"id": "talks", "where": {"kind": "talk"}}])
    _note(tmp_path, "a.md", kind="talk", status="archived", superseded_by=_link("b.md"))
    _note(tmp_path, "b.md", kind="talk", status="wip", superseded_by=_link("a.md"))
    _note(tmp_path, "c.md", purpose=None, superseded_by=_link("a.md"))
    found = _found(_run(tmp_path), "unarchived-superseded")
    assert [(issue.rel, issue.detail, issue.blocking) for issue in found] == [
        (
            "m/b.md",
            "superseded_by belongs to an archived note, whereas the status wip is not "
            "declared under archived_statuses: archived",
            True,
        ),
        (
            "m/c.md",
            "superseded_by belongs to an archived note, whereas the file declares no status",
            True,
        ),
    ]


@pytest.mark.parametrize(
    ("vocabulary", "message"),
    [
        ({"archived_statuses": "archived"}, "archived_statuses must list status values"),
        (
            {"archived_statuses": ["archived"], "key_values": {"status": ["wip", "stable"]}},
            "archived_statuses names a status outside key_values.status: archived",
        ),
    ],
)
def test_malformed_archived_statuses_fail_the_configuration(
    tmp_path: Path, vocabulary: dict[str, Any], message: str
) -> None:
    """Archived statuses must be a list of values, each declared when the statuses are."""
    _repository(tmp_path, vocabulary)
    result = CliRunner().invoke(app, ["check", "--root", str(tmp_path)])
    assert result.exit_code == 2
    assert message in result.stderr
