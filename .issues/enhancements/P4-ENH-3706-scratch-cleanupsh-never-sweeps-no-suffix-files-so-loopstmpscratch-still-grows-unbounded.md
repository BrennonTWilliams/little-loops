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
---

# ENH-3706: scratch-cleanup.sh never sweeps no-suffix files so .loops/tmp/scratch still grows unbounded

## Summary

At review time (2026-10-03), 2,766 of the 2,822 files (109 MB) in `.loops/tmp/scratch` had no `-<pid>` suffix. `hooks/scripts/scratch-cleanup.sh` skips them unconditionally (BUG-2525 contract: user-typed files are not owned by the sweep), so the directory grows without bound even though BUG-3705 (done, 87d50cb02) made the pid-file sweep complete.

Add a second retention tier: sweep no-suffix files by mtime age alone, at a much longer threshold (7 days) than the 24h dead-pid tier, without reintroducing the BUG-2525 deletion of files a user, skill, or loop is still reading (`init-verify-*.txt`, `test-results.txt`).

## Motivation

- File count, not bytes, is the real cost: the sweep's `find` enumerates every file each SessionStart and the 3s `$SECONDS` deadline (BUG-3705) is shared with the delete work, so an ever-growing no-suffix backlog erodes the headroom BUG-3705 just bought.
- Measured no-suffix backlog by age (2026-10-03): >1d 2,745, >3d 2,743, >7d 2,489, >14d 2,423, >30d 1,820. A 7-day threshold clears ~90% of it; 30 days would leave ~66%.
- Producers of no-suffix files are one-shot model-typed redirects (`enhN-full.txt`, `bugN-tests.txt`, `test-results-enhN.txt`, ...) and skill-documented fixed names (`skills/init/SKILL.md` `init-verify-{test,lint}.txt`, `skills/manage-issue/SKILL.md` `test-results.txt`). Fixed names are rewritten every run so their mtime stays fresh; one-shot names are dead after the turn that read their tail. mtime is the only liveness signal a pid-less file has.

## Current Behavior

`scratch-cleanup.sh` enumerates `find "$SCRATCH_DIR" -maxdepth 1 -type f -mmin +1440` and, for each file, requires a `.`, a non-empty extension, a `-` in the stem, and an all-digit trailing pid (`case ... continue`). Any file failing that shape — every no-suffix file — is skipped regardless of age. They accumulate forever: after BUG-3705 swept the pid-suffixed backlog, 2,766 of the 2,822 files (98%) left are no-suffix (it was 54% of 5,152 at the original BUG-3705 review).

## Expected Behavior

A no-suffix regular file directly in `.loops/tmp/scratch` is removed at SessionStart once its mtime is more than 7 days old (`UNOWNED_MIN_AGE_MINUTES=10080`). No-suffix files younger than 7 days, and all pid-suffixed files, behave exactly as after BUG-3705 (pid-suffixed: swept after 24h iff owner dead). Subdirectories are never swept. The hook still always exits 0 and still finishes inside the 5s hook timeout (3s `$SECONDS` deadline) on a directory of ≥5,000 files.

## Proposed Solution

_Revised after pre-implementation review (Opus consult via `/ll:advise`, 2026-10-03, confidence 0.85)._

1. **Policy: hardcoded 7-day mtime sweep, no config knob, no env var.** A knob would mean bash parsing JSON (fork/`jq`) inside a 5s hook; scratch is ephemeral by name. One named constant next to `MIN_AGE_MINUTES`: `UNOWNED_MIN_AGE_MINUTES=10080`.
2. **Second `find` pass, not a branch in the existing loop.** `find -mmin +1440` also returns no-suffix files that are 1–7 days old; telling those apart in bash needs a per-file stat fork or non-portable date math. Add `find "$SCRATCH_DIR" -maxdepth 1 -type f -mmin +"$UNOWNED_MIN_AGE_MINUTES"` after the dead-pid pass; in that pass delete only files whose pid parse **fails** (no `-<pid>` shape). Files with a valid pid shape are left to pass 1 (owner-liveness still governs them — a live-pid file older than 7d is not deleted).
3. **Share the pid parse through one function, with no subshell.** Extract the existing builtin parse into `scratch_pid_of`, which sets a global (e.g. `PID_OF`) instead of echoing, so pass 1 and pass 2 cannot drift and the no-per-file-forks test keeps holding. Bash 3.2 compatible: no `mapfile`, no namerefs.
4. **Shared deadline, dead-pid pass first.** Pass 1 (the contract BUG-3705 protects) runs first; skip pass 2 entirely once `$SECONDS - start >= DEADLINE_SECONDS`. Reuse the existing 500-file chunked `rm -f --`.
5. **Rename the BUG-2525 contract to "two-tier retention"**: pid-suffixed files are swept after 24h once the owner is dead; no-suffix files are swept after 7 days regardless of owner. Update every statement of the old "preserved unconditionally" wording (see Integration Map).
6. **Do not use ctime (`-cmin`) as an extra guard against mtime-preserving moves.** It is a stronger signal, but tests cannot backdate it (`os.utime` cannot set ctime) and BSD `find -cmin +0` does not match fresh files. Document the limitation instead.

**Accepted behavior to document (docs + script header):**
- Files moved/copied into scratch with their mtime preserved (`mv`, `cp -p`, `rsync -a`, `tar x`, `git checkout`) are deleted at the next SessionStart if the original mtime is >7d.
- The "partial progress notes in `.loops/tmp/scratch/`" that `issue_manager.py` and `parallel/worker_pool.py` guillotine/resume prompts point to are lost if a resume happens more than 7d after the kill.
- Subdirectories (and anything not a regular file at depth 1) are never swept.

## Scope Boundaries

- **In scope**: the 7d no-suffix tier in `scratch-cleanup.sh`; shared pid-parse function; contract wording in the script header, `docs/guides/BUILTIN_HOOKS_GUIDE.md`, `.claude/CLAUDE.md`, `AGENTS.md`, `CHANGELOG`; tests for the new tier.
- **Out of scope**:
  - Writer-side fix so redirect filenames carry the real command pid — BUG-3707.
  - Sweeping stray scratch subdirectories (`.ll`, `split`, `head`, `pbuild`, `__pycache__`) — ENH-3709 (the stray `.ll` also shadows `find_project_root()`).
  - A user-facing retention config knob or env var.
  - Changing the 24h dead-pid tier or the 3s deadline.

## Integration Map

### Files to Modify
- `hooks/scripts/scratch-cleanup.sh` — add `UNOWNED_MIN_AGE_MINUTES`, extract `scratch_pid_of`, add pass 2, update header comment (lines ~36–40 state the old contract)

### Dependent Files (Callers/Importers)
- `hooks/hooks.json` — SessionStart entry (`timeout: 5`) invokes the script; no change needed
- `scripts/little_loops/hooks/adapters/codex/hooks.json` / `hooks/adapters/codex/README.md` — mention the scratch dir; confirm no contract wording

### Similar Patterns
- `hooks/scripts/session-cleanup.sh` `pid_alive()` — liveness fallback; only adopt if it adds no per-file fork
- `scripts/little_loops/cli/verify_evidence.py` `write_snapshot` — writes `evidence-snapshot-<uuid4>-<pid>.json` (pid-suffixed, stays in tier 1)

### Tests
- `scripts/tests/test_hooks_integration.py` `TestScratchCleanupSessionEnd` — reuse `_backdate(path, hours=...)` and `run_scratch_cleanup(project_root, bash_bin, timeout)`; `test_scratch_cleanup_preserves_file_without_pid_suffix` uses a fresh file and still passes; extend `test_scratch_cleanup_large_dir_within_hook_timeout` and `test_scratch_cleanup_hot_path_has_no_per_file_forks` to cover pass 2

### Documentation
- `docs/guides/BUILTIN_HOOKS_GUIDE.md:55,184` — hook table row and "Scratch-pad cleanup" section ("preserved unconditionally (BUG-2525)")
- `.claude/CLAUDE.md:240` and `AGENTS.md:220` — "`scratch-cleanup.sh` only prunes files this hook created … user-typed scratch files … survive cleanup (BUG-2525)"; **update both together or the mirror gates fail**
- `CHANGELOG.md` — add under a concrete version section at release prep (not `[Unreleased]`)
- `docs/development/TROUBLESHOOTING.md:~1066` — references scratch-cleanup timeout; check for contract wording

### Configuration
- N/A — deliberately no new config key (`scratch_pad` schema block untouched)

## Program Design

### Types

- N/A — shell hook, no new types

### Signatures

- `scratch_pid_of(base: str) -> str` — new shell function in `scratch-cleanup.sh`; sets a global (no subshell) to the trailing numeric pid of `<name>-<pid>.<ext>`, or empty when the name lacks that shape
- `run_scratch_cleanup(project_root: Path, bash_bin: str = "bash", timeout: float = 5.0) -> subprocess.CompletedProcess[str]` — existing test helper; runs the hook with the 5s timeout enforced
- `_backdate(path: Path, hours: float = 48) -> None` — existing test helper; call with `hours=8 * 24` / `hours=6 * 24` for the new tier

### Call Path

`run_scratch_cleanup` -> `scratch-cleanup.sh` pass 1 (`find -mmin +1440` -> `scratch_pid_of` -> `kill -0` -> chunked `rm -f`) -> pass 2 (`find -mmin +10080` -> `scratch_pid_of` empty -> chunked `rm -f`)

In production the same script is invoked by the `hooks/hooks.json` SessionStart entry.

## Implementation Steps

1. Extract the existing builtin pid parse into `scratch_pid_of`; confirm pass-1 behavior is byte-for-byte unchanged (existing `test_scratch_cleanup_pid_parsing_matches_legacy_sed` stays green).
2. Add `UNOWNED_MIN_AGE_MINUTES=10080` and pass 2 with the shared deadline check and chunked delete.
3. Write tests first (TDD mode is on): fixtures below, run RED, then implement.
4. Update the contract wording in the script header, `BUILTIN_HOOKS_GUIDE.md`, `.claude/CLAUDE.md`, `AGENTS.md`; add the "accepted behavior" notes.
5. Add the CHANGELOG entry at release prep; run `python -m pytest scripts/tests/` and verify under both PATH `bash` and macOS `/bin/bash` 3.2.
6. Stray-subdirectory follow-up is filed as ENH-3709 (out of scope here).

## Impact

- **Priority**: P4 - disk growth (109 MB) is minor, but unbounded file count slows `find` and erodes the 3s sweep deadline
- **Effort**: Small - one extra `find` pass reusing the existing chunked-delete and deadline machinery
- **Risk**: Low-Medium - mtime-only deletion; files moved in with preserved mtime or resume notes older than 7d are lost (documented, accepted); contract wording lives in 4 places and the CLAUDE.md/AGENTS.md copies are mirror-gated
- **Breaking Change**: No (behavior change limited to files untouched for >7 days)

## Acceptance Criteria

- [ ] A no-suffix file with mtime 8 days old is removed at SessionStart
- [ ] A no-suffix file with mtime 6 days old is preserved
- [ ] A fresh `test-results.txt` (and a re-written fixed-name file) is preserved
- [ ] A pid-suffixed file older than 7d whose owner pid is alive is still preserved (pass 2 never touches valid-pid shapes)
- [ ] Dead-pid 24h-tier behavior is unchanged (all existing `TestScratchCleanupSessionEnd` tests pass unmodified apart from deliberate additions)
- [ ] Subdirectories under `.loops/tmp/scratch` are never removed
- [ ] A ≥5,000-file directory mixing both tiers sweeps within 5s under PATH `bash` and `/bin/bash` 3.2; a truncated run still exits 0 and makes progress
- [ ] No per-file `basename`/`sed`/`stat` forks in either pass and `rm` stays batched (shim-verified); pass 2 is skipped once the 3s deadline has passed
- [ ] Contract wording updated consistently in the script header, `BUILTIN_HOOKS_GUIDE.md`, `.claude/CLAUDE.md`, and `AGENTS.md`; accepted-behavior limits documented
- [ ] `python -m pytest scripts/tests/` exits 0 (including the CLAUDE.md/AGENTS.md mirror gates)

## Status

**Open** | Created: 2026-10-03 | Priority: P4


## Session Log
- `/ll:format-issue` - 2026-10-03T17:29:28 - `782c403d-3c0b-47cc-a461-f433badb1263.jsonl`
