# Record registry specification

The record registry of a repository is read by the same rules on every read side, in Python and in
TypeScript, and an identifier is looked up in it by the rules below. The registry follows the
contract `anagraphe:record-registry@1`, whose schema
`https://github.com/esther-poniatowski/anagraphe/schemas/record-registry.v1.schema.yml` is published
as package data. The [conformance cases](https://github.com/esther-poniatowski/anagraphe/blob/main/specs/conformance/record-registry.yml)
fix the defects of each registry and the findings of the checks that read it. The
[targets guide](../guide/targets.md) shows the commands that write and check the registry.

## Reading

In the configuration file `anagraphe.yml`, the section `records` names the registry under its key
`path`, by default the file `record-registry.yml` at the root. When that file is absent, the read side finds no registry and
reports no defect. A read side reads the file as YAML, and reads each date as the string written in
the file, such as `2026-11-20`. When the file cannot be read, or YAML cannot parse it, the read side
finds no registry and one defect at the root pointer `''`.

A parsed registry is valid when it passes two checks:

1. the schema of the contract validates it, and a mapping holding a key read by YAML as no string,
   such as `2024:`, violates that schema;
2. no chain of the key `replaced_by` passes twice through one identifier.

The second check runs only on a registry that passes the first. An invalid registry yields no entry,
and its defects are located at the JSON Pointer of each violating value, one defect per pointer.

## Lookup in a registry

A target into another repository is resolved by reading the registry of that repository, without
walking its records. The lookup of an identifier yields the first outcome of the table whose
condition holds, so an identifier both listed and retired yields a record:

| Outcome | Condition | Result |
| --- | --- | --- |
| record | an entry of the mapping `records` of the registry holds the identifier | the path and the format of the entry |
| renamed | the identifier is retired, and its successors reach an entry of `records` | the chain of successors, then the path and the format of the entry of the last one |
| retired | the identifier is retired, and its successors reach no entry of `records` | the successor of the identifier, if any |
| unknown | the registry neither lists nor retires the identifier | none |

The successors of a retired identifier are followed through the key `replaced_by`, from one retired
identifier to the next, up to the first live successor. The lookup in a registry takes an
identifier as live when an entry of `records` holds it. The chain also stops without a live
successor in three cases:

- at an identifier retired without a successor;
- at a successor that is neither live nor retired;
- at a successor already met.

A valid registry never stops a chain on a successor already met, since none of its chains passes
twice through one identifier.

## Lookup in the open repository

A read side holding the records of its own repository looks up an identifier against those records
first. An identifier held by one record resolves to that record, and an identifier held by several
records resolves to none of them, as a duplicate. The retired identifiers of the registry are
consulted only when no record holds the identifier. In that lookup, the chain of successors takes an
identifier as live when a record of the repository holds it, so the mapping `records` of the
registry plays no part. A chain reaching a successor held by several records yields a rename to a
duplicate, without a single record. No identifier is
retired when the repository declares no section `records`, or when its registry is absent or
invalid.
