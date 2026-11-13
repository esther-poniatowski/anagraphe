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
anagraphe bindings check [PATHS]... [--root PATH] [--config PATH] [--format FORMAT] [--output PATH]
anagraphe bindings show PATH [--role ROLE]... [--merge RULE] [--format FORMAT] [--root PATH] [--config PATH]
anagraphe targets check [PATHS]... [--root PATH] [--config PATH] [--format FORMAT] [--output PATH]
anagraphe move OLD NEW [--dry-run] [--yes] [--root PATH] [--config PATH]
```

| Command | Effect |
| --- | --- |
| `anagraphe check` | runs the check of every declared section, and changes no file |
| `anagraphe indexes check` | reports the generated regions that differ from their rendering, and changes no file |
| `anagraphe indexes write` | replaces the generated regions, only once every selected index validates |
| `anagraphe refs check` | reports the references that name no file or anchor, or break a convention |
| `anagraphe bindings check` | reports the required texts bound to no value, and the invalid declarations and marks |
| `anagraphe bindings show` | prints the values bound to a file for each role, with the declarations supplying them |
| `anagraphe targets check` | reports the logical targets that do not resolve within the repository, and the defects of the identifiers, of their declarations and of `repository.yml` |
| `anagraphe move` | moves a file or a folder, rewrites every pointer to it, and updates the affected indexes, once the plan is confirmed on a terminal or by `--yes`; `--dry-run` prints the plan and changes no file |

| Option | Purpose | Default |
| --- | --- | --- |
| `-r`, `--root PATH` | selects the repository root, from which every reported path is written | `ANAGRAPHE_ROOT`, else the nearest folder, from the current one upwards, holding `config/tools/anagraphe.yml` or `anagraphe.yml`, else the current folder |
| `-c`, `--config PATH` | selects the configuration file, relative to the current folder | `config/tools/anagraphe.yml` or `anagraphe.yml` below the root; both existing is an error |
| `--role ROLE` | of `bindings show`: a role to resolve, repeatable | every declared role |
| `--merge RULE` | of `bindings show`: `override` or `union` | `override` |
| `--format FORMAT` | of the check commands: `text`, or `sarif` for a findings log; of `bindings show`: `text`, or `json` | `text` |
| `-o`, `--output PATH` | with `--format sarif` only: writes the log to `PATH`, relative to the current folder, and creates its missing folders | standard output |
| `--dry-run` | of `move`: prints the plan and changes no file | applies the plan |
| `--yes` | of `move`: applies the plan without asking for a confirmation | asks on a terminal, and stops with status `2` without one |

Every path typed on the command line, a target, `OLD`, `NEW`, `--config` or `--output`, is read from
the current folder; every path written in the configuration is read from the root. For the
indexes, each path may name an index, a directory, or a member whose parent index must be
processed. For the references, the bindings and the targets, each path names a file or a directory
to check.

## Output and exit status

Each command prints one line per issue, `path:line: [warning: |note: ]kind: detail`, then one
summary line per section. The summary counts the violations, the warnings, the notes when one is
reported, and the issues of each kind. A warning and a note do not block, so they leave the exit
status at `0`.

| Status | Meaning |
| --- | --- |
| `0` | no issue blocks |
| `1` | at least one violation is reported |
| `2` | the configuration, a named target, or a required section is invalid or absent; the log cannot be written; or a move lacks its confirmation without a terminal |

## Findings log

Under `--format sarif`, a check command also writes its findings as a SARIF 2.1.0 log of the
[findings profile](https://github.com/esther-poniatowski/elenchos) of the gate Elenchos, as
[ADR 0004](../adr/0004-findings-output.md) decides. The text report and the exit status stay
unchanged. When the log takes standard output, the text report moves to standard error, so that
standard output holds the log alone.

The log holds one run of the driver `anagraphe`, which lists every kind of every section as a rule
`<section>/<kind>`, such as `references/broken` or `indexes/retired-key`. Each issue yields one
result:

| Field | Value |
| --- | --- |
| `ruleId` | `<section>/<kind>` |
| `level` | `error` for a violation, `warning` for a warning, `note` for a note |
| `message.text` | the detail of the issue |
| physical location | the file relative to the root, with the line of an issue that has one; an issue of the whole file or of a key of the metadata holds no region |
| logical location | `path:<file>`, followed by `#<locus>` when the issue has a locus |
| `partialFingerprints["discriminator/v1"]` | the entry of a list that the issue concerns, when the locus does not suffice |

The locus is `link:<target as written>` for a reference, the JSON Pointer of a key for an issue of
the metadata, such as `/aliases` or `/groups`, and empty for an issue of the whole file. The run
declares itself failed in two cases. In the first, an invalid configuration or target stopped it,
and it holds the results of the sections that ran, none when no section ran. In the second, a file
could not be parsed, as `unreadable-file`, `unreadable-metadata`, `unreadable-binding-source` and
`unreadable-schema` report.
