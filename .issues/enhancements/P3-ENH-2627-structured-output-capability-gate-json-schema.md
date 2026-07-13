---
id: ENH-2627
title: Gate --json-schema on a structured_output host capability flag
type: ENH
priority: P3
status: open
labels:
- fsm
- evaluators
- host-runner
- host-portability
- captured
captured_at: '2026-07-13T06:46:00Z'
discovered_date: '2026-07-13'
discovered_by: capture-issue
relates_to: [BUG-2626]
---

# ENH-2627: Gate --json-schema on a structured_output host capability flag

## Summary

Add a `structured_output` capability flag to `HostCapabilities` and have the FSM
LLM evaluator only append `--json-schema` when the active host actually honors it.
This is the cleaner long-term design behind BUG-2626, where a non-Anthropic
backend (MiniMax-M3 reached through the `claude` CLI) ignored `--json-schema` and
returned the verdict as `<StructuredOutput>` tags, spuriously failing loops.
BUG-2626 shipped a tolerant tag-parsing fallback as the interim mitigation; this
enhancement makes the flag decision explicit and observable rather than relying on
downstream recovery.

## Current Behavior

`evaluate_llm_structured` (`scripts/little_loops/fsm/evaluators.py`) uncondition-
ally appends `--json-schema <schema>` to every evaluator invocation:

```python
args = list(invocation.args) + [
    "--json-schema",
    json.dumps(effective_schema),
    "--no-session-persistence",
]
```

`HostCapabilities` (`scripts/little_loops/host_runner.py`) currently exposes only
`streaming`, `permission_skip`, `agent_select`, and `tool_allowlist` — there is no
flag describing whether a host enforces schema-constrained structured output. So
the evaluator sends the flag to every host and hopes for a populated
`structured_output` envelope field. Against hosts that ignore it, the response
degrades to tag- or prose-format text in `.result`, which BUG-2626's fallback now
rescues but which is invisible in `ll-doctor`.

## Expected Behavior

- `HostCapabilities` carries a `structured_output: bool` flag; each `HostRunner`
  sets it truthfully (Anthropic `claude` → `True`; Codex → per ENH-1530 temp-file
  bridge; hosts with no schema enforcement → `False`).
- `evaluate_llm_structured` reads the capability off the resolved
  `HostInvocation.capabilities` and appends `--json-schema` only when
  `structured_output` is `True`. When `False`, it skips the flag and relies on the
  prompt-and-parse path (the tolerant parser from BUG-2626 stays as the safety net).
- `ll-doctor` surfaces the flag in its capability table so users can see at a
  glance whether their configured host enforces structured output.

## Motivation

The interim fix makes loops *work* on non-Anthropic hosts, but the flag is still
sent blindly and the mismatch is silent. Gating on a real capability (1) stops
sending an unsupported flag that some CLIs may warn on or reject, (2) makes host
behavior legible via `ll-doctor`, and (3) aligns with the project's host-
abstraction rule that call sites branch on `HostInvocation.capabilities` rather
than assume Anthropic-only features. It also composes with ENH-1530's Codex schema
bridge — both are about honest per-host structured-output support.

## API / Interface

- `HostCapabilities` gains `structured_output: bool = False`.
- Each `HostRunner.capabilities` / `describe_capabilities()` reports it.
- No public signature change to `evaluate_llm_structured`; it branches internally
  on `invocation.capabilities.structured_output`.

## Implementation Steps

1. Add `structured_output: bool = False` to the `HostCapabilities` dataclass and
   set it per runner (`ClaudeRunner` → `True`; others per their real support).
2. Add a `CapabilityEntry` for it in each runner's `describe_capabilities()` so
   `ll-doctor` renders it.
3. In `evaluate_llm_structured`, conditionally append `--json-schema` based on
   `invocation.capabilities.structured_output`; when disabled, keep the prompt
   asking for the default schema shape and rely on the existing parse path
   (JSON → `_extract_tagged_structured_output` fallback).
4. Do the same for the other `--json-schema` call sites in `evaluators.py`
   (blind comparator and the third site) for consistency.
5. Tests: assert the flag is present for a structured-output-capable host and
   absent for one with `structured_output=False`; assert `ll-doctor` lists the new
   capability.

## Acceptance Criteria

- [ ] `HostCapabilities.structured_output` exists and is set truthfully per host.
- [ ] `evaluate_llm_structured` appends `--json-schema` only when the capability is
      `True`; the BUG-2626 tag fallback still parses responses when it is `False`.
- [ ] `ll-doctor` shows the `structured_output` capability with ✓/✗ per host.
- [ ] Tests cover both the flag-present and flag-absent branches.
- [ ] `python -m pytest scripts/tests/` green; `ruff`/`mypy` clean.

## Impact

Turns the silent, host-blind `--json-schema` send into an explicit,
capability-gated decision surfaced in `ll-doctor`, hardening FSM evaluation across
all non-Anthropic hosts while keeping BUG-2626's parser as a defensive fallback.

## Scope Boundaries

In scope: the `structured_output` capability flag, its per-runner values, the
`ll-doctor` surface, and gating the `--json-schema` append in `evaluators.py`.

Out of scope: changing the tolerant tag-parsing fallback shipped in BUG-2626 (it
stays as the safety net), the Codex temp-file schema bridge (ENH-1530, already
done), and any change to the default LLM schema or evidence contract (ENH-2342).

## Status

- **State**: open
- **Blocking**: none (BUG-2626 mitigation already ships)

## Session Log
- `/ll:capture-issue` - 2026-07-13T06:46:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7fbaa27f-176e-40cb-af35-0e12a49942b6.jsonl`
