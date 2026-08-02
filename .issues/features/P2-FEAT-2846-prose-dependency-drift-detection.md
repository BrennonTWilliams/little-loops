---
id: FEAT-2846
type: FEAT
priority: P2
status: done
discovered_date: 2026-07-26
discovered_by: manual-review
labels:
- issues-cli
- dependency-graph
- linting
blocks:
- ENH-2847
relates_to:
- FEAT-2842
- BUG-2848
decision_needed: true
confidence_score: 95
outcome_confidence: 52
score_complexity: 10
score_test_coverage: 22
score_ambiguity: 10
score_change_surface: 10
size: Very Large
completed_at: '2026-07-27T03:06:47Z'
---

# FEAT-2846: Detect prose dependency claims that are missing from frontmatter

## Summary

Issue bodies routinely state dependencies in prose ("Depends on FEAT-109") that
never reach the `blocked_by:` frontmatter the dependency graph reads. The
sequencer has no way to know the edge exists, so it reports the issue as
unblocked. Add a shared prose-dependency extractor, surface drift as a
`format-check` gap, and provide a repo-wide sweep gated in the test suite.

## Current Behavior

`DependencyGraph.from_issues()` (`dependency_graph.py:56-146`) reads only the
structured frontmatter fields. It never parses issue bodies — correctly; the
graph algorithm is not the defect. The failure is upstream: nothing ensures a
prose dependency claim is mirrored into `blocked_by:`.

Observed in a downstream project: `ll-issues sequence` placed
FEAT-110 first with rationale `[P2, no blockers]`. FEAT-110's body says
"Depends on FEAT-109 (recovery + crash matrix)"; FEAT-109 is `status: open`.
FEAT-110 has no `blocked_by`, `blocks`, or `depends_on` key at all, so its
in-degree is 0 and Kahn's algorithm schedules it immediately.

**This repo has the same drift.** A probe over the 50 active issues in
`.issues/` found 9 (18%) with a prose dependency ID absent from both
`blocked_by` and `depends_on`:

```
EPIC-2149→ENH-2148   FEAT-2414→FEAT-2413   ENH-2580→ENH-2581
ENH-2582→ENH-2581    EPIC-2457→ENH-2581    EPIC-2575→FEAT-2576
EPIC-2765→ENH-2762   FEAT-2416→FEAT-2413   EPIC-2257→BUG-2266
```

Nothing detects this at authoring time or at read time.

The converse case also exists and must not become a false positive: an issue
whose prose "Blocked By" section names an issue that has since shipped. Parsing
prose without a status check would start reporting those as active blockers.

## Expected Behavior

Three layers, one extractor:

1. **`little_loops/issues/prose_deps.py`** — `extract_prose_deps(body) -> set[str]`.
   Frontmatter- and code-fence-aware (reuse the fence-skipping logic in
   `issues/anchor_sweep.py`). Canonical phrasings only: `Depends on <ID>`,
   `Blocked by <ID>`, `## Blocked By` section bodies, `Requires <ID>`. Strips
   `P\d-` prefixes and normalizes case. Deliberately conservative — recall
   matters less than not crying wolf.
2. **A `format-check` gap.** `check_format_gaps()` already has a taxonomy
   (`missing` / `renamed` / `empty` / `boilerplate` / `malformed_id`) that
   `ll-issues format-check` reports and the refine/ready skills consume. Add:
   - `prose_dep_drift` — prose names an **active** issue absent from
     `blocked_by`/`depends_on`.
   - `stale_prose_dep` — prose names a `done`/`cancelled` issue. Distinct code;
     the remedy is deleting stale text, not adding an edge.
   Reusing the existing taxonomy means no new command surface and free
   integration with every consumer of `format-check`.
3. **A repo-wide sweep**, gated in `python -m pytest scripts/tests/` per the
   project's no-hosted-CI policy. Not `ll-verify-docs` — that verifies
   documented counts; this belongs either as a `--all` mode on `format-check` or
   as a new `ll-verify-*` entry point following that family's conventions.

Skills enforce by **calling** layer 2, not by reading prose themselves:
`/ll:refine-issue`, `/ll:ready-issue`, and `/ll:wire-issue` treat
`prose_dep_drift` as a blocking gap. That puts a deterministic oracle behind an
LLM-driven check.

An opt-in `--fix` that backfills `blocked_by:` from confidently-matched prose is
worth having for the 9 issues above, but should stage a reviewable diff rather
than write silently — the `anchor-sweep --dry-run` posture. It should write via
`ll-issues link` (FEAT-2842) rather than editing frontmatter directly.

## Root Cause

Issue templates and authoring skills accept prose dependency statements without
requiring the structured mirror, and no read path reconciles the two. The
invariant "a prose dependency claim implies a frontmatter edge" was never
written down or enforced.

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/issues/prose_deps.py` — **NEW**: `extract_prose_deps(body) -> set[str]`
- `scripts/little_loops/issue_parser.py:136-165,191-283` — extend `FormatGaps` dataclass and `check_format_gaps()`
- `scripts/little_loops/cli/issues/format_check.py:19-20,35-73` — extend `cmd_format_check()` text/JSON rendering and subparser help string. Note: the taxonomy string is hardcoded **twice** in this file — the subparser `help=` (lines 19-20, already noted) AND the `cmd_format_check()` docstring itself (line 36, `"""Report structural format gaps (missing/renamed/empty/boilerplate/malformed_id) for an issue.`) — both need the new gap kinds appended.
- `commands/refine-issue.md`, `commands/ready-issue.md`, `skills/wire-issue/SKILL.md` — wire to call `format-check` / treat `prose_dep_drift` as blocking

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/verify_prose_deps.py` — **NEW, conditional**: only if the repo-wide sweep (Step 4) is built as a standalone `ll-verify-prose-deps` entry point rather than a `format-check --all` mode. Follow `scripts/little_loops/cli/verify_cli_allowlist.py`'s `_run()`/`main_verify_*()` shape.
- `scripts/little_loops/cli/__init__.py:90-144` — imports/exports every `main_verify_*` function; a new `main_verify_prose_deps` must be added here (conditional on the standalone-entry-point route).
- `scripts/little_loops/cli/doctor.py:455-489` — `ll-doctor --full`'s `_FULL_CHECKS` registry is **hand-registered, not auto-discovering** (confirmed by reading the code): each existing `ll-verify-*` has a dedicated `@register_full_check`-decorated adapter (e.g. `_full_docs_check` at `doctor.py:486-489`). A new `ll-verify-prose-deps` entry point needs its own adapter here or `ll-doctor --full` silently won't run it (conditional on the standalone-entry-point route).
- `skills/configure/areas.md` ("All ll- commands" preset) and `writers._LL_PERMISSIONS` — `ll-verify-cli-allowlist` (already in this repo, per CLAUDE.md) asserts every `ll-` entry point in `scripts/pyproject.toml` is mirrored in both. A new `ll-verify-prose-deps` registration in `pyproject.toml` without matching entries here will fail that existing gate (conditional on the standalone-entry-point route).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/dependency_graph.py:56-146` — `DependencyGraph.from_issues()`, the consumer this feature ultimately protects; needs no code change itself
- `commands/ready-issue.md:214-221,297,305` — has its own independent `## Blocked By` prose check today, not routed through `ll-issues format-check`; needs explicit wiring, not automatic pickup

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/__init__.py:53-56` — registers `cmd_format_check`/`add_format_check_parser`; confirms `check_format_gaps()`'s only production import chain runs through this file → `format_check.py` (no other production module imports `check_format_gaps`/`FormatGaps` directly — a signature change has exactly one production call site: `format_check.py:51`).
- `scripts/tests/test_issue_parser_unresolved.py:245` — imports `FormatGaps` directly as the second production-tree importer (besides `issue_parser.py` itself); check whether it instantiates `FormatGaps()` positionally before adding new dataclass fields.
- `scripts/tests/test_ready_issue_lint.py` — ready-issue's prose "Blocked By" lint tests; may need updates once `ready-issue.md`'s independent check is wired to (or replaced by) `format-check`'s `prose_dep_drift`.

### Similar Patterns
- `scripts/little_loops/issues/anchor_sweep.py` — `_sweep_file()`/`sweep_issues()`: fence-span skip via `_CODE_FENCE` (`text_utils.py`), `_ACTIVE_CATEGORIES` directory walk, per-file `OSError` isolation
- `scripts/little_loops/cli/verify_cli_allowlist.py` — `_run()`/`main_verify_cli_allowlist()`: the `ll-verify-*` entry-point convention (pure `_run()` returns `(exit_code, data)`, wrapped in `cli_event_context`), registered at `scripts/pyproject.toml:101`
- `scripts/little_loops/cli/issues/link.py:92-176` — `cmd_link()`: idempotent frontmatter list-field writer with `--dry-run` and `_check_cycle()` guard; the target for the optional `--fix`

### Tests
- `scripts/tests/test_ll_issues_format_check.py` — existing format-check tests; inline fixture-string convention, `format_check_dir` fixture, in-process `_invoke()` helper — model for the new gap-kind tests
- `scripts/tests/test_issue_parser.py` — `check_format_gaps`/`FormatGaps` unit tests
- `scripts/tests/test_dependency_graph.py`, `test_link_cli.py`, `test_issues_anchors.py` — related coverage
- `scripts/tests/test_verify_cli_allowlist.py` — in-process gate-test pattern to follow for the repo-wide sweep (not `test_policy_builder_node_gate.py`'s subprocess-wrap style, which is for a different toolchain)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_parser.py:3719-3838` (`TestFormatGradedChecker`) — the exact 7 direct `check_format_gaps(...)` call sites (lines 3734,3752,3772,3792,3811,3829,3837) that would break with a `TypeError` **only if** the new `issue_statuses` param is added without a default; safe if given `= None`. Every one of these tests also asserts `has_gaps is False` on a clean fixture — since `has_gaps` ORs across all categories, these assertions stay correct only if the clean fixture body has no prose dependency phrasing.
- **New test module needed**: no existing test file covers `sweep_issues()`/`_sweep_file()` in `scripts/little_loops/issues/anchor_sweep.py` end-to-end (only `resolve_anchor()` is unit-tested, in `test_issues_anchors.py`) — the fence-span-skip scanning logic `prose_deps.py` most closely mirrors has no direct test precedent to copy; author the corpus from scratch per Implementation Step 1's own list (fenced code, `P2-FEAT-109` prefix forms, `## Blocked By` sections, self-references, link-target IDs).
- `scripts/little_loops/text_utils.py:21` (`_CODE_FENCE` regex) — shared fence-skip primitive already used by `anchor_sweep.py` and `is_formatted()`; reuse directly rather than redefining the pattern in `prose_deps.py`.
- If the standalone `ll-verify-prose-deps` route is chosen: new test module following `scripts/tests/test_verify_cli_allowlist.py`'s exact three-tier shape (pure-function unit tests → `_run()` with `patch(...)` for the dirty-state branch → `main_verify_*()` with `patch("sys.argv", ...)` asserting exit code + `capsys` stderr).

### Documentation
- `docs/reference/CLI.md` — `ll-issues format-check` subcommand docs; would need a new entry if a standalone `ll-verify-prose-deps` route is chosen over a `format-check --all` mode
- `docs/reference/API.md` — module reference for `DependencyGraph` and the new `prose_deps` module

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:1611` — taxonomy prose sentence ("reports gaps in five classes: `missing`... `malformed_id`") needs the two new classes appended.
- `docs/reference/CLI.md:1621` — separate hardcoded `--format json` example showing the five-key JSON shape `{"missing": [...], ..., "malformed_id": [...]}` — a second, distinct edit site from the taxonomy sentence above.
- `docs/reference/API.md:843` — exact `check_format_gaps()` signature line; update if `issue_statuses` param is added.
- `docs/reference/API.md:848-853` — five gap-class bullets; add `prose_dep_drift`/`stale_prose_dep` bullets.
- `docs/reference/API.md:859` — fail-open behavior sentence; fold in the new gap kinds' fail-open semantics (e.g. what happens if the status lookup for `stale_prose_dep` is unavailable).
- `.claude/CLAUDE.md` CLI Tools list — needs a new bullet if `ll-verify-prose-deps` is registered (conditional on that route).

### Configuration
- `scripts/pyproject.toml:69-102` — `[project.scripts]` `ll-verify-*` registrations; exact line format to copy if a new `ll-verify-prose-deps` entry point is chosen

## Implementation Steps

1. Write `prose_deps.py` with the extractor and a test corpus covering: fenced
   code containing `Depends on FEAT-1`, `P2-FEAT-109` prefix forms, `## Blocked
   By` sections, self-references, and IDs inside link targets.
2. Extend `check_format_gaps()` with the two new gap kinds; thread the referenced
   issues' statuses in (needs a lookup — check whether `check_format_gaps` has
   backlog access today or needs a new parameter).
3. Extend `ll-issues format-check` text and `--json` output.
4. Add the repo-wide sweep mode plus its pytest gate.
5. Update `/ll:refine-issue`, `/ll:ready-issue`, `/ll:wire-issue` to call it and
   treat `prose_dep_drift` as blocking.
6. Optional `--fix`, dry-run by default, writing via `ll-issues link`.
7. Fix the 9 drifting issues in this repo.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step 2's open question is answered**: `check_format_gaps(issue_path: Path,
  templates_dir: Path | None = None) -> FormatGaps`
  (`scripts/little_loops/issue_parser.py:191-283`) has **no backlog/status
  parameter today** — it reads only the single issue's own content plus its
  template's `sections_data`. `stale_prose_dep` detection (which needs another
  issue's current status) requires either a new optional parameter (e.g.
  `issue_statuses: dict[str, str] | None`, following the "fails open when data
  absent" pattern already used in this module) or resolving status in the
  caller and merging results — `check_format_gaps` has no existing hook into
  `find_issues()`/backlog status.
- The `FormatGaps` dataclass (`issue_parser.py:136-165`) is a flat
  `list[str]`-per-category shape with a `has_gaps` property and `to_dict()`;
  the sibling `QuestionGaps` dataclass (lines 168-188) is documented as a
  "mirror" of this shape — confirms `prose_dep_drift`/`stale_prose_dep` should
  follow the same two-field convention.
- `cmd_format_check()` (`scripts/little_loops/cli/issues/format_check.py:35-73`)
  is the **sole** production consumer of `check_format_gaps()` today. It has a
  fixed-order text-rendering loop (`missing` → `renamed` → `empty` →
  `boilerplate` → `malformed_id`) and a hardcoded taxonomy list in the
  subparser `help=` string (lines 19-20) — both need parallel additions for
  the two new gap kinds.
- **Step 5's integration is not a no-op**: none of `/ll:refine-issue`,
  `/ll:ready-issue`, `/ll:wire-issue` currently shell out to `ll-issues
  format-check` at all. `commands/ready-issue.md` has its own independent
  `## Blocked By` prose check (lines 214-221, outcome logic at 297/305) that
  reads the markdown section directly rather than calling the CLI — so wiring
  `prose_dep_drift` in means either replacing that inline check with a
  `format-check` call or adding a second, parallel check.
- `scripts/little_loops/issues/anchor_sweep.py` is the template for step 1's
  scanner shape: `_sweep_file()` (lines 59-97) precomputes `fence_spans` via
  `_CODE_FENCE.finditer()` (imported from `little_loops/text_utils.py`), then
  uses an `_in_fence(start, end)` closure to skip matches inside fenced code;
  `sweep_issues()` (lines 100-120) drives the repo-wide walk over
  `_ACTIVE_CATEGORIES = ("bugs", "features", "enhancements", "epics")`
  subdirs, isolating per-file `OSError`s so one bad file doesn't abort the
  sweep — directly reusable for step 4's sweep driver. Frontmatter is not
  regex-skipped in this module; a prose scanner should call
  `little_loops.frontmatter.parse_frontmatter()` first and scan only the body
  portion.
- For step 4's sweep-gate, the closer analog is the in-process
  `scripts/tests/test_verify_cli_allowlist.py` style (call `_run()` /
  `main_verify_*()` directly, assert `exit_code == 0`) rather than
  `scripts/tests/test_policy_builder_node_gate.py`'s subprocess-wrap style,
  which is reserved for a different-toolchain gate (Node), not a same-language
  Python sweep.
- For step 6's `--fix`, `cmd_link()` (`scripts/little_loops/cli/issues/link.py:92-176`)
  is idempotent (no-ops to `unchanged` if the edge already exists), supports
  `--dry-run` (`would_link`/`would_unlink` status), and gates every write
  through `_check_cycle()` — builds a `DependencyGraph` including the
  prospective edge and calls `topological_sort()`, catching `ValueError` on a
  cycle — before allowing a `blocked_by`/`depends_on` write. `--fix` should
  invoke this (in-process or via `ll-issues link <id> --blocked-by <target>`),
  not call `update_frontmatter()` directly.

### Behavioral Side Effect (not a file change, but a consequence to plan for)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/rn-remediate.yaml:98-113` — the `ensure_formatted` gate checks `check_format_gaps(...).has_gaps` via `exit_code` only (not per-category), so any issue with prose-dependency drift will start routing to `format_issue` remediation once the new gap kinds land — an intentional but repo-wide behavior change worth calling out in the PR description, not a file to edit.

## Use Case

As someone planning the next work item, I run `ll-issues sequence` and trust
that an issue shown as unblocked really is — because any issue whose body claims
a dependency it never recorded was caught by `format-check` during refinement
and either wired up or corrected. As a backlog owner adopting this on an
existing project, the repo-wide sweep tells me up front which issues drifted
before the rule existed, instead of discovering them one mis-scheduled issue at
a time.

## Acceptance Criteria

- [ ] `extract_prose_deps()` ignores IDs inside fenced code blocks and inside
      frontmatter.
- [ ] An issue with `Depends on FEAT-109` in prose and no `blocked_by` reports
      `prose_dep_drift` from `ll-issues format-check`.
- [ ] An issue whose prose names a `done` issue reports `stale_prose_dep`, not
      `prose_dep_drift`.
- [ ] The repo-wide sweep runs under `python -m pytest scripts/tests/` and
      passes once this repo's 9 drifting issues are corrected.
- [ ] No GitHub Actions workflow is added.

## Impact

- **Users**: `ll-issues sequence`, `next-issue`, and wave planning stop
  scheduling work whose prerequisites are unfinished. The current failure is
  silent and indistinguishable from a correct answer.
- **Risk**: Low-Medium. The extractor will have false positives; keeping it a
  reported gap (with `--fix` opt-in and dry-run) rather than an ordering input
  bounds the blast radius.
- **Effort**: Medium.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `scripts/little_loops/issues/anchor_sweep.py` | Fence-skipping body scanner to reuse |
| `scripts/little_loops/issue_parser.py` — `check_format_gaps` | Gap taxonomy to extend |
| `scripts/little_loops/dependency_graph.py:56-146` | Why prose is invisible today |
| `.claude/CLAUDE.md` § Testing & CI Policy | Gate belongs in the local pytest suite |

## Context

Traced from a downstream project's `ll-issues sequence` run that reported a
blocked issue as `[P2, no blockers]`; the same drift was then confirmed in this
repo's own backlog.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-26_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 52/100 → LOW

### Outcome Risk Factors
- Step 3's format-check `--all` mode vs. a new standalone `ll-verify-prose-deps`
  entry point is left as an open decision point — the issue phrases it as
  "either as a `--all` mode on `format-check` or as a new `ll-verify-*` entry
  point" and threads "conditional on the standalone-entry-point route" through
  ~8 downstream Files-to-Modify/Dependent-Files/Tests/Documentation entries
  (`verify_prose_deps.py`, `cli/__init__.py`, `doctor.py`, `pyproject.toml`,
  `CLAUDE.md`, docs). Resolving this route choice before implementation
  collapses the conditional branches into a single concrete file list.
- Depth is Moderate, not purely mechanical: `check_format_gaps()` needs a new
  status-lookup parameter (`issue_statuses`) threaded from the caller for
  `stale_prose_dep`, and Step 5's skill wiring is a real behavior change
  (`ready-issue.md`'s existing inline prose check must be reconciled with, not
  just supplemented by, the new `format-check` gap) — broad enumeration across
  many touch points combined with non-uniform per-site logic (deep per-site
  complexity on the status-threading and skill-reconciliation sites) is what
  drives the low outcome-confidence score, not readiness.

## Session Log
- `/ll:decide-issue` - 2026-07-27T03:01:20 - `e544f15c-8f0e-4ca2-9209-d4f33625112f.jsonl`
- `/ll:confidence-check` - 2026-07-26T00:00:00 - `3631dc0e-0144-4e1b-9cf6-91d068e6bdfb.jsonl`
- `/ll:wire-issue` - 2026-07-27T02:57:59 - `af01e05c-9dda-44a1-accf-89cccdffc7ed.jsonl`
- `/ll:refine-issue` - 2026-07-27T02:52:54 - `dd9c5a7b-99a8-4eeb-b962-5cbd76412b9c.jsonl`
- `/ll:issue-size-review` - 2026-07-26T00:00:00 - `52f8c37a-8768-4813-8704-c3364dbd6e28.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-07-26
- **Reason**: Issue too large for single session (score 11/11, Very Large)

### Decomposed Into
- FEAT-2849: Prose dependency extractor + format-check gap taxonomy + skill wiring
- FEAT-2850: Repo-wide prose-dependency sweep gated in pytest
- FEAT-2851: Optional --fix to backfill blocked_by from prose dependencies

---

## Status

done

---

## Resolution

- **Status**: Decomposed
- **Closed**: 2026-07-27
- **Decomposed into**: FEAT-2849, FEAT-2850, FEAT-2851

Work for FEAT-2846 is now carried by its child issues; this parent was closed by rn-decompose.
