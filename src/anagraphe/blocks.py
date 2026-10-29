"""
Generated regions of an index: their markers, and the rewriting of their body.

A region opens with ``<!-- index <parameter> -->`` and closes with ``<!-- /index -->``. Two regions
exist, as the decision on index slots fixes:

- ``groups`` renders the groups that the index declares in its frontmatter, each under its heading
  and its description. The membership, the mode, the order, the nesting and the displayed fields
  of each group belong to its declaration;
- ``control`` lists the control files present in the folder: the files that the type of the index
  expects, then the files of a role that the index never lists as entries. It admits
  ``show=<field>,<field>``, naming the fields displayed beside each title.

Everything outside the markers belongs to the author, and the generator rewrites only the lines
between them.

Examples
--------
>>> text = "Intro\\n<!-- index groups -->\\n- old\\n<!-- /index -->\\nEnd\\n"
>>> [block.region for block in parse_blocks(text)]
[True]
>>> replace_bodies(text, ["- new\\n"])
'Intro\\n<!-- index groups -->\\n- new\\n<!-- /index -->\\nEnd\\n'
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: An opening marker, its parameters, the body, and the closing marker.
BLOCK = re.compile(
    r"(?P<open><!-- index(?P<params>(?: [^\s>]+)*) -->\n)(?P<body>.*?)"
    r"(?P<close><!-- /index -->)",
    re.DOTALL,
)
#: The fields that the control block may display beside each title, in their display order.
DISPLAY_FIELDS = ("purpose", "status", "blocked_by", "contribution")
#: The parameters admitted by an opening marker.
PARAMETERS = frozenset({"control", "groups", "show"})


@dataclass(frozen=True)
class Block:
    """One generated region of an index, between its two markers."""

    #: The fields displayed beside each title by the control block, in display order.
    show: tuple[str, ...]
    #: The current text between the two markers.
    body: str
    #: The line of the opening marker, counted from 1.
    line: int
    #: Whether the region lists the control files of the folder.
    control: bool = False
    #: Whether the region renders the groups declared in the frontmatter of the index.
    region: bool = False
    #: The problems of the opening marker itself.
    problems: tuple[str, ...] = ()


def parse_blocks(text: str) -> list[Block]:
    """Return the regions of an index text, in their order of appearance.

    Examples
    --------
    >>> block = parse_blocks("<!-- index control show=status,purpose colour=red -->\\n<!-- /index -->")[0]
    >>> block.show, block.problems
    (('purpose', 'status'), ('unknown parameter: colour',))
    >>> parse_blocks("<!-- index group=core -->\\n<!-- /index -->")[0].problems
    ('unknown parameter: group', 'a marker opens either the region of groups or the control block')
    """
    blocks = []
    for match in BLOCK.finditer(text):
        values: dict[str, str] = {}
        problems: list[str] = []
        for pair in match["params"].split():
            key, _, value = pair.partition("=")
            if key not in PARAMETERS:
                problems.append(f"unknown parameter: {key}")
            else:
                values[key] = value
        if ("groups" in values) == ("control" in values):
            problems.append("a marker opens either the region of groups or the control block")
        if "groups" in values and "show" in values:
            problems.append("the region of groups takes its fields from the declared groups")
        shown = [field for field in values.get("show", "").split(",") if field]
        problems.extend(
            f"unknown field in show: {field}" for field in shown if field not in DISPLAY_FIELDS
        )
        blocks.append(
            Block(
                show=tuple(field for field in DISPLAY_FIELDS if field in shown),
                body=match["body"],
                line=text.count("\n", 0, match.start()) + 1,
                control="control" in values,
                region="groups" in values,
                problems=tuple(problems),
            )
        )
    return blocks


def replace_bodies(text: str, bodies: list[str]) -> str:
    """Return the text with the body of each region replaced, in order of appearance."""
    replacements = iter(bodies)
    return BLOCK.sub(lambda match: f"{match['open']}{next(replacements)}{match['close']}", text)
