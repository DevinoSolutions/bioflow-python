"""The version constant is the single source of truth for the package version."""

from __future__ import annotations

import re
from importlib import metadata

import bioflow_py


def test_version_is_a_semver_string() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", bioflow_py.__version__)


def test_version_matches_installed_distribution_metadata() -> None:
    assert metadata.version("bioflow-sdk") == bioflow_py.__version__
