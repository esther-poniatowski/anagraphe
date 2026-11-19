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

from resolution_cases import consumer_repository, other_lab_state


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
