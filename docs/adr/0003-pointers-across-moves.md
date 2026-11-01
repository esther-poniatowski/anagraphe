# ADR 0003: Pointers preserved across moves

**Status**: Accepted on 2026-11-01

---

## Problem Statement

Restructuring a repository moves or renames files and folders, and moves or renames the anchors
and the identifiers cited by other files. Each such change breaks the pointers to the old address.
When Obsidian renames a Markdown note, it rewrites the Markdown links to that note. Obsidian reads
no other file, and it leaves the indexes and the pointers inside files unchanged. As a result,
stale pointers accumulate in YAML records, configuration files, build inputs and indexes, and an
agent repairs them one by one.

A pointer takes one of four forms, and each form raises its own difficulty:

- **a Markdown link** `[text](notes/a.md#^claim)`, written in a note, in a frontmatter, or in a
  Markdown paragraph held by a YAML value;
- **a bare path** `notes/a.md#^claim`, written in a field, a configuration file or a build input;
- **an anchor** `^claim`, cited by the fragment of a link;
- **an identifier** of a namespace, such as a task identifier cited under `blocked_by`.

A string shaped like a path is not always a pointer. On 2026-10-30, the YAML files of the Geonexus
vault held 6,488 strings shaped like paths. Of these, 5,209 resolved to a file from neither base:
the folder of their file and the root of the vault. Among them are DOIs, paths relative to another
repository, and prose holding a slash. A single key may also hold values of several kinds: the key
`source` holds a website name in the icon registry, a Markdown link in the correspondence records,
and a gloss in the vocabulary.

**Questions to be addressed**:

1. How is each pointer to a moved address found, without a declaration of each field of each file?
2. How does a move keep the indexes of the affected folders consistent?
3. How are the anchors and the identifiers moved or renamed?
4. How does a repository exclude files from the checks and the moves, by path and by metadata?
5. How does a repository declare the link formats and the path styles of its pointers, by location,
   file type or other condition?
6. Where do these capabilities live in the package, its configuration and its command line?

---

## Decision Drivers

- **No declaration by file**: a repository declares no field of any file before a move preserves
  its pointers. The researcher rejected such declarations on 2026-10-30: they are cumbersome, they
  miss the links written freely in a Markdown paragraph of a field, and they cover YAML files only.
- **No false rewrite**: a move rewrites only a string that designates a moved address, never a DOI,
  a gloss or a path of another repository.
- **One transaction**: a move applies its rename and every edit of a pointer, or none of them, and
  checks the repository again after applying them.
- **Separation of concerns**: the indexes and the references share their primitives, and neither
  imports the other.
- **Repository boundary**: following [ADR 0001](0001-repository-boundary.md), the core holds no
  path, field, scheme or namespace of a consumer.

---

## Considered Options

The options differ by the criterion that identifies a pointer.

1. **Shape**: a string is a pointer when it is shaped like a path.
2. **Declaration**: a string is a pointer when the repository declares the field holding it, file
   class by file class.
3. **Syntax and resolution**: a Markdown link is a pointer by its syntax, in every text file. A bare
   path is a pointer to a moved address when it resolves to that address. A declaration is kept
   only for two objects that no syntax identifies: the fields whose bare paths are checked when
   they name no file, and the namespaces of identifiers.

---

## Analysis of Options

### Individual Assessment

1. **Shape**
   - Pros:
     - No declaration by file: the repository declares no field.
   - Cons:
     - No false rewrite: the counts of the vault show that thousands of strings shaped like paths
       are not pointers.

2. **Declaration**
   - Pros:
     - No false rewrite: the move reads only the declared fields.
   - Cons:
     - No declaration by file: each class of fields of each kind of file is declared.
     - A link written in a Markdown paragraph of a field is missed when its field is undeclared.
     - Only the YAML records are covered, not the other text files.

3. **Syntax and resolution**
   - Pros:
     - No declaration by file: the Markdown links are found by their syntax in every text file,
       and the bare paths by their resolution.
     - No false rewrite: a move knows its old addresses, so a bare path is rewritten only when it
       resolves to one of them. A DOI or a gloss resolves to no moved file.
   - Cons:
     - A bare path that names no file is ambiguous outside a move: it may be broken, or not be a
       path. Such a path is therefore checked only in a declared field.
     - An identifier has no syntax of its own, so each namespace is declared once.

### Summary: Comparison by Criteria

- **No declaration by file**
  - **Shape**: HIGH (no field declared)
  - **Declaration**: LOW (every field of every file class)
  - **Syntax and resolution**: HIGH (only the namespaces, and the fields checked by choice)
- **No false rewrite**
  - **Shape**: LOW (thousands of strings that are not pointers)
  - **Declaration**: HIGH (declared fields only)
  - **Syntax and resolution**: HIGH (resolution to a moved address)

---

## Conclusions

### Decision

**Chosen option**: Syntax and resolution.

**Justification**: A move knows the old address of every moved file, so the resolution of a string
to that address identifies a pointer without any declaration. The syntax of a Markdown link
identifies it in every text file. Declarations remain for two objects left undecided by both
criteria: a bare path naming no file, and an identifier. On 2026-10-30, a planned move of the
folder `exchanges` of the vault found 88 pointers in 54 files. Every sampled pointer was genuine,
once a bare word, such as the name of the folder in a sentence, was no longer read as a path.

#### Addresses and pointers

An address designates a file, or a place inside a file:

| Address | Form | Example |
| --- | --- | --- |
| file | a repository-relative path | `notes/a.md` |
| anchor | a file and a block anchor | `notes/a.md#^claim` |
| identifier | a namespace and a name | the task `brief-draft` |

A pointer is one occurrence of an address in one file. The pointer records its line and its
column, so that a check reports it there, and a rewrite replaces exactly the characters spelling
it. The pointer also records its base, the starting folder of its path: the folder of its file, or
the root.

| Pointer | Found by | Checked when broken | Rewritten by a move |
| --- | --- | --- | --- |
| a candidate of a strict syntax: a Markdown link, a wikilink, a LaTeX input, a declared pattern or key | its syntax | yes | yes |
| a candidate of a syntax that is not strict, such as a backticked path | its syntax, when it names a file | where a convention declares it strict | yes |
| bare path | a token holding a slash, or a file name with a suffix, that resolves to a moved address | no | yes |
| anchor fragment | the fragment of a link or a bare path | yes | yes, when its anchor moves |
| identifier | the syntax declared by its namespace | yes, within its namespace | yes, when it is renamed |

A rewritten path keeps its base, and its percent-encoding when its link was encoded. A pointer held
by a moved file and written relative to that file is recomputed from the new folder of the file.

#### Syntaxes and metadata sources

The syntaxes and the metadata sources are declared, so that no file type is assumed. A syntax
finds the candidate pointers of one notation, in the files named by its condition. Four syntaxes
are built in: `markdown`, `wikilink`, `code` for a path written alone in a code span, and `latex`
for the targets of the LaTeX commands naming files. A repository redefines a built-in syntax, or
declares a further one by a regular expression or by the keys of a YAML, JSON or TOML document. Each
syntax states the suffixes that a target may omit, and whether a target naming no file is reported.
The syntax `code` reports no such target by default. On 2026-10-30, the vault held 10,818
backticked paths: 5,296 named a file, and the 5,522 others mixed stale paths with examples.

A metadata source names the place of the fields of a file: its frontmatter, the mappings of a
YAML, JSON or TOML document at declared key paths, or no source. The sources are declared by rules
on the path and the type of a file. Built-in rules come first: they read the frontmatter of a note,
and the top level of a YAML document overridden by its block `metadata`. The filters of the exclusions and of the
conventions test the fields read from these sources. A source also marks the metadata region of a
file, so a pointer belongs to the `metadata` or to the `content` of its file. These two regions
replace the layers of a fixed file type.

#### Conventions

A convention admits a set of syntaxes, a set of path styles, and the syntaxes that are strict. The
path styles are the following:

- `relative`, from the folder of the holding file;
- `root`, from the repository root, and `absolute`, from the root after a leading slash;
- `shortest`, the shortest end of the path naming one file, as Obsidian writes wikilinks;
- `{base: folder}`, from a declared folder, such as the root of a project inside a vault.

The repository declares a list of rules under `references.conventions`. Each rule holds a condition
on the path, the type, the metadata, the region or the syntax of a pointer, and sets a format, a
style, a strictness, or several of them. The rules cascade after built-in rules: each matching rule overrides only the keys set by
that rule. A narrow rule can therefore change the format of one folder and keep its path style. The built-in
rules admit every syntax, the style `relative` in the content, the style `root` in the metadata,
and both styles for a backticked path, as the vault writes 4,969 of its 5,296 resolving backticked
paths from the root. A check reports three kinds of departure. A link written in a format left out is a
`link-format`. A path naming a file only under a style left out breaks the `convention`. An end of
a path naming several files is an `ambiguous-link`. A move respells each pointer in its own syntax and style, so it never converts a
link.

The researcher asked on 2026-10-30 for conventions customizable by location, file type or other
condition. The built-in rules admit both formats, because a format left undeclared is not enforced:
a vault written in wikilinks then raises no issue before it declares a format. The built-in path
styles keep the conventions enforced by the vault checker.

#### Moves and the indexes

The command `anagraphe move OLD NEW` moves one file or one folder in three steps:

1. **plan** the rename, the rewrites of every pointer to a moved address, and the edits of the
   indexes listed below;
2. **apply** the edits and the rename as one transaction, with `git mv` for a tracked path, and
   restore every edited file when the rename fails;
3. **settle** the result: write the generated regions of the affected indexes, check the moved
   and edited files, and report each remaining occurrence of an old path, such as one held by an
   excluded file.

An affected index already holding a blocking issue keeps its region and is reported. As a result,
an unrelated issue of an index never blocks a move.

The option `--dry-run` prints the plan and changes no file. A move edits the indexes in four ways:

- the key `index` of each moved member names the index of its new folder;
- an explicit list of a group, `members` or `sequence`, drops a member moved out of its folder;
- a build manifest under `indexes.sequences` follows a renamed member, and drops a member moved out;
- the generated regions of the old and the new parent indexes are written again.

The moves belong to the composition module `anagraphe.refactor`. This module calls both
capabilities, so that neither capability imports the other.

#### Anchors and identifiers

The command `anagraphe move-anchor FILE#^NAME TARGET[#^NAME]` rewrites every pointer to an anchor
that moves to another file or takes another name. When the target is another file, the command also
moves the anchored block. A namespace of identifiers declares, once for the repository, the syntax
of a definition and the syntax of a citation. For example, a task is defined by `🆔 name` on a
checklist line, and is cited under `blocked_by` and after `⛔`. The command `anagraphe rename-id
NAMESPACE OLD NEW` rewrites the definition and every citation. A check reports a citation of an
undefined identifier, and an identifier defined twice.

#### Exclusions

An exclusion removes a file from the files that hold pointers: an excluded file is neither checked
nor rewritten. The file stays a valid target, so a link to an archived note resolves, and follows the
note when it moves. A move reports each old path left in an excluded file. An exclusion selects its
files in two ways:

- by **path**, in the syntax of `.gitignore`, read by the library `pathspec`. The syntax covers
  folders, files and patterns, and an exception opens on `!`, as in `!utils/macros/_index.md`;
- by **metadata**, through filters of the form of the `where` of a group. A file is excluded when its
  metadata, read from its declared source, matches one filter. For example, the filters `{status: archived}`, `{role: audit}`
  and `{role: decision}` exclude archived notes, audits and decision records.

Hidden files and folders are excluded by default, and an exception can admit one of them. The
shared `exclude` applies to every capability, and the patterns of a section follow the shared ones,
so that an exception of a section prevails. On request, under `gitignore: true`, the patterns of the
root `.gitignore` apply first. The researcher chose on 2026-10-30 not to read `.gitignore` by
default.

#### Structure of the package

The package holds three layers. Each layer depends only on the layers listed before it:

| Layer | Modules | Responsibility |
| --- | --- | --- |
| core | `anagraphe.core` | issues and reports, paths and exclusions, metadata and filters, Markdown links, configuration primitives, file access, Git state |
| capabilities | `anagraphe.indexes`, `anagraphe.references` | generating the indexes, and finding, checking and rewriting the pointers |
| composition | `anagraphe.refactor`, `anagraphe.configuration`, `anagraphe.cli` | the moves and the renames, the sections of `anagraphe.yml`, and the command line |

The configuration `anagraphe.yml` takes the layout of `schema_version: 2`, with a shared `exclude`
and one section per capability, `indexes` and `references`. A section left out disables its
capability. The command line holds `anagraphe indexes check|write`, `anagraphe refs check`, the
moves and renames, and `anagraphe check`. The last command runs the check of every declared
section.

#### Port of the vault checker

The check of the Markdown links ports the vault checker `utils/scripts/check_links.py`, with its five
kinds `broken`, `convention`, `broken-anchor`, `heading-fragment` and `foreign-scheme`. On
2026-10-30, within the scope of the vault checker, the port and the vault checker reported the same
137 issues, apart from the departures below. The port read the files of the vault checker, except
six hidden files of tool state. Each departure corrects a defect of the vault checker or extends
its scope:

1. a link inside a code span or a math span is not read. A fenced block closes only on a fence of its
   own marker, at least as long as its opening fence, and the delimiters `$$` of display math pair
   in sequence through the text;
2. a path naming a file outside the repository is reported as `outside-repository`;
3. a bare path in a declared field is read as written, without percent-decoding;
4. a target carrying a URL scheme, in a declared field, is checked as a scheme;
5. a block anchor opening the first line of a file is found;
6. an empty frontmatter is recognized;
7. hidden files and folders are not read;
8. when a declared file cannot be parsed, it is reported as `unreadable-file`.

### Final Answers

1. A candidate is found by a declared syntax: a link, a LaTeX input, a backticked path, a pattern
   or a key. A candidate naming a file is a pointer, and one naming no file is reported only where
   its syntax is strict. During a move, a bare path is a pointer when it resolves to a moved address.
2. A move updates the key `index` of each moved member, the explicit lists and the build manifests
   of the affected folders, in the same transaction as the rename. The move then writes the
   generated regions of the old and the new parent indexes.
3. An anchor is moved or renamed by rewriting every fragment citing it. An identifier is renamed
   within its namespace. The namespace declares the syntax of a definition and of a citation.
4. An exclusion selects files by `.gitignore` patterns and by metadata filters. An excluded file
   holds no checked or rewritten pointer, and stays a valid target.
5. A list of cascading rules sets the admitted syntaxes, path styles and strictness, each rule
   applying by path pattern, file type, metadata filter, region or syntax. The metadata comes from
   declared sources.
6. The capabilities form `anagraphe.indexes` and `anagraphe.references` over the core
   `anagraphe.core`, and the moves form the composition module `anagraphe.refactor`.

---

## Implications

- **ADR 0001**: once accepted, this record amends two points of ADR 0001. The scope of Anagraphe
  covers the pointers between files beside the indexes. The command line holds one group of
  commands per capability, so the command `anagraphe write` of ADR 0001 becomes
  `anagraphe indexes write`.
- **Configuration**: the exclusions take the keys `paths` and `where` in place of `directories`,
  `files` and `basenames`. The rules of `references.conventions` replace the bases
  `markdown.body`, `markdown.frontmatter` and `records[].base`. The registry
  `references.syntaxes` replaces `references.markdown` and `references.records`. The top-level key
  `metadata` declares the metadata sources.
- **LaTeX**: the syntax `latex` resolves a target from the folder of its file. LaTeX also resolves
  images through the folders of `\graphicspath` and from the folder of the main document. On
  2026-10-30, these resolutions accounted for the 35 targets of the vault reported as broken.
- **Dependencies**: the core depends on the library `pathspec`.
- **Consumers**: each consumer moves its `anagraphe.yml` to `schema_version: 2`, with its index keys
  under `indexes`, and replaces the command `anagraphe write` by `anagraphe indexes write`.
- **Vault**: when the vault adopts Anagraphe, its checker `check_links.py` retires, and its schemes
  move under `references.schemes`.
- **Phases**: the capabilities are delivered in this order:
  1. the check of the Markdown links and of the declared fields, delivered on 2026-10-30;
  2. the moves of files and folders, with the edits of the indexes, delivered on 2026-10-30;
  3. the exclusions by `.gitignore` patterns and by metadata, the conventions, the registry of
     syntaxes and the metadata sources, delivered on 2026-10-30;
  4. the resolution of LaTeX targets through `\graphicspath` and from the main document;
  5. the moves and renames of anchors;
  6. the namespaces of identifiers;
  7. the repair of the pointers broken by the renames that Git records;
  8. the reading of the entry fields of the indexes through the declared metadata sources,
     delivered on 2026-10-31.

---

## See Also

### Related Decisions

- [ADR 0001](0001-repository-boundary.md): Amends. The scope and the command line of Anagraphe.
- [ADR 0002](0002-collection-owned-order.md): Relates to. The explicit lists of a group and the build
  manifests are edited by a move.

### References and Resources

- [Reference specification](../guide/references.md)
