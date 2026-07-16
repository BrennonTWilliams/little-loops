---
discovered_commit: 6f81ca029f3c40a05520d5f1d8536fdd0a8723cc
discovered_branch: main
discovered_date: 2026-07-15 00:00:00+00:00
completed_at: '2026-07-16T00:30:45Z'
discovered_by: capture-issue
status: done
relates_to:
- FEAT-2652
- BUG-2651
labels:
- ready-issue
- verifier
- worktree
- epic-branches
confidence_score: 92
outcome_confidence: 82
score_complexity: 20
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 20
---

# ENH-2653: `ready-issue` must name the branch it checked and not reject on suspected base-branch mismatch

## Summary

The `ready-issue` verifier decides whether an issue's cited symbols exist by
reading files in the current working directory, then reports its verdict against
"the current branch" — without ever naming which branch that is. Inside an EPIC
worktree forked from the wrong base, this yields a confident false `NOT_READY`
("the current branch has no `Tableau`, `center`, … surface") for symbols that
exist exactly where the EPIC intends them. The verifier even noticed the
mismatch in one run — *"the original symbols are present on the alternate
`refactor/tableau-third-revision` branch"* — classified it as a `concern`, and
rejected the issue anyway.

Make the verifier branch-transparent: always print the branch it inspected, and
treat "symbols absent but plausibly on another base" as a **concern**, not a
rejection.

## Current Behavior

- `commands/ready-issue.md` drives an LLM that reads files in `cwd`. It has no
  `target_branch` / `base_branch` parameter (the only branch-adjacent call is
  `ll-history-context {{issue_id}}` at ~line 132, which is branch-agnostic).
- The verifier never runs `git rev-parse --abbrev-ref HEAD`, so its "current
  branch has no X" claim is unfalsifiable from the output — the reader can't tell
  which branch was checked.
- A symbol-absence that is really a base-branch mismatch (the EPIC was sprinted
  off `main` but the symbols live on an unmerged feature branch) is scored as a
  hard `NOT_READY`, producing a silent false negative the user only catches by
  reading the per-issue transcript.

## Expected Behavior

- The verifier **always states which branch it inspected** (`git rev-parse
  --abbrev-ref HEAD`, plus the worktree path when in one) in its output.
- When a cited symbol is absent, the verifier must consider "this may be a
  base-branch mismatch" before rejecting: if the issue is an EPIC child (or the
  EPIC declares a `base_branch` — see FEAT-2652) and the symbol could live on
  that other base, it raises a **concern** ("symbols not on inspected branch
  `<X>`; EPIC target base may differ") instead of a `NOT_READY` verdict.
- If the EPIC declares no target base, flag "EPIC declared no target_branch" as a
  readiness concern rather than silently assuming `cwd` is authoritative.

## Proposed Solution

Two tiers, ship the cheap half first:

1. **Prompt-only (cheap):** Amend `commands/ready-issue.md` so the verifier runs
   and reports `git rev-parse --abbrev-ref HEAD`, names the branch in every
   symbol-existence claim, and downgrades suspected-base-mismatch absences to a
   concern rather than a rejection.
2. **Optional `--target-branch` (larger):** Accept a target branch and run
   symbol-existence checks against `git show <branch>:<file>` (or a sidecar
   worktree) instead of `cwd`. Populated from FEAT-2652's EPIC `base_branch`
   field when available.

## Scope Boundaries

**In scope:**
- Making the `ready-issue` verifier report the branch/worktree it inspected.
- Downgrading suspected base-branch-mismatch symbol absences from `NOT_READY` to
  a concern.
- Optional `--target-branch` to run symbol checks against another ref.

**Out of scope:**
- Choosing or creating the EPIC's base branch (owned by FEAT-2652).
- The FTS5 hyphenated-ID bug in `ll-history-context` (owned by BUG-2651).
- Changing the overall `partial` vs `failed` verdict taxonomy of the loop
  (FEAT-2652's validation gate handles the hard-stop escalation).

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `commands/ready-issue.md` — the entire command is a bash/prose spec (no Python
  module). Prompt-only tier (Tier 1) lives here:
  - **Flag parse block** `### 0. Parse Flags` (lines 40–47): add a
    `TARGET_BRANCH` extraction for Tier 2. Note all existing flags (`--deep`,
    `--check`) are boolean substring toggles — no current flag takes a *value*,
    so `--target-branch <ref>` is new territory (extract with a
    `sed`/parameter-expansion parse, not a `*"--flag"*` substring test).
  - **New branch-report step**: add a `git rev-parse --abbrev-ref HEAD` call
    (guard against detached `HEAD` per `worktree_utils.detect_default_branch`),
    plus `git rev-parse --show-toplevel` for the worktree path, and require the
    verdict output to name the inspected branch.
  - **Verdict/verdict-downgrade** `### 4. Determine Verdict` (lines 241–258),
    `### 6. Output Format` VALIDATION table (lines 367–378) and `## CONCERNS`
    block: add a `Symbol Existence` row using the existing `PASS | WARN |
    NOT_READY` three-state shape (mirror the Learning-Test-Gate WARN-vs-override
    split at lines 176–185) so a suspected base-mismatch absence emits WARN +
    a `CONCERNS` bullet, not a `NOT_READY` verdict.
  - **Arguments / Examples** (lines 412–446): document the new flag + one
    example invocation line (established convention).
- `skills/ll-ready-issue/SKILL.md` — thin Codex bridge that defers to
  `commands/ready-issue.md`; check whether the flag list needs mirroring here.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

The verifier's verdict/VALIDATION output **is** parsed downstream — the downgrade
is not just a prompt change, it flips automation control flow:
- `scripts/little_loops/output_parsing.py` — `parse_ready_issue_output()`,
  `parse_validation_table()` (`TABLE_ROW_PATTERN`, line 20): parses `## VERDICT`
  and every `## VALIDATION` row generically into a `validation` dict. A new
  `Symbol Existence` row is **auto-absorbed as an extra dict key — no parser
  change required**; the top-level verdict enum (`VALID_VERDICTS`, line 24) is
  untouched since the taxonomy stays the same [Agent 2 finding].
- `scripts/little_loops/issue_manager.py` (ll-auto, ~lines 794–819) — branches on
  `parsed["is_ready"]`/`is_blocked`. Downgrading a base-mismatch absence from
  `NOT_READY` to WARN flips `is_ready` `False→True` for that class, so ll-auto now
  **proceeds to implementation** where it previously blocked. Intended behavior
  change — verify it's the desired effect [Agent 2 finding].
- `scripts/little_loops/parallel/worker_pool.py` (ll-parallel, ~lines 454–494) —
  same `should_close→is_blocked→is_ready` gate; same intentional behavior-flip
  [Agent 2 finding].
- FSM loops that invoke `/ll:ready-issue` and consume its verdict:
  `scripts/little_loops/loops/refine-to-ready-issue.yaml` (primary wrapper),
  `recursive-refine.yaml`, `auto-refine-and-implement.yaml`, `autodev.yaml`,
  `issue-refinement.yaml` — no YAML edit needed, but their pass/fail expectations
  now see the flipped verdict for base-mismatch issues [Agent 1 finding].
- Not coupled (confirmed clear): `scripts/little_loops/cli/issues/check_readiness.py`
  and `commands.confidence_gate` config read issue-frontmatter `confidence_score`,
  **not** `ready-issue` output — no coupling to this change [Agent 2 finding].

### Reusable Code (Tier 2 — `--target-branch`)
- `scripts/little_loops/worktree_utils.py`:
  - `resolve_epic_base(epic_id, base_branch, repo_path=None, config=None)`
    (lines 65–98) — **single source of truth** for an EPIC's declared base
    (FEAT-2652 extends only this function). Call with `repo_path` set to opt into
    the frontmatter lookup; returns the caller default when the EPIC declares
    none. This is exactly the field the issue's Tier 2 says to populate
    `--target-branch` from.
  - `_load_epic_base_branch()` (lines 101–132) — globs
    `.issues/*/P?-<epic_id>-*.md`, parses `base_branch:` (alias `target_branch:`).
  - `detect_default_branch()` (lines 23–62) — canonical detached-HEAD-safe
    `git rev-parse --abbrev-ref HEAD` idiom to mirror in the bash snippet.
- `scripts/little_loops/issue_progress.py` — `find_nearest_epic_ancestor(issue,
  parent_map)` + `build_parent_map()`: the existing "is this an EPIC child" walk
  (climbs `parent` to the nearest `EPIC-` ancestor, cycle-guarded). Precedent
  consumer: `cli/sprint/run.py:_run_epic_base_preflight()`.
- `scripts/little_loops/issue_parser.py` — `IssueInfo.base_branch: str | None`
  (~line 595), populated from `base_branch:` / deprecated `target_branch:` alias.
- **Read-file-at-ref primitive**:
  `scripts/tests/spike/git_show_blob_at_ref/blob_reader.py` —
  `read_blob_at_ref(git_lock, repo, ref, path) -> BlobResult`, wraps
  `git_lock.run(["show", f"{ref}:{path}"])`, classifies absence by
  `returncode != 0` (never raises). **Spike, not yet promoted** to
  `scripts/little_loops/` (FEAT-2652 notes a follow-on PR to move it) — Tier 2
  either depends on that promotion or inlines the `git show` call routed through
  `GitLock` (never bare `subprocess`).

### Similar Patterns
- Learning-Test Gate (`ready-issue.md` lines 176–185) and Decisions Gate
  (187–217): the direct precedent for "downgrade a hard condition to
  non-blocking WARN, and distinguish gate-didn't-run from clean-pass" — model
  the symbol-existence downgrade on this three-state shape.
- `scripts/tests/spike/git_show_blob_at_ref/test_blob_reader.py` — fixture builds
  the exact "wrong base" scenario (symbol only on `feature`, absent on `base`)
  with an `absent on base → would be a false NOT_READY` assertion; reuse as the
  test model for the downgrade behavior.

### Tests
- `scripts/tests/test_ready_issue_lint.py` — existing file:line contamination
  lint for ready-issue; add branch-transparency assertions here or a sibling.
- `scripts/tests/test_worktree_utils.py` (`TestDetectDefaultBranch`, lines
  55–95) — model for detached-HEAD / branch-detection tests if any Python lands.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_refine_issue_command.py` — sibling markdown-command lint
  test (`COMMAND_FILE.read_text()` + heading-sliced substring asserts, 17 call
  sites). Confirms the established convention for prose-spec tests; structural
  template if a fresh `test_ready_issue_branch_transparency.py` is preferred over
  extending `test_ready_issue_lint.py` in place [Agent 3 finding].
- `scripts/tests/test_output_parsing.py` — many literal `NOT_READY`-string
  fixtures (lines ~186, 335, 418, 460, 496, 638, 648, 658). **Confirmed NOT at
  risk**: they test verdict-token *parsing*, not the prose conditions that emit
  it; no `Symbol Existence` / VALIDATION-row content is asserted. No update
  needed — listed so implementers don't mistake them for breakage [Agent 3].
- `scripts/tests/conftest.py` (sample ready-issue output fixtures, ~lines
  381–413) — add a Symbol-Existence-WARN fixture variant if downstream parser
  tests need to exercise the new row [Agent 1 finding].
- `scripts/tests/test_issue_progress.py` — existing coverage for
  `find_nearest_epic_ancestor()` / `build_parent_map()`; extend here if Tier 2's
  "is this an EPIC child" walk lands Python [Agent 1 finding].

### Documentation
- `docs/ARCHITECTURE.md`, `docs/guides/SPRINT_GUIDE.md` — describe the epic-branch
  workflow; a note on `ready-issue` branch transparency may belong here.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` — documents `/ll:ready-issue` and its `--deep` /
  `--check` flags; **must gain the new `--target-branch <ref>` flag** (Tier 2) and
  a branch-transparency note [Agent 1 finding].
- `docs/reference/API.md` — documents `parse_ready_issue_output` and a fixed
  Valid-Verdicts table. No content change needed (verdict taxonomy unchanged), but
  verify it stays accurate if the WARN sub-state is ever surfaced upward [Agent 2].
- `docs/reference/CLI.md` — CLI reference; check whether the ready-issue flag list
  is mirrored here and needs `--target-branch` [Agent 1 finding].

### Configuration
- No new config. Per-EPIC base lives in issue frontmatter (`base_branch:`), not
  `.ll/ll-config.json`. `parallel.epic_branches.enabled` gates the EPIC-branch
  machinery generally.

### Codebase Research Findings

_Key discovery:_ `ready-issue` today has **zero** branch awareness — grep of
`commands/ready-issue.md` finds no `rev-parse`, `abbrev-ref`, `current branch`,
or `parent:` references. It validates symbols against whatever tree is checked
out, with no code path calling `resolve_epic_base`, `find_nearest_epic_ancestor`,
or `read_blob_at_ref`. All the EPIC-base resolution infrastructure the Tier-2
plan needs (FEAT-2652 + ENH-2656) **already exists and is landed** in
`worktree_utils.py`; the only missing primitive is the promoted read-at-ref
helper (still a spike). Tier 1 is pure prompt-markdown editing with no Python
dependency — genuinely shippable independently as the issue claims.

### Wiring Touchpoints (added by `/ll:wire-issue`)

_Beyond editing `commands/ready-issue.md`, these must be verified as part of the
implementation:_

1. Confirm the intended behavior-flip in `issue_manager.py` (ll-auto) and
   `parallel/worker_pool.py` (ll-parallel): a base-mismatch issue that was
   `NOT_READY` now parses as `is_ready: True` and proceeds to implementation.
   Sanity-check this is the desired outcome (it is, per the issue's premise).
2. No change needed in `output_parsing.py` — the new `Symbol Existence` VALIDATION
   row is auto-absorbed; add a `conftest.py` fixture only if a parser test needs
   to exercise it.
3. Tier 2 only: add `--target-branch <ref>` to `docs/reference/COMMANDS.md` (and
   `CLI.md` if mirrored), and note it in `CHANGELOG.md`.

## Impact

Medium. The prompt-only tier alone converts a silent false negative into a
visible, actionable concern and is near-zero-cost. Combined with FEAT-2652 it
closes the wrong-base false-`NOT_READY` class end to end. Improves trust in
`sprint-refine-and-implement` verdicts.

## Status

open — captured from consumer-project run findings. Guardrail that complements
root-cause fix FEAT-2652; the prompt-only tier is shippable independently.


## Resolution

**Tier 1 (prompt-only) shipped** — `commands/ready-issue.md`:
- Added a **Symbol Existence Gate (Branch-Aware)** subsection to Step 2 that runs
  the detached-HEAD-safe `git rev-parse --abbrev-ref HEAD` + `--show-toplevel`
  idiom, requires every symbol-existence claim to name the inspected branch, and
  emits a new `## INSPECTED_BRANCH` output section.
- The gate uses the `PASS | WARN | NOT_READY` three-state shape (mirroring the
  Learning-Test Gate): a suspected base-branch mismatch (EPIC child or differing
  declared `base_branch:`) is downgraded to a **WARN + `## CONCERNS` bullet**, not
  a hard `NOT_READY`. A "no target_branch declared" case is likewise a WARN.
- Added a `Symbol Existence` row to the VALIDATION table. The downstream parser
  (`output_parsing.parse_validation_table`) auto-absorbs the extra row — no parser
  change needed; the top-level verdict taxonomy is unchanged.

**Tests:** `scripts/tests/test_ready_issue_branch_transparency.py` (7 assertions:
branch-report command, worktree toplevel, detached-HEAD guard, `## INSPECTED_BRANCH`
section, Symbol Existence VALIDATION row, base-mismatch downgrade, three-state WARN).

**Deferred to a follow-up (Tier 2):** the optional `--target-branch <ref>` flag that
checks symbols against `git show <ref>:<file>` — it depends on the
`read_blob_at_ref` spike being promoted out of `scripts/tests/spike/` into
`little_loops/` (FEAT-2652 follow-on). Tier 1 ships independently as the issue
premised. Full suite: 15093 passed.

## Session Log
- `/ll:manage-issue` - 2026-07-16T00:30:14 - `c203f178-56b5-4ef7-bfa0-0ab6f2f1be06.jsonl`
- `/ll:ready-issue` - 2026-07-16T00:25:27 - `42f55224-bb02-4a99-b678-b4188cdaff34.jsonl`
- `/ll:wire-issue` - 2026-07-16T00:22:44 - `062c1c2f-97de-4dba-8be8-fd79c9580269.jsonl`
- `/ll:refine-issue` - 2026-07-16T00:17:30 - `14b85714-9b59-4e14-8def-14345bc850d6.jsonl`
