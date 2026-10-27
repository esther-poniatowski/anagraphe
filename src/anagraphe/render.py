"""
Rendering of the entries of one block, as Markdown list items.

Each entry opens with the title of the member, linked by its path relative to the index. The
fields named by the block follow in a fixed order: the purpose after a colon, then the
citations, the status and the blockers inside parentheses, then one nested item per contribution. The rendering
is a pure function of the members and of the block, so a second run writes the same text.
"""

from __future__ import annotations

import posixpath
import urllib.parse
from pathlib import PurePosixPath
from typing import Any, Callable, Sequence

from anagraphe.notes import Note


def title_of(note: Note) -> str:
    """Return the title of a file: its first alias, else its file name without suffix.

    Examples
    --------
    >>> title_of(Note("notes/lemma.md"))
    'lemma'
    """
    if note.title:
        return note.title
    path = PurePosixPath(note.rel)
    return path.parent.name if path.name == "_index.md" and path.parent.name else path.stem


def link_to(note: Note, index_dir: str) -> str:
    """Return the path of a file relative to the folder of an index, encoded for a link.

    Examples
    --------
    >>> link_to(Note("contacts/Erin Grant.md"), "contacts")
    'Erin%20Grant.md'
    """
    return urllib.parse.quote(posixpath.relpath(note.rel, index_dir or "."), safe="/#^")


def render_entry(
    note: Note,
    index_dir: str,
    show: Sequence[str],
    title_of_target: Callable[[str], str],
) -> list[str]:
    """Return the lines of one entry, the nested contributions included.

    Examples
    --------
    >>> from anagraphe.fields import Citation
    >>> note = Note("notes/lemma.md", status="wip", title="Lemma", purpose="derives the bound",
    ...             cites=(Citation("uses-conclusions-from", "notes/main.md"),
    ...                    Citation("cites-as-evidence", "smith2020", external=True)),
    ...             contribution=("the gain decays",), blocked_by=("brief-draft",))
    >>> render_entry(note, "notes", ("purpose", "cites", "status", "blocked_by", "contribution"),
    ...              lambda rel: "Main result")[0]
    '- [Lemma](lemma.md): derives the bound (uses-conclusions-from Main result, cites-as-evidence @smith2020, wip, blocked by brief-draft)'
    >>> render_entry(Note("s.md", title="Panel", status="inbox",
    ...                   data={"presenter": ["Ann Lee", "Bo Wu"], "attended": False}),
    ...              "", ("presenter", "attended", "status"), str)
    ['- [Panel](s.md) (Ann Lee, Bo Wu, not attended, inbox)']
    """
    line = f"- [{title_of(note)}]({link_to(note, index_dir)})"
    if "purpose" in show and note.purpose:
        line += f": {note.purpose}"
    details: list[str] = []
    # The details follow the order of the shown fields; any other key is shown when scalar.
    for name in show:
        if name in ("purpose", "contribution"):
            continue
        if name == "cites":
            details.extend(
                (
                    f"{citation.relation} @{citation.target}"
                    if citation.external
                    else f"{citation.relation} {title_of_target(citation.target)}"
                )
                for citation in note.cites
            )
        elif name == "status":
            details.extend([note.status] if note.status else [])
        elif name == "blocked_by":
            details.extend(["blocked by " + ", ".join(note.blocked_by)] if note.blocked_by else [])
        else:
            details.extend(_display(name, note.data.get(name)))
    if details:
        line += f" ({', '.join(details)})"
    lines = [line]
    if "contribution" in show:
        lines.extend(f"  - {clause}" for clause in note.contribution)
    return lines


def render_body(
    notes: Sequence[Note],
    index_dir: str,
    show: Sequence[str],
    title_of_target: Callable[[str], str],
    depths: Sequence[int] | None = None,
) -> str:
    """Return the text written between the two markers of a block, one entry per member.

    A member of depth ``d`` is indented by ``d`` levels, beneath the member before it.
    """
    levels = depths if depths is not None else [0] * len(notes)
    lines = [
        "  " * level + line
        for note, level in zip(notes, levels)
        for line in render_entry(note, index_dir, show, title_of_target)
    ]
    return "".join(f"{line}\n" for line in lines)


def _display(name: str, value: Any) -> list[str]:
    """Return the displayed form of one key: a boolean by its name, a list joined by commas.

    >>> _display("attended", True), _display("attended", False), _display("day", None)
    (['attended'], ['not attended'], [])
    """
    if isinstance(value, bool):
        return [name if value else f"not {name}"]
    values = value if isinstance(value, list) else [value]
    shown = [
        item.isoformat() if hasattr(item, "isoformat") else str(item)
        for item in values
        if item not in (None, "") and not isinstance(item, (list, dict))
    ]
    return [", ".join(shown)] if shown else []
