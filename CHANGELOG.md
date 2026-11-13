# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- The logical targets of ADR 0006. A record names a record, a unit inside it, or a repository by
  the mapping `{repository, id, unit}`, defined in the schema resource
  `https://github.com/esther-poniatowski/anagraphe/schemas/addressing.v1.schema.yml`, which the
  package ships with the contract `anagraphe:repository@1` of `repository.yml`. The registry
  `specs/schema-registry.yml` of Anagraphe maps both for Kleisis.
- The section `targets` of `anagraphe.yml`, and the command `anagraphe targets check`, which
  `anagraphe check` also runs. The check reads `repository.yml`, the identifier of every record
  through `x-identifier` or the default key `id`, and the units of each record, then reports each
  finding of the first version of ADR 0006. A target into another repository is reported as
  `unverified-target`, at the level `note`.
- The package `anagraphe.targets` reads, normalizes and compares targets, and matches the entries of
  `x-target-contract`. The conformance cases `specs/conformance/targets.yml` fix each reading.
- An issue may take the level `note`, which the text report prints as `note:` and the findings log
  as the level `note`. A note does not block, and the summary line counts the notes when one is
  reported.

### Changed

- The walk of the schemas of record contracts moved from `anagraphe.bindings.schemas` to
  `anagraphe.core.schemas`, and the block anchors from `anagraphe.references.anchors` to
  `anagraphe.core.anchors`. The readings of the bindings are unchanged.

- **Breaking:** `anagraphe.yml` names its format under the key `_schema`, as its first key, with
  the value `anagraphe:configuration@2`. The key `schema_version` is retired: a command reading it
  stops with status 2 and names the value to write. A file without the key, or with another value,
  stops the same way.
- The schema registry of the section `bindings.records` is read in the format
  `_schema: kleisis:schema-registry@2`, which Kleisis now writes, and still in the legacy formats
  `schema_version: 1` and `schema_version: 2`.
- **Breaking:** a schema registry that declares no format stops the command with status 2 and names
  the value `_schema: kleisis:schema-registry@2`; version 0.3.0 read it as the format 1. A registry
  carrying both keys, or another value of either key, stops the same way.

### Fixed

- When the target of an entry of `external` is a web address, Anagraphe keeps it whole and does
  not check that it exists. Version 0.3.0 read the address as a path and reported no file.

## [0.3.0] - 2026-11-10

### Added

- A condition of `indexes.members` may name under `keys` the keys that a member declares at its
  top level, such as the block `metadata` of a YAML record.
- Without `--config`, every command reads `config/tools/anagraphe.yml` or `anagraphe.yml` below
  the root. When both files exist, the command stops with status 2 and names both; when neither
  exists, the message names both places.
- Without `--root`, the root is read from the new environment variable `ANAGRAPHE_ROOT`, and
  otherwise is the nearest folder, from the current one upwards, holding one of both files, and
  otherwise the current folder.
- The short options `-r` for `--root`, `-c` for `--config`, and `-o` for `--output`.
- `anagraphe bindings show --format json` prints the bindings as JSON.
- `anagraphe move` asks for a confirmation on a terminal once its plan is printed, and `--yes`
  applies the plan without the question.

### Changed

- A given `--config` is read from the current folder, no longer from the root, and an absent file
  is an error. A call that runs from the root, such as `--root . --config config/anagraphe.yml`,
  reads the same file.
- The targets of every command, the arguments `OLD` and `NEW` of `move` and the argument `PATH` of
  `bindings show` are read from the current folder, no longer from the root.
- Without a terminal and without `--yes`, `anagraphe move` stops with status 2 and changes no file;
  a declined confirmation exits with status 1.

### Removed

- The option `--json` of `anagraphe bindings show`, replaced by `--format json`, with no alias.

### Fixed

- A group holding no member is no longer reported for a sort key that no member holds, since it
  sorts nothing.

## [0.2.2] - 2026-11-10

### Changed

- Read Markdown through Merismos at commit `feb6654`, which follows Obsidian 1.15.0: a
  wikilink runs to its first closing `]]`, `[[note\|alias]]` links to `note`, and an unclosed
  `$$` opening a line opens a formula running to the end of its container.

## [0.2.1] - 2026-11-04

### Fixed

- The package ships the marker `py.typed`, so the type checkers of consumers read its annotations.
- The Release workflow attaches the wheel and the sdist to each release, through the publish
  command of semantic-release.

## [0.2.0] - 2026-11-04

### Added

- The section `bindings` of `anagraphe.yml` and the commands `anagraphe bindings check` and
  `anagraphe bindings show` resolve the bindings of texts to the roles of tools along the
  directory chain, as [ADR 0005](docs/adr/0005-text-bindings.md) proposes. A record binds through
  the fields marked by `x-binds` in its schema, found through the schema registry of Kleisis. The
  check reports the kinds `unbound-text`, `invalid-binding`, `unreadable-binding-source`,
  `invalid-schema-binding`, `unresolved-schema-reference` and `unreadable-schema`. The contract
  `anagraphe:bindings@1`, with its specification and its conformance cases, fixes the readings
  of the bindings, and the JSON output of `bindings show` names it.

### Changed

- The syntaxes `markdown`, `wikilink` and `code` read the link destinations and the code spans of a
  Markdown file from [Merismos](https://github.com/esther-poniatowski/merismos), a new dependency,
  instead of regular expressions. Six readings change:
  - a destination holding balanced parentheses or escaped characters is read whole;
  - a destination between angle brackets, such as `[a](<my file.md>)`, is found;
  - a link is found when its text runs over two lines;
  - the outer link of a badge, `[![badge](image)](target)`, is found;
  - a link inside indented code is no longer read;
  - a code span holding mathematics, such as `` `notes/$x$` ``, no longer yields a path.
- The check of the prose units of an index reads its fenced code blocks from Merismos: a view fenced
  by tildes is admitted, a longer fence holds its inner fences, and a block inside a callout belongs
  to the callout.

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
