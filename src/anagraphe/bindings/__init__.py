"""
The check of the bindings of the texts of a repository, ``anagraphe bindings check``.

The bindings themselves, their roles and their resolution along the directory chain belong to the
read distribution, ``anagraphe-read``, whose interface is :mod:`anagraphe_read`.
"""

from anagraphe.bindings.service import BindingChecker

__all__ = ["BindingChecker"]
