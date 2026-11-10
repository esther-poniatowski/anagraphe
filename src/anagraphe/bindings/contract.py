"""
The contract of the bindings, which a tool reading them pins to one version.

The contract covers the resolution along the directory chain, the values of a declaration, the
marks ``x-binds`` of a record schema, and the JSON written by
``anagraphe bindings show --format json``. The specification
``docs/specification/bindings-contract.md`` states it, and the conformance cases of
``specs/conformance/bindings.yml`` fix its readings.
"""

#: The identifier of the contract, versioned apart from the command line.
CONTRACT = "anagraphe:bindings@1"
