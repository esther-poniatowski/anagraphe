"""
Generation and checking of the entries of one index.

The index of a collection is the specification of that collection (ADR 0002). For an index holding
at least one generated region, the generator collects the members of its folder, assigns each
member to one group of the index, orders the members of each group under the mode of the group,
renders the entries, and reports the issues of the index and of its members. An index holding no
region is left untouched, so the checks grow folder by folder as the indexes migrate, except in
the areas declared as generated: there, an index without the region of its groups is reported.
A retired key is reported under every index, with or without its region, so that a repository
learns each edit owed before its indexes migrate.

No source of order is dropped silently: a sequence, an ``order`` or a build manifest that the mode
of its group ignores is reported. A key retired by ADR 0002 is reported with its replacement.

Violations gate a commit, whereas warnings report a decision still owed by the author, such as a
member that a sequence does not list, or a retired key tolerated by a declared migration class.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Protocol, Sequence

from anagraphe.indexes.blocks import Block, parse_blocks, replace_bodies
from anagraphe.indexes.fields import FieldRules
from anagraphe.core.issues import Issue, pointer
from anagraphe.indexes.membership import Membership, assign
from anagraphe.core.metadata import MetadataReader
from anagraphe.indexes.notes import Note, NoteReader
from anagraphe.indexes.order import Collation, Ordering, order_registry, order_sequence
from anagraphe.core.links import link_target, value_link
from anagraphe.core.paths import normalize
from anagraphe.indexes.render import render_body, title_of
from anagraphe.indexes.retired import MigrationClass, Scope, migration_of, retired_keys
from anagraphe.indexes.slots import SORT_KEYS, GroupSpec, prose_units
from anagraphe.indexes.types import IndexType, IndexTypes

#: Emphasis markers removed from an H1 heading before it is compared with the first alias.
EMPHASIS = re.compile(r"[*_`]")


class SequenceProvider(Protocol):
    """Resolve the build manifest of a repository folder."""

    def __call__(self, folder: Path) -> Sequence[str] | None:
        """Return the ordered member paths, relative to the folder, or ``None`` without manifest."""
        ...


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
    #: Whether an index lists a repository-relative file of its folder, by its declared types.
    is_member: Callable[[str], bool] = field(
        default=lambda rel: rel.endswith((".md", ".yml", ".yaml"))
    )

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


@dataclass
class _Collection:
    """The state shared by the groups of one index while the index is generated."""

    index_rel: str
    #: Repository-relative folder of the index, empty at the root.
    folder: str
    kind: IndexType
    #: The files that the index lists.
    members: list[Note]
    #: The group holding each placed member.
    assigned: Mapping[str, str]
    #: The repository-relative paths of the build manifest of the folder, or None.
    manifest: tuple[str, ...] | None
    issues: list[Issue]
    #: The mode of each heading, keyed by the number of the group that opens the heading.
    modes: dict[int, str] = field(default_factory=dict)
    #: The listed members, each with the group that displays it.
    listed: list[tuple[Note, GroupSpec]] = field(default_factory=list)


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
    sequence_provider
        The build manifest of each folder, which prevails over the sequence of a group.
    migrations
        The files tolerating a retired key until a declared migration.
    """

    def __init__(
        self,
        root: Path,
        settings: Settings,
        rules: FieldRules,
        tasks: Mapping[str, bool],
        sequence_provider: SequenceProvider | None = None,
        migrations: Sequence[MigrationClass] = (),
        metadata: MetadataReader | None = None,
    ) -> None:
        self.root = root
        self.settings = settings
        self.rules = rules
        self.tasks = tasks
        self.sequence_provider = sequence_provider or (lambda _folder: None)
        self.migrations = tuple(migrations)
        self.reader = NoteReader(root, metadata)

    def members(self, index_rel: str) -> list[Note]:
        """Return the files that an index lists: the files of its declared types, and child indexes."""
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
            elif path.name != self.settings.entry_point and self.settings.is_member(rel.as_posix()):
                candidates.append(rel.as_posix())
        notes = [self.reader.read(rel) for rel in candidates]
        return [
            note
            for note in notes
            if note is not None and note.role not in self.settings.unlisted_roles
        ]

    def exists(self, rel: str) -> bool:
        """Whether a repository-relative path names a file."""
        return (self.root / rel).is_file()

    def generate(self, index_rel: str) -> Result:
        """Rewrite the regions of one index, and report the issues of the index and its members."""
        path = self.root / index_rel
        text = path.read_text(encoding="utf-8")
        blocks = parse_blocks(text)
        has_region = any(block.region for block in blocks)
        # A new index, or an index of an area whose indexes are generated, must hold its region.
        generated_area = PurePosixPath(index_rel).parts[0] in self.settings.generated_areas
        ungenerated = []
        if (generated_area or index_rel in self.settings.new_indexes) and not has_region:
            where = "of a generated area" if generated_area else "created since the last commit"
            ungenerated.append(
                Issue(
                    index_rel,
                    None,
                    "ungenerated-index",
                    f"an index {where} must hold the region <!-- index groups -->",
                )
            )
        folder = PurePosixPath(index_rel).parent.as_posix()
        folder = "" if folder == "." else folder
        index_note = self.reader.read(index_rel)
        kind, type_problems = self.settings.types.resolve(
            index_rel, index_note.index_type if index_note is not None else None
        )
        # The expected files are listed by the control block, never as entries, and a file declared
        # under the key files takes its declared entry, never a second one as a member.
        controls = {normalize(PurePosixPath(folder) / spec.name) for spec in kind.expected}
        controls |= {
            normalize(PurePosixPath(folder) / spec.file)
            for spec in (index_note.files if index_note is not None else ())
        }
        members = [note for note in self.members(index_rel) if note.rel not in controls]
        retired = self._retired_member_issues(index_rel, index_note, members)
        if not blocks:
            return Result(text=text, changed=False, issues=ungenerated + retired)
        issues: list[Issue] = (
            ungenerated
            + [
                Issue(index_rel, None, "index-type", problem, locus=pointer("index_type"))
                for problem in type_problems
            ]
            + retired
        )
        declared = index_note.groups if index_note is not None else ()
        membership = (
            assign(index_rel, declared, members, self.rules.values, self.exists)
            if has_region
            else Membership()
        )
        issues.extend(membership.issues)
        collection = _Collection(
            index_rel, folder, kind, members, membership.assigned, self._manifest(folder), issues
        )
        bodies: list[str] = []
        for block in blocks:
            issues.extend(
                Issue(index_rel, block.line, "malformed-block", problem)
                for problem in block.problems
            )
            if block.control:
                bodies.append(render_body(self._control_files(folder, kind), folder, block.show))
            elif block.region:
                bodies.append(self._render_region(block, declared, collection))
            else:
                # A malformed marker opens no known region, so its body stays as written.
                bodies.append(block.body)
        if index_note is not None and has_region:
            issues.extend(
                Issue(index_rel, None, "malformed-groups", problem, locus=pointer("groups"))
                for problem in index_note.slot_problems
            )
            issues.extend(self._relation_issues(index_rel, index_note, members))
            issues.extend(self._external_issues(index_rel, index_note, members))
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
        # An index holding a control block alone has not yet migrated its entries.
        if has_region:
            for note in members:
                issues.extend(self._placement_issues(index_rel, note, membership.assigned))
                issues.extend(self._superseded_issues(note))
        issues.extend(
            issue
            for note, spec in collection.listed
            for issue in self._member_issues(note, spec, index_rel)
        )
        issues.extend(self._control_issues(index_rel, folder, kind))
        rendered = replace_bodies(text, bodies)
        return Result(text=rendered, changed=rendered != text, issues=issues)

    def _manifest(self, folder: str) -> tuple[str, ...] | None:
        """Return the build manifest of a folder as repository-relative paths, or None."""
        supplied = self.sequence_provider(self.root / folder)
        if supplied is None:
            return None
        return tuple(normalize(PurePosixPath(folder) / name) for name in supplied)

    def _retired_member_issues(
        self, index_rel: str, index_note: Note | None, members: list[Note]
    ) -> list[Issue]:
        """Report the retired keys of an index and of its members, whether or not it is generated."""
        issues = (
            self._retired_issues(index_rel, "index", index_note.data)
            if index_note is not None
            else []
        )
        for note in members:
            scope: Scope = (
                "member" if PurePosixPath(note.rel).name == self.settings.entry_point else "note"
            )
            issues.extend(self._retired_issues(note.rel, scope, note.data))
        return issues

    def _retired_issues(self, rel: str, scope: Scope, data: Mapping[str, Any]) -> list[Issue]:
        """Report each retired key of a file, as a warning inside a declared migration class."""
        issues: list[Issue] = []
        for entry in retired_keys(scope, data):
            migration = migration_of(self.migrations, entry.key, rel)
            if migration is None:
                issues.append(
                    Issue(rel, None, "retired-key", entry.message(), locus=pointer(entry.key))
                )
            else:
                issues.append(
                    Issue(
                        rel,
                        None,
                        "migration-key",
                        f"{entry.message()}; tolerated until {migration.awaits}",
                        blocking=False,
                        locus=pointer(entry.key),
                    )
                )
        return issues

    @staticmethod
    def _placement_issues(index_rel: str, note: Note, assigned: Mapping[str, str]) -> list[Issue]:
        """Report a member that no group holds.

        A member declaring no purpose has not migrated, so it stays in the hand-written list and
        is reported as a warning.
        """
        if note.rel in assigned:
            return []
        if note.purpose is None:
            return [
                Issue(
                    note.rel,
                    None,
                    "unmigrated-member",
                    "the file declares no entry field, so no group lists it yet",
                    blocking=False,
                )
            ]
        return [
            Issue(
                note.rel,
                None,
                "unplaced-member",
                f"no group of {index_rel} holds the file: declare a catch-all group *, or "
                "name the file in the where or the members of a group",
            )
        ]

    def _render_region(
        self, region: Block, declared: tuple[GroupSpec, ...], collection: _Collection
    ) -> str:
        """Render the groups declared by an index, each under its heading and its description."""
        index_rel, folder, issues = collection.index_rel, collection.folder, collection.issues
        index_note = self.reader.read(index_rel)
        index_files = index_note.files if index_note is not None else ()
        issues.extend(
            Issue(
                index_rel,
                region.line,
                "unknown-file",
                f"files names no file of the folder: {spec_file.file}",
                locus=pointer("files"),
                discriminator=spec_file.file,
            )
            for spec_file in index_files
            if not (self.root / folder / spec_file.file).is_file()
        )
        issues.extend(
            Issue(
                index_rel,
                region.line,
                "malformed-groups",
                f"files names an undeclared group: {spec_file.group}",
                locus=pointer("files"),
                discriminator=spec_file.file,
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
                    locus=pointer("groups"),
                )
            )
        parts = []
        section = 0
        for number, spec in enumerate(declared, start=1):
            # A group without a heading stands under the heading of the group before it.
            section = number if spec.heading else section
            header = (f"## {spec.heading}\n\n" if spec.heading else "") + (
                f"{spec.description}\n\n" if spec.description else ""
            )
            show = tuple(dict.fromkeys(spec.show))
            entries = self._list_group(spec, section, region.line, collection)
            files = [
                Note(
                    normalize(PurePosixPath(folder) / spec_file.file),
                    title=spec_file.title,
                    purpose=spec_file.purpose,
                )
                for spec_file in sorted(index_files, key=lambda item: item.title.casefold())
                if spec_file.group == spec.id
            ]
            parts.append(header + entries + render_body(files, folder, show))
        return "\n".join(parts)

    def _list_group(self, spec: GroupSpec, section: int, line: int, collection: _Collection) -> str:
        """Order and render the members of one group, and record them for the later checks."""
        index_rel, issues = collection.index_rel, collection.issues
        mode = spec.mode or collection.kind.default_mode
        # One heading per mode keeps the parts of a hybrid scheme visibly apart.
        if collection.modes.setdefault(section, mode) != mode:
            issues.append(
                Issue(
                    index_rel,
                    line,
                    "mixed-modes",
                    f"a {mode} group stands under the heading of a "
                    f"{collection.modes[section]} group",
                    locus=pointer("groups"),
                    discriminator=spec.id,
                )
            )
        group_members = [
            note for note in collection.members if collection.assigned.get(note.rel) == spec.id
        ]
        collation = Collation.of(spec, self.rules.values)
        issues.extend(self._collation_issues(index_rel, spec, collation, group_members))
        ordering = self._order(spec, mode, group_members, collation, collection)
        collection.listed.extend((note, spec) for note in ordering.members)
        show = tuple(dict.fromkeys(spec.show))
        if spec.nest:
            nested, depths, cycle = nest_members(ordering.members, spec.nest)
            issues.extend(
                Issue(
                    index_rel,
                    None,
                    "nest-cycle",
                    f"group {spec.id}: {note.rel} closes a cycle of {spec.nest}",
                    locus=pointer("groups"),
                    discriminator=f"{spec.id} {note.rel}",
                )
                for note in cycle
            )
            return render_body(nested, collection.folder, show, depths)
        return render_body(ordering.members, collection.folder, show)

    def _collation_issues(
        self, index_rel: str, spec: GroupSpec, collation: Collation, group_members: list[Note]
    ) -> list[Issue]:
        """Report a sort key that no member holds, an ignored ``order``, and unranked values.

        A member value outside the declared values of its key is a violation. A declared value, or
        a value of a key declaring none, that the ``order`` of the group omits is a warning, and
        the member sorts after the ranked values.
        """
        issues = [
            # Any key of the members may sort a group, so a key that no member holds is a typo.
            Issue(
                index_rel,
                None,
                "malformed-groups",
                f"group {spec.id}: no member holds the sort key {key}",
                locus=pointer("groups"),
                discriminator=f"{spec.id} {key}",
            )
            for key in spec.sort
            if key not in SORT_KEYS and not any(key in note.data for note in group_members)
        ]
        first = spec.sort[0]
        if spec.order and first in SORT_KEYS:
            issues.append(
                Issue(
                    index_rel,
                    None,
                    "ignored-order",
                    f"group {spec.id} sorts first by {first}, so its order is ignored: sort "
                    "first by the categorical key that order ranks",
                    locus=pointer("groups"),
                    discriminator=f"{spec.id} order",
                )
            )
        elif spec.order and first in self.rules.values:
            issues.extend(
                Issue(
                    index_rel,
                    None,
                    "undeclared-value",
                    f"order of group {spec.id}: {first} admits no value {value}; its values are "
                    f"{', '.join(self.rules.values[first])}",
                    locus=pointer("groups"),
                    discriminator=f"{spec.id} {value}",
                )
                for value in spec.order
                if value not in self.rules.values[first]
            )
        for note in group_members:
            for key, value in collation.undeclared(note):
                declared = self.rules.values.get(key)
                if declared is not None and value not in declared:
                    issues.append(
                        Issue(
                            note.rel,
                            None,
                            "undeclared-value",
                            f"{key} holds {value}, which group {spec.id} in {index_rel} sorts "
                            f"by, outside its declared values: {', '.join(declared)}",
                            locus=pointer(*key.split(".")),
                        )
                    )
                else:
                    issues.append(
                        Issue(
                            note.rel,
                            None,
                            "unranked-value",
                            f"{key} holds {value}, which the order of group {spec.id} in "
                            f"{index_rel} does not rank, so the file follows the ranked values: "
                            f"{', '.join(collation.ranks[key])}",
                            blocking=False,
                            locus=pointer(*key.split(".")),
                        )
                    )
        return issues

    def _order(
        self,
        spec: GroupSpec,
        mode: str,
        group_members: list[Note],
        collation: Collation,
        collection: _Collection,
    ) -> Ordering:
        """Order the members of one group under its mode, and report each ignored source of order."""
        index_rel, issues, manifest = collection.index_rel, collection.issues, collection.manifest
        folder = collection.folder or "."
        if mode == "registry":
            if spec.sequence is not None:
                # A sequence holding the members of its group still assigns them under a registry.
                remedy = (
                    "set mode sequence, or list the files under members"
                    if spec.members is None and not spec.where
                    else "set mode sequence, or remove the sequence"
                )
                issues.append(
                    Issue(
                        index_rel,
                        None,
                        "ignored-order",
                        f"group {spec.id} is a registry, so the order of its sequence is "
                        f"ignored: {remedy}",
                        locus=pointer("groups"),
                        discriminator=f"{spec.id} sequence",
                    )
                )
            manifested = [note.rel for note in group_members if manifest and note.rel in manifest]
            if manifested:
                issues.append(
                    Issue(
                        index_rel,
                        None,
                        "ignored-order",
                        f"the build manifest of {folder} orders {', '.join(manifested)}, which "
                        f"the registry group {spec.id} sorts by {', '.join(spec.sort)}",
                        locus=pointer("groups"),
                        discriminator=f"{spec.id} manifest",
                    )
                )
            return order_registry(group_members, collation)
        # A sequence holding the members of its group defines them, beside its order.
        holds_members = spec.members is None and not spec.where
        if manifest is not None:
            if spec.sequence is not None:
                remedy = "move the links under members" if holds_members else "remove the sequence"
                issues.append(
                    Issue(
                        index_rel,
                        None,
                        "ignored-order",
                        f"the build manifest of {folder} prevails over the sequence of group "
                        f"{spec.id}: {remedy}",
                        locus=pointer("groups"),
                        discriminator=f"{spec.id} sequence",
                    )
                )
            source: tuple[str, ...] = manifest
        elif spec.sequence is not None:
            source = spec.sequence
        else:
            issues.append(
                Issue(
                    index_rel,
                    None,
                    "missing-sequence",
                    f"group {spec.id} is a sequence, which needs a sequence of links or a build "
                    "manifest of the folder",
                    locus=pointer("groups"),
                    discriminator=spec.id,
                )
            )
            source = ()
        ordering = order_sequence(group_members, source, collation)
        # A sequence holding the members of its group has its outside links reported as members.
        if manifest is None and not holds_members:
            issues.extend(
                Issue(
                    index_rel,
                    None,
                    "ignored-order" if self.exists(rel) else "invalid-link",
                    (
                        f"sequence of group {spec.id} names {rel}, which the group does not hold"
                        if self.exists(rel)
                        else f"sequence of group {spec.id} names no file: {rel}"
                    ),
                    locus=pointer("groups"),
                    discriminator=f"{spec.id} {rel}",
                )
                for rel in ordering.outside
            )
        if source:
            issues.extend(
                Issue(
                    note.rel,
                    None,
                    "unsequenced-member",
                    f"the sequence of group {spec.id} in {index_rel} does not list the file",
                    blocking=False,
                )
                for note in ordering.unsequenced
            )
        return ordering

    def _relation_issues(
        self, index_rel: str, index_note: Note, members: list[Note]
    ) -> list[Issue]:
        """Report a contextual relation of an undeclared kind, or between files that are not members."""
        rels = {note.rel for note in members}
        issues: list[Issue] = []
        for relation in index_note.context_relations:
            problems: list[str] = []
            if relation.relation not in self.rules.relations:
                problems.append(
                    f"relation not declared under context_relations in the vocabulary: "
                    f"{relation.relation}"
                )
            problems.extend(
                f"{end} is no member of {index_rel}: {path}"
                for end, path in (
                    ("source", relation.source),
                    ("target", relation.target),
                )
                if path not in rels
            )
            issues.extend(
                Issue(
                    index_rel,
                    None,
                    "invalid-context-relation",
                    problem,
                    locus=pointer("context_relations"),
                    discriminator=f"{relation.source} {relation.relation} {relation.target}",
                )
                for problem in problems
            )
        return issues

    def _external_issues(
        self, index_rel: str, index_note: Note, members: list[Note]
    ) -> list[Issue]:
        """Report a dependency naming no file, or naming a member rather than an outside file."""
        rels = {note.rel for note in members}
        issues: list[Issue] = []
        for spec in index_note.external:
            if not self.exists(spec.target):
                issues.append(
                    Issue(
                        index_rel,
                        None,
                        "invalid-link",
                        f"external names no file: {spec.target}",
                        locus=pointer("external"),
                        discriminator=spec.target,
                    )
                )
            elif spec.target in rels:
                issues.append(
                    Issue(
                        index_rel,
                        None,
                        "invalid-external",
                        f"external names {spec.target}, which {index_rel} lists: external holds "
                        "the files outside the collection",
                        locus=pointer("external"),
                        discriminator=spec.target,
                    )
                )
        return issues

    def _superseded_issues(self, note: Note) -> list[Issue]:
        """Report a successor that is not a link to a file, or held by a note not archived."""
        if "superseded_by" not in note.data:
            return []
        value = note.data["superseded_by"]
        target = link_target(value)
        issues = [
            Issue(
                note.rel,
                None,
                "unarchived-superseded",
                f"superseded_by belongs to an archived note, whereas {problem}",
                locus=pointer("superseded_by"),
            )
            for problem in self.rules.check_superseded(note.status)
        ]
        if target is None or not self.exists(target):
            issues.append(
                Issue(
                    note.rel,
                    None,
                    "invalid-link",
                    (
                        f"superseded_by is not a link [Title](path.md): {value}"
                        if target is None
                        else f"superseded_by names no file: {target}"
                    ),
                    locus=pointer("superseded_by"),
                )
            )
        return issues

    def _member_issues(self, note: Note, spec: GroupSpec, index_rel: str) -> list[Issue]:
        """Report the title, the index, the purpose and the blockers of a listed member.

        A member without a metadata source, such as a PDF, cannot declare these fields, so it is
        titled by its file name and raises none of these issues.
        """
        if not note.reads_metadata:
            return []
        issues: list[Issue] = []
        if not note.title:
            issues.append(
                Issue(
                    note.rel,
                    None,
                    "missing-alias",
                    "a listed file declares no alias, whose first is its title",
                    locus=pointer("aliases"),
                )
            )
        elif note.rel.endswith(".md") and (
            note.heading is None or EMPHASIS.sub("", note.heading) != EMPHASIS.sub("", note.title)
        ):
            issues.append(
                Issue(
                    note.rel,
                    None,
                    "title-mismatch",
                    f"the H1 heading {note.heading!r} differs from the first alias "
                    f"{note.title!r}",
                    locus=pointer("aliases"),
                )
            )
        if note.index != index_rel:
            issues.append(
                Issue(
                    note.rel,
                    None,
                    "index-location",
                    f"index names {note.index}, whereas the file is listed by {index_rel}",
                    locus=pointer("index"),
                )
            )
        # A purpose is owed where a group displays it; a registry displaying titles needs none.
        if "purpose" in spec.show and not note.purpose:
            issues.append(
                Issue(
                    note.rel,
                    None,
                    "missing-purpose",
                    "the group displays a purpose, which the file does not declare",
                    blocking=False,
                    locus=pointer("purpose"),
                )
            )
        for identifier in note.blocked_by:
            if identifier not in self.tasks:
                issues.append(
                    Issue(
                        note.rel,
                        None,
                        "unknown-task",
                        f"blocked_by names no declared task: {identifier}",
                        locus=pointer("blocked_by"),
                        discriminator=identifier,
                    )
                )
            elif self.tasks[identifier]:
                issues.append(
                    Issue(
                        note.rel,
                        None,
                        "finished-blocker",
                        f"the task {identifier} is closed, so the status may advance",
                        blocking=False,
                        locus=pointer("blocked_by"),
                        discriminator=identifier,
                    )
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
                        None,
                        "missing-control-file",
                        f"the type {kind.name} requires {rel}",
                        discriminator=spec.name,
                    )
                )
            elif note is not None and spec.role and note.role != spec.role:
                issues.append(
                    Issue(
                        rel,
                        None,
                        "control-file-role",
                        f"the type {kind.name} expects the role {spec.role}, not {note.role}",
                        locus=pointer("role"),
                    )
                )
        return issues


def nest_members(members: list[Note], path: str) -> tuple[list[Note], list[int], list[Note]]:
    """Place each member beneath the member that its key names, keeping the order of siblings.

    The key is a dotted path into the data of a member; its value, or the first of its values
    naming a member of the group, designates the parent by file stem, by ``id``, or by link. A
    member whose parent lies outside the group stands at the first level. A member that no chain
    of parents connects to the first level, being on a cycle or beneath one, is returned apart so
    that the cycle can be reported. Taken in the order of the group, each of those members not
    yet placed stands at the first level, and its descendants nest beneath it, so the first
    member of a cycle stands at the first level and the others of the cycle beneath it.

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
