"""
The section ``references`` of ``anagraphe.yml``: how the pointers of a repository are written.

The section declares four things:

- the URL schemes that a reader resolves outside the repository;
- the syntaxes of the pointers, built-in or declared, with the files to which each applies;
- the conventions of the syntaxes, the path styles and the strictness, by path, type, metadata or
  region;
- the files left unread, after the shared exclusions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping

from anagraphe.core.configuration import ConfigurationError, known_keys, strings
from anagraphe.core.exclusions import Exemptions, exemptions
from anagraphe.core.metadata import MetadataReader
from anagraphe.references.conventions import Conventions, parse_conventions
from anagraphe.references.model import Fragments
from anagraphe.references.rules import RULES
from anagraphe.references.syntaxes import Syntaxes, parse_syntaxes

#: The keys of the section ``references``.
SECTION_KEYS = frozenset({"exclude", "schemes", "fragments", "syntaxes", "conventions", "ignore"})
#: The retired keys of the section, each with the declaration that replaces it.
RETIRED_KEYS = {
    "markdown": "the files of a syntax under syntaxes.markdown.when, such as {types: [md, yml]}",
    "records": "a syntax of keys under syntaxes, such as {glossary: {when: {...}, keys: [source]}}",
}


@dataclass(frozen=True)
class ReferenceConfig:
    """The resolved declaration of the references of one repository."""

    exemptions: Exemptions = Exemptions()
    #: The URL schemes resolved outside the repository, in lowercase.
    schemes: frozenset[str] = frozenset({"https", "http", "mailto"})
    fragments: Fragments = Fragments.BLOCK
    syntaxes: Syntaxes = Syntaxes()
    conventions: Conventions = Conventions()
    #: The kinds of issue that the check does not report.
    ignored: frozenset[str] = frozenset()
    #: The metadata of each file, read from its declared source.
    metadata: MetadataReader | None = None


def _choice[E: StrEnum](enum: type[E], value: Any, default: E, field: str) -> E:
    """Return the member of an enumeration that a value names, the default when absent."""
    if value is None:
        return default
    try:
        return enum(value)
    except ValueError as error:
        admitted = ", ".join(member.value for member in enum)
        raise ConfigurationError(f"{field} must be one of: {admitted}") from error


def _schemes(value: Any, field: str) -> frozenset[str]:
    """Return the declared schemes, written as a list or as a mapping to their glosses."""
    if value is None:
        return ReferenceConfig.schemes
    names = list(value) if isinstance(value, Mapping) else value
    return frozenset(name.lower() for name in strings(names, field))


def parse_section(
    root: Path,
    raw: Mapping[str, Any],
    shared: Exemptions,
    metadata: MetadataReader | None = None,
    field: str = "references",
) -> ReferenceConfig:
    """Validate and resolve the section ``references``, its exemptions added to the shared ones."""
    for key, replacement in RETIRED_KEYS.items():
        if key in raw:
            raise ConfigurationError(f"{field}.{key} is retired: declare {replacement}")
    known_keys(raw, SECTION_KEYS, field)
    ignored = strings(raw.get("ignore"), f"{field}.ignore")
    unknown = sorted(ignored - {rule.kind for rule in RULES})
    if unknown:
        raise ConfigurationError(
            f"{field}.ignore names unknown kinds: {', '.join(unknown)}; "
            f"admitted kinds: {', '.join(rule.kind for rule in RULES)}"
        )
    syntaxes = parse_syntaxes(raw.get("syntaxes"), f"{field}.syntaxes", metadata)
    rules = parse_conventions(raw.get("conventions"), f"{field}.conventions", syntaxes.names())
    return ReferenceConfig(
        exemptions=shared.union(exemptions(raw.get("exclude"), f"{field}.exclude", root, metadata)),
        schemes=_schemes(raw.get("schemes"), f"{field}.schemes"),
        fragments=_choice(Fragments, raw.get("fragments"), Fragments.BLOCK, f"{field}.fragments"),
        syntaxes=syntaxes,
        conventions=Conventions(rules, metadata),
        ignored=ignored,
        metadata=metadata,
    )
