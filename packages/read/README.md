# @anagraphe/read

The package `@anagraphe/read` reads the addressing of Anagraphe in TypeScript, as the Python read
side of Anagraphe reads it. The package serves a host without Python, such as the Obsidian plugin
Ekphrasis on mobile. The package passes the conformance cases of `specs/conformance/targets.yml`,
`specs/conformance/identity.yml`, `specs/conformance/record-registry.yml` and
`specs/conformance/field-paths.yml`, and Python alone writes the record registry.

## Installation

Each release of Anagraphe attaches the package as a tarball, since npm installs no subdirectory of
a Git repository. A consumer pins the tarball by its URL in its file `package.json`:

```json
{
  "dependencies": {
    "@anagraphe/read": "https://github.com/esther-poniatowski/anagraphe/releases/download/v<version>/anagraphe-read-<version>.tgz"
  }
}
```

After the command `npm install`, the lockfile of the consumer records the integrity hash of the
tarball, and the command `npm ci` refuses a tarball whose bytes differ from that hash. The command
below computes the hash of a tarball in the form recorded by the lockfile, so that the hash can be
checked against the release before the lockfile adopts it:

```sh
curl -sL <tarball-url> | openssl dgst -sha512 -binary | base64 | sed 's/^/sha512-/'
```

During joint development, a consumer points at a local clone of Anagraphe instead. The package
exports its build output, so the commands below build the package in the clone, then install it in
the consumer:

```sh
npm --prefix ../anagraphe/packages/read install
npm --prefix ../anagraphe/packages/read run build
npm install ../anagraphe/packages/read
```

Then, the file `package.json` of the consumer records the dependency as
`file:../anagraphe/packages/read`, and each change of the sources of the package takes effect after
a new build.

## Ports

A host implements the three port interfaces declared below, with every path relative to the root
of the open repository:

```ts
interface FileSource {
  read(path: string): Promise<string | null>;
}

interface BindingResolver {
  bind(path: string, text: string, data: Readonly<Record<string, unknown>>): Promise<RecordBinding>;
}
interface RecordBinding {
  readonly contract: string | null; // the logical contract of the record, such as its _schema
  readonly schema: string | null; // the key of its schema, passed back to the loader
  readonly dependencies: readonly string[]; // paths whose change can change the binding
}

interface SchemaLoader {
  load(schema: string): Promise<SchemaLoading>;
}
type SchemaLoading =
  | { readonly status: "loaded"; readonly schema: LoadedSchema }
  | { readonly status: "failed"; readonly reason: string; readonly dependencies: readonly string[] };
interface LoadedSchema {
  readonly root: string;
  document(key: string): unknown;
  locate(address: string, from: string): string | null; // the document of the address of a $ref
  readonly dependencies: readonly string[];
}
```

The binding resolver names the contract and the schema of a record. Its rule belongs to the host,
for instance a modeline, a path rule, or the key `_schema` read through a schema registry. A loaded
schema locates the key of the document named by the address of a `$ref`, an absolute `$id` or a
relative path. The package recognizes a target field by the URI of the definition `target`, the
constant `TARGET_REFERENCE`, so the schema loader need not supply the resource of the addressing.

## Usage

The live index holds the records of the open repository, and the host reports each event of its
files to it, as the example below shows:

```ts
import { RepositoryIndex, deriveIdentity, readDeclaredIdentity, readTarget } from "@anagraphe/read";

// The host reads the section repository of anagraphe.yml, and knows the folder of the vault.
const declared = readDeclaredIdentity(configuration.repository);
const identity = deriveIdentity({ remote: null, folder: vaultFolderName, declared });
const index = new RepositoryIndex(
  { files, bindings, schemas },
  { registry: "record-registry.yml", repository: identity.id },
);
await index.rebuild(allPaths); // reads the registry and the records
await index.indexFile(path); // a file created or changed
index.removeFile(path); // a file deleted
await index.renameFile(oldPath, newPath);
await index.dependencyChanged(path); // a schema or a schema registry created, changed or deleted

const reading = readTarget(value);
if (reading.ok) console.log(index.resolve(reading.target));
```

The option `registry` holds the path of the record registry, named by the section `records` of
`anagraphe.yml`, and the value `null` declares no registry. The option `repository` holds the
identifier of the repository, which the package reads from no file. The host derives it with
`deriveIdentity`, as the Python read side derives it. The identifier is the override `repository.id`
of `anagraphe.yml`, else the name of the remote `origin`, else the name of the folder of the root,
each name kept only when the pattern `repository-id` admits it. `readDeclaredIdentity` validates the
section `repository`, and throws `IdentityError` for an invalid one. `deriveIdentity` throws
`IdentityError` when `retired` lists the derived identifier. After a change of that section, the
host passes the new identifier to `setRepository`. The index never reads `repository.yml`, the
retired manifest, as a record.

When an indexing of a file completes after a later indexing or a removal of that file, or after a
rebuild of the index, the index discards the result of that indexing. The method `resolve` returns a
resolution in one of these statuses:

| Status | Meaning |
| --- | --- |
| `resolved` | one record holds the identifier; `unit` is `none`, `present`, `unknown-unit` or `ambiguous-unit` |
| `renamed` | the identifier is retired, and its successors reach a record; `chain` lists them, `target` is the followed target, and `resolution` is `resolved` or `duplicate` |
| `retired` | the identifier is retired, and its successors reach no record |
| `duplicate` | several records hold the identifier |
| `unknown` | no record holds the identifier, and the registry does not retire it |
| `unverified` | the target names another repository, or names any repository while the open repository has no identity |
| `repository` | the target names the open repository itself |

## API

The functions, the class and the constants are grouped by reading:

| Reading | Exports |
| --- | --- |
| targets | `readTarget`, `normalize`, `sameTarget`, `written`, `formatTarget` |
| contracts of a target field | `readContracts`, `admits`, `contractVerdict` |
| declarations of a schema | `readDeclarations` |
| records | `parseRecord`, `readRecord`, `formatOf` |
| identity of a repository | `deriveIdentity`, `readDeclaredIdentity`, `remoteName`, `IdentityError`, `RETIRED_MANIFEST_FILE` |
| record registry | `readRegistry`, `checkRegistry`, `lookup`, `follow`, `REGISTRY_FILE` |
| live index | `RepositoryIndex` |
| key paths and YAML | `valuesAt`, `pointer`, `readYaml` |
| field paths | `parseFieldPath`, `parseFieldPathPattern`, `printFieldPath`, `isFieldPath`, `isFieldPathPattern`, `toPointer`, `fromPointer`, `pointerTokens`, `matchNodes`, `expand`, `ANY_ITEM`, `ANY_KEY`, `FieldPathError`, `PointerError` |
| resources | `ADDRESSING_ID`, `TARGET_REFERENCE`, `REPOSITORY_CONTRACT`, `REGISTRY_CONTRACT`, `REGISTRY_ID`, `matches`, `IMPLEMENTED_SPECIFICATION` |
| kinds of problem | `INVALID_IDENTIFIER_DECLARATION`, `INVALID_TARGET_CONTRACT`, `UNRESOLVED_REFERENCE`, `UNREADABLE_SCHEMA`, `IDENTITY_DISAGREEMENT` |

The [logical targets specification](../../docs/specification/logical-targets.md), the
[record registry specification](../../docs/specification/record-registry.md) and the
[field paths specification](../../docs/specification/field-paths.md) state each reading.
The function `readYaml` reads a YAML text as PyYAML reads it, so that a scalar such as `y`, `09` or
`1e3` remains a string, as on the Python read side. The constant `IMPLEMENTED_SPECIFICATION`
declares the implemented versions, as the
[versioning rules](../../docs/specification/logical-targets.md#versioning) state.

## Development

The package generates the module `src/generated/resources.ts` from the packaged schemas of
Anagraphe, so that no pattern is copied by hand. The scripts `typecheck`, `lint`, `test` and `build` run the generator first. The commands
below run the checks of the continuous integration:

```sh
npm install
npm run typecheck
npm run lint
npm run format:check
npm test
npm pack --dry-run
```

## License

The package is licensed under GPL-3.0-or-later, as Anagraphe is.
