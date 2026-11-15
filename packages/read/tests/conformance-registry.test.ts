/**
 * The conformance cases of `specs/conformance/record-registry.yml`: every document, and the check
 * cases of the targets, which read the retired identifiers of the registry.
 */
import { describe, expect, it } from "vitest";
import { readRegistry } from "../src/registry.js";
import { REGISTRY_CONTRACT, REGISTRY_ID } from "../src/resources.js";
import { caseFiles, findings, suite, type CheckCase } from "./support/conformance.js";

const SUITE = suite("record-registry.yml");

interface DocumentCase {
  readonly id: string;
  readonly text: string;
  readonly invalid: readonly string[];
}

interface RegistryCase extends CheckCase {
  readonly check: "records" | "targets";
  readonly sections?: Record<string, unknown>;
}

const DOCUMENTS = SUITE["documents"] as DocumentCase[];
const CASES = SUITE["cases"] as RegistryCase[];
const FILES = SUITE["files"] as Record<string, string>;

describe("the suite of the registry", () => {
  it("names the contract and the schema of the package", () => {
    expect([SUITE["contract"], SUITE["schema"]]).toEqual([REGISTRY_CONTRACT, REGISTRY_ID]);
  });
});

describe.each(DOCUMENTS)("the document $id", (document) => {
  it("states the pointers of its defects, and holds entries only when valid", () => {
    const reading = readRegistry(document.text);
    expect(reading.problems.map((problem) => problem.pointer)).toEqual(document.invalid);
    expect(reading.registry === null).toBe(document.invalid.length > 0);
  });
});

// The cases of the check `records` are left out: their findings compare the registry with its
// generation from the walk, which belongs to the write side, in Python only.
describe.each(CASES.filter((check) => check.check === "targets"))("the check case $id", (check) => {
  it("yields the findings of the case", async () => {
    const records = check.sections === undefined || "records" in check.sections;
    const { issues } = await findings(
      caseFiles(FILES, check),
      "specs/schema-registry.yml",
      records ? "record-registry.yml" : null,
    );
    expect(issues).toEqual(check.issues);
  });
});
