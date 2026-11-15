# Field paths specification

This page fixes the readings of a field path, the text naming one node of a structured document,
so that every read side, in Python and in TypeScript, reads, prints and converts it alike. The
readings rest on two definitions of the resource `addressing.v1`, `field-path` and
`field-path-pattern`. The [conformance cases](https://github.com/esther-poniatowski/anagraphe/blob/main/specs/conformance/field-paths.yml)
fix each reading, and the [decision on field paths](../adr/0008-field-paths.md) records the reason
for each choice.

## Grammar

A field path joins segments that descend from the root of a document. The empty text names the
root. Each segment takes one of three forms:

| Segment | Written | Node |
| --- | --- | --- |
| bare key | the key itself, after a dot unless the segment opens the path | the value of the key in a mapping |
| quoted key | a JSON string between brackets, such as `["a.b"]` | the value of the key in a mapping |
| position | `0`, or a decimal of at most 15 digits without a leading zero, between brackets | the item of a sequence, counted from zero |

A path may therefore open on a bare key, on a quoted key or on a position, as in `statement`,
`["a b"].c` and `[0].name`. A position holds at most 15 digits, so that every position is exact in
a double of JavaScript.

A bare key holds at least one character, and excludes the following characters:

- the dot `.`, the brackets `[` and `]`, the quotes `"` and `'`, and the star `*`;
- the controls, from U+0000 to U+001F and from U+007F to U+009F;
- the characters of the Unicode property White_Space outside the controls: U+0020, U+00A0,
  U+1680, U+2000 to U+200A, U+2028, U+2029, U+202F, U+205F and U+3000.

A bare key may hold any other character, such as `/`, `~`, `\`, a digit or a letter outside ASCII.
A key written in digits after a dot, as in `a.0`, is a key, since a position always stands between
brackets. A quoted key follows the grammar of a string of RFC 8259, section 7: its escapes are
`\"`, `\\`, `\/`, `\b`, `\f`, `\n`, `\r`, `\t` and `\u` followed by four hexadecimal digits, and it
holds no unescaped control from U+0000 to U+001F. The empty key is written `[""]`.

Each of the two wildcards of a field-path pattern stands where a segment stands:

- `[*]` names every item of a sequence;
- `*` names every key of a mapping, after a dot unless it opens the pattern.

A field path holds no wildcard, and a key holding a star is quoted, such as `["*"]`. The
definitions `field-path` and `field-path-pattern` state the grammar of a path and of a pattern as
patterns that admit a text only when they match the whole text. Each read side derives its check
from them, and its parser tests each bare key and each bracket against the pattern of
`field-path`.

## Parsing

A parser reads a text from the left and fails at its first defect, with one of the reasons below
and the offset of the defect. The bracket closing an opening bracket is the first `]` outside a
string: each `"` opens or closes a string, and a `\` inside a string makes the next character part
of it. Therefore, `x[1"]` holds no closing bracket. The offset of a defect of a bracket is the
offset of its opening bracket.

| Reason | Defect |
| --- | --- |
| `empty-key` | a key opens at the end of the text, on a dot or on `[` |
| `invalid-character` | a key opens on a character that a bare key excludes, other than `.`, `[` and `*`, or a segment is followed by a character other than `.` and `[` |
| `wildcard` | a field path holds `*` where a key opens, or `[*]` |
| `unclosed-bracket` | no `]` outside a string closes a bracket |
| `invalid-index` | a bracket opening on a digit or on `-` holds no position, such as `[01]`, `[-1]`, `[-]` or a decimal of 16 digits |
| `invalid-quoted-key` | a bracket opening on `"` holds other than one JSON string |
| `invalid-bracket` | a bracket holds content other than a position, a JSON string or a wildcard of a pattern |

An offset, of a field path or of a JSON Pointer, counts the units of a string of its language: code
points in Python, UTF-16 code units in TypeScript. The two counts agree on every text that holds no
character outside the Basic Multilingual Plane.

## Canonical form

The printer writes each segment of a path as follows:

- a key admitted as a bare key is written bare, after a dot unless it opens the path;
- every other key is written as a JSON string between brackets, with the escapes `\"` and `\\`, the
  escapes `\b`, `\f`, `\n`, `\r` and `\t`, and `\u` followed by four lowercase hexadecimal digits
  for every other control from U+0000 to U+001F and every lone surrogate. Every other character,
  the controls from U+007F to U+009F included, is written as itself;
- a position is written as its decimal between brackets, and a printer refuses a position outside
  the grammar, a negative or non-integer number or one of more than 15 digits;
- a wildcard is written `[*]` or `*`.

Since the parser accepts a quoted key that a bare key can hold, such as `["abc"]`, and an escape
that names a printable character, such as `\/`, one path may be written several ways. Printing the
parsed segments yields the canonical form, and parsing the canonical form yields the segments.

## Property paths

The value of `x-identifier` follows the definition `property-path`: names of properties joined by
dots, each name an ASCII letter or an underscore followed by ASCII letters, digits, underscores
and hyphens.
Every character of such a name is a character of a bare key, so every property path is a field
path, and it names the same field.

## Conversion to a JSON Pointer

A field path converts to a JSON Pointer of RFC 6901 segment by segment:

- the root converts to the empty string;
- each segment contributes `/` followed by its token;
- the token of a position is its decimal;
- the token of a key is the key with each `~` replaced by `~0`, and then each `/` replaced by `~1`.

For example, `relations[2].target` converts to `/relations/2/target`, the key `a/b` to `/a~1b`, the
key `c~1d` to `/c~01d`, and the empty key to `/`. A tool converts the segments, never the printed
text of a path.

## Conversion from a JSON Pointer

A JSON Pointer converts to a field path within its addressed document, since a token
written in digits names either a key or a position. The pointer is checked first, then its tokens
are read from the left, each unescaped by reading `~1` as `/` and then `~0` as `~`:

1. a pointer opening on a character other than `/` fails as `not-a-pointer`, at offset 0;
2. a `~` closing the pointer, or followed by a character other than `0` and `1`, fails as
   `invalid-escape`, at its offset;
3. a token below a sequence is a position: it fails as `invalid-index` unless it is `0` or a decimal
   without a leading zero, and as `index-out-of-range` unless the sequence holds an item at that
   position;
4. a token below a mapping is a key, present in that mapping or absent from it;
5. a token below an absent key, or below a scalar, fails as `no-node`.

The offset of the failure of a token is the offset of the slash opening it. A token below a
mapping converts even when the key is absent, so the locus of a missing required key, such as
`/identity/id` in a record whose block `identity` holds no `id`, converts to `identity.id`. A token
below an absent node fails, since nothing tells whether it names a key or a position.

## Expansion of a pattern

The conversion from a JSON Pointer and the expansion read a document as JSON data, whose keys are
strings: a key of a Python mapping that is no string matches no token, no key and no `*`.

A pattern applied to a document names a list of nodes, each with its field path. The list starts
from the root, and each segment of the pattern replaces each node of the list by the nodes below
it:

- a key names the value of a mapping that holds the key;
- a position names the item of a sequence that holds the position;
- `*` names every value of a mapping, in the order of its keys;
- `[*]` names every item of a sequence, in its order.

A segment applied to a node of another kind, or to a node lacking the key or the position, names
nothing. The expansion yields the field paths of the final list, in document order. A path without a
wildcard therefore yields its canonical form when its node exists, and nothing otherwise; a key
whose value is `null` names a node. A JavaScript object enumerates its keys that read as array
indices first, in ascending order, so `*` follows that order over such keys on the TypeScript read
side.
