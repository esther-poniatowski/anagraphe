/**
 * The metadata source of a file, and the default identifier read through it, as the Python read
 * side reads them in `anagraphe.core.metadata`.
 *
 * A source names where the fields of a file are written: the frontmatter of a text, a structured
 * document at declared key paths, the path `.` naming its top level, or none. The host selects
 * the source of each file from the section `metadata` of its configuration, whose conditions the
 * read side does not evaluate; without a host selection, the built-in sources apply: the
 * frontmatter of a Markdown note, and the top level of a YAML document, then its block `metadata`.
 *
 * The default identifier of a file is the key `id` of its source. The first declared key path whose
 * mapping holds `id` with a value other than null gives the identifier; each later path holding
 * another value is a conflict.
 */
import { isMapping } from "./documents/text.js";

/** The kind of source holding the metadata of a file. */
export type MetadataKind = "frontmatter" | "yaml" | "json" | "toml" | "none";

/** One source of metadata: its kind and, for a document, the key paths read in order. */
export interface MetadataSource {
  readonly kind: MetadataKind;
  /** The dotted key paths of a document, `.` for its top level; `["."]` for a frontmatter. */
  readonly at: readonly string[];
}

/** The key path naming the top level of a document. */
export const TOP = ".";

/** The key holding the default identifier of a file in its metadata source. */
export const IDENTIFIER_KEY = "id";

/** The source of a file that no rule names. */
export const NO_SOURCE: MetadataSource = { kind: "none", at: [] };

/** Returns the built-in source of a file: the frontmatter of a note, the top level then the block
 * `metadata` of a YAML document, and none otherwise. */
export function builtInSource(path: string): MetadataSource {
  if (path.endsWith(".md")) return { kind: "frontmatter", at: [TOP] };
  if (path.endsWith(".yml") || path.endsWith(".yaml"))
    return { kind: "yaml", at: [TOP, "metadata"] };
  return NO_SOURCE;
}

/** The value at a dotted key path of a document, `undefined` when a key is absent. */
function at(document: unknown, path: string): unknown {
  if (path === TOP) return document;
  let node = document;
  for (const key of path.split(".")) {
    if (!isMapping(node)) return undefined;
    node = node[key];
  }
  return node;
}

/** A field holding an identifier: its keys from the top level, and its value. */
export interface Holder {
  readonly keys: readonly string[];
  readonly value: unknown;
}

/**
 * Returns the keys and the value of each declared mapping of a parsed document that holds a key
 * with a value other than null, in the declared order. The path `.` holds no key naming the first
 * segment of a deeper declared path.
 */
export function holders(source: MetadataSource, document: unknown, key: string): Holder[] {
  if (source.kind === "none") return [];
  const nested = new Set(
    source.at.filter((path) => path !== TOP).map((path) => path.split(".")[0]),
  );
  const found: Holder[] = [];
  for (const path of source.at) {
    if (path === TOP && nested.has(key)) continue;
    const node = at(document, path);
    if (isMapping(node) && node[key] !== undefined && node[key] !== null) {
      const keys = path === TOP ? [] : path.split(".");
      found.push({ keys: [...keys, key], value: node[key] });
    }
  }
  return found;
}

/** The default identifier of a file, read through its metadata source. */
export interface DefaultIdentifier {
  /** The value of the identifier, `undefined` when no declared path holds the key. */
  readonly value: unknown;
  /**
   * The keys of the field holding the identifier; the field of the first declared path when no
   * path holds the key, and no key for a source of the kind `none`.
   */
  readonly keys: readonly string[];
  /** Each later path holding another value than the identifier. */
  readonly conflicts: readonly Holder[];
}

/** Whether two values of a document are equal, as Python compares them. */
function same(a: unknown, b: unknown): boolean {
  return a === b || JSON.stringify(a) === JSON.stringify(b);
}

/** Returns the default identifier of a parsed document read through its source. */
export function defaultIdentifier(source: MetadataSource, document: unknown): DefaultIdentifier {
  const [first, ...later] = holders(source, document, IDENTIFIER_KEY);
  if (first === undefined) {
    const path = source.at[0];
    if (source.kind === "none" || path === undefined) {
      return { value: undefined, keys: [], conflicts: [] };
    }
    const keys = path === TOP ? [] : path.split(".");
    return { value: undefined, keys: [...keys, IDENTIFIER_KEY], conflicts: [] };
  }
  return {
    value: first.value,
    keys: first.keys,
    conflicts: later.filter((holder) => !same(holder.value, first.value)),
  };
}
