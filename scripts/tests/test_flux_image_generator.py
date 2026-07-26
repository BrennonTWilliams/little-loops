"""Tests for FEAT-2817: the flux-image-generator built-in loop.

Covers both the wrapper loop (``flux-image-generator.yaml``) and the oracle
variant it delegates to (``oracles/generator-evaluator-flux.yaml``), which
extends ``oracles/generator-evaluator`` via ``from:`` inheritance.

The behavioural half of this file extracts the real ``synthesize`` shell action
out of the oracle YAML, interpolates it exactly as the FSM engine would, and
runs it under bash against a local stub HTTP server standing in for the FLUX
endpoint. That exercises the acceptance criteria that cannot be checked
structurally: base64 decode to a real PNG, distinct per-iteration paths with
recorded seeds, HTTP/empty/undecodable/zero-byte failure routing, and shell
metacharacter safety in the prompt.
"""

from __future__ import annotations

import base64
import http.server
import json
import os
import subprocess
import threading
from pathlib import Path

import pytest
import yaml

from little_loops.fsm.interpolation import InterpolationContext, interpolate
from little_loops.fsm.validation import ValidationSeverity, load_and_validate, validate_fsm

BUILTIN_LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"
WRAPPER = BUILTIN_LOOPS_DIR / "flux-image-generator.yaml"
ORACLE = BUILTIN_LOOPS_DIR / "oracles" / "generator-evaluator-flux.yaml"

# Smallest valid PNG (1x1, transparent) — enough for a non-zero-byte decode check.
_PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


class TestLoopStructure:
    """Structural guarantees for the wrapper + oracle pair."""

    def test_both_files_exist(self) -> None:
        assert WRAPPER.exists(), f"missing wrapper loop: {WRAPPER}"
        assert ORACLE.exists(), f"missing oracle loop: {ORACLE}"

    @pytest.mark.parametrize("path_key", ["wrapper", "oracle"])
    def test_validates_without_errors(self, path_key: str) -> None:
        path = WRAPPER if path_key == "wrapper" else ORACLE
        fsm, warnings = load_and_validate(path)
        errors = [e for e in validate_fsm(fsm) if e.severity == ValidationSeverity.ERROR]
        assert not errors, f"{path.name}: {[str(e) for e in errors]}"
        load_errors = [w for w in warnings if w.severity == ValidationSeverity.ERROR]
        assert not load_errors, f"{path.name}: {[str(w) for w in load_errors]}"

    def test_oracle_inherits_generator_evaluator(self) -> None:
        raw = yaml.safe_load(ORACLE.read_text())
        assert raw.get("from") == "generator-evaluator", (
            "oracle must customize via from: inheritance (FEAT-2269 precedent), "
            "not by duplicating the base oracle"
        )
        assert raw.get("visibility") == "internal"

    def test_oracle_evaluate_does_not_use_playwright(self) -> None:
        """The FLUX response is already a PNG — no render/screenshot step."""
        fsm, _ = load_and_validate(ORACLE)
        action = fsm.states["evaluate"].action
        assert "playwright" not in action.lower()
        assert "screenshot.png" in action

    def test_oracle_inherits_stall_machinery(self) -> None:
        """score/record_score/check_stall/check_diff_stall come from the base."""
        fsm, _ = load_and_validate(ORACLE)
        for name in ("score", "record_score", "check_stall", "check_diff_stall"):
            assert name in fsm.states, f"oracle lost inherited state '{name}'"

    def test_oracle_max_steps_covers_intended_cycle_count(self) -> None:
        """BUG-2822: the oracle's cycle is 8 states; the budget must buy several
        full scored cycles, not silently cap out at 2.5 (the observed failure)."""
        fsm, _ = load_and_validate(ORACLE)
        INTENDED_CYCLES = 7
        assert fsm.max_steps >= 8 * INTENDED_CYCLES, (
            f"max_steps={fsm.max_steps} does not buy {INTENDED_CYCLES} full "
            "8-state cycles (generate -> synthesize -> evaluate -> snapshot -> "
            "score -> record_score -> check_stall -> check_diff_stall)"
        )

    def test_oracle_has_on_max_steps_summary_handler(self) -> None:
        """BUG-2822: budget exhaustion must be a reported outcome, not a silent
        crash that discards a generated-but-unscored image."""
        fsm, _ = load_and_validate(ORACLE)
        assert fsm.on_max_steps, "oracle must declare on_max_steps"
        assert fsm.on_max_steps in fsm.states, (
            f"on_max_steps={fsm.on_max_steps!r} does not name a real state"
        )
        summary = fsm.states[fsm.on_max_steps]
        assert summary.terminal is True, (
            "the on_max_steps handler must be terminal-doubling (BUG-158 shape) "
            "so its action actually runs"
        )

    def test_wrapper_max_steps_covers_vision_rounds(self) -> None:
        """BUG-2822: the parent must be able to complete the vision_gate <->
        run_gen_eval back-edge (ROUND_CAP: 3 rounds, 2 states/round) plus its
        4-state linear prefix, not just the single first pass."""
        fsm, _ = load_and_validate(WRAPPER)
        LINEAR_PREFIX = 4  # init, check_image_env, plan, run_gen_eval
        ROUND_CAP = 3
        STATES_PER_ROUND = 2  # run_gen_eval, vision_gate
        assert fsm.max_steps >= LINEAR_PREFIX + ROUND_CAP * STATES_PER_ROUND, (
            f"max_steps={fsm.max_steps} cannot complete {ROUND_CAP} vision "
            "rounds the loop's own code budgets for"
        )

    def test_generate_routes_through_synthesize(self) -> None:
        fsm, _ = load_and_validate(ORACLE)
        gen = fsm.states["generate"]
        assert {gen.on_yes, gen.on_no, gen.on_partial} == {"synthesize"}, (
            "the LLM generate state authors the prompt; synthesis is the shell "
            "FLUX call that must run on every generate outcome"
        )
        syn = fsm.states["synthesize"]
        assert str(getattr(syn.action_type, "value", syn.action_type)) == "shell"
        assert syn.on_yes == "evaluate"
        # MR-1: HTTP/decode failure must not be scored as a pass.
        assert syn.on_no == "failed"
        assert syn.on_error == "failed"

    def test_wrapper_delegates_to_flux_oracle(self) -> None:
        raw = yaml.safe_load(WRAPPER.read_text())
        delegating = [
            s for s in raw["states"].values() if s.get("loop") == "oracles/generator-evaluator-flux"
        ]
        assert delegating, "wrapper must delegate to oracles/generator-evaluator-flux"

    def test_wrapper_distinguishes_exhausted_from_errored_child(self) -> None:
        """BUG-2822: run_gen_eval's on_no must route to a check that separates
        "child exhausted with usable output" from "child errored", instead of
        collapsing both straight into diagnose -> failed."""
        fsm, _ = load_and_validate(WRAPPER)
        run_gen_eval = fsm.states["run_gen_eval"]
        assert run_gen_eval.capture, (
            "run_gen_eval must capture the child event stream so downstream "
            "routing can inspect it for the oracle's SUMMARY_EMITTED verdict"
        )
        assert run_gen_eval.on_no != "diagnose", (
            "on_no must not collapse straight to diagnose/failed; it must first "
            "check whether the child left usable output behind"
        )
        gate = fsm.states[run_gen_eval.on_no]
        assert gate.on_yes in fsm.states and gate.on_yes != "diagnose"
        assert gate.on_no == "diagnose"
        partial_terminal = fsm.states[gate.on_yes]
        # finalize_partial is non-terminal (action must run) and routes onward
        # to a distinct terminal from `done`.
        while not partial_terminal.terminal:
            partial_terminal = fsm.states[partial_terminal.next]
        assert partial_terminal is not fsm.states["done"], (
            "the partial-success path must not collapse into the same terminal "
            "as a clean pass"
        )

    def test_wrapper_fails_loudly_on_missing_image_base_url(self) -> None:
        """IMAGE_BASE_URL is the loop's core dependency — actionable hard failure."""
        fsm, _ = load_and_validate(WRAPPER)
        state = fsm.states["check_image_env"]
        assert "IMAGE_BASE_URL" in state.action
        assert state.on_no == "diagnose"
        assert state.on_error == "diagnose"

    def test_wrapper_vision_gate_degrades_gracefully(self) -> None:
        fsm, _ = load_and_validate(WRAPPER)
        action = fsm.states["vision_gate"].action
        assert "VISION_PASS: skipped (VISION_* env not configured)" in action

    def test_no_raw_user_input_in_shell_actions(self) -> None:
        """MR-11: the user prompt never reaches a shell body as a raw token."""
        for path in (WRAPPER, ORACLE):
            raw = yaml.safe_load(path.read_text())
            for name, state in (raw.get("states") or {}).items():
                if state.get("action_type") != "shell":
                    continue
                action = state.get("action", "")
                for token in (
                    "${context.input}",
                    "${context.description}",
                    "${context.prompt}",
                    "${context.query}",
                    "${context.task}",
                    "${context.goal}",
                    "${context.topic}",
                ):
                    assert token not in action, (
                        f"{path.name}/{name} splices {token} into a shell body (MR-11)"
                    )

    def test_registered_in_builtin_catalog_test(self) -> None:
        src = (Path(__file__).parent / "test_builtin_loops.py").read_text()
        assert '"flux-image-generator"' in src

    def test_documented_in_loops_readme(self) -> None:
        readme = (BUILTIN_LOOPS_DIR / "README.md").read_text()
        assert "`flux-image-generator`" in readme
        assert "`oracles/generator-evaluator-flux`" in readme

    def test_ll_loop_validate_exits_zero(self) -> None:
        result = subprocess.run(
            ["ll-loop", "validate", "flux-image-generator"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )
        assert result.returncode == 0, result.stdout + result.stderr


class _StubFluxHandler(http.server.BaseHTTPRequestHandler):
    """Stub FLUX endpoint. Behaviour is driven by class attributes."""

    mode = "ok"
    received: list[dict] = []

    def do_POST(self) -> None:  # noqa: N802 - stdlib API
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            _StubFluxHandler.received.append(json.loads(body))
        except Exception:
            _StubFluxHandler.received.append({"_unparseable": body.decode(errors="replace")})

        if _StubFluxHandler.mode == "http_error":
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'{"error":"boom"}')
            return

        payloads = {
            "ok": {"image_b64": base64.b64encode(_PNG_1PX).decode(), "seed": 1, "steps": 4},
            "empty": {"image_b64": "", "seed": 1, "steps": 4},
            "undecodable": {"image_b64": "!!!not base64!!!", "seed": 1, "steps": 4},
            "zero_byte": {"image_b64": "", "seed": 1, "steps": 4},
            "missing_field": {"seed": 1, "steps": 4},
        }
        data = json.dumps(payloads[_StubFluxHandler.mode]).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args: object) -> None:  # silence test output
        pass


@pytest.fixture
def flux_stub():
    _StubFluxHandler.mode = "ok"
    _StubFluxHandler.received = []
    server = http.server.HTTPServer(("127.0.0.1", 0), _StubFluxHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, _StubFluxHandler
    finally:
        server.shutdown()
        server.server_close()


def _render_synthesize(run_dir: Path) -> str:
    """Interpolate the oracle's synthesize action exactly as the engine would."""
    fsm, _ = load_and_validate(ORACLE)
    ctx = InterpolationContext(
        context={**fsm.context, "run_dir": str(run_dir)},
        captured={},
        prev=None,
    )
    return interpolate(fsm.states["synthesize"].action, ctx)


def _run_synthesize(run_dir: Path, base_url: str, prompt: str) -> subprocess.CompletedProcess:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "image-prompt.txt").write_text(prompt)
    env = {**os.environ, "IMAGE_BASE_URL": base_url}
    env.pop("LL_DOTENV", None)
    return subprocess.run(
        ["bash", "-c", _render_synthesize(run_dir)],
        capture_output=True,
        text=True,
        env=env,
        cwd=run_dir,  # keep the state's `.env` sourcing away from the repo .env
    )


class TestSynthesizeBehaviour:
    """Behavioural tests for the FLUX generate/decode shell state."""

    def test_happy_path_writes_png_and_records_seed(self, flux_stub, tmp_path: Path) -> None:
        server, handler = flux_stub
        url = f"http://127.0.0.1:{server.server_port}"
        run_dir = tmp_path / "run"
        result = _run_synthesize(run_dir, url, "a server rack, flat vector diagram")

        assert "IMAGE_OK" in result.stdout, result.stdout + result.stderr
        artifact = run_dir / "image.png"
        assert artifact.exists() and artifact.stat().st_size > 0
        assert artifact.read_bytes() == _PNG_1PX

        iter_pngs = sorted(run_dir.glob("image-iter-*.png"))
        assert len(iter_pngs) == 1, f"expected one per-iteration PNG, got {iter_pngs}"
        seeds = (run_dir / "seeds.txt").read_text()
        assert iter_pngs[0].name in seeds
        assert "seed=" in seeds

        # The prompt reached the endpoint as JSON, unmangled.
        assert handler.received[0]["prompt"] == "a server rack, flat vector diagram"

    def test_second_iteration_does_not_overwrite_and_uses_a_new_seed(
        self, flux_stub, tmp_path: Path
    ) -> None:
        server, _ = flux_stub
        url = f"http://127.0.0.1:{server.server_port}"
        run_dir = tmp_path / "run"
        _run_synthesize(run_dir, url, "first")
        _run_synthesize(run_dir, url, "second")

        iter_pngs = sorted(run_dir.glob("image-iter-*.png"))
        assert len(iter_pngs) == 2, f"iterations must not overwrite: {iter_pngs}"
        seed_lines = [ln for ln in (run_dir / "seeds.txt").read_text().splitlines() if ln.strip()]
        assert len(seed_lines) == 2
        seeds = {ln.split("seed=")[1].split()[0] for ln in seed_lines}
        assert len(seeds) == 2, f"seed must vary per iteration, got {seed_lines}"

    def test_stale_prompt_on_second_iteration_fails_loudly(
        self, flux_stub, tmp_path: Path
    ) -> None:
        """BUG-2822: a regenerate against an unrewritten image-prompt.txt must
        fail loudly (IMAGE_FAIL) on iteration >= 2 instead of burning a full
        FLUX generation to re-render a near-identical latent."""
        server, handler = flux_stub
        url = f"http://127.0.0.1:{server.server_port}"
        run_dir = tmp_path / "run"
        first = _run_synthesize(run_dir, url, "a server rack, flat vector diagram")
        assert "IMAGE_OK" in first.stdout, first.stdout + first.stderr

        second = _run_synthesize(run_dir, url, "a server rack, flat vector diagram")
        combined = second.stdout + second.stderr
        assert "IMAGE_OK" not in combined, combined
        assert "IMAGE_FAIL" in combined, combined
        assert len(handler.received) == 1, (
            "the stale-prompt gate must fail before the second HTTP call is made"
        )

    def test_shell_metacharacters_in_prompt_are_safe(self, flux_stub, tmp_path: Path) -> None:
        server, handler = flux_stub
        url = f"http://127.0.0.1:{server.server_port}"
        run_dir = tmp_path / "run"
        nasty = "a \"rack\" with $HOME and `whoami` and 100% power! \\ and 'quotes'"
        result = _run_synthesize(run_dir, url, nasty)

        assert "IMAGE_OK" in result.stdout, result.stdout + result.stderr
        assert handler.received[0]["prompt"] == nasty, "prompt must reach the API verbatim"
        # No command substitution leaked into the payload.
        assert "whoami" in handler.received[0]["prompt"]
        assert os.environ.get("HOME", "/nonexistent") not in handler.received[0]["prompt"]

    @pytest.mark.parametrize("mode", ["http_error", "empty", "undecodable", "missing_field"])
    def test_failure_modes_do_not_report_success(
        self, flux_stub, tmp_path: Path, mode: str
    ) -> None:
        server, handler = flux_stub
        handler.mode = mode
        url = f"http://127.0.0.1:{server.server_port}"
        run_dir = tmp_path / "run"
        result = _run_synthesize(run_dir, url, "anything")

        combined = result.stdout + result.stderr
        assert "IMAGE_OK" not in combined, f"{mode} must not report success: {combined}"
        assert "IMAGE_FAIL" in combined, f"{mode} must emit an actionable failure: {combined}"
        assert not (run_dir / "image.png").exists() or (run_dir / "image.png").stat().st_size > 0

    def test_missing_image_base_url_is_actionable(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir(parents=True)
        (run_dir / "image-prompt.txt").write_text("anything")
        env = {k: v for k, v in os.environ.items() if k != "IMAGE_BASE_URL"}
        result = subprocess.run(
            ["bash", "-c", _render_synthesize(run_dir)],
            capture_output=True,
            text=True,
            env=env,
            cwd=run_dir,
        )
        combined = result.stdout + result.stderr
        assert "IMAGE_OK" not in combined
        assert "IMAGE_BASE_URL" in combined
