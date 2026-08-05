"""Secrets never reach a log line or an exception message."""

from __future__ import annotations

import httpx
import pytest
import respx

from bioflow_py import APIConnectionError
from bioflow_py._redact import redact_secrets
from conftest import TEST_BASE_URL, make_client

LIVE_KEY = "bf_live_" + "A" * 43 + "_0badc0de"
TEST_KEY = "bf_test_" + "B" * 43 + "_0badc0de"
WEBHOOK_SECRET = "whsec_c2VjcmV0LXZhbHVlLWhlcmU="


@pytest.mark.parametrize("secret", [LIVE_KEY, TEST_KEY, WEBHOOK_SECRET])
def test_every_secret_shape_is_redacted(secret: str) -> None:
    redacted = redact_secrets(f"before {secret} after")
    assert secret not in redacted
    assert "[redacted]" in redacted
    assert redacted.startswith("before ") and redacted.endswith(" after")


def test_redaction_leaves_ordinary_text_alone() -> None:
    assert redact_secrets("GET /v1/pages -> 200") == "GET /v1/pages -> 200"


@respx.mock
def test_debug_output_never_contains_the_api_key() -> None:
    respx.mock.get(f"{TEST_BASE_URL}/v1/usage").mock(return_value=httpx.Response(200, json={}))
    lines: list[str] = []
    with make_client(api_key=LIVE_KEY, debug=lines.append) as client:
        client.usage.get()
    assert lines, "debug sink received nothing"
    joined = "\n".join(lines)
    assert LIVE_KEY not in joined
    assert "[bioflow-py]" in joined


@respx.mock
def test_debug_true_writes_redacted_lines_to_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    respx.mock.get(f"{TEST_BASE_URL}/v1/usage").mock(return_value=httpx.Response(200, json={}))
    with make_client(api_key=LIVE_KEY, debug=True) as client:
        client.usage.get()
    captured = capsys.readouterr()
    assert "[bioflow-py]" in captured.err
    assert LIVE_KEY not in captured.err


@respx.mock
def test_debug_off_stays_silent(capsys: pytest.CaptureFixture[str]) -> None:
    respx.mock.get(f"{TEST_BASE_URL}/v1/usage").mock(return_value=httpx.Response(200, json={}))
    with make_client(api_key=LIVE_KEY) as client:
        client.usage.get()
    assert capsys.readouterr().err == ""


@respx.mock
def test_a_connection_error_message_never_leaks_the_key() -> None:
    respx.mock.get(f"{TEST_BASE_URL}/v1/usage").mock(
        side_effect=httpx.ConnectError(f"failed while sending {LIVE_KEY}")
    )
    with (
        make_client(api_key=LIVE_KEY, max_retries=0) as client,
        pytest.raises(APIConnectionError) as excinfo,
    ):
        client.usage.get()
    assert LIVE_KEY not in str(excinfo.value)
    assert "[redacted]" in str(excinfo.value)


@respx.mock
def test_an_api_error_message_never_echoes_a_secret_from_the_problem_detail() -> None:
    """Even if the server ever echoed a key back, the SDK must not widen the leak."""
    respx.mock.get(f"{TEST_BASE_URL}/v1/usage").mock(return_value=httpx.Response(200, json={}))
    with make_client(debug=True) as client:
        client.usage.get()
