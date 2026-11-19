# Configuration

The configuration file `anagraphe.yml` binds Anagraphe to one repository. Without the option
`--config`, a command reads `config/tools/anagraphe.yml` below the repository root, or
`anagraphe.yml` at the root; when both files exist, the command stops with an error naming both. A
file named by `--config` is read from the current folder, and its absence is an error. The [CLI
reference](cli-reference.md) states how a command finds the root. The file names its format under
`_schema`, as its first key, and a command stops with status 2 when the key is absent or holds
another value than `anagraphe:configuration@3`. The file also declares one section per capability:
`indexes` to generate the indexes, `references` to check the references between files, `bindings` to
resolve the bindings of texts, and `targets` to check the logical targets between records and the
versions declared by the other read sides. The section `records` names the record registry and
enables its commands. A section left out disables its capability. The optional section
`repository` overrides the identifier that Anagraphe derives for the repository, and lists its
former identifiers; it enables no command. Each declared path is relative to
the repository root selected by the root option. Absolute paths and paths that resolve outside that
root are invalid.

## Layout of the file

A configuration enabling the indexes and the references declares the sources of metadata, the shared
exclusions, the section `indexes` with its two required keys and its metadata schema, and the
section `references` with its defaults:

```yaml
_schema: anagraphe:configuration@3
metadata:
  - when: {types: [toml]}
    from: {toml: [project]}
exclude:
  paths: [build/]
indexes:
  entry_point: _index.md
  index_types: config/index-types
  metadata_schema: specs/schemas/metadata.schema.yml
references: {}
```

The format `anagraphe:configuration@3` replaces `anagraphe:configuration@2`, whose section
`indexes` named a vocabulary under `vocabulary`. A configuration declaring the former format stops
the command, and the message names each change to write, as the section "Migrate from a vocabulary"
below lists them.

The metadata sources and the shared `exclude` apply to every section, and each section may
exclude further files under its own `exclude`, as the next sections state. The [reference specification](references.md) states
the keys of the section `references`, the [bindings guide](bindings.md) those of the section
`bindings`, and the [targets guide](targets.md) those of the sections `targets`, `records`,
`resolution` and `repository`. The rest of this page states the keys of the section
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
The built-in rules read the frontmatter of a Markdown note, and the top level of a YAML or JSON
document overridden by its block `metadata`, as `{yaml: [., metadata]}` and `{json: [., metadata]}`
write it. The source also marks the
**metadata region** of a file, where a pointer takes the conventions of the metadata. That region is
the block of a frontmatter, each YAML node at a declared path, or the whole of a JSON or TOML
document whose top level is declared.

The source also gives the **default identifier** of a record whose schema declares no
`x-identifier`: the key `id` at the first declared key path that holds it, as the
[targets guide](targets.md) states. A TOML document is a record of the check of the targets only
when its source is `toml`.

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
  git_ignored: true
```

| Key | Value | Default |
| --- | --- | --- |
| `paths` | patterns in the syntax of `.gitignore`, a later pattern prevailing over an earlier one | none |
| `where` | a list of metadata filters; a file is excluded when one filter selects it | none |
| `gitignore` | whether the patterns of the root `.gitignore` apply before the declared ones | `false` |
| `git_ignored` | whether every file ignored and not tracked by Git is excluded | `false` |

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

### Files that Git ignores

The key `git_ignored` excludes every file ignored and not tracked by Git. Git reads the rules of
every `.gitignore` and of `.git/info/exclude`. Anagraphe never passes the global excludes file of
the machine to Git, so two clones of one commit exclude the same files. The two keys on `.gitignore` differ in
two ways:

- `gitignore` reads the root `.gitignore` alone, and excludes a tracked file matched by its
  patterns;
- `git_ignored` asks Git, and Git never ignores a tracked file.

The key serves a working tree shared by several sessions. When a session holds an unfinished file,
it lists the file in `.git/info/exclude`. Git keeps that list in the clone and never commits it.
Listed there, the file stays out of the indexes, the record registry and every check, while links
to it still resolve. Git adds an ignored file only under `git add -f`. That refusal reminds the
session to complete the file first. Once Git tracks the file, the key stops excluding it, and its
checks resume without an edit of the configuration:

```sh
echo "notes/draft.md" >> .git/info/exclude   # excluded while unfinished
git add -f notes/draft.md                    # tracked, so checked again
```

No commit records a rule of `.git/info/exclude`, so such a rule could hide a file from every check
without notice. Therefore, each command reports every file or folder excluded by such a rule
alone, as a note of the kind `locally-excluded` under the section `exclusions`. A note gates no
commit:

```text
notes/draft.md:1: note: locally-excluded: a rule of .git/info/exclude leaves the file out of every check, until Git tracks it
```

A rule of a committed `.gitignore` raises no note, since its commit records it.

When the root lies in no Git work tree, a configuration declaring the key stops with a
configuration error.

## Required inputs

The section `indexes` declares the file name of an index under `entry_point`, such as `_index.md`,
and names one directory of index-type JSON Schemas under `index_types`. Both keys are required.
A schema declares an index type when two conditions hold: its filename ends in `.schema.yaml`,
and it holds the annotation `x-default-mode`. That annotation gives the default mode of the groups
of the type, `registry` or `sequence`. Any other value stops the command, and so does the retired
mode `construction`. The schemas must declare the type `module`. An index declaring no type takes
that type outside the locations that fix a type.

## Members of an index

An index lists the files of its folder whose type the section `indexes` admits under `members`, a
list of conditions on `paths`, `types`, `where` and `keys`; one holding condition suffices. The key
`keys` lists the keys that a member declares at its top level: the keys of its frontmatter, or of
the top-level mapping of its document. By default,
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
configuration of a tool, is kept out by an exclusion pattern, such as `environment.yml`, or by a
condition on its declared keys. The rule below lists a YAML file only when it declares the block
`metadata`, so a new configuration file stays out without an edit:

```yaml
indexes:
  members:
    - {types: [md]}
    - {types: [yml, yaml], keys: [metadata]}
```

## Generated areas and unlisted roles

The optional key `generated_areas` lists the top-level folders whose every index must hold the
region of its groups, so an index written by hand there is reported as `ungenerated-index`. The
optional key `unlisted_roles` lists the roles of the notes that an index reaches through its
control block alone, never through an entry, such as a work-state file:

```yaml
indexes:
  generated_areas: [docs, conferences]
  unlisted_roles: [worklog]
```

## Categorical values

A categorical key sorts the members of a group in the order of its declared values. The values of
a key are the enumeration of that key in the metadata schema that the optional key
`metadata_schema` names: a JSON Schema of the metadata of the files, written in YAML or JSON, and
relative to the root. The values of a key `K` are the `enum` of `properties.K`, or of
`properties.K.items` for a key holding a list, in their listed order:

```yaml
# specs/schemas/metadata.schema.yml
properties:
  kind:
    enum: [keynote, talk]
  outputs:
    type: array
    items: {enum: [claim, method, question]}
  bearing:
    $ref: 'definitions.schema.yml#/$defs/bearing'
```

The schema is read through `allOf`, `anyOf`, `oneOf` and `$ref`. A `$ref` by a path names a file
of the repository, relative to the file holding it. An absolute `$ref` resolves through the
`resources` of the schema registry of the records, under `targets.records.registry`, else
`bindings.records.registry`. A reference naming no readable node stops the command. The first
enumeration met in the order of the walk gives the values of a key, and a key without an
enumeration has no closed value set.

The check command reports a value outside this set in two cases. Either a filter or an `order`
names the value, or a member holds it under a categorical sort key of its group. The [index specification](index-specification.md) states how a group sorts by such a
key.

## Context relations

In an index, the key `context_relations` states the distinctions between two members, each as a
mapping `{source, relation, target, for}`. The admitted relations are the enumeration of the field
`relation` of its items in the metadata schema. Without that enumeration, every relation is
admitted:

```yaml
properties:
  context_relations:
    type: array
    items:
      properties:
        relation: {enum: [contrasts, visualizes]}
```

## Archived statuses

Only an archived note may declare `superseded_by`, the link to the note replacing it. The
statuses marking a note as archived are listed under the key `archived_statuses` of the section
`indexes`:

```yaml
indexes:
  archived_statuses: [archived]
```

A note declaring `superseded_by` must hold one of these statuses, as the [index
specification](index-specification.md) states. Without the key, the check command reports every
note declaring `superseded_by`. When the metadata schema enumerates the values of `status`, each
archived status must be one of them; otherwise the command stops.

## Migrate from a vocabulary

Until the format `anagraphe:configuration@3`, the section `indexes` named a vocabulary, a YAML
file or folder, under `vocabulary`. Each entry that Anagraphe read moves as follows:

| Entry of the vocabulary | Place in `anagraphe:configuration@3` |
| --- | --- |
| `schema.entry_point` | `indexes.entry_point` |
| `schema.generated_index_areas` | `indexes.generated_areas` |
| `key_values.K`, a list or a mapping of glosses | the `enum` of `properties.K`, or of `properties.K.items` for a list, in the metadata schema |
| `context_relations` | the `enum` of `properties.context_relations.items.properties.relation` |
| `archived_statuses` | `indexes.archived_statuses` |
| `roles.R.listed: false` | `R` listed under `indexes.unlisted_roles` |
| `schema.frames` | none: Hermeneia checks the form of a prose field |
| the rest of `roles` | none: Anagraphe no longer reads it |

The other entries of a vocabulary, such as the statuses, the tags or the key order, belong to the
tools of the repository that read them, and Anagraphe never read them.

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
