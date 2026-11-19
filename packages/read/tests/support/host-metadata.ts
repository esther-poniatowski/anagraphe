/**
 * The adapters by which a host supplies the metadata of its files to the read side: the selection
 * of the metadata source of a file from the rules `{when, from}` of the section `metadata` of
 * `anagraphe.yml`, and a TOML parser.
 *
 * The conditions of a rule hold the keys `types`, the suffixes of a file, and `paths`, read here as
 * exact repository paths, which is all that the conformance cases write. The TOML parser reads the
 * subset of TOML that the cases write: table headers and string values.
 */
import { isMapping } from "../../src/documents/text.js";
import { builtInSource, type MetadataKind, type MetadataSource } from "../../src/metadata.js";

/** Whether a condition `{types, paths}` of a rule holds for a file. */
function holds(condition: unknown, path: string): boolean {
  if (!isMapping(condition)) return true;
  const types = condition["types"];
  const paths = condition["paths"];
  const typed = !Array.isArray(types) || types.some((type) => path.endsWith(`.${String(type)}`));
  const placed =
    !Array.isArray(paths) || paths.some((pattern) => String(pattern).replace(/^\//, "") === path);
  return typed && placed;
}

/** Returns the source named by a value `from`: a kind alone, or a kind with its key paths. */
function sourceOf(value: unknown): MetadataSource {
  if (value === "frontmatter") return { kind: "frontmatter", at: ["."] };
  if (value === "none") return { kind: "none", at: [] };
  if (!isMapping(value)) throw new Error(`no metadata source: ${String(value)}`);
  const [kind, paths] = Object.entries(value)[0] ?? [];
  const listed = Array.isArray(paths) ? paths.map(String) : [String(paths)];
  return { kind: kind as MetadataKind, at: listed };
}

/**
 * Returns the selection of the metadata source of a file: the source of the last rule whose
 * condition holds, after the built-in sources.
 */
export function ruleSources(rules: readonly unknown[]): (path: string) => MetadataSource {
  return (path) => {
    let source = builtInSource(path);
    for (const rule of rules) {
      if (isMapping(rule) && holds(rule["when"], path)) source = sourceOf(rule["from"]);
    }
    return source;
  };
}

/** Parses the subset of TOML that the cases write: table headers and string values. */
export function parseToml(text: string): unknown {
  const document: Record<string, unknown> = {};
  let table = document;
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (line === "" || line.startsWith("#")) continue;
    const header = /^\[([A-Za-z0-9_.-]+)\]$/.exec(line);
    if (header?.[1] !== undefined) {
      table = document;
      for (const key of header[1].split(".")) {
        const next = table[key];
        table[key] = isMapping(next) ? next : {};
        table = table[key] as Record<string, unknown>;
      }
      continue;
    }
    const pair = /^([A-Za-z0-9_-]+)\s*=\s*"([^"]*)"$/.exec(line);
    if (pair?.[1] === undefined) throw new Error(`unsupported TOML line: ${line}`);
    table[pair[1]] = pair[2];
  }
  return document;
}
