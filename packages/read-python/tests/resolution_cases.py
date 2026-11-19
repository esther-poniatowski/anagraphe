"""
The fixtures of the resolution shared by the tests: the conformance suite of
``specs/conformance/resolution.yml``, and a consumer repository whose record cites another
repository.

The tests of the read side and the tests of the command line both import this module, so that the
consumer of the cases is written once.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

from anagraphe_read._resolution.provider import Blob, MemoryProvider, Mode
from anagraphe_read._targets.resource import TARGET_REFERENCE

#: The root of the repository of Anagraphe, which holds the conformance cases.
PROJECT = Path(__file__).resolve().parents[3]
CASES_FILE = PROJECT / "specs" / "conformance" / "resolution.yml"
SUITE: dict[str, Any] = yaml.safe_load(CASES_FILE.read_text(encoding="utf-8"))
CASES = {case["id"]: case for case in SUITE["cases"]}
#: Two commits of 40 hexadecimal digits.
COMMIT = "1" * 40
OTHER_COMMIT = "2" * 40


def write(root: Path, files: Mapping[str, str]) -> None:
    """Write files below a root, creating their folders."""
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def blob(value: Any) -> Blob:
    """Return the entry of a case file: its text, or ``{link: path}`` for a symbolic link."""
    if isinstance(value, dict):
        return Blob(value["link"].encode("utf-8"), Mode.LINK)
    return Blob(value.encode("utf-8"))


def consumer_repository(root: Path, citing: str, sections: Mapping[str, Any] | None = None) -> None:
    """Write a consumer declaring other-lab at COMMIT, whose record ``cite.yml`` cites ``citing``.

    The configuration declares the sections ``targets``, ``repository`` and ``resolution``, and
    each section of ``sections`` besides them.
    """
    write(root, SUITE["consumer"]["files"])
    write(
        root,
        {
            "schemas/citing.schema.yml": (
                "properties:\n  _schema: {const: test:citing@1}\n  profile:\n"
                f"    $ref: {TARGET_REFERENCE}\n"
                "    x-target-contract: ['test:person']\n"
            ),
            "cite.yml": f"_schema: test:citing@1\nprofile: {citing}\n",
            "anagraphe.yml": yaml.safe_dump(
                {
                    "_schema": "anagraphe:configuration@3",
                    "targets": SUITE["consumer"]["section"],
                    "repository": {"id": "lab"},
                    "resolution": {
                        "repositories": {
                            "other-lab": {"commit": COMMIT, "remote": "https://h.org/o.git"}
                        }
                    },
                    **(sections or {}),
                }
            ),
        },
    )
    registry = root / "specs" / "schema-registry.yml"
    registry.write_text(
        registry.read_text(encoding="utf-8").replace(
            "schemas:\n", "schemas:\n  test:citing@1: schemas/citing.schema.yml\n"
        ),
        encoding="utf-8",
    )


def other_lab_state() -> MemoryProvider:
    """Return a provider holding the shared state of other-lab at COMMIT."""
    files = SUITE["states"]["other-lab"]
    return MemoryProvider({COMMIT: {rel: blob(value) for rel, value in files.items()}})
