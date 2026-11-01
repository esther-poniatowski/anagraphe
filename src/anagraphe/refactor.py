"""
Moves of files and folders that preserve every pointer and keep the indexes consistent (ADR 0003).

A move runs in three steps:

1. **plan**: the new path of each moved file, the rewrite of each pointer to a moved file, found by
   :mod:`anagraphe.references.rewrite`, and the edits of the indexes, computed by
   :mod:`anagraphe.indexes.relocation`;
2. **apply**: the edits and the rename form one transaction, and a failed rename restores every
   edited file;
3. **settle**: the generated regions of the affected indexes are written again, the moved and edited
   files are checked, and each old path left in a file, such as an excluded one, is reported.

This module composes both capabilities, so that neither of them imports the other.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Protocol

from anagraphe.configuration import RepositoryConfig
from anagraphe.core.exclusions import Exemptions
from anagraphe.core.files import TargetError, is_text, walk, write_atomically
from anagraphe.core.issues import Report
from anagraphe.core.metadata import MetadataReader
from anagraphe.core.structured import apply_edits
from anagraphe.indexes.configuration import load_vocabulary
from anagraphe.indexes.relocation import IndexEdit, IndexRelocator
from anagraphe.indexes.service import RunResult, run
from anagraphe.references.configuration import ReferenceConfig
from anagraphe.references.resolution import FileIndex
from anagraphe.references.rewrite import PointerEdit, PointerRewriter, Relocation
from anagraphe.references.service import ReferenceChecker


class Mover(Protocol):
    """Rename one file or one folder of a repository."""

    def move(self, root: Path, old: str, new: str) -> None:
        """Rename a repository-relative path, creating the parent folders of the new path."""
        raise NotImplementedError


class GitMover:
    """Rename with ``git mv`` a path that Git tracks, and with the file system any other path."""

    def move(self, root: Path, old: str, new: str) -> None:
        (root / new).parent.mkdir(parents=True, exist_ok=True)
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", old],
            cwd=root,
            capture_output=True,
            check=False,
        )
        if tracked.returncode == 0:
            subprocess.run(["git", "mv", "--", old, new], cwd=root, capture_output=True, check=True)
        else:
            os.rename(root / old, root / new)


@dataclass(frozen=True)
class MovePlan:
    """The rename, and every edit that a move owes, computed before any file changes."""

    old: str
    new: str
    relocation: Relocation
    #: The new text of each edited file, keyed by its path before the move.
    texts: dict[str, str] = field(default_factory=dict)
    pointer_edits: tuple[PointerEdit, ...] = ()
    index_edits: tuple[IndexEdit, ...] = ()
    #: The indexes whose generated regions the move changes, by their path after the move.
    affected_indexes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Residue:
    """One old path left in a file after the move."""

    rel: str
    line: int
    old: str


@dataclass(frozen=True)
class MoveResult:
    """The outcome of an applied move."""

    plan: MovePlan
    regions: RunResult | None
    check: Report | None
    residues: tuple[Residue, ...]


def _relative(root: Path, given: str) -> str:
    """Return a target of the command as a repository-relative path, or raise."""
    path = (Path(given) if Path(given).is_absolute() else root / given).resolve()
    if path != root and root not in path.parents:
        raise TargetError(f"target lies outside the repository: {given}")
    return path.relative_to(root).as_posix()


class MoveService:
    """Plan and apply the moves of one repository."""

    def __init__(
        self, root: Path, config: RepositoryConfig, config_rel: str, mover: Mover | None = None
    ) -> None:
        self.root = root.resolve()
        self.config = config
        self.config_rel = config_rel
        self.references = config.references or ReferenceConfig()
        self.mover = mover or GitMover()

    def plan(self, old_given: str, new_given: str) -> MovePlan:
        """Return the plan of moving one file or folder to a new path, changing no file."""
        old, new = _relative(self.root, old_given), _relative(self.root, new_given)
        source, destination = self.root / old, self.root / new
        if not old or not source.exists():
            raise TargetError(f"target does not exist: {old_given}")
        if destination.exists():
            raise TargetError(f"destination already exists: {new_given}")
        if source.is_dir() and (new == old or new.startswith(f"{old}/")):
            raise TargetError(f"a folder cannot move into itself: {new_given}")
        every = list(walk(self.root, self.root, Exemptions()))
        if source.is_dir():
            relocation = Relocation(
                {rel: new + rel[len(old) :] for rel in every if rel.startswith(f"{old}/")},
                {old: new},
            )
        else:
            relocation = Relocation({old: new})
        after = {relocation.new_path(rel) for rel in every}
        # Existence is answered from the walk, since a token may be no valid file name at all.
        present = set(every) | {
            parent.as_posix() for rel in every for parent in PurePosixPath(rel).parents
        }
        rewriter = PointerRewriter(
            relocation,
            present.__contains__,
            self.references.syntaxes,
            FileIndex(every),
            FileIndex(after),
            self.references.conventions.bases(),
        )
        relocator = self._relocator(relocation, after)
        texts: dict[str, str] = {}
        pointers: list[PointerEdit] = []
        indexes: list[IndexEdit] = []
        for holder, indexed, referenced in self._holders():
            text = (self.root / holder).read_text(encoding="utf-8")
            owed: list[IndexEdit] = []
            if relocator is not None and indexed:
                owed.extend(relocator.edits(holder, text))
            if relocator is not None and holder == self.config_rel:
                owed.extend(relocator.manifests(holder, text))
            rewritten: list[PointerEdit] = []
            if referenced:
                rewritten = rewriter.edits(holder, text, tuple(edit.edit for edit in owed))
            if owed or rewritten:
                texts[holder] = apply_edits(
                    text, [edit.edit for edit in owed] + [edit.edit for edit in rewritten]
                )
                indexes.extend(owed)
                pointers.extend(rewritten)
        affected = relocator.affected(relocation.files) if relocator is not None else []
        return MovePlan(
            old, new, relocation, texts, tuple(pointers), tuple(indexes), tuple(affected)
        )

    def apply(self, plan: MovePlan) -> MoveResult:
        """Apply a plan, then write the regions of the affected indexes and check the result."""
        originals = {rel: (self.root / rel).read_text(encoding="utf-8") for rel in plan.texts}
        write_atomically(self.root, plan.texts)
        try:
            self.mover.move(self.root, plan.old, plan.new)
        except (OSError, subprocess.CalledProcessError):
            write_atomically(self.root, originals)
            raise
        regions = None
        if self.config.indexes is not None and plan.affected_indexes:
            regions = run(
                self.root,
                self.config.indexes,
                "write",
                tuple(Path(rel) for rel in plan.affected_indexes),
                strict=False,
            )
        touched = sorted({plan.relocation.new_path(rel) for rel in plan.texts} | {plan.new})
        check = None
        if self.config.references is not None:
            check = ReferenceChecker(self.root, self.config.references).check(
                tuple(Path(rel) for rel in touched), strict=False
            )
        return MoveResult(plan, regions, check, tuple(self._residues(plan)))

    def _relocator(self, relocation: Relocation, after: set[str]) -> IndexRelocator | None:
        """Return the relocator of the indexes, None when the configuration declares no indexes."""
        if self.config.indexes is None:
            return None
        entry_point = str(load_vocabulary(self.config.indexes.vocabulary)["schema"]["entry_point"])
        inverse = {new: old for old, new in relocation.files.items()}

        metadata = self.config.metadata or MetadataReader(self.root)

        def title(rel: str) -> str | None:
            aliases = metadata(rel).get("aliases")
            first = aliases[0] if isinstance(aliases, list) and aliases else aliases
            return str(first) if isinstance(first, str) else None

        return IndexRelocator(
            entry_point,
            relocation.new_path,
            lambda rel: inverse.get(rel, rel),
            after.__contains__,
            title,
            metadata.source_of,
        )

    def _holders(self) -> list[tuple[str, bool, bool]]:
        """Return each text file, whether the indexes read it, and whether its pointers are read.

        An excluded file is neither rewritten nor edited, so a move reports its old paths instead.
        """
        indexes = self.config.indexes.exemptions if self.config.indexes is not None else None
        holders: list[tuple[str, bool, bool]] = []
        for rel in walk(self.root, self.root, Exemptions()):
            path = PurePosixPath(rel)
            indexed = indexes is not None and not indexes.contains(path)
            referenced = not self.references.exemptions.contains(path)
            if (indexed or referenced) and is_text(self.root / rel):
                holders.append((rel, indexed, referenced))
        return holders

    def _residues(self, plan: MovePlan) -> list[Residue]:
        """Return each occurrence of an old path left in a text file after the move."""
        # A folder is searched as a prefix, so that each file below it is found once.
        tail = "/" if plan.relocation.folders else r"(?![\w-])"
        pattern = re.compile(rf"(?<![\w./-]){re.escape(plan.old)}{tail}")
        found: list[Residue] = []
        for rel in walk(self.root, self.root, Exemptions()):
            path = self.root / rel
            if not is_text(path):
                continue
            text = path.read_text(encoding="utf-8")
            found.extend(
                Residue(rel, text.count("\n", 0, match.start()) + 1, plan.old)
                for match in pattern.finditer(text)
            )
        return found
