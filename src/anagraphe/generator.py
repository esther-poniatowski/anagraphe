"""
Generation and checking of the entries of one index.

For an index holding at least one block, the generator collects the members of its folder, assigns
each member to the block of its group, orders the members of each block under the ordering mode of
the block, renders the entries, and reports the issues that the decisions on generated index
entries, on index types and on typed citations list. An index holding no block is left untouched, so the checks grow folder by
folder as the indexes migrate, except in the areas declared as generated: there, an index without
the region of its groups is reported.

Violations gate a commit, whereas warnings report a decision still owed by the author, such as a
citation whose evidence is missing from the body.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Protocol, Sequence

from anagraphe.blocks import MODES, SORT_KEYS, Block, parse_blocks, replace_bodies
from anagraphe.fields import End, FieldRules, Grade
from anagraphe.notes import Note, NoteReader, normalize, value_link
from anagraphe.order import Ordering, order_members, order_registry, order_sequence
from anagraphe.render import render_body, title_of
from anagraphe.slots import GroupSpec, prose_units
from anagraphe.types import IndexType, IndexTypes

#: Emphasis markers removed from an H1 heading before it is compared with the first alias.
EMPHASIS = re.compile(r"[*_`]")


class SequenceProvider(Protocol):
    """Resolve the declared member order of a repository folder."""

    def __call__(self, folder: Path) -> Sequence[str] | None:
        """Return the ordered member paths, or ``None`` when no order is declared."""
        ...


@dataclass(frozen=True)
class Issue:
    """One issue of an index or of one of its members, located at a file and a line."""

    rel: str
    line: int
    kind: str
    detail: str
    #: Whether the issue gates a commit. A non-blocking issue is reported as a warning.
    blocking: bool = True


@dataclass(frozen=True)
class Settings:
    """The repository declarations read by the generator."""

    entry_point: str
    #: Roles that an index lists in its control block, never as entries, such as a worklog.
    unlisted_roles: frozenset[str]
    #: Whether a repository-relative path is excluded from every check.
    is_exempt: Callable[[Path], bool]
    #: Types of index, which supply the default mode and the expected files of an index.
    types: IndexTypes
    #: Top-level areas whose every index must hold the region of its groups.
    generated_areas: frozenset[str] = frozenset()
    #: Indexes absent from the last commit, which must hold the region of their groups in any area.
    new_indexes: frozenset[str] = frozenset()

    @classmethod
    def from_vocabulary(
        cls,
        raw: Mapping[str, Any],
        is_exempt: Callable[[Path], bool],
        types: IndexTypes,
    ) -> Settings:
        """Read the settings from the parsed vocabulary and the types of index."""
        schema = raw["schema"]
        return cls(
            entry_point=str(schema["entry_point"]),
            unlisted_roles=frozenset(
                name
                for name, spec in (raw.get("roles") or {}).items()
                if spec.get("listed", True) is False
            ),
            is_exempt=is_exempt,
            types=types,
            generated_areas=frozenset(schema.get("generated_index_areas") or ()),
        )


@dataclass
class Result:
    """The text of an index after generation, and the issues found while generating it."""

    text: str
    changed: bool
    issues: list[Issue] = field(default_factory=list)


class IndexGenerator:
    """Generate and check the indexes of one repository.

    Parameters
    ----------
    root
        Repository root.
    settings
        Repository declarations read by the generator.
    rules
        Rules of the entry fields.
    tasks
        Whether each declared task is closed, by identifier.
    """

    def __init__(
        self,
        root: Path,
        settings: Settings,
        rules: FieldRules,
        tasks: Mapping[str, bool],
        sequence_provider: SequenceProvider | None = None,
    ) -> None:
        self.root = root
        self.settings = settings
        self.rules = rules
        self.tasks = tasks
        self.sequence_provider = sequence_provider or (lambda _folder: None)
        self.reader = NoteReader(root, rules)

    def members(self, index_rel: str) -> list[Note]:
        """Return the files that an index lists: notes, child indexes and specifications."""
        folder = self.root / PurePosixPath(index_rel).parent
        candidates: list[str] = []
        for path in sorted(folder.iterdir(), key=lambda item: item.name):
            rel = path.relative_to(self.root)
            if self.settings.is_exempt(rel):
                continue
            if path.is_dir():
                child = path / self.settings.entry_point
                if child.is_file() and not self.settings.is_exempt(child.relative_to(self.root)):
                    candidates.append(child.relative_to(self.root).as_posix())
            elif path.suffix == ".md" and path.name != self.settings.entry_point:
                candidates.append(rel.as_posix())
            elif self.reader.is_specification(rel.as_posix()):
                candidates.append(rel.as_posix())
        notes = [self.reader.read(rel) for rel in candidates]
        return [
            note
            for note in notes
            if note is not None and note.role not in self.settings.unlisted_roles
        ]

    def title(self, rel: str) -> str:
        """Return the title of any repository file, or its name when unreadable."""
        note = self.reader.read(rel)
        return title_of(note) if note else PurePosixPath(rel).stem

    def generate(self, index_rel: str) -> Result:
        """Rewrite the blocks of one index, and report the issues of the index and its members."""
        path = self.root / index_rel
        text = path.read_text(encoding="utf-8")
        blocks = parse_blocks(text)
        # A new index, or an index of an area whose indexes are generated, must hold its region.
        generated_area = PurePosixPath(index_rel).parts[0] in self.settings.generated_areas
        if (generated_area or index_rel in self.settings.new_indexes) and not any(
            block.region for block in blocks
        ):
            where = "of a generated area" if generated_area else "created since the last commit"
            ungenerated = [
                Issue(
                    index_rel,
                    1,
                    "ungenerated-index",
                    f"an index {where} must hold the region <!-- index groups -->",
                )
            ]
        else:
            ungenerated = []
        if not blocks:
            return Result(text=text, changed=False, issues=ungenerated)
        folder = PurePosixPath(index_rel).parent.as_posix()
        folder = "" if folder == "." else folder
        index_note = self.reader.read(index_rel)
        kind, type_problems = self.settings.types.resolve(
            index_rel, index_note.index_type if index_note is not None else None
        )
        issues: list[Issue] = ungenerated + [
            Issue(index_rel, 1, "index-type", problem) for problem in type_problems
        ]
        # The expected files are listed by the control block, never as entries.
        controls = {normalize(PurePosixPath(folder) / spec.name) for spec in kind.expected}
        members = [note for note in self.members(index_rel) if note.rel not in controls]
        declared = index_note.groups if index_note is not None else ()
        groups = {spec.id for spec in declared} if any(block.region for block in blocks) else set()
        # Each member belongs to the group that it names, else to the first group whose filter it
        # matches, else to the catch-all group.
        assigned = {
            note.rel: note.group
            or next((spec.id for spec in declared if spec.selects(note.data)), "*")
            for note in members
        }
        bodies: list[str] = []
        listed: list[tuple[Note, Block]] = []
        constructed: list[Note] = []
        sequence, from_key = self._sequence(index_rel, folder, members, issues)
        modes: dict[int, str] = {}
        context = (
            index_rel,
            folder,
            kind,
            members,
            sequence,
            from_key,
            modes,
            listed,
            constructed,
            assigned,
            issues,
        )
        for block in blocks:
            issues.extend(
                Issue(index_rel, block.line, "malformed-block", problem)
                for problem in block.problems
            )
            if block.control:
                bodies.append(
                    render_body(
                        self._control_files(folder, kind),
                        folder,
                        block.show,
                        self.title,
                    )
                )
            elif block.region:
                bodies.append(self._render_region(block, declared, context))
            else:
                # A malformed marker opens no known region, so its body stays as written.
                bodies.append(block.body)
        if index_note is not None and any(block.region for block in blocks):
            issues.extend(
                Issue(index_rel, 1, "malformed-groups", problem)
                for problem in index_note.slot_problems
            )
            issues.extend(self._relation_issues(index_rel, index_note, members))
            # Outside its slots, an index holds no prose: each other unit moves to its owner.
            issues.extend(
                Issue(
                    index_rel,
                    line,
                    "index-prose",
                    f"{description}, outside the slots of an index",
                    blocking=False,
                )
                for line, description in prose_units(text)
            )
        # An index holding a control block alone has not yet migrated its entries. A member
        # declaring no entry field has not migrated either, so it stays in the hand-written list.
        if any(block.region for block in blocks):
            for note in members:
                if assigned[note.rel] in groups:
                    continue
                if note.group is None and note.purpose is None and not note.cites:
                    issues.append(
                        Issue(
                            note.rel,
                            1,
                            "unmigrated-member",
                            "the file declares no entry field, so no block lists it yet",
                            blocking=False,
                        )
                    )
                else:
                    issues.append(
                        Issue(
                            note.rel,
                            1,
                            "unplaced-member",
                            f"no block of {index_rel} holds the group " f"{note.group or '*'}",
                        )
                    )
        issues.extend(
            issue for note, block in listed for issue in self._member_issues(note, block, index_rel)
        )
        issues.extend(self._goal_issues(index_rel, constructed))
        issues.extend(self._control_issues(index_rel, folder, kind))
        rendered = replace_bodies(text, bodies)
        return Result(text=rendered, changed=rendered != text, issues=issues)

    def _list_group(self, block: Block, context: tuple[Any, ...]) -> str:
        """Order and render the members of one group, and record them for the later checks."""
        (
            index_rel,
            folder,
            kind,
            members,
            sequence,
            from_key,
            modes,
            listed,
            constructed,
            assigned,
            issues,
        ) = context
        strategy, problems = self.rules.resolve_strategy(block.strategy)
        issues.extend(
            Issue(
                index_rel,
                block.line,
                "malformed-groups",
                f"group {block.group}: {problem}",
            )
            for problem in problems
        )
        mode = block.mode or kind.default_mode
        # One heading per mode keeps the parts of a hybrid scheme visibly apart.
        if modes.setdefault(block.section, mode) != mode:
            issues.append(
                Issue(
                    index_rel,
                    block.line,
                    "mixed-modes",
                    f"a {mode} block stands under the heading of a "
                    f"{modes[block.section]} block",
                )
            )
        block_members = [note for note in members if assigned[note.rel] == block.group]
        ordering = self._order(
            index_rel,
            folder,
            block,
            mode,
            block_members,
            strategy,
            sequence,
            from_key,
            issues,
        )
        if block.group is not None:
            listed.extend((note, block) for note in ordering.members)
            if mode == "construction":
                constructed.extend(ordering.members)
        if block.nest:
            nested, depths, cycle = nest_members(ordering.members, block.nest)
            issues.extend(
                Issue(
                    index_rel,
                    block.line,
                    "malformed-groups",
                    f"group {block.group}: {note.rel} closes a cycle of {block.nest}",
                )
                for note in cycle
            )
            return render_body(nested, folder, block.show, self.title, depths)
        return render_body(ordering.members, folder, block.show, self.title)

    def _render_region(
        self, region: Block, declared: tuple[GroupSpec, ...], context: tuple[Any, ...]
    ) -> str:
        """Render the groups declared by an index, each under its heading and its description."""
        index_rel, issues = context[0], context[-1]
        index_note = self.reader.read(index_rel)
        index_files = index_note.files if index_note is not None else ()
        issues.extend(
            Issue(
                index_rel,
                region.line,
                "unknown-file",
                f"files names no file of the folder: {spec_file.file}",
            )
            for spec_file in index_files
            if not (self.root / context[1] / spec_file.file).is_file()
        )
        issues.extend(
            Issue(
                index_rel,
                region.line,
                "malformed-groups",
                f"files names an undeclared group: {spec_file.group}",
            )
            for spec_file in index_files
            if spec_file.group not in {spec.id for spec in declared}
        )
        if not declared:
            issues.append(
                Issue(
                    index_rel,
                    region.line,
                    "malformed-groups",
                    "the region renders groups, which the index does not declare",
                )
            )
        parts = []
        section = 0
        for number, spec in enumerate(declared, start=1):
            # A group without a heading stands under the heading of the group before it.
            section = number if spec.heading else section
            problems = []
            # Any key of the members may sort a group, so a key that no member holds is a typo.
            if spec.sort not in SORT_KEYS and not any(
                spec.sort in note.data for note in context[3] if context[-2][note.rel] == spec.id
            ):
                problems.append(f"group {spec.id}: no member holds the sort key {spec.sort}")
            if spec.mode is not None and spec.mode not in MODES:
                problems.append(f"group {spec.id}: unknown mode: {spec.mode}")
            issues.extend(
                Issue(index_rel, region.line, "malformed-groups", problem) for problem in problems
            )
            block = Block(
                group=spec.id,
                show=tuple(dict.fromkeys(spec.show)),
                strategy=spec.strategy,
                body="",
                line=region.line,
                sort=spec.sort,
                mode=spec.mode if spec.mode in MODES else None,
                section=section,
                nest=spec.nest,
            )
            header = (f"## {spec.heading}\n\n" if spec.heading else "") + (
                f"{spec.description}\n\n" if spec.description else ""
            )
            entries = self._list_group(block, context)
            files = [
                Note(
                    normalize(PurePosixPath(context[1]) / spec_file.file),
                    title=spec_file.title,
                    purpose=spec_file.purpose,
                )
                for spec_file in sorted(index_files, key=lambda item: item.title.casefold())
                if spec_file.group == spec.id
            ]
            parts.append(header + entries + render_body(files, context[1], block.show, self.title))
        return "\n".join(parts)

    def _relation_issues(
        self, index_rel: str, index_note: Note, members: list[Note]
    ) -> list[Issue]:
        """Report a contextual relation of an undeclared kind, or between files that are not members."""
        rels = {note.rel for note in members}
        issues: list[Issue] = []
        for relation in index_note.context_relations:
            problems: list[str] = []
            if relation.relation not in self.rules.relations:
                problems.append(f"relation not declared: {relation.relation}")
            problems.extend(
                f"{end} is no member of {index_rel}: {path}"
                for end, path in (
                    ("source", relation.source),
                    ("target", relation.target),
                )
                if path not in rels
            )
            issues.extend(
                Issue(index_rel, 1, "invalid-context-relation", problem) for problem in problems
            )
        return issues

    def _sequence(
        self, index_rel: str, folder: str, members: list[Note], issues: list[Issue]
    ) -> tuple[list[str] | None, bool]:
        """Return the sequence of the folder, and whether the key ``sequence`` states it.

        The injected sequence prevails, and a key ``sequence`` beside it is reported, since it
        states the same order a second time. A name of the key matching no member is reported.
        """
        index_note = self.reader.read(index_rel)
        declared = list(index_note.sequence) if index_note is not None else []
        supplied = self.sequence_provider(self.root / folder)
        if supplied is not None:
            if declared:
                issues.append(
                    Issue(
                        index_rel,
                        1,
                        "redundant-sequence",
                        "the key sequence restates the configured folder sequence",
                    )
                )
            return (list(supplied), False)
        if not declared:
            return (None, False)
        rels = {note.rel for note in members}
        issues.extend(
            Issue(
                index_rel,
                1,
                "unknown-sequence-entry",
                f"sequence names no member of the folder: {name}",
            )
            for name in declared
            if normalize(PurePosixPath(folder) / name) not in rels
        )
        return (declared, True)

    def _order(
        self,
        index_rel: str,
        folder: str,
        block: Block,
        mode: str,
        block_members: list[Note],
        strategy: Mapping[str, str],
        sequence: list[str] | None,
        from_key: bool,
        issues: list[Issue],
    ) -> Ordering:
        """Order the members of one block under its mode, and report the issues of the order."""
        if mode == "registry":
            return order_registry(block_members, block.sort)
        if mode == "sequence":
            if sequence is None:
                issues.append(
                    Issue(
                        index_rel,
                        block.line,
                        "missing-sequence",
                        "a sequence block needs a configured folder sequence or a key sequence",
                    )
                )
            ordering = order_sequence(block_members, sequence or [], folder, block.sort)
            issues.extend(
                Issue(
                    note.rel,
                    1,
                    "unsequenced-member",
                    f"the sequence of {index_rel} does not list the file",
                    blocking=False,
                )
                for note in ordering.unsequenced
                if sequence is not None
            )
            return ordering
        ordering = order_members(block_members, self.rules.relations, strategy, block.sort)
        issues.extend(
            Issue(
                index_rel,
                block.line,
                "order-conflict",
                f"{earlier} cannot precede {later} without a cycle",
                blocking=False,
            )
            for earlier, later in ordering.conflicts
        )
        return ordering

    def _member_issues(self, note: Note, block: Block, index_rel: str) -> list[Issue]:
        issues: list[Issue] = []
        if not note.title:
            issues.append(
                Issue(
                    note.rel,
                    1,
                    "missing-alias",
                    "a listed file declares no alias, whose first is its title",
                )
            )
        elif note.rel.endswith(".md") and (
            note.heading is None or EMPHASIS.sub("", note.heading) != EMPHASIS.sub("", note.title)
        ):
            issues.append(
                Issue(
                    note.rel,
                    1,
                    "title-mismatch",
                    f"the H1 heading {note.heading!r} differs from the first alias "
                    f"{note.title!r}",
                )
            )
        if note.index != index_rel:
            issues.append(
                Issue(
                    note.rel,
                    1,
                    "index-location",
                    f"index names {note.index}, whereas the file is listed by {index_rel}",
                )
            )
        # A purpose is owed where a block displays it; a registry displaying titles needs none.
        if "purpose" in block.show and not note.purpose:
            issues.append(
                Issue(
                    note.rel,
                    1,
                    "missing-purpose",
                    "the block displays a purpose, which the file does not declare",
                    blocking=False,
                )
            )
        issues.extend(self._citation_issues(note))
        for identifier in note.blocked_by:
            if identifier not in self.tasks:
                issues.append(
                    Issue(
                        note.rel,
                        1,
                        "unknown-task",
                        f"blocked_by names no declared task: {identifier}",
                    )
                )
            elif self.tasks[identifier]:
                issues.append(
                    Issue(
                        note.rel,
                        1,
                        "finished-blocker",
                        f"the task {identifier} is closed, so the status may advance",
                        blocking=False,
                    )
                )
        return issues

    def _citation_issues(self, note: Note) -> list[Issue]:
        """Report the citations of one note naming no file, lacking evidence, or mirrored."""
        issues: list[Issue] = []
        # A specification has no body, so its citations carry no evidence to check. The citations
        # of an index are metadata read in its frontmatter, as the decision on index slots fixes.
        has_body = (
            note.rel.endswith(".md") and PurePosixPath(note.rel).name != self.settings.entry_point
        )
        for citation in note.cites:
            if citation.external:
                evidence = (
                    citation.target in note.external_links
                    if citation.link_text is not None
                    else citation.target in note.tail_tags
                )
                if has_body and not evidence:
                    evidence_target = (
                        f"the link {citation.target}"
                        if citation.link_text is not None
                        else f"the tail tag [{citation.target}]"
                    )
                    issues.append(
                        Issue(
                            note.rel,
                            1,
                            "missing-evidence",
                            f"{citation.relation} expects {evidence_target} in the body",
                            blocking=False,
                        )
                    )
                continue
            target = self.reader.read(citation.target)
            if target is None:
                issues.append(
                    Issue(
                        note.rel,
                        1,
                        "unknown-target",
                        f"cites names no file: {citation.target}",
                    )
                )
                continue
            if has_body and citation.target not in note.links:
                issues.append(
                    Issue(
                        note.rel,
                        1,
                        "missing-evidence",
                        f"{citation.relation} expects the body to link " f"{citation.target}",
                        blocking=False,
                    )
                )
            relation = self.rules.relations.get(citation.relation)
            mirror = relation.mirror if relation is not None else None
            # The pair is reported once, on the note whose path sorts first.
            if (
                mirror
                and note.rel < target.rel
                and any(
                    back.relation == mirror and not back.external and back.target == note.rel
                    for back in target.cites
                )
            ):
                issues.append(
                    Issue(
                        note.rel,
                        1,
                        "mirror-citation",
                        f"{note.rel} {citation.relation} {target.rel}, and "
                        f"{target.rel} {mirror} {note.rel}: keep the citation of the "
                        "note that depends on the other",
                    )
                )
        return issues

    def _goal_issues(self, index_rel: str, listed: list[Note]) -> list[Issue]:
        """Report the goals naming no member, and the members contributing to no goal.

        A member is relevant when a chain of contributions leads from it to a goal, each step
        following one citation from its contributing end, with at most one step of grade
        *exposition*. The chains run through the listed members only.
        """
        index_note = self.reader.read(index_rel)
        if index_note is None or not index_note.goal:
            return []
        by_rel = {note.rel: note for note in listed}
        issues = [
            Issue(index_rel, 1, "unknown-goal", f"goal names no listed member: {goal}")
            for goal in index_note.goal
            if goal not in by_rel
        ]
        # served[v] lists (u, grade) for each contribution of u to v.
        served: dict[str, list[tuple[str, Grade]]] = {rel: [] for rel in by_rel}
        for note in listed:
            for citation in note.cites:
                relation = self.rules.relations.get(citation.relation)
                if (
                    relation is None
                    or citation.external
                    or citation.target not in by_rel
                    or citation.target == note.rel
                ):
                    continue
                if relation.contributes is End.TARGET:
                    served[note.rel].append((citation.target, relation.grade))
                elif relation.contributes is End.SOURCE:
                    served[citation.target].append((note.rel, relation.grade))
        states = [(goal, False) for goal in index_note.goal if goal in by_rel]
        seen = set(states)
        while states:
            rel, used = states.pop()
            for contributor, grade in served[rel]:
                if grade is Grade.NONE or (grade is Grade.EXPOSITION and used):
                    continue
                state = (contributor, used or grade is Grade.EXPOSITION)
                if state not in seen:
                    seen.add(state)
                    states.append(state)
        relevant = {rel for rel, _used in seen}
        issues.extend(
            Issue(
                note.rel,
                1,
                "off-goal",
                f"no chain of contributions leads to a goal of {index_rel}",
                blocking=False,
            )
            for note in listed
            if note.rel not in relevant
        )
        return issues

    def _control_files(self, folder: str, kind: IndexType) -> list[Note]:
        """Return the control files present in a folder: the expected files, then the worklogs.

        The expected files follow the order of the type, and the files of an unlisted role, such
        as a handoff or a plan, follow them by title.
        """
        found: list[Note] = []
        for spec in kind.expected:
            note = self.reader.read(normalize(PurePosixPath(folder) / spec.name))
            if note is not None:
                found.append(note)
        base = self.root / folder
        others = [
            note
            for path in sorted(base.glob("*.md"))
            if not self.settings.is_exempt(path.relative_to(self.root))
            for note in [self.reader.read(path.relative_to(self.root).as_posix())]
            if note is not None and note.role in self.settings.unlisted_roles and note not in found
        ]
        return found + sorted(others, key=lambda note: (title_of(note).casefold(), note.rel))

    def _control_issues(self, index_rel: str, folder: str, kind: IndexType) -> list[Issue]:
        """Report a required control file that is missing, or an expected file of another role."""
        issues: list[Issue] = []
        for spec in kind.expected:
            rel = normalize(PurePosixPath(folder) / spec.name)
            note = self.reader.read(rel)
            if note is None and spec.required:
                issues.append(
                    Issue(
                        index_rel,
                        1,
                        "missing-control-file",
                        f"the type {kind.name} requires {rel}",
                    )
                )
            elif note is not None and spec.role and note.role != spec.role:
                issues.append(
                    Issue(
                        rel,
                        1,
                        "control-file-role",
                        f"the type {kind.name} expects the role {spec.role}, " f"not {note.role}",
                    )
                )
        return issues


def nest_members(members: list[Note], path: str) -> tuple[list[Note], list[int], list[Note]]:
    """Place each member beneath the member that its key names, keeping the order of siblings.

    The key is a dotted path into the data of a member; its value, or the first of its values
    naming a member of the group, designates the parent by file stem, by ``id``, or by link. A
    member whose parent lies outside the group stands at the first level. The members of a cycle
    are placed at the first level too, and returned apart so that the cycle can be reported.

    >>> notes = [Note("a.yml", data={"up": None}), Note("b.yml", data={"up": ["a"]}),
    ...          Note("c.yml", data={"up": "b"}), Note("d.yml")]
    >>> nested, depths, cycle = nest_members(notes, "up")
    >>> [(note.rel, depth) for note, depth in zip(nested, depths)], cycle
    ([('a.yml', 0), ('b.yml', 1), ('c.yml', 2), ('d.yml', 0)], [])
    """

    def key(note: Note) -> list[str]:
        value: Any = note.data
        for part in path.split("."):
            value = value.get(part) if isinstance(value, Mapping) else None
        values = value if isinstance(value, list) else [value] if value is not None else []
        return [str(item) for item in values]

    names = {}
    for note in members:
        names[PurePosixPath(note.rel).stem] = note
        names[note.rel] = note
        if note.data.get("id") is not None:
            names[str(note.data["id"])] = note
    parent: dict[str, Note] = {}
    for note in members:
        for value in key(note):
            target = names.get(value) or names.get(
                normalize(PurePosixPath(value_link(value) or value))
            )
            if target is not None and target is not note:
                parent[note.rel] = target
                break
    children: dict[str, list[Note]] = {}
    for note in members:
        if note.rel in parent:
            children.setdefault(parent[note.rel].rel, []).append(note)
    nested: list[Note] = []
    depths: list[int] = []
    seen: set[str] = set()

    def visit(note: Note, depth: int) -> None:
        seen.add(note.rel)
        nested.append(note)
        depths.append(depth)
        for child in children.get(note.rel, []):
            if child.rel not in seen:
                visit(child, depth + 1)

    for note in members:
        if note.rel not in parent:
            visit(note, 0)
    cycle = [note for note in members if note.rel not in seen]
    for note in cycle:
        if note.rel not in seen:
            visit(note, 0)
    return nested, depths, cycle
