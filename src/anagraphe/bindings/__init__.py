"""
The bindings of the texts of a repository: the values that a text is bound to for the role of a
tool, resolved along the directory chain.

A tool reading a binding declares its role and its merge rule, and the repository names, in the
section ``bindings`` of ``anagraphe.yml``, the key holding each role. A text declares the role in
its frontmatter, a record in the fields that its schema marks by ``x-binds``, and the index of each
enclosing directory declares it for every file below it.

Examples
--------
A tool resolves the glossary of a note through the configuration of its repository::

    from anagraphe.bindings import BindingResolver, Role
    from anagraphe.configuration import load_config

    config = load_config(root, root / "anagraphe.yml").bindings
    binding = BindingResolver(root, config).resolve("notes/a.md", Role("onomasia.glossary"))
"""

from anagraphe.bindings.configuration import BindingConfig, RecordSchemas, RoleSpec
from anagraphe.bindings.contract import CONTRACT
from anagraphe.bindings.model import Binding, Declaration, Merge, Role
from anagraphe.bindings.resolution import BindingResolver
from anagraphe.bindings.service import BindingChecker

__all__ = [
    "CONTRACT",
    "Binding",
    "BindingChecker",
    "BindingConfig",
    "BindingResolver",
    "Declaration",
    "Merge",
    "RecordSchemas",
    "Role",
    "RoleSpec",
]
