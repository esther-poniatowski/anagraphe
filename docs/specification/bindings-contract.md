# Bindings contract

The contract `anagraphe:bindings@1` fixes the values bound to a file for the role of a tool, so that
each reading tool pins one version of these readings. The contract covers four
points: the declarations of a file, the chain along which they are read, the merge rules, and the
JSON written by `anagraphe bindings show --format json`. The [conformance cases](https://github.com/esther-poniatowski/anagraphe/blob/main/specs/conformance/bindings.yml)
fix each reading, and the [bindings guide](../guide/bindings.md) shows the configuration and the
commands.

## Declarations

A file declares a role in one of two places:

- a text declares in its frontmatter, under the key named for the role by the section `bindings`;
- a record of a contract held by the schema registry declares in the fields marked by `x-binds` in
  its schema; when several fields bind one role, the first field holding a valid value, in the order
  of the schema, declares it.

Any other file holds no declaration of its own. A declaration names at least one value: a non-empty string,
or a non-empty list of non-empty strings, each value kept once in its first position. A key holding
null declares no value, and the file takes the binding of the next link. Any other value is reported as `invalid-binding`, and the resolution ignores
it.

## Chain

The chain of a file lists its own declaration, then the declaration of the index of each enclosing
directory, from the directory of the file up to the root. The index of the root is the last link
of the chain. An index does not appear twice in its own chain. A file path is resolved in its
normal form, and an absolute path or a path leaving the repository is rejected.

## Merge rules

The tool reading a role declares its merge rule:

- `override` binds the values of the nearest valid declaration;
- `union` binds the values of every valid declaration, from the root down to the file, each value
  once in its first position.

Both rules bind a file to at least one value exactly when its chain holds a valid declaration, so
the check of a required file depends on no merge rule.

## Marks of a schema

The keyword `x-binds` sits on a property and names a role as `<tool>.<name>`. The key path of the
field is the sequence of property names from the root of the schema. The marks are read through
`properties`, the subschemas of `allOf`, `anyOf` and `oneOf`, and every `$ref`. A mark at the root of
a schema, or under another applicator such as `items`, is reported as `invalid-schema-binding`. A
`$ref` naming no readable node of the repository is reported as `unresolved-schema-reference`.

## JSON output

The command `anagraphe bindings show PATH --format json` writes one object with five keys:

| Key | Content |
| --- | --- |
| `contract` | `anagraphe:bindings@1` |
| `file` | the file, relative to the root, in its normal form |
| `merge` | the merge rule applied to every role |
| `bindings` | for each role, its `values` and its `declarations`, each declaration with its `file`, its `pointer` and its `values` |
| `problems` | the invalid declarations and the unreadable sources met by the resolution, each with its `file`, its `pointer` and its `kind` |

## Versioning

Adding an optional key to the JSON output keeps the version. Every other change starts the next
version: a change of the declarations, of the chain, of a merge rule or of the reading of the marks,
and a key removed or renamed in the output.
