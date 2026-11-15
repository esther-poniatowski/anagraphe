/**
 * The texts of the files of a repository as the Python read side reads them: with universal
 * newlines, a document parsed as JSON or YAML by its suffix, and a note split into its frontmatter
 * and its body, whose block anchors name units.
 */
import { UNIT_NAME } from "../resources.js";
import { readYaml, type YamlReading } from "./yaml.js";

/**
 * Returns a text with each `\r\n` and each `\r` read as `\n`, as Python reads a file in text mode,
 * so that a file written on any platform reads alike.
 */
export function universalNewlines(text: string): string {
  return text.replace(/\r\n?/g, "\n");
}

/** The outcome of parsing a document: its value, or the first line of the reason of the failure. */
export type DocumentReading =
  { readonly ok: true; readonly value: unknown } | { readonly ok: false; readonly error: string };

/** Parses a document as JSON for a suffix `.json`, and as YAML otherwise. */
export function readDocument(path: string, text: string): DocumentReading {
  if (path.endsWith(".json")) {
    try {
      return { ok: true, value: JSON.parse(text) as unknown };
    } catch (error) {
      return { ok: false, error: error instanceof Error ? error.message : String(error) };
    }
  }
  const reading: YamlReading = readYaml(text);
  return reading.ok ? { ok: true, value: reading.value } : reading;
}

/** The opening line of a frontmatter, and the token closing it. */
const OPENING = "---\n";
const CLOSING = "\n---";

/** Returns the position of the line closing the frontmatter of a note, -1 when none closes it. */
function closing(text: string): number {
  return text.startsWith(OPENING) ? text.indexOf(CLOSING, OPENING.length) : -1;
}

/**
 * Whether a value is a mapping: a plain object, as a reading of YAML or JSON builds it, and not a
 * date, a set or the bytes of a binary scalar.
 */
export function isMapping(value: unknown): value is Readonly<Record<string, unknown>> {
  if (typeof value !== "object" || value === null) return false;
  const prototype: unknown = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

/**
 * Returns the parsed frontmatter of a note and its body; an empty mapping when the note holds no
 * readable frontmatter.
 */
export function splitFrontmatter(text: string): {
  readonly data: Readonly<Record<string, unknown>>;
  readonly body: string;
} {
  const end = closing(text);
  if (end === -1) return { data: {}, body: text };
  const reading = readYaml(text.slice(OPENING.length, end));
  const rest = text.slice(end + CLOSING.length);
  const body = rest.startsWith("\n") ? rest.replace(/^\n+/, "") : rest;
  return { data: reading.ok && isMapping(reading.value) ? reading.value : {}, body };
}

/** Returns why the frontmatter of a note cannot be read, `null` when it is absent or readable. */
export function frontmatterProblem(text: string): string | null {
  if (!text.startsWith(OPENING)) return null;
  const end = closing(text);
  if (end === -1) return "the frontmatter opens on --- and never closes";
  const reading = readYaml(text.slice(OPENING.length, end));
  if (!reading.ok) return `the frontmatter is not valid YAML: ${reading.error}`;
  if (reading.value !== null && !isMapping(reading.value))
    return "the frontmatter is not a mapping";
  return null;
}

/** The characters that Python reads as `\s` in a text, which `\s` of JavaScript does not match. */
const SPACE =
  "[\\t\\n\\v\\f\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000]";

/** A block anchor closing a line, after a space or at the start of the line. */
const BLOCK_ANCHOR = new RegExp(`(?:^|${SPACE})\\^(${UNIT_NAME})${SPACE}*$`);

/**
 * Returns the name of each block anchor of a text, in its order, a repeated name repeated: a caret
 * token `^name` closing a line after a space or a line break, whose name is a unit identifier.
 * A line ends at `\n` only, as a line of a Python pattern in multiline mode.
 */
export function blockAnchors(text: string): string[] {
  return text.split("\n").flatMap((line) => {
    const name = BLOCK_ANCHOR.exec(line)?.[1];
    return name === undefined ? [] : [name];
  });
}
