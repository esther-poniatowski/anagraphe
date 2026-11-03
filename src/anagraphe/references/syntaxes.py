"""
The syntaxes in which the pointers of a repository are written, declared as one registry.

A syntax finds the candidate pointers of one notation in the text of a file. Four syntaxes are
built in:

- ``markdown``, the links and embeds ``[text](path)``;
- ``wikilink``, the links and embeds ``[[path#^anchor|alias]]``, which may omit the suffix ``.md``;
- ``code``, a path written alone in a code span, such as ``notes/a.md`` between backticks;
- ``latex``, the targets of ``\\input``, ``\\include``, ``\\subfile``, ``\\includegraphics``,
  ``\\includepdf``, ``\\lstinputlisting`` and ``\\addbibresource``, which may omit their suffix.

A repository declares further syntaxes by name under ``references.syntaxes``: a ``pattern`` syntax
finds its targets by a regular expression with a group ``target``, and a ``keys`` syntax reads the
values of keys of a YAML, JSON or TOML document. A built-in syntax may be redefined: its condition
``when``, the suffixes it may ``omit``, whether a target naming no file is reported (``unresolved``),
and whether it is ``enabled``.

The three syntaxes of Markdown read the regions of Merismos, the span library: the link
destinations and the code spans of a file, each with its exact offset. A link inside a code block,
a code span or mathematics is therefore an example, found by no syntax.

A candidate naming a file is a pointer. A candidate naming no file is reported as broken only when
its syntax reports unresolved targets, since a code span or a string of code may hold a path that is
an example, a command or no path at all.
"""

from __future__ import annotations

import bisect
import json
import re
import tomllib
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Mapping, Protocol

import yaml

from anagraphe.core.conditions import Condition, parse_condition
from anagraphe.core.configuration import ConfigurationError, known_keys, mapping, strings_in_order
from anagraphe.core.links import VALUE_LINK, VALUE_WIKILINK
from anagraphe.core.regions import CODE_KIND, markdown_regions
from anagraphe.references.model import (
    CODE,
    LATEX,
    MARKDOWN,
    WIKILINK as WIKILINK_NAME,
    Form,
    Reference,
    Region,
)

#: The name of each link syntax of Merismos among the syntaxes of Anagraphe.
LINK_SYNTAXES = {"markdown": MARKDOWN, "wiki": WIKILINK_NAME}
#: A path written alone: segments of path characters, each closing on no period.
SEGMENT = r"[\w~@+%-](?:[\w.~@+%-]*[\w~@+%-])?"
PATH_TOKEN = re.compile(rf"(?:\.{{1,2}}/)*{SEGMENT}(?:/{SEGMENT})*/?(?:#[\w^%-]+)?")
#: The commands of LaTeX naming a file, capturing a target written without a macro.
LATEX_COMMANDS = (
    r"\\(?:input|include|subfile|includegraphics|includepdf|lstinputlisting|addbibresource)"
    r"(?:\[[^\]]*\])?\{(?P<target>[^{}\\#\n]+)\}"
)
#: The suffixes that a LaTeX command may omit.
LATEX_SUFFIXES = (".tex", ".pdf", ".png", ".jpg", ".jpeg", ".eps", ".svg", ".bib")
#: The keys of a syntax; a built-in syntax admits only the keys that redefine it.
SYNTAX_KEYS = frozenset(
    {"when", "pattern", "keys", "form", "omit", "unresolved", "comment", "enabled"}
)
BUILT_IN_KEYS = frozenset({"when", "omit", "unresolved", "enabled"})
#: The resolved tag of a YAML string scalar.
STRING_TAG = "tag:yaml.org,2002:str"


class ExtractionError(ValueError):
    """Report a file whose syntax prevents the extraction of its references."""


@dataclass(frozen=True)
class Candidate:
    """One candidate pointer: its offset, its raw target, and the syntax of a link held by a field."""

    start: int
    raw: str
    exact: bool = True
    #: The link syntax of a value of a field, ``markdown`` or ``wikilink``, None for the syntax itself.
    link: str | None = None


def shaped(token: str) -> bool:
    """Whether a token can be a path: it holds a slash, or names a file with a suffix.

    Examples
    --------
    >>> [shaped(token) for token in ("exchanges", "a.md", "exchanges/", "m/a.md")]
    [False, True, True, True]
    """
    return "/" in token or "." in token.strip(".")


def blank(match: re.Match[str]) -> str:
    """Return spaces as long as a match, so that the columns of its line are kept."""
    return " " * len(match.group(0))


class Syntax(Protocol):
    """One notation of pointers: where it applies, and how it finds its candidates."""

    name: str
    condition: Condition
    #: The suffixes that a target may omit.
    omit: tuple[str, ...]
    #: Whether a target naming no file is reported, by default.
    reports_unresolved: bool
    #: Whether a target is percent-encoded.
    encoded: bool
    enabled: bool

    def find(self, text: str) -> Iterator[Candidate]:
        """Yield the candidate pointers of a text, in the order of the text."""
        raise NotImplementedError


@dataclass(frozen=True)
class MarkdownLinks:
    """The links and embeds ``[text](path)``, read from the link destinations of Merismos."""

    name: str = MARKDOWN
    condition: Condition = Condition(types=frozenset({"md"}))
    omit: tuple[str, ...] = ()
    reports_unresolved: bool = True
    encoded: bool = True
    enabled: bool = True

    def find(self, text: str) -> Iterator[Candidate]:
        for region in markdown_regions(text):
            if LINK_SYNTAXES.get(region.link or "") == self.name and region.text:
                yield Candidate(region.start, region.text)


@dataclass(frozen=True)
class WikiLinks:
    """The links and embeds ``[[path#^anchor|alias]]``, read from the link destinations of Merismos."""

    name: str = WIKILINK_NAME
    condition: Condition = Condition(types=frozenset({"md"}))
    omit: tuple[str, ...] = (".md",)
    reports_unresolved: bool = True
    encoded: bool = False
    enabled: bool = True

    def find(self, text: str) -> Iterator[Candidate]:
        for region in markdown_regions(text):
            if LINK_SYNTAXES.get(region.link or "") == self.name and region.text:
                yield Candidate(region.start, region.text)


@dataclass(frozen=True)
class CodePaths:
    """A path written alone in a code span, such as ``notes/a.md`` between backticks."""

    name: str = CODE
    condition: Condition = Condition(types=frozenset({"md"}))
    omit: tuple[str, ...] = ()
    reports_unresolved: bool = False
    encoded: bool = False
    enabled: bool = True

    def find(self, text: str) -> Iterator[Candidate]:
        for region in markdown_regions(text):
            if region.kind != CODE_KIND:
                continue
            token = region.text.strip()
            if PATH_TOKEN.fullmatch(token) and shaped(token.split("#")[0]):
                yield Candidate(region.start + region.text.index(token), token)


@dataclass(frozen=True)
class PatternSyntax:
    """Targets found by a regular expression with a group ``target``, outside comments."""

    name: str
    condition: Condition
    pattern: re.Pattern[str]
    omit: tuple[str, ...] = ()
    reports_unresolved: bool = True
    encoded: bool = False
    #: A marker opening a comment to the end of its line, whose targets are not read.
    comment: str | None = None
    enabled: bool = True

    def find(self, text: str) -> Iterator[Candidate]:
        if self.comment:
            marker = re.compile(rf"(?<!\\){re.escape(self.comment)}[^\n]*")
            text = marker.sub(blank, text)
        for match in re.finditer(self.pattern, text):
            target = match["target"].strip()
            if target:
                yield Candidate(match.start("target") + match["target"].index(target), target)


@dataclass(frozen=True)
class FieldSyntax:
    """The values of declared keys of a YAML, JSON or TOML document, at any depth."""

    name: str
    condition: Condition
    keys: frozenset[str]
    form: Form = Form.PATH
    omit: tuple[str, ...] = ()
    reports_unresolved: bool = True
    encoded: bool = False
    enabled: bool = True

    def find(self, text: str) -> Iterator[Candidate]:
        raise NotImplementedError("a field syntax reads a document; call find_in")

    def find_in(self, rel: str, text: str) -> Iterator[Candidate]:
        """Yield the candidates of the declared keys of a document, read by the suffix of its file."""
        if rel.endswith((".json", ".toml")):
            yield from self._plain(rel, text)
            return
        try:
            documents = list(yaml.compose_all(text, Loader=yaml.SafeLoader))
        except yaml.YAMLError as error:
            raise ExtractionError(f"cannot parse the record: {error}") from error
        for document in documents:
            if document is not None:
                yield from self._walk(text, document)

    def _walk(self, text: str, node: yaml.Node) -> Iterator[Candidate]:
        """Yield the candidates of the declared keys below one node, in the order of the text."""
        if isinstance(node, yaml.MappingNode):
            for key, value in node.value:
                if isinstance(key, yaml.ScalarNode) and key.value in self.keys:
                    scalars = value.value if isinstance(value, yaml.SequenceNode) else [value]
                    for scalar in scalars:
                        if isinstance(scalar, yaml.ScalarNode) and scalar.tag == STRING_TAG:
                            yield from self._located(
                                text, scalar.value, scalar.start_mark.index, scalar.end_mark.index
                            )
                else:
                    yield from self._walk(text, value)
        elif isinstance(node, yaml.SequenceNode):
            for item in node.value:
                yield from self._walk(text, item)

    def _plain(self, rel: str, text: str) -> Iterator[Candidate]:
        """Yield the candidates of a JSON or TOML document, each value located by its text."""
        try:
            document = json.loads(text) if rel.endswith(".json") else tomllib.loads(text)
        except ValueError as error:
            raise ExtractionError(f"cannot parse the document: {error}") from error
        position = 0
        for value in self._values(document):
            found = text.find(value, position)
            if found == -1:
                continue
            position = found + len(value)
            yield from self._located(text, value, found, found + len(value))

    def _values(self, node: Any) -> Iterator[str]:
        """Yield the string values of the declared keys of a parsed document, in document order."""
        if isinstance(node, dict):
            for key, value in node.items():
                if key in self.keys:
                    for item in value if isinstance(value, list) else [value]:
                        if isinstance(item, str):
                            yield item
                else:
                    yield from self._values(value)
        elif isinstance(node, list):
            for item in node:
                yield from self._values(item)

    def _located(self, text: str, value: str, start: int, end: int) -> Iterator[Candidate]:
        """Yield the candidate of one value, located at the characters spelling its target."""
        link: str | None = None
        raw = value
        if self.form is Form.LINK:
            markdown, wiki = VALUE_LINK.match(value), VALUE_WIKILINK.match(value)
            if markdown:
                raw, link = markdown.group(1), MARKDOWN
            elif wiki:
                raw, link = wiki.group(1), WIKILINK_NAME
            else:
                return
        if not raw:
            return
        prefix = {MARKDOWN: "(", WIKILINK_NAME: "[["}.get(link or "", "")
        found = text.find(prefix + raw, start, end)
        if found == -1:
            yield Candidate(start, raw, exact=False, link=link)
        else:
            yield Candidate(found + len(prefix), raw, link=link)


#: The built-in syntaxes, by name.
BUILT_IN: dict[str, Any] = {
    MARKDOWN: MarkdownLinks(),
    WIKILINK_NAME: WikiLinks(),
    CODE: CodePaths(),
    LATEX: PatternSyntax(
        LATEX,
        Condition(types=frozenset({"tex", "sty", "cls"})),
        re.compile(LATEX_COMMANDS),
        LATEX_SUFFIXES,
        comment="%",
    ),
}


@dataclass(frozen=True)
class Syntaxes:
    """The enabled syntaxes of a repository, built-in and declared, in their order."""

    items: tuple[Any, ...] = tuple(BUILT_IN.values())
    metadata: Callable[[str], Mapping[str, Any]] | None = field(default=None, compare=False)

    def covering(self, rel: str) -> list[Any]:
        """Return the enabled syntaxes whose condition holds for a file."""
        return [
            syntax
            for syntax in self.items
            if syntax.enabled and syntax.condition.holds(rel, self.metadata)
        ]

    def names(self) -> tuple[str, ...]:
        """Return the names of every syntax, enabled or not."""
        return tuple(syntax.name for syntax in self.items)

    def strict(self) -> frozenset[str]:
        """Return the names of the syntaxes reporting a target that names no file, by default."""
        return frozenset(syntax.name for syntax in self.items if syntax.reports_unresolved)


def _unresolved(value: Any, default: bool, field_name: str) -> bool:
    """Parse whether a syntax reports a target naming no file: ``report`` or ``ignore``."""
    if value is None:
        return default
    if value not in ("report", "ignore"):
        raise ConfigurationError(f"{field_name} must be report or ignore")
    return bool(value == "report")


def _enabled(value: Any, field_name: str) -> bool:
    """Parse whether a syntax is enabled."""
    if value is None:
        return True
    if not isinstance(value, bool):
        raise ConfigurationError(f"{field_name} must be a boolean")
    return value


def _declared(name: str, raw: Mapping[str, Any], field_name: str) -> Any:
    """Parse a syntax declared by the repository, a pattern or a set of keys."""
    known_keys(raw, SYNTAX_KEYS, field_name)
    if ("pattern" in raw) == ("keys" in raw):
        raise ConfigurationError(f"{field_name} must declare exactly one of pattern and keys")
    condition, _ = parse_condition(raw.get("when"), f"{field_name}.when")
    omit = strings_in_order(raw.get("omit"), f"{field_name}.omit")
    unresolved = _unresolved(raw.get("unresolved"), True, f"{field_name}.unresolved")
    enabled = _enabled(raw.get("enabled"), f"{field_name}.enabled")
    if "pattern" in raw:
        try:
            pattern = re.compile(str(raw["pattern"]))
        except re.error as error:
            raise ConfigurationError(f"{field_name}.pattern is invalid: {error}") from error
        if "target" not in pattern.groupindex:
            raise ConfigurationError(f"{field_name}.pattern must capture a group named target")
        comment = raw.get("comment")
        if comment is not None and (not isinstance(comment, str) or not comment):
            raise ConfigurationError(f"{field_name}.comment must be a comment marker, such as #")
        return PatternSyntax(name, condition, pattern, omit, unresolved, False, comment, enabled)
    keys = frozenset(strings_in_order(raw.get("keys"), f"{field_name}.keys"))
    if not keys:
        raise ConfigurationError(f"{field_name}.keys must name at least one key")
    form_value = raw.get("form", Form.PATH.value)
    if form_value not in (Form.PATH.value, Form.LINK.value):
        raise ConfigurationError(f"{field_name}.form must be path or link")
    return FieldSyntax(name, condition, keys, Form(form_value), omit, unresolved, False, enabled)


def parse_syntaxes(
    value: Any, field_name: str, metadata: Callable[[str], Mapping[str, Any]] | None = None
) -> Syntaxes:
    """Parse the syntaxes: redefinitions of the built-in ones, and new ones by name."""
    raw = mapping(value, field_name)
    items: dict[str, Any] = dict(BUILT_IN)
    for name, entry in raw.items():
        item = f"{field_name}.{name}"
        definition = mapping(entry, item)
        if name in BUILT_IN:
            known_keys(definition, BUILT_IN_KEYS, item)
            base = BUILT_IN[name]
            condition = (
                parse_condition(definition["when"], f"{item}.when")[0]
                if "when" in definition
                else base.condition
            )
            omit = (
                strings_in_order(definition["omit"], f"{item}.omit")
                if "omit" in definition
                else base.omit
            )
            items[name] = type(base)(
                **{
                    **{key: getattr(base, key) for key in base.__dataclass_fields__},
                    "condition": condition,
                    "omit": omit,
                    "reports_unresolved": _unresolved(
                        definition.get("unresolved"), base.reports_unresolved, f"{item}.unresolved"
                    ),
                    "enabled": _enabled(definition.get("enabled"), f"{item}.enabled"),
                }
            )
        else:
            items[str(name)] = _declared(str(name), definition, item)
    return Syntaxes(tuple(items.values()), metadata)


@dataclass(frozen=True)
class Found:
    """One reference, the syntax that found it, and whether that syntax reports it by default."""

    reference: Reference
    syntax: str
    reports_unresolved: bool


def references_of(
    rel: str, text: str, syntaxes: list[Any], regions: list[tuple[int, int]]
) -> Iterator[Found]:
    """Yield the references of a file found by its syntaxes, each in its region.

    A value of a field written as a link takes the syntax of the link, for its convention and its
    encoding, and the strictness of its field.
    """
    starts = [0, *(index + 1 for index, char in enumerate(text) if char == "\n")]
    for syntax in syntaxes:
        candidates: Iterator[Candidate] = (
            syntax.find_in(rel, text) if isinstance(syntax, FieldSyntax) else syntax.find(text)
        )
        for candidate in candidates:
            number = bisect.bisect_right(starts, candidate.start)
            region = (
                Region.METADATA
                if any(start <= candidate.start < end for start, end in regions)
                else Region.CONTENT
            )
            fmt = candidate.link or syntax.name
            yield Found(
                Reference(
                    rel,
                    number,
                    candidate.start - starts[number - 1] + 1,
                    candidate.raw,
                    region,
                    fmt,
                    encoded=fmt == MARKDOWN,
                    exact=candidate.exact,
                    omit=(".md",) if candidate.link == WIKILINK_NAME else syntax.omit,
                ),
                syntax.name,
                syntax.reports_unresolved,
            )
