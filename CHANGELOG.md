# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- **Breaking:** the index of a collection specifies the membership, the order and the nesting of
  its groups (e.g. the group keys `where`, `members`, `sort`, `order`, `sequence`), as
  [ADR 0002](docs/adr/0002-collection-owned-order.md) decides.
- **Breaking:** the title, then the path, break the ties of every sort key, the key `date`
  included.
- The check command reports each source of order ignored by the mode of its group.
- The check command reports a retired key under every index, whether or not it holds the region
  of groups.
- A key of the members sorts its numbers by value, before its other values.

### Added

- The index key `external` and the member key `superseded_by`, each resolved to a file. A note
  declaring `superseded_by` must hold an archived status.
- The vocabulary sections `key_values`, `context_relations` and `archived_statuses`.
- The configuration key `migrations`, to tolerate the retired key `cites` in declared files.
- The issue kinds `invalid-link`, `duplicate-member`, `unknown-filter-key`, `undeclared-value`,
  `unranked-value`, `ignored-order`, `nest-cycle`, `invalid-external`, `unarchived-superseded`,
  `retired-key` and `migration-key`, each defined by the
  [index specification](docs/guide/index-specification.md).

### Removed

- **Breaking:** every construction retired by ADR 0002 (e.g. the member key `group`, the mode
  `construction`). Each leftover fails with a message naming its replacement.
- **Breaking:** the core no longer parses typed citations, so the checks of citations and of goals
  are removed.
- **Breaking:** the issue kinds `unknown-target`, `missing-evidence`, `mirror-citation`,
  `order-conflict`, `unknown-goal`, `off-goal`, `redundant-sequence` and `unknown-sequence-entry`
  are removed. A redundant or unknown entry of a sequence is now reported as `ignored-order` or
  `invalid-link`.
