"""The kinds of issue that the indexes report, each with its description and default level.

The catalogue lists every kind that :mod:`anagraphe.indexes` can report, whether or not a run
reports it, so that a findings log declares the rules that the section evaluates. A new kind of
issue joins the catalogue; the tests compare the catalogue with the kinds written in the sources.
"""

from __future__ import annotations

from anagraphe.core.issues import IssueKind

KINDS: tuple[IssueKind, ...] = (
    IssueKind("stale-block", "A generated region differs from its rendering."),
    IssueKind("ungenerated-index", "An index that must be generated holds no region of groups."),
    IssueKind("index-type", "An index declares an unknown or invalid index type."),
    IssueKind("malformed-block", "A marker of a generated region is malformed."),
    IssueKind("malformed-groups", "The declaration of the groups of an index is malformed."),
    IssueKind("index-prose", "An index holds prose outside its slots.", blocking=False),
    IssueKind("retired-key", "A file declares a retired key."),
    IssueKind(
        "migration-key",
        "A file declares a retired key tolerated by a declared migration class.",
        blocking=False,
    ),
    IssueKind(
        "unmigrated-member",
        "A member declares no entry field, so no group lists it yet.",
        blocking=False,
    ),
    IssueKind("unplaced-member", "No group of its index holds a member."),
    IssueKind("unknown-file", "The key files of an index names no file of its folder."),
    IssueKind("mixed-modes", "A group stands under the heading of a group of another mode."),
    IssueKind("nest-cycle", "A member closes a cycle of the nesting key of its group."),
    IssueKind("ignored-order", "An order declared for a group is ignored."),
    IssueKind("undeclared-value", "A value lies outside the declared values of its key."),
    IssueKind(
        "unranked-value",
        "A member holds a value that the order of its group does not rank.",
        blocking=False,
    ),
    IssueKind("missing-sequence", "A sequence group has neither a sequence nor a build manifest."),
    IssueKind("invalid-link", "A link declared in the metadata names no file, or is malformed."),
    IssueKind(
        "unsequenced-member", "The sequence of its group does not list a member.", blocking=False
    ),
    IssueKind("invalid-context-relation", "A context relation is malformed or undeclared."),
    IssueKind("invalid-external", "The key external names a member of the collection."),
    IssueKind("unarchived-superseded", "A file declares superseded_by without an archived status."),
    IssueKind("missing-alias", "A listed file declares no alias."),
    IssueKind("title-mismatch", "The heading of a note differs from its first alias."),
    IssueKind("index-location", "The key index of a file names another index than its own."),
    IssueKind(
        "missing-purpose",
        "A group displays a purpose that a member does not declare.",
        blocking=False,
    ),
    IssueKind("unknown-task", "The key blocked_by names no declared task."),
    IssueKind("finished-blocker", "The key blocked_by names a closed task.", blocking=False),
    IssueKind("missing-control-file", "A file required by the index type is absent."),
    IssueKind("control-file-role", "A file required by the index type holds another role."),
    IssueKind("duplicate-member", "Groups name one member twice."),
    IssueKind("unknown-filter-key", "A filter of a group names a key that no member declares."),
)
