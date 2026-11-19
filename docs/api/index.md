# API Reference

## Read Interface

The module `anagraphe_read` is the public interface of the read distribution `anagraphe-read`; its
`__all__` lists every public name.

```{eval-rst}
.. automodule:: anagraphe_read
   :members:
   :undoc-members:

.. autodata:: anagraphe_read.AMBIGUOUS_UNIT

.. autodata:: anagraphe_read.ESCAPING_TARGET_PATH

.. autodata:: anagraphe_read.IDENTITY_DISAGREEMENT

.. autodata:: anagraphe_read.INVALID_RECORD_REGISTRY

.. autodata:: anagraphe_read.INVALID_TARGET_REPOSITORY

.. autodata:: anagraphe_read.INVALID_TARGET_STATE

.. autodata:: anagraphe_read.LINKED_TARGET_PATH

.. autodata:: anagraphe_read.RENAMED_REPOSITORY

.. autodata:: anagraphe_read.RENAMED_TARGET

.. autodata:: anagraphe_read.RETIRED_REPOSITORY_MANIFEST

.. autodata:: anagraphe_read.RETIRED_TARGET

.. autodata:: anagraphe_read.STALE_TARGET_REGISTRY

.. autodata:: anagraphe_read.TARGET_CONTRACT_MISMATCH

.. autodata:: anagraphe_read.UNBOUND_TARGET

.. autodata:: anagraphe_read.UNKNOWN_RECORD

.. autodata:: anagraphe_read.UNKNOWN_REPOSITORY

.. autodata:: anagraphe_read.UNKNOWN_UNIT

.. autodata:: anagraphe_read.UNREADABLE_RECORD

.. autodata:: anagraphe_read.UNREADABLE_TARGET_STATE

.. autodata:: anagraphe_read.UNVERIFIED_TARGET

.. autodata:: anagraphe_read.ADDRESSING_ID

.. autodata:: anagraphe_read.IMPLEMENTED_SPECIFICATION

.. autodata:: anagraphe_read.__version__
```

## Command Line

The package `anagraphe` holds the command line. Its modules are internal to the distribution
`anagraphe`.

### Package Overview

```{eval-rst}
.. automodule:: anagraphe
   :members:
   :undoc-members:
```

### Composition

```{eval-rst}
.. automodule:: anagraphe.configuration
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: anagraphe.cli
   :members:
   :undoc-members:

.. automodule:: anagraphe.refactor
   :members:
   :undoc-members:

.. automodule:: anagraphe.states
   :members:
   :undoc-members:
```

### Core

```{eval-rst}
.. automodule:: anagraphe.core.structured
   :members:
   :undoc-members:

.. automodule:: anagraphe.core.writes
   :members:
   :undoc-members:

.. automodule:: anagraphe.core.sarif
   :members:
   :undoc-members:

.. automodule:: anagraphe.core.links
   :members:
   :undoc-members:

.. automodule:: anagraphe.core.regions
   :members:
   :undoc-members:

.. automodule:: anagraphe.core.paths
   :members:
   :undoc-members:
```

### Indexes

```{eval-rst}
.. automodule:: anagraphe.indexes.service
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: anagraphe.indexes.configuration
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: anagraphe.indexes.generator
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: anagraphe.indexes.relocation
   :members:
   :undoc-members:

.. automodule:: anagraphe.indexes.types
   :members:
   :undoc-members:

.. automodule:: anagraphe.indexes.value_sets
   :members:
   :undoc-members:

.. automodule:: anagraphe.indexes.slots
   :members:
   :undoc-members:

.. automodule:: anagraphe.indexes.membership
   :members:
   :undoc-members:

.. automodule:: anagraphe.indexes.order
   :members:
   :undoc-members:

.. automodule:: anagraphe.indexes.fields
   :members:
   :undoc-members:

.. automodule:: anagraphe.indexes.notes
   :members:
   :undoc-members:

.. automodule:: anagraphe.indexes.render
   :members:
   :undoc-members:

.. automodule:: anagraphe.indexes.blocks
   :members:
   :undoc-members:

.. automodule:: anagraphe.indexes.retired
   :members:
   :undoc-members:

.. automodule:: anagraphe.indexes.kinds
   :members:
   :undoc-members:
```

### References

```{eval-rst}
.. automodule:: anagraphe.references.service
   :members:
   :undoc-members:

.. automodule:: anagraphe.references.configuration
   :members:
   :undoc-members:

.. automodule:: anagraphe.references.model
   :members:
   :undoc-members:

.. automodule:: anagraphe.references.syntaxes
   :members:
   :undoc-members:

.. automodule:: anagraphe.references.conventions
   :members:
   :undoc-members:

.. automodule:: anagraphe.references.resolution
   :members:
   :undoc-members:

.. automodule:: anagraphe.references.rules
   :members:
   :undoc-members:

.. automodule:: anagraphe.references.rewrite
   :members:
   :undoc-members:
```

### Checks of the Bindings and the Targets

```{eval-rst}
.. automodule:: anagraphe.bindings.service
   :members:
   :undoc-members:

.. automodule:: anagraphe.targets.service
   :members:
   :undoc-members:

.. automodule:: anagraphe.targets.migration
   :members:
   :undoc-members:
```

### Record Registry

```{eval-rst}
.. automodule:: anagraphe.targets.registry.service
   :members:
   :undoc-members:

.. automodule:: anagraphe.targets.registry.rendering
   :members:
   :undoc-members:

.. automodule:: anagraphe.targets.registry.kinds
   :members:
   :undoc-members:
```

## Internals of the Read Distribution

The modules below are private to the distribution `anagraphe-read`. Their names and contents can
change without a change of its version; a consumer imports `anagraphe_read` alone. Their entries are
left out of the index, so that a reference to a public name resolves to the interface.

### Composition of the Read Side

```{eval-rst}
.. automodule:: anagraphe_read._repository
   :no-index:
   :members:
   :undoc-members:

.. automodule:: anagraphe_read._configuration
   :no-index:
   :members:
   :undoc-members:
   :show-inheritance:
```

### Core of the Read Side

```{eval-rst}
.. automodule:: anagraphe_read._core.configuration
   :no-index:
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: anagraphe_read._core.filters
   :no-index:
   :members:
   :undoc-members:

.. automodule:: anagraphe_read._core.conditions
   :no-index:
   :members:
   :undoc-members:

.. automodule:: anagraphe_read._core.exclusions
   :no-index:
   :members:
   :undoc-members:

.. automodule:: anagraphe_read._core.metadata
   :no-index:
   :members:
   :undoc-members:

.. automodule:: anagraphe_read._core.issues
   :no-index:
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: anagraphe_read._core.files
   :no-index:
   :members:
   :undoc-members:

.. automodule:: anagraphe_read._core.anchors
   :no-index:
   :members:
   :undoc-members:

.. automodule:: anagraphe_read._core.json_text
   :no-index:
   :members:
   :undoc-members:

.. automodule:: anagraphe_read._core.schemas
   :no-index:
   :members:
   :undoc-members:

.. automodule:: anagraphe_read._core.published
   :no-index:
   :members:
   :undoc-members:

.. automodule:: anagraphe_read._core.git_state
   :no-index:
   :members:
   :undoc-members:
```

### Bindings

```{eval-rst}
.. automodule:: anagraphe_read._bindings.configuration
   :no-index:
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: anagraphe_read._bindings.model
   :no-index:
   :members:
   :undoc-members:

.. automodule:: anagraphe_read._bindings.contract
   :no-index:
   :members:
   :undoc-members:

.. automodule:: anagraphe_read._bindings.resolution
   :no-index:
   :members:
   :undoc-members:

.. automodule:: anagraphe_read._bindings.schemas
   :no-index:
   :members:
   :undoc-members:

.. automodule:: anagraphe_read._bindings.kinds
   :no-index:
   :members:
   :undoc-members:
```

### Targets

```{eval-rst}
.. automodule:: anagraphe_read._targets.configuration
   :no-index:
   :members:
   :undoc-members:

.. automodule:: anagraphe_read._targets.model
   :no-index:
   :members:
   :undoc-members:

.. automodule:: anagraphe_read._targets.identity
   :no-index:
   :members:
   :undoc-members:

.. automodule:: anagraphe_read._targets.records
   :no-index:
   :members:
   :undoc-members:

.. automodule:: anagraphe_read._targets.declarations
   :no-index:
   :members:
   :undoc-members:

.. automodule:: anagraphe_read._targets.verification
   :no-index:
   :members:
   :undoc-members:

.. automodule:: anagraphe_read._targets.walk
   :no-index:
   :members:
   :undoc-members:

.. automodule:: anagraphe_read._targets.field_paths
   :no-index:
   :members:
   :undoc-members:

.. automodule:: anagraphe_read._targets.read_sides
   :no-index:
   :members:
   :undoc-members:

.. automodule:: anagraphe_read._targets.resource
   :no-index:
   :members:
   :undoc-members:

.. automodule:: anagraphe_read._targets.specification
   :no-index:
   :members:
   :undoc-members:

.. automodule:: anagraphe_read._targets.kinds
   :no-index:
   :members:
   :undoc-members:
```

### Records

```{eval-rst}
.. automodule:: anagraphe_read._targets.registry.configuration
   :no-index:
   :members:
   :undoc-members:

.. automodule:: anagraphe_read._targets.registry.contract
   :no-index:
   :members:
   :undoc-members:
```

### Resolution

```{eval-rst}
.. automodule:: anagraphe_read._resolution.resolver
   :no-index:
   :members:
   :undoc-members:

.. automodule:: anagraphe_read._resolution.context
   :no-index:
   :members:
   :undoc-members:

.. automodule:: anagraphe_read._resolution.provider
   :no-index:
   :members:
   :undoc-members:

.. automodule:: anagraphe_read._resolution.git
   :no-index:
   :members:
   :undoc-members:

.. automodule:: anagraphe_read._resolution.configuration
   :no-index:
   :members:
   :undoc-members:
```
