---
id: FEAT-2470
title: "Tier 0 token-cost behavioral quick-wins (P6 verbatim-output, haiku pin, edit-batch hook, LogCleaner filter, JSON output helpers)"
type: FEAT
priority: P2
status: open
captured_at: "2026-07-03T00:00:00Z"
discovered_date: 2026-07-03
discovered_by: scope-epic
parent: EPIC-2456
relates_to: [ENH-2471]
labels:
  - token-cost
  - hooks
  - skills
  - agents
  - tier-0
---

# FEAT-2470: Tier 0 token-cost behavioral quick-wins

## Summary

Ship EPIC-2456's Tier 0 layer (~180 LOC): five behavioral techniques that need no
measurement infrastructure and deliver immediate token savings. Per the epic's
prioritization plan (`thoughts/plans/2026-07-02-token-cost-optimal-techniques.md`),
Tier 0 is strictly dominant — it ships before any F-feature.

## Use Case

**Who**: Anyone running `ll-loop` / `ll-auto` / `ll-sprint` on this repo

**Context**: Every loop run pays avoidable token cost from verbose audit output, flagship-model subagents, unbatched edits, noisy tool logs, and unconstrained JSON output

**Goal**: Capture the immediate, infrastructure-free savings tier before any measurement/caching features land

**Outcome**: Lower $/run on every invocation, with the delta measured on ENH-2471's locked trace set

## Scope

| Source | Technique | Surface |
|---|---|---|
| wozcode P6 | Verbatim-output rule in audit skill bodies | ~6 `skills/*/SKILL.md` bodies |
| wozcode P2 | Haiku pin + dense-list template + 3–5-call budget on read-only audit agents | ~4 `agents/*.md` frontmatter |
| wozcode P1 | Edit-batching nudge (`PostToolUse` on Edit/Write/MultiEdit) | `hooks/hooks.json` + new hook module |
| LogCleaner [25] | Anti-event regex + duplicate-window pre-filter on tool/log output | new filter module (~60 LOC) |
| pass-2 #7 | Stop-sequence + prefill JSON output helpers (`extract_between_tags()`, `parse_prefilled_json()`, `rfind('{')` recipe) | new `scripts/little_loops/output/parse.py` (~30 LOC) |

**P2 haiku pin is Claude-adapter-only for now** — do not duplicate the pin
speculatively for Codex/OpenCode/omp/Gemini; a wrong `model:` field could
silently route a subagent to a flagship model (see epic's cross-host table).

## Current Behavior

Audit skills re-summarize instead of quoting verbatim; read-only audit agents run on default (flagship) models with no call budget; edits land one-at-a-time with no batching nudge; tool/log output carries anti-event noise and duplicated windows into context; FSM verdict JSON is emitted unconstrained (no stop-sequence/prefill helpers).

## Expected Behavior

All five Tier 0 techniques active by default: audit skills carry the verbatim-output rule, audit agents pin haiku with a 3–5-call budget, a `PostToolUse` hook nudges edit batching, the anti-event filter trims tool/log output, and `output/parse.py` helpers constrain JSON output.

## Acceptance Criteria

- Verbatim-output rule present in the ~6 audit skill bodies identified during implementation.
- Read-only audit agents pin haiku, use the dense-list template, and declare a 3–5-call budget in frontmatter.
- `PostToolUse` edit-batch hook registered in `hooks/hooks.json`; handler lives under `scripts/little_loops/hooks/` and is covered by `scripts/tests/test_edit_batch_hook.py`.
- LogCleaner-style anti-event/duplicate-window filter module exists with unit tests.
- `scripts/little_loops/output/parse.py` ships `extract_between_tags()` and `parse_prefilled_json()` with `scripts/tests/test_json_output_parse.py`.
- `python -m pytest scripts/tests/` exits 0.

## Verification

Before/after cost delta measured on ENH-2471's locked trace set (measured via
host CLI `usage` block since Tier 1 telemetry isn't online yet). Target: JSON
output helpers deliver 20–40% output-token reduction on FSM verdict strings.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `.issues/epics/P2-EPIC-2456-token-cost-reduction.md` | Parent epic; Tier 0 spec (§ Scope, § Integration Map) |
| `thoughts/plans/2026-07-02-token-cost-optimal-techniques.md` | Tier prioritization rationale |
| `docs/reference/API.md` | Document `output/parse.py` |

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis (locator + pattern-finder agents, 2026-07-04):_

### Files to Modify

**P6 (verbatim-output rule, ~6 audit skill bodies):**
- `skills/audit-loop-run/SKILL.md` — line 181 already carries a `quote ... verbatim` directive; expand to the full `CHECK_SEMANTIC_EVIDENCE_CONTRACT` template
- `skills/audit-claude-config/SKILL.md` — append verbatim-output rule at end of body
- `skills/audit-docs/SKILL.md` — append verbatim-output rule
- `skills/audit-issue-conflicts/SKILL.md` — append verbatim-output rule
- `skills/review-epic/SKILL.md` — append verbatim-output rule
- `skills/review-loop/SKILL.md` — append verbatim-output rule

**P2 (haiku pin + dense-list template + 3–5-call budget, ~4 read-only audit agents; Claude-adapter-only):**
- `agents/codebase-locator.md` — already `model: haiku` at line 32; add dense-list template + 3–5-call budget
- `agents/codebase-analyzer.md` — change `model: sonnet` (line 31) → `model: haiku` + add dense-list template + 3–5-call budget (read-only)
- `agents/codebase-pattern-finder.md` — same pattern at line 32 (`model: sonnet` → `haiku`)
- `agents/plugin-config-auditor.md` — same pattern at line 30

> ⚠ Haiku pin is per-adapter; do not duplicate the pin for Codex/OpenCode/omp/Gemini (per EPIC-2456 § cross-host table). A wrong `model:` field on a non-Claude host could silently route a subagent to a flagship.

**P1 (edit-batch nudge hook):**
- `hooks/hooks.json` — append a `PostToolUse` entry with matcher `Edit|Write|MultiEdit` (lines 65–143 hold the existing PostToolUse array; new entry goes after line 131)
- `scripts/little_loops/hooks/__init__.py` — register a new intent `edit_batch_nudge` in `_dispatch_table()` (lines 72–80+)
- `scripts/little_loops/hooks/edit_batch_nudge.py` (new) — the Python handler; returns an `LLHookResult` with `feedback` set to the nudge message and `exit_code=0` (nudge, never block)
- `scripts/little_loops/hooks/types.py` — reuses existing `LLHookEvent` / `LLHookResult`

### Files to Create

- `scripts/little_loops/output/parse.py` (~30 LOC) — `extract_between_tags()`, `parse_prefilled_json()`, `rfind('{')` recipe. Sibling to `scripts/little_loops/output_parsing.py` (NOT under `cli/`; spec calls for top-level `output/` package even though no `output/` package exists yet — creates the new directory)
- `scripts/little_loops/output_cleaner.py` (~60 LOC) — LogCleaner-style anti-event regex + duplicate-window pre-filter (named `output_cleaner.py` since `log_cleaner.py` doesn't exist; module-level compiled `_REGEX_NAME` constants + multi-regex union following `scripts/little_loops/text_utils.py:extract_file_paths` pattern)
- `scripts/tests/test_edit_batch_hook.py` (new) — Python-direct PostToolUse handler test; follows `scripts/tests/test_hook_post_tool_use.py:TestPostToolUseBaseline` layout (handler invocation + `monkeypatch.chdir(tmp_path)` + synthetic `LLHookEvent` via `_event()` factory)
- `scripts/tests/test_json_output_parse.py` (new) — pure-function parser tests; follows `scripts/tests/test_output_parsing.py:TestParseSections` layout (no `tmp_path`, no `monkeypatch`)
- `scripts/tests/test_output_cleaner.py` (new) — pure-function filter tests; follows the same `Test<FunctionName>` class-per-function shape

### Dependent Files (Callers / Importers)

- `scripts/little_loops/host_runner.py:244, 298` — `ClaudeCodeRunner.build_streaming` / `build_blocking_json` accept the `model:` parameter; haiku pin from agent frontmatter propagates through these factory methods (no change required)
- `scripts/little_loops/hooks/post_tool_use.py:158–199` — adjacent handler that the new edit-batch nudge composes with (analytics + auto-commit + learning gate)
- `scripts/little_loops/fsm/evaluators.py:64–71` — `CHECK_SEMANTIC_EVIDENCE_CONTRACT` is the canonical verbatim-output rule wording (use this exact copy); enforced by `_EVIDENCE_CONTRACT_KEYWORDS = frozenset({"verbatim", "quote", "evidence"})` at `scripts/little_loops/fsm/validation.py:1825` (MR-8 lint)
- `scripts/little_loops/output_parsing.py:27` — sibling module `extract_tagged_json` already implements similar logic; the new `output/parse.py` should be import-compatible (same `(data, error)` tuple convention established by BUG-2383)
- `scripts/little_loops/text_utils.py` — `extract_file_paths()` is the closest existing pattern for the LogCleaner multi-regex union; reuse the module-level `_REGEX_NAME` constant style

### Similar Patterns

- `scripts/little_loops/hooks/post_tool_use.py:handle` — Python handler returning typed `LLHookResult` (`exit_code`, `feedback`, `decision`)
- `scripts/little_loops/cli/output.py:42` (`strip_ansi`) — simplest "single-regex transform" precedent for the LogCleaner module
- `scripts/little_loops/session_log.py:138` (`rfind('## Session Log\n')`) and `scripts/little_loops/decisions_sync.py:36` (`rfind('## Active Rules\n')`) — both use the `rfind` insertion recipe that the EPIC spec calls `rfind('{')`
- `hooks/scripts/issue-auto-commit.sh` + `lib/common.sh` — bash hook pattern with `ll_resolve_config` + `ll_feature_enabled` for config-driven gates (use this pattern if a bash wrapper is preferred over Python for the edit-batch nudge)

### Tests

- `scripts/tests/test_hook_post_tool_use.py` — established PostToolUse handler test layout
- `scripts/tests/test_output_parsing.py` — established output parser test layout (pure functions, `Test<FunctionName>` class per function)
- `scripts/tests/test_json_output_contracts.py` — established CLI surface JSON contract snapshot test (lock `REQUIRED_FIELDS` set + class-per-field shape)
- `scripts/tests/test_pricing.py` — covers `pricing.MODEK_PRICING` (call-out because FEAT-2470 ships alongside Tier 1 cost primitives; downstream Tier 1 must not break pricing tests)

### Documentation

- `docs/reference/API.md:2947–2989` — has `output_parsing` documentation; `output/parse.py` entry should be added under the same "Output Parsing" section
- `docs/ARCHITECTURE.md:240+` — package tree lists `host_runner.py` and `output_parsing.py`; the new `output/parse.py` lands in the tree at the same level
- `.ll/decisions.yaml` — line 3859 holds the EPIC-2456 decision rule; FEAT-2470 decision appended at ship time (NOT captured at issue-creation per the FEAT capture-time decisions skip rule)

### Configuration

- `config-schema.json` — NO `cost_limits`, `max_cost`, `compression`, or `cache` keys exist yet. Tier 1 work (FEAT-2476 / ENH-2477) lands those keys per EPIC-2456. Tier 0 needs no schema change.
- `.ll/ll-config.json` — current blocks: `analytics`, `context_monitor`, `loops.run_defaults`, `prompt_optimization`, `history.compaction`. No Tier 0 changes required.

## Implementation Steps

_Added by `/ll:refine-issue` — concrete file references from research:_

1. **P1 hook first** — register `EditBatchNudge` intent in `scripts/little_loops/hooks/__init__.py:_dispatch_table` (after line 80); author `scripts/little_loops/hooks/edit_batch_nudge.py` returning `LLHookResult(exit_code=0, feedback="…batch your edits…")`. Add `hooks/hooks.json` matcher `Edit|Write|MultiEdit` entry. Test at `scripts/tests/test_edit_batch_hook.py` follows `TestPostToolUseBaseline` shape. Verify: `python -m pytest scripts/tests/test_edit_batch_hook.py -v`.
2. **JSON output helpers** — author `scripts/little_loops/output/parse.py` with `extract_between_tags(start_tag, end_tag, raw)` and `parse_prefilled_json(raw)` (model after `output_parsing.py:extract_tagged_json` with the same `(data, error)` tuple convention; reuse `rfind('{')` recipe from `session_log.py:138`). Test at `scripts/tests/test_json_output_parse.py` with `TestExtractBetweenTags` and `TestParsePrefilledJson` classes.
3. **LogCleaner filter** — author `scripts/little_loops/output_cleaner.py` with module-level `_ANTI_EVENT_RE = re.compile(...)` constants and a single `def filter(raw: str) -> str:` entry point. Test at `scripts/tests/test_output_cleaner.py`.
4. **P6 verbatim-output rule** — for each of the 6 audit skills, append the `CHECK_SEMANTIC_EVIDENCE_CONTRACT` block (verbatim copy from `fsm/evaluators.py:64–71`) near the top of the body. Verify with `python -m pytest scripts/tests/test_fsm_validation.py` that MR-8 keyword lint passes for any loop-YAML referencing these skills.
5. **P2 haiku pin** — change `model: sonnet` → `model: haiku` on the 3 candidates (`codebase-analyzer`, `codebase-pattern-finder`, `plugin-config-audapter`); add `dense_list_template: <text>` and `max_calls: 5` frontmatter fields per the project's existing frontmatter style. Confirm Claude-only (don't propagate to Codex/OpenCode/omp/Gemini agents).
6. **Verify**: `python -m pytest scripts/tests/` exits 0; before/after cost delta measured on ENH-2471's locked trace set.

## Impact

- **Priority**: P2 — first-shipped tier of EPIC-2456; strictly dominant (no infra prerequisites, immediate savings)
- **Effort**: Small-Medium — ~180 LOC across skill/agent text edits, one hook module, two small Python modules + tests
- **Risk**: Low — behavioral/additive; no default runtime behavior changes outside automation nudges
- **Breaking Change**: No

## Status

**Open** | Created: 2026-07-03 | Priority: P2

## Session Log
- `/ll:refine-issue` - 2026-07-04T20:17:26 - `c598e9f8-80b2-4ec0-9e0f-bc292080ce64.jsonl`

- `/ll:scope-epic` - 2026-07-03T00:00:00Z - filed from EPIC-2456 § Children [TBD-1] (Tier 0 roll-up)
