# ADR 0004: Findings output

**Status**: Proposed. It implements the Anagraphe row of the producer migration of Elenchos.

---

## Problem Statement

The gate Elenchos reads the findings of each domain tool as a SARIF 2.1.0 log in its findings
profile. The gate builds the identity of each finding from four components: the tool, the rule,
the resource and the locus, completed by an optional discriminator. Before this decision, the check
commands of Anagraphe printed each issue as one line, `path:line: [warning: ]kind: detail`. That
line names the file and the kind, but it names no place inside the file apart from its line. A
baseline built from the line therefore depends on the wording of the detail, and on the line once
the line is normalized away.

**Questions to be addressed**:

1. Which rule, resource, locus and discriminator does each issue take?
2. Which component decides the locus of an issue?
3. How does a command write the log while keeping its text report?
4. When does a run declare itself incomplete?

---

## Decision Drivers

- **Correctness**: every log conforms to the profile, and the identity of an issue changes neither
  with its line nor with the wording of its detail.
- **Consistency**: the kinds keep the names of the Geonexus checkers that they replace, so that the
  gate carries a Geonexus baseline to Anagraphe by one rename rule per section.
- **Separation of concerns**: the writer of the log imports no capability, and each capability
  owns its kinds.
- **Usability**: the text report and the exit status stay byte-identical under the log.
- **Robustness**: the rules declared by the driver cannot drift from the kinds that the sources
  report.

---

## Considered Options

The options differ by the component that decides the locus of an issue.

1. **Locus at the creation site**
   Each issue carries its locus and its discriminator, set where the issue is created.
   - `Issue` gains the fields `locus` and `discriminator`, both empty by default.
   - The code creating the issue writes the key, the list entry or the target that it tested.

2. **Locus derived in the writer**
   The writer derives the locus from the kind and the detail of each issue.
   - One parser per kind reads the key or the target out of the detail.
   - `Issue` stays unchanged.

---

## Analysis of Options

### Individual Assessment

#### Locus at the creation site

Pros:

- Correctness: the locus comes from the tested value itself, such as the raw target of a
  reference or the key of a retired field, so it never depends on the wording of a detail.
- Separation of concerns: the writer maps fields, and knows no kind.

Cons:

- Each of the 46 creation sites of an issue states its locus.

#### Locus derived in the writer

Pros:

- The creation sites stay unchanged.

Cons:

- Correctness: rewording a detail changes or breaks the locus, although the profile excludes the
  message from the identity.
- Separation of concerns: the writer must know every kind of both capabilities.

### Summary: Comparison by Criteria

- **Correctness**
  - **Locus at the creation site**: HIGH (tested value)
  - **Locus derived in the writer**: LOW (parsed message)
- **Separation of concerns**
  - **Locus at the creation site**: HIGH (generic writer)
  - **Locus derived in the writer**: LOW (writer coupled to every kind)

---

## Conclusions

### Decision

**Chosen option**: Locus at the creation site

**Justification**: only the code that creates an issue holds the value that it tested, so only that
code can name the locus without reading the message.

**Discarded options**:

- **Locus derived in the writer**: it builds an identity from the message, which the profile
  excludes from the identity.

### Final Answers

1. **Rule, resource, locus and discriminator.** The rule is `<section>/<kind>`, such as
   `references/broken` or `indexes/retired-key`. The resource is `path:<file>`, relative to the
   root, with `%` written `%25` and `#` written `%23`. The locus follows the table below. A list
   keyed by identifiers, such as `groups`, `files`, `external` or `blocked_by`, is located by the
   pointer of the list and a discriminator naming the entry, so that reordering the list keeps each
   identity.

   | Kinds | Locus | Discriminator |
   | --- | --- | --- |
   | every kind of `references` but `unreadable-file` | `link:<target as written>` | — |
   | `unreadable-file`, `unreadable-metadata`, `stale-block`, `ungenerated-index`, `malformed-block`, `index-prose`, `unmigrated-member`, `unplaced-member`, `unsequenced-member` | empty | — |
   | `missing-control-file` | empty | the required file |
   | `retired-key`, `migration-key` | `/<key>` | — |
   | `missing-alias`, `title-mismatch` | `/aliases` | — |
   | `index-location`, `missing-purpose`, `control-file-role`, `index-type` | `/index`, `/purpose`, `/role`, `/index_type` | — |
   | `unarchived-superseded`, `invalid-link` of `superseded_by` | `/superseded_by` | — |
   | `undeclared-value`, `unranked-value` of a member | the pointer of the sort key | — |
   | `unknown-task`, `finished-blocker` | `/blocked_by` | the task |
   | `unknown-file`, `malformed-groups` of `files` | `/files` | the file |
   | `invalid-link`, `invalid-external` of `external` | `/external` | the target |
   | `invalid-context-relation` | `/context_relations` | source, relation and target |
   | the kinds of a group: `malformed-groups`, `mixed-modes`, `nest-cycle`, `ignored-order`, `missing-sequence`, `duplicate-member`, `unknown-filter-key`, `undeclared-value`, `invalid-link` | `/groups` | the group, followed by the offending key, value, file or source of order |

   A `malformed-groups` issue that names no group takes `/groups` without a discriminator. Such an
   issue is found while the groups are parsed, or when an index renders groups that it does not
   declare.
2. **Locus.** The creation site sets the locus and the discriminator. Each capability declares its
   kinds in a catalogue, with a description and a default level:
   `anagraphe.indexes.kinds.KINDS` and `anagraphe.references.service.KINDS`. The writer
   `anagraphe.core.sarif` refuses an issue whose kind its catalogue omits. A test compares each
   catalogue with the kinds that the sources construct.
3. **Output.** The commands `check`, `indexes check` and `refs check` accept `--format sarif`, and
   `--output PATH` with it. The text report keeps its bytes. When the log takes standard output,
   the text report moves to standard error. The driver lists every rule of both sections, whatever
   the command, since the profile lists every rule that the tool can emit. The command
   `indexes write` and the command `move` write files, so they take no log.
4. **Incomplete runs.** A run is complete when every declared section ran to its end and read every
   file. A run declares a failed invocation, with one notification of level `error`, in two cases:

   | Case | `results` |
   | --- | --- |
   | an invalid configuration or target stopped the command, exit status 2 | absent when no section ran; otherwise the results of the sections that ran |
   | a document read by a syntax of keys, or the metadata of an indexed file, cannot be parsed | every result, including `unreadable-file` or `unreadable-metadata` |

---

## Implications

- **Rename map.** The kinds `broken`, `heading-fragment` and `broken-anchor` of Anagraphe keep the
  names of the Geonexus link checker, and `retired-key` keeps the name of the Geonexus frontmatter
  checker. The kind `unlinkable-target` of the Geonexus frontmatter checker becomes the kind
  `unlinkable-target` of the section `references`, since it concerns a pointer and its cited file.
  Its locus is the target as written; the Geonexus checker removes the fragment and the
  percent-encoding, so a suppression carries over only for a link without them.
- **Region.** An issue holds a line only where its defect has one, such as a reference or a
  marker. An issue of a whole file or of a key of the metadata holds no line, so its physical
  location holds no region, as the profile requires of a finding on a whole file. The text report
  still prints such an issue at line 1, so its bytes are unchanged.
- **Unparsed metadata.** A metadata source that cannot be parsed is reported as
  `unreadable-metadata`, in place of the missing fields that would follow from its empty mapping.
  The exclusions and the conventions still read such a file as holding no field.
- **New kinds.** A new kind of issue joins the catalogue of its section, and takes a locus at its
  creation site. Renaming a kind changes the identity of its results, so it requires a rename in
  the gate.
- **Omitted objects.** The log holds no `suppressions`, no `fingerprints` and no `baselineState`,
  which the gate alone writes or which the profile excludes.

---

## See Also

### Related Decisions

- [ADR 0003](0003-pointers-across-moves.md): relates to; it defines the section `references`, whose
  kinds this decision maps.

### References and Resources

- [Elenchos](https://github.com/esther-poniatowski/elenchos): the findings profile and the producer
  migration.
- [SARIF 2.1.0](https://docs.oasis-open.org/sarif/sarif/v2.1.0/errata01/os/sarif-v2.1.0-errata01-os-complete.html):
  the standard that the profile restricts.
