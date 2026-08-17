---
id: ENH-3247
type: ENH
title: Extend format-check --fix to repair structural debris in issue files
priority: P2
status: done
completed_at: '2026-08-17T23:00:00Z'
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-17'
captured_at: '2026-08-17T19:30:05Z'
relates_to:
- ENH-3244
- BUG-3245
- ENH-3246
- ENH-3248
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# ENH-3247: Extend format-check --fix to repair structural debris in issue files

## Summary

`ll-issues format-check --fix` already exists with a dry-run/`--apply` convention, but is hardcoded
to one gap class (`prose_dep_drift`). Add a dispatch layer and a second repair: deterministic
normalization of duplicate section headings and empty `_Added by_` provenance stubs. No LLM
involved — the correct output is fully determined by the input.

## Current Behavior

`format-check` already describes itself as a "Deterministic structural linter"
(`scripts/little_loops/cli/issues/format_check.py:60-68`) and enumerates 20 gap classes. It already
has a write mode with the right safety shape (`:95-105`):

```
--fix     Preview backfilling blocked_by from prose_dep_drift gaps via
          `ll-issues link` (dry-run by default; combine with --apply to write)
--apply   With --fix, write the proposed edges instead of previewing them
```

But `--fix` has **no dispatch layer**. Both call sites hardcode the single repair:

- `format_check.py:299` — sweep path (`--all`): `_fix_prose_deps(config, info.issue_id, gaps.prose_dep_drift, apply=apply_fix)`
- `format_check.py:343` — single-issue path: `_fix_prose_deps(config, source_id, gaps.prose_dep_drift, apply=apply_fix)`

So a second repairable gap class cannot be added without first generalizing those two sites.

Separately, the two structural defects this issue targets are not currently *detected* either:

- **Duplicate section headings** — ENH-3238 carried two `### Call Path` headings and two
  `### Dependent Files (Callers/Importers)` headings after one retry pass.
- **Empty provenance stubs** — three consecutive identical
  `_Added by \`/ll:refine-issue\` — <date> — based on codebase analysis:_` lines with no bullets
  between them.

The nearest existing gap class, `boilerplate`, cannot catch these: it fires only when a **required
section's body equals its `creation_template` in full**
(`scripts/little_loops/issue_parser.py:853-856`). Any partial fill defeats the whole-body equality
test — which is exactly why ENH-3238's `## Integration Map` passed while still holding five `TBD`
bullets.

## Expected Behavior

`ll-issues format-check <ID> --fix` previews, and `--fix --apply` writes, deterministic repairs for
structural debris:

- Duplicate `###` headings within the same parent `##` section are collapsed into one, with the
  bodies concatenated in document order.
- An `_Added by …:_` provenance stub with no bullet before the next heading is deleted. Deletion
  **normalizes surrounding whitespace to exactly one blank line** — two adjacent stubs collapsing
  must not leave a three-blank-line gap. Without this, the idempotency criterion below is satisfiable
  while the repair still emits a new debris shape.
- Content inside fenced code blocks is neither detected nor modified (see Proposed Solution step 0).

Both are pure functions of the input file. Running the repair twice is a no-op.

## Motivation

This class of debris is not a content judgment — for any given input there is exactly one correct
output. Sending it to an LLM pass costs tokens and introduces the risk of collateral rewrites for
zero decision value. It belongs in the deterministic linter that already owns structural gaps.

Doing it inside `format-check` rather than as a new command avoids three costs:

- **No reimplementation.** The write path, dry-run default, and `--apply` gate exist and are tested.
- **No detection/repair drift.** A separate `normalize-structure` command would have to re-derive
  the same gap classes to know what to fix, and the two definitions would diverge.
- **No new gate plumbing.** `format-check` is already consumed by non-LLM shell gates via its JSON
  payload (`superseded_marker_count` → `autodev.yaml:1590-1596`), so the loop step is one existing-
  shape command.

The remaining argument for a separate command was "don't turn a checker into a writer." That already
happened; a new command would make the existing `--fix` read as an inconsistency.

## Proposed Solution

0. **Fence-masking is a precondition, not a caveat.** Both detectors *and* both repairs must operate
   on fence-masked offsets via `fence_spans()`/`in_fence()`
   (`scripts/little_loops/text_utils`; precedent BUG-3202, applied at
   `scripts/little_loops/issue_parser.py:21`, `:439-463`). This is load-bearing because `--fix
   --apply` is a **writer**: the two helpers this issue builds on are both fence-blind, so without
   masking the repairs would delete and relocate content *inside illustrative code fences* —
   corrupting exactly the population these two issues target, namely issues that document markdown
   structure.

   Confirmed empirically against BUG-3245's own file. Its ```` ```markdown ```` example block
   (`BUG-3245:48-60`) contains a `## Program Design` line and three consecutive empty `_Added by`
   stubs, and `_iter_h2_sections()` reports `Program Design` **twice** for that file — so both new
   detectors false-positive on this very issue pair, and the repair would rewrite the example.

   Also decide and record: `_duplicate_findings_blocks()` (`issue_parser.py:1049-1068`) has the same
   latent blindness today. Either fix it in the same pass or explicitly defer it — do not leave it
   unstated.

1. **Add a dispatch layer for `--fix`.** Replace the two hardcoded `_fix_prose_deps` calls
   (`:299`, `:343`) with a table mapping gap class → repair function, so repairs compose and future
   classes are additive. Preserve the existing `prose_dep_drift` behavior exactly.
2. **Detect the two structural classes.** New gap classes in `issue_parser.py` alongside the
   existing 20:
   - `duplicate_heading` — the same `###` heading text appearing more than once under one `##`
     parent.
   - `empty_provenance_stub` — an `_Added by …:_` line with no list item between it and the next
     heading or stub.
3. **Repair them.** Collapse duplicate headings (concatenate bodies in document order, keep the
   first position); delete empty stubs. Both under the existing dry-run/`--apply` convention.
4. **Assert idempotency**: applying the repair to its own output changes nothing.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/format_check.py` — the `--fix` dispatch layer (`:299`, `:343`)
  and the new repair functions next to `_fix_prose_deps` (`:110`).
- `scripts/little_loops/issue_parser.py` — the two new gap classes, added to `FormatGaps`
  (`:494`), its truthiness aggregate (`:520`), its dict serialization (`:546`), and the gap-class
  docstring table (`:623-650`).
- `scripts/little_loops/cli/issues/format_check.py` — `_print_gaps` (`:132`) for text output.
- `scripts/little_loops/text_utils` — **read-only consumer**, no change expected:
  `fence_spans()`/`in_fence()` supply the fence masking both detectors and both repairs require
  (Proposed Solution step 0). Already imported by `issue_parser.py:21`; listed here so the dependency
  is not rediscovered mid-implementation.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/format_check.py` — `add_format_check_parser()` (`:55-68`) hardcodes
  the gap-class list into `--help` text, and `cmd_format_check`'s own docstring (`:194-199`) repeats
  the same enumerated list — two additional go-stale sites beyond `check_format_gaps`'s docstring
  table and CLI.md, both in the file already listed above. [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/autodev.yaml:1590-1596` — reads `format-check --format json`; new keys
  are additive and must not change existing ones.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — ENH-3248's proposed normalize step is the
  main consumer of the repair.
- Every caller of `ll-issues format-check` — the exit-code contract (`1` when `gaps.has_gaps`,
  `format_check.py:379`) now also fires on the two new classes, so a previously-clean issue with
  duplicate headings starts reporting. Intended, but it is a behavior change for existing callers.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/rn-remediate.yaml` — `ensure_formatted` state (`:100-121`) is a **real
  exit-code consumer**, confirmed distinct from `autodev.yaml`'s JSON-key read: `action_type: shell`
  runs `ll-issues format-check "$ID"` with `evaluate: {type: exit_code}`, `on_no: format_issue`. An
  issue that previously exited 0 here but now trips `duplicate_heading`/`empty_provenance_stub` routes
  through an extra `/ll:format-issue --auto` pass where none ran before — consistent with the state's
  documented fail-open intent, but confirm it's the intended new trigger, not just an accepted side
  effect. [Agent 2 finding]
- `scripts/little_loops/cli/issues/check_design.py:38` — calls `check_format_gaps()` directly (not via
  `cmd_format_check`); the two new gap classes flow through this call site automatically since
  `FormatGaps` is keyword-constructed everywhere (confirmed: no positional-construction call site
  exists repo-wide), but note it as a second consumer of the widened dataclass. [Agent 1 + Agent 2
  finding]
- `scripts/little_loops/issues/program_design.py` — imports and uses `check_format_gaps()`; same
  additive-safe note as above. [Agent 1 finding]

### Similar Patterns
- `_fix_prose_deps` (`format_check.py:110-130`) — the existing repair's shape: a dedicated helper
  taking `apply: bool`, delegating to an idempotent write path rather than editing frontmatter
  directly. Match it.
- `duplicate_findings_block` — an already-enumerated gap class in the same family, useful precedent
  for how duplicate-content classes are named and reported.

### Tests
- `scripts/tests/` — per gap class: detection on a crafted fixture, `--fix` previewing without
  writing, `--fix --apply` writing, and idempotency (apply twice → byte-identical).
- **Fixture sourcing — ENH-3238's pre-cleanup revision does not exist and cannot be used.**
  Verified: `aadbe100`, `a65245fe`, and `HEAD` all show that file with **0** `_Added by` stubs and a
  single `### Call Path`. The debris lived only in the working tree and was cleaned before commit;
  no committed revision carries it. Use these three fixtures instead:
  1. **Real-world duplicate headings** — BUG-3245's own file, which carries two
     `### Dependent Files (Callers/Importers)` under `## Integration Map` and passes `format-check`
     today. Copy the relevant slice into the fixture rather than reading the live file, so the test
     does not break when BUG-3245 is eventually cleaned.
  2. **Synthetic empty stubs** — adjacent `_Added by …:_` lines with no bullets between them,
     covering the blank-line normalization rule in Expected Behavior.
  3. **Fence safety (required)** — a fixture whose ```` ```markdown ```` block contains a duplicate
     `##`/`###` heading and adjacent empty stubs. Assert detection reports **nothing** and that
     `--fix --apply` leaves the file **byte-identical**. This is the regression test for Proposed
     Solution step 0; without it the repair silently corrupts documentation.
- Existing `--fix` tests must still pass unchanged, proving the dispatch refactor is behavior-preserving.
- `duplicate_findings_block` routed through the new dispatch table (see Decision Rules) needs its own
  preview / apply / idempotency cases, and a case asserting a duplicated
  `### Codebase Research Findings` is reported **once**, under the old class name only.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_issues_format_check.py::TestFormatCheckFix` — new tests follow the existing
  4-case template exactly: `test_fix_without_apply_previews_and_does_not_write` (`:1507-1524`),
  `test_fix_apply_writes_blocked_by_and_clears_drift` (`:1526-1551`), `test_fix_apply_is_idempotent`
  (`:1553-1590`), `test_fix_all_mode_applies_across_sweep` (`:1592-1616`) — all via `_invoke([...])`
  + `capsys.readouterr()`, never internals directly. [Agent 3 finding]
- `scripts/tests/test_issue_parser.py` — new detection-only test classes for `duplicate_heading` and
  `empty_provenance_stub`, modeled on `TestStackedFindingsBlocks` (`:4658-4708`), which builds its
  fixture as an inline class-level string constant rather than a file on disk. Note: neither
  `_iter_h2_sections()` nor `_paragraph_spans()` (the two helpers the new detectors are meant to
  build on) has any existing direct test pinning its `(heading, start, end)` return-shape contract —
  the new tests establish that contract for the first time. [Agent 3 finding]
- `scripts/tests/test_ll_issues_format_check.py::TestFormatCheckTestableRendering.test_every_format_gaps_field_is_rendered`
  (`:1920-1942`) — no edit needed; it iterates `dataclasses.fields(FormatGaps)` dynamically and will
  automatically enforce that both new fields get a `_print_gaps` loop, failing loudly if one is
  missing. [Agent 3 finding]
- **Exit-code widening sweep**: grep the suite for any existing fixture that currently asserts
  `format-check` returns `0` on an issue body containing duplicate `###` headings or an empty
  `_Added by …:_` stub — such fixtures would flip to exit 1 once the two new gap classes land, and
  weren't targeted by this wiring pass's search. [Agent 3 finding]
- `scripts/tests/test_ll_issues_check_design.py`, `scripts/tests/test_program_design_gate.py` —
  existing coverage of `check_format_gaps()` consumers (`check_design.py`, `program_design.py`); no
  changes required (additive-safe, confirmed keyword-only `FormatGaps` construction), but worth a
  pass-through run to confirm. [Agent 1 finding]

### Documentation
- `docs/reference/CLI.md` — `ll-issues format-check` gap classes and `--fix` scope.

_Wiring pass added by `/ll:wire-issue`:_
- No update needed in `commands/refine-issue.md`, `commands/ready-issue.md`,
  `skills/confidence-check/SKILL.md`, or `skills/wire-issue/prose-dependency-gate.md` — each reads
  only specific `FormatGaps` keys by name (`prose_dep_drift`, `program_design_nonspecific`, etc.),
  never enumerates the full gap-class list, so the two new classes are additive-safe there.
  [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

- Test precedent for the 4-case matrix this issue's Tests section calls for (detect / preview-no-write / apply-writes / idempotent-reapply), already exercised for the existing `prose_dep_drift` repair: `TestFormatCheckFix` (`scripts/tests/test_ll_issues_format_check.py:1487-1616`) — `test_fix_without_apply_previews_and_does_not_write` (asserts byte-identical file, "would link (dry-run)" in output), `test_fix_apply_writes_blocked_by_and_clears_drift`, `test_fix_apply_is_idempotent` (runs `--fix --apply` twice, asserts byte-identical on the second apply), `test_fix_all_mode_applies_across_sweep` (`--all --fix --apply` variant). A related invariant test worth mirroring: `test_ref_index_built_once_with_fix_apply_recheck` (`:716-749`), pinned to the index being built exactly once even across the fix/apply re-check.
- Test precedent for detection-only gap classes at the `issue_parser` layer: `TestStackedFindingsBlocks` (`scripts/tests/test_issue_parser.py:4658-4708`) — builds a raw markdown fixture inline at class scope (not a file on disk) and asserts against exact/sorted list output; a template for the `duplicate_heading`/`empty_provenance_stub` detection tests.
- `_fix_prose_deps` (`format_check.py:110-131`) delegates to `cmd_link` — an existing idempotent, cycle-safe write path (FEAT-2851) — rather than editing frontmatter directly; this is the "use a dedicated sub-command when one exists" branch. The alternative branch, for repairs with no dedicated sub-command (this issue's two new repairs, and the existing `cmd_fold_findings`), writes via `atomic_write()` (`scripts/little_loops/file_utils.py:16-31`, tempfile + `os.replace`) directly on transformed file content.

## Program Design

### Call Path

`cmd_format_check` -> `_fix_prose_deps` -> `superseded_marker_count`

- `cmd_format_check` (`scripts/little_loops/cli/issues/format_check.py:191`) is the entry point;
  returns `1 if gaps.has_gaps else 0` (`:379`).
- `_fix_prose_deps` (`:110`) is the only current repair, invoked from `:299` and `:343` — the two
  sites the dispatch layer replaces.
- `superseded_marker_count` (`scripts/little_loops/issue_parser.py:1173`) is the precedent for a
  deterministic public count consumed by a non-LLM gate.

### Decision Rules

- **Determinism requirement**: a repair qualifies only if the correct output is fully determined by
  the input. Duplicate-heading collapse and empty-stub deletion both qualify. Anything requiring a
  content judgment does not belong here — it goes to `/ll:reconcile-issue` (ENH-3246).
- **Duplicate-heading merge order**: keep the first occurrence's position, concatenate subsequent
  bodies in document order. Never drop a body — this is a *move*, not a deletion.
- **Empty-stub deletion is a true deletion**, justified because the stub carries no information: it
  is a provenance marker for content that does not exist.
- **Fenced regions are invisible to detection and untouchable by repair.** Both new detectors and
  both repairs mask fences via `fence_spans()`/`in_fence()` before computing any offset. A duplicate
  heading or empty stub that exists only inside a code fence is *not* a gap — it is documentation.
  See Proposed Solution step 0 for the empirical confirmation and the `_duplicate_findings_blocks()`
  decision this forces.
- **`empty_provenance_stub` is owned here, not by ENH-3244.** ENH-3244's pattern list previously
  included the same shape ("an `_Added by …:_` stub with no bullet before the next heading"), which
  would have put two detectors for one defect into the same dataclass in the same file. Ownership is
  now strict: this issue owns stub emptiness (a **line-adjacency** check, built on `_paragraph_spans`
  — `issue_parser.py:1100-1117`); ENH-3244 owns literal template strings (a **containment** check
  against `scripts/little_loops/templates/`). ENH-3244 is `blocked_by` this issue and adds its class
  alongside these two rather than racing them.
- **`Codebase Research Findings` carve-out**: `duplicate_heading` **excludes** the exact heading text
  `Codebase Research Findings`, deferring to the pre-existing `duplicate_findings_block` class
  (`issue_parser.py:1049`), which already detects it per-H2 and has a dedicated repair path
  (`ll-issues fold-findings`). Without this carve-out a duplicated findings block is reported twice
  under two different gap names, and two repairs would race for the same region. The alternative —
  subsuming `duplicate_findings_block` into the general class — is rejected: it would break the
  existing gap-class name in the JSON payload for current consumers.
- **Register `fold-findings` as `duplicate_findings_block`'s repair.** The dispatch table lands
  anyway; wiring the existing class into it is nearly free and is the only thing that proves the
  table generalizes past N=2 rather than being a two-case `if`. In scope.
- **Safety convention (inherited)**: `--fix` previews, `--fix --apply` writes. Do not introduce a
  second convention.
- **Sweep mode does not write bodies.** `--all --fix --apply` remains restricted to the existing
  frontmatter repairs (`prose_dep_drift` via `cmd_link`). The two new body-rewriting repairs run in
  single-issue mode only. Rationale under Impact › Risk.

### Signatures
- `cmd_format_check(config: BRConfig, args: argparse.Namespace) -> int` — the entry point gaining
  the `--fix` dispatch layer, at `scripts/little_loops/cli/issues/format_check.py:191`; returns 1
  when any gap remains.
- `_fix_prose_deps(config: BRConfig, source_id: str, targets: list[str], *, apply: bool) -> None` — the
  existing single repair whose shape the new repairs mirror, at
  `scripts/little_loops/cli/issues/format_check.py:110`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

- Exact anchors, corrected against current line numbers: `_fix_prose_deps` spans `scripts/little_loops/cli/issues/format_check.py:110-131` (not 110-130); the two hardcoded dispatch sites are `:298-308` (sweep) and `:340-352` (single-issue), each pairing the `if fix and gaps.prose_dep_drift:` gate with a re-check call to `check_format_gaps` (same kwargs) only `if apply_fix` — this re-check-after-apply call is duplicated verbatim at both sites today and is a natural third thing the dispatch refactor can centralize alongside the fixer lookup.
- `FormatGaps` dataclass spans `scripts/little_loops/issue_parser.py:483-564` (fields `:491-511`, `has_gaps` OR-chain `:513-538`, `to_dict()` `:540-564`); the "Gap classes:" docstring table inside `check_format_gaps()` runs `:623-746`. `cmd_format_check`'s own docstring (`:201-203`) states the enforced invariant: every `FormatGaps` field must have a matching loop in `_print_gaps` (`format_check.py:134-189`), or it counts toward `has_gaps`/exit 1 while rendering nothing — the exact defect class ENH-2946 fixed for the `testable` field. The two new gap classes need the same four-touchpoint treatment (field, has_gaps clause, to_dict key, docstring paragraph) plus a `_print_gaps` loop.
- Existing "collapse duplicates, concatenate bodies in document order, keep first position" precedent, directly reusable as the merge-order template: `fold_research_findings()` (`scripts/little_loops/issues/fold_research_findings.py:156-223`) — a pure function on `str` (I/O and dry-run live only in the CLI wrapper), documented as relocation-only ("nothing is deleted, summarized, or deduped"), collapsing N>1 occurrences into the *first* span's position by removing later spans in reverse order (so earlier offsets stay valid) and reinserting the merged block there.
- `duplicate_findings_block` detection precedent: `_duplicate_findings_blocks()` (`issue_parser.py:1049-1068`), built on `_iter_h2_sections()` (`:1380-1395`), which yields `(heading, start, end)` per `##` slice — explicitly *not* built on the document-wide `_heading_bodies()` helper, because that helper carries no parent-section info and would false-positive on N separate H2s each legitimately holding one instance. `duplicate_heading` detection needs the same per-H2 slicing but tallying a variable heading text via `Counter`, not a single fixed-pattern count like `_FINDINGS_H3_RE`.
- `empty_provenance_stub` detection has no existing precedent as close as `duplicate_findings_block`'s: `superseded_marker_count` (`issue_parser.py:1173-1199`) is a whole-body substring count via `_heading_bodies()`, not a line-adjacency check. The closer shape is `_paragraph_spans` (`:1100-1117`), which walks `text.splitlines(keepends=True)` tracking blank-line-delimited spans — needed because "stub with no bullet before the next heading" requires looking at what comes after the stub line, not just counting occurrences within a body.

## Implementation Steps

1. Refactor `--fix` into a gap-class → repair dispatch table; prove `prose_dep_drift` behavior is
   unchanged by the existing tests. Register `duplicate_findings_block` → `fold-findings` in the same
   table (see Decision Rules) so the table is exercised at N=3, not N=2.
2. Add the `duplicate_heading` and `empty_provenance_stub` gap classes to `issue_parser.py`
   (`FormatGaps`, `has_gaps`, dict serialization, docstring table) and to `_print_gaps`. Both
   detectors mask fences via `fence_spans()`/`in_fence()` from the outset — retrofitting this after
   the repairs exist is how the corruption ships. Apply the `Codebase Research Findings` carve-out to
   `duplicate_heading`.
3. Implement the two repairs behind the existing dry-run/`--apply` convention, fence-masked, with the
   blank-line normalization rule from Expected Behavior. Restrict both to single-issue mode; leave
   `--all` writing frontmatter only.
4. Record the `_duplicate_findings_blocks()` fence-blindness decision (fix here, or defer with a
   captured follow-up issue).
5. Add detection, preview, apply, idempotency, and **fence-safety** tests using the three fixtures
   named in Integration Map › Tests.
6. Update `docs/reference/CLI.md`.
7. `python -m pytest scripts/tests/` exits 0.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `add_format_check_parser()`'s `--help` text (`format_check.py:55-68`) and
  `cmd_format_check`'s docstring (`:194-199`) with the two new gap-class names — both hardcode the
  gap-class list independently of CLI.md.
- Confirm `rn-remediate.yaml`'s `ensure_formatted` state (`:100-121`) picking up the exit-code
  widening (routes to an extra `/ll:format-issue --auto` pass) is the intended behavior, not an
  unnoticed side effect.
- Sweep existing test fixtures across the suite for any that assert `format-check` exits 0 on an
  issue containing duplicate `###` headings or an empty provenance stub — these will flip to exit 1.

## Impact

- **Priority**: P2 - Removes an entire debris class from every issue deterministically and at
  near-zero cost, and supplies the cheap first stage of ENH-3248's triage.
- **Effort**: Small-Medium - the dispatch refactor is mechanical; the two repairs are small; the
  test matrix (4 cases × 2 classes, plus fence safety) is the bulk of it.
- **Risk**: Medium - `--fix --apply` mutates issue files, and the duplicate-heading merge moves
  content between locations. Mitigated by dry-run default, the never-drop-a-body rule, fence masking,
  and idempotency tests. The exit-code widening also affects existing `format-check` callers.
- **Risk — sweep blast radius**: today `--all --fix --apply` only adds frontmatter edges via
  `cmd_link`, which is idempotent and cycle-safe. Extending the new body-rewriting repairs to sweep
  mode would rewrite markdown bodies across the entire backlog in one command, with no backup and no
  per-file review — a categorically larger failure mode than anything `--fix` can do now. **Mitigation
  (decided, see Decision Rules): the two new repairs are single-issue mode only.** If sweep support is
  wanted later it should be a separate issue, gated on a clean git working tree so the blast is
  reviewable as a diff.
- **Breaking Change**: No - new gap classes are additive to the JSON payload; the exit code fires on
  strictly more conditions, which is the intent.

## Scope Boundaries

**Determinism is the admission test.** Only repairs with a single correct output belong here.
Filling a `TBD` requires knowing what should replace it — that is `/ll:reconcile-issue`'s job
(ENH-3246), not this command's. Detecting the placeholder is ENH-3244's.

**Not a new command.** `format-check --fix` already exists with the right convention; a separate
`normalize-structure` would duplicate the write path and split detection from repair.

**Fenced content is out of scope by construction**, not by omission. A duplicate heading or empty
stub inside a ```` ``` ```` block is documentation — an issue explaining the debris this command
repairs must be able to show it. See Proposed Solution step 0.

**Sweep-mode body repair is out of scope.** The two new repairs run in single-issue mode only; see
Impact › Risk — sweep blast radius. Extending them to `--all` is a separate issue.

## Related Issues

- BUG-3245 — stops new duplicate headings and empty stubs being created; this issue cleans existing
  ones. Both are needed; neither blocks the other. BUG-3245's own file is this issue's real-world
  duplicate-heading fixture and is deliberately left uncleaned until this issue's detection lands.
- ENH-3244 — placeholder detection, which lands in the same `format-check` payload and is
  `blocked_by` this issue. **Ownership split (see Decision Rules):** `empty_provenance_stub` is this
  issue's; literal template strings are ENH-3244's. Note ENH-3244 additionally needs *inline-code*
  masking that this issue's fence-only masking does not provide — its own file is the counter-example.
- ENH-3246 — owns the non-deterministic half (filling placeholders from findings).
- ENH-3248 — consumes this as the first, cheapest stage of the retry triage.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._


## Blocks

- ENH-3244
- ENH-3248

## Status

**Done** | Created: 2026-08-17 | Completed: 2026-08-17 | Priority: P2


## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue and ENH-2966 both modify `check_format_gaps`/`FormatGaps` in `scripts/little_loops/issue_parser.py` for unrelated gap classes (ENH-3247's two new structural-debris gap classes vs. ENH-2966's testable-keyword scan surface). Coordinate implementation order to avoid a merge collision in the same function.

## Session Log
- `/ll:ready-issue` - 2026-08-17T22:12:48 - `4d3fe332-8d66-43da-8f30-42deac212b4e.jsonl`
- `/ll:confidence-check` - 2026-08-17T21:34:22 - `878d0e98-a6e4-41e7-80a9-53a56e3db6f7.jsonl`
- `/ll:confidence-check` - 2026-08-17T20:31:13 - `e97f4c03-b671-421e-ac95-ea56a86f3a4e.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-17T20:25:55 - `fe71c380-6bd8-44e2-9c73-d0617456c6e4.jsonl`
- `/ll:confidence-check` - 2026-08-17T20:10:26 - `37e075a7-49b8-44db-b567-e15852c40c0b.jsonl`
- `/ll:wire-issue` - 2026-08-17T19:59:57 - `86ab77f1-d20d-487b-9f55-2f4d8abf9a06.jsonl`
- `/ll:refine-issue` - 2026-08-17T19:49:50 - `91301036-37cc-4bb2-8a07-a3ddf3c555b7.jsonl`
- `/ll:capture-issue` - 2026-08-17T19:29:38 - `3ce34465-00fd-4ba7-a470-b61774849ebd.jsonl`
