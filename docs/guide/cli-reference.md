# CLI Reference

## Global options

```text
anagraphe [OPTIONS] COMMAND [ARGS]
```

| Option | Purpose |
| --- | --- |
| `--version`, `-v` | prints the package version |
| `--help` | prints command help |

## Check

The check command reports stale managed blocks and changes no file:

```text
anagraphe check [PATHS]... [--root PATH] [--config PATH]
```

## Write

The write command replaces managed blocks only after every selected index passes validation:

```text
anagraphe write [PATHS]... [--root PATH] [--config PATH]
```

| Option | Purpose | Default |
| --- | --- | --- |
| `--root PATH` | selects the repository root | current directory |
| `--config PATH` | selects the configuration relative to the root | `anagraphe.yml` |

Each path may name an index, a directory, or a member whose parent index must be processed.
