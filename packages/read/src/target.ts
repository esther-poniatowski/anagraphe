/**
 * The logical target: its reading from a value, its normalization, its equality, and the
 * contracts that a target field admits.
 *
 * A target is the mapping `{repository, id, unit}`. An absent `repository` names the repository
 * holding the citing file, so the normalization fills it, and two targets are equal when their
 * normalized mappings are equal. A target with `repository` and without `id` names the repository
 * itself.
 */
import { isMapping } from "./documents/text.js";
import { CONTRACT_ENTRY, matches, type IdentifierDefinition } from "./resources.js";

/** Why a value is not a logical target, in the order of the checks. */
export type Reason =
  | "not-a-mapping"
  | "unknown-key"
  | "no-record-or-repository"
  | "unit-without-record"
  | "invalid-component";

/** A logical target: a record, a unit inside it, or a repository. */
export interface Target {
  readonly repository?: string;
  readonly id?: string;
  readonly unit?: string;
}

/** The outcome of reading a value as a target. */
export type TargetReading =
  | { readonly ok: true; readonly target: Target }
  | { readonly ok: false; readonly reason: Reason; readonly detail: string };

/** The keys of a target, in their written order, each with the definition of its value. */
const COMPONENTS: readonly (readonly [keyof Target, IdentifierDefinition])[] = [
  ["repository", "repository-id"],
  ["id", "record-id"],
  ["unit", "unit-id"],
];

const has = (value: object, key: string): boolean =>
  Object.prototype.hasOwnProperty.call(value, key);

/**
 * Reads a value as a target. The first failed check, in the order of {@link Reason}, names the
 * reason of an invalid value.
 */
export function readTarget(value: unknown): TargetReading {
  const invalid = (reason: Reason, detail: string): TargetReading => ({
    ok: false,
    reason,
    detail,
  });
  if (!isMapping(value))
    return invalid("not-a-mapping", "a target is a mapping {repository, id, unit}");
  const unknown = Object.keys(value)
    .filter((key) => !COMPONENTS.some(([name]) => name === key))
    .sort();
  if (unknown.length > 0) {
    return invalid(
      "unknown-key",
      `a target holds only repository, id and unit, not ${unknown.join(", ")}`,
    );
  }
  if (!has(value, "id") && !has(value, "repository")) {
    return invalid(
      "no-record-or-repository",
      "a target names a record under id, or a repository under repository",
    );
  }
  if (has(value, "unit") && !has(value, "id")) {
    return invalid("unit-without-record", "a target holding a unit names its record under id");
  }
  const target: { -readonly [K in keyof Target]: string } = {};
  for (const [key, definition] of COMPONENTS) {
    if (!has(value, key)) continue;
    const component = value[key];
    if (!matches(definition, component)) {
      return invalid(
        "invalid-component",
        `${key} ${JSON.stringify(component) ?? String(component)} lies outside the pattern of ${definition}`,
      );
    }
    target[key] = component;
  }
  return { ok: true, target };
}

/**
 * Returns a target with its repository filled by the repository holding the citing file; unchanged
 * when that repository declares no identifier.
 */
export function normalize(target: Target, repository: string | null): Target {
  if (target.repository !== undefined || repository === null) return target;
  return { repository, ...target };
}

/** Returns the written form of a target, its absent keys left out, in the order of its keys. */
export function written(target: Target): Target {
  return Object.fromEntries(
    COMPONENTS.flatMap(([key]) => (target[key] === undefined ? [] : [[key, target[key]]])),
  );
}

/** Whether two targets written in one repository name the same record, unit or repository. */
export function sameTarget(a: Target, b: Target, repository: string | null): boolean {
  const [left, right] = [normalize(a, repository), normalize(b, repository)];
  return COMPONENTS.every(([key]) => left[key] === right[key]);
}

/** Returns a target in the flow form of its mapping, as a record writes it. */
export function formatTarget(target: Target): string {
  const entries = Object.entries(written(target)).map(([key, value]) => `${key}: ${String(value)}`);
  return `{${entries.join(", ")}}`;
}

/** The outcome of reading the value of `x-target-contract`. */
export type ContractsReading =
  | { readonly ok: true; readonly entries: readonly string[] }
  | { readonly ok: false; readonly detail: string };

/** Reads the value of `x-target-contract`: a non-empty list of contract identifiers. */
export function readContracts(value: unknown): ContractsReading {
  if (!Array.isArray(value) || value.length === 0) {
    return {
      ok: false,
      detail: "x-target-contract holds a non-empty list of contract identifiers",
    };
  }
  for (const entry of value as unknown[]) {
    if (typeof entry !== "string" || !CONTRACT_ENTRY.test(entry)) {
      return {
        ok: false,
        detail: `x-target-contract holds ${JSON.stringify(entry) ?? String(entry)}, which is no contract identifier namespace:name or namespace:name@version`,
      };
    }
  }
  return { ok: true, entries: value as string[] };
}

/**
 * Whether an entry of `x-target-contract` admits one of the contracts of a record: its `_schema`,
 * then the contracts that its root schema declares under `x-implements`. An entry `namespace:name`
 * admits every version of that contract, and an entry `namespace:name@n` admits that version only.
 */
export function admits(entries: readonly string[], contracts: readonly string[]): boolean {
  return entries.some((entry) =>
    contracts.some(
      (contract) =>
        entry === contract || (!entry.includes("@") && contract.split("@")[0] === entry),
    ),
  );
}

/** How the record of a target satisfies the declarations of `x-target-contract` of its field. */
export type ContractVerdict =
  /** The field declares no contract, or the record satisfies each declaration. */
  | { readonly status: "admitted" }
  /** The field declares contracts, and the record names no contract. */
  | { readonly status: "unbound" }
  /** The declarations that no contract of the record satisfies. */
  | { readonly status: "mismatch"; readonly failed: readonly (readonly string[])[] };

/**
 * Returns how a record satisfies the declarations of `x-target-contract` of a target field, each
 * declaration a list of entries that one contract of the record must satisfy.
 *
 * @param contracts The contracts of the record, its `_schema` first, empty when it names none.
 */
export function contractVerdict(
  declarations: readonly (readonly string[])[],
  contracts: readonly string[],
): ContractVerdict {
  if (declarations.length === 0) return { status: "admitted" };
  if (contracts.length === 0) return { status: "unbound" };
  const failed = declarations.filter((entries) => !admits(entries, contracts));
  return failed.length === 0 ? { status: "admitted" } : { status: "mismatch", failed };
}
