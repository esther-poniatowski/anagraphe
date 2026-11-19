"""
Fields that describe a file in its index entry, and the rules that each value obeys.

The decision on generated index entries assigns its entry fields to the metadata of a file: its
purpose, its contributions, and the tasks blocking its status (``blocked_by``). The section
``indexes`` supplies the closed value sets of the categorical keys and the relations admitted by
the table ``context_relations`` of an index, read from the enumerations of its metadata schema, and
the statuses of an archived note, under ``archived_statuses``. The form of a prose field, such as a
purpose, is checked by Hermeneia, not by Anagraphe.

Every validator returns a list of problems, each a short lowercase clause, and an empty list for
a valid value. The caller attaches the file and the kind of issue.

Examples
--------
>>> rules = FieldRules({"kind": ("keynote", "talk")}, frozenset({"contrasts"}), ("archived",))
>>> rules.values["kind"], sorted(rules.relations or ()), rules.archived
(('keynote', 'talk'), ['contrasts'], ('archived',))
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

#: A task identifier, declared by ``🆔`` on a checklist line.
TASK_ID = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class FieldRules:
    """The rules of the entry fields, supplied by the section ``indexes``."""

    #: The declared values of each categorical key, in their declared order.
    values: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    #: The relations admitted by the table ``context_relations`` of an index; None when the
    #: metadata schema enumerates none, so that any relation is admitted.
    relations: frozenset[str] | None = None
    #: The statuses of an archived note, the only notes that may declare ``superseded_by``.
    archived: tuple[str, ...] = ()

    def check_superseded(self, status: str | None) -> list[str]:
        """Return the problems of a note declaring ``superseded_by``, whose status must be archived.

        Examples
        --------
        >>> rules = FieldRules(archived=("archived",))
        >>> rules.check_superseded("archived"), rules.check_superseded("wip")
        ([], ['the status wip is not declared under indexes.archived_statuses: archived'])
        >>> FieldRules().check_superseded(None)
        ['the file declares no status']
        """
        if status is None:
            return ["the file declares no status"]
        if status in self.archived:
            return []
        declared = ", ".join(self.archived) if self.archived else "none declared"
        return [f"the status {status} is not declared under indexes.archived_statuses: {declared}"]

    @staticmethod
    def check_blocked_by(value: Any) -> list[str]:
        """Return the problems of a ``blocked_by`` value, a list of task identifiers.

        Examples
        --------
        >>> FieldRules.check_blocked_by(["brief-draft", "two words"])
        ['not a task identifier: two words']
        >>> FieldRules.check_blocked_by("brief-draft")
        ['must be a list of task identifiers']
        """
        if not isinstance(value, list):
            return ["must be a list of task identifiers"]
        return [f"not a task identifier: {item}" for item in value if not TASK_ID.match(str(item))]
