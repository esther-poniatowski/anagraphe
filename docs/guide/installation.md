# Installation

Anagraphe currently runs from a local source checkout. Python 3.12 or later and Conda are required
for the supported development route.

## Create the environment

The environment declaration installs the runtime, test, type-checking, and documentation tools:

```sh
conda env create -f environment.yml
conda activate anagraphe
```

## Register the source checkout

The editable installation exposes both the package and the `anagraphe` executable:

```sh
pip install -e .
```

Published package and Conda installation instructions will replace this source-only route after the
first release.
