/**
 * Key paths: the values of a document that one schema node describes, and their JSON Pointers.
 *
 * A key path grows through three keywords of a schema: `properties`, whose names form its steps,
 * `items`, whose step names every item of an array from a position on, and
 * `additionalProperties`, whose step names every value of a mapping under a key that the sibling
 * `properties` does not declare.
 */
import { isMapping } from "./documents/text.js";

/** The step from a mapping to the value of one of its keys. */
export interface PropertyStep {
  readonly kind: "property";
  readonly name: string;
}

/** The step from an array to each of its items, from the position `start` on. */
export interface ItemsStep {
  readonly kind: "items";
  readonly start: number;
}

/** The step from a mapping to each value under a key outside `declared`. */
export interface ValuesStep {
  readonly kind: "values";
  readonly declared: ReadonlySet<string>;
}

/** One step of a key path. */
export type Step = PropertyStep | ItemsStep | ValuesStep;

/** A key path, from the root of a document. */
export type KeyPath = readonly Step[];

/** Returns the JSON Pointer of a sequence of keys, escaping `~` and then `/` in each key. */
export function pointer(...keys: readonly (string | number)[]): string {
  return keys.map((key) => `/${String(key).replace(/~/g, "~0").replace(/\//g, "~1")}`).join("");
}

/** A value of a document at a key path, with the keys leading to it. */
export interface Located {
  readonly keys: readonly (string | number)[];
  readonly value: unknown;
}

/** Returns each value of a document at a key path, in the order of the document. */
export function valuesAt(data: unknown, path: KeyPath): Located[] {
  const [step, ...rest] = path;
  if (step === undefined) return [{ keys: [], value: data }];
  const below = (key: string | number, value: unknown): Located[] =>
    valuesAt(value, rest).map((found) => ({ keys: [key, ...found.keys], value: found.value }));
  switch (step.kind) {
    case "property":
      return isMapping(data) && Object.prototype.hasOwnProperty.call(data, step.name)
        ? below(step.name, data[step.name])
        : [];
    case "items":
      return Array.isArray(data)
        ? data.slice(step.start).flatMap((item: unknown, index) => below(step.start + index, item))
        : [];
    case "values":
      return isMapping(data)
        ? Object.entries(data).flatMap(([name, item]) =>
            step.declared.has(name) ? [] : below(name, item),
          )
        : [];
  }
}

/** Returns the value at a path of property names, `undefined` when a key is absent. */
export function valueAt(data: unknown, names: readonly string[]): unknown {
  let node = data;
  for (const name of names) {
    if (!isMapping(node) || !Object.prototype.hasOwnProperty.call(node, name)) return undefined;
    node = node[name];
  }
  return node;
}

/** Returns the key path of a path of property names. */
export function properties(names: readonly string[]): KeyPath {
  return names.map((name) => ({ kind: "property", name }));
}

/** Returns a string identifying a key path, equal for equal paths. */
export function pathKey(path: KeyPath): string {
  return JSON.stringify(
    path.map((step) =>
      step.kind === "property"
        ? ["p", step.name]
        : step.kind === "items"
          ? ["i", step.start]
          : ["v", [...step.declared].sort()],
    ),
  );
}
