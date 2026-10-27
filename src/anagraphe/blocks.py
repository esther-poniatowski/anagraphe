"""
Generated regions of an index: their markers, and the rewriting of their body.

A region opens with ``<!-- index <parameter> -->`` and closes with ``<!-- /index -->``. Two regions
exist, as the decision on index slots fixes:

- ``groups`` renders the groups that the index declares in its frontmatter, each under its heading
  and its description. The mode, the sort key, the strategy and the displayed fields of each group
  belong to its declaration;
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
#: The fields that a group may display beside each title, in their display order.
DISPLAY_FIELDS = ("purpose", "cites", "status", "blocked_by", "contribution")
#: The parameters admitted by an opening marker.
PARAMETERS = frozenset({"control", "groups", "show"})
#: The sort keys handled apart from the keys of the members, the first being the default.
SORT_KEYS = ("title", "file", "date")
#: The ordering modes that a group may name with ``mode``.
MODES = ("construction", "registry", "sequence")


@dataclass(frozen=True)
class Block:
    """One generated region of an index, or one group that the region of groups renders."""

    #: The group listed, ``*`` for the members declaring none, or None for a region.
    group: str | None
    #: The fields displayed beside each title, in display order.
    show: tuple[str, ...]
    #: The strategy tokens of a group, validated against the vocabulary by the caller.
    strategy: tuple[str, ...]
    #: The current text between the two markers.
    body: str
    #: The line of the opening marker, counted from 1.
    line: int
    #: The key of the order wherever the mode leaves a choice, among ``SORT_KEYS``.
    sort: str = SORT_KEYS[0]
    #: The declared ordering mode, among ``MODES``, or None for the default mode of the index.
    mode: str | None = None
    #: The key naming the parent of each member, whose children are rendered beneath it.
    nest: str | None = None
    #: The heading under which a group stands; groups without a heading share the one above them.
    section: int = 0
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
                group=None,
                show=tuple(field for field in DISPLAY_FIELDS if field in shown),
                strategy=(),
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
