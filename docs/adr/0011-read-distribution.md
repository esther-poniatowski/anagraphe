# ADR 0011: Read distribution

**Status**: Accepted by the researcher on 2026-11-19. The record implements role 3 of the
[decision of Geonexus on tool roles][tool-roles], and answers the finding "Interface of Anagraphe"
of the [audit of public interfaces][audit].

---

## Problem Statement

Role 3 of the decision on tool roles states: "Anagraphe publishes the addressing specification with
versioned conformance cases, a Python read package and a TypeScript read package, versioned apart
from its command line." The TypeScript read package `@anagraphe/read` exists. The Python read side
existed only as internal modules of the package `anagraphe`, whose `__init__` exported its version
alone.

The audit of public interfaces measured three facts:

- the sources of Onomasia import twelve internal modules of Anagraphe, in `imports.py`,
  `texts/bindings.py`, `records/validation.py`, `service.py`, and six further modules importing
  `anagraphe.targets.model.Target`;
- Onomasia assembles the read side itself, in `imports.py`, lines 234 to 272. Its code locates
  `anagraphe.yml` through `CONFIG_LOCATIONS`, loads it and reads the manifest of the repository.
  Next, the code builds the resolution context, the schema reader, the declarations and the default
  binding key. The command line of Anagraphe builds the same four objects in its own code;
- the distribution `anagraphe` requires typer and Merismos, and typer installs rich. A tool that
  only reads therefore installs every dependency of the command line.

**Questions to be addressed**:

1. Which form does the Python read side take?
2. How is it versioned, and how does a consumer pin it?
3. Which function builds the objects of the read side?

---

## Decision Drivers

- **Versioning apart**: the version of the read side changes only when its interface or its
  behaviour changes, and a release of the command line leaves it unchanged. Pip resolves the
  requirement of a consumer against that version.
- **Dependency footprint**: a reader installs the dependencies of the read side alone, without
  typer, rich or Merismos.
- **Enforceable boundary**: a check fails when a module of the read side imports a module of the
  command line.
- **One wiring**: the composition of the configuration, the identity, the context, the declarations
  and the binding key exists once, and the command line uses it.
- **Release cost**: one repository and one release workflow serve both sides.

---

## Considered Options

1. **Separate distribution**: a distribution `anagraphe-read` in `packages/read-python`, with its
   own `pyproject.toml`, its own version and the import package `anagraphe_read`.
   - The interface is the `__all__` of `anagraphe_read`, and every module below it is private.
   - The distribution `anagraphe` depends on `anagraphe-read` by name and exact version.
   - The release builds and attaches the wheels of both distributions.

   ```python
   from anagraphe_read import Target, open_repository

   repository = open_repository(root)
   resolution = repository.resolve(Target.parse(value))
   ```

2. **One module with an interface version**: a module `anagraphe.read` inside the distribution
   `anagraphe`.
   - The interface is the `__all__` of that module, and a constant `INTERFACE_VERSION` names its
     version.
   - A reader depends on the distribution `anagraphe`, pinned by a commit.

   ```python
   from anagraphe.read import INTERFACE_VERSION, Target, open_repository

   repository = open_repository(root)
   resolution = repository.resolve(Target.parse(value))
   ```

---

## Analysis of Options

### Individual Assessment

1. **Separate distribution**
   - Pros:
     - Versioning apart: the version of the distribution is a version that pip resolves, and the
       release of the command line stamps another one.
     - Dependency footprint: the distribution requires PyYAML, jsonschema, referencing, pathspec and
       Kleisis alone.
     - Enforceable boundary: a CI job installs the read distribution without the command line and
       runs its suite, so an import of `anagraphe` fails there.
     - Additional advantage: the Python read side has the form of the TypeScript read package.
   - Cons:
     - Release cost: the release builds two distributions, and the conda channel needs a second
       recipe.
     - Additional disadvantage: the command line imports private modules of the read distribution,
       so both distributions must be installed from the same commit. A pip reference to a
       subdirectory of the same repository cannot name its own future commit, so the command line
       requires `anagraphe-read` by name, and a consumer of the command line names both
       distributions.
2. **One module with an interface version**
   - Pros:
     - Release cost: one distribution, one wheel, one pin.
   - Cons:
     - Versioning apart: pip resolves no requirement against a constant of a module, so a consumer
       pins a commit of the whole command line.
     - Dependency footprint: a reader installs typer, rich and Merismos.
     - Enforceable boundary: only the discipline of the imports keeps the module from reaching the
       command line, since both ship in one distribution.

### Summary: Comparison by Criteria

| Driver | Separate distribution | One module with an interface version |
| --- | --- | --- |
| Versioning apart | high (a distribution version) | low (a constant pip ignores) |
| Dependency footprint | high (five dependencies) | low (every dependency of the command line) |
| Enforceable boundary | high (installed alone in CI) | medium (import scans) |
| One wiring | high (one composition) | high (one composition) |
| Release cost | medium (two distributions) | high (one distribution) |

---

## Conclusions

### Decision

**Chosen option**: Separate distribution.

**Justification**: Role 3 requires a read package versioned apart from the command line. Only a
distribution of its own carries a version that pip resolves, and installs without the dependencies
of the command line.

**Discarded options**:

- **One module with an interface version**: its version binds no installation, and every reader
  installs the command line.

### Final Answers

1. Which form does the Python read side take?
   The distribution `anagraphe-read`, whose import package `anagraphe_read` is a top-level package.
   The `__all__` of `anagraphe_read` is the whole interface, and every subpackage below it opens on
   an underscore. When a module read and wrote files, its readers stay in the read distribution,
   and its writers move to the command line.
2. How is it versioned, and how does a consumer pin it?
   The version starts at `0.1.0` and is raised by hand when the interface or the behaviour changes.
   A consumer pins
   `anagraphe-read @ git+https://github.com/esther-poniatowski/anagraphe.git@<commit>#subdirectory=packages/read-python`,
   and each release attaches the wheel. The distribution `anagraphe` requires
   `anagraphe-read==<version>`; the development environment installs the read distribution of the
   clone in editable mode, and a consumer of the command line pins both distributions at one
   commit.
3. Which function builds the objects of the read side?
   The function `anagraphe_read._repository.compose`. The entry point `open_repository` and the
   configuration of the command line both build their objects through it, and the check of the
   targets and the record registry receive the composition that it returns.

---

## Implications

- **Modules**: the read side moves to `anagraphe_read`, and three mixed modules are split, as the
  [architecture](../internals/architecture.md) lists them. The [changelog](https://github.com/esther-poniatowski/anagraphe/blob/main/CHANGELOG.md)
  maps the former module paths.
- **Consumers**: Onomasia and the scripts of the vault move onto the names of `anagraphe_read` in a
  later step. The vault imports `load_yaml`, `Exemptions` and `exemptions` to read its exclusions,
  and the interface holds none of them yet; that step adds them or replaces their use.
- **Versions**: a change of the interface or the behaviour raises the version of
  `packages/read-python/pyproject.toml` and the pin of the root `pyproject.toml` in the same commit,
  and a test fails while they differ.
- **Configuration**: `open_repository` keeps the current places of `anagraphe.yml`. Their move to
  the folders declared to Hodegos is a later, separate step.
- **Conda**: the recipe of `anagraphe` copies the requirement `anagraphe-read==<version>`. No conda
  package satisfies that requirement until the channel publishes the read distribution.

---

## See Also

### Related Decisions

- [ADR 0009](0009-record-resolver.md): Relates to. The record resolver of ADR 0009 is the core of
  the operations `resolve` and `read` of the interface.
- [ADR 0010](0010-state-provider.md): Relates to. The Git provider of ADR 0010 is the default
  provider of `open_repository`, and its fetch stays with the command line.

### References and Resources

- [Decision of Geonexus on tool roles][tool-roles]
- [Audit of public interfaces][audit]

[tool-roles]: https://github.com/esther-poniatowski/geonexus/blob/main/docs/_decisions/tool-roles.md
[audit]: https://github.com/esther-poniatowski/geonexus/blob/main/docs/_audits/tool-boundaries/public-interfaces.md
