"""
The interface of the distribution anagraphe-read: the names of ``anagraphe_read``, the boundary
that keeps the distribution independent of the command line, and the repository that
``open_repository`` opens.

The repository of the tests is the consumer of the conformance cases of
``specs/conformance/resolution.yml``, whose record cites the repository ``other-lab``; an
in-memory provider serves the state of ``other-lab``.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

import anagraphe_read
from anagraphe_read import (
    ADDRESSING_ID,
    RENAMED_REPOSITORY,
    TARGET_CONTRACT_MISMATCH,
    UNREADABLE_TARGET_STATE,
    Availability,
    ConfigurationError,
    MemoryProvider,
    Merge,
    Outcome,
    Role,
    State,
    Target,
    Unavailable,
    addressing_schema,
    git_provider,
    Repository,
    open_repository,
)

from resolution_cases import COMMIT, SUITE, consumer_repository, other_lab_state, write

#: The source tree of the distribution.
PACKAGE = Path(anagraphe_read.__file__).resolve().parent
#: The names of the interface of the distribution.
INTERFACE = frozenset(
    {
        "open_repository",
        "Repository",
        "RecordFile",
        "Pointer",
        "Configuration",
        "ConfigurationError",
        "Target",
        "InvalidTarget",
        "Resolution",
        "Outcome",
        "Provenance",
        "RecordRead",
        "Finding",
        "Identity",
        "Binding",
        "Role",
        "Merge",
        "StateProvider",
        "State",
        "Reading",
        "Blob",
        "Mode",
        "Missing",
        "Escaping",
        "Unavailable",
        "Availability",
        "MemoryProvider",
        "git_provider",
        "AMBIGUOUS_UNIT",
        "ESCAPING_TARGET_PATH",
        "IDENTITY_DISAGREEMENT",
        "INVALID_RECORD_REGISTRY",
        "INVALID_TARGET_REPOSITORY",
        "INVALID_TARGET_STATE",
        "LINKED_TARGET_PATH",
        "RENAMED_REPOSITORY",
        "RENAMED_TARGET",
        "RETIRED_REPOSITORY_MANIFEST",
        "RETIRED_TARGET",
        "STALE_TARGET_REGISTRY",
        "TARGET_CONTRACT_MISMATCH",
        "UNBOUND_TARGET",
        "UNKNOWN_RECORD",
        "UNKNOWN_REPOSITORY",
        "UNKNOWN_UNIT",
        "UNREADABLE_RECORD",
        "UNREADABLE_TARGET_STATE",
        "UNVERIFIED_TARGET",
        "ADDRESSING_ID",
        "IMPLEMENTED_SPECIFICATION",
        "addressing_schema",
        "__version__",
    }
)
#: The script that imports every module of the distribution with the package anagraphe blocked,
#: then opens a repository and reads the published resource.
BLOCKED_IMPORT = """
import importlib, pkgutil, sys
from importlib.abc import MetaPathFinder

class Blocker(MetaPathFinder):
    def find_spec(self, name, path, target=None):
        if name == "anagraphe" or name.startswith("anagraphe."):
            raise ModuleNotFoundError(f"anagraphe_read imports {name}")
        return None

sys.meta_path.insert(0, Blocker())
import anagraphe_read
for module in pkgutil.walk_packages(anagraphe_read.__path__, "anagraphe_read."):
    importlib.import_module(module.name)
from pathlib import Path
repository = anagraphe_read.open_repository(Path(sys.argv[1]))
assert repository.identity.id == "lab"
assert anagraphe_read.addressing_schema()["$id"] == anagraphe_read.ADDRESSING_ID
"""


def _imported(path: Path) -> set[str]:
    """Return the modules that a source file imports, relative imports resolved to none."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module)
    return names


def _foreign(names: set[str]) -> set[str]:
    """Return the names of the package anagraphe among imported modules."""
    return {name for name in names if name == "anagraphe" or name.startswith("anagraphe.")}


# --- The interface.


def test_all_names_exactly_the_documented_interface() -> None:
    assert set(anagraphe_read.__all__) == INTERFACE
    assert len(anagraphe_read.__all__) == len(INTERFACE)
    for name in anagraphe_read.__all__:
        assert hasattr(anagraphe_read, name), name


def test_every_module_below_the_interface_is_private() -> None:
    modules = {
        path.relative_to(PACKAGE).parts[0]
        for path in PACKAGE.rglob("*.py")
        if path.relative_to(PACKAGE).parts[0] != "__init__.py"
    }
    assert modules and all(name.startswith("_") for name in modules), modules


# --- The boundary of the distribution.


def test_no_module_of_the_distribution_imports_anagraphe() -> None:
    sources = sorted(PACKAGE.rglob("*.py"))
    assert len(sources) > 30
    found = {
        path.relative_to(PACKAGE).as_posix(): _foreign(_imported(path))
        for path in sources
        if _foreign(_imported(path))
    }
    assert not found


def test_the_distribution_runs_with_anagraphe_blocked(tmp_path: Path) -> None:
    consumer_repository(tmp_path, "{repository: other-lab, id: bo}")
    result = subprocess.run(
        [sys.executable, "-c", BLOCKED_IMPORT, str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


# --- The repository.


def test_open_repository_reads_the_identity_of_its_configuration(tmp_path: Path) -> None:
    consumer_repository(tmp_path, "{repository: other-lab, id: bo}")
    repository = open_repository(tmp_path)
    assert repository.root == tmp_path.resolve()
    assert repository.identity.id == "lab"
    assert repository.configuration.targets is not None
    assert repository.roles == ()


def test_a_target_into_another_repository_resolves_and_reads(tmp_path: Path) -> None:
    consumer_repository(tmp_path, "{repository: other-lab, id: bo}")
    repository = open_repository(tmp_path, provider=other_lab_state())
    resolution = repository.resolve(Target.parse({"repository": "other-lab", "id": "ada"}))
    assert resolution.outcome is Outcome.RECORD
    read = repository.read(resolution, (("test:person",),))
    assert read.verified
    assert read.data == SUITE["states"]["other-lab"]["people/ada.yml"].encode("utf-8")
    assert (read.provenance.repository, read.provenance.commit) == ("other-lab", COMMIT)


def test_the_findings_of_a_resolution_carry_the_exported_kinds(tmp_path: Path) -> None:
    consumer_repository(tmp_path, "{repository: old-lab, id: arg.one}")
    repository = open_repository(tmp_path, provider=other_lab_state())
    resolution = repository.resolve(Target.parse({"repository": "old-lab", "id": "arg.one"}))
    read = repository.read(resolution, (("test:person",),))
    kinds = [finding.kind for finding in (*resolution.findings, *read.findings)]
    assert kinds == [RENAMED_REPOSITORY, TARGET_CONTRACT_MISMATCH]


def test_a_target_of_the_repository_itself_is_local(tmp_path: Path) -> None:
    consumer_repository(tmp_path, "{repository: other-lab, id: bo}")
    resolution = open_repository(tmp_path).resolve(Target.parse({"repository": "lab", "id": "x"}))
    assert resolution.outcome is Outcome.LOCAL
    assert resolution.target == Target("lab", "x")


def test_a_state_absent_from_the_machine_is_reported(tmp_path: Path) -> None:
    consumer_repository(tmp_path, "{repository: other-lab, id: bo}")
    repository = open_repository(tmp_path, provider=MemoryProvider({}))
    resolution = repository.resolve(Target.parse({"repository": "other-lab", "id": "ada"}))
    assert resolution.outcome is Outcome.UNRESOLVED
    assert [finding.kind for finding in resolution.findings] == [UNREADABLE_TARGET_STATE]


def test_the_bindings_of_a_text_resolve_along_the_directory_chain(tmp_path: Path) -> None:
    bindings = {
        "index": "_index.md",
        "roles": {"onomasia.glossary": {"key": "glossary"}, "onomasia.audiences": {"key": "aud"}},
    }
    consumer_repository(tmp_path, "{repository: other-lab, id: bo}", {"bindings": bindings})
    write(
        tmp_path,
        {
            "_index.md": "---\nglossary: base\naud: [general]\n---\n# Root\n",
            "notes/_index.md": "---\naud: [ml]\n---\n# Notes\n",
            "notes/a.md": "---\ntitle: a\n---\nText.\n",
        },
    )
    repository = open_repository(tmp_path)
    assert set(repository.roles) == {"onomasia.glossary", "onomasia.audiences"}
    glossary = repository.bindings("notes/a.md", Role("onomasia.glossary"))
    assert (glossary.values, [item.rel for item in glossary.declarations]) == (
        ("base",),
        ["_index.md"],
    )
    audiences = repository.bindings("notes/a.md", Role("onomasia.audiences", Merge.UNION))
    assert audiences.values == ("general", "ml")


def test_a_role_without_a_key_is_a_configuration_error(tmp_path: Path) -> None:
    bindings = {"index": "_index.md", "roles": {"onomasia.glossary": {"key": "glossary"}}}
    consumer_repository(tmp_path, "{repository: other-lab, id: bo}", {"bindings": bindings})
    with pytest.raises(ConfigurationError, match="no key for the role onomasia.notation"):
        open_repository(tmp_path).bindings("a.md", Role("onomasia.notation"))


def test_a_root_without_configuration_opens_empty(tmp_path: Path) -> None:
    root = tmp_path / "plain-lab"
    root.mkdir()
    repository = open_repository(root, provider=MemoryProvider({}))
    assert repository.identity.id == "plain-lab"
    assert repository.configuration.targets is None and repository.roles == ()
    with pytest.raises(ConfigurationError, match="declares no section bindings"):
        repository.bindings("a.md", Role("onomasia.glossary"))
    assert open_repository(root).resolve(Target(None, "x")).outcome is Outcome.LOCAL


def test_a_named_configuration_must_exist(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="no configuration file at"):
        open_repository(tmp_path, config=tmp_path / "absent.yml")


def test_an_invalid_configuration_is_a_configuration_error(tmp_path: Path) -> None:
    write(tmp_path, {"anagraphe.yml": "_schema: anagraphe:configuration@3\ntargts: {}\n"})
    with pytest.raises(ConfigurationError, match="unknown keys: targts"):
        open_repository(tmp_path)


def test_the_git_provider_reads_the_cache_of_the_machine(tmp_path: Path) -> None:
    reading = git_provider(tmp_path / "cache").read(State(COMMIT), "a.yml")
    assert isinstance(reading, Unavailable) and reading.availability is Availability.ABSENT
    assert "anagraphe states fetch" in reading.detail


def test_the_addressing_schema_is_a_copy_of_the_resource() -> None:
    first = addressing_schema()
    assert first["$id"] == ADDRESSING_ID
    first["$id"] = "changed"
    assert addressing_schema()["$id"] == ADDRESSING_ID


def test_the_records_name_their_contract_and_place_their_nodes(tmp_path: Path) -> None:
    consumer_repository(tmp_path, "{repository: other-lab, id: bo}")
    (tmp_path / "note.md").write_text("---\n_schema: test:note@1\ntitle: t\n---\nbody\n")
    repository = open_repository(tmp_path, provider=MemoryProvider({}))
    records = {record.path: record for record in repository.records()}
    assert repository.binding == "_schema"
    assert repository.schema_registry is not None and repository.schema_registry.is_file()
    cite = records["cite.yml"]
    assert cite.contract == "test:citing@1" and cite.problem is None
    assert cite.data["profile"] == {"repository": "other-lab", "id": "bo"}
    assert cite.position(["profile", "id"]) == (2, 38)
    assert cite.position(["profile", "absent"]) == cite.position(["profile"]) == (2, 10)
    assert cite.position([]) is None
    assert records["note.md"].position(["title"]) == (3, 8)


def test_records_require_the_section_targets(tmp_path: Path) -> None:
    root = tmp_path / "plain-lab"
    root.mkdir()
    with pytest.raises(ConfigurationError, match="declares no section targets"):
        open_repository(root, provider=MemoryProvider({})).records()


# --- The pointers, the metadata and the exclusions of the files.


def _texts(root: Path, config: str) -> Repository:
    """Write a repository of notes and documents, configured by ``config``, and open it."""
    files = {
        "anagraphe.yml": "_schema: anagraphe:configuration@3\n" + config,
        "notes/a.md": (
            "---\nsource: '[B](../b.md)'\nrole: note\n---\n"
            "See [B](../b.md), [[b]], `[C](../c.md)`, [gone](../gone.md) and "
            "[site](https://example.org).\n"
        ),
        "b.md": "# B\n",
        "data/table.yml": "title: Table\nrole: data\n",
        "data/plain.txt": "no metadata\n",
        "drafts/x.md": "---\nrole: draft\n---\n",
        ".hidden/y.md": "---\nrole: hidden\n---\n",
    }
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return open_repository(root, provider=MemoryProvider({}))


def test_the_pointers_of_a_note_are_resolved(tmp_path: Path) -> None:
    pointers = _texts(tmp_path, "exclude:\n  paths: [drafts/]\n").references("notes/a.md")
    found = {(pointer.raw, pointer.syntax, pointer.region, pointer.target) for pointer in pointers}
    assert found == {
        ("../b.md", "markdown", "metadata", "b.md"),
        ("../b.md", "markdown", "content", "b.md"),
        ("b", "wikilink", "content", "b.md"),
        ("../gone.md", "markdown", "content", None),
        ("https://example.org", "markdown", "content", None),
    }
    link = next(pointer for pointer in pointers if pointer.region == "content")
    assert (link.source, link.line, link.column) == ("notes/a.md", 5, 9)


def test_the_metadata_of_a_file_is_read_from_its_source(tmp_path: Path) -> None:
    repository = _texts(tmp_path, "exclude:\n  paths: [drafts/]\n")
    assert repository.metadata("notes/a.md")["role"] == "note"
    assert repository.metadata("data/table.yml") == {"title": "Table", "role": "data"}
    assert repository.metadata("data/plain.txt") == {}


def test_the_shared_exclusions_leave_out_excluded_and_hidden_paths(tmp_path: Path) -> None:
    repository = _texts(tmp_path, "exclude:\n  paths: [drafts/]\n")
    assert repository.exempt("drafts/x.md") and repository.exempt(".hidden/y.md")
    assert not repository.exempt("notes/a.md")


def test_a_path_leaving_the_repository_is_refused(tmp_path: Path) -> None:
    repository = _texts(tmp_path, "exclude:\n  paths: [drafts/]\n")
    for call in (repository.references, repository.metadata, repository.exempt):
        with pytest.raises(ValueError, match="inside the repository"):
            call("../outside.md")


def test_a_pointer_states_the_path_that_it_names(tmp_path: Path) -> None:
    """A broken link still names a path of the repository, unlike a URL."""
    repository = _texts(tmp_path, "exclude:\n  paths: [drafts/]\n")
    (tmp_path / "notes/c.md").write_text(
        "[gone](../../projects/x/gone.md) [lost](../lost/a.md) [b](../b.md) "
        "[site](https://example.org) [rooted](/root/missing.md)\n",
        encoding="utf-8",
    )
    named = {
        pointer.raw: (pointer.target, pointer.named)
        for pointer in repository.references("notes/c.md")
    }
    assert named["../lost/a.md"] == (None, "lost/a.md")
    assert named["../../projects/x/gone.md"] == (None, None)
    assert named["../b.md"] == ("b.md", "b.md")
    assert named["https://example.org"] == (None, None)
    assert named["/root/missing.md"] == (None, "root/missing.md")
