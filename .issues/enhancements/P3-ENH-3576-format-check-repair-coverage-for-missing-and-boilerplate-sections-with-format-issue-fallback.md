---
id: ENH-3576
type: ENH
title: Format-check repair coverage for missing and boilerplate sections with format-issue
  fallback
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T19:33:14Z'
parent: EPIC-3565
blocks:
- ENH-3577
confidence_score: 100
outcome_confidence: 78
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# ENH-3576: Format-check repair coverage for missing and boilerplate sections with format-issue fallback

## Summary

`refine-to-ready-issue`'s normalization step runs `ll-issues format-check <ID> --fix --apply`
and tolerates failure with `|| true`. `format_check._REPAIR_DISPATCH` repairs exactly six gap
classes: `prose_dep_drift`, `duplicate_findings_block`, `duplicate_heading`,
`empty_provenance_stub`, `template_placeholders` (derivable tokens only) and
`duplicate_session_log`. Missing, renamed, empty and boilerplate sections have no
deterministic repair, and the loop never invokes `/ll:format-issue`. Refinement and
ready-issue may incidentally repair some gaps, but there is no guaranteed
check → apply → recheck cycle. Separately, the BUG and ENH templates do not list
`Acceptance Criteria` as a required section (only FEAT does), so a BUG/ENH with no AC section
produces no format gap at all, and `ll-issues check-acceptance-criteria` exits 0 on it.

## Current Behavior

- A structurally malformed issue reaches `/ll:refine-issue` (the most expensive research step) with no structural check at all — `normalize_structure` first runs after refine and wire.
- After `normalize_structure`, remaining `missing`/`empty`/`boilerplate`/`renamed` gaps in directive sections are silently discarded (`|| true`, pass-through state).
- A BUG/ENH with no `## Acceptance Criteria` passes `format-check`, `check-acceptance-criteria` and the confidence-check Phase 1.8 `STRUCT_GAP` probe. Phase 1.8's `{Summary, Acceptance Criteria}` allowlist therefore only ever fires on `Summary` for BUG/ENH.

## Expected Behavior

1. Deterministic check
2. Apply supported repairs
3. Recheck
4. Invoke `/ll:format-issue --auto` only when directive-section gaps remain, at most once per run
5. Recheck; directive gaps that survive the fallback are reported (`[STRUCT_GAP_REMAINS]`) and
   the loop proceeds — they are advisory from here on, capping confidence-check Criterion 4 via
   Phase 1.8 `STRUCT_GAP`, never a routing blocker

This runs twice: before `refine_issue` (so research starts from a well-formed file) and at
every `normalize_structure` pass (after content-changing steps). Ceremonial gaps
(`Impact`, `Status`) never route; `Program Design` stays owned by `check_design`.

## Motivation

Malformed structure is cheap to detect and fix deterministically. Leaving it to incidental repair during expensive research wastes budget and lowers score quality.

## Proposed Solution

**Directive set.** Directive sections are every *required* template section except
`{Program Design, Impact, Status}`: Summary, Current Behavior, Expected Behavior, plus
type-specific ones (BUG: Steps to Reproduce; ENH: Scope Boundaries; FEAT: Use Case,
Acceptance Criteria). Deriving the set from the template, rather than hardcoding names, keeps
it type-aware.

**Template change.** Add `Acceptance Criteria` to `type_sections` in `bug-sections.json` and
`enh-sections.json` with `"level": "required"`, mirroring the existing `feat-sections.json`
entry. This is a template-data change, not a change to `check_format_gaps` logic.

**`directive_gaps` projection.** Add `directive_gaps(gaps) -> list[str]` in `issue_parser.py`,
which projects `missing`/`empty`/`boilerplate` names and `renamed` targets (the text after `→`)
onto the directive set. Emit it as a `directive_gaps` key in the single-issue
`--format json` payload, beside `superseded_marker_count`. It is not a `FormatGaps` field, so
`has_gaps`/`has_blocking_gaps` and exit codes are unchanged. The loop and Phase 1.8 both
read this key instead of re-deriving the set inline.

**Status fixer.** Add `_fix_missing_status` to `_REPAIR_DISPATCH` under the `missing` key.
It acts only when `Status` is among the targets and renders
`**<Status>** | Created: <discovered_date> | Priority: <P>` from frontmatter
(`resolve_priority`, `discovered_date`, display-cased `status`). It is a no-op when any value
is unresolvable, so it never writes a partial line. It inserts before `## Session Log` when
present, else appends. Single-issue only: not added to `_SWEEP_SAFE_REPAIRS`. `Impact` gets no
fixer — its Effort/Risk fields are judgment, and inserting its template would create
`template_placeholders` debris that routes to refine.

**Loop (`refine-to-ready-issue.yaml`).**
- `normalize_structure` becomes a gate. Its action is two calls: `format-check --fix --apply`
  (output discarded, `|| true`), then `format-check --format json` reading
  `len(directive_gaps)`. Two calls are required because fixers print to the same stdout
  (`cmd_link`), which would corrupt a combined `--fix --apply --format json` payload. The
  budget is folded into the same probe:
  counter file `refine-to-ready-format-fallback` ≥ 1 with gaps remaining → print
  `[STRUCT_GAP_REMAINS] <ID>: <gaps>` to stderr and emit 0; gaps with counter 0 → write 1 to the
  counter and emit the count. Any probe failure emits 0 (fail-open). `evaluate: output_numeric
  eq 0`; `on_yes`/`on_error: clear_verify_verdict`, `on_no: format_issue_post`.
- New `precheck_format` state with the same action, between `check_lifetime_limit.on_yes` and
  `refine_issue`: `on_yes`/`on_error: refine_issue`, `on_no: format_issue_pre`.
- New `format_issue_pre` / `format_issue_post` states: `/ll:format-issue <ID> --auto`,
  bare slash-command shape (host-file convention — no rate-limit fragment, see
  `reconcile_issue`), `next` and `on_error` both to `refine_issue` / `clear_verify_verdict`
  respectively. The two share the one counter, so at most one format pass runs per run.
- `resolve_issue` seeds `printf '0' > …/refine-to-ready-format-fallback` (autodev reuses one
  `run_dir` across issues).
- Budget: `max_steps` 85 → 90 (+1 `precheck_format`, +1 fallback — shared bound — rounded for
  headroom, with the usual comment block). `recurrent_window` stays 6: `normalize_structure`'s
  new `(0, yes)` triple recurs once per gate-band pass, the same ~5 as the hottest existing
  triple (BUG-3574 recount).

## Program Design

### Types

- `DIRECTIVE_EXCLUDED_SECTIONS: frozenset[str]` — `{"Program Design", "Impact", "Status"}` in `issue_parser.py`; every other required section is directive
- `FormatGaps.missing: list[str]` — unchanged; read by `directive_gaps` and `_fix_missing_status`

### Signatures

- `directive_gaps(gaps: FormatGaps) -> list[str]` — projects `missing`/`empty`/`boilerplate` names and `renamed` targets onto the directive set, sorted and de-duplicated
- `_fix_missing_status(config: BRConfig, source_id: str, path: Path, targets: list[str], *, apply: bool) -> None` — inserts a frontmatter-rendered `## Status` section; same shape as the other `_fix_*` fixers

### Call Path

`cmd_format_check` -> `check_format_gaps` -> `_apply_fix_dispatch` -> `_fix_missing_status`; `cmd_format_check` -> `directive_gaps` (JSON payload); loop: `check_lifetime_limit` -> `precheck_format` -> `format_issue_pre` -> `refine_issue`, and `check_decision_mid_wire` -> `normalize_structure` -> `format_issue_post` -> `clear_verify_verdict`

## Scope Boundaries

- Out of scope: changing `check_format_gaps` detection logic or format-check exit-code semantics (the AC requirement is template data; `directive_gaps` is a payload projection)
- Out of scope: authoring substantive content beyond what `/ll:format-issue --auto` infers — surviving directive gaps are advisory (Phase 1.8), not re-routed to refine by this issue
- Out of scope: sweep mode (`--all --fix --apply`) repairs; `_fix_missing_status` stays single-issue only (see `_SWEEP_SAFE_REPAIRS`)
- Out of scope: a deterministic `Impact` inserter
- Out of scope: a cutover stamp for the AC requirement (unlike Program Design's `.ll/program-design-cutover.json`) — see Impact › Risk
- Out of scope: consolidating the preparation pipeline into one controller (ENH-3577)

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `resolve_issue` seed, `normalize_structure` gate, new `precheck_format`/`format_issue_pre`/`format_issue_post`, `check_lifetime_limit.on_yes`, `max_steps`
- `scripts/little_loops/cli/issues/format_check.py` — `_fix_missing_status`, `_REPAIR_DISPATCH` entry, `directive_gaps` in the single-issue JSON payload; `_print_gaps`'s `template_placeholders` line still says "no --fix" (stale since ENH-3248) — correct it
- `scripts/little_loops/issue_parser.py` — `DIRECTIVE_EXCLUDED_SECTIONS`, `directive_gaps`
- `scripts/little_loops/templates/bug-sections.json`, `scripts/little_loops/templates/enh-sections.json` — `Acceptance Criteria` as `"level": "required"`

### Dependent Files (Callers/Importers)
- `skills/confidence-check/SKILL.md` Phase 1.8 (`STRUCT_GAP`) — replace the inline `{Summary, Acceptance Criteria}` filter with the payload's `directive_gaps`; correct the "`/ll:format-issue` inserts missing sections" remedy note
- `is_formatted` consumers pick up the AC requirement automatically: `ll-issues show` ✓/✗, `ll-issues next-action` (`cli/issues/next_action.py`), `refine-status`'s `formatted` column
- `scripts/little_loops/loops/rn-remediate.yaml` `ensure_formatted` — gates on format-check's exit code, so BUG/ENH issues lacking AC now take its one `format_issue` pass (intended)

### Similar Patterns
- `rn-remediate.yaml` `ensure_formatted` → `format_issue` → `assess` — the same check → one bounded `/ll:format-issue --auto` pass → proceed shape, fail-open on every verdict
- `check_placeholders` / `check_verify_retries` in `refine-to-ready-issue.yaml` — JSON-probe and increment-in-probe counter idioms
- Existing `_fix_*` fixers in `format_check.py`; `superseded_marker_count` for a non-`FormatGaps` payload key

### Tests
- `scripts/tests/test_ll_issues_format_check.py` — `_fix_missing_status` (inserts rendered line; no-op on missing `discovered_date`; idempotent; skipped in sweep mode); `directive_gaps` (excludes Program Design/Impact/Status; maps `renamed` targets; includes `empty`/`boilerplate`); JSON payload carries `directive_gaps` with exit code unchanged; a BUG and an ENH without `## Acceptance Criteria` report it under `missing`
- `scripts/tests/test_spike_verdict_routing.py` pattern (`_stub_path` + `_run`: run a state's real shell action against a stubbed `ll-issues` on `PATH`) — new tests for the `normalize_structure`/`precheck_format` probe: gaps + counter 0 → nonzero output and counter becomes 1; counter 1 → output 0 plus `[STRUCT_GAP_REMAINS]` on stderr; no gaps → 0; failing stub → 0
- `scripts/tests/test_builtin_loops.py` — routing table (`check_lifetime_limit.on_yes == precheck_format`, fallback targets, `resolve_issue` seeds the counter, `max_steps`)

### Documentation
- `docs/reference/ISSUE_TEMPLATE.md` § Type-Specific Sections — list Acceptance Criteria (required) for BUG and ENH
- `docs/guides/LOOPS_REFERENCE.md` — `refine-to-ready-issue` row gains "format-check → one `/ll:format-issue` fallback"

### Configuration
- N/A

## Implementation Steps

1. Add `Acceptance Criteria` (`"level": "required"`) to the BUG and ENH templates; add the template test
2. Add `DIRECTIVE_EXCLUDED_SECTIONS` + `directive_gaps` and emit `directive_gaps` in the single-issue JSON payload; tests
3. Add `_fix_missing_status` to `_REPAIR_DISPATCH` (not sweep-safe); fix the stale `_print_gaps` note; tests
4. Loop: seed the counter in `resolve_issue`; convert `normalize_structure` to the probe gate; add `precheck_format`, `format_issue_pre`, `format_issue_post`; retarget `check_lifetime_limit.on_yes`; bump `max_steps` to 90 with a comment block
5. Probe state-action tests (stubbed `ll-issues`) and routing-table tests
6. Point confidence-check Phase 1.8 at `directive_gaps`; update `ISSUE_TEMPLATE.md` and `LOOPS_REFERENCE.md`
7. Run `ll-loop validate refine-to-ready-issue` and the full suite

## Impact

- **Priority**: P3
- **Effort**: Medium
- **Risk**: Medium — the AC template change makes 26 of 75 active BUG/ENH issues (counted 2026-09-25) newly report `missing: Acceptance Criteria`, flipping `format-check`'s exit code, `is_formatted`, and `rn-remediate`'s `ensure_formatted` for them. No gate hard-blocks on it (`normalize_structure` is fail-open and bounded; `rn-remediate` takes one format pass), so no cutover stamp is added.

## Acceptance Criteria

- [ ] A BUG or ENH issue with no `## Acceptance Criteria` reports `Acceptance Criteria` under `missing` in `ll-issues format-check --format json`
- [ ] The single-issue `--format json` payload carries `directive_gaps`, excluding `Program Design`, `Impact` and `Status`, and the exit code matches the pre-change exit code for the same gaps
- [ ] `ll-issues format-check <ID> --fix --apply` on an issue missing only `## Status` (with `priority` and `discovered_date` resolvable) leaves it with no `missing` gaps
- [ ] With a directive gap and counter 0, the probe emits a nonzero count and writes 1 to `refine-to-ready-format-fallback`; with counter 1 it emits 0 and prints `[STRUCT_GAP_REMAINS]` to stderr
- [ ] `check_lifetime_limit.on_yes` is `precheck_format`; `format_issue_pre` routes to `refine_issue` and `format_issue_post` to `clear_verify_verdict` on every exit; `resolve_issue` seeds the counter to 0
- [ ] `ll-loop validate refine-to-ready-issue` passes

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Verification Notes

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

- `format-check --json` does not exist; the flag is `--format json` — corrected.
- The normalization state is `normalize_structure` in `refine-to-ready-issue.yaml`; it runs after `refine_issue`/`refine_followup`/`wire_issue`, not before research. The "run before expensive research" expectation therefore needs a second placement, not just a `recheck_format` after the existing state — noted for implementation. *(Resolved 2026-09-25: `precheck_format` before `refine_issue`.)*
- All six `_REPAIR_DISPATCH` classes, the `|| true` tolerance and the Phase 1.8 `STRUCT_GAP` allowlist verified accurate.
- 2026-09-25 review: `Acceptance Criteria` is required only in `feat-sections.json`, so the AC half of the Phase 1.8 allowlist could never fire for BUG/ENH — resolved via the template change. An empty-heading `missing` inserter would only convert `missing` → `empty` (`check_format_gaps` flags empty required bodies), so the fixer is scoped to a fully rendered `Status`. The separate `recheck_format` state was folded into `normalize_structure` to save one step per gate-band pass.

## Status

**Open** | Created: 2026-09-24 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-09-25T17:25:07 - `b51bc121-4424-46da-83bd-8c5c91334957.jsonl`
- `/ll:format-issue` - 2026-09-25T17:14:23 - `6249b55a-80e7-48d1-ad8e-6ad301b4a4d0.jsonl`
- `/ll:verify-issues` - 2026-09-25T15:27:34 - `bc279096-6a89-4a82-b7c2-8e6f11cc30f5.jsonl`
- `/ll:capture-issue` - 2026-09-24T19:42:32 - `59fe3bd4-3622-4dd2-bb8b-ad5cc55e79ec.jsonl`
