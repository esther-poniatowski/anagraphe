/**
 * The conformance cases of `specs/conformance/identity.yml`: the validation of the section
 * `repository` of `anagraphe.yml`, and the derivation of the identity of a repository.
 */
import { describe, expect, it } from "vitest";
import { IdentityError, deriveIdentity, readDeclaredIdentity } from "../src/identity.js";
import { suite } from "./support/conformance.js";

const SUITE = suite("identity.yml");

interface SectionCase {
  readonly id: string;
  readonly section: unknown;
  readonly valid: boolean;
}

interface DerivationCase {
  readonly id: string;
  readonly remote: string | null;
  readonly folder: string | null;
  readonly declared: unknown;
  readonly identity?: string | null;
  readonly retired?: readonly string[];
  readonly source?: string;
  readonly warnings?: readonly string[];
  readonly error?: boolean;
}

const SECTIONS = SUITE["sections"] as SectionCase[];
const DERIVATIONS = SUITE["derivations"] as DerivationCase[];

describe.each(SECTIONS)("the section case $id", (check) => {
  it("is valid exactly when the case states it", () => {
    const read = (): unknown => readDeclaredIdentity(check.section);
    if (check.valid) expect(read).not.toThrow();
    else expect(read).toThrow(IdentityError);
  });
});

describe.each(DERIVATIONS)("the derivation case $id", (check) => {
  it("derives the identity of the case, or fails", () => {
    const declared = check.declared === null ? null : readDeclaredIdentity(check.declared);
    const derive = (): unknown =>
      deriveIdentity({ remote: check.remote, folder: check.folder, declared });
    if (check.error === true) {
      expect(derive).toThrow(IdentityError);
      return;
    }
    const identity = deriveIdentity({ remote: check.remote, folder: check.folder, declared });
    expect({
      identity: identity.id,
      retired: identity.retired,
      source: identity.source,
      warnings: identity.problems.map((problem) => problem.kind),
    }).toEqual({
      identity: check.identity,
      retired: check.retired,
      source: check.source,
      warnings: check.warnings,
    });
  });
});
