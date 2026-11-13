# Logical targets

A record of one tool often refers to a record held by another tool, or to a unit inside that
record, possibly in another repository. A contact profile names an audience, and a notation entry
denotes a quantity of a model. Such a reference is written as a **logical target**, which names the
record by its identifier rather than by its path, so that a move of the file leaves the target
valid. Anagraphe publishes the form of a target and checks the targets of a repository. The
[decision on logical targets](../adr/0006-logical-targets.md) records the reason for each choice,
and the [specification of the targets](../specification/logical-targets.md) fixes each reading for
the tools that read them.

## Write a target

A target is a mapping with at most three keys:

| Key | Content | Required |
| --- | --- | --- |
| `repository` | the identifier of a repository, declared by its `repository.yml` | no; an absent repository names the repository holding the citing file |
| `id` | the identifier of a record, unique within its repository | yes, unless the target names a repository |
| `unit` | the identifier of a unit inside the record | no; an absent unit names the whole record |

A YAML record and the frontmatter of a Markdown note write the same mapping. A target inside a list
takes the flow form on one line:

```yaml
# a record of the same repository
profile: {id: kriegeskorte_nikolaus}
# a unit of a record of another repository
source: {repository: mixture-input-encoding, id: ans.grokking.slow-structured-representation, unit: eta_rep}
# a repository, and thereby the project that it holds
project: {repository: mixture-input-encoding}
```

A target never holds a path, a URL, a title or an alias. Identifiers are compared case by case, so
`N` and `n` name two units.

## Declare the identifiers

A repository declares its identifier in `repository.yml` at its root:

```yaml
_schema: anagraphe:repository@1
repository:
  id: symmetry-lens-on-representations
  retired: []
```

The optional list `retired` holds the former identifiers of the repository, and a retired
identifier is never reused. Every root key other than `_schema` and `repository`, such as the
block `project` of the project specification, belongs to another contract. A manifest written in
the earlier form `schema_version: 1` is still read, and reported as `legacy-repository-manifest`
until it is converted.

A record declares its own identifier in the field that the schema of its contract names by
`x-identifier`, a dotted path of property names, at the root of the schema:

```yaml
x-identifier: identity.id
properties:
  identity:
    properties:
      id: {type: string}
```

A record whose schema declares no `x-identifier`, and a note without a schema, take the key `id`
of their metadata: the frontmatter of a note, or the block `metadata` of a YAML document.

## Declare the units

A unit is a place inside a record that a target can name:

- in a YAML record, an item of an array, whose definition carries `x-identifier` naming the field
  of the identifier of each item;
- in a Markdown note, a block anchor, named without its caret: `{id: mixture-input, unit:
  definition}` names the block `^definition` of the note declaring `id: mixture-input`.

A heading is not a unit. The units of one record share one namespace.

```yaml
properties:
  ideas:
    type: array
    items: {$ref: '#/$defs/idea'}
$defs:
  idea:
    x-identifier: id
    properties:
      id: {type: string}
```

## Declare a target field

A consumer schema references the definition `target` of the resource of Anagraphe by its absolute
URI, and lists under `x-target-contract` the contracts that the record of the target must follow:

```yaml
profile:
  $ref: 'https://github.com/esther-poniatowski/anagraphe/schemas/addressing.v1.schema.yml#/$defs/target'
  x-target-contract: ['geonexus:contact', 'homilia:contact']
  not: {required: [unit]}
```

An entry `namespace:name` admits every version of that contract, and an entry
`namespace:name@n` admits that version only. A field whose tool reads the fields of the target
record therefore pins the version. A field that admits a record of any contract, or a Markdown
note, omits `x-target-contract`. A field requires or forbids a unit, or a repository, by `required`
and `not` beside the `$ref`, which every validator of the consumer enforces.

The consumer also selects Anagraphe as a source of resources in its record of schema resources, so
that Kleisis materializes the resource. Anagraphe recognizes the definition by its URI, and does
not read the materialized copy.

## Check the targets

The section `targets` of `anagraphe.yml` enables the check. The section declares the schema registry
through which records reach the schemas of their contracts, as the section `bindings` does:

```yaml
targets:
  records:
    registry: specs/schema-registry.yml
```

| Key | Content | Default |
| --- | --- | --- |
| `records.registry` | the schema registry of Kleisis, relative to the root | no record reaches a schema: the check reads the default identifiers and the manifest only |
| `records.binding` | the key of a record naming its contract | `_schema` |
| `exclude` | files left out of the check, after the shared exclusions | none |

The command `anagraphe targets check`, and `anagraphe check` with every declared section, read every
Markdown note and every YAML or JSON document of the repository for its identifier. A file of a
nested repository, such as a submodule, belongs to that repository and is not read. The check then
reports the identifiers and the targets of the selected files:

| Kind | Level | Issue |
| --- | --- | --- |
| `invalid-target` | error | a target field holds a value that is not a mapping, holds another key, names neither a record nor a repository, holds a unit without a record, or holds a component outside its pattern |
| `invalid-identifier-declaration` | error | `x-identifier` is not a dotted path of property names, or names no property of its schema |
| `invalid-target-contract` | error | `x-target-contract` is not a non-empty list of contract identifiers |
| `missing-identifier` | error | a record of a contract whose schema declares `x-identifier` holds no value there |
| `invalid-identifier` | error | an identifier lies outside the pattern of a record identifier |
| `duplicate-identifier` | error | two records of the repository hold one identifier; reported at each record |
| `invalid-repository-manifest` | error | `repository.yml` violates `anagraphe:repository@1` |
| `legacy-repository-manifest` | warning | `repository.yml` writes `schema_version: 1` |
| `unknown-record` | error | no record of the repository holds the identifier of a target of the same repository |
| `unknown-unit` | error | the record of a target holds no unit of its identifier |
| `ambiguous-unit` | error | two units of the record of a target hold its identifier |
| `target-contract-mismatch` | error | the contract of the record of a target matches no entry of `x-target-contract` |
| `unbound-target` | error | the field declares `x-target-contract`, and the record of its target declares no contract |
| `unverified-target` | note | the target names another repository, whose records the check does not read |
| `unreadable-record` | error | the frontmatter or the document of a record cannot be parsed |
| `unresolved-schema-reference` | error | a `$ref` of a schema names no readable node of the repository |
| `unreadable-schema` | error | the schema of a contract of the registry cannot be read |

A target of the same repository is one without `repository`, or one whose repository equals the
identifier of the manifest at the root. A repository without a manifest therefore resolves only
its targets without `repository`. A target naming a duplicated identifier receives no finding of
its own, since `duplicate-identifier` reports its cause. A duplicated unit is reported only through
a target that names it.

Each finding names its file and the JSON Pointer of the target, of the identifier, or of the
declaring keyword of a schema, and the text report prints that pointer at the start of the detail.
A note does not change the exit status, and the gate that reads the findings log decides its
severity. When a record or a schema cannot be read, the findings log declares the run incomplete.

A domain tool may validate the same record against its schema, and report an invalid target as
well. Anagraphe still reports `invalid-target`, so that it stays usable without that tool, and a
gate running both tools removes one of the two findings through its suppressions.

## Read targets from a tool

A tool written in Python reads and compares targets through the package:

```python
from anagraphe.targets import Target, read_manifest

manifest = read_manifest(root).manifest
repository = manifest.id if manifest is not None else None
same = Target.parse(a).normalized(repository) == Target.parse(b).normalized(repository)
```

`Target.parse` raises `InvalidTarget`, whose `reason` names the first failed check, and
`admits(entries, contracts)` states whether a list `x-target-contract` admits a record.
