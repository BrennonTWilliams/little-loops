---
id: ENH-2341
type: ENH
priority: P2
status: done
discovered_date: 2026-06-27
captured_at: '2026-06-27T05:17:49Z'
completed_at: '2026-06-30T03:59:24Z'
discovered_by: capture-issue
decision_needed: false
parent: EPIC-2149
confidence_score: 96
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-2341: Add Rubric-Gated Compaction Timing to pre_compact Hook

## Summary

Replace the current token-threshold-only trigger for `pre_compact` with a structural rubric that gates compaction on whether the current reasoning unit is genuinely closed and reducible — not on a blind token counter. Each rubric condition requires verbatim evidence from the trajectory; absence of evidence defaults to "no, don't compact yet."

## Current Behavior

`pre_compact.py` fires whenever the host's token threshold is reached, regardless of where the conversation is in its reasoning. This means compaction can interrupt mid-derivation (before a sub-task resolves), re-summarizing the same dead-end content into every summary window rather than waiting for a clean closure point.

## Expected Behavior

Before compacting, the hook evaluates a lightweight structural rubric over the recent trajectory:
1. **Closed reasoning unit** — the current sub-task has a definite resolution (not mid-derivation)
2. **Reducible to N facts** — the relevant content can be faithfully expressed in 3–5 cite-able facts
3. **Progress made** — something actually changed since the last compact
4. **Not stuck** — the agent is not in a repetitive loop on the same problem

Each condition requires a verbatim quote from the trajectory as evidence. If any condition lacks evidence it defaults to `no`, and compaction is deferred until the next check. Compaction still fires at the hard token ceiling regardless.

## Success Metrics

- Token cost per compaction window reduced by 30–70% vs. threshold-only baseline (per SELFCOMPACT research)
- Downstream task quality improves +5–18 points when rubric gates compaction
- Hard-ceiling bypass rate does not increase (rubric must not cause excessive deferral)
- All 4 rubric conditions independently testable in unit tests with clear pass/fail signal

## Motivation

SELFCOMPACT (research: `docs/research/05-26-2026-batch/`) shows that **the rubric — not the act of compacting — is where the quality gain comes from**. Fixed-interval / fixed-threshold compaction fails by firing blind: qualitative traces show it re-summarizing a dead-end shortlist into every summary window, while rubric-gated compaction waits for the lead to be corrected first. The result: 30–70% lower token cost and +5–18 points on downstream tasks, training-free.

This directly complements the existing `LCM-*` research line and the `continuation-prompt-template.md` handoff path. The rubric value is largest for weaker/open hosts (relevant to ll's multi-host story) but applies to Claude Code as well.

## Proposed Solution

Add a rubric evaluation step inside `scripts/little_loops/hooks/pre_compact.py` (the Python handler invoked by the Claude Code adapter) before deciding whether to emit the compaction payload:

```python
# scripts/little_loops/hooks/pre_compact.py

def should_compact(trajectory_excerpt: str, config: dict) -> tuple[bool, str]:
    """
    Evaluate the SELFCOMPACT rubric over the recent trajectory.
    Returns (compact_now, reason).
    Each condition requires verbatim evidence; absence → False.
    """
    rubric = {
        "closed_unit": _find_evidence(trajectory_excerpt, CLOSED_UNIT_SIGNALS),
        "reducible":   _find_evidence(trajectory_excerpt, REDUCIBLE_SIGNALS),
        "progress":    _find_evidence(trajectory_excerpt, PROGRESS_SIGNALS),
        "not_stuck":   not _find_evidence(trajectory_excerpt, STUCK_SIGNALS),
    }
    passed = all(rubric.values())
    reason = ", ".join(k for k, v in rubric.items() if not v) or "all conditions met"
    return passed, reason
```

The rubric runs as a probe appended to the hook context (not a substitution), so the KV cache is reused and the check is near-free. The existing hard-ceiling logic stays as a fallback.

**Key signals to define** (derived from trajectory text):
- **Closed unit**: phrases like "done", "completed", "fixed", resolved tool calls, explicit task summary
- **Reducible**: short recent window, few open threads, no pending tool calls
- **Progress**: diff between current and last compact checkpoint is non-empty
- **Stuck**: identical consecutive outputs, same error repeated ≥2 times

The rubric config (thresholds, signal lists) lives in `ll-config.json` under `hooks.pre_compact.rubric` so it can be tuned per-project.

## Implementation Steps

1. **Add `PreCompactRubricConfig` dataclass** — create in `scripts/little_loops/config/features.py` following `LearningTestsConfig` shape: outer class with `enabled: bool = False`, `hard_ceiling_pct: float = 0.95`; inner class with `closed_unit_signals`, `reducible_signals`, `progress_signals`, `stuck_signals` lists and `from_dict()` classmethod
2. **Add `hooks.pre_compact.rubric` to `config-schema.json`** — add a `pre_compact` property under `hooks.properties` (currently the parent block has `additionalProperties: false`, so the property must be explicitly declared); include `enabled`, `hard_ceiling_pct`, and per-condition signal array defaults
3. **Add config read + `should_compact()` to `pre_compact.py`** — import `resolve_config_path` from `little_loops.config.core`; add `_load_rubric_config(cwd)` helper following `learning_tests_gate.py:_load_lt_config()` pattern; add `_find_evidence(text, signals)` using compiled-regex approach from `session_store.py:is_correction()`; add `should_compact(trajectory_excerpt, config)` returning `tuple[bool, str]`
4. **Wire rubric into `pre_compact.handle()`** — before writing the state file: (a) read `transcript_path` from payload, tail it for a trajectory excerpt; (b) call `_load_rubric_config()`; (c) if `rubric_config.enabled`, call `should_compact(excerpt, rubric_config)` — if result is `(False, reason)` and token count is below `hard_ceiling_pct`, return early `LLHookResult(exit_code=0)` (or appropriate code per verified exit-code semantics); (d) proceed to state-write on pass or hard-ceiling
5. **Verify exit code semantics** — check `docs/claude-code/hooks-reference.md` or `docs/guides/BUILTIN_HOOKS_GUIDE.md` to confirm whether `exit_code=0` from a PreCompact hook defers compaction or allows it silently; adjust return values accordingly
6. **Add test classes to `scripts/tests/test_pre_compact.py`** — add `TestRubricGating` class covering: rubric disabled (bypass), rubric pass all conditions, rubric fail each condition individually, hard-ceiling bypass, evidence-absent → no-compact, transcript-read error (graceful degradation); follow `_event(**payload)` factory and `monkeypatch.chdir(tmp_path)` pattern from existing tests; seed config using `_write_config()` helper pattern from `test_hook_user_prompt_submit.py`
7. **Update `hooks/prompts/continuation-prompt-template.md`** — add a `### Compaction Timing` subsection under `## Template Usage Notes` noting the rubric timing policy

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. **Re-export from `scripts/little_loops/config/__init__.py`** — add `PreCompactRubricConfig` (and any inner config class) to the `from little_loops.config.features import (...)` block and to `__all__`; mandatory per project pattern for every dataclass in `features.py`
9. **Add `TestPreCompactRubricConfig` to `scripts/tests/test_config.py`** — cover `from_dict({})` defaults, each field override, and `BRConfig` round-trip; follow `TestLearningTestsConfig` template (10 methods)
10. **Add `test_hooks_pre_compact_rubric_in_schema` to `scripts/tests/test_config_schema.py`** — assert `hooks.pre_compact.rubric` is declared in `config-schema.json` with `enabled`, `hard_ceiling_pct`, and signal-array keys
11. **Update `docs/guides/BUILTIN_HOOKS_GUIDE.md`** — add rubric opt-in qualifier to `## PreCompact` prose and new config rows in `## Configuration Reference` table
12. **Update `docs/reference/CONFIGURATION.md`** — add `hooks.pre_compact.rubric` subsection under `### hooks`

## Integration Map

### Files to Modify
- `scripts/little_loops/hooks/pre_compact.py` — add `should_compact()` rubric function and wire into main handler
- `config-schema.json` — add `hooks.pre_compact.rubric` schema with signal-list and threshold defaults
- `scripts/little_loops/config/features.py` — add `PreCompactRubricConfig` dataclass (outer: `enabled: bool = False`, `hard_ceiling_pct: float = 0.95`; inner: signal-list fields and `from_dict()` classmethod); Implementation Step 1 references this file but it was absent from the list [Agent 1 finding]
- `scripts/little_loops/config/__init__.py` — add `PreCompactRubricConfig` to the `from little_loops.config.features import (...)` block and to `__all__`; every config dataclass in `features.py` follows this mandatory re-export pattern [Agent 1 + 2 finding]

### Dependent Files (Callers/Importers)
- `hooks/hooks.json` — two `matcher: "*"` `PreCompact` entries pointing to `precompact.sh`
- `hooks/adapters/claude-code/precompact.sh` — bash bridge: `echo "$INPUT" | python -m little_loops.hooks pre_compact`
- `scripts/little_loops/hooks/adapters/codex/hooks.json` — Codex `PreCompact` entry pointing to `pre-compact.sh`
- `scripts/little_loops/hooks/adapters/codex/pre-compact.sh` — sets `LL_HOOK_HOST=codex`, same Python invocation
- `hooks/adapters/opencode/index.ts` — `session.compacted` event → `spawnIntent("pre_compact", ...)` (TypeScript adapter)

### Similar Patterns
- `scripts/little_loops/hooks/session_start.py` — sibling hook handler; follow the same `resolve_config_path` pattern for config reads

### Tests
- `scripts/tests/test_pre_compact.py` — **already exists** (8 test classes for current handler); add new classes here for rubric pass, rubric fail per condition, hard-ceiling bypass, evidence-absent → no-compact. Do not create a separate file.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config.py` — add new `TestPreCompactRubricConfig` class; follows `TestLearningTestsConfig` pattern (cover `from_dict({})` defaults, each field override, nested sub-config, and `BRConfig` round-trip); this file already tests every dataclass in `features.py` [Agent 1 + 3 finding]
- `scripts/tests/test_config_schema.py` — add `test_hooks_pre_compact_rubric_in_schema` method asserting `hooks.pre_compact.rubric` is declared in `config-schema.json` with `enabled`, `hard_ceiling_pct`, and signal-array keys [Agent 2 + 3 finding]
- `scripts/tests/test_hooks_integration.py` — `TestPrecompactState.test_atomic_write_with_missing_directory` and `test_concurrent_precompact_writes` assert `returncode == 2`; safe only if rubric defaults to `enabled=False` when no config present — must be verified during implementation [Agent 3 finding]

### Documentation
- `hooks/prompts/continuation-prompt-template.md` — add a note about rubric timing policy (Implementation Step 7)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — `## PreCompact` prose ("always-on" description needs conditional qualifier); `## Configuration Reference` table needs rows for `hooks.pre_compact.rubric.enabled` and `hooks.pre_compact.rubric.hard_ceiling_pct`; `## The Lifecycle at a Glance` PreCompact row needs annotation [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` — `### hooks` section currently documents only `host` and `stale_ref_fix`; add `hooks.pre_compact.rubric` subsection with key table [Agent 2 finding]

### Configuration
- `.ll/ll-config.json` — `hooks.pre_compact.rubric` block with `hard_ceiling_pct`, signal lists, and enabled flag

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Critical: `config-schema.json` `additionalProperties: false` constraint**
The `hooks` object in `config-schema.json` (lines 1228–1244) currently only has `host` and `stale_ref_fix` properties and declares `"additionalProperties": false`. Adding `hooks.pre_compact.rubric` requires explicitly adding a `pre_compact` nested object to `hooks.properties` — the schema block won't accept unknown keys. Follow the nested object shape in the `epics.scope` block as a reference.

**`pre_compact.py` has no config read path**
Unlike `session_start.py` (line 41–96) or `learning_tests_gate.py:_load_lt_config()`, `pre_compact.py` currently does not import `resolve_config_path`. The config-read pattern to follow:
```python
from little_loops.config.core import resolve_config_path  # add to imports
# inside handle():
cwd = Path.cwd()
config_path = resolve_config_path(cwd)
rubric_cfg: dict = {}
if config_path is not None:
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        rubric_cfg = data.get("hooks", {}).get("pre_compact", {}).get("rubric", {})
    except (OSError, json.JSONDecodeError):
        pass
```

**Config dataclass pattern**
Define a `PreCompactRubricConfig` dataclass following `LearningTestsConfig` + `DiscoverabilityConfig` in `scripts/little_loops/config/features.py`. Outer class holds `enabled: bool = False`; inner holds signal lists and `hard_ceiling_pct: float = 0.95`.

**Signal detection pattern**
Follow `is_correction()` in `scripts/little_loops/session_store.py:150` — compiled module-level `re.Pattern` constants for each signal category; config-supplied signal strings are OR-joined at call time. Each `_find_evidence(text, signals)` call mirrors `is_correction(text, extra_patterns=signals)` with a text cap.

**`should_compact()` tuple return**
Follow `_verify_work_was_done()` in `scripts/little_loops/parallel/worker_pool.py:1144` for `tuple[bool, str]` shape: `(True, "")` on pass, `(False, "closed_unit, reducible")` with the failing conditions on defer.

**Trajectory excerpt source**
The hook payload carries `transcript_path` (a JSONL file path) but does NOT include transcript content. To evaluate rubric over recent trajectory, the handler must read and tail that file. Use `Path(transcript_path).read_text()` with a size cap (last N bytes or last N lines) to avoid reading large transcripts.

**Exit code semantics — VERIFY BEFORE IMPLEMENTING**
Claude Code's `PreCompact` hook treats `exit_code=2` as "inject feedback into compaction prompt" (compaction still proceeds). It is not confirmed whether `exit_code=0` from a PreCompact hook defers compaction or just silently allows it. The issue's "defer until next check" behavior must be validated against actual Claude Code PreCompact documentation before implementing. If exit_code cannot defer, the rubric can only gate whether state is preserved (exit 2 with message) vs. silently skipped (exit 0) — not whether compaction fires.

**Test config-seeding pattern**
Follow `_write_config()` helper in `scripts/tests/test_hook_user_prompt_submit.py` and config-seeding in `scripts/tests/test_hook_session_start.py:TestSessionStartConfigLoad` — write a `.ll/ll-config.json` with `{"hooks": {"pre_compact": {"rubric": {...}}}}` inside `tmp_path / ".ll"` before calling `pre_compact.handle()`.

**`continuation-prompt-template.md` update location**
The template at `hooks/prompts/continuation-prompt-template.md` has a `## Template Usage Notes` section listing trigger scenarios. The rubric timing policy note fits as a new `### Compaction Timing` callout there.

## Scope Boundaries

**In scope:**
- `should_compact()` rubric function in `pre_compact.py` with the four conditions above
- Config schema for `hooks.pre_compact.rubric` (signal lists, `hard_ceiling_pct`)
- Hard-ceiling bypass (compact regardless at ≥ `hard_ceiling_pct` of context, default 95%)
- Unit tests covering all rubric branches

**Out of scope:**
- Changing the hard token ceiling mechanism or compaction payload format
- ML-based or learned compaction decisions
- Storing full trajectory history across sessions
- Modifying how other hooks invoke or respond to compaction events

## Impact

- **Priority**: P2 — High leverage for token efficiency and post-compaction quality; not blocking, but multiplies value of the multi-host story for weaker/open hosts
- **Effort**: Medium — New `should_compact()` function + signal definitions + config schema + tests; implementation surface is well-scoped to `pre_compact.py`
- **Risk**: Low — Hard-ceiling bypass preserves existing behavior as permanent fallback; rubric is additive and never prevents compaction permanently
- **Breaking Change**: No — Defaults to existing threshold-only behavior when rubric config is absent; opt-in via `hooks.pre_compact.rubric.enabled`

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/research/05-26-2026-batch/SYNTHESIS-and-recommendations.md` | Source recommendation #1; SELFCOMPACT findings |
| `scripts/little_loops/hooks/pre_compact.py` | Primary implementation surface |
| `hooks/prompts/continuation-prompt-template.md` | Handoff template that pairs with this |
| `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` | Structural-state gating context |

## Labels

`hooks`, `compaction`, `pre-compact`, `captured`

## Status

**Open** | Created: 2026-06-27 | Priority: P2

## Resolution

Implemented `PreCompactRubricConfig` (opt-in, default disabled) that gates pre-compact state writing on four structural conditions evaluated over the recent transcript excerpt: closed reasoning unit, reducible content, measurable progress, and absence of stuck-loop signals. Exit code 0 on rubric failure defers state writing; exit 2 on pass preserves existing feedback behaviour. All signal lists are configurable via `hooks.pre_compact.rubric.signals.*` in `ll-config.json`.

**Files modified:**
- `scripts/little_loops/config/features.py` — added `RubricSignalsConfig` + `PreCompactRubricConfig` dataclasses
- `scripts/little_loops/config/__init__.py` — re-exported `PreCompactRubricConfig`
- `scripts/little_loops/hooks/pre_compact.py` — added `_load_rubric_config()`, `_find_evidence()`, `should_compact()`, wired into `handle()`
- `config-schema.json` — declared `hooks.pre_compact.rubric` schema
- `scripts/tests/test_pre_compact.py` — added `TestRubricGating` (8 tests)
- `scripts/tests/test_config.py` — added `TestPreCompactRubricConfig` (10 tests)
- `scripts/tests/test_config_schema.py` — added schema assertion test
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — added rubric qualifier + config table rows
- `docs/reference/CONFIGURATION.md` — added `hooks.pre_compact.rubric` subsection
- `hooks/prompts/continuation-prompt-template.md` — added `### Compaction Timing` note

## Session Log
- `/ll:manage-issue` - 2026-06-30T03:59:24Z - `manage-issue`
- `/ll:ready-issue` - 2026-06-30T03:38:28 - `5d7b1be5-e434-44ab-bd7c-e7f4353b60e9.jsonl`
- `/ll:confidence-check` - 2026-06-29T00:00:00Z - `4fa7b3c8-2ba9-4ece-b050-a044af097c04.jsonl`
- `/ll:wire-issue` - 2026-06-27T06:13:39 - `5c164999-cef5-4e23-b356-71ebf3af4e40.jsonl`
- `/ll:refine-issue` - 2026-06-27T05:33:04 - `15663aad-3484-4d3c-b333-946a0e331e1a.jsonl`
- `/ll:format-issue` - 2026-06-27T05:22:30 - `b1f554bc-7cd6-42a8-af86-2e0e2a418a25.jsonl`
- `/ll:capture-issue` - 2026-06-27T05:17:49Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cd21288e-7370-4e7e-8040-6f118e73e291.jsonl`
