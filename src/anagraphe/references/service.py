"""
The check of the references of a repository: find, resolve, then apply every rule.

The check reads each selected file through the syntaxes that cover it, locates each candidate in
the metadata or the content of its file, resolves it once, and applies the rules of
:data:`~anagraphe.references.rules.RULES` in their order. A candidate naming no file is a pointer
only when its syntax is strict there. The check writes no file.
"""

from __future__ import annotations

from pathlib import Path

from anagraphe.core.exclusions import Exemptions
from anagraphe.core.files import TextCache, select, walk
from anagraphe.core.issues import Issue, IssueKind, Report, link
from anagraphe.core.links import Target
from anagraphe.core.metadata import MetadataReader
from anagraphe.references.configuration import ReferenceConfig
from anagraphe.references.model import SHORTEST, WIKILINK, Reference
from anagraphe.references.resolution import FileIndex, Resolver
from anagraphe.references.rules import RULES, Rule, RuleContext, Subject
from anagraphe.references.syntaxes import ExtractionError, Found, references_of

#: The kind of issue reported for a file whose syntax prevents the extraction of its references.
UNREADABLE = "unreadable-file"

#: Every kind of issue that the check can report: one per rule, then the unreadable file.
KINDS: tuple[IssueKind, ...] = tuple(IssueKind(rule.kind, rule.description) for rule in RULES) + (
    IssueKind(UNREADABLE, "A document read by a syntax of keys cannot be parsed."),
)


class ReferenceChecker:
    """Check the references of one repository against its declaration."""

    def __init__(
        self, root: Path, config: ReferenceConfig, rules: tuple[Rule, ...] = RULES
    ) -> None:
        self.root = root.resolve()
        self.config = config
        self.rules = tuple(rule for rule in rules if rule.kind not in config.ignored)
        self.read = TextCache()
        self.resolver = Resolver(self.root, config.conventions.bases())
        self.context = RuleContext(config.schemes, config.fragments, self.read, self.root)
        self.metadata = config.metadata or MetadataReader(self.root)

    def _index(self) -> FileIndex:
        """Return the index of the ends of the paths, built on the first pointer that needs it.

        The index lists every file that is not hidden, excluded ones included, since an excluded
        file stays a valid target.
        """
        if self.resolver.index is None:
            self.resolver.index = FileIndex(walk(self.root, self.root, Exemptions()))
        return self.resolver.index

    def covers(self, rel: str) -> bool:
        """Whether one syntax reads a repository-relative file."""
        return bool(self.config.syntaxes.covering(rel))

    def check(self, paths: tuple[Path, ...] = (), strict: bool = True) -> Report:
        """Check the files below the given targets, the whole repository without a target.

        When ``strict``, a named target holding no file read by a syntax raises a
        :class:`~anagraphe.core.files.TargetError`.
        """
        files = select(self.root, paths, self.config.exemptions, self.covers, strict)
        issues = [issue for rel in files for issue in self.check_file(rel)]
        return Report(len(files), tuple(issues))

    def check_file(self, rel: str) -> list[Issue]:
        """Return the issues of the references written in one file."""
        text = self.read(self.root / rel)
        regions = self._regions(rel, text)
        issues: list[Issue] = []
        for syntax in self.config.syntaxes.covering(rel):
            try:
                found = list(references_of(rel, text, [syntax], regions))
            except ExtractionError as error:
                issues.append(Issue(rel, None, UNREADABLE, str(error)))
                continue
            for item in found:
                issues.extend(self.check_reference(item.reference, item))
        return issues

    def check_reference(self, reference: Reference, found: Found | None = None) -> list[Issue]:
        """Return the issues of one reference, one per rule that it breaks.

        A reference naming no file, or carrying a URL scheme, is no pointer when its syntax is not
        strict for its file, so it raises no issue.
        """
        target = Target.parse(reference.raw, decode=reference.encoded)
        syntax = found.syntax if found is not None else reference.format
        convention = self.config.conventions.of(reference.holder, reference.region, syntax)
        default = found.reports_unresolved if found is not None else True
        strict = default if convention.strict is None else syntax in convention.strict
        resolution = None
        if not target.scheme:
            if reference.format == WIKILINK or SHORTEST in convention.styles:
                self._index()
            resolution = self.resolver.resolve(reference, target, convention.styles)
        # A syntax that is not strict yields a pointer only where its target names a file of the
        # repository, since its candidates may be examples, commands or mentions of other projects.
        if not strict and (resolution is None or not resolution.resolved):
            return []
        subject = Subject(reference, target, resolution, convention)
        return [
            Issue(
                reference.holder,
                reference.line,
                rule.kind,
                f"{reference.raw}: {detail}",
                locus=link(reference.raw),
            )
            for rule in self.rules
            if (detail := rule.check(subject, self.context)) is not None
        ]

    def _regions(self, rel: str, text: str) -> list[tuple[int, int]]:
        """Return the spans of a file where its declared source writes its metadata."""
        return self.metadata.region(rel, text)
