---
id: BUG-2626
title: LLM evaluator spuriously fails loops on non-Anthropic hosts (tag-format structured output)
type: BUG
priority: P2
status: done
labels:
- fsm
- evaluators
- host-portability
- captured
captured_at: '2026-07-13T06:37:35Z'
discovered_date: '2026-07-13'
discovered_by: debug-loop-run
completed_at: '2026-07-13T06:37:35Z'
---

# BUG-2626: LLM evaluator spuriously fails loops on non-Anthropic hosts (tag-format structured output)

## Summary

`evaluate_llm_structured` (`scripts/little_loops/fsm/evaluators.py`) — the single
code path behind every `check_semantic` and default LLM evaluation in the FSM
engine — assumed the Anthropic-only `claude --json-schema` → `structured_output`
envelope contract. When `ll-loop`/`ll-auto`/`ll-sprint` run against a
non-Anthropic host reached through the same CLI (e.g. a **MiniMax-M3** backend),
the host ignores `--json-schema` and returns the verdict as `<StructuredOutput>`
tags inside the envelope's `result` string. The parser called `json.loads()` on
that tag string, threw `Expecting value: line 1 column 1 (char 0)`, coerced the
verdict to `error`, and routed the loop to its failure terminal — even when the
model's actual verdict was `yes`.

## Current Behavior (before fix)

Running `ll-loop run html-website-generator "..."` in a project whose `claude`
CLI is pointed at MiniMax-M3 reported `failed` after 2 iterations. The generator
had produced a complete, valid 68KB `index.html`, and the evaluator LLM returned
a **passing** verdict:

```
"last_result": { "verdict": "error", "details": {
  "error": "Failed to parse LLM response: Expecting value: line 1 column 1 (char 0)",
  "raw_preview": "{\"type\":\"result\",...,\"result\":\"<StructuredOutput>\\n<verdict>yes</verdict>\\n<confidence>0.75</confidence>\\n<reason>The assi" }}
```

Route: `run_gen_eval` → `on_error: failed`. The failure was **spurious** — a
parsing bug, not an output-quality rejection. `grep -rln StructuredOutput
scripts/little_loops/` returned nothing: the tag format originates entirely from
the host CLI, and little-loops had no code to parse it.

### Severity

Not loop-specific. Every `check_semantic` and every default LLM evaluation, in
every loop, failed identically on any non-Anthropic host that doesn't honor
`--json-schema`. This matches the standing "why is the general-task FSM loop
failing in forescout" correction.

## Expected Behavior

The evaluator recovers a structured verdict host-agnostically: when the envelope
has no `structured_output` dict and `result` is not JSON, mine the verdict from
`<StructuredOutput>` tags before treating the response as an error. Anthropic
`structured_output` and JSON-in-`result` paths are unchanged; genuinely
unparseable output still errors.

## Root Cause

`evaluate_llm_structured` parse block (`evaluators.py`, the `elif raw_result:`
branch): `structured_output` absent → `raw_result = envelope.get("result")` →
non-empty string → `json.loads(raw_result)` on `"<StructuredOutput>\n<verdict>..."`
→ `JSONDecodeError` → caught → `verdict="error"`.

## Resolution

`scripts/little_loops/fsm/evaluators.py`:

- Added module-level helper `_extract_tagged_structured_output(text)` that
  regex-extracts `verdict` / `confidence` / `reason` / `evidence` from a
  `<StructuredOutput>` block (tolerant of missing wrapper, case, whitespace, and
  a ` ```json ` fence), returning the same dict shape the JSON path yields, or
  `None` when no `<verdict>` tag is present.
- Wired the fallback into the `elif raw_result:` branch: try `json.loads` first;
  on `JSONDecodeError`, call the helper; if it yields a dict, use it; otherwise
  re-raise so the existing `except` still produces the `error` + `raw_preview`
  result (genuine garbage still errors). Downstream verdict/confidence and the
  ENH-2342 evidence-coercion logic are untouched — a tag verdict lacking
  `<evidence>` is still coerced to `no`.

`scripts/tests/test_fsm_evaluators.py`: new `TestTaggedStructuredOutputFallback`
class covering (1) MiniMax-style tag envelope → `yes` @ 0.75 with reason/evidence
populated, (2) tag verdict missing `<evidence>` → coerced to `no`, (3) tags inside
a ` ```json ` fence → recovered, (4) non-tag garbage → still `error` with
`raw_preview`.

## Acceptance Criteria

- [x] A MiniMax-style envelope (`{"result":"<StructuredOutput><verdict>yes</verdict>..."}`)
      parses to `verdict == "yes"` instead of `error`.
- [x] Default-schema evidence contract still holds on the fallback path (no
      `<evidence>` → coerced to `no`).
- [x] Genuinely unparseable `result` still returns `verdict == "error"` with a
      `raw_preview` (no behavior regression).
- [x] Anthropic `structured_output`-dict path unchanged.
- [x] `python -m pytest scripts/tests/` green (14843 passed, 36 skipped);
      `ruff check`, `ruff format --check`, and `mypy` clean on the touched files.

## Impact

Fixes the failure class for every `check_semantic`/default LLM evaluation across
all loops when run against a non-Anthropic host, unblocking `ll-loop`/`ll-auto`/
`ll-sprint` on MiniMax and similar CLI-compatible backends.

## Follow-up (out of scope)

Host-capability gating — a `structured_output` flag on `HostCapabilities` +
`ll-doctor` surface so `--json-schema` is only sent to hosts that support it — is
the cleaner long-term design and is deferred. This parse fix is the interim
mitigation.


## Session Log
- `hook:posttooluse-status-done` - 2026-07-13T06:38:10 - `7fbaa27f-176e-40cb-af35-0e12a49942b6.jsonl`
