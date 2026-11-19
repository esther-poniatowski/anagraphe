"""
The record registry of a repository, read: the committed map from the identifiers of its records to
their files, and the permanent list of its retired identifiers, under ADR 0007.

A resolver of another repository reads the registry of a selected state instead of walking that
state. The section ``records`` of ``anagraphe.yml`` names its file. The command line of Anagraphe
writes the registry.

The subpackage is private: the interface of the distribution is the top-level module
:mod:`anagraphe_read`.
"""
