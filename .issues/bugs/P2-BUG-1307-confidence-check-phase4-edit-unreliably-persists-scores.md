---
captured_at: "2026-04-30T17:48:28Z"
discovered_date: 2026-04-30
discovered_by: capture-issue
---

# BUG-1307: `/ll:confidence-check` Phase 4 LLM Edit unreliably persists scores to frontmatter, causing `check_readiness` to fail and route ready issues to size-review

## Summary

In `refine-to-ready-issue.yaml`, the `check_readiness` gate reads `confidence_score` from the issue's YAML frontmatter via `ll-issues show --json`. That frontmatter value is written by **Phase 4 of `/ll:confidence-check`, which is a natural-language instruction for the LLM to use the `Edit` tool to update frontmatter** — there is no deterministic CLI write and no verification.

When the LLM skips, mis-targets, or otherwise fails Phase 4, the chat may display "100/97" but the frontmatter retains the previous value (or none). The gate then reads the stale value, exits 1, the refine-limit ladder advances, and `breakdown_issue` runs `/ll:issue-size-review` — destructively decomposing a ready issue.

Observed in `blender-agents` autodev run on BUG-9106:
- Iter 7: `/ll:confidence-check` reports 94/75; refine triggered.
- Iter 12: `/ll:confidence-check` reports 100/97 in chat.
- Iter 13: `check_readiness` still exits 1 → refine-limit reached → `breakdown_issue` runs `/ll:issue-size-review`. (Trace in `ba-autodev-debug.txt`.)

## Current Behavior

`refine-to-ready-issue.yaml` (`confidence_check` → `check_readiness`):

1. `confidence_check` runs `/ll:confidence-check`. The skill's Phase 4 (`skills/confidence-check/SKILL.md` Phase 4) is plain prose telling the LLM to `Edit` the issue file's YAML frontmatter to set `confidence_score:` and `outcome_confidence:`.
2. `check_readiness` shells out to `ll-issues show <id> --json` and exits 0 iff `int(d.get('confidence') or 0) >= readiness`.
3. `ll-issues show` (`scripts/little_loops/cli/issues/show.py`) populates the JSON `confidence` key from the frontmatter `confidence_score:` field.

If Phase 4's Edit step did not run (or wrote to the wrong file, or got replaced by a stdout markdown line like `**confidence_score**: 100`), the frontmatter is unchanged. The gate sees a stale value or `None` (→ `int(None or 0) = 0 >= 90 = False`) and exits 1, regardless of what the LLM announced in chat.

After two refine retries, `check_refine_limit` advances to `breakdown_issue` and runs `/ll:issue-size-review` on an issue that may already be ready, destroying it.

## Expected Behavior

Score persistence must be deterministic and verified, not LLM-driven:

1. Persistence of `confidence_score` and `outcome_confidence` happens through a CLI command that writes frontmatter idempotently (e.g. `ll-issues set-scores <id> --confidence N --outcome N ...`).
2. `/ll:confidence-check` Phase 4 invokes that CLI via `Bash` instead of `Edit`.
3. `refine-to-ready-issue.yaml` includes a `verify_scores_persisted` state between `confidence_check` and `check_readiness` that re-reads frontmatter and routes to `failed` (with a clear log line) when scores are missing — surfacing this class of bug loudly instead of routing to a destructive operation.

When the LLM-announced score is `>= readiness_threshold`, `check_readiness` must reflect that and the loop must reach `implement_current`, not `breakdown_issue`.

## Motivation

Failure mode is silent and routes to a destructive operation: `/ll:issue-size-review` decomposes a ready issue into children, blowing up effort estimates and destroying carefully refined context. Observed once on BUG-9106 in `blender-agents`; the pattern affects every autodev run because every run depends on Phase 4 succeeding.

The same fragility applies to `autodev`'s post-refine `check_passed` gate (`autodev.yaml`), which reads the same frontmatter — so this bug also undermines the parent loop's main routing decision, not just the sub-loop.

## Proposed Solution

**Minimum viable: (1) + (2).** Add (3) as defense-in-depth.

**(1) Add `ll-issues set-scores` CLI** in `scripts/little_loops/cli/issues/`:
- Accepts `--confidence`, `--outcome`, `--score-complexity`, `--score-test-coverage`, `--score-ambiguity`, `--score-change-surface`.
- Writes them into the target issue's YAML frontmatter idempotently.
- Becomes the single source of truth for score persistence.

**(2) Update `skills/confidence-check/SKILL.md` Phase 4** to instruct the LLM to call `ll-issues set-scores <id> --confidence N --outcome N ...` via `Bash` instead of `Edit`. Deterministic CLI is much harder to skip than free-form Edit. Keep Phase 4.5 ("Confidence Check Notes" markdown append) as `Edit` — that part is genuinely narrative.

**(3) Add `verify_scores_persisted` state in `refine-to-ready-issue.yaml`** between `confidence_check` and `check_readiness`: re-read frontmatter and assert both `confidence_score` and `outcome_confidence` are non-null. On failure, route to `failed` with a clear log line, not silently to the refine/breakdown ladder.

**(4) Optional output-capture fallback**: have the loop capture the slash-command's stdout, parse the trailing `**confidence_score**: N` / `**outcome_confidence**: N` markdown lines, and call `ll-issues set-scores` from the loop itself if the skill failed to. Makes correctness a property of the loop, not LLM compliance.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/` — new `set_scores.py` module + entry-point registration in `scripts/little_loops/cli/issues/__init__.py` / `pyproject.toml`.
- `skills/confidence-check/SKILL.md` — replace Phase 4 Edit instructions with Bash CLI call.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — insert `verify_scores_persisted` between `confidence_check` and `check_readiness`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/show.py` — reads `confidence_score`/`outcome_confidence` from frontmatter; must stay in sync with whatever `set-scores` writes.
- `scripts/little_loops/loops/autodev.yaml` — `check_passed` reads same frontmatter via `ll-issues check-readiness` (or `show --json`); confirm it observes the new writes.
- Any other loop YAML that calls `/ll:confidence-check` and then reads `confidence_score` from frontmatter.

### Similar Patterns
- Existing `ll-issues` subcommands (e.g., `update-frontmatter`, `next-id`, `show`) — follow their CLI/argparse conventions.
- `scripts/little_loops/utils/frontmatter.py` (or wherever frontmatter round-trip lives — see BUG-474 history) for safe YAML write.

### Tests
- New: `scripts/tests/test_set_scores_cli.py` — writes new frontmatter when none, updates existing fields, leaves unrelated fields intact, handles missing file.
- New integration: `/ll:confidence-check` against synthetic issue with no frontmatter; assert `ll-issues show <id> --json` returns the announced scores.
- Existing: any tests touching `refine-to-ready-issue.yaml` flow need updating for the new `verify_scores_persisted` state.

### Documentation
- `skills/confidence-check/SKILL.md` Phase 4 prose.
- Any developer docs describing the autodev/refine flow.

### Configuration
- N/A.

## Implementation Steps

1. Implement `ll-issues set-scores` CLI with idempotent frontmatter writes; ship with unit tests.
2. Rewrite Phase 4 of `skills/confidence-check/SKILL.md` to use `Bash` + `ll-issues set-scores` instead of `Edit`.
3. Add `verify_scores_persisted` state to `refine-to-ready-issue.yaml`; route to `failed` on missing scores with a descriptive log message.
4. Confirm parity for `autodev.yaml` `check_passed` (it reads the same frontmatter — should "just work" after step 1).
5. E2E reproduce: re-queue BUG-9106 in `blender-agents` via `ll-loop run autodev "BUG-9106"`; second `/ll:confidence-check` must result in `check_readiness` passing and reaching `implement_current`.
6. (Optional) Add the loop-level stdout fallback if Phase 4 reliability remains a concern after deterministic CLI swap.

## Steps to Reproduce

1. Run `ll-loop run autodev <issue-id>` against any issue that needs one refine pass to reach `confidence_score >= readiness_threshold`.
2. Observe `/ll:confidence-check` announcing a passing score (e.g. 100/97) in chat on the second iteration.
3. Inspect the issue file's frontmatter: `confidence_score` is unchanged from a prior iteration (or absent).
4. Loop proceeds to `breakdown_issue` → `/ll:issue-size-review` instead of `implement_current`.

The bug is probabilistic (depends on whether the LLM executed the Phase 4 Edit). To force it, instruct the model to skip Phase 4 in a test variant of the skill.

## Root Cause

`skills/confidence-check/SKILL.md` Phase 4 (around the "frontmatter update" instructions): persistence of `confidence_score` / `outcome_confidence` is a free-form `Edit` step the LLM is told to perform. There is no deterministic write path, no verification step, and no fallback. When the LLM omits or mis-targets the Edit, downstream gates that read frontmatter (`check_readiness` in `refine-to-ready-issue.yaml`, `check_passed` in `autodev.yaml`) consume stale or null data and make the wrong routing decision.

## Location

- `skills/confidence-check/SKILL.md` Phase 4 (frontmatter Edit instructions) — root cause.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` `confidence_check` → `check_readiness` — gate that misfires.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` `check_refine_limit` → `breakdown_issue` — destructive downstream effect.
- `scripts/little_loops/cli/issues/show.py` (`confidence` JSON key from `confidence_score` frontmatter) — gate's data source.
- `scripts/little_loops/loops/autodev.yaml` `refine_current` / `check_passed` — parent loop also affected.

## Impact

- **Severity**: High. Failure is silent and routes to a destructive operation that decomposes ready issues into children, breaking effort estimates and discarding refinement work.
- **Scope**: Every autodev / refine-to-ready-issue run. Probabilistic, but the trigger (Phase 4 LLM compliance) is not under our control.
- **Affected runs**: At least one confirmed (`blender-agents` BUG-9106). Likely others previously misattributed to "issue is too big".
- **Blast radius**: Any sprint or autodev session that hits a refine pass.

## Related Key Documentation

| Document | Why Relevant |
|---|---|
| `skills/confidence-check/SKILL.md` | Phase 4 frontmatter persistence is the root cause |
| `scripts/little_loops/loops/refine-to-ready-issue.yaml` | Sub-loop where the misfire occurs |
| `scripts/little_loops/loops/autodev.yaml` | Parent loop with same vulnerability via `check_passed` |
| `scripts/little_loops/cli/issues/show.py` | JSON contract consumed by the gate |

## Labels

bug, autodev, refine-to-ready-issue, confidence-check, frontmatter, persistence, fsm

## Session Log
- `/ll:format-issue` - 2026-05-01T17:38:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1483ec77-4cf9-4aca-8312-065f15a52a5f.jsonl`
- `/ll:capture-issue` - 2026-04-30T17:48:28Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/27ef26bc-40e0-42b3-b405-4e9de6b8db77.jsonl`

---

## Status
- **Created**: 2026-04-30
- **State**: Open
