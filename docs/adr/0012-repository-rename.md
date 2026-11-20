# ADR 0012: Repository rename

**Status**: Proposed on 2026-11-20. The record implements the design of renames that the researcher
ratified on 2026-11-20, recorded in the decision log of the [handoff of Geonexus on tool
boundaries][handoff]: Anagraphe owns the identity of a renamed repository and every pointer to it,
and Architekta calls Anagraphe through its command line. The details below are decisions of the
implementation, and the researcher has not reviewed them yet.

---

## Problem Statement

The [decision of Geonexus on tool roles][tool-roles-renames] states that a retired identifier is
never reused, and that a resolver follows a declared rename with a warning. The decision also states
that "citers are rewritten in each repository checked out under the composing repository, one commit
per repository; citers elsewhere keep the warning". The researcher stated the ratified design as the
command `anagraphe repository rename OLD NEW`, with four requirements:

1. the renamed repository records the rename: `OLD` joins `repository.retired` of its
   `anagraphe.yml`, created when absent, and an override `repository.id` equal to `OLD` becomes
   `NEW`;
2. the citers of `OLD` are rewritten in each repository checked out under the composing repository:
   every logical target naming `OLD`, and every entry of the resolution context keyed by `OLD`;
3. the command prints its plan before acting, as `anagraphe move` does. Under the option
   `--format json`, the plan is machine-readable, so that Architekta shows it in its own dry run and
   commits once per repository. Anagraphe commits nothing;
4. the command writes no file outside the repositories that the resolution context knows, and
   changes no text other than the edited values.

The [logical targets specification](../specification/logical-targets.md) and the [record registry
specification](../specification/record-registry.md) name a repository by its identifier in six
places:

- the override `repository.id` and the list `repository.retired` of `anagraphe.yml`;
- the component `repository` of a logical target;
- the keys of the mapping `resolution.repositories`, each selecting the state of a declared
  repository;
- the keys of the machine file of the local clones;
- the key `repository` of the record registry, compared by a resolver with the identity of the state
  holding the registry;
- the retired manifest `repository.yml`, reported by the check until the file is deleted.

**Questions to be addressed**:

1. Where does the command run, and how does it name the renamed repository?
2. Which of these values does a rename edit, and which does it report?
3. How does the command edit the files?
4. What does the command print, and which statuses does it return?

---

## Decision Drivers

- **Separation of concerns**: Anagraphe edits the values defined by its specifications, and only
  those. The folder, the remote, the submodules and the commits stay with Architekta and the
  researcher.
- **Decoupling**: Architekta reads the plan without importing a module of Anagraphe, and the plan
  depends on no stage of Architekta, such as whether the remote is renamed yet.
- **Robustness**: a rename writes every file or none. When a value cannot change in place, the
  identity and the context stay consistent, and every value left unchanged is reported.

---

## Considered Options

### Place of the command

1. **At the root, naming the renamed folder**: the root of the command is the composing repository,
   and the option `--repository PATH` names the folder of the renamed repository, the root itself
   by default. The scope is the root and each submodule of its index checked out in its folder.
2. **At the root, finding the renamed repository by `OLD`**: the root is the composing repository,
   and the command takes as renamed repository the member of the scope whose identity is `OLD`.
3. **At the renamed repository, naming the composing root**: the root of the command is the renamed
   repository, and an option names the composing repository, whose submodules form the scope.

### Editing of the files

1. **Located edits**: each edit replaces or inserts the characters of one value, located by the
   marks of the YAML parser, through the module `anagraphe.core.structured`. The commands
   `anagraphe move` and `anagraphe records migrate` edit through the same module. Each edited file
   is parsed again and compared with the planned values, as the migration compares each rewritten
   record. The module `anagraphe.core.writes` writes the changed files all at once.
2. **Round-trip serialization**: a YAML library that keeps comments, such as ruamel.yaml, loads each
   file, changes its values, and writes it again.
3. **Plain serialization**: PyYAML loads each file and dumps the changed data.

### Form of the plan

1. **Versioned JSON output**: the plan is printed on standard output, with a key `version` raised
   when a key changes its meaning or disappears. The command line reference documents its shape.
2. **Registered contract**: the plan follows a contract `anagraphe:rename-plan@1`, whose schema is
   published as package data of the read distribution and registered in the schema registry.

---

## Analysis of Options

### Individual Assessment

#### Place of the command

1. **At the root, naming the renamed folder**
   - Pros:
     - Separation of concerns: the root is the repository whose resolution context the command
       reads, as for `anagraphe targets check` and `anagraphe states fetch`.
     - Decoupling: Architekta owns the folder of the renamed project, so it names that folder at
       every stage of its run.
     - Robustness: the renamed repository is named by a path. Therefore, a remote renamed before the
       command does not change which repository is edited.
   - Cons:
     - The option repeats a fact that the identity of the folder often implies.
2. **At the root, finding the renamed repository by `OLD`**
   - Pros:
     - The command takes one option less.
   - Cons:
     - Robustness: once Architekta renames the remote or the folder, the identity of the renamed
       repository is derived as `NEW`, so no member is identified as `OLD`. A member identified as
       `NEW` may then be the renamed repository or a collision, and the command cannot tell them
       apart.
3. **At the renamed repository, naming the composing root**
   - Pros:
     - Robustness: the renamed repository is named by its root, so no identity decides it.
   - Cons:
     - Separation of concerns: the scope is the set of submodules of the composing repository, so
       the command reads a context that is not the context of its root.
     - Decoupling: a repository does not know its composing repository, so the option is required
       for every rename under a composing repository.

#### Editing of the files

1. **Located edits**
   - Pros:
     - Separation of concerns: one module edits YAML in place for the moves, the migration and the
       rename. The rename adds two generic edits to it: an item appended to a list, and an entry
       added to a mapping.
     - Decoupling: the edits need no dependency beyond PyYAML, already required by the command line.
     - Robustness: every other byte is kept. The second parse rejects an edit that reads otherwise
       than planned, such as an edit of the first of two keys written twice.
   - Cons:
     - A TOML document holding a target is not edited, since the module locates YAML nodes only.
2. **Round-trip serialization**
   - Pros:
     - TOML and YAML could be edited by two libraries of the same kind.
   - Cons:
     - Separation of concerns: the moves and the migration keep their located edits, so two editors
       of YAML coexist in the command line.
     - Decoupling: a new dependency of the command line.
     - Robustness: the writer normalizes the indentation, the quoting and the line breaks of a file,
       a change that requirement 4 forbids.
3. **Plain serialization**
   - Pros:
     - Decoupling: no dependency beyond PyYAML.
   - Cons:
     - Separation of concerns: two editors of YAML coexist in the command line, as for the
       round-trip serialization.
     - Robustness: the comments and the order of the keys are lost.

#### Form of the plan

1. **Versioned JSON output**
   - Pros:
     - Decoupling: Architekta reads the output of a command already called through its command line,
       and checks one integer.
     - Separation of concerns: the read distribution stays a reader of repositories, since the plan
       is no file of a repository.
   - Cons:
     - Robustness: no schema validates the plan for Architekta.
2. **Registered contract**
   - Pros:
     - Robustness: a schema validates the plan.
   - Cons:
     - Separation of concerns: a contract registered with Kleisis names the format of a file kept in
       a repository. The plan passes from one process to another, and no repository stores it.
     - Decoupling: the schema would raise the version of the read distribution, although that
       distribution reads no plan.

### Summary: Comparison by Criteria

| Question | Option | Separation of concerns | Decoupling | Robustness |
| --- | --- | --- | --- | --- |
| Place | root, naming the folder | high (root reads its context) | high (Architekta names its folder) | high (path, not identity) |
| Place | root, finding `OLD` | high (root reads its context) | medium (depends on the stage of the remote) | low (collision undetectable) |
| Place | renamed repository, naming the root | low (context of another root) | low (option always required) | high (root, not identity) |
| Editing | located edits | high (one editor of YAML) | high (no new dependency) | high (bytes kept, parse checked) |
| Editing | round-trip serialization | medium (two editors of YAML) | low (new dependency) | low (formatting normalized) |
| Editing | plain serialization | medium (two editors of YAML) | high (no new dependency) | low (comments lost) |
| Plan | versioned JSON output | high (no file of a repository) | high (one integer checked) | medium (no schema) |
| Plan | registered contract | low (contract for a file never stored) | low (read distribution raised) | high (schema) |

---

## Conclusions

### Decision

**Chosen options**: the command runs at the root and names the renamed folder; it edits by located
edits; it prints a versioned JSON output.

**Justification**: The scope of the citers is the set of submodules of the composing repository. The
composing repository is therefore the root, as for every command reading a resolution context. A
path names the renamed repository at every stage of Architekta. Located edits keep every byte
outside the edited values, and reuse the module that the moves and the migration share.

**Discarded options**:

- **At the root, finding the renamed repository by `OLD`**: a remote renamed first makes the
  renamed repository indistinguishable from a collision.
- **At the renamed repository, naming the composing root**: its root is not the repository whose
  context the command reads.
- **Round-trip and plain serialization**: each rewrites text outside the edited values.
- **Registered contract**: the plan is no file of a repository.

### Final Answers

1. **Where does the command run, and how does it name the renamed repository?** The command runs at
   its root, located by Hodegos as for every command. The composing repository is therefore named by
   the option `--root`, or by the current folder. The option `--repository PATH` names the folder of
   the renamed repository. That folder must be the root or a submodule of its index checked out in
   its folder, and defaults to the root. The scope of the rename is the root and each such
   submodule, a narrower set than the repositories known to the context. A nested submodule, a
   declared repository and a clone elsewhere lie outside the scope, so their citers keep `OLD`. Once
   their context selects a state of the renamed repository under `NEW`, the resolver follows `OLD`
   to it with the warning `renamed-repository`.
2. **Which values does a rename edit, and which does it report?**
   The rename edits four of the six places named by the specifications:
   - the override and the former identifiers of the renamed repository;
   - the key `repository` of its record registry, so that the registry names the new identity;
   - the keys of `resolution.repositories` in each member, with their commit and their remote
     unchanged, since the researcher moves a declared commit, and Architekta owns the remote;
   - the logical targets of each member, in the target fields declared by its schema registry.

   The machine file is reported, not edited, since it belongs to one machine and no commit records
   it. The retired manifest is not edited either, since the check already asks for its deletion.
   Every value left unchanged is a warning, whose kinds the [targets guide](../guide/targets.md)
   lists.
3. **How does the command edit the files?** By located edits, each file parsed again and compared
   with its planned values, then written at once with every other changed file. The identity, the
   registry and the context must change together, since a resolver compares the registry and the
   context with the identity. A failed edit of one of them therefore refuses the rename. When the
   edit of a target fails, the target keeps `OLD`. Once `OLD` is retired, the resolver follows it,
   so that case is a warning.
4. **What does the command print, and which statuses does it return?**
   The command prints one line per edit and one line per warning, then a summary. Under the option
   `--format json`, it prints the plan alone. On a terminal, it asks for a confirmation, as
   `anagraphe move` does. The statuses follow the conventions of the command line: `0` for a plan
   applied or printed, `1` for a rename refused or declined, and `2` for an invalid invocation or
   configuration. A warning keeps the status at `0`, as a residue of a move does. The refusals are
   listed in the [targets guide](../guide/targets.md), and the statuses in the
   [CLI reference](../guide/cli-reference.md).

---

## Implications

- **Second run**: after a rename, each configuration of the scope that declared `OLD` declares
  `NEW`. A second run of the same rename is therefore refused when such a configuration exists.
  Otherwise, it plans no edit, and exits with status `0`.
- **Commits**: the plan lists the files of each repository, relative to that repository, so that
  Architekta commits them once per repository. The composing repository then records the new
  commit of each submodule in the same commit as its own citers.
- **Declared commits**: a declared entry keyed `NEW` keeps its commit. When the renamed repository
  declares an override, the identity of that commit is `OLD`. The resolver then reports
  `invalid-target-repository` until the researcher moves the commit to a state recording the
  rename. Without an override, the identity of the state follows the remote of the entry.
- **Architekta**: Architekta calls the command through its command line. The option `--root` names
  the composing repository, and the option `--repository` names the folder of the project, read from
  the current folder of the call. Architekta shows the plan of `--dry-run --format json`, and
  applies it with `--yes --format json`. Architekta then renames the folder, the remote origin and
  the address of the submodule in `.gitmodules`, and commits each repository listed in the plan.

---

## See Also

### Related Decisions

- [ADR 0003](0003-pointers-across-moves.md): Relates to. A move rewrites the pointers by path, and
  a rename the pointers by identifier, through the same edits of `anagraphe.core.structured`.
- [ADR 0006](0006-logical-targets.md): Extends. The rename writes the section `repository` that the
  derivation of the identity reads.
- [ADR 0007](0007-record-registry.md): Relates to. The registry of the renamed repository names its
  new identity.
- [ADR 0009](0009-record-resolver.md): Relates to. A citer outside the scope keeps `OLD`, followed
  by the resolver with the warning `renamed-repository`.

### References and Resources

- [Decision of Geonexus on tool roles: resolution context and renames][tool-roles-renames]
- [Handoff of Geonexus on tool boundaries][handoff]

[tool-roles-renames]: https://github.com/esther-poniatowski/geonexus/blob/main/docs/_decisions/tool-roles.md#resolution-context-and-renames
[handoff]: https://github.com/esther-poniatowski/geonexus/blob/main/_handoff_tool-boundaries.md
