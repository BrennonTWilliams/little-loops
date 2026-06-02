---
id: ENH-1639
type: ENH
priority: P4
status: done
captured_at: 2026-05-23 12:00:00+00:00
completed_at: 2026-05-24T14:13:35Z
discovered_date: 2026-05-23
discovered_by: capture-issue
testable: false
confidence_score: 100
outcome_confidence: 71
score_complexity: 18
score_test_coverage: 10
score_ambiguity: 18
score_change_surface: 25
implementation_order_risk: true
---

# ENH-1639: Document timeout-budget guidance for `prompt` actions doing many MCP tool calls

## Summary

The `harness-exploratory-user-eval`-style template (which imports `lib/common.yaml` from little-loops) ships with `timeout: 720` for prompt actions. When the prompt does ~10 MCP tool calls + synthesis (vision agents, playwright orchestration), 720s is too tight and the action is regularly killed mid-synthesis. Users should budget ≥1500s and consider a streaming agent.

## Current Behavior

- `loops/lib/common.yaml` ships `timeout: 720` as the default for `action_type: prompt` entries that get reused via YAML anchors.
- The `/ll:create-loop` skill's prompt-action template does not call out a higher budget when the suggested prompt includes MCP tool calls.
- `docs/reference/SCHEMA.md` (or the equivalent timeout reference) does not document that prompt + MCP synthesis can run several minutes.
- Result: users authoring loops that perform many MCP tool calls (e.g. semantic-vision checks with ~10 playwright calls + synthesis) hit the 720s timeout mid-synthesis and the action is killed without producing a verdict.

## Expected Behavior

- `loops/lib/common.yaml` includes an inline comment (or accompanying README note) explaining when 720s is too tight and recommending ≥1500s for prompt actions doing multiple MCP tool calls.
- `/ll:create-loop` defaults `timeout: 1500` (with rationale comment) whenever it scaffolds a prompt action expected to perform MCP tool calls.
- `docs/reference/SCHEMA.md` documents the budgeting guidance alongside the `timeout` field so authors discover it before hitting the timeout in practice.

## Motivation

- Repeatedly observed in `harness-exploratory-user-eval` runs: the semantic-vision check timed out at 12m every pass.
- Low-friction fix: a clear note in the README/SKILL for `lib/common.yaml` and the loop wizard's prompt-action template.

## Proposed Solution

Add a short guidance block to:

1. The `lib/common.yaml` doc/comment block (or its accompanying README) explaining the timeout budget for prompt actions.
2. The `/ll:create-loop` skill prompt template — when a `prompt` action is suggested with MCP tool calls, default to `timeout: 1500` and add a comment with the rationale.
3. `docs/reference/SCHEMA.md` (or wherever timeouts are documented) — note that prompt + MCP synthesis can run several minutes and `timeout:` should reflect that.

Suggested text:

> When `action_type: prompt` performs multiple MCP tool calls followed by synthesis (e.g. a vision agent with ~10 tool calls), allow ≥1500s; the default 720s is too tight and will cause timeouts mid-synthesis. Consider a streaming agent if you need progress visibility within the budget.

## Integration Map

### Files to Modify
- `loops/lib/common.yaml` (and any accompanying README at `loops/lib/`)
- `skills/create-loop/SKILL.md` and `skills/create-loop/loop-types.md` — scaffolding templates for harness `execute` states live in `loop-types.md` (~lines 711, 786); `SKILL.md` contains the wizard narrative
- `skills/create-loop/reference.md` — `execute` state field tables at lines 103–109 (Multi-Item variant) and 150–163 (Single-Shot variant) do not list `timeout`; `check_skill` already has a 120–300 recommendation; adding `timeout: 1500` to `loop-types.md` without updating this reference creates an undocumented field discrepancy [Wiring pass added by `/ll:wire-issue`]
- `docs/generalized-fsm-loop.md` — `## Timeouts` section (~line 1335); this is the actual schema reference (`docs/reference/SCHEMA.md` does not exist)

### Dependent Files (Callers/Importers)
- 16 loops import `lib/common.yaml` via `import: [lib/common.yaml]` (the codebase uses the FSM `fragment:` key system, not YAML anchors — `<<: *prompt` syntax does not exist anywhere)
- Key examples: `harness-single-shot.yaml`, `harness-multi-item.yaml`, `issue-refinement.yaml`, `autodev.yaml`, `recursive-refine.yaml`, `sprint-refine-and-implement.yaml`
- Find all: `grep -rn "lib/common.yaml" scripts/little_loops/loops/`

### Similar Patterns
- `scripts/little_loops/loops/lib/common.yaml` — no `timeout:` on any fragment; `llm_gate` description lists timeout as optional caller-supplied field with no guidance on what value to use
- `scripts/little_loops/loops/lib/score-plan-quality.yaml:29` — `timeout: 300`; only lib fragment carrying a numeric timeout
- `scripts/little_loops/loops/fix-quality-and-tests.yaml:73` — `timeout: 1800` on `fix-tests` state; highest per-state prompt timeout in built-in loops
- `scripts/little_loops/loops/harness-single-shot.yaml:23` — `timeout: 3600  # 1-hour wall clock limit (seconds)` — inline comment pattern to follow
- `scripts/little_loops/loops/dataset-curation.yaml:21` — `timeout: 7200  # 2-hour wall clock limit` — densest inline-comment documentation example

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1639_doc_wiring.py` — new test file to write following the established `test_enh<NNN>_doc_wiring.py` pattern (see `test_enh1115_doc_wiring.py`, `test_enh1345_doc_wiring.py`, `test_enh1557_doc_wiring.py`); assert: (1) `timeout: 1500` present in `skills/create-loop/loop-types.md`, (2) MCP timeout guidance text present in `docs/generalized-fsm-loop.md` `## Timeouts` section, (3) MCP timeout guidance text present in `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` Best Practices section [new test to write]
- `scripts/tests/test_fsm_fragments.py` — `TestCommonYamlNewFragments.test_all_common_yaml_fragments_have_description` (line ~1068) reads the real `lib/common.yaml` and asserts every fragment has a non-empty `description:`; will pass as long as the updated `llm_gate` description text is non-empty [existing — no change needed]
- `scripts/tests/test_circuit_breaker_doc_wiring.py` — `TestCreateLoopTypesWiring` asserts `circuit_breaker_enabled` and `circuit_breaker_path` are present in `loop-types.md`; adding `timeout: 1500` will not affect these assertions [existing — monitor only]

### Documentation
- `docs/generalized-fsm-loop.md` — `## Timeouts` section (~line 1335); the actual schema reference (`docs/reference/SCHEMA.md` does not exist)
- `docs/guides/LOOPS_GUIDE.md` — `### Retry and Timing Fields` table (~line 1518) and action-timeout `exit_code=124` note (~line 1368); also line ~2879 mirrors the `llm_gate` fragment `description:` verbatim from `lib/common.yaml` — will become stale after `lib/common.yaml` edit until `update-docs` runs [Wiring pass added by `/ll:wire-issue`]
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — `## Tips` (~line 700) and `## Troubleshooting` table (~line 716) already mention tuning `timeout` on `check_skill`; add MCP-heavy prompt guidance here too
- `scripts/little_loops/loops/lib/common.yaml` — no accompanying README; guidance goes inline in the `llm_gate` fragment `description:` string

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`timeout: 720` does not exist in `lib/common.yaml`**: The issue description's claim that `common.yaml` ships `timeout: 720` is inaccurate. No `timeout:` field appears on any fragment in that file. The executor hardcoded fallback is **3600s** for prompt/LLM states (`scripts/little_loops/fsm/executor.py` `_run_action()`, ~line 949: `state.timeout or self.fsm.default_timeout or 3600`).
- **Fragment system, not YAML anchors**: `lib/common.yaml` uses the FSM `fragment:` merge system (state declares `fragment: llm_gate`), not YAML `<<: *anchor` syntax. No `<<: *prompt` pattern exists anywhere in the codebase.
- **`docs/reference/SCHEMA.md` does not exist**: The equivalent documentation is `docs/generalized-fsm-loop.md`, `## Timeouts` section (~line 1335).
- **Real risk scenario**: When a loop sets a low `default_timeout:` (e.g., 300–600s), states using `llm_gate` without an explicit `timeout:` inherit that low value — MCP-heavy prompts then get killed mid-synthesis. The 3600s fallback only applies when *neither* state-level `timeout:` *nor* loop-level `default_timeout:` is set.
- **Scaffolding location**: `skills/create-loop/loop-types.md` (not `SKILL.md`) is where harness templates live; `execute` states are generated without any `timeout:` (Variant A ~line 735, Variant B ~line 819); only `check_skill` states get `timeout: 300`.

## Implementation Steps

1. **`scripts/little_loops/loops/lib/common.yaml`** — update the `llm_gate` fragment's `description:` string to add timeout budget guidance: "When the prompt performs multiple MCP tool calls followed by synthesis (~10 calls), set `timeout: 1500` or higher at the state level; the 3600s executor fallback only applies when neither state-level `timeout:` nor loop-level `default_timeout:` is set."
2. **`skills/create-loop/loop-types.md`** — in harness Variant A (~line 711) and Variant B (~line 786) scaffolding templates, add `timeout: 1500  # ≥1500s when execute prompt does multiple MCP calls + synthesis` on the `execute` state; update `SKILL.md` wizard narrative to mention the MCP budget heuristic.
3. **`docs/generalized-fsm-loop.md`** — in the `## Timeouts` section (~line 1335), after the bullet noting the 3600s hardcoded fallback, add: "If the prompt performs multiple MCP tool calls followed by synthesis, budget ≥1500s at the state level — the 3600s fallback is bypassed whenever a loop-level `default_timeout:` is set."
4. **`docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`** — in `## Tips` (~line 700), add a note that `execute` states performing MCP-heavy synthesis should set `timeout: 1500` or higher.
5. **Verification**: confirm guidance text is consistent across all four touchpoints; run `wc -l skills/create-loop/SKILL.md` and `wc -l skills/create-loop/loop-types.md` to confirm both remain under 500 lines.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. **`skills/create-loop/reference.md`** — add a `timeout` row to the `execute` state field tables: Multi-Item variant (~lines 103–109) and Single-Shot variant (~lines 150–163); recommended value `≥1500` for MCP-heavy prompts, mirroring the `check_skill` table's existing pattern (`timeout` → "Recommended: 120–300")
7. **`scripts/tests/test_enh1639_doc_wiring.py`** — create new doc-wiring test file following the `test_enh<NNN>_doc_wiring.py` pattern; assert: (a) `"timeout: 1500"` present in `skills/create-loop/loop-types.md`, (b) MCP guidance string present in `docs/generalized-fsm-loop.md` `## Timeouts` section, (c) MCP guidance string present in `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`
8. **`docs/guides/LOOPS_GUIDE.md` line 2793** — verify this mirror of the `llm_gate` description is updated (or note it will be picked up by the next `update-docs` run); if `docs-sync` or `update-docs` runs automatically, no manual edit needed — otherwise update inline

## Scope Boundaries

- **In scope**: Documentation/comment additions in the three locations above; default-value bump in the create-loop scaffolding template.
- **Out of scope**: Changing the runtime default of 720s in already-published loops; introducing a new streaming-agent action type; adding timeout-budget linting to `ll-loop validate`.

## Impact

- **Priority**: P4 — quality-of-life documentation fix; users can already work around by setting `timeout:` explicitly.
- **Effort**: Small — three doc/comment touchpoints, no code logic.
- **Risk**: Low — documentation-only and a default-value change in a scaffolding template (does not modify existing loops).
- **Breaking Change**: No.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Source

Findings from `~/.claude/plans/we-are-running-little-loops-glistening-kitten.md` (Finding 5). Documentation-only — no code change required.

## Labels

`enhancement`, `documentation`, `captured`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-24_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Outcome Risk Factors
- **Tests are co-deliverables**: `test_enh1639_doc_wiring.py` must be written as part of this issue (step 7). Implement tests first so the three assertions are runnable before finishing the doc edits — confirms coverage incrementally rather than discovering a missed touchpoint at the end.
- **LOOPS_GUIDE.md mirror**: The `llm_gate` description at line 2873 will become stale after `lib/common.yaml` edit. Minor open question: update inline now (step 8) vs. rely on `update-docs`. Default to updating inline to keep the implementation self-contained.

## Session Log
- `/ll:ready-issue` - 2026-05-24T14:09:33 - `b51b5e02-dbda-41ad-818b-5ce6e94b1437.jsonl`
- `/ll:confidence-check` - 2026-05-24T00:00:00Z - `b3785ae3-1506-4a4e-a176-62ea92db57f6.jsonl`
- `/ll:wire-issue` - 2026-05-24T13:48:53 - `cacb1713-b7ae-4ca0-a57e-5857ee6834c8.jsonl`
- `/ll:refine-issue` - 2026-05-24T13:41:42 - `8f14fda9-d560-46f6-992c-b2274de5ed68.jsonl`
- `/ll:format-issue` - 2026-05-23T19:21:50 - `e2957f37-1ad6-4175-b382-d8060a7c090f.jsonl`

- `/ll:capture-issue` — 2026-05-23T12:00:00Z
- `/ll:manage-issue` - 2026-05-24T14:13:35Z - implemented all 7 touchpoints; 7/7 doc-wiring tests pass

---
**Status**: Done | Created: 2026-05-23 | Completed: 2026-05-24 | Priority: P4

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue adds content to `skills/create-loop/SKILL.md`. ENH-494 enforces a 500-line limit on all `SKILL.md` files. `create-loop/SKILL.md` is currently 324 lines — well under the cap — but implementors should run `wc -l skills/create-loop/SKILL.md` after changes to confirm it remains under 500 lines.
