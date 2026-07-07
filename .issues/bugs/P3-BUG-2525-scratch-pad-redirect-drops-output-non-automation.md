---
id: BUG-2525
title: Scratch-pad redirect drops output file outside automation context
type: BUG
priority: P3
status: done
discovered_date: 2026-07-07
completed_at: 2026-07-07 19:03:08+00:00
discovered_by: capture-issue
testable: false
decision_needed: false
confidence_score: 95
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

## Summary

The scratch-pad pattern `mkdir -p .loops/tmp/scratch && <command> > .loops/tmp/scratch/<name>.txt 2>&1` exits 0 but the output file is absent after the command completes when run from a non-automation Claude Code session. CLAUDE.md documents that "the explicit `mkdir -p` makes the command self-sufficient even when the hook doesn't fire" — it does not: the file disappears, the `> redirect` succeeds, and `echo $?` lies about success.

## Current Behavior

```bash
$ mkdir -p .loops/tmp/scratch && python -m pytest scripts/tests/ --tb=short -q > .loops/tmp/scratch/test-results.txt 2>&1; echo "EXIT_CODE=$?"
EXIT_CODE=0
$ ls -la .loops/tmp/scratch/
ls: .loops/tmp/scratch/: No such file or directory
```

Exit code 0 indicates success, but the scratch directory itself is gone — meaning the `scratch-pad-redirect` hook (or a session-cleanup hook) wiped `.loops/tmp/` after the command finished. The user gets no output and no error.

## Expected Behavior

Either:

1. The scratch-pad pattern should work as documented: the `> .loops/tmp/scratch/<name>.txt` redirect should produce a persistent file the user can `Read` afterward, OR
2. The bash command should exit non-zero (or emit a warning to stderr) when the scratch dir is wiped by a hook, so the user knows to use a different path, OR
3. CLAUDE.md should be updated to clarify the pattern is unreliable outside automation mode and recommend `/tmp/` or a project-root path instead.

## Motivation

The scratch-pad pattern is the recommended way to keep large command output out of conversation context (CLAUDE.md: "For test/lint runs and other large command output, pipe to scratch and tail the summary"). If the pattern silently loses output, it is worse than not using it — the user assumes the file exists, navigates to it, and finds nothing.

## Proposed Solution

Two options:

- **Fix the pattern** — make the `mkdir -p` + redirect self-sufficient by adding a `chmod` or `touch` to anchor the file, or change the cleanup hook to only sweep `*.tmp` patterns, not the whole `.loops/tmp/` directory.
- **Fix the documentation** — clarify that the scratch-pad pattern is automation-only and recommend `/tmp/<name>.txt` for manual use.

The structural fix is to ensure the cleanup hook preserves files the user explicitly created via redirect. A user-intent-aware cleanup (e.g., only sweep `*.pid` or files older than N hours) would solve it without losing the auto-cleanup benefit.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The two options above are correct in spirit, but research uncovered a third, more targeted option that aligns with existing codebase conventions. **Three options are now on the table** — `decision_needed: true` (see frontmatter).

- **Option A — Gate `scratch-cleanup.sh` on `automation_contexts_only`** (mirror the redirect hook)
  - Add at the top of `hooks/scripts/scratch-cleanup.sh` (after `ll_resolve_config`):
    ```bash
    if ! ll_feature_enabled "scratch_pad.enabled"; then exit 0; fi
    AUTO_ONLY=$(ll_config_value "scratch_pad.automation_contexts_only" "true")
    if [ "$AUTO_ONLY" = "true" ] && [ "${LL_NON_INTERACTIVE:-}" != "1" ]; then
        exit 0
    fi
    ```
  - Caveat: `SessionEnd` does not pass a `permission_mode` payload, so the gate must use `LL_NON_INTERACTIVE` (set by `scripts/little_loops/host_runner.py:264, 308, 329, 507, 558, 581` on all host builds) instead. This requires `host_runner.py` to also export `LL_NON_INTERACTIVE=1` for the `SessionEnd` subprocess, or the user to opt in via env.
  - Pro: aligns the cleanup with the existing redirect semantics, single semantic model, smallest code change to a single file.
  - Con: depends on a host-side env var that is not currently exported to `SessionEnd` hooks; needs `host_runner.py` updates or a parallel gate.

- **Option B — Preserve user-typed files (filename shape)**
  > **Selected:** Option B — Preserve user-typed files (filename shape) — Inverts the cleanup contract to match the existing `kill -0` PID-liveness intent; reuses all primitives; Option A's gate is inert in interactive sessions, Option C leaves the bug in place.
  - Change the sweep in `hooks/scripts/scratch-cleanup.sh:30–48` to only `rm -f` files whose name matches `.*-[0-9]+\.[^.]+$` (the PID-suffix shape produced by `scratch-pad-redirect.sh:105`). User-typed files without a `-<pid>` tail are skipped unconditionally.
  - This piggy-backs on the existing `kill -0` liveness check (line 36–38) — the same regex that extracts the PID becomes the only files eligible for removal.
  - Pro: no config gating needed, no host env var, no signal coupling. Always preserves user-typed files. The cleanup then has a clear contract: "I only clean up files this tool itself created."
  - Con: a user who types `pytest-12345.txt` (accidentally matching the shape) would have their file swept when PID 12345 dies. Low risk in practice — PIDs are 32-bit, collision is rare.

- **Option C — Documentation only**
  - Update `.claude/CLAUDE.md:244–250` to remove the misleading "the explicit `mkdir -p` makes the command self-sufficient even when the hook doesn't fire" line, and recommend `/tmp/<name>.txt` (or `${TMPDIR:-/tmp}/ll-scratch-<name>.txt`) for manual scratch use.
  - Pro: smallest change, no code path touched.
  - Con: doesn't actually fix the bug; the misleading line and pattern remain available; the user still has to know to use `/tmp/` instead of the documented pattern.

**Recommended (research)**: Option B is the most robust fix because it inverts the cleanup's contract from "I sweep everything in the scratch dir" to "I sweep only files this hook created" — which is the original intent per the `kill -0` liveness check added in BUG-2438. Option A is the most *consistent* with the existing redirect-hook semantics but introduces a host env-var coupling. Option C is a stopgap that leaves the misleading pattern in place.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-07.

**Selected**: Option B — Preserve user-typed files (filename shape)

**Reasoning**: Option B directly addresses the bug by inverting the cleanup hook's contract from "sweep everything in the scratch dir" to "sweep only files this hook created" (the original intent per the `kill -0` PID-liveness check added in BUG-2438). It is a 2-line filter swap reusing the existing PID-extraction regex at `scratch-cleanup.sh:36`. Option A's `LL_NON_INTERACTIVE` gate is structurally inert in interactive sessions — exactly where BUG-2525 manifests — because `SessionEnd` subprocesses do not inherit `LL_NON_INTERACTIVE` from the parent `claude` CLI; the sibling `session_start.py:149` defensive gate shows the codebase already knows this signal is unreliable. Option C leaves the cleanup hook's behavior unchanged and shifts the burden to the user to read a warning; the recipe at `skills/manage-issue/SKILL.md:374` would still teach the broken pattern.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A — Config-gated cleanup | 2/3 | 2/3 | 1/3 | 0/3 | 5/12 |
| Option B — Filename-shape sweep | 3/3 | 3/3 | 2/3 | 2/3 | 10/12 |
| Option C — Documentation only | 1/3 | 3/3 | 2/3 | 1/3 | 7/12 |

**Key evidence**:
- Option A: Helpers (`ll_feature_enabled`, `ll_config_value`) and the canonical sibling gate exist (`scratch-pad-redirect.sh:52-60`), but the load-bearing `permission_mode` signal is absent from `SessionEnd` payloads and `LL_NON_INTERACTIVE=1` is only exported by `host_runner.build_*` to its spawned subprocess, never to a SessionEnd hook in an interactive session. The gate would be inert in the exact scenario BUG-2525 covers.
- Option B: Reuses the existing `kill -0` regex `.*-([0-9]+)\.[^.]+$` at `scratch-cleanup.sh:36` and the `kill -0 "$pid"` liveness check at line 37 directly. Only one test contradicts (`test_scratch_cleanup_removes_dir_when_present` at `test_hooks_integration.py:2557-2570`); it must be inverted. The PID-suffix shape `${SAFE_NAME}-$$.txt` is the only documented writer convention (`scratch-pad-redirect.sh:103-105`); no other code path writes to `.loops/tmp/scratch/` outside this convention.
- Option C: Pure-textual edit; `skills/manage-issue/SKILL.md:370-374` still teaches the broken `mkdir -p .loops/tmp/scratch && ... > .loops/tmp/scratch/<name>.txt` recipe; the cleanup hook still sweeps user-typed files; the user-facing bug premise (followed docs, lost output) is not eliminated.

## Steps to Reproduce

1. From repo root, run `mkdir -p .loops/tmp/scratch && python -m pytest scripts/tests/ --tb=short -q > .loops/tmp/scratch/test-results.txt 2>&1; echo "EXIT_CODE=$?"` from a non-automation Claude Code session.
2. After the command completes, run `ls -la .loops/tmp/scratch/`.
3. Observe: `No such file or directory`. The scratch dir has been removed by a hook.

## Root Cause

- **File**: `hooks/hooks.json` (or the hook implementation registered for session cleanup)
- **Anchor**: the session-end / post-tool-use hook that sweeps `.loops/tmp/`
- **Cause**: The cleanup hook removes `.loops/tmp/` (or `.loops/tmp/scratch/`) on session boundary or post-command, wiping files the user explicitly created with `> redirect`. The hook fires in all modes, not just automation.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **File (precise)**: `hooks/scripts/scratch-cleanup.sh` — a pure-bash `SessionEnd` handler (NOT a Python intent handler under `scripts/little_loops/hooks/`). The Python dispatch table at `scripts/little_loops/hooks/__init__.py:_dispatch_table` (lines 74–99) does not register scratch cleanup; only `sweep_stale_refs.handle` is bound to `session_end`.
- **Anchor**: `hooks/scripts/scratch-cleanup.sh:30–48` — the sweep body iterates `.loops/tmp/scratch/*`, extracts a `-<pid>` segment via `sed -nE 's/.*-([0-9]+)\.[^.]+$/\1/p'`, calls `kill -0 "$pid"` to liveness-check the writing process, then `rm -f`s files whose owning PID is gone, finally `rmdir`ing the dir when empty.
- **Cause (precise)**: The hook fires on every `SessionEnd`, not just automation. It reads no config, checks no `permission_mode`, never inspects `scratch_pad.automation_contexts_only`. The sibling redirect hook `hooks/scripts/scratch-pad-redirect.sh:57–60` honors that flag (returns `allow_response` when `PERM_MODE != bypassPermissions` and `automation_contexts_only == true`), but the cleanup hook does not — a key asymmetry that produces BUG-2525.
- **Why a user-typed `test-results.txt` is unconditionally removed**: The cleanup regex requires a `-<pid>` segment to short-circuit on a live owner. A user-typed `> .loops/tmp/scratch/test-results.txt` has no such suffix, so the regex returns empty, `kill -0` is skipped, and `rm -f "$f"` runs (line 41). The `rmdir` (line 45, guarded by `|| true`) then removes the empty directory — the exact `ls: .loops/tmp/scratch/: No such file or directory` symptom.
- **Migration history**: This script was carved out of `session-cleanup.sh` per BUG-2420 (the original cleanup ran on `Stop`, every turn, double-firing the sweep) and now lives on `SessionEnd`. PID-liveness was added per BUG-2438 to fix a blind `rm -rf` race against concurrent sessions. Neither fix considered the case where a user manually creates a scratch file outside the redirect hook.
- **Registration**: `hooks/hooks.json:188–199` binds `SessionEnd → scratch-cleanup.sh` with `timeout: 5` and `statusMessage: "Cleaning up scratch pad..."`. There is no `permission_mode` payload passed to `SessionEnd` hooks — that's why the cleanup cannot use the same `PERM_MODE` gate the redirect hook uses.

## Location

- **File**: `hooks/hooks.json` (or the corresponding implementation under `scripts/little_loops/hooks/`)
- **Anchor**: the cleanup hook intent that removes `.loops/tmp/`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Primary site**: `hooks/scripts/scratch-cleanup.sh` (the `SessionEnd` cleanup script that performs the sweep)
- **Wiring**: `hooks/hooks.json:188–199` (the `SessionEnd` block binding `scratch-cleanup.sh`)
- **Config (currently unused)**: `config-schema.json:763–802` declares `scratch_pad.automation_contexts_only` (default `true`); only the redirect hook reads it today
- **Active project config**: `.ll/ll-config.json:30–54` sets `scratch_pad.automation_contexts_only: true`
- **Helper functions available for the fix** (in `hooks/scripts/lib/common.sh`):
  - `ll_resolve_config` (line 184) — sets `LL_CONFIG_FILE`
  - `ll_feature_enabled "section.enabled"` (line 198) — returns 0/1 from jq
  - `ll_config_value "path.to.key" "default"` (line 218) — prints value or fallback
- **Test file (existing)**: `scripts/tests/test_hooks_integration.py:2572–2623` — `TestScratchCleanup` class already covers PID-liveness behavior; the fix should add a sibling test for the "no PID suffix" preserve case

## Implementation Steps

1. Identify the hook responsible for cleaning `.loops/tmp/` (search `hooks/hooks.json` and `scripts/little_loops/hooks/` for path patterns matching `.loops/tmp`).
2. Update the hook to:
   - Only sweep files matching known transient patterns (e.g., `*.tmp`, `*.pid`, `*.lock`), OR
   - Only sweep on session-end, not post-command, OR
   - Skip files modified within the last N minutes (preserves active scratch files).
3. Update `CLAUDE.md` § "Automation: Scratch Pad" to reflect the actual semantics.
4. Verify by running the pattern in a non-automation session and confirming the file persists for `Read`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The Implementation Steps above are correct in shape but the "Identify" step is now done. Replace the abstract enumeration with the concrete site.

1. **Locate the cleanup hook (already done by this refinement)**: `hooks/scripts/scratch-cleanup.sh` — the bash `SessionEnd` handler at `hooks/hooks.json:188–199`. NOT under `scripts/little_loops/hooks/` (the Python intent-dispatch table at `__init__.py:74–99` has no entry for scratch cleanup).
2. **Pick a fix strategy** (see `## Proposed Solution` — three options have been deposited by this refinement; run `/ll:decide-issue BUG-2525` after this issue is ready):
   - **Option 1 (gate cleanup)**: add an `ll_feature_enabled`/`ll_config_value` block at the top of `scratch-cleanup.sh` that bails out when `scratch_pad.automation_contexts_only == true` and the host is not in automation. Caveat: `SessionEnd` does not pass a `permission_mode` payload, so the gate must use a different signal — either `LL_NON_INTERACTIVE` env var (set by `scripts/little_loops/host_runner.py:264, 308, 329, 507, 558, 581`) or a static "skip in interactive" rule.
   - **Option 2 (preserve user files)**: change the sweep to only `rm -f` files whose filename matches `.*-[0-9]+\.[^.]+$` (the PID-suffix shape that `scratch-pad-redirect.sh:105` produces). User-typed files without that suffix are skipped unconditionally. Simplest fix; aligns with the existing `kill -0` liveness check.
   - **Option 3 (docs only)**: leave the sweep alone; update `.claude/CLAUDE.md:244–250` to recommend `/tmp/<name>.txt` for manual use and remove the misleading "the explicit `mkdir -p` makes the command self-sufficient even when the hook doesn't fire" line.
3. **Implement the chosen fix in `hooks/scripts/scratch-cleanup.sh`** — follow the existing `must-NEVER-fail` convention (every op wrapped in `2>/dev/null || true`, final `exit 0`). Use the `kill -0` liveness pattern at `hooks/scripts/scratch-cleanup.sh:36–38` as the model.
4. **Add a test** to `scripts/tests/test_hooks_integration.py` following the `TestScratchCleanup` class (lines 2572–2623). Recommended: `test_scratch_cleanup_preserves_file_without_pid_suffix` that creates a `test-results.txt` with no `-<pid>` tail, runs the cleanup, and asserts the file (and its parent dir) survive.
5. **Update `.claude/CLAUDE.md:244–250`** ("Automation: Scratch Pad" section) to reflect the new behavior — note the chosen semantics in the "next steps" line.
6. **Update `docs/guides/BUILTIN_HOOKS_GUIDE.md:345–349`** (the `scratch-cleanup` section) if Option 1 or 2 changes the sweep behavior.
7. **Update `docs/reference/CONFIGURATION.md:898`** — the `scratch_pad.automation_contexts_only` row — to mention cleanup, not just redirection, if Option 1 is chosen.
8. **Update `config-schema.json:779–783`** — broaden the `automation_contexts_only` description to cover both layers.
9. **Run the full test suite**: `python -m pytest scripts/tests/test_hooks_integration.py -v -k Scratch` (and then the full suite per the project's CI policy in `.claude/CLAUDE.md`).
10. **Verify the reproduction** (from § Steps to Reproduce) in a non-automation session — the file should persist for `Read`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation. Tackle them after the chosen fix lands in `hooks/scripts/scratch-cleanup.sh`:_

11. **Doc listing gaps** (resolved as part of any fix):
    - Update `docs/ARCHITECTURE.md:100–110` to enumerate `scratch-cleanup.sh` alongside `scratch-pad-redirect.sh` (pre-existing oversight from BUG-2420).
    - Update `docs/development/TROUBLESHOOTING.md:894` to add `scratch-cleanup.sh` to the `chmod +x` list (cosmetic, but consistent with the rest of the recipe).

12. **Rewrite the contradicting test (Option B only)** — replace or invert `scripts/tests/test_hooks_integration.py:2557–2570` (`test_scratch_cleanup_removes_dir_when_present`); the existing assertion `assert not scratch.exists()` directly contradicts Option B's contract. The cleanest fix: delete it and add `test_scratch_cleanup_preserves_file_without_pid_suffix` (modeled on `test_scratch_cleanup_removes_file_owned_by_dead_process` at line 2595).

13. **Add a config-toggle test (Option A only)** — `test_scratch_cleanup_skips_when_automation_contexts_only` in `TestScratchCleanupSessionEnd` after line 2611, using `TestScratchPadRedirect._write_config` helper at `scripts/tests/test_hooks_integration.py:2141–2155`. Pair with a fallback test (`test_scratch_cleanup_handles_missing_config_gracefully`) that asserts no-config defaults to "run cleanup" — critical because `SessionEnd` has no `permission_mode` payload and interactive sessions have no `LL_NON_INTERACTIVE=1` exported, so any gate must degrade gracefully to not silently break other consumers.

14. **Cross-check init registration** — confirm no change is required in `scripts/little_loops/init/{tui,cli,writers,core}.py` because none of them reads `scratch_pad.automation_contexts_only` in Python (verified by Agent 1). If a new schema property is introduced, update `scripts/little_loops/init/core.py:157–159` to write the default; otherwise skip.

15. **Cross-host confirmation** — no Codex or opencode adapter change required. The Codex adapter at `scripts/little_loops/hooks/adapters/codex/hooks.json` and the opencode plugin do not register any scratch-cleanup equivalent. Document this confirmation in the PR description so reviewers don't ask for parity work.

## Integration Map

### Files to Modify
- `hooks/hooks.json` — adjust the cleanup hook's path filter
- `scripts/little_loops/hooks/` — the Python handler that performs the sweep
- `.claude/CLAUDE.md` — clarify the scratch-pad pattern's reliability

### Tests
- A new test under `scripts/tests/` that exercises the scratch-pad pattern and asserts the file persists.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The original Integration Map listed `scripts/little_loops/hooks/` as the location of the Python handler. This is **inaccurate** — the actual handler is a pure-bash script under `hooks/scripts/`. The Python intent-dispatch framework (`scripts/little_loops/hooks/__init__.py:_dispatch_table` lines 74–99) does not implement scratch-pad redirect or cleanup; both are bash under `hooks/scripts/`.

**Files to Modify (corrected):**

- `hooks/scripts/scratch-cleanup.sh` — gate the sweep on `scratch_pad.automation_contexts_only` (mirroring `scratch-pad-redirect.sh:57–60`), OR change the sweep to preserve user-typed files (no `-<pid>` suffix) regardless of mode
- `hooks/hooks.json:188–199` — only edit if the chosen fix changes which event the hook binds to
- `.claude/CLAUDE.md:244–250` (the "Automation: Scratch Pad" section) — clarify the actual semantics for interactive users
- `docs/guides/BUILTIN_HOOKS_GUIDE.md:345–349` (the scratch-cleanup section) — update if behavior changes
- `docs/reference/CONFIGURATION.md:898` (the `automation_contexts_only` description) — broaden scope from "redirection" to "redirection AND cleanup" if Option 1 is chosen

**Dependent Files (Callers/Importers):**

- `hooks/scripts/lib/common.sh:198–234` — `ll_feature_enabled` / `ll_config_value` are the only config read paths used by sibling hooks; `scratch-cleanup.sh` currently calls neither
- `hooks/scripts/scratch-pad-redirect.sh:105` — creates files of the form `${SAFE_NAME}-$$.txt`; the cleanup relies on the `-<pid>` suffix for ownership, which the user-typed pattern doesn't provide
- `scripts/little_loops/init/core.py:157–159` — `build_config` writes the `scratch_pad` block when enabled; no change needed unless defaults change

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/init/tui.py:27, 47, 89, 654, 788` — TUI labels `scratch_pad` ("Scratch pad (automation context masking)") and surfaces the enable flag during `ll-init`. Registration only — neither file reads `scratch_pad.automation_contexts_only` from Python. No change needed under any option. [Agent 1 finding]
- `scripts/little_loops/init/cli.py:27, 381, 598, 652` — `--enable scratch_pad` allowlist and the re-init prompt that consults existing `scratch_pad.enabled`. Same constraint as `tui.py`: no code path reads `automation_contexts_only`. [Agent 1 finding]
- `scripts/little_loops/init/writers.py:132` — preserves user-set `scratch_pad` sub-config across re-inits so that an `automation_contexts_only` flip set after `ll-init` survives a subsequent re-run. No change needed. [Agent 1 finding]
- `scripts/little_loops/subprocess_utils.py:248–266` — `_list_scratch_files()` reads `Path(".loops/tmp/scratch")` to feed the guillotine prompt; tolerates an empty or missing dir (`return "None"` at line 252). Safe under any option — the dir existing, being absent, or being empty all yield correct output. [Agent 2 finding]
- `scripts/little_loops/issue_manager.py:375` and `scripts/little_loops/parallel/worker_pool.py:986` — both emit resume-hint templates that include the literal `"3. Review \`.loops/tmp/scratch/\` for partial progress notes"`. String-constant only; refers to the directory, not its contents. No change needed. [Agent 2 finding]
- `scripts/little_loops/fsm/handoff_handler.py:122` — comment-only reference that uses `scratch-pad-redirect` as the canonical example of an `automation_contexts_only`-gated hook. Useful context if Option A is chosen (cleaner to mirror what the codebase already documents as the established pattern). [Agent 1 finding]
- No cross-host replication required. `scripts/little_loops/hooks/adapters/codex/hooks.json` and `hooks/adapters/opencode/` do **not** register any `scratch-cleanup.sh` equivalent — the `SessionEnd`-equivalent handlers in those adapters are bound to different intents (`sweep_stale_refs.handle`). The fix only needs to land in the Claude Code `hooks/scripts/scratch-cleanup.sh`. [Agent 1 + Agent 2 finding] — **critical constraint** for Option A: `SessionEnd` fires inside the Claude Code process and **does not** receive a `permission_mode` payload, and the user's own interactive session has no `LL_NON_INTERACTIVE=1` exported. An `LL_NON_INTERACTIVE`-gated sweep would therefore never bail out in the exact scenario BUG-2525 covers; the env-var path proposed in Option A would be inert for this bug.

**Similar Patterns:**

- `hooks/scripts/scratch-pad-redirect.sh:52–60` — the canonical example of the `automation_contexts_only` gate. Reads `PERM_MODE` from the JSON stdin payload, bails out when `AUTO_ONLY == "true"` and `PERM_MODE != "bypassPermissions"`. Cleanup can't read this payload (`SessionEnd` doesn't provide it), so the cleanup must use a different signal.
- `hooks/scripts/session-cleanup.sh:7–9, 11–57` — sibling `Stop`-event cleanup that *explicitly does not* touch scratch (after BUG-2420 removed that behavior). Useful as a model for "scope-limited cleanup" if Option 3 is chosen.
- `scripts/little_loops/fsm/concurrency.py:204, 250` and `scripts/little_loops/fsm/persistence.py:1088–1095` — both use `kill -0 <pid>` liveness with filename-encoded ownership (`.lock`, `.pid`).

**Tests (existing and needed):**

- `scripts/tests/test_hooks_integration.py:2133+` — `TestScratchPadRedirect` covers the rewrite side
- `scripts/tests/test_hooks_integration.py:2572–2610` — `TestScratchCleanup` covers PID-liveness; `test_scratch_cleanup_preserves_file_owned_by_live_process` (live PID kept), `test_scratch_cleanup_removes_file_owned_by_dead_process` (`2**31-1` killed) — model for the new test
- `scripts/tests/test_config_schema.py:30–37` — schema-default regression test for `scratch_pad` block
- `scripts/tests/test_hook_session_start.py:240–340` — pattern for `LL_NON_INTERACTIVE` env-var gating tests (relevant if Option 4 below is chosen)
- **New test needed**: `test_scratch_cleanup_preserves_file_without_pid_suffix` — assert a user-typed `test-results.txt` (no `-<pid>` tail) survives the sweep when `automation_contexts_only: true` is in effect

_Wiring pass added by `/ll:wire-issue`:_

**Established test patterns to model on:**

- The class actually housing the cleanup tests is `TestScratchCleanupSessionEnd` at `scripts/tests/test_hooks_integration.py:2512` (the issue text refers to it as `TestScratchCleanup` — both names point to the same class). Subprocess fixture pattern: `script = self.REPO_ROOT / "hooks/scripts/scratch-cleanup.sh"` + `monkeypatch.chdir(tmp_path)` + `subprocess.run([str(script)], input="{}", capture_output=True, text=True, timeout=5)`. The `input="{}"` payload is the empty `SessionEnd` JSON stdin that bash hooks read. [Agent 3 finding]
- Config-toggle pattern: `TestScratchPadRedirect._write_config(...)` helper at `scripts/tests/test_hooks_integration.py:2141–2155` is the canonical way to drop a `tmp_path/.ll/ll-config.json` with a chosen `scratch_pad` block. Mirror this helper (or import it) for any new test that wants to assert behavior gated on `scratch_pad.automation_contexts_only`. [Agent 3 finding]
- `test_hook_session_start.py:240–340` uses `monkeypatch.delenv("LL_NON_INTERACTIVE", raising=False)` for cleanup, **not** for assertion — it is not the canonical config-toggle pattern. Don't model new env-var tests on it. [Agent 3 finding]

**Existing tests to update (Option B):**

- `scripts/tests/test_hooks_integration.py:2557–2570` — `test_scratch_cleanup_removes_dir_when_present` **directly contradicts Option B**. It writes `x.txt` (no PID suffix) into `.loops/tmp/scratch` and asserts `assert not scratch.exists()` at line 2570. Under Option B the file (and dir) must survive. Action: rewrite to assert the file IS preserved, or delete it and add `test_scratch_cleanup_preserves_file_without_pid_suffix` alongside. **Critical test to address before landing Option B** — this is the single largest implementation risk the wiring pass surfaced. [Agent 2 + Agent 3 finding]

**Tests that may need updates (Option A):**

- `scripts/tests/test_hooks_integration.py:2530–2545` — `test_scratch_cleanup_script_prunes_scratch` does a structural check: `"assert \"kill -0\" in text"` (line 2542). If Option A replaces the PID sweep entirely with a config-gated early-return, this test breaks; otherwise it stays green. [Agent 3 finding]
- `scripts/tests/test_hooks_integration.py:2518` — `test_session_cleanup_no_longer_removes_scratch` asserts `session-cleanup.sh` does NOT touch scratch. Independent of any option; remains green. [Agent 3 finding]
- `scripts/tests/test_config_schema.py:28–37` — `test_scratch_pad_properties`. Only needs extension under Option A if a NEW schema property is introduced (e.g., `cleanup_preserve_user_files`). Reusing `automation_contexts_only` does not require extending this test. [Agent 3 finding]

**New tests needed:**

- `scripts/tests/test_hooks_integration.py` (in `TestScratchCleanupSessionEnd`, after line 2611) — `test_scratch_cleanup_preserves_file_without_pid_suffix`: create `test-results.txt` with no `-<pid>` tail, run cleanup, assert both the file and the dir survive. Model on `test_scratch_cleanup_removes_file_owned_by_dead_process` (line 2595). [Agent 1 + Agent 3 finding]
- (Option A only) `scripts/tests/test_hooks_integration.py` — `test_scratch_cleanup_skips_when_automation_contexts_only`: write `_write_config(tmp_path, automation_contexts_only=True)` (model on `TestScratchPadRedirect._write_config` at line 2141), create `pytest-{dead_pid}.txt`, run cleanup, assert file and dir survive. Pair with a second test that drops `automation_contexts_only=False` and asserts the same dead-PID file IS removed. [Agent 3 finding]
- (Option A only) `scripts/tests/test_hooks_integration.py` — `test_scratch_cleanup_handles_missing_config_gracefully`: run the script with no `.ll/ll-config.json` present (the default path), assert it falls back to "run cleanup" semantics, not the gated semantics. Confirms the gate doesn't accidentally break the no-config case for non-automation users. [Agent 3 finding] — **derived from the env-var-coupling finding above**: since `SessionEnd` lacks `permission_mode` payload and an interactive session has no `LL_NON_INTERACTIVE=1`, the gate must default to "run cleanup" when no config is present to avoid silently breaking other consumers.

**Init-path tests that should NOT need updates:**

- `scripts/tests/test_init_core.py:580–592` — `test_scratch_pad_omitted_by_default`, `test_scratch_pad_written_when_enabled`. No change; init writes only `enabled: True`.
- `scripts/tests/test_init_core.py:1621–1624` — headless `--enable scratch_pad` plan path. No change.
- `scripts/tests/test_init_tui.py:810–842` — TUI scratch-pad toggle round-trip. No change. [Agent 1 finding]

**Registration cross-checks:**

- `scripts/tests/test_hooks_integration.py:2612–2623` — `test_hooks_json_registers_session_end_scratch_cleanup` asserts the `SessionEnd → scratch-cleanup.sh` binding is preserved. No change unless the fix changes which event the hook binds to. [Agent 3 finding]
- `scripts/tests/test_hooks_integration.py:2516–2528` — `test_session_cleanup_does_not_touch_scratch_dir` confirms `session-cleanup.sh` does NOT touch scratch (post-BUG-2420 invariant). No change.

**Configuration:**

- `config-schema.json:763–802` — `scratch_pad` schema. If Option 1 (gate cleanup on `automation_contexts_only`) is chosen, the description of `automation_contexts_only` (line 779–783) must be broadened to mention cleanup, not just redirection.
- `.ll/ll-config.json:30–54` — current project config has `scratch_pad.automation_contexts_only: true`, so the fix should take effect immediately without config changes.

_Wiring pass added by `/ll:wire-issue`:_

**Schema constraints discovered:**

- `config-schema.json:804` — `additionalProperties: false` on the `scratch_pad` block. Any new key under `scratch_pad` (e.g., a separate `cleanup_preserve_user_files` switch) would be rejected by schema validation. Option A reusing `automation_contexts_only` doesn't need to extend the schema; Option A introducing a NEW switch does. [Agent 2 finding]
- `scripts/little_loops/init/core.py:94` — docstring-level `scratch_pad_enabled` mention only; the writer at line 157–159 sets `{"enabled": True}` and nothing else. Option A would not change init defaults; Option B definitely does not. [Agent 1 finding]

**Init registration sites that do NOT need updates:**

- `scripts/little_loops/init/tui.py:27, 47, 89, 654, 788` — TUI checkbox + label for scratch_pad. Surface only; reads no config.
- `scripts/little_loops/init/cli.py:27, 381, 598, 652` — `--enable scratch_pad` allowlist.
- `scripts/little_loops/init/writers.py:132` — preserves user-set scratch_pad sub-config across re-inits.

None of these read `scratch_pad.automation_contexts_only` in Python; only the bash hooks do. [Agent 1 finding] — **registration correctness**: the active project's `.ll/ll-config.json:30–54` already sets `automation_contexts_only: true`, so Option A would take effect immediately under default config. Option B requires no config change at all.

**Documentation:**

- `.claude/CLAUDE.md:244–250` — the section the user reads when learning the scratch-pad pattern. The phrase "the explicit `mkdir -p` makes the command self-sufficient even when the hook doesn't fire" is the misleading line.
- `docs/guides/BUILTIN_HOOKS_GUIDE.md:345–349` — the scratch-cleanup section in the hook guide
- `docs/reference/CONFIGURATION.md:898` — the `automation_contexts_only` config table entry

_Wiring pass added by `/ll:wire-issue`:_

**Doc gaps surfaced by the wiring pass:**

- `docs/ARCHITECTURE.md:100–110` — hook scripts directory listing. Line 105 currently lists only `scratch-pad-redirect.sh`; `scratch-cleanup.sh` is **not** enumerated despite BUG-2420 carving it out of `session-cleanup.sh`. This is a pre-existing oversight that any fix to BUG-2525 should resolve as part of landing. [Agent 2 finding]
- `docs/development/TROUBLESHOOTING.md:894` — manual exercise recipe; the `chmod +x` list at line 894 includes `scratch-pad-redirect.sh` but omits `scratch-cleanup.sh`. Cosmetic but consistent — add it. [Agent 2 finding]
- `docs/guides/GETTING_STARTED.md:93` and `docs/reference/CLI.md:50, 73` — `--enable` feature lists that mention `scratch_pad` by name. Cosmetic only; no behavior described here couples to the cleanup semantics. [Agent 1 finding]
- `docs/reference/CONFIGURATION.md:178` — example config block containing a `scratch_pad` snippet. Cosmetic; the example block is illustrative and the table row at 898 is the authoritative source. [Agent 1 finding]

**Cross-host documentation:**

- `docs/reference/HOST_COMPATIBILITY.md:260` — confirms `.loops/tmp/scratch/` is the same path across Claude Code, Codex, and opencode. **No change required for cross-host**, because the Codex and opencode adapters do NOT register a `scratch-cleanup.sh` equivalent (see Dependent Files subsection). The fix is scoped to Claude Code's `SessionEnd` binding alone. [Agent 2 finding]

**Skill that actively teaches the broken pattern (consumer of the docs):**

- `skills/manage-issue/SKILL.md:370–374` — headless automation tail-rec with literal recipe `mkdir -p .loops/tmp/scratch && {{config.project.test_cmd}} > .loops/tmp/scratch/test-results.txt 2>&1; tail -20 ...`. This is the **canonical documented example** of the pattern BUG-2525 reports as silently broken. If the fix lands, this skill body becomes valid again without edits; if Option C (docs only) lands, this skill would need to point to `/tmp/<name>.txt` instead. [Agent 1 finding]

**Existing misleading line confirmed:**

- `.claude/CLAUDE.md:247` (within the `244–250` block above) — the exact phrase `"...the explicit \`mkdir -p\` makes the command self-sufficient even when the hook doesn't fire..."` is what BUG-2525 explicitly refutes. Must change under all three options. [Agent 2 finding] (also confirmed by Agent 1).

## Impact

Low-severity user-experience bug. Developers using `/ll:run-tests` (or any command with large output) in non-automation mode will hit this and lose test output. The pattern is documented as the recommended approach, so the failure is misleading.

## Related Key Documentation

- `.claude/CLAUDE.md` § "Automation: Scratch Pad"

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `.claude/CLAUDE.md:244–250` — the section the user reads when learning the pattern. The phrase "the explicit `mkdir -p` makes the command self-sufficient even when the hook doesn't fire" is the misleading line.
- `docs/guides/BUILTIN_HOOKS_GUIDE.md:213–227` (scratch-pad redirect section) and `:345–349` (scratch-cleanup section) — hook guide that pairs with the implementation
- `docs/reference/CONFIGURATION.md:891–898` — `scratch_pad` config table, including the `automation_contexts_only` row
- `config-schema.json:763–802` — JSON Schema source of truth for the `scratch_pad` block
- `.issues/bugs/P2-BUG-2420-scratch-pad-redirect-stop-hook-race-and-double-wrap.md` — the previous fix that moved scratch cleanup from `Stop` to `SessionEnd` and carved out `scratch-cleanup.sh` from `session-cleanup.sh`
- `.issues/bugs/P2-BUG-2438-scratch-cleanup-blind-rm-rf-races-concurrent-sessions.md` — the previous fix that added the `kill -0` PID-liveness check
- `.issues/bugs/P2-BUG-2491-scratch-pad-redirect-masks-wrapped-command-exit-code.md` — sibling issue about exit-code masking (related, not a duplicate)
- `.issues/enhancements/P3-ENH-1111-scratch-pad-enforcement-pretooluse-hook.md` — related enhancement about pretooluse enforcement

## Status

done

## Resolution

Implemented Option B (preserve user-typed files via filename shape) from the
research findings. Changed `hooks/scripts/scratch-cleanup.sh` so the sweep
loop's first guard is `[ -n "$pid" ] || continue` — files without the
`${SAFE_NAME}-<pid>.txt` shape that `scratch-pad-redirect.sh:103-105` produces
are now preserved unconditionally. The `kill -0` PID-liveness check (BUG-2438
invariant) still runs for files that DO match the shape, so concurrent-session
collisions remain guarded against.

Files changed:
- `hooks/scripts/scratch-cleanup.sh` — inverted cleanup contract; documents new behavior in the header comment
- `scripts/tests/test_hooks_integration.py` — replaced `test_scratch_cleanup_removes_dir_when_present` (which contradicted the new contract) with `test_scratch_cleanup_preserves_file_without_pid_suffix`
- `.claude/CLAUDE.md:247` — replaced misleading "explicit `mkdir -p` makes the command self-sufficient" line with accurate description of the PID-suffix contract
- `docs/guides/BUILTIN_HOOKS_GUIDE.md:349` — documented that only `-<pid>`-suffixed files are eligible for removal
- `docs/ARCHITECTURE.md:105` — added `scratch-cleanup.sh` to the hook scripts listing (pre-existing oversight from BUG-2420)
- `docs/development/TROUBLESHOOTING.md:914` — added `chmod +x hooks/scripts/scratch-cleanup.sh` to the recipe (pre-existing omission)

Verification: full suite (14148 tests, 35 skipped) passes; targeted `-k Scratch` runs all 24 tests including the new `test_scratch_cleanup_preserves_file_without_pid_suffix`.

## Session Log
- `/ll:confidence-check` - 2026-07-07T18:55:00Z - `a70a919a-409b-4074-81ca-a32b68be9694.jsonl`
- `/ll:decide-issue` - 2026-07-07T18:52:36 - `d76b43c7-6459-4885-8f39-3acc21a4eb58.jsonl`
- `/ll:confidence-check` - 2026-07-07T18:47:34Z - `d14eece0-78bc-4134-b4c8-6b2bffa9260b.jsonl`
- `/ll:wire-issue` - 2026-07-07T18:45:39 - `73d1da94-8c2f-47d6-a9e6-a1fdabfe3288.jsonl`
- `/ll:refine-issue` - 2026-07-07T18:37:40 - `98048d86-2541-495e-8cd7-1c92912dfdac.jsonl`

- `/ll:capture-issue` - 2026-07-07T00:00:00Z - `agents:session-log-placeholder`
