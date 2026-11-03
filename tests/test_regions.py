"""Tests of the regions that the Markdown syntaxes read from Merismos.

Each case states the reading of a construct that the former masking by regular expressions read
otherwise, and every candidate must locate the exact characters of its target, which a rewrite
replaces.
"""

from __future__ import annotations

import pytest

from anagraphe.references.syntaxes import BUILT_IN

CASES = {
    "balanced-parentheses": (
        "[d](https://doi.org/10.1/0004(79)90)",
        "markdown",
        ["https://doi.org/10.1/0004(79)90"],
    ),
    "link-text-over-two-lines": (
        "See the [index\nspecification](b/target.md).\n",
        "markdown",
        ["b/target.md"],
    ),
    "badge-inside-link": (
        "[![x](badge.svg)](https://example.org)\n",
        "markdown",
        ["badge.svg", "https://example.org"],
    ),
    "brackets-open-no-wikilink": ("[[s](v.md), [o](w.md)]]\n", "markdown", ["v.md", "w.md"]),
    "brackets-hold-no-wikilink": ("[[s](v.md), [o](w.md)]]\n", "wikilink", []),
    "frontmatter-value": (
        '---\nindex: "[I](b/target.md)"\n---\nText.\n',
        "markdown",
        ["b/target.md"],
    ),
    "frontmatter-wikilink": ("---\nup: '[[b/target]]'\n---\n", "wikilink", ["b/target"]),
    "indented-code": ("Text.\n\n    [a](a.md)\n", "markdown", []),
    "display-math": ("$$\n[a](a.md)\n$$\n", "markdown", []),
    "math-inside-code-span": ("`notes/$x$`\n", "code", []),
    "path-in-code-span": ("Run `b/target.md` now.\n", "code", ["b/target.md"]),
}


@pytest.mark.parametrize("case", sorted(CASES))
def test_syntax_reads_the_regions_of_merismos(case: str) -> None:
    text, syntax, expected = CASES[case]
    candidates = list(BUILT_IN[syntax].find(text))
    assert [candidate.raw for candidate in candidates] == expected
    for candidate in candidates:
        assert text[candidate.start : candidate.start + len(candidate.raw)] == candidate.raw
