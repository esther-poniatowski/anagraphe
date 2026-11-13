"""
The logical targets of a repository: the addresses by which a record refers to a record of another
tool, or to a unit inside it, possibly in another repository.

A target is the mapping ``{repository, id, unit}``, published as the definition ``target`` of the
resource ``addressing.v1``. A repository declares its identifier in ``repository.yml``, a record
type declares the field of its identifier by ``x-identifier``, and a consumer types a target field
by ``x-target-contract``. The section ``targets`` of ``anagraphe.yml`` enables the check, which
resolves the targets within one repository.

Examples
--------
A tool reads and compares two targets written in one repository::

    from anagraphe.targets import Target, read_manifest

    repository = read_manifest(root).manifest.id
    same = Target.parse(a).normalized(repository) == Target.parse(b).normalized(repository)
"""

from anagraphe.targets.configuration import TargetConfig
from anagraphe.targets.manifest import Manifest, ManifestReading, check_manifest, read_manifest
from anagraphe.targets.model import InvalidTarget, Reason, Target, admits, parse_contracts
from anagraphe.targets.resource import ADDRESSING_ID, REPOSITORY_CONTRACT, TARGET_REFERENCE
from anagraphe.targets.service import TargetChecker

__all__ = [
    "ADDRESSING_ID",
    "REPOSITORY_CONTRACT",
    "TARGET_REFERENCE",
    "InvalidTarget",
    "Manifest",
    "ManifestReading",
    "Reason",
    "Target",
    "TargetChecker",
    "TargetConfig",
    "admits",
    "check_manifest",
    "parse_contracts",
    "read_manifest",
]
