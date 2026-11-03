"""
The resolution of the bindings of a text along the directory chain.

A text declares a role in its frontmatter, under the key that the repository names for the role.
A record of a contract held by the schema registry declares it in the fields that the schema marks
by ``x-binds``, since the fields of a record belong to its schema. Any other file, such as a
configuration file or a record of an unregistered contract, declares nothing itself, so that a key
of the same name with another meaning is never read as a binding. The index of each enclosing
directory then declares the role for every file below it, up to the index of the root, the last
link of the chain. The merge rule of the role combines these declarations.

A declaration names at least one value: a non-empty string, or a list of them. A key holding null
declares nothing, so the file takes the binding of the next link.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Mapping

from anagraphe.bindings.configuration import BindingConfig
from anagraphe.bindings.model import Binding, Declaration, Merge, Role
from anagraphe.bindings.schemas import SchemaBindings, parse_document
from anagraphe.core.configuration import ConfigurationError
from anagraphe.core.issues import pointer
from anagraphe.core.metadata import MetadataReader, SourceKind, frontmatter_problem

#: The suffixes of a record, whose contract may mark its binding fields.
RECORD_SUFFIXES = (".yml", ".yaml", ".json")


@dataclass(frozen=True)
class InvalidDeclaration:
    """A declaration naming no value, or a value that is not a non-empty string."""

    rel: str
    pointer: str
    role: str


@dataclass(frozen=True)
class UnreadableSource:
    """A file whose frontmatter or record cannot be parsed, so its own declaration is unread."""

    rel: str
    detail: str


def values_of(value: Any) -> tuple[str, ...] | None:
    """Return the values of a declaration, each once; None when it names no valid value.

    Examples
    --------
    >>> values_of("base"), values_of(["base", "ml", "base"])
    (('base',), ('base', 'ml'))
    >>> values_of([]), values_of(" "), values_of(["base", 3])
    (None, None, None)
    """
    items = [value] if isinstance(value, str) else value
    if not isinstance(items, list) or not items:
        return None
    if not all(isinstance(item, str) and item.strip() for item in items):
        return None
    return tuple(dict.fromkeys(items))


def normalized(rel: str) -> str:
    """Return a repository-relative path in its normal form.

    Raises
    ------
    ValueError
        If the path is absolute, or leaves the repository.

    Examples
    --------
    >>> normalized("./notes//a.md")
    'notes/a.md'
    >>> normalized("../a.md")
    Traceback (most recent call last):
    ...
    ValueError: a binding is resolved for a file inside the repository: ../a.md
    """
    path = posixpath.normpath(rel)
    if PurePosixPath(rel).is_absolute() or path == "." or path.split("/")[0] == "..":
        raise ValueError(f"a binding is resolved for a file inside the repository: {rel}")
    return path


class BindingResolver:
    """Resolve the bindings of the files of one repository, each file read once.

    The resolver records, as it reads them, the declarations whose value is invalid and the files
    whose frontmatter or record cannot be parsed, so that the check reports them.
    """

    def __init__(
        self, root: Path, config: BindingConfig, metadata: MetadataReader | None = None
    ) -> None:
        self.root = root.resolve()
        self.config = config
        self.metadata: MetadataReader = metadata or config.metadata or MetadataReader(self.root)
        self.invalid: list[InvalidDeclaration] = []
        self.unreadable: list[UnreadableSource] = []
        self._schemas: SchemaBindings | None = None
        self._records: dict[str, Mapping[str, Any] | None] = {}
        self._frontmatters: set[str] = set()

    @property
    def schemas(self) -> SchemaBindings | None:
        """Return the binding fields of the contracts, None when the repository declares no records."""
        if self._schemas is None and self.config.records is not None:
            self._schemas = SchemaBindings(self.root, self.config.records.registry)
        return self._schemas

    def resolve(self, rel: str, role: Role) -> Binding:
        """Resolve the binding of a repository-relative file for a role.

        Raises
        ------
        ConfigurationError
            If the repository declares no key for the role.
        ValueError
            If the path is absolute, or leaves the repository.
        """
        declarations = [item for item in self.chain(normalized(rel), role.name) if item is not None]
        if role.merge is Merge.OVERRIDE:
            chosen = declarations[:1]
            return Binding(role, chosen[0].values if chosen else (), tuple(chosen))
        ordered = tuple(reversed(declarations))
        values = tuple(dict.fromkeys(value for item in ordered for value in item.values))
        return Binding(role, values, ordered)

    def chain(self, rel: str, role: str) -> Iterator[Declaration | None]:
        """Yield the declaration of each link of the chain of a file, nearest first, None for a
        link declaring nothing: the file itself, then the index of each enclosing directory."""
        if role not in self.config.roles:
            raise ConfigurationError(f"bindings.roles declares no key for the role {role}")
        yield self.own(rel, role)
        folder = PurePosixPath(rel).parent
        while True:
            index = (folder / self.config.index).as_posix()
            if index != rel and (self.root / index).is_file():
                yield self._frontmatter_declaration(index, role)
            if folder == PurePosixPath("."):
                return
            folder = folder.parent

    def is_record(self, rel: str) -> bool:
        """Whether a file may be a record whose contract marks its binding fields."""
        return self.config.records is not None and rel.endswith(RECORD_SUFFIXES)

    def own(self, rel: str, role: str) -> Declaration | None:
        """Return the declaration of a file itself, None when it declares nothing for the role.

        When several fields of a record bind one role, the first valid one, in the order of the
        schema, declares it.
        """
        record = self._record_fields(rel)
        if record is not None:
            data, paths = record
            for path in paths.get(role, ()):
                found = self._at(data, path)
                if found is not None:
                    declaration = self._declaration(rel, pointer(*path), role, found)
                    if declaration is not None:
                        return declaration
            return None
        return self._frontmatter_declaration(rel, role)

    def _frontmatter_declaration(self, rel: str, role: str) -> Declaration | None:
        """Return the declaration written under the key of a role in the frontmatter of a file,
        None for a file whose metadata is read from another source."""
        if self.metadata.source_of(rel).kind is not SourceKind.FRONTMATTER:
            return None
        if rel not in self._frontmatters:
            self._frontmatters.add(rel)
            try:
                problem = frontmatter_problem((self.root / rel).read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError) as error:
                problem = f"the file cannot be read: {error}"
            if problem is not None:
                self.unreadable.append(UnreadableSource(rel, problem))
        key = self.config.roles[role].key
        found = self.metadata(rel).get(key)
        if found is None:
            return None
        return self._declaration(rel, pointer(key), role, found)

    def _declaration(self, rel: str, at: str, role: str, value: Any) -> Declaration | None:
        """Return a declaration, None after recording a value that names no valid value."""
        values = values_of(value)
        if values is None:
            entry = InvalidDeclaration(rel, at, role)
            if entry not in self.invalid:
                self.invalid.append(entry)
            return None
        return Declaration(rel, at, values)

    def _record_fields(
        self, rel: str
    ) -> tuple[Mapping[str, Any], Mapping[str, tuple[tuple[str, ...], ...]]] | None:
        """Return the data of a record and the binding fields of its contract, None for a file
        that is no record of a contract held by the registry."""
        schemas = self.schemas
        if schemas is None or not self.is_record(rel):
            return None
        if rel not in self._records:
            self._records[rel] = self._load(rel)
        data = self._records[rel]
        if data is None:
            return None
        assert self.config.records is not None
        contract = data.get(self.config.records.binding)
        fields = schemas.fields(contract) if isinstance(contract, str) else None
        if fields is None:
            return None
        return data, fields

    def _load(self, rel: str) -> Mapping[str, Any] | None:
        """Return the top mapping of a record, None after recording a record that cannot be parsed."""
        try:
            data = parse_document(rel, (self.root / rel).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as error:
            self.unreadable.append(UnreadableSource(rel, f"the record cannot be parsed: {error}"))
            return None
        return data if isinstance(data, Mapping) else None

    @staticmethod
    def _at(data: Mapping[str, Any], path: tuple[str, ...]) -> Any:
        """Return the value at a key path of a record, None when a key is absent."""
        node: Any = data
        for key in path:
            if not isinstance(node, Mapping) or key not in node:
                return None
            node = node[key]
        return node
