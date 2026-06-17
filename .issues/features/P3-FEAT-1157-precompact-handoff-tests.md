---
id: FEAT-1157
type: FEAT
priority: P3
status: done
discovered_date: 2026-04-18
discovered_by: issue-size-review
completed_at: 2026-06-17 13:38:07+00:00
blocked_by: []
parent: FEAT-1113
relates_to:
- FEAT-1156
- FEAT-1158
confidence_score: 98
outcome_confidence: 89
score_complexity: 22
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 25
decision_needed: false
---

# FEAT-1157: PreCompact Handoff Hook — Integration Tests

## Summary

Write `TestPrecompactHandoff` integration tests in `scripts/tests/test_hooks_integration.py` and review timing-sensitive existing tests that a fresh `ll-continue-prompt.md` write could break.

Both blockers (FEAT-1112, FEAT-1156) are now `done` — `pre_compact_handoff.py` and `precompact-handoff.sh` exist and have unit-test coverage. This issue adds the **shell-adapter integration layer**: tests that run `precompact-handoff.sh` via subprocess exactly as Claude Code does.

## Parent Issue

Decomposed from FEAT-1113: PreCompact Auto-Handoff Hook

## Acceptance Criteria

- `TestPrecompactHandoff` class added to `scripts/tests/test_hooks_integration.py`, modeled after `TestPrecompactState` (line 2037)
- Test coverage:
  - (a) Hook produces `ll-continue-prompt.md` ≤ 2KB (exit 2, file exists, `len(read_bytes()) <= 2048`)
  - (b) Priority-tier dropping under size pressure with synthetic large in-progress list
  - (c) Idempotency: exit 0 (no file write) when `ll-continue-prompt.md` mtime > `compacted_at` in `.ll/ll-precompact-state.json`
  - (d) Schema validation: produced file has YAML frontmatter (`---`), `## Intent` heading, `## Next Steps` heading
- Timing-sensitive tests reviewed and confirmed safe (or isolated):
  - `test_hooks_integration.py:435` — `test_reminder_rate_limited_second_call`
  - `test_hooks_integration.py:490` — `test_state_contains_last_reminder_at_after_exit2`
  - `test_hooks_integration.py:532` — `test_fresh_state_with_handoff_file_sets_handoff_complete_false`
- Existing tests unbroken:
  - `scripts/tests/test_subprocess_utils.py:150` — `TestReadContinuationPrompt`
  - `scripts/tests/test_issue_manager.py` — patches `read_continuation_prompt`
  - `scripts/tests/test_worker_pool.py:2202` — patches `read_continuation_prompt`
  - `scripts/tests/test_cli_loop_lifecycle.py:665,715` — continuation prompt display

## Integration Map

### Files to Modify

- `scripts/tests/test_hooks_integration.py` — add `TestPrecompactHandoff` class after `TestPrecompactState` (line 2037); review timing-sensitive tests at lines 435, 490, 532

### Shell Adapter (under test)

- `hooks/adapters/claude-code/precompact-handoff.sh` — 3-line script: reads stdin via `cat`, pipes to `python -m little_loops.hooks pre_compact_handoff`, exits with Python exit code
- `scripts/little_loops/hooks/pre_compact_handoff.py` — Python handler; `handle()` and `_build_content()` functions; writes `.ll/ll-continue-prompt.md`

### Dependent Files (not modified, must stay green)

- `scripts/tests/test_pre_compact_handoff.py` — unit tests for handler logic at Python level; `TestBuildContent`, `TestIdempotencyGuard`, `TestResultContract`, `TestOutputSchema`, `TestSubprocessDegradation`, `TestExceptionSafety` already cover internals — integration tests must exercise the **shell → dispatcher → handler** path without duplicating unit logic
- `scripts/tests/test_hook_intents.py` — dispatcher-level test at `TestHooksMainModule.test_dispatch_pre_compact_handoff_happy_path` (Python -m invocation, no shell wrapper); the new `TestPrecompactHandoff` adds the `.sh` wrapper layer on top

### Model Class

- `scripts/tests/test_hooks_integration.py:2037` — `TestPrecompactState` — exact structural model: `hook_script` fixture → `os.chdir(tmp_path)` + `try/finally` → `subprocess.run([str(hook_script)], input=json.dumps(input_data), ...)` → file assertions

### Test Configuration

- `scripts/little_loops/hooks/types.py` — `LLHookEvent`, `LLHookResult` (not used directly in integration tests; used by the Python handler under test)
- `hooks/hooks.json` — PreCompact hooks registered at lines 176–199 (reference only; not exercised by pytest)

## Implementation

### New Test Class

Add to `scripts/tests/test_hooks_integration.py` after `TestPrecompactState` (line 2037), using identical structural patterns:

```python
class TestPrecompactHandoff:
    """Integration tests for precompact-handoff.sh shell adapter.

    Exercises the shell → dispatcher → pre_compact_handoff.handle() path.
    Unit-level handler logic is covered by test_pre_compact_handoff.py.
    """

    @pytest.fixture
    def hook_script(self) -> Path:
        """Path to the Claude Code precompact-handoff adapter."""
        return Path(__file__).parent.parent.parent / "hooks/adapters/claude-code/precompact-handoff.sh"

    def test_produces_prompt_file_within_2kb(self, hook_script: Path, tmp_path: Path):
        """(a) Hook writes ll-continue-prompt.md ≤ 2KB and exits 2."""
        import os
        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = subprocess.run(
                [str(hook_script)],
                input=json.dumps({}),
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert result.returncode == 2
            prompt_file = tmp_path / ".ll" / "ll-continue-prompt.md"
            assert prompt_file.exists()
            assert len(prompt_file.read_bytes()) <= 2048
        finally:
            os.chdir(original_dir)

    def test_priority_tier_dropping_under_size_pressure(self, hook_script: Path, tmp_path: Path):
        """(b) Output stays ≤ 2KB even with a large in-progress issues list."""
        import os
        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            # Simulate large issues list by pre-writing a 1.9KB ll-session-events.jsonl
            # so the handler has heavy Section 3 content to drop
            ll_dir = tmp_path / ".ll"
            ll_dir.mkdir(exist_ok=True)
            (ll_dir / "ll-session-events.jsonl").write_text(
                '{"type": "tool_use"}\n' * 200
            )
            result = subprocess.run(
                [str(hook_script)],
                input=json.dumps({}),
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert result.returncode == 2
            prompt_file = tmp_path / ".ll" / "ll-continue-prompt.md"
            assert prompt_file.exists()
            assert len(prompt_file.read_bytes()) <= 2048
        finally:
            os.chdir(original_dir)

    def test_idempotency_skips_when_prompt_is_fresh(self, hook_script: Path, tmp_path: Path):
        """(c) Exit 0 (no write) when ll-continue-prompt.md mtime > compacted_at."""
        import os, json, time
        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            ll_dir = tmp_path / ".ll"
            ll_dir.mkdir(exist_ok=True)

            # Write a precompact state file with compacted_at in the past
            past_ts = "2000-01-01T00:00:00"
            (ll_dir / "ll-precompact-state.json").write_text(
                json.dumps({"compacted_at": past_ts, "preserved": True, "recent_plan_files": []})
            )

            # Write a fresh prompt file (mtime > past_ts → idempotency guard fires)
            prompt_file = ll_dir / "ll-continue-prompt.md"
            prompt_file.write_text("---\nsession_date: today\n---\n## Intent\n\n## Next Steps\n")

            result = subprocess.run(
                [str(hook_script)],
                input=json.dumps({}),
                capture_output=True,
                text=True,
                timeout=10,
            )
            # Idempotency path exits 0 (no feedback written to stderr)
            assert result.returncode == 0
        finally:
            os.chdir(original_dir)

    def test_schema_has_required_resume_sections(self, hook_script: Path, tmp_path: Path):
        """(d) Produced file has YAML frontmatter, ## Intent, and ## Next Steps."""
        import os
        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = subprocess.run(
                [str(hook_script)],
                input=json.dumps({}),
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert result.returncode == 2
            content = (tmp_path / ".ll" / "ll-continue-prompt.md").read_text(encoding="utf-8")
            assert content.startswith("---")
            assert "session_date:" in content
            assert "## Intent" in content
            assert "## Next Steps" in content
        finally:
            os.chdir(original_dir)
```

### Timing-Sensitive Test Review

**Assessment** (from codebase analysis of `context-monitor.sh:371–384`): all three tests are **safe** — no isolation changes needed.

The mtime check in `context-monitor.sh` is gated by `[ "$USAGE_PERCENT" -ge "$THRESHOLD" ]`. Each timing-sensitive test runs in its own `tmp_path` via `os.chdir(tmp_path)` + try/finally; `precompact-handoff.sh` is never invoked within those tests. Cross-test filesystem contamination is impossible.

- **line 435 `test_reminder_rate_limited_second_call`**: does NOT write `ll-continue-prompt.md`; the new hook class adds a separate test class in the same file but shares no shared state. No isolation change needed.
- **line 490 `test_state_contains_last_reminder_at_after_exit2`**: same — isolated `tmp_path`. Safe.
- **line 532 `test_fresh_state_with_handoff_file_sets_handoff_complete_false`**: explicitly writes `ll-continue-prompt.md` itself before running `context-monitor.sh`; usage stays below threshold so the mtime block is never reached. Safe.

### Key Behavioral Details for Test Authoring

- **Exit codes**: handler returns `exit_code=2` on successful write (precompact hooks use exit 2 to show stderr feedback to user), `exit_code=0` on idempotency skip or exception. Shell adapter propagates Python exit code directly.
- **Output path**: always `.ll/ll-continue-prompt.md` relative to cwd — tests must `os.chdir(tmp_path)` so the file lands under `tmp_path / ".ll" / "ll-continue-prompt.md"`.
- **Stdin format**: `precompact-handoff.sh` pipes stdin verbatim to Python; `handle()` never reads `event.payload`. Any valid JSON dict works (e.g., `{}` or `{"transcript_path": "/tmp/x.jsonl"}`).
- **Idempotency guard source**: reads `.ll/ll-precompact-state.json` key `compacted_at` (ISO datetime written by `pre_compact.py`). If file absent, guard falls through and write proceeds.
- **Size cap**: `_build_content()` enforces LIFO — drops Section 3 (`## Recent Activity`), then Section 2 (`## Decisions Made`), then Section 1 (`## File Modifications`). Section 0 (header + frontmatter) is always kept.

## Files to Modify

- `scripts/tests/test_hooks_integration.py` — add `TestPrecompactHandoff` class after `TestPrecompactState` (line 2037); confirm no changes needed on lines 435, 490, 532

## Verification Notes

**Verdict**: VALID — Verified 2026-04-23

- No `TestPrecompactHandoff` class in `scripts/tests/test_hooks_integration.py` ✓
- Both blockers now done: FEAT-1156 (done 2026-06-17), FEAT-1112 (done) ✓
- `pre_compact_handoff.py` and `precompact-handoff.sh` exist and are tested at unit level ✓

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis 2026-06-17:_

- `scripts/little_loops/hooks/pre_compact_handoff.py` — `handle()` and `_build_content(sections, max_bytes=2048)` confirmed present
- `hooks/adapters/claude-code/precompact-handoff.sh` — 3-line wrapper: `INPUT=$(cat); echo "$INPUT" | python -m little_loops.hooks pre_compact_handoff; exit $?`
- `scripts/tests/test_pre_compact_handoff.py` — unit coverage in `TestBuildContent`, `TestIdempotencyGuard`, `TestOutputSchema`, `TestResultContract`, `TestSubprocessDegradation`, `TestExceptionSafety`; integration tests must not duplicate these
- `scripts/tests/test_hook_intents.py` — `test_dispatch_pre_compact_handoff_happy_path` covers Python dispatcher layer; shell layer is the remaining gap
- `TestPrecompactState` confirmed at line 2037 (issue previously said 1468 — stale line number now corrected above)
- Timing tests confirmed at lines 435/490/532 — all in isolated `tmp_path` environments, no cross-test interference risk

## References

- Depends on: FEAT-1156 (done), FEAT-1112 (done)
- Docs: FEAT-1158

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue adds `TestPrecompactHandoff` to `scripts/tests/test_hooks_integration.py`. FEAT-1262 also adds `TestSessionCapture` to the same file (class confirmed at line 2942). No logical conflict exists (different test classes), but concurrent edits risk git merge conflicts. If worked in parallel, coordinate line insertions or serialize work on this shared test file.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-16_

**Readiness Score**: 72/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 85/100 → HIGH CONFIDENCE

### Concerns

- ~~`pre_compact_handoff.py` and `precompact-handoff.sh` must be delivered (FEAT-1156) before any test in this class can be run; do not start until FEAT-1156 is merged~~ — **RESOLVED**: FEAT-1156 is done
- Lines 435, 490, 532 in `test_hooks_integration.py` (rate-limit and mtime tests) need a read-and-decide pass — **RESOLVED**: analysis confirms all three are safe (see Timing-Sensitive Test Review above)

## Session Log
- `/ll:ready-issue` - 2026-06-17T13:35:27 - `e4dfb0b3-15eb-4d46-a615-8452feeb092b.jsonl`
- `/ll:confidence-check` - 2026-06-17T14:00:00Z - `c0db3348-450a-4490-804d-df87b4c6bdce.jsonl`
- `/ll:refine-issue` - 2026-06-17T13:29:43 - `8dcc2379-31de-47b9-af33-931e7d690937.jsonl`
- `/ll:refine-issue` - 2026-06-17T13:29:35 - `8dcc2379-31de-47b9-af33-931e7d690937.jsonl`
- `/ll:refine-issue` - 2026-06-17T00:00:00Z - `current`
- `/ll:confidence-check` - 2026-06-17T00:00:00Z - `368fa975-0c10-4e7f-863f-7fdb38b5aead.jsonl`
- `/ll:confidence-check` - 2026-06-16T00:00:00Z - `582fb982-6866-45ba-b90e-d2cfdc139ff2.jsonl`
- `/ll:verify-issues` - 2026-05-14T20:42:05 - `08e4ebf6-4da6-445a-91f6-ae578f565978.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:21:15 - `8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:verify-issues` - 2026-04-26T19:34:07 - `316256f6-01c2-468b-8efc-2db79aff6b29.jsonl`
- `/ll:verify-issues` - 2026-04-24T03:02:16 - `1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`
