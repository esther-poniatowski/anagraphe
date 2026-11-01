# CLI Reference

Anagraphe provides one group of commands per section of `anagraphe.yml`, and one check of every
declared section.

## Global options

```text
anagraphe [OPTIONS] COMMAND [ARGS]
```

| Option | Purpose |
| --- | --- |
| `--version`, `-v` | prints the package version |
| `--help` | prints command help |

## Commands

The commands below take the arguments and options shown:

```text
anagraphe check [PATHS]... [--root PATH] [--config PATH]
anagraphe indexes check [PATHS]... [--root PATH] [--config PATH]
anagraphe indexes write [PATHS]... [--root PATH] [--config PATH]
anagraphe refs check [PATHS]... [--root PATH] [--config PATH]
anagraphe move OLD NEW [--dry-run] [--root PATH] [--config PATH]
```

| Command | Effect |
| --- | --- |
| `anagraphe check` | runs the check of every declared section, and changes no file |
| `anagraphe indexes check` | reports the generated regions that differ from their rendering, and changes no file |
| `anagraphe indexes write` | replaces the generated regions, only once every selected index validates |
| `anagraphe refs check` | reports the references that name no file or anchor, or break a convention |
| `anagraphe move` | moves a file or a folder, rewrites every pointer to it, and updates the affected indexes; `--dry-run` prints the plan and changes no file |

| Option | Purpose | Default |
| --- | --- | --- |
| `--root PATH` | selects the repository root | current directory |
| `--config PATH` | selects the configuration relative to the root | `anagraphe.yml` |

For the indexes, each path may name an index, a directory, or a member whose parent index must be
processed. For the references, each path names a file or a directory to check.

## Output and exit status

Each command prints one line per issue, `path:line: [warning: ]kind: detail`, then one summary
line per section. The summary counts the violations, the warnings and the issues of each kind.

| Status | Meaning |
| --- | --- |
| `0` | no issue blocks |
| `1` | at least one violation is reported |
| `2` | the configuration, a named target, or a required section is invalid or absent |
