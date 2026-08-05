"""Official Python SDK for the BioFlow public API.

```python
from bioflow_py import BioFlow

with BioFlow(api_key="bf_live_…") as bioflow:
    usage = bioflow.usage.get()
    print(usage["meter"]["remaining"])
```

API reference: <https://getbioflow.com/docs/api/reference>
"""

from __future__ import annotations

__version__ = "0.1.0"

from ._http import (
    API_KEY_ENV_VAR,
    DEFAULT_BASE_URL,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MAX_RETRY_AFTER,
    DEFAULT_TIMEOUT,
    USER_AGENT,
    AuthStyle,
    RateLimitInfo,
    RawResult,
)
from .async_client import AsyncBioFlow
from .client import BioFlow
from .errors import (
    PROBLEM_CODE_ERROR_CLASSES,
    APIConnectionError,
    APIError,
    APITimeoutError,
    APIUserAbortError,
    AuthenticationError,
    BadRequestError,
    BioFlowError,
    ConflictError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    ProblemDocument,
    ProblemFieldError,
    QuotaExhaustedError,
    RateLimitError,
    UnprocessableEntityError,
    WebhookVerificationError,
    api_error_from_response,
    parse_retry_after_ms,
)
from .operations import OPERATIONS, HttpMethod, Operation
from .pagination import AsyncCursorPage, CursorPage
from .webhooks import (
    KNOWN_EVENT_TYPES,
    WEBHOOK_ID_HEADER,
    WEBHOOK_SIGNATURE_HEADER,
    WEBHOOK_TIMESTAMP_HEADER,
    WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS,
    WebhookEvent,
    Webhooks,
    verify_webhook,
)

__all__ = [
    "API_KEY_ENV_VAR",
    "DEFAULT_BASE_URL",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_MAX_RETRY_AFTER",
    "DEFAULT_TIMEOUT",
    "KNOWN_EVENT_TYPES",
    "OPERATIONS",
    "PROBLEM_CODE_ERROR_CLASSES",
    "USER_AGENT",
    "WEBHOOK_ID_HEADER",
    "WEBHOOK_SIGNATURE_HEADER",
    "WEBHOOK_TIMESTAMP_HEADER",
    "WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS",
    "APIConnectionError",
    "APIError",
    "APITimeoutError",
    "APIUserAbortError",
    "AsyncBioFlow",
    "AsyncCursorPage",
    "AuthStyle",
    "AuthenticationError",
    "BadRequestError",
    "BioFlow",
    "BioFlowError",
    "ConflictError",
    "CursorPage",
    "HttpMethod",
    "InternalServerError",
    "NotFoundError",
    "Operation",
    "PermissionDeniedError",
    "ProblemDocument",
    "ProblemFieldError",
    "QuotaExhaustedError",
    "RateLimitError",
    "RateLimitInfo",
    "RawResult",
    "UnprocessableEntityError",
    "WebhookEvent",
    "WebhookVerificationError",
    "Webhooks",
    "__version__",
    "api_error_from_response",
    "parse_retry_after_ms",
    "verify_webhook",
]
