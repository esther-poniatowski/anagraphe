/**
 * The record registry of a repository, `record-registry.yml` under the contract
 * `anagraphe:record-registry@1`: its reading, its validation, and the lookup of an identifier.
 *
 * A registry maps the identifier of each record to its path and its format, and keeps the
 * permanent list of the retired identifiers, each with its date and its optional successor. A YAML
 * date is read as the string that it writes. An invalid registry yields no entry, only its
 * defects. Python alone writes the registry.
 */
import { universalNewlines } from "./documents/text.js";
import { readYaml } from "./documents/yaml.js";
import { pointer } from "./key-path.js";
import type { RecordFormat } from "./records.js";
import { REGISTRY_CONTRACT } from "./resources.js";
import { violations } from "./validation.js";

/** The file of the registry at the root, unless the configuration of the host names another. */
export const REGISTRY_FILE = "record-registry.yml";

/** The file of one record: its path relative to the root, and its format. */
export interface RegistryEntry {
  readonly path: string;
  readonly format: RecordFormat;
}

/** A retired identifier: the day of its retirement, and its successor after a rename. */
export interface Retirement {
  /** The day of the retirement, `YYYY-MM-DD`. */
  readonly date: string;
  /** The identifier replacing the retired one, `null` when the record was removed. */
  readonly replacedBy: string | null;
}

/** The content of a valid record registry. */
export interface RecordRegistry {
  readonly repository: string;
  readonly records: ReadonlyMap<string, RegistryEntry>;
  readonly retired: ReadonlyMap<string, Retirement>;
}

/** A defect of a registry: the JSON Pointer of its value, and why. */
export interface RegistryProblem {
  readonly pointer: string;
  readonly detail: string;
}

/** The registry read from a text, `null` when the text is absent or invalid, and its defects. */
export interface RegistryReading {
  readonly registry: RecordRegistry | null;
  readonly problems: readonly RegistryProblem[];
  /** Whether the file of the registry exists. */
  readonly exists: boolean;
}

/**
 * Reads the text of a registry, `null` when the file is absent. A text that cannot be parsed, or
 * that violates the contract, holds no registry and its defects.
 */
export function readRegistry(text: string | null): RegistryReading {
  if (text === null) return { registry: null, problems: [], exists: false };
  const reading = readYaml(universalNewlines(text), { timestamps: "string" });
  if (!reading.ok) {
    return {
      registry: null,
      problems: [{ pointer: "", detail: `the registry cannot be parsed: ${reading.error}` }],
      exists: true,
    };
  }
  return { ...checkRegistry(reading.value, reading.nonStringKeys), exists: true };
}

/**
 * Checks the content of a registry against `anagraphe:record-registry@1`: the schema first, then
 * the rule that no chain of `replaced_by` returns to an identifier that it has left. Each defect
 * is reported once per JSON Pointer.
 *
 * @param nonStringKeys The mappings holding a key that YAML reads as no string; every mapping of
 *   the contract admits string keys only, so each is a defect at its pointer.
 */
export function checkRegistry(
  data: unknown,
  nonStringKeys: readonly string[] = [],
): Omit<RegistryReading, "exists"> {
  const violated = (detail: string): string =>
    `the registry violates ${REGISTRY_CONTRACT}: ${detail}`;
  const found = new Map<string, string>(
    violations("registry", data).map(({ pointer: at, message }) => [at, violated(message)]),
  );
  for (const at of nonStringKeys) {
    if (!found.has(at)) found.set(at, violated("a key is no string"));
  }
  if (found.size > 0) {
    const problems = [...found.keys()]
      .sort()
      .map((at) => ({ pointer: at, detail: found.get(at) ?? "" }));
    return { registry: null, problems };
  }
  const valid = data as {
    repository: string;
    records: Record<string, { path: string; format: RecordFormat }>;
    retired: Record<string, { date: string; replaced_by?: string }>;
  };
  const registry: RecordRegistry = {
    repository: valid.repository,
    records: new Map(
      Object.entries(valid.records).map(([id, entry]) => [
        id,
        { path: entry.path, format: entry.format },
      ]),
    ),
    retired: new Map(
      Object.entries(valid.retired).map(([id, retirement]) => [
        id,
        { date: retirement.date, replacedBy: retirement.replaced_by ?? null },
      ]),
    ),
  };
  const cycles = [...registry.retired.keys()]
    .sort()
    .filter((identifier) => endless(registry.retired, identifier))
    .map((identifier) => ({
      pointer: pointer("retired", identifier, "replaced_by"),
      detail: violated(
        `the successors of ${identifier} return to an identifier that they have left, so no chain of renames ends`,
      ),
    }));
  return cycles.length > 0 ? { registry: null, problems: cycles } : { registry, problems: [] };
}

/** Whether the chain of successors from a retired identifier never ends. */
function endless(retired: ReadonlyMap<string, Retirement>, identifier: string): boolean {
  const seen = new Set([identifier]);
  let current = retired.get(identifier)?.replacedBy ?? null;
  while (current !== null && retired.has(current)) {
    if (seen.has(current)) return true;
    seen.add(current);
    current = retired.get(current)?.replacedBy ?? null;
  }
  return false;
}

/**
 * Returns the successors of a retired identifier up to the first one that `live` accepts, `null`
 * when the chain ends without a live identifier: at an identifier retired without a successor, at
 * a successor neither live nor retired, or on a cycle.
 */
export function follow(
  retired: ReadonlyMap<string, Retirement>,
  identifier: string,
  live: (identifier: string) => boolean,
): string[] | null {
  const chain: string[] = [];
  const seen = new Set([identifier]);
  let current = identifier;
  for (
    let retirement = retired.get(current);
    retirement !== undefined;
    retirement = retired.get(current)
  ) {
    const successor = retirement.replacedBy;
    if (successor === null || seen.has(successor)) return null;
    chain.push(successor);
    seen.add(successor);
    if (live(successor)) return chain;
    current = successor;
  }
  return null;
}

/** The outcome of looking up an identifier in a registry. */
export type RegistryLookup =
  /** A record of the registry holds the identifier. */
  | { readonly status: "record"; readonly identifier: string; readonly entry: RegistryEntry }
  /**
   * The identifier is retired by a rename, whose successors reach a record; `chain` lists the
   * successors, the identifier of the record last.
   */
  | {
      readonly status: "renamed";
      readonly chain: readonly string[];
      readonly identifier: string;
      readonly entry: RegistryEntry;
    }
  /** The identifier is retired without a successor, or its successors reach no record. */
  | { readonly status: "retired"; readonly successor: string | null }
  /** The registry neither lists nor retires the identifier. */
  | { readonly status: "unknown" };

/**
 * Looks up an identifier in a registry alone, as a resolver of another repository reads it: a
 * record of the registry, else a retired identifier, whose successors are followed to a record.
 */
export function lookup(registry: RecordRegistry, identifier: string): RegistryLookup {
  const entry = registry.records.get(identifier);
  if (entry !== undefined) return { status: "record", identifier, entry };
  const retirement = registry.retired.get(identifier);
  if (retirement === undefined) return { status: "unknown" };
  const chain = follow(registry.retired, identifier, (id) => registry.records.has(id));
  const live = chain?.[chain.length - 1];
  const found = live === undefined ? undefined : registry.records.get(live);
  if (chain === null || live === undefined || found === undefined) {
    return { status: "retired", successor: retirement.replacedBy };
  }
  return { status: "renamed", chain, identifier: live, entry: found };
}
