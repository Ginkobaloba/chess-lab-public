# Provenance: copied verbatim from Ginkobaloba/draughts-lab train/seeds.py at commit 0a5c5a0fe6cc3443565937a738509f5de9479b19
# (Paradigm-owned, MIT). Changes from the original: none.
"""Stable seeds. Python's ``hash()`` is salted per process, so never use it here."""

from __future__ import annotations

import hashlib


def derive_seed(*parts: object) -> int:
    """A 63-bit seed from the SHA-256 of the parts joined by ``|``."""
    text = "|".join(str(p) for p in parts)
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "little") >> 1
