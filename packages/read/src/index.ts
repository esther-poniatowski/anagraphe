/**
 * The TypeScript read side of the addressing of Anagraphe: logical targets, identifier
 * declarations, units, repository manifests, record registries and field paths, read as the Python
 * read side reads them, and the live index of the records of an open repository.
 *
 * A host supplies three ports: {@link BindingResolver}, {@link SchemaLoader} and
 * {@link FileSource}. {@link IMPLEMENTED_SPECIFICATION} declares the versions of the specification
 * that the package implements.
 */
export type {
  BindingResolver,
  FileSource,
  LoadedSchema,
  RecordBinding,
  SchemaLoader,
  SchemaLoading,
} from "./ports.js";
export {
  ADDRESSING_ID,
  IMPLEMENTED_SPECIFICATION,
  REGISTRY_CONTRACT,
  REGISTRY_ID,
  REPOSITORY_CONTRACT,
  TARGET_REFERENCE,
  matches,
  type IdentifierDefinition,
} from "./resources.js";
export {
  admits,
  contractVerdict,
  formatTarget,
  normalize,
  readContracts,
  readTarget,
  sameTarget,
  written,
  type ContractVerdict,
  type ContractsReading,
  type Reason,
  type Target,
  type TargetReading,
} from "./target.js";
export { pointer, valuesAt, type KeyPath, type Located, type Step } from "./key-path.js";
export {
  ANY_ITEM,
  ANY_KEY,
  FieldPathError,
  PointerError,
  expand,
  fromPointer,
  isFieldPath,
  isFieldPathPattern,
  matchNodes,
  parseFieldPath,
  parseFieldPathPattern,
  pointerTokens,
  printFieldPath,
  toPointer,
  type FieldPathReason,
  type MatchedNode,
  type PatternSegment,
  type PointerReason,
  type Segment,
} from "./field-path.js";
export {
  INVALID_IDENTIFIER_DECLARATION,
  INVALID_TARGET_CONTRACT,
  readDeclarations,
  type Declarations,
  type TargetField,
  type UnitDeclaration,
} from "./schema/declarations.js";
export { UNRESOLVED_REFERENCE, type SchemaProblem } from "./schema/walk.js";
export {
  formatOf,
  parseRecord,
  readRecord,
  type IdentifierReading,
  type RecordFormat,
  type RecordReading,
  type RecordSource,
} from "./records.js";
export {
  INVALID_REPOSITORY_MANIFEST,
  LEGACY_REPOSITORY_MANIFEST,
  MANIFEST_FILE,
  readManifest,
  type Manifest,
  type ManifestProblem,
  type ManifestReading,
} from "./manifest.js";
export {
  REGISTRY_FILE,
  checkRegistry,
  follow,
  lookup,
  readRegistry,
  type RecordRegistry,
  type RegistryEntry,
  type RegistryLookup,
  type RegistryProblem,
  type RegistryReading,
  type Retirement,
} from "./registry.js";
export {
  RepositoryIndex,
  UNREADABLE_SCHEMA,
  type Duplicate,
  type IndexOptions,
  type IndexPorts,
  type Resolution,
  type Resolved,
  type UnitResolution,
} from "./live-index.js";
export { readYaml, type YamlOptions, type YamlReading } from "./documents/yaml.js";
