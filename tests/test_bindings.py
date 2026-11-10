"""Behavioral tests of the bindings of texts: their resolution along the directory chain, the
fields of records marked by ``x-binds``, and the check of the required, invalid and marked values.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from anagraphe.bindings import BindingChecker, BindingResolver, Merge, Role
from anagraphe.bindings import kinds as binding_kinds
from anagraphe.bindings.kinds import KINDS
from anagraphe.cli import app
from anagraphe.configuration import load_config
from anagraphe.core.configuration import ConfigurationError

SECTION: dict[str, Any] = {
    "index": "_index.md",
    "roles": {
        "onomasia.glossary": {
            "key": "glossary",
            "required": {"types": ["md"], "paths": ["/projects/"]},
        },
        "onomasia.audiences": {"key": "audiences"},
    },
    "records": {"registry": "specs/schema-registry.yml"},
}

BASE_SCHEMA = {
    "$id": "https://example.org/base.schema.yaml",
    "properties": {
        "binds": {"properties": {"glossary": {"type": "string", "x-binds": "onomasia.glossary"}}}
    },
}

FILES: dict[str, Any] = {
    "_index.md": "---\nglossary: base\naudiences: [general]\n---\n# Root\n",
    "projects/p/_index.md": "---\nglossary: project\naudiences: [ml]\n---\n# P\n",
    "projects/p/notes/a.md": "---\nglossary: own\n---\nText.\n",
    "projects/p/notes/b.md": "Text without frontmatter.\n",
    "projects/x.md": "---\ntitle: x\n---\n",
    "projects/p/problem.yml": {
        "_schema": "test:problem@1",
        "glossary": "not-a-binding",
        "binds": {"glossary": "record"},
    },
    "projects/p/other.yml": {"_schema": "test:other@1", "glossary": "from-metadata"},
    "specs/schema-registry.yml": {
        "schema_version": 2,
        "schemas": {"test:problem@1": "schemas/problem.schema.yaml"},
        "resources": {"https://example.org/base.schema.yaml": "schemas/base.schema.yaml"},
    },
    "schemas/problem.schema.yaml": {
        "allOf": [{"$ref": "https://example.org/base.schema.yaml"}],
        "properties": {"_schema": {"const": "test:problem@1"}},
    },
    "schemas/base.schema.yaml": BASE_SCHEMA,
}


def _repository(root: Path, files: dict[str, Any] | None = None, **section: Any) -> Path:
    """Write the fixture repository, with files and keys of the section replaced."""
    for rel, content in {**FILES, **(files or {})}.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            content if isinstance(content, str) else yaml.safe_dump(content), encoding="utf-8"
        )
    declared = {"schema_version": 2, "bindings": {**SECTION, **section}}
    (root / "anagraphe.yml").write_text(yaml.safe_dump(declared), encoding="utf-8")
    return root


def _resolver(root: Path) -> BindingResolver:
    """Return the resolver of the fixture repository."""
    config = load_config(root, root / "anagraphe.yml").bindings
    assert config is not None
    return BindingResolver(root, config)


def _issues(root: Path) -> list[tuple[str, str, str]]:
    """Return the file, the kind and the locus of each issue of the check."""
    config = load_config(root, root / "anagraphe.yml").bindings
    assert config is not None
    return sorted(
        (issue.rel, issue.kind, issue.locus or issue.discriminator)
        for issue in BindingChecker(root, config).check().issues
    )


@pytest.mark.parametrize(
    ("rel", "values", "source"),
    [
        ("projects/p/notes/a.md", ("own",), "projects/p/notes/a.md"),
        ("projects/p/notes/b.md", ("project",), "projects/p/_index.md"),
        ("projects/p/_index.md", ("project",), "projects/p/_index.md"),
        ("projects/x.md", ("base",), "_index.md"),
    ],
)
def test_override_takes_the_nearest_declaration(
    tmp_path: Path, rel: str, values: tuple[str, ...], source: str
) -> None:
    binding = _resolver(_repository(tmp_path)).resolve(rel, Role("onomasia.glossary"))
    assert binding.values == values
    assert [item.rel for item in binding.declarations] == [source]


def test_union_joins_the_declarations_from_the_root(tmp_path: Path) -> None:
    role = Role("onomasia.audiences", Merge.UNION)
    binding = _resolver(_repository(tmp_path)).resolve("projects/p/notes/b.md", role)
    assert binding.values == ("general", "ml")
    assert [item.rel for item in binding.declarations] == ["_index.md", "projects/p/_index.md"]


def test_record_binds_through_the_fields_marked_by_its_schema(tmp_path: Path) -> None:
    binding = _resolver(_repository(tmp_path)).resolve(
        "projects/p/problem.yml", Role("onomasia.glossary")
    )
    assert binding.values == ("record",)
    assert binding.declarations[0].pointer == "/binds/glossary"


def test_record_of_an_unregistered_contract_takes_the_binding_of_its_folder(tmp_path: Path) -> None:
    binding = _resolver(_repository(tmp_path)).resolve(
        "projects/p/other.yml", Role("onomasia.glossary")
    )
    assert binding.values == ("project",)


def test_record_without_its_marked_field_takes_the_binding_of_its_folder(tmp_path: Path) -> None:
    files = {"projects/p/problem.yml": {"_schema": "test:problem@1", "glossary": "ignored"}}
    binding = _resolver(_repository(tmp_path, files)).resolve(
        "projects/p/problem.yml", Role("onomasia.glossary")
    )
    assert binding.values == ("project",)


def test_resolving_an_undeclared_role_fails(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="declares no key for the role"):
        _resolver(_repository(tmp_path)).resolve("projects/x.md", Role("hermeneia.profile"))


def test_clean_repository_reports_nothing(tmp_path: Path) -> None:
    assert _issues(_repository(tmp_path)) == []


PLANTED = {
    "unbound-text": (
        {"_index.md": "# Root without a glossary\n"},
        ("projects/x.md", "unbound-text", "onomasia.glossary"),
    ),
    "invalid-binding": (
        {"projects/p/notes/a.md": "---\nglossary: 3\n---\n"},
        ("projects/p/notes/a.md", "invalid-binding", "/glossary"),
    ),
    "invalid-schema-binding": (
        {
            "schemas/base.schema.yaml": {
                **BASE_SCHEMA,
                "properties": {"binds": {"x-binds": "Glossary"}},
            }
        },
        ("schemas/base.schema.yaml", "invalid-schema-binding", "/properties/binds/x-binds"),
    ),
    "unreadable-schema": (
        {
            "specs/schema-registry.yml": {
                "schema_version": 2,
                "schemas": {"test:problem@1": "schemas/absent.schema.yaml"},
            }
        },
        ("schemas/absent.schema.yaml", "unreadable-schema", ""),
    ),
    "unreadable-binding-source": (
        {"projects/p/notes/a.md": "---\nglossary: [own\n---\nText.\n"},
        ("projects/p/notes/a.md", "unreadable-binding-source", ""),
    ),
    "unresolved-schema-reference": (
        {
            "schemas/problem.schema.yaml": {
                "allOf": [{"$ref": "https://example.org/absent.schema.yaml"}],
            }
        },
        ("schemas/problem.schema.yaml", "unresolved-schema-reference", "/allOf/0/$ref"),
    ),
}


@pytest.mark.parametrize("kind", sorted(PLANTED))
def test_planted_defect_is_reported(tmp_path: Path, kind: str) -> None:
    files, expected = PLANTED[kind]
    assert expected in _issues(_repository(tmp_path, files))


def test_mark_on_a_whole_record_is_reported(tmp_path: Path) -> None:
    files = {"schemas/base.schema.yaml": {**BASE_SCHEMA, "x-binds": "onomasia.glossary"}}
    assert ("schemas/base.schema.yaml", "invalid-schema-binding", "/x-binds") in _issues(
        _repository(tmp_path, files)
    )


@pytest.mark.parametrize(
    ("section", "message"),
    [
        ({"roles": {"glossary": {"key": "glossary"}}}, "must name a role as <tool>.<name>"),
        ({"index": "notes/_index.md"}, "must name the file of a directory index"),
        ({"roles": {"onomasia.glossary": {}}}, "must name the key holding the role"),
        ({"colour": "blue"}, "declares unknown keys: colour"),
    ],
)
def test_invalid_section_is_rejected(tmp_path: Path, section: dict, message: str) -> None:
    root = _repository(tmp_path, **section)
    with pytest.raises(ConfigurationError, match=message):
        load_config(root, root / "anagraphe.yml")


def test_show_prints_the_bindings_of_a_file(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    runner = CliRunner()
    text = runner.invoke(app, ["bindings", "show", "projects/p/notes/b.md", "--root", str(root)])
    shown = runner.invoke(
        app,
        [
            "bindings",
            "show",
            "projects/p/notes/b.md",
            "--root",
            str(root),
            "--role",
            "onomasia.audiences",
            "--merge",
            "union",
            "--format",
            "json",
        ],
    )
    assert text.exit_code == 0
    assert "onomasia.glossary: project (projects/p/_index.md#/glossary)" in text.output
    assert json.loads(shown.output)["bindings"]["onomasia.audiences"]["values"] == ["general", "ml"]


def test_check_exits_with_the_status_of_its_issues(tmp_path: Path) -> None:
    clean = _repository(tmp_path / "clean")
    unbound = _repository(tmp_path / "unbound", {"_index.md": "# Root\n"})
    runner = CliRunner()
    assert runner.invoke(app, ["bindings", "check", "--root", str(clean)]).exit_code == 0
    assert runner.invoke(app, ["check", "--root", str(unbound)]).exit_code == 1


def test_every_kind_of_the_check_is_planted() -> None:
    assert set(PLANTED) == {kind.kind for kind in KINDS}


def test_key_of_a_configuration_file_is_no_binding(tmp_path: Path) -> None:
    files = {"config/checks.yaml": {"glossary": {"paths": ["projects/"]}}}
    assert _issues(_repository(tmp_path, files)) == []


def test_every_kind_constant_is_in_the_catalogue() -> None:
    constants = {
        value
        for name, value in vars(binding_kinds).items()
        if name.isupper() and isinstance(value, str)
    }
    assert constants == {kind.kind for kind in KINDS}


def _schema_repository(root: Path, problem: dict[str, Any], **extra: Any) -> Path:
    """Write the fixture repository with a schema of the contract test:problem@1 replaced."""
    return _repository(root, {"schemas/problem.schema.yaml": problem, **extra})


SCHEMAS: dict[str, tuple[dict[str, Any], dict[str, Any], tuple[str, ...]]] = {
    "recursive-schema": (
        {
            "properties": {"child": {"$ref": "#"}, "binds": {"$ref": "#/$defs/binds"}},
            "$defs": {"binds": {"properties": {"glossary": {"x-binds": "onomasia.glossary"}}}},
        },
        {},
        ("record",),
    ),
    "relative-reference-with-parent": (
        {"allOf": [{"$ref": "../schemas/parts/../base.schema.yaml"}]},
        {},
        ("record",),
    ),
    "escaped-fragment": (
        {"allOf": [{"$ref": "#/$defs/a~1b"}], "$defs": {"a/b": BASE_SCHEMA}},
        {},
        ("record",),
    ),
    "any-of": (
        {"anyOf": [{"$ref": "base.schema.yaml"}]},
        {},
        ("record",),
    ),
    "root-reference": (
        {"allOf": [{"$ref": "/schemas/base.schema.yaml"}]},
        {},
        ("record",),
    ),
    "urn-identifier": (
        {"allOf": [{"$ref": "urn:example:base"}]},
        {
            "specs/schema-registry.yml": {
                "schema_version": 2,
                "schemas": {"test:problem@1": "schemas/problem.schema.yaml"},
                "resources": {"urn:example:base": "schemas/base.schema.yaml"},
            }
        },
        ("record",),
    ),
    "second-field-when-the-first-is-invalid": (
        {
            "properties": {
                "bad": {"x-binds": "onomasia.glossary"},
                "binds": {"properties": {"glossary": {"x-binds": "onomasia.glossary"}}},
            }
        },
        {
            "projects/p/problem.yml": {
                "_schema": "test:problem@1",
                "bad": 7,
                "binds": {"glossary": "record"},
            }
        },
        ("record",),
    ),
}


@pytest.mark.parametrize("case", sorted(SCHEMAS))
def test_record_schema_is_read_through_its_references(tmp_path: Path, case: str) -> None:
    problem, files, values = SCHEMAS[case]
    root = _schema_repository(tmp_path, problem, **files)
    binding = _resolver(root).resolve("projects/p/problem.yml", Role("onomasia.glossary"))
    assert binding.values == values


UNRESOLVED = {
    "unmapped-urn": {"allOf": [{"$ref": "urn:example:absent"}]},
    "missing-relative-file": {"allOf": [{"$ref": "parts/absent.schema.yaml"}]},
    "reference-leaving-the-root": {"allOf": [{"$ref": "../../outside.schema.yaml"}]},
    "missing-fragment": {"allOf": [{"$ref": "#/$defs/absent"}]},
}


@pytest.mark.parametrize("case", sorted(UNRESOLVED))
def test_unresolved_reference_is_reported_at_the_referring_schema(
    tmp_path: Path, case: str
) -> None:
    root = _schema_repository(tmp_path, UNRESOLVED[case])
    assert (
        "schemas/problem.schema.yaml",
        "unresolved-schema-reference",
        "/allOf/0/$ref",
    ) in _issues(root)


def test_mark_under_items_is_reported(tmp_path: Path) -> None:
    problem = {"properties": {"list": {"items": {"x-binds": "onomasia.glossary"}}}}
    issues = _issues(_schema_repository(tmp_path, problem))
    assert (
        "schemas/problem.schema.yaml",
        "invalid-schema-binding",
        "/properties/list/items/x-binds",
    ) in issues


@pytest.mark.parametrize(
    ("value", "kind"),
    [("[]", "invalid-binding"), ("'  '", "invalid-binding"), ("[own, 3]", "invalid-binding")],
)
def test_declaration_naming_no_valid_value_is_invalid(
    tmp_path: Path, value: str, kind: str
) -> None:
    files = {"projects/p/notes/a.md": f"---\nglossary: {value}\n---\n"}
    root = _repository(tmp_path, files)
    assert ("projects/p/notes/a.md", kind, "/glossary") in _issues(root)
    binding = _resolver(root).resolve("projects/p/notes/a.md", Role("onomasia.glossary"))
    assert binding.values == ("project",)


def test_null_declares_nothing(tmp_path: Path) -> None:
    root = _repository(tmp_path, {"projects/p/notes/a.md": "---\nglossary:\n---\n"})
    binding = _resolver(root).resolve("projects/p/notes/a.md", Role("onomasia.glossary"))
    assert binding.values == ("project",) and _issues(root) == []


def test_values_appear_once_under_both_rules(tmp_path: Path) -> None:
    files = {
        "projects/p/notes/a.md": "---\naudiences: [ml, ml, general]\n---\n",
    }
    resolver = _resolver(_repository(tmp_path, files))
    assert resolver.resolve("projects/p/notes/a.md", Role("onomasia.audiences")).values == (
        "ml",
        "general",
    )
    union = resolver.resolve("projects/p/notes/a.md", Role("onomasia.audiences", Merge.UNION))
    assert union.values == ("general", "ml")


@pytest.mark.parametrize("rel", ["/etc/passwd", "../outside.md", "projects/../../outside.md"])
def test_path_outside_the_repository_is_rejected(tmp_path: Path, rel: str) -> None:
    with pytest.raises(ValueError, match="inside the repository"):
        _resolver(_repository(tmp_path)).resolve(rel, Role("onomasia.glossary"))


def test_path_is_normalized_before_resolution(tmp_path: Path) -> None:
    role = Role("onomasia.audiences", Merge.UNION)
    binding = _resolver(_repository(tmp_path)).resolve("./projects/p/_index.md", role)
    assert [item.rel for item in binding.declarations] == ["_index.md", "projects/p/_index.md"]


def test_json_record_with_its_own_binding_key_is_read_and_checked(tmp_path: Path) -> None:
    files = {
        "projects/p/problem.json": json.dumps(
            {"contract": "test:problem@1", "binds": {"glossary": 7}}
        ),
    }
    root = _repository(
        tmp_path, files, records={"registry": "specs/schema-registry.yml", "binding": "contract"}
    )
    assert ("projects/p/problem.json", "invalid-binding", "/binds/glossary") in _issues(root)


def test_missing_registry_fails_the_configuration(tmp_path: Path) -> None:
    root = _repository(tmp_path, records={"registry": "specs/absent.yml"})
    with pytest.raises(ConfigurationError, match="registry names no file"):
        load_config(root, root / "anagraphe.yml")


def test_show_json_names_its_contract_and_its_problems(tmp_path: Path) -> None:
    root = _repository(tmp_path, {"projects/p/_index.md": "---\nglossary: 5\n---\n"})
    result = CliRunner().invoke(
        app, ["bindings", "show", "projects/p/notes/b.md", "--root", str(root), "--format", "json"]
    )
    data = json.loads(result.output)
    assert data["contract"] == "anagraphe:bindings@1"
    assert data["bindings"]["onomasia.glossary"]["values"] == ["base"]
    assert data["problems"][0]["pointer"] == "/glossary"


def test_show_of_a_file_outside_the_repository_exits_with_status_2(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    result = CliRunner().invoke(app, ["bindings", "show", "../elsewhere.md", "--root", str(root)])
    assert result.exit_code == 2
