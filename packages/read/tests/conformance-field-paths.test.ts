/**
 * The conformance cases of `specs/conformance/field-paths.yml`: the parsing and the printing of
 * field paths and patterns, their rejections, the conversions to and from a JSON Pointer, and the
 * expansion of patterns. The pattern of each definition of the resource and the parser accept the
 * same texts, on every case and on generated texts.
 */
import { describe, expect, it } from "vitest";
import {
  ANY_ITEM,
  ANY_KEY,
  FieldPathError,
  PointerError,
  expand,
  fromPointer,
  isFieldPath,
  isFieldPathPattern,
  parseFieldPath,
  parseFieldPathPattern,
  printFieldPath,
  toPointer,
  type PatternSegment,
  type Segment,
} from "../src/field-path.js";
import { ADDRESSING_ID, PROPERTY_PATH } from "../src/resources.js";
import { suite } from "./support/conformance.js";

const SUITE = suite("field-paths.yml");

interface ParseCase {
  readonly id: string;
  readonly text: string;
  readonly segments: unknown[];
  readonly printed: string;
}

interface Rejection {
  readonly id: string;
  readonly text: string;
  readonly reason: string;
  readonly offset: number;
}

interface PointerCase {
  readonly id: string;
  readonly segments?: Segment[];
  readonly pointer: string;
  readonly document?: unknown;
  readonly path?: string;
  readonly reason?: string;
  readonly offset?: number;
}

interface ExpansionCase {
  readonly id: string;
  readonly pattern: string;
  readonly document: unknown;
  readonly paths: string[];
}

const PATHS = SUITE["paths"] as ParseCase[];
const INVALID_PATHS = SUITE["invalid-paths"] as Rejection[];
const PATTERNS = SUITE["patterns"] as ParseCase[];
const INVALID_PATTERNS = SUITE["invalid-patterns"] as Rejection[];
const TO_POINTER = SUITE["to-pointer"] as PointerCase[];
const FROM_POINTER = SUITE["from-pointer"] as PointerCase[];
const PROPERTY_PATHS = SUITE["property-paths"] as string[];
const EXPANSIONS = SUITE["expansions"] as ExpansionCase[];

/** Returns the segments of a case, each wildcard written as {any: item} or {any: key}. */
function segments(written: unknown[]): PatternSegment[] {
  return written.map((item) =>
    typeof item === "object" && item !== null
      ? (item as { any: string }).any === "item"
        ? ANY_ITEM
        : ANY_KEY
      : (item as Segment),
  );
}

/** Returns the error that a function throws, `null` when it returns. */
function thrown(run: () => unknown): unknown {
  try {
    run();
    return null;
  } catch (error) {
    return error;
  }
}

function accepts(parse: (text: string) => unknown, text: string): boolean {
  return !(thrown(() => parse(text)) instanceof FieldPathError);
}

describe("the suite of the field paths", () => {
  it("names the resource and its definitions", () => {
    expect(SUITE["resource"]).toBe(ADDRESSING_ID);
    expect(SUITE["definitions"]).toEqual({ path: "field-path", pattern: "field-path-pattern" });
  });
});

describe.each(PATHS)("the path $id", (path) => {
  it("parses into its segments and prints in its canonical form", () => {
    const parsed = parseFieldPath(path.text);
    expect(parsed).toEqual(path.segments);
    expect(printFieldPath(parsed)).toBe(path.printed);
    expect(parseFieldPath(path.printed)).toEqual(path.segments);
  });
});

describe.each(INVALID_PATHS)("the invalid path $id", (rejection) => {
  it("fails with its reason at its offset", () => {
    const error = thrown(() => parseFieldPath(rejection.text));
    expect(error).toBeInstanceOf(FieldPathError);
    const { reason, offset } = error as FieldPathError;
    expect({ reason, offset }).toEqual({ reason: rejection.reason, offset: rejection.offset });
  });
});

describe.each(PATTERNS)("the pattern $id", (pattern) => {
  it("parses into its segments and prints in its canonical form", () => {
    const parsed = parseFieldPathPattern(pattern.text);
    expect(parsed).toEqual(segments(pattern.segments));
    expect(printFieldPath(parsed)).toBe(pattern.printed);
  });
});

describe.each(INVALID_PATTERNS)("the invalid pattern $id", (rejection) => {
  it("fails with its reason at its offset", () => {
    const error = thrown(() => parseFieldPathPattern(rejection.text));
    expect(error).toBeInstanceOf(FieldPathError);
    const { reason, offset } = error as FieldPathError;
    expect({ reason, offset }).toEqual({ reason: rejection.reason, offset: rejection.offset });
  });
});

const TEXTS = [
  ...new Set([
    ...[...PATHS, ...PATTERNS].flatMap((parse) => [parse.text, parse.printed]),
    ...[...INVALID_PATHS, ...INVALID_PATTERNS].map((rejection) => rejection.text),
    ...EXPANSIONS.map((expansion) => expansion.pattern),
    ...FROM_POINTER.flatMap((vector) => (vector.path === undefined ? [] : [vector.path])),
  ]),
];

describe("the patterns of the resource", () => {
  it.each(TEXTS)("accept %j exactly when the parsers accept it", (text) => {
    expect(isFieldPath(text)).toBe(accepts(parseFieldPath, text));
    expect(isFieldPathPattern(text)).toBe(accepts(parseFieldPathPattern, text));
  });

  it("agree with the parsers on generated texts", () => {
    const alphabet = [
      ..."a0159.[]\"\\*-u/~ 'tbnfA",
      "\t",
      String.fromCharCode(0xa0),
      String.fromCharCode(0x2028),
      "é",
      String.fromCodePoint(0x1d6fc),
    ];
    // A linear congruential generator with a fixed seed, so that each run draws the same texts.
    let seed = 8;
    const draw = (bound: number): number => {
      seed = (seed * 1103515245 + 12345) % 2147483648;
      return seed % bound;
    };
    for (let count = 0; count < 20000; count += 1) {
      const length = draw(10);
      const text = Array.from({ length }, () => alphabet[draw(alphabet.length)]).join("");
      expect([text, isFieldPath(text)]).toEqual([text, accepts(parseFieldPath, text)]);
      expect([text, isFieldPathPattern(text)]).toEqual([
        text,
        accepts(parseFieldPathPattern, text),
      ]);
    }
  });
});

describe.each(PROPERTY_PATHS)("the property path %s", (path) => {
  it("is a field path of the same meaning", () => {
    expect(PROPERTY_PATH.test(path)).toBe(true);
    expect(parseFieldPath(path)).toEqual(path.split("."));
    expect(printFieldPath(parseFieldPath(path))).toBe(path);
  });
});

describe.each(TO_POINTER)("the conversion to a pointer $id", (vector) => {
  it("writes each segment as a token", () => {
    expect(toPointer(vector.segments ?? [])).toBe(vector.pointer);
  });
});

describe.each(FROM_POINTER)("the conversion from a pointer $id", (vector) => {
  it("yields the field path, or fails with its reason at its offset", () => {
    if (vector.reason !== undefined) {
      const error = thrown(() => fromPointer(vector.pointer, vector.document));
      expect(error).toBeInstanceOf(PointerError);
      const { reason, offset } = error as PointerError;
      expect({ reason, offset }).toEqual({ reason: vector.reason, offset: vector.offset });
    } else {
      const path = fromPointer(vector.pointer, vector.document);
      expect(printFieldPath(path)).toBe(vector.path);
      expect(toPointer(path)).toBe(vector.pointer);
    }
  });
});

describe.each(EXPANSIONS)("the expansion $id", (expansion) => {
  it("lists the field paths of the named nodes in document order", () => {
    const paths = expand(parseFieldPathPattern(expansion.pattern), expansion.document);
    expect(paths.map((path) => printFieldPath(path))).toEqual(expansion.paths);
  });
});

describe("the segments outside the conformance cases", () => {
  it("print a lone surrogate bare, and as an escape inside a quoted key", () => {
    const surrogate = String.fromCharCode(0xd800);
    expect(printFieldPath([surrogate])).toBe(surrogate);
    const printed = printFieldPath([`a ${surrogate}`]);
    expect(printed).toBe(`["a \\ud800"]`);
    expect(parseFieldPath(printed)).toEqual([`a ${surrogate}`]);
  });

  it.each([[-1], [1e15], [1.5], [Number.NaN]])("refuse the position %s", (position) => {
    expect(() => printFieldPath(["a", position])).toThrow(RangeError);
    expect(() => toPointer(["a", position])).toThrow(RangeError);
  });
});
