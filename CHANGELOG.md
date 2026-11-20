# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `anagraphe-read` publishes the field paths in its interface: their parsing, their printing,
  their conversions to and from a JSON Pointer and the expansion of a pattern, so that every tool
  converts a field path through Anagraphe.
- The command `anagraphe records migrate --plan PATH [--dry-run | --check]`, which rewrites the
  contract named by the binding key of the records under a migration plan in the new contract
  `anagraphe:migration-plan@1`, keeping every other byte of each file. A plan is rejected when a
  contract lies outside the grammar of Kleisis, a `from` equals its `to` or is listed twice, a `to`
  is also a `from`, or a `to` is absent from the schema registry of the records. The findings
  `pending-migration`, `unmigratable-record` and `unreadable-record` form the section `migration`
  of the findings log. The schema `migration-plan.v1.schema.yml` is packaged and exported by the
  registry of Anagraphe.
- A TOML document is a record of the check of the targets and of the record registry when the
  section `metadata` declares a `toml` source for it, and the registry admits the format `toml`.
- The finding `invalid-identifier` also reports a declared item identifier outside the pattern
  `unit-id`, which is no longer kept as a unit, and a later key path of the metadata source holding
  another identifier than the first.
- `@anagraphe/read` takes the metadata source of each file from the host, through the options
  `metadata` and `toml` of `RepositoryIndex`, and exports `builtInSource`, `defaultIdentifier` and
  the type `MetadataSource`.
- The distribution `anagraphe-read`, in `packages/read-python`, with its own version `0.4.0`. The
  distribution holds the Python read side of Anagraphe and depends on no part of the command line.
  Its module `anagraphe_read` is its whole interface:
  - `open_repository` locates and loads the configuration of a repository, derives its identity
    and builds its resolution context; a root without `anagraphe.yml` opens with an empty
    configuration;
  - `Repository` exposes `root`, `identity`, `configuration`, `roles`, `binding`,
    `schema_registry`, `records`, `references`, `metadata`, `exempt`, `resolve`, `read` and
    `bindings`;
  - `RecordFile`, returned by `records`, holds the path of a record, the contract that it names,
    its data and its declared identifier, and gives the line and the column of each node of its
    data;
  - `references(path)` returns the `Pointer` of each target written in a file, found by the
    syntaxes of the section `references` and resolved as `anagraphe refs check` resolves it. A
    pointer holds the file that it names, and the path that it names under the conventions of the
    repository, which a broken link keeps;
    `metadata(path)` reads the metadata of a file from its declared source, and `exempt(path)`
    tells whether the shared exclusions leave it out. The syntaxes, the conventions and the
    resolution of the references move into the distribution, which therefore requires Merismos;
  - the value types of the targets, the resolutions, the bindings and the state providers, with
    `git_provider` and `ConfigurationError`;
  - the kinds of the findings carried by the results;
  - `ADDRESSING_ID`, `addressing_schema` and `IMPLEMENTED_SPECIFICATION`.

  Each release attaches the wheel and the sdist of the distribution. A consumer pins it by
  `anagraphe-read @ git+https://github.com/esther-poniatowski/anagraphe.git@<commit>#subdirectory=packages/read-python`.

### Changed

- **Breaking:** Hodegos locates the root of a command and the file `anagraphe.yml`, as its
  [specification](https://github.com/esther-poniatowski/hodegos/blob/main/docs/specification.md)
  states, in the command line, in `open_repository`, and in each state of another repository that
  the record resolver reads. The file lies at the root, in its subfolder `.config/`, or in a folder
  that the `hodegos.yml` of the root declares, and two places holding a file is an error.
  `config/tools/anagraphe.yml` is read only when `hodegos.yml` lists `config/tools`, also at a
  state. Hodegos reads the variable `ANAGRAPHE_ROOT`, which the help of `--root` no longer shows as
  an environment variable of the option. A root holding no configuration stops a command with
  `no configuration: write anagraphe.yml at the root, in .config/, or in a folder that hodegos.yml
  declares, or name it with --config`, and an invalid `hodegos.yml` stops it with status 2.
  `discover_configuration` of `anagraphe_read._core.configuration` replaces `find_root`,
  `locate_config`, `holds_config` and `CONFIG_LOCATIONS`. The distribution `anagraphe-read`
  requires Hodegos, and raises its version to `0.4.0`.
- The configuration format is `anagraphe:configuration@3`, and the section `indexes` no longer
  reads a vocabulary. The closed value sets of `key_values` become the enumerations of the metadata
  schema named by `indexes.metadata_schema`: the `enum` of `properties.K`, or of
  `properties.K.items`, in its order, which also orders a group sorted by the key. Its `$ref`
  resolve within the repository, and an absolute one through the `resources` of the schema
  registry of the records. The relations of `context_relations` become the enumeration of
  `properties.context_relations.items.properties.relation`; without it, every relation is
  admitted. The settings become keys of the section: `entry_point`, required, `generated_areas`,
  `archived_statuses`, checked against the enumeration of `status`, and `unlisted_roles`, for the
  roles that declared `listed: false`. A configuration in `anagraphe:configuration@2` stops with
  a message naming each change to write.
- The default identifier of a record whose schema declares no `x-identifier` is the key `id` read
  through the metadata source that `anagraphe.yml` declares for its file, as ADR 0006 states since
  its amendment of 2026-11-19. The first key path holding `id` gives the identifier. Under the
  built-in sources, a key `id` at the top level of a YAML document is now its identifier, read
  before its block `metadata`, and the same holds for a JSON document, which gains a built-in
  source.
- A nested group of an index designates a parent by the identifier that the check of the targets
  resolves, through `x-identifier` when the section `targets` is declared, instead of the key `id`
  of the merged metadata.
- The record resolver reads the default identifier of a record through the metadata source that the
  configuration of its state declares.
- `IMPLEMENTED_SPECIFICATION`, in Python and in TypeScript, no longer names `repository`, since no
  read side reads the contract `anagraphe:repository@1`. A read side of 0.10.0 therefore differs
  from this release on that key.
- The block anchor of `anagraphe.core.anchors` derives its name from the pattern `unit-id` of the
  resource, read by the new module `anagraphe.core.published`, which `anagraphe.targets.resource`
  now imports.

- The schema registry is read through `kleisis.registry`, the public reader of Kleisis, now a
  dependency. A registry of the legacy form `schema_version: 1` holding `resources` is rejected, as
  Kleisis rejects it, and a missing `resources` reads as an empty map.
- The identifier of a repository is derived, as ADR 0006 states since 2026-11-19. It is the override
  `repository.id` of `anagraphe.yml`, else the name of the remote `origin`, else the name of the
  folder of the root, each name kept only under the pattern `repository-id`. The former identifiers
  come from `repository.retired` of `anagraphe.yml`. The configuration keeps the format
  `anagraphe:configuration@2`, since the section `repository` is optional, and an invalid section
  stops a command with status 2. The function `anagraphe.targets.repository_identity` returns the
  identity, and `derive_identity` holds the derivation without Git.
- The check of the targets reports `identity-disagreement`, a warning, when the remote and the
  folder name two different identifiers without an override, and `retired-repository-manifest`, a
  warning, for a `repository.yml` left at the root. That finding names the section `repository` to
  write when the derived identifier or the configured former identifiers differ from those of the
  manifest.
- The record registry compares its key `repository` with the derived identifier, so a change of
  the identity makes it stale, and `anagraphe records write` refuses a repository without identity
  as `unidentified-repository`.
- The record resolver names a selected state by the override of its configuration, else by the
  name of its remote, and reads its former identifiers from that configuration.
- `@anagraphe/read` exports `deriveIdentity` and `readDeclaredIdentity`, and `RepositoryIndex`
  takes the identifier of the repository from the host, through its option `repository` and its
  method `setRepository`.
- The read side moves from `anagraphe` to the private subpackages of `anagraphe_read`, and the
  distribution `anagraphe` requires `anagraphe-read==0.4.0`. A consumer imports the names of
  `anagraphe_read` instead of the moved modules:
  - the modules `configuration`, `conditions`, `filters`, `exclusions`, `git_state`, `issues`,
    `json_text`, `metadata`, `published`, `schemas`, `anchors` and `files` of `anagraphe.core` move
    to `anagraphe_read._core`;
  - the modules of `anagraphe.targets` except `service` and `migration` move to
    `anagraphe_read._targets`, and `anagraphe.targets.registry.configuration` and `.contract` move
    to `anagraphe_read._targets.registry`;
  - `anagraphe.resolution` becomes `anagraphe_read._resolution`;
  - the modules of `anagraphe.bindings` except `service` move to `anagraphe_read._bindings`;
  - the packaged schemas move to `anagraphe_read/data/schemas`.
- Three modules are split, since each both read and wrote files: `write_atomically` moves to
  `anagraphe.core.writes`, `fetch_states` with `FetchStatus`, `Fetched` and `STATE_REFERENCES` to
  `anagraphe.states`, and `RecordRegistry.render()` becomes the function
  `anagraphe.targets.registry.rendering.render`.
- The packages `anagraphe.targets`, `anagraphe.targets.registry` and `anagraphe.bindings` export
  only their checks and writers: `TargetChecker`, `RegistryService` with `RetireRefused` and
  `WriteResult`, and `BindingChecker`.
- `TargetChecker` and `RegistryService` take the composition of the read side,
  `anagraphe_read._repository.Composition`. The function `load_config` takes an optional state
  provider and returns a `RepositoryConfig`, whose attribute `reading` holds the `Composition`.
- The distribution `anagraphe` no longer declares `pathspec`; the read distribution requires it.
- The tests of the findings logs check each log of Anagraphe with the profile interface
  `elenchos.profile`: `violations` judges its conformance, and `identities` states the identity of
  each result. The validator of `tests/test_sarif.py`, written from the text of the profile, is
  deleted with its planted breaches, since Elenchos tests its own rules. The extra `test` and
  `environment.yml` pin Elenchos by commit, without its extra `validate`.

### Fixed

- A target that the process may not examine, such as a path below a folder of another user named
  by a target opening on `/`, names no file. `anagraphe refs check` stopped there with a
  `PermissionError`.

### Removed

- The key `indexes.vocabulary`, with `load_vocabulary`, `validate_vocabulary` and
  `RETIRED_VOCABULARY`, `Settings.from_vocabulary`, `FieldRules.from_vocabulary`,
  `declared_values`, and the frames of the prose fields: `Frame`, `frame_of`,
  `FieldRules.check_purpose` and `FieldRules.check_contribution`. Hermeneia checks the form of a
  prose field, and the section `roles` of a vocabulary is no longer read.

- The manifest reader `anagraphe.targets.manifest`, with `Manifest`, `ManifestReading`,
  `read_manifest` and `check_manifest`, and the kinds `invalid-repository-manifest` and
  `legacy-repository-manifest`. The schema of `anagraphe:repository@1` stays packaged and
  registered until the files bound to it migrate.
- `manifest.ts` of `@anagraphe/read`, with `readManifest`, `MANIFEST_FILE`, the kinds of the
  manifest, the types `Manifest`, `ManifestProblem` and `ManifestReading`, and the getter
  `RepositoryIndex.manifest`.

## [0.10.0] - 2026-11-17

### Added

- The Git provider of ADR 0010, `anagraphe.resolution.git.GitProvider`. It reads each selected
  state from the objects of its commit, in the clone of its entry, then in the cache of the
  machine, and hashes every object that it reads against its identifier.
- The command `anagraphe states fetch`, which fetches into the cache each selected state that no
  Git store of the machine holds, and the environment variable `ANAGRAPHE_CACHE`, which names the
  cache.
- The remote of each submodule in the resolution context, read from `.gitmodules`.

### Changed

- The check of the targets reads the states of other repositories through the Git provider. A
  target into a submodule whose clone holds its commit is verified without the network.
- A remote address beginning with `-` is rejected, since Git would read it as an option.

## [0.9.0] - 2026-11-17

### Added

- The record resolver of ADR 0009, in the module `anagraphe.resolution`. Its operation `resolve`
  locates the record of a target into another repository at a selected state, and its operation
  `read` returns the verified bytes of that record with their provenance. A provider of the states
  implements the protocol `StateProvider`; the class `MemoryProvider` serves the states of tests.
- The section `resolution` of `anagraphe.yml`, which declares each cited repository with a full
  commit and a remote address, and names the machine file of the local clones under `local`. The
  environment variable `ANAGRAPHE_REPOSITORIES` names a machine file outside the repository.
- The kinds `renamed-repository`, `unknown-repository`, `invalid-target-repository`,
  `linked-target-path`, `escaping-target-path`, `stale-target-registry`, `invalid-target-state` and
  `unreadable-target-state` of the section `targets`.
- The conformance cases of the resolver, `specs/conformance/resolution.yml`.

### Changed

- The check of the targets resolves each target into another repository through the context of the
  root, instead of noting it as `unverified-target`. This release installs no provider of the
  states, so each target into a repository of the context receives the warning
  `unreadable-target-state`. A target into a repository that the context does not select receives
  the error `unknown-repository`.
- The note `unverified-target` keeps two legitimate gaps: a state holding no record registry, and a
  record whose contract has no schema in the checked repository.
- A target naming a former identifier of the checked repository receives the warning
  `renamed-repository`, and is checked in that repository.

## [0.8.1] - 2026-11-16

### Fixed

- The note `locally-excluded` leaves out a path that a hidden name or a declared pattern already
  excludes, since a rule of `.git/info/exclude` does not alone keep that path out of the checks.

## [0.8.0] - 2026-11-16

### Changed

- The key `git_ignored` reads the rules of the `.gitignore` files and of `.git/info/exclude` only,
  never the global excludes file of the machine. Therefore, two clones of one commit exclude the
  same files.

### Added

- The note `locally-excluded` of the section `exclusions`. Each command reports every file or
  folder excluded by a rule of `.git/info/exclude` alone, since no commit records that rule.

## [0.7.0] - 2026-11-16

### Added

- The key `git_ignored` of an `exclude` mapping, `false` by default. When it is `true`, every file
  ignored and not tracked by Git is excluded. Git reads the rules of every `.gitignore`, of
  `.git/info/exclude` and of the global excludes file. A session sharing a working tree lists an
  unfinished file in `.git/info/exclude`, and the file stays out of every check until Git tracks
  it.

## [0.6.0] - 2026-11-15

### Added

- The field paths of ADR 0008, `docs/adr/0008-field-paths.md`, with their specification,
  `docs/specification/field-paths.md`. The definitions `field-path` and `field-path-pattern` of
  the resource `addressing.v1` state the grammar of a field path, such as `subject.foils[1].symbol`,
  and of a pattern holding the wildcards `[*]` and `*`. The conformance cases
  `specs/conformance/field-paths.yml` fix the parsing, the canonical printing, the conversions to
  and from a JSON Pointer, and the expansion of a pattern.
- The module `anagraphe.targets.field_paths`, exported from `anagraphe.targets`, and the module
  `field-path` of `@anagraphe/read`. Both parse and print field paths and patterns, convert them to
  and from JSON Pointers within a document, and expand a pattern, with the checks derived from the
  patterns of the resource.
- The key `read_sides` of the section `targets`. The key names each file holding the versions
  implemented by another read side of the repository, with the JSON Pointer of that declaration.
  `anagraphe targets check` compares each declaration with `IMPLEMENTED_SPECIFICATION`, and reports
  `read-side-mismatch` and `unreadable-read-side`.
- The TypeScript package `@anagraphe/read`, in the directory `packages/read`. The package reads the
  addressing as the Python read side reads it (targets, identifier declarations, units, manifest and
  record registry), and passes the conformance cases of `specs/conformance/targets.yml` and
  `specs/conformance/record-registry.yml`. A host supplies adapters for three ports: the binding of
  a record, the loading of a schema, and the files. The live index of the package resolves a target
  of the open repository against its records, then against the retired identifiers of the registry.
  Each release attaches the package as a tarball.
- The constant `anagraphe.targets.IMPLEMENTED_SPECIFICATION`. The constant names the versions of
  the addressing, of the manifest and of the record registry implemented by the Python read side,
  and the TypeScript package exports the same mapping.
- The definitions `contract-entry` and `property-path` of the resource `addressing.v1`, which state
  the grammar of an entry of `x-target-contract` and of the path of `x-identifier`. Both read sides
  read these patterns from the resource.
- The specification of the record registry, `docs/specification/record-registry.md`: how a read
  side reads the registry and looks up an identifier in it.
- The record registry of ADR 0007. Each repository commits a registry in the contract
  `anagraphe:record-registry@1`, whose schema
  `https://github.com/esther-poniatowski/anagraphe/schemas/record-registry.v1.schema.yml` the
  package ships and the registry `specs/schema-registry.yml` exports. The registry maps each record
  identifier to the path and the format of its record, and keeps the retired identifiers with
  their date and their successor. The conformance cases `specs/conformance/record-registry.yml`
  fix its reading and the findings of its check.
- The section `records` of `anagraphe.yml`, whose key `path` names the registry,
  `record-registry.yml` at the root by default. The section requires the section `targets`.
- The command `anagraphe records write`, which generates the registry from the walk of the check
  of the targets and carries over its retired identifiers. The write changes no file when the
  records, the registry or `repository.yml` hold a defect, such as a missing, invalid, duplicate or
  retired identifier, an identifier of the registry naming no record and not retired, or a schema
  that cannot be read.
- The command `anagraphe records check`, which `anagraphe check` also runs, and which reports
  `invalid-record-registry`, `stale-registry`, `vanished-identifier`, `reused-identifier` and
  `unknown-successor` at the JSON Pointer of each entry.
- The command `anagraphe records retire ID [--replaced-by NEW]`, which moves an identifier that no
  record holds from `records` into `retired`, with the date of the day and an optional successor.
  The command refuses while a schema cannot be read, since a record may hold the identifier
  unseen.

### Changed

- When the section `records` is declared, `anagraphe targets check` reads the retired identifiers
  of the registry. A target naming an identifier retired by a rename is reported as
  `renamed-target`, a warning, and is checked against the record of its last successor. A target
  naming an identifier retired without a successor is reported as `retired-target`, an error. Both
  findings replace `unknown-record` for a retired identifier.
- An atomic write of the core creates a file that does not exist yet, and removes it if a later
  file of the same write cannot be replaced.

### Fixed

- The patterns of the packaged schemas close on `$(?!\n)`, so that a validator of Python, which
  reads `$` before a final line break, refuses an identifier, a path or a date closed by a line
  break, as ECMA-262 does.
- A JSON document holding `NaN`, `Infinity` or `-Infinity`, which RFC 8259 excludes, is no longer
  read as JSON by the Python read side, as the TypeScript read side rejects it.
- The TypeScript read package orders the keys of a mapping holding a merge key `<<` as PyYAML
  orders them.
- A YAML timestamp naming an impossible date, such as `2026-02-30`, no longer stops Anagraphe with a
  `ValueError`. A frontmatter or a manifest holding one is reported as unreadable, a configuration
  or a schema registry holding one is a configuration error, and a scalar reading as one is quoted.

## [0.5.0] - 2026-11-14

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

## [0.4.0] - 2026-11-11

### Changed

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

## [0.3.1] - 2026-11-10

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
