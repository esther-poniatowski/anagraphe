"""
The kinds of issue that the check of the bindings can report, with their descriptions.
"""

from __future__ import annotations

from anagraphe.core.issues import IssueKind

#: A text that a condition requires to be bound, bound to no value.
UNBOUND = "unbound-text"
#: A declaration naming no value, or a value that is not a non-empty string.
INVALID = "invalid-binding"
#: A file whose frontmatter or record cannot be parsed, which leaves its own declaration unread.
UNREADABLE_SOURCE = "unreadable-binding-source"
#: A mark ``x-binds`` that names no role, marks a whole record, or sits where a field has no key path.
INVALID_MARK = "invalid-schema-binding"
#: A ``$ref`` of a schema that names no readable schema node inside the repository.
UNRESOLVED_REFERENCE = "unresolved-schema-reference"
#: A schema named by the registry that cannot be read, which leaves its records unanalyzed.
UNREADABLE_SCHEMA = "unreadable-schema"

#: Every kind of issue that the check can report.
KINDS: tuple[IssueKind, ...] = (
    IssueKind(
        UNBOUND, "A text that the repository requires to be bound for a role is bound to no value."
    ),
    IssueKind(INVALID, "A binding names no value, or a value that is not a non-empty string."),
    IssueKind(
        UNREADABLE_SOURCE, "The frontmatter or the record holding a binding cannot be parsed."
    ),
    IssueKind(
        INVALID_MARK, "A schema mark x-binds names no role, or sits where a field has no key path."
    ),
    IssueKind(
        UNRESOLVED_REFERENCE, "A $ref of a schema names no readable schema node in the repository."
    ),
    IssueKind(UNREADABLE_SCHEMA, "A schema named by the registry cannot be read."),
)

#: The kinds reporting a file left unanalyzed, which makes a run incomplete.
UNANALYZED = frozenset({UNREADABLE_SOURCE, UNREADABLE_SCHEMA})
