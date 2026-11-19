"""
The two distributions of Anagraphe: the command line pins the version of the read distribution,
and builds its objects through the composition of the read side.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import anagraphe_read
from anagraphe_read._repository import Composition
from anagraphe_read._resolution.provider import MemoryProvider

from anagraphe.configuration import load_config
from anagraphe.targets.registry.service import RegistryService
from anagraphe.targets.service import TargetChecker

from resolution_cases import consumer_repository

PROJECT = Path(__file__).resolve().parent.parent
READ_PROJECT = PROJECT / "packages" / "read-python" / "pyproject.toml"


def _metadata(path: Path) -> dict[str, object]:
    """Return the table ``project`` of a pyproject file."""
    project = tomllib.loads(path.read_text(encoding="utf-8"))["project"]
    assert isinstance(project, dict)
    return project


def test_the_command_line_pins_the_version_of_the_read_distribution() -> None:
    version = _metadata(READ_PROJECT)["version"]
    dependencies = _metadata(PROJECT / "pyproject.toml")["dependencies"]
    assert isinstance(dependencies, list)
    assert f"anagraphe-read=={version}" in dependencies
    assert anagraphe_read.__version__ == version


def test_the_read_distribution_depends_on_no_command_line_package() -> None:
    dependencies = _metadata(READ_PROJECT)["dependencies"]
    assert isinstance(dependencies, list)
    names = {item.split(" ")[0].split(">")[0].split("=")[0].lower() for item in dependencies}
    assert names == {"jsonschema", "kleisis", "pathspec", "pyyaml", "referencing"}


def test_the_checks_share_the_composition_of_the_read_side(tmp_path: Path) -> None:
    consumer_repository(tmp_path, "{repository: other-lab, id: bo}", {"records": {}})
    provider = MemoryProvider({})
    config = load_config(tmp_path, tmp_path / "anagraphe.yml", provider)
    reading = config.reading
    assert isinstance(reading, Composition) and reading.provider is provider
    checker = TargetChecker(reading)
    registry = RegistryService(reading)
    assert checker.resolver is reading.resolver
    assert checker.walk is reading.walk is registry.walk
    assert checker.identity is reading.identity is registry.identity
