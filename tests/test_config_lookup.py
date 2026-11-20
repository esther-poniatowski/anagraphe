"""Behavioral tests of the resolution of the root and of the configuration file.

Hodegos locates both. The root is the folder given by ``--root``, else by ``ANAGRAPHE_ROOT``, else
the nearest folder, from the current one upwards, holding ``anagraphe.yml`` at one of its places,
else the current folder. The places are the root, its ``.config/`` and its ``config/``; two places
holding a file is an error, and a folder outside them is not searched. A given ``--config`` is read
from the current folder. The former option ``--json`` of ``bindings show`` is retired.
"""

from __future__ import annotations

import re

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from anagraphe_read._core.configuration import ConfigurationError, discover_configuration

from anagraphe.cli import app
from anagraphe.configuration import load_config

#: A valid configuration, which the command ``check`` reads with no issue.
VALID = "_schema: anagraphe:configuration@3\nreferences: {}\n"
#: A configuration that the command ``check`` rejects with a message naming the retired version.
RETIRED = "schema_version: 1\nreferences: {}\n"
#: The configuration in the subfolder ``config/``, a place of Hodegos.
NESTED = Path("config/anagraphe.yml")
#: The configuration in a folder that no place of Hodegos admits.
OUTSIDE = Path("shared/anagraphe.yml")


def _repository(root: Path, files: dict[Path | str, str]) -> Path:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _runner() -> CliRunner:
    """A runner keeping the standard error apart from the standard output, under Click 8.1 too."""
    try:
        return CliRunner(mix_stderr=False)  # type: ignore[call-arg]
    except TypeError:
        return CliRunner()


def _located(root: Path, config: Path | None = None) -> Path | None:
    """Return the configuration file that the discovery locates for the root."""
    return discover_configuration(root, config)[1]


def test_lookup_reads_the_file_of_config(tmp_path: Path) -> None:
    root = _repository(tmp_path, {NESTED: VALID})
    assert _located(root) == root / NESTED
    assert CliRunner().invoke(app, ["check", "--root", str(root)]).exit_code == 0


def test_lookup_ignores_a_folder_outside_the_places(tmp_path: Path) -> None:
    root = _repository(tmp_path, {OUTSIDE: VALID})
    assert _located(root) is None
    result = _runner().invoke(app, ["check", "--root", str(root)])
    assert result.exit_code == 2
    assert "no configuration" in result.stderr


def test_lookup_reads_the_file_at_the_root(tmp_path: Path) -> None:
    root = _repository(tmp_path, {"anagraphe.yml": RETIRED})
    assert _located(root) == root / "anagraphe.yml"
    result = CliRunner().invoke(app, ["check", "--root", str(root)])
    assert result.exit_code == 2
    assert "schema_version is retired: write _schema: anagraphe:configuration@3" in result.output


def test_lookup_reads_the_file_of_dot_config(tmp_path: Path) -> None:
    root = _repository(tmp_path, {".config/anagraphe.yml": VALID})
    assert _located(root) == root / ".config/anagraphe.yml"
    assert CliRunner().invoke(app, ["check", "--root", str(root)]).exit_code == 0


@pytest.mark.parametrize(
    "text",
    [
        "references: {}\n",
        "_schema: anagraphe:configuration@1\nreferences: {}\n",
        "schema_version: 2\nreferences: {}\n",
    ],
)
def test_a_file_of_another_format_stops_with_status_2(tmp_path: Path, text: str) -> None:
    """An absent key, a wrong identifier and the old key all name the value to write."""
    root = _repository(tmp_path, {"anagraphe.yml": text})
    result = _runner().invoke(app, ["check", "--root", str(root)])
    assert result.exit_code == 2
    assert "anagraphe:configuration@3" in result.stderr


def test_the_former_format_names_each_move_of_the_vocabulary(tmp_path: Path) -> None:
    """A configuration in anagraphe:configuration@2 stops, and names the format to write and the
    place of each entry of the vocabulary that it read."""
    text = "_schema: anagraphe:configuration@2\nindexes: {vocabulary: v.yml}\n"
    root = _repository(tmp_path, {"anagraphe.yml": text})
    with pytest.raises(ConfigurationError) as raised:
        load_config(root, root / "anagraphe.yml")
    message = str(raised.value)
    assert message.startswith(
        "_schema: anagraphe:configuration@2 is retired: write _schema: anagraphe:configuration@3"
    )
    for move in (
        "indexes.vocabulary is removed",
        "properties.<key>.items",
        "properties.context_relations.items.properties.relation",
        "schema.entry_point becomes indexes.entry_point",
        "schema.generated_index_areas becomes indexes.generated_areas",
        "archived_statuses becomes indexes.archived_statuses",
        "listed: false under roles is listed under indexes.unlisted_roles",
        "schema.frames is checked by Hermeneia",
    ):
        assert move in message


def test_two_configuration_files_are_an_error_naming_both(tmp_path: Path) -> None:
    root = _repository(tmp_path, {NESTED: VALID, "anagraphe.yml": VALID})
    with pytest.raises(ConfigurationError, match="two places hold a configuration"):
        _located(root)
    result = _runner().invoke(app, ["check", "--root", str(root)])
    assert result.exit_code == 2
    assert str(root / NESTED) in result.stderr
    assert str(root / "anagraphe.yml") in result.stderr


def test_given_config_is_read_from_the_current_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repository(
        tmp_path / "repository", {"anagraphe.yml": RETIRED, "settings/other.yml": VALID}
    )
    monkeypatch.chdir(root / "settings")
    assert _located(root, Path("other.yml")) == root / "settings/other.yml"
    result = CliRunner().invoke(app, ["check", "-r", str(root), "-c", "other.yml"])
    assert result.exit_code == 0, result.output
    # The same name read from the root would be absent: the root does not anchor --config.
    monkeypatch.chdir(tmp_path)
    assert CliRunner().invoke(app, ["check", "-r", str(root), "-c", "other.yml"]).exit_code == 2


def test_given_absolute_config_is_kept(tmp_path: Path) -> None:
    root = _repository(tmp_path, {"elsewhere/settings.yml": VALID})
    assert _located(root, root / "elsewhere/settings.yml") == root / "elsewhere/settings.yml"


def test_given_absent_config_is_an_error(tmp_path: Path) -> None:
    root = _repository(tmp_path, {"anagraphe.yml": VALID})
    with pytest.raises(ConfigurationError, match="no configuration file at"):
        _located(root, root / "absent.yml")
    command = ["check", "--root", str(root), "--config", str(root / "absent.yml")]
    result = _runner().invoke(app, command)
    assert result.exit_code == 2
    assert "absent.yml" in result.stderr


def test_missing_configuration_names_the_places(tmp_path: Path) -> None:
    assert _located(tmp_path) is None
    result = CliRunner().invoke(app, ["check", "--root", str(tmp_path)])
    assert result.exit_code == 2
    assert (
        "no configuration: write anagraphe.yml at the root, in .config/ or in config/, or name "
        "it with --config"
    ) in result.output


def test_root_is_found_upwards_from_the_current_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repository(
        tmp_path / "repository", {"anagraphe.yml": VALID, "notes/deep/a.md": "# A\n"}
    )
    monkeypatch.chdir(root / "notes/deep")
    assert discover_configuration()[0] == root.resolve()
    result = CliRunner().invoke(app, ["refs", "check", "a.md"])
    assert result.exit_code == 0, result.output
    assert "references: checked 1 files" in result.output


def test_root_is_read_from_the_environment_below_the_option(tmp_path: Path) -> None:
    valid = _repository(tmp_path / "valid", {"anagraphe.yml": VALID})
    retired = _repository(tmp_path / "retired", {"anagraphe.yml": RETIRED})
    runner = CliRunner()
    assert runner.invoke(app, ["check"], env={"ANAGRAPHE_ROOT": str(valid)}).exit_code == 0
    assert runner.invoke(app, ["check"], env={"ANAGRAPHE_ROOT": str(retired)}).exit_code == 2
    command = ["check", "--root", str(valid)]
    assert runner.invoke(app, command, env={"ANAGRAPHE_ROOT": str(retired)}).exit_code == 0


#: A repository declaring one role, bound by the root index.
BOUND = {
    "anagraphe.yml": (
        "_schema: anagraphe:configuration@3\nbindings:\n  index: _index.md\n  roles:\n"
        "    onomasia.glossary: {key: glossary}\n"
    ),
    "_index.md": "---\nglossary: base\n---\n",
    "notes/a.md": "# A\n",
}


def test_format_json_prints_the_bindings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _repository(tmp_path, BOUND)
    monkeypatch.chdir(root)
    result = _runner().invoke(app, ["bindings", "show", "notes/a.md", "--format", "json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["bindings"]["onomasia.glossary"]["values"] == ["base"]


def test_retired_option_json_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _repository(tmp_path, BOUND)
    monkeypatch.chdir(root)
    result = _runner().invoke(app, ["bindings", "show", "notes/a.md", "--json"])
    assert result.exit_code == 2
    # Rich colours the message on a terminal that admits colours, as on the runners of CI.
    assert "No such option: --json" in re.sub(r"\x1b\[[0-9;]*m", "", result.stderr)
