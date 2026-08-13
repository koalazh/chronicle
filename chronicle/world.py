from __future__ import annotations

import hashlib


class WorldAccessError(PermissionError):
    """A caller is not authorized for the current V6 World wake."""


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
