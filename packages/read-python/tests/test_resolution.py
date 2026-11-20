"""
The record resolver of ADR 0009.

The conformance cases of ``specs/conformance/resolution.yml`` fix the operations ``resolve`` and
``read`` on a declared context and an in-memory provider. The tests below them build the context
of a root from its gitlinks and its section ``resolution``, validate that section and the machine
file of the local clones, and name a submodule by the identity of its state. The check of the
targets with a provider is tested with the command line.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Mapping

import pytest

from anagraphe_read._core.configuration import ConfigurationError
from anagraphe_read._core.schemas import SchemaReader
from anagraphe_read._resolution.configuration import MACHINE_VARIABLE, parse_section
from anagraphe_read._resolution.context import (
    Entry,
    ResolutionContext,
    Unnamed,
    Unreadable,
    build_context,
    read_configuration,
)
from anagraphe_read._resolution.provider import (
    Blob,
    EmptyProvider,
    Escaping,
    MemoryProvider,
    Mode,
    State,
)
from anagraphe_read._resolution.resolver import Outcome, RecordResolver
from anagraphe_read._targets.declarations import Declarations
from anagraphe_read._targets.identity import Identity, IdentitySource
from anagraphe_read._targets.kinds import KINDS
from anagraphe_read._targets.model import Target

from resolution_cases import CASES, COMMIT, OTHER_COMMIT, SUITE, blob, write

#: The kinds of the record resolver, which ADR 0009 adds or extends to another repository.
RESOLVER_KINDS = frozenset(
    {
        "renamed-repository",
        "unknown-repository",
        "invalid-target-repository",
        "linked-target-path",
        "escaping-target-path",
        "stale-target-registry",
        "invalid-target-state",
        "unreadable-target-state",
        "unknown-record",
        "unreadable-record",
        "invalid-record-registry",
        "renamed-target",
        "retired-target",
        "unverified-target",
    }
)
#: The identity of the root of the tests of the context.
ROOT_IDENTITY = Identity("lab", IdentitySource.OVERRIDE)


def _git(root: Path, *args: str) -> None:
    """Run a Git command in a repository, failing the test when Git fails."""
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _provider(case: Mapping[str, Any]) -> MemoryProvider:
    """Return the provider of the states of a case."""
    states: dict[str, dict[str, Blob]] = {}
    for commit, declared in case["states"].items():
        files = dict(SUITE["states"][declared["from"]]) if "from" in declared else {}
        files.update(declared.get("files", {}))
        for rel in declared.get("remove", []):
            files.pop(rel)
        states[commit] = {rel: blob(value) for rel, value in files.items()}
    return MemoryProvider(
        states, frozenset(case.get("denied", [])), frozenset(case.get("invalid", []))
    )


def _context(case: Mapping[str, Any]) -> ResolutionContext:
    """Return the resolution context declared by a case."""
    declared = case["context"]
    remotes = declared.get("remotes", {})
    configs = declared.get("configs", {})
    return ResolutionContext(
        declared["repository"],
        tuple(declared.get("retired", [])),
        {
            identifier: Entry(
                identifier,
                State(commit, remotes.get(identifier)),
                "resolution.repositories",
                configs.get(identifier),
            )
            for identifier, commit in declared["commits"].items()
        },
        tuple(
            Unnamed(item["path"], item["commit"], "unread") for item in declared.get("unnamed", [])
        ),
    )


def _declarations(root: Path) -> Declarations:
    """Write the files of the consumer, and return the declarations of its schema registry."""
    write(root, SUITE["consumer"]["files"])
    registry = root / SUITE["consumer"]["section"]["records"]["registry"]
    return Declarations(SchemaReader(root.resolve(), registry.resolve()))


# --- Conformance cases.


@pytest.mark.parametrize("case_id", sorted(CASES))
def test_case_conforms(tmp_path: Path, case_id: str) -> None:
    case = CASES[case_id]
    resolver = RecordResolver(_context(case), _provider(case), _declarations(tmp_path))
    resolution = resolver.resolve(Target.parse(case["target"]))
    kinds = [finding.kind for finding in resolution.findings]
    if resolution.outcome is Outcome.RECORD:
        contracts = tuple(tuple(entries) for entries in case.get("contracts", []))
        kinds.extend(finding.kind for finding in resolver.read(resolution, contracts).findings)
    assert resolution.outcome.value == case["outcome"]
    assert kinds == case["findings"]
    if "provenance" in case:
        assert resolution.provenance is not None
        assert vars(resolution.provenance) == case["provenance"]
    else:
        assert resolution.provenance is None


def test_every_kind_of_the_resolver_has_a_planted_case() -> None:
    planted = {kind for case in CASES.values() for kind in case["findings"]}
    assert RESOLVER_KINDS <= planted
    catalogue = {kind.kind: kind.level for kind in KINDS}
    assert RESOLVER_KINDS <= set(catalogue)
    assert (catalogue["unreadable-target-state"], catalogue["unverified-target"]) == (
        "warning",
        "note",
    )


def test_a_verified_read_returns_the_bytes_and_their_provenance(tmp_path: Path) -> None:
    case = CASES["record-of-another-repository"]
    resolver = RecordResolver(_context(case), _provider(case), _declarations(tmp_path))
    read = resolver.read(resolver.resolve(Target.parse(case["target"])), (("test:person",),))
    assert read.verified
    assert read.data == SUITE["states"]["other-lab"]["people/ada.yml"].encode("utf-8")
    assert (read.provenance.repository, read.provenance.commit) == ("other-lab", "c1")


def test_read_refuses_an_unresolved_target(tmp_path: Path) -> None:
    case = CASES["unknown-record"]
    resolver = RecordResolver(_context(case), _provider(case), _declarations(tmp_path))
    with pytest.raises(ValueError, match="placed at a record"):
        resolver.read(resolver.resolve(Target.parse(case["target"])))


def test_the_providers_reject_an_escaping_path() -> None:
    state = State(COMMIT)
    assert isinstance(MemoryProvider({COMMIT: {}}).read(state, "../a.yml"), Escaping)
    assert isinstance(EmptyProvider().read(state, "/a.yml"), Escaping)


# --- The context of a root.


def _configuration_bytes(identifier: str) -> Blob:
    """Return a configuration overriding the identifier of a repository, as the file of a state."""
    return Blob(f"_schema: anagraphe:configuration@3\nrepository: {{id: {identifier}}}\n".encode())


def _root_with_gitlink(root: Path) -> None:
    """Initialize a repository whose index records the submodule ``projects/x`` at COMMIT."""
    _git(root, "init", "-q")
    _git(root, "update-index", "--add", "--cacheinfo", f"160000,{COMMIT},projects/x")


def test_a_gitlink_names_its_repository_through_the_provider(tmp_path: Path) -> None:
    _root_with_gitlink(tmp_path)
    provider = MemoryProvider({COMMIT: {"anagraphe.yml": _configuration_bytes("x-lab")}})
    context = build_context(tmp_path, ROOT_IDENTITY, None, provider)
    assert set(context.entries) == {"x-lab"}
    entry = context.entries["x-lab"]
    assert (entry.state.commit, entry.state.clone, entry.origin) == (
        COMMIT,
        tmp_path / "projects/x",
        "submodule projects/x",
    )
    assert not context.unnamed


def test_an_unread_gitlink_stays_unnamed(tmp_path: Path) -> None:
    _root_with_gitlink(tmp_path)
    context = build_context(tmp_path, ROOT_IDENTITY, None, EmptyProvider())
    assert context.entries == {}
    assert [(item.path, item.commit) for item in context.unnamed] == [("projects/x", COMMIT)]


def test_a_gitlink_without_override_is_named_by_its_remote(tmp_path: Path) -> None:
    _root_with_gitlink(tmp_path)
    write(
        tmp_path,
        {".gitmodules": '[submodule "x"]\n\tpath = projects/x\n\turl = git@h.org:lab/x-lab.git\n'},
    )
    context = build_context(tmp_path, ROOT_IDENTITY, None, MemoryProvider({COMMIT: {}}))
    assert set(context.entries) == {"x-lab"}
    assert context.entries["x-lab"].state.remote == "git@h.org:lab/x-lab.git"


def test_a_gitlink_without_identity_stays_unnamed(tmp_path: Path) -> None:
    _root_with_gitlink(tmp_path)
    context = build_context(tmp_path, ROOT_IDENTITY, None, MemoryProvider({COMMIT: {}}))
    assert context.entries == {}
    (unnamed,) = context.unnamed
    assert "declares no repository.id" in unnamed.detail


@pytest.mark.parametrize(
    "place", ["anagraphe.yml", ".config/anagraphe.yml", "config/anagraphe.yml"]
)
def test_the_configuration_of_a_state_is_read_at_each_place(place: str) -> None:
    provider = MemoryProvider({COMMIT: {place: _configuration_bytes("x-lab")}})
    found = read_configuration(provider, State(COMMIT))
    assert isinstance(found, tuple) and found[0] == place
    assert found[1]["repository"] == {"id": "x-lab"}


def test_a_folder_outside_the_places_of_a_state_is_not_read() -> None:
    provider = MemoryProvider({COMMIT: {"shared/anagraphe.yml": _configuration_bytes("x-lab")}})
    assert read_configuration(provider, State(COMMIT)) is None


@pytest.mark.parametrize(
    ("entries", "detail"),
    [
        (
            {"anagraphe.yml": b"records: {}\n", "config/anagraphe.yml": b"records: {}\n"},
            "two places hold a configuration of anagraphe: anagraphe.yml and config/anagraphe.yml",
        ),
        ({"config/anagraphe.yml": Blob(b"x.yml", Mode.LINK)}, "config/anagraphe.yml is a link"),
        ({"config": Blob(b"elsewhere", Mode.LINK)}, "config/anagraphe.yml leaves the state"),
        ({".config/anagraphe.yml/a": b""}, ".config/anagraphe.yml is a directory"),
        ({"anagraphe.yml": b"- a list\n"}, "anagraphe.yml cannot be parsed as a mapping"),
    ],
)
def test_a_defect_at_a_place_of_a_state_makes_its_configuration_unreadable(
    entries: dict[str, bytes | Blob], detail: str
) -> None:
    blobs = {path: item if isinstance(item, Blob) else Blob(item) for path, item in entries.items()}
    found = read_configuration(MemoryProvider({COMMIT: blobs}), State(COMMIT))
    assert isinstance(found, Unreadable) and found.detail.startswith(detail)


def test_an_absent_state_keeps_the_reading_of_the_provider() -> None:
    found = read_configuration(EmptyProvider(), State(COMMIT))
    assert isinstance(found, Unreadable) and found.reading is not None


def test_a_derived_and_a_declared_entry_of_one_repository_stop_the_command(
    tmp_path: Path,
) -> None:
    _root_with_gitlink(tmp_path)
    provider = MemoryProvider({COMMIT: {"anagraphe.yml": _configuration_bytes("x-lab")}})
    config = parse_section(
        tmp_path,
        {"repositories": {"x-lab": {"commit": OTHER_COMMIT, "remote": "https://h.org/x.git"}}},
        environment={},
    )
    with pytest.raises(ConfigurationError, match="both select a state of x-lab"):
        build_context(tmp_path, ROOT_IDENTITY, config, provider)


def test_an_entry_naming_the_root_stops_the_command(tmp_path: Path) -> None:
    config = parse_section(
        tmp_path,
        {"repositories": {"lab": {"commit": COMMIT, "remote": "https://h.org/lab.git"}}},
        environment={},
    )
    with pytest.raises(ConfigurationError, match="the repository of the root itself"):
        build_context(tmp_path, ROOT_IDENTITY, config, EmptyProvider())


# --- The section resolution and the machine file.


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        ({"commit": "1234567", "remote": "https://h.org/x.git"}, "full commit"),
        ({"commit": COMMIT, "remote": "https://token@h.org/x.git"}, "credentials"),
        ({"commit": COMMIT, "remote": "https://u:p@h.org/x.git"}, "credentials"),
        ({"commit": COMMIT, "remote": "/Users/lab/x"}, "names no remote address"),
        ({"commit": COMMIT}, "the keys commit and remote"),
        ({"commit": COMMIT, "remote": "https://h.org/x.git", "file": "a.yml"}, "optionally config"),
        ({"commit": COMMIT, "remote": "https://h.org/x.git", "config": "/x.yml"}, "inside that"),
        ({"commit": COMMIT, "remote": "https://h.org/x.git", "config": "../x.yml"}, "inside that"),
        ({"commit": COMMIT, "remote": "https://h.org/x.git", "config": ""}, "inside that"),
        ({"commit": COMMIT, "remote": "https://h.org/x.git", "config": 3}, "inside that"),
    ],
)
def test_a_declared_repository_is_validated(
    tmp_path: Path, entry: dict[str, str], message: str
) -> None:
    with pytest.raises(ConfigurationError, match=message):
        parse_section(tmp_path, {"repositories": {"x-lab": entry}}, environment={})


def test_ssh_and_scp_remotes_are_admitted(tmp_path: Path) -> None:
    config = parse_section(
        tmp_path,
        {
            "repositories": {
                "x-lab": {"commit": COMMIT, "remote": "ssh://git@h.org/x.git"},
                "y-lab": {"commit": "a" * 64, "remote": "git@h.org:lab/y.git"},
            }
        },
        environment={},
    )
    assert set(config.repositories) == {"x-lab", "y-lab"}


def test_the_key_config_names_the_configuration_of_the_declared_state(tmp_path: Path) -> None:
    config = parse_section(
        tmp_path,
        {
            "repositories": {
                "x-lab": {
                    "commit": COMMIT,
                    "remote": "https://h.org/x.git",
                    "config": "./settings/anagraphe.yml",
                },
                "y-lab": {"commit": OTHER_COMMIT, "remote": "https://h.org/y.git"},
            }
        },
        environment={},
    )
    context = build_context(tmp_path, ROOT_IDENTITY, config, EmptyProvider())
    assert context.entries["x-lab"].config == "settings/anagraphe.yml"
    assert context.entries["y-lab"].config is None


def test_the_place_named_by_the_key_config_is_read_alone() -> None:
    provider = MemoryProvider(
        {
            COMMIT: {
                "anagraphe.yml": _configuration_bytes("x-lab"),
                "settings/anagraphe.yml": _configuration_bytes("y-lab"),
            }
        }
    )
    found = read_configuration(provider, State(COMMIT), "settings/anagraphe.yml")
    assert isinstance(found, tuple) and found[0] == "settings/anagraphe.yml"
    assert found[1]["repository"] == {"id": "y-lab"}
    assert read_configuration(provider, State(COMMIT)) == (
        "anagraphe.yml",
        {"_schema": "anagraphe:configuration@3", "repository": {"id": "x-lab"}},
    )


def test_an_absent_named_configuration_names_the_repository_the_commit_and_the_path(
    tmp_path: Path,
) -> None:
    case = CASES["place-named-by-the-entry-absent"]
    resolver = RecordResolver(_context(case), _provider(case), _declarations(tmp_path))
    resolution = resolver.resolve(Target.parse(case["target"]))
    assert [finding.detail for finding in resolution.findings] == [
        "{repository: other-lab, id: ada}: the state c1 of other-lab: the key config names "
        "settings/anagraphe.yml, and the state holds no configuration there"
    ]


def test_a_local_machine_file_must_be_ignored_by_git(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    write(tmp_path, {"clones.yml": "x-lab: ../x\n"})
    with pytest.raises(ConfigurationError, match="which Git would record"):
        parse_section(tmp_path, {"local": "clones.yml"}, environment={})
    write(tmp_path, {".gitignore": "clones.yml\n"})
    config = parse_section(tmp_path, {"local": "clones.yml"}, environment={})
    assert config.clones == {"x-lab": tmp_path.resolve() / "../x"}


def test_a_tracked_machine_file_stops_the_command(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    write(tmp_path, {"clones.yml": "x-lab: ../x\n", ".gitignore": "clones.yml\n"})
    _git(tmp_path, "add", "-f", "clones.yml")
    with pytest.raises(ConfigurationError, match="which Git would record"):
        parse_section(tmp_path, {"local": "clones.yml"}, environment={})


def test_an_absent_local_machine_file_maps_no_clone(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    write(tmp_path, {".gitignore": "clones.yml\n"})
    assert parse_section(tmp_path, {"local": "clones.yml"}, environment={}).clones == {}


def test_the_variable_names_the_machine_file_before_the_key_local(tmp_path: Path) -> None:
    machine = tmp_path / "machine" / "repositories.yml"
    write(tmp_path, {"machine/repositories.yml": "x-lab: /work/x\n", "root/.keep": ""})
    config = parse_section(
        tmp_path / "root", {"local": "clones.yml"}, environment={MACHINE_VARIABLE: str(machine)}
    )
    assert (config.machine_file, config.clones) == (machine, {"x-lab": Path("/work/x")})
    with pytest.raises(ConfigurationError, match="names no file"):
        parse_section(
            tmp_path / "root", None, environment={MACHINE_VARIABLE: str(tmp_path / "absent.yml")}
        )
