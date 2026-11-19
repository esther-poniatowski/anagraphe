/**
 * In-memory adapters of the three ports, over a mutable map of repository paths to texts.
 *
 * The binding reads the contract of a record under `_schema`, and finds its schema through the
 * key `schemas` of a schema registry of Kleisis. The schema loader resolves a `$ref` as the Python
 * read side does: an absolute `$id` through the key `resources` of the registry, a path opening on
 * `/` from the root, and any other path from the folder of the referring document.
 */
import { posix } from "node:path";
import { isMapping, readDocument } from "../../src/documents/text.js";
import { readYaml } from "../../src/documents/yaml.js";
import type {
  BindingResolver,
  FileSource,
  LoadedSchema,
  RecordBinding,
  SchemaLoader,
  SchemaLoading,
} from "../../src/ports.js";
import { RepositoryIndex } from "../../src/live-index.js";

/** The files of a repository, each read counted. */
export class MemoryFiles implements FileSource {
  readonly reads: string[] = [];

  constructor(readonly files: Record<string, string>) {}

  read(path: string): Promise<string | null> {
    this.reads.push(path);
    return Promise.resolve(this.files[path] ?? null);
  }
}

/** The two maps of a schema registry of Kleisis, empty when the registry cannot be read. */
async function registryMaps(
  files: FileSource,
  path: string,
): Promise<{ schemas: Map<string, string>; resources: Map<string, string> }> {
  const text = await files.read(path);
  const reading = text === null ? null : readYaml(text);
  const data = reading?.ok === true && isMapping(reading.value) ? reading.value : {};
  const map = (key: string): Map<string, string> => {
    const value = data[key];
    return new Map(
      isMapping(value)
        ? Object.entries(value).map(([name, file]) => [name, posix.normalize(String(file))])
        : [],
    );
  };
  return { schemas: map("schemas"), resources: map("resources") };
}

/** Binds a record to the schema that the registry maps to its `_schema`. */
export class RegistryBinding implements BindingResolver {
  constructor(
    private readonly files: FileSource,
    private readonly registry: string,
  ) {}

  async bind(
    _: string,
    __: string,
    data: Readonly<Record<string, unknown>>,
  ): Promise<RecordBinding> {
    const contract = typeof data["_schema"] === "string" ? data["_schema"] : null;
    const { schemas } = await registryMaps(this.files, this.registry);
    const schema = contract === null ? null : (schemas.get(contract) ?? null);
    return { contract, schema, dependencies: [this.registry] };
  }
}

/** A URI scheme, which makes a reference an absolute `$id`. */
const SCHEME = /^[A-Za-z][A-Za-z0-9+.-]*:/;

/** Loads a schema with every document that its references reach. */
export class RegistrySchemas implements SchemaLoader {
  constructor(
    private readonly files: FileSource,
    private readonly registry: string,
  ) {}

  async load(key: string): Promise<SchemaLoading> {
    const { resources } = await registryMaps(this.files, this.registry);
    const documents = new Map<string, unknown>();
    const locate = (address: string, from: string): string | null => {
      if (SCHEME.test(address)) return resources.get(address) ?? null;
      const path = address.startsWith("/")
        ? posix.normalize(address.slice(1))
        : posix.normalize(posix.join(posix.dirname(from), address));
      return path === ".." || path.startsWith("../") ? null : path;
    };
    const pending = [key];
    for (let path = pending.pop(); path !== undefined; path = pending.pop()) {
      if (documents.has(path)) continue;
      const text = await this.files.read(path);
      const reading = text === null ? null : readDocument(path, text);
      if (reading === null || !reading.ok) {
        if (path === key) {
          return { status: "failed", reason: "absent or malformed", dependencies: [this.registry] };
        }
        continue;
      }
      documents.set(path, reading.value);
      for (const address of references(reading.value)) {
        const found = locate(address, path);
        if (found !== null) pending.push(found);
      }
    }
    const schema: LoadedSchema = {
      root: key,
      document: (path) => documents.get(path),
      locate: (address, from) => {
        const path = locate(address, from);
        return path !== null && documents.has(path) ? path : null;
      },
      dependencies: [...documents.keys(), this.registry],
    };
    return { status: "loaded", schema };
  }
}

/** Returns the address of every `$ref` of a document, its part before `#`, when not empty. */
function references(value: unknown): string[] {
  if (Array.isArray(value)) return value.flatMap(references);
  if (!isMapping(value)) return [];
  const own = typeof value["$ref"] === "string" ? [value["$ref"].split("#")[0] ?? ""] : [];
  return [...own.filter((address) => address !== ""), ...Object.values(value).flatMap(references)];
}

/** Returns an index over in-memory files, its schema registry at `registry`. */
export function memoryIndex(
  files: FileSource,
  registry: string,
  records: string | null,
  repository: string | null = null,
): RepositoryIndex {
  return new RepositoryIndex(
    {
      files,
      bindings: new RegistryBinding(files, registry),
      schemas: new RegistrySchemas(files, registry),
    },
    { registry: records, repository },
  );
}
