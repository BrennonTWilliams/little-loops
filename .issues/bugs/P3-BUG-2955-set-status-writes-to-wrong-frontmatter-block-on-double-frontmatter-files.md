---
id: BUG-2955
title: set-status writes to the wrong frontmatter block on double-frontmatter issue
  files
type: BUG
priority: P3
status: done
captured_at: '2026-08-01T01:11:34Z'
completed_at: '2026-08-01T02:25:56Z'
discovered_date: 2026-08-01
discovered_by: capture-issue
relates_to:
- BUG-2769
- ENH-2937
labels:
- issue-parser
- data-integrity
decision_needed: false
confidence_score: 95
outcome_confidence: 64
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 10
---

# BUG-2955: `ll-issues set-status` writes to the wrong frontmatter block on double-frontmatter issue files

## Summary

A small class of issue files carries **two** YAML frontmatter blocks: an outer
scores block at the very top (`confidence_score`, `outcome_confidence`,
`score_*` — written by the confidence-check scoring path), then the H1 title,
then the canonical block containing `id:`/`type:`/`priority:`/`status:`. On such
a file, `ll-issues set-status` writes `status:`/`completed_at` into the **outer**
block and never touches the canonical one, leaving two contradictory `status:`
values in the same file.

## Steps to Reproduce

1. Take an issue file whose first frontmatter block holds only `score_*` keys and
   whose canonical `id:`-bearing block sits after the H1 (see the file list under
   Impact for real examples).
2. Run `ll-issues set-status <ID> done`.
3. Observe the CLI print `<ID>: unknown → done` — "unknown", not "open", proving it
   never read the canonical block's existing `status:`.
4. `grep -n '^status:' <file>` now shows two lines with different values.

## Current Behavior

Observed on ENH-2937 during this session: `ll-issues set-status ENH-2937 done`
printed `ENH-2937: unknown → done` and inserted `status: done` +
`completed_at: '2026-08-01T01:08:02Z'` into the top scores block (line 8), while
the canonical block at line 17 still read `status: open`.

The divergence was live on **ENH-2936** until it was hand-corrected on
2026-07-31 (see the note under Impact). Recorded here verbatim as the canonical
evidence of the defect — this exact byte-level shape is the regression-test
fixture, since no file in the repo carries it any more:

```
.issues/enhancements/P2-ENH-2936-...md:8:status: done
.issues/enhancements/P2-ENH-2936-...md:17:status: open
```

`ll-issues show ENH-2936 --json` reports `Completed` — the read path takes the
outer block, so the contradiction is invisible to tooling while being plainly
wrong to any human or agent reading the canonical frontmatter.

## Expected Behavior

`set-status` updates the issue's canonical `status:` — the one in the block that
carries `id:` — regardless of how many frontmatter blocks precede it. A file
should never end up with two `status:` keys holding different values. Ideally
the read and write paths agree on a single definition of "the frontmatter block."

## Motivation

Status is the field every orchestration path branches on: dependency resolution
(`blocked_by`/`depends_on` edges resolve only on `done`/`cancelled`), work
selection, epic rollup, and history ingest. A file that says both `done` and
`open` is a silent correctness hazard — today it happens to read correctly
because the outer block wins, but any change to block-selection order (or any
consumer that parses the `id:`-bearing block directly, which is the intuitive
choice) flips the answer with no error. BUG-2769 is the same family: frontmatter
trusted without validating which block the value came from.

## Root Cause

Confirmed (see Codebase Research Findings below). Relevant anchors:

- `scripts/little_loops/frontmatter.py` — `parse_frontmatter()` (line 77),
  `_parse_frontmatter_lines()` (line 145), `update_frontmatter()` (line 290).
- The outer scores block is emitted by the confidence-check scoring path;
  `skills/confidence-check/rubric.md` defines the `score_*` keys it writes.

The `unknown → done` transition message is the key evidence: the writer parsed a
block that had no `status:` at all, i.e. it stopped at the first `---` fence
rather than locating the block that owns the issue's identity.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Confirmed — all three frontmatter helpers in `scripts/little_loops/frontmatter.py`
locate a block unconditionally by "first `---` fence," with no concept of "the
block containing `id:`":

- `parse_frontmatter()` (`frontmatter.py:77-142`) — line 108:
  `end_match = re.search(r"\n---\s*\n", content[3:])` finds the *nearest*
  closing fence after the opening one, i.e. the first block's end. Line 112
  slices only that span into `frontmatter_text`. No later block is ever
  inspected.
- `update_frontmatter()` (`frontmatter.py:290-313`) — line 305:
  `fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)` anchors at
  position 0 and stops at the nearest `\n---`. Lines 310-313 merge `updates`
  into that first block's parsed dict and splice it back in; everything after
  `fm_match.end()` (including the canonical `id:`/`status:` block) is passed
  through verbatim, untouched.
- `_parse_frontmatter_lines()` (`frontmatter.py:145-219`) only ever receives
  the substring already isolated by the first-block boundary above — it has no
  independent visibility into a second block either.

Traced end-to-end in `scripts/little_loops/cli/issues/set_status.py`
(`cmd_set_status()`, line 20): line 120 —
`old_status = parse_frontmatter(content).get("status", "unknown")` — is the
exact source of the `unknown → done` transcript: on these files the first
block has no `status:` key at all (only `score_*`), so `.get()` falls back to
the literal string `"unknown"`. `parse_frontmatter()` itself never returns
that string. Line 121 —
`new_content = update_frontmatter(content, _status_updates(args.status))` —
writes into the same first block via the merge-not-replace path above. The
cascade-to-children branch (lines 158-210, specifically line 198) repeats the
identical pattern per child, so a double-frontmatter child issue is exposed to
the same bug during a cascade.

`format-check`'s existing checks are also blind to this shape: `malformed_id`
(`issue_parser.py:365-372`) reads `raw_id = fm.get("id")` from the same
first-block parse — on these files `raw_id` is `None`, so the
`if raw_id and filename_id_match:` guard short-circuits and the missing `id:`
in the outer block never surfaces as a gap today.

## Proposed Solution

Two candidate angles were considered. **Option A was selected** — see Decision
Rationale below for the choice and its resolved sub-decision, and Program Design
for the concrete shape. The original framing is preserved for context:

1. **Normalize on read + write.** Teach the frontmatter helpers that the
   canonical block is the one containing `id:`, and either merge duplicate blocks
   or consistently target that one. Lower blast radius, leaves the two-block
   files intact.
2. **Stop creating the second block.** Have the confidence-check scoring path
   write `score_*` keys into the existing canonical block instead of prepending a
   new one, plus a one-time migration to fold existing outer blocks in. Removes
   the malformed shape entirely rather than accommodating it.

Whichever is chosen, add a `format-check` gap class for "more than one
frontmatter block" / "duplicate `status:` key" so the shape can't silently
reappear.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Restating the two angles above in the enumerable-option format the
`decision_needed` tooling (`ll-issues check-decidable`) scans for — the
underlying alternatives are unchanged, no recommendation is added (the issue
deliberately punts this as a scope call, see the paragraph above):

**Option A**: Normalize on read + write. Teach `parse_frontmatter()` and
`update_frontmatter()` (`scripts/little_loops/frontmatter.py`) that the
canonical block is the one containing `id:`, and either merge duplicate blocks
or consistently target that one. Lower blast radius, leaves the two-block
files intact.

> **Selected:** Option A — fixes the actual root cause (first-fence-only block
> selection in `frontmatter.py`, shared by every `parse_frontmatter()`/
> `update_frontmatter()` caller including `set_scores.py`) rather than just the
> one call site that currently exposes it.

**Option B**: Stop creating the second block. Have the confidence-check
scoring path (`scripts/little_loops/cli/issues/set_scores.py:cmd_set_scores()`
→ `update_frontmatter()`) write `score_*` keys into the existing canonical
block instead of prepending a new one, plus a one-time migration to fold
existing outer blocks in. Removes the malformed shape entirely rather than
accommodating it.

### Decision Rationale

**Selected: Option A — Normalize on read + write in `frontmatter.py`.**

Both options were evaluated with codebase-pattern-finder agents against the
current implementation. Option A addresses the actual root cause the issue's
own research identified: `parse_frontmatter()` (`frontmatter.py:108`) and
`update_frontmatter()` (`frontmatter.py:305`) both locate a frontmatter block
by "first `---` fence" unconditionally, with no concept of "the block
containing `id:`." This is the shared logic behind *both* `set_status.py`'s
bug and `set_scores.py`'s block-creation behavior — Option B only patches the
`set_scores.py` call site, leaving the shared parsing helpers (and their other
~30 call sites) exposed to the same failure mode if a double-block file is
ever produced by any other path. Option A also has a direct precedent to model
against (`canonicalize_issue_id()`, `session_store/writers.py:1968` — a single
normalization helper all callers route through, WARN-logging on repair) and
dedicated existing unit test coverage (`test_frontmatter.py`) that lets the
fix be verified in isolation without new CLI-level fixtures.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|:-----------:|:----------:|:------------:|:----:|:-----:|
| **A — Normalize read+write** | 2 | 2 | 3 | 2 | **9/12** |
| B — Stop creating second block | 2 | 3 | 2 | 1 | 8/12 |

Key evidence:
- Root cause is shared parsing logic, not the scoring write path alone
  (`frontmatter.py:108`, `frontmatter.py:305`; `set_status.py:120-121`
  independently hits the same first-block bug).
- Option B's own migration precedent (`cli/migrate_status.py`) is clean, but
  the issue's own risk note rates Option B "Medium (touches every scored
  issue file)" vs. Option A "Low."
- Option A's `_canonical_frontmatter_block()`-style fix has a strong,
  already-used precedent to imitate (`canonicalize_issue_id`).

#### Resolved sub-decision: merge, don't target-only

Option A as originally written left its central question open — *"either merge
duplicate blocks **or** consistently target that one."* These are not
interchangeable, and target-only is wrong:

The outer block is where `confidence_score` / `outcome_confidence` / `score_*`
live. **14 modules read those keys** — `cli/issues/check_readiness.py:50`
(`int(fm.get("confidence_score") or 0)`), `cli/issues/next_issue.py`,
`cli/sprint/show.py`, `cli/sprint/_helpers.py`, `cli/issues/refine_status.py`,
`cli/issues/next_action.py`, `cli/issues/search.py`, `analytics/variance.py`,
`config/features.py`, and others. If `parse_frontmatter()` were changed to
return *only* the `id:`-bearing block, every double-frontmatter file would
silently read `confidence_score = 0` — readiness gates would block and
`next-issue` ordering would shift. That trades this bug for a worse one.

**Therefore: the read path merges all header-region blocks in document order,
and the write path targets the canonical (`id:`-bearing) block only.**

#### Why the merge cannot use a static "canonical wins" rule

An earlier draft of this section said the canonical block should win every key
conflict. **That is wrong, and would corrupt data.** On the legacy files the
canonical block's `status:` is precisely the *stale* value — it is stale because
this bug meant `set-status` never updated it. Applying canonical-wins would
resurrect `open` on a shipped issue and break the `blocked_by`/`depends_on`
resolution this issue's own Motivation cites.

Worked example — `ENH-2936` is genuinely **done** (implementation landed in
commit `5e29c4d4`: `skills/decide-issue/SKILL.md`, `issue_parser.py`,
`autodev.yaml`, 4 test files). Its blocks:

- outer: `status: done`, `completed_at: '2026-07-31T23:53:39Z'` (single quotes —
  `yaml.dump` via `update_frontmatter`, i.e. the CLI)
- canonical: `status: open`, `completed_at: "2026-07-31T23:52:59Z"` (double
  quotes — a skill-driven `Edit`)

Note the canonical block is *internally* contradictory (`open` + a
`completed_at`). Note also that the skill path wrote to the canonical block
correctly; the CLI is the outlier. That asymmetry is why the **write**-side
half of the rule (target canonical) is right even though the **read**-side half
is not.

There is already a codified tiebreak for exactly this shape —
`issue_parser.py:1150-1152`:

- `status = frontmatter.get("status", "open")`
- `if status == "open" and frontmatter.get("completed_at"): status = "done"`

**Resolution: don't rely on a permanent precedence rule at all.** Fold the 8
legacy files into a single block as part of this fix (see Migration below), so
no double-block file survives for a precedence rule to arbitrate. The merge
becomes a transitional safety net rather than a load-bearing policy, and the
new `format-check` gap prevents the shape from reappearing.

#### Migration (required, part of this fix)

Fold each of the 8 files' outer block into its canonical block, then delete the
outer block. Per-key resolution:

- `score_*` / `confidence_score` / `outcome_confidence` — exist only in the
  outer block; move them in verbatim.
- `status` — all 8 files now agree between blocks, so the fold is value-preserving
  and no arbitration is needed in practice. Retain the rule anyway for any file
  that regresses before the fix lands: take the **non-`open`** value when the two
  disagree, and assert the result is consistent with `completed_at` (the
  `issue_parser.py:1150` rule).
- `completed_at` — keep the canonical block's value if present, else the outer's;
  they differ only by seconds.

This must run as a reviewed one-shot (8 files), not an unattended sweep — the
`status` resolution is a data-truth call, not a mechanical one.

## Program Design

### Types

- `FrontmatterBlock` — a frozen dataclass locating one parsed block in the source:
- `span: tuple[int, int]`
- `body_span: tuple[int, int]`
- `data: dict[str, Any]`
- `is_canonical: bool`

### Signatures

- `def _iter_frontmatter_blocks(content: str) -> list[FrontmatterBlock]`
- `def _canonical_frontmatter_block(blocks: list[FrontmatterBlock]) -> FrontmatterBlock | None`
- `def _merge_blocks(blocks: list[FrontmatterBlock]) -> dict[str, Any]`
- `def parse_frontmatter(content: str, coerce_types: bool = False) -> dict[str, Any]`
- `def update_frontmatter(content: str, updates: dict[str, Any]) -> str`
- `def has_multiple_frontmatter_blocks(content: str) -> bool`

**Block-scanning contract** (shared by the fix and the new `format-check` gap,
so the two can never disagree about what a "block" is):

`_iter_frontmatter_blocks()` scans **only the header region** — content up to
the first `^## ` heading — and **skips fenced code regions** (` ``` ` / `~~~`).
Both constraints are load-bearing: a naive `^---$` scan false-positives on
`---` inside ` ```yaml ` fences and on body horizontal rules (see Impact for
the measured false-positive rate). A candidate block counts only when its body
parses as a YAML mapping.

`_canonical_frontmatter_block()` returns the first block whose `data` contains
an `id:` key, else `None`.

`_merge_blocks()` applies blocks in document order, then runs the existing
`STATUS_SYNONYMS` canonicalization on the merged result. It deliberately does
**not** implement a canonical-block-wins precedence — see *Why the merge cannot
use a static "canonical wins" rule* above. Because the migration folds every
double-block file, this function only ever sees one block in practice; the
document-order fallback is a transitional safety net, and any surviving
`status`/`completed_at` contradiction is settled by the existing
`issue_parser.py:1150` coercion rather than here.

`parse_frontmatter()` returns `_merge_blocks(...)`; its existing
`coerce_types` / empty-value / `BaseLoader`-string contract is unchanged, and
for the single-block case (the overwhelming majority) the result is
byte-identical to today's.

`update_frontmatter()` splices `updates` into the canonical block's
`body_span`. When no block carries `id:` it falls back to the first block —
preserving today's behavior for the non-issue callers (agent, skill, and loop
YAML frontmatter, which have no `id:` key). When no block exists at all it
prepends one, as today.

### Call Path

- `cmd_set_status` → `parse_frontmatter` → `_iter_frontmatter_blocks` → `_merge_blocks`
- `cmd_set_status` → `update_frontmatter` → `_canonical_frontmatter_block`
- `cmd_set_scores` → `update_frontmatter` → `_canonical_frontmatter_block`
- `check_format_gaps` → `has_multiple_frontmatter_blocks` → `_iter_frontmatter_blocks`
- `_parse_frontmatter_lines` stays the per-block permissive fallback, now invoked
  once per block rather than once per file.

### Deviations

If any of the 61 `parse_frontmatter(` call sites turns out to *depend* on
first-fence-only behavior, prefer adding an explicit opt-out parameter at that
call site over weakening the merge default.

## Integration Map

### Files to Modify
- `scripts/little_loops/frontmatter.py` — block selection in `parse_frontmatter()`
  (line 108 fence-boundary search), `update_frontmatter()` (line 305 fence-boundary
  match)
- `scripts/little_loops/cli/issues/set_status.py` — `cmd_set_status()` (line 20);
  reads `old_status` at line 120, writes via `update_frontmatter()` at line 121; the
  cascade-to-children branch (line 198) has the identical exposure
- `scripts/little_loops/issue_parser.py` — `FormatGaps` dataclass (line 164) needs a
  new gap category (e.g. `multi_frontmatter`); `check_format_gaps()` (line 235) needs
  detection logic. It must **call `has_multiple_frontmatter_blocks()` from
  `frontmatter.py`** (see Program Design) rather than growing its own raw-`content`
  regex scan in the style of `deprecated_key` (lines 304-311). A naive `^---$` scan
  is measurably wrong here: it flags every issue containing a ` ```yaml ` fence or a
  body horizontal rule — 912 files by that heuristic vs. 8 real ones (see Impact).
  Sharing one scanner also guarantees the gap check and the parse/write fix can never
  disagree about what a block is. The parsed-dict shortcuts remain unusable because
  `parse_frontmatter()` collapses the exact information this check needs to see
- `scripts/little_loops/cli/issues/format_check.py` — `_print_gaps()` (line 83) and
  the JSON output path need the new gap category wired through
- Possibly `scripts/little_loops/cli/issues/set_scores.py` — `cmd_set_scores()`
  (line 13), under Option B

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_lifecycle.py`, `scripts/little_loops/cli/issues/deferred_triage.py`,
  `scripts/little_loops/cli/issues/show.py`, `scripts/little_loops/cli/issues/link.py`,
  `scripts/little_loops/sync.py`, `scripts/little_loops/issue_history/parsing.py`,
  `scripts/little_loops/session_store/writers.py` — all call `parse_frontmatter()`
  and would be affected by a block-selection fix (Option A) the same way `set-status`
  is; not confirmed exposed to the same-symptom bug, but worth a targeted check when
  implementing
- **Measured surface: 61 `parse_frontmatter(` call sites in `scripts/little_loops/`**
  (`grep -rn "parse_frontmatter(" scripts/little_loops --include="*.py" | wc -l`) —
  not the "~7" the named list above implies. The merge-not-replace design in Program
  Design is what keeps this surface tractable: single-block files (the overwhelming
  majority) parse byte-identically to today, so the audit burden is limited to the 8
  double-block files rather than all 61 call sites.
- **Score-key readers that would regress under a target-only fix** — the reason the
  merge design was chosen (see Resolved sub-decision):
  `cli/issues/check_readiness.py:50`, `cli/issues/next_issue.py`,
  `cli/issues/next_issues.py`, `cli/issues/next_action.py`, `cli/issues/search.py`,
  `cli/issues/refine_status.py`, `cli/issues/show.py`, `cli/issues/__init__.py`,
  `cli/issues/set_scores.py`, `cli/sprint/show.py`, `cli/sprint/_helpers.py`,
  `analytics/variance.py`, `config/features.py`, `issue_parser.py`

### Similar Patterns
- `BUG-2769` (done) — issue-id ingest trusting a malformed frontmatter `id:`;
  same "trust the frontmatter without validating it" family. Its fix landed as
  `canonicalize_issue_id()` (`scripts/little_loops/session_store/writers.py:1968`)
  — a single normalization helper routed through by every ingest call site,
  WARN-logging when it silently repairs a value. Closest shape to model a new
  `_canonical_frontmatter_block()`-style helper after if Option A is chosen.

### Tests
- No existing coverage for multi-block frontmatter. `scripts/tests/test_frontmatter.py`
  (`TestParseFrontmatter`, `TestUpdateFrontmatter`) and
  `scripts/tests/test_set_status_cli.py` (`TestSetStatusRecordsIssueEvent`, line 1150 —
  `test_set_status_canonicalizes_malformed_frontmatter_id` around line 1200 is the
  closest existing template) have no double-frontmatter fixture today.
- `scripts/tests/test_ll_issues_format_check.py` — `TestFormatCheckMalformedId`
  (line 217) is the template for a new gap-category test class; `_CLEAN_BUG_BODY`
  (line 17) + `_write_issue()` (line 63) are the fixture-construction helpers to
  reuse for a double-frontmatter fixture, e.g.:
  `"---\nscore_complexity: 20\nstatus: done\n---\n# Title\n\n---\nid: BUG-XXXX\ntype: BUG\npriority: PX\nstatus: open\n---\n"`
- Live *shape* fixtures (double-block, values agree) — any of the 8 files in the
  Impact table, e.g.
  `.issues/enhancements/P2-ENH-2936-decide-issue-un-preferenced-decision-directive-shape.md`.
  The divergent-*value* case no longer exists on disk (ENH-2936 was corrected
  2026-07-31) and must be built as a synthetic fixture from the bytes recorded
  under Current Behavior.
- **Required negative fixtures** (these are what the corrected scope measurement
  proves are necessary — without them the detector regresses to a 912-file
  false-positive rate):
  - an issue whose body contains a ` ```yaml ` fenced block containing `---`
  - an issue whose body contains a `---` horizontal rule after the frontmatter
  - a single-block file with `id:` in the *first* block (the normal shape) —
    asserting `parse_frontmatter()` output is unchanged byte-for-byte
- **Required merge / write-target assertions** (Program Design's core contract):
  - merged read exposes outer-block `score_*` keys *and* canonical-block `id:`
    — neither block's keys are dropped
  - `update_frontmatter()` writes into the canonical block and leaves the outer
    block's `score_*` keys untouched
  - a no-`id:` file (agent/skill/loop YAML shape) still round-trips through the
    first-block fallback unchanged
  - **no assertion that "canonical wins" on a `status` conflict** — that rule was
    rejected as data-corrupting (see Decision Rationale). A test encoding it
    would lock in the bug.
- **Required migration assertions**:
  - folding a synthetic divergent fixture (`done` outer / `open` canonical, plus a
    `completed_at`) yields `status: done` — **not `open`**
  - folding each of the 8 real files is value-preserving (all now agree)
  - post-migration, `has_multiple_frontmatter_blocks()` is False for all 8 files
    and `format-check` reports no `multi_frontmatter` gap repo-wide

## Impact

- **Priority**: P3 — rare shape, and the read path currently masks it, but it is
  a silent data-integrity defect on the single most load-bearing field.
- **Scope measured (corrected)**: **8** files under `.issues/` carry the
  double-frontmatter shape — an outer block with no `id:`, followed by a later block
  whose first key is `id:`:

  | File | `status:` lines |
  |------|-----------------|
  | `P2-FEAT-1216-parallel-mutual-exclusion-validation-tests.md` | `done` |
  | `P2-FEAT-1217-parallel-loop-yaml-fixture-and-load-test.md` | `done` |
  | `P2-FEAT-1218-test-parallel-state-config-class.md` | `done` |
  | `P2-FEAT-1220-update-testing-md-fixture-count.md` | `done` |
  | `P2-FEAT-1221-parallel-state-no-transition-guard-test.md` | `done` |
  | `P2-FEAT-1222-parallel-fuzz-strategy-extension.md` | `done` |
  | `P2-ENH-2936-decide-issue-un-preferenced-decision-directive-shape.md` | `done` / `done` (was `done` / `open`) |
  | `P3-ENH-2937-reconcile-issue-rewrite-contradicted-scope-boundaries-claims.md` | `done` / `done` |

  **No file carries a live `status:` divergence any more** — ENH-2936, the only
  one, was hand-corrected on 2026-07-31. All 8 still carry the malformed
  double-block *shape*, which is what the fix and the fold migration address; the
  divergent-value case must now be reproduced from a synthetic fixture (the
  verbatim bytes are recorded under Current Behavior).

  **The earlier "9 files" list was wrong and is retained here only as a warning.**
  It named `P1-BUG-035`, `P3-BUG-1508`, `P4-BUG-197`, `P3-ENH-397`, `P3-ENH-522`,
  `P4-ENH-398`, `P5-ENH-401` — all **single-block files** whose second `---` is a
  ` ```yaml ` code fence or a body horizontal rule — and it missed all six
  `FEAT-12xx` files entirely. The naive `^---$` heuristic that produced it matches
  **912** of the ~2860 issue files. This is exactly why the `format-check` detector
  must share `has_multiple_frontmatter_blocks()` (Program Design) instead of
  rolling its own scan.
- **Effort**: Small-Medium — Option A (selected): one new block scanner in
  `frontmatter.py`, two rewritten public functions, one new `format-check` gap
  category, a reviewed 8-file fold migration, plus fixtures.
- **Risk**: Low. Changes no behavior for single-block files (the ~2850-file
  majority), and the fold migration is bounded at 8 files with exactly one
  genuine data-truth call (`ENH-2936` → `done`). This is *not* Option B's
  Medium-risk sweep, which would have rewritten every scored issue file.
- **Sequencing**: land the `frontmatter.py` fix and the regression tests first,
  then run the fold migration — migrating first would destroy the repro fixture.

**Note**: ENH-2937's divergence was hand-corrected during the session that found
this. **ENH-2936 was also hand-corrected on 2026-07-31** — its canonical block
now reads `status: done`, matching its outer block.

**ENH-2936's true status is `done`, not `open`** — verified, not inferred. The
implementation landed in commit `5e29c4d4` (`skills/decide-issue/SKILL.md`,
`issue_parser.py`, `autodev.yaml`, and 4 test files), and its canonical block
already carried a `completed_at` alongside the stale `open`. It must **not** be
reopened. Any fix or migration that resolves it to `open` is wrong and has
mis-resolved the conflict.

The correction was applied by editing the canonical block directly, **not** via
`ll-issues set-status` — that command is the defect under test here, and would
have rewritten the outer block (already `done`) while leaving the canonical
block stale. That it cannot be used to fix its own damage is itself part of the
case for this issue.

**Consequence for testing**: the divergent-value case no longer exists anywhere
in the repo and must be reproduced synthetically. The verbatim bytes are
recorded under Current Behavior; the double-block *shape* remains live on all 8
files listed above.

## Confidence Check Notes

_Added by `/ll:confidence-check`:_

**Readiness 95/100, Outcome Confidence 64/100 (MODERATE) — but Program Design
gate override forces STOP — ADDRESS GAPS.**

### Gaps to Address

**~~`## Program Design` section is absent~~ — RESOLVED 2026-07-31.** The section
is now present with concrete types/signatures/call path for Option A.
`ll-issues format-check BUG-2955 --format json` returns all-empty (`"missing":
[]`, `"program_design_nonspecific": []`), so the gate clears.

Two further gaps were found and fixed in the same pass:

- **Option A's merge-vs-target-only ambiguity — RESOLVED.** The original wording
  ("either merge duplicate blocks or consistently target that one") left the
  central design question open, and target-only would have regressed 14
  score-key readers to `confidence_score = 0`. Settled as: **read merges, write
  targets canonical, and a one-shot migration folds the 8 legacy files** so no
  permanent precedence rule is needed. An intermediate draft proposed
  "canonical wins on conflict" — that was rejected on evidence as
  data-corrupting (it would reopen the shipped `ENH-2936`). See *Resolved
  sub-decision* under Decision Rationale.
- **Impact scope list was wrong — CORRECTED.** The prior "9 files" list was
  produced by a naive `^---$` heuristic that matches 912 files; it named seven
  single-block files and missed all six real `FEAT-12xx` cases. Corrected to the
  measured 8, with the false-positive trap now called out as a binding
  constraint on the `format-check` detector.

### Outcome Risk Factors
- Change surface (10/25): **measured at 61 `parse_frontmatter(` call sites**, not
  the ~7 originally named. Mitigated by design rather than by audit — the
  merge-not-replace contract makes single-block parsing byte-identical to today,
  confining behavioral change to the 8 double-block files. The 7 named callers
  (`issue_lifecycle.py`, `deferred_triage.py`, `show.py`, `link.py`, `sync.py`,
  `issue_history/parsing.py`, `session_store/writers.py`) still warrant a
  targeted check that none depends on first-fence-only behavior.
- Test coverage (18/25): no existing double-frontmatter fixture in
  `test_frontmatter.py` or `test_set_status_cli.py` — new fixtures are
  required, not just new assertions on existing ones. The specific negative
  fixtures and merge-precedence assertions are now enumerated under
  Integration Map → Tests.

## Resolution

Implemented Option A as designed:

- `scripts/little_loops/frontmatter.py` gained `FrontmatterBlock`,
  `_iter_frontmatter_blocks()`, `_canonical_frontmatter_block()`,
  `_merge_blocks()`, and `has_multiple_frontmatter_blocks()`.
  `parse_frontmatter()` now merges all header-region blocks in document
  order; `update_frontmatter()` splices into the canonical (`id:`-bearing)
  block, falling back to the first block when none carries `id:`
  (non-issue frontmatter — agent/skill/loop YAML). Single-block files parse
  byte-identically to before.
- `issue_parser.py` gained a `multi_frontmatter` `FormatGaps` category
  (via `has_multiple_frontmatter_blocks()`), wired through
  `format_check.py`'s text/JSON output and help text.
- Migrated the 8 files identified in Impact (`FEAT-1216`, `FEAT-1217`,
  `FEAT-1218`, `FEAT-1220`, `FEAT-1221`, `FEAT-1222`, `ENH-2936`, `ENH-2937`)
  by folding each outer block into its canonical block and deleting the
  outer block, preserving all inter-block body content (title/notes).
  `ENH-2936`'s canonical `status: open` was corrected to `done` per the
  issue's own verified finding (implementation landed in commit
  `5e29c4d4`); `ENH-2937`'s canonical status was already `done`.
- Added regression coverage: `TestMultiFrontmatterBlocks`
  (`test_frontmatter.py`) covers merge, canonical-only writes, the no-`id:`
  fallback, byte-identical single-block parsing, and the fenced-code/
  horizontal-rule false-positive guards; `TestFormatCheckMultiFrontmatter`
  (`test_ll_issues_format_check.py`) covers the new gap category end to end.

`python -m pytest scripts/tests/` passes (17428 passed, 1 pre-existing
unrelated failure — `test_no_prose_dependency_drift_in_repo` on
`ENH-2923`/`ENH-2925`, predates this change).

## Status

**Open** | Created: 2026-08-01 | Priority: P3

## Session Log
- `/ll:manage-issue` - 2026-08-01T02:25:38 - `847ba1b6-a9a3-4c07-b3be-3f3ad4d7d56b.jsonl`
- `/ll:ready-issue` - 2026-08-01T02:04:22 - `b1084b85-efda-47f8-9cf6-6100bbc37ed1.jsonl`
- `/ll:confidence-check` - 2026-08-01T01:30:31Z - `5e6bb49e-330c-449c-8327-ffed663d51ae.jsonl`
- `/ll:decide-issue` - 2026-08-01T01:28:38 - `a787d27f-d441-42c8-ad0a-bbb1c5440b7d.jsonl`
- `/ll:refine-issue` - 2026-08-01T01:25:28 - `09532938-31d1-4024-8919-daa21100acff.jsonl`
- `/ll:capture-issue` - 2026-08-01T01:11:34Z - `eae1dd1c-2379-4edd-a323-b6c99ede585d.jsonl`
