"""
The rules that a reference obeys, each reporting one kind of issue.

A rule reads one evaluated reference, :class:`Subject`, and returns its :class:`Breach`, or None
when the reference obeys it. The registry :data:`RULES` fixes the kinds and their order of
report. A repository silences a kind under ``references.ignore``, and a new rule extends the check
by joining the registry.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from anagraphe.core.conditions import Condition
from anagraphe.core.filters import scalars
from anagraphe.core.links import Target
from anagraphe.references.anchors import has_block_anchor
from anagraphe.references.conventions import Convention
from anagraphe.references.model import MARKDOWN, WIKILINK, Fragments, Reference
from anagraphe.references.resolution import Resolution


@dataclass(frozen=True)
class Breach:
    """The issue that a reference raises under one rule: its detail, and whether it blocks."""

    detail: str
    blocking: bool = True


@dataclass(frozen=True)
class Unlinkable:
    """Files that the other files must not cite, such as notes unfiled or superseded.

    A pointer written in one of ``syntaxes`` and citing a file that ``target`` selects breaks the
    declaration, unless its holding file meets ``unless``. A file that ``target`` selects may cite
    the files that ``target`` selects.
    """

    target: Condition
    unless: Condition | None = None
    blocking: bool = True
    syntaxes: frozenset[str] = frozenset({MARKDOWN, WIKILINK})

    def reason(self, metadata: Mapping[str, Any]) -> str:
        """Return what makes a selected file unlinkable: the values of the filter selecting it.

        Examples
        --------
        >>> from anagraphe.core.filters import Filter
        >>> rule = Unlinkable(Condition(filters=(Filter((("status", ("inbox",)),)),)))
        >>> rule.reason({"status": "inbox"})
        'has status inbox'
        >>> Unlinkable(Condition(("/drafts/",))).reason({})
        'lies at an unlinkable path'
        """
        for selected in self.target.filters:
            if selected.selects(metadata):
                values = (
                    f"{key} {', '.join(scalars(metadata.get(key)))}"
                    for key, _ in selected.conditions
                )
                return "has " + " and ".join(values)
        return "lies at an unlinkable path"


def _no_metadata(_rel: str) -> Mapping[str, Any]:
    """Return the empty metadata of a file, for a context declaring no metadata source."""
    return {}


def _no_exclusion(_rel: str) -> bool:
    """Return that no file is excluded, for a context declaring no exclusion."""
    return False


@dataclass(frozen=True)
class Subject:
    """One reference, the parts of its target, and the files that its path names."""

    reference: Reference
    target: Target
    #: None for a target carrying a URL scheme, which resolves outside the repository.
    resolution: Resolution | None
    #: The link formats and the path styles that the reference admits.
    convention: Convention = Convention()

    @property
    def cited(self) -> Path | None:
        """Return the cited file, under an admitted style first."""
        if self.resolution is None:
            return None
        return self.resolution.under(self.convention.styles) or self.resolution.cited


@dataclass(frozen=True)
class RuleContext:
    """The declarations and the file access that the rules share."""

    #: The URL schemes resolved outside the repository, in lowercase.
    schemes: frozenset[str]
    fragments: Fragments
    #: Return the text of a file, each file read once.
    read: Callable[[Path], str]
    #: The root of the repository, from which the paths of an issue are written.
    root: Path = Path(".")
    #: Return the metadata of a repository-relative file, read from its declared source.
    metadata: Callable[[str], Mapping[str, Any]] = field(default=_no_metadata)
    #: The files that the other files must not cite.
    unlinkable: tuple[Unlinkable, ...] = ()
    #: Whether the section excludes a repository-relative file by its path.
    excluded: Callable[[str], bool] = field(default=_no_exclusion)


class Rule(Protocol):
    """One rule of the references, reporting one kind of issue."""

    @property
    def kind(self) -> str:
        """Return the kind of issue reported by the rule."""
        raise NotImplementedError

    @property
    def description(self) -> str:
        """Return the one-sentence description of the kind, listed in a findings log."""
        raise NotImplementedError

    def check(self, subject: Subject, context: RuleContext) -> Breach | None:
        """Return the breach of a reference, None when the reference obeys."""
        raise NotImplementedError


@dataclass(frozen=True)
class ForeignScheme:
    """A target carries a URL scheme that no reader of the repository resolves.

    An editor writes an absolute address, such as ``vscode-webview://``, valid in one window only.
    """

    kind: str = "foreign-scheme"
    description: str = "A target carries a URL scheme outside the declared schemes."

    def check(self, subject: Subject, context: RuleContext) -> Breach | None:
        scheme = subject.target.scheme
        if scheme is None or scheme in context.schemes:
            return None
        return Breach(f"no reader resolves the scheme {scheme}")


@dataclass(frozen=True)
class HeadingFragment:
    """A fragment opens on no caret, as the slug of a heading does, where only blocks are admitted."""

    kind: str = "heading-fragment"
    description: str = "A fragment names a heading, where only block anchors are admitted."

    def check(self, subject: Subject, context: RuleContext) -> Breach | None:
        fragment = subject.target.fragment
        if (
            context.fragments is not Fragments.BLOCK
            or subject.resolution is None
            or not fragment
            or fragment.startswith("^")
        ):
            return None
        return Breach(f"the fragment #{fragment} is no block anchor #^name")


@dataclass(frozen=True)
class Broken:
    """The path of a target names no file under any path style."""

    kind: str = "broken"
    description: str = "The path of a strict syntax names no file."

    def check(self, subject: Subject, context: RuleContext) -> Breach | None:
        resolution = subject.resolution
        if (
            resolution is None
            or resolution.resolved
            or resolution.outside is not None
            or resolution.ambiguous
        ):
            return None
        return Breach("names no file, from the folder of the file nor from the repository root")


@dataclass(frozen=True)
class AmbiguousLink:
    """The end of a path names several files, and no other style names one."""

    kind: str = "ambiguous-link"
    description: str = "The end of a path names several files."

    def check(self, subject: Subject, context: RuleContext) -> Breach | None:
        resolution = subject.resolution
        if resolution is None or resolution.resolved or not resolution.ambiguous:
            return None
        root = context.root
        names = ", ".join(path.relative_to(root).as_posix() for path in resolution.ambiguous)
        return Breach(f"names several files: {names}")


@dataclass(frozen=True)
class OutsideRepository:
    """The path of a target names a file outside the repository, which resolves on one machine only."""

    kind: str = "outside-repository"
    description: str = "The path of a target names a file outside the repository."

    def check(self, subject: Subject, context: RuleContext) -> Breach | None:
        resolution = subject.resolution
        if resolution is None or resolution.resolved or resolution.outside is None:
            return None
        return Breach("names a file outside the repository")


@dataclass(frozen=True)
class PathStyle:
    """The path of a target names a file only under a path style that its convention leaves out."""

    kind: str = "convention"
    description: str = "A path names its file only under a path style left out by its convention."

    def check(self, subject: Subject, context: RuleContext) -> Breach | None:
        resolution, convention = subject.resolution, subject.convention
        if resolution is None or not resolution.resolved:
            return None
        if any(style in resolution.resolved for style in convention.styles):
            return None
        written = " or ".join(str(style) for style in resolution.resolved)
        return Breach(
            f"a pointer of the {subject.reference.region} must be written {convention.describe()}, "
            f"not {written}"
        )


@dataclass(frozen=True)
class LinkFormat:
    """A pointer naming a file is written in a syntax that its convention leaves out."""

    kind: str = "link-format"
    description: str = "A pointer is written in a syntax that its convention leaves out."

    def check(self, subject: Subject, context: RuleContext) -> Breach | None:
        written, convention = subject.reference.format, subject.convention
        if convention.admits(written) or subject.resolution is None:
            return None
        names = " or ".join(convention.formats or ())
        return Breach(
            f"a pointer of the {subject.reference.region} must be written as {names}, "
            f"not {written}"
        )


@dataclass(frozen=True)
class BrokenAnchor:
    """A fragment ``#^name`` names no block anchor of the cited file."""

    kind: str = "broken-anchor"
    description: str = "A fragment names no block anchor of the cited file."

    def check(self, subject: Subject, context: RuleContext) -> Breach | None:
        fragment = subject.target.fragment
        cited = subject.cited
        if cited is None or not fragment.startswith("^"):
            return None
        if has_block_anchor(context.read(cited), fragment[1:]):
            return None
        return Breach(f"no line of {cited.name} closes on the anchor {fragment}")


@dataclass(frozen=True)
class UnlinkableTarget:
    """A pointer cites a file that the section declares unlinkable, from a file outside it."""

    kind: str = "unlinkable-target"
    description: str = "A pointer cites a file that the declared rules forbid to cite."

    def check(self, subject: Subject, context: RuleContext) -> Breach | None:
        cited = subject.cited
        if not context.unlinkable or cited is None:
            return None
        try:
            rel = cited.relative_to(context.root).as_posix()
        except ValueError:
            return None
        # A file excluded by path, such as a template, holds metadata that is not its own.
        if context.excluded(rel):
            return None
        holder = subject.reference.holder
        # The rule protects the other files from depending on unlinkable material, not that
        # material from itself, so an unlinkable file cites freely.
        if any(entry.target.holds(holder, context.metadata) for entry in context.unlinkable):
            return None
        for entry in context.unlinkable:
            if subject.reference.format not in entry.syntaxes:
                continue
            if not entry.target.holds(rel, context.metadata):
                continue
            if entry.unless is not None and entry.unless.holds(holder, context.metadata):
                continue
            reason = entry.reason(context.metadata(rel))
            return Breach(f"{rel} {reason}, so it must not be cited", entry.blocking)
        return None


#: The rules of the references, in their order of report for one reference.
RULES: tuple[Rule, ...] = (
    ForeignScheme(),
    LinkFormat(),
    HeadingFragment(),
    Broken(),
    AmbiguousLink(),
    OutsideRepository(),
    PathStyle(),
    BrokenAnchor(),
    UnlinkableTarget(),
)
