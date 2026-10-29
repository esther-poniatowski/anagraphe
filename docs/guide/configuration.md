# Configuration

The configuration file binds Anagraphe's generic renderer to one repository. Each declared path is
relative to the repository root selected by the root option. Absolute paths and paths that resolve
outside that root are invalid.

## Required inputs

The configuration below names one vocabulary file and one directory of index-type JSON Schemas:

```yaml
schema_version: 1
vocabulary: config/vocabulary.yml
index_types: config/index-types
```

The vocabulary declares the entry-point filename, the roles and the frames of the prose fields.
A schema declares an index type when two conditions hold: its filename ends in `.schema.yaml`,
and it holds the annotation `x-default-mode`. That annotation gives the default mode of the groups
of the type, `registry` or `sequence`. Any other value stops the command, and so does the retired
mode `construction`. The schemas must declare the type `module`. An index declaring no type takes
that type outside the locations that fix a type.

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

## Exclusions

Exclusions keep tool state, generated output, or repository-specific control files outside member
discovery:

```yaml
exclude:
  directories: [.git, build]
  files: [docs/private.md]
  basenames: [README.md]
```

Hidden paths are always excluded.

## Task states and build manifests

The optional task-state file maps repository task identifiers to completion booleans. This mapping
lets an entry report an unknown or already completed blocker without making Anagraphe own the task
syntax:

```yaml
task_states: build/task-states.yml
```

The optional sequence mapping declares the build manifest of each folder whose order comes from
an external build system. Each path is relative to its folder, and the [index
specification](index-specification.md) states how a sequence group follows the manifest:

```yaml
sequences:
  manuscript/sections:
    - introduction.md
    - results.md
    - discussion.md
```

The Boolean setting `inspect_git` defaults to `true`. When enabled, an index absent from `HEAD` must
already contain a generated region.

## Migration classes

A migration class lets a repository keep the retired key `cites` in some of its files until a
declared migration. Each instance inside the class is reported as a warning naming the migration
awaited, and each instance outside it remains a violation:

```yaml
migrations:
  - key: cites
    paths: ["models/*"]
    awaits: the conversion of the research notes into Gnomon records
```

Each pattern of `paths` follows the `fnmatch` syntax. In that syntax, the wildcard `*` also
matches the separator `/`.
