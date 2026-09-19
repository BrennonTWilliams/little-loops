---
discovered_commit: 7239f57347ee03db42f2029666eda6b506a448a9
discovered_branch: main
discovered_date: 2026-09-19T03:54:01Z
discovered_by: manual-investigation
status: done
completed_at: 2026-09-19T03:54:01Z
priority: P3
---

# BUG-3508: `/ll:advise` consult fails on claude-code host — verdict schema dropped and `--host` unvalidated

## Summary

A Codex session running `/ll:advise` (Fable 5.1 critique) hit two consecutive failures: (1) `Host 'claude' is not registered`, then (2) `Failed to parse LLM response: Expecting value: line 1 column 1 (char 0)` after retrying with `claude-code` and an explicit model ID. Both are defects in little-loops, not the model or the Codex host.

## Current Behavior

1. `ll-advise --host claude` stored the string verbatim in `config.advisor.host`; the consult unit was reserved (`record_consult`) before `resolve_host_named` rejected the name. `claude` is only the binary name — the registry key is `claude-code`. No skill/doc text listed valid `--host` values.
2. `advisor.consult()` called `run_blocking_json(...)` without `schema=`. `ClaudeCodeRunner.build_blocking_json` discards `json_schema` (`_ = json_schema`), and `--json-schema` is only appended by `run_blocking_json(schema=...)`. So claude-code (and Qwen, same pattern) never received the verdict schema; the model answered in prose, the envelope `result` was free text, and `json.loads` failed at char 0. The error hid the model text (`raw_preview` was the envelope head, and never surfaced anyway).

## Expected Behavior

- An unregistered/binary-name `--host` is rejected by argparse before any consult budget is spent, with the valid names listed.
- The verdict schema reaches every structured-output host so the advisor returns a parseable verdict.
- Parse failures show the start of what the model actually returned.

## Root Cause

- **File**: `scripts/little_loops/advisor.py`
- **Anchor**: `in function consult` (the `run_blocking_json` call) and the comment above `_VERDICT_SCHEMA`
- **Cause**: The comment claimed the schema is sent "at build time, not via `run_blocking_json(schema=...)`" — true only for codex (temp-file `--output-schema`). claude-code/qwen need the run-time inline flag. The advisor was effectively only validated against codex; `test_advisor.py` always patched `run_blocking_json`, so no test exercised the real argv or parse path.
- **Repro**: `claude --output-format json --model claude-fable-5-1 --no-session-persistence -p "..."` → exit 0, valid envelope, prose in `result`, no `structured_output`; the same call plus `--json-schema '{...}'` populates `structured_output`.

## Resolution

- `advisor.py`: pass `schema=_VERDICT_SCHEMA` to `run_blocking_json`; rewrite the stale comment; append the truncated `raw_preview` to `ConsultOutcome.error` for `BlockingJsonError`; add `claude-fable-5-1` (rank 4) to `MODEL_RANKS["claude-code"]`.
- `host_runner.py`: parse-failure `raw_preview` now uses the model's `result` text rather than the envelope head; new public `registered_host_names()` (excludes `TEST_ONLY_HOSTS`).
- `cli/advise.py`: `--host` uses `choices=registered_host_names()` so a bad name exits 2 before `consult_for_trigger`/`record_consult`.
- Docs: `skills/advise/SKILL.md` and `docs/reference/CLI.md` list valid host names (`claude-code`, not `claude`); gemini/kimi-code/qwen skill mirrors regenerated via `ll-adapt --apply`.
- Tests (`scripts/tests/test_advisor.py`): claude-code argv carries `--json-schema` while codex's does not; prose result → `failed` with model text in the error; `--host claude` rejected with no consult; updated the pinned `MODEL_RANKS` set.
- Deliberately not done: aliasing `claude`→`claude-code` in `resolve_host` (would widen `LL_HOST_CLI` globally for a one-off typo); leaving the `HostNotConfigured`→`failed` telemetry outcome unchanged.
- Verification: `scripts/tests/test_advisor.py`, `test_host_runner.py`, `test_fsm_evaluators.py` pass (671). Full unit suite: 24190 passed, 2 failed, both unrelated to these changes — `test_verify_evidence.py::TestRepoGate::test_no_new_unverifiable_evidence` (fails identically with the changes stashed; span in BUG-3484) and `test_feat3323_sse_bridge.py::TestSseBridgeFanIn` (passed in isolation; known xdist contention flake, BUG-3484).

## Impact

- **Priority**: P3 - `/ll:advise` was unusable on the claude-code host (the default advisor path) and on Qwen; wrong host names also burned budget.
- **Effort**: Small
- **Risk**: Low — `schema=` is capability-gated in `_structured_output_args`, so codex argv is unchanged.
- **Breaking Change**: No (`--host` now rejects names that already failed at resolve time).

## Labels

`bug`, `advisor`, `host-runner`, `cli`

## Status

**Resolved** | Created: 2026-09-19 | Resolved: 2026-09-19 | Priority: P3


## Session Log
- `hook:posttooluse-status-done` - 2026-09-19T03:54:33 - `09eaaf00-a050-4904-8160-69489d352a04.jsonl`
