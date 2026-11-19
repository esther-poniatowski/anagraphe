# Installation

Anagraphe consists of two Python distributions, kept in one repository: the read distribution
`anagraphe-read`, in `packages/read-python`, and the command line `anagraphe`, at the root. The
command line requires the read distribution by name and by exact version,
`anagraphe-read==<version>`. Neither distribution is published on a package index. Python 3.12 or
later is required.

## Install for development

The environment declaration installs the runtime, test, type-checking, and documentation tools, and
the read distribution of the clone in editable mode:

```sh
conda env create -f environment.yml
conda activate anagraphe
```

The command below installs the root in editable mode, with the package `anagraphe` and the
executable `anagraphe`:

```sh
pip install -e .
```

## Pin the distributions in a consumer

When a tool only reads records, the tool pins the read distribution alone, as the
[README of the read distribution](https://github.com/esther-poniatowski/anagraphe/blob/main/packages/read-python/README.md) states.

When a repository runs the command line, the repository pins both distributions at the same commit.
The command line imports internal modules of the read distribution, so the two distributions must be
installed from the same commit. The `pip` section of the `environment.yml` of the consumer, or the
`dependencies` of its `pyproject.toml`, holds two requirements:

```text
anagraphe-read @ git+https://github.com/esther-poniatowski/anagraphe.git@<commit>#subdirectory=packages/read-python
anagraphe @ git+https://github.com/esther-poniatowski/anagraphe.git@<commit>
```

The first requirement satisfies the dependency of the command line on `anagraphe-read`. When a
consumer names the command line alone, pip stops with an error naming the version that the command
line pins:

```text
ERROR: No matching distribution found for anagraphe-read==0.2.0
```
