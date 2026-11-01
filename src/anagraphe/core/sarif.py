"""Write the issues of a check as a log of the findings profile of Elenchos, a subset of SARIF 2.1.0.

The log holds one run of the driver ``anagraphe``, whose driver lists every kind of every section
as the rule ``<section>/<kind>``, whether or not the run reports it. Each result names its rule,
its level and its message, the file as a physical location relative to ``SRCROOT``, and one logical
location ``path:<file>#<locus>``. The physical location holds the line of an issue that has one,
and no region for an issue of the whole file or of a key of the metadata. The gate builds the identity of
each result and writes its suppressions; a producer writes neither.

The run holds one invocation, which states whether the analysis ran to its end. A run that stopped,
or that could not read a file, declares a failed invocation with one notification of level
``error`` stating why. A run whose analysis never began, such as a run with an invalid
configuration, omits ``results``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from anagraphe.core.issues import Issue, IssueKind

SARIF_VERSION = "2.1.0"
SARIF_SCHEMA = (
    "https://docs.oasis-open.org/sarif/sarif/v2.1.0/errata01/os/schemas/sarif-schema-2.1.0.json"
)
TOOL_NAME = "anagraphe"
URI_BASE_ID = "SRCROOT"
DISCRIMINATOR_KEY = "discriminator/v1"

# The characters of an RFC 3986 path segment kept as written, besides unreserved characters: the
# sub-delimiters and ``@``. A colon is encoded, so that a first segment never reads as a scheme.
_URI_SAFE = "/!$&'()*+,;=@"


@dataclass(frozen=True)
class Section:
    """The issues reported by one section of the configuration, and every kind it can report."""

    name: str
    kinds: tuple[IssueKind, ...]
    issues: tuple[Issue, ...] = ()

    def rule_id(self, kind: str) -> str:
        """Return the identifier of the rule of a kind, ``<section>/<kind>``.

        Examples
        --------
        >>> Section("references", ()).rule_id("broken")
        'references/broken'
        """
        return f"{self.name}/{kind}"


def level(blocking: bool) -> str:
    """Return the SARIF level of an issue: ``error`` when it blocks, ``warning`` otherwise."""
    return "error" if blocking else "warning"


def logical_name(issue: Issue) -> str:
    """Return ``path:<file>``, followed by ``#<locus>`` when the locus is not empty.

    In the resource, ``%`` is written ``%25`` and ``#`` is written ``%23``, so that the name splits
    at its first ``#``; the locus is written as is.

    Examples
    --------
    >>> logical_name(Issue("notes/a#1.md", 3, "broken", "x", locus="link:b.md#^c"))
    'path:notes/a%231.md#link:b.md#^c'
    >>> logical_name(Issue("100%.md", 1, "stale-block", "x"))
    'path:100%25.md'
    """
    resource = "path:" + issue.rel.replace("%", "%25").replace("#", "%23")
    return f"{resource}#{issue.locus}" if issue.locus else resource


def artifact_uri(rel: str) -> str:
    """Return a repository-relative path percent-encoded as a relative URI reference.

    Examples
    --------
    >>> artifact_uri("notes/a b#1.md")
    'notes/a%20b%231.md'
    """
    return quote(rel, safe=_URI_SAFE)


def _result(section: Section, issue: Issue) -> dict[str, Any]:
    """Return the result of one issue of a section."""
    physical: dict[str, Any] = {
        "artifactLocation": {"uri": artifact_uri(issue.rel), "uriBaseId": URI_BASE_ID}
    }
    if issue.line is not None:
        physical["region"] = {"startLine": issue.line}
    result: dict[str, Any] = {
        "ruleId": section.rule_id(issue.kind),
        "level": level(issue.blocking),
        "message": {"text": issue.detail},
        "locations": [
            {
                "physicalLocation": physical,
                "logicalLocations": [{"name": logical_name(issue)}],
            }
        ],
    }
    if issue.discriminator:
        result["partialFingerprints"] = {DISCRIMINATOR_KEY: issue.discriminator}
    return result


def invocation(stopped: str | None) -> dict[str, Any]:
    """Return the invocation of a run, failed with the reason ``stopped`` when it is given."""
    if stopped is None:
        return {"executionSuccessful": True}
    return {
        "executionSuccessful": False,
        "toolExecutionNotifications": [{"level": "error", "message": {"text": stopped}}],
    }


def sarif_log(
    sections: Sequence[Section],
    version: str,
    stopped: str | None = None,
    began: bool = True,
) -> dict[str, Any]:
    """Return the log of one run of anagraphe of ``version``, with one result per issue.

    ``sections`` lists every section that the command can check, so that the driver declares all
    their rules, including the sections that the run did not reach. ``stopped`` states why the run
    is incomplete, and is ``None`` for a complete run. ``began`` is false when the analysis never
    began, and the run then omits ``results``.

    Raises
    ------
    ValueError
        When an issue holds a kind that the catalogue of its section does not list, since its rule
        would then be absent from the driver, or when a run that never began states no reason.
    """
    if not began and stopped is None:
        raise ValueError("a run whose analysis never began must state why it stopped")
    rules = [
        {
            "id": section.rule_id(kind.kind),
            "shortDescription": {"text": kind.description},
            "defaultConfiguration": {"level": level(kind.blocking)},
        }
        for section in sections
        for kind in section.kinds
    ]
    for section in sections:
        listed = {kind.kind for kind in section.kinds}
        unlisted = sorted({issue.kind for issue in section.issues} - listed)
        if unlisted:
            raise ValueError(
                f"the section {section.name} lists no kind {', '.join(unlisted)} in its catalogue"
            )
    run: dict[str, Any] = {
        "tool": {
            "driver": {
                "name": TOOL_NAME,
                "version": version,
                "isComprehensive": True,
                "rules": rules,
            }
        },
        "invocations": [invocation(stopped)],
        "columnKind": "unicodeCodePoints",
    }
    if began:
        run["results"] = [
            _result(section, issue) for section in sections for issue in section.issues
        ]
    return {"version": SARIF_VERSION, "$schema": SARIF_SCHEMA, "runs": [run]}
