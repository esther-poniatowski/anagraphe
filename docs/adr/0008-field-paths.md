# ADR 0008: Field paths

**Status**: Accepted by the researcher on 2026-11-15. [ADR 0006](0006-logical-targets.md) leaves
the syntax of a field path, its wildcards and its conversion to a JSON Pointer to a later decision,
and this record takes that decision.

---

## Problem Statement

A field path is the text naming one node of a structured document from its root, such as
`subject.foils[1].symbol`. ADR 0006 restricts the value of `x-identifier` to a dotted path of
property names, and leaves every other field path to this decision. Its section "Identifier
declarations" states that the wildcards and the conversion to a JSON Pointer belong to the
field-path syntax. Its section "Schema resource" states that a definition added to the resource
`addressing.v1`, such as the syntax of a field path, keeps its `$id`.

Four facts, surveyed on 2026-11-15, make the decision necessary:

- Ekphrasis writes field paths in its issues, its rules, its custom checkers and its outline, by a
  grammar stated in its [documentation of field paths][ekphrasis-field-paths]. Its parser admits a
  bare key holding a space or a quote, so one path takes several spellings.
- The findings profile of Elenchos converts a field path to a JSON Pointer segment by segment, and
  states that this conversion moves to the addressing specification of Anagraphe once published
  ([locus of a finding][elenchos-locus]).
- Four tools print field paths in forms read differently by the grammar of Ekphrasis:
  - the method `FieldPath.__str__` of Ekthesis quotes a key only when it holds `.` or `[`, and
    escapes no quote inside it;
  - Gnomon prints keys joined by dots without quoting, writes `[]` for every item of a sequence,
    and its YAML report writes the root as `"/"` under a key `field_path` that holds a pointer;
  - the record checks of the vault write a position as a key, as in `identity.communities.0`;
  - the function `field_pointer` of Kleisis reads only keys of `[A-Za-z_]+` and positions `[n]`.
- The TypeScript read side moves out of Ekphrasis into the package `@anagraphe/read`, and the
  decision on tool roles forbids implementing its logic twice.

**Premises.** The following points are fixed, and this record does not reopen them:

- A field path converts to a JSON Pointer segment by segment, by the rule of the findings profile
  of Elenchos: a position contributes its decimal, and a key contributes itself with `~` escaped
  before `/`.
- A pattern applied to a document yields the field paths of the nodes that it names, in document
  order, as the rules of Ekphrasis expand `subject.foils[*].symbol` into `subject.foils[0].symbol`
  and `subject.foils[1].symbol`.

**Questions to be addressed**:

1. Which syntax writes a field path, and a field-path pattern?
2. Does the parser admit several spellings of one path, and is the printed form canonical?
3. Does `x-identifier` admit every field path, or only the dotted paths of property names?
4. How does a JSON Pointer convert to a field path, when a token names no node of the document?

---

## Decision Drivers

- **One reading in two languages**: one pattern of the resource states the grammar, and the Python
  and the TypeScript read sides derive their checks from it, print the same text for each path,
  and pass the same conformance cases.
- **One spelling**: each path has one printed form, so that two tools printing one node compare
  their texts by equality.
- **Exact conversion**: a conversion yields the field path of the node named by the pointer, or
  fails; it never guesses whether a token is a key or a position. The conversion still locates
  each finding of the tools, a missing required key included.
- **Readable text**: an author writes the path or the pattern of a rule by hand, wildcards
  included, and a reader finds the node of an issue from its printed path.

---

## Considered Options

### Question 1: the syntax

- **Ekphrasis grammar**: a key follows a dot, except at the start; a position stands between
  brackets; a key stands between brackets as a JSON string when it cannot be written bare. A pattern
  adds `[*]` for every item and `*` for every key.
- **Normalized paths of RFC 9535**: the form `$['subject']['foils'][1]['symbol']`. Each name
  stands in single quotes between brackets, and the root is written `$`. Wildcards belong to the
  full JSONPath query language of the same RFC.
- **JSON Pointer only**: every path is written `/subject/foils/1/symbol`, as RFC 6901 defines it.

### Question 2: strictness

- **Lenient**: the parser of Ekphrasis today, whose bare key excludes only `.`, `[` and `]`.
- **Strict and canonical**: a bare key excludes every character that makes a printed path ambiguous
  or unreadable, and every other key is a JSON string in brackets. The parser accepts a quoted key
  that a bare key could hold, and the printer writes bare each key that can be written bare.

### Question 3: the value of `x-identifier`

- **Restricted**: the definition `property-path`, a dotted path of property names, as ADR 0006
  publishes it.
- **Full**: every field path, positions and quoted keys included.

### Question 4: a token naming no node

The conversion from a JSON Pointer reads the document, since a token written in digits names a key
of a mapping or a position of a sequence. A token may name no node of the document.

- **Fail**: the conversion fails at the first token naming no node.
- **Continue as a key**: every token from the first one naming no node is read as a key.
- **Key below a mapping**: a token below a mapping is a key, present or absent; a token descending
  from no node, or from a scalar, fails.

---

## Analysis of Options

### Summary: Comparison by Criteria

- **Question 1**
  - **One spelling**: Ekphrasis grammar HIGH once strict; RFC 9535 HIGH; JSON Pointer HIGH.
  - **Readable text**: Ekphrasis grammar HIGH (the form written in the rules of Ekphrasis today,
    with two wildcards); RFC 9535 LOW (four characters around each name, and no wildcard in a
    normalized path, since the wildcards belong to the far larger query language); JSON Pointer LOW
    (no wildcard, and a position looks like a key written in digits).
  - **Exact conversion**: Ekphrasis grammar HIGH (a position is bracketed); RFC 9535 HIGH; JSON
    Pointer LOW (a pointer alone does not tell a position from a key).
- **Question 2**
  - **One spelling**: lenient LOW (`a b` and `["a b"]` name one key); strict HIGH.
  - **One reading in two languages**: lenient LOW (each language decides alone on the characters
    of a bare key); strict HIGH (one pattern of the resource decides).
- **Question 3**
  - **Exact conversion**: both HIGH.
  - **One reading in two languages**: restricted HIGH (the published definition stays, and every
    property path is a field path of the same meaning); full LOW (a position inside the path of an
    identifier names no field of a schema, so the check of a declaration would reject it again).
- **Question 4**
  - **Exact conversion**: fail MEDIUM (exact, but the locus of a missing required key converts to
    no path, such as `/identity/id` of the finding `missing-identifier` for a record whose block
    `identity` holds no `id`); continue as a key LOW (the token `0` below an absent key may name a
    position); key below a mapping HIGH (a mapping makes each token below it a key, and nothing
    below an absent node is converted).

The normalized paths of RFC 9535 would win if every field path were written by a tool, since the
form is standardized and canonical. Authors write the paths of rules by hand, and patterns need
wildcards, so the RFC form loses on both counts. On question 4, the researcher offered two options:
fail, or continue as a key. Failing loses the locus of every missing required key, whereas
continuing as a key guesses the kind of every later token. The third option converts exactly, as
failing does, and still converts a token naming an absent key, since its parent mapping fixes its
kind.

---

## Conclusions

### Decision

**Chosen option**: the grammar of Ekphrasis, strict and canonical, published as the definitions
`field-path` and `field-path-pattern` of the resource `addressing.v1`; `x-identifier` keeps the
definition `property-path`; the conversions run on segments, and a token below a mapping is a key.

**Justification**: The grammar of Ekphrasis is the readable form already written by hand, and its
brackets tell a position from a key without the document. A strict grammar gives each path one
printed form, decided by one pattern that both read sides compile. A conversion that types a token
by its parent node stays exact, and still locates a missing required key.

#### Grammar

A key follows a dot, except at the start; a position stands between brackets; a key that a bare
key cannot hold stands between brackets as a JSON string; the empty text names the root. A path
may open on a position, as `[0].name`. A bare key excludes the characters that make a printed path
ambiguous or invisible: `.`, `[`, `]`, `"`, `'`, `*`, the controls and the characters of the
Unicode property White_Space. A position holds at most 15 digits, so that it stays exact in a
double of JavaScript. The [field-path specification](../specification/field-paths.md) states the
grammar, the canonical form, the conversions and the expansion, and is their single source.

#### Parsing and printing

The parser accepts a quoted key that a bare key could hold, such as `["abc"]`, whereas the printer
writes bare each key that a bare key can hold. Therefore, printing a parsed text yields its
canonical form, and parsing a printed path yields its segments. A refused text fails at its first
defect from the left, with a reason and an offset.

#### Identifier declarations

`x-identifier` keeps the definition `property-path`, and every property path is a field path naming
the same field.

#### Conversion from a JSON Pointer

A token is a position exactly when its parent node is a sequence, and it must then be a canonical
decimal naming an item. A token below a mapping is a key, present or absent, and a token below an
absent key or a scalar fails.

### Final Answers

1. A field path follows the grammar of Ekphrasis, and a pattern adds `[*]` and `*`; the resource
   `addressing.v1` publishes both as the definitions `field-path` and `field-path-pattern`.
2. The parser accepts one grammar, with a quoted key that a bare key could hold, and the printer
   writes one canonical form.
3. `x-identifier` admits the dotted paths of property names only, each a field path of the same
   meaning.
4. A pointer converts to a field path within its document: a token below a sequence is a position
   within range, a token below a mapping is a key, present or absent, and a token below an absent
   key or a scalar fails.

---

## Implications

- **Package**: the Python module `anagraphe.targets.field_paths` and the TypeScript module
  `field-path` of `@anagraphe/read` implement the readings, and both derive their checks from the
  patterns of the resource.
- **Versioning**: the definitions extend `addressing.v1` under its `$id`, as ADR 0006 allows.
  Therefore, a read side declaring that `$id` may predate the field paths, and the comparison of
  the declared versions of two read sides cannot tell them apart. A consumer relying on field paths
  pins a release of the package that implements them.
- **Order of keys**: a JavaScript object enumerates its keys that read as array indices first, so
  the TypeScript read side expands `*` over such keys in ascending order rather than in document
  order. The conformance cases therefore expand `*` over no such key.
- **Elenchos**: the findings profile cites the field-path specification for the conversion, and
  drops its statement that a printed form need not quote every key holding `.`, `[` or `"`.
- **Ekphrasis**: Ekphrasis replaces its parser and its printer by those of `@anagraphe/read`, and
  narrows its reading of `x-identifier` to the definition `property-path`.
- **Other tools**: each tool migrates its printed form under a task of its own:
  - Ekthesis quotes with the escapes of JSON every key that cannot be written bare;
  - Gnomon quotes its keys, writes `[*]` in place of `[]`, and writes the root of its report as an
    empty pointer under a key that names a pointer;
  - the record checks of the vault write a position between brackets;
  - Kleisis reads every field path through the grammar, quoted keys included.

---

## See Also

### Related Decisions

- [ADR 0004](0004-findings-output.md): Relates to. The locus of a finding is a JSON Pointer, into
  which a field path converts.
- [ADR 0006](0006-logical-targets.md): Completes. The record fixes the field-path syntax that ADR
  0006 defers, and keeps its definition of `x-identifier`.

### References and Resources

- [RFC 6901, JavaScript Object Notation (JSON) Pointer](https://www.rfc-editor.org/rfc/rfc6901)
- [RFC 9535, JSONPath: Query Expressions for JSON, section 2.7 on normalized paths](https://www.rfc-editor.org/rfc/rfc9535#section-2.7)
- [RFC 8259, The JavaScript Object Notation (JSON) Data Interchange Format, section 7 on strings](https://www.rfc-editor.org/rfc/rfc8259#section-7)

[ekphrasis-field-paths]: https://github.com/esther-poniatowski/ekphrasis/blob/main/docs/features/field-paths.md
[elenchos-locus]: https://github.com/esther-poniatowski/elenchos/blob/main/docs/profile.md
