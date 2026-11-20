"""
The commands of Anagraphe on the logical targets and the records of a repository: the check of
the targets, the record registry, the migration of the contracts of the records, and the rename of
a repository identifier.

The logical targets themselves, the identity of a repository and the record resolver belong to
the read distribution, ``anagraphe-read``, whose interface is :mod:`anagraphe_read`. This
subpackage composes them into the commands ``anagraphe targets check``, ``anagraphe records``,
``anagraphe records migrate`` and ``anagraphe repository rename``.
"""

from anagraphe.targets.service import TargetChecker

__all__ = ["TargetChecker"]
