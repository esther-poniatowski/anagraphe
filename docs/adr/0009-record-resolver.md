# ADR 0009: Record resolver

**Status**: Accepted by the researcher on 2026-11-17, with the answers recorded under "Resolved
questions"; proposed on 2026-11-16. Clarified on 2026-11-17 by four choices of the implementation,
recorded under "Clarifications of the implementation". The record answers the task `record-resolver` of the
[task list of Geonexus][geonexus-todo]. [ADR 0007](0007-record-registry.md) unblocked that task by
adding the record registries.

**Amended** on 2026-11-19, with the derivation of the identity in [ADR
0006](0006-logical-targets.md): no state is named by a manifest any longer. The identity of a
selected state is the override `repository.id` of the configuration of Anagraphe at that state, else
the name of the remote of the state. Its former identifiers come from `repository.retired` of that
configuration. Each passage below that named the manifest of a state carries the date of the
amendment.

---

## Problem Statement

The record resolver of Anagraphe locates the record of another repository named by a logical
target. The resolver also reads that record, verified against a selected state of its repository.
[ADR 0006](0006-logical-targets.md) fixes the target `{repository, id, unit}`. For a target into
another repository, the check of the targets reads the form alone, and reports `unverified-target`
at the level `note`.

The [decision of Geonexus on cross-repository resolution][resolution] fixes the contract of the
resolver:

- a resolution context maps each repository identifier to its locations and its selected state;
- a repository-state provider reads the bytes of a selected state, from a Git object store, a
  verified cache or an authorized bundle;
- the record-access library exposes two operations: `resolve` returns the locator and the
  provenance of a target, and `read` returns the verified bytes of its record;
- the library follows one route of seven steps, and distinguishes the failures that the decision
  lists.

The decision assigns the library and its providers to Anagraphe. The task list of Geonexus divides
that work into two tasks: `record-resolver`, the library, and `record-state-provider`, the readers
of Git trees, caches and bundles. ADR 0006 adds three duties to the first task: the normalization of
a target, the reading of the manifest that names a repository (since 2026-11-19, the identity of a
state), and the matching of `x-target-contract`.

Two consumers wait on the library. The task `glossary-import-closure` of Onomasia imports a glossary
from another repository, such as the glossary of Mixture copied today into the thesis. The check of
the targets verifies each field target into another repository, instead of noting it. The form of
a body link into another repository waits on the task `record-reader-views`.

**Questions to be addressed**:

1. Where does a standalone clone find the location and the selected state of each repository that
   its targets name?
2. Does this task read real states, or only states supplied through the port of the provider?
3. Which task implements the resolver in the TypeScript read package?
4. At which level does the check report a target whose selected state the machine cannot read?

---

## Decision Drivers

- **Determinism**: a verified read follows from the target, a full commit and the bytes of that
  commit. A working tree, a branch, a tag or an abbreviated commit never certifies a record.
- **Explicit availability**: an unreadable state stays distinguishable from a missing record, and
  from an invalid manifest or registry of the target repository; since 2026-11-19, from a state
  without identity or with an invalid configuration.
- **Portability**: a committed file names neither a machine path nor a credential. Two clones of one
  commit, on two machines, select the same states.
- **Usable gates**: the gate of a project runs on its host without the clones of the cited
  repositories, and its findings keep their meaning there.
- **Task boundaries**: each task delivers one testable part, and leaves the next task its declared
  scope.

---

## Considered Options

### Context of a standalone clone

1. **Declared context**: the section `resolution` of `anagraphe.yml` maps each cited repository
   identifier to a full commit and to a remote address without credentials.
   - The path of a local clone comes from a machine file kept out of Git: a file outside the
     repository, named by an environment variable, or a file ignored by Git inside it, named by a
     path in the configuration.
2. **Sibling discovery**: the resolver looks for a clone beside the root of the repository, whose
   manifest declares the cited identifier (since 2026-11-19, whose identity is the cited
   identifier), and reads the commit checked out in that clone.
3. **Workspace only**: a standalone clone resolves no target into another repository, and keeps
   reporting each of them as `unverified-target`.

### States read by this task

1. **Port only**: the task delivers the library and the port of the provider, and tests both with
   an in-memory provider. The task `record-state-provider` reads Git trees, caches and bundles, as
   the task list of Geonexus assigns them.
2. **Git trees now**: the task also reads Git trees, and leaves the caches and the bundles to the
   task `record-state-provider`.

### Owner of the TypeScript resolver

1. **Reader views**: the task `record-reader-views` implements the resolver in the TypeScript
   package, on the conformance cases written now, since its views are built on `resolve`.
2. **This task**: the task implements the resolver in Python and in TypeScript.

### Level of an unreadable state

1. **Error**: the check reports an unreadable state as an error, as ADR 0006 lists it among its
   findings.
2. **Note**: the check keeps the note `unverified-target`, whose detail names the repository, the
   commit and the reason: the state is absent, or its access is denied.
3. **Warning**: the check reports the kind `unreadable-target-state` at the level `warning`, with
   the same detail. A warning gates no commit under the default policy of a gate.

---

## Analysis of Options

### Individual Assessment

#### Context of a standalone clone

1. **Declared context**
   - Pros: the configuration records a full commit, so two clones of one commit select the same
     state; the path of a local clone stays out of the repository.
   - Cons: the researcher declares each cited repository, and moves its commit by hand.
2. **Sibling discovery**
   - Pros: the repository declares no context.
   - Cons: the commit checked out in a sibling clone floats, so the read certifies no record; the
     result depends on the layout of one machine.
3. **Workspace only**
   - Pros: no new configuration.
   - Cons: a standalone project, such as the thesis read alone, never verifies its imports.

#### States read by this task

1. **Port only**
   - Pros: the two tasks keep the boundaries of the task list. The conformance cases fix the
     behavior of the resolver before any provider exists.
   - Cons: no repository reads a real state until the task `record-state-provider` closes.
2. **Git trees now**
   - Pros: a workspace resolves its targets at the close of this task.
   - Cons: the task takes part of the scope of `record-state-provider`, and binds the port to its
     first implementation before the caches and the bundles test it.

#### Owner of the TypeScript resolver

1. **Reader views**
   - Pros: the TypeScript resolver arrives with its first consumer, the live and materialized
     views. The decision of Geonexus asks for one read implementation per language, tested on
     shared cases.
   - Cons: the two read sides differ until that task closes.
2. **This task**
   - Pros: no period of difference.
   - Cons: no consumer of the TypeScript resolver exists to test it.

#### Level of an unreadable state

1. **Error**
   - Pros: no target passes unread.
   - Cons: the gate of a project fails on its host for every cited repository, a property of the
     machine rather than of the record.
2. **Note**
   - Pros: the gate stays usable on its host, and the note keeps each unread target visible.
   - Cons: a machine without the cited states verifies the form of the target alone, and the note
     ranks that gap with the legitimate absence of a registry.
3. **Warning**
   - Pros: the gate stays usable on its host, and the warning ranks an unread state above the
     notes of a legitimate gap. The kind of its own lets a gate set its level apart.
   - Cons: a machine without the cited states verifies the form of the target alone.

### Summary: Comparison by Criteria

Each table compares the options of one question.

| Context of a standalone clone | Declared context | Sibling discovery | Workspace only |
| --- | --- | --- | --- |
| Determinism | high (full commit) | low (floating checkout) | high (no read) |
| Portability | high (machine file apart) | low (machine layout) | high |
| Usable gates | medium (declared states) | medium | low (never verified) |

| States read by this task | Port only | Git trees now |
| --- | --- | --- |
| Task boundaries | high (declared scopes) | low (moves a scope) |
| Usable gates | low until the next task | medium |

| Owner of the TypeScript resolver | Reader views | This task |
| --- | --- | --- |
| Task boundaries | high (arrives with its consumer) | low (no consumer) |

| Level of an unreadable state | Error | Note | Warning |
| --- | --- | --- | --- |
| Explicit availability | high | medium (ranked with a legitimate gap) | high (kind of its own) |
| Usable gates | low (fails on the host) | high | high (non-blocking) |

---

## Conclusions

### Decision

**Chosen option**: the record-access library of Anagraphe, with four answers:

- the declared context of a standalone clone;
- the port only, the states being read by the task `record-state-provider`;
- the TypeScript resolver in the task `record-reader-views`;
- a warning of its own kind for an unreadable state.

**Justification**: the design delivers a library testable on its own, keeps the scopes of the task
list, and keeps the gate of a project usable on its host.

The library lives in the module `anagraphe.resolution`, and composes four parts.

**Resolution context**. The context belongs to the root checked by the command, so one commit of a
repository resolves alike in every clone of it:

- a root holding submodules derives an entry for each submodule. The gitlink in the index of the
  root selects the commit, since the index holds the state that the next commit records. The
  manifest at that commit, read through the provider, names the repository. Since 2026-11-19, the
  identity of the state at that commit names it: the override of its configuration, read through the
  provider, else the name of the remote of the submodule;
- the section `resolution` of the root declares the other entries, each with a full commit and a
  remote address without credentials. A derived and a declared entry of one identifier stop the
  command with a configuration error;
- a machine file maps an identifier to the path of a local clone. The environment variable
  `ANAGRAPHE_REPOSITORIES` names a file outside the repository; otherwise, the key `local` of the
  section `resolution` names a file inside it. A file that Git tracks stops the command with a
  configuration error, since its paths belong to one machine. The machine file serves the declared
  entries; a submodule is read from its own folder.

**State provider**. A port reads a path of a selected commit, and returns its bytes and its mode. A
provider reports a state as absent, denied or failing its verification. A provider also rejects a
path that escapes the state, as the task list assigns to the task `record-state-provider`.

**Resolve**. The operation follows the route of the decision of Geonexus:

1. normalize the target: a target naming the repository of the root is a local target;
2. select the state of the repository from the context. A repository identifier listed as retired by
   a manifest of the context (since 2026-11-19, by the configuration of a state of the context)
   resolves to its current identifier, with a warning;
3. read the manifest and the configuration of Anagraphe at that state, then the registry at the path
   named by that configuration. Since 2026-11-19, the resolver derives the identity of the state
   from its configuration and its remote, in place of the manifest, and requires it to equal the
   identifier naming the state;
4. look up the identifier, and follow a chain of `replaced_by` as the check of a local target does.

A target without `id` names the repository itself, and resolves once its state declares the
identifier.

**Read**. The operation reads the registered path through the port. The resolver never follows a
symbolic link, since a link may leave the selected state. Next, the operation verifies four
properties of the record:

- the record parses in its registered format;
- the record holds the identifier, through the default field or the field declared by its contract;
- the record holds the unit of the target;
- the contract of the record matches `x-target-contract` of the citing field.

The operation returns the bytes with their provenance: the repository, the commit and the path.

The selected state keeps its own schema closure outside Git. Therefore, the resolver reads the
schemas of a contract through the schema registry of the consumer: the field declaring the
identifier, and the declarations matching the contract to `x-target-contract`. When the consumer
lacks those schemas, the identifier, the unit and the contract stay unverified, and the check notes
them.

The check of the targets maps each outcome to a finding:

| Outcome | Finding | Level |
| --- | --- | --- |
| the record holds the identifier, the unit and an admitted contract | none | |
| the repository identifier is retired, and names a current repository | `renamed-repository` | warning |
| the record identifier was renamed, and its chain ends at a record | `renamed-target` | warning |
| the record identifier was retired without a live successor | `retired-target` | error |
| the context selects no state of the repository, and every submodule names its repository | `unknown-repository` | error |
| the manifest of the state is absent, invalid, or declares another identifier (since 2026-11-19: the state has no identity, or another one, or its section `repository` is invalid); or the state holds two configuration files, or a configuration that cannot be parsed or names no registry inside the repository | `invalid-target-repository` | error |
| the state holds no configuration of Anagraphe, no section `records`, or no registry at the path that this section names, as ADR 0007 admits | `unverified-target` | note |
| the registry of the state violates its contract | `invalid-record-registry` | error |
| the registry holds no such identifier | `unknown-record` | error |
| the registered path names a symbolic link | `linked-target-path` | error |
| the provider reports the registered path as escaping the state | `escaping-target-path` | error |
| the record cannot be parsed in its registered format | `unreadable-record` | error |
| the registered path names no file, or a record holding another identifier | `stale-target-registry` | error |
| the record declares no such unit, or two of them | `unknown-unit`, `ambiguous-unit` | error |
| the contract of the record matches no admitted contract, or the record declares none | `target-contract-mismatch`, `unbound-target` | error |
| the consumer lacks the schemas declaring the identifier or matching the contract | `unverified-target` | note |
| the state is absent or denied on the machine; or the context selects no state of the repository, and a submodule whose manifest cannot be read (since 2026-11-19, whose state names no repository) may hold it | `unreadable-target-state` | warning |
| the provider fails to verify the bytes of the state | `invalid-target-state` | error |

A duplicated identifier stays out of a registry written by Anagraphe, since the command
`anagraphe records write` refuses it. A record omitted by a stale registry appears to the consumer
as `unknown-record`.
The check of the registry in the gate of the target repository, `anagraphe records check`, reports
both defects at their source.

Two failures of the decision stay with the owner of a compositional field: a cycle or an exceeded
limit in an import closure, and a content violating the contract of the importing field. Onomasia
detects both in the task `glossary-import-closure`.

### Final Answers

1. Where does a standalone clone find the location and the selected state of each repository that
   its targets name?
   The section `resolution` of its configuration names a full commit and a remote address for each
   cited repository. A machine file kept out of Git maps an identifier to a local clone: a file
   outside the repository named by an environment variable, or a file ignored by Git inside it,
   named by a path in the configuration.
2. Does this task read real states?
   No. The task delivers the library and the port, tested with an in-memory provider, and the task
   `record-state-provider` reads Git trees, caches and bundles.
3. Which task implements the resolver in the TypeScript read package?
   The task `record-reader-views`, on the conformance cases written now.
4. At which level does the check report a target whose selected state the machine cannot read?
   The warning `unreadable-target-state`, whose detail names the repository, the commit and the
   reason. The answer amends ADR 0006, where an unavailable or denied state is an error.

### Resolved questions

The researcher answered the four questions on 2026-11-17. Two answers refine the proposal:

1. The machine file may also lie inside the repository, ignored by Git and named by a path in the
   configuration, beside the file outside it named by an environment variable.
2. An unreadable state is a warning of its own kind, not a note, so that it ranks above the
   legitimate gaps noted by `unverified-target`.

### Clarifications of the implementation

The researcher ratified four choices of the implementation on 2026-11-17. Each choice settles a
case that the decision above leaves open, and the table of outcomes states its finding:

1. **A repository outside the context**. A target naming a repository that the context does not
   select receives `unknown-repository`, an error, even while no provider reads real states. The
   context follows from the index and the configuration of the root alone, without reading any
   state. Therefore, the defect lies in the configuration of the root, not on the machine. The
   warning `unreadable-target-state` of the period without a provider covers the repositories of
   the context alone.
2. **A submodule naming no repository**. The context names a submodule by its manifest, read through
   the provider; since 2026-11-19, by the identity of its state. When that identity cannot be read
   or derived, the submodule may hold the repository that a target names. A target naming a
   repository outside the context then receives `unreadable-target-state`, since its cause may be a
   state that the machine cannot read.
3. **A state without registry, or with a defective configuration**. A state holding no configuration
   of Anagraphe, no section `records`, or no registry at the declared path holds no registry, and
   its targets receive the note `unverified-target`. The gate of the target repository reports a
   declared registry that is absent, through `anagraphe records check`. A state holding two
   configuration files, or a configuration that cannot be parsed or that names a registry outside
   the repository, receives `invalid-target-repository`, since the configuration belongs with the
   manifest to the identity of the repository. Since 2026-11-19, the configuration holds the
   override of that identity.
4. **The local clone of a submodule**. The machine file serves the declared repositories alone. A
   submodule is read from its own folder, which the gitlink of the root locates. That folder holds
   the commit that the gitlink selects, whereas another clone named by a machine file may lack it.

---

## Implications

- **Module**: the module `anagraphe.resolution` holds the context, the port of the provider, an
  in-memory provider for the tests, and the two operations. The check of the targets calls them for
  every target into another repository. Until a provider reads real states, each target into a
  repository of the context receives the warning `unreadable-target-state`, whose detail states
  that no provider reads its state. A target into a repository outside the context receives
  `unknown-repository`.
- **Configuration**: the section `resolution` declares the cited repositories of a root and,
  under its key `local`, the path of an ignored machine file. The guide of the targets documents
  both, with the environment variable `ANAGRAPHE_REPOSITORIES`.
- **Findings**: the catalogue of the targets changes in three ways:
  - eight kinds join it: `renamed-repository`, `unknown-repository`, `invalid-target-repository`,
    `linked-target-path`, `escaping-target-path`, `stale-target-registry`, `invalid-target-state`
    and `unreadable-target-state`;
  - five kinds extend to a target into another repository: `unknown-record`, `unreadable-record`,
    `invalid-record-registry`, `renamed-target` and `retired-target`;
  - the note `unverified-target` keeps two legitimate gaps: a state holding no registry, and a
    consumer lacking the schemas of a contract. Its description drops the mention of a missing
    resolver.
- **ADR 0006**: an amendment of the record points its row of cross-repository failures to the
  table of outcomes above, at their levels.
- **Conformance**: the file `specs/conformance/resolution.yml` holds the shared cases, each with a
  context, the files of each state and an expected outcome.
- **Later tasks**: the task `record-state-provider` implements the port for Git trees, caches and
  bundles. With those providers, a workspace verifies the targets into its submodules. A gate on its
  host verifies the targets whose states a cache or a bundle supplies. The task
  `glossary-import-closure` reads the imported glossaries through `read`.

---

## See Also

### Related Decisions

- [ADR 0006](0006-logical-targets.md): Completes. ADR 0006 checks a target into another repository
  by its form alone, and the resolver verifies it.
- [ADR 0007](0007-record-registry.md): Reads. The resolver loads the registry of each selected
  state.

### References and Resources

- [Decision of Geonexus on cross-repository resolution][resolution]

[geonexus-todo]: https://github.com/esther-poniatowski/geonexus/blob/main/TODO.md
[resolution]: https://github.com/esther-poniatowski/geonexus/blob/main/docs/_decisions/cross-repository-record-resolution.md
