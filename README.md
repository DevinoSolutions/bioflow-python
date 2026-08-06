# bioflow-sdk

The official Python SDK for the [BioFlow](https://getbioflow.com) public API — link-in-bio
pages, captured contacts, files, analytics and Standard-Webhooks endpoints, with typed errors,
cursor pagination, idempotent writes and a retry policy that mirrors the server's own rules.

Sync and async clients, `httpx` as the only runtime dependency, full type hints (`py.typed`).

```bash
pip install bioflow-sdk
```

> **The distribution name and the import name differ.** Install `bioflow-sdk`, then
> `import bioflow_py`:
>
> ```python
> # pip install bioflow-sdk
> from bioflow_py import BioFlow
> ```
>
> The PyPI project is **`bioflow-sdk`**; the importable Python package stays **`bioflow_py`**
> throughout this README and in every code sample below.

Requires Python 3.10+. The API reference lives at
<https://getbioflow.com/docs/api/reference>; a TypeScript SDK with the same surface is
available as [`@getbioflow/sdk`](https://github.com/DevinoSolutions/bioflow-sdk).

## Authentication

Create an API key in **BioFlow → Settings → Developers**. Keys look like
`bf_live_…` (full access) or `bf_test_…` (**read-only** — every write returns
`403 test_key_read_only`, which makes them safe to put in CI).

```python
from bioflow_py import BioFlow

# Explicit
client = BioFlow(api_key="bf_live_…")

# Or from the BIOFLOW_API_KEY environment variable
client = BioFlow()

# The key can also travel in the x-api-key header instead of Authorization
client = BioFlow(api_key="bf_live_…", auth_style="x-api-key")
```

`bf_` keys are secrets: keep them server-side, never in a browser bundle or a mobile app.

## Quickstart

```python
from bioflow_py import BioFlow

with BioFlow(api_key="bf_live_…") as bioflow:
    page = bioflow.pages.create({"title": "Summer drop"})

    bioflow.pages.add_block(
        page["id"],
        {"type": "link", "data": {"label": "Pre-order", "url": "https://example.com/drop"}},
    )

    result = bioflow.pages.publish(page["id"])
    print(result["status"], result["url"])
```

Responses are plain dictionaries typed as `TypedDict`s, so `page["id"]` type-checks while a
field the server adds tomorrow still arrives intact.

## Async

Same surface, every call awaitable:

```python
import asyncio
from bioflow_py import AsyncBioFlow


async def main() -> None:
    async with AsyncBioFlow(api_key="bf_live_…") as bioflow:
        usage = await bioflow.usage.get()
        print(usage["meters"][0]["remaining"])

        pages = await bioflow.pages.list(limit=50)
        async for page in pages:
            print(page["slug"])


asyncio.run(main())
```

## Pagination

List endpoints return a `CursorPage`. Iterate it to walk the **whole** collection — following
pages are fetched lazily with the same query — or read `.data` for just the page in hand.

```python
with BioFlow(api_key="bf_live_…") as bioflow:
    # Every contact, transparently paged
    for contact in bioflow.contacts.list(limit=100):
        print(contact["email"])

    # One page at a time
    page = bioflow.pages.list(limit=25)
    print(page.data, page.has_more, page.next_cursor, page.request_id)
    if page.has_next_page():
        page = page.next_page()
```

Cursors are opaque and bound to the query that minted them: never move one between endpoints
(the server answers `400 invalid_request` with the field code `cursor_operation_mismatch`).

## Error handling

Every failure is an `application/problem+json` document (RFC 9457) raised as a typed
exception. Branch on `err.code` — the stable machine value — never on `title`/`detail`.

```python
from bioflow_py import (
    BioFlow,
    APIError,
    BadRequestError,
    AuthenticationError,
    PermissionDeniedError,
    NotFoundError,
    ConflictError,
    RateLimitError,
    QuotaExhaustedError,
)

try:
    bioflow.pages.publish("pg_123")
except QuotaExhaustedError as err:
    print("monthly quota gone; resets at", err.retry_after_ms)
except RateLimitError:
    ...  # burst limit — the SDK already retried this for you
except PermissionDeniedError as err:
    if err.code == "feature_not_enabled":
        print("this workspace is on Free — upgrade to Creator or Pro")
except APIError as err:
    print(err.status, err.code, err.detail, err.request_id)
```

| `code` | HTTP | Exception | What it means |
| --- | --- | --- | --- |
| `invalid_request` | 400 | `BadRequestError` | Malformed request; see `err.errors` for field pointers |
| `invalid_api_key` | 401 | `AuthenticationError` | Missing, revoked or unknown key |
| `insufficient_scope` | 403 | `PermissionDeniedError` | The key lacks the scope this operation needs |
| `feature_not_enabled` | 403 | `PermissionDeniedError` | The workspace plan does not include the public API |
| `test_key_read_only` | 403 | `PermissionDeniedError` | A `bf_test_` key attempted a write |
| `resource_not_found` | 404 | `NotFoundError` | No such resource in this workspace |
| `stale_snapshot` | 409 | `ConflictError` | `expected_updated_at` is out of date — re-read and retry |
| `idempotency_in_progress` | 409 | `ConflictError` | The same key is still executing |
| `idempotency_key_reused` | 422 | `UnprocessableEntityError` | Same key, different body or path |
| `endpoint_verification_failed` | 422 | `UnprocessableEntityError` | The webhook URL did not answer the test event with a 2xx |
| `endpoint_limit_reached` | 422 | `UnprocessableEntityError` | Too many webhook endpoints |
| `rate_limited` | 429 | `RateLimitError` | Burst limit; retried automatically |
| `quota_exhausted` | 429 | `QuotaExhaustedError` | Monthly quota consumed; never auto-retried |
| `internal_error` | 500 | `InternalServerError` | A BioFlow-side failure |

Codes this SDK build has never heard of fall back to the HTTP status family and keep
`err.code` verbatim, so a new server code never turns into a crash.

Every exception carries `err.request_id` (also on every successful response as
`X-Request-Id`) — quote it in support requests.

## Idempotency

Every consequential `POST` automatically carries an `Idempotency-Key` (`sdk_<uuid4>`), which
is what makes those calls safe to retry. Supply your own to make a retry across process
restarts safe too:

```python
bioflow.pages.create({"title": "Summer drop"}, idempotency_key="drop-2026-08")
```

A replayed (ledgered) response is flagged on the raw result:

```python
raw = bioflow.request(
    "POST", "/v1/pages", body={"title": "Summer drop"}, idempotency_key="drop-2026-08"
)
print(raw.idempotency_replayed)  # True the second time
```

Pass `auto_idempotency_keys=False` to the constructor to opt out entirely.

## Rate limits, retries and plan requirements

The public API is available on the **Creator** and **Pro** plans; Free workspaces get
`403 feature_not_enabled`. Burst limits are 60 requests/minute (Creator) and 120 (Pro);
the monthly workspace quota resets on the 1st, UTC. `GET /v1/usage` is free to call and never
consumes quota.

Limiter state is parsed off every response:

```python
raw = bioflow.request("GET", "/v1/usage")
print(raw.rate_limit.limit, raw.rate_limit.remaining, raw.rate_limit.reset_seconds)
```

Retry policy (defaults: `max_retries=2`, `timeout=30`, `max_retry_after=60`):

* `429 rate_limited` — retried for **any** method (the server refused it before executing).
* `429 quota_exhausted` — **never** retried; `Retry-After` points at the period boundary.
* `408`, `5xx`, connection errors and timeouts — retried for `GET`, and for `POST` carrying an
  `Idempotency-Key`. `PATCH` and `DELETE` are never auto-retried.
* `Retry-After` is honoured exactly (delay-seconds or HTTP-date); a wait longer than
  `max_retry_after` raises instead of sleeping.
* Otherwise exponential backoff, `min(500ms · 2^attempt, 8s)` with ±25 % jitter.

## Webhook verification

BioFlow signs deliveries with [Standard Webhooks](https://www.standardwebhooks.com/) v1.
Verify the **raw** body before parsing it — any re-serialization breaks the signature.
Verification needs no API key.

### Flask

```python
from flask import Flask, request
from bioflow_py import verify_webhook, WebhookVerificationError

app = Flask(__name__)


@app.post("/webhooks/bioflow")
def bioflow_webhook():
    try:
        event = verify_webhook(request.get_data(), request.headers, WEBHOOK_SECRET)
    except WebhookVerificationError:
        return "", 400

    if event["type"] == "contact.created":
        ...
    return "", 204
```

### FastAPI

```python
from fastapi import FastAPI, Request, Response
from bioflow_py import verify_webhook, WebhookVerificationError

app = FastAPI()


@app.post("/webhooks/bioflow")
async def bioflow_webhook(request: Request) -> Response:
    try:
        event = verify_webhook(await request.body(), request.headers, WEBHOOK_SECRET)
    except WebhookVerificationError:
        return Response(status_code=400)

    match event["type"]:
        case "contact.created":
            ...
        case "page.published":
            ...
        case _:
            ...  # new types ship without a major version — always keep a default
    return Response(status_code=204)
```

Known event types are `contact.created`, `page.published`, `sale.paid`, `sale.refunded` and
`endpoint.test` — treat that list as an **open set**. The `webhook-id` (`whmsg_…`) is stable
across retries: use it as your dedup key. During a secret rotation BioFlow signs with both the
old and new secret for 24 h and `verify_webhook` accepts either.

## Escape hatch

For endpoints newer than your installed SDK, `client.request()` runs the same auth, retry,
idempotency and error pipeline:

```python
raw = bioflow.request("GET", "/v1/some-new-endpoint", query={"limit": 5})
print(raw.data, raw.status, raw.request_id, raw.rate_limit)
```

`bioflow_py.OPERATIONS` is the registry of everything this build models — it is pinned 1:1
against the published OpenAPI document by a contract test, so it can never drift.

## Configuration reference

```python
BioFlow(
    api_key=None,  # falls back to $BIOFLOW_API_KEY
    base_url="https://app.getbioflow.com",
    timeout=30.0,
    max_retries=2,
    max_retry_after=60.0,
    auth_style="bearer",  # or "x-api-key"
    auto_idempotency_keys=True,
    default_headers=None,
    debug=False,  # True -> stderr, or pass a callable sink
    http_client=None,  # bring your own httpx.Client
)
```

Every resource method also accepts `timeout=`, `max_retries=`, `idempotency_key=`, `headers=`
and `extra_query=` for a single call. Debug output is secret-redacted: an API key or webhook
secret never reaches a log line.

## Links

* [API reference](https://getbioflow.com/docs/api/reference)
* [OpenAPI document](https://getbioflow.com/docs/api/openapi.json)
* [TypeScript SDK](https://github.com/DevinoSolutions/bioflow-sdk)
* [Issues](https://github.com/DevinoSolutions/bioflow-python/issues)

## License

MIT © Devino Solutions Inc.
