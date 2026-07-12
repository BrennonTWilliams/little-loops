---
id: ENH-2621
priority: P3
status: open
type: ENH
created: 2026-07-12
parent:
labels: [docs, audit, technical-debt]
---

# ENH-2621: Apply remaining docs/guides/ audit fixes from 2026-07-12 sweep

## Summary

`/ll:audit-docs docs/guides/` produced a 249-finding report across 16 files. The orchestrator applied ~50 high-confidence mechanical corrections directly; the remaining ~199 findings are paraphrased/structural/completeness gaps that need design or research work before fixing. This issue collects them for triage and incremental closure.

**Audit date**: 2026-07-12
**Source**: One-time sweep (no prior audit issue existed)
**Files staged**: 15 of 16 files (`docs/guides/{AUTOMATIC_HARNESSING,BUILTIN_HOOKS,DECISIONS_LOG,EXAMPLES_MINING,GETTING_STARTED,HARNESS_OPTIMIZATION,HISTORY_SESSION,ISSUE_MANAGEMENT,LEARNING_TESTS,LOOPS,LOOPS_REFERENCE,POLICY_ROUTER,SESSION_HANDOFF,SPRINT,WORKFLOW_ANALYSIS}_GUIDE.md`)
**Recurring-corrected**: No

## What was already fixed (committed, ~50 items, low-risk)

### AUTOMATIC_HARNESSING_GUIDE.md
- "Full 6-phase ordering" heading clarifies "5 evaluation gates + stall detection"
- ENH-2516 force-exit branch line range corrected (103-107 → 126-148) in two locations

### BUILTIN_HOOKS_GUIDE.md
- install-nudge gate reclassified PreToolUse → PostToolUse in lifecycle table, narrative, and section heading
- install-nudge hook chain re-attributed (`post-tool-use.sh → post_tool_use → install_learning_gate.gate`)
- install-nudge message exact output corrected
- Duplicate-ID error messages exact strings (PreToolUse and PostToolUse variants)
- Dropped false scratch cleanup claim from `session-cleanup.sh` (BUG-2420)

### DECISIONS_LOG_GUIDE.md
- Sync trigger factually corrected: only `promote --enforcement required` triggers automatic sync; `add` and session-start do not

### EXAMPLES_MINING_GUIDE.md
- `tools_used` schema corrected to `{tool, count}` object format (3 occurrences)
- `ResponseMetadata` field list expanded (`files_read`, `error_message`)
- `max_iterations: 20` → `max_steps: 20` (apo-textgrad inheritance)
- `loop:` interpolation caveat corrected
- `target_pass_rate` documented as defined-but-unused and apo-textgrad override risk
- EPIC issue-type coverage caveat added
- "12 states" → "12 non-terminal states + done terminal"

### GETTING_STARTED.md
- `--enable FEATURE` valid names reordered to match argparse order
- `--quick` "5 fields only" claim dropped (template variant, not fixed count)
- `--format-issue` description corrected (template alignment, not minimal→full promotion)

### HARNESS_OPTIMIZATION_GUIDE.md
- Trajectory path corrected (`.loops/runs/harness-optimize/<run-id>/...` → `${context.run_dir}/states/...`)
- Cross-host probe order fixed (`claude, codex, opencode, pi` → `claude-code, codex, pi, gemini, omp`; opencode intentionally absent)

### HISTORY_SESSION_GUIDE.md
- `tool_events` byte counts vs token counts clarified
- `--kind` `--issue` interaction clarified (required unless issue given)
- Dropped nonexistent `--branch` flag example on `ll-session recent`

### ISSUE_MANAGEMENT_GUIDE.md
- `format-issue` example rewritten for ISSUE_ID not file path
- Status synonym list expanded (`closed`, `in progress`)
- 4-decision type discriminator labels fixed (`decision, rule, exception, coupling`)
- `ll-auto --only` example pluralized; `ll-sprint create` example given `--issues`

### LEARNING_TESTS_GUIDE.md
- PreToolUse hook output corrected to single-line form with `--context task=` syntax
- LOOPS_GUIDE troubleshooting link anchor added
- "session" cache wording clarified (per-process module-level)

### LOOPS_GUIDE.md
- `cost_ceiling_per_state` / `cost_warn_at` table corrected (no `on_ceiling_exceeded` symbol; validator rejects, doesn't warn; FEAT-2476 cancelled 2026-07-10)
- BUG-2305 stub converted to non-stub paragraph (severity promoted to ERROR by BUG-2400)
- BUG-2302 stub converted to non-stub paragraph (landed)
- `error_patterns` wording corrected (overrides no-match → error)
- Dangling `<!-- END TODO stub -->` removed

### LOOPS_REFERENCE.md
- `general-task` "200 iterations" → 500 steps (also ~83 plan steps, not 32)
- `html-website-generator` "30 iterations / 4-hour timeout" → 12 / 1 hour
- `vega-viz` `max_steps: 20` → 30
- `rn-plan` "8-dimension rubric" → 9 dimensions
- `check_broke_down` flag path corrected to `${context.run_dir}/refine-broke-down`

### POLICY_ROUTER_GUIDE.md
- `--no-warnings` wording covers both verdict-matrix and compound mode
- `--allow-delete` clarified (verdict-matrix only)

### SESSION_HANDOFF.md
- `result_token_count` formula corrected (drops `cache_read_input_tokens`)
- `.ll/ll-session-state.json` row marked as not-currently-produced
- `.ll/ll-context-handoff-needed` row added

### SPRINT_GUIDE.md
- `blocked_by` description softened (soft ordering, not hard gate)
- Single-issue wave note acknowledges subsequent merge integration
- Two broken `../../` link paths corrected to `../`
- "Merging remains manual" updated to reflect `merge_epic_branch` automation
- New config row: `parallel.timeout_per_issue` vs `sprints.max_issue_wall_clock_time`
- Checkpoint cadence paragraph added (per sub-wave, not per wave)
- Six grouping strategies → seven
- Pre-validation completed/cancelled handling clarified
- Resume scope language (Ctrl+C vs abrupt restart)

### WORKFLOW_ANALYSIS_GUIDE.md
- `--input FILE` default path corrected (`user-messages.jsonl` → `step1-patterns.jsonl`)
- `--intent` description wording aligned to code

## Remaining findings (triage queue, ~199 items)

### High-priority completeness/correctness gaps that need real fixes

#### docs/guides/RECURSIVE_LOOPS_GUIDE.md (16 findings, mostly structural)

All four high-severity items require substantial rewrites of:

- L39 (`rn-plan` artifact list) — add `research.md` to output trio
- L52-88 (`rn-build` call graph) — rewrite: rn-build does not delegate to `rn-plan`/`rn-refine`; it has its own research/design/scoping stages and uses `goal-cluster` for execution
- L81-82 (rn-build narrative) — "runs planning first and implementation second" is wrong
- L92-97 (rn-refine delegation) — uses `oracles/plan-node-refine`, not `oracles/plan-research-iteration`
- L121-122 (`rn-refine` overwrite semantics) — has preflight that may abort; backs up first
- L228-230 (`GATE_SKIP` and `GATE_FAILED_INFRA` outcome rows) — these are not routed as documented; remove `GATE_SKIP` row, correct `GATE_FAILED_INFRA` destination
- L243-252 (three-loop comparison) — section omits the subject loop (`rn-implement`); restructures needed
- L365-367 (`rn-build` summary line) — adds eval-harness step

This file is heavy with structural rewrites. Recommend opening a single ENH that touches this file exclusively, possibly rolling into a sprint.

#### docs/guides/HARNESS_OPTIMIZATION_GUIDE.md

- L94 MR-1 evaluator type list omits 6 types (validator at `fsm/validation.py:84` lists 12)
- L165-197 "Canonical Shape" diagram/table names don't match `harness-optimize.yaml`'s actual states (`baseline_score`, `commit_and_log`, `revert_and_log` etc.). Either anchor or note as pedagogical simplification
- L210-256 "Minimal Example" YAML — `gate` state uses `on_yes/on_no` against `convergence` evaluator (verdicts: `target/progress/stall/error`); needs full rewrite to use `route:` keys
- L215-222 `baseline` state action chains; convergence gate source mismatch
- L463 "specialist-pipeline not a meta-loop" — MR-1 trigger is action-string/import heuristic via `_is_meta_loop()`, not `category`
- L271-286 wizard label discrepancy (`"Optimize a harness"` vs `"Optimize a harness (meta-loop)"`)

#### docs/guides/LOOPS_REFERENCE.md

- L1028, 1046, 985-987, 1121 — recursive-refine and autodev path prefixes (`.loops/tmp/recursive-refine-*` and `.loops/tmp/autodev-*`) need to be replaced with `${context.run_dir}/...` equivalents across a ~500-word paragraph. Apply with sed/awk or careful Edit per-path.
- L3057-3076, L98 — `outer-loop-eval` variable inversion (`loop_name` vs `input`/`loop_input`)
- L3163-3165, 3168-3183 — Seven libraries → eleven (4 missing: `apo-shape-a.yaml`, `rubric-router.yaml`, `policy-router.yaml`, `composer.yaml`)
- L3168-3183 — lib/common.yaml fragment table has 19 fragments, document only lists 14 (missing `with_throttle`, `open_question_stall_gate`, `snapshot_artifact`, `ll_auto_auth_check`, `ll_auto_learning_gate_check`)
- L905-923, 1066-1087, 537-546, 320-359, 270-278 — five loops each have FSM flow diagrams that miss 1-3 actual states (`recheck_set`, `record_error`, `check_wire_budget`, `run_wire_for_artifacts`, `skip_missing_artifacts`, `check_missing_artifacts`, `gate_recursion`, `finalize_parent`, `emit_no_children`, `emit_size_review_failed`, `rate_limit_diagnostic`, `route_resume_synth`, `record_node_crash`, `finalize_aborted`, `load_planning_prompt`, `score`)
- L1055 — broken `--context order=next-action commit_every=5 no_recursion=true` syntax (needs `--context` per pair)
- L1508 — wrong cross-ref to `LOOPS_GUIDE.md:897`
- L1395, 1577, 1641, 1755, 1842, 1911, 1975, 2054, 2134, 2206 — `run_dir` path pattern (`-timestamp` → `-{instance_id}`)

#### docs/guides/AUTOMATIC_HARNESSING_GUIDE.md

- L355-356, 1110-1111 — `on_tie: execute` and `on_no_baseline: check_invariants` shorthand keys don't exist; only `on_yes/on_no/on_error/on_partial/on_blocked` are recognized. Two example YAML blocks need restructuring (use `route:` table for `comparator` evaluator's `tie/no_baseline` verdicts)
- L489 internal "6-phase" terminology drift (partial fix already applied)
- L810 attribution to `loop-router.yaml:296-319` for APPROVE/REVISE pattern is misleading
- L1182 — `events.jsonl` archival description slightly misleading

#### docs/guides/SESSION_HANDOFF.md

- L278 — config table missing three keys (`per_turn_overhead`, `system_prompt_baseline`, `post_compaction_percent`)
- L281 — accuracy claim `±30-50%` → `±5-15%` not verifiable
- L362 — example state file breakdown keys (`read`, `bash`, `grep`, `glob`, `task`) miss `claude_overhead`, `last_baseline_mtime`
- L277 — `context_limit_estimate` description omits 1100000 cap
- L289-295 — `--handoff-threshold` scope incomplete (also on `ll-loop run`/`resume`)
- L474-478 — `working_dir` parameter name mismatch (actual: `repo_path`)

#### docs/guides/SPRINT_GUIDE.md

- L350 — partial fix applied; verify
- L222 (already partially fixed)
- L267 (already partially fixed)
- L399 (already partially fixed)
- L465 (already partially fixed)
- L495 (already partially fixed)
- L89 sub-wave display message
- L141 seven strategies (already partially fixed) — table cell needs confirmation

#### docs/guides/HISTORY_SESSION_GUIDE.md

- L50 ENH version mapping needs explicit version numbers
- L74-76 analytics capture keys (`skills`, `cli_commands`) underdocumented
- L65 `user_corrections` regex list is illustrative but undersized
- L402-411 retention and `prune` integration underdocumented
- L35 vs L244 example ID inconsistency
- L438-455 Configuration Reference table omits `history.session_digest.sections`, `history.effort_fields`, `history.evolution`, `history.go_no_go`, `history.capture_issue`
- Missing docs for `ll-session export` subcommand

#### docs/guides/LEARNING_TESTS_GUIDE.md

- L339 — `discoverability.skip_packages` row omits hardcoded `_BUILTIN_SKIP` set
- L405-406 — Release gate example values need realistic target strings
- L147 — `check` exit-code column qualifier added in some rows
- L224-228 — Gate Entry Points table omits `oracles/enumerate-and-prove`
- L91-92 — `scrape-docs` reference attribution clarified

#### docs/guides/BUILTIN_HOOKS_GUIDE.md

- L113, 179 — schema default vs effective-runtime default mismatch
- L381-385 — Rubric default-signal lists underdocumented (`resolved`, `implemented`, `repeat`)
- L444, 454 — Config `parallel.worktree_base` vs `automation.worktree_base` cross-check needed
- L192-197, 286-289 — error message quotes (partial fix already applied)

#### docs/guides/EXAMPLES_MINING_GUIDE.md

- L5 "≥ 5 completed issues" claim not enforced anywhere
- L256 (already partially fixed)
- L382 — harvested example schema omits `session_id`
- L496-510 — `judge` state restructure for sub-loop delegation is oversimplified

#### docs/guides/ISSUE_MANAGEMENT_GUIDE.md

- L209-218 — pipeline 8 steps is incomplete (adds `decide-issue`, `align-issues`, `link-epics` per canonical skills)
- L82 — Validating phase pipeline list also incomplete
- L367, 610, 344 — minor redundancies/claims
- L522 — minor (mostly fixed)

#### docs/guides/GETTING_STARTED.md

- L13-18 — Canonical flow diagram omits `format-issue`/`refine-issue`
- L86 — gitignore example list expansion
- L169 — manage-issue callout completeness

#### docs/guides/DECISIONS_LOG_GUIDE.md

- L468-474 — example auto_generate vs default consistency
- L201-205 — `--auto` and `--validate-only` flag documentation missing
- L229-233 — CHANGES APPLIED granularity

#### docs/guides/HARNESS_OPTIMIZATION_GUIDE.md (additional)

- L98 MR-1 evaluator types list omission

#### docs/guides/POLICY_ROUTER_GUIDE.md

- L44 — natural language shortcut example may map to `orch-router` instead
- L192-195 — minor completeness (`validate policy-refine` already covers unscored-dim case)

#### docs/guides/WORKFLOW_ANALYSIS_GUIDE.md

- L223-224 — Manual pipeline `--input` path default needs patch
- L106-115 — `ll-messages` flag list expansion
- L268 — workflow-automation-proposer invocation note
- L288 — "fully scriptable end-to-end" claim oversold (still requires Claude CLI)

## Recommended triage order

1. **High-severity path/syntax corrections** (RECURSIVE_LOOPS, LOOPS_REFERENCE, AUTOMATIC_HARNESSING YAML examples) — concretely incorrect, can be applied after a re-read of each section
2. **Schema/config-table completeness** (SESSION_HANDOFF, HISTORY_SESSION) — additive row updates
3. **FSM-diagram updates** (LOOPS_REFERENCE missing-state lists, RECURSIVE_LOOPS call graph) — research state lists per file before redrawing
4. **Risk-flagged prose** (HARNESS_OPTIMIZATION canonical-shape ambiguity, EXAMPLES_MINING ad-hoc guides) — design discussion needed before applying

**Estimated remaining work**: 4-8 focused commits across ~2-3 sprint cycles if handled as a single audit-driven sprint, or rolled into existing docs work.

## Acceptance Criteria

- [ ] All listed file/lines below have appropriate fix or `<!-- TODO: ... -->` stub left in place
- [ ] No contradictory claims between docs after fix (cross-link check)
- [ ] `python -m pytest scripts/tests/` passes (for any code-rendered sections)
- [ ] Each fix is referenced in a commit message (`docs: ...`) or rolled into a parent epic

## Related

- Skill: `/ll:audit-docs` invoked 2026-07-12 with `docs/guides/` scope
- Templates: `skills/audit-docs/templates.md` defines the finding→issue mapping used here
- Note: this issue replaces the verbose per-file/per-finding issue rollup; sub-issues should be created per-area (`FEAT-` per rewrite region) if scope grows beyond ~10 days of effort.
