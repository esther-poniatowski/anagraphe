/**
 * The live index of the open repository: the identifier, the contracts and the units of each of
 * its records and its record registry, kept current by the events of the host, and the resolution
 * of a logical target against them. The host derives the identity of the repository, with
 * {@link deriveIdentity}, and supplies its identifier; the retired manifest `repository.yml` is no
 * record.
 *
 * The host reports each creation, change, rename and deletion of a file, and each change of a file
 * on which a binding or a schema depends, such as a schema or a schema registry. Each indexing of a
 * file draws a number from one counter, so an indexing that completes after a later one, a removal
 * or a rebuild records nothing.
 *
 * A target of the same repository resolves against the live records first, then against the
 * retired identifiers of the registry. A target into another repository is unverified: its
 * resolution belongs to a resolver of that repository, which reads its registry.
 */
import { RETIRED_MANIFEST_FILE } from "./identity.js";
import type { BindingResolver, FileSource, SchemaLoader } from "./ports.js";
import { builtInSource, type MetadataSource } from "./metadata.js";
import { parseRecord, readRecord, type RecordReading, type TomlParser } from "./records.js";
import { follow, readRegistry, type RegistryReading } from "./registry.js";
import { readDeclarations, type Declarations } from "./schema/declarations.js";
import type { SchemaProblem } from "./schema/walk.js";
import type { Target } from "./target.js";

/** The kind of problem of a schema that the schema loader cannot read. */
export const UNREADABLE_SCHEMA = "unreadable-schema";

/** The ports of the host. */
export interface IndexPorts {
  readonly files: FileSource;
  readonly bindings: BindingResolver;
  readonly schemas: SchemaLoader;
}

/**
 * The identity of the repository, where the index finds its record registry, and how it reads the
 * metadata of a file.
 */
export interface IndexOptions {
  /** The path of the record registry; `null` when the repository declares none. */
  readonly registry: string | null;
  /**
   * The identifier of the repository, derived by the host with {@link deriveIdentity}; `null`
   * when the repository has no identity.
   */
  readonly repository: string | null;
  /**
   * The metadata source of a file, which the host selects from the section `metadata` of its
   * configuration; the built-in source of the file when absent. The source gives the default
   * identifier of a record, and makes a TOML document with a source `toml` a record.
   */
  readonly metadata?: (path: string) => MetadataSource;
  /** The TOML parser of the host; without it, a TOML record cannot be read. */
  readonly toml?: TomlParser;
}

/** How the record of a target holds the unit that the target names. */
export type UnitResolution = "none" | "present" | "unknown-unit" | "ambiguous-unit";

/** A target whose record is found. */
export interface Resolved {
  readonly status: "resolved";
  readonly path: string;
  readonly record: RecordReading;
  /** `none` when the target names no unit. */
  readonly unit: UnitResolution;
}

/** A target naming an identifier that several records hold. */
export interface Duplicate {
  readonly status: "duplicate";
  readonly identifier: string;
  readonly paths: readonly string[];
}

/** The resolution of a logical target in the open repository. */
export type Resolution =
  | Resolved
  | Duplicate
  /** The identifier is retired by a rename; `chain` lists its successors, the live one last. */
  | {
      readonly status: "renamed";
      readonly chain: readonly string[];
      readonly target: Target;
      readonly resolution: Resolved | Duplicate;
    }
  /** The identifier is retired without a successor, or its successors reach no record. */
  | { readonly status: "retired"; readonly identifier: string; readonly successor: string | null }
  | { readonly status: "unknown"; readonly identifier: string }
  /** The target names another repository, whose records this index does not hold. */
  | { readonly status: "unverified"; readonly repository: string }
  /** The target names the open repository itself. */
  | { readonly status: "repository" };

/** The declarations of one schema, with the documents on which they depend. */
interface SchemaEntry {
  readonly declarations: Declarations | null;
  readonly dependencies: readonly string[];
  readonly problems: readonly SchemaProblem[];
}

/** The live index of the records of the open repository. */
export class RepositoryIndex {
  private identifier: string | null;
  private registryReading: RegistryReading = { registry: null, problems: [], exists: false };
  private readonly records = new Map<string, RecordReading>();
  private readonly holders = new Map<string, Set<string>>();
  private readonly dependencies = new Map<string, readonly string[]>();
  private readonly schemas = new Map<string, Promise<SchemaEntry>>();
  /** The number of the latest indexing of each path, and the paths whose indexing runs. */
  private readonly generations = new Map<string, number>();
  private readonly running = new Set<string>();
  private counter = 0;

  constructor(
    private readonly ports: IndexPorts,
    private readonly options: IndexOptions,
  ) {
    this.identifier = options.repository;
  }

  /** The identifier of the repository, `null` when it has no identity. */
  get repository(): string | null {
    return this.identifier;
  }

  /**
   * Records the identifier that the host derives again, such as after a change of the section
   * `repository` of its configuration; the records stay indexed.
   */
  setRepository(repository: string | null): void {
    this.identifier = repository;
  }

  get registry(): RegistryReading {
    return this.registryReading;
  }

  /** The reading of the record at `path`, as last indexed. */
  record(path: string): RecordReading | undefined {
    return this.records.get(path);
  }

  /** The valid identifier of the record at `path`, as last indexed, or `null`. */
  identifierOf(path: string): string | null {
    const identifier = this.records.get(path)?.identifier;
    return identifier?.status === "valid" ? identifier.value : null;
  }

  /** The paths of the records holding a valid identifier, sorted. */
  pathsOf(identifier: string): string[] {
    return [...(this.holders.get(identifier) ?? [])].sort();
  }

  /** The defects of the schemas loaded so far: unreadable schemas, references and declarations. */
  async schemaProblems(): Promise<SchemaProblem[]> {
    const entries = await Promise.all(this.schemas.values());
    return entries.flatMap((entry) => entry.problems);
  }

  /** Forgets every file and every schema, then reads the registry and `paths`. */
  async rebuild(paths: readonly string[]): Promise<void> {
    for (const path of [...this.records.keys()]) this.forget(path);
    this.schemas.clear();
    this.generations.clear();
    this.registryReading = { registry: null, problems: [], exists: false };
    const reserved = this.options.registry === null ? [] : [this.options.registry];
    await Promise.all([...new Set([...reserved, ...paths])].map((path) => this.indexFile(path)));
  }

  /** Indexes the file at `path`, created or changed: a record or the registry. */
  async indexFile(path: string): Promise<void> {
    if (path === RETIRED_MANIFEST_FILE) return;
    const generation = this.next(path);
    this.running.add(path);
    try {
      const text = await this.ports.files.read(path);
      if (path === this.options.registry) {
        if (this.generations.get(path) === generation) this.registryReading = readRegistry(text);
      } else {
        await this.indexRecord(path, text, generation);
      }
    } finally {
      if (this.generations.get(path) === generation) this.running.delete(path);
    }
  }

  /** Forgets the file at `path`, deleted. */
  removeFile(path: string): void {
    this.next(path);
    this.running.delete(path);
    if (path === this.options.registry) {
      this.registryReading = { registry: null, problems: [], exists: false };
    } else this.forget(path);
  }

  /** Moves the file from `oldPath` to `newPath`, then indexes it again, since its binding may change. */
  async renameFile(oldPath: string, newPath: string): Promise<void> {
    this.removeFile(oldPath);
    await this.indexFile(newPath);
  }

  /**
   * Indexes again every record whose binding or schema depends on the file at `path`, created,
   * changed, renamed or deleted, and every record whose indexing runs.
   */
  async dependencyChanged(path: string): Promise<void> {
    for (const [key, entry] of [...this.schemas]) {
      const { dependencies } = await entry;
      if (key === path || dependencies.includes(path)) this.schemas.delete(key);
    }
    const dependents = [...this.dependencies]
      .filter(([, documents]) => documents.includes(path))
      .map(([file]) => file);
    await Promise.all(
      [...new Set([...dependents, ...this.running])].map((file) => this.indexFile(file)),
    );
  }

  /** Resolves a target read in a file of the open repository. */
  resolve(target: Target): Resolution {
    if (target.repository !== undefined && target.repository !== this.repository) {
      return { status: "unverified", repository: target.repository };
    }
    if (target.id === undefined) return { status: "repository" };
    const found = this.found(target, target.id);
    if (found !== null) return found;
    const retired = this.registryReading.registry?.retired;
    const retirement = retired?.get(target.id);
    if (retired === undefined || retirement === undefined) {
      return { status: "unknown", identifier: target.id };
    }
    const chain = follow(retired, target.id, (id) => this.holders.has(id));
    const live = chain?.[chain.length - 1];
    const followed = live === undefined ? null : { ...target, id: live };
    const resolution = followed === null || live === undefined ? null : this.found(followed, live);
    if (chain === null || followed === null || resolution === null) {
      return { status: "retired", identifier: target.id, successor: retirement.replacedBy };
    }
    return { status: "renamed", chain, target: followed, resolution };
  }

  /** Returns the record holding an identifier, the records when several hold it, else `null`. */
  private found(target: Target, identifier: string): Resolved | Duplicate | null {
    const paths = this.pathsOf(identifier);
    const [path] = paths;
    if (path === undefined) return null;
    const record = this.records.get(path);
    if (paths.length > 1 || record === undefined) return { status: "duplicate", identifier, paths };
    const count =
      target.unit === undefined ? -1 : record.units.filter((u) => u === target.unit).length;
    const unit: UnitResolution =
      count === -1
        ? "none"
        : count === 0
          ? "unknown-unit"
          : count === 1
            ? "present"
            : "ambiguous-unit";
    return { status: "resolved", path, record, unit };
  }

  private async indexRecord(path: string, text: string | null, generation: number): Promise<void> {
    const metadata = this.options.metadata?.(path) ?? builtInSource(path);
    const source =
      text === null ? null : parseRecord(path, text, { source: metadata, toml: this.options.toml });
    if (source === null) {
      if (this.generations.get(path) === generation) this.forget(path);
      return;
    }
    const binding =
      source.problem === null
        ? await this.ports.bindings.bind(path, text ?? "", source.data)
        : { contract: null, schema: null, dependencies: [] };
    const schema = binding.schema === null ? null : await this.schemaEntry(binding.schema);
    if (this.generations.get(path) !== generation) return;
    this.forget(path);
    const reading = readRecord(source, binding.contract, schema?.declarations ?? null);
    this.records.set(path, reading);
    if (reading.identifier.status === "valid") {
      const value = reading.identifier.value;
      this.holders.set(value, (this.holders.get(value) ?? new Set()).add(path));
    }
    this.dependencies.set(path, [...binding.dependencies, ...(schema?.dependencies ?? [])]);
  }

  private schemaEntry(key: string): Promise<SchemaEntry> {
    let entry = this.schemas.get(key);
    if (entry === undefined) {
      entry = this.ports.schemas.load(key).then((loading): SchemaEntry => {
        if (loading.status === "failed") {
          const detail = `the schema ${key} cannot be read: ${loading.reason}`;
          return {
            declarations: null,
            dependencies: [key, ...loading.dependencies],
            problems: [{ kind: UNREADABLE_SCHEMA, document: key, pointer: "", detail }],
          };
        }
        const declarations = readDeclarations(loading.schema);
        const dependencies = [key, ...loading.schema.dependencies];
        return { declarations, dependencies, problems: declarations.problems };
      });
      this.schemas.set(key, entry);
    }
    return entry;
  }

  private next(path: string): number {
    this.counter += 1;
    this.generations.set(path, this.counter);
    return this.counter;
  }

  /** Removes a record from the index. */
  private forget(path: string): void {
    const identifier = this.identifierOf(path);
    this.records.delete(path);
    this.dependencies.delete(path);
    if (identifier === null) return;
    const paths = this.holders.get(identifier);
    paths?.delete(path);
    if (paths?.size === 0) this.holders.delete(identifier);
  }
}
