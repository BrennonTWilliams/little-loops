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

### Wiring Pass Additions (added by `/ll:wire-issue`)

_Wiring-pass audit by `/ll:wire-issue` (2026-07-04) — items below were identified by the caller-tracer / side-effect-surface / test-gap agents and were not in the Refinement Pass 1/2 Integration Map:_

**Loop YAMLs invoking modified skills (must re-validate when the skill bodies change):**
- `scripts/little_loops/loops/outer-loop-eval.yaml:93,117` — invokes `/ll:audit-loop-run ${context.input} --auto` from this loop's evaluate state. The P6 verbatim-output rule applies when this skill runs from these states.
- `scripts/little_loops/loops/sprint-build-and-validate.yaml:100,124` — invokes `/ll:audit-issue-conflicts --auto` from two states. Same rule applies.
- `scripts/little_loops/loops/README.md:97` — describes `outer-loop-eval`'s delegation to `audit-loop-run`; no body change needed (documentation only).

**Re-export sites (sibling-pattern reference for the new `output/parse.py` package):**
- `scripts/little_loops/__init__.py:42` — re-exports `parse_manage_issue_output`, `parse_ready_issue_output` from `output_parsing` under the `# output_parsing` banner (line 118). Any new `output/parse.py` re-exports land here too — model the new re-exports after this banner pattern.

**Registration / manifest files (NEW):**
- `scripts/little_loops/hooks/__init__.py:50–54` — `_USAGE` static string listing available intents for the `python -m little_loops.hooks` banner. **Must be updated** to include `edit_batch_nudge` so the new intent is discoverable. Not test-enforced, but consumers see it via the `Unknown intent` error message at line 113–117 and the `python -m little_loops.hooks` help output.
- `scripts/little_loops/hooks/adapters/codex/hooks.json` — Codex mirror of `hooks/hooks.json` PostToolUse array. The "Claude-adapter-only" warning applies to the **P2 haiku pin** (NOT the edit-batch nudge). The `Edit|Write|MultiEdit` matcher is host-agnostic; **decide** whether the nudge should fire on Codex hosts and mirror the entry accordingly. Document the decision in Implementation Step 9.
- `.claude-plugin/plugin.json:22–27` — agent manifest entries for `codebase-analyzer`, `codebase-locator`, `codebase-pattern-finder`, `plugin-config-auditor`. Per Refinement Pass 2 the agents' `.md` frontmatter is the source of truth for `model:`; verify the manifest doesn't carry stale model hints after the P2 pin (read-only check, do NOT modify unless manifest diverges).

**Tests (NEW gaps identified):**
- `scripts/tests/test_audit_claude_config.py` — **does not exist**. P6 verbatim-output rule on `skills/audit-claude-config/SKILL.md` has no body-lint coverage today. Same gap for `scripts/tests/test_audit_docs.py` (does not exist; P6 rule on `skills/audit-docs/SKILL.md` is uncovered). The 4 other audit skills have at least one structural test. If lint coverage is desired, create minimal body tests asserting the verbatim-output rule is present (out-of-scope per Refinement Pass 2, flagged for follow-on in Step 11).
- `scripts/tests/test_enh494_skill_companions.py:71–81` (`test_all_skills_within_limit`) — **CRITICAL 500-line `SKILL.md` cap**. `SKILL_LINE_LIMIT = 500` and the test iterates every `skills/*/SKILL.md`. The P6 verbatim-output append (~10 lines of `CHECK_SEMANTIC_EVIDENCE_CONTRACT` content) must fit within each skill's remaining line budget, OR the overflow must be extracted to a companion file following the `reference.md` / `wave1-prompts.md` precedent (ENH-494). Pre-check each of the 6 skills' current line count before appending; if any would exceed 500, extract the verbatim-output block to a companion file. `scripts/little_loops/cli/docs.py:240,250,254,267,269` (`ll-verify-skills`) enforces the same 500-line cap.

**Documentation (NEW coupling surfaced by the side-effect agent):**
- `docs/reference/API.md:8075–8083` — agent table lists `codebase-analyzer` (sonnet), `codebase-locator` (haiku), `codebase-pattern-finder` (sonnet), `plugin-config-auditor` (sonnet). **Three rows must flip to `haiku`** after the P2 pin lands (`codebase-locator` is already `haiku`). `scripts/tests/test_wiring_reference_docs.py` already asserts `### /ll:review-epic` and `| review-epic` strings at lines 158–159 — keep those substrings present when editing.
- `docs/guides/BUILTIN_HOOKS_GUIDE.md:55–64, 227, 382–394` — line 227 says "Six hooks run after each tool call" (PostToolUse); the table at lines 55–64 lists 6 entries; the config-keys table at lines 382–394 lists PostToolUse-related config keys. Adding the 7th PostToolUse entry (`edit_batch_nudge`) makes the count and the tables stale. **Update the count and both tables** in Implementation Step 10.

**Cross-skill references (NEW — verify still load after the body edits; append-only change is safe but worth a CI sanity check):**
- `skills/create-loop/SKILL.md`, `skills/scope-epic/SKILL.md`, `skills/configure/areas.md`, `skills/configure/show-output.md`, `skills/simplify-loop/SKILL.md`, `skills/simplify-loop/reference.md`, `skills/improve-claude-md/algorithm.md`, `skills/update-docs/SKILL.md`, `skills/review-loop/reference.md`, `skills/audit-docs/templates.md`, `skills/audit-claude-config/wave1-prompts.md`, `agents/consistency-checker.md`, `agents/prompt-optimizer.md` — reference one or more of the 6 audit skills or 4 audit agents. The append-only P6 change preserves all anchors.

**Adapter callers (do NOT modify these, included for context):**
- `.codex/agents/codebase-analyzer.toml`, `.codex/agents/codebase-pattern-finder.toml`, `.codex/agents/plugin-config-auditor.toml` — currently `model = "sonnet"`. Per the "Claude-adapter-only" warning they MUST remain `sonnet`. Don't regenerate via `ll-adapt --host codex --apply` for these three agents until Codex-side model support lands. `.codex/agents/codebase-locator.toml` is already `model = "haiku"` (parallel to the agent's `model: haiku`).

### Codebase Research Findings (Refinement Pass 2)

_Added by `/ll:refine-issue` (second pass, 2026-07-04) — based on analyzer + pattern-finder agent output:_

**MR-8 lint scope clarification (P6):**
- `scripts/little_loops/fsm/validation.py:1828–1867` — `_validate_llm_evidence_contract` operates only on `FSMLoop` state configs (YAML), NOT on skill markdown bodies. The P6 verbatim-output rule on skill bodies is BEHAVIORAL — no lint validates it today. If lint coverage is desired, a separate skill-body MR-8 check would be needed (out of scope for FEAT-2470).
- The "verify MR-8 lint passes" line in Implementation Step 4 only applies to FSM-YAML state prompts that reference these skills; the skill-body text change itself is unchecked.

**`exit_code` semantics for the edit-batch nudge handler (P1):**
- `scripts/little_loops/hooks/types.py:84–116` — `LLHookResult(exit_code=0, feedback=...)` writes feedback to stderr only; `LLHookResult(exit_code=2, feedback=...)` blocks + injects feedback into Claude's context. The current Implementation Step 1 returns `exit_code=0` — this is a silent nudge (visible to the user, not to the model). If the goal is to actually influence Claude's editing behavior, switch to `exit_code=2`. If a status-line nudge is intended, `exit_code=0` is correct.
- `scripts/little_loops/hooks/user_prompt_submit.py:61–80` — existing `LLHookResult(exit_code=0, feedback="…")` precedent for status-line nudges; `pre_tool_use.py:23–30` is the smallest handler template (~7 lines, branch on tool_name, return result) — cleaner template than `post_tool_use.py:handle` for a single-purpose nudge.

**`dense_list_template` / `max_calls` frontmatter are inert today (P2):**
- `scripts/little_loops/frontmatter.py:30` — flat YAML parser; reads `model:` and any other top-level key as a dict value.
- Verified by Grep: `dense_list_template` / `max_calls:` have no consumer outside the issue file. Tier 0 adds the frontmatter fields; honoring them is downstream work (loop YAML / agent dispatcher). Document this as forward-looking; ship Tier 0 anyway so the fields land before consumers.

**Cross-host model field plumbing:**
- `scripts/little_loops/adapters/codex.py:349–374` — `CodexAdapter.emit_agent` reads `fm.get("model")` and would dispatch the same field to Codex's model resolver. This validates the "Claude-only" warning in Issue § Scope: a `model: haiku` on a Codex agent would route to whichever model Codex interprets that string as (likely the flagship). Do not mirror the pin to Codex/OpenCode/omp/Gemini agent markdowns.
- `scripts/little_loops/host_runner.py:236–282` + `scripts/little_loops/subprocess_utils.py:329–336` — `model:` from agent frontmatter does NOT auto-flow into `build_streaming`. Orchestration layer must pass `model=` explicitly. Tier 0 only changes frontmatter; the dispatch wiring is downstream.

**Test pattern references (more precise):**
- `scripts/tests/test_hook_post_tool_use.py:27–33` — `_event(payload, *, cwd)` test factory; new `test_edit_batch_hook.py` follows this exact shape (synthetic `LLHookEvent`, `monkeypatch.chdir(tmp_path)`, assert `result.exit_code` + `result.feedback`).
- `scripts/tests/test_output_parsing.py:15–78` — `TestParseSections` class-per-function shape (no `tmp_path` / `monkeypatch`, pure functions). New `test_json_output_parse.py` and `test_output_cleaner.py` follow this shape exactly.
- `scripts/little_loops/cli/output.py:38–47` — `_ANSI_RE` + `strip_ansi()` precedent for a single-regex transform; the simplest "filter" example to model the LogCleaner's simplest regex after.
- `scripts/little_loops/text_utils.py:14–21` — module-level compiled `re.Pattern` constants grouped under a banner comment, pre-process step (`_CODE_FENCE.sub("", content)`) before the union loop; this is the multi-regex precedent for the LogCleaner `_ANTI_EVENT_RE` / `_DUPLICATE_WINDOW_RE` constants.

## Implementation Steps

_Added by `/ll:refine-issue` — concrete file references from research:_

1. **P1 hook first** — register `EditBatchNudge` intent in `scripts/little_loops/hooks/__init__.py:_dispatch_table` (after line 80); author `scripts/little_loops/hooks/edit_batch_nudge.py` returning `LLHookResult(exit_code=0, feedback="…batch your edits…")`. Add `hooks/hooks.json` matcher `Edit|Write|MultiEdit` entry. Test at `scripts/tests/test_edit_batch_hook.py` follows `TestPostToolUseBaseline` shape. Verify: `python -m pytest scripts/tests/test_edit_batch_hook.py -v`.
2. **JSON output helpers** — author `scripts/little_loops/output/parse.py` with `extract_between_tags(start_tag, end_tag, raw)` and `parse_prefilled_json(raw)` (model after `output_parsing.py:extract_tagged_json` with the same `(data, error)` tuple convention; reuse `rfind('{')` recipe from `session_log.py:138`). Test at `scripts/tests/test_json_output_parse.py` with `TestExtractBetweenTags` and `TestParsePrefilledJson` classes.
3. **LogCleaner filter** — author `scripts/little_loops/output_cleaner.py` with module-level `_ANTI_EVENT_RE = re.compile(...)` constants and a single `def filter(raw: str) -> str:` entry point. Test at `scripts/tests/test_output_cleaner.py`.
4. **P6 verbatim-output rule** — for each of the 6 audit skills, append the `CHECK_SEMANTIC_EVIDENCE_CONTRACT` block (verbatim copy from `fsm/evaluators.py:64–71`) near the top of the body. Verify with `python -m pytest scripts/tests/test_fsm_validation.py` that MR-8 keyword lint passes for any loop-YAML referencing these skills.
5. **P2 haiku pin** — change `model: sonnet` → `model: haiku` on the 3 candidates (`codebase-analyzer`, `codebase-pattern-finder`, `plugin-config-audapter`); add `dense_list_template: <text>` and `max_calls: 5` frontmatter fields per the project's existing frontmatter style. Confirm Claude-only (don't propagate to Codex/OpenCode/omp/Gemini agents).
6. **Verify**: `python -m pytest scripts/tests/` exits 0; before/after cost delta measured on ENH-2471's locked trace set.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by `/ll:wire-issue` wiring analysis (caller-tracer + side-effect-surface + test-gap agents, 2026-07-04) and must be included in the implementation:_

7. **`_USAGE` banner update** — add `edit_batch_nudge` to the static intent list in `scripts/little_loops/hooks/__init__.py:50–54`. Not test-enforced but `python -m little_loops.hooks` help output and the `Unknown intent` error branch both surface the list.
8. **500-line `SKILL.md` cap pre-check (CRITICAL for P6)** — before appending the verbatim-output block to any of the 6 audit skills, run `wc -l skills/<skill>/SKILL.md` and verify the post-append count stays ≤500. If any would exceed, extract the verbatim-output block to a companion file (`skills/<skill>/verbatim-output.md`) following the ENH-494 `reference.md` / `wave1-prompts.md` pattern. Verify: `python -m pytest scripts/tests/test_enh494_skill_companions.py -v`. The `ll-verify-skills` CLI at `scripts/little_loops/cli/docs.py:240,250,254,267,269` enforces the same cap and must exit 0.
9. **Codex mirror decision** — decide whether the `Edit|Write|MultiEdit` PostToolUse matcher should fire on Codex hosts. The haiku-pin is Claude-only (per cross-host table), but the edit-batch nudge is host-agnostic. If yes, mirror the matcher entry in `scripts/little_loops/hooks/adapters/codex/hooks.json` (do NOT regenerate the three `.codex/agents/*.toml` files for the pinned agents — those must remain `sonnet`).
10. **Docs update** — flip 3 rows in `docs/reference/API.md:8075–8083` agent table from `model: sonnet` to `model: haiku`; update the PostToolUse count ("Six hooks…" at line 227) and both tables (lines 55–64, 382–394) in `docs/guides/BUILTIN_HOOKS_GUIDE.md`. Keep `### /ll:review-epic` and `| review-epic` substrings present in `docs/reference/COMMANDS.md` (asserted by `scripts/tests/test_wiring_reference_docs.py:158–159`).
11. **Body-lint coverage gap (optional follow-on)** — `scripts/tests/test_audit_claude_config.py` and `scripts/tests/test_audit_docs.py` do not exist; the P6 rule on those two SKILL.md bodies has no test coverage today (the other 4 audit skills have at least one structural test). If coverage is desired, create minimal body tests asserting `verbatim` / `quote` / `evidence` keywords are present — modeled on `test_audit_loop_run_skill.py:test_pid_corruption_skill_step4_has_verbatim_quote_contract` (lines 617–631). Flagged as a follow-on issue, not blocking FEAT-2470 ship.

### Implementation Notes (Refinement Pass 2)

_Added by `/ll:refine-issue` (second pass, 2026-07-04) — clarifications from agent analysis:_

- **Step 1 (edit-batch nudge handler)** — confirm whether the nudge is meant to be a visible-to-Claude nudge (`exit_code=2`, feedback flows into model context) or a status-line nudge (`exit_code=0`, feedback only to stderr). The current step says `exit_code=0`; if the intent is to actually influence editing behavior, switch to `exit_code=2`. Per `types.py:97-99`, `exit_code=2` is "block and inject feedback into the model's context" — semantically not blocking when there's no permission gate, just nudging Claude.
- **Step 4 (P6 verbatim-output rule)** — the MR-8 lint at `validation.py:1828–1867` operates only on FSM state prompts. The skill-body change is behavioral; no lint validates it. The "verify with `test_fsm_validation.py`" line in Step 4 only applies if any loop-YAML state references these skills in `evaluate.prompt` fields.
- **Step 5 (haiku pin)** — note that `dense_list_template` and `max_calls` frontmatter fields are inert today (no consumer); Tier 0 ships the fields forward-looking, consumers land in later tiers. Verify the parser at `frontmatter.py:30` doesn't reject the new keys (it accepts any top-level YAML).
- **Bash wrapper alternative** — if a bash wrapper is preferred over a Python handler for the edit-batch nudge, `hooks/scripts/issue-auto-commit.sh:1–81` is the canonical pattern: `set -euo pipefail` + `source lib/common.sh` + `ll_resolve_config` + `ll_feature_enabled "key.path"` + `jq -r '.tool_name // ""'`. The Python handler is preferred for consistency with `post_tool_use.handle` and the canonical pattern at `pre_tool_use.py:23-30`.

## Impact

- **Priority**: P2 — first-shipped tier of EPIC-2456; strictly dominant (no infra prerequisites, immediate savings)
- **Effort**: Small-Medium — ~180 LOC across skill/agent text edits, one hook module, two small Python modules + tests
- **Risk**: Low — behavioral/additive; no default runtime behavior changes outside automation nudges
- **Breaking Change**: No

## Status

**Open** | Created: 2026-07-03 | Priority: P2

## Session Log
- `/ll:wire-issue` - 2026-07-05T04:54:07 - `3ba600e5-885f-4d1d-8b33-b44ca74a0610.jsonl`
- `/ll:wire-issue` - 2026-07-05T04:53:54 - `3ba600e5-885f-4d1d-8b33-b44ca74a0610.jsonl`
- `/ll:refine-issue` - 2026-07-05T01:50:49 - `c72d5171-8193-4412-8ed0-3b840d31619b.jsonl`
- `/ll:refine-issue` - 2026-07-04T20:17:26 - `c598e9f8-80b2-4ec0-9e0f-bc292080ce64.jsonl`

- `/ll:scope-epic` - 2026-07-03T00:00:00Z - filed from EPIC-2456 § Children [TBD-1] (Tier 0 roll-up)
