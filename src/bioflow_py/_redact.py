"""Secret redaction for debug logging.

``bf_`` API keys and ``whsec_`` webhook secrets must never reach a log line,
whatever string they ride in on. Mirrors ``packages/sdk/src/core/redact.ts``.
"""

from __future__ import annotations

import re

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bbf_(?:live|test)_[A-Za-z0-9]+(?:_[A-Za-z0-9]+)?\b"),
    re.compile(r"\bwhsec_[A-Za-z0-9+/=]+"),
)

REDACTED = "[redacted]"


def redact_secrets(text: str) -> str:
    """Replace every API key / webhook secret in ``text`` with ``[redacted]``."""
    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(REDACTED, redacted)
    return redacted


__all__ = ["REDACTED", "redact_secrets"]
