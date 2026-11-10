# ADR 0005: Text bindings

**Status**: Accepted on 2026-11-04, proposed on 2026-11-03. The record implements the bindings assigned to Anagraphe by the
[decision on designation and typography](https://github.com/esther-poniatowski/geonexus/blob/main/docs/_decisions/designation-and-typography.md)
of Geonexus.

---

## Problem Statement

A tool checking a text reads the resources bound to it: Onomasia reads its glossary, its notation
and its audiences, and Hermeneia reads its prose profile. The decision of Geonexus assigns the
resolution of these bindings to Anagraphe, along the directory chain, and lets a record schema mark
its binding fields by the keyword `x-binds`. That decision leaves five points to Anagraphe.

**Questions to be addressed**:

1. How is a role named, and where does a repository name its key?
2. Which declarations bind a file, and in which order?
3. How does a record declare its binding?
4. Which tool reports a text bound to no value, given that each tool declares its own merge rule?
5. In which form do the tools read the bindings?

---

## Decision Drivers

- **Boundary**: following [ADR 0001](0001-repository-boundary.md), Anagraphe names no record type
  and no vocabulary of another tool.
- **Economy**: one declaration binds a whole folder, and a text overrides it where it differs.
- **Unambiguous reading**: a key of a file binds only where it is meant to, and two tools never
  read one role.
- **One report**: a text bound to no value is reported once, in the gate.

---

## Considered Options

**Names of roles.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| Bare names, such as `glossary`, also serving as keys | Shorter | Two tools reading different resources under one name would clash |
| **`<tool>.<name>`, each mapped to a key by the repository** | Each tool owns its roles, and each repository keeps its keys | Taken |

**Own declaration of a file.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| The key of the role in the metadata of any file | One rule for every file | A configuration file whose key `glossary` holds a mapping, as `config/checks.yaml` of Geonexus does, is read as a binding |
| **The frontmatter of a text, and the fields marked by `x-binds` in a registered record** | A key binds only in a frontmatter or in a marked field | Taken. Any other file takes the binding of its directory |

**Place of `x-binds`.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| At the root of the schema, mapping each role to a field pointer | All the bindings of a type in one place | The pointer drifts when the field moves |
| **On the property that binds** | The field and its role stay together, and the mark is read through `allOf` and `$ref` | Taken |

**Meaning of an empty list.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| An empty list unbinds the texts below it | A folder can opt out of an inherited binding | Under `override` the text is unbound and under `union` it is not, so the check of a required text would depend on the merge rule of the reading tool |
| The merge rule restated in `anagraphe.yml` | The check follows the rule of the tool | The repository restates a rule owned by the tool, and the two may drift apart |
| **An empty list reported as invalid** | Both rules bind a text exactly when its chain holds a valid declaration | Taken |

**The root of the chain.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| A default of each role in `anagraphe.yml` | A repository binds every text without writing its root index | A second place of declaration, outside the documents read by every tool |
| **The index of the root, the last link of the chain** | Every declaration stays in a document of the repository | Taken |

**Form of the contract.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| The guide only | No version to maintain | A reading tool cannot pin the readings relied on |
| **The contract `anagraphe:bindings@1`, with conformance cases** | Each reading tool pins one version, and the JSON output names it | Taken |

**Report of an unbound text.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| Each reading tool reports it | No requirement in `anagraphe.yml` | Each tool repeats the report and its scope |
| **The check of Anagraphe, for the files that a condition `required` selects** | One report in the gate | Taken. The resolver still returns an empty binding to the reading tool |

---

## Decision

The section `bindings` of `anagraphe.yml` declares the file name of a directory index, each role
`<tool>.<name>` with its key and its optional condition `required`, and the schema registry of
the records. A tool declares its role and its merge rule, `override` by default or `union`, when it
resolves a binding. The resolution reads the own declaration of the file, then the index of each
enclosing directory up to the root. A text declares in its frontmatter, and a record of a contract
held by the registry declares in the fields that its schema marks by `x-binds`. The check reports a
required file bound to no value, an invalid declaration, an unreadable source, an invalid mark, an
unresolved reference and an unreadable schema. A declaration names at least one value, so an empty
list is invalid, and the index of the root is the last link of the chain. The contract
`anagraphe:bindings@1` fixes these readings, its [specification](../specification/bindings-contract.md)
states them, and the [bindings guide](../guide/bindings.md) states the section and the commands.

---

## Consequences

- Onomasia, Hermeneia and every other reading tool resolve their roles through
  `anagraphe.bindings`, or through `anagraphe bindings show --format json` for a tool in another language.
- A repository migrating to bindings declares its roles, then moves its bindings into the
  frontmatter of its indexes and texts. The bindings of the `project.yml` of each project of
  Geonexus move the same way.
- Anagraphe reads the schema registry of Kleisis without importing Kleisis, in its format version 1
  or 2, and rejects any other version.
