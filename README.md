# Anagraphe

[![Maintenance](https://img.shields.io/maintenance/yes/2026)]()
[![Python](https://img.shields.io/badge/python-%E2%89%A53.12-blue)](https://www.python.org/)
[![License: GPL](https://img.shields.io/badge/License-GPL--3.0-yellow.svg)](https://opensource.org/licenses/GPL-3.0)

Generates repository indexes from record metadata, and checks their drift and the references between files.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Quick Start](#quick-start)
- [Public Interface](#public-interface)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

## Overview

Repository records often declare the metadata needed for navigation, while hand-written indexes
repeat that metadata and drift after files move or change. Anagraphe reads repository-owned
metadata schemas and index-type schemas, then renders only the managed blocks of each index. The
non-mutating check command compares those blocks with the same rendering used by the write command.
The same check reads the fields declared as references by the repository, and reports each
reference naming no file or anchor.

### Advantages

- **One authority** — record metadata supplies each generated entry
- **Deterministic output** — a second write produces identical bytes
- **Repository-owned policy** — metadata schemas, index types, exclusions, tasks, and sequences remain
  with the consuming repository
- **Transactional writes** — a blocking issue prevents every selected write
- **CI drift checks** — the check command changes no source file and fails on stale blocks

## Features

- [x] Render the groups declared by an index, each as a registry or a sequence.
- [x] Assign the members of a group by a filter or by an explicit list of links.
- [x] List the files of declared types, by default Markdown notes and YAML records, with their fields read from declared metadata sources.
- [x] Check managed blocks without writing files.
- [x] Validate index types through repository-supplied JSON Schemas.
- [x] Accept repository task states and folder build manifests through configuration.
- [x] Check the declared references of Markdown links and YAML record fields.
- [x] Move a file or a folder, rewriting every pointer to it and updating the affected indexes.
- [x] Resolve the bindings of texts to the roles of tools along the directory chain, records included through `x-binds`.
- [x] Check the logical targets between records within one repository, with the identifiers and the derived repository identity that they name.
- [x] Check the references of a field to the units of the same record, declared by `x-units`.
- [x] Generate and check the record registry, the file of each record identifier, and retire the identifiers that no record holds, with their successors after a rename.
- [x] Rewrite the contract named by each record when a domain tool migrates its records, under a migration plan.
- [x] Rename a repository identifier, retiring the former one and rewriting the targets and the context entries that name it, in the root and each submodule checked out under it.
- [x] Read the logical targets, the records of other repositories and the bindings in Python, without the command line, through the distribution [`anagraphe-read`](packages/read-python/README.md).
- [x] Read the logical targets and the record registry in TypeScript, for a host without Python, through the package [`@anagraphe/read`](packages/read/README.md).
- [x] Parse, print and expand field paths, and convert them to and from JSON Pointers, in Python and in TypeScript.
- [x] Compare the versions of the specification declared by another read side of the repository with those of Anagraphe.
- [x] Exclude files by `.gitignore` patterns, by metadata such as `status: archived`, and by the ignore rules of Git for untracked files.
- [x] Declare the link formats and path styles of the pointers by location, file type or metadata.
- [ ] Move and rename anchors, and rename the identifiers of a declared namespace.
- [ ] Load repository-specific adapters as plugins.
- [ ] Render and manipulate indexes in Obsidian through a plugin.

## Quick Start

The repository must contain an `anagraphe.yml` configuration, read from the root, from its
subfolder `.config/`, or from its subfolder `config/`, as the
[specification of Hodegos](https://github.com/esther-poniatowski/hodegos/blob/main/docs/specification.md) states, and the metadata schema and index-type schemas named by that configuration. The write command materializes every managed block:

```sh
anagraphe indexes write
```

The check command verifies the same rendering, the declared references, the bindings of texts,
the logical targets and the record registry, without changing a file:

```sh
anagraphe check
```

## Public Interface

Anagraphe ships two Python distributions from this repository, each with its own version:

| Distribution | Import package | Role |
| --- | --- | --- |
| [`anagraphe-read`](packages/read-python/README.md) | `anagraphe_read` | reads the identity, the logical targets, the records of other repositories and the bindings of a repository |
| `anagraphe` | `anagraphe` | provides the command line: the writers of the indexes, the registry and the moves, and every check |

When a tool only reads records, the tool imports `anagraphe_read` alone. The `__all__` of
`anagraphe_read` is the whole public interface of Anagraphe in Python. The package `anagraphe` holds
the command line, and its modules are internal. The [installation guide](docs/guide/installation.md)
states how to pin each distribution.

## Documentation

| Guide | Purpose |
| --- | --- |
| [Usage](docs/guide/usage.md) | runs the write-and-check workflow |
| [CLI reference](docs/guide/cli-reference.md) | lists commands, arguments, and exit states |
| [Configuration](docs/guide/configuration.md) | declares repository-owned inputs |
| [Index specification](docs/guide/index-specification.md) | declares the groups, membership and order of a collection |
| [Reference specification](docs/guide/references.md) | declares the references between files, and repairs the reported ones |
| [Bindings](docs/guide/bindings.md) | binds the texts to the resources read by tools, along the directory chain |
| [Bindings contract](docs/specification/bindings-contract.md) | fixes the version of the bindings read by a tool |
| [Logical targets](docs/guide/targets.md) | names a record, a unit or a repository by identifier, and checks the names |
| [Logical targets specification](docs/specification/logical-targets.md) | fixes the readings of a target for every read side |
| [Field paths specification](docs/specification/field-paths.md) | fixes the grammar of a field path and its conversions to and from a JSON Pointer |
| [Architecture](docs/internals/architecture.md) | separates the generic core from repository adapters |

## Contributing

[The contribution guidelines](CONTRIBUTING.md) state the development environment and checks.

## License

Anagraphe is licensed under the [GNU General Public License v3.0](LICENSE).
