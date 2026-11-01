# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-11-01

### Changed

- **Breaking:** the configuration `anagraphe.yml` takes `schema_version: 2`. This layout holds a shared
  `exclude`, then one section per capability: `indexes`, holding the former top-level keys, and
  `references`. The version 1 fails with a message naming the new layout.
- **Breaking:** the command line holds one group per section, as
  [ADR 0003](docs/adr/0003-pointers-across-moves.md) proposes. The command `anagraphe write` becomes
  `anagraphe indexes write`, and `anagraphe check` runs the check of every declared section.
- **Breaking:** the modules move into the subpackages `anagraphe.core`, `anagraphe.indexes` and
  `anagraphe.references`.
- **Breaking:** an exclusion selects files by patterns in the syntax of `.gitignore` under `paths`,
  exceptions included, and by metadata filters under `where`, such as `{status: archived}`. The
  key `gitignore` also applies the root `.gitignore`. The keys `directories`, `files` and
  `basenames` fail with the pattern replacing each of them. Hidden files and folders are excluded
  unless an exception admits them.
- **Breaking:** the summary line of a check names its section and counts each kind of issue, as in
  `indexes: processed 3 indexes holding blocks: 1 violations, 0 warnings (1 stale-block)`.
- **Breaking:** a target error is printed after `target:`, not after `configuration:`.
- **Breaking:** the index of a collection specifies the membership, the order and the nesting of
  its groups (e.g. the group keys `where`, `members`, `sort`, `order`, `sequence`), as
  [ADR 0002](docs/adr/0002-collection-owned-order.md) decides.
- **Breaking:** the title, then the path, break the ties of every sort key, the key `date`
  included.
- The check command reports each source of order ignored by the mode of its group.
- The check command reports a retired key under every index, whether or not it holds the region
  of groups.
- A key of the members sorts its numbers by value, before its other values.

### Added

- The section `references.unlinkable` declares the files that the other files must not cite, by
  path, type or metadata, such as `{status: archived}`, with the citing files exempted under
  `unless` and a warning level under `blocking: false`. A pointer citing such a file is reported as
  `unlinkable-target`, the kind of the Geonexus frontmatter checker.
- The indexes report a file whose metadata cannot be parsed as `unreadable-metadata`, in place of
  the missing fields that followed from its empty metadata, and the findings log declares the run
  incomplete.
- The commands `check`, `indexes check` and `refs check` write their findings as a SARIF 2.1.0 log
  of the findings profile of Elenchos under `--format sarif`, on standard output or at the path of
  `--output`, as [ADR 0004](docs/adr/0004-findings-output.md) proposes. Each issue carries a locus,
  such as `link:<target>` or the JSON Pointer of its key, and each section declares its kinds in a
  catalogue. The text report and the exit status are unchanged.
- The command `anagraphe refs check` reports the references that name no file or anchor, or break
  a convention. Its issue kinds are `broken`, `outside-repository`, `convention`, `broken-anchor`,
  `heading-fragment`, `foreign-scheme` and `unreadable-file`, each defined by the
  [reference specification](docs/guide/references.md).
- The conventions of the pointers under `references.conventions`: cascading rules that admit
  syntaxes, path styles (`relative`, `root`, `absolute`, `shortest`, `{base: folder}`) and the
  strictness of each syntax, by path pattern, file type, metadata filter, region or syntax. They
  replace the bases `markdown.body`, `markdown.frontmatter` and `records[].base`. The issue kinds
  `link-format` and `ambiguous-link` are added.
- The registry of syntaxes under `references.syntaxes`, replacing `references.markdown` and
  `references.records`: the built-in syntaxes `markdown`, `wikilink`, `code` (a backticked path)
  and `latex`, each redefinable, and further syntaxes declared by a pattern or by the keys of a
  YAML, JSON or TOML document.
- **Breaking:** an index lists the files of the types declared under `indexes.members`, by
  default its Markdown notes and its YAML records, and reads their entry fields from their
  metadata source. A YAML record without a block `metadata` is now listed; before, it was dropped
  without notice. A file of another type, such as a PDF, can be declared a member. A file declared
  under the index key `files` is listed once, by its declared entry.
- The metadata sources under the top-level key `metadata`: the frontmatter, or a YAML, JSON or TOML
  document at declared key paths, or none, by path and type. The filters of the exclusions and of
  the conventions read through them, and they mark the regions `metadata` and `content`.
- The command `anagraphe move` moves a file or a folder, rewrites every pointer to it, and updates
  the affected indexes, as the [usage guide](docs/guide/usage.md) describes.
- The index key `external` and the member key `superseded_by`, each resolved to a file. A note
  declaring `superseded_by` must hold an archived status.
- The vocabulary sections `key_values`, `context_relations` and `archived_statuses`.
- The configuration key `migrations`, to tolerate the retired key `cites` in declared files.
- The issue kinds `invalid-link`, `duplicate-member`, `unknown-filter-key`, `undeclared-value`,
  `unranked-value`, `ignored-order`, `nest-cycle`, `invalid-external`, `unarchived-superseded`,
  `retired-key` and `migration-key`, each defined by the
  [index specification](docs/guide/index-specification.md).

### Removed

- **Breaking:** every construction retired by ADR 0002 (e.g. the member key `group`, the mode
  `construction`). Each leftover fails with a message naming its replacement.
- **Breaking:** the core no longer parses typed citations, so the checks of citations and of goals
  are removed.
- **Breaking:** the issue kinds `unknown-target`, `missing-evidence`, `mirror-citation`,
  `order-conflict`, `unknown-goal`, `off-goal`, `redundant-sequence` and `unknown-sequence-entry`
  are removed. A redundant or unknown entry of a sequence is now reported as `ignored-order` or
  `invalid-link`.
