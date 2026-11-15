/**
 * The declarations that the schema of a contract makes for the logical targets, read from the
 * nodes of its walk:
 *
 * - `x-identifier` on a node of the root, reached through `allOf` and `$ref`, names the field
 *   holding the identifier of the record, as a dotted path of property names; the first
 *   declaration in the order of the walk applies;
 * - `x-identifier` on a definition reached as the items of an array names the field holding the
 *   identifier of each item, and makes each item a unit of the record;
 * - a `$ref` equal to the URI of the definition `target` makes its value a target field, and
 *   `x-target-contract` on a node of the same key path lists the contracts that its record must
 *   satisfy;
 * - `x-implements` on a node of the root names the contracts that the records also implement.
 *
 * A node reached through `anyOf` or `oneOf` describes only the values matching its branch, so its
 * `x-identifier` is not read, and a value of its target field is a target only when it is a
 * mapping.
 */
import { pathKey, pointer, properties, type KeyPath } from "../key-path.js";
import type { LoadedSchema } from "../ports.js";
import { ADDRESSING_ID, PROPERTY_PATH, TARGET_REFERENCE } from "../resources.js";
import { readContracts } from "../target.js";
import { record, walkSchema, type SchemaNode, type SchemaProblem } from "./walk.js";

/** The keyword naming the field of an identifier. */
export const IDENTIFIER = "x-identifier";
/** The keyword typing a target field by the contracts of its record. */
export const TARGET_CONTRACT = "x-target-contract";
/** The keyword naming the contracts that a root schema implements. */
export const IMPLEMENTS = "x-implements";
/** The kind of problem of an invalid `x-identifier`. */
export const INVALID_IDENTIFIER_DECLARATION = "invalid-identifier-declaration";
/** The kind of problem of an invalid `x-target-contract`. */
export const INVALID_TARGET_CONTRACT = "invalid-target-contract";

/** A field of a record whose values are logical targets. */
export interface TargetField {
  readonly path: KeyPath;
  /**
   * Whether every node reaching the definition does so through `anyOf` or `oneOf`, so that a value
   * is a target only when it is a mapping.
   */
  readonly conditional: boolean;
  /** The valid declarations of `x-target-contract` at the key path of the field. */
  readonly contracts: readonly (readonly string[])[];
}

/** The items of an array of a record that form its units, with the field of their identifier. */
export interface UnitDeclaration {
  /** The key path of the items, its last step naming every item. */
  readonly path: KeyPath;
  readonly identifier: readonly string[];
}

/** What the schema of one contract declares for the targets. */
export interface Declarations {
  /** The field of the identifier of a record; `null` when the default applies. */
  readonly identifier: readonly string[] | null;
  readonly units: readonly UnitDeclaration[];
  readonly targets: readonly TargetField[];
  /** The contracts named by `x-implements` at the root. */
  readonly implements: readonly string[];
  /** The invalid declarations and the unresolved references met, each once. */
  readonly problems: readonly SchemaProblem[];
}

/** Reads the declarations of a schema from the nodes of its walk. */
export function readDeclarations(schema: LoadedSchema): Declarations {
  const problems: SchemaProblem[] = [];
  const nodes = walkSchema(schema, new Set([ADDRESSING_ID]), problems).filter(
    (node): node is SchemaNode & { readonly path: KeyPath } => node.path !== null,
  );
  const paths = new Set(nodes.map((node) => pathKey(node.path)));
  let identifier: readonly string[] | null = null;
  const units = new Map<string, UnitDeclaration>();
  const targets = new Map<string, { path: KeyPath; conditional: boolean }>();
  const contracts = new Map<string, (readonly string[])[]>();
  const implemented = new Set<string>();
  for (const node of nodes) {
    const { value, path } = node;
    const last = path[path.length - 1];
    if (IDENTIFIER in value && !node.conditional && (last === undefined || last.kind === "items")) {
      const segments = identifierField(node, paths, problems);
      if (segments !== null && last === undefined) identifier ??= segments;
      else if (segments !== null) {
        units.set(pathKey(path) + JSON.stringify(segments), { path, identifier: segments });
      }
    }
    if (TARGET_CONTRACT in value) {
      const reading = readContracts(value[TARGET_CONTRACT]);
      if (!reading.ok) {
        problem(problems, INVALID_TARGET_CONTRACT, node, TARGET_CONTRACT, reading.detail);
      } else {
        const known = contracts.get(pathKey(path)) ?? [];
        const entries = reading.entries;
        if (!known.some((other) => other.join("\n") === entries.join("\n"))) known.push(entries);
        contracts.set(pathKey(path), known);
      }
    }
    if (value["$ref"] === TARGET_REFERENCE) {
      const previous = targets.get(pathKey(path));
      targets.set(pathKey(path), {
        path,
        conditional: (previous?.conditional ?? true) && node.conditional,
      });
    }
    if (IMPLEMENTS in value && last === undefined && !node.conditional) {
      for (const name of names(value[IMPLEMENTS])) implemented.add(name);
    }
  }
  return {
    identifier,
    units: [...units.values()],
    targets: [...targets.entries()].map(([key, field]) => ({
      ...field,
      contracts: contracts.get(key) ?? [],
    })),
    implements: [...implemented],
    problems,
  };
}

/** Records an invalid declaration at a keyword of a node, once. */
function problem(
  problems: SchemaProblem[],
  kind: string,
  node: SchemaNode,
  keyword: string,
  detail: string,
): void {
  record(problems, { kind, document: node.document, pointer: node.at + pointer(keyword), detail });
}

/**
 * Returns the field named by the `x-identifier` of a node, `null` after recording why the
 * declaration is invalid: it is not a dotted path of property names, or names no property that the
 * walk reached.
 */
function identifierField(
  node: SchemaNode & { readonly path: KeyPath },
  paths: ReadonlySet<string>,
  problems: SchemaProblem[],
): readonly string[] | null {
  const value = node.value[IDENTIFIER];
  if (typeof value !== "string" || !PROPERTY_PATH.test(value)) {
    const written = JSON.stringify(value) ?? String(value);
    problem(
      problems,
      INVALID_IDENTIFIER_DECLARATION,
      node,
      IDENTIFIER,
      `${IDENTIFIER} ${written} is not a dotted path of property names, such as identity.id`,
    );
    return null;
  }
  const segments = value.split(".");
  if (!paths.has(pathKey([...node.path, ...properties(segments)]))) {
    problem(
      problems,
      INVALID_IDENTIFIER_DECLARATION,
      node,
      IDENTIFIER,
      `${IDENTIFIER} ${value} names no property of its schema`,
    );
    return null;
  }
  return segments;
}

/** Returns the contracts named by `x-implements`: a string, or a list of strings. */
function names(value: unknown): string[] {
  const items: unknown[] = typeof value === "string" ? [value] : Array.isArray(value) ? value : [];
  return items.filter((item): item is string => typeof item === "string");
}
