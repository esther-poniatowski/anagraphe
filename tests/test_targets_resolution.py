"""
The check of the targets into another repository, with a provider of the selected states.

The consumer and the state of ``other-lab`` are the fixtures of the read side, which follow the
conformance cases of ``specs/conformance/resolution.yml``. The check reports each finding of the
record resolver at the level of its kind, located at the citing field.
"""

from __future__ import annotations

from pathlib import Path

from anagraphe_read._resolution.provider import EmptyProvider, MemoryProvider

from anagraphe.configuration import load_config
from anagraphe.targets.service import TargetChecker

from resolution_cases import COMMIT, consumer_repository, other_lab_state


def _issues(root: Path, provider: MemoryProvider | EmptyProvider) -> list[tuple[str, str, str]]:
    """Check the targets of a repository with a provider, and return its sorted issues."""
    checker = TargetChecker(load_config(root, root / "anagraphe.yml", provider).reading)
    return sorted((issue.kind, issue.level, issue.locus) for issue in checker.check().issues)


def test_the_check_reads_a_target_into_another_repository(tmp_path: Path) -> None:
    consumer_repository(tmp_path, "{repository: other-lab, id: bo}")
    assert _issues(tmp_path, other_lab_state()) == []


def test_the_check_reports_each_finding_of_the_resolver(tmp_path: Path) -> None:
    consumer_repository(tmp_path, "{repository: old-lab, id: arg.one}")
    assert _issues(tmp_path, other_lab_state()) == [
        ("renamed-repository", "warning", "/profile"),
        ("target-contract-mismatch", "error", "/profile"),
    ]


def test_without_a_provider_the_check_warns_of_each_unread_state(tmp_path: Path) -> None:
    consumer_repository(tmp_path, "{repository: other-lab, id: bo}")
    assert _issues(tmp_path, EmptyProvider()) == [
        ("unreadable-target-state", "warning", "/profile")
    ]


def _state_with_configuration_in_settings() -> MemoryProvider:
    """Return the state of other-lab at COMMIT, its configuration moved to
    ``settings/anagraphe.yml``, a place that no rule of Hodegos admits."""
    blobs = dict(other_lab_state().states[COMMIT])
    blobs["settings/anagraphe.yml"] = blobs.pop("anagraphe.yml")
    return MemoryProvider({COMMIT: blobs})


def _declaring(config: str | None) -> dict[str, object]:
    """Return the section ``resolution`` declaring other-lab at COMMIT, with the key ``config``
    when ``config`` is not None."""
    entry = {"commit": COMMIT, "remote": "https://h.org/o.git"}
    if config is not None:
        entry["config"] = config
    return {"resolution": {"repositories": {"other-lab": entry}}}


def test_the_key_config_names_the_configuration_of_a_state(tmp_path: Path) -> None:
    consumer_repository(
        tmp_path, "{repository: other-lab, id: bo}", _declaring("settings/anagraphe.yml")
    )
    assert _issues(tmp_path, _state_with_configuration_in_settings()) == []


def test_without_the_key_config_the_accepted_places_are_searched(tmp_path: Path) -> None:
    consumer_repository(tmp_path, "{repository: other-lab, id: bo}", _declaring(None))
    assert _issues(tmp_path, _state_with_configuration_in_settings()) == [
        ("invalid-target-repository", "error", "/profile")
    ]


def test_the_default_place_names_the_configuration_of_a_state(tmp_path: Path) -> None:
    resolution = _declaring(None)["resolution"]
    assert isinstance(resolution, dict)
    resolution["config"] = "settings/anagraphe.yml"
    consumer_repository(tmp_path, "{repository: other-lab, id: bo}", {"resolution": resolution})
    assert _issues(tmp_path, _state_with_configuration_in_settings()) == []
