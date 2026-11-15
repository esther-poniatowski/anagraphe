# ADR 0007: Record registry

**Status**: Accepted by the researcher on 2026-11-14, with the answers recorded under "Resolved
questions"; proposed on the same day. The record answers the task `record-registry` of the
[task list of Geonexus][geonexus-todo]. [ADR 0006](0006-logical-targets.md) leaves that task open:
it fixes neither the format of the record registry nor the form of a declared rename.

---

## Problem Statement

A logical target `{repository, id, unit}` names a record by its identifier, never by its path, as
ADR 0006 states. Within one repository, `anagraphe targets check` finds the record of an identifier
by walking every file and reading its identifier. A resolver of another repository cannot walk that
repository. It reads the repository at a selected state, possibly through a bundle limited to the
files of one operation, and possibly from the TypeScript read side on mobile. Each repository must
therefore publish the map from the identifiers of its records to their files.

**Premises.** The following points are fixed by earlier decisions. This record reopens only the
digest of an entry, under question 2:

- The record registry maps each record identifier to its repository-relative path, its format and
  the digest of its raw bytes. Each repository generates its registry from the metadata and the
  bytes of its files, and the registry is never maintained by hand
  ([resolution context][resolution-context]).
- The resolver loads the registry of the selected state and resolves an identifier to a path. It
  rejects a path escaping the state, then verifies the identifier, the format and the digest of the
  file. It distinguishes a stale registry from a missing record ([failure rules][resolution-failures]).
- The manifest of a bundle or of a cache binds the repository, the commit and the tree, the digest
  of the registry, and each included path with the digest of its record
  ([resolution context][resolution-context]).
- The record registry keeps each declared rename permanently, and a retired identifier is never
  reused. A resolver follows a declared rename with a warning
  ([resolution context and renames][tool-roles-renames]).
- The identifier of a record is the field declared by `x-identifier` in its schema, by default the
  key `id` of its metadata source. Its units are the items of an array whose definition carries
  `x-identifier` and, in a note, the block anchors of its body (ADR 0006).
- An index helps a reader choose a record, whereas a registry maps the identity of a record to its
  location; the two remain distinct views ([implications][resolution-implications]).

**Questions to be addressed**:

1. Is the registry a file committed in each state of the repository, or is it derived from the tree
   of that state when a resolver reads it?
2. Does an entry hold the digest of the raw bytes of its record, beside its path and its format?
3. How does the registry keep the retired identifiers, and how does an author declare a rename?
4. Where does the registry live, which commands write and check it, and which findings does the
   check report?

---

## Decision Drivers

- **Reach**: a resolver finds the record of an identifier from the registry and the selected state
  alone, including from a bundle that holds no full snapshot, and from the TypeScript read side.
- **Single source**: the registry restates no fact that the Git tree or the manifest of a bundle
  already binds.
- **Stability**: an entry changes when its record appears, disappears, moves or changes identifier,
  not when its text changes. Several sessions commit to one repository, so each changed line is a
  possible conflict between them.
- **Permanence**: a retired identifier stays retired after its record is deleted.
- **No hand edits**: every line of the registry is written by a command.
- **Safety**: an identifier is retired only by an explicit act of the author.

---

## Considered Options

### Question 1: committed or derived

- **Committed registry**: a command generates a file in the repository, and the gate rejects a
  commit whose file differs from the generation, as it does for the indexes.
- **Derived registry**: no file exists; a resolver walks the tree of the selected state and reads
  each record, as `anagraphe targets check` does within one repository.

### Question 2: the digest of an entry

- **Path, format and digest**: the entry stated by the decision on cross-repository resolution, with
  the SHA-256 digest of the raw bytes of the record.
- **Path and format**: the entry holds no digest. The bytes of a record are bound by the tree of the
  selected state, through the object identifier of each file, or by the manifest of the bundle or the
  cache that supplies them.

### Question 3: retired identifiers

- **Kept by the registry**: the registry holds a list `retired`, carried over by each generation
  from the current file. A generation refuses to drop an identifier that no record holds any longer.
  The author first retires that identifier by a command, naming its successor in the case of a rename.
- **Declared by the records**: each record lists its former identifiers in a field, as the manifest
  of a repository lists them under `repository.retired`.
- **Retired automatically**: a generation retires every identifier that no record holds any longer,
  without a command.

---

## Analysis of Options

### Summary: Comparison by Criteria

- **Question 1**
  - **Reach**: committed HIGH (a bundle carries one file, and the TypeScript side reads it); derived
    LOW (a resolver needs the full tree and every schema of that state, and a bundle holds neither).
  - **Single source**: committed MEDIUM (a generated view of the identifiers and paths of the tree);
    derived HIGH.
  - **Stability**: committed MEDIUM (an entry changes when a record is added, moved or renamed);
    derived HIGH.
- **Question 2**
  - **Reach**: both HIGH, since the resolver verifies the bytes in either case.
  - **Single source**: with digest LOW (it restates the object identifier of the tree, and the digest
    already recorded by the manifest of a bundle); without digest HIGH.
  - **Stability**: with digest LOW (an entry changes at each edit of its record); without digest
    HIGH. On 2026-11-14, 37 of the 555 commits of Geonexus over 30 days changed a file that holds a
    record today.
- **Question 3**
  - **Permanence**: kept by the registry HIGH; declared by the records LOW (a deleted record takes its
    former identifiers with it); retired automatically HIGH.
  - **No hand edits**: kept by the registry HIGH (a command writes each line); declared by the
    records LOW (each contract of each tool needs a field written by the author); retired
    automatically HIGH.
  - **Safety**: kept by the registry HIGH; retired automatically LOW (a record removed by mistake, or
    left out of the walk by a new exclusion, loses its identifier for ever).

A derived registry would win if every resolver read full Git trees. The premise on bundles excludes
that route. A digest in each entry would win if a resolver read records from a source that binds no
bytes. The Git tree and the manifests of bundles and caches already bind them.

---

## Conclusions

### Decision

**Chosen option**: each repository commits a record registry generated by
`anagraphe records write` and checked by `anagraphe records check`. An entry maps an identifier to
its path and its format, without a digest. The registry keeps a permanent list of retired
identifiers, extended only by `anagraphe records retire`.

**Justification**: A bundle can carry a committed file, and no other form of the registry. The
absence of a digest keeps each entry stable, while the tree and the manifests still bind the bytes.
The list of retired identifiers lives in the registry, because only a file outliving each record can
keep an identifier retired after its record is deleted.

#### Written form

The registry is a YAML document under the contract `anagraphe:record-registry@1`. Anagraphe publishes
that contract with an absolute `$id`, as it publishes the resource `addressing.v1`. The mappings of the
registry are keyed by identifier and sorted, so that each record occupies one line:

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

The key `repository` holds the identifier of the manifest. The format is `markdown`, `yaml` or `json`. A nested repository, such as a submodule,
is a repository of its own, and its records belong to its own registry. The walk is the walk of
`anagraphe targets check`, with its exclusions and its reading of `x-identifier`.

The resolver verifies the bytes of a record against the tree of the selected state, or against the
digest of the record in the manifest of a bundle or a cache. The decision on cross-repository
resolution must drop the digest from the entry of the registry in the same change.

#### Configuration and commands

The section `records` of `anagraphe.yml` enables the commands. Its key `path` names the file,
`record-registry.yml` at the root by default. The file name keeps its qualifier, and the section
does not take the name `registry`, because each repository also holds a schema registry, which the
section `targets` already names by its key `registry`. The configuration keeps
`anagraphe:configuration@2`.

- `anagraphe records write` generates `records` from the walk and carries over `retired` from the
  current file. It writes nothing and exits with a failure when the walk holds a missing, invalid,
  duplicate or retired identifier. It fails in the same way when an identifier of the current file
  names no record and is not retired.
- `anagraphe records check` reports the findings below, and writes nothing.
- `anagraphe records retire ID [--replaced-by NEW]` moves an identifier that no record holds any
  longer into `retired`, with the date and the successor when one is given. The successor must be a
  record or a retired identifier.

A rename therefore takes three steps. The author changes the identifier in the record, retires the
former identifier with its successor, and writes the registry. The command `anagraphe rename-id` of
the task list will later combine the three steps.

#### Checks

Each finding names the registry as its resource, and the JSON Pointer of the entry as its locus,
under [ADR 0004](0004-findings-output.md).

| Finding | Level | Condition |
| --- | --- | --- |
| `invalid-record-registry` | error | the registry violates `anagraphe:record-registry@1` |
| `stale-registry` | error | the entries of `records` differ from the generation |
| `vanished-identifier` | error | an identifier of `records` names no record of the walk, and is not retired |
| `reused-identifier` | error | a record holds a retired identifier |
| `unknown-successor` | error | `replaced_by` names neither a record nor a retired identifier |

The findings `missing-identifier`, `invalid-identifier` and `duplicate-identifier` remain those of
`anagraphe targets check`, in the terms of ADR 0006. Within one repository, `anagraphe targets check`
keeps its walk, since it reads every record for its targets in any case. It also reads the list
`retired`, and reports a target naming a retired identifier in one of two ways:

- `renamed-target`, a warning naming the successor, for an identifier retired with a successor;
- `retired-target`, an error, for an identifier retired without a successor.

These two findings replace `unknown-record` for a retired identifier.

### Final Answers

1. The registry is a file committed in each state of the repository, generated by a command and
   checked by the gate.
2. An entry holds the path and the format of its record, without a digest; the tree of the selected
   state or the manifest of a bundle binds the bytes.
3. The registry keeps a permanent list of retired identifiers, extended only by the command
   `retire`, with the successor of a rename.
4. The section `records` of `anagraphe.yml` names the file, `record-registry.yml` at the root by
   default. The commands `write`, `check` and
   `retire` maintain it, and the check reports the five findings of the table.

---

## Implications

- **Decision on cross-repository resolution**: the entry of the record registry loses its digest. The
  step that verifies the digest declared by the registry verifies it against the tree or the manifest
  of the bundle instead.
- **ADR 0006**: the sentence stating that the generated registry replaces the walk of the check
  changes. The walk stays within one repository, and the registry serves the other repositories. The
  deferred finding of a renamed record becomes `renamed-target`.
- **Consumers**: every repository with a manifest declares the section `records`, commits its
  registry and runs `anagraphe records check` in its gate.
- **Resolver**: the task `record-resolver` of Geonexus loads the registry of the selected state, and
  the TypeScript read package reads the same file.

### Resolved questions

The researcher answered the open questions of the proposal on 2026-11-14:

1. An entry drops its digest. The decision on cross-repository resolution is amended in the same
   change.
2. A vanished identifier is retired by the command `retire` only.
3. The registry defaults to `record-registry.yml` at the root, under the section `records`.
4. Every repository with a manifest commits a registry, so that any of its records can be cited
   from another repository without a further step.

---

## See Also

### Related Decisions

- [ADR 0004](0004-findings-output.md): Follows. The findings take its profile.
- [ADR 0006](0006-logical-targets.md): Completes. The registry is the task that ADR 0006 defers.

### References and Resources

[geonexus-todo]: https://github.com/esther-poniatowski/geonexus/blob/72178bb5d10ff828a15546947fae588f58dee64d/TODO.md
[resolution-context]: https://github.com/esther-poniatowski/geonexus/blob/72178bb5d10ff828a15546947fae588f58dee64d/docs/_decisions/cross-repository-record-resolution.md#resolution-context
[resolution-failures]: https://github.com/esther-poniatowski/geonexus/blob/72178bb5d10ff828a15546947fae588f58dee64d/docs/_decisions/cross-repository-record-resolution.md#failure-and-access-rules
[resolution-implications]: https://github.com/esther-poniatowski/geonexus/blob/72178bb5d10ff828a15546947fae588f58dee64d/docs/_decisions/cross-repository-record-resolution.md#implications
[tool-roles-renames]: https://github.com/esther-poniatowski/geonexus/blob/72178bb5d10ff828a15546947fae588f58dee64d/docs/_decisions/tool-roles.md#resolution-context-and-renames
