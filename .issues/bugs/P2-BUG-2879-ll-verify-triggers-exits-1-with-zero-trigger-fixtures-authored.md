---
id: BUG-2879
title: "ll-verify-triggers exits 1 \u2014 zero skills declare trigger_fixtures"
type: BUG
priority: P2
status: done
captured_at: '2026-07-28T02:07:33Z'
completed_at: '2026-07-28T03:24:12Z'
discovered_date: 2026-07-28
labels:
- skills
- verification
relates_to:
- FEAT-1910
- FEAT-2795
- ENH-2884
decision_needed: false
learning_tests_required:
- yaml
confidence_score: 100
outcome_confidence: 75
score_complexity: 15
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 18
---

# BUG-2879: ll-verify-triggers exits 1 — zero skills declare trigger_fixtures

## Summary

`ll-verify-triggers` reports **0% precision and 0% recall for every one of the 40
model-invocable skills** and exits 1. The cause is not a scoring defect: **no
`SKILL.md` or `commands/*.md` file in the repo declares a `trigger_fixtures`
frontmatter block at all.** FEAT-1910 (Completed) built the validation harness,
but the fixture data it consumes was never authored, so the gate has been
failing-closed on empty input since it landed.

## Current Behavior

```
$ grep -rl "trigger_fixtures" skills/ commands/ | wc -l
0

$ ll-verify-triggers ; echo "exit=$?"
Skill Trigger Validation Report
Thresholds: precision ≥ 50%, recall ≥ 50%
adversarial-verify-loop     0%    0%
analyze-history             0%    0%
... (all 40 skills at 0% / 0%)
No cross-skill collisions detected.
exit=1
```

`_load_trigger_fixtures(skill_md_path)` (`cli/verify_triggers.py:218`) returns
`None` whenever the frontmatter has no `trigger_fixtures` key, or when both
`should_fire` and `should_not_fire` are empty (line 260). Every skill takes that
path, so `skill_fixtures` (line 371) is populated for zero skills and every score
degenerates to 0%.

Two downstream consequences:

1. **The gate is inert as a regression detector.** A genuinely mis-triggering
   skill description is indistinguishable from the current all-zero baseline.
2. **`No cross-skill collisions detected.` is not trustworthy.**
   `_detect_collisions()` (line 330) works by finding a phrasing that matches
   more than one skill description — with zero phrasings loaded, it has nothing
   to test and reports clean by construction. This surfaced during the ENH-2877
   skill-merge audit, where the collision result had to be discounted as weak
   evidence for exactly this reason.

## Steps to Reproduce

From a clean checkout of this repo:

1. Confirm no fixtures exist anywhere in the skill/command surface:
   ```bash
   grep -rl "trigger_fixtures" skills/ commands/ | wc -l
   # → 0
   ```
2. Run the gate and capture its exit code:
   ```bash
   ll-verify-triggers ; echo "exit=$?"
   # → every skill reports 0% precision / 0% recall
   # → "No cross-skill collisions detected."
   # → exit=1
   ```
3. Observe that a skill scoring 0% because it has *no fixtures* is presented
   identically to one that has fixtures and genuinely mis-triggers.

**Frequency**: Deterministic — every invocation, on any checkout.

## Expected Behavior

Either the fixtures exist and the gate measures something, or the gate reports
honestly that it has no data — not a hard failure that looks like 40 broken
skills.

- `ll-verify-triggers` exits 0 on a healthy tree.
- A skill with no `trigger_fixtures` is reported as **unmeasured**, distinct from
  a skill that has fixtures and scores 0%.
- The exit code reflects real threshold violations among skills that actually
  have fixtures.
- `_detect_collisions()` either has phrasings to work with, or states that it was
  skipped for lack of input rather than printing a clean bill of health.

## Motivation

`ll-verify-triggers` is part of the `ll-verify-*` family that FEAT-2795
aggregates into `ll-doctor --full`. A member of that family that always exits 1
either fails the aggregate for every consumer or has been quietly special-cased
— both are bad. Whichever it is should be established as part of this fix.

Beyond the exit code, this is a **completed-issue outcome gap**: FEAT-1910 is
marked done, and by the letter of its acceptance criteria it probably is (the
harness works). But the capability it was meant to deliver — knowing whether
skill descriptions route correctly — does not exist, and nothing surfaced that.

## Proposed Solution

Two separable parts; both are needed, and the first is the actual bug.

**Part 1 — fix the no-fixture reporting contract (the bug).**
Distinguish "unmeasured" from "scored 0%" in `cli/verify_triggers.py`. Skills
with no `trigger_fixtures` are excluded from the pass/fail computation and
reported in a separate `unmeasured` section with a count. Exit 1 only when a
skill that *has* fixtures falls below threshold. Add a coverage line
(`N/40 skills have fixtures`) so the gap is visible instead of disguised as
uniform failure. Gate `_detect_collisions()`'s clean-result message on having
had any phrasings to test.

**Part 2 — author fixtures.**
Populate `trigger_fixtures` for the model-invocable skills. This is data entry
against the `should_fire` / `should_not_fire` shape already parsed at
`verify_triggers.py:254-255`, and can land incrementally once Part 1 stops
treating absence as failure. Prioritize skills whose descriptions are most
likely to collide — the issue-refinement cluster (`refine-issue`, `wire-issue`,
`reconcile-issue`, `format-issue`) and the loop cluster (`create-loop`,
`review-loop`, `simplify-loop`, `debug-loop-run`, `audit-loop-run`).

Splitting Part 2 into its own follow-up issue is reasonable if it proves large;
Part 1 must not wait on it.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Scope correction — the gate scores 71 skills, not 40, and does not filter
model-invocability.** `_load_skill_descriptions()`
(`scripts/little_loops/cli/verify_triggers.py:274`) globs `skills/*/SKILL.md`
and keeps every skill whose frontmatter carries a non-empty `description`. It
applies **no** `disable-model-invocation` filter. Measured on the current tree:
71 skill dirs, all 71 with a description → all 71 scored at 0%/0%; only **19**
are model-invocable (52 carry `disable-model-invocation: true`). `--json`
confirms `len(skills) == 71`. The issue's "40 model-invocable skills" figure is
wrong in both directions and should not be used to size Part 2.

This raises a scoping decision Part 1 must settle, because it changes Part 2's
workload by ~3.7×:

> **Selected:** Option A — filters `_load_skill_descriptions()` to model-invocable skills, matching the codebase's established skip-`disable-model-invocation` precedent and yielding an actionable N/19 coverage target instead of a permanently-unreachable N/71.

**Option A**: Filter the population to model-invocable skills. Reuse
`_is_model_invocation_disabled()` (`scripts/little_loops/adapters/core.py:104`)
inside `_load_skill_descriptions()` so `disable-model-invocation: true` skills
are never loaded, scored, or counted in coverage. Coverage then reads
`N/19`. Precedent for exactly this filter exists in three places:
`doc_counts.py:350` and `:399`, and `generate_skill_descriptions.py:110`.
Trigger accuracy is meaningless for a skill the model can never auto-invoke, so
these are noise in both the score table and the coverage denominator.

**Option B**: Keep scoring all 71 and rely solely on the unmeasured/scored split
from Part 1. Model-uninvocable skills simply land in the `unmeasured` bucket
because they have no fixtures, so the exit code is already correct without a
population change. Coverage reads `N/71` and honestly reports that most skills
carry no fixtures.

**Recommended**: Option A — the unmeasured bucket in Option B conflates two
different things ("has no fixtures yet, should get them" vs. "can never be
model-invoked, will never need them"), which reintroduces the exact
indistinguishability this bug is about, one level up. Option A also makes the
`N/19` coverage line an actionable Part 2 backlog rather than a permanently
unreachable `N/71`.

**`ll-doctor --full` does not special-case this gate — it fails today** (answers
Implementation Step 2). `_full_triggers_data()`
(`scripts/little_loops/cli/doctor.py:531-558`) calls `_run_validation()` /
`_any_failures()` directly (not via subprocess), and on failure returns
`{"status": "unsupported", "severity": "error"}`. Under FEAT-2795's
error/warn severity split, `severity: "error"` fails the aggregate exit code.
The only exemption is `severity: "informational"`, used when `skills/` is
absent entirely (line 539) — which never applies in this repo. So the
"quietly special-cased" alternative in the Motivation section is ruled out:
`ll-doctor --full` has been failing on this gate. Confirmed empirically on the
current tree:

```
$ ll-doctor --full 2>&1 | grep -i 'trigger'
  ✓  ll-verify-triggers
  ✗  triggers  one or more skills below threshold or collisions detected
$ ll-doctor --full >/dev/null 2>&1 ; echo $?
1
```

(The `✓ ll-verify-triggers` line is the entry-point-presence check, a separate
concern from the `✗ triggers` gate result.) A useful acceptance criterion falls
out of this: `ll-doctor --full` exits 0 after Part 1 lands. Because doctor imports the
internals rather than shelling out, any Part 1 refactor of `_run_validation()`'s
return shape or `_any_failures()`'s signature must update doctor.py in the same
change.

**`commands/*.md` are never scanned.** Only `skills/*/SKILL.md` is globbed
(line 285). The `grep -rl trigger_fixtures skills/ commands/` in Steps to
Reproduce is fine as a reproduction, but fixtures placed under `commands/`
would be silently ignored — Part 2 authoring belongs in `skills/*/SKILL.md`
only, as the Integration Map already says.

**Collision detection confirmed vacuous by construction.**
`_detect_collisions()` (line 330) derives entirely from its `phrasing_matches`
argument; its `results` parameter is accepted and never read. `phrasing_matches`
is a `defaultdict(set)` populated only inside the per-skill fixture loop
(`_run_validation()`, line ~380/~405), which is skipped via `continue` for every
fixture-less skill (line ~387). With zero fixtures it stays empty, so
`collisions == []` and `_format_text_report()` prints the unconditional `else`
branch "No cross-skill collisions detected." — the ENH-2877 audit was right to
discount it.

**Three sites drive the exit code, not one.** All iterate the full `results`
dict with no fixture-presence guard, so all three need the measured/unmeasured
split:
- `_any_failures()` (line 555) — the exit-code decision, also called by doctor.
- `_format_text_report()` FAILURES block (line ~493) — emits two failure lines
  per fixture-less skill.
- `_format_json_report()` (line ~516) — emits no `measured`/`unmeasured` flag
  today; add one so JSON consumers can make the same distinction.

**Test surface.** `scripts/tests/test_verify_triggers.py` (560 lines);
`class TestMainVerifyTriggers` begins ~line 404 and already exercises exit codes
via `patch("sys.argv", [..., "-C", str(tmp_path)])` with a `_setup_skills_dir()`
helper — the regression tests belong there and can reuse that harness.
`test_no_skills_dir` (line ~404) asserts exit 1 for a *missing* `skills/` dir;
that is a distinct case from "present but fixture-less" and must keep exiting 1.
No existing test covers a fixture-less tree, which is why the regression landed
unnoticed.

### Decision Rationale

**Selected: Option A** — filter the scored population to model-invocable skills
via `_is_model_invocation_disabled()` reused inside `_load_skill_descriptions()`.

Option A scored higher primarily on consistency and risk: the codebase already
has three sites (`doc_counts.py:350`, `doc_counts.py:399`,
`generate_skill_descriptions.py:110`) that skip `disable-model-invocation: true`
skills from skill-wide sweeps, and `_load_skill_descriptions()` already builds
the frontmatter dict at the exact point a one-line filter would go. Option B's
merged "unmeasured" bucket was found to reintroduce the bug's own core problem
one level up — conflating "no fixtures yet" with "can never be model-invoked" —
and its `N/71` coverage line can never reach 100% since 52 of 71 skills are
permanently non-invocable, so it never signals "done" the way Option A's
actionable `N/19` does.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|:-----------:|:----------:|:------------:|:----:|:-----:|
| A — filter to model-invocable | 2 | 3 | 3 | 2 | 10/12 |
| B — unfiltered, unmeasured-only split | 1 | 2 | 2 | 2 | 7/12 |

**Key evidence:**
- `_is_model_invocation_disabled()` (`adapters/core.py:104`) already handles
  both native-bool and stringified `disable-model-invocation` values; the three
  cited precedent sites duplicate its logic inline rather than calling it, so
  Option A becomes that helper's first real external caller — consolidating
  duplication instead of adding a fourth copy.
- No downstream code (collision detection included) independently assumes the
  full 71-skill population; `_detect_collisions()` derives entirely from
  `_load_skill_descriptions()`'s output, so filtering there consistently narrows
  every downstream step together.
- Both options require the same measured/unmeasured split across
  `_run_validation()`, `_any_failures()`, `_format_text_report()`, and
  `_format_json_report()` — that work is common, not a differentiator.

## Integration Map

- `scripts/little_loops/cli/verify_triggers.py` — `_load_trigger_fixtures()`
  (line 218), `TriggerFixtures` dataclass (line 130), `_extract_keywords()`
  (line 166), `_detect_collisions()` (line 330), score/report assembly (line
  370+). The whole fix is in this file for Part 1.
- `skills/*/SKILL.md` — where `trigger_fixtures` blocks land for Part 2.
- `scripts/little_loops/cli/doctor.py` — confirm how `--full` treats this gate's
  exit code today (FEAT-2795 aggregation, error/warn severity split).
- `scripts/tests/` — a regression test asserting that a tree with zero fixtures
  exits 0 with an unmeasured report, and that a below-threshold skill with
  fixtures exits 1.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Files to Modify
- `scripts/little_loops/cli/verify_triggers.py` — `_load_skill_descriptions()`
  (line 274, population filter for Option A), `_run_validation()` (line 355,
  return a measured/unmeasured split), `_any_failures()` (line 555, gate on
  measured only), `_format_text_report()` (line ~459, coverage line + guarded
  collision message + failures block), `_format_json_report()` (line ~516, add
  a `measured` flag / `coverage` block).
- `scripts/little_loops/cli/doctor.py` — `_full_triggers_data()` (line 531)
  imports `_run_validation` and `_any_failures` directly; must be updated in
  lockstep with any signature/return-shape change.

#### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/doctor.py:533` — the only in-tree importer of
  `_run_validation` / `_any_failures`.
- `scripts/pyproject.toml:96` — `ll-verify-triggers =
  "little_loops.cli:main_verify_triggers"` entry point.
- `scripts/tests/test_verify_triggers.py` — 20 call sites of
  `main_verify_triggers` / `_run_validation`.

#### Similar Patterns
- `scripts/little_loops/adapters/core.py:104` `_is_model_invocation_disabled(fm)`
  — the canonical truthiness-tolerant filter (handles YAML bool and
  `"true"/"yes"/"1"`); reuse rather than reimplementing.
- `scripts/little_loops/doc_counts.py:350`, `:399` and
  `scripts/little_loops/cli/generate_skill_descriptions.py:110` — three existing
  precedents for excluding `disable-model-invocation: true` skills from a
  skill-wide sweep.
- `scripts/little_loops/cli/doctor.py:537-541` — the `severity:
  "informational"` escape hatch, the established way a check declines to fail
  the aggregate when it has no input to judge.

#### Tests
- `scripts/tests/test_verify_triggers.py` — `class TestMainVerifyTriggers`
  (~line 404) with its `_setup_skills_dir()` fixture-tree helper; add the
  fixture-less-exits-0 and below-threshold-exits-1 cases here.
- Also assert `ll-doctor --full` no longer reports `full:triggers` at
  `severity: "error"` on a fixture-less tree.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_history/evolution.py:188,197` — imports
  `_extract_keywords`, `_load_skill_descriptions`, and `_tokenize` from
  `verify_triggers.py` for `_load_skill_keywords()` / `_tokenize_content()`,
  which power `detect_skill_bypass()`. Not previously listed in this issue.
  If Option A's model-invocable filter changes `_load_skill_descriptions()`'s
  returned population (71 → 19 skills), this caller's keyword set shrinks
  too — confirm that's acceptable for skill-bypass detection, or the filter
  needs to be applied only inside `verify_triggers.py`'s own callers, not at
  the shared function.
- `scripts/little_loops/cli/__init__.py:96,144` — imports and re-exports
  `main_verify_triggers` in `__all__`; unaffected by the internal
  measured/unmeasured refactor since the CLI entry contract is unchanged, but
  listed for completeness.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_doctor_full.py::TestFullAdapters.test_triggers_reports_unsupported_on_failure`
  (~line 78) — mocks `verify_triggers_mod._run_validation` to return the
  current 3-tuple shape and `_any_failures` directly; update the mocked
  return value if `_run_validation()`'s signature grows a measured/unmeasured
  split. Not previously listed in this issue's Integration Map.
- `scripts/tests/test_cli_doctor_full.py::TestFullSection.test_run_full_checks_returns_check_result_per_verifier`
  (~line 177) — asserts `full:triggers` appears in the aggregated check set;
  review for the new severity behavior on a fixture-less tree.
- `scripts/tests/test_verify_triggers.py::TestRunValidation.test_results_have_zero_precision_when_no_fixtures`
  (~line 356) — currently asserts a fixture-less skill's `precision`/`recall`
  are `0.0` inside the same `results` dict; will break once unmeasured skills
  move out of pass/fail scoring — update to assert the new unmeasured
  representation instead.
- `scripts/tests/test_verify_triggers.py::TestMainVerifyTriggers.test_json_output_no_fixtures`
  (~line 503) — asserts the JSON `skills` list contains the fixture-less
  skill at `precision == 0.0`; will break if unmeasured skills move to a
  separate JSON section per the planned `_format_json_report()` change.
- No existing test covers "skills dir exists, populated, zero skills declare
  `trigger_fixtures`" end-to-end through `main_verify_triggers()` — this is
  the exact repro scenario in this issue's title and is a genuine gap.
- Test-pattern precedent: `scripts/tests/test_cli_doctor_full.py`'s
  `test_check_links_reports_unsupported_on_broken` /
  `test_check_links_reports_informational_on_unreachable_only` (ENH-2836) is
  the closest existing template for an error-tier vs. informational-tier
  pair on `_full_triggers_data()`. `scripts/tests/test_skill_size_checker.py`'s
  `_make_skill(..., disable_model_invocation=bool)` factory +
  `test_disable_model_invocation_skill_skipped` is the template for the new
  `_load_skill_descriptions()` filter test.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:2982-3006` — the `### ll-verify-triggers` section
  documents the exit-code contract as "`1` = threshold miss or collision
  detected" for *any* skill; this goes stale once Part 1 scopes failures to
  measured skills only. Not previously listed in this issue's Related Key
  Documentation table.

## Implementation Steps

1. Reproduce: confirm the exit-1 path and capture current output as a baseline.
2. ~~Determine whether `ll-doctor --full` currently fails on this gate or
   special-cases it; record the answer in the issue.~~ **Answered** — it fails
   (`severity: "error"`, no special-case). See Proposed Solution → Codebase
   Research Findings.
3. In `verify_triggers.py`, separate unmeasured skills from scored skills; make
   exit code depend only on scored skills.
4. Add a fixture-coverage line to the report.
5. Gate the collision-clean message on non-empty phrasing input.
6. Add pytest coverage for both the empty-fixture and below-threshold cases.
7. Author `trigger_fixtures` for the highest-collision-risk skill clusters.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Check `scripts/little_loops/issue_history/evolution.py:188,197` — confirm
   whether `detect_skill_bypass()` should see the full 71-skill population or
   the Option A-filtered 19; apply the model-invocable filter only inside
   `verify_triggers.py`'s own scoring path if `evolution.py` needs the
   unfiltered set.
9. Update `scripts/tests/test_cli_doctor_full.py` — fix the mocked
   `_run_validation` return-tuple shape in
   `test_triggers_reports_unsupported_on_failure` and review
   `test_run_full_checks_returns_check_result_per_verifier` for the new
   severity behavior.
10. Update `scripts/tests/test_verify_triggers.py` —
    `test_results_have_zero_precision_when_no_fixtures` and
    `test_json_output_no_fixtures` both assume unmeasured skills score 0.0
    inside the current result shape; update for the measured/unmeasured
    split.
11. Update `docs/reference/CLI.md:2982-3006` — the `ll-verify-triggers`
    exit-code description to reflect "measured skills only" semantics.

## Impact

- **Severity**: Medium — no runtime behavior is wrong, but a verification gate
  has been reporting a false signal (in both directions) since FEAT-1910 landed,
  and other work has already had to discount its output.
- **Blast radius**: `ll-verify-triggers`, `ll-doctor --full`, and any judgement
  made about skill-description routing quality.
- **Risk of fix**: Low. Part 1 is contained to one CLI module plus tests.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `.claude/CLAUDE.md` | Lists `ll-verify-triggers` under CLI Tools; documents the "local pytest suite is CI" policy the regression test must satisfy |
| `docs/reference/API.md` | Module reference for `little_loops.cli.verify_triggers` |
| `docs/reference/CLI.md` | Full CLI reference (`### ll-verify-triggers`, lines 2982-3006) with an exit-code contract that goes stale after Part 1 — _added by `/ll:wire-issue`_ |

## Resolution

**Part 1 (the bug) — implemented.** `scripts/little_loops/cli/verify_triggers.py`:

- `SkillTriggerResult` gained a `measured: bool` flag, set True only when the
  skill declared `trigger_fixtures`.
- `_load_skill_descriptions()` gained an opt-in `model_invocable_only` parameter
  reusing `adapters.core._is_model_invocation_disabled()` (Option A). Default is
  `False`, so `issue_history/evolution.py:_load_skill_keywords()` — which powers
  `detect_skill_bypass()` and legitimately wants the full 71-skill population —
  is unaffected (resolves Wiring Step 8). `_run_validation()` passes `True`,
  narrowing the scored population to 19.
- `_any_failures()` skips unmeasured skills; `_format_text_report()` lists them in
  a dedicated `Unmeasured` section, adds a `Fixture coverage: M/N` line, and gates
  the collision-clean message (now `Collision detection skipped: no trigger
  fixtures to test.` when nothing was measured).
- `_format_json_report()` adds a per-skill `measured` flag plus top-level
  `coverage` and `collision_detection` keys.
- `doctor.py:_full_triggers_data()` reports `M/N skill(s) measured`. No signature
  change to `_run_validation()`/`_any_failures()`, so the existing doctor mocks
  hold.

Verified: `ll-verify-triggers` now exits 0 reporting `Fixture coverage: 0/19`, and
`ll-doctor --full` reports `✓ triggers 0/19 skill(s) measured` where it previously
failed at `severity: "error"`.

**Part 2 (author fixtures) — split to ENH-2884.** A pilot on the loop cluster
showed Part 2 is not data entry: `_match_phrasing()` fires on a *single* shared
token, so realistic phrasings match 3–6 skills each and every one registers as a
collision (e.g. `"generate a verification loop from FEAT-100"` →
`adversarial-verify-loop`, `create-eval-from-issues`, `create-loop`,
`verify-issue-loop`). Authoring fixtures now would flip the gate back to exit 1 for
matcher-fidelity reasons rather than description defects — reintroducing this
bug's own failure mode. ENH-2884 covers matcher fidelity first, then the fixture
authoring.

Tests added (`test_verify_triggers.py`): fixture-less tree exits 0 with an
unmeasured report and no collision-clean claim; a skill *with* fixtures below
threshold still exits 1; unmeasured skills absent from FAILURES; model-uninvocable
skills excluded from scoring and coverage; JSON `measured`/`coverage`/
`collision_detection` shape; and the `_load_skill_descriptions()` filter being
opt-in. `test_cli_doctor_full.py` gained `test_triggers_passes_on_fixture_less_tree`.

Full suite: 16721 passed. The 6 failures in `test_general_task_loop.py`,
`test_builtin_loops.py`, `test_rn_refine.py`, and `test_prose_dep_sweep_gate.py`
reproduce identically on a clean `git stash` tree — pre-existing and unrelated.

## Session Log
- `/ll:manage-issue` - 2026-07-28T03:23:51Z - `bde35a6a-0676-47b5-9df9-c42e7200e84e.jsonl`
- `/ll:ready-issue` - 2026-07-28T02:59:34 - `808ab62e-a3cc-4318-8865-b51adadca76f.jsonl`
- `/ll:wire-issue` - 2026-07-28T02:36:27 - `1679ea24-85ef-4b97-b445-0a9c3a5e3f4b.jsonl`
- `/ll:decide-issue` - 2026-07-28T02:28:19 - `cf5573d6-5c50-4030-93dd-76c7e1c89898.jsonl`
- `/ll:refine-issue` - 2026-07-28T02:22:13 - `e2671968-a7c2-48ee-8e1c-446533c43048.jsonl`
- `/ll:capture-issue` - 2026-07-28T02:07:33Z - `e2671968-a7c2-48ee-8e1c-446533c43048.jsonl`

## Status

open
