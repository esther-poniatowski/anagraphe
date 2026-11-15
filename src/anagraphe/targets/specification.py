"""
The versions of the specification of the addressing that the Python read side implements.

Each read side, in Python and in TypeScript, declares the same mapping, so that a gate can report
a consumer whose two read sides declare different versions. The mapping names the absolute
``$id`` of the resource ``addressing.v1``, and the contracts of the manifest and of the record
registry. The TypeScript package ``@anagraphe/read`` exports it as ``IMPLEMENTED_SPECIFICATION``.

Examples
--------
>>> IMPLEMENTED_SPECIFICATION["registry"]
'anagraphe:record-registry@1'
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from anagraphe.targets.registry.contract import REGISTRY_CONTRACT
from anagraphe.targets.resource import ADDRESSING_ID, REPOSITORY_CONTRACT

#: The implemented version of each resource and contract of the specification, by its role.
IMPLEMENTED_SPECIFICATION: Mapping[str, str] = MappingProxyType(
    {
        "addressing": ADDRESSING_ID,
        "repository": REPOSITORY_CONTRACT,
        "registry": REGISTRY_CONTRACT,
    }
)
