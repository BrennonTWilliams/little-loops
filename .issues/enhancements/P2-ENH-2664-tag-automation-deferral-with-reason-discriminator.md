---
id: ENH-2664
type: ENH
priority: P2
status: done
captured_at: '2026-07-18T02:50:02Z'
completed_at: '2026-07-18T03:26:18Z'
discovered_date: '2026-07-18'
discovered_by: capture-issue
parent: EPIC-2663
relates_to:
- FEAT-2665
- ENH-2666
decision_needed: false
labels:
- loops
- issue-lifecycle
- orchestration
confidence_score: 100
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# ENH-2664: Tag automation deferral with a reason discriminator

## Summary

When `rn-implement` defers an issue it writes a bare `status: deferred` with no
machine-readable indication of *who* deferred it or *why*. This conflates two
distinct situations that need different downstream treatment. Add frontmatter
fields — `deferred_by: automation|human`, `deferred_reason: <code>`, and a
`deferred_at` timestamp — set at every deferral site.

## Motivation

`rn-implement`'s `mark_deferred` state (rn-implement.yaml:1330-1357) is reached
from two very different conditions:

1. **Unmet `blocked_by` deps** (`check_blocked_by`, line ~518) — recoverable; a
   within-run re-enqueue path already exists.
2. **Remediation stalled AND decomposition declined** (`route_dec_stalled_origin`,
   line ~1201) — this is an issue that needs *human* attention, yet it gets the
   same quiet `deferred` as an intentional human "not now."

Without a discriminator, downstream tooling (FEAT-2665's resurfacing sweep, any
triage view) can't tell an automation circuit-breaker from a deliberate human
deferral, and can't prioritize the "remediation stalled" class that most needs
review. This is the enabling change for the rest of EPIC-2663.

## Current Behavior

- `mark_deferred` runs `ll-issues set-status "$ID" deferred` — status only.
- `issue_lifecycle.py:defer_issue()` (794-857) writes `status: deferred` to
  frontmatter with no reason metadata.

## Proposed Behavior

- Extend `defer_issue()` to accept and persist `deferred_by`, `deferred_reason`,
  and `deferred_at`.
- Pass a distinct `deferred_reason` at each `mark_deferred` entry point
  (`blocked_by_unmet`, `remediation_stalled`, `decomposition_declined`).
- Human/manual deferral (`ll-issues set-status <ID> deferred`) defaults
  `deferred_by: human`.

## API/Interface

- `defer_issue(issue_id, *, deferred_by="human", deferred_reason=None, deferred_at=None)` — additive kwargs.
- Reason codes are a small closed enum documented in `.claude/CLAUDE.md` § Issue File Format.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

> ⚠ **The proposed `defer_issue(issue_id, *, ...)` signature does not match the
> real code, and `defer_issue()` is not on the automation deferral path.**
> - Real signature: `defer_issue(info: IssueInfo, config: BRConfig, logger:
>   Logger, reason: str | None = None, event_bus: EventBus | None = None)` at
>   `scripts/little_loops/issue_lifecycle.py:794-857`. It takes an `IssueInfo`,
>   not a bare `issue_id`, and already has a `reason` string param.
> - **`defer_issue()` has zero callers** in `scripts/` or any loop YAML (repo-wide
>   grep confirms only the definition + doc/issue references). It is library-only /
>   effectively dead relative to automation.
> - The automation deferral path is **entirely** `ll-issues set-status <ID>
>   deferred` → `cmd_set_status()` (`scripts/little_loops/cli/issues/set_status.py:13-135`),
>   which does its own read/update/write via `update_frontmatter` and **never calls
>   `defer_issue()`**. So the primary integration site for stamping the
>   discriminator is `set_status.py`, not `defer_issue()`.
> - `defer_issue()` today writes the reason only into a Markdown `## Deferred`
>   body section (`_build_deferred_section`, `issue_lifecycle.py:770-779`) and the
>   `issue.deferred` event payload (`:841-851`) — never into frontmatter.

**Naming precedent already exists (decision point).** ENH-2535 introduced closure-context
frontmatter that `show.py` already reads and renders:
- `deferred_reason` — `scripts/little_loops/cli/issues/show.py:202,335,390`
- `deferred_date` — `show.py:205`; documented in `docs/reference/CLI.md:1150`

The issue proposes `deferred_reason` (name collision) + `deferred_at` (near-synonym of the
existing `deferred_date`). Two viable field-naming strategies:

**Option A** (reuse existing keys): Add only `deferred_by`; reuse `deferred_reason` for the
enum code and `deferred_date` for the timestamp. Pro: aligns with `show.py`'s existing
display, no new keys. Con: overloads `deferred_reason` — ENH-2535's usage is free-text
closure prose, this needs a machine-readable enum code; may need a `show.py` tweak to
render a code vs. prose.

> **Selected:** Option A (reuse existing keys) — reuses `deferred_date` (no new timestamp
> field), avoids reproducing the existing `_at`/`_date` drift, and lets `deferred_by`
> discriminate enum code from prose.

**Option B** (distinct machine keys): Add `deferred_by` + `deferred_reason` (enum code) +
`deferred_at`, keeping them distinct from ENH-2535's display fields, and update `show.py`
to read the new keys. Pro: clean separation of machine-code vs. human-prose. Con: two
timestamp fields (`deferred_at` vs `deferred_date`) risks drift; more surface to keep in
sync.

**Recommended**: Option A for v1 — reuse `deferred_reason`/`deferred_date`, add
`deferred_by`, and have the automation path write an enum code into `deferred_reason`.
Minimizes new frontmatter keys and reuses the existing `show.py` consumer. Confirm whether
ENH-2535 prose and the ENH-2664 enum code can coexist in one field before finalizing.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-17.

**Selected**: Option A (reuse existing keys)

**Reasoning**: The two options differ on only one substantive axis — the timestamp field.
Both overload `deferred_reason` with a machine enum code (Option B's "distinct"
`deferred_reason` actually name-collides with ENH-2535's existing key), so the real
difference is reusing `deferred_date` (A) vs. adding a new `deferred_at` (B). The codebase
already carries a checked-in `_at`/`_date` naming drift (`closed_at` vs `deferred_date`,
`show.py:204-205`) with no lint guarding it; Option B would add a third variant to that
inconsistency. The prose-vs-enum overloading of `deferred_reason` applies equally to both
options and is resolved by the shared `deferred_by` discriminator — a reader keys off
`deferred_by: automation` to interpret `deferred_reason` as an enum code. Option A therefore
wins on simplicity (one fewer new key, reuses the existing `deferred_date` render in
`show.py`) at no extra risk.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (reuse keys) | 2/3 | 3/3 | 3/3 | 2/3 | 10/12 |
| Option B (distinct keys) | 2/3 | 2/3 | 3/3 | 2/3 | 9/12 |

**Key evidence**:
- Option A: `deferred_reason`/`deferred_date` exist and are read/rendered by `show.py:202,205,335,390`; reuses `_completed_at_now()` + `update_frontmatter()` + the `_status_updates()` `done`-branch template (`set_status.py:38-49`). Sole caveat — `show.py:335,503-510` renders `deferred_reason` verbatim, so an automation enum code needs a `show.py` code→label tweak; this caveat applies to Option B too.
- Option B: matches the prefixed field-family precedent (`closed_*`/`cancelled_*`/`deferred_*`), but adds `deferred_at` as a third `_at`/`_date` timestamp variant and requires ~4 additional `show.py` read/render sites, with no lint preventing `deferred_at`/`deferred_date` drift.

**Follow-up for implementation**: add the `show.py` code→prose mapping (or accept raw-token
display) so an automation `deferred_reason` enum renders acceptably — required regardless of
option, gated on `deferred_by: automation`.

## Implementation Steps

1. Add the reason enum + frontmatter writer to `issue_lifecycle.defer_issue()`.
2. Thread `--reason`/`--by` (or equivalent) through `ll-issues set-status` for the deferred path.
3. Set the reason at each `mark_deferred` route in `rn-implement.yaml`.
4. Document fields + reason enum in `.claude/CLAUDE.md`.
5. Tests: assert each deferral path stamps the expected `deferred_by`/`deferred_reason`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete, code-grounded revision of the steps above:_

1. **Define the reason enum.** Model on `FailureType(Enum)` at
   `issue_lifecycle.py:51-62`, or a `frozenset` like `_OPEN_STATUSES`
   (`issue_progress.py:12-14`). The two *automation* codes the loop can actually
   emit today are `blocked_by_unmet` and `remediation_stalled` (see note on step 3).
2. **Primary stamping site is `set_status.py`, not `defer_issue()`.** In
   `cmd_set_status()`'s inner `_status_updates(status)` closure
   (`set_status.py:38-49`), add a `status == "deferred"` branch that mirrors the
   existing `status == "done"` → `completed_at` branch — stamp `deferred_by`
   (default `"human"`), `deferred_date`/`deferred_at` via `_completed_at_now()`
   (`issue_lifecycle.py:41`, already imported at `set_status.py:35`), and
   `deferred_reason` from the new flag. This is applied uniformly to both the
   primary update (`set_status.py:68`) and cascaded children (`:122`).
3. **Add `--reason`/`--by` to the set-status subparser.** Register in
   `cli/issues/__init__.py:736-762` following the adjacent `--cascade`/`--cascade-to`
   template; the `skip` subcommand's `--reason` (`__init__.py` skip parser +
   `skip.py:cmd_skip`) is the closest single-flag precedent. Thread onto
   `args` and consume in `cmd_set_status`.
4. **Set the reason at each `mark_deferred` route** in
   `rn-implement.yaml:1330-1357`. The state's shell body already computes a two-branch
   `$REASON` (blocked_by vs. generic stall); pass it as `ll-issues set-status "$ID"
   deferred --by automation --reason <code>`. Entry points:
   - `route_blocked_by` (`on_yes: mark_deferred` @ `:518`) → `deferred_reason:
     blocked_by_unmet` (an `UNMET_FILE` exists).
   - `route_dec_stalled_origin` (`on_yes: mark_deferred` @ `:1201`, matches
     `STALLED_NEEDS_DECOMPOSE`) → `deferred_reason: remediation_stalled`.
   - **Note:** the issue's Motivation names a third code `decomposition_declined`,
     but the shell folds that into the same generic stall branch — there is no
     separate signal at `mark_deferred` to distinguish it. Either (a) collapse to two
     codes for v1, or (b) split the routing/`$REASON` upstream to surface the third.
   - Also consider `mark_learning_blocked` (`rn-implement.yaml:1359+`), a sibling
     deferral-like state that writes `failures.txt` with `LEARNING_GATE_BLOCKED_*`
     tags — it does **not** currently call `set-status deferred`, so it is out of
     scope unless the epic wants that class tagged too.
5. **Document** the fields + enum in `.claude/CLAUDE.md` § Issue File Format
   (`:174-179`), plus `docs/reference/CLI.md` (set-status) and `docs/reference/API.md`
   (`defer_issue` signature, `:2479-2498`).
6. **Optional — keep `defer_issue()` in sync.** Since it's dead relative to
   automation, updating it is cosmetic, but for consistency add the same
   frontmatter keys to its `update_frontmatter(content, {"status": "deferred"})`
   call (`issue_lifecycle.py:831`) and extend the `issue.deferred` event payload
   (`:841-851`) + its schema in `observability/schema.py`.
7. **Tests.** Mirror the positive/negative pair
   `test_set_status_done_stamps_completed_at` / `test_set_status_non_terminal_omits_completed_at`
   (`test_set_status_cli.py:80-145`): assert `deferred_by`/`deferred_reason`/`deferred_date`
   are stamped on the `deferred` transition and absent otherwise. `TestDeferIssue`
   (`test_issue_lifecycle.py:1153-1223`) covers the library path if step 6 is done.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/set_status.py:38-49` — add `deferred` branch to
  `_status_updates()` (primary stamping site).
- `scripts/little_loops/cli/issues/__init__.py:736-762` — add `--reason`/`--by` flags
  to the `set-status` subparser; thread onto `args`.
- `scripts/little_loops/loops/rn-implement.yaml:1330-1357` — pass `--by automation
  --reason <code>` from `mark_deferred`, distinct per entry point.
- `scripts/little_loops/issue_lifecycle.py:794-857` — (optional) mirror the fields in
  `defer_issue()` + `issue.deferred` event payload.
- `.claude/CLAUDE.md:174-179`, `docs/reference/CLI.md`, `docs/reference/API.md` — docs.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/observability/schema.py:416-420` — `IssueDeferredVariant` (DES variant for `issue.deferred`). **Only if optional step 6 lands** (extending `defer_issue()`'s event payload with the new keys). The variant declares only a `type: Literal["issue.deferred"]` discriminator and inherits its payload shape from the base `DESVariant`, so no structural class change is required unless payload fields are typed explicitly; `ll-verify-des-audit` still passes since the emit-site name is unchanged. [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:1150` — the closure-context bullet already documents `deferred_reason`/`deferred_date` (ENH-2535 free-prose semantics); add a note that under `deferred_by: automation`, `deferred_reason` is an **enum code**, not prose. [Agent 2 finding]
- `docs/reference/CLI.md:1627-1641` — the `#### ll-issues set-status` argument table has no `--reason`/`--by` rows and its examples show no usage; add two table rows + an example invoking `set-status <ID> deferred --by automation --reason <code>`. [Agent 2 finding]
- **Verified no coupling (report only):** `config-schema.json:105-110` documents only the config-default `status` enum, not issue frontmatter — it is *not* the place for the reason-code enum (target `.claude/CLAUDE.md` § Issue File Format instead). No `commands/*.md` or `skills/*/SKILL.md` mentions the deferred-specific fields. [Agent 2 finding]

### Consumers Verified Unaffected (report only)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/skip.py:cmd_skip` — guards *against* deferred (`status in ("done","cancelled","deferred")` @ `:40`), never writes `status: deferred`, shares no code path with `_status_updates()`. Its `--reason` is a naming precedent only; **no change needed**. [Agent 1 + Agent 2 finding]
- `ll-parallel` / `ll-auto` / `ll-sprint` — all shell out to `ll-issues set-status` as a subprocess (no in-process `Namespace` construction), so new *optional* flags don't break them. `parallel/orchestrator.py`'s `_requeue_deferred_issues()` (`:1210-1228`) manages a within-run re-enqueue of deferred issues but keys off `status`, not the new discriminator — out of scope for ENH-2664 (relevant later to FEAT-2665). [Agent 1 + Agent 2 finding]

### Dependent Files (Callers / Consumers)
- `scripts/little_loops/cli/issues/show.py:202,205,335,390` — already reads
  `deferred_reason`/`deferred_date` for closure-context display (ENH-2535); verify it
  renders the new enum-code value acceptably.
- `scripts/little_loops/loops/rn-implement.yaml` — `route_blocked_by:518`,
  `route_dec_stalled_origin:1201`, `check_blocked_by:405-508` (writes
  `blocked_by_unmet_<ID>.txt`).
- FEAT-2665 (blocked_by ENH-2664) — the resurfacing sweep that consumes the
  discriminator.

### Reusable Helpers
- `_completed_at_now()` (`issue_lifecycle.py:41`) — Z-suffixed ISO frontmatter
  timestamp; already imported in `set_status.py`.
- `update_frontmatter()` / `parse_frontmatter()` (`frontmatter.py`) — the single
  read/write path used by all three lifecycle sites.
- `FailureType(Enum)` (`issue_lifecycle.py:51-62`) / `STATUS_SYNONYMS`
  (`frontmatter.py:18-27`) — closed-enum patterns to model the reason codes on.

### Tests
- `scripts/tests/test_set_status_cli.py:80-145` — positive/negative stamping template.
- `scripts/tests/test_issue_lifecycle.py:1153-1223` (`TestDeferIssue`) — library path.
- `scripts/tests/test_rn_implement.py` — loop-level `mark_deferred` coverage.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_decisions.py:244-313` (`TestSourceProvenanceFields`) + `scripts/tests/test_cli_decisions.py:380-454` — **strongest precedent** (ENH-2667): the three-tier "new optional field on write" test shape to model on — (1) round-trips through the write/read fn, (2) backward-compat: pre-existing data / omitted flag loads as `None`/absent (not an error), (3) omit-when-None: field absent from output when unset, (4) CLI-level test threading the new argparse flag through `main_issues()` end-to-end. Mirror this for `deferred_by`/`deferred_reason`/`deferred_date`. [Agent 3 finding]
- `scripts/tests/test_rn_implement.py` — update specific static-assertion tests to distinguish the two reason codes at their two routes: `TestDeferredOnStall.test_mark_deferred_writes_reason_sets_status_and_dequeues` (~`:993`) and `TestBlockedByGate.test_mark_deferred_names_unmet_blocker` (~`:1074`) — assert `--reason blocked_by_unmet` on the `route_blocked_by` branch, `--reason remediation_stalled` on the `route_dec_stalled_origin` branch, and `--by automation` present. No existing test distinguishes which route produced which reason. [Agent 3 finding]
- `scripts/tests/test_set_status_cli.py` — new cases beyond the stamping pair: invalid `--reason`/`--by` choice → argparse exit 2 (mirror `test_set_status_invalid_value_rejected:204`, using `choices=` on the flags); `deferred_date` ISO-8601 `Z`-suffix format assertion (mirror `test_set_status_done_stamps_completed_at:108-110`); establish expected behavior for `--reason` passed without `deferred` status (no-op vs reject — currently undefined). [Agent 3 finding]
- `scripts/tests/test_show.py` — reads `deferred_reason`/`deferred_date`; verify an automation **enum code** renders acceptably (gated on the `show.py` code→label follow-up). [Agent 1 + Agent 3 finding]
- `scripts/tests/test_wiring_reference_docs.py` — references the deferred fields; check whether the new/reused key documentation keeps it green. [Agent 1 finding]
- **No tests expected to break:** no repo test does exact-dict frontmatter equality on a deferred issue; all `deferred`-adjacent assertions use substring/`.get()` checks that tolerate added keys (e.g. `test_cascade_active_children_get_deferred_by_default:267`, `test_cascade_continues_on_individual_failure:614`). [Agent 3 finding]

**Argparse precedent note:** for the constrained flags, model `--reason`/`--by` on the existing `choices=`/`default=` args already in the `set-status` subparser (`__init__.py:744-761`, e.g. the `status` positional and `--cascade-to` choices), not on `skip.py`'s unconstrained free-text `--reason`.

## Impact

- **Priority**: P2 — blocks FEAT-2665; small surface, high leverage.
- **Effort**: Small.
- **Risk**: Low — additive frontmatter; no change to selection semantics.
- **Breaking Change**: No.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Resolution

Implemented Option A (reuse existing `deferred_reason`/`deferred_date` keys, add
`deferred_by`) per the recorded decision:

- Added `DeferBy`/`DeferReason` enums (`issue_lifecycle.py`) documenting the
  `human`/`automation` discriminator and the two automation reason codes.
- `set_status.py`'s `_status_updates()` gained a `deferred` branch that stamps
  `deferred_by` (default `human`), `deferred_date`, and `deferred_reason` (when
  provided) — the primary stamping site, confirmed by `/ll:refine-issue` research.
- Added `--by {human,automation}` / `--reason {blocked_by_unmet,remediation_stalled}`
  choices-constrained flags to the `set-status` subparser.
- `rn-implement.yaml`'s `mark_deferred` state now passes `--by automation --reason
  <code>`, distinguishing `blocked_by_unmet` (from `route_blocked_by`) from
  `remediation_stalled` (from `route_dec_stalled_origin`).
- `defer_issue()` was left unchanged (optional/cosmetic step — it has zero callers
  on the automation path per the refine-issue finding).
- `show.py` already renders `deferred_reason`/`deferred_date` verbatim; the
  automation enum code displays as raw text (accepted per the issue's follow-up
  note — no `show.py` code→label mapping added for v1).

## Session Log
- `/ll:manage-issue` - 2026-07-18T03:25:41Z - `d5c676bb-de27-4239-8136-10a939bf6c45.jsonl`
- `/ll:ready-issue` - 2026-07-18T03:17:37 - `1bc61385-8931-4b84-b29a-562a5ee0d2f6.jsonl`
- `/ll:wire-issue` - 2026-07-18T03:12:16 - `5b371a7f-6f3f-4a6b-a7e3-0d2e9c555d54.jsonl`
- `/ll:decide-issue` - 2026-07-18T03:05:24 - `2d062121-c6c8-4eac-acd8-deaa9fe844d1.jsonl`
- `/ll:refine-issue` - 2026-07-18T03:01:00 - `2d062121-c6c8-4eac-acd8-deaa9fe844d1.jsonl`
- `/ll:capture-issue` - 2026-07-18T02:50:02Z

---

## Status

- **Current**: open
- **Last Updated**: 2026-07-18
