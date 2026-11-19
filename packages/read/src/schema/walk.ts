/**
 * The walk of a schema: each node, with the key path of the values of a record that it describes.
 *
 * The path grows through `properties`, `items` and `additionalProperties`. The walk also enters
 * the subschemas of `allOf`, `anyOf` and `oneOf`, which describe the same value as their schema,
 * and every `$ref`, resolved through the schema loader. Under any other applicator, such as `not`
 * or `patternProperties`, a node describes no value of a single key path, so the walk visits it
 * without a path. The walk mirrors `anagraphe_read._core.schemas.SchemaReader.walk` of the Python read
 * side, node for node and in the same order.
 */
import { isMapping } from "../documents/text.js";
import { pointer, type KeyPath, type Step } from "../key-path.js";
import type { LoadedSchema } from "../ports.js";

/** The keywords whose subschemas describe the same value as their schema. */
const COMPOSITIONS = ["allOf", "anyOf", "oneOf"] as const;
/** The compositions whose subschemas describe the value only when it matches them. */
const CONDITIONAL = new Set<string>(["anyOf", "oneOf"]);
/** The applicators other than `properties` and the compositions, in the order of the walk. */
const APPLICATORS = [
  "items",
  "prefixItems",
  "contains",
  "additionalProperties",
  "patternProperties",
  "propertyNames",
  "unevaluatedProperties",
  "unevaluatedItems",
  "dependentSchemas",
  "if",
  "then",
  "else",
  "not",
] as const;

/** The kind of problem of a `$ref` naming no readable schema node. */
export const UNRESOLVED_REFERENCE = "unresolved-schema-reference";

type Mapping = Readonly<Record<string, unknown>>;

/** A node of a schema, with the values of a record that it describes. */
export interface SchemaNode {
  readonly value: Mapping;
  /** The key of the document holding the node. */
  readonly document: string;
  /** The JSON Pointer of the node in its document. */
  readonly at: string;
  /** The key path of the values that the node describes; `null` under another applicator. */
  readonly path: KeyPath | null;
  /** Whether the walk crossed `anyOf` or `oneOf` since the last step of the path. */
  readonly conditional: boolean;
}

/** A defect of a schema met by a walk: its kind, its document, its node, and why. */
export interface SchemaProblem {
  readonly kind: string;
  readonly document: string;
  /** The JSON Pointer of the offending node; empty for the whole document. */
  readonly pointer: string;
  readonly detail: string;
}

/** Records a problem once, comparing every field. */
export function record(problems: SchemaProblem[], problem: SchemaProblem): void {
  const known = problems.some(
    (other) =>
      other.kind === problem.kind &&
      other.document === problem.document &&
      other.pointer === problem.pointer &&
      other.detail === problem.detail,
  );
  if (!known) problems.push(problem);
}

const extend = (path: KeyPath | null, step: Step): KeyPath | null =>
  path === null ? null : [...path, step];

/**
 * Returns every node reached from the root of a schema, the root first. A `$ref` whose address,
 * its part before `#`, lies in `opaque` is not followed. A recursive schema stops where it
 * re-enters a node. A `$ref` naming no readable node is recorded in `problems`.
 */
export function walkSchema(
  schema: LoadedSchema,
  opaque: ReadonlySet<string>,
  problems: SchemaProblem[],
): SchemaNode[] {
  const root = schema.document(schema.root);
  if (!isMapping(root)) return [];
  const nodes: SchemaNode[] = [];

  const child = (
    parent: SchemaNode,
    value: unknown,
    at: string,
    path: KeyPath | null,
    conditional: boolean,
    stack: ReadonlySet<string>,
  ): void => {
    if (isMapping(value)) {
      walk({ value, document: parent.document, at: parent.at + at, path, conditional }, stack);
    }
  };

  const applicator = (node: SchemaNode, keyword: string, stack: ReadonlySet<string>): void => {
    const value = node.value[keyword];
    const at = pointer(keyword);
    if (keyword === "items" && isMapping(value)) {
      const prefix = node.value["prefixItems"];
      const start = Array.isArray(prefix) ? prefix.length : 0;
      child(node, value, at, extend(node.path, { kind: "items", start }), false, stack);
    } else if (keyword === "additionalProperties" && isMapping(value)) {
      const properties = node.value["properties"];
      const declared = new Set(isMapping(properties) ? Object.keys(properties) : []);
      child(node, value, at, extend(node.path, { kind: "values", declared }), false, stack);
    } else if (Array.isArray(value)) {
      value.forEach((item: unknown, index) =>
        child(node, item, at + pointer(index), null, false, stack),
      );
    } else if (
      isMapping(value) &&
      (keyword === "patternProperties" || keyword === "dependentSchemas")
    ) {
      for (const [name, item] of Object.entries(value)) {
        child(node, item, at + pointer(name), null, false, stack);
      }
    } else {
      child(node, value, at, null, false, stack);
    }
  };

  const walk = (node: SchemaNode, stack: ReadonlySet<string>): void => {
    const identity = JSON.stringify([node.document, node.at]);
    if (stack.has(identity)) return;
    const inner = new Set(stack).add(identity);
    nodes.push(node);
    for (const keyword of COMPOSITIONS) {
      const subschemas = node.value[keyword];
      if (!Array.isArray(subschemas)) continue;
      subschemas.forEach((subschema: unknown, index) =>
        child(
          node,
          subschema,
          pointer(keyword, index),
          node.path,
          node.conditional || CONDITIONAL.has(keyword),
          inner,
        ),
      );
    }
    const properties = node.value["properties"];
    if (isMapping(properties)) {
      for (const [name, subschema] of Object.entries(properties)) {
        child(
          node,
          subschema,
          pointer("properties", name),
          extend(node.path, { kind: "property", name }),
          false,
          inner,
        );
      }
    }
    for (const keyword of APPLICATORS) applicator(node, keyword, inner);
    const reference = node.value["$ref"];
    if (typeof reference === "string" && !opaque.has(reference.split("#")[0] ?? "")) {
      const target = resolve(schema, reference, node, problems);
      if (target !== null)
        walk({ ...target, path: node.path, conditional: node.conditional }, inner);
    }
  };

  walk({ value: root, document: schema.root, at: "", path: [], conditional: false }, new Set());
  return nodes;
}

/** Decodes the percent-escapes of a fragment, leaving a malformed escape as written. */
function unquote(fragment: string): string {
  try {
    return decodeURIComponent(fragment);
  } catch {
    return fragment;
  }
}

/**
 * Returns the node named by a `$ref`, with its document and its pointer, `null` after recording
 * why the reference names no readable node.
 */
function resolve(
  schema: LoadedSchema,
  reference: string,
  node: SchemaNode,
  problems: SchemaProblem[],
): { readonly value: Mapping; readonly document: string; readonly at: string } | null {
  const hash = reference.indexOf("#");
  const address = hash === -1 ? reference : reference.slice(0, hash);
  const fragment = unquote(hash === -1 ? "" : reference.slice(hash + 1));
  const unresolved = (detail: string): null => {
    record(problems, {
      kind: UNRESOLVED_REFERENCE,
      document: node.document,
      pointer: node.at + pointer("$ref"),
      detail,
    });
    return null;
  };
  const document = address === "" ? node.document : schema.locate(address, node.document);
  if (document === null) return unresolved(`${reference} names no readable schema`);
  let value = schema.document(document);
  if (value === undefined) return unresolved(`${reference} names no readable schema: ${document}`);
  for (const part of fragment.split("/").filter((segment) => segment !== "")) {
    const key = part.replace(/~1/g, "/").replace(/~0/g, "~");
    if (isMapping(value) && Object.prototype.hasOwnProperty.call(value, key)) {
      value = value[key];
    } else if (Array.isArray(value) && /^[0-9]+$/.test(key) && Number(key) < value.length) {
      value = value[Number(key)] as unknown;
    } else {
      return unresolved(`${reference} names no node of ${document}`);
    }
  }
  return isMapping(value) ? { value, document, at: fragment } : null;
}
