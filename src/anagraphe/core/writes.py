"""
The atomic writes of the command line: every changed file is replaced, or none is.

The indexes, the moves, the record registry and the migration of the records write through this
module, so a failed write is recovered alike in each.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Mapping


def write_atomically(root: Path, changes: Mapping[str, str]) -> None:
    """Replace every changed file, and restore the originals if one replacement fails.

    A file that does not exist yet is created, and removed again if a later replacement fails.
    Its folder must exist.
    """
    prepared: dict[Path, Path] = {}
    backups: dict[Path, Path] = {}
    replaced: list[Path] = []
    try:
        for relative, text in changes.items():
            target = root / relative
            handle, temporary = tempfile.mkstemp(
                prefix=f".{target.name}.",
                suffix=".tmp",
                dir=target.parent,
            )
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            prepared[target] = Path(temporary)
            if target.exists():
                backup = Path(temporary).with_suffix(".bak")
                shutil.copy2(target, backup)
                backups[target] = backup
            else:
                # mkstemp creates its file readable by its owner alone; a new file takes the mode
                # that the umask grants to any file created by the process.
                os.chmod(temporary, 0o666 & ~_umask())
        for target, prepared_path in prepared.items():
            os.replace(prepared_path, target)
            replaced.append(target)
    except OSError:
        for target in reversed(replaced):
            if target in backups:
                os.replace(backups[target], target)
            else:
                target.unlink(missing_ok=True)
        raise
    finally:
        for path in (*prepared.values(), *backups.values()):
            path.unlink(missing_ok=True)


def _umask() -> int:
    """Return the umask of the process, which the operating system reads only by setting it."""
    current = os.umask(0o022)
    os.umask(current)
    return current
