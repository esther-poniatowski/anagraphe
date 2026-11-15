/**
 * The conformance cases of Anagraphe, read from `specs/conformance/` at the root of the
 * repository, and the findings that the read side yields for a check case.
 *
 * A check case states the findings of the Python checker. The function {@link findings} derives
 * the same findings from the outcomes of the read side alone: the manifest reading, the
 * declarations of each schema of the registry, and the reading and the resolution of each record
 * through the live index. It names each outcome by the kind of its finding, and decides nothing.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { isMapping } from "../../src/documents/text.js";
import { readYaml } from "../../src/documents/yaml.js";
import { pointer, valuesAt } from "../../src/key-path.js";
import type { RepositoryIndex, Resolved, Duplicate } from "../../src/live-index.js";
import { MANIFEST_FILE } from "../../src/manifest.js";
import type { RecordReading } from "../../src/records.js";
import type { TargetField } from "../../src/schema/declarations.js";
import { readDeclarations } from "../../src/schema/declarations.js";
import { contractVerdict, readTarget } from "../../src/target.js";
import { MemoryFiles, RegistrySchemas, memoryIndex } from "./memory.js";

/** One finding: its file, its kind and its JSON Pointer. */
export type Finding = [file: string, kind: string, locus: string];

/** Reads a suite of conformance cases, as PyYAML reads it. */
export function suite(name: string): Record<string, unknown> {
  const path = fileURLToPath(new URL(`../../../../specs/conformance/${name}`, import.meta.url));
  const reading = readYaml(readFileSync(path, "utf-8"));
  if (!reading.ok || !isMapping(reading.value)) throw new Error(`${name} cannot be read`);
  return reading.value;
}

/** The fields of a check case, as the suites write them. */
export interface CheckCase {
  readonly id: string;
  readonly files: Record<string, string>;
  readonly remove?: readonly string[];
  readonly issues: readonly Finding[];
}

/** Returns the files of a case: the shared files, without those it removes, under its own. */
export function caseFiles(
  shared: Record<string, string>,
  check: CheckCase,
): Record<string, string> {
  const kept = Object.entries(shared).filter(([path]) => !(check.remove ?? []).includes(path));
  return { ...Object.fromEntries(kept), ...check.files };
}

/** Sorts findings as Python sorts lists of strings. */
export function sorted(issues: readonly Finding[]): Finding[] {
  const key = (issue: Finding): string => JSON.stringify(issue);
  return [...new Map(issues.map((issue) => [key(issue), issue])).values()].sort((a, b) => {
    for (let index = 0; index < 3; index += 1) {
      const [x, y] = [a[index] ?? "", b[index] ?? ""];
      if (x !== y) return x < y ? -1 : 1;
    }
    return 0;
  });
}

/**
 * Indexes every file of a repository, and returns the findings that its read outcomes name.
 *
 * @param registry The schema registry of Kleisis.
 * @param records The record registry, `null` when the repository declares none.
 */
export async function findings(
  files: Record<string, string>,
  registry: string,
  records: string | null,
): Promise<{ readonly index: RepositoryIndex; readonly issues: Finding[] }> {
  const memory = new MemoryFiles(files);
  const index = memoryIndex(memory, registry, records);
  await index.rebuild(Object.keys(files));
  const issues: Finding[] = index.manifest.problems.map((problem) => [
    MANIFEST_FILE,
    problem.kind,
    problem.pointer,
  ]);
  for (const path of Object.keys(files).sort()) {
    const record = index.record(path);
    if (record !== undefined) issues.push(...recordFindings(index, record));
  }
  issues.push(...(await schemaFindings(memory, registry)));
  return { index, issues: sorted(issues) };
}

/** Returns the findings of the declarations of every schema that the registry names. */
async function schemaFindings(files: MemoryFiles, registry: string): Promise<Finding[]> {
  const loader = new RegistrySchemas(files, registry);
  const text = files.files[registry];
  const reading = text === undefined ? null : readYaml(text);
  const schemas = reading?.ok === true && isMapping(reading.value) ? reading.value["schemas"] : {};
  const keys = Object.values(isMapping(schemas) ? schemas : {}).map(String);
  const findings: Finding[] = [];
  for (const key of keys) {
    const loading = await loader.load(key);
    if (loading.status === "failed") findings.push([key, "unreadable-schema", ""]);
    else {
      for (const problem of readDeclarations(loading.schema).problems) {
        findings.push([problem.document, problem.kind, problem.pointer]);
      }
    }
  }
  return findings;
}

/** Returns the findings of one record: its reading, its identifier, then its targets. */
function recordFindings(index: RepositoryIndex, record: RecordReading): Finding[] {
  if (record.problem !== null) return [[record.path, "unreadable-record", ""]];
  const issues: Finding[] = [];
  const { identifier } = record;
  if (identifier.status === "missing" || identifier.status === "invalid") {
    issues.push([record.path, `${identifier.status}-identifier`, identifier.pointer]);
  } else if (identifier.status === "valid" && index.pathsOf(identifier.value).length > 1) {
    issues.push([record.path, "duplicate-identifier", identifier.pointer]);
  }
  for (const field of record.declarations?.targets ?? []) {
    for (const { keys, value } of valuesAt(record.data, field.path)) {
      issues.push(...targetFindings(index, record.path, field, pointer(...keys), value));
    }
  }
  return issues;
}

/** Returns the findings of one value of a target field. */
function targetFindings(
  index: RepositoryIndex,
  path: string,
  field: TargetField,
  at: string,
  value: unknown,
): Finding[] {
  if (field.conditional && !isMapping(value)) return [];
  const reading = readTarget(value);
  if (!reading.ok) return [[path, "invalid-target", at]];
  const resolution = index.resolve(reading.target);
  switch (resolution.status) {
    case "unverified":
      return [[path, "unverified-target", at]];
    case "unknown":
      return [[path, "unknown-record", at]];
    case "retired":
      return [[path, "retired-target", at]];
    case "renamed":
      return [
        [path, "renamed-target", at],
        ...resolvedFindings(path, field, at, resolution.resolution),
      ];
    case "resolved":
    case "duplicate":
      return resolvedFindings(path, field, at, resolution);
    case "repository":
      return [];
  }
}

/** Returns the findings of a target whose record is found: its unit, then its contract. */
function resolvedFindings(
  path: string,
  field: TargetField,
  at: string,
  resolution: Resolved | Duplicate,
): Finding[] {
  if (resolution.status === "duplicate") return [];
  const issues: Finding[] = [];
  if (resolution.unit === "unknown-unit" || resolution.unit === "ambiguous-unit") {
    issues.push([path, resolution.unit, at]);
  }
  const verdict = contractVerdict(field.contracts, resolution.record.contracts);
  if (verdict.status === "unbound") issues.push([path, "unbound-target", at]);
  if (verdict.status === "mismatch") issues.push([path, "target-contract-mismatch", at]);
  return issues;
}
