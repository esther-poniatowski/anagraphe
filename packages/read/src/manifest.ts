/**
 * The manifest of a repository, `repository.yml` at its root, which declares its identifier.
 *
 * The manifest names its format `_schema: anagraphe:repository@1`, and the contract fixes its
 * block `repository`: the identifier `id`, and the optional list `retired` of the former
 * identifiers, none of them reused. Every other root key stays open. During the migration, the
 * form `schema_version: 1` is still read, and reported.
 */
import { isMapping, universalNewlines } from "./documents/text.js";
import { readYaml } from "./documents/yaml.js";
import { pointer } from "./key-path.js";
import { REPOSITORY_CONTRACT } from "./resources.js";
import { violations } from "./validation.js";

/** The file of the manifest, at the root of the repository. */
export const MANIFEST_FILE = "repository.yml";
/** The key of the legacy form, whose only version is the integer 1. */
const LEGACY_KEY = "schema_version";

/** The kinds of defect of a manifest. */
export const INVALID_REPOSITORY_MANIFEST = "invalid-repository-manifest";
export const LEGACY_REPOSITORY_MANIFEST = "legacy-repository-manifest";

/** The identity of a repository, read from its manifest. */
export interface Manifest {
  readonly id: string;
  /** The former identifiers of the repository. */
  readonly retired: readonly string[];
  /** Whether the manifest is written in the legacy form `schema_version: 1`. */
  readonly legacy: boolean;
}

/** A defect of the manifest: its kind, the JSON Pointer of its key, and why. */
export interface ManifestProblem {
  readonly kind: typeof INVALID_REPOSITORY_MANIFEST | typeof LEGACY_REPOSITORY_MANIFEST;
  readonly pointer: string;
  readonly detail: string;
}

/** The manifest of a repository, `null` when it holds none or an invalid one, and its defects. */
export interface ManifestReading {
  readonly manifest: Manifest | null;
  readonly problems: readonly ManifestProblem[];
}

const invalid = (at: string, detail: string): ManifestReading => ({
  manifest: null,
  problems: [{ kind: INVALID_REPOSITORY_MANIFEST, pointer: at, detail }],
});

/** Returns a value whose integers are read as numbers, for the validation by the schema. */
function numbers(value: unknown): unknown {
  if (typeof value === "bigint") return Number(value);
  if (Array.isArray(value)) return value.map(numbers);
  if (isMapping(value)) {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, numbers(item)]));
  }
  return value;
}

/**
 * Reads the text of a manifest, `null` when the repository holds no `repository.yml`. A manifest
 * that violates the contract is reported and read as no manifest, so its repository declares no
 * identifier.
 */
export function readManifest(text: string | null): ManifestReading {
  if (text === null) return { manifest: null, problems: [] };
  const reading = readYaml(universalNewlines(text), { integers: "bigint" });
  if (!reading.ok) return invalid("", `${MANIFEST_FILE} cannot be parsed: ${reading.error}`);
  if (!isMapping(reading.value)) return invalid("", `${MANIFEST_FILE} is not a mapping`);
  const problems: ManifestProblem[] = [];
  let data: Readonly<Record<string, unknown>> = reading.value;
  const legacy = Object.prototype.hasOwnProperty.call(data, LEGACY_KEY);
  if (legacy) {
    if (Object.prototype.hasOwnProperty.call(data, "_schema")) {
      return invalid(
        pointer(LEGACY_KEY),
        `${MANIFEST_FILE} holds both _schema and ${LEGACY_KEY}; write _schema: ${REPOSITORY_CONTRACT} alone`,
      );
    }
    if (data[LEGACY_KEY] !== 1n) {
      return invalid(
        pointer(LEGACY_KEY),
        `${LEGACY_KEY}: ${String(data[LEGACY_KEY])} is no form of the manifest; write _schema: ${REPOSITORY_CONTRACT}`,
      );
    }
    problems.push({
      kind: LEGACY_REPOSITORY_MANIFEST,
      pointer: pointer(LEGACY_KEY),
      detail: `${MANIFEST_FILE} writes ${LEGACY_KEY}: 1; write _schema: ${REPOSITORY_CONTRACT}`,
    });
    const rest = Object.entries(data).filter(([key]) => key !== LEGACY_KEY);
    data = { _schema: REPOSITORY_CONTRACT, ...Object.fromEntries(rest) };
  }
  const found = violations("repository", numbers(data)).map(
    ({ pointer: at, message }): ManifestProblem => ({
      kind: INVALID_REPOSITORY_MANIFEST,
      pointer: at,
      detail: `${MANIFEST_FILE} violates ${REPOSITORY_CONTRACT}: ${message}`,
    }),
  );
  const repository = data["repository"];
  if (found.length === 0 && isMapping(repository)) {
    const id = repository["id"] as string;
    const retired = (Array.isArray(repository["retired"]) ? repository["retired"] : []) as string[];
    if (!retired.includes(id)) {
      return { manifest: { id, retired, legacy }, problems };
    }
    found.push({
      kind: INVALID_REPOSITORY_MANIFEST,
      pointer: pointer("repository", "retired"),
      detail: `repository.retired lists the current identifier ${id}, and a retired identifier is never reused`,
    });
  }
  return { manifest: null, problems: [...problems, ...found] };
}
