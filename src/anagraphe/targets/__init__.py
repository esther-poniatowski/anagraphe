"""
The commands of Anagraphe on the logical targets and the records of a repository: the check of
the targets, the record registry and the migration of the contracts of the records.

The logical targets themselves, the identity of a repository and the record resolver belong to
the read distribution, ``anagraphe-read``, whose interface is :mod:`anagraphe_read`. This
subpackage composes them into the commands ``anagraphe targets check``, ``anagraphe records`` and
``anagraphe records migrate``.
"""

from anagraphe.targets.service import TargetChecker

__all__ = ["TargetChecker"]
