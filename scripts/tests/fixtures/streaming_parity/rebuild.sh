#!/usr/bin/env bash
# rebuild.sh — Regenerate the ENH-2479 streaming-parity trace set.
#
# THIS IS THE FIRST rebuild.sh IN THE REPO (verified: Glob '**/rebuild.sh'
# returns zero results elsewhere). Document the contract here so future
# contributors have a reference precedent.
#
# WHEN TO RE-RUN:
#   1. Anthropic ships a new SDK version that changes how cache_read_input_tokens
#      or cache_creation_input_tokens are reported.
#   2. The upstream wire-protocol field names change (rename, deprecation).
#   3. A new model variant is added whose behavior drifts in create() vs stream().
#   4. The internal rename boundary at subprocess_utils.py:462-465 changes.
#
# WHAT IT DOES:
#   Regenerates BOTH:
#     - scripts/tests/fixtures/streaming_parity/<trace_id>/recorded.jsonl
#     - scripts/tests/fixtures/streaming_parity/<trace_id>/expected.jsonl
#     - scripts/little_loops/observability/fixtures/streaming_parity/<trace_id>/*
#       (FEAT-2478's wheel-side mirror; created on first run if absent)
#   from a fresh `claude -p` invocation routed through both messages.create()
#   and messages.stream().
#
# PRE-CONDITIONS:
#   - anthropic SDK installed (pip install 'anthropic>=0.40')
#   - ANTHROPIC_API_KEY set in env
#   - Network access to api.anthropic.com
#   - Python 3.11+ (matches scripts/pyproject.toml)
#
# USAGE:
#   ANTHROPIC_API_KEY=sk-ant-... ./rebuild.sh
#
# The script body itself is a contract stub for this first-of-its-kind helper;
# the real recording loop ships with FEAT-2478's wheel-side integration.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../" && pwd)"
PYTEST_FIXTURE_DIR="${REPO_ROOT}/scripts/tests/fixtures/streaming_parity"
WHEEL_FIXTURE_DIR="${REPO_ROOT}/scripts/little_loops/observability/fixtures/streaming_parity"

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "ERROR: ANTHROPIC_API_KEY must be set" >&2
  exit 1
fi

if ! python -c "import anthropic" 2>/dev/null; then
  echo "ERROR: anthropic SDK not installed; pip install 'anthropic>=0.40'" >&2
  exit 1
fi

echo "Recording fresh streaming-parity traces..."
echo "  pytest-side: ${PYTEST_FIXTURE_DIR}"
echo "  wheel-side:  ${WHEEL_FIXTURE_DIR}"

# Recording stub: real implementation lands with FEAT-2478.
# When the recording script lands, it MUST:
#   1. Invoke claude -p (or direct SDK) for each trace pattern (A/B/C).
#   2. Capture raw stream-json events to recorded.jsonl per trace.
#   3. Run the same prompts through messages.create() and messages.stream().
#   4. Write the per-turn {create, stream, phase, diff_pct} to expected.jsonl.
#   5. Mirror both files to the wheel-side directory.
#   6. Use INTERNAL field names (cache_read_tokens) in expected.jsonl
#      per the subprocess_utils.py:462-465 rename boundary.
echo "TODO: implement recording loop (lands with FEAT-2478)"
echo "See ENH-2479 issue: docs/observability/streaming-parity-traces.md"
exit 0
