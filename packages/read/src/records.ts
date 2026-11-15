/**
 * The records of a repository as targets: the identifier of each record and the units inside it.
 *
 * A record is a Markdown note, read through its frontmatter, or a YAML or JSON document. The
 * schema of its contract may declare the field of its identifier by `x-identifier`. Without that
 * declaration, the identifier of a record is the key `id` of its metadata source: the frontmatter
 * of a note, or the block `metadata` of a document.
 *
 * The units of a record are the items declared by `x-identifier` on the definition of the items of
 * an array, then, in a note, the block anchors of its body. The units of one record share one
 * namespace, so a repeated identifier is kept twice.
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
import { matches } from "./resources.js";
import type { Declarations } from "./schema/declarations.js";

/** The format of the file of a record, read from its suffix. */
export type RecordFormat = "markdown" | "yaml" | "json";

const SUFFIX_FORMATS: readonly (readonly [string, RecordFormat])[] = [
  [".md", "markdown"],
  [".yml", "yaml"],
  [".yaml", "yaml"],
  [".json", "json"],
];

/** Returns the format of a file that may be a record, `null` for another suffix. */
export function formatOf(path: string): RecordFormat | null {
  return SUFFIX_FORMATS.find(([suffix]) => path.endsWith(suffix))?.[1] ?? null;
}

/** The default field of the identifier of a note and of a document. */
const NOTE_IDENTIFIER = ["id"] as const;
const DOCUMENT_IDENTIFIER = ["metadata", "id"] as const;

/** The parsed text of a record, before its binding. */
export interface RecordSource {
  readonly path: string;
  readonly format: RecordFormat;
  /** The frontmatter of a note, or the top-level mapping of a document; empty when it holds none. */
  readonly data: Readonly<Record<string, unknown>>;
  /** The body of a note after its frontmatter; empty for a document. */
  readonly body: string;
  /** Why the record cannot be read; `null` when it can. */
  readonly problem: string | null;
}

/**
 * Parses the text of a record, `null` for a file that is no record: neither a Markdown note nor a
 * YAML or JSON document.
 */
export function parseRecord(path: string, raw: string): RecordSource | null {
  const format = formatOf(path);
  if (format === null) return null;
  const text = universalNewlines(raw);
  const unreadable = (problem: string): RecordSource => ({
    path,
    format,
    data: {},
    body: "",
    problem,
  });
  if (format === "markdown") {
    const problem = frontmatterProblem(text);
    if (problem !== null) return unreadable(problem);
    const { data, body } = splitFrontmatter(text);
    return { path, format, data, body, problem: null };
  }
  const reading = readDocument(path, text);
  if (!reading.ok)
    return unreadable(`the document cannot be parsed: ${reading.error || "no detail"}`);
  return {
    path,
    format,
    data: isMapping(reading.value) ? reading.value : {},
    body: "",
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
  readonly units: readonly string[];
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
  const field = declared ?? (source.format === "markdown" ? NOTE_IDENTIFIER : DOCUMENT_IDENTIFIER);
  const at = pointer(...field);
  const value = source.problem === null ? valueAt(source.data, field) : undefined;
  const identifier: IdentifierReading =
    value === undefined || value === null
      ? { status: declared === null ? "absent" : "missing", pointer: at }
      : matches("record-id", value)
        ? { status: "valid", value, pointer: at }
        : { status: "invalid", value, pointer: at };
  const items = (declarations?.units ?? []).flatMap((unit) =>
    valuesAt(source.data, unit.path).flatMap(({ value: item }) => {
      const name = valueAt(item, unit.identifier);
      return typeof name === "string" ? [name] : [];
    }),
  );
  const anchors =
    source.format === "markdown" && source.problem === null ? blockAnchors(source.body) : [];
  return {
    path: source.path,
    format: source.format,
    data: source.data,
    contract,
    contracts: contract === null ? [] : [contract, ...(declarations?.implements ?? [])],
    declarations,
    identifier,
    units: source.problem === null ? [...items, ...anchors] : [],
    problem: source.problem,
  };
}
