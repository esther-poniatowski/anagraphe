"""
Entry point for the `anagraphe` package, invoked as a module.

Usage
-----
To launch the command-line interface, execute::

    python -m anagraphe


See Also
--------
anagraphe.cli: Module implementing the application's command-line interface.
"""

from .cli import app

app()
