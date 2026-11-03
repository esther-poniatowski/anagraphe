"""
The regions of a Markdown file, read from Merismos, the span library.

Merismos segments a text into typed regions with exact offsets, under its Obsidian syntax. Both
capabilities read the regions through this module, so that the constructs of a file are located
once and alike: the references read its link destinations and its code spans, and the indexes read
its fenced code blocks.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Iterator

from merismos import Segmentation, Span, inline_regions, segment

#: The source type under which Merismos segments a Markdown file.
MARKDOWN_SOURCE = "markdown"
#: The kinds of Merismos read by Anagraphe.
FRONTMATTER_KIND, LINK_KIND, DESTINATION_KIND, CODE_KIND, FENCED_KIND, QUOTATION_KIND = (
    "frontmatter",
    "link",
    "link-destination",
    "inline-code",
    "fenced-code",
    "quotation",
)


@lru_cache(maxsize=8)
def segmentation_of(text: str) -> Segmentation:
    """Return the segmentation of a Markdown text, cached since several readers share each file."""
    return segment(text, MARKDOWN_SOURCE)


@dataclass(frozen=True)
class MarkdownRegion:
    """A region of a Markdown file read by the references: a link destination or a code span."""

    #: The kind of Merismos of the region.
    kind: str
    #: The offset of the content of the region in the file.
    start: int
    #: The content of the region: the destination, or the text between the backticks.
    text: str
    #: The syntax of Merismos of the link holding a destination, ``markdown`` or ``wiki``; None for a
    #: code span.
    link: str | None = None


def _regions_of(segmentation: Segmentation) -> Iterator[MarkdownRegion]:
    """Yield the link destinations and the code spans of a segmentation, each destination with
    the syntax of its link, which precedes it in the order of the segmentation."""
    link: str | None = None
    for region in segmentation.select([LINK_KIND, DESTINATION_KIND, CODE_KIND]):
        if region.kind == LINK_KIND:
            link = str(region.attributes.get("syntax"))
        elif region.content is not None:
            yield MarkdownRegion(
                region.kind,
                region.content.start,
                segmentation.text(region.content),
                link if region.kind == DESTINATION_KIND else None,
            )


@lru_cache(maxsize=8)
def markdown_regions(text: str) -> tuple[MarkdownRegion, ...]:
    """Return the link destinations and the code spans of a Markdown text, in the order of the text.

    Merismos segments the text, so a link inside a code block, a code span or mathematics is
    found by no syntax. Merismos reads the frontmatter as one opaque region, so each of its lines
    is scanned as a paragraph of its own, and a link written in a value of the frontmatter is
    found as in the body. The result is cached, since three syntaxes read each file.

    Examples
    --------
    >>> [(region.text, region.link) for region in
    ...  markdown_regions("[a](a.md)\\n```\\n[x](x.md)\\n```\\n`b.md` $[[c]]$ [[d]]\\n")]
    [('a.md', 'markdown'), ('b.md', None), ('d', 'wiki')]
    """
    segmentation = segmentation_of(text)
    regions = list(_regions_of(segmentation))
    for frontmatter in segmentation.select([FRONTMATTER_KIND]):
        if frontmatter.content is None:
            continue
        position = frontmatter.content.start
        for line in text[frontmatter.content.start : frontmatter.content.end].splitlines(True):
            stripped = line.rstrip("\r\n")
            if stripped:
                lines = [Span(position, position + len(stripped))]
                regions.extend(_regions_of(inline_regions(text, lines)))
            position += len(line)
    return tuple(sorted(regions, key=lambda region: region.start))


@dataclass(frozen=True)
class FencedBlock:
    """A fenced code block, by its lines counted from 0 in the text split at each newline."""

    #: The line of the opening fence.
    first: int
    #: The last line of the block: its closing fence, or the last line of an unclosed block.
    last: int
    #: The first word of the info string, empty when the fence names no language.
    language: str
    #: Whether the block lies inside a quotation, such as the body of a callout.
    quoted: bool = False


def fenced_blocks(text: str) -> tuple[FencedBlock, ...]:
    """Return the fenced code blocks of a Markdown text, in the order of the text.

    Examples
    --------
    >>> text = "Text.\\n\\n~~~base\\nviews: []\\n~~~\\n> ```\\n> x\\n> ```\\n"
    >>> [(block.first, block.last, block.language, block.quoted) for block in fenced_blocks(text)]
    [(2, 4, 'base', False), (5, 7, '', True)]
    """
    starts = [0]
    for number, character in enumerate(text):
        if character == "\n":
            starts.append(number + 1)
    segmentation = segmentation_of(text)
    quotations = segmentation.select([QUOTATION_KIND])
    blocks: list[FencedBlock] = []
    for region in segmentation.select([FENCED_KIND]):
        words = str(region.attributes.get("info") or "").split()
        blocks.append(
            FencedBlock(
                _line(starts, region.range.start),
                _line(starts, max(region.range.start, region.range.end - 1)),
                words[0] if words else "",
                any(
                    quotation.range.start <= region.range.start < quotation.range.end
                    for quotation in quotations
                ),
            )
        )
    return tuple(blocks)


def _line(starts: list[int], offset: int) -> int:
    """Return the line, counted from 0, holding an offset."""
    low, high = 0, len(starts) - 1
    while low < high:
        middle = (low + high + 1) // 2
        if starts[middle] <= offset:
            low = middle
        else:
            high = middle - 1
    return low
