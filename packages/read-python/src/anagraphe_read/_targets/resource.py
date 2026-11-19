"""
The schema resources of the addressing, published as package data: the resource ``addressing.v1``
and the contract ``anagraphe:repository@1`` of ``repository.yml``. That manifest is retired, since
the identity of a repository is derived; the contract stays published until the files bound to it
migrate.

The patterns of the identifiers, of the entries of ``x-target-contract`` and of the paths of
``x-identifier`` are read from the resource itself by :mod:`anagraphe_read._core.published`, so the read
side states no pattern of its own. A consumer schema references the definition ``target`` by its
absolute URI, :data:`TARGET_REFERENCE`, and Anagraphe recognizes a target field by that URI without
loading the copy that Kleisis materializes in the consumer.
"""

from __future__ import annotations

from anagraphe_read._core.published import ADDRESSING_FILE, matches, pattern, schema

__all__ = [
    "ADDRESSING_FILE",
    "ADDRESSING_ID",
    "REPOSITORY_CONTRACT",
    "REPOSITORY_FILE",
    "TARGET_REFERENCE",
    "matches",
    "pattern",
    "schema",
]

#: The absolute ``$id`` of the resource, which carries its major version.
ADDRESSING_ID = "https://github.com/esther-poniatowski/anagraphe/schemas/addressing.v1.schema.yml"
#: The reference to the definition of a logical target.
TARGET_REFERENCE = f"{ADDRESSING_ID}#/$defs/target"
#: The contract of the retired manifest ``repository.yml``.
REPOSITORY_CONTRACT = "anagraphe:repository@1"
#: The package file of the schema of the retired manifest.
REPOSITORY_FILE = "repository.schema.yml"
