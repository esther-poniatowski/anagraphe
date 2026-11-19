/**
 * The live index of the open repository: the events of the host, the races between indexings, the
 * changes of schemas, of the identity and of the registry, and the resolution of targets. The
 * cases of the index of Ekphrasis are ported, binding by `_schema` through a schema registry.
 */
import { describe, expect, it } from "vitest";
import { RepositoryIndex } from "../src/live-index.js";
import type { BindingResolver, FileSource } from "../src/ports.js";
import type { MetadataSource } from "../src/metadata.js";
import { parseToml } from "./support/host-metadata.js";
import { MemoryFiles, RegistryBinding, RegistrySchemas, memoryIndex } from "./support/memory.js";

const REGISTRY = "specs/schema-registry.yml";

/** A schema registry mapping each contract to its schema file. */
const registry = (
  schemas: Record<string, string>,
  resources: Record<string, string> = {},
): string =>
  [
    "_schema: kleisis:schema-registry@2",
    "schemas:",
    ...Object.entries(schemas).map(([contract, path]) => `  ${contract}: ${path}`),
    "resources:",
    ...Object.entries(resources).map(([id, path]) => `  '${id}': ${path}`),
    "",
  ].join("\n");

const RECORD_SCHEMA = "x-identifier: code\nproperties:\n  code: {type: string}\n";
const NESTED_SCHEMA =
  "x-identifier: identity.id\nproperties:\n  identity:\n    properties:\n      id: {type: string}\n";

/**
 * An index over a mutable map of files, with the record registry at its default path, in a
 * repository whose identifier the host derived.
 */
function service(
  vault: Record<string, string>,
  files = new MemoryFiles(vault),
  repository: string | null = null,
): RepositoryIndex {
  return memoryIndex(files, REGISTRY, "record-registry.yml", repository);
}

describe("the indexing of identifiers", () => {
  it("indexes the identifier at the field named by the schema of the contract", async () => {
    const vault = {
      [REGISTRY]: registry({ "t:quest@1": "s/record.yml", "t:project@1": "s/project.yml" }),
      "s/record.yml": RECORD_SCHEMA,
      "s/project.yml": NESTED_SCHEMA,
      "q/a.yml": "_schema: t:quest@1\ncode: quest.a\n",
      "p/b.yml": "_schema: t:project@1\nidentity:\n  id: project-b\n",
    };
    const index = service(vault);
    await index.rebuild(["q/a.yml", "p/b.yml"]);
    expect(index.pathsOf("quest.a")).toEqual(["q/a.yml"]);
    expect(index.pathsOf("project-b")).toEqual(["p/b.yml"]);
  });

  it("reads the default field of an unbound or undeclaring record, and none of an unparsable one", async () => {
    const vault = {
      [REGISTRY]: registry({ "t:plain@1": "plain.yml" }),
      "plain.yml": "properties:\n  id: {type: string}\n",
      "unbound.yml": "id: quest.unbound\nmetadata: {id: meta.unbound}\n",
      "broken.yml": "_schema: t:plain@1\nmetadata: {id: [quest.broken\n",
      "undeclaring.yml": "_schema: t:plain@1\nid: quest.plain\n",
      "missing.yml": "_schema: t:absent@1\nmetadata: {id: quest.missing}\n",
      "data.json": '{"metadata": {"id": "quest.json"}}',
    };
    const index = service(vault);
    await index.rebuild(Object.keys(vault));
    // The top level of a YAML document is read before its block metadata, which conflicts.
    expect(index.identifierOf("unbound.yml")).toBe("quest.unbound");
    expect(index.pathsOf("meta.unbound")).toEqual([]);
    expect(index.record("unbound.yml")?.conflicts).toEqual([
      { pointer: "/metadata/id", value: "meta.unbound" },
    ]);
    expect(index.record("broken.yml")?.problem).toMatch(/^the document cannot be parsed/);
    expect(index.identifierOf("undeclaring.yml")).toBe("quest.plain");
    expect(index.identifierOf("missing.yml")).toBe("quest.missing");
    // A JSON document has no built-in metadata source.
    expect(index.identifierOf("data.json")).toBeNull();
  });

  it("reads a TOML record through the source and the parser that the host supplies", async () => {
    const files = new MemoryFiles({ "a.toml": '[tool.record]\nid = "from-toml"\n' });
    const ports = {
      files,
      bindings: new RegistryBinding(files, REGISTRY),
      schemas: new RegistrySchemas(files, REGISTRY),
    };
    const source = (): MetadataSource => ({ kind: "toml", at: ["tool.record"] });
    const unsourced = new RepositoryIndex(ports, { registry: null, repository: null });
    await unsourced.rebuild(["a.toml"]);
    expect(unsourced.record("a.toml")).toBeUndefined();
    const unparsed = new RepositoryIndex(ports, {
      registry: null,
      repository: null,
      metadata: source,
    });
    await unparsed.rebuild(["a.toml"]);
    expect(unparsed.record("a.toml")?.problem).toBe(
      "the document cannot be parsed: the host supplies no TOML parser",
    );
    const parsed = new RepositoryIndex(ports, {
      registry: null,
      repository: null,
      metadata: source,
      toml: parseToml,
    });
    await parsed.rebuild(["a.toml"]);
    expect(parsed.identifierOf("a.toml")).toBe("from-toml");
  });

  it("resolves an identifier held by two records, even of two contracts, as a duplicate", async () => {
    const vault = {
      [REGISTRY]: registry({ "t:quest@1": "record.yml", "t:project@1": "project.yml" }),
      "record.yml": RECORD_SCHEMA,
      "project.yml": NESTED_SCHEMA,
      "a.yml": "_schema: t:quest@1\ncode: core\n",
      "b.yml": "_schema: t:project@1\nidentity: {id: core}\n",
    };
    const index = service(vault);
    await index.rebuild(["b.yml", "a.yml"]);
    expect(index.resolve({ id: "core" })).toEqual({
      status: "duplicate",
      identifier: "core",
      paths: ["a.yml", "b.yml"],
    });
  });

  it("follows the creation, change, rename and deletion of a record", async () => {
    const vault: Record<string, string> = {
      [REGISTRY]: registry({ "t:quest@1": "record.yml" }),
      "record.yml": RECORD_SCHEMA,
    };
    const index = service(vault);
    await index.rebuild([]);

    vault["records/a.yml"] = "_schema: t:quest@1\ncode: quest.a\n";
    await index.indexFile("records/a.yml");
    expect(index.pathsOf("quest.a")).toEqual(["records/a.yml"]);

    vault["records/a.yml"] = "_schema: t:quest@1\ncode: quest.renamed\n";
    await index.indexFile("records/a.yml");
    expect(index.pathsOf("quest.a")).toEqual([]);
    expect(index.identifierOf("records/a.yml")).toBe("quest.renamed");

    vault["archive/a.yml"] = vault["records/a.yml"] ?? "";
    delete vault["records/a.yml"];
    await index.renameFile("records/a.yml", "archive/a.yml");
    expect(index.pathsOf("quest.renamed")).toEqual(["archive/a.yml"]);
    expect(index.record("records/a.yml")).toBeUndefined();

    delete vault["archive/a.yml"];
    index.removeFile("archive/a.yml");
    expect(index.resolve({ id: "quest.renamed" })).toEqual({
      status: "unknown",
      identifier: "quest.renamed",
    });
  });

  it("binds again after a rebuild, when the binding of the host changes", async () => {
    const vault = { "record.yml": RECORD_SCHEMA, "q/a.yml": "code: quest.a\n" };
    let rules: Record<string, string> = {};
    const files = new MemoryFiles(vault);
    const bindings: BindingResolver = {
      bind: (path) =>
        Promise.resolve({ contract: null, schema: rules[path] ?? null, dependencies: [] }),
    };
    const index = new RepositoryIndex(
      { files, bindings, schemas: new RegistrySchemas(files, REGISTRY) },
      { registry: null, repository: null },
    );
    await index.rebuild(["q/a.yml"]);
    expect(index.identifierOf("q/a.yml")).toBeNull();
    rules = { "q/a.yml": "record.yml" };
    await index.rebuild(["q/a.yml"]);
    expect(index.identifierOf("q/a.yml")).toBe("quest.a");
  });
});

describe("the changes of schemas", () => {
  it("indexes again the records of a schema when one of its files changes", async () => {
    const vault: Record<string, string> = {
      [REGISTRY]: registry({ "t:quest@1": "record.yml" }),
      "record.yml": "properties:\n  code: {$ref: common.yml}\n",
      "common.yml": "type: string\n",
      "a.yml": "_schema: t:quest@1\ncode: quest.a\nkey: other\n",
    };
    const index = service(vault);
    await index.rebuild(["a.yml"]);
    expect(index.identifierOf("a.yml")).toBeNull();

    vault["record.yml"] = `x-identifier: code\n${vault["record.yml"] ?? ""}`;
    await index.dependencyChanged("record.yml");
    expect(index.identifierOf("a.yml")).toBe("quest.a");

    vault["record.yml"] =
      "x-identifier: key\nproperties:\n  code: {$ref: common.yml}\n  key: {type: string}\n";
    // A change reported for a referenced file loads the whole schema again.
    await index.dependencyChanged("common.yml");
    expect(index.identifierOf("a.yml")).toBe("other");
  });

  it("indexes a record again once its missing schema is created", async () => {
    const vault: Record<string, string> = {
      [REGISTRY]: registry({ "t:quest@1": "record.yml" }),
      "a.yml": "_schema: t:quest@1\ncode: quest.a\n",
    };
    const index = service(vault);
    await index.rebuild(["a.yml"]);
    expect(index.identifierOf("a.yml")).toBeNull();
    expect((await index.schemaProblems()).map((problem) => problem.kind)).toEqual([
      "unreadable-schema",
    ]);

    vault["record.yml"] = RECORD_SCHEMA;
    await index.dependencyChanged("record.yml");
    expect(index.identifierOf("a.yml")).toBe("quest.a");
    expect(await index.schemaProblems()).toEqual([]);
  });

  it("indexes a record again once the schema registry maps its contract", async () => {
    const vault: Record<string, string> = {
      [REGISTRY]: registry({}),
      "record.yml": RECORD_SCHEMA,
      "a.yml": "_schema: t:quest@1\ncode: quest.a\n",
    };
    const index = service(vault);
    await index.rebuild(["a.yml"]);
    expect(index.identifierOf("a.yml")).toBeNull();

    vault[REGISTRY] = registry({ "t:quest@1": "record.yml" });
    await index.dependencyChanged(REGISTRY);
    expect(index.identifierOf("a.yml")).toBe("quest.a");
  });

  it("reads the identifier through allOf and an absolute $id once the registry maps it", async () => {
    const uri = "https://example.org/tool/record@1/base.schema.yml";
    const vault: Record<string, string> = {
      [REGISTRY]: registry({ "t:quest@1": "consumer.yml" }),
      "consumer.yml": `allOf:\n  - $ref: '${uri}'\n`,
      "tool/base.yml": `$id: '${uri}'\n${RECORD_SCHEMA}`,
      "a.yml": "_schema: t:quest@1\ncode: quest.a\n",
    };
    const index = service(vault);
    await index.rebuild(["a.yml"]);
    expect(index.identifierOf("a.yml")).toBeNull();
    expect((await index.schemaProblems()).map((problem) => problem.kind)).toEqual([
      "unresolved-schema-reference",
    ]);

    vault[REGISTRY] = registry({ "t:quest@1": "consumer.yml" }, { [uri]: "tool/base.yml" });
    await index.dependencyChanged(REGISTRY);
    expect(index.identifierOf("a.yml")).toBe("quest.a");
  });

  it("loads each schema once across the records bound to it", async () => {
    const vault = {
      [REGISTRY]: registry({ "t:quest@1": "record.yml" }),
      "record.yml": RECORD_SCHEMA,
      "a.yml": "_schema: t:quest@1\ncode: quest.a\n",
      "b.yml": "_schema: t:quest@1\ncode: quest.b\n",
    };
    const files = new MemoryFiles(vault);
    const index = service(vault, files);
    await index.rebuild(["a.yml", "b.yml"]);
    expect(files.reads.filter((path) => path === "record.yml")).toHaveLength(1);
  });
});

describe("the races between indexings", () => {
  /** Files whose first read of `held` waits until `release` runs. */
  function held(
    vault: Record<string, string>,
    path: string,
  ): { files: FileSource; release: () => void } {
    const waiting: (() => void)[] = [];
    let first = true;
    return {
      files: {
        read: async (read) => {
          const text = vault[read] ?? null;
          if (read === path && first) {
            first = false;
            await new Promise<void>((resolve) => waiting.push(resolve));
          }
          return text;
        },
      },
      release: () => waiting[0]?.(),
    };
  }

  it("records only the latest indexing of a record that changes while it is read", async () => {
    const vault: Record<string, string> = {
      [REGISTRY]: registry({ "t:quest@1": "record.yml" }),
      "record.yml": RECORD_SCHEMA,
      "a.yml": "_schema: t:quest@1\ncode: quest.first\n",
    };
    const { files, release } = held(vault, "a.yml");
    const index = memoryIndex(files, REGISTRY, null);
    const first = index.indexFile("a.yml");
    vault["a.yml"] = "_schema: t:quest@1\ncode: quest.second\n";
    await index.indexFile("a.yml");
    release();
    await first;
    expect(index.identifierOf("a.yml")).toBe("quest.second");
  });

  it("records nothing for an indexing that completes after the removal of its record", async () => {
    const vault: Record<string, string> = { "a.md": "---\nid: note-a\n---\n" };
    const { files, release } = held(vault, "a.md");
    const index = memoryIndex(files, REGISTRY, null);
    const first = index.indexFile("a.md");
    index.removeFile("a.md");
    release();
    await first;
    expect(index.record("a.md")).toBeUndefined();
  });

  it("indexes again a record whose first indexing runs while its schema changes", async () => {
    const vault: Record<string, string> = {
      [REGISTRY]: registry({ "t:quest@1": "record.yml" }),
      "record.yml": "properties:\n  code: {type: string}\n",
      "a.yml": "_schema: t:quest@1\ncode: quest.a\n",
    };
    const { files, release } = held(vault, "a.yml");
    const index = memoryIndex(files, REGISTRY, null);
    const first = index.indexFile("a.yml");
    vault["record.yml"] = RECORD_SCHEMA;
    const changed = index.dependencyChanged("record.yml");
    release();
    await Promise.all([first, changed]);
    expect(index.identifierOf("a.yml")).toBe("quest.a");
  });
});

describe("the resolution of targets", () => {
  const vault = (): Record<string, string> => ({
    [REGISTRY]: registry({ "t:argument@1": "argument.yml" }),
    "argument.yml": [
      "properties:",
      "  ideas:",
      "    items: {$ref: '#/$defs/idea'}",
      "$defs:",
      "  idea:",
      "    x-identifier: id",
      "    properties:",
      "      id: {type: string}",
      "",
    ].join("\n"),
    "record-registry.yml": [
      "_schema: anagraphe:record-registry@1",
      "repository: lab",
      "records: {}",
      "retired:",
      "  note-old: {date: 2026-11-01, replaced_by: note-n}",
      "  gone: {date: 2026-11-02}",
      "",
    ].join("\n"),
    "notes/n.md": "---\nid: note-n\n---\nOne. ^claim\n\nTwo. ^claim\nThree. ^single\n",
    "args/one.yml": "_schema: t:argument@1\nmetadata: {id: arg.one}\nideas: [{id: premise}]\n",
  });

  async function indexed(files: Record<string, string>): Promise<RepositoryIndex> {
    const index = service(files, undefined, "lab");
    await index.rebuild(Object.keys(files));
    return index;
  }

  it("reads the units of a note and of a document, and resolves a unit against them", async () => {
    const index = await indexed(vault());
    expect(index.record("notes/n.md")?.units).toEqual(["claim", "claim", "single"]);
    expect(index.record("args/one.yml")?.units).toEqual(["premise"]);
    const unit = (id: string, name?: string): unknown => {
      const resolution = index.resolve(name === undefined ? { id } : { id, unit: name });
      return resolution.status === "resolved" ? resolution.unit : resolution.status;
    };
    expect([unit("note-n"), unit("note-n", "single"), unit("note-n", "claim")]).toEqual([
      "none",
      "present",
      "ambiguous-unit",
    ]);
    expect([unit("arg.one", "premise"), unit("arg.one", "claim")]).toEqual([
      "present",
      "unknown-unit",
    ]);
  });

  it("follows a rename through the registry, and reads a retirement", async () => {
    const index = await indexed(vault());
    const renamed = index.resolve({ id: "note-old", unit: "single" });
    expect(
      renamed.status === "renamed" && [renamed.chain, renamed.target, renamed.resolution.status],
    ).toEqual([["note-n"], { id: "note-n", unit: "single" }, "resolved"]);
    expect(index.resolve({ id: "gone" })).toEqual({
      status: "retired",
      identifier: "gone",
      successor: null,
    });
  });

  it("reads a target into the repository, into another one, and without identity", async () => {
    const files = vault();
    const index = await indexed(files);
    expect(index.resolve({ repository: "lab" })).toEqual({ status: "repository" });
    expect(index.resolve({ repository: "lab", id: "arg.one" }).status).toBe("resolved");
    expect(index.resolve({ repository: "other", id: "arg.one" })).toEqual({
      status: "unverified",
      repository: "other",
    });
    index.setRepository(null);
    expect(index.resolve({ repository: "lab", id: "arg.one" }).status).toBe("unverified");
  });

  it("keeps a retired manifest out of the records", async () => {
    const files = vault();
    files["repository.yml"] = "repository: {id: lab}\nid: not-a-record\n";
    const index = await indexed(files);
    expect(index.record("repository.yml")).toBeUndefined();
    expect(index.pathsOf("not-a-record")).toEqual([]);
  });

  it("follows a change of the identity and of the registry", async () => {
    const files = vault();
    const index = await indexed(files);
    index.setRepository("lab-two");
    expect(index.repository).toBe("lab-two");
    expect(index.resolve({ repository: "lab-two", id: "arg.one" }).status).toBe("resolved");
    expect(index.resolve({ repository: "lab", id: "arg.one" }).status).toBe("unverified");
    files["record-registry.yml"] = "records: {\n";
    await index.indexFile("record-registry.yml");
    expect(index.registry.problems.map((problem) => problem.pointer)).toEqual([""]);
    expect(index.resolve({ id: "gone" }).status).toBe("unknown");
  });
});
