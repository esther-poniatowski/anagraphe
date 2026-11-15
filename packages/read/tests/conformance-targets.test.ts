/**
 * The conformance cases of `specs/conformance/targets.yml`: every reading and every contract case,
 * and the check cases whose findings the read side yields.
 */
import { Ajv2020 } from "ajv/dist/2020.js";
import { describe, expect, it } from "vitest";
import { ADDRESSING_SCHEMA } from "../src/generated/resources.js";
import { ADDRESSING_ID, REPOSITORY_CONTRACT } from "../src/resources.js";
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
const CASES = SUITE["cases"] as CheckCase[];
const FILES = SUITE["files"] as Record<string, string>;

/**
 * The check cases left out, each with the reason: the walk of the files of a repository, its
 * exclusions and its nested repositories belong to the host, which feeds the live index.
 */
const LEFT_OUT: Readonly<Record<string, string>> = {
  "nested-repository": "the host walks the files, and feeds no file of a nested repository",
};

describe("the suite of the targets", () => {
  it("names the resource and the contract of the package", () => {
    expect([SUITE["resource"], SUITE["manifest"]]).toEqual([ADDRESSING_ID, REPOSITORY_CONTRACT]);
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
    const { issues } = await findings(caseFiles(FILES, check), "specs/schema-registry.yml", null);
    expect(issues).toEqual(check.issues);
  });
});

describe("the check cases left out", () => {
  it("each name a case of the suite", () => {
    const ids = CASES.map((check) => check.id);
    expect(Object.keys(LEFT_OUT).filter((id) => !ids.includes(id))).toEqual([]);
  });
});
