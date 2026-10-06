"""Behavioral test for FEAT-3589 html-webapp-generator `viewport_gate` shell action.

The viewport_gate state runs an inline Playwright probe at each configured
viewport size (default 1440x900, 1024x768, 375x667) and asserts:

  1. `document.documentElement.scrollHeight <= innerHeight` and
     `scrollWidth <= innerWidth` (page-level overflow; works under
     `body{overflow:hidden}` because scrollHeight counts clipped content).
  2. Bounding boxes of visible interactive elements (button, a, input,
     select, textarea, [role="button"]) not inside a scrollable ancestor
     lie within the viewport — excluding elements inside semantically
     hidden subtrees ([inert], [hidden], [aria-hidden="true"], visibility:
     hidden), so a closed off-canvas drawer hidden that way does not
     false-fail at 375x667 (prototype-validated, 2026-09-25).

These tests extract the real inline node script (heredoc-delivered) from
the loop YAML and run it under Node against:

  - a hand-crafted app-shell page that fits every viewport → VIEWPORT_PASS
  - a page that overflows at narrow widths → VIEWPORT_FAIL with the
    failing per-viewport measurements appended to critique.md
  - a page with a closed off-canvas drawer hidden semantically ([inert])
    → drawer contents do NOT count as interactive overflow (gate passes
    on geometry; the rubric criterion covers non-interactive content)
  - a malformed viewports string → zero-valid-viewports is a harness
    fault (exit 2)

This test fails if the gate's geometry check regresses.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml

from little_loops.fsm.interpolation import InterpolationContext, interpolate

from tests.helpers import require_node

BUILTIN_LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"
LOOP_FILE = BUILTIN_LOOPS_DIR / "html-webapp-generator.yaml"

# Minimal Playwright stub. The real script does:
#   const { chromium } = require('@playwright/test');
#   await chromium.launch() -> { newContext({ viewport }) { width, height } }
#     -> { newPage() -> { goto(), waitForTimeout(), close() } }
#   await page.evaluate(fn) -> returns the function's return value
# We supply a stub that:
#   - exposes width/height on the newContext's viewport
#   - exposes goto + waitForTimeout on page
#   - returns canned docOverflow + interactOverflow values from page.evaluate
#     based on the (width, height) viewport passed in (so we can assert
#     "fits at desktop, overflows at mobile" deterministically without
#     loading a real browser).
#
# For the page fixture, evaluate results are an array indexed by call:
#     [0] -> docOverflow object
#     [1] -> interactOverflow array
_FAKE_PLAYWRIGHT_TEMPLATE = """
const pageCalls = [];

function makePage(viewport) {
  return {
    async goto() {},
    async waitForTimeout() {},
    async close() {},
    async evaluate(fn) {
      const arg = pageCalls.length;
      pageCalls.push(arg);
      if (arg === 0) {
        // docOverflow probe
        const results = __DOC_OVERFLOW__;
        return results[String(viewport.width) + '|' + String(viewport.height)];
      }
      // interactOverflow probe
      const results = __INTERACT_OVERFLOW__;
      return results[String(viewport.width) + '|' + String(viewport.height)];
    },
  };
}

module.exports = {
  chromium: {
    async launch() {
      return {
        async newContext(opts) {
          return {
            async newPage() { return makePage(opts.viewport); },
            async close() {},
          };
        },
        async close() {},
      };
    },
  },
};
"""


def _make_fake_playwright(doc_overflow_by_viewport: dict, interact_overflow_by_viewport: dict) -> str:
    doc_json = json.dumps(doc_overflow_by_viewport)
    interact_json = json.dumps(interact_overflow_by_viewport)
    return (
        _FAKE_PLAYWRIGHT_TEMPLATE
        .replace("__DOC_OVERFLOW__", doc_json)
        .replace("__INTERACT_OVERFLOW__", interact_json)
    )


def _extract_viewport_gate_script() -> str:
    """Pull the literal inline node script out of viewport_gate.action.

    The loop YAML uses `node - <<'JS'` with the closing 'JS' on its own line
    after the script body. We extract the body verbatim.
    """
    assert LOOP_FILE.exists(), f"Loop file not found: {LOOP_FILE}"
    data = yaml.safe_load(LOOP_FILE.read_text())
    action = data["states"]["viewport_gate"]["action"]
    match = re.search(r"<<'JS'\n(.+?)\n      JS", action, re.DOTALL)
    assert match, "could not locate inline `<<'JS' ... JS` Playwright script in viewport_gate.action"
    return match.group(1)


def _render_viewport_gate_action(run_dir: Path, viewports: str) -> str:
    """Render viewport_gate.action via the FSM interpolator.

    The raw action contains `${context.run_dir}` and
    `${context.viewports:shell}` placeholders that the FSM resolves at
    run time. We exercise the real renderer (rather than reimplementing the
    substitution) so this test fails if interpolation regresses.
    """
    data = yaml.safe_load(LOOP_FILE.read_text())
    action = data["states"]["viewport_gate"]["action"]
    ctx = InterpolationContext(
        context={"run_dir": str(run_dir), "viewports": viewports},
        loop_name="html-webapp-generator",
        state_name="viewport_gate",
    )
    return interpolate(action, ctx)


def _make_fake_playwright(doc_overflow_by_viewport: dict, interact_overflow_by_viewport: dict) -> str:
    doc_json = json.dumps(doc_overflow_by_viewport)
    interact_json = json.dumps(interact_overflow_by_viewport)
    return (
        _FAKE_PLAYWRIGHT_TEMPLATE
        .replace("__DOC_OVERFLOW__", doc_json)
        .replace("__INTERACT_OVERFLOW__", interact_json)
    )


def _run_gate(*, fake_playwright: str, run_dir: Path, viewports: str,
              node: str | None = None) -> subprocess.CompletedProcess[str]:
    """Render viewport_gate.action against `run_dir` + `viewports` and execute it.

    Substitutes `NODE_PATH` so the stub Playwright module is found.
    The action's first guard checks `$ABS_DIR/index.html` exists; tests
    must therefore write that file before calling.
    """
    node_modules = run_dir / "node_modules" / "@playwright"
    node_modules.mkdir(parents=True)
    (node_modules / "test").mkdir(exist_ok=True)
    (node_modules / "test" / "index.js").write_text(fake_playwright)
    (node_modules / "test" / "package.json").write_text(
        '{"name": "@playwright/test", "main": "index.js"}'
    )

    rendered = _render_viewport_gate_action(run_dir, viewports)
    # The action hardcodes `NODE_PATH="$(npm root -g)"` which would override
    # our test's NODE_PATH. We rewrite it to point at our test node_modules
    # so the stub @playwright/test module is found. Real loop runs use the
    # global Playwright install (the unmodified production behavior).
    test_node_path = str(run_dir / "node_modules")
    rendered = rendered.replace(
        'NODE_PATH="$(npm root -g)"',
        f'NODE_PATH="{test_node_path}"',
    )
    proc = subprocess.run(
        ["bash", "-c", rendered],
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(run_dir),
            "ABS_DIR": str(run_dir),
        },
        capture_output=True,
        text=True,
        timeout=60,
    )
    return proc


# Viewport geometry used in fake Playwright results. Keys are sorted `${w}|${h}`.
_FIT_ALL = {
    "1440|900": {
        "scrollHeight": 900, "scrollWidth": 1440,
        "innerHeight": 900, "innerWidth": 1440,
        "hOverflow": 0, "wOverflow": 0,
    },
    "1024|768": {
        "scrollHeight": 768, "scrollWidth": 1024,
        "innerHeight": 768, "innerWidth": 1024,
        "hOverflow": 0, "wOverflow": 0,
    },
    "375|667": {
        "scrollHeight": 667, "scrollWidth": 375,
        "innerHeight": 667, "innerWidth": 375,
        "hOverflow": 0, "wOverflow": 0,
    },
}

_NO_OVERFLOWS = {
    "1440|900": [],
    "1024|768": [],
    "375|667": [],
}

_OVERFLOWS_MOBILE = {
    "1440|900": [],
    "1024|768": [],
    "375|667": [
        {"tag": "a", "id": "drawer-link", "cls": "nav", "overflow": ["right=420>375"]},
    ],
}


def test_viewport_gate_passes_for_app_shell_page_fitting_every_viewport(tmp_path: Path) -> None:
    """A page whose geometry fits all configured viewports emits VIEWPORT_PASS.

    Acceptance criterion: viewport_gate passes for an app-shell page whose
    overflow is confined to internal scroll panes (prototype finding 2026-09-25).
    """
    require_node(min_major=None)

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "index.html").write_text(
        "<html><body style='height:100dvh;overflow:hidden'><div>app</div></body></html>"
    )

    fake = _make_fake_playwright(_FIT_ALL, _NO_OVERFLOWS)
    proc = _run_gate(fake_playwright=fake, run_dir=run_dir,
                     viewports="1440x900 1024x768 375x667")

    assert proc.returncode == 0, (
        f"expected exit 0 on pass, got {proc.returncode}. "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    assert "VIEWPORT_PASS" in proc.stdout, (
        f"expected VIEWPORT_PASS in stdout, got: {proc.stdout!r}"
    )


def test_viewport_gate_fails_when_mobile_overflows_and_appends_to_critique(
    tmp_path: Path,
) -> None:
    """A page overflowing at 375x667 fails the gate; per-viewport measurements
    are appended to critique.md and the gate emits VIEWPORT_FAIL (exit 0,
    routing to run_gen_eval).
    """
    require_node(min_major=None)

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "index.html").write_text(
        "<html><body><a id='drawer-link' style='position:absolute;left:400px'>link</a></body></html>"
    )

    fake = _make_fake_playwright(_FIT_ALL, _OVERFLOWS_MOBILE)
    proc = _run_gate(fake_playwright=fake, run_dir=run_dir,
                     viewports="1440x900 1024x768 375x667")

    assert proc.returncode == 0, (
        f"artifact failure must exit 0 (routing to on_no), got {proc.returncode}. "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    assert "VIEWPORT_FAIL" in proc.stdout, (
        f"expected VIEWPORT_FAIL in stdout, got: {proc.stdout!r}"
    )
    assert "drawer-link" in proc.stdout or "375x667" in proc.stdout, (
        f"expected per-viewport measurements mentioning the offender or viewport, "
        f"got: {proc.stdout!r}"
    )

    crit = run_dir / "critique.md"
    assert crit.exists(), "viewport_gate must append to critique.md on FAIL"
    body = crit.read_text()
    assert "## Issues to Address (viewport gate, round" in body, (
        f"critique.md must carry the gate's heading, got: {body!r}"
    )
    assert "drawer-link" in body, (
        f"critique.md must include the offender element id, got: {body!r}"
    )


def test_viewport_gate_zero_valid_viewports_is_harness_fault(tmp_path: Path) -> None:
    """A viewports string with only malformed entries is a harness fault (exit 2 -> failed)."""
    require_node(min_major=None)

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "index.html").write_text("<html><body>app</body></html>")

    fake = _make_fake_playwright(_FIT_ALL, _NO_OVERFLOWS)
    proc = _run_gate(fake_playwright=fake, run_dir=run_dir, viewports="abc xyz")

    assert proc.returncode == 2, (
        f"zero valid viewports should exit 2 (harness fault), got {proc.returncode}. "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )


def test_viewport_gate_accepts_at_round_cap(tmp_path: Path) -> None:
    """After 3 fail rounds, the gate accepts with a warning line carrying the
    failing measurements (accept-at-cap disposition; prototype-validated).

    The accept-at-cap message must still contain VIEWPORT_PASS so the FSM's
    output_contains routing evaluates `on_yes` and the loop proceeds to
    vision_gate rather than re-running run_gen_eval indefinitely.
    """
    require_node(min_major=None)

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "index.html").write_text(
        "<html><body><a id='drawer-link' style='position:absolute;left:400px'>link</a></body></html>"
    )
    # Pre-seed the round counter at the cap so the gate takes the accept path.
    (run_dir / ".viewport_rounds").write_text("3")

    fake = _make_fake_playwright(_FIT_ALL, _OVERFLOWS_MOBILE)
    proc = _run_gate(fake_playwright=fake, run_dir=run_dir,
                     viewports="1440x900 1024x768 375x667")

    assert proc.returncode == 0, (
        f"accept-at-cap must exit 0 (artifact failure routes via on_yes -> vision_gate "
        f"because the cap message contains VIEWPORT_PASS). Got {proc.returncode}. "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    assert "VIEWPORT_PASS" in proc.stdout, (
        f"accept-at-cap must emit VIEWPORT_PASS substring to route to vision_gate, "
        f"got: {proc.stdout!r}"
    )
    assert "round cap" in proc.stdout, (
        f"expected 'round cap' message in stdout, got: {proc.stdout!r}"
    )
    # The cap message must carry at least one per-viewport measurement so the
    # violation lands in the run log.
    assert "375x667" in proc.stdout, (
        f"accept-at-cap output must include per-viewport measurements, got: {proc.stdout!r}"
    )
