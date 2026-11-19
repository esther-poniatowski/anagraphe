# Architecture

Anagraphe separates its generic mechanisms from the policy of each repository, its read side from
its command line, and its capabilities from each other.

## Two distributions

The repository ships two Python distributions, and the dependency runs one way:

| Distribution | Source | Holds |
| --- | --- | --- |
| `anagraphe-read` | `packages/read-python/src/anagraphe_read` | the readers of a repository: its configuration, its identity, its records and their logical targets, the record resolver with its state providers, the reading of record registries, the bindings of texts, and every schema that Anagraphe publishes |
| `anagraphe` | `src/anagraphe` | the command line and every writer: the indexes, the references, the moves, the record registry as written, the migration of the records, the fetch of the states, and the checks |

The package `anagraphe` imports `anagraphe_read`, and `anagraphe_read` imports no module of
`anagraphe`. Three checks enforce that direction:

- a test of the read distribution scans the imports of its modules;
- a second test imports every module of the read distribution while the package `anagraphe` is
  blocked;
- a CI job runs the suite of the read distribution without the command line installed.

Within the read distribution, the module `anagraphe_read` is the interface, and every subpackage
opening on an underscore is private. The command line imports those private modules, so both
distributions must be installed from the same commit.

The read distribution reads files and writes none. Each writer of the read side lies in the command
line, beside the reader that it serves:

- `anagraphe.core.writes` replaces files atomically, for the walks and reads of
  `anagraphe_read._core.files`;
- `anagraphe.states` fetches the selected states into the cache that the Git provider of
  `anagraphe_read._resolution.git` reads;
- `anagraphe.targets.registry.rendering` writes the record registry that
  `anagraphe_read._targets.registry.contract` reads.

The composition of the read side, `anagraphe_read._repository.compose`, builds each object of the
read side once:

- the identity of the repository;
- the walk of its records, with the declarations of their contracts;
- the key binding a record to its contract;
- the resolution context, the record resolver and the binding resolver.

The entry point `open_repository` and the configuration of the command line,
`anagraphe.configuration.load_config`, both build their objects through it. The check of the targets
and the record registry receive that composition. Two services of the command line build an object
of their own. The check of the bindings builds its binding resolver, since that resolver collects
the defects that the check reports. The migration of the records builds a walk that leaves out its
plan file.

## Layers of the command line

The package `anagraphe` holds three layers, each depending only on the layers listed before it and
on the read distribution:

| Layer | Modules | Responsibility |
| --- | --- | --- |
| core | `anagraphe.core` | the findings log, paths and patterns, Markdown links, the regions of a Markdown file read from Merismos, structured edits, atomic writes |
| capabilities | `anagraphe.indexes`, `anagraphe.references`, `anagraphe.bindings`, `anagraphe.targets` | generating the indexes, checking the references between files, checking the bindings of texts, checking the logical targets between records, writing the record registry and migrating the records |
| composition | `anagraphe.refactor`, `anagraphe.states`, `anagraphe.configuration`, `anagraphe.cli` | the moves, the fetch of the states, the sections of `anagraphe.yml`, and the command line |

No capability imports another. The read distribution parses the sections `targets`, `records`,
`bindings`, `resolution` and `repository` of `anagraphe.yml`. The capabilities `anagraphe.indexes`
and `anagraphe.references` parse the sections `indexes` and `references` with the primitives of the
read core, and the composition layer joins every section into one configuration. The composition
layer also hands the indexes the identifier of a file as the targets resolve it, so a nested group
honours `x-identifier` without importing the capability.

Each capability also declares the kinds of issue that it can report, in `anagraphe.indexes.kinds`,
`anagraphe.references.service`, `anagraphe_read._bindings.kinds`, `anagraphe_read._targets.kinds`
and `anagraphe.targets.registry.kinds`. The writer of the findings log, `anagraphe.core.sarif`,
receives these catalogues and the issues from the command line, so it imports no capability. An
issue carries its locus from the code that creates it, since only that code holds the key or the
target that it tested.

## Indexes

Within `anagraphe.indexes`, the domain modules parse records and generated regions, assign the
members to groups, order them, render the entries, and report issues. These modules depend only on supplied
values and narrow callbacks. In particular, they do not import a repository's task parser, paths,
vocabulary loader, or sequence source. A repository adapter may derive those values from its own
control files before invoking the service.

Write mode validates the complete selection before changing a file. Each file replacement is
atomic. If an ordinary replacement raises an operating-system error, Anagraphe restores the files
replaced earlier in that run. This rollback does not cover process termination or machine failure.

## References

The check of `anagraphe.references` runs as a pipeline of three stages, whose first two stages lie
in the read distribution, under `anagraphe_read._references`, so that `Repository.references`
finds and resolves the pointers of a file as the check does. A stage is extended by
declaring one more syntax, or by registering one more rule:

1. each syntax of `anagraphe_read._references.syntaxes` covering a file finds its candidates, each with
   its line, its column, and its region, from the metadata source declared in
   `anagraphe_read._core.metadata`.
   The syntaxes of Markdown take the link destinations and the code spans of a file from Merismos;
2. the resolver resolves the path of each reference under every path style, and the conventions
   of `anagraphe_read._references.conventions` state the formats and the styles that it admits;
3. each rule of the registry reads the resolved reference and its convention, and reports one
   kind of issue.

The column recorded for a candidate locates the exact characters of a target, so a rewrite
replaces those characters and leaves the rest of the file unchanged.

## Bindings

Within `anagraphe_read._bindings`, the resolver reads the declaration of a file, then the
declaration of the index of each enclosing directory, and combines them by the merge rule of the
role. A text declares in its frontmatter, through the metadata reader of the core. A record declares
in the fields marked by `x-binds` in its schema, found once per contract through the schema
registry. The check of `anagraphe.bindings` selects the texts read through their frontmatter, the
records when the repository declares records, and the files that a condition `required` selects,
then reports the kinds of `anagraphe_read._bindings.kinds`.

## Targets

Within `anagraphe_read._targets`, the model reads a target and matches the entries of
`x-target-contract`, with the patterns compiled from the resource of the package data. The
declarations of each contract, its identifier field, its units, its target fields and its
`x-implements`, are read once from the walk of the schemas of the core, which leaves the URI of the
resource unresolved. The check of `anagraphe.targets` first derives the identity of the repository,
in `anagraphe_read._targets.identity`. Next, the check reads the identifier of every record of the
repository into one table, and reports the identifiers and the targets of the selected records
against that table. The module `anagraphe_read._targets.walk` defines the walk, and the record registry of
`anagraphe.targets.registry` shares it. The registry maps the identifiers of the walk to their
files, and the check of the targets reads its retired identifiers. The committed registry is the
source of the record resolver of `anagraphe_read._resolution` for a target into another repository,
whereas the check within one repository keeps its walk.

## Moves

A move crosses the indexes and the references, so it belongs to the composition module `anagraphe.refactor`.
The module asks `anagraphe.references.rewrite` for the rewrites of the pointers to the moved files,
and `anagraphe.indexes.relocation` for the edits of the indexes. Both return edits located in the
texts before the move, and `anagraphe.core.structured` applies them from the last position to the
first. The edits of the indexes are computed first, and a pointer edit overlapping one of them is
left out, so that no span is edited twice. The edits and the rename then form one transaction,
and the indexes service writes the regions of the affected indexes afterwards.
