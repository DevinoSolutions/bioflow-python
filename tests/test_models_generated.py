"""The generated wire types stay in lockstep with the vendored spec."""

from __future__ import annotations

import subprocess
import sys

import pytest

from bioflow_py import models
from conftest import REPO_ROOT, load_spec

SCHEMA_NAMES = sorted(load_spec()["components"]["schemas"])


def test_the_spec_still_declares_twenty_eight_named_schemas() -> None:
    assert len(SCHEMA_NAMES) == 28


@pytest.mark.parametrize("schema_name", SCHEMA_NAMES)
def test_every_named_schema_is_exported_from_the_models_facade(schema_name: str) -> None:
    assert hasattr(models, schema_name), f"{schema_name} missing from bioflow_py.models"
    assert schema_name in models.__all__


def test_file_is_also_exported_under_its_non_shadowing_alias() -> None:
    assert models.FileObject is models.File


def test_regenerating_the_models_is_a_no_op() -> None:
    """CI drift gate: `scripts/regenerate.py --check` must stay green."""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "regenerate.py"), "--check"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_response_payloads_are_plain_dicts_so_unknown_fields_survive() -> None:
    """TypedDicts carry no runtime validation — a new server field must not break."""
    payload: models.Contact = {
        "id": "ct_1",
        "email": "a@b.co",
        "name": None,
        "source": "form",
        "source_block_id": None,
        "created_at": "2026-08-05T00:00:00Z",
        "a_field_shipped_after_this_sdk": True,  # type: ignore[typeddict-unknown-key]
    }
    assert payload["id"] == "ct_1"
