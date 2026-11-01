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
anagraphe check [PATHS]... [--root PATH] [--config PATH] [--format FORMAT] [--output PATH]
anagraphe indexes check [PATHS]... [--root PATH] [--config PATH] [--format FORMAT] [--output PATH]
anagraphe indexes write [PATHS]... [--root PATH] [--config PATH]
anagraphe refs check [PATHS]... [--root PATH] [--config PATH] [--format FORMAT] [--output PATH]
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
| `--root PATH` | selects the repository root, from which every reported path is written | current directory |
| `--config PATH` | selects the configuration relative to the root | `anagraphe.yml` |
| `--format FORMAT` | of the three check commands: `text`, or `sarif` for a findings log | `text` |
| `--output PATH` | with `--format sarif` only: writes the log to `PATH`, relative to the current directory, and creates its missing folders | standard output |

For the indexes, each path may name an index, a directory, or a member whose parent index must be
processed. For the references, each path names a file or a directory to check.

## Output and exit status

Each command prints one line per issue, `path:line: [warning: ]kind: detail`, then one summary
line per section. The summary counts the violations, the warnings and the issues of each kind.

| Status | Meaning |
| --- | --- |
| `0` | no issue blocks |
| `1` | at least one violation is reported |
| `2` | the configuration, a named target, or a required section is invalid or absent; or the log cannot be written |

## Findings log

Under `--format sarif`, a check command also writes its findings as a SARIF 2.1.0 log of the
[findings profile](https://github.com/esther-poniatowski/elenchos) of the gate Elenchos, as
[ADR 0004](../adr/0004-findings-output.md) proposes. The text report and the exit status stay
unchanged. When the log takes standard output, the text report moves to standard error, so that
standard output holds the log alone.

The log holds one run of the driver `anagraphe`, which lists every kind of both sections as a rule
`<section>/<kind>`, such as `references/broken` or `indexes/retired-key`. Each issue yields one
result:

| Field | Value |
| --- | --- |
| `ruleId` | `<section>/<kind>` |
| `level` | `error` for a violation, `warning` for a warning |
| `message.text` | the detail of the issue |
| physical location | the file relative to the root, with the line of the issue |
| logical location | `path:<file>`, followed by `#<locus>` when the issue has a locus |
| `partialFingerprints["discriminator/v1"]` | the entry of a list that the issue concerns, when the locus does not suffice |

The locus is `link:<target as written>` for a reference, the JSON Pointer of a key for an issue of
the metadata, such as `/aliases` or `/groups`, and empty for an issue of the whole file. The run
declares itself failed when it stopped on an invalid configuration or target, in which case it
holds no results, or when a file could not be read.
