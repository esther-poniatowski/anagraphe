"""
The kinds of issue that the check of the logical targets can report, with their descriptions.

The kinds of the first version are those of ADR 0006. Three further kinds report a file or a schema
that the check cannot read, so that no record is skipped without a finding: an unreadable record,
and the two kinds of the reader of schemas of the core, which the bindings report as well.
"""

from __future__ import annotations

from anagraphe.core.issues import IssueKind
from anagraphe.core.schemas import UNREADABLE_SCHEMA, UNRESOLVED_REFERENCE

#: A target field holding a value that is not a logical target.
INVALID_TARGET = "invalid-target"
#: A keyword ``x-identifier`` that is not a dotted path of property names of its schema.
INVALID_IDENTIFIER_DECLARATION = "invalid-identifier-declaration"
#: A keyword ``x-target-contract`` that is not a non-empty list of contract identifiers.
INVALID_TARGET_CONTRACT = "invalid-target-contract"
#: A record of a contract declaring ``x-identifier``, holding no value there.
MISSING_IDENTIFIER = "missing-identifier"
#: An identifier outside the pattern of ``record-id``.
INVALID_IDENTIFIER = "invalid-identifier"
#: An identifier held by two records of the repository.
DUPLICATE_IDENTIFIER = "duplicate-identifier"
#: A ``repository.yml`` that violates ``anagraphe:repository@1``.
INVALID_REPOSITORY_MANIFEST = "invalid-repository-manifest"
#: A ``repository.yml`` written in the form ``schema_version: 1``.
LEGACY_REPOSITORY_MANIFEST = "legacy-repository-manifest"
#: A target of the same repository naming an identifier that no record holds.
UNKNOWN_RECORD = "unknown-record"
#: A target naming a unit that its record does not declare.
UNKNOWN_UNIT = "unknown-unit"
#: A target naming a unit that two units of its record hold.
AMBIGUOUS_UNIT = "ambiguous-unit"
#: A target whose record follows no contract that the field admits.
TARGET_CONTRACT_MISMATCH = "target-contract-mismatch"
#: A target of a field declaring ``x-target-contract``, whose record declares no contract.
UNBOUND_TARGET = "unbound-target"
#: A target into another repository, whose form alone is checked until the resolver exists.
UNVERIFIED_TARGET = "unverified-target"
#: A record whose frontmatter or document cannot be parsed, which leaves it unread.
UNREADABLE_RECORD = "unreadable-record"

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
        MISSING_IDENTIFIER, "A record holds no value at the identifier field of its contract."
    ),
    IssueKind(INVALID_IDENTIFIER, "An identifier lies outside the pattern of record-id."),
    IssueKind(DUPLICATE_IDENTIFIER, "Two records of the repository hold one identifier."),
    IssueKind(INVALID_REPOSITORY_MANIFEST, "repository.yml violates anagraphe:repository@1."),
    IssueKind(
        LEGACY_REPOSITORY_MANIFEST, "repository.yml writes schema_version: 1.", blocking=False
    ),
    IssueKind(UNKNOWN_RECORD, "No record of the repository holds the identifier of a target."),
    IssueKind(UNKNOWN_UNIT, "The record of a target holds no unit of its identifier."),
    IssueKind(AMBIGUOUS_UNIT, "Two units of the record of a target hold its identifier."),
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
        "A target names another repository, whose form alone is checked.",
        blocking=False,
        note=True,
    ),
    IssueKind(
        UNREADABLE_RECORD,
        "The frontmatter or the document of a record cannot be parsed, so it is unread.",
    ),
    IssueKind(
        UNRESOLVED_REFERENCE, "A $ref of a schema names no readable schema node in the repository."
    ),
    IssueKind(UNREADABLE_SCHEMA, "A schema named by the registry cannot be read."),
)

#: The kinds reporting a file left unanalyzed, which makes a run incomplete.
UNANALYZED = frozenset({UNREADABLE_RECORD, UNREADABLE_SCHEMA})
