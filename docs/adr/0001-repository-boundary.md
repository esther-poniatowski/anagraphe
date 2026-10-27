# 0001 — Repository boundary

**Status:** accepted

## Context

The first implementation lived inside one consuming repository. Its rendering logic was reusable,
but its command imported repository paths, task syntax, vocabulary loading, and build manifests.
Copying that command would make each consumer maintain a divergent renderer. Extending an existing
tool would instead add repository navigation to a product with another declared purpose.

## Decision

Anagraphe is an independent repository, Python package, and executable. Its core owns managed-block
parsing, metadata reading, member ordering, rendering, and index diagnostics. Each consumer owns
its vocabulary, index types, exclusions, task-state derivation, and sequence derivation.

The executable exposes the direct commands `anagraphe check` and `anagraphe write`. No umbrella
command or compatibility wrapper preserves the source repository's former script name.

## Consequences

Consumers can pin and release the index tool independently. Repository adapters remain small and
testable because they only translate local control files into the public configuration and callback
contracts. A mechanism shared with another tool moves into a library only after both tools require
the same stable contract.
