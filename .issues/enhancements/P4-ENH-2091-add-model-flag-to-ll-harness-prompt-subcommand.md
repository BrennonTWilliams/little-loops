---
id: ENH-2091
title: Add --model flag to ll-harness prompt subcommand
type: ENH
priority: P4
status: done
captured_at: '2026-06-11T14:16:38Z'
completed_at: '2026-06-11T15:48:57Z'
discovered_date: '2026-06-11'
discovered_by: capture-issue
confidence_score: 96
outcome_confidence: 89
score_complexity: 21
score_test_coverage: 22
score_ambiguity: 24
score_change_surface: 22
labels:
- cli
- ll-harness
- enhancement
---

# ENH-2091: Add --model flag to ll-harness prompt subcommand

## Summary

Add a `--model` flag to the `ll-harness prompt` subcommand so callers can specify which Claude model to use for a one-shot evaluation. The `host_runner` already supports `model=` on both `build_streaming` and `build_blocking_json`; the harness just never threads it through.

## Current Behavior

The `ll-harness prompt` subcommand invokes Claude via `build_blocking_json` with no way to specify the model — the model is whatever the host session defaults to. Callers cannot select a cheaper or more capable model for a given evaluation without wrapping the call in a separate script.

## Expected Behavior

`ll-harness prompt` accepts an optional `--model` flag (e.g., `--model claude-haiku-4-5-20251001`) that threads the value to `build_blocking_json(prompt=..., model=...)`. When omitted, behavior is identical to today (`model=None`, host default). The flag is absent from `skill`, `cmd`, and `mcp` subparsers.

## Motivation

The `prompt` subcommand invokes Claude directly via `build_blocking_json`. Callers running cost-sensitive or thoroughness-sensitive evaluations need to pick the model explicitly—haiku for cheap smoke tests, opus for high-stakes semantic checks—without having to wrap the call in a separate script. The other three subcommands (`skill`, `cmd`, `mcp`) don't benefit: `skill` runs inside a host session that owns its own model selection, and `cmd`/`mcp` don't call Claude at all, so the flag should live on `prompt` only to avoid silently-ignored global noise.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/harness.py` — add `--model` to `prompt_p` in `_build_harness_parser()` (~line 132, after `prompt_p.add_argument("target", ...)`); thread `args.model` into `cmd_prompt()` at the `build_blocking_json` call (~line 334)

### Dependent Files (Read-only / No Change Expected)
- `scripts/little_loops/host_runner.py` — `HostRunner` protocol and `ClaudeCodeRunner.build_blocking_json()` (lines 190–303) already accept `model: str | None = None` — no changes needed

### Tests
- `scripts/tests/test_cli_harness.py` — `TestParser` class (~line 80) and `TestCmdPrompt` class (~line 425) are the two classes to extend; `_make_namespace()` helper (~line 45) may need `model=None` as a default kwarg

### Similar Patterns
- `scripts/little_loops/cli/harness.py:111–119` — `mcp_p.add_argument("--args", ...)` is a subparser-only flag in the same position; `--model` on `prompt_p` follows the same structure
- `scripts/little_loops/session_store.py:1354` — `build_blocking_json(prompt=prompt, model=model)` is the exact call pattern to follow in `cmd_prompt()`
- `scripts/little_loops/cli/loop/__init__.py:138` — `run_parser.add_argument("--llm-model", ...)` is another run-subparser-only model flag example

### Documentation
- `docs/reference/CLI.md` — `ll-harness prompt` flag table (~lines 158–193) may need `--model` added

## Implementation Steps

1. In `_build_harness_parser()` (`scripts/little_loops/cli/harness.py`, ~line 132), add `--model` to `prompt_p` only — after `prompt_p.add_argument("target", ...)` and before `_add_evaluator_flags(prompt_p)`:
   ```python
   prompt_p.add_argument("--model", default=None, help="Override Claude model (e.g. claude-haiku-4-5-20251001)")
   ```
2. In `cmd_prompt()` (~line 334), thread `args.model` into the `build_blocking_json` call (follow `session_store.py:1354` as the reference pattern):
   ```python
   inv = resolve_host().build_blocking_json(prompt=args.target, model=args.model)
   ```
3. Add tests in `scripts/tests/test_cli_harness.py` following existing patterns:
   - In `TestParser`: add `test_prompt_subparser_with_model` (parse `["prompt", "...", "--model", "claude-haiku-4-5-20251001"]`, assert `args.model == "claude-haiku-4-5-20251001"`) and `test_prompt_model_defaults_none` (parse without `--model`, assert `args.model is None`)
   - In `TestCmdPrompt`: extend `test_prompt_sends_request` or add `test_prompt_threads_model` — update `fake_build_blocking_json` signature to capture `model` kwarg and assert it matches the passed value; add a no-model regression test asserting `model=None` when flag omitted
   - Pattern reference: `TestCmdPrompt.test_prompt_sends_request` (~line 428) uses a `FakeRunner` with `fake_build_blocking_json(*, prompt, **_)` — extend `**_` to explicit `model: str | None = None` to capture the value

## Acceptance Criteria

- `ll-harness prompt "What is 2+2?" --model claude-haiku-4-5-20251001 --semantic "response contains a number"` exits 0
- `--model` flag is absent from `skill`, `cmd`, and `mcp` subparsers
- Existing harness tests continue to pass

## Impact

- **Priority**: P4 - Low; convenience feature, not blocking any workflow
- **Effort**: Small - Two lines of production code plus tests; all wiring exists in `host_runner`
- **Risk**: Low - Purely additive flag; existing callers omit it and behavior is unchanged (`model=None`)
- **Breaking Change**: No

## Out of Scope

- Adding `--model` to `skill`, `cmd`, or `mcp` subcommands
- Model validation / allowed-values list (host_runner handles passthrough)

## Status

open


## Session Log
- `/ll:ready-issue` - 2026-06-11T15:45:31 - `36182a5f-2f9a-495b-b44b-0974c7521a84.jsonl`
- `/ll:refine-issue` - 2026-06-11T14:42:49 - `1b6eda93-645a-493c-98d9-14262e8fd598.jsonl`
- `/ll:confidence-check` - 2026-06-11T00:00:00Z - `e6f2a3ec-7fc9-4c7b-bd1d-15bc5e7ece6f.jsonl`
