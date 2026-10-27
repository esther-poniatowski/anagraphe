# Usage

Anagraphe serves repositories whose records already declare their navigation metadata. Install the
package in a dedicated environment, place the configuration file at the repository root, and keep
the referenced vocabulary and schemas under version control.

## Update managed blocks

The write command first renders and validates every selected index. It writes no file when any
blocking issue occurs:

```sh
anagraphe write
```

An optional path restricts processing to one index, one member whose parent index must be updated,
or one directory:

```sh
anagraphe write docs/
```

## Check repository drift

The check command compares source files with the deterministic rendering and preserves every byte:

```sh
anagraphe check
```

An exit status of `1` reports an index violation or stale block. An exit status of `2` reports an
invalid configuration or an unreadable input.

## Use another repository root

The root option lets an orchestrator invoke Anagraphe without changing its working directory:

```sh
anagraphe check --root ../research-project
```

The [configuration guide](configuration.md) defines the repository-owned inputs. The [CLI
reference](cli-reference.md) lists the complete command surface.
