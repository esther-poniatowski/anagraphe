/**
 * The validation of a manifest and of a record registry against their packaged schemas, through
 * Ajv, as the Python read side validates them through `jsonschema`.
 *
 * Each validator reports every violation, located at the JSON Pointer of the violating value, so
 * that a violation of `required`, `additionalProperties` or `propertyNames` is located at its
 * mapping. The format `date` admits a day of the calendar written `YYYY-MM-DD`, as the format
 * checker of `jsonschema` does.
 */
import { Ajv2020, type ValidateFunction } from "ajv/dist/2020.js";
import { isDay } from "./documents/yaml.js";
import {
  ADDRESSING_SCHEMA,
  RECORD_REGISTRY_SCHEMA,
  REPOSITORY_SCHEMA,
} from "./generated/resources.js";

/** One violation of a schema: the JSON Pointer of the violating value, and why. */
export interface Violation {
  readonly pointer: string;
  readonly message: string;
}

/** A day of the calendar, as `datetime.date.fromisoformat` reads `YYYY-MM-DD`. */
function isDate(text: string): boolean {
  const parts = /^([0-9]{4})-([0-9]{2})-([0-9]{2})$/.exec(text);
  return parts !== null && isDay(Number(parts[1]), Number(parts[2]), Number(parts[3]));
}

let validators: {
  readonly repository: ValidateFunction;
  readonly registry: ValidateFunction;
} | null = null;

/** Returns the two validators, compiled once, the resource of the addressing registered by `$id`. */
function compiled(): NonNullable<typeof validators> {
  if (validators === null) {
    // The packaged schemas state `pattern` under `not` without `type`, which JSON Schema admits.
    const ajv = new Ajv2020({ allErrors: true, strictTypes: false });
    ajv.addFormat("date", { type: "string", validate: isDate });
    ajv.addSchema(ADDRESSING_SCHEMA);
    validators = {
      repository: ajv.compile(REPOSITORY_SCHEMA),
      registry: ajv.compile(RECORD_REGISTRY_SCHEMA),
    };
  }
  return validators;
}

/**
 * Returns the violations of a value against the schema of the manifest or of the registry, the
 * first violation of each JSON Pointer, sorted by pointer.
 */
export function violations(schema: "repository" | "registry", value: unknown): Violation[] {
  const validate = compiled()[schema];
  if (validate(value)) return [];
  const first = new Map<string, string>();
  for (const error of validate.errors ?? []) {
    if (!first.has(error.instancePath))
      first.set(error.instancePath, error.message ?? error.keyword);
  }
  return [...first.keys()]
    .sort()
    .map((pointer) => ({ pointer, message: first.get(pointer) ?? "" }));
}
