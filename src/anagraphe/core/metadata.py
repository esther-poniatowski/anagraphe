"""
The metadata of a file, read from the source that the repository declares for it.

A source names where the fields of a file are written:

- ``frontmatter``: the YAML block opening a text file between two lines ``---``;
- a structured document, ``yaml``, ``json`` or ``toml``, at declared key paths. The mappings found
  at those paths merge in their order, a later one overriding an earlier one, and the path ``.``
  names the top level of the document;
- ``none``: the file holds no metadata.

The repository declares its sources under ``metadata``, as rules holding a condition on the path or
the type of a file. The rules cascade after the built-in ones, and the last matching rule names the
source. The built-in rules read the frontmatter of a Markdown note, and the top level of a YAML
document overridden by its block ``metadata``. The metadata region of a file, where its fields are
written, tells a pointer of the metadata from a pointer of the content.

Examples
--------
>>> reader = MetadataReader(Path("."), parse_metadata([
...     {"when": {"types": ["toml"]}, "from": {"toml": ["tool.notes"]}}], "metadata"))
>>> reader.source_of("a.md").kind.value, reader.source_of("pyproject.toml").at
('frontmatter', ('tool.notes',))
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

from anagraphe.core.conditions import Condition, parse_condition
from anagraphe.core.configuration import ConfigurationError, known_keys, mapping

#: The suffixes of a YAML document.
YAML_SUFFIXES = (".yml", ".yaml")
#: The key path naming the top level of a document.
TOP = "."


class SourceKind(StrEnum):
    """The kind of source holding the metadata of a file."""

    FRONTMATTER = "frontmatter"
    YAML = "yaml"
    JSON = "json"
    TOML = "toml"
    NONE = "none"


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Return the parsed frontmatter of a note and its body; an empty mapping when absent.

    Examples
    --------
    >>> split_frontmatter("---\\nrole: spec\\n---\\n# Title\\n")
    ({'role': 'spec'}, '# Title\\n')
    >>> split_frontmatter("# No frontmatter\\n")
    ({}, '# No frontmatter\\n')
    """
    if not text.startswith("---\n"):
        return ({}, text)
    end = text.find("\n---", 4)
    if end == -1:
        return ({}, text)
    try:
        parsed = yaml.safe_load(text[4:end])
    except yaml.YAMLError:
        parsed = None
    body = text[end + 4 :].lstrip("\n") if text[end + 4 : end + 5] == "\n" else text[end + 4 :]
    return (parsed if isinstance(parsed, dict) else {}, body)


def frontmatter_problem(text: str) -> str | None:
    """Return why the frontmatter of a note cannot be read, None when it is absent or readable.

    Examples
    --------
    >>> frontmatter_problem("---\\nrole: spec\\n---\\n"), frontmatter_problem("# Title\\n")
    (None, None)
    >>> frontmatter_problem("---\\nrole: spec\\n# Title\\n")
    'the frontmatter opens on --- and never closes'
    >>> frontmatter_problem("---\\n- a\\n- b\\n---\\n")
    'the frontmatter is not a mapping'
    """
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return "the frontmatter opens on --- and never closes"
    try:
        parsed = yaml.safe_load(text[4:end])
    except yaml.YAMLError as error:
        return f"the frontmatter is not valid YAML: {_first_line(error)}"
    if parsed is not None and not isinstance(parsed, dict):
        return "the frontmatter is not a mapping"
    return None


def _first_line(error: Exception) -> str:
    """Return the first line of the message of a parse error."""
    return str(error).strip().splitlines()[0] if str(error).strip() else type(error).__name__


def _at(document: Any, path: str) -> Any:
    """Return the value at a dotted key path of a document, None when a key is absent."""
    if path == TOP:
        return document
    for key in path.split("."):
        if not isinstance(document, dict):
            return None
        document = document.get(key)
    return document


@dataclass(frozen=True)
class Source:
    """One source of metadata: its kind and, for a document, the key paths merged in order.

    Examples
    --------
    >>> Source(SourceKind.YAML, (".", "metadata")).read("role: audit\\nmetadata: {status: wip}\\n")
    {'role': 'audit', 'status': 'wip'}
    >>> Source(SourceKind.JSON, ("project",)).read('{"project": {"status": "archived"}}')
    {'status': 'archived'}
    >>> Source(SourceKind.TOML, ("tool.notes",)).read('[tool.notes]\\nrole = "audit"\\n')
    {'role': 'audit'}
    """

    kind: SourceKind
    at: tuple[str, ...] = (TOP,)

    def read(self, text: str) -> dict[str, Any]:
        """Return the metadata held by a text, an empty mapping when the source holds none."""
        return self.parse(text)[0]

    def parse(self, text: str) -> tuple[dict[str, Any], str | None]:
        """Return the metadata held by a text, and why it cannot be read, None when it can.

        A text that cannot be parsed holds no metadata, so its mapping is empty.

        Examples
        --------
        >>> Source(SourceKind.JSON, (".",)).parse('{"status": "wip"')[0]
        {}
        >>> Source(SourceKind.JSON, (".",)).parse('{"status": "wip"')[1].split(":")[0]
        'the document is not valid JSON'
        """
        if self.kind is SourceKind.NONE:
            return {}, None
        if self.kind is SourceKind.FRONTMATTER:
            return split_frontmatter(text)[0], frontmatter_problem(text)
        document, problem = self._parse(text)
        merged: dict[str, Any] = {}
        # A mapping merged from a deeper path is not also kept as a field of the top level.
        nested = {path.split(".")[0] for path in self.at if path != TOP}
        for path in self.at:
            found = _at(document, path)
            if isinstance(found, dict):
                merged.update(
                    {str(key): value for key, value in found.items()}
                    if path != TOP
                    else {str(key): value for key, value in found.items() if key not in nested}
                )
        return merged, problem

    def region(self, text: str) -> list[tuple[int, int]]:
        """Return the spans of a text where its metadata is written, as character offsets.

        A frontmatter spans its block. A YAML document spans each node at a declared path. A JSON
        or TOML document spans the whole text when its top level is declared, and nothing
        otherwise.
        """
        if self.kind is SourceKind.FRONTMATTER:
            if not text.startswith("---\n"):
                return []
            end = text.find("\n---", 3)
            return [] if end == -1 else [(0, end + 4)]
        if self.kind is SourceKind.YAML:
            try:
                root = yaml.compose(text, Loader=yaml.SafeLoader)
            except yaml.YAMLError:
                return []
            spans: list[tuple[int, int]] = []
            for path in self.at:
                node = root
                for key in [] if path == TOP else path.split("."):
                    node = next(
                        (
                            value
                            for name, value in getattr(node, "value", [])
                            if isinstance(node, yaml.MappingNode) and name.value == key
                        ),
                        None,
                    )
                if node is not None:
                    spans.append((node.start_mark.index, node.end_mark.index))
            return spans
        if self.kind in (SourceKind.JSON, SourceKind.TOML) and TOP in self.at:
            return [(0, len(text))]
        return []

    def _parse(self, text: str) -> tuple[Any, str | None]:
        """Return the parsed document and None, or None and why the document does not parse."""
        try:
            if self.kind is SourceKind.YAML:
                return yaml.safe_load(text), None
            if self.kind is SourceKind.JSON:
                return json.loads(text), None
            return tomllib.loads(text), None
        except (yaml.YAMLError, ValueError) as error:
            return None, f"the document is not valid {self.kind.name}: {_first_line(error)}"


@dataclass(frozen=True)
class MetadataRule:
    """A condition on the path or the type of a file, and the source of its metadata."""

    condition: Condition
    source: Source


#: The built-in rules, before every declared rule.
BUILT_IN = (
    MetadataRule(Condition(types=frozenset({"md"})), Source(SourceKind.FRONTMATTER)),
    MetadataRule(
        Condition(types=frozenset({"yml", "yaml"})), Source(SourceKind.YAML, (TOP, "metadata"))
    ),
)
#: The source of a file that no rule names.
NO_SOURCE = Source(SourceKind.NONE)


class MetadataReader:
    """Read the metadata of the files of one repository from their sources, each file once."""

    def __init__(self, root: Path, rules: tuple[MetadataRule, ...] = ()) -> None:
        self.root = root
        self.rules = (*BUILT_IN, *rules)
        self._cache: dict[str, dict[str, Any]] = {}

    def source_of(self, rel: str) -> Source:
        """Return the source named by the last rule whose condition holds for a file."""
        source = NO_SOURCE
        for rule in self.rules:
            if rule.condition.holds(rel):
                source = rule.source
        return source

    def __call__(self, rel: str) -> dict[str, Any]:
        if rel not in self._cache:
            path = self.root / rel
            source = self.source_of(rel)
            text = ""
            if source.kind is not SourceKind.NONE and path.is_file():
                try:
                    text = path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    text = ""
            self._cache[rel] = source.read(text) if text else {}
        return self._cache[rel]

    def region(self, rel: str, text: str) -> list[tuple[int, int]]:
        """Return the spans of the text of a file where its metadata is written."""
        return self.source_of(rel).region(text)


def metadata_of(rel: str, text: str) -> dict[str, Any]:
    """Return the metadata of a file under the built-in sources, an empty mapping when it holds none.

    Examples
    --------
    >>> metadata_of("a.md", "---\\nstatus: archived\\n---\\n")
    {'status': 'archived'}
    >>> metadata_of("r.yml", "role: audit\\nmetadata: {status: wip}\\n")
    {'role': 'audit', 'status': 'wip'}
    >>> metadata_of("r.yml", "- a list\\n"), metadata_of("x.py", "status = 1\\n")
    ({}, {})
    """
    return MetadataReader(Path(".")).source_of(rel).read(text)


def _source(value: Any, field_name: str) -> Source:
    """Parse a source: ``frontmatter``, ``none``, or a mapping from a document kind to key paths."""
    if value in (SourceKind.FRONTMATTER.value, SourceKind.NONE.value):
        return Source(SourceKind(value))
    documents = (SourceKind.YAML.value, SourceKind.JSON.value, SourceKind.TOML.value)
    raw = mapping(value, field_name) if isinstance(value, dict) else None
    if raw is None or len(raw) != 1 or next(iter(raw)) not in documents:
        raise ConfigurationError(
            f"{field_name} must be frontmatter, none, or one of {{yaml|json|toml: [key paths]}}"
        )
    kind, paths = next(iter(raw.items()))
    listed = paths if isinstance(paths, list) else [paths]
    if not listed or any(not isinstance(path, str) or not path for path in listed):
        raise ConfigurationError(
            f"{field_name}.{kind} must list key paths, such as ['.', metadata]"
        )
    return Source(SourceKind(kind), tuple(listed))


def parse_metadata(value: Any, field_name: str) -> tuple[MetadataRule, ...]:
    """Parse the declared metadata rules, each a condition ``when`` and a source ``from``."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ConfigurationError(f"{field_name} must be a list of rules {{when, from}}")
    rules: list[MetadataRule] = []
    for number, entry in enumerate(value, start=1):
        item = f"{field_name}[{number}]"
        raw = mapping(entry, item)
        known_keys(raw, frozenset({"when", "from"}), item)
        if "from" not in raw:
            raise ConfigurationError(f"{item} must name its source under from")
        condition, _ = parse_condition(
            raw.get("when"), f"{item}.when", frozenset({"paths", "types"})
        )
        rules.append(MetadataRule(condition, _source(raw["from"], f"{item}.from")))
    return tuple(rules)
