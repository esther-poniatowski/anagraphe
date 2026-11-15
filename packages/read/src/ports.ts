/**
 * The ports through which a host supplies what the read side does not decide: the text of a file,
 * the contract and the schema that a record follows, and the documents of a schema with the
 * resolution of its references.
 *
 * Every path is a repository path: relative to the root of the open repository, with slashes. A
 * schema key is any string that the schema loader understands, such as the path of the root file
 * of a schema; the read side only passes it back.
 */

/** Read access to the text files of the open repository. */
export interface FileSource {
  /** Text of the file at `path`, or `null` when no such file exists. */
  read(path: string): Promise<string | null>;
}

/** The contract and the schema that one record follows, as the host binds them. */
export interface RecordBinding {
  /**
   * The logical contract of the record, such as the value of its `_schema`, `null` when the record
   * names none. The contracts that a target field admits are compared with it.
   */
  readonly contract: string | null;
  /** The key of the schema of the record, which the schema loader reads; `null` without one. */
  readonly schema: string | null;
  /** Paths whose change can change the binding, such as the schema registry of the host. */
  readonly dependencies: readonly string[];
}

/** Binds a record to its contract and its schema. */
export interface BindingResolver {
  /**
   * Binds the record at `path`, whose text is `text`, and whose top-level mapping, its frontmatter
   * or its document, is `data`.
   */
  bind(path: string, text: string, data: Readonly<Record<string, unknown>>): Promise<RecordBinding>;
}

/** The documents of one schema, loaded with every document that its references reach. */
export interface LoadedSchema {
  /** The key of the root document. */
  readonly root: string;
  /** The parsed document of a key, `undefined` when the set holds none. */
  document(key: string): unknown;
  /**
   * The key of the document named by the address of a `$ref`, its part before `#`, written in the
   * document `from`: an absolute `$id`, or a path relative to `from`. `null` when the address
   * names no document of the set.
   */
  locate(address: string, from: string): string | null;
  /** Paths whose change can change the set: its documents and any registry consulted. */
  readonly dependencies: readonly string[];
}

/** The outcome of loading a schema. */
export type SchemaLoading =
  | { readonly status: "loaded"; readonly schema: LoadedSchema }
  | {
      readonly status: "failed";
      /** Why the schema cannot be read, such as an absent or malformed file. */
      readonly reason: string;
      /** Paths whose creation or change may make the schema readable. */
      readonly dependencies: readonly string[];
    };

/** Loads a schema, by the key that a binding names. */
export interface SchemaLoader {
  load(schema: string): Promise<SchemaLoading>;
}
