"""The operation registry mirrors ``openapi/v1.json`` 1:1.

This is what makes "22/22 parity" a machine-checked fact rather than a claim, and
it is the Python mirror of ``packages/sdk/src/sdk-contracts.test.ts``.
"""

from __future__ import annotations

import pytest

from bioflow_py import OPERATIONS
from conftest import spec_operations

SPEC_OPERATIONS = spec_operations()


def test_the_spec_still_describes_exactly_twenty_two_operations() -> None:
    assert len(SPEC_OPERATIONS) == 22


def test_registry_covers_every_spec_operation_and_nothing_else() -> None:
    assert sorted(OPERATIONS) == sorted(op["operation_id"] for op in SPEC_OPERATIONS)


@pytest.mark.parametrize("operation", SPEC_OPERATIONS, ids=lambda op: str(op["operation_id"]))
def test_registry_entry_matches_the_spec_method_path_and_idempotency(
    operation: dict[str, object],
) -> None:
    entry = OPERATIONS[str(operation["operation_id"])]
    assert entry.method == operation["method"]
    assert entry.path == operation["path"]
    assert entry.idempotent == operation["idempotent"]


def test_every_post_is_ledgered_and_nothing_else_is() -> None:
    """The server ledgers every consequential POST — that is what makes them retryable."""
    for operation_id, entry in OPERATIONS.items():
        assert entry.idempotent == (entry.method == "POST"), operation_id


def test_registry_is_read_only_so_callers_cannot_corrupt_the_contract() -> None:
    with pytest.raises(TypeError):
        OPERATIONS["listPages"] = OPERATIONS["getUsage"]  # type: ignore[index]
