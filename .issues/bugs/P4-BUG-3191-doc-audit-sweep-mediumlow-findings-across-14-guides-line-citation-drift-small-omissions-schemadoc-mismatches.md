---
id: BUG-3191
type: BUG
title: 'Doc audit sweep: medium/low findings across 14 guides (line-citation drift,
  small omissions, schema/doc mismatches)'
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T17:51:50Z'
---

# BUG-3191: Doc audit sweep: medium/low findings across 14 guides (line-citation drift, small omissions, schema/doc mismatches)

## Summary

`/ll:audit-docs` (readme scope, 2026-08-15) fanned out one audit subagent per file across README.md and its 26 linked docs. Beyond the ~17 high-severity findings already fixed directly (and the 5 grouped into separate issues above for HISTORY_SESSION_GUIDE/EVENT-SCHEMA/BUILTIN_HOOKS_GUIDE/CLI.md+qwen-host-list/ARCHITECTURE-skills-tree), the remaining medium/low findings are collected here by file for triage. Each is independently small; grouped into one issue to avoid one-issue-per-nit sprawl.

## Findings by file

**docs/ARCHITECTURE.md**
- `:24` vs `:64`: mermaid diagram says "29 slash commands" (correct, matches `commands/*.md`); Directory Structure prose says "28 slash command templates" (stale). Fix the prose line to 29.

**docs/codex/getting-started.md**
- `:45`: "registers four hooks" undercounts — `hooks/adapters/codex/hooks.json` registers 6 handler entries (adds `drift-check.sh` under SessionStart, `edit-batch-nudge.sh` under PostToolUse).
- `:62-67`: trust-key list missing `session_start:1:0` and `post_tool_use:1:0` entries for the above.
- `:114`: "exercises all four adapter scripts" — `test_adapter_files_exist` actually checks five (adds `drift-check.sh`); `edit-batch-nudge.sh` isn't covered by that test at all.

**docs/guides/AUTOMATIC_HARNESSING_GUIDE.md**
- `:1195`: "Harness Questions section (lines 549–1046)" in `skills/create-loop/loop-types.md` — actual section runs 549–1185 (next `##` heading at 1186).

**docs/guides/DECISIONS_LOG_GUIDE.md**
- `:523`: claims `decisions.enabled` gates automation's `decision_needed` pause — neither `ll-auto` nor `ll-parallel` actually reads that config key; the gate fires purely off frontmatter regardless.
- `:582`: "Loops Guide" link for the decision gate should point to `LOOPS_REFERENCE.md` (has the actual `check_decision_needed`/`resolve_decision` content), not `LOOPS_GUIDE.md`.
- `:202-207`: signal-phrase list missing `"resolve before starting"` and `"open question"` (present in `_DECISION_NEEDED_PHRASES`).
- `:190`: Phase 7b says it "appends DecisionEntry to `.ll/decisions.yaml`" — actually writes a `.ll/decisions.d/<uuid4>.json` fragment.
- `:447`: `[high-signal]` tag description says it requires "3+ decisions sharing common tokens" — actually purely a `len(cat_entries) >= 3` count; shared tokens aren't required.

**docs/guides/GETTING_STARTED.md**
- `:101`: `--hosts` row omits `qwen` from the fully-wired list (see also the dedicated qwen-host-list issue for CLI.md/CONFIGURATION.md/HARNESS_OPTIMIZATION_GUIDE.md).
- `:97-98`: `--enable`/`--disable` valid-features list missing `parallel`, `documents`, `design_tokens`, `sync`, `confidence_gate`, `tdd`.
- `:86`: gitignore-entries list missing `.ll/history.db*`, `.ll/queue.db*`, `.ll/*.lock`, `.ll/ll-continue-prompt.md`, `.ll/private-refs.local.txt`, and the nested-`.ll/` stray guards.

**docs/guides/LOOPS_REFERENCE.md**
- `:919-922`: documents a `max_issues` context variable (default 100) for `sprint-refine-and-implement`; the loop YAML declares no such variable and doesn't forward it to `auto-refine-and-implement` even if set via `--context` — the knob has no effect.

**docs/guides/POLICY_ROUTER_GUIDE.md**
- `:391`: says the policy-table rule lives in "CLAUDE.md" — it actually lives in `HARNESS_OPTIMIZATION_GUIDE.md`'s `policy-table` row.

**docs/guides/HARNESS_OPTIMIZATION_GUIDE.md**
- `:318,331`: severity summary omits MR-12 entirely (should be "MR-1, MR-7, MR-9, MR-12 Check 1 (ERROR)" and "...MR-12 Checks 2–3... (WARNING)"), even though the rule table itself lists MR-12 correctly.
- `:432-433`: says `check_substrate` inserts "between `plan` and `research`"; canonical source (`skills/create-loop/loop-types.md:1256`) says "between `review_plan` and `research`."

**docs/guides/EXAMPLES_MINING_GUIDE.md**
- `:63,190,415` and the underlying `examples-miner.yaml` judge prompt: reference `.issues/completed/`, which doesn't exist — completed issues stay in their type dir with `status: done` in frontmatter.
- `:524`: `interpolate(state.loop, ctx)` cited at `executor.py:840` (a comment line); the real call is at `:862`.

**docs/guides/LOOPS_GUIDE.md**
- `:1341`: `error_patterns` override behavior cited at `evaluators.py:455-465`; actual logic is at `:466-474`.

**docs/guides/SPRINT_GUIDE.md**
- `:179-186`: describes `/ll:review-sprint` as a flat "six-phase analysis" {staleness, priority drift, dependency cycles, file contention, backlog scan, removal proposals}; the actual skill has Phase 1 Load & Health Check, Phase 2 Backlog Scan, Phase 3 Analysis (3a-3f: Staleness/Goal Coherence/Priority Drift/Backlog Opportunities/Wave Optimization/EPIC Context), Phase 4 Recommendations, Phase 5 Approval, Phase 6 Apply — Goal Coherence and Wave Optimization are omitted from the doc entirely.

**docs/guides/ISSUE_MANAGEMENT_GUIDE.md**
- `:176-178`: `--parent EPIC-NNN` description says linking does two things atomically (sets `parent:`, adds to `## Children`); it also updates the EPIC's `relates_to:` list (per `skills/capture-issue/SKILL.md:53`) — a third, undocumented effect.

**docs/guides/LEARNING_TESTS_GUIDE.md**
- `:412`: `_SESSION_CACHE` cited at `learning_tests_gate.py:42`; actual line is `:46`.
- `:297`: `learning-tests-audit` loop report path described as fixed `.loops/runs/learning-tests-audit/report-<timestamp>.md`; `context.run_dir` actually resolves to a per-run `.loops/runs/<loop>-<run-timestamp>/` directory.

**docs/reference/CONFIGURATION.md**
- `:897,909-921`: doc's `learning_tests.enabled` default (`false`) is correct against the dataclass but conflicts with `config-schema.json`'s declared `"default": true` — worth flagging as a schema/doc mismatch even though the doc text itself is right.
- `:720`: `sync.github.pull_limit` is documented and real in code but absent from `config-schema.json`'s `sync.github` properties (which has `additionalProperties: false`) — schema would reject the documented key.
- `:1466`: doc's `events.socket.max_clients` default of 32 is correct against code; `config-schema.json` declares `"default": 8` — schema is stale, not the doc.

**docs/reference/COMMANDS.md**
- `:338`: `/ll:confidence-check --check` line description is inaccurate — only failing issues print the score line (with a `(below threshold)` suffix), plus aggregate `N issues not ready`/`All issues pass` lines the doc omits.
- `:944-966`: `/ll:cleanup-loops` Arguments list omits `--interrupted-age H` (default 24h).
- `:16`: `--auto` "Used by" summary table omits `decide-issue`, `wire-issue`, `go-no-go`, `scope-epic`, `review-loop`, `simplify-loop`, all of which support it per their own sections later in the same doc.

## Motivation

These are individually minor (stale line citations, small omissions, one mis-cited default) but collectively erode trust in the guides as an accurate second source alongside `--help`/code. Worth a single triage/cleanup pass.

## Impact

- **Priority**: P4 — no single item is load-bearing; several are just line-number drift.
- **Effort**: Medium — many small independent edits across ~14 files.
- **Risk**: None — doc-only changes.


## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]
