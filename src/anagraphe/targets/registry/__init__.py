"""
The writer and the check of the record registry of a repository, under ADR 0007.

The registry is written in the contract ``anagraphe:record-registry@1`` by
``anagraphe records write``, checked by ``anagraphe records check``, and extended by
``anagraphe records retire``. The model of the contract and its reading belong to the read
distribution, ``anagraphe-read``, so that a resolver of another repository reads a registry
without the command line.
"""

from anagraphe.targets.registry.service import RegistryService, RetireRefused, WriteResult

__all__ = ["RegistryService", "RetireRefused", "WriteResult"]
