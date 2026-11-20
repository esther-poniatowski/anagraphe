"""
The kinds of issue that the check of the logical targets can report, with their descriptions.

The kinds of the first version are those of ADR 0006, and ADR 0007 adds the two kinds of a target
naming a retired identifier. The versioning rules of the logical-targets specification add
the two kinds of the comparison with the versions declared by another read side of the repository. Three further kinds report a file or a schema that the check cannot
read, so that no record is skipped without a finding: an unreadable record, and the two kinds of
the reader of schemas of the core, which the bindings report as well. ADR 0009 adds the kinds of
the record resolver, which reads a target into another repository at a selected state, and extends
five kinds to such a target: an unknown record, an unreadable record, an invalid registry, and the
two kinds of a retired identifier. The derivation of the identity of a repository replaces the two
kinds of its former manifest by two warnings, a disagreement of the derived names and a manifest
left at the root, and the generation of the record registry refuses a repository without
identity. The keyword ``x-units`` adds two kinds: an invalid declaration, and a value naming no unit
of the arrays that its field admits.
"""

from __future__ import annotations

from anagraphe_read._core.issues import IssueKind
from anagraphe_read._core.schemas import UNREADABLE_SCHEMA, UNRESOLVED_REFERENCE

#: A target field holding a value that is not a logical target.
INVALID_TARGET = "invalid-target"
#: A keyword ``x-identifier`` that is not a dotted path of property names of its schema.
INVALID_IDENTIFIER_DECLARATION = "invalid-identifier-declaration"
#: A keyword ``x-target-contract`` that is not a non-empty list of contract identifiers.
INVALID_TARGET_CONTRACT = "invalid-target-contract"
#: A keyword ``x-units`` that is not a non-empty list of field paths, each naming an array of the
#: record whose items are units.
INVALID_UNITS_DECLARATION = "invalid-units-declaration"
#: A record of a contract declaring ``x-identifier``, holding no value there.
MISSING_IDENTIFIER = "missing-identifier"
#: An identifier outside the pattern of ``record-id``, a unit identifier outside the pattern of
#: ``unit-id``, or a later key path of the metadata source holding another identifier.
INVALID_IDENTIFIER = "invalid-identifier"
#: An identifier held by two records of the repository.
DUPLICATE_IDENTIFIER = "duplicate-identifier"
#: A remote name and a folder name deriving two different identifiers, without an override.
IDENTITY_DISAGREEMENT = "identity-disagreement"
#: A ``repository.yml`` left at the root, whose identity the section ``repository`` now declares.
RETIRED_REPOSITORY_MANIFEST = "retired-repository-manifest"
#: A repository without identity, whose record registry would name no repository.
UNIDENTIFIED_REPOSITORY = "unidentified-repository"
#: A target naming an identifier that no record of its repository holds.
UNKNOWN_RECORD = "unknown-record"
#: A target naming an identifier retired with a successor, which the check follows to its record.
RENAMED_TARGET = "renamed-target"
#: A target naming an identifier retired without a successor reaching a record.
RETIRED_TARGET = "retired-target"
#: A target naming a unit that its record does not declare.
UNKNOWN_UNIT = "unknown-unit"
#: A target naming a unit that two units of its record hold.
AMBIGUOUS_UNIT = "ambiguous-unit"
#: A value of a field declaring ``x-units`` naming no unit of the arrays that the field admits.
UNKNOWN_UNIT_REFERENCE = "unknown-unit-reference"
#: A target whose record follows no contract that the field admits.
TARGET_CONTRACT_MISMATCH = "target-contract-mismatch"
#: A target of a field declaring ``x-target-contract``, whose record declares no contract.
UNBOUND_TARGET = "unbound-target"
#: A target into another repository whose record a legitimate gap leaves unverified: its state
#: holds no registry, or the consumer lacks the schemas of the contract of its record.
UNVERIFIED_TARGET = "unverified-target"
#: A record whose frontmatter or document cannot be parsed, which leaves it unread.
UNREADABLE_RECORD = "unreadable-record"
#: A declared read side implementing other versions of the specification than this read side.
READ_SIDE_MISMATCH = "read-side-mismatch"
#: A declared read side whose file or pointer yields no mapping of strings to compare.
UNREADABLE_READ_SIDE = "unreadable-read-side"
#: A record registry violating ``anagraphe:record-registry@1``, here in a state of another
#: repository; the check of the registry reports it in its own repository.
INVALID_RECORD_REGISTRY = "invalid-record-registry"
#: A target naming a retired repository identifier, which the resolver follows to its successor.
RENAMED_REPOSITORY = "renamed-repository"
#: A target naming a repository of which the resolution context selects no state.
UNKNOWN_REPOSITORY = "unknown-repository"
#: A selected state without identity, or whose identity differs from the identifier naming it, or
#: whose configuration is invalid.
INVALID_TARGET_REPOSITORY = "invalid-target-repository"
#: A registered path of another repository naming a symbolic link, which the resolver never follows.
LINKED_TARGET_PATH = "linked-target-path"
#: A registered path of another repository leaving its state.
ESCAPING_TARGET_PATH = "escaping-target-path"
#: A registered path of another repository naming no file, or a record of another identifier.
STALE_TARGET_REGISTRY = "stale-target-registry"
#: A selected state whose bytes fail the verification of the provider.
INVALID_TARGET_STATE = "invalid-target-state"
#: A selected state absent from the machine, or whose access is denied.
UNREADABLE_TARGET_STATE = "unreadable-target-state"

#: Every kind of issue that the check can report.
KINDS: tuple[IssueKind, ...] = (
    IssueKind(INVALID_TARGET, "A target field holds a value that is not a logical target."),
    IssueKind(
        INVALID_IDENTIFIER_DECLARATION,
        "x-identifier is not a dotted path of property names, or names no property of its schema.",
    ),
    IssueKind(
        INVALID_TARGET_CONTRACT,
        "x-target-contract is not a non-empty list of contract identifiers.",
    ),
    IssueKind(
        INVALID_UNITS_DECLARATION,
        "x-units is not a non-empty list of field paths, each naming an array of the record whose "
        "items declare x-identifier.",
    ),
    IssueKind(
        MISSING_IDENTIFIER, "A record holds no value at the identifier field of its contract."
    ),
    IssueKind(
        INVALID_IDENTIFIER,
        "An identifier lies outside the pattern of record-id, a unit identifier outside the "
        "pattern of unit-id, or two key paths of a metadata source hold two identifiers.",
    ),
    IssueKind(DUPLICATE_IDENTIFIER, "Two records of the repository hold one identifier."),
    IssueKind(
        IDENTITY_DISAGREEMENT,
        "Without an override, the remote name and the folder name derive two identifiers.",
        blocking=False,
    ),
    IssueKind(
        RETIRED_REPOSITORY_MANIFEST,
        "repository.yml is left at the root; the section repository of anagraphe.yml replaces it.",
        blocking=False,
    ),
    IssueKind(
        UNIDENTIFIED_REPOSITORY,
        "The repository has no identity, which the record registry names under repository.",
    ),
    IssueKind(UNKNOWN_RECORD, "No record of its repository holds the identifier of a target."),
    IssueKind(
        RENAMED_TARGET,
        "A target names an identifier retired by a rename; the check follows it to the successor.",
        blocking=False,
    ),
    IssueKind(
        RETIRED_TARGET,
        "A target names an identifier retired without a successor that reaches a record.",
    ),
    IssueKind(UNKNOWN_UNIT, "The record of a target holds no unit of its identifier."),
    IssueKind(AMBIGUOUS_UNIT, "Two units of the record of a target hold its identifier."),
    IssueKind(
        UNKNOWN_UNIT_REFERENCE,
        "A value of a field declaring x-units names no unit of the arrays that the field admits.",
    ),
    IssueKind(
        TARGET_CONTRACT_MISMATCH,
        "The contract of the record of a target matches no entry of x-target-contract.",
    ),
    IssueKind(
        UNBOUND_TARGET,
        "The field declares x-target-contract, and the record of its target declares no contract.",
    ),
    IssueKind(
        UNVERIFIED_TARGET,
        "A target into another repository stays unverified: its state holds no registry, or "
        "the schemas of the contract of its record are not held here.",
        blocking=False,
        note=True,
    ),
    IssueKind(
        UNREADABLE_RECORD,
        "The frontmatter or the document of a record cannot be parsed, so it is unread.",
    ),
    IssueKind(
        READ_SIDE_MISMATCH,
        "A declared read side implements other versions of the specification than Anagraphe.",
    ),
    IssueKind(
        UNREADABLE_READ_SIDE,
        "The file or the pointer of a declared read side yields no mapping of strings.",
    ),
    IssueKind(
        UNRESOLVED_REFERENCE, "A $ref of a schema names no readable schema node in the repository."
    ),
    IssueKind(UNREADABLE_SCHEMA, "A schema named by the registry cannot be read."),
    IssueKind(
        INVALID_RECORD_REGISTRY,
        "The record registry of a selected state of another repository violates its contract.",
    ),
    IssueKind(
        RENAMED_REPOSITORY,
        "A target names a retired repository identifier; the resolver follows it to the successor.",
        blocking=False,
    ),
    IssueKind(UNKNOWN_REPOSITORY, "The resolution context selects no state of a named repository."),
    IssueKind(
        INVALID_TARGET_REPOSITORY,
        "A selected state has no identity or another identity, or its configuration is invalid.",
    ),
    IssueKind(
        LINKED_TARGET_PATH,
        "The registered path of a record of another repository names a symbolic link.",
    ),
    IssueKind(
        ESCAPING_TARGET_PATH,
        "The registered path of a record of another repository leaves its state.",
    ),
    IssueKind(
        STALE_TARGET_REGISTRY,
        "The registered path of a record of another repository names no file, or a record of "
        "another identifier.",
    ),
    IssueKind(
        INVALID_TARGET_STATE, "The bytes of a selected state fail the verification of the provider."
    ),
    IssueKind(
        UNREADABLE_TARGET_STATE,
        "A selected state is absent from the machine, or its access is denied.",
        blocking=False,
    ),
)

#: The kinds reporting a file left unanalyzed, which makes a run incomplete.
UNANALYZED = frozenset({UNREADABLE_RECORD, UNREADABLE_SCHEMA})
