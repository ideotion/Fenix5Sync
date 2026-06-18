"""Content-based deduplication helpers.

Files are identified by the SHA-256 of their *contents*, not their filename, so
the same activity copied under a different name is still recognised as a
duplicate. The persistent ledger lives in the SQLite store (see
:mod:`core.store`); this module just provides hashing.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK = 1 << 20  # 1 MiB


def sha256_file(path: str | Path) -> str:
    """Return the hex SHA-256 digest of a file's contents (streamed)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    """Return the hex SHA-256 digest of a bytes object."""
    return hashlib.sha256(data).hexdigest()
