"""
The record registry of a repository: the committed map from the identifiers of its records to
their files, and the permanent list of its retired identifiers, under ADR 0007.

A resolver of another repository reads the registry of a selected state instead of walking that
state. The registry is written in the contract ``anagraphe:record-registry@1`` by
``anagraphe records write``, checked by ``anagraphe records check``, and extended by
``anagraphe records retire``. The section ``records`` of ``anagraphe.yml`` names its file. Within
one repository, the check of the targets keeps its walk, and reads the retired identifiers from the
registry.

Examples
--------
A tool reads the registry of a repository and finds the file of a record::

    from anagraphe.targets.registry import read_registry

    registry = read_registry(root / "record-registry.yml", "record-registry.yml").registry
    entry = registry.records["mixture-input"] if registry is not None else None
"""

from anagraphe.targets.registry.configuration import DEFAULT_PATH, RecordsConfig
from anagraphe.targets.registry.contract import (
    REGISTRY_CONTRACT,
    REGISTRY_ID,
    Entry,
    Format,
    RecordRegistry,
    RegistryReading,
    Retirement,
    follow,
    read_registry,
)
from anagraphe.targets.registry.service import RegistryService, RetireRefused, WriteResult

__all__ = [
    "DEFAULT_PATH",
    "REGISTRY_CONTRACT",
    "REGISTRY_ID",
    "Entry",
    "Format",
    "RecordRegistry",
    "RecordsConfig",
    "RegistryReading",
    "RegistryService",
    "Retirement",
    "RetireRefused",
    "WriteResult",
    "follow",
    "read_registry",
]
