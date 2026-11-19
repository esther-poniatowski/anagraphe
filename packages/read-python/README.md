# anagraphe-read

The distribution `anagraphe-read` reads the addressing of Anagraphe in Python. The distribution
covers six objects of a repository:

- its identity;
- its files: their metadata, their pointers, and whether the shared exclusions leave them out;
- its records, each with the contract that it names and the position of each of its nodes;
- the logical targets of its records;
- the records named by those targets in other repositories;
- the bindings of its texts.

When a tool only reads the records of Anagraphe, the tool depends on this distribution alone,
without the command line. The distribution reads files and writes none. The command line of
Anagraphe, the distribution `anagraphe`, depends on it.

## Installation

A consumer pins the distribution by a commit of the repository of Anagraphe and the subdirectory
that holds it. The `dependencies` of the `pyproject.toml` of the consumer, or the `pip` section of
its `environment.yml`, hold this requirement:

```text
anagraphe-read @ git+https://github.com/esther-poniatowski/anagraphe.git@<commit>#subdirectory=packages/read-python
```

The commit is a full commit identifier. Each release of Anagraphe also attaches the wheel of the
distribution, `anagraphe_read-<version>-py3-none-any.whl`, to its GitHub release.

When a consumer and Anagraphe change together, the consumer installs a local clone of Anagraphe in
editable mode instead:

```sh
pip install -e ../anagraphe/packages/read-python
```

## Interface

The module `anagraphe_read` is the interface, and its `__all__` lists every public name. The
subpackages and modules below it open on an underscore: they are private, and they can change
without a change of the version.

The entry point `open_repository(root, *, config=None, provider=None)` opens a repository for
reading. The function locates `anagraphe.yml` at `config/tools/anagraphe.yml` or at the root, unless
`config` names another file. A root holding neither file opens with an empty configuration, so that
its submodules still resolve. The provider reads the selected states of other repositories, and
defaults to the Git provider returned by `git_provider()`. That provider reads a state from a local
clone of its repository when the machine holds one, else from the cache of the machine.

The script below opens a repository, resolves a target into another repository and reads the record
that the target names:

```python
from pathlib import Path

from anagraphe_read import Outcome, Role, Target, open_repository

repository = open_repository(Path("."))
print(repository.identity.id)
resolution = repository.resolve(Target.parse({"repository": "other-lab", "id": "ada"}))
if resolution.outcome is Outcome.RECORD:
    read = repository.read(resolution, (("test:person",),))
    print(read.verified, read.provenance)
binding = repository.bindings("notes/a.md", Role("onomasia.glossary"))
```

The returned `Repository` exposes thirteen members:

| Member | Returns |
| --- | --- |
| `root` | the root of the repository, resolved |
| `identity` | the `Identity` of the repository: its identifier, its former identifiers and its problems |
| `configuration` | the `Configuration`, whose fields hold, among others, the sections `targets`, `records`, `bindings`, `resolution` and `repository` of `anagraphe.yml` |
| `roles` | the names of the roles declared by the section `bindings` |
| `binding` | the key of a record naming its contract, `_schema` by default |
| `schema_registry` | the path of the schema registry declared by the section `targets`, or `None` |
| `records()` | the `RecordFile` of each record of the walk: its path, the contract that it names, its data, its declared identifier and its problem; its method `position(path)` returns the line and the column where a node of the data opens |
| `resolve(target)` | the `Resolution` of a `Target`: its outcome, its findings and its provenance |
| `read(resolution, contracts=())` | the `RecordRead` of a resolved target: the bytes of the record, their provenance and the findings of their verification; its property `verified` states that none failed |
| `references(path)` | the `Pointer` of each target written in a file: its place, its raw text, its syntax, its region (`metadata` or `content`), and the repository-relative file that it names, or `None` when it names no file of the repository, an external URL or a path outside it; a candidate naming no file counts only when its syntax reports unresolved targets |
| `metadata(path)` | the metadata of a file, read from the source that the configuration declares for it, the built-in sources without one; empty when the file holds none or cannot be read |
| `exempt(path)` | whether the shared exclusions leave a file out: the hidden paths, the top-level `exclude`, and the paths that Git ignores when the configuration says so |
| `bindings(path, role)` | the `Binding` of a text for a `Role`, resolved along the directory chain |

The other public names fall into four groups:

- the value types of the results: `Finding`, `Outcome`, `Provenance`, `InvalidTarget`, `Merge`;
- the port of a repository-state provider, `StateProvider`, with the types of the values that it
  returns (`State`, `Reading`, `Blob`, `Mode`, `Missing`, `Escaping`, `Unavailable`, `Availability`)
  and the in-memory provider `MemoryProvider` for tests;
- the kinds of the findings carried by a resolution, a read or an identity, such as
  `RENAMED_REPOSITORY`, `RENAMED_TARGET` and `UNVERIFIED_TARGET`;
- the published specification: the identifier `ADDRESSING_ID` of the resource `addressing.v1`, the
  function `addressing_schema()` returning a copy of that resource, and the mapping
  `IMPLEMENTED_SPECIFICATION` of the versions that the distribution implements.

Every invalid configuration raises `ConfigurationError`.

## Versioning

The distribution carries a version of its own. The version follows [Semantic
Versioning](https://semver.org/) and starts at `0.1.0`. The version changes only when the interface
or the behaviour of `anagraphe_read` changes. Before 1.0.0, a breaking change raises the minor
version. The version of the command line changes apart, and a release of the command line leaves
this version unchanged.

The test suites of Anagraphe run the conformance cases under `specs/conformance/` against this
distribution, as they run them against the TypeScript read package
[`@anagraphe/read`](../read/README.md).
