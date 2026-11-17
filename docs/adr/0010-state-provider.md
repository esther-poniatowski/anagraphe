# ADR 0010: Repository-state provider

**Status**: Proposed on 2026-11-17. The record answers the task `record-state-provider` of the
[task list of Geonexus][geonexus-todo], and awaits the answers of the researcher to its four
questions.

---

## Problem Statement

[ADR 0009](0009-record-resolver.md) delivered the record resolver and the port of a
repository-state provider, tested with an in-memory provider. No provider reads a real state, so
each target into another repository receives the warning `unreadable-target-state`.

The [decision of Geonexus on cross-repository resolution][resolution] fixes the contract of the
provider:

- the provider obtains the exact selected state from a local Git object store, an ignored verified
  cache or an authorized read-only bundle;
- a certified read uses the bytes of the selected Git tree, never the files of a working tree;
- the trusted resolution context supplies the remote locators and the selected states, and
  imported content supplies neither;
- remote access, credentials and cache policy belong to the provider, and no credential enters a
  record, a receipt or the metadata of a cache;
- the provider distinguishes an unavailable state, a denied access, an escaping path or symbolic
  link, bytes that fail their verification, and an incomplete cache or bundle.

A selected state is a full commit. A Git commit identifier is the hash of the commit object, which
names its tree by the hash of the tree, and each tree names its entries by their hashes. Therefore,
every Git object store holding a commit yields the same bytes for each path of it, and Git verifies
them while it reads them. That property holds for the clone of a submodule, a declared local clone
and a fetched copy alike.

Three measured facts of the workspace bear on the design:

- the vault declares its submodules in `.gitmodules` by relative addresses, such as
  `../mixture-input-encoding.git`, which Git resolves against the remote of the root;
- the gate of a project runs on its host without the clones of the repositories it cites;
- the workflows of four projects already read the private vault through a read-only token, from
  which they build an HTTP `Authorization` header for Kleisis;
- GitHub serves a fetch of one commit by its full identifier at depth one, with the commit and its
  whole tree, as a probe of Anagraphe confirmed.

**Questions to be addressed**:

1. Which form does the verified cache take?
2. When does the provider use the network?
3. Does this task implement the authorized bundle?
4. Where does the cache lie on a machine?

---

## Decision Drivers

- **Determinism**: the bytes of a read follow from the full commit alone, whatever store supplies
  them. A branch, a tag, an abbreviated commit or a working tree never certifies a record.
- **Verification**: no byte reaches the resolver unverified against the selected commit; a store
  that fails its verification reports `invalid`, not a missing record.
- **Credential hygiene**: no committed file, cache file or receipt names a credential or a machine
  path. Credentials reach Git through the configuration of the machine or of the host.
- **Usable gates**: the commit hook of the vault verifies the targets into its submodules without
  the network; the gate of a project on its host verifies its targets after one explicit step.
- **Task boundaries**: the task delivers the sources that a consumer needs now, and leaves a
  source without a consumer to a later decision.

---

## Considered Options

### Form of the cache

1. **Git object store**: one bare Git repository per repository identifier, filled by fetching the
   selected commit, with its tree, from the remote of the context. The provider reads a path
   through the objects of the commit, as for a clone.
2. **File cache with a manifest**: a folder holding the files of the selected state and a manifest
   binding the repository identifier, the commit, the tree, the digest of the registry and the
   `sha256` digest of each file. The provider authenticates the manifest against the Git objects
   of the commit.

### Use of the network

1. **Explicit fetch**: a command `anagraphe states fetch` fills the cache with each state of the
   context absent from every local store. The checks never use the network.
2. **Fetch on demand**: the check fetches a state absent from every local store when a target
   needs it.

### Authorized bundle

1. **Later decision**: this task reads Git object stores alone. A later decision fixes the bundle
   when a consumer needs offline or private inputs without repository access.
2. **Git bundle now**: the provider also reads a file written by `git bundle` for the selected
   commit, whose `sha256` digest the section `resolution` pins.

### Location of the cache

1. **Cache of the user**: one folder per machine, `anagraphe/states/` below the cache folder of the
   user, which the environment variable `ANAGRAPHE_CACHE` replaces. Every root of the machine
   shares it.
2. **Folder of the root**: an ignored folder below each root, such as `.anagraphe/states/`.

---

## Analysis of Options

### Individual Assessment

#### Form of the cache

1. **Git object store**
   - Pros: Git verifies each object by its hash while it reads it, so the cache needs no manifest
     and no verification code of its own. A fetch of depth one holds the commit and its whole
     tree. The provider reads a clone and the cache through one code path.
   - Cons: the provider depends on the Git command. The cache binds the repository identifier,
     the commit and the digests through the object graph, not through the manifest that the
     decision of Geonexus describes.
2. **File cache with a manifest**
   - Pros: the form matches the text of the decision of Geonexus, and a bounded subset of files
     fits it.
   - Cons: the provider computes and checks digests that Git already holds, and the manifest is a
     new format to version.

#### Use of the network

1. **Explicit fetch**
   - Pros: a check runs offline and in bounded time, so the commit hook stays fast. The network,
     the credentials and their failures belong to one command, which reports a denied access
     where it occurs.
   - Cons: a host runs one more step before its gate; a state never fetched reports
     `unreadable-target-state` until that step runs.
2. **Fetch on demand**
   - Pros: no extra step.
   - Cons: a commit hook depends on the network and on credentials; its duration and its result
     vary with the connection.

#### Authorized bundle

1. **Later decision**
   - Pros: the bundle arrives with its consumer, which fixes what the bundle must hold, such as
     the closure of a glossary import. Every current repository is reachable through Git with the
     token of its host.
   - Cons: a machine without access to a private repository cannot verify its targets.
2. **Git bundle now**
   - Pros: the three sources of the decision exist at the close of the task.
   - Cons: no consumer exists to test it; a `git bundle` holds whole trees, so it cannot be the
     bounded closure that the decision admits.

#### Location of the cache

1. **Cache of the user**
   - Pros: the objects are addressed by their hashes, so every root of the machine shares them
     safely; the vault and its projects fetch each state once.
   - Cons: the cache lies outside every repository, so a cleanup of a clone leaves it in place.
2. **Folder of the root**
   - Pros: the cache disappears with its clone.
   - Cons: each root fetches the same states again, and each root must ignore one more folder.

### Summary: Comparison by Criteria

Each table compares the options of one question.

| Form of the cache | Git object store | File cache with a manifest |
| --- | --- | --- |
| Verification | high (hashes of Git) | medium (digests of its own) |
| Task boundaries | high (one code path) | low (a new format) |

| Use of the network | Explicit fetch | Fetch on demand |
| --- | --- | --- |
| Determinism | high (offline checks) | low (depends on the connection) |
| Usable gates | high (fast hook, one host step) | low (hook on the network) |
| Credential hygiene | high (one command) | medium (every check) |

| Authorized bundle | Later decision | Git bundle now |
| --- | --- | --- |
| Task boundaries | high (arrives with its consumer) | low (no consumer) |

| Location of the cache | Cache of the user | Folder of the root |
| --- | --- | --- |
| Determinism | high (content-addressed) | high |
| Usable gates | high (one fetch per machine) | medium (one fetch per root) |

---

## Conclusions

### Decision

**Proposed option**: a Git provider of the selected states, with four answers:

- the cache as a Git object store;
- the network used by the explicit command `anagraphe states fetch` alone;
- the authorized bundle left to a later decision;
- the cache in the cache folder of the user, replaced by `ANAGRAPHE_CACHE`.

**Justification**: Git already verifies every byte of a commit, so a provider built on Git object
stores satisfies the verification of the decision of Geonexus without a format of its own. The
explicit fetch keeps every check offline and keeps the credentials in one command.

The provider composes three parts.

**Stores of a state**. A state is read from the first store that holds its commit:

- the clone of the entry: the folder of a submodule for a derived entry, or the clone named by the
  machine file for a declared entry;
- the cache: the bare repository of the repository identifier.

Every store holding the commit yields the same bytes, so the order affects the speed alone. The
provider reads the object database, never the working tree of a clone.

**Read**. The provider requires the commit object, resolves the path through the trees of the
commit, and returns the bytes and the mode of the entry:

- a file returns its bytes; a symbolic link returns its target as bytes, with the mode `link`;
- a folder and a gitlink return the modes `directory` and `submodule`;
- a path through a symbolic link of the tree, or outside the root, is `escaping`;
- a commit absent from every store is `absent`, with a detail naming the command that fetches it;
- a store that Git cannot read for lack of permission is `denied`;
- an object that fails the verification of Git is `invalid`.

**Fetch**. The command `anagraphe states fetch` reads the context of the root, and fetches each
state absent from every store into the cache, with the commit and its tree alone:

- the remote of a declared entry is its address in the section `resolution`. The remote of a
  derived entry is the address of its submodule in `.gitmodules`, a relative address being
  resolved against the remote of the root, as Git resolves it;
- the fetch runs with `fetch.fsckObjects`, so Git checks every fetched object. The fetch names the
  address directly and records no remote, so no credential enters the configuration of the cache;
- credentials come from the configuration of Git on the machine, or from the host, such as a
  setting `http.extraHeader` that a workflow builds from its token;
- the command reports each state that it fetches, that the remote holds no longer, or whose
  access is denied.

The context supplies every remote and every commit, from the committed `.gitmodules` and section
`resolution` of the root. An imported record supplies neither, so the provider never fetches an
address that the root does not declare.

### Final Answers

1. Which form does the verified cache take?
   A bare Git repository per repository identifier, which Git verifies by the hashes of its
   objects.
2. When does the provider use the network?
   In the command `anagraphe states fetch` alone; every check reads offline.
3. Does this task implement the authorized bundle?
   No. A later decision fixes the bundle with its first consumer.
4. Where does the cache lie on a machine?
   In `anagraphe/states/` below the cache folder of the user, replaced by `ANAGRAPHE_CACHE`.

---

## Implications

- **Module**: a Git provider joins `anagraphe.resolution`, and the check of the targets uses it
  instead of the empty provider. The commit hook of the vault then verifies its targets into its
  submodules offline.
- **Context**: a derived entry gains the remote of its submodule, read from `.gitmodules`.
- **Command**: `anagraphe states fetch` fills the cache. The gate workflow of a project that cites
  another repository runs it before the gate, with the token that it already holds.
- **Findings**: `unreadable-target-state` keeps its meaning; its detail names the command that
  fetches the state. `invalid-target-state` reports an object that fails the verification of Git.
- **Decision of Geonexus**: its paragraph on the provider describes a cache bound by a manifest.
  An amendment states that a Git object store binds the same items through its object graph, and
  that the manifest applies to a bundle.
- **Conformance**: the cases of `specs/conformance/resolution.yml` stay valid. Tests of the Git
  provider build small repositories with Git, holding a symbolic link, a gitlink and a nested
  tree.
- **Later tasks**: a decision on the authorized bundle, with the task `glossary-import-closure` of
  Onomasia as its first consumer.

---

## See Also

### Related Decisions

- [ADR 0009](0009-record-resolver.md): Completes. ADR 0009 fixes the port of the provider, and this
  record implements it for Git object stores.
- [ADR 0006](0006-logical-targets.md): Reads. The provider serves the states that the targets of
  ADR 0006 select.

### References and Resources

- [Decision of Geonexus on cross-repository resolution][resolution]

[geonexus-todo]: https://github.com/esther-poniatowski/geonexus/blob/main/TODO.md
[resolution]: https://github.com/esther-poniatowski/geonexus/blob/main/docs/_decisions/cross-repository-record-resolution.md
