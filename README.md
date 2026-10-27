# Anagraphe

[![Maintenance](https://img.shields.io/maintenance/yes/2026)]()
[![Python](https://img.shields.io/badge/python-%E2%89%A53.12-blue)](https://www.python.org/)
[![License: GPL](https://img.shields.io/badge/License-GPL--3.0-yellow.svg)](https://opensource.org/licenses/GPL-3.0)

Generates repository indexes from record metadata and checks their drift.

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

### Advantages

- **One authority** — record metadata supplies each generated entry
- **Deterministic output** — a second write produces identical bytes
- **Repository-owned policy** — vocabularies, index types, exclusions, tasks, and sequences remain
  with the consuming repository
- **Transactional writes** — a blocking issue prevents every selected write
- **CI drift checks** — the check command changes no source file and fails on stale blocks

## Features

- [x] Render registry, sequence, and dependency-ordered index groups.
- [x] Read Markdown frontmatter and YAML record metadata.
- [x] Check managed blocks without writing files.
- [x] Validate index types through repository-supplied JSON Schemas.
- [x] Accept repository task states and explicit folder sequences through configuration.
- [ ] Load repository-specific adapters as plugins.

## Quick Start

The repository must contain an `anagraphe.yml` configuration and the vocabulary and index-type
schemas named by that configuration. The write command materializes every managed block:

```sh
anagraphe write
```

The check command verifies the same rendering without changing a file:

```sh
anagraphe check
```

## Documentation

| Guide | Purpose |
| --- | --- |
| [Usage](docs/guide/usage.md) | runs the write-and-check workflow |
| [CLI reference](docs/guide/cli-reference.md) | lists commands, arguments, and exit states |
| [Configuration](docs/guide/configuration.md) | declares repository-owned inputs |
| [Architecture](docs/internals/architecture.md) | separates the generic core from repository adapters |

## Contributing

[The contribution guidelines](CONTRIBUTING.md) state the development environment and checks.

## License

Anagraphe is licensed under the [GNU General Public License v3.0](LICENSE).
