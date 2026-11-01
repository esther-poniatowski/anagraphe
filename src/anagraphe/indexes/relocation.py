"""
Edits of the indexes owed by a move of files (ADR 0003).

A move changes the folder of its members, so four facts of the indexes change with it:

- the key ``index`` of each moved member names the index of its new folder;
- an explicit list of a group, ``members`` or ``sequence``, drops a member moved out of its folder;
- a build manifest under ``indexes.sequences`` follows a renamed member, and drops a member moved
  out of its folder;
- the generated regions of the old and the new parent indexes are written again.

The module computes the first three as edits of the texts before the move, and names the indexes
to write again. It receives the new path of each file as a callable, so it imports nothing of the
references.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable

import yaml

from anagraphe.core.links import link_target, value_link
from anagraphe.core.metadata import TOP, MetadataReader, Source, SourceKind
from anagraphe.core.structured import Edit, compose, node_at, remove_item, replace_scalar

#: The keys of a group holding an explicit list of links to its members.
LIST_KEYS = ("members", "sequence")


def parent_index(rel: str, entry_point: str) -> str | None:
    """Return the index listing a file: the index of its folder, or of the parent of an index.

    Examples
    --------
    >>> parent_index("m/a.md", "_index.md"), parent_index("m/_index.md", "_index.md")
    ('m/_index.md', '_index.md')
    >>> parent_index("_index.md", "_index.md") is None
    True
    """
    path = PurePosixPath(rel)
    if path.name == entry_point:
        if path.parent == PurePosixPath("."):
            return None
        folder = path.parent.parent
    else:
        folder = path.parent
    return (folder / entry_point).as_posix() if folder != PurePosixPath(".") else entry_point


def metadata_texts(source: Source, text: str) -> list[tuple[str, int, tuple[str, ...]]]:
    """Return the YAML texts holding the fields of a file, each with its offset and its key path.

    A frontmatter holds its fields in its block. A YAML document holds them at each declared key
    path, returned from the last one, since a later path overrides an earlier one. A JSON or TOML
    document is not edited in place, so it yields none.

    Examples
    --------
    >>> metadata_texts(Source(SourceKind.YAML, (".", "metadata")), "a: 1\\n")
    [('a: 1\\n', 0, ('metadata',)), ('a: 1\\n', 0, ())]
    """
    if source.kind is SourceKind.FRONTMATTER:
        if not text.startswith("---\n"):
            return []
        end = text.find("\n---", 3)
        return [(text[4 : end + 1], 4, ())] if end != -1 else []
    if source.kind is SourceKind.YAML:
        return [
            (text, 0, () if path == TOP else tuple(path.split("."))) for path in reversed(source.at)
        ]
    return []


def _line(node: yaml.Node, offset: int) -> int:
    """Return the line of a node in its file, a frontmatter opening on the second line."""
    return node.start_mark.line + (2 if offset else 1)


def _root(text: str) -> yaml.Node | None:
    """Return the node tree of a metadata text, None when it does not parse."""
    try:
        return compose(text)
    except yaml.YAMLError:
        return None


@dataclass(frozen=True)
class IndexEdit:
    """One edit of a file owed by a move, with a description of its effect."""

    holder: str
    line: int
    description: str
    edit: Edit


class IndexRelocator:
    """Compute the edits of the indexes owed by a move.

    ``new_path`` and ``old_path`` map a path before the move to its path after it, and back.
    ``exists_after`` answers whether a path names a file after the move, ``title`` returns the
    title of a file named by its path before the move, and ``source_of`` the metadata source of a
    file, where its key ``index`` and its groups are written.
    """

    def __init__(
        self,
        entry_point: str,
        new_path: Callable[[str], str],
        old_path: Callable[[str], str],
        exists_after: Callable[[str], bool],
        title: Callable[[str], str | None],
        source_of: Callable[[str], Source] = MetadataReader(Path(".")).source_of,
    ) -> None:
        self.entry_point = entry_point
        self.new_path = new_path
        self.old_path = old_path
        self.exists_after = exists_after
        self.title = title
        self.source_of = source_of

    def _node(self, holder: str, text: str, key: str) -> tuple[yaml.Node, str, int] | None:
        """Return the node of a key of the metadata of a file, with its text and its offset."""
        for body, offset, keys in metadata_texts(self.source_of(holder), text):
            node = node_at(_root(body), [*keys, key])
            if node is not None:
                return node, body, offset
        return None

    def edits(self, holder: str, text: str) -> list[IndexEdit]:
        """Return the edits of one file: its key ``index`` if it moves, its lists if it is an index."""
        found: list[IndexEdit] = []
        if self.new_path(holder) != holder:
            found.extend(self._index_key(holder, text))
        if PurePosixPath(holder).name == self.entry_point:
            found.extend(self._lists(holder, text))
        return found

    def _index_key(self, holder: str, text: str) -> list[IndexEdit]:
        """Return the edit pointing the key ``index`` of a moved file to its new parent index."""
        found = self._node(holder, text, "index")
        if found is None:
            return []
        node, _, offset = found
        if not isinstance(node, yaml.ScalarNode) or value_link(node.value) is None:
            return []
        expected = parent_index(self.new_path(holder), self.entry_point)
        current = link_target(node.value)
        if expected is None or current is None or self.new_path(current) == expected:
            return []
        if not self.exists_after(expected):
            return []
        label = self.title(self.old_path(expected)) or posixpath.basename(expected)
        edit = replace_scalar(node, f"[{label}]({expected})", offset)
        return [IndexEdit(holder, _line(node, offset), f"index names {expected}", edit)]

    def _lists(self, holder: str, text: str) -> list[IndexEdit]:
        """Return the edits dropping, from the lists of an index, each member moved out of its folder."""
        located = self._node(holder, text, "groups")
        if located is None:
            return []
        groups, body, offset = located
        if not isinstance(groups, yaml.SequenceNode):
            return []
        folder = posixpath.dirname(self.new_path(holder))
        found: list[IndexEdit] = []
        for group in groups.value:
            for key in LIST_KEYS:
                items = node_at(group, [key])
                if not isinstance(items, yaml.SequenceNode):
                    continue
                for item in items.value:
                    target = link_target(item.value) if isinstance(item, yaml.ScalarNode) else None
                    if target is None or self.new_path(target) == target:
                        continue
                    moved = self.new_path(target)
                    if posixpath.dirname(moved) == folder:
                        continue
                    found.append(
                        IndexEdit(
                            holder,
                            _line(item, offset),
                            f"{key} drops {target}, moved to {moved}",
                            remove_item(body, items, item, offset),
                        )
                    )
        return found

    def manifests(self, config_rel: str, text: str) -> list[IndexEdit]:
        """Return the edits of the build manifests of ``indexes.sequences`` in the configuration."""
        sequences = node_at(_root(text), ["indexes", "sequences"])
        if not isinstance(sequences, yaml.MappingNode):
            return []
        found: list[IndexEdit] = []
        for key, entries in sequences.value:
            if not isinstance(key, yaml.ScalarNode) or not isinstance(entries, yaml.SequenceNode):
                continue
            folder = key.value.rstrip("/")
            new_folder = self.new_path(folder)
            if new_folder != folder:
                found.append(
                    IndexEdit(
                        config_rel,
                        key.start_mark.line + 1,
                        f"sequences.{folder} becomes " f"sequences.{new_folder}",
                        replace_scalar(key, new_folder),
                    )
                )
            for entry in entries.value:
                if not isinstance(entry, yaml.ScalarNode):
                    continue
                member = posixpath.join(folder, entry.value) if folder else entry.value
                moved = self.new_path(member)
                if moved == member or moved == posixpath.join(new_folder, entry.value):
                    continue
                line = entry.start_mark.line + 1
                if posixpath.dirname(moved) == new_folder:
                    relative = posixpath.relpath(moved, new_folder or ".")
                    found.append(
                        IndexEdit(
                            config_rel,
                            line,
                            f"sequences.{folder} names {relative}",
                            replace_scalar(entry, relative),
                        )
                    )
                else:
                    found.append(
                        IndexEdit(
                            config_rel,
                            line,
                            f"sequences.{folder} drops {entry.value}",
                            remove_item(text, entries, entry),
                        )
                    )
        return found

    def affected(self, moved: Iterable[str]) -> list[str]:
        """Return the indexes, after the move, whose generated regions the move changes."""
        indexes: list[str] = []
        for old in moved:
            new = self.new_path(old)
            for candidate in (
                parent_index(old, self.entry_point),
                parent_index(new, self.entry_point),
                new if PurePosixPath(new).name == self.entry_point else None,
            ):
                if candidate and self.exists_after(candidate) and candidate not in indexes:
                    indexes.append(candidate)
        return sorted(indexes)
