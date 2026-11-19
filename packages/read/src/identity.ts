/**
 * The identity of a repository: the identifier that a logical target names, and its former
 * identifiers, derived as the Python read side derives them in `anagraphe_read._targets.identity`.
 *
 * The identifier is the override `repository.id` of `anagraphe.yml` when the configuration
 * declares it, else the name of the remote `origin`, else the name of the folder of the root, each
 * name kept only when the pattern `repository-id` of the resource `addressing.v1` admits it. The
 * name of a remote is the last segment of its address, after `/` or the `:` of an scp-like
 * address, without a final `/` and `.git`. The former identifiers come from `repository.retired`.
 *
 * The package reads no Git and no file: the host supplies the address of the remote, the name of
 * the folder, such as the folder of an Obsidian vault, and the section `repository` of its
 * configuration, which {@link readDeclaredIdentity} validates.
 */
import { isMapping } from "./documents/text.js";
import { matches } from "./resources.js";

/** The kind of the warning of a remote name and a folder name deriving two identifiers. */
export const IDENTITY_DISAGREEMENT = "identity-disagreement";
/** The retired manifest of a repository, at its root, which is no record. */
export const RETIRED_MANIFEST_FILE = "repository.yml";

/** Where the identifier of a repository comes from. */
export type IdentitySource = "override" | "remote" | "folder" | "none";

/** The section `repository` of `anagraphe.yml`: the override and the former identifiers. */
export interface DeclaredIdentity {
  /** The override of the identifier, `null` when the section declares none. */
  readonly id: string | null;
  readonly retired: readonly string[];
}

/** A warning of the derivation of the identity. */
export interface IdentityProblem {
  readonly kind: typeof IDENTITY_DISAGREEMENT;
  readonly detail: string;
}

/** The identity of a repository, the source of its identifier, and its warnings. */
export interface Identity {
  /** The identifier, `null` when the repository has no identity. */
  readonly id: string | null;
  readonly retired: readonly string[];
  readonly source: IdentitySource;
  readonly problems: readonly IdentityProblem[];
}

/** An invalid section `repository`, or retired identifiers listing the derived identifier. */
export class IdentityError extends Error {
  override readonly name = "IdentityError";
}

const SECTION_KEYS = ["id", "retired"];

/**
 * Validates the section `repository` of `anagraphe.yml`, `null` or `undefined` for a section
 * declaring nothing.
 *
 * @throws IdentityError If the section is not a mapping, holds an unknown key, an identifier
 *   outside the pattern `repository-id`, a retired identifier twice, or the override among the
 *   retired identifiers.
 */
export function readDeclaredIdentity(section: unknown): DeclaredIdentity {
  if (section === null || section === undefined) return { id: null, retired: [] };
  if (!isMapping(section)) throw new IdentityError("repository must be a mapping");
  const unknown = Object.keys(section)
    .filter((key) => !SECTION_KEYS.includes(key))
    .sort();
  if (unknown.length > 0) {
    throw new IdentityError(`repository declares unknown keys: ${unknown.join(", ")}`);
  }
  const has = (key: string): boolean => Object.prototype.hasOwnProperty.call(section, key);
  const id = section["id"];
  if (has("id") && !matches("repository-id", id)) {
    throw new IdentityError(
      `repository.id: ${String(id)} lies outside the pattern of repository-id`,
    );
  }
  const value = section["retired"] ?? [];
  if (!Array.isArray(value)) {
    throw new IdentityError("repository.retired must be a list of repository identifiers");
  }
  const retired: string[] = [];
  for (const item of value as unknown[]) {
    if (!matches("repository-id", item)) {
      throw new IdentityError(
        `repository.retired: ${String(item)} lies outside the pattern of repository-id`,
      );
    }
    if (retired.includes(item)) {
      throw new IdentityError(`repository.retired lists ${item} more than once`);
    }
    retired.push(item);
  }
  const override = has("id") ? (id as string) : null;
  if (override !== null && retired.includes(override)) {
    throw new IdentityError(
      `repository.retired lists the identifier ${override}, and a retired identifier is never reused`,
    );
  }
  return { id: override, retired };
}

/**
 * Returns the name of a remote address: its last segment, after `/` or the `:` of an scp-like
 * address, without a final `/` and `.git`; `null` for an absent or empty name.
 */
export function remoteName(url: string | null): string | null {
  if (url === null) return null;
  let name = url.trim().replace(/\/+$/, "");
  if (name.endsWith(".git")) name = name.slice(0, -".git".length);
  name = name.replace(/\/+$/, "");
  const segment = name.replace(/:/g, "/").split("/").pop() ?? "";
  return segment === "" ? null : segment;
}

/** Returns an identity whose identifier is none of its retired identifiers, or throws. */
function unreused(identity: Identity): Identity {
  if (identity.id !== null && identity.retired.includes(identity.id)) {
    const repair = identity.source === "override" ? "" : "; declare repository.id";
    throw new IdentityError(
      `repository.retired lists ${identity.id}, the identifier of the ${identity.source}, and a retired identifier is never reused${repair}`,
    );
  }
  return identity;
}

/**
 * Derives the identity from the address of the remote `origin`, the name of the folder of the root,
 * and the declared section; a folder of `null` names no identifier, as for a state of another
 * repository.
 *
 * @throws IdentityError If the retired identifiers list the derived identifier.
 */
export function deriveIdentity(input: {
  readonly remote: string | null;
  readonly folder: string | null;
  readonly declared: DeclaredIdentity | null;
}): Identity {
  const retired = input.declared?.retired ?? [];
  const override = input.declared?.id ?? null;
  if (override !== null) {
    return unreused({ id: override, retired, source: "override", problems: [] });
  }
  const name = remoteName(input.remote);
  const remote = matches("repository-id", name) ? name : null;
  const folder = matches("repository-id", input.folder) ? input.folder : null;
  const problems: IdentityProblem[] =
    remote !== null && folder !== null && remote !== folder
      ? [
          {
            kind: IDENTITY_DISAGREEMENT,
            detail: `the remote origin names the repository ${remote}, and its folder names it ${folder}; the identifier is ${remote}. Declare repository: {id: <identifier>} in anagraphe.yml to settle it`,
          },
        ]
      : [];
  if (remote !== null) return unreused({ id: remote, retired, source: "remote", problems });
  if (folder !== null) return unreused({ id: folder, retired, source: "folder", problems });
  return { id: null, retired, source: "none", problems };
}
