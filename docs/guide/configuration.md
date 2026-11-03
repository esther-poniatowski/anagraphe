# Configuration

The configuration file `anagraphe.yml` binds Anagraphe to one repository. The file declares one
section per capability: `indexes` to generate the indexes, `references` to check the references
between files, and `bindings` to resolve the bindings of texts. A section left out disables its
capability. Each declared path is
relative to the repository root selected by the root option. Absolute paths and paths that resolve
outside that root are invalid.

## Layout of the file

A configuration enabling the indexes and the references declares the sources of metadata, the shared
exclusions, the section `indexes` with its two required paths, and the section `references` with
its defaults:

```yaml
schema_version: 2
metadata:
  - when: {types: [toml]}
    from: {toml: [project]}
exclude:
  paths: [build/]
indexes:
  vocabulary: config/vocabulary.yml
  index_types: config/index-types
references: {}
```

The metadata sources and the shared `exclude` apply to every section, and each section may
exclude further files under its own `exclude`, as the next sections state. The [reference specification](references.md) states
the keys of the section `references`, and the [bindings guide](bindings.md) those of the section
`bindings`. The rest of this page states the keys of the section
`indexes`.

## Metadata sources

The metadata of a file holds the fields tested by the filters `where` of the exclusions and of the
conventions, such as `status` or `role`. A metadata source names the place of these fields in a
file. The
rules below read the fields of TOML files under the table `project`, of JSON records under their key
`meta`, and of the notes of a legacy folder from no source at all:

```yaml
metadata:
  - when: {types: [toml]}
    from: {toml: [project]}
  - when: {types: [json]}
    from: {json: [meta]}
  - when: {paths: ["/legacy/"]}
    from: none
```

A rule holds a condition under `when`, on `paths` and `types`, and a source under `from`:

| Source | Fields read |
| --- | --- |
| `frontmatter` | the YAML block opening the file between two lines `---` |
| `{yaml: [paths]}` | the mappings of a YAML document at the listed key paths, merged in order, `.` naming the top level |
| `{json: [paths]}` | the same for a JSON document |
| `{toml: [paths]}` | the same for a TOML document, such as `[tool.notes]` at the path `tool.notes` |
| `none` | no field |

The rules cascade after built-in rules, and the last rule whose condition holds names the source.
The built-in rules read the frontmatter of a Markdown note, and the top level of a YAML document
overridden by its block `metadata`, as `{yaml: [., metadata]}` writes it. The source also marks the
**metadata region** of a file, where a pointer takes the conventions of the metadata. That region is
the block of a frontmatter, each YAML node at a declared path, or the whole of a JSON or TOML
document whose top level is declared.

## Exclusions

An exclusion keeps files out of a capability: tool state, generated output, archived notes or
decision records. An excluded file is neither indexed, nor checked, nor rewritten by a move. The
file stays a valid target, so a link to an archived note still resolves. The exclusion below selects
files by path and by metadata:

```yaml
exclude:
  paths:
    - build/
    - /drafts/
    - "*.tmp"
    - utils/macros/*
    - "!utils/macros/_index.md"
  where:
    - {status: archived}
    - {role: [audit, decision]}
  gitignore: false
```

| Key | Value | Default |
| --- | --- | --- |
| `paths` | patterns in the syntax of `.gitignore`, a later pattern prevailing over an earlier one | none |
| `where` | a list of metadata filters; a file is excluded when one filter selects it | none |
| `gitignore` | whether the patterns of the root `.gitignore` apply before the declared ones | `false` |

In the syntax of `.gitignore`, `build/` excludes every folder named `build`, `/drafts/` excludes
the folder `drafts` of the root, and `*.tmp` excludes every file of that suffix. A pattern opening
on `!` admits a path again, such as the index of a folder whose other files are excluded. The files
inside an excluded folder cannot be admitted again, so the example excludes `utils/macros/*`, the
files of the folder, instead of the folder itself.

A filter has the form of the filter `where` of a group: each key admits one value or a list of
values, and a file is selected when every key holds an admitted value. A file is tested by the
fields read from its metadata source.

A hidden file or folder, whose name opens on a dot, is excluded before any declared pattern, and an
exception such as `!.github/` admits it again. The folder `.git` is never read. The patterns of a
section follow the shared patterns, so an exception of a section admits a file that the shared
patterns exclude. The filters of both apply. The keys `directories`, `files` and `basenames` of
earlier releases stop the command with the pattern replacing each of them.

## Required inputs

The section `indexes` names one vocabulary file and one directory of index-type JSON Schemas.
The vocabulary declares the entry-point filename, the roles and the frames of the prose fields.
A schema declares an index type when two conditions hold: its filename ends in `.schema.yaml`,
and it holds the annotation `x-default-mode`. That annotation gives the default mode of the groups
of the type, `registry` or `sequence`. Any other value stops the command, and so does the retired
mode `construction`. The schemas must declare the type `module`. An index declaring no type takes
that type outside the locations that fix a type.

## Members of an index

An index lists the files of its folder whose type the section `indexes` admits under `members`, a
list of conditions on `paths`, `types` and `where`; one holding condition suffices. By default,
`members` admits the Markdown notes and the YAML records:

```yaml
indexes:
  members:
    - {types: [md, yml, yaml]}
    - {types: [pdf], paths: ["/papers/"]}
    - {types: [json], where: [{role: dataset}]}
```

The entry fields of a member, such as its aliases, its `index` and its `purpose`, are read from
its metadata source. A YAML record therefore joins its index whether its fields stand at its top
level or in its block `metadata`. A member without a metadata source, such as a PDF, is titled by
its file name and raises no issue about its fields. A YAML file that holds no record, such as the
configuration of a tool, is kept out by an exclusion pattern, such as `environment.yml` or
`*.schema.yaml`.

## Categorical values

A categorical key sorts the members of a group in the order of its declared values. The
vocabulary section `key_values` declares those values, either as a list or as a mapping from each
value to its gloss:

```yaml
key_values:
  kind:
    keynote: a plenary lecture by an invited speaker
    talk: a contributed presentation within a themed block
  bearing: [direct, indirect, none]
```

The check command reports a value outside this set in two cases. Either a filter or an `order`
names the value, or a member holds it under a categorical sort key of its group. The [index specification](index-specification.md) states how a group sorts by such a
key.

## Context relations

In an index, the key `context_relations` states the distinctions between two members. The
vocabulary section `context_relations` lists the admitted relation names:

```yaml
context_relations: [contrasts, visualizes]
```

## Archived statuses

Only an archived note may declare `superseded_by`, the link to the note replacing it. The
statuses marking a note as archived are listed in the vocabulary section `archived_statuses`:

```yaml
archived_statuses: [archived]
```

A note declaring `superseded_by` must hold one of these statuses, as the [index
specification](index-specification.md) states. Without the section, the check command reports
every note declaring `superseded_by`. When `key_values` declares the values of `status`, each
archived status must be one of them; otherwise the command stops.

## Task states and build manifests

The optional task-state file maps repository task identifiers to completion booleans. This mapping
lets an entry report an unknown or already completed blocker without making Anagraphe own the task
syntax:

```yaml
indexes:
  task_states: build/task-states.yml
```

The optional sequence mapping declares the build manifest of each folder whose order comes from
an external build system. Each path is relative to its folder, and the [index
specification](index-specification.md) states how a sequence group follows the manifest:

```yaml
indexes:
  sequences:
    manuscript/sections:
      - introduction.md
      - results.md
      - discussion.md
```

The Boolean setting `inspect_git` of the section `indexes` defaults to `true`. When enabled, an
index absent from `HEAD` must already contain a generated region.

## Migration classes

A migration class lets a repository keep the retired key `cites` in some of its files until a
declared migration. Each instance inside the class is reported as a warning naming the migration
awaited, and each instance outside it remains a violation:

```yaml
indexes:
  migrations:
    - key: cites
      paths: ["models/*"]
      awaits: the conversion of the research notes into Gnomon records
```

Each pattern of `paths` follows the `fnmatch` syntax. In that syntax, the wildcard `*` also
matches the separator `/`.
