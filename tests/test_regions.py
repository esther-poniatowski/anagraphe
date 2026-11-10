"""Tests of the regions that the Markdown syntaxes and the index units read from Merismos.

Each case states the reading of one construct: most were read otherwise by the former masking by
regular expressions, and the others guard a reading that the switch must keep. Every candidate must
locate the exact characters of its target, which a rewrite replaces.
"""

from __future__ import annotations

import pytest

from anagraphe.indexes.slots import prose_units
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
    "destination-in-angle-brackets": ("[a](<my file.md>)\n", "markdown", ["my file.md"]),
    "markdown-link-around-a-wiki-embed": (
        "[![[img.png]]](notes/my%20file.md)\n",
        "markdown",
        ["notes/my%20file.md"],
    ),
    "wiki-embed-inside-a-markdown-link": (
        "[![[img.png]]](notes/my%20file.md)\n",
        "wikilink",
        ["img.png"],
    ),
    "wikilink-holding-markdown-links": ("[[s](v.md), [o](w.md)]]\n", "markdown", []),
    "wikilink-runs-to-its-first-closing": (
        "[[s](v.md), [o](w.md)]]\n",
        "wikilink",
        ["s](v.md), [o](w.md)"],
    ),
    "escaped-separator-in-a-table": ("| x |\n| - |\n| [[a\\|b]] |\n", "wikilink", ["a"]),
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


INDEX_HEAD = "---\nrole: index\n---\n\n# Module\n\n"

UNITS = {
    "view-fenced-by-tildes": ("~~~base\nviews: []\n~~~\n", []),
    "longer-fence-holding-backticks": ("````\n```\nx\n```\n````\n", ["code block: ````"]),
    "code-block-in-a-callout": ("> [!WARNING] Kept\n> ```\n> x\n> ```\n", []),
    "code-block-in-a-list-item": (
        "- [Loose](loose.md)\n\n  ```\n  x\n  ```\n",
        ["list: - [Loose](loose.md)", "paragraph:   ```"],
    ),
}


@pytest.mark.parametrize("case", sorted(UNITS))
def test_prose_units_read_the_code_blocks_of_merismos(case: str) -> None:
    body, expected = UNITS[case]
    units = prose_units(INDEX_HEAD + body)
    assert [description for _line, description in units] == expected
