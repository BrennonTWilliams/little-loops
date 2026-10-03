---
id: ENH-3706
type: ENH
title: scratch-cleanup.sh never sweeps no-suffix files so .loops/tmp/scratch still
  grows unbounded
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-03'
captured_at: '2026-10-03T16:28:16Z'
relates_to:
- BUG-3705
- BUG-3707
- BUG-2525
- ENH-3709
confidence_score: 100
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-3706: scratch-cleanup.sh never sweeps no-suffix files so .loops/tmp/scratch still grows unbounded

## Summary

At review time (2026-10-03), 2,766 of the 2,822 files (109 MB) in `.loops/tmp/scratch` had no `-<pid>` suffix. `hooks/scripts/scratch-cleanup.sh` skips them unconditionally under the BUG-2525 preservation contract, so they accumulate even after BUG-3705 (done, `87d50cb02`) improved the dead-pid sweep.

Add a **universal 7-day mtime retention tier** for regular files directly in scratch, regardless of name or apparent PID liveness. Also fix the existing pass's newline-filename wrong-file deletion and check its deadline before every record is processed. Cleanup remains best effort: normal completion exits 0, but the host may terminate a slow run at its 5s timeout, leaving already-completed deletions in place for the next invocation to continue.

This deliberately replaces BUG-2525's unconditional preservation of user-written files with finite retention. Modification time measures writes, not reads or ownership; old notes still being read can be removed.

## Motivation

- The growing file count makes every SessionStart enumeration more expensive. Measured no-suffix backlog by age (2026-10-03): >1d 2,745, >3d 2,743, >7d 2,489, >14d 2,423, >30d 1,820. Seven-day retention makes roughly 90% of that backlog eligible for removal.
- A filename PID is not proof of writer ownership. `scratch-pad-redirect.sh` embeds the exiting hook's own `$$`; BUG-3707 is cancelled with `closed_reason: wont_fix`. The eight pid-shaped files older than 24h inspected on 2026-10-03 all matched unrelated live macOS daemon PIDs. A no-suffix-only cap would leave those files behind indefinitely.
- No-suffix files come from one-shot model redirects and skill-documented fixed names, including `init-verify-{test,lint}.txt` and `test-results.txt`. Rewriting a fixed name refreshes its mtime; reading it does not. Their observed producers support an inactivity heuristic, not a guarantee that every old file is unused.
- Review probes exposed two gaps in the existing tests: a newline-containing old filename deleted a separate fresh file; a delayed, keep-only enumeration ran 6.44s without checking the 3s deadline. Both need explicit regression coverage.

## Current Behavior

The hook finds direct regular files older than 24h with `find "$SCRATCH_DIR" -maxdepth 1 -type f -mmin +1440`, reads newline-separated paths, parses a trailing numeric PID before the final extension, skips live PIDs, and deletes dead-PID files in batches of 500. Names without that suffix are skipped regardless of age.

The newline protocol is unsafe: an old file named `old\nfresh-2147483647.txt` was interpreted as multiple records and caused deletion of a separate fresh `fresh-2147483647.txt`, while the original old file remained. This bypasses the fresh-file age guard.

The `$SECONDS` deadline is checked only after a full deletion batch. Skipped records never check it, and a blocked `find`/read or deletion cannot be interrupted by that check. The existing implementation therefore does not guarantee completion within the configured 5s timeout.

## Expected Behavior

- On a successful sweep, direct regular files with mtime older than seven days are removed regardless of filename or apparent PID liveness (`MAX_AGE_MINUTES=10080`). Dotfiles and names containing newlines are eligible.
- Below seven days, retain the existing policy: no-suffix files are kept; pid-shaped files older than 24h are deleted only when `kill -0` does not succeed; younger pid-shaped files are kept.
- The existing pass processes complete path records so an old filename cannot select another, younger file. Its 3s deadline is checked before processing every record, including records that will be skipped. It flushes any pending delete batch after a cooperative stop.
- Subdirectories and symlinks are excluded. A symlinked scratch-directory path must not cause deletion inside its target.
- Cleanup is best effort and restartable. Normal and cooperative-stop paths exit 0; a host timeout or external termination has no exit-0 guarantee. Completed deletions persist, surviving files remain independently usable, and a later run continues without a cleanup checkpoint.

## Proposed Solution

_Revised after the 2026-10-03 review and `/ll:advise` Opus critique (confidence 0.80). The advisor favored the native deletion pass with an honest best-effort timeout contract; the reproduced wrong-file deletion is a required fix._

1. **Keep the hardcoded universal seven-day mtime policy.** Add `MAX_AGE_MINUTES=10080` next to `MIN_AGE_MINUTES=1440`. No new config key or environment override.
2. **Run pass 0 before the dead-PID pass:** `find "$SCRATCH_DIR" -maxdepth 1 -type f -mmin +"$MAX_AGE_MINUTES" -delete 2>/dev/null || true`. This performs deletion inside `find`, avoids per-file subprocesses, and tolerates concurrent disappearance. Preserve the default no-follow behavior; do not add a trailing slash to the scratch path or enable link following.
3. **Fix pass 1's record protocol without changing its PID parsing policy.** Add `-print0` to its `find`, read with `while IFS= read -r -d '' f`, and queue the complete enumerated path (`dead[n]="$f"`). Keep the builtin PID extraction and existing parser edge-case tests. No `scratch_pid_of` refactor is needed.
4. **Check pass 1's deadline on every record.** Keep `start=$SECONDS` before pass 0, and check elapsed time at the top of the pass-1 loop before parsing or any `continue`. The pending batch is still flushed after the loop. If pass 0 consumed the cooperative budget, pass 1 can stop immediately. This bounds further pass-1 processing once a record is available; it does not interrupt pass 0, a blocked read, or a filesystem operation.
5. **State the timeout tradeoff explicitly.** Keep the efficient native pass instead of adding a watchdog. A large backlog or slow filesystem can exceed the host's unchanged 5s timeout and produce a timeout notice. Do not describe this as guaranteed completion or require exit 0 after host termination. Test safe rerun after an interrupted sweep separately from cooperative-stop behavior.
6. **Retain `kill -0` for the 24h tier.** Treat it as a compatibility check against the filename PID, not proof of the actual writer's liveness. It does not exempt files from the universal seven-day tier. Removing it or changing writer naming remains out of scope.
7. **Update the complete retention contract and misleading ownership comments.** Replace unconditional user-file preservation and writer/PID-liveness guarantees with the two tiers and their limits. Keep `rmdir` of an empty scratch root; producers must recreate the directory with `mkdir -p` before redirecting.

**Retention limits to document in the script and guide:**
- Reading a file does not refresh its mtime. Keep durable progress/resume notes outside scratch, or explicitly refresh retained scratch notes; later reads alone do not preserve them.
- Files moved or copied in with an already-old mtime, including preserved-mtime copies or archive extraction, may be eligible immediately.
- The partial-progress scratch notes referenced by `issue_manager.py` and `parallel/worker_pool.py` may be absent on a delayed resume. Neither the 24h tier nor the seven-day cap promises durable resume storage.
- A matching live PID does not exempt an idle file older than seven days, even if that PID belongs to a real reader or writer.
- Selection and deletion are not atomic with concurrent rewrites. An old file refreshed or replaced after `find` examines it can still be removed. Age is an inactivity heuristic; ENOENT tolerance is not a reader/writer safety guarantee.
- Failed or interrupted runs can leave eligible files behind until a subsequent sweep. Seven days is the eligibility threshold, not a guaranteed maximum age on disk.

## Scope Boundaries

- **In scope**: the direct-file seven-day tier; pass-1 null-separated path handling and per-record deadline check; regression tests; retention, timeout, ownership, and resume-note wording in the hook and documentation.
- **Out of scope**:
  - Writer PID naming changes or removing the 24h tier's `kill -0` check (BUG-3707 remains cancelled).
  - Recursive file deletion or stray-subdirectory pruning. ENH-3709 is deferred pending recurrence evidence and does not block this issue.
  - A user-facing retention setting, watchdog, or changes to the 24h threshold, 3s cooperative budget, or 5s hook timeout.
  - Durable resume-note storage or synchronization with concurrent readers/writers.

## Integration Map

### Files to Modify
- `hooks/scripts/scratch-cleanup.sh` — universal pass, pass-1 `-print0`/null-record read, complete-path batching, per-record deadline check, and accurate comments throughout the header and loop.
- `scripts/tests/test_hooks_integration.py` — extend `TestScratchCleanupSessionEnd` using the existing cleanup helpers and shims.

### Dependent Files (Callers/Importers)
- `hooks/hooks.json` — SessionStart invokes the script with `timeout: 5`; keep the binding and timeout unchanged.
- `scripts/little_loops/issue_manager.py` and `scripts/little_loops/parallel/worker_pool.py` — resume prompts reference partial progress in scratch; document its limited retention without changing their storage behavior here.
- `scripts/little_loops/hooks/adapters/codex/hooks.json` and `hooks/adapters/codex/README.md` — inspect references for obsolete contract wording.
- `skills/init/SKILL.md` and `skills/manage-issue/SKILL.md` — retain their `mkdir -p` before fixed-name redirects.

### Similar Patterns
- Existing builtin PID parsing and batched deletion in `scratch-cleanup.sh` — preserve filename-shape policy and the 500-file batching limit.
- `scripts/little_loops/cli/verify_evidence.py` `write_snapshot` — allocates pid-shaped evidence snapshots in scratch; they remain subject to both tiers. Coordinate any lifecycle wording with BUG-3702, which owns its docstring and fresh-snapshot regression.

### Tests
- Reuse `_backdate`, `_scratch_bashes`, and `run_scratch_cleanup` from `scripts/tests/test_hooks_integration.py`.
- Add the reproduced newline-name case: a 48h-old `old\nfresh-2147483647.txt` must not delete the separate fresh file; the original complete filename must receive normal dead-PID handling.
- Use age fixtures with margins around thresholds (24h ±1h and 7d ±1h), plus 8d/6d cases. Include pid-shaped live/dead files, fixed names, dotfiles, spaces, and newlines.
- Use a delayed `find` shim and a small keep-only fixture to prove skipped records check the cooperative deadline; cover pending-batch flushing and normal exit 0 after that stop.
- Test interruption after deterministic partial progress, then rerun with the real tools to finish. Do not assert exit 0 for the terminated invocation or infer ownership safety from ENOENT handling.
- Preserve the 48h fixture for the fork-count test so pass 1 still exercises batched `rm`; add pass-0 coverage proving no per-file `rm`, `basename`, `sed`, or `stat` forks.
- Keep the existing 5,000-file timing check as a local/integration benchmark and extend it to mixed tiers. It is performance evidence for the tested environment, not a universal deadline guarantee. The containing module is integration-marked and excluded from the push unit matrix; new deterministic checks that need automatic GNU/BSD coverage should live in an unmarked unit-test module under `scripts/tests/`, without a new workflow.
- Cover direct and scratch-root symlinks, unchanged external targets and nested files, and a deterministic concurrent-disappearance/error case.

### Documentation
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — update the hook table, lifecycle diagram, and scratch-cleanup section, including liveness claims, retention limits, and best-effort timeout behavior.
- `.claude/CLAUDE.md` and `AGENTS.md` — update the Automation: Scratch Pad contract together to satisfy the mirror gates.
- `docs/development/TROUBLESHOOTING.md` — replace the unconditional deadline-bounded description with the actual cooperative-stop and host-timeout behavior.
- `CHANGELOG.md` — explicitly identify removal of the unconditional user-file preservation guarantee under a concrete version at release prep, not `[Unreleased]`.

### Configuration
- No new setting. `scratch_pad`, the hook binding, and configured timeouts remain unchanged.

## Program Design

### Types

- Bash path records and the existing `dead` array — records become null-delimited; queued strings retain the full enumerated path. No new Python type or shell parser function.

### Signatures

- `run_scratch_cleanup(project_root: Path, bash_bin: str = "bash", timeout: float = 5.0) -> subprocess.CompletedProcess[str]` — existing helper for normal and cooperative-stop cases; use a dedicated subprocess harness for controlled interruption.
- `_backdate(path: Path, hours: float = 48) -> None` — existing age-fixture helper.

### Call Path

`run_scratch_cleanup` -> `scratch-cleanup.sh` (`start=$SECONDS`) -> pass 0 (`find -mmin +10080 -delete`) -> pass 1 (`find -mmin +1440 -print0` -> builtin null-record read -> elapsed-time check -> unchanged builtin PID parse -> `kill -0` -> complete-path batched `rm -f`) -> flush pending batch -> empty-root `rmdir` -> normal `exit 0`.

Production invokes the same script through `hooks/hooks.json` SessionStart. Host termination can interrupt this path; no resume checkpoint is introduced.

### Behavior Parity

The 24h threshold, numeric suffix parser, live-PID exemption below seven days, batching limit, direct-file scope, and normal exit-0 behavior are retained. Deliberate changes are the universal seven-day tier, safe path-record handling, per-record cooperative-stop checks, and accurate documentation of interruption and retention limits.

## Implementation Steps

1. Refresh readiness/outcome scoring for the revised scope before implementation, then write regression tests first: newline wrong-file deletion, seven-day retention, skipped-record deadline handling, partial-batch flushing, and interruption/rerun; verify the relevant new cases fail against current code.
2. Add `MAX_AGE_MINUTES=10080` and pass 0 before the existing pass, preserving `start=$SECONDS` before both passes.
3. Switch pass 1 to null-separated paths, queue the full path, and check elapsed time before processing each record. Keep PID parsing, liveness compatibility, thresholds, batched deletion, and pending-batch flushing.
4. Update all contract and ownership wording in the hook, guide, mirrored instruction files, and troubleshooting documentation. Document the behavioral compatibility change and scratch-note lifetime; coordinate snapshot wording with BUG-3702.
5. Run targeted tests under PATH bash and macOS `/bin/bash` 3.2, verify GNU/BSD behavior through the existing test matrix where deterministic checks are added, and run `python -m pytest scripts/tests/`. Treat the large-directory timing test as integration performance evidence.
6. Add the CHANGELOG note at release prep.

## Impact

- **Priority**: P4 — accumulated scratch files erode cleanup performance; safe path handling is a required correction within this change.
- **Effort**: Small — one native retention pass, small changes to the existing loop, and focused regression/documentation updates.
- **Risk**: Medium — older user-written files and resume notes lose a documented preservation guarantee; slow filesystems can still produce a host timeout, and concurrent rewrites are not synchronized.
- **Breaking Change**: Yes (behavioral) — user-written scratch files older than seven days become eligible for automatic deletion.

## Acceptance Criteria

- [ ] On a successful sweep, a no-suffix file 8d old is removed and one 6d old is preserved; margin-based cases cover both sides of the seven-day threshold.
- [ ] Old dotfiles and files with spaces/newlines are removed using complete paths; fresh fixed-name and rewritten files are preserved.
- [ ] The reproduced 48h-old newline filename is handled as one path and cannot cause deletion of a separate fresh pid-shaped file.
- [ ] A pid-shaped file 8d old is removed even if its filename PID is alive; the same live-PID fixture 6d old remains. Dead-PID fixtures on either side of 24h preserve the existing tier policy.
- [ ] Existing PID parser edge cases still pass; existing preservation-test comments are updated to describe the finite two-tier contract.
- [ ] A delayed keep-only scan stops pass-1 processing after the cooperative deadline is observed, including before a skip; a pending partial deletion batch is flushed and the hook exits 0 normally.
- [ ] A deliberately interrupted sweep leaves completed deletions in place, preserves unrelated/fresh files, and a subsequent successful invocation finishes the remaining eligible work. No exit-0 assertion is made for external termination.
- [ ] Subdirectories, nested files, symlinks, and external targets are preserved; a symlink at the scratch-directory path causes no target deletion.
- [ ] Fork-count checks show no per-file `basename`/`sed`/`stat` and only batched pass-1 `rm`; pass 0 invokes no `rm`. A disappearing-file race does not make normal completion fail.
- [ ] Mixed-tier large-directory performance is measured under supported bash variants without turning the observed timing into a hard completion guarantee; normal, cooperative-stop, and host-timeout outcomes are distinguished.
- [ ] The hook header/loop comments, guide, troubleshooting, and mirrored CLAUDE.md/AGENTS.md contracts consistently state the two tiers, behavioral compatibility change, resume-note limits, and best-effort timeout behavior.
- [ ] `python -m pytest scripts/tests/` exits 0, including mirror gates; supported shell/platform validation is recorded.

## Review Evidence

2026-10-03: 27 existing scratch-cleanup/root-resolution tests passed. Separate temporary-fixture probes reproduced fresh-file deletion from a newline-containing old filename and a 6.44s keep-only scan with no cooperative deadline check. The proposed native seven-day pass was locally checked against old/fresh files, dotfiles, newline names, a symlink to an external target, and a nested file; direct-file scope and target preservation behaved as intended. These observations justify the added regressions but do not prove timing on every filesystem or atomic safety against concurrent rewrites. The prior readiness/outcome scores of 100/93 described the previous design and were removed; they must be reassessed for the revised scope.

## Status

**Open** | Created: 2026-10-03 | Priority: P4 | Revised after review: 2026-10-03

## Session Log
- `/ll:confidence-check` - 2026-10-03T18:44:58 - `b1c5eb16-ae1a-4e20-9a59-b0f92f518844.jsonl`
- `/ll:confidence-check` - 2026-10-03T17:44:48 - `32f52444-a659-4ef8-933a-2361ae6c6aff.jsonl`
- `/ll:format-issue` - 2026-10-03T17:29:28 - `782c403d-3c0b-47cc-a461-f433badb1263.jsonl`
