---
id: BUG-3705
type: BUG
title: scratch-cleanup.sh sweep exceeds its 5s hook timeout on large scratch dirs,
  leaving dead-pid files unswept
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-03'
captured_at: '2026-10-03T01:30:35Z'
verify_verdict: VALID
relates_to:
- BUG-3702
confidence_score: 95
outcome_confidence: 89
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# BUG-3705: scratch-cleanup.sh sweep exceeds its 5s hook timeout on large scratch dirs, leaving dead-pid files unswept

## Summary

`hooks/scripts/scratch-cleanup.sh` (SessionStart) has a 5s hook timeout (`hooks/hooks.json`) but sweeps `.loops/tmp/scratch` with one `kill -0` / `sed` / `rm` per file. With thousands of dead-pid files the hook is killed part-way through the glob, so dead-pid files late in the sort order are never swept and the directory grows without bound. Found while reviewing BUG-3702.

## Current Behavior

At review time (2026-10-02) `.loops/tmp/scratch` held 5,143 files. The sweep iterates `"$SCRATCH_DIR"/*` in alphabetical order and spawns `basename`/`sed` subprocesses per file; once the 5s timeout kills the hook, the remaining files survive. Each later session repeats the same prefix of the sweep.

## Expected Behavior

The sweep completes within the timeout regardless of directory size (or makes monotonic progress across sessions), so dead-pid files do not accumulate.

## Proposed Solution

Replace the per-file subprocess spawns with shell-builtin parsing (parameter expansion instead of `basename`/`sed`) and/or a single `find`-based pass; optionally bound runtime and sweep oldest-first so partial runs still make progress. Add a test with a few thousand synthetic dead-pid files asserting the hook finishes under the timeout and removes them.

## Steps to Reproduce

1. Populate `.loops/tmp/scratch` with a few thousand dead-pid files (`<name>-<dead pid>.txt`).
2. Run `time bash hooks/scripts/scratch-cleanup.sh` (or start a session; the hook has `timeout: 5`).
3. Observe the sweep exceed 5s / be killed, leaving dead-pid files late in the sort order in place.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-03 — based on codebase analysis:_

- **Files to Modify**: `hooks/scripts/scratch-cleanup.sh` (the sweep); `scripts/tests/test_hooks_integration.py` (class `TestScratchCleanupSessionEnd`, ~line 2948 — add the large-directory case and the Program Design's `run_scratch_cleanup` helper, which is not yet defined anywhere under `scripts/tests`). `hooks/hooks.json:43-45` only if the timeout itself is changed; the issue's Expected Behavior says the sweep should fit the existing 5s.
- **Dependents / readers of the directory** (none write pid-suffixed names, none are affected by sweep internals): `scripts/little_loops/subprocess_utils.py:561` (`_list_scratch_files`; comment at `:379` already notes the dir "can accumulate thousands" of files), `scripts/little_loops/cli/verify_evidence.py:1938` (`SNAPSHOT_DIR`) and `:2013` (`write_snapshot`, docstring at `:2017` cites this sweep), `hooks/scripts/scratch-pad-redirect.sh:103-119` (writer; recreates the dir with `mkdir -p` inside each rewritten command, so a sweep that `rmdir`s is safe).
- **Contract tests that must keep passing** (all in `test_hooks_integration.py`, direct-exec via shebang with `monkeypatch.chdir(tmp_path)` and `timeout=5`): `test_scratch_cleanup_script_prunes_scratch` (~2970) is a *static text* check — script text must still contain the literal `kill -0` and no non-comment line may contain both `rm -rf` and `scratch`; `..._never_fails_when_dir_absent` (~2987); `..._preserves_file_without_pid_suffix` (~2999, BUG-2525, `test-results.txt`); `..._preserves_file_owned_by_live_process` (~3020, uses `os.getpid()`); `..._removes_file_owned_by_dead_process` (~3045, pid `2147483647`, also asserts the dir is gone via `rmdir`). Registration tests: `test_hooks_json_registers_scratch_cleanup_under_session_start` (~3064 and `test_claude_code_adapter.py:130`) check presence only, not the timeout value.
- **Conventions in force**: (1) cleanup hooks must never fail — `exit 0` and `|| true` on every operation (`scratch-cleanup.sh` header, BUG-2525 contract). (2) Hook shell must run on bash 3.2 and BSD userland; `scripts/tests/test_portability_gate.py` scans tracked `hooks/**/*.sh` and flags `mapfile`/`readarray`, `declare -A`, `${x,,}`, `sed -i`, `grep -P`, `stat -c`/`date -d` unpaired, etc. (suppress with `ll-portability-ok: <reason>`); it does not cover `BASH_REMATCH`, `find -delete`, `xargs` — but BSD `xargs` has no `-r`, and `CONTRIBUTING.md:428-440` is the written rule. (3) Hook runtime is bounded only by the static `hooks.json` timeout plus the test's `subprocess.run(timeout=...)`; no in-script deadline convention exists (searched all `*.sh` for `SECONDS`/deadline/`timeout`; only `acquire_lock` in `hooks/scripts/lib/common.sh:8-38` counts time). (4) Wall-clock test assertions follow `time.monotonic()` before/after `subprocess.run` with `assert elapsed < 5.0` (`test_hooks_integration.py:1086-1141`, context-monitor).
- **Contested convention**: pid-liveness — `scratch-cleanup.sh:52` uses bare `kill -0`, while `hooks/scripts/session-cleanup.sh:11-16` `pid_alive()` adds a `ps -p` fallback because bare `kill -0` reads another user's process as dead (EPERM). Whether the sweep needs the stricter check is a decision for the implementer; whichever is chosen must keep the literal `kill -0` the static test greps for, and must not add per-file forks back into the hot path.
- **Tests / timing facts for the new case**: the 5,000-file fixture should be generated in-test under `tmp_path`; with current code it takes ~24s here, so a `timeout=5` / `elapsed < 5.0` assertion fails before the fix and passes after (red/green). Run it under `/bin/bash` as well as PATH `bash` — bash 3.2 is the slowest/most restrictive case and the existing shim tests already parametrize over it (`test_record_hook_event_shim.py:35-41`, `_available_bashes()`). Pid reuse in fixtures: use pids that are certainly dead (existing tests use `2147483647`), and include a few no-suffix and live-pid files to hold the BUG-2525 contract at scale.
- **Docs**: `docs/guides/BUILTIN_HOOKS_GUIDE.md` (~line 182, "Scratch-pad cleanup" section) describes the hook as pure bash and says nothing about the timeout budget; `docs/development/TROUBLESHOOTING.md:1011,1059` reference the script.
- **Behavior Parity** (hook rewrite is in place, not a replacement): the externally visible behaviors — skip files lacking a `-<pid>` suffix, skip live-pid files, remove dead-pid files, `rmdir` the directory only when empty, always exit 0, tolerate a missing dir — are all PRESERVED.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

- `hooks/hooks.json:43-44` (SessionStart, `scratch-cleanup.sh` entry) — sole invoker (`bash <path>`, PATH bash) with `"timeout": 5` and `"statusMessage": "Cleaning up scratch pad..."`; nothing sources or imports the script, there is no Python port, and no codex/opencode/gemini/kimi/qwen copy or sync gate [Agent 1/2 finding]
- `hooks/scripts/session-cleanup.sh:41,43` — comments only ("Scratch cleanup now lives in scratch-cleanup.sh"); no runtime coupling. `test_session_cleanup_no_longer_removes_scratch` pins that file, not the sweep [Agent 1/2 finding]
- `scripts/little_loops/issue_manager.py:483` and `scripts/little_loops/parallel/worker_pool.py:1195` — prompt strings tell the model to review `.loops/tmp/scratch/`; read-only, unaffected by a faster sweep [Agent 1 finding]
- `skills/init/SKILL.md:148-150` (`init-verify-test.txt`, `init-verify-lint.txt`) and `skills/manage-issue/SKILL.md:385` (`test-results.txt`) — writers of no-suffix files; these are the BUG-2525 preserve cases the rewrite must keep skipping [Agent 1 finding]
- `scripts/little_loops/subprocess_utils.py::_list_scratch_files` — read-only and tolerates a missing dir (returns `"None"`), so the sweep's `rmdir` stays safe [Agent 2 finding]
- Worktree copies under `.claude/worktrees/agent-*/hooks/scripts/scratch-cleanup.sh` are ephemeral agent checkouts, not mirrors — do not edit [Agent 1 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_portability_gate.py::test_repo_is_portable` — scans tracked `hooks/**/*.sh` line-by-line (`RULES`: `bash4-mapfile`, `bash4-declare-A`, `bash4-case-mod`, `bash4-local-n`, `sed-i-no-attached-suffix`, `grep-P`, `stat-c`, `date-d`, ...); a rewrite using `mapfile`, `declare -A` (per-pid liveness cache), or `${x,,}` fails it. Not covered by any rule: `find -delete`/`-print0`, `xargs`/`xargs -r` (BSD has no `-r`), `[[ =~ ]]`/`BASH_REMATCH`, `$SECONDS` — verify these by hand under `/bin/bash` 3.2 [Agent 2/3 finding]
- `scripts/tests/test_hooks_integration.py::TestScratchCleanupSessionEnd.test_scratch_cleanup_script_prunes_scratch` — may break: requires literal `.loops/tmp/scratch` and literal `kill -0` anywhere in the script text (comments count) and no non-comment line with both `rm -rf` and lowercase `scratch` [Agent 3 finding]
- `scripts/tests/test_hooks_integration.py::TestScratchCleanupSessionEnd` — new large-directory test goes here (precedent for the `time.monotonic()` + `elapsed < 5.0` shape: `test_large_tool_response_completes_within_timeout`, ~1086-1141); `test_hooks_json_has_no_session_end_key` (~3082) and `TestScratchPadRedirect`/`TestScratchPadRedirectBug2420` (producer hook) are unaffected [Agent 3 finding]
- `scripts/tests/test_record_hook_event_shim.py::_available_bashes` (line 35) — module-private; the new test's PATH-bash + `/bin/bash` parametrization must either import it or copy it (no shared helper exists). Invoke as `[bash_bin, str(script)]` with `cwd=tmp_path` to exercise both legs — the existing direct-exec tests only hit the `#!/bin/bash` shebang, while `hooks.json` runs PATH `bash` [Agent 3 finding]
- `scripts/tests/test_wiring_guides_and_meta.py::test_hook_coverage_matches_guide` (via `little_loops.doc_counts.registered_hook_scripts`/`verify_coverage`) — requires every `*.sh` in `hooks/hooks.json` to be named in `BUILTIN_HOOKS_GUIDE.md`; keep the script name and registration unchanged. A helper script under `hooks/scripts/` that is not registered would not need a guide entry, but must be `git add`ed for the portability gate [Agent 2 finding]
- Test-runner constraints (`scripts/pyproject.toml`): `--timeout=120 --timeout-method=thread -n logical --dist loadfile --max-worker-restart=0`; no `slow`/`no_parallel` markers are used in `test_hooks_integration.py` and none are needed for a `subprocess.run(timeout=5)` call, but the 5,000-file fixture should be built with a plain loop of `Path.touch()` (no per-file subprocess) [Agent 3 finding]
- `scripts/tests/test_check_decisions_yaml_hook.py:117` — docstring cites a stale `test_hooks_integration.py:2703-2714` range for the scratch-cleanup template (class is now ~2948); optional drive-by fix, not required [Agent 3 finding]
- No test asserts on the script's stdout/stderr or on the numeric `timeout` in `hooks.json` — the 5s bound exists only as the `hooks.json` literal and each test's `subprocess.run(timeout=5)` [Agent 2/3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `docs/guides/BUILTIN_HOOKS_GUIDE.md` § "Scratch-pad cleanup" (~line 182) — besides the "(pure bash)" label, the body claims the hook is "fast (~0.07s)" with no budget caveat; update if the mechanism gains batching/`find`/a runtime bound, and mention the 5s timeout budget. Keep the `scratch-cleanup.sh` name for `test_hook_coverage_matches_guide`. Other mentions (lifecycle table row, session-flow block, cross-refs at ~447/458) describe semantics that don't change [Agent 2 finding]
- `docs/development/TROUBLESHOOTING.md` § "Hook timeout errors" — lists lock acquisition and slow file ops as causes but not an oversized `.loops/tmp/scratch`; consider adding it as a cause (script is already referenced at ~1011/~1059 for the `chmod +x` step, so the exec bit must survive) [Agent 2 finding]
- `CONTRIBUTING.md` § "Shell Portability (BSD vs GNU, bash 3.2)" (~428-440) — the written rule the rewrite must satisfy; no edit needed [Agent 2 finding]
- `.claude/CLAUDE.md:240` / `AGENTS.md:220` ("Automation: Scratch Pad") — state the `-<pid>`-suffix-only contract, which is unchanged; no edit needed (if wording ever changes, both files carry the same sentence) [Agent 2 finding]
- `docs/ARCHITECTURE.md:105` (hooks tree listing) and `hooks/adapters/codex/README.md:196`, `docs/reference/HOST_COMPATIBILITY.md:659` (scratch-dir path rows) — name/path-only mentions; no edit needed [Agent 1/2 finding]
- `CHANGELOG.md` — add the BUG-3705 entry under a concrete `## [X.Y.Z]` section at release prep, not `[Unreleased]` (prior scratch-cleanup entries: BUG-3363 ~421, BUG-2438 ~2308) [Agent 2 finding]
- `.issues/bugs/P3-BUG-3702-*.md` — names BUG-3705 as the cause of its snapshot loss (line ~29) and plans a hook-level survival test (~56); update/close-out coordination once this lands (`relates_to` already recorded) [Agent 1 finding]

## Program Design

### Types

- N/A — shell hook, no new types

### Signatures

- `run_scratch_cleanup(project_root: Path, timeout: float = 5.0) -> subprocess.CompletedProcess[str]` — new test helper that runs `hooks/scripts/scratch-cleanup.sh` against a synthetic scratch dir and enforces the hook timeout; the hook's own contract (BUG-2525: preserve files without a `-<pid>` suffix and files owned by a live pid) is unchanged

### Call Path

`hooks/hooks.json` SessionStart entry -> `scratch-cleanup.sh` sweeps the files that `write_snapshot` and `scratch-pad-redirect.sh` leave in `.loops/tmp/scratch` -> per-file pid extraction -> `kill -0` -> `rm -f`

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-03 — based on codebase analysis:_

1. A 5,000-file dead-pid directory is swept to empty well inside the 5s hook budget under `/bin/bash` 3.2 as well as PATH `bash`; verified by a new `TestScratchCleanupSessionEnd` case (fixture generated in-test, `elapsed < 5.0`) that fails against the current script (~24s measured) and passes after the change.
2. Per-file process spawns are gone from the hot path — pid extraction yields the same result as `sed -nE 's/.*-([0-9]+)\.[^.]+$/\1/p'` for the shapes in Root Cause (including the non-match cases `x-123.tar.gz` and `foo-123`), and deletion no longer costs one `rm` fork per file.
3. The BUG-2525 contract holds at scale: no-suffix files and live-pid files survive a 5,000-file sweep (add a handful of each to the large fixture); the five existing `TestScratchCleanupSessionEnd` tests, including the static `kill -0` / no-`rm -rf`-on-scratch text check, pass unmodified.
4. If a runtime bound or oldest-first ordering is added (optional per Proposed Solution), a killed or truncated run still leaves the next session strictly further along than the prior one; note the script has no cross-run state today, and `test_portability_gate.py` forbids bash-4-only constructs.
5. `python -m pytest scripts/tests/test_hooks_integration.py scripts/tests/test_portability_gate.py -v` passes, then the full `python -m pytest scripts/tests/`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_hooks_integration.py` (`TestScratchCleanupSessionEnd`) — add the 5,000-file test plus the `run_scratch_cleanup` helper; run it via `[bash_bin, str(script)]` with `cwd=tmp_path` for PATH `bash` and `/bin/bash`, importing or copying `_available_bashes` from `scripts/tests/test_record_hook_event_shim.py:35`
- Keep literal `kill -0` and literal `.loops/tmp/scratch` in `hooks/scripts/scratch-cleanup.sh` (static text test) and avoid `rm -rf` on any line containing `scratch`
- Keep the script's shebang and exec bit, and keep it CWD-relative (tests `monkeypatch.chdir(tmp_path)`; no reliance on `CLAUDE_PLUGIN_ROOT`)
- Hand-check any `find -delete`, `xargs`, or `[[ =~ ]]`/`BASH_REMATCH` use under `/bin/bash` 3.2 and BSD userland — `test_portability_gate.py` does not detect them; `git add` any new tracked helper so the gate scans it
- Update `docs/guides/BUILTIN_HOOKS_GUIDE.md` § "Scratch-pad cleanup" — correct the "~0.07s"/"pure bash" description and note the 5s timeout budget; keep the `scratch-cleanup.sh` name (`test_hook_coverage_matches_guide`)
- Update `docs/development/TROUBLESHOOTING.md` § "Hook timeout errors" — add an oversized `.loops/tmp/scratch` as a cause (optional)
- Add the BUG-3705 `CHANGELOG.md` entry at release prep under a concrete version section

## Impact

- **Priority**: P3 - unbounded scratch growth; also made BUG-3702's snapshot loss intermittent
- **Effort**: Small
- **Risk**: Low - must keep the BUG-2525 contract (files without a `-<pid>` suffix and live-pid files are preserved)

## Acceptance Criteria

- [ ] `scratch-cleanup.sh` removes all dead-pid files from a 5,000-file directory within the hook timeout
- [ ] Files without a `-<pid>` suffix and files owned by a live pid are still preserved
- [ ] `python -m pytest scripts/tests/` exits 0

## Status

**Open** | Created: 2026-10-03 | Priority: P3

## Root Cause

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-03 — based on codebase analysis:_

- **File**: `hooks/scripts/scratch-cleanup.sh` — top-level `for f in "$SCRATCH_DIR"/*` loop (no functions)
- **Cause**: per-file cost is dominated by process spawns, not by `kill -0` (a builtin). Each iteration forks `basename` and a `$(echo | sed -nE ...)` pipeline, and each dead file forks `rm -f`: roughly 3–4 fork/execs per file. Nothing bounds runtime, memoizes per pid, or keeps state between runs, so a hook killed at 5s never reaches `rmdir`/`exit 0` and the next session restarts at the same alphabetical prefix.
- **Measured** (this pass, `/bin/bash` 3.2.57 on arm64 macOS, 5,000 synthetic `pytest-<dead pid>.txt` files in a temp dir, script run to completion with no timeout): 23.8s wall (7.07s user + 13.11s sys); all 5,000 files removed. That is ~4.8× the `timeout: 5` budget in `hooks/hooks.json:44`; figure is host/load dependent but the order of magnitude holds.
- **Filename shapes the sweep must keep parsing** (pid extraction semantics = `sed -nE 's/.*-([0-9]+)\.[^.]+$/\1/p'`): `${SAFE_NAME}-$$.txt` from `hooks/scripts/scratch-pad-redirect.sh:105` (`SAFE_NAME` is `tr -cd '[:alnum:]_-'`, so no dots, possibly several dashes, extension always `.txt`) and `evidence-snapshot-<uuid4>-<pid>.json` from `scripts/little_loops/cli/verify_evidence.py:2024` (`write_snapshot`; uuid contributes four internal dashes). Semantics worth pinning: the pid is the last `-<digits>` run directly before the final dot; `x-123.tar.gz` and `foo-123` (no dot) do **not** match; `a-1-2.txt` yields `2`; `-123.txt` matches.
- **Consequence for liveness**: in `scratch-pad-redirect.sh`, `$$` is the PreToolUse hook process's own pid, which exits right after emitting its JSON — so redirect files are dead-pid on arrival and the live-pid guard only ever protects via pid recycling. `write_snapshot` files likewise carry the already-exiting `ll-verify-evidence` pid. This is why every such file is immediately sweep-eligible and why accumulation is purely a throughput problem. (Same eligibility is the root of BUG-3702; relation recorded in frontmatter.)


## Session Log
- `/ll:confidence-check` - 2026-10-03T08:32:12 - `bb60645b-4c2c-4059-9593-4feaa83c6070.jsonl`
- `/ll:wire-issue` - 2026-10-03T08:30:04 - `b1db8e5c-4be0-4d16-bc71-7a863a1daa3f.jsonl`
- `/ll:refine-issue` - 2026-10-03T08:24:06 - `7c0a7319-78e5-4f96-858b-d6064cc6aba9.jsonl`
