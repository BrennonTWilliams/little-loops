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
relates_to:
- ENH-3678
- ENH-3679
- ENH-3699
- ENH-3658
confidence_score: 95
outcome_confidence: 72
score_complexity: 14
score_test_coverage: 22
score_ambiguity: 18
score_change_surface: 18
---

# ENH-3698: Gate the SessionStart rebuild on a store-size threshold with a rebuild-pending notice and doctor check

## Summary

Slice 3678b (split from ENH-3678, 2026-10-02). Above a store-size threshold the SessionStart hook must not auto-spawn `backfill_worker --rebuild`; it reports "rebuild pending" (SessionStart feedback and `ll-doctor`) and the user runs `ll-session rebuild` explicitly. **This must land before any `REBUILD_DERIVE_VERSION` bump**: ENH-3678 only changes *when* a rebuild is needed; without this gate a derive bump still forces a full multi-GB rebuild on every store.

## Current Behavior

After ENH-3678 the hook spawns `--rebuild` whenever `rebuild_needed()` is `stale`, regardless of store size. A ~9.6 GB store held the write lock for minutes on such a rebuild and dropped concurrent `ll-*` telemetry rows. No "pending" notice exists, and `ll-doctor` has no rebuild surface.

## Expected Behavior

- **Size gate.** A module constant (not a config key, to avoid `config-schema.json` / dataclass / `test_config_schema.py` churn; promote to config only if a user asks) of **1 GiB (`2**30` bytes)**, measured as `db_path.stat().st_size` of the **main DB file only**; `-wal` bytes are excluded (transient and checkpoint-dependent). There is no shared size helper today: sites inline `stat().st_size` behind an `exists()` guard, and units disagree (`1024 * 1024` in the retention gate, `1_000_000` in `recompress()`), so state the unit in the constant's name/comment. This constant is distinct from the config-driven `RetentionConfig.min_db_size_mb` (800). **Calibration (Opus review, 2026-10-03):** `rebuild()` is one `BEGIN IMMEDIATE` transaction, so any auto-rebuild longer than the 5 s busy timeout still drops concurrent telemetry rows, even under 1 GiB. 1 GiB is therefore an uncalibrated starting value: time a rebuild on a store near 1 GiB before landing and lower the constant (e.g. 256 MiB) if replay is well over 5 s, or record the accepted drop explicitly. Comment the constant as replay-cost-driven, not "big DB". Main-file `stat()` is lock-free and over-counts, which errs toward pending (safe).
- **Shared helper.** Put the constant and a single `rebuild_disposition(db) -> RebuildDisposition` helper in `session_store/lifecycle.py` (frozen dataclass: `state: RebuildState`, `size_bytes: int | None`, `outcome: Literal["auto", "pending", "none", "unknown_size"]`), exported via `session_store`, reading the constant at call time (so tests can monkeypatch it). It calls `rebuild_needed` first (remote -> `unknown`/`remote`, so remote never reaches `stat()`) and stats only when `stale`. The hook and `ll-doctor` both call it so the decision cannot diverge.
- **Hook decision.** `handle` combines `rebuild_needed()` (ENH-3678) with the size check: `stale` and size <= threshold -> spawn `--rebuild` as today; `stale` and size > threshold -> no `--rebuild`, emit the pending notice; `current` or `unknown` -> neither. "Spawn" here means the `--rebuild` flag only: the incremental backfill worker's `Popen` is outside the check and still runs in every case (ENH-3678 review, 2026-10-03). "Pending" is this combination, not a state of `rebuild_needed`.
- **Unreadable size.** A *missing* DB file (`FileNotFoundError`, i.e. `rebuild_needed` reason `db_missing`) counts as size 0 -> small -> `auto` (ENH-3678's `test_stale_adds_rebuild` uses a nonexistent DB and expects `--rebuild`). Any *other* `OSError` from the size probe is unknown, never zero: outcome `unknown_size` skips auto-rebuild and the actionable pending notice; doctor reports an informational unknown reason without creating/migrating the store. Test a permission/stat failure separately from a missing DB.
- **Pending notice.** One `[little-loops] ...` line appended to `feedback_lines` (joined into `LLHookResult.feedback`; stdout stays the context payload), stating that a rebuild is pending, the command to run (`ll-session rebuild`), and the consequence: derived tables (sessions, tool/skill events, summaries, corrections, search index) are **mixed** until rebuilt — rows derived before the bump keep the old derivation while rows ingested by the still-running incremental worker use the new one; raw events and usage tables stay current. The notice must also **warn that `ll-session rebuild` holds the write lock for the whole replay** (run it with no other ll sessions active), since following it blindly reproduces the incident that motivated ENH-3678. It fires only while the store is `stale` **and** over the size limit, which happens only after a derive bump and is actionable, so **no extra throttle** is added. **Placement:** compute it inside the existing `_backfill_path is not None and not LL_NON_INTERACTIVE` block into a local variable and append it to `feedback_lines` at step 5 (feedback is composed after the spawn block); "pending" means *this hook withheld a rebuild*, so headless/`LL_NON_INTERACTIVE` runs emit nothing — doctor is their surface. The automation-pruning path needs no code: its early return (`session_start.py` ~`:104`) precedes the rebuild block, so no decision or notice runs there.
- **Doctor check.** A report-only "rebuild pending" check following the doctor shape: `_<x>_data() -> dict` (`status`, `severity`, `note`), `_print_<x>_section()`, and an `@register_check` returning `CheckResult` with `severity="informational"` (a `severity == "error"` + `unsupported` result changes exit codes via `_exit_code_for`); the dict is added to the JSON payload and the print list (`cli/doctor.py` ~`:1742`, `:1860`; precedents `_history_db_data` ~`:503`, `_schema_drift_data` ~`:678`). It calls `rebuild_disposition` (read-only via `connect_readonly`, reusing `_REBUILD_NEEDED_TIMEOUT`), resolves the DB path the way `_history_db_data` does, reports an absent DB as informational ("not yet created") without creating it, and reports "not applicable" for a remote target. It reports one wording per outcome (all informational): current; stale + small ("will auto-rebuild on next SessionStart"); stale + over size ("rebuild pending — run `ll-session rebuild`", with the lock-hold warning); `db_missing` ("not yet created"); `unknown`/`unknown_size` (reason code, e.g. `read_error`); remote ("not applicable"). Known residual: hook (`LL_HISTORY_DB`/hook root) and doctor (`Path.cwd()`) path resolution can still diverge; the shared helper unifies semantics, not paths. **It is the only surface for `unknown`** (ENH-3678 review, 2026-10-03): the SessionStart hook does not log or print `rebuild_needed`'s `unknown` reason (the hook module's `logger` has no handler), so the check reports the `unknown` status and its reason code (`read_error`, e.g. a lock timeout; `remote` maps to "not applicable") as informational.
- Remote stores never rebuild from a hook (the guard in `session_start.handle` stays ahead of the size `stat()`).

## Motivation

A multi-GB rebuild from a hook is the incident that motivated ENH-3678. The gate removes the cause for typical bumps; the size threshold removes the blast radius for the unavoidable ones, at the cost of an explicit user action.

## Scope Boundaries

- **In scope**: the size constant and check, the hook decision, the pending notice, the `ll-doctor` check, tests, and the end-user docs for them.
- **Out of scope**: `REBUILD_DERIVE_VERSION`/`rebuild_needed` (ENH-3678), the single-flight lock/cooldown/contention report (ENH-3699), restructuring `rebuild()` (ENH-3666), remote stores.
- **Sequencing:** ENH-3679 (drop-count line), ENH-3658 (`ll-doctor --trim` remote guard) and this issue all edit `cli/doctor.py` and the `ll-doctor` check list/count in `docs/reference/CLI.md`. Land them in sequence, never as parallel branches. ENH-3679 is an **ordering note, not a `blocked_by` edge** (no technical dependency; it only edits the same `doctor.py`/`CLI.md` lines) — if it has not landed, rebase onto it or land this first and let ENH-3679 rebase.

## Integration Map

### Files to Modify

- `scripts/little_loops/hooks/session_start.py` (`handle`, ~`:189-214`) — replace the inline `rebuild_needed(...).status == "stale"` with `rebuild_disposition(...)`; spawn decision, pending notice stashed in a local and appended to `feedback_lines` at step 5. No pruning-path code needed (early return precedes the block).
- `scripts/little_loops/cli/doctor.py` — `_rebuild_pending_data`, `_print_rebuild_pending_section`, `@register_check`, and the JSON payload key in `_print_report`; do **not** spawn the worker from `ll-doctor` (`test_enh3184_spawn_site_guard.py` pins `cli/doctor.py` at `(2, 2)`).
- `scripts/little_loops/session_store/lifecycle.py` + `session_store/__init__.py` — the size constant, `RebuildDisposition`, and `rebuild_disposition()` (decided: lifecycle home; hook and doctor both import it). Also update the stale comment above `REBUILD_DERIVE_VERSION` (~`:1043-1048`, "do NOT bump before ENH-3698").
- `scripts/little_loops/cli/backfill_worker.py` docstring (~`:11-12`) if it references the pre-gate rebuild behavior.

### Tests

- `test_hook_session_start.py::TestSessionStartRebuild` harness (`_setup`, `_FakePopen` argv recorder via `monkeypatch.setattr("little_loops.hooks.session_start.subprocess.Popen", ...)`): stale + small -> spawn; stale + over size (monkeypatch the constant at call time or stub `stat`) -> argv without `--rebuild` and a notice in `feedback_lines`; **size == threshold boundary** (`<=` spawns); missing DB file -> size 0 -> spawns; non-`FileNotFoundError` `OSError` -> `unknown_size`, no spawn, no notice; `current`/`unknown` -> argv without `--rebuild` and no notice (the incremental `Popen` still runs in all cases); WAL bytes do not count.
- `test_enh3678_rebuild_derive_gate.py` — **retarget** `TestSessionStartGate::test_unknown_spawns_incremental_worker_without_rebuild` / `test_exception_in_rebuild_needed_does_not_block_popen` (~`:274`, `:290`): they patch `little_loops.session_store.rebuild_needed`, which the hook no longer calls directly once it goes through `rebuild_disposition` (patch the helper, or `rebuild_needed` as seen from `lifecycle`). Delete only `TestFrozenLegacyPins::test_lockstep_derive_version_not_bumped_before_enh_3698`; keep `test_frozen_legacy_derive_version_literal`; update the `TestDeriveFingerprint` docstring and the `test_digest_matches_snapshot` assert message ("Before ENH-3698 lands you may not bump it…"), which are wrong once the gate exists.
- `TestAutomationPruningStayInTurn::test_pruning_gate_injects_stay_in_turn_instruction` (`result.feedback is None`, ~`:603`) — regression check only; the early return already keeps the notice off this path; `TestAmbientAutomationEnvHermeticity::test_suite_passes_with_ambient_ll_automation` re-runs the whole file under `LL_AUTOMATION=1`.
- `test_remote_hooks.py` — remote stores still never get `--rebuild` and never `stat()` a local path; `TestBackfillWorker::test_a_rebuild_is_refused_with_a_message_and_no_traceback` unchanged.
- Doctor: data function + `@register_check` with `severity="informational"`; absent-DB case (`test_cli_doctor_install_checks.py::TestHistoryDb` style, `_bootstrap_at(db, version)` helper); remote "not applicable" (`test_remote_doctor.py`); add the new function to `test_remote_doctor.py::TestNoTokenLeaks::test_no_doctor_surface_echoes_the_token`; `test_remote_callers_bug3652.py::_CALLER_ALLOWLIST` (`:97`, plus `test_allowlist_has_no_stale_entries`) needs an entry if the doctor function calls `resolve_history_db()`; `test_stray_ll_regression.py::test_ll_doctor_from_subdirectory_creates_no_stray_ll` must keep passing; `test_history_store_chokepoint_gate.py` (open via `connect_readonly`).

### Documentation (end-user shape; `test_docs_audience_gate.py`)

- `docs/reference/CLI.md` — `ll-doctor` "always runs 7 default install-surface checks" count and name list (~`:494`) and `--json` key list (~`:497`); `docs/reference/HOST_COMPATIBILITY.md` (~`:885`) and `docs/codex/usage.md` (~`:173`) install-surface check lists (`test_wiring_guides_and_meta.py` pins only the token `install-surface`).
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — SessionStart section (`:52` table row, `:153`, `:157` "You see": add the `[little-loops] ... rebuild pending` line).
- `docs/guides/HISTORY_SESSION_GUIDE.md` — explain what a pending rebuild means (stale derived tables; raw events and usage stay current) and how to run `ll-session rebuild`.
- `docs/ARCHITECTURE.md` `ll-doctor --json` payload key list (~`:922`) if the doctor surface adds a key.

## Program Design

### Types

- Module constant `REBUILD_AUTO_MAX_BYTES: int = 2**30` in `lifecycle.py` (name indicative; value subject to the replay-duration calibration above) with a comment stating GiB, "main file only, WAL excluded", and "replay-cost-driven".
- `@dataclass(frozen=True) class RebuildDisposition` — `state: RebuildState`, `size_bytes: int | None`, `outcome: Literal["auto", "pending", "none", "unknown_size"]`.

### Signatures

- `rebuild_disposition(db: Path | str = DEFAULT_DB_PATH) -> RebuildDisposition` — `lifecycle.py`; calls `rebuild_needed` first, stats only when `stale`; `FileNotFoundError` -> 0, other `OSError` -> `unknown_size`; never raises.
- `_rebuild_pending_data(db: Path | None) -> dict` — `status`/`severity`/`note`; informational; remote -> not applicable; absent DB -> informational, no creation.

### Call Path

- `handle` (`little_loops.hooks.session_start`) → remote guard → `rebuild_disposition` (wraps `rebuild_needed` from ENH-3678 + size check) → `auto`: spawn `backfill_worker --rebuild`; `pending`: no `--rebuild`, notice stashed then appended to `feedback_lines`; `none`/`unknown_size`: no `--rebuild`, no notice.
- `ll-doctor` → `_rebuild_pending_data` → `rebuild_disposition` → informational report line.

## Implementation Steps

1. ENH-3678 has landed (`rebuild_needed`, `REBUILD_DERIVE_VERSION = "enh3678-v1"`). **Calibrate first:** time a `rebuild()` on a store near 1 GiB and set the constant accordingly (see Calibration). **Delete ENH-3678's ordering lockstep test** (`REBUILD_DERIVE_VERSION == _FROZEN_LEGACY_DERIVE_VERSION`, "do not bump before ENH-3698") in the same change that lands the size gate, so a derive bump becomes possible only once the gate exists. **Keep** ENH-3678's permanent frozen-literal pin test (`_FROZEN_LEGACY_DERIVE_VERSION == "<literal>"`); deleting the lockstep test must not remove it, or bumping both constants would silently mark legacy stores current. **Then check for silent-window drift:** if the fingerprint snapshot's `current_digest != frozen_legacy_digest` (derivation changes were regenerated without a bump while the lockstep test forbade bumping), bump `REBUILD_DERIVE_VERSION` in this change so existing stores re-derive (the size gate now protects large stores); if the digests match, no bump. **Checked 2026-10-03: both are `eae23c057b02` — no bump unless that changes before landing; recheck at landing.** Also update the stale "do NOT bump before ENH-3698" comment in `lifecycle.py`, the `TestDeriveFingerprint` docstring, and the `test_digest_matches_snapshot` assert message. The schema-58 digest can also be recomputed from `git show 9cb4467d6:<file>`. Add the size constant, `RebuildDisposition` and `rebuild_disposition()` (main file only, GiB). `rebuild_needed` already opens with a short busy timeout (ENH-3678); the doctor check reports a lock-timeout `unknown` as informational.
2. Switch `handle` to `rebuild_disposition` for the spawn/pending decision; stash the notice in a local and append at step 5; keep the remote guard first. No pruning-path suppression code (early return).
3. Add the doctor check and payload key; allowlist/`TestNoTokenLeaks` updates.
4. Tests per above; docs per above. Sequence the `cli/doctor.py` and `docs/reference/CLI.md` edits with ENH-3679 and ENH-3658.
5. Run `python -m pytest scripts/tests/`, `ruff check scripts/`, `python -m mypy scripts/little_loops/`.

## Impact

- **Priority**: P3 - not needed to unblock FEAT-3561, but required before any derive-version bump
- **Effort**: Medium - one constant, a hook branch, a doctor check, tests and docs in several files
- **Risk**: Low-Medium - a wrong threshold could suppress a needed rebuild (accepted: derived tables are documented as mixed and the notice is actionable), or leave an auto-rebuild above the 5 s busy timeout still dropping telemetry rows (mitigated by calibrating the constant)
- **Breaking Change**: No

## Acceptance Criteria

- [ ] Above the size threshold (1 GiB, main file only, WAL excluded) a `stale` store spawns no `--rebuild` and surfaces the pending notice via `feedback_lines`; at or below it the hook spawns as before; `current`/`unknown` spawn nothing and print no notice.
- [ ] The notice explains the mixed-derived-tables consequence and the `ll-session rebuild` command, is not throttled, and does not appear on the automation-pruning path (early return; `TestAutomationPruningStayInTurn` still passes) or under `LL_NON_INTERACTIVE`.
- [ ] `ll-doctor` reports "rebuild pending" as an informational check (text and JSON), does not change the exit code, reports "not applicable" for a remote target, creates nothing, and is covered by `TestNoTokenLeaks`.
- [ ] Remote stores never rebuild from a hook and never reach the size `stat()`.
- [ ] A *missing* DB file counts as size 0 (spawns, as in `test_stale_adds_rebuild`); any other failed size probe (non-`FileNotFoundError` `OSError`) does not auto-spawn, treat the store as small, or claim a known pending state; doctor reports informational unknown. A replay duration measured on a store near the threshold is recorded in the implementation review and the constant is set from it (lowered, e.g. to 256 MiB, if replay is well over the 5 s busy timeout) while ENH-3699's single-flight protection remains deferred.
- [ ] Hook and `ll-doctor` both go through `rebuild_disposition()`; the size-==-threshold boundary spawns; ENH-3678's `session_store.rebuild_needed` patch-based hook tests are retargeted to the helper.
- [ ] The notice states the derived tables are *mixed* (not "pre-bump") and warns that `ll-session rebuild` holds the write lock for the whole replay.
- [ ] `ll-doctor` has distinct informational wording for current, stale+small, stale+over-size, `db_missing`, unknown, and remote.
- [ ] Stale ENH-3698 references are updated: `lifecycle.py` comment above `REBUILD_DERIVE_VERSION`, `TestDeriveFingerprint` docstring and assert message, `backfill_worker` docs.
- [ ] No `REBUILD_DERIVE_VERSION` bump lands before this issue (ENH-3678's constant comment names it); ENH-3678's ordering lockstep test is deleted in this issue's change while its permanent frozen-literal pin test stays.
- [ ] At landing, `current_digest` vs `frozen_legacy_digest` in ENH-3678's fingerprint snapshot is checked: unequal -> `REBUILD_DERIVE_VERSION` bumped in this change; equal -> no bump.
- [ ] `ll-doctor`'s rebuild-pending check reports `unknown` (with its reason code) as informational; the hook emits nothing for `unknown`.
- [ ] `stale` + over-size and `unknown` hook cases still spawn the incremental worker without `--rebuild` (test asserts the argv).
- [ ] Docs (`CLI.md` check count/list, `BUILTIN_HOOKS_GUIDE.md`, `HISTORY_SESSION_GUIDE.md`) updated in end-user shape; `python -m pytest scripts/tests/` passes.

## Related

- ENH-3678 (done; provides `rebuild_needed`), ENH-3699 (single-flight lock; deferred), ENH-3679 and ENH-3658 (edit the same `ll-doctor` surfaces; sequence), ENH-3666, FEAT-3561.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Ordering vs ENH-3679: ENH-3679 lands first (matches `blocked_by: ENH-3679`); this issue then rebases onto its `cli/doctor.py` drop-count line and the `ll-doctor` check list/count in `docs/reference/CLI.md`. "Land them in sequence" means ENH-3679 → ENH-3698. *Superseded 2026-10-03 (Opus review):* ENH-3679 is now an ordering note only, not a `blocked_by` edge; see Scope Boundaries.

## Status

**Open** | Created: 2026-10-02 | Priority: P3


## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-10-03 (post-advise amendments; supersedes the 2026-10-02 notes, which predated ENH-3678 landing)_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 72/100 → MODERATE

### Concerns
- Criterion 1 (18/20): `handle` already carries an inline `rebuild_needed(...).status == "stale"` decision (`session_start.py` ~`:189-214`); this replaces it with the new `rebuild_disposition()` helper, so the hook edit extends existing logic and the helper is net-new.
- Criterion 4 (19/20): the size-threshold value is deliberately open until a ~1 GiB `rebuild()` is timed against the 5 s busy timeout (Implementation Step 1 "Calibrate first").
- Criterion 5 (19/20): ENH-3679 is an ordering note only (still open; edits the same `cli/doctor.py` / `CLI.md` lines) — rebase onto it or land first.

### Outcome Risk Factors
- ~12 change sites (lifecycle helper, hook, doctor, 4+ docs, 5+ test files); the `cli/doctor.py` / `CLI.md` edits must be sequenced with ENH-3679 and ENH-3658.
- Ambiguity (18/25): threshold value pending calibration; a wrong value either drops telemetry on sub-threshold rebuilds or defers needed rebuilds.
- Existing ENH-3678 hook tests patch `session_store.rebuild_needed` and must be retargeted once the hook calls `rebuild_disposition()`.

All hard-override gates clear: Program Design, Dependencies (no `blocked_by`), Learning Tests (none required), and no claim/decision/structure gaps.

## Session Log
- `/ll:confidence-check` - 2026-10-03T17:30:10 - `97ad9d47-f49e-462e-89fd-8370be4b7314.jsonl`
- `/ll:advise` (Opus, pre-implementation review of ENH-3698) - 2026-10-03
- `/ll:confidence-check` - 2026-10-03T16:19:56 - `d0c15f05-2419-498e-9618-a73b38b2c464.jsonl`
- `/ll:confidence-check` - 2026-10-03T03:33:39 - `559f97f2-0fed-4e17-be64-5c3d7a03740e.jsonl`
- `/ll:advise` (Opus, ENH-3678/FEAT-3667 review follow-up: delete ENH-3678 lockstep test) - 2026-10-02
- `/ll:audit-issue-conflicts` - 2026-10-02T19:46:01 - `f99945f8-c860-47a6-88f6-46140ee77213.jsonl`
