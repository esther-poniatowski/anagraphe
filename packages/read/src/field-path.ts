/**
 * Field paths: the text naming one node of a document, its parsing and its canonical printing, its
 * conversions to and from a JSON Pointer, and the expansion of a field-path pattern, as the Python
 * read side reads them in `anagraphe_read._targets.field_paths`.
 *
 * A key follows a dot, except at the start of the path; a position in a sequence stands between
 * brackets, counted from zero; a key that a bare key cannot hold stands between brackets as a JSON
 * string. The empty text names the root. A pattern may also hold the wildcards `[*]`, every item
 * of a sequence, and `*`, every key of a mapping.
 *
 * The definitions `field-path` and `field-path-pattern` of the resource state the grammar once. The
 * parser tests each bare key and each bracket against the pattern of `field-path`, so it restates
 * no class of characters, and it reports the reason and the offset of the first defect from the
 * left. An offset counts the UTF-16 code units of the text, where the Python read side counts code
 * points; the two agree on every text within the Basic Multilingual Plane.
 */
import { isMapping } from "./documents/text.js";
import { pointer } from "./key-path.js";
import { FIELD_PATH, FIELD_PATH_PATTERN } from "./resources.js";

/** The wildcard naming every item of a sequence, written `[*]`. */
export const ANY_ITEM: unique symbol = Symbol("any-item");

/** The wildcard naming every key of a mapping, written `*`. */
export const ANY_KEY: unique symbol = Symbol("any-key");

/** A key of a mapping, or a position in a sequence. */
export type Segment = string | number;

/** A segment of a field-path pattern. */
export type PatternSegment = Segment | typeof ANY_ITEM | typeof ANY_KEY;

/** Why a text is not a field path, or not a field-path pattern. */
export type FieldPathReason =
  | "empty-key"
  | "invalid-character"
  | "wildcard"
  | "unclosed-bracket"
  | "invalid-index"
  | "invalid-quoted-key"
  | "invalid-bracket";

/** Why a JSON Pointer converts to no field path within a document. */
export type PointerReason =
  "not-a-pointer" | "invalid-escape" | "invalid-index" | "index-out-of-range" | "no-node";

/** A position admitted by the grammar: at most 15 digits, so that it is exact in a double. */
const POSITIONS = 1e15;

/** The canonical decimal form of a position in a JSON Pointer. */
const DECIMAL = /^(?:0|[1-9][0-9]*)$/;

const MESSAGES: Readonly<Record<FieldPathReason | PointerReason, string>> = {
  "empty-key": 'a key holds at least one character; write the empty key [""]',
  "invalid-character":
    "a bare key holds no dot, bracket, quote, star, space or control character, and a segment is " +
    "followed by a dot, a bracket or the end; write such a key in brackets as a JSON string",
  wildcard: 'a field path names one node and holds no wildcard; write a key * as ["*"]',
  "unclosed-bracket": "no bracket closes this bracket",
  "invalid-index":
    "a position is 0 or a decimal of at most 15 digits without a leading zero; below a sequence, " +
    "a token of a JSON Pointer is a decimal without a leading zero",
  "invalid-quoted-key": "a quoted key is one JSON string",
  "invalid-bracket": "a bracket holds a position or a JSON string",
  "not-a-pointer": "a JSON Pointer is empty or opens on /",
  "invalid-escape": "a ~ is followed by 0 or 1",
  "index-out-of-range": "the sequence holds no item at this position",
  "no-node": "the token descends from no mapping or sequence of the document",
};

/** Raised when a text is not a field path, with the reason and the offset of its defect. */
export class FieldPathError extends Error {
  override name = "FieldPathError";

  constructor(
    readonly text: string,
    readonly reason: FieldPathReason,
    readonly offset: number,
  ) {
    super(`Invalid field path \`${text}\` at offset ${offset}: ${MESSAGES[reason]}.`);
  }
}

/** Raised when a JSON Pointer converts to no field path, with the reason and its offset. */
export class PointerError extends Error {
  override name = "PointerError";

  constructor(
    readonly text: string,
    readonly reason: PointerReason,
    readonly offset: number,
  ) {
    super(`JSON Pointer \`${text}\` at offset ${offset}: ${MESSAGES[reason]}.`);
  }
}

/** Whether a value is a field path, as the definition `field-path` admits it. */
export function isFieldPath(value: unknown): value is string {
  return typeof value === "string" && FIELD_PATH.test(value);
}

/** Whether a value is a field-path pattern, as the definition `field-path-pattern` admits it. */
export function isFieldPathPattern(value: unknown): value is string {
  return typeof value === "string" && FIELD_PATH_PATTERN.test(value);
}

/**
 * Parses a field path; the empty text names the root.
 *
 * @throws FieldPathError When the text is not a field path, at the first defect from the left.
 */
export function parseFieldPath(text: string): Segment[] {
  return parse(text, false).filter((segment): segment is Segment => typeof segment !== "symbol");
}

/**
 * Parses a field-path pattern, with its wildcards.
 *
 * @throws FieldPathError When the text is not a field-path pattern, at the first defect.
 */
export function parseFieldPathPattern(text: string): PatternSegment[] {
  return parse(text, true);
}

function parse(text: string, wildcards: boolean): PatternSegment[] {
  const fail = (reason: FieldPathReason, at: number): never => {
    throw new FieldPathError(text, reason, at);
  };
  const segments: PatternSegment[] = [];
  let index = 0;
  while (index < text.length) {
    if (text[index] === "[") {
      const close = closingBracket(text, index);
      if (close < 0) fail("unclosed-bracket", index);
      segments.push(bracket(text, index, close, wildcards, fail));
      index = close + 1;
      continue;
    }
    if (index > 0) {
      if (text[index] !== ".") fail("invalid-character", index);
      index += 1;
    }
    let end = index;
    while (end < text.length && isFieldPath(text[end])) end += 1;
    const char = text.slice(index, index + 1);
    if (end > index) segments.push(text.slice(index, end));
    else if (char === "*" && wildcards) {
      segments.push(ANY_KEY);
      end += 1;
    } else if (char === "*") fail("wildcard", index);
    else if (char === "" || char === "." || char === "[") fail("empty-key", index);
    else fail("invalid-character", index);
    index = end;
  }
  return segments;
}

/** Offset of the bracket closing the one at `start`, skipping the content of a JSON string. */
function closingBracket(text: string, start: number): number {
  let quoted = false;
  for (let index = start + 1; index < text.length; index += 1) {
    const char = text[index];
    if (quoted && char === "\\") index += 1;
    else if (char === '"') quoted = !quoted;
    else if (char === "]" && !quoted) return index;
  }
  return -1;
}

function bracket(
  text: string,
  start: number,
  close: number,
  wildcards: boolean,
  fail: (reason: FieldPathReason, at: number) => never,
): PatternSegment {
  const content = text.slice(start + 1, close);
  if (content === "*") return wildcards ? ANY_ITEM : fail("wildcard", start);
  if (isFieldPath(`[${content}]`)) {
    // Validated by the pattern: a JSON string or a canonical decimal.
    return content.startsWith('"') ? (JSON.parse(content) as string) : Number(content);
  }
  if (content.startsWith('"')) return fail("invalid-quoted-key", start);
  if (/^[-0-9]/.test(content)) return fail("invalid-index", start);
  return fail("invalid-bracket", start);
}

/** Returns a position of the grammar, or throws. */
function position(segment: unknown): number {
  if (typeof segment !== "number" || !Number.isInteger(segment) || segment < 0) {
    throw new RangeError(`${String(segment)} is no key and no position of a field path`);
  }
  if (segment >= POSITIONS) throw new RangeError(`${segment} exceeds the positions of the grammar`);
  return segment;
}

/**
 * Prints a field path or a pattern in its canonical form: each key bare whenever a bare key can
 * hold it, and quoted as a JSON string otherwise; the root prints as `""`.
 *
 * @throws RangeError When a segment is neither a string, a position of the grammar nor a wildcard.
 */
export function printFieldPath(segments: readonly PatternSegment[]): string {
  return segments
    .map((segment, index) => {
      if (segment === ANY_ITEM) return "[*]";
      if (segment === ANY_KEY) return index === 0 ? "*" : ".*";
      if (typeof segment !== "string") return `[${position(segment)}]`;
      const bare = segment !== "" && !/[.[]/.test(segment) && isFieldPath(segment);
      if (bare) return index === 0 ? segment : `.${segment}`;
      return `[${JSON.stringify(segment)}]`;
    })
    .join("");
}

/** Returns the JSON Pointer of a field path, converted segment by segment. */
export function toPointer(path: readonly Segment[]): string {
  return pointer(
    ...path.map((segment) => (typeof segment === "string" ? segment : position(segment))),
  );
}

/** Returns the tokens of a JSON Pointer, each with the offset of the slash opening it. */
function tokens(text: string): [offset: number, token: string][] {
  if (text !== "" && !text.startsWith("/")) throw new PointerError(text, "not-a-pointer", 0);
  const escape = /~(?![01])/.exec(text);
  if (escape !== null) throw new PointerError(text, "invalid-escape", escape.index);
  const found: [number, string][] = [];
  let offset = 0;
  for (const raw of text.split("/").slice(1)) {
    found.push([offset, raw.replace(/~1/g, "/").replace(/~0/g, "~")]);
    offset += raw.length + 1;
  }
  return found;
}

/**
 * Returns the tokens of a JSON Pointer, each unescaped: `~1` read as `/`, then `~0` as `~`.
 *
 * @throws PointerError When the text neither is empty nor opens on `/`, or holds an invalid escape.
 */
export function pointerTokens(text: string): string[] {
  return tokens(text).map(([, token]) => token);
}

/**
 * Returns the field path of a JSON Pointer within a document. A token is a position exactly when
 * its parent node is a sequence, and it then names an item of that sequence in canonical
 * decimal. A token below a mapping is a key, present or absent. A token descending from an absent
 * key or from a scalar fails, since its node, and thus its kind, is unknown.
 *
 * @throws PointerError At the offset of an invalid escape, or of the slash opening a failing token.
 */
export function fromPointer(text: string, document: unknown): Segment[] {
  const path: Segment[] = [];
  let node: unknown = document;
  let present = true;
  for (const [offset, token] of tokens(text)) {
    if (!present || !(isMapping(node) || Array.isArray(node))) {
      throw new PointerError(text, "no-node", offset);
    }
    if (Array.isArray(node)) {
      if (!DECIMAL.test(token)) throw new PointerError(text, "invalid-index", offset);
      if (Number(token) >= node.length) throw new PointerError(text, "index-out-of-range", offset);
      path.push(Number(token));
      node = node[Number(token)] as unknown;
    } else {
      path.push(token);
      present = Object.prototype.hasOwnProperty.call(node, token);
      node = present ? node[token] : undefined;
    }
  }
  return path;
}

/** A node of a document, with its field path. */
export interface MatchedNode {
  readonly path: Segment[];
  readonly value: unknown;
}

/**
 * Returns each node of a document that a pattern names, with its field path, in document order: a
 * key names the value of a mapping holding it, a position the item of a sequence holding it, `*`
 * every value of a mapping, and `[*]` every item of a sequence. A JavaScript object enumerates the
 * keys that read as array indices first, so `*` follows that order over such keys.
 */
export function matchNodes(pattern: readonly PatternSegment[], document: unknown): MatchedNode[] {
  let found: MatchedNode[] = [{ path: [], value: document }];
  for (const segment of pattern) {
    found = found.flatMap(({ path, value }): MatchedNode[] => {
      if (Array.isArray(value) && segment === ANY_ITEM) {
        return value.map((item: unknown, index) => ({ path: [...path, index], value: item }));
      }
      if (isMapping(value) && segment === ANY_KEY) {
        return Object.entries(value).map(([key, item]) => ({ path: [...path, key], value: item }));
      }
      if (
        Array.isArray(value) &&
        typeof segment === "number" &&
        segment >= 0 &&
        segment < value.length
      ) {
        return [{ path: [...path, segment], value: value[segment] as unknown }];
      }
      if (
        isMapping(value) &&
        typeof segment === "string" &&
        Object.prototype.hasOwnProperty.call(value, segment)
      ) {
        return [{ path: [...path, segment], value: value[segment] }];
      }
      return [];
    });
  }
  return found;
}

/** Returns the field paths of the nodes of a document that a pattern names, in document order. */
export function expand(pattern: readonly PatternSegment[], document: unknown): Segment[][] {
  return matchNodes(pattern, document).map(({ path }) => path);
}
