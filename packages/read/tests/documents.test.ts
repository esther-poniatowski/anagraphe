/**
 * The texts of the files as the Python read side reads them: the scalars of PyYAML, the keys of a
 * mapping, the frontmatter of a note and its block anchors.
 */
import { describe, expect, it } from "vitest";
import {
  blockAnchors,
  frontmatterProblem,
  readDocument,
  splitFrontmatter,
  universalNewlines,
} from "../src/documents/text.js";
import { readYaml } from "../src/documents/yaml.js";

/** Returns the value of a reading that must succeed. */
function value(text: string, options: Parameters<typeof readYaml>[1] = {}): unknown {
  const reading = readYaml(text, options);
  if (!reading.ok) throw new Error(reading.error);
  return reading.value;
}

describe("the scalars of a YAML text", () => {
  it.each([
    ["y", "y"],
    ["n", "n"],
    ["yes", true],
    ["Off", false],
    ["09", "09"],
    ["017", 15],
    ["1_000", 1000],
    ["0x1F", 31],
    ["0b101", 5],
    ["-1:30", -90],
    ["1e3", "1e3"],
    ["1.5e+3", 1500],
    ["1.", 1],
    [".inf", Infinity],
    ["~", null],
    ["Null", null],
    ["quest.a", "quest.a"],
  ])("read %s as PyYAML reads it", (text, expected) => {
    expect(value(`v: ${text}\n`)).toEqual({ v: expected });
  });

  it("reads a timestamp as a date, or as its text when asked", () => {
    expect(value("v: 2026-11-20\n")).toEqual({ v: new Date(Date.UTC(2026, 10, 20)) });
    expect(value("v: 2026-11-20 10:00:00\n", { timestamps: "string" })).toEqual({
      v: "2026-11-20 10:00:00",
    });
  });

  it("fails on a day absent from the calendar, and on the scalar =", () => {
    expect(readYaml("v: 2026-02-30\n").ok).toBe(false);
    expect(readYaml("v: 2026-02-30\n", { timestamps: "string" }).ok).toBe(true);
    expect(readYaml("v: =\n").ok).toBe(false);
  });

  it("tells an integer from a float when asked", () => {
    expect(value("v: 1\nw: 1.0\n", { integers: "bigint" })).toEqual({ v: 1n, w: 1 });
  });

  it("keeps the last of two equal keys, and merges a mapping", () => {
    expect(value("a: 1\na: 2\n")).toEqual({ a: 2 });
    expect(value("base: &b {x: 1}\nm: {<<: *b, y: 2}\n")).toEqual({
      base: { x: 1 },
      m: { x: 1, y: 2 },
    });
  });

  it("orders the keys of a merged mapping as PyYAML orders them", () => {
    // Each expected order is the order of the keys that yaml.safe_load of PyYAML returns.
    const keys = (text: string): string[] =>
      Object.keys((value(text) as Record<string, Record<string, unknown>>).b ?? {});
    expect(keys("a: &a {x: 1, y: 2}\nb:\n  z: 0\n  <<: *a\n  y: 9\n")).toEqual(["x", "y", "z"]);
    expect(keys("a: &a {x: 1, y: 2}\nc: &c {y: 3, w: 4}\nb:\n  <<: [*a, *c]\n  v: 5\n")).toEqual([
      "y",
      "w",
      "x",
      "v",
    ]);
    expect(keys("a: &a {x: 1}\nb:\n  k: 1\n  <<: *a\n  x: 2\n")).toEqual(["x", "k"]);
    expect(value("a: &a {x: 1, y: 2}\nb:\n  y: 7\n  <<: *a\n")).toMatchObject({
      b: { x: 1, y: 7 },
    });
  });

  it("merges no quoted key, admits an empty list, and refuses a merge of a scalar", () => {
    expect(value("b: {'<<': {x: 1}}\n")).toEqual({ b: { "<<": { x: 1 } } });
    expect(value("b: {<<: []}\n")).toEqual({ b: {} });
    expect(readYaml("b: {<<: 1}\n").ok).toBe(false);
    expect(readYaml("b: {<<: [1]}\n").ok).toBe(false);
  });

  it("records the mappings holding a key that is no string, written as Python writes it", () => {
    const reading = readYaml("records:\n  2024: a\n  yes: b\n  ok: {c~d/e: {1: x}}\n");
    expect(reading.ok && reading.value).toEqual({
      records: { "2024": "a", True: "b", ok: { "c~d/e": { "1": "x" } } },
    });
    expect(reading.ok && reading.nonStringKeys).toEqual(["/records", "/records/ok/c~0d~1e"]);
  });

  it("keeps a key __proto__ as an own key", () => {
    const read = value("__proto__: {id: a}\n") as Record<string, unknown>;
    expect(Object.keys(read)).toEqual(["__proto__"]);
    expect(Object.getPrototypeOf(read)).toBe(Object.prototype);
  });

  it("fails on a key that is a sequence, which PyYAML refuses as unhashable", () => {
    expect(readYaml("? [a]\n: 1\n")).toEqual({ ok: false, error: "found unhashable key" });
  });

  it("fails on several documents, and reads an empty text as null", () => {
    expect(readYaml("a: 1\n---\nb: 2\n").ok).toBe(false);
    expect(value("")).toBeNull();
  });
});

describe("the documents", () => {
  it("parse JSON by the suffix .json, and YAML otherwise", () => {
    expect(readDocument("a.json", '{"id": "yes"}')).toEqual({ ok: true, value: { id: "yes" } });
    expect(readDocument("a.yml", "id: yes\n")).toEqual({ ok: true, value: { id: true } });
    expect(readDocument("a.json", '{"id": ').ok).toBe(false);
  });

  it("read each line break as \\n", () => {
    expect(universalNewlines("a\r\nb\rc\n")).toBe("a\nb\nc\n");
  });
});

describe("the frontmatter of a note", () => {
  it("splits the frontmatter from the body", () => {
    expect(splitFrontmatter("---\nrole: spec\n---\n# Title\n")).toEqual({
      data: { role: "spec" },
      body: "# Title\n",
    });
    expect(splitFrontmatter("# No frontmatter\n")).toEqual({
      data: {},
      body: "# No frontmatter\n",
    });
  });

  it("states why a frontmatter cannot be read", () => {
    expect(frontmatterProblem("---\nrole: spec\n---\n")).toBeNull();
    expect(frontmatterProblem("# Title\n")).toBeNull();
    expect(frontmatterProblem("---\nrole: spec\n# Title\n")).toBe(
      "the frontmatter opens on --- and never closes",
    );
    expect(frontmatterProblem("---\n---\n")).toBe("the frontmatter opens on --- and never closes");
    expect(frontmatterProblem("---\n- a\n- b\n---\n")).toBe("the frontmatter is not a mapping");
    expect(frontmatterProblem("---\nday: 2026-02-30\n---\n")).toMatch(
      /^the frontmatter is not valid YAML/,
    );
  });
});

describe("the block anchors of a body", () => {
  it("read each caret token closing a line, a repeated name repeated", () => {
    expect(blockAnchors("A claim. ^claim\n| a |\n^table\nAgain. ^claim\nx^not\n")).toEqual([
      "claim",
      "table",
      "claim",
    ]);
  });

  it("admit trailing spaces, and the spaces that Python reads as \\s", () => {
    expect(blockAnchors("A. ^a  \nB.\u001f^b\nC.﻿^c\nD. ^d-long ^e\n")).toEqual(["a", "b", "e"]);
  });

  it("end a line at \\n only", () => {
    expect(blockAnchors("A. ^a B")).toEqual([]);
  });
});
