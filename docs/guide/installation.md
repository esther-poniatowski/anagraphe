# Installation

## Prerequisites

- Python >= 3.12
- conda (recommended) or pip

## Using pip

The package installs directly from the GitHub repository:

```sh
pip install git+https://github.com/esther-poniatowski/anagraphe.git
```

## Using conda

The package is available on the `eresthanaconda` channel:

```sh
conda install -c eresthanaconda anagraphe
```

## From Source

1. Clone the repository:

   ```sh
   git clone https://github.com/esther-poniatowski/anagraphe.git
   ```

2. Create a dedicated environment and install:

   ```sh
   cd anagraphe
   conda env create -f environment.yml
   conda activate anagraphe
   ```
