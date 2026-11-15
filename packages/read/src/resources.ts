/**
 * The schema resources of the addressing, read from the module generated from the packaged schemas
 * of Anagraphe: the resource `addressing.v1`, the contract `anagraphe:repository@1` of
 * `repository.yml`, and the contract `anagraphe:record-registry@1`.
 *
 * Every pattern and identifier below derives from the generated module, so the package states no
 * pattern of its own. A consumer schema references the definition `target` by its absolute URI,
 * {@link TARGET_REFERENCE}, and a read side recognizes a target field by that URI without loading
 * the resource.
 */
import {
  ADDRESSING_SCHEMA,
  RECORD_REGISTRY_SCHEMA,
  REPOSITORY_SCHEMA,
} from "./generated/resources.js";

/** The absolute `$id` of the resource `addressing.v1`, which carries its major version. */
export const ADDRESSING_ID = ADDRESSING_SCHEMA.$id;

/** The reference to the definition of a logical target. */
export const TARGET_REFERENCE = `${ADDRESSING_ID}#/$defs/target`;

/** The contract of `repository.yml`. */
export const REPOSITORY_CONTRACT = REPOSITORY_SCHEMA.properties._schema.const;

/** The absolute `$id` of the schema of the record registry. */
export const REGISTRY_ID = RECORD_REGISTRY_SCHEMA.$id;

/** The contract of the record registry. */
export const REGISTRY_CONTRACT = RECORD_REGISTRY_SCHEMA.properties._schema.const;

/**
 * The versions of the specification that this read side implements: the `$id` of the resource of
 * the addressing, and the contracts of the manifest and of the record registry. The Python read
 * side exports the same mapping as `anagraphe.targets.IMPLEMENTED_SPECIFICATION`.
 */
export const IMPLEMENTED_SPECIFICATION = {
  addressing: ADDRESSING_ID,
  repository: REPOSITORY_CONTRACT,
  registry: REGISTRY_CONTRACT,
} as const;

/** An identifier definition of the resource. */
export type IdentifierDefinition = "repository-id" | "record-id" | "unit-id";

/** A pattern that admits a string only when it matches the whole string, as Python `fullmatch`. */
function whole(pattern: string): RegExp {
  return new RegExp(`^(?:${pattern})$`);
}

const PATTERNS: Readonly<Record<IdentifierDefinition, RegExp>> = {
  "repository-id": whole(ADDRESSING_SCHEMA.$defs["repository-id"].pattern),
  "record-id": whole(ADDRESSING_SCHEMA.$defs["record-id"].pattern),
  "unit-id": whole(ADDRESSING_SCHEMA.$defs["unit-id"].pattern),
};

/** Whether a value is a string that the pattern of an identifier definition admits whole. */
export function matches(definition: IdentifierDefinition, value: unknown): value is string {
  return typeof value === "string" && PATTERNS[definition].test(value);
}

/**
 * The pattern of a unit identifier without its anchors, the closing `$(?!\n)` included, so that a
 * block anchor `^name` can be read inside a line.
 */
export const UNIT_NAME = ADDRESSING_SCHEMA.$defs["unit-id"].pattern
  .replace(/^\^/, "")
  .replace(/\$(?:\(\?!\\n\))?$/, "");

/** A contract identifier admitted in `x-target-contract`: `namespace:name`, or with `@<version>`. */
export const CONTRACT_ENTRY = whole(ADDRESSING_SCHEMA.$defs["contract-entry"].pattern);

/** A dotted path of property names, as `x-identifier` writes it. */
export const PROPERTY_PATH = whole(ADDRESSING_SCHEMA.$defs["property-path"].pattern);

/** A field path naming one node of a document, as the definition `field-path` admits it. */
export const FIELD_PATH = whole(ADDRESSING_SCHEMA.$defs["field-path"].pattern);

/** A field-path pattern, with its wildcards, as the definition `field-path-pattern` admits it. */
export const FIELD_PATH_PATTERN = whole(ADDRESSING_SCHEMA.$defs["field-path-pattern"].pattern);
