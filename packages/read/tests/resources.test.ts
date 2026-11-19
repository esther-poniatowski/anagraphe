/**
 * The resources: the generated module stays equal to its sources, and the declared versions derive
 * from the packaged schemas.
 */
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { readYaml } from "../src/documents/yaml.js";
import { IMPLEMENTED_SPECIFICATION, matches, UNIT_NAME } from "../src/resources.js";

const PACKAGE = fileURLToPath(new URL("..", import.meta.url));
const SCHEMAS = new URL("../../read-python/src/anagraphe_read/data/schemas/", import.meta.url);

/** Reads a packaged schema as the Python read side reads it. */
function packaged(name: string): Record<string, unknown> {
  const reading = readYaml(readFileSync(new URL(name, SCHEMAS), "utf-8"));
  if (!reading.ok) throw new Error(reading.error);
  return reading.value as Record<string, unknown>;
}

/** Returns the value at a path of keys. */
function at(value: unknown, ...keys: string[]): unknown {
  return keys.reduce<unknown>((node, key) => (node as Record<string, unknown>)[key], value);
}

describe("the generated module", () => {
  it("equals the module that its generator writes from the sources", () => {
    expect(() =>
      execFileSync(process.execPath, ["scripts/generate-resources.mjs", "--check"], {
        cwd: PACKAGE,
        stdio: "pipe",
      }),
    ).not.toThrow();
  });
});

describe("the declared versions", () => {
  it("name the $id of the addressing and the contract of the registry", () => {
    expect(IMPLEMENTED_SPECIFICATION).toEqual({
      addressing: at(packaged("addressing.v1.schema.yml"), "$id"),
      registry: at(packaged("record-registry.v1.schema.yml"), "properties", "_schema", "const"),
    });
  });
});

describe("the identifier patterns", () => {
  it("admit an identifier only when they match the whole string", () => {
    expect(matches("record-id", "quest.grokking.explain-delay")).toBe(true);
    expect(matches("record-id", "quest.grokking\n")).toBe(false);
    expect(matches("unit-id", "eta.rep")).toBe(false);
    expect(matches("repository-id", 2024)).toBe(false);
  });

  it("read the name of a block anchor without the anchors of the unit pattern", () => {
    expect(UNIT_NAME).toBe("[A-Za-z0-9][A-Za-z0-9_-]*");
  });
});
