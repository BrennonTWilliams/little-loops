---
id: ENH-1529
title: Expose sandbox_mode parameter on CodexRunner build methods
priority: P4
type: ENH
status: open
captured_at: '2026-05-16T21:26:07Z'
discovered_date: '2026-05-16'
discovered_by: capture-issue
decision_needed: false
parent: EPIC-1463
relates_to:
- FEAT-1465
- FEAT-1462
confidence_score: 95
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
milestone: refined-ready
---

# ENH-1529: Expose sandbox_mode parameter on CodexRunner build methods

## Summary

`CodexRunner` currently hardcodes `--dangerously-bypass-approvals-and-sandbox` in every
`build_*` method, giving callers no way to request a more constrained Codex execution.
Expose a `sandbox_mode` parameter so automation code can choose between `off` (current
default), `read-only`, `write-to-cwd`, and `network` without reaching around the runner
abstraction.

## Current Behavior

All four `CodexRunner` build methods (`build_streaming`, `build_blocking_json`,
`build_detached`, `build_version_check`) unconditionally append
`--dangerously-bypass-approvals-and-sandbox` to the `codex exec` invocation.

When callers pass `tools=["Read", "Grep"]` hoping to constrain execution, the runner
emits a `CapabilityNotSupported` warning and drops the parameter — but still runs with
zero sandboxing.

## Expected Behavior

`build_streaming` (and the other relevant build methods) accept an optional
`sandbox_mode: str | None = None` parameter:

- `None` (default) → `--dangerously-bypass-approvals-and-sandbox` (current behavior, no regression)
- `"off"` → same as `None` (explicit alias)
- `"read-only"` → omit `--dangerously-bypass-approvals-and-sandbox`; append `--sandbox read-only`
- `"write-to-cwd"` → omit `--dangerously-bypass-approvals-and-sandbox`; append `--sandbox write-to-cwd`
- `"network"` → omit `--dangerously-bypass-approvals-and-sandbox`; append `--sandbox network`

Invalid values raise `ValueError`. The existing `tools` warning message is updated to
suggest `sandbox_mode` as the Codex-native alternative.

## Motivation

The `--tools` allowlist gap is well-documented (`host_runner.py:369-375`), but the
current workaround is all-or-nothing: either full unrestricted access or don't use Codex.
Surfacing Codex's own sandbox modes through the standard runner API lets callers express
the intent ("restrict file writes") in the abstraction layer rather than bypassing it.

## Proposed Solution

1. Add `sandbox_mode: str | None = None` to `build_streaming`, `build_blocking_json`,
   and `build_detached` signatures in `CodexRunner`.
2. Replace the hardcoded `--dangerously-bypass-approvals-and-sandbox` with a helper
   `_sandbox_args(sandbox_mode)` that returns the appropriate flag(s).
3. Update the `tools` warning to include: `"Use sandbox_mode='read-only' or 'write-to-cwd' for constrained Codex execution."`
4. Update `HostCapabilities` / `describe_capabilities` to note partial tool-constraint
   support via sandbox modes.
5. Add `sandbox_mode` tests to `test_host_runner.py`.

## Integration Map

### Files to Modify
- `scripts/little_loops/host_runner.py` — `CodexRunner.build_streaming`, `build_blocking_json`, `build_detached`; new `_sandbox_args` static helper; updated `tools` warning text; `describe_capabilities` note for `tool_allowlist`

### Dependent Files (Callers/Importers)
- `ll-auto`, `ll-parallel`, `ll-sprint` — all use default path (`sandbox_mode=None`); no caller changes required unless constrained execution is desired

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/subprocess_utils.py` — `run_claude_command()` calls `build_streaming`; no change needed (default `None` path) [Agent 1 finding]
- `scripts/little_loops/fsm/evaluators.py` — `evaluate_llm_structured()` calls `build_blocking_json`; no change needed (default `None` path) [Agent 1 finding]
- `scripts/little_loops/fsm/handoff_handler.py` — `HandoffHandler._spawn_continuation()` calls `build_streaming` and `build_detached`; no change needed (default `None` path) [Agent 1 finding]
- `scripts/little_loops/parallel/worker_pool.py` — `WorkerPool` calls `build_streaming`; no change needed (default `None` path) [Agent 1 finding]

### Similar Patterns
- `ClaudeRunner` / other runner subclasses in `host_runner.py` — verify no equivalent sandboxing plumbing needed

### Tests
- `scripts/tests/test_host_runner.py` — new parametrized tests for each `sandbox_mode` value (`None`, `"off"`, `"read-only"`, `"workspace-write"`, `"danger-full-access"`) and the invalid-value `ValueError` path; cover all three build methods

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_host_runner.py::TestCodexRunner::test_build_streaming_emits_warning_for_tools` — update `match="tool"` to also assert on new `sandbox_mode=` hint text in the warning; won't break but should validate the new suggestion [Agent 3 finding]
- `scripts/tests/test_host_runner.py::TestDescribeCapabilities` — add test for new `sandbox_mode` `CapabilityEntry` with `status="full"`, following the `by_name = {e.name: e for e in report.capabilities}` pattern in `test_codex_runner_agent_select_unsupported` [Agent 3 finding]
- `scripts/tests/test_enh1495_doc_wiring.py` — asserts `"CapabilityNotSupported"` and `"Current Limitations"` in `docs/codex/usage.md`; must still pass after updating the `--tools` section [Agent 2 finding]
- `scripts/tests/test_feat1462_doc_wiring.py` — asserts `describe_capabilities` is documented in `docs/reference/API.md`; must still pass after updating the Protocol signatures section [Agent 1 finding]

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md` — update `tool_allowlist` row in Codex capability table
- `thoughts/research/codex-headless-invocation.md` — flag translation source of truth; verify accuracy after change

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — update `HostRunner` Protocol code block with `sandbox_mode` parameter on `build_streaming`, `build_blocking_json`, `build_detached`; update CodexRunner table row description to reflect partial tool-constraint support [Agent 2 finding]
- `docs/codex/usage.md` — update `### --tools (tool allowlist / sandbox modes)` section; replace "limitation is total" framing with description of `sandbox_mode=` as the recommended mechanism for constrained execution [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Exact flag locations (`host_runner.py`):**
- `build_streaming` — line 435; flag at line 461 inside `args += [...]` block (easy to replace with `_sandbox_args()` call)
- `build_blocking_json` — line 487; flag at line 496 inside a **list literal** (lines 494–499); the entire literal must be refactored into dynamic assembly before threading `sandbox_mode`
- `build_detached` — line 530; flag at line 533 inside a **list literal** (lines 531–536) that also includes `prompt` as its last element; same refactoring needed
- `build_version_check` — line 522; no sandbox flag (no change required, confirmed)
- `describe_capabilities` — line 544; `tool_allowlist` entry at line 565; no `sandbox_mode` capability entry today

**Tools warning (actual location):** lines 448–455 in `build_streaming`. Issue Motivation section references `host_runner.py:369–375` — those lines are in the class docstring. The actual `CapabilityNotSupported` warning for `tools` is at **line 448**. Current message: `"tool access is controlled via --sandbox mode."` — the update should also reference the Python `sandbox_mode=` parameter.

**Snapshot test impact:** `test_codex_runner_flag_translation` (`test_host_runner.py:200`) asserts the exact `[binary, *args]` list. The default `sandbox_mode=None` case must continue to emit `--dangerously-bypass-approvals-and-sandbox`, so this existing test must still pass unchanged. New parametrized tests should cover each explicit mode value.

**`build_blocking_json` / `build_detached` refactoring pattern:** These two methods use single list literals; `build_streaming` already uses a dynamic pattern (`args: list[str] = ["exec"]` then `args += [...]`). Apply the same dynamic construction pattern before inserting `_sandbox_args()`.

**CRITICAL — Sandbox enum value mismatch:** The Proposed Solution names `"write-to-cwd"` and `"network"` as `sandbox_mode` values, but `thoughts/research/codex-headless-invocation.md:54–60` shows the actual Codex `--sandbox` enum is: `read-only`, `workspace-write`, `danger-full-access`. There is no `write-to-cwd` or `network` value. The implementer must use the real CLI enum names:
- `"read-only"` → `--sandbox read-only` ✓ (matches issue)
- `"workspace-write"` → `--sandbox workspace-write` (issue says `write-to-cwd` — wrong)
- `"danger-full-access"` → `--sandbox danger-full-access` (issue says `network` — wrong; note this is semantically equivalent to `--dangerously-bypass-approvals-and-sandbox`)
- Update `_sandbox_args()` and the `ValueError` message to use these three correct values.

**`describe_capabilities` pattern:** The established pattern for adding a new `CapabilityEntry` (from `test_host_runner.py:TestDescribeCapabilities`): `by_name = {e.name: e for e in report.capabilities}` then assert `by_name["<name>"].status == "full" | "partial" | "unsupported"`. A new `sandbox_mode` capability entry should use `"full"` status with a note listing the three valid mode values.

**Test patterns to follow** (`test_host_runner.py`):
- Snapshot test: `assert [invocation.binary, *invocation.args] == [...]` (line 203)
- Warning test: `with pytest.warns(CapabilityNotSupported, match="<substring>"):` (line 229)
- Parametrize: `@pytest.mark.parametrize(("mode", "expected_flag"), [("read-only", "--sandbox"), ...])` following `test_fsm_evaluators.py:49` style
- `ValueError` test: `with pytest.raises(ValueError, match="<substring>"):` following project convention

## Implementation Steps

1. Add `_sandbox_args(sandbox_mode: str | None) -> list[str]` as a static method or
   module-level helper in `host_runner.py`
2. Thread `sandbox_mode` through the three build methods, replacing the hardcoded flag
3. Update the `CapabilityNotSupported` warning message for `tools`
4. Update `describe_capabilities` note for `tool_allowlist`
5. Write tests; run `python -m pytest scripts/tests/test_host_runner.py`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `docs/reference/API.md` — add `sandbox_mode` parameter to `HostRunner` Protocol signature display; update CodexRunner table row description
7. Update `docs/codex/usage.md` — revise `### --tools (tool allowlist / sandbox modes)` section to describe `sandbox_mode=` as the recommended mechanism for constrained Codex execution
8. Run `python -m pytest scripts/tests/test_enh1495_doc_wiring.py scripts/tests/test_feat1462_doc_wiring.py` to verify doc-wiring tests still pass after doc updates

## API/Interface

```python
# CodexRunner — updated signatures
def build_streaming(
    self,
    prompt: str,
    ...,
    sandbox_mode: str | None = None,
    # None / "off" → --dangerously-bypass-approvals-and-sandbox (current default)
    # "read-only" | "write-to-cwd" | "network" → --sandbox <mode>
    # Other values raise ValueError
) -> HostInvocation: ...

def build_blocking_json(self, ..., sandbox_mode: str | None = None) -> HostInvocation: ...
def build_detached(self, ..., sandbox_mode: str | None = None) -> HostInvocation: ...

# New private helper
@staticmethod
def _sandbox_args(sandbox_mode: str | None) -> list[str]: ...
```

## Scope Boundaries

- **In scope**: `sandbox_mode` parameter on `build_streaming`, `build_blocking_json`, `build_detached`; `_sandbox_args` helper; `tools` warning message update; `describe_capabilities` / `HOST_COMPATIBILITY.md` update; parametrized tests for all valid and invalid mode values
- **Out of scope**: `build_version_check` (not an execution method; sandboxing not applicable); updating existing callers (`ll-auto`, `ll-parallel`, `ll-sprint` — all use the default path); adding new Codex sandbox modes beyond the four documented (`off`, `read-only`, `write-to-cwd`, `network`); exposing `sandbox_mode` on `ClaudeRunner` or other runner subclasses

## Impact

- **Priority**: P4 — ergonomic improvement; no blockers; callers can continue with default behavior
- **Effort**: Small — isolated static helper + parameter threading across three methods; well-defined change surface
- **Risk**: Low — default (`None`) preserves existing behavior exactly; no callers pass `tools` today
- **Breaking Change**: No — `sandbox_mode` is additive with a default that matches current behavior
- **Scope**: `host_runner.py` only; no callers currently pass `tools` to `CodexRunner`
- **Callers**: `ll-auto`, `ll-parallel`, `ll-sprint` all use the default path; no
  changes needed unless a caller wants constrained execution

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/reference/HOST_COMPATIBILITY.md` | Codex capability table; update `tool_allowlist` row |
| `thoughts/research/codex-headless-invocation.md` | Flag translation source of truth |
| `scripts/tests/test_host_runner.py` | Existing test surface to extend |

## Labels

`codex`, `host-runner`, `sandbox`

## Verification Notes

_Added by `/ll:verify-issues` on 2026-06-03_

**Verdict: NEEDS_UPDATE** — Proposed Solution, API interface, and Scope Boundaries sections still reference incorrect Codex sandbox enum values (`write-to-cwd`, `network`). Correct values are `workspace-write` and `danger-full-access`. The Codebase Research section already documents the correct values — the Proposed Solution must be updated to match before implementation.

## Status

- [ ] Implementation
- [ ] Tests pass
- [ ] `describe_capabilities` updated
- [ ] `HOST_COMPATIBILITY.md` updated

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-18): This issue modifies `host_runner.py` in the `CodexRunner` region (lines 343–581) and adds a new `_sandbox_args()` module-level helper. FEAT-1480 also modifies `host_runner.py` to wire `PiRunner` (lines 653+). The two changes target different class regions and are non-overlapping, but landing both PRs simultaneously can produce near-miss merge conflicts during rebase. Sequence or merge these PRs deliberately — review both diff hunks together before landing.

---

## Session Log
- `/ll:verify-issues` - 2026-06-04T22:14:36 - `ab906855-95d7-4c4f-93f3-78db8cba1111.jsonl`
- `/ll:verify-issues` - 2026-06-04T04:22:06 - `94e89e68-ddb3-448e-a123-eae4ee9ba582.jsonl`
- `/ll:verify-issues` - 2026-06-03T22:42:44 - `25083174-f806-4589-a206-0f8b53978497.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:34 - `a5f82118-5be7-4fc3-afac-e29effcffd8b.jsonl`
- `/ll:verify-issues` - 2026-06-01T14:29:19 - `f3a091ba-2869-499e-9de4-7f5c8ca96083.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:16 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:ready-issue` - 2026-05-24T17:50:06 - `a0e276a3-13b8-43b1-8581-1cb2cbdbf771.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-18T05:05:17 - `16717e5e-bfe4-4e7f-8d36-177b4b791f2d.jsonl`
- `/ll:confidence-check` - 2026-05-16T22:30:00 - `9b12ed97-216f-4ef4-a15b-b3a885a9ca71.jsonl`
- `/ll:wire-issue` - 2026-05-16T22:08:58 - `2f37cba0-e05a-4523-b0f7-0e74784e29ae.jsonl`
- `/ll:refine-issue` - 2026-05-16T21:42:51 - `201cbae4-355e-4f65-a0aa-66b54b7cd3ee.jsonl`
- `/ll:format-issue` - 2026-05-16T21:31:54 - `93cfb225-d34e-47d5-a384-898aac6f69b3.jsonl`
- `/ll:capture-issue` - 2026-05-16T21:26:07Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3c91b1bb-8b36-420d-bb06-e3e6a03f08a4.jsonl`

**Update 2026-06-04**: Confirmed still NEEDS_UPDATE. The Proposed Solution (lines 66-74), API/Interface code block (lines 163-181), and Scope Boundaries (lines 183-187) still reference incorrect Codex sandbox enum values (`write-to-cwd`, `network`). Correct values per `thoughts/research/codex-headless-invocation.md:54-60` are `workspace-write` and `danger-full-access`. The Codebase Research section (lines 130-134) correctly documents the discrepancy but the proposed solution sections have not been corrected.
