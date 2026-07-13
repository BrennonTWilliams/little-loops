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
relates_to:
- BUG-2626
decision_needed: false
confidence_score: 98
outcome_confidence: 83
score_complexity: 20
score_test_coverage: 23
score_ambiguity: 22
score_change_surface: 18
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

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify

- `scripts/little_loops/host_runner.py` — add `structured_output: bool = False` to
  the `HostCapabilities` frozen dataclass (`host_runner.py:77-89`), then set it per
  runner in each class-level `capabilities = HostCapabilities(...)`:
  - `ClaudeCodeRunner` (`:226-229`), `CodexRunner` (`:395-398`),
    `GeminiRunner` (`:798-802`), `OmpRunner` (`:987-992`),
    `OpenCodeRunner` (`:641`, bare `HostCapabilities()`), `PiRunner` (`:713`, bare).
  - Add a `CapabilityEntry("structured_output", ...)` to each runner's
    `describe_capabilities()` return (`ClaudeCodeRunner.describe_capabilities`
    `:333-350`; `CodexRunner` `:585-625`; `GeminiRunner` `:927-955`;
    `OmpRunner` after `:1057`; `OpenCodeRunner` `:685-697`; `PiRunner` `:757-769`).
    Note: a `CapabilityEntry("json_schema", ...)` **already exists** per runner —
    see the decision point below on whether to reuse/rename it vs. add a new entry.
- `scripts/little_loops/fsm/evaluators.py` — gate the `--json-schema` append on
  `invocation.capabilities.structured_output` at all three sites:
  - `evaluate_llm_structured` (`:1086-1089`)
  - `evaluate_blind_comparator` (`:1280-1284`)
  - `evaluate_contract` (`:1533-1536`)

### Dependent / Related Files (out of the issue's stated scope — flag for decision)

- `scripts/little_loops/cli/issues/decisions.py:775-779` — a **fourth** unconditional
  `--json-schema` append (decisions-sync extraction via `_EXTRACTION_SCHEMA`) that the
  issue's Scope Boundaries (which names only `evaluators.py`) does not cover. Left
  ungated, it stays host-blind. Decide: include for consistency, or explicitly defer.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/action.py` — `cmd_capabilities()` (`:152`) is a **second
  render surface** for the capability report (parallel to `ll-doctor`): it serializes
  `runner.describe_capabilities()` to JSON/text with no hardcoded capability list, so it
  auto-picks-up the new `structured_output` `CapabilityEntry` once each runner's
  `describe_capabilities()` is updated. No code change needed, but its **test differs**
  from `ll-doctor`'s (see Tests) — the issue only listed `test_cli_doctor.py`. [Agent 1/2 finding]
- `scripts/little_loops/cli/doctor.py` — `_print_report()` / `main_doctor()` (`:82-89`,
  `:142`) iterate `report.capabilities` generically by `cap.name/status/note`; **no code
  change required**. Note: the exit-code check `return 0 if not any(c.status ==
  "unsupported" ...)` already trips on the existing `json_schema` `"unsupported"` entry for
  `ClaudeCodeRunner`/`GeminiRunner`, so adding `structured_output` introduces no new exit
  behavior — but confirm the new entry's status doesn't add a *new* `"unsupported"` host. [Agent 2 finding]
- `scripts/little_loops/fsm/executor.py` — calls `evaluate_llm_structured()` (`:1744`) and
  `evaluate_blind_comparator()` (`:1979`); consumer of the gated sites, no signature change,
  no edit needed (confirms the internal-branch design is caller-safe). [Agent 1 finding]
- `scripts/little_loops/cli/harness.py` — imports `evaluate_llm_structured` (`:18`) and calls
  `resolve_host().build_blocking_json()` (`:384`); consumer only, no edit needed. [Agent 1 finding]

### Similar Patterns (model after these)

- Conditional args-list extend keyed on a schema check:
  `CodexRunner.build_blocking_json` `if json_schema is not None:` (`host_runner.py:545-552`)
  — same "check a condition, conditionally extend `args`" shape, keyed on
  `invocation.capabilities.structured_output` instead.
- No `invocation.capabilities.<flag>` call-site branch exists anywhere yet
  (`grep '\.capabilities\.\w+'` is empty) — this issue introduces the first one.

### Tests

- `scripts/tests/test_host_runner.py` — per-host flag assertions follow
  `TestCodexRunner.test_capabilities_disable_agent_and_tools` (`:527-532`);
  `describe_capabilities()` status assertions follow `TestDescribeCapabilities`
  (`:1014-1120`), e.g. `by_name["structured_output"].status == "full"`.
- `scripts/tests/test_cli_doctor.py` — `ll-doctor` output/exit assertions follow
  `test_exit_one_when_critical_capability_missing` (`:62-84`); JSON-shape at `:250-276`.
- `scripts/tests/test_fsm_evaluators.py` — flag-present/flag-absent branches; the
  BUG-2626 fallback tests live in `TestTaggedStructuredOutputFallback` (`:1156-1245`).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_action.py` — **missing from the issue.** Tests `cmd_capabilities()` /
  `ll-action capabilities` (import `:17`, `HostCapabilities` import `:22`, cases `:359-418`).
  Since `ll-action capabilities` is a second render surface for the capability report, add a
  `structured_output`-row assertion here too, not only in `test_cli_doctor.py`. [Agent 1/3 finding]
- `scripts/tests/test_host_runner.py` — the two flag-check patterns are: bool assertion after
  `TestCodexRunner.test_capabilities_disable_agent_and_tools` (`:527-532`), and
  `by_name["structured_output"].status` after the existing `by_name["json_schema"]` lines
  (`:1049/:1077/:1089`) — added alongside, changing zero existing `json_schema` assertions
  (consistent with the Option A decision). [Agent 3 finding]
- `scripts/tests/test_fsm_evaluators.py` — the existing `--json-schema`-present assertions
  (`:928-930` in `.test_custom_schema`, `:1117-1119` in `.test_default_values_used`) do **not**
  mock `resolve_host()` — they resolve the real `ClaudeCodeRunner` in test env. They stay green
  **only if** `ClaudeCodeRunner.structured_output=True`. The new flag-absent test must mock
  `resolve_host()` to return a fake `HostInvocation` with `capabilities.structured_output=False`
  — **new test infrastructure**, no existing test in this file mocks `resolve_host()`. [Agent 3 finding]
- Note: `test_cli_doctor.py` tests use hand-built `CapabilityReport` fixtures (`:62-84`, `:249-277`),
  so adding a capability to real runners does **not** break their count assertions. [Agent 3 finding]

### Documentation

- `docs/reference/API.md` — `HostCapabilities` section (`:7531-7565`) enumerates the
  public flag surface; add `structured_output`.
- `docs/reference/HOST_COMPATIBILITY.md` — per-host capability matrix.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — the `ll-doctor` section **enumerates the capability list
  explicitly** ("one `CapabilityEntry` per capability (streaming, permission skip, agent
  selection, tool allowlist)"); if kept exhaustive, append `structured_output`. [Agent 2 finding]
- `docs/codex/usage.md` — the `### json_schema` section claims evaluators "do not pass
  `json_schema`"; adjacent to the same capability-status vocabulary and goes stale once
  `evaluators.py` starts conditionally appending `--json-schema`. Review for consistency. [Agent 2 finding]
- **Stale inline comments/docstrings (in the primary files, but easy to miss):**
  `ClaudeCodeRunner.build_blocking_json` and `GeminiRunner.build_blocking_json` comments say the
  schema flag is "silently dropped"; the `json_schema` `CapabilityEntry` notes and
  `_extract_tagged_structured_output()` docstring in `evaluators.py` describe the *current
  unconditional* `--json-schema` behavior. Update these when gating so they don't misdescribe
  the new capability-gated path. [Agent 2 finding]

### Codebase Research Findings — decision point + risks

_Added by `/ll:refine-issue` — surfaced by codebase research, not in the original issue:_

**Decision — reconciling the new boolean flag with the existing `json_schema`
`CapabilityEntry`.** `describe_capabilities()` already reports a per-host
`CapabilityEntry("json_schema", ...)` today (`ClaudeCodeRunner` → `"unsupported"`,
note "claude CLI does not accept an inline schema flag; parameter is silently
dropped"; `CodexRunner` → `"partial"`; `GeminiRunner`/`OmpRunner` → `"unsupported"`).
This directly contradicts the issue's Expected Behavior of `ClaudeRunner →
structured_output=True`: the `claude` CLI *does* honor `--json-schema` when the
backend is Anthropic (which is exactly what `evaluate_llm_structured` relies on
today), yet the existing entry advertises it as unsupported. The two surfaces must
be reconciled, and there is more than one defensible way:

> **Selected:** Option A — reuses the proven non-mirrored bool + `CapabilityEntry` pattern (`agent_select`/`tool_allowlist` on `CodexRunner`), changes zero existing `json_schema` tests, needs no new infrastructure.

**Option A**: Keep the string-keyed `CapabilityEntry("json_schema", …)` as the
diagnostic surface and add a *separate* boolean `HostCapabilities.structured_output`
for call-site gating. Set `structured_output=True` for `ClaudeCodeRunner`/`CodexRunner`,
`False` elsewhere. Correct the stale claude `json_schema` note (or leave it) so the
two surfaces agree. Lowest churn to `ll-doctor` semantics.

**Option B**: Replace/rename the ad-hoc `json_schema` `CapabilityEntry` so
`describe_capabilities()` derives its `structured_output` entry from the new boolean
field (single source of truth), eliminating the possibility of the report and the
flag drifting apart. More invasive to each runner's `describe_capabilities()` and to
`test_host_runner.py`'s `by_name["json_schema"]` assertions, but removes the
double-bookkeeping this issue would otherwise create.

**Recommended**: Option A for v1 — smallest, most reversible change; it satisfies
every acceptance criterion without reworking the existing `json_schema` reporting or
its tests. Fold the "correct the stale claude note / dedupe" cleanup into Option B as
a fast-follow if the two-surface drift proves annoying.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-13.

**Selected**: Option A — separate boolean `HostCapabilities.structured_output` for call-site gating, keeping the existing `json_schema` `CapabilityEntry` as the diagnostic surface.

**Reasoning**: The "double bookkeeping" objection to Option A is already an accepted, tested, documented pattern in the codebase — `CodexRunner` carries `agent_select=False` alongside `CapabilityEntry("agent_select", "partial", …)` (`host_runner.py:398`, `:597-604`), with a comment explaining the intentional divergence. Option B's premise ("`describe_capabilities()` already derives status from a bool") is unsupported: every runner independently hardcodes both the bool and the status string for all four existing capabilities, so B would introduce a wholly new derivation pattern — and Codex's tri-state `"partial"` status cannot be reduced to a plain boolean, so B wouldn't even eliminate the dual-maintenance it claims to solve.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option B | 1/3 | 1/3 | 2/3 | 1/3 | 5/12 |

**Key evidence**:
- Option A: Reuses existing `HostCapabilities` bool + independent `CapabilityEntry` shape (proven by `agent_select`/`tool_allowlist`); changes zero existing `json_schema` test assertions (`test_host_runner.py:1049/1077/1089`); reuse score 3.
- Option B: No `bool→status` derivation precedent exists anywhere in `host_runner.py`; touches the dataclass, every runner's `describe_capabilities()`, and the test key names; Codex `"partial"` resists boolean reduction; reuse score 1.

**Implementation caveat (both agents flagged)**: the option blurb's "`structured_output=True` for ClaudeCodeRunner/CodexRunner" is inaccurate per actual `build_blocking_json` behavior — `ClaudeCodeRunner` silently drops the schema while relying on the Anthropic backend to honor `--json-schema`, and `CodexRunner` honors it via a temp file. Set per-runner values from real behavior, not the shorthand.

**Risk — the BUG-2626 fallback only guards one of the three sites.**
`_extract_tagged_structured_output` (`evaluators.py:111-145`) is invoked **only** from
`evaluate_llm_structured` (`:1180`, inside the `except json.JSONDecodeError`). Both
`evaluate_blind_comparator` and `evaluate_contract` parse `raw_result` with a bare
`json.loads(...)` and have **no** tag-recovery fallback. So gating those two sites to
skip `--json-schema` when `structured_output=False` would leave them with no safety
net on non-Anthropic hosts — the exact failure BUG-2626 fixed for the first site.
Implementation Step 4 should either (a) also extend the tag fallback to those two
sites, or (b) explicitly note they remain Anthropic-only until then.

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Verify `ll-action capabilities` renders the new row: `cli/action.py:cmd_capabilities()`
   iterates generically, so no code edit — but add a `structured_output` assertion in
   `scripts/tests/test_action.py` (`:359-418`), the second render surface the issue missed.
7. Add the flag-absent evaluator test with **new infrastructure**: mock `resolve_host()` to
   return a fake `HostInvocation` whose `capabilities.structured_output=False` (no existing
   test in `test_fsm_evaluators.py` mocks `resolve_host()`). Keep the existing
   `--json-schema`-present assertions (`:928-930`, `:1117-1119`) green by holding
   `ClaudeCodeRunner.structured_output=True`.
8. Update stale inline comments/docstrings describing unconditional `--json-schema` /
   "silently dropped" behavior in `host_runner.py` (`build_blocking_json` for Claude/Gemini)
   and `evaluators.py` (near the three append sites + `_extract_tagged_structured_output()`).
9. Update docs: `docs/reference/CLI.md` (ll-doctor capability enumeration) and
   `docs/codex/usage.md` (`### json_schema` staleness), in addition to API.md /
   HOST_COMPATIBILITY.md already listed.

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
- `/ll:wire-issue` - 2026-07-13T18:33:15 - `e418041f-97b9-4193-89df-c4643e9794aa.jsonl`
- `/ll:decide-issue` - 2026-07-13T18:27:04 - `4856cd4a-cd92-4d93-9617-eff1bb991f10.jsonl`
- `/ll:refine-issue` - 2026-07-13T18:02:12 - `a57eb810-b1eb-44db-8139-1f8ccc8244b0.jsonl`
- `/ll:capture-issue` - 2026-07-13T06:46:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7fbaa27f-176e-40cb-af35-0e12a49942b6.jsonl`
