"""
The bindings of the texts of a repository: the values that a text is bound to for the role of a
tool, resolved along the directory chain.

A tool reading a binding declares its role and its merge rule, and the repository names, in the
section ``bindings`` of ``anagraphe.yml``, the key holding each role. A text declares the role in
its frontmatter, a record in the fields that its schema marks by ``x-binds``, and the index of each
enclosing directory declares it for every file below it.

The subpackage is private: the interface of the distribution is the top-level module
:mod:`anagraphe_read`.
"""
