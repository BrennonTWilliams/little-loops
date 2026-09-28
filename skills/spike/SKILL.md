---
name: spike
description: Use when asked to prove an unproven internal mechanism with an isolated code spike before implementing.
args: "ISSUE_ID [--auto | --check | --plan-only | --plan <file> | --force]"
allowed-tools:
  - Read
  - Glob
  - Grep
  - Write(**/spike/**)
  - Write(.ll/spikes/**)
  - Edit(**/spike/**)
  - Edit(.issues/**)
  - Bash(ll-issues:*)
  - Bash(ll-config:*)
  - Bash(python -m pytest:*)
  - Bash(mkdir:*)
  - Bash(git:*)
  - Bash(find:*)
  - Bash(mktemp:*)
  - Bash(rm:*)
metadata:
  short-description: Prove an unproven internal mechanism with a code spike before implementing.
trigger_fixtures:
  should_fire:
    - "prove this unproven internal mechanism with an isolated code spike before implementing"
    - "run an isolated code spike to prove this unproven mechanism"
  should_not_fire:
    - "explore this external api library and record proof"
    - "run a pre-implementation confidence check"
---

# Spike Skill

Retire concentrated technical risk on an issue by planning, implementing, and
verifying a **code spike** — a standalone library + test class that proves a novel
**internal** mechanism in isolation — before the real integration point is touched.
On success the skill appends `## Spike Results` to the issue and sets
`spike_completed: true`, so re-running `/ll:confidence-check` recovers the
outcome-confidence points the unproven mechanism cost.

**Scope**: Python/pytest projects only. Spike packages are pytest test modules
and Verification always shells out to `pytest` directly against the spike
directory (never `project.test_cmd`, which usually already embeds its own
path).

The golden deliverable shape is the ENH-2565 spike (readiness-gated pop +
concurrency core for `rn-refine` `synth_pop`). The plan shape lives in
[plan-template.md](plan-template.md).

## When to Activate

- `/ll:confidence-check` scored outcome confidence low because a mechanism has
  **zero precedent** in the codebase and **no test exercises the risky core**
  (the `spike_needed: true` failure mode from confidence-check Phase 4.10).
- Before implementation, when the riskiest part of an issue is a novel internal
  mechanism you want to prove in isolation first.

**Not for**: unproven *external* API assumptions (use `/ll:explore-api` +
Learning-Test Registry); unresolved Option A/B ambiguity (`/ll:decide-issue`);
absent files / unwired integration (`/ll:wire-issue`); an over-large issue
(`/ll:issue-size-review`).

## Arguments

$ARGUMENTS

Parse arguments for the issue ID and flags, mirroring `confidence-check`:

```bash
ISSUE_ID=""
AUTO_MODE=false
CHECK_MODE=false
PLAN_ONLY=false
FORCE=false
PLAN_FILE=""

# Auto-enable in automation contexts
if [[ "$ARGUMENTS" == *"--dangerously-skip-permissions"* ]] || [[ -n "${LL_NON_INTERACTIVE:-}" ]] || [[ -n "${DANGEROUSLY_SKIP_PERMISSIONS:-}" ]]; then AUTO_MODE=true; fi

# Explicit flags
if [[ "$ARGUMENTS" == *"--auto"* ]]; then AUTO_MODE=true; fi
if [[ "$ARGUMENTS" == *"--check"* ]]; then CHECK_MODE=true; AUTO_MODE=true; fi
if [[ "$ARGUMENTS" == *"--plan-only"* ]]; then PLAN_ONLY=true; fi
if [[ "$ARGUMENTS" == *"--force"* ]]; then FORCE=true; fi
if [[ "$ARGUMENTS" =~ --plan[[:space:]]+([^[:space:]]+) ]]; then PLAN_FILE="${BASH_REMATCH[1]}"; fi

# Extract issue ID (first non-flag argument that is not a --plan value)
PREV=""
for token in $ARGUMENTS; do
    case "$token" in
        --*) PREV="$token" ;;                # skip flags
        *) if [[ "$PREV" == "--plan" ]]; then PREV=""; else ISSUE_ID="$token"; PREV=""; fi ;;
    esac
done
```

## Phase 1: Locate Issue

Resolve the issue file via `ll-issues path "$ISSUE_ID"`. If it does not resolve,
print `Error: issue $ISSUE_ID not found` and `exit 1`. Read the issue file
completely.

**Budget discipline** — one spike per issue by default. If the frontmatter already
carries `spike_attempted: true` and `--force` is not set, refuse:

```
⚠ Spike already attempted for $ISSUE_ID (spike_attempted: true).
  Re-run with --force to spike again, or run /ll:confidence-check to re-score.
```

and `exit 0` (mirrors the idempotent `--force-implement` HALT gates in
`skills/manage-issue/SKILL.md`).

## Phase 2: Risk Extraction

Determine which risks the spike must retire:

1. If `--plan <file>` was given, read that plan and skip to Phase 4 (Implement) —
   the caller supplied the plan.
2. Otherwise, read the issue's `## Confidence Check Notes` →
   `### Outcome Risk Factors` (and `## Spike Plan` if present). Each risk factor
   that names an **unproven internal mechanism** becomes a row in the spike's AC
   table.
3. If no risk factors exist, run standalone analysis of the issue's
   `## Proposed Solution` to identify the single riskiest unprecedented mechanism.
   In interactive mode (`AUTO_MODE=false`), confirm scope with AskUserQuestion; in
   auto mode, pick the riskiest mechanism autonomously and document the choice.

**External-API suppression**: if the risk factor names a third-party package, SDK,
or external API surface, do **not** spike — emit:

```
ℹ Risk factor names an external API surface; use /ll:explore-api (Learning-Test Registry), not a code spike.
```

and `exit 0`. (Same exclusion heuristic as confidence-check Phase 4.10 /
`refine-issue` Step 7.5.)

The `<slug>` is a kebab/snake identifier derived from the issue and mechanism
(e.g. `rn_refine_synth_pop`) — fix it now; Phase 0 and everything after
reference it.

## Phase 0: Resolve Layout

Resolve the spike directory once, before writing the plan. Every later phase
(Plan, Implement, Verify, Check Mode) references `$SPIKE_DIR`/`$TEST_DIR`
below rather than re-resolving:

```bash
TEST_DIR=$(ll-config get project.test_dir); : "${TEST_DIR:=tests}"
SPIKE_DIR="${TEST_DIR%/}/spike/<slug>"
```

`ll-config get` prints nothing and exits 0 even when `BRConfig` construction
itself fails — the `${TEST_DIR:=tests}` guard is required, otherwise
`SPIKE_DIR` would silently resolve to a filesystem-root-anchored
`/spike/<slug>`.

## Phase 3: Plan

Resolve the plan-doc artifact directory, then write
`<artifacts-dir>/spike-<ISSUE-ID>.md` there:

- **Inside an FSM loop**, the loop-run startup injects `${context.run_dir}`
  (`little_loops.cli.loop.run`), propagated to nested slash-command
  child contexts (`little_loops.fsm.executor`). Use it verbatim:
  `<artifacts-dir>` = `${context.run_dir}`.
- **Interactively** (a bare `/ll:spike <ISSUE-ID>` — no `fsm.context`, so no
  `run_dir`), fall back to the standardized, git-tracked `.ll/spikes/` directory.
  Never write the plan doc to `thoughts/` or the repo root. Create it on demand
  first (mirroring the `.ll/learning-tests/` convention in `/ll:explore-api`):

  ```bash
  mkdir -p .ll/spikes/
  ```

  so `<artifacts-dir>` = `.ll/spikes/`. The directory is curated evidence paired
  with the issue's committed `## Spike Results` section, so it is **git-tracked**
  (no `.gitignore` entry — it reuses the `!/.ll/` un-ignore).

Write the plan in the shape defined by
[plan-template.md](plan-template.md). Every mandatory section is required:
**Context** (why confidence was low), **Approach**, **Critical files**,
**Implementation** (package layout under `$SPIKE_DIR/` + API sketch),
**Acceptance Criteria → Test Table** (each test → the AC/risk it retires,
including **at least one regression-guard test**, e.g. an AST sniff preventing a
forbidden import), **Verification** (exact `pytest` commands incl. the named
existing regression suites), **Out of Scope**, **Promotion** (prose only: fold
the proven code into its production module under `project.src_dir` and its
test under `project.test_dir`, in a separate PR — there is no promotion
directory).

**If `--plan-only`**: stop here. The plan file is the deliverable; do not implement.

## Phase 4: Implement

Build the spike package + test class exactly as planned:

- Create `$SPIKE_DIR/__init__.py`, the library module(s), an optional driver,
  and the AC test module.
- Spike code lives **only** under `$SPIKE_DIR/`. `allowed-tools` pre-approves
  writes only under `**/spike/**` (plus `.ll/spikes/**` for the plan doc and
  `.issues/**` for write-back) — this is a pre-approval, not a fence: an
  unmatched write prompts in interactive mode and is allowed outright in
  automation. Isolation is enforced by convention plus the plan's mandatory
  regression-guard test, not by `allowed-tools`.
- Include the regression-guard test from the plan (isolation guard). Name every
  guard test `test_guard_*` — the verdict classifier identifies guards by that prefix.
- Install the exception-recording hook (the classifier needs each failed test's
  exception type). It goes in `$SPIKE_DIR/conftest.py` — not a `-p little_loops...`
  plugin, since `little_loops` may not be importable by the project's pytest:

  ```bash
  ll-issues spike-verdict --emit-conftest --out "$SPIKE_DIR/conftest.py"
  ```

  This appends a sentinel-delimited block and replaces it in place on a rerun, so a
  spike's own fixtures in `conftest.py` are never overwritten or duplicated.

## Phase 5: Verify

Run the plan's Verification commands **foreground-blocking** (never background the
result-blocking suite). Tag each command's role from the plan: `spike` (the
`$SPIKE_DIR` suite: AC + guard tests) or `regression` (a named existing suite).

Pick `<reports-dir>`: inside an FSM loop `${context.run_dir}/spike-junit/`;
interactively `REPORTS_DIR=$(mktemp -d)`, removed after classification. **Never**
`.ll/spikes/` — it is git-tracked and JUnit XML there would be committed noise.
Delete stale reports first, then run every command with
`--junitxml=<reports-dir>/<role>-<n>.xml` and `--maxfail=0` appended after the plan's
own flags (a project `addopts = -x` would otherwise stop before the guard tests run,
reading every refutation as inconclusive). Record each command's exit code:

```bash
python -m pytest "$SPIKE_DIR/" -v --junitxml="$REPORTS_DIR/spike-1.xml" --maxfail=0; E1=$?
python -m pytest "${TEST_DIR%/}/<named-regression-suite>.py" -v --junitxml="$REPORTS_DIR/regression-2.xml" --maxfail=0; E2=$?
ll-issues spike-verdict --report "spike:$REPORTS_DIR/spike-1.xml:$E1" "regression:$REPORTS_DIR/regression-2.xml:$E2"
```

`spike-verdict` prints `PROVEN` / `REFUTED` / `INCONCLUSIVE` plus a one-line cause and
exits 0 / 1 / 3. **Use its verdict, not the raw exit codes** — do not classify by
reading pytest output yourself. Only an `AssertionError` in an AC test, with every
guard test and regression suite passing, is `REFUTED`; anything ambiguous (import or
collection errors, non-assertion exceptions, fixture errors, skipped ACs, missing
reports, failing guards or regression suites) is `INCONCLUSIVE`.

## Phase 6: Write-Back

**Skip this phase entirely if `CHECK_MODE` is true** (see Check Mode Behavior).

### PROVEN

1. Append a `## Spike Results` section to the issue with the Edit tool. Follow
   wire-issue's append-only pattern: insert **before `## Session Log`** (or before
   `## Status` if no session log), tag it with a provenance sentinel.

   ```markdown
   ## Spike Results

   _Added by `/ll:spike` on [YYYY-MM-DD]_

   **Retired risks**

   | Risk (from Outcome Risk Factors) | Proven by | Result |
   |----------------------------------|-----------|--------|
   | [risk a] | `TestX::test_...` | ✓ pass |

   **Spike location**: `$SPIKE_DIR/`
   **Verification**: [N] tests pass across [command count] commands.
   **Promotion**: fold into its production module under `project.src_dir` and
   its test under `project.test_dir`, in a separate PR.
   ```

2. Remove `spike_refuted` if present, and set `spike_completed: true` and `spike_attempted: true` in the frontmatter
   `---` block with the Edit tool — the same inline-block convention
   confidence-check Phase 4.10 uses (there is no `set-flag` CLI verb). Always
   write `true`, never `false`; skip the write if already `true` (idempotent).

### REFUTED / INCONCLUSIVE

Every verdict writes the full flag set (there is no unset verb — edit the frontmatter
`---` block with the Edit tool):

| Verdict | `spike_attempted` | `spike_completed` | `spike_refuted` | `decision_needed` |
|---|---|---|---|---|
| proven | set | set | **remove** | unchanged |
| refuted | set | **remove** | set | set |
| inconclusive | set | **remove** | **remove** | unchanged |

A failed `--force` rerun must not leave a stale `spike_completed: true` suppressing the
unproven-mechanism cap. Removing `spike_refuted` on a later verdict does not clear a
`decision_needed` a refutation armed — `/ll:decide-issue` owns that. If the issue
already has a `## Spike Results` section from an earlier proven run, add a
`_Superseded by the failed /ll:spike --force run on [YYYY-MM-DD] — see ## Spike
Findings_` line under its heading.

Append a `## Spike Findings` section quoting the classifier's cause line and the failing
commands' output.

- **INCONCLUSIVE**: the Findings entry names the cause and does **not** claim the
  approach is wrong (the environment, a test bug, or an unrelated failure may be to
  blame). Do not route to `/ll:decide-issue`.
- **REFUTED**: additionally rewrite the issue so `/ll:decide-issue` can act on it —
  `## Proposed Solution` into `### Option <X>` header blocks, the refuted-option marker
  under `## Open Questions`, and `decision_needed: true`. Exact shapes:
  [write-back.md](write-back.md).

### Always

Append a session log entry:

```bash
ll-issues append-log "[issue-file-path]" /ll:spike
```

Then stage the issue file: `git add "[issue-file-path]"`.

## Phase 7: Recommend Next Step

Print the next action:

- PROVEN: `✓ Spike passed. Run /ll:confidence-check $ISSUE_ID to re-score, then implement.`
- REFUTED: `✗ Spike refuted the approach — see ## Spike Findings; run /ll:decide-issue $ISSUE_ID to pick a replacement (or /ll:issue-size-review if the issue is too large).`
- INCONCLUSIVE: `? Spike inconclusive — <cause>. Fix the cause, then re-run /ll:spike $ISSUE_ID --force.` Do **not** recommend `/ll:decide-issue`; a decision cannot fix an environment failure.

## Check Mode Behavior (--check)

When `CHECK_MODE` is true, run as an FSM loop evaluator with **no writes**:

1. Resolve the issue and its spike package (Phase 0's `$SPIKE_DIR`).
2. Run the spike's AC suite: `python -m pytest "$SPIKE_DIR/" -q`.
3. If the suite passes: skip (passes gate). If it fails (or no spike package
   exists): print `[ID] spike: ACs fail` .
4. After evaluation: if failed, print `Spike ACs not passing`, then `exit 1`; if
   passed, print `Spike ACs pass`, then `exit 0`.

This integrates with FSM `evaluate: type: exit_code` routing (0=pass, 1=fail,
2+=error). `--check` stays exit-code-only — it is not routed through `spike-verdict` (any non-pass
correctly blocks the gate). It implies `AUTO_MODE=true` and performs no frontmatter or
issue-body writes. The `spike-gate.yaml` wrapper loop (ENH-2641) consumes this
exit-code contract to gate any implementation loop on a proven internal mechanism.

## Auto Mode Behavior

When `AUTO_MODE` is true: skip any AskUserQuestion prompts (choose the riskiest
mechanism autonomously and document the choice), do not pause for confirmation, and
run non-interactively for `ll-auto` / `ll-parallel` / `ll-sprint` contexts. When
`AUTO_MODE` is false (interactive): confirm spike scope before implementing.

## Related

- `skills/confidence-check/SKILL.md` — sets `spike_needed: true` (Phase 4.10) and
  consumes `spike_attempted`/`spike_completed`; flag write-back convention.
- `skills/explore-api/SKILL.md` — the external-API analogue (prove-before-implement
  via the Learning-Test Registry).
- `docs/reference/ISSUE_TEMPLATE.md` — documents the
  `spike_needed`/`spike_attempted`/`spike_completed` frontmatter fields.
- `plan-template.md` — the mandatory-section plan shape.
- `write-back.md` — the refuted-verdict issue rewrite (Option headers + marker).
