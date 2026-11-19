"""
The section ``references`` of ``anagraphe.yml``, as the read side reads it.

The read side parses the part of the section that finds and resolves the pointers of a file: the
files left unread, the URL schemes resolved outside the repository, the syntaxes, and the
conventions. The command line of Anagraphe parses the rest of the section, which only its check
reads: the fragments, the unlinkable files and the ignored kinds.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from anagraphe_read._core.configuration import ConfigurationError, known_keys, strings
from anagraphe_read._core.exclusions import Exemptions, exemptions
from anagraphe_read._core.metadata import MetadataReader
from anagraphe_read._references.conventions import Conventions, parse_conventions
from anagraphe_read._references.syntaxes import Syntaxes, parse_syntaxes

#: The keys of the section ``references``.
SECTION_KEYS = frozenset(
    {"exclude", "schemes", "fragments", "syntaxes", "conventions", "unlinkable", "ignore"}
)
#: The retired keys of the section, each with the declaration that replaces it.
RETIRED_KEYS = {
    "markdown": "the files of a syntax under syntaxes.markdown.when, such as {types: [md, yml]}",
    "records": "a syntax of keys under syntaxes, such as {glossary: {when: {...}, keys: [source]}}",
}
#: The URL schemes resolved outside the repository when the section declares none.
DEFAULT_SCHEMES = frozenset({"https", "http", "mailto"})


@dataclass(frozen=True)
class ReadReferences:
    """The part of the section ``references`` that finds and resolves the pointers of a file."""

    exemptions: Exemptions = Exemptions()
    #: The URL schemes resolved outside the repository, in lowercase.
    schemes: frozenset[str] = DEFAULT_SCHEMES
    syntaxes: Syntaxes = Syntaxes()
    conventions: Conventions = Conventions()
    #: The metadata of each file, read from its declared source.
    metadata: MetadataReader | None = None


def _schemes(value: Any, field: str) -> frozenset[str]:
    """Return the declared schemes, written as a list or as a mapping to their glosses."""
    if value is None:
        return DEFAULT_SCHEMES
    names = list(value) if isinstance(value, Mapping) else value
    return frozenset(name.lower() for name in strings(names, field))


def parse_read_section(
    root: Path,
    raw: Mapping[str, Any],
    shared: Exemptions,
    metadata: MetadataReader | None = None,
    field: str = "references",
) -> ReadReferences:
    """Validate the keys of the section ``references``, and resolve its read side.

    Raises
    ------
    ConfigurationError
        If the section holds a retired or an unknown key, or an invalid syntax, convention,
        scheme or exclusion.
    """
    for key, replacement in RETIRED_KEYS.items():
        if key in raw:
            raise ConfigurationError(f"{field}.{key} is retired: declare {replacement}")
    known_keys(raw, SECTION_KEYS, field)
    syntaxes = parse_syntaxes(raw.get("syntaxes"), f"{field}.syntaxes", metadata)
    rules = parse_conventions(raw.get("conventions"), f"{field}.conventions", syntaxes.names())
    return ReadReferences(
        exemptions=shared.union(exemptions(raw.get("exclude"), f"{field}.exclude", root, metadata)),
        schemes=_schemes(raw.get("schemes"), f"{field}.schemes"),
        syntaxes=syntaxes,
        conventions=Conventions(rules, metadata),
        metadata=metadata,
    )
