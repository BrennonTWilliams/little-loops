---
id: ENH-2535
title: 'll-issues show: surface closure context, relationships, discovery, and decision
  coupling'
type: ENH
priority: P2
status: open
captured_at: '2026-07-07T22:52:13Z'
discovered_date: 2026-07-07
discovered_by: capture-issue
labels:
- cli
- issues
- ux
- developer-ergonomics
decision_needed: false
confidence_score: 100
outcome_confidence: 86
score_complexity: 16
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 23
---

# ENH-2535: ll-issues show: surface closure context, relationships, discovery, and decision coupling

## Summary

`ll-issues show` (single-issue summary card, `scripts/little_loops/cli/issues/show.py:_parse_card_fields`)
currently surfaces only a subset of the frontmatter that real issues actually
carry. Across the live `.issues/` tree, several high-traffic fields are present
but invisible on the card:

| Field | Count in tree | Currently shown? |
|-------|--------------:|------------------|
| `discovered_date` | 2,111 | No |
| `parent` | 677 | No |
| `relates_to` | 585 | No |
| `depends_on` | 158 | No |
| `blocked_by` | 107 | No |
| `discovered_commit` | 322 | No |
| `discovered_branch` | 305 | No |
| `testable` | 105 | No |
| `closing_note` / `closed_reason` / `cancelled_reason` / `deferred_reason` | ~20 combined | No |
| `affects` | 16 | No |
| `focus_area` | 30 | No |
| `decision_ref` | 13 | No |

The card's purpose is to make a single issue answerable at a glance. Three
classes of question are currently un-answerable from the card alone:

1. **"How did this end?"** — `closing_note` / `closed_reason` / `cancelled_reason`
   / `deferred_reason` / `closed_by` / `closed_at` / `deferred_date` are all
   silent on `done` / `cancelled` / `deferred` issues.
2. **"Where does this fit?"** — `parent` (epic), `relates_to`, `depends_on`,
   `blocked_by`, `blocks`, `supersedes`, `decomposed_into` are all invisible.
   When `status: blocked`, the card says "Blocked" but never names what blocks.
3. **"When / where was this found?"** — `discovered_date` (when the bug/feature
   was *observed*, distinct from `captured_at` when the file was *written*),
   plus `discovered_commit` / `discovered_branch` (git-bisect anchor) and
   `discovered_source` / `discovered_external_repo` (upstream provenance) are
   all missing.

Plus a fourth, narrower fix: `decision_needed: true` is rendered as bare
`true`; the actionable pointer `decision_ref` (e.g. `ARCHITECTURE-049`) is not
shown alongside it, so users see "Decision needed: true" with no path forward.

## Context

This issue was captured from a direct `/ll:capture-issue` invocation following
a gap analysis of `_parse_card_fields` (file:
`scripts/little_loops/cli/issues/show.py`, function at lines 127–302) against
the frontmatter field inventory across `bugs/`, `features/`, `enhancements/`,
`epics/`. The fields listed above are the high-leverage (high occurrence ×
high operational value) and medium-leverage gaps that are cheap to render as
single-line groups.

## Current Behavior

`ll-issues show <id>` renders a card with: title, type/priority/status/effort/risk,
confidence + outcome scores, dimension scores (cmplx/tcov/ambig/chsrf), summary,
labels + integration file count + milestone, captured_at/completed_at, session
history, path. Three frontmatter categories — closure context, relationships,
discovery — are entirely absent, and the existing `decision_needed` /
`missing_artifacts` / `learning_tests_required` fields render as bare
booleans / comma-joined lists without paired context.

## Expected Behavior

The card gains three new conditional blocks and one rendering fix:

1. **Closure Context** — when `status` is `done` / `cancelled` / `deferred` /
   `closed`, render `closing_note` (or `closed_reason` / `cancelled_reason` /
   `deferred_reason` depending on status), `closed_by`, `closed_at` /
   `deferred_date` adjacent to the existing `completed_at`. Single line group,
   only present when status is terminal-non-open and any of those fields exist.

2. **Relationships** — render `parent`, `relates_to`, `depends_on`,
   `blocked_by`, `blocks`, `supersedes`, `decomposed_into` as a single
   line group (or two if it overflows). Each edge type only shows when non-empty.
   For `parent`, render as `Parent: EPIC-1234 (title)` so the user can read the
   epic context without opening the file.

3. **Discovery** — render `discovered_date` (distinct from `captured_at`),
   `discovered_commit` (short SHA + link), `discovered_branch`, `discovered_source`,
   `discovered_external_repo`. BUGs benefit most here (gives the git-bisect
   anchor); FEAT/ENH/EPIC benefit from `discovered_date` separation.

4. **Decision coupling** — when `decision_needed: true`, render
   `Decision needed → <decision_ref>` (e.g. `Decision needed → ARCHITECTURE-049`).
   When `decision_needed: false`, render `Decision needed: no` explicitly so
   absence isn't confusable with unset. When `decision_ref` is set without
   `decision_needed`, render `Decision ref: <value>` as its own line.

5. **Quality-of-life rendering fixes** for fields already on the card:
   - `learning_tests_required`: distinguish `not required` from
     `required (n targets: a, b, c)`.
   - `missing_artifacts`: render count when list, otherwise bare `true` / `false`.

## Proposed Solution

All five changes are local to `_parse_card_fields` (extract) and
`_render_card` (display) in `scripts/little_loops/cli/issues/show.py`. No new
dependencies. Pattern follows the existing detail_lines block (lines 372–399) —
each new block is a list of `Key: value` strings appended to `detail_lines`
when at least one field in the group is populated.

Concretely:

- Extract the new fields in `_parse_card_fields` alongside the existing
  `decision_needed_raw` / `missing_artifacts_raw` / `learning_tests_raw`
  block (lines 186–189). Use the same `str(x).lower() if x is not None else None`
  idiom for booleans, and `", ".join(...)` for list-typed fields.
- Add three conditional builders in `_render_card`:
  - `_render_closure_block(fields)` — invoked only when `status` indicates
    a terminal-non-open state and at least one closure field is non-None.
  - `_render_relationships_block(fields)` — invoked when any of the seven
    edge-type fields is non-empty.
  - `_render_discovery_block(fields)` — invoked when `discovered_date` /
    `discovered_commit` / `discovered_branch` / `discovered_source` /
    `discovered_external_repo` is non-None.
- Insert the rendered lines into `detail_lines` at appropriate points
  (suggested: closure at end, relationships between labels and captured_at,
  discovery between captured_at and history).
- Update the `decision_needed` rendering to consult `decision_ref` and emit
  the coupled form.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Width handling — no manual recalc needed:**

- `_render_card` width calculation at `show.py:404-412` already does
  `structural_lines.extend(detail_lines)` BEFORE `wrap_width = max(...)`.
  Any new lines appended to `detail_lines` are auto-accounted for.
  AC #3 ("width calculation accounts for the longest possible new line")
  is satisfied implicitly — no separate recalc required.
- Caveat from analyzer: `_ljust` and `: <{width-1}` use **padding only**,
  not truncation. A long unbreakable token (e.g., full `discovered_commit`
  SHA) could bleed past the right border. Mitigation: render the SHA
  short-form (first 7 chars) in the card line; full SHA stays in
  `--json`. Existing test at `scripts/tests/test_show.py` `test_long_unbreakable_word_extends_box`
  confirms the bleed behavior — document this as the rationale for
  short-SHA rendering in the Discovery block.

**JSON contract — additive only:**

- `cmd_show` at `show.py:484-509` writes the raw `fields` dict to
  `print_json(fields)` (lines 504-507). There is **no schema, no key
  filter, no type coercion** beyond what `_parse_card_fields` enforces
  (everything `str | None`). All new keys appear in `--json` output
  automatically. This validates the issue's "Breaking Change: No" claim.

**Terminal-status gate set:**

- Canonical closed/cancelled/deferred indicator is `_STATUS_DISPLAY`
  at `show.py:164-173`:
  ```python
  _STATUS_DISPLAY = {
      "done": "Completed",
      "cancelled": "Cancelled",
      "deferred": "Deferred",
      "in_progress": "In Progress",
      "blocked": "Blocked",
      "open": "Open",
  }
  ```
  Note: there is **no `"closed"` key** — `closed` is not a status value.
  Closure-context block gate = `status in {"done", "cancelled", "deferred"}`
  (the same set used by `_TERMINAL_STATUSES` at
  `scripts/little_loops/issue_progress.py:12-14` plus `deferred`).

**Per-status reason field mapping:**

- Status `done` → `closing_note`, `closed_by`, `closed_at` (and possibly
  legacy `closed_reason`).
- Status `cancelled` → `cancelled_reason` (no `closed_at`).
- Status `deferred` → `deferred_reason`, `deferred_date`.
- The issue's "or `closed_reason` / `cancelled_reason` / `deferred_reason`
  depending on status" already covers this; just confirm the per-status
  helper in `_render_closure_block` reads from the right field.

**Existing detail_lines pattern (verbatim, lines 372-399):**

- Two rendering styles coexist: horizontal `│`-joined multi-part line
  (e.g., `Integration / Labels / Milestone`) at lines 385-393, and
  singleton per-line appends (`Captured at: ...`, `Completed at: ...`,
  `History: ...`) at lines 394-399. Use the singleton style for the
  new blocks (each is its own logical section, not a multi-part group);
  or the horizontal style for the Relationships block if compact form
  fits within 80 cols (otherwise fall back to singleton per-edge-type).

**Boolean/list normalization (verbatim, lines 290-301):**

- For booleans: `str(x).lower() if x is not None else None` — passes
  Python `True`/`False` AND string `"True"`/`"False"` through uniformly.
- For lists: `", ".join(str(t) for t in x) if x else None` — falsy empty
  list returns `None`; non-empty becomes comma-string. Use this for
  `parent`/`relates_to`/etc., OR resolve list-of-IDs to title strings
  via the `parent_titles` pattern (see Integration Map findings) before
  joining.

## Impact

- **Priority**: P2 — Developer-ergonomics ENH affecting one CLI command;
  affects every triage / `/ll:ready-issue` / archive review session.
  Not P3 because the closure-context gap alone makes `ll-issues show`
  near-useless on `done` / `cancelled` issues (the most common archive query).
- **Effort**: Small — Pure additive rendering: extend one extraction function
  + three small render helpers + tests. Reuses the existing detail_lines
  construction pattern verbatim. No new dependencies, no new files.
- **Risk**: Low — Card is a read-only display. Worst-case regression is
  visual overflow at narrow terminal widths (covered by acceptance criteria);
  no behavior change to `cmd_show --json` consumers (return-dict shape is
  preserved as `dict[str, str | None]`; new keys are additive only).
- **Breaking Change**: No — Pure additive display. Issues lacking any new
  field render identically to today. JSON output gains new keys but no
  existing key changes shape.

## Scope Boundaries

**In scope:**
- Conditional rendering of three new blocks (closure, relationships,
  discovery) on the card.
- Decision-coupling rendering for `decision_needed` / `decision_ref`.
- Quality-of-life fixes for `learning_tests_required` and `missing_artifacts`
  rendering.
- Tests in `scripts/tests/test_show.py` covering each new block plus a
  regression case.

**Out of scope:**
- Any change to the data model (frontmatter schema, validation, lint).
  This ENH only consumes fields that already exist in real issues.
- `ll-issues list` or other summary views. `show` is the per-issue card;
  list views are a separate surface.
- New frontmatter fields. If a field doesn't already appear in real
  issues, it doesn't belong here.
- Backfill / migration of existing issues. All needed data is already
  present in frontmatter; this ENH just surfaces it.
- Rendering changes to the `cmd_show --json` consumer contract. The
  JSON dict grows new keys but no existing key's type changes.
- Performance: card rendering stays O(1) per issue; no caching needed.

## Implementation Steps

1. Read `scripts/little_loops/cli/issues/show.py:127-302` (`_parse_card_fields`)
   and `:311-481` (`_render_card`) to map the existing extraction and rendering
   patterns.
2. Extend the extraction block (after line 189) with the new fields:
   `discovered_date`, `discovered_commit`, `discovered_branch`,
   `discovered_source`, `discovered_external_repo`, `parent`, `relates_to`,
   `depends_on`, `blocked_by`, `blocks`, `supersedes`, `decomposed_into`,
   `closing_note`, `closed_reason`, `cancelled_reason`, `deferred_reason`,
   `closed_by`, `closed_at`, `deferred_date`, `decision_ref`, `testable`,
   `affects`, `focus_area`.
3. Add three private helpers in `show.py`:
   - `_render_closure_block(fields, status)` — guarded by status.
   - `_render_relationships_block(fields)` — guarded by any edge field.
   - `_render_discovery_block(fields)` — guarded by any discovery field.
4. Insert the rendered strings into `detail_lines` in `_render_card` at the
   positions described in Proposed Solution.
5. Update the `decision_needed` line to render
   `Decision needed → <decision_ref>` when both true.
6. Add tests in `scripts/tests/test_show.py` (existing test file, located
   via `find scripts/tests -name "test_show.py"`). Cover:
   - Closure block present for `status: done` with `closing_note`.
   - Closure block absent for `status: open`.
   - Relationships block renders `parent: EPIC-1234 (title)`.
   - Relationships block renders `blocked_by` when set.
   - Discovery block renders `discovered_date` distinct from `captured_at`.
   - Decision coupling renders `Decision needed → ARCHITECTURE-049`.
   - Regression: an issue with NONE of the new fields renders identically to
     pre-change behavior (no empty sections, no extra blank lines).
7. Verify `ruff check scripts/` and `python -m mypy scripts/little_loops/`
   pass on the modified file.
8. Run the full `python -m pytest scripts/tests/` suite and confirm the
   existing `test_show.py` cases still pass plus the new cases.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be
included in the implementation:_

9. **Stale-comment refresh trio** — three pieces of documentation become
   factually stale once `ll-issues show --json` exposes `blocked_by` (and
   `decision_ref` becomes reachable alongside `decision_needed`):

   9a. Update `scripts/little_loops/loops/rn-implement.yaml:367-370` (and
   the parallel comment at line 482-486) to acknowledge that `blocked_by`
   is now exposed in `--json`, while preserving the deliberate direct-
   frontmatter-parse posture for the `check_blocked_by` gate (the
   rationale is shell-escape-safety and consistency with
   `select_next`, not the JSON projection gap).

   9b. Update `scripts/tests/test_rn_implement.py:863-878` docstring —
   `test_check_blocked_by_parses_frontmatter_not_show_json` — to reflect
   that ENH-2535 closes the underlying JSON gap without changing the
   test's intent. The `assert ".blocked_by" not in action` check
   (line 878) remains valid; only the docstring text needs refresh.

   9c. Update `docs/guides/LOOPS_REFERENCE.md:404` — `blocked_by`
   pre-gate description — to note ENH-2535 as the issue that closed
   the JSON-exposure gap.

10. **Doc coverage expansion** — touch the additional doc surfaces
    identified by the wiring pass that the existing Implementation
    Steps miss:

    10a. Update `docs/guides/LOOPS_REFERENCE.md:145` — `check_scores_from_file`
    description — with a parenthetical noting `decision_needed →
    decision_ref` exposure.

    10b. Update `commands/review-sprint.md:129` — Phase 3f EPIC Context —
    to note ENH-2535 closes the `parent:` JSON-exposure gap (the
    parenthetical fallback to direct frontmatter read remains correct
    but the framing shifts from "or" to "and fallback").

11. **Test coverage expansion** — extend Implementation Step 6 with
    these new assertions:

    11a. Add a regression guard in
    `scripts/tests/test_set_scores_cli.py` — verify that
    `data["decision_ref"] is None` for the synthetic test issue, so
    the rendering fix doesn't accidentally populate it.

    11b. New inline-frontmatter test cases in `test_show.py` for
    `parent`, `blocked_by`, `closing_note`, and `decision_ref` —
    reuse the `_write_issue` helper at `test_show.py:149-158` (the
    helper accepts raw markdown including frontmatter, no new
    fixture files needed for these 4 cases).

    11c. `stable_snapshot_env` regression guard in `TestRenderCard`
    — assert that an issue with NONE of the new frontmatter fields
    produces a byte-equal card to the pre-change baseline (the
    `test_show_new_fields_absent_gracefully` test at
    `test_issues_cli.py:2460-2493` already protects end-to-end,
    but a unit-level guard is cheap insurance).

12. **Verification** (extends step 7-8):

    12a. `ruff check scripts/` and `python -m mypy
    scripts/little_loops/cli/issues/show.py` — confirm no signature
    drift on `_parse_card_fields` / `_render_card` / `cmd_show`.

    12b. `grep -rn "len(fields.keys())" scripts/ skills/ commands/
    loops/` — confirm no fixed-shape JSON consumer has appeared
    since the wiring pass (regression sentinel).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Concrete line-number anchors for each step:**

- Step 1 (`_parse_card_fields` map): `show.py:127-302`. The existing
  `decision_needed_raw`/`missing_artifacts_raw`/`learning_tests_raw`
  block at `show.py:186-189` is the exact insertion neighborhood for
  the new fields.
- Step 1 (`_render_card` map): `show.py:311-481`. The detail_lines
  construction at `show.py:372-399` is the structural template.
- Step 2 extraction insertion point: after line 189 (current end of
  the boolean-raw / list-raw cluster) and before line 200 (summary
  body regex start). Maintain the `*_raw` → normalized-str pattern.
- Step 3 helper insertion point: between line 302 (end of
  `_parse_card_fields`) and line 305 (start of `_ljust` helper). Three
  small private helpers, each returning `list[str]`.
- Step 4 detail_lines insertion positions:
  - Discovery block: AFTER `Captured at` (line 395) and BEFORE
    `Completed at` (line 397) — keeps the temporal-discovery→capture→complete
    ordering natural.
  - Relationships block: BEFORE `Captured at` (line 395) — i.e., between
    the mid-border (line 393) and the singleton lines. Keeps relationship
    metadata adjacent to labels/milestone.
  - Closure block: AFTER `History:` (line 399) — at the tail of the
    detail_lines list, just before the path section.
- Step 5 `decision_needed` line update: search for `"decision_needed"`
  in the returned dict (line 290) and the corresponding render site
  (currently absent — `_render_card` never reads `decision_needed`).
  Add a new conditional append in detail_lines around the new
  decision-coupling line.

**Test fixture reuse:**

- New test cases should leverage the existing
  `_make_config(tmp_path, categories)` and `_write_issue(content, filename)`
  helpers at `scripts/tests/test_show.py:54-71` and `:149-158`. Pass a
  string-literal frontmatter body to `_write_issue`, run
  `_parse_card_fields(path, config)`, assert on the dict (for
  extraction tests), and assert on the rendered card string (for
  rendering tests via `TestRenderCard` at `scripts/tests/test_show.py:273-313`).
- Use the `stable_snapshot_env` fixture from
  `scripts/tests/conftest.py:109-123` for render tests (disables ANSI,
  pins terminal width to 80) — required for stable substring assertions.

**Pre-built frontmatter for discovery tests:**

- Existing fixtures at `scripts/tests/fixtures/issues/bug-with-product-impact.md`
  and `bug-no-product-impact.md` already populate `discovered_commit`,
  `discovered_branch`, `discovered_date`. New discovery-block tests can
  reuse these instead of constructing inline frontmatter.

**Regression case (AC #2, no new fields renders identically):**

- Test: pass `frontmatter={}` (no new fields, only the existing
  identity fields) → assert rendered card string is byte-equal to the
  pre-change output for the same input. The empty-`detail_lines`
  behavior at `show.py:473` (`if detail_lines:`) guarantees the
  mid-border separator is skipped, so the path section is the last
  block. Verify this in the regression test.

**Predecessor issues (validation of approach):**

- `FEAT-1179` ("show captured_at completed_at fields") is the closest
  prior analog — it added the `Captured at:` / `Completed at:` singleton
  lines (current `show.py:394-399`). Reading its diff confirms the
  pattern: extend extraction, append singleton, recalc width (no-op
  due to extend-into-structural-lines). Apply the same shape here.

## Acceptance Criteria

- All five new sections render for issues that have the relevant fields.
- Issues without any of the new fields render exactly as they do today
  (no regression on the 677-issue parent sample, the 2092-issue completed_at
  sample, etc).
- `_render_card` width calculation accounts for the longest possible new
  line, no box-drawing overflow at 80 columns.
- `decision_needed: true` paired with `decision_ref` shows the coupled form;
  `decision_needed: false` shows explicit "no".
- `learning_tests_required` distinguishes `not required` from a populated list.
- `missing_artifacts` distinguishes boolean `true` from a populated list.
- Test coverage in `scripts/tests/test_show.py` for all five additions plus
  the regression case (existing card with zero new fields).

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/issues/show.py` — extend `_parse_card_fields`
  (extract 20+ new fields) and `_render_card` (three conditional blocks +
  decision-coupling line + learning/missing rendering fixes). No public API
  changes; `cmd_show` signature unchanged.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/issues/__init__.py` — re-exports `cmd_show`;
  unaffected.
- Any tests or commands that import `_render_card` / `_parse_card_fields`
  directly: `grep -r "_render_card\|_parse_card_fields" scripts/` should
  be re-run to confirm the return-type contract (still `dict[str, str | None]`)
  is preserved for `cmd_show --json` callers.
- Sibling importers of `_resolve_issue_id` (NOT affected by this ENH —
  listed for completeness only): `scripts/little_loops/cli/issues/path_cmd.py:24`,
  `skip.py:29`, `set_status.py:33`, `set_scores.py:27`, `check_flag.py:23`,
  `check_decidable.py:26`, `check_readiness.py:28`, `format_check.py:41`,
  `history_context.py:92`.

_Wiring pass added by `/ll:wire-issue`:_

**Subprocess consumers of `ll-issues show --json` (loop YAMLs)** — all read
additive-safe key subsets; no fixed-shape JSON consumers found (confirmed by
searches for `len(fields.keys()) == N` across `scripts/`, `skills/`,
`commands/`, `loops/`). None require code changes, but they gain access to
newly exposed keys:

- `scripts/little_loops/loops/autodev.yaml:585-588` — `triage_outcome_failure`
  Python consumer reads `score_ambiguity` + `decision_needed`; will gain
  new `decision_ref` pointer for `decision_needed: true` cases.
- `scripts/little_loops/loops/rn-remediate.yaml:158, 322-328, 628` —
  writes pre/post score snapshots via `--json`; reads `confidence`/`outcome`.
  Add `closing_note`/`closed_reason` reads here if remediation needs to
  respect prior closure context (not in this ENH's scope — flag for follow-on).
- `scripts/little_loops/loops/rn-decompose.yaml:60` — writes
  `size_review_snap_<ID>.json` via `--json`; additive-safe.
- `scripts/little_loops/loops/oracles/verify-confidence-scores.yaml:34-40,
  80-86` — reads `confidence` and `outcome` only; additive-safe.

**Comments that will become stale once `--json` exposes `blocked_by`** —
refresh as a courtesy (these are doc comments / test docstrings, not code
logic; assertions still pass):

- `scripts/little_loops/loops/rn-implement.yaml:367-370` — comment block
  claims "`ll-issues show --json` does NOT expose `blocked_by` (returns
  null)". After ENH lands, `blocked_by` IS exposed. Update the comment to
  reflect the new behavior, OR (preferred) leave the deliberate-direct-
  parse-and-don't-revert rationale — `git grep show --json | jq .blocked_by`
  in the gate's `check_blocked_by` action remains the right defensive
  posture against shell escaping bugs.
- `scripts/tests/test_rn_implement.py:863-878` —
  `test_check_blocked_by_parses_frontmatter_not_show_json` docstring says
  "`ll-issues show --json` does NOT expose blocked_by (returns null)".
  Update docstring to: "Additive `--json` exposure of `blocked_by` via
  ENH-2535 does NOT change this gate's deliberate direct-parse posture
  (see `rn-implement.yaml:367-370` for rationale)."
- `docs/guides/LOOPS_REFERENCE.md:404` — `blocked_by` pre-gate description
  says "if `ll-issues show` cannot parse the frontmatter the gate passes".
  This is still operationally correct, but the preceding clause mentioning
  direct frontmatter parse as a workaround for the JSON gap becomes
  obsolete — refresh to mention ENH-2535 closed that gap.

**Subprocess consumers of `ll-issues show --json` (commands + skills)**
already enumerated in the existing "Skill consumers" block — no NEW
consumers found by Agent 1. All access `path` / `learning_tests_required`
only and are additive-safe.

**No agent (`agents/*.md`) references `ll-issues show` or `cmd_show`**
directly. Confirmed by exhaustive grep.

### Similar Patterns

- The existing detail_lines construction (`show.py:372-399`) is the
  template to mirror — conditional inclusion of `Key: value` strings
  into a flat list, then a single mid-border separator before the path
  line.
- `confidence_score` and `outcome_confidence` (extracted at `show.py:176-177`)
  use the same `str(x) if x is not None else None` idiom that the new
  boolean fields should follow.

### Tests

- `scripts/tests/test_show.py` — add new test cases (see Implementation
  Step 6). Existing cases must continue to pass.
- `scripts/tests/test_issues_cli.py` — if it exercises `cmd_show` end-to-end,
  verify no regression in the `--json` output shape.

_Wiring pass added by `/ll:wire-issue`:_

Additional test surface found by exhaustive search. None are load-bearing
for the ENH (all pass with the additive change as currently specified);
listed for tracking + regression hygiene:

- `scripts/tests/test_set_scores_cli.py:206-251` —
  `test_set_scores_verify_via_show_json` reads `confidence`/`outcome` via
  `ll-issues show --json` after `set-scores` mutation. Asserts only
  numeric string values via `data["confidence"] == "88"` —
  additive-safe, but add a parallel assertion that
  `data["decision_ref"]` is `None` for the synthetic test issue
  (regression guard against accidentally populating it).
- `scripts/tests/test_rn_implement.py:863-878` — already covered in the
  Dependent Files section (docstring refresh alongside the gate's direct-
  parse posture).
- `scripts/tests/test_ll_logs.py:943, 945, 1027, 1069, 1187, 1378` —
  fixture helpers that emit `ll-issues show` bash command records in
  session-log tests. These are structural-only (no behavior assertions
  on the rendered output) and need no change.
- **No fixture files** at `scripts/tests/fixtures/issues/` currently
  populate `parent`, `relates_to`, `depends_on`, `blocked_by`, `blocks`,
  `supersedes`, `decomposed_into`, `closing_note`, `closed_reason`,
  `cancelled_reason`, `deferred_reason`, `closed_by`, `closed_at`,
  `deferred_date`, `decision_ref`, `testable`, `affects`, `focus_area`
  in frontmatter. Reuse the `bug-with-product-impact.md` and
  `bug-with-frontmatter.md` fixtures for `discovered_commit` /
  `discovered_branch` / `discovered_date` discovery tests; use inline
  frontmatter in `_write_issue()` calls for the relationship / closure /
  decision-coupling tests (the helper at `test_show.py:149-158` accepts
  raw markdown content, so inline frontmatter is supported).
- `scripts/tests/test_json_output_contracts.py:284` — listed by Agent 1
  but is actually for `ll-issues list --json` (a different code path
  owned by `scripts/little_loops/cli/issues/list_cmd.py`, NOT
  `show.py`). Excluded from this ENH's integration map; out of scope.

### Documentation

- `docs/reference/COMMANDS.md` (or wherever `ll-issues show` is documented) —
  mention the new closure/relationships/discovery/decision-coupling fields
  in the output description.
- `docs/reference/API.md` — if `_parse_card_fields` / `_render_card` are
  part of the documented Python surface, add a note that the returned
  dict now includes the new keys.

_Wiring pass added by `/ll:wire-issue`:_

Additional doc touchpoints found by exhaustive grep that should be updated
to reflect the new fields (none are load-bearing; none are documentation
of *removed* behavior; all are references that document the current shape
of `--json` output):

- `docs/guides/LOOPS_REFERENCE.md:145` — `check_scores_from_file` description
  references the existing `confidence_score`/`outcome_confidence` reads
  via `ll-issues show --json`. No key changes needed (additive), but add
  a parenthetical noting `decision_needed → decision_ref` is now exposed
  for richer decision-routing context.
- `docs/guides/LOOPS_REFERENCE.md:404` — already covered in the Dependent
  Files section above (refresh alongside the test docstring + loop YAML
  comment trio).
- `commands/review-sprint.md:129` — Phase 3f EPIC Context step already
  reads the `parent:` field via `ll-issues show $ID --json` (with
  frontmatter read as a fallback). The `parent:` key will now appear in
  the JSON projection. No change required, but the parenthetical
  "(via `ll-issues show $ID --json` or direct frontmatter read)" implies
  the JSON path was previously unreliable — refresh to "via
  `ll-issues show $ID --json` (post-ENH-2535 exposes `parent` directly;
  direct frontmatter read remains the fallback)".
- `thoughts/shared/plans/2026-06-07-ENH-2008-management.md:29`,
  `thoughts/shared/plans/2026-06-30-ENH-2406-management.md:29` —
  historical rationale comments. These are immutable plan artifacts and
  do not need editing; they remain accurate as descriptions of the
  rationale **at the time the plan was written**. Flag only.
- Historical issue references (NOT requiring edits, listed for context
  since the issue's existing "Related" section mentions BUG-2530 and
  the gain over ENH-2008, ENH-1088, ENH-2443, etc.):
  `.issues/enhancements/P3-ENH-2008`, `P3-ENH-1088`, `P4-ENH-1284`,
  `P3-ENH-2443`, `P4-ENH-1492`, `.issues/features/P3-FEAT-1696`,
  `.issues/epics/P3-EPIC-1859`, `.issues/features/P2-FEAT-1389` —
  each mentioned a gap that ENH-2535 closes; no edits needed.

### Configuration

- N/A — no config schema changes. All five additions are derived from
  existing frontmatter, no new knobs.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Architectural observation (re-parse vs. IssueInfo reuse):**

- `scripts/little_loops/issue_parser.py:IssueInfo` (lines 398–550) already
  declares typed attributes for `parent`, `relates_to`, `depends_on`,
  `blocked_by`, `blocks`, `duplicate_of`, `testable`, `decision_needed`,
  `missing_artifacts`, `implementation_order_risk`,
  `learning_tests_required`, and `IssueParser.parse_file()` (lines 638–750)
  already extracts most relationship frontmatter. **However, `_parse_card_fields`
  re-parses frontmatter independently via `parse_frontmatter`** rather than
  consuming `IssueInfo`. This is pre-existing and out of scope to refactor —
  but worth noting that the new fields (`supersedes`, `decomposed_into`,
  `closing_note`, `closed_reason`, `cancelled_reason`, `deferred_reason`,
  `closed_by`, `closed_at`, `deferred_date`, `decision_ref`, `affects`,
  `focus_area`) are NOT in `IssueInfo` either; they need both the
  `show.py` extraction AND a future `IssueInfo` extension for symmetry.

**Title resolution pattern (for `Parent: EPIC-1234 (title)`):**

- Canonical pattern at `scripts/little_loops/cli/issues/list_cmd.py:188-190`:
  `parent_titles: dict[str, str] = {i.issue_id: i.title for i in _all_issues
  if i.title}` — built from `find_issues_all()` then `.get(key, "")` to
  fall back to ID-only. Same shape used at
  `scripts/little_loops/issue_progress.py:99-113` (`compute_epic_progress`).
- For `_render_card` (pure function on a `dict[str, str | None]`), the title
  lookup must be done in `_parse_card_fields` (which has access to `config`)
  by loading all issues and building the map there, OR by extending
  `IssueInfo` (preferred long-term). Document the chosen path in the
  Implementation Plan.

**List-or-comma-string frontmatter normalization:**

- Canonical coercion at `scripts/little_loops/issue_parser.py:702-750`
  handles both YAML lists and quoted comma-strings for `relates_to`,
  `blocked_by`, `blocks`, `depends_on`. Apply the same coercion in
  `_parse_card_fields` for the new relationship fields (otherwise issues
  with `parent: "EPIC-1234"` as a scalar won't render correctly).

**Edge-type taxonomy & color palette (optional):**

- `scripts/little_loops/cli/issues/clusters.py:18-56` defines the canonical
  edge types (`blocked_by`, `blocks`, `parent`, `depends_on`, `relates_to`),
  `EDGE_COLOR` palette, `_EDGE_PRIORITY` ordering (blocked_by=0 first),
  and `_TERMINAL_STATUSES`-like groupings (`_HARD_EDGE_TYPES` /
  `_BLOCKING_EDGE_TYPES`). Use this ordering when emitting the
  relationships block if width is constrained; the issue's "single line
  group (or two if it overflows)" hint aligns with the priority ordering
  shown there.

**Existing fixtures that already exercise discovery fields:**

- `scripts/tests/fixtures/issues/bug-with-product-impact.md` and
  `bug-no-product-impact.md` already populate `discovered_commit`,
  `discovered_branch`, `discovered_date` in frontmatter. These can
  serve as the basis for discovery-block rendering tests without
  requiring new fixture files.

**Documentation files with current field documentation:**

- `docs/reference/CLI.md:1082-1090` — documents `ll-issues show <issue_id>`
  field listing; needs new fields added.
- `docs/reference/API.md:3660-3677` — documents `--json` output field set;
  needs new additive keys noted.
- `docs/reference/OUTPUT_STYLING.md:95-148` — section "Issue Card:
  `scripts/little_loops/cli/issues/show.py`" includes box-drawing layout
  and "Detail line fields" table; needs new closure/relationships/discovery
  rows.
- `docs/reference/COMMANDS.md` does NOT currently have a dedicated
  `ll-issues show` entry (90+ `/ll:` sections but no show entry); the
  `docs/reference/CLI.md` entry is the canonical doc surface.

**Skill consumers of `ll-issues show --json` (additive impact only):**

- `skills/create-eval-from-issues/SKILL.md` (lines 27, 178, 182, 184)
- `skills/verify-issue-loop/SKILL.md` (lines 26, 60, 63, 65)
- `skills/adversarial-verify-loop/SKILL.md` (lines 26, 61, 64, 66)
- `skills/audit-loop-run/SKILL.md` (line 176)
- `skills/confidence-check/rubric.md` (line 113)
- `skills/create-loop/loop-types.md` (line 715)

All consume `--json` via key access; new additive keys will be picked up
automatically. **Verify no skill does `len(fields.keys()) == N` or other
fixed-shape assertions that would break** — `grep -r "ll-issues show.*--json"
skills/` confirms.

**Decisions log coupling:**

- `.ll/decisions.yaml:4352` already has an `ARCHITECTURE-NNN` rule referencing
  this issue ("Captured: ll-issues show: surface closure context,
  relationships, discovery, and decision coupling"). The `decision_ref`
  rendering must accept this `ARCHITECTURE-NNN` shape; the issue's example
  (`ARCHITECTURE-049`) aligns with the convention.

## Related

- BUG-2530 — example of an issue whose closure context (`## Decision
  Rationale` section with `## Related` cross-links) currently requires
  opening the file to see; this ENH would surface the same data on the
  card.
- `/ll:map-dependencies` — operates on the same `parent` / `relates_to` /
  `depends_on` frontmatter fields that this ENH surfaces on `show`. The
  two are complementary: `map-deps` is a graph view; `show` is a per-node
  view.
- `/ll:ready-issue` — gating uses `testable`; this ENH makes the readiness
  answer visible on the card.
- `scripts/little_loops/cli/issues/show.py:_parse_card_fields` — the
  function being extended (lines 127–302).

## Session Log
- `/ll:confidence-check` - 2026-07-07T23:35:00 - `e58ef6ee-abf1-4aa5-b423-937363e09287.jsonl`
- `/ll:wire-issue` - 2026-07-07T23:15:54 - `4e2bb9b6-485a-4f98-b051-74b58e421fd1.jsonl`
- `/ll:refine-issue` - 2026-07-07T23:05:09 - `1ec6186a-c209-4064-8422-49d25a74f2c5.jsonl`
- `/ll:capture-issue` - 2026-07-07T22:52:13Z

## Status

**Open** | Created: 2026-07-07 | Priority: P2