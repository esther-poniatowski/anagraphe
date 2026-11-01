"""
Conventions of the references: the syntaxes, the path styles and the strictness admitted in a file.

A convention admits a set of syntaxes (``format``), such as ``markdown``, ``wikilink``, ``code`` or a
declared syntax, and a set of path styles (``path``): ``relative``, ``root``, ``absolute``,
``shortest``, or a declared ``base`` folder. It also names the syntaxes whose targets naming no file
are reported (``strict``). The repository declares a list of rules under ``references.conventions``.
Each rule holds a condition on the path, the type, the metadata or the region of a pointer, and sets
one or more of these keys.

The rules cascade: the built-in rules come first, then each declared rule in its order, and each
matching rule overrides the keys that it sets. The built-in rules admit every syntax, the style
``relative`` in the content of a file and the style ``root`` in its metadata, both styles for a
backticked path, and leave the strictness to each syntax. A condition may also name the syntaxes of
the pointers to which its rule applies.

Examples
--------
>>> rules = parse_conventions([
...     {"format": "markdown"},
...     {"when": {"paths": ["projects/mixture/"]}, "path": {"base": "projects/mixture"}},
...     {"when": {"types": ["yml"]}, "format": ["markdown", "wikilink"]},
... ], "conventions", ("markdown", "wikilink", "code"))
>>> conventions = Conventions(rules)
>>> [str(style) for style in conventions.of("projects/mixture/a.md", Region.CONTENT).styles]
['base projects/mixture']
>>> conventions.of("notes/a.md", Region.CONTENT).formats
('markdown',)
>>> [str(style) for style in conventions.of("notes/a.md", Region.METADATA).styles]
['root']
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

from anagraphe.core.conditions import FILE_KEYS, Condition, parse_condition
from anagraphe.core.configuration import ConfigurationError, known_keys, mapping, strings
from anagraphe.references.model import CODE, RELATIVE, ROOT, Region, Style, StyleKind

#: The keys of a rule, and of its condition.
RULE_KEYS = frozenset({"when", "format", "path", "strict"})
CONDITION_KEYS = FILE_KEYS | {"regions", "syntaxes"}


@dataclass(frozen=True)
class Convention:
    """The syntaxes, the path styles and the strictness admitted for one reference."""

    #: The admitted syntaxes, None for every syntax.
    formats: tuple[str, ...] | None = None
    styles: tuple[Style, ...] = (RELATIVE,)
    #: The syntaxes whose targets naming no file are reported, None for the default of each syntax.
    strict: frozenset[str] | None = None

    def admits(self, syntax: str) -> bool:
        """Whether the convention admits a syntax."""
        return self.formats is None or syntax in self.formats

    def describe(self) -> str:
        """Return the admitted path styles, in words."""
        return " or ".join(str(style) for style in self.styles)


@dataclass(frozen=True)
class ConventionRule:
    """A condition, and the keys that it sets, None for a key that it leaves."""

    condition: Condition = Condition()
    regions: frozenset[Region] = frozenset()
    #: The syntaxes of the pointers to which the rule applies, empty for every syntax.
    syntaxes: frozenset[str] = frozenset()
    formats: tuple[str, ...] | None = None
    styles: tuple[Style, ...] | None = None
    strict: frozenset[str] | None = None

    def holds(
        self,
        rel: str,
        region: Region,
        syntax: str,
        metadata: Callable[[str], Mapping[str, Any]] | None,
    ) -> bool:
        """Whether a reference of a file, in a region and a syntax, meets the condition of the rule."""
        if self.regions and region not in self.regions:
            return False
        if self.syntaxes and syntax not in self.syntaxes:
            return False
        return self.condition.holds(rel, metadata)


#: The built-in rules, before every declared rule. A backticked path is customarily written from
#: its file or from the root, so both styles are admitted for it.
BUILT_IN = (
    ConventionRule(styles=(RELATIVE,)),
    ConventionRule(regions=frozenset({Region.METADATA}), styles=(ROOT,)),
    ConventionRule(syntaxes=frozenset({CODE}), styles=(RELATIVE, ROOT)),
)


@dataclass(frozen=True)
class Conventions:
    """The cascade of the rules of a repository."""

    rules: tuple[ConventionRule, ...] = ()
    metadata: Callable[[str], Mapping[str, Any]] | None = field(default=None, compare=False)

    def of(self, rel: str, region: Region, syntax: str = "") -> Convention:
        """Return the convention of a reference of a file, written in a region and a syntax."""
        formats: tuple[str, ...] | None = None
        styles: tuple[Style, ...] = (RELATIVE,)
        strict: frozenset[str] | None = None
        for rule in (*BUILT_IN, *self.rules):
            if rule.holds(rel, region, syntax, self.metadata):
                formats = rule.formats if rule.formats is not None else formats
                styles = rule.styles if rule.styles is not None else styles
                strict = rule.strict if rule.strict is not None else strict
        return Convention(formats, styles, strict)

    def bases(self) -> tuple[str, ...]:
        """Return the folders of the styles ``base`` that a rule declares."""
        return tuple(
            sorted(
                {
                    style.folder
                    for rule in self.rules
                    for style in rule.styles or ()
                    if style.kind is StyleKind.BASE
                }
            )
        )


def _listed(value: Any) -> list[Any]:
    """Return a value as a list, a single value as a list of one."""
    return value if isinstance(value, list) else [value]


def _names(value: Any, field_name: str, names: Iterable[str]) -> tuple[str, ...] | None:
    """Parse a set of syntax names: one name, or a list of names."""
    if value is None:
        return None
    admitted = tuple(names)
    found: list[str] = []
    for item in _listed(value):
        if item not in admitted:
            raise ConfigurationError(
                f"{field_name} must name syntaxes among: {', '.join(admitted)}"
            )
        found.append(str(item))
    return tuple(found)


def _styles(value: Any, field_name: str) -> tuple[Style, ...] | None:
    """Parse the path styles of a rule: a style name, a mapping ``{base: folder}``, or a list."""
    if value is None:
        return None
    names = [kind.value for kind in StyleKind if kind is not StyleKind.BASE]
    styles: list[Style] = []
    for item in _listed(value):
        if isinstance(item, Mapping):
            folder = item.get("base")
            if set(item) != {"base"} or not isinstance(folder, str) or not folder.strip("/"):
                raise ConfigurationError(
                    f"{field_name} must write a base folder as {{base: folder}}"
                )
            styles.append(Style(StyleKind.BASE, folder.strip("/")))
        elif item in names:
            styles.append(Style(StyleKind(item)))
        else:
            raise ConfigurationError(
                f"{field_name} must name styles among: {', '.join(names)}, or {{base: folder}}"
            )
    return tuple(styles)


def _regions(raw: Mapping[str, Any], field_name: str) -> frozenset[Region]:
    """Parse the regions of a condition: ``metadata``, ``content``, or both."""
    regions = strings(
        _listed(raw["regions"]) if "regions" in raw else None, f"{field_name}.regions"
    )
    unknown = sorted(regions - {region.value for region in Region})
    if unknown:
        raise ConfigurationError(
            f"{field_name}.regions names unknown regions: {', '.join(unknown)}; "
            f"admitted regions: {', '.join(region.value for region in Region)}"
        )
    return frozenset(Region(region) for region in regions)


def parse_conventions(
    value: Any, field_name: str, names: Iterable[str]
) -> tuple[ConventionRule, ...]:
    """Parse the list of rules, the names of the declared syntaxes checking ``format`` and ``strict``."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ConfigurationError(
            f"{field_name} must be a list of rules {{when, format, path, strict}}"
        )
    syntaxes = tuple(names)
    rules: list[ConventionRule] = []
    for number, entry in enumerate(value, start=1):
        item = f"{field_name}[{number}]"
        raw = mapping(entry, item)
        known_keys(raw, RULE_KEYS, item)
        if not {"format", "path", "strict"} & set(raw):
            raise ConfigurationError(f"{item} must set a format, a path style, or a strictness")
        condition, rest = parse_condition(raw.get("when"), f"{item}.when", CONDITION_KEYS)
        strict = _names(raw.get("strict"), f"{item}.strict", syntaxes)
        applies = _names(rest.get("syntaxes"), f"{item}.when.syntaxes", syntaxes) or ()
        rules.append(
            ConventionRule(
                condition,
                _regions(rest, f"{item}.when"),
                frozenset(applies),
                _names(raw.get("format"), f"{item}.format", syntaxes),
                _styles(raw.get("path"), f"{item}.path"),
                frozenset(strict) if strict is not None else None,
            )
        )
    return tuple(rules)
