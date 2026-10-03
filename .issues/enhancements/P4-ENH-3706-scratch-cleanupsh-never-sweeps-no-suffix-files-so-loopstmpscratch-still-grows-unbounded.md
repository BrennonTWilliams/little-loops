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
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-3706: scratch-cleanup.sh never sweeps no-suffix files so .loops/tmp/scratch still grows unbounded

## Summary

At review time (2026-10-03), 2,766 of the 2,822 files (109 MB) in `.loops/tmp/scratch` had no `-<pid>` suffix. `hooks/scripts/scratch-cleanup.sh` skips them unconditionally (BUG-2525 contract: user-typed files are not owned by the sweep), so the directory grows without bound even though BUG-3705 (done, 87d50cb02) made the pid-file sweep complete.

Add a second retention tier: a **universal 7-day mtime cap** — any regular file directly in the scratch dir untouched for >7 days is removed, whatever its name or owner pid — without reintroducing the BUG-2525 deletion of files a user, skill, or loop is still reading (`init-verify-*.txt`, `test-results.txt`; fixed names are rewritten every run so their mtime stays fresh).

## Motivation

- File count, not bytes, is the real cost: the sweep's `find` enumerates every file each SessionStart and the 3s `$SECONDS` deadline (BUG-3705) is shared with the delete work, so an ever-growing no-suffix backlog erodes the headroom BUG-3705 just bought.
- Measured no-suffix backlog by age (2026-10-03): >1d 2,745, >3d 2,743, >7d 2,489, >14d 2,423, >30d 1,820. A 7-day threshold clears ~90% of it; 30 days would leave ~66%.
- **Pid liveness is meaningless after 7 days, so the cap must not exclude pid-shaped files.** BUG-3707 (writer-side pid fix) is `cancelled`/`wont_fix`: `scratch-pad-redirect.sh` still names files with the exiting hook's own `$$`, so every hook-written file is dead-pid on arrival and the only live-pid matches come from pid recycling. Measured 2026-10-03: 8 pid-shaped files are >24h old and **all 8 have a currently-live pid belonging to an unrelated macOS system daemon** (`cloudphotod`, `rcd`, `contentlinkingd`, ...). Pass 1 never deletes them (`kill -0` succeeds), so a "no-suffix only" pass 2 would leave this leak permanent and growing (macOS pid space ~99,999).
- Producers of no-suffix files are one-shot model-typed redirects (`enhN-full.txt`, `bugN-tests.txt`, `test-results-enhN.txt`, ...) and skill-documented fixed names (`skills/init/SKILL.md` `init-verify-{test,lint}.txt`, `skills/manage-issue/SKILL.md` `test-results.txt`). Fixed names are rewritten every run so their mtime stays fresh; one-shot names are dead after the turn that read their tail. mtime is the only liveness signal a pid-less file has.

## Current Behavior

`scratch-cleanup.sh` enumerates `find "$SCRATCH_DIR" -maxdepth 1 -type f -mmin +1440` and, for each file, requires a `.`, a non-empty extension, a `-` in the stem, and an all-digit trailing pid (`case ... continue`). Any file failing that shape — every no-suffix file — is skipped regardless of age. They accumulate forever: after BUG-3705 swept the pid-suffixed backlog, 2,766 of the 2,822 files (98%) left are no-suffix (it was 54% of 5,152 at the original BUG-3705 review).

## Expected Behavior

Any regular file directly in `.loops/tmp/scratch` (dotfiles included, pid-shaped or not, owner alive or not) is removed at SessionStart once its mtime is more than 7 days old (`MAX_AGE_MINUTES=10080`). Files younger than 7 days behave exactly as after BUG-3705 (pid-suffixed: swept after 24h iff owner dead; no-suffix: kept). Subdirectories and symlinks are never swept. The hook still always exits 0 and still finishes inside the 5s hook timeout (3s `$SECONDS` deadline) on a directory of ≥5,000 files.

## Proposed Solution

_Revised after pre-implementation review (Opus consult via `/ll:advise`, 2026-10-03, confidence 0.85)._

1. **Policy: hardcoded universal 7-day mtime cap, no config knob, no env var.** A knob would mean bash parsing JSON (fork/`jq`) inside a 5s hook; scratch is ephemeral by name. One named constant next to `MIN_AGE_MINUTES`: `MAX_AGE_MINUTES=10080`.
2. **New pass 0, run BEFORE the dead-pid pass, as a single `find -delete`:** `find "$SCRATCH_DIR" -maxdepth 1 -type f -mmin +"$MAX_AGE_MINUTES" -delete 2>/dev/null || true`. No bash parse, no `rm`, no per-file forks. `|| true` is required: concurrent SessionStart sweeps (ll-parallel) race and `find -delete` can exit non-zero on ENOENT. Running it first also shrinks the set pass 1 enumerates. Verified on macOS BSD `find` (Opus consult): deletes old dotfiles and names with newlines; leaves symlinks and subdirectories alone (`-type f`).
3. **No `scratch_pid_of` refactor.** Pass 0 does not parse names, so pass 1's builtin parse stays untouched and BUG-3705's `test_scratch_cleanup_pid_parsing_matches_legacy_sed` keeps guarding it.
4. **Deadline:** `find -delete` cannot be interrupted by the `$SECONDS` deadline. Acceptable — at steady state it removes ~one week of files (well under 1s); the only exposure is the first run on a very large backlog (today: 2,489 files). Pass 1 still honors the 3s deadline, and a truncated run exits 0.
5. **Rename the BUG-2525 contract to "two-tier retention"**: (a) any regular file untouched >7 days is swept regardless of name or owner (pid liveness is unreliable — recycled pids, BUG-3707 wont_fix); (b) pid-suffixed files are swept after 24h once the owner is dead. Update every statement of the old "preserved unconditionally" wording (see Integration Map).
6. **Do not use ctime (`-cmin`) as an extra guard against mtime-preserving moves.** It is a stronger signal, but tests cannot backdate it (`os.utime` cannot set ctime) and BSD `find -cmin +0` does not match fresh files. Document the limitation instead.
7. **Leave pass 1's `kill -0` in place** (now near-useless: live-pid matches arise only from pid recycling). Removing it reworks the BUG-3705 contract and tests; the 7-day cap bounds the damage. Candidate follow-up, not this issue.

**Accepted behavior to document (docs + script header):**
- Files moved/copied into scratch with their mtime preserved (`mv`, `cp -p`, `rsync -a`, `tar x`, `git checkout`) are deleted at the next SessionStart if the original mtime is >7d.
- The "partial progress notes in `.loops/tmp/scratch/`" that `issue_manager.py` and `parallel/worker_pool.py` guillotine/resume prompts point to are lost if a resume happens more than 7d after the kill.
- A live-pid file idle >7 days is removed (the owner is assumed gone or the pid recycled).
- Subdirectories, symlinks, and anything not a regular file at depth 1 are never swept.

## Scope Boundaries

- **In scope**: the universal 7d tier in `scratch-cleanup.sh`; contract wording in the script header, `docs/guides/BUILTIN_HOOKS_GUIDE.md`, `.claude/CLAUDE.md`, `AGENTS.md`, `CHANGELOG`; tests for the new tier.
- **Out of scope**:
  - Writer-side fix so redirect filenames carry the real command pid — BUG-3707 (cancelled, `wont_fix`; this issue's universal cap is the reason it is not needed).
  - Removing/reworking pass 1's `kill -0` liveness check (candidate follow-up).
  - Sweeping stray scratch subdirectories (`.ll`, `split`, `head`, `pbuild`, `__pycache__`) — ENH-3709 (the stray `.ll` also shadows `find_project_root()`).
  - A user-facing retention config knob or env var.
  - Changing the 24h dead-pid tier or the 3s deadline.

## Integration Map

### Files to Modify
- `hooks/scripts/scratch-cleanup.sh` — add `MAX_AGE_MINUTES` and the pass-0 `find -delete`, update header comment (lines ~36–40 state the old contract)

### Dependent Files (Callers/Importers)
- `hooks/hooks.json` — SessionStart entry (`timeout: 5`) invokes the script; no change needed
- `scripts/little_loops/hooks/adapters/codex/hooks.json` / `hooks/adapters/codex/README.md` — mention the scratch dir; confirm no contract wording

### Similar Patterns
- `hooks/scripts/session-cleanup.sh` `pid_alive()` — liveness fallback; only adopt if it adds no per-file fork
- `scripts/little_loops/cli/verify_evidence.py` `write_snapshot` — writes `evidence-snapshot-<uuid4>-<pid>.json` (pid-suffixed, stays in tier 1)

### Tests
- `scripts/tests/test_hooks_integration.py` `TestScratchCleanupSessionEnd` — reuse `_backdate(path, hours=...)` and `run_scratch_cleanup(project_root, bash_bin, timeout)`; `test_scratch_cleanup_preserves_file_without_pid_suffix` uses a fresh file and still passes; `test_scratch_cleanup_preserves_file_owned_by_live_process` is fresh (not backdated) and still passes — add a sibling backdated 8d. Extend `test_scratch_cleanup_large_dir_within_hook_timeout` to a mixed-tier dir; in `test_scratch_cleanup_hot_path_has_no_per_file_forks` keep its fixtures at 48h (its `1 <= rm <= ceil(n/500)` assertion would fail if pass 0 consumed every file) and add pass 0 to the shimmed tools (`find -delete` must spawn no `rm`/`basename`/`sed`)

### Documentation
- `docs/guides/BUILTIN_HOOKS_GUIDE.md:55,184` — hook table row and "Scratch-pad cleanup" section ("preserved unconditionally (BUG-2525)"); also the table row at :55 says "Prunes dead-PID scratch files"→ mention the 7d cap
- `.claude/CLAUDE.md:240` and `AGENTS.md:220` — "`scratch-cleanup.sh` only prunes files this hook created … user-typed scratch files … survive cleanup (BUG-2525)"; **update both together or the mirror gates fail**
- `CHANGELOG.md` — add under a concrete version section at release prep (not `[Unreleased]`)
- `docs/development/TROUBLESHOOTING.md:~1066` — references scratch-cleanup timeout; check for contract wording

### Configuration
- N/A — deliberately no new config key (`scratch_pad` schema block untouched)

## Program Design

### Types

- N/A — shell hook, no new types

### Signatures

- N/A for new functions — pass 0 is an inline `find ... -delete`; no `scratch_pid_of`
- `run_scratch_cleanup(project_root: Path, bash_bin: str = "bash", timeout: float = 5.0) -> subprocess.CompletedProcess[str]` — existing test helper; runs the hook with the 5s timeout enforced
- `_backdate(path: Path, hours: float = 48) -> None` — existing test helper; call with `hours=8 * 24` / `hours=6 * 24` for the new tier

### Call Path

`run_scratch_cleanup` -> `scratch-cleanup.sh` pass 0 (`find -mmin +10080 -delete`) -> pass 1 (`find -mmin +1440` -> builtin pid parse -> `kill -0` -> chunked `rm -f`)

In production the same script is invoked by the `hooks/hooks.json` SessionStart entry.

## Implementation Steps

1. Write tests first (TDD mode is on): fixtures from Acceptance Criteria, run RED.
2. Add `MAX_AGE_MINUTES=10080` and the pass-0 `find -delete ... || true` before pass 1; leave pass 1 byte-for-byte unchanged.
3. Update the contract wording in the script header, `BUILTIN_HOOKS_GUIDE.md` (:55 and :184), `.claude/CLAUDE.md:240`, `AGENTS.md:220` (together, mirror gate); add the "accepted behavior" notes.
4. Add the CHANGELOG entry at release prep; run `python -m pytest scripts/tests/` and verify under both PATH `bash` and macOS `/bin/bash` 3.2.
5. Stray-subdirectory follow-up is filed as ENH-3709 (out of scope here; note it makes `rmdir` of an emptied scratch dir reachable, so skills must keep `mkdir -p` before redirecting).

## Impact

- **Priority**: P4 - disk growth (109 MB) is minor, but unbounded file count slows `find` and erodes the 3s sweep deadline
- **Effort**: Small - one extra `find` pass reusing the existing chunked-delete and deadline machinery
- **Risk**: Low - mtime-only deletion; files moved in with preserved mtime or resume notes older than 7d are lost (documented, accepted); contract wording lives in 4 places and the CLAUDE.md/AGENTS.md copies are mirror-gated
- **Breaking Change**: No (behavior change limited to files untouched for >7 days)

## Acceptance Criteria

- [ ] A no-suffix file with mtime 8 days old is removed at SessionStart; one 6 days old is preserved
- [ ] A dotfile with mtime 8 days old is removed
- [ ] A fresh `test-results.txt` (and a re-written fixed-name file) is preserved
- [ ] A pid-suffixed file 8 days old whose owner pid is alive (e.g. `os.getpid()`) is removed; the same file 6 days old is preserved (pid recycling makes liveness unreliable; BUG-3707 wont_fix)
- [ ] Dead-pid 24h-tier behavior is unchanged (all existing `TestScratchCleanupSessionEnd` tests pass unmodified apart from deliberate additions)
- [ ] Subdirectories and symlinks under `.loops/tmp/scratch` are never removed (old or not)
- [ ] A ≥5,000-file directory mixing both tiers (and >7d files) sweeps within 5s under PATH `bash` and `/bin/bash` 3.2; a truncated run still exits 0 and makes progress
- [ ] No per-file `basename`/`sed`/`stat` forks and `rm` stays batched (shim-verified); pass 0 spawns no `rm`; a concurrent-sweep ENOENT (file vanishes mid-`find -delete`) still exits 0
- [ ] Contract wording updated consistently in the script header, `BUILTIN_HOOKS_GUIDE.md`, `.claude/CLAUDE.md`, and `AGENTS.md`; accepted-behavior limits documented
- [ ] `python -m pytest scripts/tests/` exits 0 (including the CLAUDE.md/AGENTS.md mirror gates)

## Status

**Open** | Created: 2026-10-03 | Priority: P4


## Session Log
- `/ll:confidence-check` - 2026-10-03T17:44:48 - `32f52444-a659-4ef8-933a-2361ae6c6aff.jsonl`
- `/ll:format-issue` - 2026-10-03T17:29:28 - `782c403d-3c0b-47cc-a461-f433badb1263.jsonl`
