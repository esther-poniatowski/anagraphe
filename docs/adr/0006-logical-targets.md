# ADR 0006: Logical targets

**Status**: Accepted by the researcher on 2026-11-13, with the answers recorded under "Resolved
questions"; proposed on 2026-11-12. The record implements the logical target that the decision of
`geonexus` on [tool roles][tool-roles-references] assigns to Anagraphe, under rules 1 and 2 of its
section "References across fields", and the canonical target of the decision of `geonexus` on
[cross-repository record resolution][resolution-canonical].

---

## Problem Statement

A logical target is the address by which a record of one tool refers to a record held by another
tool, or to a unit inside that record, possibly in another repository. Four consumers wait on its
form.
Until Anagraphe publishes it, each of them writes a target as plain text, checked only as
non-empty, or as a relative link:

- Ekthesis, in its audience records and in the referenced ideas of its expositions;
- Onomasia, in the field `denotes` of a notation entry and in the document of denotes targets;
- Gnomon, whose records and units are the most frequent targets;
- Geonexus, whose contact profiles name audiences, and whose audiences name contacts.

The section "Migration of the consumers", under Implications, states each field, its current value
and its migration.

**Premises.** The following points are fixed by earlier decisions, and this record does not reopen
them:

- The pair `(repository, id)` names a record, an optional unit names a place inside it, and no
  target stores a path, a URL, a title or an alias ([canonical reference][resolution-canonical]).
  The decision on tool roles names the three keys `repository`, `id` and `unit`
  ([shared conventions][tool-roles-conventions]).
- The repository, the record and the project form three identifier namespaces. A project is
  identified by the identifier of its repository, as the amendment at the top of the
  [decision on cross-repository resolution][resolution] states. That amendment also replaces the
  fixed field `metadata.id` by a field declared by each schema, `metadata.id` being the default.
- A record of one field refers to a record of another field by a logical target, typed by the
  contract that the target must satisfy (`x-target-contract`), never by `$ref` into the schema of
  the other field (rule 1 of [references across fields][tool-roles-references]).
- The primitive types of addressing form one schema resource of Anagraphe with an absolute `$id`
  (rule 2 of the same section).
- A change that makes a valid record invalid, or changes the meaning of a field, takes a new
  version and a new identifier, and the old entry stays until every record has migrated
  ([versions][tool-roles-conventions]).
- The resolution context, the reference effects and the failure rules are those of the
  [decision on cross-repository resolution][resolution-context].

**Questions to be addressed**:

1. How is a target written in a YAML record and in a Markdown frontmatter, how is the repository
   omitted, and how is a unit written?
2. Which schema resource publishes the target, under which `$id` and which versioning, how does a
   consumer schema reference it, and how does `x-target-contract` type a target?
3. How does a record type declare the field holding its identifier, and the identifiers of its
   units, and how does a repository declare its own identifier?
4. Which findings does `anagraphe check` report on targets, and which of them does the first
   version deliver?
5. In which order do the consumers migrate, and which contract versions do they raise?
6. What does each task of the vault waiting on the form need from this record?

---

## Decision Drivers

- **One reading in two languages**: the Python and the TypeScript read sides read a target with
  no parser of their own beyond the YAML reader, and two targets naming one address compare equal.
- **Constraints by schema**: a field that requires or forbids a unit, or a repository, says so in
  standard JSON Schema, so that every validator of the consumer enforces it.
- **Repository boundary**: following [ADR 0001](0001-repository-boundary.md), Anagraphe names no
  field of a consumer. The owner of each schema declares its identifier field and its target
  fields.
- **Stability across moves**: a target survives the move of the file holding its record, so no
  move of [ADR 0003](0003-pointers-across-moves.md) edits a target.
- **No silent pass**: a target that a run cannot verify is reported as unverified, never counted
  as valid.

---

## Considered Options

**1. Written form of a target.** The decision on cross-repository resolution writes its example
target as a mapping, in YAML and in frontmatter alike ([canonical reference][resolution-canonical]).
The remaining choice is whether a compact string is admitted beside the mapping, or replaces it.

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| A compact string only, such as `repository:id#unit` | One short line per target | Each read side parses the string, and the pattern of the string restates the patterns of its three components. A field cannot require a unit by `required`. The interim values show the risk of the colon: `gnomon:concept.population-coding` names a tool where a repository belongs |
| Both forms, the mapping canonical | Short targets by hand, and a mapping for tools | One address takes two spellings. Onomasia matches `denotes` against its denotes targets by string equality, so each reader would normalize before comparing, in both languages |
| **The mapping `{repository, id, unit}` only** | One spelling, read by the YAML reader alone; each component typed by its own pattern; `required` and `not` constrain a field | Taken. A target in a list takes the flow form `{id: x, unit: y}` on one line |

**2. Omission of the repository.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| The repository always written | One spelling everywhere | A repository without a manifest, such as Geonexus today, cannot cite its own records; every target of a record repeats the repository holding it |
| The repository omitted when, and only when, the target lies in the same repository | One spelling per location | An explicit own repository then becomes a finding, although it names the same record without ambiguity |
| **The repository optional; an absent repository names the repository holding the citing file** | Short targets inside a repository, and no finding on an explicit own repository | Taken. Targets compare after normalization, which fills the repository |

**3. Form of a unit.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| A JSON Pointer into the record, such as `/ideas/3` | No declaration needed | A pointer addresses a value, and changes when a list is reordered, as the decision of Gnomon on [dotted identifiers][gnomon-dotted-constraints] states under its constraints |
| A heading or an anchor with its marker, such as `^claim` | The spelling of Obsidian | A heading is a title, which no target stores; the marker adds a second spelling of one name |
| **The identifier of a declared unit: the identifier of an item in a YAML record, the name of a block anchor in a Markdown record** | One flat namespace of units per record, as each record of Gnomon already keeps one flat table ([dotted identifiers][gnomon-dotted-file]) | Taken |

**4. Schema resource and typing.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| The version in the contract identifier only, with one `$id` for every version | One URI to cite | Rule 4 of [references across fields][tool-roles-references] identifies a base schema by its `$id`, so a breaking change requires a new `$id` |
| **The major version in the `$id`, such as `addressing.v1.schema.yml`** | A breaking change publishes a new file beside the old one | Taken |
| `x-target-contract` as one exact contract identifier, such as `geonexus:contact@16` | One value to match | Each new version of the target contract forces a new version of every citing contract. The contact contract also changes its namespace when it moves to Homilia |
| `x-target-contract` as the `$id` of a base schema that the target schema must compose | Structural typing | The check walks the composition of the target schema across sources, whereas rule 4 recognizes a record by its `_schema` or its `x-implements` |
| **`x-target-contract` as a list of contract identifiers, each with or without its version** | One citing contract admits several versions and namespaces of its target | Taken |

**5. Declaration of the identifiers.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| No default: a schema without `x-identifier` declares no record identifier | Every identifier field stated | A Markdown note has no schema, so no note could be a target. The amendment of the decision on cross-repository resolution fixes `metadata.id` as the default |
| **`x-identifier` at the root of a schema, by default the key `id` of the metadata source of the file** | One keyword, read as Ekphrasis reads it; the default matches the metadata sources of [ADR 0003](0003-pointers-across-moves.md) | Taken |
| A separate keyword for the identifier of a unit, such as `x-unit` | The role of each keyword visible by its name | Ekthesis already writes `x-identifier` on the definitions of its items, as its [argument record][ekthesis-field-roles] states, with the meaning required here |
| **`x-identifier` on a definition reached as the items of an array** | One keyword at both levels | Taken |
| The repository identifier in `anagraphe.yml` | One file of Anagraphe | The identity of a repository is not the configuration of a tool, and the decision on cross-repository resolution fixes `repository.yml` |
| **`repository.yml` at the root, named by `_schema: anagraphe:repository@1`** | The format named as every other contract is named, as `anagraphe.yml` already is | Taken. The current manifests write `schema_version: 1` |

**6. Targets that the first version cannot resolve.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| Skip a target into another repository without a finding | No noise before the registries exist | A consumer reads a clean run as a verified one |
| Resolve it in the working tree of a checked-out submodule | Most targets resolve at once | The decision on cross-repository resolution admits a working tree only for unverified navigation, never for a check ([resolution context][resolution-context]) |
| **Check its form, and report it as `unverified-target` at the level `note`** | Each unchecked target stays visible, and the gate decides its severity | Taken |

---

## Analysis of Options

### Summary: Comparison by Criteria

The written form is the choice on which every other choice rests, so its comparison is summarized
here. The other tables above state the determining reason of each option.

- **One reading in two languages**
  - **Compact string**: LOW (a parser and its conformance cases in each language)
  - **Both forms**: LOW (a parser and a normalization in each language)
  - **Mapping only**: HIGH (the YAML reader alone)
- **Constraints by schema**
  - **Compact string**: LOW (a pattern per field that requires a unit)
  - **Both forms**: MEDIUM (`oneOf` over the two forms)
  - **Mapping only**: HIGH (`required`, `not`)
- **Brevity for the author**
  - **Compact string**: HIGH (one token)
  - **Both forms**: HIGH
  - **Mapping only**: MEDIUM (a flow mapping on one line)

The compact string would win if a target had to stand where only a scalar fits, such as a key of a
mapping or the target of a Markdown link. No consumer field in scope requires either, and a
Markdown body names its targets through citation keys, under the
[canonical reference][resolution-canonical].

---

## Conclusions

### Decision

**Chosen option**: The mapping `{repository, id, unit}`, published in the schema resource
`addressing.v1` of Anagraphe, typed by a list of contract identifiers, and checked by
`anagraphe check` within one repository.

**Justification**: The mapping gives one spelling of each address that both read sides read without
a parser, and it lets each consumer constrain its targets in standard JSON Schema. Every other
choice follows from that form: the unit is a key, the omission of the repository is the absence of
a key, and the typing sits on the field beside the `$ref`.

#### Written form

A target is a mapping with three keys and no other:

| Key | Required | Content | Pattern |
| --- | --- | --- | --- |
| `repository` | no | the identifier of a repository, declared by its `repository.yml` | `^[a-z0-9]+(-[a-z0-9]+)*$` |
| `id` | yes, unless the target names a repository | the identifier of a record, unique within its repository | `^[a-z0-9]+([._-][a-z0-9]+)*$` |
| `unit` | no | the identifier of a unit declared inside the record | `^[A-Za-z0-9][A-Za-z0-9_-]*$` |

On 2026-11-12, the patterns admitted the 60 identifiers of the contacts and audiences of Geonexus,
such as `andre_jean-baptiste` and `computational-modelers`, and every block anchor of the Markdown
files tracked by the vault. The patterns also admit the forms that Gnomon states: dotted record ids, such
as `quest.grokking.explain-delay` ([dotted identifiers][gnomon-dotted]), and symbols holding
capitals, such as `L_train` and `m_N` ([symbols and expressions][gnomon-symbols]).
A unit holds no dot, so the dotted reference of Gnomon splits into a record and a unit. Identifiers
compare case by case, since Gnomon distinguishes `N` from `n`.

A YAML record and a Markdown frontmatter write the same mapping:

```yaml
# a unit of a record of another repository
source: {repository: mixture-input-encoding, id: ans.grokking.slow-structured-representation, unit: eta_rep}
# a record of the same repository
profile: {id: kriegeskorte_nikolaus}
```

```yaml
---
id: mixture-input
cites:
  - relation: cites-as-evidence
    target: {repository: geonexus, id: smith2024}
---
```

A target with `repository` and without `id`, such as `{repository: mixture-input-encoding}`, names
the repository itself, and thereby the project that the repository holds; it holds no `unit`.
A target without `repository` names a record of the repository holding the citing file. That
repository is the one whose root contains the file; a nested repository, such as a submodule, is a
repository of its own. The read side normalizes a target by filling its repository, and two targets
are equal when their normalized mappings are equal. A document generated by a tool, such as a
document of denotes targets, writes the repository of every target, so its meaning does not depend
on the repository that reads it.

In a YAML record, a `unit` names the identifier of an item whose definition carries
`x-identifier`. In a Markdown record, a `unit` names a block anchor, written without its caret. For
example, `{id: mixture-input, unit: definition}` names the block `^definition` of the note whose
frontmatter declares `id: mixture-input`. A heading is not a unit. The units of one record share one namespace.

#### Schema resource

Anagraphe publishes the resource
`https://github.com/esther-poniatowski/anagraphe/schemas/addressing.v1.schema.yml` as package
data, with the `$defs` `repository-id`, `record-id`, `unit-id` and `target`. The registry of
Anagraphe, in the format `kleisis:schema-registry@2`, maps that `$id` to its file under
`resources`. A consumer therefore selects Anagraphe as a source that supplies resources only, as
rule 3 of [references across fields][tool-roles-references] admits, and Kleisis materializes the
resource with its closure. The conformance cases `specs/conformance/targets.yml` fix each reading,
as `specs/conformance/bindings.yml` does for the bindings.

Adding a definition to the resource keeps its `$id`; the definition of a `cites` entry, or the
field-path syntax, may arrive that way. A change that makes a valid target invalid, or changes the
meaning of a key, publishes `addressing.v2.schema.yml`, and the file `v1` stays until no consumer
references it.

A consumer field references the definition by its absolute URI, and types it beside the `$ref`:

```yaml
profile:
  $ref: 'https://github.com/esther-poniatowski/anagraphe/schemas/addressing.v1.schema.yml#/$defs/target'
  x-target-contract: ['geonexus:contact', 'homilia:contact']
  not: {required: [unit]}
```

A target field is a value validated by that definition. Anagraphe finds it by reading the schema
of the citing record through `properties`, `items`, `additionalProperties`, the subschemas of
`allOf`, `anyOf` and `oneOf`, and every `$ref`. Anagraphe recognizes its own definition by its URI,
without loading the materialized file.

The keyword `x-target-contract` holds a non-empty list of contract identifiers. An entry
`namespace:name` admits every version of that contract, and an entry `namespace:name@n` admits that
version only. A target relies on the identity of its record, not on its fields, so an unversioned
entry admits a new major version of the contract without review; a field whose tool reads fields of
the target record pins the version. A target satisfies the list when the `_schema` of its record matches an entry, or
when the root schema of that `_schema` declares an `x-implements` that matches one, as rule 4
recognizes a record. A field that admits a record of any contract, or a Markdown note, omits the
keyword; the first entry of "Contradictions between sources" states why rule 1 allows this.
A field requires or forbids a unit, or a repository, by `required` and `not` beside the `$ref`.

#### Identifier declarations

`x-identifier` is a keyword of the addressing specification, as the inventory of
[tool roles][tool-roles-references] assigns it. Its value is a path of property names joined by dots,
such as `identity.id`. The wildcards and the conversion to a JSON Pointer belong to the field-path
syntax, which this record leaves to its own decision.

- At the root of the schema of a contract, read through `allOf` and `$ref`, `x-identifier` names
  the field holding the identifier of the record.
- Without it, the identifier of a record is the key `id` of its metadata source: the frontmatter of
  a Markdown note, or the block `metadata` of a YAML document. This default is the `metadata.id` of
  the decision on cross-repository resolution.
- On a definition reached as the items of an array, `x-identifier` names the field holding the
  identifier of each item, and makes each item a unit of the record. The items of a mapping keyed
  by identifier, such as the entries of an Onomasia notation, are not units in this version, since
  no consumer in scope targets them.

A repository declares its identifier in `repository.yml` at its root:

```yaml
_schema: anagraphe:repository@1
repository:
  id: symmetry-lens-on-representations
  retired: []
```

The schema of `anagraphe:repository@1` fixes the block `repository`: its `id`, and the optional list
`retired` of the former identifiers of the repository. A retired identifier is never reused, and
the resolver follows it to the current identifier with a warning. The identity of a project that the
[project specification][tool-roles-project] moves into the manifest (its short name, label, kind and
gloss) sits in a block `project` beside `repository`. That block belongs to the contract of the
project specification, not to Anagraphe, so `anagraphe:repository@1` leaves every root key other
than `_schema` and `repository` open. The repository of the vault is identified as `geonexus`. During the migration,
Anagraphe also reads the current form `schema_version: 1`, and reports it as
`legacy-repository-manifest`.

#### Checks

The section `targets` of `anagraphe.yml` enables the check. The check reads the schema registry through
which records reach their schemas, as the section `bindings` already does, so the configuration
keeps `anagraphe:configuration@2`. Each finding names the citing file as its resource, and the JSON
Pointer of the target, or of the declaring field, as its locus, under
[ADR 0004](0004-findings-output.md).

| Finding | Level | Condition | First version |
| --- | --- | --- | --- |
| `invalid-target` | error | a target field holds a value that is not a mapping, holds another key, lacks both `id` and `repository`, holds a `unit` without `id`, or holds a component outside its pattern | yes |
| `invalid-identifier-declaration` | error | `x-identifier` is not a dotted path of property names, or names no property of its schema | yes |
| `invalid-target-contract` | error | `x-target-contract` is not a non-empty list of contract identifiers | yes |
| `missing-identifier` | error | a record of a contract whose schema declares `x-identifier` holds no value there | yes |
| `invalid-identifier` | error | an identifier lies outside the pattern of `record-id` | yes |
| `duplicate-identifier` | error | two records of the repository hold one identifier; reported at each record | yes |
| `invalid-repository-manifest` | error | `repository.yml` violates `anagraphe:repository@1` | yes |
| `legacy-repository-manifest` | warning | `repository.yml` writes `schema_version: 1` | yes |
| `unknown-record` | error | no record of the repository holds the identifier of a target of the same repository | yes |
| `unknown-unit` | error | the record holds no unit of the identifier | yes |
| `ambiguous-unit` | error | two units of the record hold the identifier | yes |
| `target-contract-mismatch` | error | the contract of the record matches no entry of `x-target-contract` | yes |
| `unbound-target` | error | the field declares `x-target-contract`, and the record declares no `_schema` | yes |
| `unverified-target` | note | the target names another repository, whose form alone is checked | yes, until the resolver exists |
| the failures of the [decision on cross-repository resolution][resolution-failures] | error | an unknown repository, an unavailable or denied state, a stale registry, an escaping path, a digest mismatch, an unverified bundle | no: the task `record-resolver` names them |
| a renamed record | warning | the target names an identifier retired by a declared rename, and the resolver follows the rename | no: the record registry holds the renames |

A target of the same repository is one without `repository`, or one whose repository equals the
identifier of the manifest at the checked root. A repository without a manifest resolves only its
targets without `repository`. A target naming a duplicated identifier receives no finding of its
own, since `duplicate-identifier` reports its cause. A duplicated unit is reported only through a
target that names it, because Ekthesis lets an idea and a part share an identifier in one record.
Anagraphe reports `invalid-target` even when the domain tool of the citing record validates the
same record against its schema, so that Anagraphe stays usable without that tool. A gate that runs
both tools removes one of the two findings through its suppressions.
The first version builds the identifiers of the repository in memory from the walk of the check;
the generated record registry replaces that walk under the task `record-registry`.

### Final Answers

1. A target is the mapping `{repository, id, unit}`, in a YAML record and in a frontmatter alike.
   An absent `repository` names the repository holding the citing file, and an absent `unit` names
   the whole record. A unit is the identifier of a declared item, or the name of a block anchor
   without its caret.
2. The resource `addressing.v1.schema.yml`, with an absolute `$id` that carries its major version,
   publishes the target and its three identifier types. A consumer references
   `#/$defs/target` by that URI, and types the field by a list of contract identifiers under
   `x-target-contract`.
3. `x-identifier` names the identifier field at the root of a schema, by default the key `id` of the
   metadata source, and the identifier of each unit on the definition of an item. A repository
   declares its identifier under `repository.id` of its `repository.yml`, in the contract
   `anagraphe:repository@1`, with its former identifiers under `repository.retired`; the identity
   of a project sits in a block `project` of the same file, outside the contract of Anagraphe.
4. The first version checks the form, the declarations, the resolution within one repository and
   the contract, and reports every target into another repository as `unverified-target`. The
   failures of cross-repository resolution and the renames wait on the registries and the resolver.
5. The order and the versions are stated under "Migration of the consumers", in the Implications.
6. The needs of each task are stated under "Tasks of the vault", in the Implications.

---

## Implications

### Migration of the consumers

Each consumer field below writes its target as text, or as a link, until it migrates in the order stated below.

| Consumer and field | Names | Written today | Migration |
| --- | --- | --- | --- |
| Ekthesis, audience, `knowledge[*].concept` ([knowledge][ekthesis-knowledge]) | a record, or a unit inside it: a concept record of Gnomon, a definition in a course, a page of documentation ([concept reference][ekthesis-glossaries]) | text checked as non-empty, by the definition `logical-target`; the example of the [schema][ekthesis-audience-example] is `gnomon:concept.population-coding` | a target without `x-target-contract`, since the sources of a concept belong to several fields |
| Ekthesis, audience, `identity.representatives[*].profile` ([names of an audience][ekthesis-audience-names]) | a record: the contact profile of a researcher | the contact id, such as `kriegeskorte_nikolaus` in [computational-modelers.yml][geonexus-audience-record] | `{id: kriegeskorte_nikolaus}`, typed `['geonexus:contact', 'homilia:contact']`, with the unit forbidden |
| Ekthesis, exposition, `ideas[*].source` ([referenced idea][ekthesis-referenced-idea]) | a unit, or a record when a whole note states the idea | a relative Markdown link with an optional block anchor, marked `x-resolves: file` in the [schema][ekthesis-exposition-schema] | a target without `x-target-contract`; the anchor becomes the unit, and each cited note declares `id` in its frontmatter |
| Onomasia, notation, `entries.*.denotes` ([meaning][onomasia-meaning]) | a unit: a quantity, or the block anchor of a note | text, in the [notation schema][onomasia-notation-schema]; the tests write `mixture:weights` ([test_typography.py][onomasia-tests]) | a target, with the unit required |
| Onomasia, denotes targets, `targets[*].target` ([schema][onomasia-denotes-schema]) | a unit | text written by Gnomon, and matched to `denotes` by string equality in [contracts.py][onomasia-signatures] | a target written with its repository; Onomasia matches normalized targets |
| Gnomon, every record ([dotted identifiers][gnomon-dotted]) | records by their dotted `id`, units by one further segment | `x-identifier: id` at the root of each base schema, such as [concept.base.schema.yml][gnomon-concept-schema]; no unit declared in a schema | `x-identifier` on the definitions of declared elements (`symbol`) and of steps (`id`); a target into Gnomon writes the record segments under `id` and the last segment under `unit` |
| Geonexus, contact, `identity.communities[*]` ([contact schema][geonexus-contact-schema]) | a record: an audience | a Markdown link to the audience file, read by `x-checks` with `extract: link-id` | `{id: computational-modelers}`, typed `['ekthesis:audience']` |
| Repository manifests | a repository | `schema_version: 1` and `repository.id` in each project, such as [symmetry][symmetry-manifest]; no manifest at the root of Geonexus, nor in Mixture | `_schema: anagraphe:repository@1`; a manifest added where none exists |

The identifier fields are declared today as follows. The contact schema of Geonexus declares
`x-identifier: identity.id`, and repeats the field under `x-checks.id_key`
([contact schema][geonexus-contact-schema]); the decision on tool roles replaces `id_key` by
`x-identifier`. The audience schema of Ekthesis declares `x-identifier: identity.id`
([schema][ekthesis-audience-schema]). Both records also hold a block `metadata` without `id`, so the
default would not apply to them. Onomasia declares its identifier at the root key `id` without
`x-identifier` ([notation schema][onomasia-notation-schema]), so the default `metadata.id` would
miss it.

The migration follows this order:

1. **Anagraphe** releases the resource `addressing.v1`, the contract `anagraphe:repository@1`, the
   conformance cases, the Python read side and the first check.
2. **Repository manifests**: Geonexus and Mixture add their `repository.yml`, and each project
   converts its manifest to `_schema`. A target can name another repository only once that
   repository declares its identifier.
3. **Declarations without a new version**: Onomasia adds `x-identifier: id` to `onomasia:glossary@1`
   and `onomasia:notation@1`, and Gnomon declares its units. An annotation invalidates no record and
   changes no field, so each lands as a coordinated update under the same identifier.
4. **Onomasia** publishes `onomasia:notation@2` and `onomasia:denotes-targets@2`, and reads both
   versions of the denotes targets. **Gnomon** then generates `onomasia:denotes-targets@2`.
5. **Ekthesis** publishes `ekthesis:audience@2` for `concept` and `profile`, and
   `ekthesis:exposition@3` for `source`, under its task `logical-target-references`.
6. **Geonexus** publishes `geonexus:contact@17` for `identity.communities[*]`. Homilia starts from the
   target form when it takes the contact contract.
7. **Records** migrate in one coordinated update per repository: the audiences and contacts of
   Geonexus, the notations and expositions of each project, and the frontmatter `id` of each note
   cited as a source.
8. Each superseded contract leaves its registry once no record uses it.

Each consumer schema that references the resource also selects Anagraphe as a source of resources
in its `specs/schema-resources.yml`. The current schemas of Ekthesis, Onomasia and Geonexus carry a
relative `$id`, such as `$id: audience.schema.yaml`; their move to base schemas under rule 4 is
independent of this record.

### Tasks of the vault

The tasks below are those of the [task list of Geonexus][geonexus-todo].

| Task | Needs from this record | Left open after it |
| --- | --- | --- |
| `record-reference-schema` | the definition `target` and its `$id`; the rule of `x-identifier` and its default; the contract `anagraphe:repository@1` | the definition of a `cites` entry with its citation key, to be added to the same resource without a new `$id`; the division of the metadata schema |
| `record-registry` | the field holding each identifier, the pattern of `record-id`, and the findings `missing-identifier`, `duplicate-identifier` and `invalid-identifier`, which the registry reports in the same terms | the format of the registry and of the declared renames |
| `record-resolver` | the normalization of a target, the manifest that names a repository, and the matching of `x-target-contract` | the findings of cross-repository failures, which replace `unverified-target` |
| `record-state-provider` | the pattern of `repository-id` only | nothing further from this record |
| `glossary-import-closure` | the target as the form of `imports[*].from`, whose compositional effect the glossary schema declares, under a new version of the Onomasia glossary | the traversal, owned by Onomasia and Ekthesis |
| `record-reader-views` | the omission rule, and the mapping from a unit to the fragment `#^unit` of a Markdown record | the output profiles |
| `record-reference-migration-dispatch` and its successors | the migration order above | the tasks of each repository |

### Package and contracts

- **Schema traversal**: the reading of marks through `allOf`, `anyOf`, `oneOf` and `$ref`, now in
  `anagraphe.bindings.schemas`, moves to the core, and gains `items` and `additionalProperties`. The
  capability `anagraphe.targets` and the bindings then share it without importing each other, as
  [ADR 0003](0003-pointers-across-moves.md) requires of the capabilities.
- **Registry reading**: Anagraphe resolves an absolute `$ref` through the `resources` map of a
  registry of format 2, which the bindings do not yet read.
- **TypeScript**: the TypeScript read side implements the same conformance cases when it moves out
  of Ekphrasis, under step 2 of the [order of extraction][tool-roles-order].
- **Moves**: a move rewrites no target, since a target holds no path. A rename of a record
  identifier is a later command, once the record registry holds the declared renames.

### Contradictions between sources

1. **Typing of every target.** Rule 1 of [references across fields][tool-roles-references] types
   each target by the contract of its record. Three consumers admit sources without a contract:
   - a knowledge item cites "a definition in a course, or a page of documentation"
     ([concept reference][ekthesis-glossaries]);
   - a referenced idea cites "the file that states it" ([referenced idea][ekthesis-referenced-idea]);
   - a notation entry denotes "the block anchor of a note" ([meaning][onomasia-meaning]).

   *Resolution*: `x-target-contract` is optional, and a field
   admitting any source omits it. Rule 1 of the decision on tool roles states this exception since
   2026-11-13.
2. **Renames of a repository.** The decision on cross-repository resolution states that a repository
   identifier is never reused and stays stable ([canonical reference][resolution-canonical]),
   whereas the project specification moves "its retired names" into `repository.yml`
   ([project specification][tool-roles-project]). *Resolution*: a manifest may list its
   former identifiers under `repository.retired`; a retired identifier is never reused, and the
   resolver follows it with a warning. Accepted on 2026-11-13.
3. **Dotted references of Gnomon.** Gnomon states that "every reference to a record, or to a unit of
   a record, is a uniform sequence of dots", and that its consumers cite steps from other
   repositories in that form ([dotted identifiers][gnomon-dotted]). A dotted string names no
   repository, and rule 1 requires a logical target between fields. *Resolution*: the
   dotted form stays the syntax of references inside Gnomon within one repository; a target from
   another field, or into another repository, splits it into `id` and `unit` by the prefix rule of
   Gnomon. Accepted on 2026-11-13.
4. **Interim form of a referenced idea.** The decision on [independent research and
   exposition][independent-decision] states that a citation is checked "only that it is non-empty
   text". The [referenced idea][ekthesis-referenced-idea] of Ekthesis is a relative link resolved
   from the directory of the record. *Resolution*: the record of Ekthesis states its
   interim form; the migration replaces the link in either reading.
5. **Interim values in the place of a repository.** The audience schema gives the example
   `gnomon:concept.population-coding` ([schema][ekthesis-audience-example]), which names a tool, and
   the tests of Onomasia write `mixture:weights` ([test_typography.py][onomasia-tests]), which names
   no declared repository. A target names a repository by the identifier of its manifest, such as
   `symmetry-lens-on-representations`. *Resolution*: the migration writes the identifier of
   each manifest; no alias of a repository is admitted.
6. **Reference to an export.** The decision of Ekthesis on glossaries still names a unit "by a
   relative link until the source publishes an export" ([concept reference][ekthesis-glossaries]),
   whereas the export is retired ([decision][independent-decision]). *Resolution*: the
   wording belongs to Ekthesis, and its migration to targets removes it.

### Resolved questions

The researcher answered the open questions of the proposal on 2026-11-13:

1. `x-target-contract` is optional: a field that admits sources of any field omits it, and rule 1
   of the decision on tool roles names that exception.
2. A repository may change its identifier: `repository.retired` lists its former identifiers, as
   the decision on tool roles moves the retired names of a project into `repository.yml`, and a
   retired identifier is never reused.
3. A record of Gnomon cites a record of Gnomon in another repository by a logical target; the dotted
   form stays the syntax of references within one repository.
4. A record names a project by a target `{repository: R}` without `id`, since a project is
   identified by its repository.
5. Anagraphe reports `invalid-target` even when the domain tool validates the record; the gate of a
   consumer that runs both removes one finding through its suppressions.
6. An unversioned entry of `x-target-contract` admits a new major version without review, since a
   target relies on the identity of its record; a field that reads the fields of the target pins
   the version.
7. The contract `anagraphe:repository@1` owns `repository.id` and `repository.retired`; the
   identity of a project sits in a block `project`, owned by the contract of the project
   specification.
8. The repository of the vault is identified as `geonexus`.

---

## See Also

### Related Decisions

- [ADR 0001](0001-repository-boundary.md): Relates to. Anagraphe names no field of a consumer.
- [ADR 0003](0003-pointers-across-moves.md): Extends. A target is a pointer by identity, which
  moves preserve without a rewrite; the metadata sources fix the default identifier.
- [ADR 0004](0004-findings-output.md): Relates to. The findings of targets follow its loci.
- [ADR 0005](0005-text-bindings.md): Relates to. The targets read the schema registry and the marks
  of schemas as the bindings do.

### References and Resources

- [JSON Schema 2020-12, Core: `$ref` with sibling keywords](https://json-schema.org/draft/2020-12/json-schema-core#section-8.2.3.1)

[tool-roles-references]: https://github.com/esther-poniatowski/geonexus/blob/c9616185754637dd1254c3454502e9b5604d8750/docs/_decisions/tool-roles.md#references-across-fields
[tool-roles-conventions]: https://github.com/esther-poniatowski/geonexus/blob/c9616185754637dd1254c3454502e9b5604d8750/docs/_decisions/tool-roles.md#shared-conventions
[tool-roles-project]: https://github.com/esther-poniatowski/geonexus/blob/c9616185754637dd1254c3454502e9b5604d8750/docs/_decisions/tool-roles.md#project-specification
[tool-roles-order]: https://github.com/esther-poniatowski/geonexus/blob/c9616185754637dd1254c3454502e9b5604d8750/docs/_decisions/tool-roles.md#order-of-extraction
[resolution]: https://github.com/esther-poniatowski/geonexus/blob/c9616185754637dd1254c3454502e9b5604d8750/docs/_decisions/cross-repository-record-resolution.md
[resolution-canonical]: https://github.com/esther-poniatowski/geonexus/blob/c9616185754637dd1254c3454502e9b5604d8750/docs/_decisions/cross-repository-record-resolution.md#canonical-reference
[resolution-context]: https://github.com/esther-poniatowski/geonexus/blob/c9616185754637dd1254c3454502e9b5604d8750/docs/_decisions/cross-repository-record-resolution.md#resolution-context
[resolution-failures]: https://github.com/esther-poniatowski/geonexus/blob/c9616185754637dd1254c3454502e9b5604d8750/docs/_decisions/cross-repository-record-resolution.md#failure-and-access-rules
[independent-decision]: https://github.com/esther-poniatowski/geonexus/blob/c9616185754637dd1254c3454502e9b5604d8750/docs/_decisions/independent-research-and-exposition.md#decision
[geonexus-todo]: https://github.com/esther-poniatowski/geonexus/blob/c9616185754637dd1254c3454502e9b5604d8750/TODO.md
[geonexus-contact-schema]: https://github.com/esther-poniatowski/geonexus/blob/c9616185754637dd1254c3454502e9b5604d8750/specs/schemas/contact.schema.yaml#L11
[geonexus-audience-record]: https://github.com/esther-poniatowski/geonexus/blob/c9616185754637dd1254c3454502e9b5604d8750/audiences/computational-modelers.yml#L15
[symmetry-manifest]: https://github.com/esther-poniatowski/symmetry-lens-on-representations/blob/f07796d366366d97f79a468953441fb1837e5e33/repository.yml
[ekthesis-audience-names]: https://github.com/esther-poniatowski/ekthesis/blob/67d29547d6200cdd92d162d189935c3709dc4e6c/docs/adr/audiences.md#^audience-names
[ekthesis-knowledge]: https://github.com/esther-poniatowski/ekthesis/blob/67d29547d6200cdd92d162d189935c3709dc4e6c/docs/adr/audiences.md#^knowledge
[ekthesis-referenced-idea]: https://github.com/esther-poniatowski/ekthesis/blob/67d29547d6200cdd92d162d189935c3709dc4e6c/docs/adr/argument-record.md#^referenced-idea
[ekthesis-field-roles]: https://github.com/esther-poniatowski/ekthesis/blob/67d29547d6200cdd92d162d189935c3709dc4e6c/docs/adr/argument-record.md#^field-roles
[ekthesis-glossaries]: https://github.com/esther-poniatowski/ekthesis/blob/67d29547d6200cdd92d162d189935c3709dc4e6c/docs/adr/glossaries.md#^concept-reference
[ekthesis-audience-schema]: https://github.com/esther-poniatowski/ekthesis/blob/67d29547d6200cdd92d162d189935c3709dc4e6c/src/ekthesis/data/schemas/audience.schema.yaml#L13
[ekthesis-exposition-schema]: https://github.com/esther-poniatowski/ekthesis/blob/67d29547d6200cdd92d162d189935c3709dc4e6c/src/ekthesis/data/schemas/exposition.schema.yaml#L106-L140
[onomasia-meaning]: https://github.com/esther-poniatowski/onomasia/blob/f02aa0623073f65a1745bed2b3bb5083cf31c047/docs/formats.md#^meaning
[onomasia-notation-schema]: https://github.com/esther-poniatowski/onomasia/blob/f02aa0623073f65a1745bed2b3bb5083cf31c047/src/onomasia/data/schemas/notation.schema.yml#L7-L30
[onomasia-denotes-schema]: https://github.com/esther-poniatowski/onomasia/blob/f02aa0623073f65a1745bed2b3bb5083cf31c047/src/onomasia/data/schemas/denotes-targets.schema.yml#L19
[onomasia-signatures]: https://github.com/esther-poniatowski/onomasia/blob/f02aa0623073f65a1745bed2b3bb5083cf31c047/src/onomasia/contracts.py#L107-L122
[onomasia-tests]: https://github.com/esther-poniatowski/onomasia/blob/f02aa0623073f65a1745bed2b3bb5083cf31c047/tests/test_typography.py#L40-L43
[ekthesis-audience-example]: https://github.com/esther-poniatowski/ekthesis/blob/67d29547d6200cdd92d162d189935c3709dc4e6c/src/ekthesis/data/schemas/audience.schema.yaml#L185
[gnomon-dotted]: https://github.com/esther-poniatowski/gnomon/blob/b39311496cd6229935f288235a497414a93c9996/docs/adr/dotted-identifiers.md#^identifier-form
[gnomon-dotted-file]: https://github.com/esther-poniatowski/gnomon/blob/b39311496cd6229935f288235a497414a93c9996/docs/adr/dotted-identifiers.md
[gnomon-dotted-constraints]: https://github.com/esther-poniatowski/gnomon/blob/b39311496cd6229935f288235a497414a93c9996/docs/adr/dotted-identifiers.md#constraints-that-decide-the-form
[gnomon-symbols]: https://github.com/esther-poniatowski/gnomon/blob/b39311496cd6229935f288235a497414a93c9996/docs/specification/expressions.md
[gnomon-concept-schema]: https://github.com/esther-poniatowski/gnomon/blob/b39311496cd6229935f288235a497414a93c9996/src/gnomon/data/schemas/concept.base.schema.yml#L2-L6
