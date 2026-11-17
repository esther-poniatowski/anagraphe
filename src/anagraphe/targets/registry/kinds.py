"""
The kinds of issue that the check of the record registry can report, with their descriptions.

The kinds are those of ADR 0007. Each names the registry as its resource and the JSON Pointer of
its entry as its locus. The defects of the identifiers in the walk, ``missing-identifier``,
``invalid-identifier`` and ``duplicate-identifier``, stay findings of the check of the targets.
"""

from __future__ import annotations

from anagraphe.core.issues import IssueKind

# A registry that cannot be parsed, or that violates ``anagraphe:record-registry@1``: the kind is
# defined beside the kinds of the targets, whose resolver reports it in another repository.
from anagraphe.targets.kinds import INVALID_RECORD_REGISTRY

#: A registry that is absent, or whose entries, repository or form differ from the generation.
STALE_REGISTRY = "stale-registry"
#: An identifier of ``records`` that names no record of the walk, and is not retired.
VANISHED_IDENTIFIER = "vanished-identifier"
#: A retired identifier that a record of the walk holds.
REUSED_IDENTIFIER = "reused-identifier"
#: A ``replaced_by`` naming neither a record of the walk nor a retired identifier.
UNKNOWN_SUCCESSOR = "unknown-successor"

#: Every kind of issue that the check can report.
KINDS: tuple[IssueKind, ...] = (
    IssueKind(
        INVALID_RECORD_REGISTRY,
        "The record registry cannot be parsed, or violates anagraphe:record-registry@1.",
    ),
    IssueKind(
        STALE_REGISTRY,
        "The registry is absent, or differs from the generation in its entries, its repository or "
        "its written form.",
    ),
    IssueKind(
        VANISHED_IDENTIFIER,
        "An identifier of records names no record of the walk, and is not retired.",
    ),
    IssueKind(REUSED_IDENTIFIER, "A record holds a retired identifier."),
    IssueKind(UNKNOWN_SUCCESSOR, "replaced_by names neither a record nor a retired identifier."),
)

#: The kinds stopping the comparisons of the registry, which makes a run incomplete.
UNANALYZED = frozenset({INVALID_RECORD_REGISTRY})
