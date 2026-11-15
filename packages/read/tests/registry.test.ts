/**
 * The lookup of an identifier in a record registry alone, as a resolver of another repository
 * reads it.
 */
import { describe, expect, it } from "vitest";
import { follow, lookup, readRegistry, type RecordRegistry } from "../src/registry.js";

const REGISTRY = [
  "_schema: anagraphe:record-registry@1",
  "repository: lab",
  "records:",
  "  ada: {path: people/ada.yml, format: yaml}",
  "retired:",
  "  ada-old: {date: 2026-11-01, replaced_by: ada-mid}",
  "  ada-mid: {date: 2026-11-02, replaced_by: ada}",
  "  gone: {date: 2026-11-03}",
  "  lost: {date: 2026-11-04, replaced_by: gone}",
  "  stray: {date: 2026-11-05, replaced_by: nowhere}",
  "",
].join("\n");

function registry(): RecordRegistry {
  const reading = readRegistry(REGISTRY);
  if (reading.registry === null) throw new Error(JSON.stringify(reading.problems));
  return reading.registry;
}

describe("the lookup in a registry", () => {
  it("finds the path and the format of a record", () => {
    expect(lookup(registry(), "ada")).toEqual({
      status: "record",
      identifier: "ada",
      entry: { path: "people/ada.yml", format: "yaml" },
    });
  });

  it("follows the successors of a renamed identifier to its record, reporting the chain", () => {
    expect(lookup(registry(), "ada-old")).toEqual({
      status: "renamed",
      chain: ["ada-mid", "ada"],
      identifier: "ada",
      entry: { path: "people/ada.yml", format: "yaml" },
    });
  });

  it("reads an identifier retired without a live successor as retired", () => {
    expect(lookup(registry(), "gone")).toEqual({ status: "retired", successor: null });
    expect(lookup(registry(), "lost")).toEqual({ status: "retired", successor: "gone" });
    expect(lookup(registry(), "stray")).toEqual({ status: "retired", successor: "nowhere" });
  });

  it("reads an identifier that the registry neither lists nor retires as unknown", () => {
    expect(lookup(registry(), "ghost")).toEqual({ status: "unknown" });
  });

  it("stops a chain on a cycle, which a valid registry excludes", () => {
    const retired = new Map([
      ["a", { date: "2026-11-01", replacedBy: "b" }],
      ["b", { date: "2026-11-02", replacedBy: "a" }],
    ]);
    expect(follow(retired, "a", () => false)).toBeNull();
  });
});

describe("the reading of a registry", () => {
  it("holds no registry for an absent file, and keeps the date as written", () => {
    expect(readRegistry(null)).toEqual({ registry: null, problems: [], exists: false });
    expect(registry().retired.get("gone")).toEqual({ date: "2026-11-03", replacedBy: null });
  });

  it("reports an identifier that YAML reads as no string at its mapping", () => {
    const text = REGISTRY.replace("  ada: {", "  2024: {path: a.json, format: json}\n  ada: {");
    expect(readRegistry(text).problems.map((problem) => problem.pointer)).toEqual(["/records"]);
  });
});
