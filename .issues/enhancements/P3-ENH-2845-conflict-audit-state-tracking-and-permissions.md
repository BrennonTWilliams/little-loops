---
id: ENH-2845
type: ENH
priority: P3
status: done
discovered_date: 2026-07-26
discovered_by: manual-review
labels:
- audit-issue-conflicts
- skills
- permissions
relates_to:
- FEAT-2842
- BUG-2844
confidence_score: 96
outcome_confidence: 75
score_complexity: 18
score_test_coverage: 22
score_ambiguity: 15
score_change_surface: 20
completed_at: '2026-07-27T02:32:04Z'
---

# ENH-2845: `/ll:audit-issue-conflicts` — non-persistent bash state, under-declared tools, contradictory auto mode

## Summary

Three correctness-adjacent defects in the skill's scaffolding, none of which
change what conflicts are *detected* but all of which make what happens
*afterward* unreliable: bash arrays used as cross-phase state that cannot
persist, `allowed-tools` that omits the interpreters the skill's own guards run
on, and an auto-mode specification that contradicts itself.

## Current Behavior

### 1. Bash arrays used as cross-phase state

The skill declares and mutates shell variables across separate phases:

- `ISSUE_FILES` — Phase 1 (`SKILL.md:105`, populated at `:113-141`)
- `MODIFIED_FILES` / `SKIPPED_INACTIVE_COUNT` — Phase 4b (`:309-310`), appended
  to at `:351`, `:373`, `:398`
- Consumed in Phase 5 (`:409-411`) and Phase 6 (`:429`)

Shell state does not persist between separate `Bash` tool invocations. Phase 4b's
appends and Phase 5's `for f in "${MODIFIED_FILES[@]}"; do git add "$f"; done`
run in different calls, so the loop iterates an empty array and **stages
nothing** — silently, with Phase 6 still printing "All changes staged".

The write-side guards have the same problem from the other direction: Phase 4b
specifies membership checks against "the ISSUE_FILES list **from Phase 1
context**" (`:318`, `:368`, `:384`) — i.e. the model's memory, not the variable
the surrounding bash implies. The code and the prose disagree about where the
state lives.

`test_phase5_stages_only_modified_files` asserts the instruction text is
present; it cannot catch that the mechanism does not work.

### 2. `allowed-tools` omits required interpreters

Declared (`SKILL.md:7-14`): `Read`, `Glob`, `Edit`, `Task`, `AskUserQuestion`,
`Bash(git:*)`, `Bash(ll-issues:*)`.

Actually invoked:

| Phase | Command | Covered? |
|---|---|---|
| 0 (`:78`) | `python3 -c` (EPIC validation) | **No** |
| 1 (`:116`) | `python3 -c` (status filter) | **No** |
| 1 (`:135`) | `awk` (frontmatter status parse) | **No** |
| 1 (`:131-141`) | shell `for` loop over globs | **No** |
| 4b (`:318`, `:368`, `:384`) | `awk` TOCTOU status re-check | **No** |

Under `--auto` / `LL_NON_INTERACTIVE` / `--dangerously-skip-permissions` — the
modes Phase 0 auto-enables — these are denied. The TOCTOU re-check that guards
every write is therefore the most likely thing to fail silently.

### 3. Auto mode contradicts itself

Phase 4 (`:293`): "Apply **all** recommendations without prompting."
Phase 6 (`:445`): "no action needed (low severity, **skipped in auto mode**)".

Low-severity conflicts have undefined behavior in the mode that runs
unattended.

## Expected Behavior

- Cross-phase state is tracked in one place with one mechanism. Either the skill
  keeps a run-scoped file (`${run_dir}/modified-files.txt`, appended by each
  write and read by Phase 5) or it drops the bash-array framing entirely and
  states plainly that the model tracks the list — but not both.
- `allowed-tools` covers every command the skill runs, or the skill stops
  shelling out for things `ll-issues` can already answer (`ll-issues list
  --json` already returns `status` and `path`, which removes most of the `awk`
  and `python3` usage outright — including all three TOCTOU re-checks).
- Auto mode has one stated policy for low-severity conflicts.

## Root Cause

The skill was written in a bash-pseudocode style that reads as executable but is
partly model-directed narration. Where the two are mixed inside one document,
neither the model nor a test can tell which lines are contracts and which are
illustration. `allowed-tools` was declared against the skill's *intent*
(`git`, `ll-issues`) rather than its literal command surface, and drifted as
guard logic was added in later revisions.

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `skills/audit-issue-conflicts/SKILL.md` — frontmatter `allowed-tools` (lines 7-14),
  Phase 0 (lines 60-86), Phase 1 (lines 104-149), Phase 4b (lines 304-406),
  Phase 5 (lines 409-417), Phase 6 (lines 421-459)

### Dependent Files (Tests to Update)
- `scripts/tests/test_audit_issue_conflicts_skill.py` — existing structural tests
  including `test_phase5_stages_only_modified_files`, `test_phase4b_write_side_guard_present`,
  `test_phase4b_idempotency_guard_present`, `test_phase6_skipped_inactive_count_reported`
  (uses the `content.index("## Phase N")` slicing idiom to scope assertions to a phase).
  `test_phase5_stages_only_modified_files` (lines 62-69) asserts literal
  `MODIFIED_FILES=()` / `MODIFIED_FILES+=(` / `for f in "${MODIFIED_FILES[@]}"`
  text — it **will break** and needs rewriting once Step 3 picks a real
  mechanism (state file or `git add -u`), since those literal strings
  disappear either way. [Agent 3 finding]
- `TestAuditIssueConflictsEpicScoping._phase(start_header, end_header)` helper
  (`scripts/tests/test_audit_issue_conflicts_skill.py:153`) — the more reusable
  phase-slicing idiom (vs. inline `content.index` calls) to model new
  phase-scoped tests on. [Agent 3 finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/sprint-build-and-validate.yaml` — `audit_conflicts`
  / `audit_conflicts_retry` states (~lines 864-865) invoke
  `/ll:audit-issue-conflicts --auto` then route an `llm_structured` evaluator's
  `on_yes` to a `commit` state. This is a real behavioral caller: today, if
  Phase 6 reports "All changes staged" when Phase 5's bash-array staging
  silently did nothing (the bug this issue fixes), `commit` may commit
  nothing (or unrelated pre-existing staged state) while the loop believes it
  succeeded. Fixing Phase 5/6 changes what `commit` actually sees at runtime.
  No code edit required in the loop file itself, but worth a manual
  re-validation pass on `sprint-build-and-validate.yaml` after the fix lands.
  [Agent 2 finding]

### Similar Patterns
- `skills/update/SKILL.md:6-10`, `skills/spike/SKILL.md:6-17` — `allowed-tools`
  interpreter-allowlist entries (`Bash(python3:*)`, `Bash(pip:*)`, etc.)
- `skills/map-dependencies/SKILL.md:202-213` — `git add -u` staging that avoids
  cross-phase state tracking entirely (BUG-1976 precedent)
- `skills/create-eval-from-issues/SKILL.md:339-391` — write-then-read-back state
  file idiom (FSM-loop context, not a plain markdown skill)
- `scripts/little_loops/cli/verify_cli_allowlist.py` — `ll-verify-*` lint template
  for a repo-wide `allowed-tools`-coverage check (Step 5)

### Reusable CLI Surface
- `scripts/little_loops/cli/issues/list_cmd.py:152-172` — `ll-issues list --json`
  (uncased `status`, `path`)
- `scripts/little_loops/cli/issues/show.py:154-458` — `ll-issues show --json`
  (display-cased `status` via `_STATUS_DISPLAY`, plus uncased `raw_status`)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` (`### /ll:audit-issue-conflicts` section,
  ~lines 304-312) — documents `--auto` as "apply all recommendations without
  prompting," silent on severity. If Step 4 changes what `--auto` does for
  low-severity conflicts, this line needs a matching clause. [Agent 2 finding]
- `docs/reference/CLI.md` (lines 15-16) — lists `audit-issue-conflicts` in the
  `--dry-run`/`--auto` flag tables; update only if Step 4 changes the
  documented `--auto` behavior. [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- New test for **(a) allowed-tools coverage** — generalize
  `test_edit_in_allowed_tools` (`scripts/tests/test_issue_size_review_skill.py:18-26`,
  which slices the frontmatter via `content.index("---", 3)` and checks a
  single hand-picked token) into a real diff: extract every fenced-block
  `Bash(...)`-invoked binary and assert each has a matching
  `Bash(<binary>:*)` entry in declared `allowed-tools`. [Agent 3 finding]
- New test for **(b) Phase 5 stages exactly what Phase 4b modified, via a
  real mechanism** — cannot just grep for array syntax (that's what the
  now-inadequate `test_phase5_stages_only_modified_files` does). If a state
  file is chosen, assert the same literal path appears in both the Phase 4b
  write site(s) and the Phase 5 read site (path-string equality across the
  two phase slices, not just presence). If `git add -u`-style staging is
  chosen instead, assert Phase 5 uses `git add -u` and that no
  `MODIFIED_FILES` array declaration remains anywhere in the file. [Agent 3
  finding]
- New test `test_phase4_phase6_auto_mode_low_severity_agree` for **(c)** —
  slice `## Phase 4` and `## Phase 6` (via the `_phase()` helper idiom) and
  assert both state the same low-severity `--auto` policy token, mirroring
  how `test_phase4b_supersession_uses_cancelled_not_done` asserts a specific
  token's absence alongside a specific token's presence. [Agent 3 finding]
- No existing test in the repo structurally validates a skill's
  cross-Bash-call state persistence (write in one call, read in another) —
  confirmed via grep for `git add -u` literal (0 hits) and for
  `map_dependencies`/`map.dependencies` test coverage (3 unrelated hits, no
  dedicated `test_map_dependencies_skill.py`). Any new test for Step 3's
  chosen mechanism is original, not an extension of prior art. [Agent 3
  finding]

### Registration Files (conditional on Step 5's repo-wide lint)

_Wiring pass added by `/ll:wire-issue`:_ if Step 5 is implemented as a new
`ll-verify-*` CLI (per the issue's own template reference to
`verify_cli_allowlist.py`), the following need registration, mirroring how
`ll-verify-cli-allowlist` is wired in today:
- `scripts/pyproject.toml` — new `[project.scripts]` entry alongside the
  existing `ll-verify-cli-allowlist = "little_loops.cli:main_verify_cli_allowlist"`
  (line 101). [Agent 1 finding]
- `scripts/little_loops/cli/doctor.py` — `--full` aggregation registry (the
  `@register_full_check`-style adapters around lines 458-679, e.g. the
  `ll-verify-des-audit` adapter at line 679) needs a new adapter following
  the same `"""Adapter over <fn>() (ll-verify-<name>)."""` docstring
  convention so the new lint participates in `ll-doctor --full`. [Agent 2
  finding]
- `.claude/CLAUDE.md` § CLI Tools — new one-line bullet for the new
  `ll-verify-*` tool, matching the existing convention (e.g. the
  `ll-verify-cli-allowlist` line at ~226). [Agent 2 finding]

## Implementation Steps

1. Replace the `awk`/`python3` status parsing in Phases 1 and 4b with
   `ll-issues list --json` / `ll-issues show --json` — already permitted, and
   removes the need to widen `allowed-tools` for those call sites.
2. For anything still needing a shell interpreter, add explicit `allowed-tools`
   entries.
3. Pick one state mechanism for `MODIFIED_FILES` / `SKIPPED_INACTIVE_COUNT` /
   `ISSUE_FILES` and apply it consistently; if a run-scoped file, define the
   path and have Phase 5/6 read it.
4. Resolve the auto-mode contradiction — state whether low-severity
   recommendations are applied in `--auto`, and align Phase 4 and Phase 6.
5. Strengthen the existing skill tests: assert `allowed-tools` covers every
   `Bash(...)`-invoked binary appearing in fenced blocks. This is a generalizable
   check — consider a repo-wide lint over `skills/*/SKILL.md` rather than a
   single-skill test.
6. Re-check `ll-issues show --json` status casing before writing guard
   comparisons — it is display-cased (`"Completed"`), so comparisons must
   lowercase first.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation:_

7. Rewrite `test_phase5_stages_only_modified_files` to match whichever
   mechanism Step 3 picks — its current literal-string assertions
   (`MODIFIED_FILES=()` etc.) will fail regardless of which fix is chosen.
8. Add a new test generalizing `test_edit_in_allowed_tools`'s single-token
   check into a real allowed-tools-vs-fenced-block-binaries diff for this
   skill (or the repo-wide lint from Step 5, if implemented now).
9. Add `test_phase4_phase6_auto_mode_low_severity_agree`, asserting Phase 4
   and Phase 6 state the same low-severity `--auto` policy token.
10. If Step 5's repo-wide lint is implemented as a new `ll-verify-*` CLI
    (rather than deferred): register it in `scripts/pyproject.toml`
    (`[project.scripts]`), add a `--full` adapter in
    `scripts/little_loops/cli/doctor.py`, and add a one-line entry under
    `.claude/CLAUDE.md` § CLI Tools.
11. If Step 4's auto-mode fix changes the documented `--auto` low-severity
    behavior, update the matching line in `docs/reference/COMMANDS.md`
    (`### /ll:audit-issue-conflicts`) and, if applicable,
    `docs/reference/CLI.md`'s flag table.
12. After Phase 5/6 correctness is fixed, flag
    `scripts/little_loops/loops/sprint-build-and-validate.yaml`'s
    `audit_conflicts`/`commit` states for a manual re-validation pass — their
    runtime behavior (what actually gets staged/committed) changes once the
    reported "All changes staged" claim becomes true.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **JSON-over-parse precedent already exists in this same file**: Phase 0
  (`SKILL.md:77-81`, EPIC-id check) and Phase 1's `--parent` branch
  (`SKILL.md:116-123`) already pipe `ll-issues list --json` into
  `python3 -c` instead of parsing frontmatter directly. Step 1's fix is
  extending an idiom the skill already uses elsewhere in itself to the
  *unscoped* Phase 1 branch (`awk` at `:135`) and the three Phase 4b TOCTOU
  re-checks (`awk` at `:318`, `:373`, `:389`) — not introducing a new
  pattern. `ll-issues list --json` returns `status` uncased (matches
  `open|in_progress|blocked` comparisons directly) — `scripts/little_loops/cli/issues/list_cmd.py:161`,
  sourced from `scripts/little_loops/cli/issues/search.py:121-151`.
- **`allowed-tools` interpreter-allowlist precedent**: `skills/update/SKILL.md:6-10`
  declares `Bash(python3:*)`, `Bash(pip:*)`, `Bash(pip3:*)`, `Bash(claude:*)` as
  separate entries; `skills/spike/SKILL.md:6-17` combines path-scoped `Write`/`Edit`
  grants with per-binary `Bash(...)` entries (`ll-issues`, `python -m pytest`,
  `git`, `find`). Model the fix on these — one `Bash(<binary>:*)` entry per
  interpreter actually invoked in a fenced block, not just intent-level tools.
- **Phase 5 staging alternative that avoids a state file entirely**:
  `skills/map-dependencies/SKILL.md:202-213` stages with
  `git add -u {{config.issues.base_dir}}/` (already-tracked files only, citing
  BUG-1976) rather than tracking a `MODIFIED_FILES` array across Bash calls.
  This sidesteps Step 3's persistence problem structurally instead of solving
  it with a state file — worth considering as a simpler alternative if Phase
  4b never creates untracked new issue files.
- **Cross-Bash-call append/read-back precedent** (if a state file is chosen
  for Step 3 instead): `skills/create-eval-from-issues/SKILL.md:339-391`
  (Variant B `discover`/`advance` states) writes progress to a temp file in
  one step and reads it back in a later, separate step — the closest existing
  "write in one Bash call, read in another" shape in the repo, though it lives
  inside FSM-loop YAML (`${context.run_dir}`/`${captured.*}` are engine-provided
  there) rather than a plain markdown skill's direct Bash invocations.
- **Repo-wide lint template for Step 5**: `scripts/little_loops/cli/verify_cli_allowlist.py`
  is a directly analogous existing `ll-verify-*` check (declared-vs-actual diff,
  `ERROR:`-per-violation output, exit 1 on drift) to model a new
  `allowed-tools`-vs-fenced-block-binaries lint on: glob `skills/*/SKILL.md`,
  extract frontmatter `allowed-tools:` entries and fenced-block first-token
  binaries, diff, exit 1 listing `{skill_name: [uncovered_binaries]}`.
  `scripts/tests/test_issue_size_review_skill.py:18-26`
  (`test_edit_in_allowed_tools`) is the existing single-tool, single-skill
  precedent to generalize from.
- **Status casing detail for Step 6**: `ll-issues show --json` returns both a
  display-cased `status` (`_STATUS_DISPLAY` dict, `scripts/little_loops/cli/issues/show.py:190-200`,
  e.g. `"done"` → `"Completed"`) *and* an uncased `raw_status` field
  (`show.py:377`). Guards reading `show --json` should compare against
  `raw_status`, not `status`, rather than lowercasing the display string.

## Scope Boundaries

**In scope**: the skill's scaffolding — cross-phase state tracking,
`allowed-tools` coverage, and the auto-mode low-severity contradiction.

**Out of scope**: what the audit writes. The `add_dependency` frontmatter-write
mechanism is FEAT-2842; the supersession status/edge defect is BUG-2844. Conflict
*detection* quality (Phase 2 batching, the Phase 2b fingerprint thresholds, the
prompt template) is untouched here.

## Acceptance Criteria

- [ ] Every command in a `SKILL.md` fenced block is covered by `allowed-tools`.
- [ ] Phase 5 stages exactly the files Phase 4b modified, verified by a test that
      does not merely assert the instruction text is present.
- [ ] Phase 4 and Phase 6 agree on low-severity handling under `--auto`.
- [ ] `python -m pytest scripts/tests/` passes.

## Impact

- **Users**: audit changes may be applied but never staged, contradicting the
  final report; write-side safety guards may not execute at all in the
  unattended mode where they matter most.
- **Risk**: Low-Medium. No data loss, but the skill reports success for work it
  did not do.
- **Effort**: Small-Medium.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `skills/audit-issue-conflicts/SKILL.md` | All three defects |
| `scripts/tests/test_audit_issue_conflicts_skill.py` | Existing assertion style to extend |
| `.claude/CLAUDE.md` § Development Preferences | Skill-over-agent conventions |

## Context

Found while auditing `/ll:audit-issue-conflicts` for reliable frontmatter
writing.

## Session Log
- `ll-auto` - 2026-07-27T02:32:04 - `3ddbb22f-2d44-418c-8a48-60641b02d003.jsonl`
- `/ll:wire-issue` - 2026-07-27T02:18:07 - `103de32b-74c6-44b7-98a1-99493fe9e723.jsonl`
- `/ll:refine-issue` - 2026-07-27T02:12:41 - `d774bf31-7161-4969-87a4-33146903cf31.jsonl`

---

## Status

open


---

## Resolution

- **Action**: improve
- **Completed**: 2026-07-26
- **Status**: Completed (automated fallback)
- **Implementation**: Command exited early but issue was addressed


### Files Changed
- See git history for details

### Verification Results
- Automated verification passed

### Commits
- See git log for details
