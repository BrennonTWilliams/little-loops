---
id: ENH-2655
type: ENH
priority: P3
status: done
captured_at: '2026-07-15T23:07:23Z'
completed_at: '2026-07-15T23:54:20Z'
discovered_date: 2026-07-15
discovered_by: capture-issue
decision_needed: false
confidence_score: 100
outcome_confidence: 92
score_complexity: 22
score_test_coverage: 22
score_ambiguity: 25
score_change_surface: 23
---

# ENH-2655: Standardize a `.ll/` artifact directory for `/ll:spike` plan docs

## Summary

The `/ll:spike` skill writes its plan doc to an undefined `<run-artifacts>`
placeholder. Inside an FSM loop this resolves to `${context.run_dir}`, but for an
**interactive** `/ll:spike <ISSUE-ID>` invocation there is no run_dir and the skill
gives no fallback — so the model improvises (it picked `thoughts/spike-BUG-2650.md`
in a recent run). Standardize a `.ll/`-based default location instead.

## Motivation

- `<run-artifacts>` appears exactly once in `skills/spike/SKILL.md` (line 125), at
  its use site, with **no resolution rule** defined anywhere in the skill.
- Interactive spike runs have no `${context.run_dir}`, leaving the plan-doc
  location ad hoc and unpredictable.
- `thoughts/` is **not** an appropriate fallback: projects that adopt little-loops
  may not use `thoughts/` at all, and little-loops' own project-level artifacts
  (the kind a consuming project would generate) should live under `.ll/`, not
  scattered at repo root.

Note the spike **code** location is already standardized and enforced via
`allowed-tools` (`scripts/tests/spike/<slug>/`, promoted to
`scripts/little_loops/spike/<slug>/`). Only the **plan doc** location is undefined.

## Proposed Change

1. Add a new default artifact directory under `.ll/` (e.g. `.ll/spikes/`) for
   interactive spike plan docs.
2. Define `<run-artifacts>` resolution explicitly in `skills/spike/SKILL.md`:
   `${context.run_dir}` when running inside an FSM loop, else the new `.ll/`
   default when invoked interactively.
3. Ensure the directory is created on demand (no reliance on it pre-existing) and
   add an appropriate `.gitignore` decision (track vs. ignore) consistent with how
   other `.ll/` artifacts are handled.

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `skills/spike/SKILL.md:125` — Phase 3 `Write <run-artifacts>/spike-<ISSUE-ID>.md`
  use site; add the resolution rule (loop → `${context.run_dir}`, interactive →
  `.ll/spikes/`) inline here.
- `skills/spike/SKILL.md:6-16` — `allowed-tools` frontmatter. It currently grants
  only `Write(scripts/tests/spike/**)` (plus `Edit(scripts/tests/spike/**)`,
  `Edit(.issues/**)` and `Bash` prefixes). **No `Write`/`Edit` grant covers any
  `.ll/` path** — a `Write(.ll/spikes/**)` entry must be added or the interactive
  plan-doc write is denied.
- `.gitignore` — add (or deliberately omit) a `.ll/spikes/` line depending on the
  track-vs-ignore decision below.
- `skills/spike/plan-template.md` — co-located plan-doc shape referenced from Phase 3
  and the `## Related` section. Cross-check only: confirm it hardcodes no directory
  assumptions (it defines *what* goes in the file, not *where*). [Agent 2 finding]

### Resolution Rule (to document in SKILL.md Phase 3)
`run_dir` is injected only by the FSM loop-run startup path
(`scripts/little_loops/cli/loop/run.py:179`:
`fsm.context["run_dir"] = str(loops_dir / "runs" / (_pre_instance_id or loop_name)) + "/"`)
and propagated to nested slash-command child contexts
(`scripts/little_loops/fsm/executor.py:805-813`). A bare interactive `/ll:spike`
never enters `cli/loop/run.py`, so `fsm.context` — and thus `run_dir` — does not
exist. Fallback needed only for the interactive branch.

### Similar Patterns (model after)
- **Closest precedent — `.ll/learning-tests/` (`/ll:explore-api`)**:
  `skills/explore-api/SKILL.md` (Phase 3/4, ~lines 144-166, 209) creates the dir
  on demand from **inside the skill body** via `mkdir -p .ll/learning-tests/raw/`,
  writes to a `mktemp -d` scratch path first and `mv`s into place only on success,
  and the directory is **git-tracked** (curated evidence, no `.gitignore` entry).
  A spike plan doc is analogous curated evidence → this is the recommended shape.
- `scripts/little_loops/workflow_sequence/__init__.py:229-280` — `.ll/workflow-analysis/`
  created via `Path(...).parent.mkdir(parents=True, exist_ok=True)`; **gitignored**
  (`.gitignore:109`) as regenerable analysis output.
- `scripts/little_loops/file_utils.py:35` (`atomic_write_json`) auto-creates the
  parent dir; `scripts/little_loops/decisions.py:30` (`_fragments_dir`) derives a
  sibling `.d` dir name — reusable helpers if any Python touches the path.

### Tests
- `scripts/tests/test_spike_skill.py` — existing `test_spike_code_confined_to_tests_dir`
  (line 79) / `test_promotion_path_documented` (line 83) assert path strings appear
  in the skill/plan text. Add a sibling test asserting Phase 3 documents **both**
  `${context.run_dir}` and `.ll/spikes/` resolutions, and (optionally) that
  `allowed-tools` grants `Write(.ll/spikes/**)`.
- `scripts/tests/test_builtin_loops.py` (`TestSpikeGateLoop`) — no change expected;
  used to confirm the loop path is untouched.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_spike_skill.py` — **new regression-guard test**: assert the
  literal placeholder `<run-artifacts>` **no longer** appears in `SKILL_FILE.read_text()`
  once Phase 3 resolves it. Follows the exact `test_sets_spike_completed_flag` (line
  97-98) substring-`in` idiom against `SKILL_FILE.read_text()`. Guards the fix from
  silently reverting. No existing test references `<run-artifacts>` today (grep of
  `scripts/tests/` returns zero hits), so this is net-new, not an update. [Agent 3 finding]
- `scripts/tests/test_wiring_skills_and_commands.py:202-204` — advisory only: asserts
  `spike` is listed in `commands/help.md` and `.claude/CLAUDE.md`. This ENH changes
  neither listing, so no update needed — flagged so the implementer confirms the
  catalog listings stay untouched (a stray edit to the one-line spike description
  would trip it). [Agent 1 finding]
- Note: no existing structural test covers `skills/explore-api/SKILL.md`'s
  `.ll/learning-tests/` convention (no `test_explore_api*.py`), so `test_spike_skill.py`
  is the *only* precedent for skill-markdown-content assertions — model new tests on it,
  not on a learning-tests test. [Agent 3 finding]

### Documentation
- `docs/ARCHITECTURE.md` — add a `### Storage Layout` subsection for `.ll/spikes/`
  modeled on the Learning Test Registry one (`docs/ARCHITECTURE.md:1426-1451`),
  stating which component `mkdir`s it and the "gracefully skip when absent" convention.

### Cleanup Note (do not implement here)
The motivating ad-hoc artifact `thoughts/spike-BUG-2650.md` (5.5 KB, untracked)
exists on disk — the exact improvisation this issue prevents. Migrating/removing it
is a follow-up housekeeping step, not part of this ENH's scope.

## Codebase Research Findings — `.gitignore` Decision

_Added by `/ll:refine-issue` — decision point surfaced by codebase analysis:_

The two established `.ll/`-subdir postures apply here (Acceptance-Criteria item 3
asks for a track-vs-ignore decision):

**Option A**: Track `.ll/spikes/` (no `.gitignore` entry; relies on the `!/.ll/`
un-ignore at `.gitignore:132`).
> **Selected:** Option A (track `.ll/spikes/`) — the plan doc is curated evidence paired with the committed `## Spike Results` in the issue; reuses the `!/.ll/` un-ignore and `explore-api` mkdir pattern with zero new infrastructure.

Mirrors `.ll/learning-tests/` and `.ll/decisions.d/`
— treats the spike plan doc as **curated evidence** committed alongside the proven
mechanism, consistent with the closest precedent (`/ll:explore-api`).

**Option B**: Gitignore `.ll/spikes/` (add a line in the noisy-files block near
`.gitignore:108-110`). Mirrors `.ll/workflow-analysis/` and `.ll/loop-suggestions/`
— treats the plan doc as **regenerable/ephemeral** scratch that need not be committed.

**Recommended**: Option A — the plan doc is durable evidence of a retired risk
(paired with `## Spike Results` written back to the issue), directly analogous to
the learning-test registry, which is tracked.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-15.

**Selected**: Option A — Track `.ll/spikes/` (no `.gitignore` entry)

**Reasoning**: The spike plan doc is curated evidence, not regenerable scratch — the
skill appends a paired `## Spike Results`/`## Spike Findings` section back into the
git-tracked issue file (`skills/spike/SKILL.md:170-200`), so gitignoring only the
plan-doc half would create an asymmetric audit trail. Option A reuses two already-committed
precedents (`.ll/learning-tests/`, `.ll/decisions.d/`) sharing the identical `!/.ll/`
un-ignore mechanism (`.gitignore:126-132`) and the near line-for-line `mkdir`/`mktemp`/`mv`
shell pattern from `skills/explore-api/SKILL.md:144-166` — zero new infrastructure, only a
one-line `Write(.ll/spikes/**)` allowed-tools grant.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (track) | 3/3 | 3/3 | 2/3 | 3/3 | 11/12 |
| Option B (gitignore) | 1/3 | 2/3 | 2/3 | 2/3 | 7/12 |

**Key evidence**:
- Option A: Two tracked-`.ll/`-subdir precedents (`.ll/learning-tests/`, `.ll/decisions.d/`),
  both covered by the `!/.ll/` un-ignore and documented at `.gitignore:126-131`; reuse score 3.
- Option B: Two gitignored precedents (`.ll/workflow-analysis/`, `.ll/loop-suggestions/`) but
  both are standalone regenerable reports with no write-back into a tracked file — a weaker
  structural fit for a plan doc paired with committed `## Spike Results`; reuse score 1.

## Implementation Steps

- Pick + document the canonical dir name under `.ll/` (recommended: `.ll/spikes/`).
- Update `skills/spike/SKILL.md:125` (Phase 3) to define the `<run-artifacts>`
  resolution: `${context.run_dir}` inside an FSM loop, else `.ll/spikes/` interactively.
- Add `Write(.ll/spikes/**)` to `allowed-tools` (`skills/spike/SKILL.md:6-16`) — the
  interactive write is otherwise denied.
- Ensure on-demand creation (`mkdir -p .ll/spikes/` in the skill body, mirroring
  `skills/explore-api/SKILL.md`); do not assume the dir pre-exists.
- Apply the `.gitignore` decision (Option A recommended: track — no entry needed).
- Add a `test_spike_skill.py` assertion covering both resolutions (+ the allowed-tools grant).
- Confirm `spike-gate.yaml` (ENH-2641) still routes `run_dir` artifacts unchanged
  (it never references artifact paths itself — `executor.py:805-813` propagates
  `run_dir` to the child skill context, so no loop change is required).
- Add the `.ll/spikes/` `### Storage Layout` subsection to `docs/ARCHITECTURE.md`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included:_

- Add a **regression-guard** test to `scripts/tests/test_spike_skill.py` asserting the
  literal `<run-artifacts>` placeholder is gone from `SKILL.md` (alongside the positive
  `.ll/spikes/` + `${context.run_dir}` assertions already planned above).
- Cross-check `skills/spike/plan-template.md` for hardcoded directory assumptions
  (expected: none — it defines doc shape, not location).
- Confirm `scripts/tests/test_wiring_skills_and_commands.py:202-204` still passes
  unchanged (the spike catalog listing in `commands/help.md` / `.claude/CLAUDE.md`
  is untouched by this ENH).

## Acceptance Criteria

- [x] `<run-artifacts>` is explicitly defined in `skills/spike/SKILL.md` with both
  the loop (`run_dir`) and interactive (`.ll/…`) resolutions.
- [x] Interactive `/ll:spike <ID>` writes its plan doc under `.ll/`, never
  `thoughts/` or repo root.
- [x] The FSM-loop path (`${context.run_dir}`) is unchanged.
- [x] `allowed-tools` permits writing to the new location.

## Out of Scope

- Changing the spike **code** location (`scripts/tests/spike/<slug>/`) — already
  standardized and enforced.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `skills/spike/SKILL.md` | Defines `<run-artifacts>` use site (line 125) and code-location rules |

## Session Log
- `/ll:ready-issue` - 2026-07-15T23:25:09 - `6c540f7a-bb19-4d27-b451-c8f12038547f.jsonl`
- `/ll:wire-issue` - 2026-07-15T23:22:36 - `d6eae4b5-b439-4617-9ac1-9a6b401a46c6.jsonl`
- `/ll:decide-issue` - 2026-07-15T23:16:55 - `7285c640-59d1-431f-84f9-29111bbcaa9d.jsonl`
- `/ll:refine-issue` - 2026-07-15T23:12:55 - `f1f13942-9501-4084-bb65-11325b5a6c0c.jsonl`
- `/ll:capture-issue` - 2026-07-15T23:07:23Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d207819-80f4-4de9-af1a-ed38c3beaa7b.jsonl`

---

## Status

open
