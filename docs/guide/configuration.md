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

The vocabulary declares the entry-point filename, roles, citation relations, ordering strategies,
and prose-field frames. Each schema whose filename ends in `.schema.yaml` may declare an index type.

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

## Task states and sequences

The optional task-state file maps repository task identifiers to completion booleans. This mapping
lets an entry report an unknown or already completed blocker without making Anagraphe own the task
syntax:

```yaml
task_states: build/task-states.yml
```

The optional sequence mapping declares the member order of folders whose order comes from an
external build system:

```yaml
sequences:
  manuscript/sections:
    - introduction.md
    - results.md
    - discussion.md
```

The Boolean setting `inspect_git` defaults to `true`. When enabled, an index absent from `HEAD` must
already contain a generated region.
