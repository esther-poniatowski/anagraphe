"""
The versions of the specification of the addressing that the Python read side implements.

Each read side, in Python and in TypeScript, declares the same mapping, so that a gate can report
a consumer whose two read sides declare different versions. The mapping names the absolute
``$id`` of the resource ``addressing.v1``, and the contract of the record registry. The contract
``anagraphe:repository@1`` of the retired manifest is no longer read, since the identity of a
repository is derived, so the mapping names it no longer. The TypeScript package
``@anagraphe/read`` exports the same mapping as ``IMPLEMENTED_SPECIFICATION``.

Examples
--------
>>> IMPLEMENTED_SPECIFICATION["registry"]
'anagraphe:record-registry@1'
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from anagraphe.targets.registry.contract import REGISTRY_CONTRACT
from anagraphe.targets.resource import ADDRESSING_ID

#: The implemented version of each resource and contract of the specification, by its role.
IMPLEMENTED_SPECIFICATION: Mapping[str, str] = MappingProxyType(
    {
        "addressing": ADDRESSING_ID,
        "registry": REGISTRY_CONTRACT,
    }
)
