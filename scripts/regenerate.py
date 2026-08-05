#!/usr/bin/env python
"""Regenerate ``src/bioflow_py/_generated/models.py`` from the vendored OpenAPI spec.

The wire types are machine-generated (28 named schemas, several deeply nested) so
they cannot drift from ``openapi/v1.json``; everything else in the SDK is
hand-written. This mirrors what the TypeScript SDK does with ``openapi-typescript``.

Usage::

    python scripts/regenerate.py            # regenerate models in place
    python scripts/regenerate.py --check    # fail if regeneration would change anything
    python scripts/regenerate.py --fetch    # refresh openapi/v1.json from the live spec first
    python scripts/regenerate.py --check-spec  # fail if the vendored spec differs from live

``--check`` is the CI drift gate.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = REPO_ROOT / "openapi" / "v1.json"
OUTPUT_PATH = REPO_ROOT / "src" / "bioflow_py" / "_generated" / "models.py"
LIVE_SPEC_URL = "https://getbioflow.com/docs/api/openapi.json"
SPEC_FETCH_USER_AGENT = "bioflow-py-spec-drift (+https://github.com/DevinoSolutions/bioflow-python)"

HEADER = '''"""Wire types generated from ``openapi/v1.json`` — NEVER hand-edit.

Regenerate with ``python scripts/regenerate.py``; CI fails if this file and the
spec disagree. Import these through :mod:`bioflow_py.models`, which re-exports
them under their public names (``File`` is exposed as ``FileObject``).

Forward compatibility: server-sent string unions (statuses, event types, ...) are
OPEN sets — new values may appear without a major version, so these are typing
aids only. The SDK performs no runtime narrowing of responses.
"""

'''


def _generate_to(target: Path) -> None:
    """Run datamodel-code-generator, writing the models module to ``target``."""
    command = [
        sys.executable,
        "-m",
        "datamodel_code_generator",
        "--input",
        str(SPEC_PATH),
        "--input-file-type",
        "openapi",
        "--output-model-type",
        "typing.TypedDict",
        "--target-python-version",
        "3.10",
        "--output",
        str(target),
        "--disable-timestamp",
        "--use-standard-collections",
        "--use-union-operator",
        "--use-schema-description",
        "--use-double-quotes",
        # PEP 728 closed=True would make every response type reject unknown keys,
        # which is exactly the forward compatibility the API promises to break.
        "--no-use-closed-typed-dict",
        # NotRequired lives in typing only from 3.11; route it through our own
        # shim so the wheel keeps httpx as its ONLY runtime dependency.
        "--import-overrides",
        '{"NotRequired": "bioflow_py._generated._compat"}',
        # `builtin` is dependency-free and therefore byte-stable across machines,
        # which is what makes `--check` a trustworthy CI gate.
        "--formatters",
        "builtin",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise SystemExit(f"datamodel-code-generator failed with exit code {result.returncode}")
    body = target.read_text(encoding="utf-8")
    target.write_text(HEADER + body, encoding="utf-8")


def _download_spec() -> dict[str, object]:
    """Fetch the published OpenAPI document.

    The landing host rejects the default ``Python-urllib`` User-Agent with a 403,
    so identify this tool explicitly.
    """
    request = urllib.request.Request(LIVE_SPEC_URL, headers={"User-Agent": SPEC_FETCH_USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def _fetch_spec() -> None:
    payload = _download_spec()
    SPEC_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"fetched {LIVE_SPEC_URL} -> {SPEC_PATH.relative_to(REPO_ROOT)}")


def _check_spec() -> int:
    live = _download_spec()
    vendored = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    if live == vendored:
        print("spec check: vendored openapi/v1.json matches the live document")
        return 0
    print(
        "spec check: vendored openapi/v1.json DIFFERS from "
        f"{LIVE_SPEC_URL} — run `python scripts/regenerate.py --fetch` and regenerate.",
        file=sys.stderr,
    )
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if regenerating would change the committed models module",
    )
    parser.add_argument(
        "--fetch",
        action="store_true",
        help=f"refresh openapi/v1.json from {LIVE_SPEC_URL} before generating",
    )
    parser.add_argument(
        "--check-spec",
        action="store_true",
        help="compare the vendored spec against the live document and exit",
    )
    args = parser.parse_args()

    if args.check_spec:
        return _check_spec()
    if args.fetch:
        _fetch_spec()

    if args.check:
        with tempfile.TemporaryDirectory() as tmp:
            candidate = Path(tmp) / "models.py"
            _generate_to(candidate)
            fresh = candidate.read_text(encoding="utf-8")
        current = OUTPUT_PATH.read_text(encoding="utf-8") if OUTPUT_PATH.exists() else ""
        if fresh == current:
            print("models check: _generated/models.py is up to date with openapi/v1.json")
            return 0
        print(
            "models check: _generated/models.py is STALE — run `python scripts/regenerate.py`.",
            file=sys.stderr,
        )
        return 1

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _generate_to(OUTPUT_PATH)
    print(f"wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
