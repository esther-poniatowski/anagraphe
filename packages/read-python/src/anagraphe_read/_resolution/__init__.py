"""
The record resolver of ADR 0009: it locates and reads the record of another repository named by a
logical target, verified against a selected state of that repository.

The subpackage composes five parts:

- the section ``resolution`` of ``anagraphe.yml`` and the machine file of the local clones,
  :mod:`anagraphe_read._resolution.configuration`;
- the resolution context of a root, derived from its submodules and its declared repositories,
  :mod:`anagraphe_read._resolution.context`;
- the port of a repository-state provider, with an in-memory provider and an empty one,
  :mod:`anagraphe_read._resolution.provider`;
- the Git provider of ADR 0010, :mod:`anagraphe_read._resolution.git`;
- the operations ``resolve`` and ``read``, :mod:`anagraphe_read._resolution.resolver`.

The subpackage is private: the interface of the distribution is the top-level module
:mod:`anagraphe_read`.
"""
