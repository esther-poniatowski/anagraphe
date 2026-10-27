# Architecture

Anagraphe separates deterministic index semantics from repository policy.

| Layer | Responsibility |
| --- | --- |
| domain modules | parse records and blocks, order members, render entries, and report issues |
| application service | coordinates validated replacement and rollback after ordinary write failures |
| infrastructure adapters | read YAML, schemas, Git state, task mappings, and folder sequences |
| CLI | translates command inputs, diagnostics, summaries, and exit states |

The domain modules depend only on supplied values and narrow callbacks. In particular, the core
does not import a repository's task parser, paths, vocabulary loader, or sequence source. A
repository adapter may derive those values from its own control files before invoking the core.

Write mode validates the complete selection before changing a file. Each file replacement is
atomic. If an ordinary replacement raises an operating-system error, Anagraphe restores the files
replaced earlier in that run. This rollback does not cover process termination or machine failure.
