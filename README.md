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
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

## Overview

Repository records often declare the metadata needed for navigation, while hand-written indexes
repeat that metadata and drift after files move or change. Anagraphe reads repository-owned
vocabularies and index-type schemas, then renders only the managed blocks of each index. The
non-mutating check command compares those blocks with the same rendering used by the write command.
The same check reads the fields declared as references by the repository, and reports each
reference naming no file or anchor.

### Advantages

- **One authority** — record metadata supplies each generated entry
- **Deterministic output** — a second write produces identical bytes
- **Repository-owned policy** — vocabularies, index types, exclusions, tasks, and sequences remain
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
- [x] Exclude files by `.gitignore` patterns and by metadata, such as `status: archived`.
- [x] Declare the link formats and path styles of the pointers by location, file type or metadata.
- [ ] Move and rename anchors, and rename the identifiers of a declared namespace.
- [ ] Load repository-specific adapters as plugins.
- [ ] Render and manipulate indexes in Obsidian through a plugin.

## Quick Start

The repository must contain an `anagraphe.yml` configuration, read from `config/tools/` or
from the root, and the vocabulary and index-type schemas named by that configuration. The write command materializes every managed block:

```sh
anagraphe indexes write
```

The check command verifies the same rendering, the declared references and the bindings of texts,
without changing a file:

```sh
anagraphe check
```

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
| [Architecture](docs/internals/architecture.md) | separates the generic core from repository adapters |

## Contributing

[The contribution guidelines](CONTRIBUTING.md) state the development environment and checks.

## License

Anagraphe is licensed under the [GNU General Public License v3.0](LICENSE).
