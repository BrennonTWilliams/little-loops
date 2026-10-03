---
id: ENH-3698
type: ENH
title: Gate the SessionStart rebuild on a store-size threshold with a rebuild-pending
  notice and doctor check
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-10-02'
captured_at: '2026-10-02T17:56:06Z'
completed_at: '2026-10-03T19:22:03Z'
relates_to:
- ENH-3678
- ENH-3679
- ENH-3699
- ENH-3658
- BUG-3715
confidence_score: 95
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# ENH-3698: Gate the SessionStart rebuild on a store-size threshold with a rebuild-pending notice and doctor check

## Summary

Slice 3678b, split from ENH-3678 on 2026-10-02. Suppress automatic SessionStart replay above a calibrated size threshold, report the deferred rebuild through hook feedback and `ll-doctor`, and recheck eligibility **after ingestion, immediately before replay** in the detached worker. This is a guard-only change: do not bump `REBUILD_DERIVE_VERSION` here.

The gate must land before a future derive-version bump. BUG-3715 (retention-summary preservation) is **done** (`3ea2ccaf0`; `rebuild()` now preserves `kind = 'retention'` summary nodes), so it is no longer a prerequisite or an interim caveat.

## Current Behavior

- `hooks/session_start.py::handle` appends `--rebuild` whenever `rebuild_needed()` returns `stale`, regardless of size. A roughly 9.6 GB store held the write lock for minutes and dropped concurrent telemetry.
- `cli/backfill_worker.py::main` delegates to `backfill_incremental(..., also_rebuild=True)`, which ingests raw events **before** calling `rebuild()`. Even a missing or small database can become large between the hook's decision and replay.
- `rebuild_needed()` resolves default-shaped arguments through environment/config overrides. Statting the original argument afterward can measure a different file, or treat a missing default file as size 0 while the real configured store is large.
- Committed database growth can reside in the WAL. Main-file size alone is not a conservative bound on replay cost.
- ENH-3679 has landed: CLI telemetry lock waits are **250 ms**, while other writers retain 5 s. A replay shorter than 5 s can still drop CLI events; the gate reduces exposure and does not guarantee a lock-time bound.
- `rebuild(db, config=None)` clears leaf/condensed summaries without regenerating them (retention summaries are preserved since BUG-3715). Manual `ll-session rebuild` loads the project's raw JSON config and can run blocking LLM compaction inside the write transaction.

## Expected Behavior

### Shared decision and size metric

Put `REBUILD_AUTO_MAX_BYTES`, a frozen `RebuildDisposition`, and `rebuild_disposition()` in `session_store/lifecycle.py`; export them through `session_store/__init__.py`.

- Resolve one `HistoryTarget`. Pass that exact typed target to `rebuild_needed()` and use the same `LocalTarget.path` for all size probes. Extend `rebuild_needed()`'s type annotation to accept `HistoryTarget`; its resolver already accepts typed targets at runtime. Never stat the unresolved caller argument.
- Remote targets return `unknown`/`remote` without a local stat or remote query. Current and unknown states do not require size probes.
- For a stale local store, measure **main DB bytes + WAL bytes** using filesystem stats. Missing WAL counts as 0; ignore `-shm`. This is a conservative proxy that can overcount overwritten WAL frames or allocated free pages. No checkpoint, SQL row count, or new config key.
- A known `db_missing` state returns size 0 and `auto`. A `FileNotFoundError` during a later main-file probe also counts as 0; still account for any WAL found. Other `OSError` values from either probe produce `unknown_size`, with `size_bytes=None`, rather than treating unreadable storage as small.
- Read the constant at call time so tests can monkeypatch it. **1 GiB (`2**30`) is only a provisional ceiling, not the required shipped value.** Select the actual constant from the calibration below and state the byte unit and main-plus-WAL metric in its comment.
- The helper is report-only, uses the existing read-only metadata probe and `_REBUILD_NEEDED_TIMEOUT`, creates/migrates nothing, and fails softly. Resolution/read failures become `unknown`/`read_error`; size-probe failures become `unknown_size`. Do not include arbitrary exception text or credentials in diagnostic output.

| State / size | Disposition | Size probe |
| --- | --- | --- |
| `current` | `none` | None |
| `unknown` (including remote) | `none` | None |
| `stale`, `db_missing` | `auto`, size 0 | None |
| `stale`, size <= calibrated threshold | `auto` | Resolved main + WAL |
| `stale`, size > calibrated threshold | `pending` | Resolved main + WAL |
| `stale`, other stat failure | `unknown_size` | Failed; size unknown |

### Hook and worker protocol

- Inside the existing `_backfill_path is not None and not LL_NON_INTERACTIVE` block, the hook calls `rebuild_disposition()`. Keep the remote guard ahead of the decision.
- `auto` adds a new **hook-only `--auto-rebuild`** flag. `pending` adds no replay flag and stashes a pending notice. `none` and `unknown_size` add no replay flag and no pending notice.
- The incremental worker's `Popen` remains outside the decision: pending/current/unknown stores still get ingestion when the existing source and interactivity conditions allow it.
- The worker's `--auto-rebuild` path first calls `backfill_incremental(..., also_rebuild=False)`. **After that commits**, call the shared helper again and invoke `rebuild(db, config=None)` only if its outcome is still `auto`. A backlog that grows the store over the threshold must not cause replay. A store now current or unreadable also skips replay. No new persistent pending marker; doctor and a later eligible SessionStart report deferral.
- Existing explicit `--rebuild` remains ungated. Reject `--rebuild` combined with `--auto-rebuild` before ingestion using the worker's existing clean-message/exit-1 style. Do not change manual CLI/backfill/refresh semantics.
- Only a hook-preflight `auto` request can enter the worker's automatic path. A current store must not gain an automatic replay because new data was ingested; `rebuild_needed()` checks version metadata, not raw-row freshness.
- No single-flight lock or atomic size/replay guarantee is added. Concurrent workers can both pass the final check; data can grow after it. ENH-3699 owns coordination. Raw ingestion and usage-only replay can also hold long write locks independently of this gate.

### Pending notice and safe manual guidance

Append one `[little-loops] ...` line to `feedback_lines` at feedback composition (step 5), leaving stdout as the context payload. Initialize the stashed notice before the guarded block so a failed spawn cannot lose an already-established pending result.

- Explain that derived tables (sessions, tool/skill events, corrections, summaries, search) remain out of date. `derive_mismatch` means historical and live-derived rows may be **mixed**; `no_stamp`/`legacy_below_floor` means tables may be **incomplete**, not necessarily empty. Incremental backfill only ingests raw events; it does not refresh all these tables. Raw ingestion and usage derivation continue independently.
- Name `ll-session rebuild` as the explicit, deferrable recovery path. Warn that replay holds the write lock throughout; run it with no other ll sessions active.
- BUG-3715 has landed: retention summaries survive `rebuild()`, so **no irreversible-loss warning is required**. Do disclose that leaf/condensed summaries are cleared and only regenerated when history compaction is enabled for the manual command. Present rebuilding as optional/deferrable.
- When the raw project JSON that manual rebuild loads enables `history.compaction.enabled`, also disclose LLM summarization inside the transaction. The manual command currently does not merge `.ll/ll.local.md`; avoid deciding this warning solely from the hook's merged config or doctor's merged `BRConfig`. A failed config read must not break the hook/check; use conservative wording when the setting cannot be established.
- No throttle, force/yes flag, or new confirmation flow. The notice appears whenever this interactive hook actually withholds replay for a known over-threshold stale store. It does not appear under `LL_NON_INTERACTIVE`, when no source is found, or on the automation-pruning early return. Doctor is the headless diagnostic surface.

### Doctor check

Add `_rebuild_pending_data() -> dict`, `_print_rebuild_pending_section()`, and a no-arg `@register_check` returning `[CheckResult(name="rebuild_pending", ..., severity="informational")]` (`register_check` takes `Callable[[], list[CheckResult]]`). Add the `rebuild_pending` key to `_print_report` and the section to the text print list. Doctor never spawns a worker.

The data function resolves through the target-aware shared helper, rather than introducing another `resolve_history_db()` caller or allowlist exception. Its data includes `status`, `severity`, `note`, `state` (rebuild status), `reason` (rebuild reason), `size_bytes`, `threshold_bytes`, and `outcome`. `unknown_size` is identified by `outcome`; preserve the underlying stale metadata reason separately. Machine consumers must not need to parse the prose notice.

| Result | Doctor status | Informational wording |
| --- | --- | --- |
| Current | `full` | Derivation current |
| Stale + `auto` | `partial` | Eligible for automatic rebuild on an interactive SessionStart with a source; size is rechecked after ingestion |
| Stale + `pending` | `partial` | Rebuild pending; explicit recovery command with the same lock and applicable compaction caveats |
| `db_missing` | `unsupported` | Not yet created; create nothing |
| `unknown` / `unknown_size` | `unknown` | Could not establish eligibility; include the safe reason code / outcome |
| Remote | `unsupported` | Not applicable to a remote store |

Every row has informational severity and must leave doctor exit codes unchanged. Remote handling wins over the generic unknown case. Hook root-versus-cwd resolution is an existing separate limitation; this issue guarantees that each decision reads metadata and sizes the **same resolved target**.

### Calibration

Before choosing the shipped constant, time `rebuild(db, config=None)` on representative **copies or synthetic stores**, including a candidate near the provisional 1 GiB ceiling and samples near the resulting threshold. Never replay the live project store for calibration.

Record main/WAL bytes at decision time, raw-row count and representative event mix, replay duration/lock-hold time, and the chosen constant with margin. Seconds per row can help explain the result, but compression and repeated replay passes mean one store's bytes-per-row ratio is not a universal conversion.

Use 5 s as the original operational upper target for automatic replay; lower the threshold if representative replay exceeds it. **CLI telemetry already times out at 250 ms**, so even a replay comfortably below 5 s can drop concurrent CLI events; those drops are counted by ENH-3679. State this accepted residual explicitly instead of claiming the calibration prevents all drops. The gate is a heuristic for limiting expensive automatic replay, not a duration guarantee. Calibration is implementation evidence, not a new timing-sensitive CI test.

## Scope Boundaries

- **In scope:** the shared size decision, hook notice, worker automatic-only post-ingest gate, doctor data/text/registry surfaces, tests, documentation, and preserving the derive-bump safety pin.
- **Out of scope:** changing derivation semantics/version, fixing summary preservation (BUG-3715), transaction batching/LLM compaction restructuring (ENH-3666), single-flight/cooldown/contention reporting (ENH-3699), remote rebuilding, and gating explicit rebuild paths.
- `_USAGE_DERIVE_VERSION` changes can replay all raw rows through the usage path and bypass this gate; describe that limitation without expanding this issue.
- ENH-3678 and ENH-3679 are **done**. ENH-3658 remains a shared-surface sequencing consideration. Rebase onto the current doctor implementation; no `blocked_by` ordering edge is needed merely because files overlap.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/lifecycle.py` — constant, frozen disposition/helper, target-aware `rebuild_needed` annotation, and outdated derive-version / automatic-backfill comments. Metadata and size probes must share the resolved target.
- `scripts/little_loops/session_store/__init__.py` — export the new API.
- `scripts/little_loops/hooks/session_start.py` — preflight decision, `--auto-rebuild`, and feedback notice appended after the guarded spawn block.
- `scripts/little_loops/cli/backfill_worker.py` — parse the automatic-only flag, ingest then recheck/replay, flag conflict handling, and docstring. This is a behavior change, not only a documentation edit.
- `scripts/little_loops/cli/doctor.py` — data helper, section, informational check, JSON key. Do not add a subprocess spawn (`test_enh3184_spawn_site_guard.py` pins doctor at `(2, 2)`).
- `scripts/tests/test_enh3678_rebuild_derive_gate.py` — retarget hook tests, flag expectations, temporal derive pin and stale messages.

### Tests

- Add helper tests in `scripts/tests/test_enh3698_rebuild_size_gate.py` (new file): size below/equal/above threshold; configured path differing from a missing or tiny default; `LL_HISTORY_DB`; deliberate explicit path; typed target; main-small/WAL-large; missing WAL; missing DB and disappearance race; permission/stat failure on either file; current/unknown/remote short-circuit without a stat; no store creation/migration. Patch the constant at call time, not a captured default value. Use tiny fixtures or mocked stats, not the live store or a GiB fixture.
- Extend the actual hook harness in `test_enh3678_rebuild_derive_gate.py::TestSessionStartGate` (`_setup`/`_FakePopen`): stale + small adds `--auto-rebuild`; pending/current/unknown/stat-error still start incremental ingestion without a replay flag. Pending feedback survives a simulated `Popen` failure. Check reason-specific wording, stdout separation, `LL_NON_INTERACTIVE`, no-source suppression, raw-config versus local-override compaction warning, and the retention-loss caveat.
- Retarget tests that patch `session_store.rebuild_needed` to the helper or lifecycle import seam. Check `TestAutomationPruningStayInTurn` and `TestAmbientAutomationEnvHermeticity` in `test_hook_session_start.py`; its early return needs no new pruning logic.
- Add worker tests in `scripts/tests/test_backfill_worker_auto_rebuild.py` (new file): ingest commits before the final decision; missing/small DB becomes over-limit after a backlog and skips replay; still-small stale DB replays once with `config=None`; now-current/unknown skips; a preflight-current hook supplies no auto flag and cannot introduce replay; plain incremental mode never replays; explicit `--rebuild` remains ungated; conflicting flags fail cleanly before ingestion. Verify actual call order, not just the hook argv.
- Keep `test_remote_hooks.py` remote refusal/no-traceback checks; add expectations for absence of `--auto-rebuild` and ensure automatic worker rechecks cannot replay or stat a remote target. Existing Stop usage-trigger behavior (`test_backfill_worker_usage_trigger.py`) stays unchanged.
- Doctor: all table rows above; text/JSON/registered-result parity, informational exit behavior, no creation or migration, resolved configured/env paths, remote handling and token redaction. Include the new data/text/check surfaces in `test_remote_doctor.py::TestNoTokenLeaks`.
- Keep `test_stray_ll_regression.py`, `test_history_store_chokepoint_gate.py`, `test_remote_callers_bug3652.py`, and `test_enh3184_spawn_site_guard.py` passing. The target-aware doctor design needs no new `resolve_history_db` allowlist entry.
- Delete `TestFrozenLegacyPins::test_lockstep_derive_version_not_bumped_before_enh_3698` (its docstring says ENH-3698 deletes it; BUG-3715 is done, so no re-anchor is needed). Keep the permanent frozen-literal pin (`test_frozen_legacy_derive_version_literal`) and frozen legacy digest unchanged. Update the `TestDeriveFingerprint` docstring/assert messages (`test_enh3678_rebuild_derive_gate.py` ~lines 313–355) and the `lifecycle.py` comment near `REBUILD_DERIVE_VERSION` ("bump before ENH-3698 lands") so they no longer reference the pending gate. Landing the gate permits, but does not perform, a future bump.

### Documentation

- `docs/reference/CLI.md` — add the doctor section/key and recount the **actual registry**, not the stale “7” plus one. Currently 10 default registered checks exist; this adds one. Include the warning/recovery guidance and automatic worker semantics where relevant.
- `docs/reference/HOST_COMPATIBILITY.md`, `docs/codex/usage.md` — align install-surface lists.
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — SessionStart size deferral and feedback example.
- `docs/guides/HISTORY_SESSION_GUIDE.md` — stale derivation, continued independent ingestion/usage, optional manual recovery and its lock/compaction caveats; clarify main-plus-WAL sizing.
- `docs/ARCHITECTURE.md` — doctor JSON key list if enumerated.
- Keep end-user prose compliant with `test_docs_audience_gate.py`; do not expose internal issue IDs as recovery instructions.

## Program Design

### Types

- `REBUILD_AUTO_MAX_BYTES: int` — calibrated value in bytes; provisional ceiling `2**30`; no config/schema/dataclass churn for settings.
- `@dataclass(frozen=True) class RebuildDisposition` — `state: RebuildState`, `size_bytes: int | None`, `outcome: Literal["auto", "pending", "none", "unknown_size"]`.

### Signatures

- `rebuild_disposition(db: Path | str | HistoryTarget = DEFAULT_DB_PATH) -> RebuildDisposition` — resolve once; metadata first; stat the resolved local main and WAL only if stale; fail softly.
- `rebuild_needed(db: Path | str | HistoryTarget = DEFAULT_DB_PATH) -> RebuildState` — annotation update for the existing typed-target resolver behavior; no new staleness condition.
- `_rebuild_pending_data() -> dict` — no-arg helper for all three doctor surfaces; target-aware resolution through the shared decision.

### Call Path

- `hooks/session_start.py::handle` → `rebuild_disposition` → `rebuild_needed` → eligible `cli/backfill_worker.py::main` with `--auto-rebuild` → `backfill_incremental(also_rebuild=False)` / commit → `rebuild_disposition` → eligible `rebuild(config=None)`.
- Doctor data/text/check surfaces → `_rebuild_pending_data` → `rebuild_disposition` → informational result; no worker spawn.
- Explicit `--rebuild` → existing `backfill_incremental(also_rebuild=True)` → `rebuild`; no size gate.

## Implementation Steps

1. Recheck the derive fingerprint before work/landing. Current and frozen digests both start `eae23c057b02` (confirmed 2026-10-03). Keep the version unchanged. If drift appears, investigate and resolve it; do **not** automatically bump in this change or bypass BUG-3715.
2. Calibrate on offline copies/synthetic stores and record the chosen constant and remaining 250 ms telemetry-drop risk. Add the helper and its resolved-target/WAL tests.
3. Switch the hook to the automatic-only protocol and feedback. Implement and test the worker's post-ingest recheck. Preserve incremental ingestion, explicit rebuilds, remote handling and Stop usage-trigger behavior.
4. Add the doctor surfaces and deterministic status/JSON mapping, then docs and all relevant tests. Rebase doctor changes onto landed ENH-3679; sequence overlapping work with ENH-3658.
5. Delete the temporal derive-version pin, retaining the frozen literal/digest pins. Update outdated comments/messages. No derive bump in this change.
6. Run `python -m pytest scripts/tests/`, `ruff check scripts/`, and `python -m mypy scripts/little_loops/`.

## Impact

- **Priority:** P3 — mitigation required before future derive-version bumps.
- **Effort:** Medium — lifecycle helper, hook/worker protocol, doctor surface, tests and documentation.
- **Risk:** Medium — stale derived data is explicitly deferred; sizing and calibration are heuristics; raw ingestion, usage replay and concurrent workers can still contend. The gate suppresses existing replay and must add no new trigger.
- **Breaking Change:** No for explicit rebuild paths; small automatic rebuilds remain subject to the final eligibility check.

## Acceptance Criteria

- [ ] Hook, automatic worker, and doctor use the same `rebuild_disposition()` semantics; metadata and size probes operate on the same resolved target, including configured/env overrides.
- [ ] Size means main plus WAL, with missing WAL = 0 and no `-shm`/checkpoint/row-count probe. Below/equal threshold is eligible; above threshold is pending; unreadable size is unknown, never small.
- [ ] Missing DB is size 0 without creation; current/unknown/remote skip stats. Remote stores never auto-replay.
- [ ] The hook adds `--auto-rebuild` only for preflight `auto`; pending/current/unknown still spawn incremental ingestion when the existing source/interactivity conditions permit it.
- [ ] The worker ingests and commits before rechecking automatic eligibility. A missing/small store that grows over the limit skips replay; still-small stale stores replay; now-current/unknown stores skip. A preflight-current store cannot acquire a new automatic trigger from ingestion.
- [ ] Explicit `--rebuild` stays ungated; simultaneous manual/auto flags fail cleanly before ingestion; Stop usage-trigger behavior is unchanged.
- [ ] Pending feedback uses reason-specific mixed/incomplete wording, optional manual recovery, whole-replay lock warning, and the compaction/LLM warning based on the config the manual command actually loads (no retention-loss warning; BUG-3715 is done).
- [ ] Pending feedback survives a spawn failure and appears only on the eligible interactive hook path; stdout, no-source/headless suppression and automation-pruning behavior remain correct. No new throttle or confirmation flow.
- [ ] Doctor text, JSON and registered checks agree on the specified status/outcome/reason/size/threshold data. Every result is informational; exit behavior stays unchanged; missing/remote/unknown are distinct; no creation/migration/spawn or token leakage.
- [ ] Replay calibration using `config=None` on offline stores is recorded with size, row count/event mix, duration and chosen constant. The shipped value is calibrated, not mandated as 1 GiB; remaining drops past 250 ms and concurrency/ingestion limitations are explicit.
- [ ] No `REBUILD_DERIVE_VERSION` bump lands here. Fingerprint drift is checked and investigated; the old ENH-3698 temporal pin is deleted, while permanent frozen-literal/digest pins stay intact.
- [ ] End-user docs and actual doctor check/key lists are updated; `python -m pytest scripts/tests/`, lint and type checks pass.

## Related

ENH-3678 (done; metadata decision), ENH-3679 (done; 250 ms CLI waits/drop counting), ENH-3699 (deferred coordination), ENH-3658 (overlapping doctor work), ENH-3666 (transaction restructuring), BUG-3715 (done; retention-summary preservation), FEAT-3561.

## Pre-Implementation Review — 2026-10-03

- Temporary configured-path fixture: `rebuild_needed(root/.ll/history.db)` read the configured 573,440-byte store and returned `stale/no_stamp`, while the argument file was absent. This proves an unresolved-argument stat can incorrectly classify the actual store as size 0.
- Temporary WAL fixture: committed 2 MiB of payload with autocheckpoint disabled while keeping the connection open; main file = 4,096 bytes, WAL = 2,125,952 bytes. Main-only sizing can undercount committed data.
- Code inspection confirmed ingestion precedes replay, staleness is metadata-based, CLI telemetry now uses 250 ms, and the default doctor registry contains 10 checks.
- `/ll:advise` with `claude-opus-5-5` endorsed resolved-target sizing, WAL inclusion, the automatic-only post-ingest recheck, and contract cleanup (confidence 0.80). It favored a documented 250 ms residual over a zero-drop requirement; this review adopts that distinction while retaining offline calibration.
- Follow-up Opus consult withdrew a proposed BUG-3715 implementation blocker after considering the already-existing auto-replay path (confidence 0.82). Adopted conditions: no new trigger/bump, re-anchor the mechanical bump pin to BUG-3715, and disclose the manual command's retention-loss risk. No summary-table guard or new dependency edge is added.
- Existing baseline: `python -m pytest scripts/tests/test_enh3678_rebuild_derive_gate.py -q` → **42 passed**. This verifies the current metadata/fingerprint behavior; it does not validate the proposed unimplemented gate. Threshold calibration remains implementation work.

- **2026-10-03 (`/ll:ready-issue`)**: BUG-3715 landed in `3ea2ccaf0` (verified: `rebuild()` preserves `kind = 'retention'`). Superseded the Opus-adopted conditions above that depended on it — the interim retention-loss notice and the BUG-3715 re-anchor of the derive pin are dropped; the pin is deleted per its own docstring.

## Resolution

- **Action**: improve
- **Completed**: 2026-10-03
- **Status**: Completed

### Changes Made
- `session_store/lifecycle.py`: `REBUILD_AUTO_MAX_BYTES` (64 MiB), frozen `RebuildDisposition`, `rebuild_disposition()` (one resolved target, main+WAL filesystem size), `rebuild_compaction_enabled()`, `rebuild_pending_notice()`; `rebuild_needed` accepts a `HistoryTarget`; stale "bump before ENH-3698" comment updated. `REBUILD_DERIVE_VERSION` unchanged.
- `session_store/__init__.py`: exports.
- `hooks/session_start.py`: `--auto-rebuild` only for preflight `auto`; `pending` stashes a notice appended to feedback (initialized before the guarded block, survives a spawn failure).
- `cli/backfill_worker.py`: `--auto-rebuild` ingests, then rechecks `rebuild_disposition` and replays `rebuild(db, config=None)` only if still `auto`; conflicts with `--rebuild`/`--usage-trigger` and is rejected before ingestion.
- `cli/doctor.py`: `_rebuild_pending_data`, `_print_rebuild_pending_section`, informational `rebuild_pending` check, `rebuild_pending` JSON key.
- Tests: new `test_enh3698_rebuild_size_gate.py`, `test_backfill_worker_auto_rebuild.py`; hook tests added/retargeted in `test_enh3678_rebuild_derive_gate.py` and `test_hook_session_start.py`; temporal derive-version pin deleted (frozen literal/digest pins kept).
- Docs: CLI.md (11 registered checks, JSON key), HOST_COMPATIBILITY.md, codex/usage.md, ARCHITECTURE.md, BUILTIN_HOOKS_GUIDE.md, HISTORY_SESSION_GUIDE.md.

### Calibration (offline synthetic Claude stores, `rebuild(copy, config=None)`)
| raw rows | main+WAL | replay |
| --- | --- | --- |
| 3,000 | 3.6 MiB | 0.14 s |
| 60,000 | 60.4 MiB | 2.95 s |
| 180,000 | 180.5 MiB | 8.87 s |
| 450,000 | 450.8 MiB | 22.40 s |

Event mix per turn: 1 user message, 1 assistant message with text + Read `tool_use` and usage, 1 `tool_result`. About 1 KiB and 50 µs per raw row; replay scales linearly. 5 s ≈ 100 MiB on this mix, so the shipped ceiling is **64 MiB** (~1.5x margin; real stores differ in compression and event mix). Residual accepted: CLI telemetry waits 250 ms (ENH-3679), so even a replay inside the ceiling can drop concurrent CLI events; the gate does not bound lock time, and concurrent workers/raw ingestion can still contend (ENH-3699).

### Verification Results
- Tests: PASS for all touched suites (full run: 27785 passed; 2 failures + 8 errors unrelated to this change — `test_verify_evidence::TestRepoGate` on BUG-3696/BUG-3702 issue prose, flaky `test_kills_grandchild_in_same_group` (passes alone), live-endpoint `test_libsql_integration`)
- Lint: PASS
- Types: PASS
- Derive fingerprint: unchanged, no bump

## Status

**Open** | Created: 2026-10-02 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-10-03 (re-scored against the post-review design: resolved-target sizing, main+WAL, worker post-ingest recheck)_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Concerns
- Calibration is still outstanding: `REBUILD_AUTO_MAX_BYTES` is a provisional 1 GiB until offline replay timing picks the shipped value (Ambiguity 18/25). Not a blocker, but the constant, the recorded evidence, and the accepted 250 ms telemetry-drop residual must land with the change.
- The doctor wording says the no-arg `@register_check` function returns `CheckResult(name="rebuild_pending", ...)`, but `register_check` (`cli/doctor.py:94`) takes `Callable[[], list[CheckResult]]`. Return `[CheckResult(...)]`.
- Hook-to-worker protocol change (new `--auto-rebuild` flag, ingest-then-recheck ordering) spans lifecycle, hook, worker, and doctor; keep the call-order test (ingest commits before the final disposition check) as the first test written.

_The earlier note's staleness warning (open ENH-3679, main-only sizing, hook-only gate, deleting the bump pin) is resolved by this re-score; those scores no longer stand._

## Session Log
- `/ll:manage-issue` - 2026-10-03T19:21:52 - `26f917ae-d375-4323-b7dd-b174ab5bae3a.jsonl`
- `/ll:ready-issue` - 2026-10-03T19:03:51 - `18d3eb94-1416-4336-907d-3475d4b1e8f3.jsonl`
- `/ll:confidence-check` - 2026-10-03T18:44:58 - `b1c5eb16-ae1a-4e20-9a59-b0f92f518844.jsonl`
- `/ll:advise` (Opus, resolved-target/WAL sizing and post-ingest gate critique; follow-up on BUG-3715 sequencing) - 2026-10-03
- `/ll:confidence-check` - 2026-10-03T17:30:10 - `97ad9d47-f49e-462e-89fd-8370be4b7314.jsonl`
- `/ll:advise` (Opus, second pre-implementation review: compaction-in-txn, summary_nodes wipe, notice wording) - 2026-10-03
- `/ll:advise` (Opus, pre-implementation review of ENH-3698) - 2026-10-03
- `/ll:confidence-check` - 2026-10-03T16:19:56 - `d0c15f05-2419-498e-9618-a73b38b2c464.jsonl`
- `/ll:confidence-check` - 2026-10-03T03:33:39 - `559f97f2-0fed-4e17-be64-5c3d7a03740e.jsonl`
- `/ll:advise` (Opus, ENH-3678/FEAT-3667 review follow-up: delete ENH-3678 lockstep test) - 2026-10-02
- `/ll:audit-issue-conflicts` - 2026-10-02T19:46:01 - `f99945f8-c860-47a6-88f6-46140ee77213.jsonl`
