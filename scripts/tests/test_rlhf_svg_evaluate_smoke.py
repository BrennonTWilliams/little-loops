"""Regression test for BUG-2756: rlhf-svg-evaluate smoke harness crash.

The `smoke_test` state in ``rlhf-svg-evaluate.yaml`` runs an inline Playwright
``node -e`` script that aggregates ``pageerror``/``console-error`` payloads
into an ``errors`` array and joins them into a ``SMOKE_FAIL: ...`` line. Before
the fix, a captured ``pageerror`` whose ``.message`` was not a string (e.g. a
minified Playwright/V8 internal ``ErrorEvent``) crashed the aggregation itself,
so the outer ``.catch`` emitted a raw, unreadable runtime message
(``n.split is not a function``) instead of a clean ``SMOKE_FAIL: <cause>``
line — masking a genuine smoke failure as a harness crash.

This test extracts the real inline script from the YAML (not a reimplementation)
and runs it under Node against a minimal in-process Playwright stub that fires
a non-string-message ``pageerror`` after navigation, asserting the harness
still exits 1 with a readable ``SMOKE_FAIL:`` line and never surfaces the raw
minified message.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

BUILTIN_LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"
LOOP_FILE = BUILTIN_LOOPS_DIR / "rlhf-svg-evaluate.yaml"

# Minimal Playwright stub: enough surface for the smoke_test inline script to
# run to completion. `page.evaluate` returns canned values in call order
# (bodyText length, svgCount, animeReady) so the harness proceeds past the
# blank-render / anime.js checks straight to frame capture. Immediately after
# `page.goto` resolves, the stub fires a `pageerror` whose `.message` getter
# throws — reproducing the "n.split is not a function"-shaped failure mode
# (a non-string, throw-on-access `.message`) without depending on real
# Playwright internals.
_FAKE_PLAYWRIGHT_MODULE = """
const evaluateResults = [11, 1, true];
let evaluateCall = 0;

function makePage(errorHandlers) {
  return {
    on(event, cb) {
      if (event === 'pageerror' || event === 'console') {
        errorHandlers.push([event, cb]);
      }
    },
    async goto() {
      for (const [event, cb] of errorHandlers) {
        if (event === 'pageerror') {
          cb({ get message() { throw new Error('n.split is not a function'); } });
        }
      }
    },
    async waitForTimeout() {},
    async evaluate() {
      const value = evaluateResults[evaluateCall] !== undefined
        ? evaluateResults[evaluateCall]
        : true;
      evaluateCall += 1;
      return value;
    },
    async screenshot() {},
  };
}

module.exports = {
  chromium: {
    async launch() {
      const errorHandlers = [];
      return {
        async newPage() {
          return makePage(errorHandlers);
        },
        async close() {},
      };
    },
  },
};
"""


def _extract_inline_node_script() -> str:
    """Pull the literal inline `node -e "..."` script out of smoke_test.action.

    Extracting the real script (rather than reimplementing its logic) ensures
    this test fails if the guarded coercion/try-catch behavior regresses.
    """
    assert LOOP_FILE.exists(), f"Loop file not found: {LOOP_FILE}"
    data = yaml.safe_load(LOOP_FILE.read_text())
    action = data["states"]["smoke_test"]["action"]
    match = re.search(r'node -e "(.*)"\s*2>&1', action, re.DOTALL)
    assert match, 'could not locate inline `node -e "..."` Playwright script in smoke_test.action'
    return match.group(1)


def test_smoke_harness_survives_non_string_pageerror_message(tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip(
            "node not installed; smoke harness regression gate runs wherever Node is available"
        )

    script = _extract_inline_node_script()

    # Fake output.html — never actually loaded (goto is stubbed), but the
    # harness's earlier bash guard would otherwise short-circuit before
    # reaching node if this file check were exercised (it isn't, here).
    fake_run_dir = tmp_path / "run"
    fake_run_dir.mkdir()
    (fake_run_dir / "output.html").write_text("<html></html>")

    node_modules = tmp_path / "node_modules" / "playwright"
    node_modules.mkdir(parents=True)
    (node_modules / "index.js").write_text(_FAKE_PLAYWRIGHT_MODULE)
    (node_modules / "package.json").write_text('{"name": "playwright", "main": "index.js"}')

    proc = subprocess.run(
        [node, "-e", script],
        env={"ABS_DIR": str(fake_run_dir), "NODE_PATH": str(tmp_path / "node_modules")},
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert proc.returncode == 1, (
        f"expected exit code 1 on smoke failure, got {proc.returncode}. "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    smoke_fail_lines = [line for line in proc.stdout.splitlines() if line.startswith("SMOKE_FAIL:")]
    assert smoke_fail_lines, f"expected a SMOKE_FAIL line in stdout, got: {proc.stdout!r}"
    assert "n.split is not a function" not in proc.stdout, (
        "raw minified runtime message leaked into harness output — "
        f"aggregation guard regressed: {proc.stdout!r}"
    )
