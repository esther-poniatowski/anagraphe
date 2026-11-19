/**
 * The conformance cases of `specs/conformance/targets.yml`: every reading and every contract case,
 * and the check cases whose findings the read side yields.
 */
import { Ajv2020 } from "ajv/dist/2020.js";
import { describe, expect, it } from "vitest";
import { ADDRESSING_SCHEMA } from "../src/generated/resources.js";
import { deriveIdentity, readDeclaredIdentity } from "../src/identity.js";
import { ADDRESSING_ID } from "../src/resources.js";
import { admits, normalize, readTarget, sameTarget, written } from "../src/target.js";
import { caseFiles, findings, suite, type CheckCase } from "./support/conformance.js";

const SUITE = suite("targets.yml");

interface ReadingCase {
  readonly id: string;
  readonly value: unknown;
  readonly repository: string | null;
  readonly normalized?: Record<string, string>;
  readonly invalid?: string;
}

interface ContractCase {
  readonly id: string;
  readonly entries: string[];
  readonly contracts: string[];
  readonly admits: boolean;
}

const READINGS = SUITE["readings"] as ReadingCase[];
const CONTRACTS = SUITE["contracts"] as ContractCase[];
const CASES = SUITE["cases"] as (CheckCase & { readonly repository?: unknown })[];
const FILES = SUITE["files"] as Record<string, string>;
const FOLDER = SUITE["folder"] as string;

/** Returns the identifier of the root of a case, derived from its folder and its section. */
function identifier(check: { readonly repository?: unknown }): string | null {
  const section = check.repository === undefined ? SUITE["repository"] : check.repository;
  const declared = section === null ? null : readDeclaredIdentity(section);
  return deriveIdentity({ remote: null, folder: FOLDER, declared }).id;
}

/**
 * The check cases left out, each with the reason: the walk of the files of a repository, its
 * exclusions and its nested repositories belong to the host, which feeds the live index.
 */
const LEFT_OUT: Readonly<Record<string, string>> = {
  "nested-repository": "the host walks the files, and feeds no file of a nested repository",
  "retired-repository-manifest":
    "the host reads the root, and reports the manifest left there; the index never reads it",
  "retired-repository-manifest-of-a-lost-identity":
    "the host reads the root, and reports the manifest left there; the index never reads it",
  "unknown-repository":
    "the resolver of ADR 0009 reaches this package in the task record-reader-views",
  "unknown-repository-without-identity":
    "the resolver of ADR 0009 reaches this package in the task record-reader-views",
  "renamed-repository-of-the-root":
    "the resolver of ADR 0009 reaches this package in the task record-reader-views",
};

describe("the suite of the targets", () => {
  it("names the resource of the package", () => {
    expect(SUITE["resource"]).toEqual(ADDRESSING_ID);
  });
});

describe.each(READINGS)("the reading $id", (reading) => {
  it("states the reason of an invalid value, or the normalized target", () => {
    const result = readTarget(reading.value);
    if (reading.invalid !== undefined) {
      expect(result.ok ? null : result.reason).toBe(reading.invalid);
    } else {
      expect(result.ok).toBe(true);
      if (!result.ok || reading.normalized === undefined) return;
      const target = normalize(result.target, reading.repository);
      expect(written(target)).toEqual(reading.normalized);
      expect(Object.keys(written(target))).toEqual(Object.keys(reading.normalized));
      const again = readTarget(reading.normalized);
      expect(again.ok && sameTarget(target, again.target, reading.repository)).toBe(true);
    }
  });

  it("agrees with the definition target of the resource", () => {
    const validate = new Ajv2020({ strict: false }).compile({
      ...ADDRESSING_SCHEMA,
      $ref: "#/$defs/target",
    });
    expect(validate(reading.value)).toBe(reading.invalid === undefined);
  });
});

describe.each(CONTRACTS)("the contract case $id", (contract) => {
  it("admits the record exactly when the case states it", () => {
    expect(admits(contract.entries, contract.contracts)).toBe(contract.admits);
  });
});

describe.each(CASES.filter((check) => !(check.id in LEFT_OUT)))("the check case $id", (check) => {
  it("yields the findings of the case", async () => {
    const { issues } = await findings(
      caseFiles(FILES, check),
      "specs/schema-registry.yml",
      null,
      identifier(check),
    );
    expect(issues).toEqual(check.issues);
  });
});

describe("the check cases left out", () => {
  it("each name a case of the suite", () => {
    const ids = CASES.map((check) => check.id);
    expect(Object.keys(LEFT_OUT).filter((id) => !ids.includes(id))).toEqual([]);
  });
});
