/**
 * The records of a repository as targets: the identifier of each record and the units inside it.
 *
 * A record is a Markdown note, read through its frontmatter, a YAML or JSON document, or a TOML
 * document whose metadata source is `toml`. The schema of its contract may declare the field of
 * its identifier by `x-identifier`. Without that declaration, the identifier of a record is the key
 * `id` of the metadata source of the file, which the host selects from its configuration, as
 * {@link defaultIdentifier} reads it: by default the frontmatter of a note, and the top level of a
 * YAML or JSON document, then its block `metadata`.
 *
 * The units of a record are the items declared by `x-identifier` on the definition of the items of
 * an array, then, in a note, the block anchors of its body. The units of one record share one
 * namespace, so a repeated identifier is kept twice. A declared item identifier outside the pattern
 * `unit-id` is no unit, and the reading keeps it apart.
 */
import {
  blockAnchors,
  frontmatterProblem,
  isMapping,
  readDocument,
  splitFrontmatter,
  universalNewlines,
} from "./documents/text.js";
import { pointer, valueAt, valuesAt } from "./key-path.js";
import { builtInSource, defaultIdentifier, type MetadataSource } from "./metadata.js";
import { matches } from "./resources.js";
import type { Declarations } from "./schema/declarations.js";

/** The format of the file of a record, read from its suffix. */
export type RecordFormat = "markdown" | "yaml" | "json" | "toml";

const SUFFIX_FORMATS: readonly (readonly [string, RecordFormat])[] = [
  [".md", "markdown"],
  [".yml", "yaml"],
  [".yaml", "yaml"],
  [".json", "json"],
  [".toml", "toml"],
];

/** Returns the format of the suffix of a file, `null` for a suffix that names no format. */
export function formatOf(path: string): RecordFormat | null {
  return SUFFIX_FORMATS.find(([suffix]) => path.endsWith(suffix))?.[1] ?? null;
}

/**
 * Parses the text of a TOML document, as the host supplies it; throws when the text does not
 * parse. The read side holds no TOML parser of its own.
 */
export type TomlParser = (text: string) => unknown;

/** How a record is parsed: its metadata source, and the TOML parser of the host. */
export interface ParseOptions {
  /** The metadata source of the file; its built-in source when absent. */
  readonly source?: MetadataSource | undefined;
  /** The TOML parser of the host; without it, a TOML record cannot be read. */
  readonly toml?: TomlParser | undefined;
}

/** The parsed text of a record, before its binding. */
export interface RecordSource {
  readonly path: string;
  readonly format: RecordFormat;
  /** The frontmatter of a note, or the top-level mapping of a document; empty when it holds none. */
  readonly data: Readonly<Record<string, unknown>>;
  /** The body of a note after its frontmatter; empty for a document. */
  readonly body: string;
  /** The metadata source of the file, which gives its default identifier. */
  readonly metadata: MetadataSource;
  /** Why the record cannot be read; `null` when it can. */
  readonly problem: string | null;
}

/**
 * Parses the text of a record, `null` for a file that is no record: neither a Markdown note, nor a
 * YAML or JSON document, nor a TOML document whose metadata source is `toml`.
 */
export function parseRecord(
  path: string,
  raw: string,
  options: ParseOptions = {},
): RecordSource | null {
  const format = formatOf(path);
  const metadata = options.source ?? builtInSource(path);
  if (format === null || (format === "toml" && metadata.kind !== "toml")) return null;
  const text = universalNewlines(raw);
  const unreadable = (problem: string): RecordSource => ({
    path,
    format,
    data: {},
    body: "",
    metadata,
    problem,
  });
  if (format === "markdown") {
    const problem = frontmatterProblem(text);
    if (problem !== null) return unreadable(problem);
    const { data, body } = splitFrontmatter(text);
    return { path, format, data, body, metadata, problem: null };
  }
  let value: unknown;
  if (format === "toml") {
    if (options.toml === undefined)
      return unreadable("the document cannot be parsed: the host supplies no TOML parser");
    try {
      value = options.toml(text);
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      return unreadable(`the document cannot be parsed: ${detail || "no detail"}`);
    }
  } else {
    const reading = readDocument(path, text);
    if (!reading.ok)
      return unreadable(`the document cannot be parsed: ${reading.error || "no detail"}`);
    value = reading.value;
  }
  return {
    path,
    format,
    data: isMapping(value) ? value : {},
    body: "",
    metadata,
    problem: null,
  };
}

/** The identifier of a record, as its field holds it. */
export type IdentifierReading =
  | { readonly status: "valid"; readonly value: string; readonly pointer: string }
  /** The default field holds no value; the record declares no identifier, and no finding arises. */
  | { readonly status: "absent"; readonly pointer: string }
  /** The field declared by `x-identifier` holds no value. */
  | { readonly status: "missing"; readonly pointer: string }
  /** The field holds a value outside the pattern of `record-id`. */
  | { readonly status: "invalid"; readonly value: unknown; readonly pointer: string };

/** A value of a record that the check reports, at its JSON Pointer. */
export interface LocatedValue {
  readonly pointer: string;
  readonly value: unknown;
}

/** One record, read for its identifier, its contracts and its units. */
export interface RecordReading {
  readonly path: string;
  readonly format: RecordFormat;
  readonly data: Readonly<Record<string, unknown>>;
  /** The contract that the record follows, `null` when it names none. */
  readonly contract: string | null;
  /** The contracts of the record: its contract, then those its schema implements. */
  readonly contracts: readonly string[];
  /** The declarations of the schema of the record, `null` without a readable schema. */
  readonly declarations: Declarations | null;
  readonly identifier: IdentifierReading;
  /** Each later key path of the metadata source holding another identifier. */
  readonly conflicts: readonly LocatedValue[];
  readonly units: readonly string[];
  /** Each declared item identifier outside the pattern `unit-id`. */
  readonly invalidUnits: readonly LocatedValue[];
  /** Why the record cannot be read; `null` when it can. */
  readonly problem: string | null;
}

/** Reads a parsed record, bound to its contract and to the declarations of its schema. */
export function readRecord(
  source: RecordSource,
  contract: string | null,
  declarations: Declarations | null,
): RecordReading {
  const declared = declarations?.identifier ?? null;
  const readable = source.problem === null;
  const fallback = defaultIdentifier(source.metadata, source.data);
  const field = declared ?? fallback.keys;
  const at = pointer(...field);
  const value = !readable
    ? undefined
    : declared !== null
      ? valueAt(source.data, declared)
      : fallback.value;
  const identifier: IdentifierReading =
    value === undefined || value === null
      ? { status: declared === null ? "absent" : "missing", pointer: at }
      : matches("record-id", value)
        ? { status: "valid", value, pointer: at }
        : { status: "invalid", value, pointer: at };
  const conflicts =
    readable && declared === null
      ? fallback.conflicts.map((holder) => ({
          pointer: pointer(...holder.keys),
          value: holder.value,
        }))
      : [];
  const units: string[] = [];
  const invalidUnits: LocatedValue[] = [];
  for (const unit of declarations?.units ?? []) {
    for (const { keys, value: item } of valuesAt(source.data, unit.path)) {
      const name = valueAt(item, unit.identifier);
      if (name === undefined || name === null) continue;
      if (matches("unit-id", name)) units.push(name);
      else invalidUnits.push({ pointer: pointer(...keys, ...unit.identifier), value: name });
    }
  }
  const anchors = source.format === "markdown" && readable ? blockAnchors(source.body) : [];
  return {
    path: source.path,
    format: source.format,
    data: source.data,
    contract,
    contracts: contract === null ? [] : [contract, ...(declarations?.implements ?? [])],
    declarations,
    identifier,
    conflicts,
    units: readable ? [...units, ...anchors] : [],
    invalidUnits: readable ? invalidUnits : [],
    problem: source.problem,
  };
}
