"""
The check of the bindings of a repository: every required text is bound, and every declaration,
source and schema mark is valid.

The check reads each selected file that may declare a role, or that a condition ``required``
selects: a text read through its frontmatter, and a record when the repository declares records.
A required file bound to no value for a role is reported, and so is each invalid declaration, each
file whose frontmatter or record cannot be parsed, and each defect of the schemas reached by the
marks ``x-binds``. The check writes no file.
"""

from __future__ import annotations

from pathlib import Path

from anagraphe.bindings.configuration import BindingConfig
from anagraphe.bindings.kinds import INVALID, KINDS, UNBOUND, UNREADABLE_SOURCE
from anagraphe.bindings.model import Role
from anagraphe.bindings.resolution import BindingResolver
from anagraphe.core.files import select
from anagraphe.core.issues import Issue, Report
from anagraphe.core.metadata import SourceKind

__all__ = ["KINDS", "BindingChecker"]


class BindingChecker:
    """Check the bindings of one repository against its declaration."""

    def __init__(self, root: Path, config: BindingConfig) -> None:
        self.root = root.resolve()
        self.config = config
        self.resolver = BindingResolver(self.root, config)

    def covers(self, rel: str) -> bool:
        """Whether a file may declare a role, or must be bound for one."""
        metadata = self.resolver.metadata
        if metadata.source_of(rel).kind is SourceKind.FRONTMATTER or self.resolver.is_record(rel):
            return True
        return any(
            spec.required is not None and spec.required.holds(rel, metadata)
            for spec in self.config.roles.values()
        )

    def check(self, paths: tuple[Path, ...] = (), strict: bool = True) -> Report:
        """Check the files below the given targets, the whole repository without a target."""
        files = select(self.root, paths, self.config.exemptions, self.covers, strict)
        issues: list[Issue] = []
        for rel in files:
            issues.extend(self.check_file(rel))
        issues.extend(
            Issue(
                entry.rel,
                None,
                INVALID,
                f"{entry.role}: {entry.pointer} names no value, or a value that is not a "
                "non-empty string",
                locus=entry.pointer,
                discriminator=entry.role,
            )
            for entry in self.resolver.invalid
        )
        issues.extend(
            Issue(entry.rel, None, UNREADABLE_SOURCE, entry.detail)
            for entry in self.resolver.unreadable
        )
        schemas = self.resolver.schemas
        if schemas is not None:
            for contract in schemas.contracts():
                schemas.fields(contract)
            issues.extend(
                Issue(problem.rel, None, problem.kind, problem.detail, locus=problem.pointer)
                for problem in schemas.problems
            )
        return Report(len(files), tuple(_distinct(issues)))

    def check_file(self, rel: str) -> list[Issue]:
        """Return the issues of one file: an unbound text, for each role requiring it."""
        issues: list[Issue] = []
        for name, spec in self.config.roles.items():
            # Each declaration of the file is read, so that an invalid value is reported.
            self.resolver.own(rel, name)
            if spec.required is None or not spec.required.holds(rel, self.resolver.metadata):
                continue
            if not self.resolver.resolve(rel, Role(name)).bound:
                issues.append(
                    Issue(
                        rel,
                        None,
                        UNBOUND,
                        f"{name}: no declaration binds the text, in its own metadata or in the "
                        f"index {self.config.index} of an enclosing directory",
                        discriminator=name,
                    )
                )
        return issues


def _distinct(issues: list[Issue]) -> list[Issue]:
    """Return the issues in their order, each identity once."""
    seen: set[tuple[str, str, str, str]] = set()
    kept: list[Issue] = []
    for issue in issues:
        identity = (issue.rel, issue.kind, issue.locus, issue.discriminator)
        if identity not in seen:
            seen.add(identity)
            kept.append(issue)
    return kept
