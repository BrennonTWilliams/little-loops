---
id: BUG-3191
type: BUG
title: 'Doc audit sweep: medium/low findings across 14 guides (line-citation drift,
  small omissions, schema/doc mismatches)'
priority: P4
status: done
testable: false
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T17:51:50Z'
completed_at: '2026-08-15T19:31:33Z'
---

# BUG-3191: Doc audit sweep: medium/low findings across 14 guides (line-citation drift, small omissions, schema/doc mismatches)

## Summary

`/ll:audit-docs` (readme scope, 2026-08-15) fanned out one audit subagent per file across README.md and its 26 linked docs. Beyond the ~17 high-severity findings already fixed directly (and the 5 grouped into separate issues above for HISTORY_SESSION_GUIDE/EVENT-SCHEMA/BUILTIN_HOOKS_GUIDE/CLI.md+qwen-host-list/ARCHITECTURE-skills-tree), the remaining medium/low findings are collected here by file for triage. Each is independently small; grouped into one issue to avoid one-issue-per-nit sprawl.

**Scope boundary (triage pass, 2026-08-15; revised same day after a second pass).** This
issue is **doc-only, with no exceptions.** Three `config-schema.json` findings were split
into **BUG-3192** because the doc was right and the schema was wrong. All `qwen` host-list
edits belong to **BUG-3186**.

The earlier revision of this paragraph carved out the `.issues/completed/` sweep as a
deliberate non-doc exception "which necessarily touches 5 loop YAMLs." **That carve-out is
withdrawn.** On inspection none of those 5 YAMLs should be edited — the occurrences are a
guard, two defensive path-excludes, and live dual-path closure accounting. See the
re-scoped section below. If a future issue does want to retire the vestigial `completed/`
branch in `auto-refine-and-implement.yaml`, that is an ENH with a test, not a sweep item.

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
- `:101`: **owned by BUG-3186, not this issue** — every `qwen` host-list edit across all files belongs to BUG-3186. Listed here only so the line isn't touched twice; both issues edit this file within ~15 lines of each other, so leave `:101` alone here to avoid a conflict if the two run in parallel.
- `:97-98`: `--enable`/`--disable` valid-features list missing `parallel`, `documents`, `design_tokens`, `sync`, `confidence_gate`, `tdd`.
- `:86`: gitignore-entries list missing `.ll/history.db*`, `.ll/queue.db*`, `.ll/*.lock`, `.ll/ll-continue-prompt.md`, `.ll/private-refs.local.txt`, and the nested-`.ll/` stray guards.

**docs/guides/LOOPS_REFERENCE.md**
- `:919-922`: documents a `max_issues` context variable (default 100) for `sprint-refine-and-implement`; the loop YAML declares no such variable and doesn't forward it to `auto-refine-and-implement` even if set via `--context` — the knob has no effect. Confirmed 2026-08-15: `sprint-refine-and-implement.yaml:17-21` declares only `sprint_name` and `skip_learning_gate`, and the `with:` block at `:31-32` forwards neither `max_issues` nor anything else that would reach the child's own `max_issues: 100` (`auto-refine-and-implement.yaml:74`).
  - **Direction: delete the doc paragraph.** Wiring the knob is a YAML change and therefore out of scope for a doc-only sweep; it also isn't obviously wanted, since the child already caps at 100 and no one has reported wanting to override it through the sprint alias. If the knob turns out to be desirable, file it as a separate ENH against `sprint-refine-and-implement.yaml` rather than smuggling a behavior change in here.

**docs/guides/POLICY_ROUTER_GUIDE.md**
- `:391`: says the policy-table rule lives in "CLAUDE.md" — it actually lives in `HARNESS_OPTIMIZATION_GUIDE.md`'s `policy-table` row.

**docs/guides/HARNESS_OPTIMIZATION_GUIDE.md**
- `:318,331`: severity summary omits MR-12 entirely (should be "MR-1, MR-7, MR-9, MR-12 Check 1 (ERROR)" and "...MR-12 Checks 2–3... (WARNING)"), even though the rule table itself lists MR-12 correctly.
- `:432-433`: says `check_substrate` inserts "between `plan` and `research`"; canonical source (`skills/create-loop/loop-types.md:1256`) says "between `review_plan` and `research`."

**docs/guides/EXAMPLES_MINING_GUIDE.md**
- `:524`: `interpolate(state.loop, ctx)` cited at `executor.py:840` (a comment line); the real call is at `:862`.

**`.issues/completed/` references — repo-wide, not one guide**

Originally filed as an EXAMPLES_MINING_GUIDE line item; the scope was undercounted. The
path `.issues/completed/` is not created by any current code path — completed issues stay
in their type directory with `status: done` in frontmatter (never infer status from
directory location).

> **Re-scoped 2026-08-15 (second triage pass).** The first draft of this item said "fix
> all 12 occurrences in one pass; grep `issues/completed` to confirm zero remaining."
> That framing was wrong in three ways and would have caused real damage if implemented
> literally. Corrected below. **Read the do-not-touch list before editing anything.**

**Prior art: BUG-2798 ("purge `.issues/completed/` dir references") is already
`status: done`,** as are BUG-2728, BUG-2732, BUG-2733, BUG-2766, and BUG-1485 — six
closed issues in this exact area. Before editing, establish *why* residue survived that
purge. The likely answer is that the survivors are deliberate, which is what the audit
below finds. Do not re-run a sweep that has already been run without that answer.

**Do NOT edit these — each is correct as written (verified 2026-08-15):**

- `docs/development/MERGE-COORDINATOR.md:579` — **false positive.** The match is
  `my-issues/completed/file.py`, which is the *counterexample* in BUG-968's description
  of an unanchored-substring bug (`in` vs `startswith`). Editing it destroys the example
  and makes the paragraph incoherent.
- `docs/reference/CLI.md:1534` — `ll-issues fd ENH-123 --move  # Legacy: move into
  .issues/completed/`. The `--move` flag **still exists** (`--move` at
  `scripts/little_loops/cli/issues/finalize_decomposition.py:91`, threaded through as
  `move_to_completed=args.move` at `:47`). This is accurate documentation of live
  opt-in legacy behavior, correctly labeled "Legacy."
- `scripts/little_loops/loops/issue-staleness-review.yaml:66` — reads "`.issues/completed/`
  directory must not be recreated." This is a **guard against** the directory, not a
  reference to it. Removing the string removes the guard.
- `CHANGELOG.md` (7 occurrences), `.ll/decisions.yaml`, and ~130 files under `.issues/`
  are historical records. They are supposed to mention the legacy path.

**Requires a decision, not a string replacement:**

- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — 7 of the original "12
  occurrences" are here, and they are **not** a mis-scoping bug. The `init`/`finalize`
  closure accounting is a deliberate two-path union, annotated in place:
  `init` (`:88-97`) snapshots both the `completed/` set *and* the live `status: done`
  set; `finalize` (`:728-742`) diffs both. The comments cite BUG-2403 explicitly ("leaf
  issues complete IN PLACE … and never enter `.issues/completed/` — only decomposed
  parents still git-mv there. Snapshot the live done-set too so finalize can union both
  closure paths").
  The open question is whether the `completed/` half is still reachable now that
  BUG-2732 is done and `--move` is opt-in. If it isn't, the branch is vestigial and can
  be deleted — but that is a **behavior change to closure accounting**, out of scope for
  a doc sweep, and it needs its own issue with a test. Leaving it costs one empty file
  per run. **Default action: leave it, and file a separate ENH.**
- `backlog-flow-optimizer.yaml:24` and `issue-staleness-review.yaml:20` — `-not -path
  '.issues/completed/*'` exclusions. Defensive against a legacy checkout that still has
  the dir; harmless either way. Removing them is safe but gains nothing. **Default
  action: leave.**

**Actually fix — 5 cosmetic doc references, all prose/examples:**

- `docs/reference/EVENT-SCHEMA.md:845,869` — example payload `file_path` values.
- `docs/guides/EXAMPLES_MINING_GUIDE.md:420` — table row `.issues/completed/*.md`.
- `docs/guides/RECURSIVE_LOOPS_GUIDE.md:355` — `DONE_SET_ERROR` table row.
- `docs/guides/LOOPS_REFERENCE.md:941,966,994,1076` — prose describing `auto-refine-and-implement`
  closure accounting. **Note:** this prose is describing the dual-path YAML above. It should
  be corrected to describe *both* paths accurately, not to delete the `completed/` mention —
  otherwise the doc stops matching the code it documents.
- `docs/demo/scenarios.md:212` — a `cat` example. (Gitignored per `.gitignore:76`, so
  `git ls-files`-based tooling won't see it.)

**Verification.** The original AC — "grep `issues/completed` to confirm zero remaining" —
can never pass and must not be used. Scope it instead:

```bash
grep -rn "issues/completed" docs/ scripts/little_loops/loops/ \
  | grep -v "MERGE-COORDINATOR.md" \
  | grep -v "CLI.md:.*Legacy" \
  | grep -v "must not be recreated"
```

This should return only the `auto-refine-and-implement.yaml` / `LOOPS_REFERENCE.md`
dual-path lines that are deliberately retained.

**Re-priced.** This item is ~5 cosmetic doc edits, not a 12-site sweep, and it is
**not** the highest-value item in this issue — the original "treat the YAML edits as the
priority" instruction inverted the actual risk. The YAML edits are the ones most likely
to break something and least likely to be needed. Run `ll-loop validate` only if a YAML
is touched at all.

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
- No findings. Three items originally filed here (`learning_tests.enabled`, `sync.github.pull_limit`, `events.socket.max_clients`) were **split into BUG-3192** — in each case the doc text is correct and `config-schema.json` is the artifact that needs changing, so they are not doc-only work and do not belong in this sweep. Do not fix them here.

**docs/reference/COMMANDS.md**
- `:338`: `/ll:confidence-check --check` line description is inaccurate — only failing issues print the score line (with a `(below threshold)` suffix), plus aggregate `N issues not ready`/`All issues pass` lines the doc omits.
- `:944-966`: `/ll:cleanup-loops` Arguments list omits `--interrupted-age H` (default 24h).
- `:16`: `--auto` "Used by" summary table omits `decide-issue`, `wire-issue`, `go-no-go`, `scope-epic`, `review-loop`, `simplify-loop`, all of which support it per their own sections later in the same doc.

## Replace line citations with symbol anchors (amended 2026-08-15)

Four findings in this sweep are pure line-number drift:

- `AUTOMATIC_HARNESSING_GUIDE.md:1195` → `loop-types.md` Harness Questions section bounds
- `EXAMPLES_MINING_GUIDE.md:524` → `interpolate(state.loop, ctx)` in `executor.py`
- `LOOPS_GUIDE.md:1341` → `error_patterns` override in `evaluators.py`
- `LEARNING_TESTS_GUIDE.md:412` → `_SESSION_CACHE` in `learning_tests_gate.py`

**All four cited line numbers were verified correct as of 2026-08-15** — which is the
point. They drifted once and will drift again; `executor.py` alone saw 199 edits in the
trailing 7 days. Rewriting `:840` → `:862` schedules the same finding for re-discovery.

Fix them the way BUG-3188 now specifies: cite the **symbol**, not the line
(`interpolate()` in `scripts/little_loops/fsm/executor.py`; `_SESSION_CACHE` in
`scripts/little_loops/hooks/learning_tests_gate.py`; the `error_patterns` override branch
in `scripts/little_loops/fsm/evaluators.py`). For the `loop-types.md` section-bounds
citation, name the heading rather than the line range. This matches the anchor-based
reference convention from ENH-1298.

## Motivation

These are individually minor (stale line citations, small omissions, one mis-cited default) but collectively erode trust in the guides as an accurate second source alongside `--help`/code. Worth a single triage/cleanup pass.

## Impact

- **Priority**: P4 — no single item is load-bearing; several are just line-number drift.
- **Effort**: Small-Medium — many small independent edits across ~14 docs. Revised down after the second triage pass: the `.issues/completed/` item shrank from "5 loop YAMLs + 7 docs" to ~5 cosmetic doc references once the false positives and deliberate retentions were separated out.
- **Risk**: Low, and now genuinely doc-only. The earlier assessment ("apart from the string replacement in 5 loop YAMLs") no longer applies — **no loop YAML should be edited by this issue.** The three would-be YAML edits are either a guard, defensive excludes, or live dual-path closure accounting; see the do-not-touch list above.
- **Breaking Change**: No.

## Acceptance Criteria

- [ ] The four line-number citations above are replaced with symbol anchors, not corrected integers.
- [ ] The `.issues/completed/` do-not-touch list is honored: `MERGE-COORDINATOR.md:579`, `CLI.md:1534`, `issue-staleness-review.yaml:66`, `CHANGELOG.md`, and `.issues/**` are unchanged.
- [ ] No file under `scripts/little_loops/loops/` is modified by this issue.
- [ ] `LOOPS_REFERENCE.md` closure-accounting prose describes **both** closure paths (in-place `status: done` and legacy decomposed-parent move), matching `auto-refine-and-implement.yaml`.
- [ ] The scoped verification grep (above) returns only the deliberately-retained dual-path lines.
- [ ] `docs/guides/GETTING_STARTED.md:101` is untouched (owned by BUG-3186).
- [ ] The three `config-schema.json` items remain out of scope (owned by BUG-3192).


## Status

**Open** | Created: 2026-08-15 | Priority: P4
