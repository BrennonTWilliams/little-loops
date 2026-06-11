---
id: ENH-2090
title: "Add --model flag to ll-harness prompt subcommand"
type: ENH
priority: P4
status: open
captured_at: "2026-06-11T14:16:38Z"
discovered_date: "2026-06-11"
discovered_by: capture-issue
---

# ENH-2090: Add --model flag to ll-harness prompt subcommand

## Summary

Add a `--model` flag to the `ll-harness prompt` subcommand so callers can specify which Claude model to use for a one-shot evaluation. The `host_runner` already supports `model=` on both `build_streaming` and `build_blocking_json`; the harness just never threads it through.

## Motivation

The `prompt` subcommand invokes Claude directly via `build_blocking_json`. Callers running cost-sensitive or thoroughness-sensitive evaluations need to pick the model explicitly—haiku for cheap smoke tests, opus for high-stakes semantic checks—without having to wrap the call in a separate script. The other three subcommands (`skill`, `cmd`, `mcp`) don't benefit: `skill` runs inside a host session that owns its own model selection, and `cmd`/`mcp` don't call Claude at all, so the flag should live on `prompt` only to avoid silently-ignored global noise.

## Implementation Steps

1. In `_build_harness_parser()` (`scripts/little_loops/cli/harness.py`), add `--model` to `prompt_p` only:
   ```python
   prompt_p.add_argument("--model", default=None, help="Override Claude model (e.g. claude-haiku-4-5-20251001)")
   ```
2. In `cmd_prompt()`, thread `args.model` into the `build_blocking_json` call:
   ```python
   inv = resolve_host().build_blocking_json(prompt=args.target, model=args.model)
   ```
3. Add a test in `scripts/tests/test_harness.py` (or the existing harness test file) verifying:
   - `--model claude-haiku-4-5-20251001` appears in the constructed invocation args
   - Omitting `--model` produces the same invocation as before (no regression)

## Acceptance Criteria

- `ll-harness prompt "What is 2+2?" --model claude-haiku-4-5-20251001 --semantic "response contains a number"` exits 0
- `--model` flag is absent from `skill`, `cmd`, and `mcp` subparsers
- Existing harness tests continue to pass

## Out of Scope

- Adding `--model` to `skill`, `cmd`, or `mcp` subcommands
- Model validation / allowed-values list (host_runner handles passthrough)

## Status

open
