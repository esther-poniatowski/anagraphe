"""
The logical targets of a repository: the addresses by which a record refers to a record of another
tool, or to a unit inside it, possibly in another repository.

A target is the mapping ``{repository, id, unit}``, published as the definition ``target`` of the
resource ``addressing.v1``. A repository derives its identifier from the override of the section
``repository`` of ``anagraphe.yml``, its remote or its folder, a record type declares the field of
its identifier by ``x-identifier``, and a consumer types a target field by ``x-target-contract``.
A field path names one node of a document, and converts to and from a JSON Pointer.

The subpackage is private: the interface of the distribution is the top-level module
:mod:`anagraphe_read`.
"""
