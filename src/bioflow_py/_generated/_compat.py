"""Typing shim so the generated models need no runtime dependency beyond httpx.

``typing.NotRequired`` only exists from Python 3.11. The generated module carries
``from __future__ import annotations``, so ``NotRequired`` is never evaluated at
runtime — but the import statement still has to resolve. On 3.10 we borrow it
from ``typing_extensions`` when it happens to be installed and fall back to a
subscriptable placeholder otherwise.

Type checkers always see the real special form.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from typing_extensions import NotRequired as NotRequired
elif sys.version_info >= (3, 11):
    from typing import NotRequired
else:  # pragma: no cover - exercised only on Python 3.10
    try:
        from typing_extensions import NotRequired
    except ImportError:

        class _NotRequiredPlaceholder:
            """Stand-in that makes ``NotRequired[X]`` importable and subscriptable."""

            def __getitem__(self, item: Any) -> Any:
                return item

        NotRequired = _NotRequiredPlaceholder()

__all__ = ["NotRequired"]
