"""Behavioral tests of the lookup of the configuration file, and of the former option ``--json``.

Without ``--config``, a command reads ``config/tools/anagraphe.yml`` below the root, then
``anagraphe.yml``. A given ``--config`` names its file relative to the root, as before the lookup.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from anagraphe.cli import app
from anagraphe.configuration import locate_config
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


def test_lookup_prefers_the_file_of_config_tools(tmp_path: Path) -> None:
    root = _repository(tmp_path, {NESTED: VALID, "anagraphe.yml": RETIRED})
    assert locate_config(root) == root / NESTED
    assert CliRunner().invoke(app, ["check", "--root", str(root)]).exit_code == 0


def test_lookup_falls_back_on_the_file_at_the_root(tmp_path: Path) -> None:
    root = _repository(tmp_path, {"anagraphe.yml": RETIRED})
    assert locate_config(root) == root / "anagraphe.yml"
    result = CliRunner().invoke(app, ["check", "--root", str(root)])
    assert result.exit_code == 2
    assert "schema_version 1 is retired" in result.output


def test_given_config_is_read_relative_to_the_root(tmp_path: Path) -> None:
    root = _repository(tmp_path, {NESTED: RETIRED, "anagraphe.yml": VALID})
    assert locate_config(root, Path("anagraphe.yml")) == root / "anagraphe.yml"
    result = CliRunner().invoke(app, ["check", "--root", str(root), "--config", "anagraphe.yml"])
    assert result.exit_code == 0


def test_given_absolute_config_is_kept(tmp_path: Path) -> None:
    root = _repository(tmp_path, {"elsewhere/settings.yml": VALID})
    assert locate_config(root, root / "elsewhere/settings.yml") == root / "elsewhere/settings.yml"


def test_missing_configuration_names_both_places(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="config/tools/anagraphe.yml or anagraphe.yml"):
        locate_config(tmp_path)
    result = CliRunner().invoke(app, ["check", "--root", str(tmp_path)])
    assert result.exit_code == 2
    assert "configuration: no configuration file at config/tools/anagraphe.yml or" in result.output


#: A repository declaring one role, bound by the root index.
BOUND = {
    "anagraphe.yml": (
        "schema_version: 2\nbindings:\n  index: _index.md\n  roles:\n"
        "    onomasia.glossary: {key: glossary}\n"
    ),
    "_index.md": "---\nglossary: base\n---\n",
    "notes/a.md": "# A\n",
}


def test_json_is_a_hidden_alias_of_format_json(tmp_path: Path) -> None:
    root = _repository(tmp_path, BOUND)
    runner = _runner()
    command = ["bindings", "show", "notes/a.md", "--root", str(root)]
    current = runner.invoke(app, [*command, "--format", "json"])
    former = runner.invoke(app, [*command, "--json"])
    assert current.exit_code == former.exit_code == 0
    assert former.stdout == current.stdout
    assert json.loads(former.stdout)["bindings"]["onomasia.glossary"]["values"] == ["base"]
    assert "--json is deprecated; use --format json" in former.stderr
    assert "--json" not in runner.invoke(app, ["bindings", "show", "--help"]).stdout


def test_json_contradicting_format_text_is_rejected(tmp_path: Path) -> None:
    root = _repository(tmp_path, BOUND)
    command = ["bindings", "show", "notes/a.md", "--root", str(root), "--json", "--format", "text"]
    assert CliRunner().invoke(app, command).exit_code == 2
