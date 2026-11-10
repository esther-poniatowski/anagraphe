# Usage

Anagraphe serves repositories whose records already declare their navigation metadata. Install the
package in a dedicated environment, place the configuration file at the repository root, and keep
the referenced vocabulary and schemas under version control.

## Update managed blocks

The write command first renders and validates every selected index. It writes no file when any
blocking issue occurs:

```sh
anagraphe indexes write
```

An optional path restricts processing to one index, one member whose parent index must be updated,
or one directory:

```sh
anagraphe indexes write docs/
```

## Check repository drift

The check command compares source files with the deterministic rendering and preserves every byte.
When the configuration declares the section `references`, the same command checks the references,
and when it declares the section `bindings`, the bindings of the texts:

```sh
anagraphe check
```

An exit status of `1` reports an index violation, a stale block, a broken reference or an invalid
binding. An exit
status of `2` reports an invalid configuration, or a target that names no file to read.

## Move a file or a folder

A move through Anagraphe keeps every pointer to the moved files valid, and keeps the indexes of the
affected folders consistent. The command below first prints the planned rename and edits, and
changes no file:

```sh
anagraphe move notes/draft.md archive/draft.md --dry-run
```

Without the option `--dry-run`, the same command prints the plan, asks for a confirmation on a
terminal, and then applies the plan in three steps. The option `--yes` applies the plan without the
question; without a terminal and without `--yes`, the command stops with status `2` and changes no
file. A declined confirmation exits with status `1` and changes no file. The three steps are:

1. **Rewrite and rename.** The command rewrites every pointer to the moved files, and renames the
   path with `git mv` when Git tracks it. A failed rename restores every edited file.
2. **Update the indexes.** The key `index` of each moved member names the index of its new folder.
   An explicit list or a build manifest drops a member moved out of its folder. The generated
   regions of the old and the new parent indexes are written again.
3. **Check.** The command checks the moved and edited files, and prints each old path left in a
   file as a warning `residue`, such as a path held by an excluded file.

When an affected index already holds a blocking issue, the index keeps its region, and its issue
is printed. The move then exits with `1`, although its rename and its edits are applied.

## Check the references after a move outside Anagraphe

A file moved or renamed outside Anagraphe leaves stale the pointers to it. The command
`anagraphe refs check` reports each stale pointer at its line, under the kind of its defect:

```sh
anagraphe refs check
```

The [reference specification](references.md) lists the pointers read by the check, and the repair
of each reported kind.

## Use another repository root

A command run without `--root` takes the root from the variable `ANAGRAPHE_ROOT`, and otherwise
from the nearest folder, from the current one upwards, holding `config/tools/anagraphe.yml` or
`anagraphe.yml`, so that it runs from any subfolder of the repository. The root option lets an
orchestrator invoke Anagraphe without changing its working directory:

```sh
anagraphe check --root ../research-project
```

The targets, `--config` and `--output` are still read from the current folder.

The [configuration guide](configuration.md) defines the repository-owned inputs. The [CLI
reference](cli-reference.md) lists the complete command surface.
