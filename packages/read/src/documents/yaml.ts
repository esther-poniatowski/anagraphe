/**
 * The reading of a YAML text as the Python read side reads it, through `yaml.safe_load` of PyYAML.
 *
 * PyYAML follows YAML 1.1 with its own implicit resolvers, which the YAML 1.1 schema of the
 * package `yaml` does not reproduce: that schema reads `y` as a boolean, `09` and `1e3` as
 * numbers, whereas PyYAML reads the three as strings. The plain scalars are therefore resolved
 * here by the patterns and the constructors of PyYAML, in the order of its resolvers: null,
 * boolean, float, integer, timestamp and `=`, which PyYAML refuses to construct.
 *
 * A timestamp is read as a `Date`, as PyYAML constructs a date, or as the string that it writes
 * when the caller asks for it, as the record registry reads its dates. A day absent from the
 * calendar fails a reading of dates, where PyYAML raises.
 */
import { parseDocument, type ScalarTag, type Tags } from "yaml";

/** How a reading returns its timestamps and its integers. */
export interface YamlOptions {
  /** A timestamp as a `Date`, by default, or as the string that it writes. */
  readonly timestamps?: "date" | "string";
  /**
   * An integer as a `number`, by default, or as a `bigint`, so that a caller tells the integer
   * `1` from the float `1.0`, as Python does.
   */
  readonly integers?: "number" | "bigint";
}

/** The outcome of reading a YAML text. */
export type YamlReading =
  | {
      readonly ok: true;
      readonly value: unknown;
      /**
       * The JSON Pointers of the mappings holding a key that YAML reads as no string, such as
       * `2024:`; each key is converted to the string that Python writes for it.
       */
      readonly nonStringKeys: readonly string[];
    }
  | { readonly ok: false; readonly error: string };

const NULL = /^(?:~|null|Null|NULL|)$/;
const BOOL = /^(?:yes|Yes|YES|no|No|NO|true|True|TRUE|false|False|FALSE|on|On|ON|off|Off|OFF)$/;
const FLOAT =
  /^(?:[-+]?(?:[0-9][0-9_]*)\.[0-9_]*(?:[eE][-+][0-9]+)?|\.[0-9][0-9_]*(?:[eE][-+][0-9]+)?|[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\.[0-9_]*|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$/;
const INT =
  /^(?:[-+]?0b[0-1_]+|[-+]?0[0-7_]+|[-+]?(?:0|[1-9][0-9_]*)|[-+]?0x[0-9a-fA-F_]+|[-+]?[1-9][0-9_]*(?::[0-5]?[0-9])+)$/;
const TIMESTAMP =
  /^(?:[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]|[0-9][0-9][0-9][0-9]-[0-9][0-9]?-[0-9][0-9]?(?:[Tt]|[ \t]+)[0-9][0-9]?:[0-9][0-9]:[0-9][0-9](?:\.[0-9]*)?(?:[ \t]*(?:Z|[-+][0-9][0-9]?(?::[0-9][0-9])?))?)$/;
const TIMESTAMP_PARTS =
  /^([0-9]{4})-([0-9]{1,2})-([0-9]{1,2})(?:(?:[Tt]|[ \t]+)([0-9]{1,2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]*))?(?:[ \t]*(Z|([-+])([0-9]{1,2})(?::([0-9]{2}))?))?)?$/;

/** Returns the signed digits of a number, with its underscores removed, as PyYAML reads them. */
function signed(text: string): [sign: number, digits: string] {
  const value = text.replace(/_/g, "");
  if (value.startsWith("-")) return [-1, value.slice(1)];
  return [1, value.startsWith("+") ? value.slice(1) : value];
}

/** Returns the value of sexagesimal digits `a:b:c`, the parts read by `read`. */
function sexagesimal(digits: string, read: (part: string) => number): number {
  return digits.split(":").reduce((total, part) => total * 60 + read(part), 0);
}

/** Reads an integer as `construct_yaml_int` of PyYAML. */
function integer(text: string): number {
  const [sign, digits] = signed(text);
  if (digits === "0") return 0;
  if (digits.startsWith("0b")) return sign * parseInt(digits.slice(2), 2);
  if (digits.startsWith("0x")) return sign * parseInt(digits.slice(2), 16);
  if (digits.includes(":")) return sign * sexagesimal(digits, (part) => parseInt(part, 10));
  if (digits.startsWith("0")) return sign * parseInt(digits, 8);
  return sign * parseInt(digits, 10);
}

/** Reads a float as `construct_yaml_float` of PyYAML. */
function float(text: string): number {
  const [sign, digits] = signed(text.toLowerCase());
  if (digits === ".inf") return sign * Infinity;
  if (digits === ".nan") return NaN;
  if (digits.includes(":")) return sign * sexagesimal(digits, Number);
  return sign * Number(digits);
}

/** Whether a day exists in the proleptic Gregorian calendar, as `datetime.date` requires. */
export function isDay(year: number, month: number, day: number): boolean {
  const leap = (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return year >= 1 && day >= 1 && day <= (days[month - 1] ?? 0);
}

/**
 * Reads a timestamp as `construct_yaml_timestamp` of PyYAML, `null` when PyYAML raises for a
 * date, a time or an offset out of range.
 */
function timestamp(text: string): Date | null {
  const parts = TIMESTAMP_PARTS.exec(text);
  if (parts === null) return null;
  const [, y, mo, d, h, mi, s, fraction, zone, zoneSign, zoneHour, zoneMinute] = parts;
  const [year, month, day] = [Number(y), Number(mo), Number(d)];
  if (!isDay(year, month, day)) return null;
  if (h === undefined) return new Date(Date.UTC(year, month - 1, day));
  const [hour, minute, second] = [Number(h), Number(mi), Number(s)];
  if (hour > 23 || minute > 59 || second > 59) return null;
  const offset =
    zone === undefined || zone === "Z"
      ? 0
      : (zoneSign === "-" ? -1 : 1) * (Number(zoneHour) * 60 + Number(zoneMinute ?? "0"));
  if (Math.abs(offset) >= 24 * 60) return null;
  const milliseconds = Math.floor(Number(`0.${(fraction ?? "").slice(0, 6) || "0"}`) * 1000);
  return new Date(
    Date.UTC(year, month - 1, day, hour, minute, second, milliseconds) - offset * 60_000,
  );
}

/** A scalar tag resolved by a pattern of PyYAML. */
function scalarTag(
  tag: string,
  test: RegExp,
  resolve: (text: string, onError: (message: string) => void) => unknown,
): ScalarTag {
  return { tag: `tag:yaml.org,2002:${tag}`, default: true, test, resolve };
}

/** The scalar tags of PyYAML, for a reading that returns its values as `options` asks. */
function pythonScalars(options: YamlOptions): ScalarTag[] {
  return [
    scalarTag("null", NULL, () => null),
    scalarTag("bool", BOOL, (text) => ["yes", "true", "on"].includes(text.toLowerCase())),
    scalarTag("float", FLOAT, float),
    scalarTag("int", INT, (text) =>
      options.integers === "bigint" ? BigInt(integer(text)) : integer(text),
    ),
    scalarTag("timestamp", TIMESTAMP, (text, onError) => {
      if (options.timestamps === "string") return text;
      const value = timestamp(text);
      if (value === null) onError(`the timestamp ${text} names no moment of the calendar`);
      return value;
    }),
    scalarTag("value", /^=$/, (_, onError) => {
      onError("the plain scalar = has no constructor in a safe reading");
      return "=";
    }),
  ];
}

/** The tags of the YAML 1.1 schema kept beside the scalars of PyYAML: collections and strings. */
const KEPT = new Set(
  ["map", "seq", "str", "binary", "merge", "omap", "pairs", "set"].map(
    (name) => `tag:yaml.org,2002:${name}`,
  ),
);

/** Raised for a key that is a mapping or a sequence, which PyYAML refuses as unhashable. */
class UnhashableKey extends Error {}

/** Returns the string that Python writes for a scalar key of a mapping. */
function pythonKey(key: unknown): string {
  if (key === true) return "True";
  if (key === false) return "False";
  if (key === null || key === undefined) return "None";
  if (key instanceof Date) return key.toISOString();
  if (typeof key === "string" || typeof key === "number" || typeof key === "bigint") {
    return String(key);
  }
  throw new UnhashableKey("found unhashable key");
}

/** Escapes a key as a token of a JSON Pointer. */
function token(key: string): string {
  return key.replace(/~/g, "~0").replace(/\//g, "~1");
}

/** Converts the maps of a value into objects, recording the mappings holding a non-string key. */
function plain(value: unknown, at: string, nonStringKeys: string[]): unknown {
  if (value instanceof Map) {
    const object: Record<string, unknown> = {};
    let recorded = false;
    for (const [key, item] of value as Map<unknown, unknown>) {
      if (typeof key !== "string" && !recorded) {
        nonStringKeys.push(at);
        recorded = true;
      }
      const name = pythonKey(key);
      // A key such as __proto__ stays an own key, as in a Python mapping.
      Object.defineProperty(object, name, {
        value: plain(item, `${at}/${token(name)}`, nonStringKeys),
        enumerable: true,
        writable: true,
        configurable: true,
      });
    }
    return object;
  }
  if (Array.isArray(value)) {
    return value.map((item: unknown, index) => plain(item, `${at}/${index}`, nonStringKeys));
  }
  return value;
}

/**
 * Reads a YAML text as `yaml.safe_load` of PyYAML reads it: an empty text reads as `null`, and a
 * text holding several documents fails.
 */
export function readYaml(text: string, options: YamlOptions = {}): YamlReading {
  const document = parseDocument(text, {
    version: "1.1",
    uniqueKeys: false,
    customTags: (tags: Tags): Tags => [
      // The base tags of the YAML 1.1 schema are objects; a name would select a tag by name.
      ...tags.filter((tag) => typeof tag !== "string" && KEPT.has(tag.tag)),
      ...pythonScalars(options),
    ],
  });
  const [error] = document.errors;
  if (error !== undefined) return { ok: false, error: error.message.split("\n")[0] ?? "" };
  const nonStringKeys: string[] = [];
  try {
    const value = plain(document.toJS({ mapAsMap: true }), "", nonStringKeys);
    return { ok: true, value, nonStringKeys };
  } catch (error) {
    if (error instanceof UnhashableKey) return { ok: false, error: error.message };
    throw error;
  }
}
