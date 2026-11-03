# Architecture

Anagraphe separates its generic mechanisms from the policy of each repository, and its two
capabilities from each other. The package holds three layers, each depending only on the layers
listed before it:

| Layer | Modules | Responsibility |
| --- | --- | --- |
| core | `anagraphe.core` | issues and reports, the findings log, paths and patterns, Markdown links, the regions of a Markdown file read from Merismos, configuration primitives, file walks, cached reads, atomic writes, Git state |
| capabilities | `anagraphe.indexes`, `anagraphe.references` | generating the indexes, and checking the references between files |
| composition | `anagraphe.refactor`, `anagraphe.configuration`, `anagraphe.cli` | the moves, the sections of `anagraphe.yml`, and the command line |

Neither capability imports the other. Each capability parses its own section of `anagraphe.yml`
with the primitives of the core, and the composition layer joins the sections into one
configuration.

Each capability also declares the kinds of issue that it can report, in
`anagraphe.indexes.kinds` and `anagraphe.references.service`. The writer of the findings log,
`anagraphe.core.sarif`, receives these catalogues and the issues from the command line, so it
imports no capability. An issue carries its locus from the code that creates it, since only that
code holds the key or the target that it tested.

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

Within `anagraphe.references`, the check runs as a pipeline of three stages. A stage is extended by
declaring one more syntax, or by registering one more rule:

1. each syntax of `anagraphe.references.syntaxes` covering a file finds its candidates, each with
   its line, its column, and its region, from the metadata source declared in `anagraphe.core.metadata`.
   The syntaxes of Markdown take the link destinations and the code spans of a file from Merismos;
2. the resolver resolves the path of each reference under every path style, and the conventions
   of `anagraphe.references.conventions` state the formats and the styles that it admits;
3. each rule of the registry reads the resolved reference and its convention, and reports one
   kind of issue.

The column recorded for a candidate locates the exact characters of a target, so a rewrite
replaces those characters and leaves the rest of the file unchanged.

## Moves

A move crosses both capabilities, so it belongs to the composition module `anagraphe.refactor`.
The module asks `anagraphe.references.rewrite` for the rewrites of the pointers to the moved files,
and `anagraphe.indexes.relocation` for the edits of the indexes. Both return edits located in the
texts before the move, and `anagraphe.core.structured` applies them from the last position to the
first. The edits of the indexes are computed first, and a pointer edit overlapping one of them is
left out, so that no span is edited twice. The edits and the rename then form one transaction,
and the indexes service writes the regions of the affected indexes afterwards.
