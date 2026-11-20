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
| `repository` | the identifier of a repository, derived from its remote or its folder, or declared in its `anagraphe.yml` | no; an absent repository names the repository holding the citing file |
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

The identifier of a repository is derived, so most repositories declare none. The derivation takes
the first of these names:

1. the override `repository.id` of `anagraphe.yml`, when the configuration declares it;
2. the name of the remote `origin`, without `.git`: `git@github.com:lab/geonexus.git` names
   `geonexus`;
3. the name of the folder of the root.

A name is kept only when it is a repository identifier: lowercase letters and digits, in groups
joined by single hyphens. Without such a name, the repository has no identity. The section
`repository` of `anagraphe.yml` overrides the identifier, and lists the former identifiers of the
repository:

```yaml
repository:
  id: symmetry-lens-on-representations   # optional; a fork declares the identifier it continues
  retired: [symmetry-lens]               # former identifiers, never reused
```

A section holding another key, an identifier outside the pattern, or a list `retired` holding the
override stops every command with a configuration error. A list `retired` holding the derived
identifier stops every command that derives the identity. Without an override, a remote and a folder
naming two different identifiers raise the warning `identity-disagreement`; the remote wins until
the section declares the identifier. The manifest `repository.yml`, which declared the identifier
before, is retired. A `repository.yml` left at the root is reported as
`retired-repository-manifest`; when it declares another identifier or other former identifiers than
the configuration, the finding names the section to write before the file is deleted.

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
of the metadata source that the section `metadata` of `anagraphe.yml` declares for the file, as
the [configuration guide](configuration.md) states. The built-in sources read the frontmatter of a
note, and the top level of a YAML or JSON document, then its block `metadata`. A TOML document is a record when a rule
declares a `toml` source for it.

When several key paths of the source hold `id`, the first path in the declared order gives the
identifier. A later path holding another value is reported as `invalid-identifier` at that path,
and the record keeps the identifier of the first path:

```yaml
# a YAML record under the built-in source: its identifier is first, and /metadata/id is reported
id: first
metadata: {id: second}
```

## Declare the units

A unit is a place inside a record that a target can name:

- in a YAML record, an item of an array, whose definition carries `x-identifier` naming the field
  of the identifier of each item;
- in a Markdown note, a block anchor, named without its caret: `{id: mixture-input, unit:
  definition}` names the block `^definition` of the note declaring `id: mixture-input`.

A heading is not a unit. The units of one record share one namespace. An item identifier outside
the pattern of a unit identifier, such as `eta.rep`, is no unit, and the check reports it as
`invalid-identifier` at the field of the item.

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
| `records.registry` | the schema registry of Kleisis, relative to the root | no record reaches a schema: the check reads the default identifiers and the identity only |
| `records.binding` | the key of a record naming its contract | `_schema` |
| `exclude` | files left out of the check, after the shared exclusions | none |
| `read_sides` | the places where other read sides declare their implemented versions, each `{path, pointer}`, as the section "Compare the read sides" below states | none |

The command `anagraphe targets check`, and `anagraphe check` with every declared section, read every
Markdown note, every YAML or JSON document, and every TOML document with a `toml` source of the
repository for its identifier. A file of a
nested repository, such as a submodule, belongs to that repository and is not read. The check then
reports the identifiers and the targets of the selected files:

| Kind | Level | Issue |
| --- | --- | --- |
| `invalid-target` | error | a target field holds a value that is not a mapping, holds another key, names neither a record nor a repository, holds a unit without a record, or holds a component outside its pattern |
| `invalid-identifier-declaration` | error | `x-identifier` is not a dotted path of property names, or names no property of its schema |
| `invalid-target-contract` | error | `x-target-contract` is not a non-empty list of contract identifiers |
| `missing-identifier` | error | a record of a contract whose schema declares `x-identifier` holds no value there |
| `invalid-identifier` | error | an identifier lies outside the pattern of a record identifier, an item identifier lies outside the pattern of a unit identifier, or a later key path of the metadata source holds another identifier; reported at the field |
| `duplicate-identifier` | error | two records of the repository hold one identifier; reported at each record |
| `identity-disagreement` | warning | no override is declared, and the remote and the folder name two different identifiers; reported at the configuration file |
| `retired-repository-manifest` | warning | a `repository.yml` is left at the root |
| `unknown-record` | error | no record of the repository holds the identifier of a target of the same repository, and the identifier is not retired |
| `renamed-repository` | warning | the target names a former identifier of the repository, which `repository.retired` of `anagraphe.yml` lists; the check resolves the target in the repository |
| `renamed-target` | warning | the target names an identifier retired with a successor |
| `retired-target` | error | the target names an identifier retired without a successor, or whose successors reach no record |
| `unknown-unit` | error | the record of a target holds no unit of its identifier |
| `ambiguous-unit` | error | two units of the record of a target hold its identifier |
| `target-contract-mismatch` | error | the contract of the record of a target matches no entry of `x-target-contract` |
| `unbound-target` | error | the field declares `x-target-contract`, and the record of its target declares no contract |
| `unreadable-record` | error | the frontmatter or the document of a record cannot be parsed |
| `unresolved-schema-reference` | error | a `$ref` of a schema names no readable node of the repository |
| `unreadable-schema` | error | the schema of a contract of the registry cannot be read |

A target of the same repository is one without `repository`, or one whose repository equals the
identifier of the repository or one of its former identifiers. A repository without identity
therefore resolves only its targets without `repository`, and those naming one of its former
identifiers. The record resolver reads every other target, with the findings that the section
"Resolve targets into other repositories" below lists. A target naming a duplicated identifier
receives no finding of its own, since `duplicate-identifier` reports its cause. A duplicated unit is
reported only through a target that names it.

The section `records` names the record registry, so the check reads the retired identifiers only
when that section is declared. For a target naming an identifier retired by a rename, the check
follows the successors to the record holding the last one. The finding `renamed-target` names that
record, and states the target to write instead. The check then applies the unit and the contract
of the target to that record. When the registry is absent or invalid, the check reads no retired
identifier, so a target naming one is reported as `unknown-record`.

Each finding names its file and the JSON Pointer of the target, of the identifier, or of the
declaring keyword of a schema, and the text report prints that pointer at the start of the detail.
A note does not change the exit status, and the gate that reads the findings log decides its
severity. When a record or a schema cannot be read, the findings log declares the run incomplete.

A domain tool may validate the same record against its schema, and report an invalid target as
well. Anagraphe still reports `invalid-target`, so that it stays usable without that tool, and a
gate running both tools removes one of the two findings through its suppressions.

## Compare the read sides

A repository may hold a second read side of the addressing: a host that bundles the TypeScript
package `@anagraphe/read`, such as the Obsidian plugin Ekphrasis once it adopts the package. The
two read sides must implement the same versions of the specification, so the host writes the
`IMPLEMENTED_SPECIFICATION` of the package into a file, and the section `targets` names that file
under `read_sides`:

```yaml
targets:
  read_sides:
    - {path: .obsidian/plugins/ekphrasis/manifest.json, pointer: /anagrapheRead}
```

| Key | Content |
| --- | --- |
| `path` | the JSON or YAML file holding the declaration, relative to the root; a suffix `.json` selects JSON |
| `pointer` | the JSON Pointer of the declaration in the file, the empty pointer for the whole file |

The declaration maps the keys `addressing` and `registry` to strings, as the
[logical targets specification](../specification/logical-targets.md) defines them under
"Versioning". In the manifest of such a plugin, the
declaration stands beside the keys of the manifest:

```json
{
  "anagrapheRead": {
    "addressing": "https://github.com/esther-poniatowski/anagraphe/schemas/addressing.v1.schema.yml",
    "registry": "anagraphe:record-registry@1"
  }
}
```

Until the release that follows 0.10.0, the declaration also held the key `repository`, the contract
of the retired manifest. A read side of 0.10.0 therefore differs on that key, and the comparison
reports it until both read sides take the same release.

The command `anagraphe targets check`, and `anagraphe check`, compare each declaration, key by key,
with the `IMPLEMENTED_SPECIFICATION` of Anagraphe, even when the command selects only some files.
Each finding names the declared file, and the declared pointer as its locus:

| Kind | Level | Issue | Repair |
| --- | --- | --- | --- |
| `read-side-mismatch` | error | the declaration differs from the versions of Anagraphe; the detail names each differing key, with the declared and the implemented value | align the releases of the two read sides |
| `unreadable-read-side` | error | the file cannot be read or parsed, the pointer names an absent node, or the value is other than a mapping of strings to strings | correct the file or the pointer |

A malformed key `read_sides`, such as a pointer holding `~2` or a path outside the repository, stops
the command as an invalid configuration. The comparison covers the identifiers of the versions only:
a definition added to the resource `addressing.v1` keeps its `$id`, so two read sides declaring
that `$id` may still differ by such an addition, as the field paths of
[ADR 0008](../adr/0008-field-paths.md) are.

## Keep the record registry

A resolver in another repository cannot walk the records of a repository, so each repository
commits a **record registry**. The registry maps the identifier of each record to its file, and
keeps every retired identifier permanently. The
[decision on the record registry](../adr/0007-record-registry.md) records the reason for each
choice.

### Write the registry

The section `records` of `anagraphe.yml` enables the registry, and requires the section `targets`,
whose walk supplies the records. The key `registry` of the section `targets` names the schema
registry of the contracts, which is another file:

```yaml
targets:
  records:
    registry: specs/schema-registry.yml
records: {}
```

| Key | Content | Default |
| --- | --- | --- |
| `path` | the file of the registry, relative to the root | `record-registry.yml` at the root |

The command `anagraphe records write` creates the registry once the section is declared, and the
repository commits the file. The command generates the registry from the walk of
`anagraphe targets check`, with its exclusions and with the identifier fields that `x-identifier`
declares. The command carries over the retired identifiers of the current file. The registry is a
YAML document of the contract `anagraphe:record-registry@1`, whose two mappings are keyed by
identifier and sorted:

```yaml
# Generated by anagraphe records write; do not edit by hand.
_schema: anagraphe:record-registry@1
repository: geonexus
records:
  andre_jean-baptiste: {path: contacts/andre_jean-baptiste.yml, format: yaml}
  mixture-input: {path: notes/mixture-input.md, format: markdown}
retired:
  former-id: {date: 2026-11-20, replaced_by: mixture-input}
  removed-id: {date: 2026-11-21}
```

The key `repository` holds the identifier of the repository. When that identifier changes, such as
after a renamed remote, the check reports the registry as stale, so an identity never changes
silently. Each entry of `records`
holds the path of its record and its format, `markdown`, `yaml`, `json` or `toml`. An entry holds no digest
of the bytes of its record, so it changes only when its record appears, disappears, moves or
changes its identifier. A second write yields the same bytes. Beyond its schema, the contract
requires that no chain of `replaced_by` returns to an identifier that it has left.

The write refuses to change the file when the records or the registry hold a defect:

- a record cannot be read, or holds a missing, invalid, duplicate or retired identifier;
- an identifier of the current registry names no record, and is not retired;
- a `replaced_by` names neither a record nor a retired identifier;
- the current registry cannot be read or parsed, or violates its contract;
- the repository has no identity, reported as `unidentified-repository`;
- a schema of the schema registry cannot be read, and the walk misses the identifiers
  declared through that schema.

A refused write prints each defect at its file, under the kind that the check of the targets or of
the registry reports for it.

### Rename or remove a record

An identifier leaves `records` only through the command `anagraphe records retire`. The command
moves the identifier into `retired`, with the date of the day. Therefore, a rename of a record
takes three steps:

1. change the identifier in the record;
2. retire the former identifier with its successor, `anagraphe records retire former-id
   --replaced-by new-id`;
3. write the registry with `anagraphe records write`.

A record is removed in the same steps: the author deletes the record, retires its identifier
without `--replaced-by`, then writes the registry. The command `retire` refuses the identifier, and changes
no file, when:

- the registry does not exist, or is invalid;
- a schema of the schema registry cannot be read, and a record may hold the identifier unseen;
- a record still holds the identifier;
- the identifier is already retired;
- `records` lists no such identifier;
- the successor is neither a record nor a retired identifier;
- the successors of the successor return to the identifier.

A retired identifier is never reused, and no command removes it from `retired`.

### Check the registry

The command `anagraphe records check` compares the registry with the records of the walk, and
writes no file; `anagraphe check` runs it when the section `records` is declared. Each finding
names the registry, and the JSON Pointer of the entry or of the value at fault, such as
`/records/mixture-input` or `/retired/former-id`. A finding of the whole file holds the empty
pointer:

| Kind | Level | Issue | Repair |
| --- | --- | --- | --- |
| `invalid-record-registry` | error | the registry cannot be read or parsed, or violates `anagraphe:record-registry@1`; no other comparison runs | restore the last valid registry from Git, then write the registry |
| `stale-registry` | error | the registry is absent; `records` omits a record, lists it with another path or format, or lists a retired identifier; `repository` differs from the identifier of the repository; or the file holds the generated entries in another written form | write the registry |
| `vanished-identifier` | error | an identifier of `records` names no record, and is not retired | retire the identifier, with its successor after a rename |
| `reused-identifier` | error | a record holds a retired identifier | give the record another identifier |
| `unknown-successor` | error | a `replaced_by` names neither a record nor a retired identifier | give the successor back to the record that replaced it, then rename that record in three steps |

Each defect is reported under one kind. Therefore, an entry naming no record is
`vanished-identifier` when its identifier is not retired, and `stale-registry` when it is. The
check compares no identifier held by two records, since `duplicate-identifier` of the check of the
targets reports that defect. Nor does the check compare the entry of a record that cannot be read.

## Migrate the contracts of the records

When a domain tool publishes a new version of a contract, the domain tool migrates the fields of
its records, and Anagraphe rewrites the contract that each record names under its binding key,
`_schema` by default. A migration plan, in the contract `anagraphe:migration-plan@1`, lists each
former contract and its successor:

```yaml
_schema: anagraphe:migration-plan@1
contracts:
  - {from: 'geonexus:contact@16', to: 'geonexus:contact@17'}
  - {from: 'geonexus:audience@1', to: 'geonexus:audience@2'}
```

The command `anagraphe records migrate --plan PATH` reads the plan, then rewrites the binding key
of every record of the walk of the check of the targets that names a `from`. The mappings apply
simultaneously: each record takes the `to` of the contract that it names before the migration, and
no mapping is chained. The command replaces the characters of the value alone, in the frontmatter
of a note, in a YAML or JSON document, or at the top level of a TOML document, so the comments, the
quoting, the order of the keys and the line breaks of each file are kept. The record registry and
the plan itself, when it lies in the repository, are never rewritten. The command requires the
section `targets` with its schema registry under `records`, and rejects the plan, with status `2`,
when:

- the plan cannot be parsed, or violates `anagraphe:migration-plan@1`;
- a `from` or a `to` is not a contract identifier, under the grammar of Kleisis;
- a `from` equals its `to`, or is listed twice;
- a `to` is also a `from`, so the order of the two mappings would be ambiguous;
- a `to` is no contract of the schema registry of the records.

Each rewritten record is parsed again, and must read as the record before with its new contract.
A record that cannot be rewritten so is reported as `unmigratable-record`, such as a frontmatter
written with Windows line breaks, or a key written twice. A record that cannot be read is reported
as `unreadable-record`, since it may name a migrated contract. Either issue blocks the migration,
which then writes no file and exits with status `1`. Otherwise, the command replaces every changed
file at once, and restores them all when one replacement fails. It prints one line per changed
file, `path:line: _schema: from -> to`.

| Option | Effect | Status |
| --- | --- | --- |
| none | applies the plan | `0`, or `1` when an issue blocks the migration |
| `--dry-run` | lists the changes, and writes no file | `0`, or `1` when an issue would block the migration |
| `--check` | reports each record to migrate as `pending-migration`, and writes no file; takes `--format sarif` and `--output` | `1` when a record would change, or an issue blocks |

A gate runs `anagraphe records migrate --plan PATH --check` after the domain tool migrates its
records, so that no record keeps a former contract. When the two contracts declare their identifier
in different fields, the identifiers change with the contract; `anagraphe records check` then
reports the registry as stale, and `anagraphe records write` writes it again.

## Resolve targets into other repositories

The record resolver reads a target into another repository at a selected state of that
repository: a full commit, never a branch, a tag or a working tree. The resolution context of the
checked root selects that state for each repository identifier:

- each submodule of the root yields an entry. The gitlink in the index selects the commit, and the
  identity of the state at that commit names the repository: the override `repository.id` of its
  `anagraphe.yml`, else the name of the remote of the submodule;
- the section `resolution` declares the other repositories, each with a full commit and a remote
  address.

```yaml
resolution:
  repositories:
    mixture-input-encoding:
      commit: 0123456789abcdef0123456789abcdef01234567
      remote: https://github.com/lab/mixture-input-encoding.git
  local: .anagraphe-repositories.yml
```

| Key | Content | Default |
| --- | --- | --- |
| `repositories` | each cited repository identifier with its `commit`, 40 or 64 hexadecimal digits, and its `remote`, an address in the form `https://`, `http://`, `ssh://`, `git://` or `user@host:path`, without credentials | no declared repository |
| `local` | the machine file of the local clones, relative to the root, which Git must ignore | no machine file |

A repository declared under `repositories` and also held as a submodule stops the command, and so
does an entry naming the repository of the root. The commit of a declared repository moves when
the researcher edits it, so two clones of one commit select the same states.

The machine file maps a repository identifier to the path of a local clone, relative to the folder
of the file or absolute, as in `mixture-input-encoding: ../mixture-input-encoding`. Its paths
belong to one machine, so no commit records the file. The environment variable
`ANAGRAPHE_REPOSITORIES` names a machine file outside the repository, and replaces the key `local`.
A machine file inside the repository that Git does not ignore stops the command. A file named by
`local` may be absent, as on the host of a gate, whereas a file named by the variable must exist.
The clones serve the declared repositories; a submodule is read from its own folder.

The resolver selects the state of the named repository and reads its configuration. It derives the
identity of the state from that configuration and the remote of the state. It then reads the record
registry that the section `records` names, and finally the registered record. A target without `id`
names the repository itself, and resolves once the identity of the state equals the named
identifier. A record of another repository follows a contract whose schemas the selected state does
not carry, so the resolver reads those schemas through the schema registry of the checked
repository. Each step adds its findings to those of the check:

| Kind | Level | Issue |
| --- | --- | --- |
| `renamed-repository` | warning | the target names an identifier that the configuration of a state of the context retires; the check follows it to the current identifier |
| `unknown-repository` | error | the context selects no state of the named repository |
| `unreadable-target-state` | warning | the selected state is absent from the machine, or its access is denied; or a submodule whose state names no repository may hold the named repository |
| `invalid-target-state` | error | the bytes of the selected state fail the verification of the provider |
| `invalid-target-repository` | error | the state has no identity, or its identity differs from the named identifier; or the state holds two configuration files, an invalid `hodegos.yml`, a configuration that cannot be parsed, an invalid section `repository`, or a configuration naming no registry inside the repository |
| `unverified-target` | note | the state holds no configuration, no section `records`, or no registry at the declared path; or the schemas of the contract of the record, which may declare its identifier field, its units or further contracts, are not held by the checked repository |
| `invalid-record-registry` | error | the registry of the state violates `anagraphe:record-registry@1`, or names another repository |
| `unknown-record`, `renamed-target`, `retired-target` | as above | the identifier of the target, looked up in the registry of the state |
| `escaping-target-path` | error | the registered path leaves the state |
| `linked-target-path` | error | the registered path names a symbolic link, which the resolver never follows |
| `stale-target-registry` | error | the registered path names no file, or a record holding another identifier |
| `unreadable-record` | error | the record cannot be parsed in its registered format |
| `unknown-unit`, `ambiguous-unit`, `target-contract-mismatch`, `unbound-target` | error | as for a target of the same repository |

The Git provider reads each selected state from the objects of its commit, never from a working
tree, in the first store of the machine holding the commit:

1. the clone of the entry: the folder of a submodule, or the clone named by the machine file for a
   declared repository;
2. the cache of the machine: one bare Git repository, `anagraphe/states` below the cache folder of
   the user, or the folder named by the environment variable `ANAGRAPHE_CACHE`.

The provider hashes every object that it reads, the commit, each tree along the path and the
file, and compares the hash with the identifier that named the object. An object whose bytes
differ yields `invalid-target-state`, and a commit held by no store yields
`unreadable-target-state`, whose detail names the command that fetches it. A target into a
repository outside the context receives `unknown-repository`.

The command `anagraphe states fetch` is the only one that uses the network. It fetches into the
cache each state of the context that no store of the machine holds, with the commit and its tree
alone, from the remote of the context: the address of a declared repository, or the address of a
submodule in `.gitmodules`, a relative address being resolved against the remote of the root.
Credentials come from the configuration of Git on the machine, and Git never prompts for one. The
command prints each state as `held`, `fetched`, `no-remote`, `unavailable`, `denied` or `failed`,
and exits with status `1` when a state stays absent from the machine.

The gate of a repository whose targets name another repository runs the fetch before the check. A
workflow of GitHub reading a private repository passes its token to Git as a header, here built
from a secret `READ_TOKEN`:

```yaml
- name: Fetch the selected states
  env:
    READ_TOKEN: ${{ secrets.READ_TOKEN }}
  run: |
    header="Authorization: Basic $(printf 'x-access-token:%s' "$READ_TOKEN" | base64 | tr -d '\n')"
    git config --global http.https://github.com/.extraheader "$header"
    anagraphe states fetch
```

## Read targets from a tool

A tool written in Python reads targets through the interface of the read distribution
`anagraphe-read`, the module `anagraphe_read`. The script below compares two targets written in one
repository:

```python
from anagraphe_read import Target, open_repository

repository = open_repository(root)
own = repository.identity.id
same = Target.parse(a).normalized(own) == Target.parse(b).normalized(own)
```

The identity of the root derives from the section `repository` of the configuration, the remote of
the root and its folder. `Target.parse` raises `InvalidTarget`, whose `reason` names the first
failed check.

The same repository reads the record of a target into another repository, through a provider of
the states, the Git provider of the machine by default:

```python
from anagraphe_read import Outcome

resolution = repository.resolve(target)
if resolution.outcome is Outcome.RECORD:
    read = repository.read(resolution, contracts)
```

`resolve` returns the outcome, the target followed to its current identifiers, its provenance and
its findings; `read` returns the bytes of the record, their provenance and the findings of its
verification. A provider implements the protocol `StateProvider`, whose method `read(state, path)`
returns a `Blob` with its mode, or the reason why the path cannot be read. The class
`MemoryProvider` serves states declared in memory, for tests. The file
`specs/conformance/resolution.yml` holds the cases that every resolver passes.
