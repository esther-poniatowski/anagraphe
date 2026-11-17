"""
The verification of a record held by a target: the unit that the target names, and the contracts
that its field admits.

The check of a local target and the record resolver apply the same rule. A record read from another
repository may follow a contract whose schemas the consumer lacks. Its units declared by
``x-identifier`` and its contracts declared by ``x-implements`` are then unknown, so a unit or a
contract that the record does not visibly hold stays unverified, instead of failing.
"""

from __future__ import annotations

from dataclasses import dataclass

from anagraphe.targets.kinds import (
    AMBIGUOUS_UNIT,
    TARGET_CONTRACT_MISMATCH,
    UNBOUND_TARGET,
    UNKNOWN_UNIT,
    UNVERIFIED_TARGET,
)
from anagraphe.targets.model import Target, admits
from anagraphe.targets.records import Record


@dataclass(frozen=True)
class Finding:
    """One finding on a target: its kind, and its detail opening on the written target."""

    kind: str
    detail: str


def held_findings(
    target: Target,
    contracts: tuple[tuple[str, ...], ...],
    held: Record,
    schemas_known: bool = True,
) -> list[Finding]:
    """Return the findings of the record held by a target: its unit, then its contract.

    Parameters
    ----------
    target : anagraphe.targets.model.Target
        The target, written as the findings name it.
    contracts : tuple of tuple of str
        The entries of each ``x-target-contract`` declared on the citing field.
    held : Record
        The record of the identifier of the target.
    schemas_known : bool
        Whether the consumer holds the schemas of the contract of the record. When it does not,
        a unit or a contract that the record does not visibly hold yields ``unverified-target``.
    """
    findings: list[Finding] = []
    written = str(target)
    count = held.units.count(target.unit) if target.unit is not None else 1
    if count == 0 and not schemas_known:
        findings.append(
            Finding(
                UNVERIFIED_TARGET,
                f"{written}: the record {held.rel} holds no anchor {target.unit}, and the "
                f"schemas of its contract {held.contract}, which may declare its units, are not "
                "held by this repository",
            )
        )
    elif count != 1:
        kind, detail = (
            (UNKNOWN_UNIT, "declares no unit") if not count else (AMBIGUOUS_UNIT, "holds two units")
        )
        findings.append(
            Finding(
                kind, f"{written}: the record {held.rel} {detail} of the identifier {target.unit}"
            )
        )
    if not contracts:
        return findings
    if held.contract is None:
        findings.append(
            Finding(
                UNBOUND_TARGET,
                f"{written}: the field admits the contracts {listed(contracts)}, and the record "
                f"{held.rel} declares no contract",
            )
        )
        return findings
    implemented = held.schema.implements if held.schema is not None else ()
    followed = (held.contract, *implemented)
    failed = tuple(entries for entries in contracts if not admits(entries, followed))
    if failed and not schemas_known:
        findings.append(
            Finding(
                UNVERIFIED_TARGET,
                f"{written}: the record {held.rel} follows {held.contract}, which no entry of "
                f"{listed(failed)} admits, and the schemas of {held.contract}, which may declare "
                "further contracts, are not held by this repository",
            )
        )
    elif failed:
        findings.append(
            Finding(
                TARGET_CONTRACT_MISMATCH,
                f"{written}: the record {held.rel} follows {', '.join(followed)}, which no entry "
                f"of {listed(failed)} admits",
            )
        )
    return findings


def listed(declarations: tuple[tuple[str, ...], ...]) -> str:
    """Return the entries of declarations of ``x-target-contract``, each declaration bracketed.

    Examples
    --------
    >>> listed((("a:b", "c:d@1"), ("e:f",)))
    '[a:b, c:d@1] and [e:f]'
    """
    return " and ".join(f"[{', '.join(entries)}]" for entries in declarations)
