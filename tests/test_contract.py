"""Run the conformance cases of the contract of the bindings, ``anagraphe:bindings@1``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from anagraphe.bindings import CONTRACT, BindingChecker, BindingResolver, Merge, Role
from anagraphe.configuration import load_config

CASES_FILE = Path(__file__).resolve().parent.parent / "specs" / "conformance" / "bindings.yml"
SUITE: dict[str, Any] = yaml.safe_load(CASES_FILE.read_text(encoding="utf-8"))
CASES = {case["id"]: case for case in SUITE["cases"]}


def test_cases_name_the_contract_of_the_package() -> None:
    assert SUITE["contract"] == CONTRACT


@pytest.mark.parametrize("case_id", sorted(CASES))
def test_case_conforms(tmp_path: Path, case_id: str) -> None:
    case = CASES[case_id]
    for rel, text in {**SUITE["files"], **case["files"]}.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    declared = {"_schema": "anagraphe:configuration@2", "bindings": SUITE["section"]}
    (tmp_path / "anagraphe.yml").write_text(yaml.safe_dump(declared), encoding="utf-8")
    config = load_config(tmp_path, tmp_path / "anagraphe.yml").bindings
    assert config is not None
    resolver = BindingResolver(tmp_path, config)
    for query in case["queries"]:
        binding = resolver.resolve(query["file"], Role(query["role"], Merge(query["merge"])))
        assert list(binding.values) == query["values"], query
        assert [f"{item.rel}#{item.pointer}" for item in binding.declarations] == query[
            "declarations"
        ], query
    issues = sorted(
        [issue.rel, issue.kind, issue.locus or issue.discriminator]
        for issue in BindingChecker(tmp_path, config).check().issues
    )
    assert issues == case["issues"]
