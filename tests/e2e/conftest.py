"""Fixtures for the production smoke suite.

These tests talk to the REAL API at https://app.getbioflow.com. Without a key they
SKIP LOUDLY rather than passing silently — a skipped e2e is not a green e2e. The
skip gates themselves live next to the tests in ``test_prod_smoke.py``.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from bioflow_py import BioFlow


@pytest.fixture(scope="session")
def prod_client() -> Iterator[BioFlow]:
    """A client on the read-only ``bf_test_`` key, pointed at production."""
    with BioFlow(api_key=os.environ.get("BIOFLOW_TEST_API_KEY")) as client:
        yield client


@pytest.fixture(scope="session")
def prod_write_client() -> Iterator[BioFlow]:
    """A client on the ``bf_live_`` key, pointed at production. Write leg only."""
    with BioFlow(api_key=os.environ.get("BIOFLOW_API_KEY")) as client:
        yield client
