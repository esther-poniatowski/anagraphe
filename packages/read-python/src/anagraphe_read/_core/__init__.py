"""
The shared core of the read side: issues, configuration primitives, metadata, schemas, exclusions,
file walks and Git state.

The core depends on no other subpackage of :mod:`anagraphe_read`, and every other subpackage
depends on it. The subpackage is private: the interface of the distribution is the top-level
module :mod:`anagraphe_read`.
"""
