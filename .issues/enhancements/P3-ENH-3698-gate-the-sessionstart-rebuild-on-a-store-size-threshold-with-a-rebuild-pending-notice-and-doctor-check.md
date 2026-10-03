---
id: ENH-3698
type: ENH
title: Gate the SessionStart rebuild on a store-size threshold with a rebuild-pending
  notice and doctor check
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-02'
captured_at: '2026-10-02T17:56:06Z'
blocked_by:
- ENH-3678
- ENH-3679
relates_to:
- ENH-3678
- ENH-3699
- ENH-3658
confidence_score: 75
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# ENH-3698: Gate the SessionStart rebuild on a store-size threshold with a rebuild-pending notice and doctor check

## Summary

Slice 3678b (split from ENH-3678, 2026-10-02). Above a store-size threshold the SessionStart hook must not auto-spawn `backfill_worker --rebuild`; it reports "rebuild pending" (SessionStart feedback and `ll-doctor`) and the user runs `ll-session rebuild` explicitly. **This must land before any `REBUILD_DERIVE_VERSION` bump**: ENH-3678 only changes *when* a rebuild is needed; without this gate a derive bump still forces a full multi-GB rebuild on every store.

## Current Behavior

After ENH-3678 the hook spawns `--rebuild` whenever `rebuild_needed()` is `stale`, regardless of store size. A ~9.6 GB store held the write lock for minutes on such a rebuild and dropped concurrent `ll-*` telemetry rows. No "pending" notice exists, and `ll-doctor` has no rebuild surface.

## Expected Behavior

- **Size gate.** A module constant (not a config key, to avoid `config-schema.json` / dataclass / `test_config_schema.py` churn; promote to config only if a user asks) of **1 GiB (`2**30` bytes)**, measured as `db_path.stat().st_size` of the **main DB file only**; `-wal` bytes are excluded (transient and checkpoint-dependent). There is no shared size helper today: sites inline `stat().st_size` behind an `exists()` guard, and units disagree (`1024 * 1024` in the retention gate, `1_000_000` in `recompress()`), so state the unit in the constant's name/comment. This constant is distinct from the config-driven `RetentionConfig.min_db_size_mb` (800).
- **Hook decision.** `handle` combines `rebuild_needed()` (ENH-3678) with the size check: `stale` and size <= threshold -> spawn `--rebuild` as today; `stale` and size > threshold -> no `--rebuild`, emit the pending notice; `current` or `unknown` -> neither. "Spawn" here means the `--rebuild` flag only: the incremental backfill worker's `Popen` is outside the check and still runs in every case (ENH-3678 review, 2026-10-03). "Pending" is this combination, not a state of `rebuild_needed`.
- **Unreadable size.** A failed size probe is unknown, never zero: skip auto-rebuild and the actionable pending notice; doctor reports an informational unknown reason without creating/migrating the store. Test a permission/stat failure separately from a missing DB.
- **Pending notice.** One `[little-loops] ...` line appended to `feedback_lines` (joined into `LLHookResult.feedback`; stdout stays the context payload), stating that a rebuild is pending, the command to run (`ll-session rebuild`), and the consequence: derived tables (sessions, tool/skill events, summaries, corrections, search index) keep pre-bump derivation until rebuilt; raw events and usage tables stay current. It fires only while the store is `stale` **and** over the size limit, which happens only after a derive bump and is actionable, so **no extra throttle** is added. It is **suppressed on the automation-pruning path** (see Tests).
- **Doctor check.** A report-only "rebuild pending" check following the doctor shape: `_<x>_data() -> dict` (`status`, `severity`, `note`), `_print_<x>_section()`, and an `@register_check` returning `CheckResult` with `severity="informational"` (a `severity == "error"` + `unsupported` result changes exit codes via `_exit_code_for`); the dict is added to the JSON payload and the print list (`cli/doctor.py` ~`:1742`, `:1860`; precedents `_history_db_data` ~`:503`, `_schema_drift_data` ~`:678`). It opens read-only, reports an absent DB as informational without creating it, and reports "not applicable" for a remote target. **It is the only surface for `unknown`** (ENH-3678 review, 2026-10-03): the SessionStart hook does not log or print `rebuild_needed`'s `unknown` reason (the hook module's `logger` has no handler), so the check reports the `unknown` status and its reason code (`read_error`, e.g. a lock timeout; `remote` maps to "not applicable") as informational.
- Remote stores never rebuild from a hook (the guard in `session_start.handle` stays ahead of the size `stat()`).

## Motivation

A multi-GB rebuild from a hook is the incident that motivated ENH-3678. The gate removes the cause for typical bumps; the size threshold removes the blast radius for the unavoidable ones, at the cost of an explicit user action.

## Scope Boundaries

- **In scope**: the size constant and check, the hook decision, the pending notice, the `ll-doctor` check, tests, and the end-user docs for them.
- **Out of scope**: `REBUILD_DERIVE_VERSION`/`rebuild_needed` (ENH-3678), the single-flight lock/cooldown/contention report (ENH-3699), restructuring `rebuild()` (ENH-3666), remote stores.
- **Sequencing:** ENH-3679 (drop-count line), ENH-3658 (`ll-doctor --trim` remote guard) and this issue all edit `cli/doctor.py` and the `ll-doctor` check list/count in `docs/reference/CLI.md`. Land them in sequence, never as parallel branches.

## Integration Map

### Files to Modify

- `scripts/little_loops/hooks/session_start.py` (`handle`, ~`:189-214`) — size gate, spawn decision, pending notice via `feedback_lines`; module-constant precedent `_LARGE_CONFIG_THRESHOLD` (`:51`); suppress the notice on the automation-pruning path.
- `scripts/little_loops/cli/doctor.py` — `_rebuild_pending_data`, `_print_rebuild_pending_section`, `@register_check`, and the JSON payload key in `_print_report`; do **not** spawn the worker from `ll-doctor` (`test_enh3184_spawn_site_guard.py` pins `cli/doctor.py` at `(2, 2)`).
- The size-constant home (a `lifecycle.py` or `session_start.py` module constant; pick one and import it in doctor so the two agree).

### Tests

- `test_hook_session_start.py::TestSessionStartRebuild` harness (`_setup`, `_FakePopen` argv recorder via `monkeypatch.setattr("little_loops.hooks.session_start.subprocess.Popen", ...)`): stale + small -> spawn; stale + over size (monkeypatch the constant or stub `stat`) -> argv without `--rebuild` and a notice in `feedback_lines`; `current`/`unknown` -> argv without `--rebuild` and no notice (the incremental `Popen` still runs in all cases); WAL bytes do not count.
- `TestAutomationPruningStayInTurn::test_pruning_gate_injects_stay_in_turn_instruction` (`result.feedback is None`, ~`:603`) — the pending notice must be suppressed on that path or this fails; `TestAmbientAutomationEnvHermeticity::test_suite_passes_with_ambient_ll_automation` re-runs the whole file under `LL_AUTOMATION=1`.
- `test_remote_hooks.py` — remote stores still never get `--rebuild` and never `stat()` a local path; `TestBackfillWorker::test_a_rebuild_is_refused_with_a_message_and_no_traceback` unchanged.
- Doctor: data function + `@register_check` with `severity="informational"`; absent-DB case (`test_cli_doctor_install_checks.py::TestHistoryDb` style, `_bootstrap_at(db, version)` helper); remote "not applicable" (`test_remote_doctor.py`); add the new function to `test_remote_doctor.py::TestNoTokenLeaks::test_no_doctor_surface_echoes_the_token`; `test_remote_callers_bug3652.py::_CALLER_ALLOWLIST` (`:97`, plus `test_allowlist_has_no_stale_entries`) needs an entry if the doctor function calls `resolve_history_db()`; `test_stray_ll_regression.py::test_ll_doctor_from_subdirectory_creates_no_stray_ll` must keep passing; `test_history_store_chokepoint_gate.py` (open via `connect_readonly`).

### Documentation (end-user shape; `test_docs_audience_gate.py`)

- `docs/reference/CLI.md` — `ll-doctor` "always runs 7 default install-surface checks" count and name list (~`:494`) and `--json` key list (~`:497`); `docs/reference/HOST_COMPATIBILITY.md` (~`:885`) and `docs/codex/usage.md` (~`:173`) install-surface check lists (`test_wiring_guides_and_meta.py` pins only the token `install-surface`).
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — SessionStart section (`:52` table row, `:153`, `:157` "You see": add the `[little-loops] ... rebuild pending` line).
- `docs/guides/HISTORY_SESSION_GUIDE.md` — explain what a pending rebuild means (stale derived tables; raw events and usage stay current) and how to run `ll-session rebuild`.
- `docs/ARCHITECTURE.md` `ll-doctor --json` payload key list (~`:922`) if the doctor surface adds a key.

## Program Design

### Types

- Module constant `REBUILD_AUTO_MAX_BYTES: int = 2**30` (name indicative) with a comment stating GiB and "main file only, WAL excluded".

### Signatures

- `_rebuild_pending_data(db: Path | None) -> dict` — `status`/`severity`/`note`; informational; remote -> not applicable; absent DB -> informational, no creation.

### Call Path

- `handle` (`little_loops.hooks.session_start`) → remote guard → `rebuild_needed` (ENH-3678) → size check → spawn `backfill_worker --rebuild` **or** pending notice in `feedback_lines`.
- `ll-doctor` → `_rebuild_pending_data` → `rebuild_needed` + size check → informational report line.

## Implementation Steps

1. Land ENH-3678 first. **Delete ENH-3678's ordering lockstep test** (`REBUILD_DERIVE_VERSION == _FROZEN_LEGACY_DERIVE_VERSION`, "do not bump before ENH-3698") in the same change that lands the size gate, so a derive bump becomes possible only once the gate exists. **Keep** ENH-3678's permanent frozen-literal pin test (`_FROZEN_LEGACY_DERIVE_VERSION == "<literal>"`); deleting the lockstep test must not remove it, or bumping both constants would silently mark legacy stores current. **Then check for silent-window drift:** if the fingerprint snapshot's `current_digest != frozen_legacy_digest` (derivation changes were regenerated without a bump while the lockstep test forbade bumping), bump `REBUILD_DERIVE_VERSION` in this change so existing stores re-derive (the size gate now protects large stores); if the digests match, no bump. The schema-58 digest can also be recomputed from `git show 9cb4467d6:<file>`. Add the size constant and the check (main file only, GiB). `rebuild_needed` already opens with a short busy timeout (ENH-3678); the doctor check reports a lock-timeout `unknown` as informational.
2. Extend `handle` with the spawn/pending decision and the notice; suppress on the automation-pruning path; keep the remote guard first.
3. Add the doctor check and payload key; allowlist/`TestNoTokenLeaks` updates.
4. Tests per above; docs per above. Sequence the `cli/doctor.py` and `docs/reference/CLI.md` edits with ENH-3679 and ENH-3658.
5. Run `python -m pytest scripts/tests/`, `ruff check scripts/`, `python -m mypy scripts/little_loops/`.

## Impact

- **Priority**: P3 - not needed to unblock FEAT-3561, but required before any derive-version bump
- **Effort**: Medium - one constant, a hook branch, a doctor check, tests and docs in several files
- **Risk**: Low-Medium - a wrong threshold could suppress a needed rebuild (accepted: stale derived tables are documented and the notice is actionable)
- **Breaking Change**: No

## Acceptance Criteria

- [ ] Above the size threshold (1 GiB, main file only, WAL excluded) a `stale` store spawns no `--rebuild` and surfaces the pending notice via `feedback_lines`; at or below it the hook spawns as before; `current`/`unknown` spawn nothing and print no notice.
- [ ] The notice explains the stale-derived-tables consequence and the `ll-session rebuild` command, is not throttled, and is suppressed on the automation-pruning path (`TestAutomationPruningStayInTurn` still passes).
- [ ] `ll-doctor` reports "rebuild pending" as an informational check (text and JSON), does not change the exit code, reports "not applicable" for a remote target, creates nothing, and is covered by `TestNoTokenLeaks`.
- [ ] Remote stores never rebuild from a hook and never reach the size `stat()`.
- [ ] A failed/unreadable size probe does not auto-spawn, treat the store as small, or claim a known pending state; doctor reports informational unknown. Record a representative sub-1 GiB replay duration in the implementation review while ENH-3699's single-flight protection remains deferred.
- [ ] No `REBUILD_DERIVE_VERSION` bump lands before this issue (ENH-3678's constant comment names it); ENH-3678's ordering lockstep test is deleted in this issue's change while its permanent frozen-literal pin test stays.
- [ ] At landing, `current_digest` vs `frozen_legacy_digest` in ENH-3678's fingerprint snapshot is checked: unequal -> `REBUILD_DERIVE_VERSION` bumped in this change; equal -> no bump.
- [ ] `ll-doctor`'s rebuild-pending check reports `unknown` (with its reason code) as informational; the hook emits nothing for `unknown`.
- [ ] `stale` + over-size and `unknown` hook cases still spawn the incremental worker without `--rebuild` (test asserts the argv).
- [ ] Docs (`CLI.md` check count/list, `BUILTIN_HOOKS_GUIDE.md`, `HISTORY_SESSION_GUIDE.md`) updated in end-user shape; `python -m pytest scripts/tests/` passes.

## Related

- ENH-3678 (blocked_by; the gate), ENH-3699 (single-flight lock; deferred), ENH-3679 and ENH-3658 (edit the same `ll-doctor` surfaces; sequence), ENH-3666, FEAT-3561.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Ordering vs ENH-3679: ENH-3679 lands first (matches `blocked_by: ENH-3679`); this issue then rebases onto its `cli/doctor.py` drop-count line and the `ll-doctor` check list/count in `docs/reference/CLI.md`. "Land them in sequence" means ENH-3679 → ENH-3698.

## Status

**Open** | Created: 2026-10-02 | Priority: P3


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-10-02; re-verified 2026-10-03 (unchanged: ENH-3678 and ENH-3679 still open)_

**Readiness Score**: 75/100 → STOP — ADDRESS GAPS (Dependencies Hard Override; aggregate alone would be PROCEED WITH CAUTION)
**Outcome Confidence**: 75/100 → MODERATE

### Concerns
- Criterion 1 (15/20): `handle` already carries an inline `last_rebuild_version < SCHEMA_VERSION` rebuild decision (`session_start.py` ~`:189-214`); this issue replaces/extends it via ENH-3678's `rebuild_needed()`, so the edit is an extension of existing logic, not greenfield.
- Doctor surface is pinned by several gates (`test_enh3184_spawn_site_guard.py`, `TestNoTokenLeaks`, `_CALLER_ALLOWLIST`, `test_stray_ll_regression.py`, `test_history_store_chokepoint_gate.py`); each must be updated or kept passing in the same change.
- Size-constant home is left as "a `lifecycle.py` or `session_start.py` module constant; pick one" — a minor open choice, resolvable during implementation.

### Gaps to Address
- Unresolved `blocked_by`: ENH-3678 (open) and ENH-3679 (open). Neither `rebuild_needed()` nor `REBUILD_DERIVE_VERSION` exists in `scripts/little_loops` yet, so the hook decision, the doctor check, and the lockstep-test deletion in Implementation Step 1 have nothing to build on or delete. Land ENH-3678 (then ENH-3679 for the `cli/doctor.py` / `CLI.md` sequencing) first, or drop the dependency edge if it no longer applies.

### Outcome Risk Factors
- Broad enumeration across ~12 change sites (hook, doctor, constant home, 4+ doc files, 5+ test files) with Local-depth logic at each; spread-out edits to `cli/doctor.py` and `docs/reference/CLI.md` must be sequenced with ENH-3679 and ENH-3658 to avoid merge conflicts.
- Behavior depends on ENH-3678's `rebuild_needed()` contract (`stale`/`current`/`unknown`, short busy timeout) which is not yet implemented; any contract drift there ripples into the hook branch and doctor check.

## Session Log
- `/ll:confidence-check` - 2026-10-03T16:19:56 - `d0c15f05-2419-498e-9618-a73b38b2c464.jsonl`
- `/ll:confidence-check` - 2026-10-03T03:33:39 - `559f97f2-0fed-4e17-be64-5c3d7a03740e.jsonl`
- `/ll:advise` (Opus, ENH-3678/FEAT-3667 review follow-up: delete ENH-3678 lockstep test) - 2026-10-02
- `/ll:audit-issue-conflicts` - 2026-10-02T19:46:01 - `f99945f8-c860-47a6-88f6-46140ee77213.jsonl`
