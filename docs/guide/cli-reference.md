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
anagraphe records write [--root PATH] [--config PATH]
anagraphe records check [--root PATH] [--config PATH] [--format FORMAT] [--output PATH]
anagraphe records retire ID [--replaced-by NEW] [--root PATH] [--config PATH]
anagraphe records migrate --plan PATH [--dry-run | --check] [--root PATH] [--config PATH] [--format FORMAT] [--output PATH]
anagraphe states fetch [--root PATH] [--config PATH]
anagraphe move OLD NEW [--dry-run] [--yes] [--root PATH] [--config PATH]
anagraphe repository rename OLD NEW [--repository PATH] [--dry-run] [--yes] [--format FORMAT] [--root PATH] [--config PATH]
```

| Command | Effect |
| --- | --- |
| `anagraphe check` | runs the check of every declared section, and changes no file |
| `anagraphe indexes check` | reports the generated regions that differ from their rendering, and changes no file |
| `anagraphe indexes write` | replaces the generated regions, only once every selected index validates |
| `anagraphe refs check` | reports the references that name no file or anchor, or break a convention |
| `anagraphe bindings check` | reports the required texts bound to no value, and the invalid declarations and marks |
| `anagraphe bindings show` | prints the values bound to a file for each role, with the declarations supplying them |
| `anagraphe targets check` | reports the logical targets that do not resolve, within the repository or at the selected state of another repository, the defects of the identifiers and of their declarations, and the warnings of the identity of the repository |
| `anagraphe records write` | generates the record registry from the records, carrying over its retired identifiers, and writes no file when the records or the registry hold a defect, or the repository has no identity |
| `anagraphe records check` | checks the record registry against the records, and changes no file |
| `anagraphe records retire` | moves an identifier held by no record from the records of the registry into its retired identifiers, with the date and an optional successor |
| `anagraphe records migrate` | rewrites the contract named by the binding key of each record whose contract a migration plan replaces, keeping every other byte, and writes no file when a record cannot be read or rewritten; `--dry-run` lists the changes and `--check` reports them, both changing no file |
| `anagraphe states fetch` | fetches into the cache of the machine each selected state of the resolution context that no Git store of the machine holds; the only command that uses the network |
| `anagraphe move` | moves a file or a folder, rewrites every pointer to it, and updates the affected indexes, once the plan is confirmed on a terminal or by `--yes`; `--dry-run` prints the plan and changes no file |
| `anagraphe repository rename` | records the rename of a repository identifier in the renamed repository, and rewrites the targets and the entries of the resolution context naming it, in the root and in each submodule checked out under it, once the plan is confirmed on a terminal or by `--yes`; `--dry-run` prints the plan and changes no file, and the command commits nothing |

| Option | Purpose | Default |
| --- | --- | --- |
| `-r`, `--root PATH` | selects the repository root, from which every reported path is written | `ANAGRAPHE_ROOT`, else the nearest folder, from the current one upwards, holding `anagraphe.yml` at one of its places, else the current folder |
| `-c`, `--config PATH` | selects the configuration file, relative to the current folder | `anagraphe.yml` at the root, in its `.config/`, or in its `config/`, as the [specification of Hodegos](https://github.com/esther-poniatowski/hodegos/blob/main/docs/specification.md) states; two places holding the file is an error |
| `--role ROLE` | of `bindings show`: a role to resolve, repeatable | every declared role |
| `--merge RULE` | of `bindings show`: `override` or `union` | `override` |
| `--replaced-by NEW` | of `records retire`: the successor of a rename, a record or a retired identifier | no successor |
| `--repository PATH` | of `repository rename`: the folder of the renamed repository, relative to the current folder, either the root or a submodule checked out under it | the root |
| `--plan PATH` | of `records migrate`, required: the migration plan in `anagraphe:migration-plan@1`, relative to the current folder | none |
| `--check` | of `records migrate`: reports each record to migrate as a violation, and changes no file; excludes `--dry-run` | applies the plan |
| `--format FORMAT` | of the check commands and of `records migrate --check`: `text`, or `sarif` for a findings log; of `bindings show`: `text`, or `json`; of `repository rename`: `text`, or `json` for the plan, with `--dry-run` or `--yes` | `text` |
| `-o`, `--output PATH` | with `--format sarif` only: writes the log to `PATH`, relative to the current folder, and creates its missing folders | standard output |
| `--dry-run` | of `move` and `repository rename`: prints the plan and changes no file; of `records migrate`: lists the changes and changes no file | applies the plan |
| `--yes` | of `move` and `repository rename`: applies the plan without asking for a confirmation | asks on a terminal, and stops with status `2` without one |

Every path typed on the command line, a target, `OLD` and `NEW` of `move`, `--repository`, `--plan`, `--config` or `--output`, is read from
the current folder; every path written in the configuration is read from the root. For the
indexes, each path may name an index, a directory, or a member whose parent index must be
processed. For the references, the bindings and the targets, each path names a file or a directory
to check. The command `records check` reads every record of the repository, even when
`anagraphe check` runs it with paths.

## Output and exit status

Each command prints one line per issue, `path:line: [warning: |note: ]kind: detail`, then one
summary line per section. The summary counts the violations, the warnings, the notes when one is
reported, and the issues of each kind. A warning and a note do not block, so they leave the exit
status at `0`.

| Status | Meaning |
| --- | --- |
| `0` | no issue blocks |
| `1` | at least one violation is reported, `records write`, `records retire`, `records migrate` or `repository rename` refuses its change, a confirmation of `move` or `repository rename` is declined, `records migrate --check` finds a record to migrate, or `states fetch` leaves a state absent from the machine |
| `2` | the configuration, a named target, a migration plan, or a required section is invalid or absent; two options exclude each other; the log cannot be written; a move or a rename lacks its confirmation without a terminal; or `repository rename` receives an identifier outside the pattern `repository-id`, two equal identifiers, a folder `--repository` outside its scope, or `--format json` without `--dry-run` or `--yes` |

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
`unreadable-schema` report, or the record registry could not be compared, as
`invalid-record-registry` reports.

## Plan of a rename

Under the option `--format json`, the command `repository rename` prints its plan on standard
output, as one JSON object. A tool such as Architekta reads the plan, shows it, and commits once per
repository. The [targets guide](targets.md) lists the values edited by a rename, and the
[decision on repository renames](../adr/0012-repository-rename.md) records the reason for each
choice. The object holds the keys below:

| Key | Value |
| --- | --- |
| `version` | the version of the form of the plan, `1`, raised when a key changes its meaning or disappears |
| `old`, `new` | the identifiers of the rename |
| `renamed` | the path of the renamed repository from the root, `.` for the root |
| `applied` | true when the command wrote the files: only under `--yes`, without `--dry-run` and without a refusal |
| `refusals` | the reason of each refusal, empty when the rename is admitted |
| `repositories` | the root, then each submodule checked out under it, each with `path` from the root, `identifier` before the rename or null, `files` and `warnings` |

Each entry of the list `files` holds three keys:

- `path`, the path of the file relative to its repository;
- `created`, true for a file created by the rename;
- `edits`, the list of its edited values.

Each edit holds its kind under the key `kind`, one of `identifier`, `retired`, `registry`,
`resolution` and `target`. The key `pointer` holds the JSON Pointer of the value, or of the key
under its former name for an edit of kind `resolution`. The key `line` holds the line of the value
after the rename. The keys `old` and `new` hold the values before and after; `old` is null for an
item added to a list. Each warning holds its `kind` and its `detail`, with a `line` that is always
null. Its `path` is relative to its repository, empty for the repository itself, and absolute for a
machine file outside the repository. The plan below renames `x-lab` to `x-hub` at
`projects/x`, under a root `lab` holding no citer, and rewrites one key of the resolution context
of `projects/y`:

```json
{
  "version": 1,
  "old": "x-lab",
  "new": "x-hub",
  "renamed": "projects/x",
  "applied": false,
  "refusals": [],
  "repositories": [
    {"path": ".", "identifier": "lab", "files": [], "warnings": []},
    {
      "path": "projects/x",
      "identifier": "x-lab",
      "files": [
        {
          "path": "anagraphe.yml",
          "created": false,
          "edits": [
            {"kind": "identifier", "pointer": "/repository/id", "line": 4, "old": "x-lab", "new": "x-hub"},
            {"kind": "retired", "pointer": "/repository/retired/1", "line": 5, "old": null, "new": "x-lab"}
          ]
        }
      ],
      "warnings": []
    },
    {
      "path": "projects/y",
      "identifier": "y-lab",
      "files": [
        {
          "path": "anagraphe.yml",
          "created": false,
          "edits": [
            {"kind": "resolution", "pointer": "/resolution/repositories/x-lab", "line": 8, "old": "x-lab", "new": "x-hub"}
          ]
        }
      ],
      "warnings": []
    }
  ]
}
```
