"""Behavioral tests of the resolution of the root and of the configuration file.

The root is the folder given by ``--root``, else by ``ANAGRAPHE_ROOT``, else the nearest folder,
from the current one upwards, holding ``config/tools/anagraphe.yml`` or ``anagraphe.yml``, else the
current folder. Without ``--config``, a command reads the one of both files that exists below the
root, and both existing is an error. A given ``--config`` is read from the current folder. The
former option ``--json`` of ``bindings show`` is retired.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from anagraphe.cli import app
from anagraphe.configuration import find_root, locate_config
from anagraphe.core.configuration import ConfigurationError

#: A valid configuration, which the command ``check`` reads with no issue.
VALID = "schema_version: 2\nreferences: {}\n"
#: A configuration that the command ``check`` rejects with a message naming the retired version.
RETIRED = "schema_version: 1\nreferences: {}\n"
NESTED = Path("config/tools/anagraphe.yml")


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


def test_lookup_reads_the_file_of_config_tools(tmp_path: Path) -> None:
    root = _repository(tmp_path, {NESTED: VALID})
    assert locate_config(root) == root / NESTED
    assert CliRunner().invoke(app, ["check", "--root", str(root)]).exit_code == 0


def test_lookup_reads_the_file_at_the_root(tmp_path: Path) -> None:
    root = _repository(tmp_path, {"anagraphe.yml": RETIRED})
    assert locate_config(root) == root / "anagraphe.yml"
    result = CliRunner().invoke(app, ["check", "--root", str(root)])
    assert result.exit_code == 2
    assert "schema_version 1 is retired" in result.output


def test_two_configuration_files_are_an_error_naming_both(tmp_path: Path) -> None:
    root = _repository(tmp_path, {NESTED: VALID, "anagraphe.yml": VALID})
    with pytest.raises(ConfigurationError, match="two configuration files"):
        locate_config(root)
    result = _runner().invoke(app, ["check", "--root", str(root)])
    assert result.exit_code == 2
    assert str(root / NESTED) in result.stderr
    assert str(root / "anagraphe.yml") in result.stderr


def test_given_config_is_read_from_the_current_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repository(tmp_path / "repository", {NESTED: RETIRED, "settings/other.yml": VALID})
    monkeypatch.chdir(root / "settings")
    assert locate_config(root, Path("other.yml")) == root / "settings/other.yml"
    result = CliRunner().invoke(app, ["check", "-r", str(root), "-c", "other.yml"])
    assert result.exit_code == 0, result.output
    # The same name read from the root would be absent: the root does not anchor --config.
    monkeypatch.chdir(tmp_path)
    assert CliRunner().invoke(app, ["check", "-r", str(root), "-c", "other.yml"]).exit_code == 2


def test_given_absolute_config_is_kept(tmp_path: Path) -> None:
    root = _repository(tmp_path, {"elsewhere/settings.yml": VALID})
    assert locate_config(root, root / "elsewhere/settings.yml") == root / "elsewhere/settings.yml"


def test_given_absent_config_is_an_error(tmp_path: Path) -> None:
    root = _repository(tmp_path, {NESTED: VALID})
    with pytest.raises(ConfigurationError, match="no configuration file at"):
        locate_config(root, root / "absent.yml")
    command = ["check", "--root", str(root), "--config", str(root / "absent.yml")]
    result = _runner().invoke(app, command)
    assert result.exit_code == 2
    assert "absent.yml" in result.stderr


def test_missing_configuration_names_both_places(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="config/tools/anagraphe.yml or anagraphe.yml"):
        locate_config(tmp_path)
    result = CliRunner().invoke(app, ["check", "--root", str(tmp_path)])
    assert result.exit_code == 2
    assert "configuration: no configuration file at config/tools/anagraphe.yml or" in result.output


def test_root_is_found_upwards_from_the_current_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repository(tmp_path / "repository", {NESTED: VALID, "notes/deep/a.md": "# A\n"})
    assert find_root(root / "notes/deep") == root.resolve()
    assert find_root(tmp_path) == tmp_path.resolve()
    monkeypatch.chdir(root / "notes/deep")
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
        "schema_version: 2\nbindings:\n  index: _index.md\n  roles:\n"
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
    assert "No such option: --json" in result.stderr
