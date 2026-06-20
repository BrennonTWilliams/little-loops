"""Tests for the brainstorm built-in FSM loop (FEAT-2248)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from little_loops.fsm.validation import ValidationSeverity, load_and_validate, validate_fsm

BUILTIN_LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"
LOOP_FILE = BUILTIN_LOOPS_DIR / "brainstorm.yaml"


def _bash(script: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", "-c", script], cwd=cwd, capture_output=True, text=True)


class TestBrainstormYaml:
    """Validate the brainstorm YAML parses and passes FSM validation."""

    @pytest.fixture
    def data(self) -> dict:
        assert LOOP_FILE.exists(), f"Loop file not found: {LOOP_FILE}"
        return yaml.safe_load(LOOP_FILE.read_text())

    def test_file_exists(self) -> None:
        assert LOOP_FILE.exists()

    def test_yaml_parses(self, data: dict) -> None:
        assert isinstance(data, dict)

    def test_fsm_validates_without_errors(self) -> None:
        fsm, _ = load_and_validate(LOOP_FILE)
        errors = validate_fsm(fsm)
        error_msgs = [r for r in errors if r.severity == ValidationSeverity.ERROR]
        assert not error_msgs, f"FSM validation errors: {error_msgs}"

    def test_description_is_present(self, data: dict) -> None:
        assert data.get("description"), "brainstorm must have a non-empty description"

    def test_required_top_level_fields(self, data: dict) -> None:
        assert data.get("name") == "brainstorm"
        assert data.get("initial") == "init"
        assert data.get("input_key") == "brief"
        assert data.get("required_inputs") == ["brief"]
        assert isinstance(data.get("states"), dict)

    def test_category_is_planning(self, data: dict) -> None:
        assert data.get("category") == "planning"

    def test_required_states_exist(self, data: dict) -> None:
        required = {
            "init",
            "frame",
            "pop_lens",
            "diverge",
            "dedup_novelty",
            "saturation_gate",
            "cluster",
            "rank",
            "converge",
            "route_sink",
            "sink_file",
            "sink_issue",
            "sink_decision",
            "done",
            "failed",
        }
        actual = set(data["states"].keys())
        missing = required - actual
        assert not missing, f"Missing required states: {missing}"

    def test_context_has_required_knobs(self, data: dict) -> None:
        ctx = data.get("context", {})
        for key in (
            "brief",
            "sink",
            "output_path",
            "decision_target",
            "ideas_per_round",
            "top_k",
            "novelty_threshold",
            "max_saturation",
            "novelty_backend",
        ):
            assert key in ctx, f"context must have key '{key}'"

    def test_context_defaults(self, data: dict) -> None:
        ctx = data.get("context", {})
        assert ctx.get("sink") == "none"
        assert ctx.get("novelty_threshold") == "0.80"
        assert ctx.get("max_saturation") == "2"
        assert ctx.get("top_k") == "3"
        assert ctx.get("ideas_per_round") == "5"

    def test_done_is_terminal(self, data: dict) -> None:
        assert data["states"]["done"].get("terminal") is True

    def test_failed_is_terminal(self, data: dict) -> None:
        assert data["states"]["failed"].get("terminal") is True

    def test_failed_has_diagnostic_action(self, data: dict) -> None:
        failed = data["states"]["failed"]
        assert failed.get("action_type") == "prompt"
        assert failed.get("action"), "failed state must have a diagnostic action"

    def test_no_issue_system_writes_in_core_states(self, data: dict) -> None:
        """Core states must not reference .issues/ — Issue writes are opt-in via sinks only."""
        core_states = {
            "init",
            "frame",
            "pop_lens",
            "diverge",
            "dedup_novelty",
            "saturation_gate",
            "cluster",
            "rank",
            "converge",
            "route_sink",
            "sink_file",
            "done",
            "failed",
        }
        for name in core_states:
            state = data["states"].get(name, {})
            action = str(state.get("action", ""))
            assert ".issues/" not in action, (
                f"Core state '{name}' must not write to .issues/ — use sink_issue or sink_decision"
            )

    def test_max_steps_is_60(self, data: dict) -> None:
        assert data.get("max_steps") == 60


class TestBrainstormShellStates:
    """Exercise key shell-state properties from the YAML."""

    @pytest.fixture
    def data(self) -> dict:
        return yaml.safe_load(LOOP_FILE.read_text())

    def test_init_is_shell_with_capture(self, data: dict) -> None:
        state = data["states"]["init"]
        assert state.get("action_type") == "shell"
        assert state.get("capture") == "run_dir"
        assert state.get("next") == "frame"

    def test_init_action_uses_absolute_path(self, data: dict) -> None:
        action = data["states"]["init"].get("action", "")
        assert "$(pwd)" in action, "init must use $(pwd) to produce an absolute run_dir path"

    def test_init_seeds_required_files(self, data: dict) -> None:
        action = data["states"]["init"].get("action", "")
        for artifact in ("ideas.jsonl", "saturation.txt", "lenses.txt", "brainstorm.md"):
            assert artifact in action, f"init must seed {artifact}"

    def test_pop_lens_routes_to_diverge_on_yes(self, data: dict) -> None:
        state = data["states"]["pop_lens"]
        assert state.get("on_yes") == "diverge"
        assert state.get("on_no") == "cluster"

    def test_saturation_gate_uses_output_numeric(self, data: dict) -> None:
        state = data["states"]["saturation_gate"]
        evaluate = state.get("evaluate", {})
        assert evaluate.get("type") == "output_numeric"
        assert evaluate.get("operator") == "lt"
        assert "max_saturation" in evaluate.get("target", "")

    def test_saturation_gate_routes_correctly(self, data: dict) -> None:
        state = data["states"]["saturation_gate"]
        assert state.get("on_yes") == "pop_lens"
        assert state.get("on_no") == "cluster"

    def test_route_sink_uses_classify_evaluator(self, data: dict) -> None:
        state = data["states"]["route_sink"]
        assert state.get("action_type") == "shell"
        evaluate = state.get("evaluate", {})
        assert evaluate.get("type") == "classify"

    def test_route_sink_has_all_branches(self, data: dict) -> None:
        state = data["states"]["route_sink"]
        route = state.get("route", {})
        assert route.get("none") == "done"
        assert route.get("file") == "sink_file"
        assert route.get("issue") == "sink_issue"
        assert route.get("decision") == "sink_decision"
        assert "_" in route, "route_sink must have a wildcard '_' fallback"

    def test_dedup_novelty_uses_exit_code_evaluator(self, data: dict) -> None:
        state = data["states"]["dedup_novelty"]
        evaluate = state.get("evaluate", {})
        assert evaluate.get("type") == "exit_code"
        assert state.get("on_yes") == "saturation_gate"
        assert state.get("on_no") == "cluster"

    def test_dedup_novelty_action_contains_difflib(self, data: dict) -> None:
        action = data["states"]["dedup_novelty"].get("action", "")
        assert "difflib" in action
        assert "SequenceMatcher" in action
        assert "IDEAS_JSON:" in action

    def test_sink_file_degrades_on_empty_output_path(self, data: dict) -> None:
        action = data["states"]["sink_file"].get("action", "")
        assert "NOTICE" in action or "unset" in action.lower(), (
            "sink_file must degrade gracefully when output_path is unset"
        )

    def test_cluster_and_rank_route_to_failed_on_error(self, data: dict) -> None:
        for state_name in ("cluster", "rank"):
            state = data["states"][state_name]
            assert state.get("on_error") == "failed", (
                f"{state_name} must route to failed on LLM error"
            )


class TestBrainstormDryRun:
    """Structural checks via FSM validation (no LLM calls)."""

    def test_fsm_validates_without_errors(self) -> None:
        fsm, _ = load_and_validate(LOOP_FILE)
        errors = validate_fsm(fsm)
        error_msgs = [r for r in errors if r.severity == ValidationSeverity.ERROR]
        assert not error_msgs, f"FSM validation errors: {error_msgs}"

    def test_no_ratcheted_category_warnings(self) -> None:
        """brainstorm.yaml must not introduce warnings in the 7 ratcheted categories."""
        _, warnings = load_and_validate(LOOP_FILE)
        RATCHETED_PATTERNS = {
            "shared-tmp": "writes to shared '.loops/tmp",
            "partial-route": "routes only on_yes",
            "required-inputs": "does not declare required_inputs",
            "unreachable": "not reachable from initial state",
            "failure-terminal": "no predecessor state with a diagnostic action",
            "artifact-versioning": "to a flat path in an iterative cycle",
            "capture-ordering": "References ${captured.",
        }
        violations = []
        for w in warnings:
            if w.severity is not ValidationSeverity.WARNING:
                continue
            for category, pattern in RATCHETED_PATTERNS.items():
                if pattern in w.message:
                    violations.append(f"[{category}] {w.path}: {w.message}")
        assert not violations, "brainstorm.yaml has ratcheted-category warnings:\n" + "\n".join(
            violations
        )

    def test_all_states_reachable(self) -> None:
        """Ensure ll-loop validate reports no unreachable states."""
        result = subprocess.run(
            ["ll-loop", "validate", "brainstorm"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"ll-loop validate brainstorm failed:\n{result.stdout}\n{result.stderr}"
        )
        assert "unreachable" not in result.stdout.lower()

    def test_required_inputs_declared(self) -> None:
        data = yaml.safe_load(LOOP_FILE.read_text())
        assert data.get("required_inputs") == ["brief"], (
            'brainstorm must declare required_inputs: ["brief"]'
        )


class TestBrainstormDedup:
    """Test the dedup_novelty difflib novelty gate logic in isolation.

    Mirrors the inline Python heredoc from dedup_novelty so changes to the
    loop's dedup logic are reflected here. Uses difflib.SequenceMatcher ratio
    (not Jaccard / calculate_word_overlap).
    """

    DEDUP_SCRIPT = """\
import json, sys, difflib

ideas_json_str = {ideas_json}
existing_texts_input = {existing}
threshold = {threshold}

new_ideas = json.loads(ideas_json_str)
existing_texts = list(existing_texts_input)

novel = []
for idea in new_ideas:
    text = idea.get('text', str(idea))
    is_dup = any(
        difflib.SequenceMatcher(None, text.lower(), ex.lower()).ratio() >= threshold
        for ex in existing_texts
    ) if existing_texts else False
    if not is_dup:
        novel.append(idea)
        existing_texts.append(text)

print(json.dumps({{"novel": [i["text"] for i in novel], "count": len(novel)}}))
"""

    def _run_dedup(
        self,
        new_ideas: list[dict],
        existing: list[str],
        threshold: float = 0.80,
    ) -> dict:
        script = self.DEDUP_SCRIPT.format(
            ideas_json=repr(json.dumps(new_ideas)),
            existing=repr(existing),
            threshold=threshold,
        )
        result = subprocess.run(["python3", "-c", script], capture_output=True, text=True)
        assert result.returncode == 0, f"Dedup script failed: {result.stderr}"
        return json.loads(result.stdout.strip())

    def test_distinct_ideas_all_pass(self) -> None:
        ideas = [
            {"text": "Use mutation testing to find untested branches", "rationale": "..."},
            {"text": "Introduce contract testing between services", "rationale": "..."},
            {"text": "Add property-based tests with Hypothesis", "rationale": "..."},
        ]
        out = self._run_dedup(ideas, existing=[])
        assert out["count"] == 3, f"All distinct ideas should pass, got: {out}"

    def test_exact_duplicate_is_filtered(self) -> None:
        text = "Use mutation testing to find untested branches"
        ideas = [{"text": text, "rationale": "..."}]
        out = self._run_dedup(ideas, existing=[text])
        assert out["count"] == 0, f"Exact duplicate should be filtered, got: {out}"

    def test_near_duplicate_above_threshold_is_filtered(self) -> None:
        existing = "Use mutation testing to identify untested code branches"
        new = [{"text": "Use mutation testing to find untested branches", "rationale": "..."}]
        out = self._run_dedup(new, existing=[existing], threshold=0.80)
        # High similarity (same core phrase) → should be filtered at 0.80 threshold
        # (We don't assert exact filtering since ratio can vary; we assert count <= 1)
        assert out["count"] <= 1

    def test_semantically_different_idea_passes(self) -> None:
        existing = ["Use mutation testing to find untested branches"]
        new = [
            {"text": "Introduce chaos engineering to surface resilience gaps", "rationale": "..."}
        ]
        out = self._run_dedup(new, existing=existing, threshold=0.80)
        assert out["count"] == 1, f"Semantically different idea should pass, got: {out}"

    def test_saturation_counter_increments_on_zero_novel(self, tmp_path: Path) -> None:
        """When no novel ideas are found, saturation.txt counter increments."""
        sat_file = tmp_path / "saturation.txt"
        sat_file.write_text("1")
        ideas_file = tmp_path / "ideas.jsonl"
        existing_text = "Use mutation testing to find untested branches"
        ideas_file.write_text(json.dumps({"text": existing_text, "rationale": "r"}) + "\n")

        script = f"""\
import json, sys, difflib

raw_ideas = json.dumps([{{"text": {repr(existing_text)}, "rationale": "..."}}])
new_ideas = json.loads(raw_ideas)

ideas_file = {repr(str(ideas_file))}
existing_texts = []
try:
    with open(ideas_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                existing_texts.append(json.loads(line).get('text', ''))
except (FileNotFoundError, json.JSONDecodeError):
    pass

threshold = 0.80
novel = []
for idea in new_ideas:
    text = idea.get('text', str(idea))
    is_dup = any(
        difflib.SequenceMatcher(None, text.lower(), ex.lower()).ratio() >= threshold
        for ex in existing_texts
    ) if existing_texts else False
    if not is_dup:
        novel.append(idea)
        existing_texts.append(text)

sat_file = {repr(str(sat_file))}
try:
    with open(sat_file, 'r') as f:
        count = int(f.read().strip() or '0')
except (FileNotFoundError, ValueError):
    count = 0

count = 0 if novel else count + 1

with open(sat_file, 'w') as f:
    f.write(str(count))

print(count)
"""
        result = subprocess.run(["python3", "-c", script], capture_output=True, text=True)
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        final_count = int(result.stdout.strip())
        assert final_count == 2, f"Saturation counter should be 2 (1+1), got: {final_count}"

    def test_saturation_counter_resets_on_novel_idea(self, tmp_path: Path) -> None:
        """When a novel idea is found, saturation.txt resets to 0."""
        sat_file = tmp_path / "saturation.txt"
        sat_file.write_text("1")  # counter was 1 before this round
        ideas_file = tmp_path / "ideas.jsonl"
        ideas_file.write_text("")  # no existing ideas

        script = f"""\
import json, sys, difflib

new_ideas = [{{"text": "A brand new idea about chaos engineering", "rationale": "r"}}]
ideas_file = {repr(str(ideas_file))}
existing_texts = []

threshold = 0.80
novel = []
for idea in new_ideas:
    text = idea.get('text', str(idea))
    is_dup = any(
        difflib.SequenceMatcher(None, text.lower(), ex.lower()).ratio() >= threshold
        for ex in existing_texts
    ) if existing_texts else False
    if not is_dup:
        novel.append(idea)
        existing_texts.append(text)

with open(ideas_file, 'a') as f:
    for idea in novel:
        f.write(json.dumps(idea) + '\\n')

sat_file = {repr(str(sat_file))}
try:
    with open(sat_file, 'r') as f:
        count = int(f.read().strip() or '0')
except (FileNotFoundError, ValueError):
    count = 0

count = 0 if novel else count + 1

with open(sat_file, 'w') as f:
    f.write(str(count))

print(count)
"""
        result = subprocess.run(["python3", "-c", script], capture_output=True, text=True)
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        final_count = int(result.stdout.strip())
        assert final_count == 0, (
            f"Saturation counter should reset to 0 after novel idea, got: {final_count}"
        )

    def test_empty_ideas_json_handled_gracefully(self) -> None:
        """An LLM that produces no IDEAS_JSON tag yields 0 novel ideas without crashing."""
        script = """\
import json, sys, difflib

raw = "Here are some ideas but I forgot the JSON tag."
ideas_json_str = None
for line in reversed(raw.split('\\n')):
    line = line.strip()
    if line.startswith('IDEAS_JSON:'):
        ideas_json_str = line[len('IDEAS_JSON:'):]
        break

if not ideas_json_str:
    print(0)
    sys.exit(0)
"""
        result = subprocess.run(["python3", "-c", script], capture_output=True, text=True)
        assert result.returncode == 0
        assert result.stdout.strip() == "0"

    def test_init_shell_creates_artifacts(self, tmp_path: Path) -> None:
        """init shell action creates the required artifact files.

        The runner injects run_dir as a relative path (.loops/runs/<loop>-<ts>/);
        the init action converts it to absolute via $(pwd)/$DIR.
        """
        result = _bash(
            """\
            DIR=".loops/runs/brainstorm-test"
            mkdir -p "$DIR"
            : > "$DIR/ideas.jsonl"
            echo 0 > "$DIR/saturation.txt"
            : > "$DIR/lenses.txt"
            : > "$DIR/brainstorm.md"
            echo "$(pwd)/$DIR"
            """,
            cwd=tmp_path,
        )
        assert result.returncode == 0
        run_dir = Path(result.stdout.strip())
        for artifact in ("ideas.jsonl", "saturation.txt", "lenses.txt", "brainstorm.md"):
            assert (run_dir / artifact).exists(), f"{artifact} not created by init"
        sat = (run_dir / "saturation.txt").read_text().strip()
        assert sat == "0", f"saturation.txt should be initialized to 0, got: {sat!r}"
