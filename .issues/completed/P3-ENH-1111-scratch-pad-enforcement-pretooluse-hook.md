---
id: ENH-1111
type: ENH
priority: P3
status: open
discovered_date: 2026-04-15
discovered_by: capture-issue
related: [FEAT-1116]
confidence_score: 98
outcome_confidence: 68
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 18
size: Very Large
---

# ENH-1111: Scratch-Pad Enforcement via PreToolUse Hook

## Summary

Enforce the `/tmp/ll-scratch` convention from `.claude/CLAUDE.md` automatically via a PreToolUse hook, so large Bash/Read outputs are redirected to scratch files instead of relying on the model to remember the convention.

## Motivation

`.claude/CLAUDE.md` currently documents a scratch-pad convention: "Before reading a file, check its size... if > 200 lines, use Bash to cat to `/tmp/ll-scratch/`." This is a soft rule — the model regularly forgets it in long loop runs, flooding context with test output, file contents, and scan results.

Context-mode (github.com/mksglu/context-mode) enforces equivalent behavior via a PreToolUse hook that intercepts tool calls, runs the command in a subprocess, and returns a summary + index pointer instead of raw output. They report ~98% context reduction on typical workloads.

## Current Behavior

- Convention lives only in `CLAUDE.md:122-130` as prose guidance
- No mechanism enforces the ≥200-line threshold
- Long ll-auto / ll-parallel runs routinely hit compaction because large outputs leak into context
- Related completed work: ENH-498 added observation masking for ll-auto/parallel, but only masks, doesn't redirect

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`scratch_pad` schema block already exists** at `config-schema.json:526-544` with `enabled` (bool, default `false`) and `threshold_lines` (int, default 200, min 50, max 1000). Guarded by `additionalProperties: false`, so new keys must be added to the schema in the same edit. `.ll/ll-config.json` does not override the section today (falls back to schema defaults).
- **Scratch path discrepancy**: `CLAUDE.md:126-127` still references `/tmp/ll-scratch/`, but BUG-817 (`.issues/completed/P2-BUG-817-...md`) migrated the active cleanup path to `.loops/tmp/scratch/` — see `hooks/scripts/session-cleanup.sh:16-17`. ENH-1111 should standardize on `.loops/tmp/scratch/` and fix CLAUDE.md as part of the acceptance criteria.
- **Only existing PreToolUse hook** is `hooks/scripts/check-duplicate-issue-id.sh` — matcher `Write|Edit` at `hooks/hooks.json:29-41`. It uses the allow/deny pattern (`hookSpecificOutput.permissionDecision`) but never `updatedInput`. This would be the codebase's first hook that rewrites a tool call.
- **`updatedInput` contract is documented** at `docs/claude-code/hooks-reference.md:807-828`: PreToolUse may return `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","updatedInput":{"command":"..."},"additionalContext":"..."}}`. For Bash, only the `command` field is rewritable. For Read, only `file_path`/`offset`/`limit` — Read's output path cannot be redirected via `updatedInput`.
- **Read limitation**: since Read can't be rewritten to "cat to scratch", the practical options are (a) `deny` with `additionalContext` suggesting a Bash scratch equivalent, or (b) inject a truncating `limit` into `updatedInput`. Option (a) is closer to the issue's intent.
- **Config reading from hooks** is already standardized via `hooks/scripts/lib/common.sh:182-234` (`ll_resolve_config`, `ll_feature_enabled "scratch_pad.enabled"`, `ll_config_value "scratch_pad.threshold_lines" 200`). No new loader needed for the shell side.
- **`BRConfig` has no `scratch_pad` dataclass** — `scripts/little_loops/config/core.py:95-115` does not construct one, and `config/__init__.py` does not export one. The shell hook does not need this, but any Python-side consumer (including future tests that assert resolved config values) would need to read it via `config._raw_config.get("scratch_pad", {})` or a new dataclass.
- **`.ll/ll.local.md` deep-merge happens only inside `session-start.sh:24-98`** (embedded Python heredoc). `ll_resolve_config` in `lib/common.sh` reads `.ll/ll-config.json` directly and does NOT apply the `.local.md` overrides. The current acceptance criterion "respects local overrides in `.ll/ll.local.md`" cannot be satisfied without first extracting the deep-merge logic into a shared helper (shell or Python CLI) that all hooks can call. **This is a hidden dependency not surfaced in the issue today.**
- **No `LL_AUTOMATION` env var exists.** `ll-auto`/`ll-parallel`/`ll-loop` all invoke Claude via `scripts/little_loops/subprocess_utils.py:97-105` with `--dangerously-skip-permissions`. The resulting hook stdin carries `permission_mode: "bypassPermissions"` (per `docs/claude-code/hooks-reference.md:395`). This is the cheapest proxy for "we're inside automation" and does not require any CLI runner changes.
- **Hook test pattern** (`scripts/tests/test_hooks_integration.py:14-95`): tests `chdir` to `tmp_path`, write `.ll/ll-config.json` there, invoke the script via `subprocess.run(..., input=json.dumps({...}))`, and assert on `returncode`/`stdout`/`stderr`. Timeout is hook-timeout + 1s. Env-var overrides tested per `test_hooks_integration.py:229-266`.
- **Related FEAT-1116** (hook-intent abstraction) aims to replace per-host shell hooks with Python intent handlers. ENH-1111 will ship as a shell hook first and likely port into FEAT-1116's intent layer later — the shell hook should stay behaviorally self-contained (no Python cross-dependencies) so the eventual port is a straight translation.

## Expected Behavior

- New PreToolUse hook (`hooks/scripts/scratch-pad-redirect.sh`) inspects Bash commands that read files (`cat`, `pytest`, `mypy`, `ruff`) and large Read calls
- When expected output exceeds a threshold (default 200 lines / configurable), the hook rewrites the `Bash` tool's `command` via `updatedInput` to pipe through `tee .loops/tmp/scratch/<name>.txt | tail -N` and returns the tail path via `additionalContext` (contract: `docs/claude-code/hooks-reference.md:807-828`)
- Read tool calls on files >N lines get **denied** with `additionalContext` suggesting the equivalent `Bash cat > .loops/tmp/scratch/<name>.txt` command (Read's `updatedInput` can only set `file_path`/`offset`/`limit`, so redirecting its output to a scratch file is not possible — denying and nudging is the supported path)
- Scratch directory path is `.loops/tmp/scratch/` (per BUG-817); CLAUDE.md's `/tmp/ll-scratch/` references are updated in the same change
- Configuration lives under the existing `scratch_pad:` section in `.ll/ll-config.json` (schema: `config-schema.json:526-544`). The section already defines `enabled` (default `false`) and `threshold_lines` (default 200); this enhancement extends it with the additional knobs below

## Acceptance Criteria

- New hook registered in `hooks/hooks.json` as a second PreToolUse entry with matcher `Bash|Read` (existing `Write|Edit` entry at `hooks/hooks.json:29-41` stays untouched)
- Configuration extends the existing `scratch_pad` object in `config-schema.json:526-544` with new properties (e.g., `automation_contexts_only`, `tail_lines`, `command_allowlist`, `file_extension_filters`) and matching examples in `.ll/ll-config.json`. Existing `enabled` / `threshold_lines` keys are reused unchanged. Schema's `additionalProperties: false` enforces schema-first updates.
- Hook reads config via `ll_resolve_config` + `ll_feature_enabled` / `ll_config_value` from `hooks/scripts/lib/common.sh:182-234` (no new loader)
- `.ll/ll.local.md` override support is **out of scope** for this issue unless the deep-merge logic in `session-start.sh:30-43` is first extracted into `lib/common.sh`. Recommendation: defer `.local.md` merging to a follow-up; for now the hook reads `.ll/ll-config.json` only, and CLAUDE.md's local-override docs note this gap.
- Hook is a no-op when `scratch_pad.enabled` is `false` (default). When enabled, hook defaults to `automation_contexts_only: true` and skips unless hook stdin's `permission_mode == "bypassPermissions"` (the `--dangerously-skip-permissions` signal passed by `ll-auto`/`ll-parallel`/`ll-loop` via `subprocess_utils.py:97-105`). `automation_contexts_only: false` makes it fire everywhere.
- Unit tests in `scripts/tests/test_hooks_integration.py` cover: (a) disabled → no-op, (b) enabled but non-automation → no-op, (c) enabled + automation + Bash command under threshold → allow unchanged, (d) enabled + automation + Bash command over threshold → `updatedInput` rewrites command to tee+tail, (e) enabled + automation + Read over threshold → deny with `additionalContext`, (f) `command_allowlist` skips non-matching Bash (e.g. `git status`)
- Integration test proves a simulated 500-line `pytest` invocation in an automation context leaves only `tail_lines` (default 20) of output + a scratch path in the hook result
- CLAUDE.md `## Automation: Scratch Pad` section (lines 122-130) is updated to: (a) describe automatic enforcement, (b) correct the path from `/tmp/ll-scratch/` to `.loops/tmp/scratch/`, (c) point at the `scratch_pad` config keys, (d) remove the prose instructions the hook now enforces
- `docs/reference/CONFIGURATION.md:155,474-481` updated with the new `scratch_pad` properties

## Integration Map

### Files to Modify

- `hooks/hooks.json` — add second PreToolUse matcher `Bash|Read` alongside the existing `Write|Edit` entry (current PreToolUse at lines 29-41)
- `config-schema.json:526-544` — extend `scratch_pad.properties` with `automation_contexts_only` (bool, default `true`), `tail_lines` (int, default 20, min 5, max 200), `command_allowlist` (array of strings, default `["cat","pytest","mypy","ruff","ls","grep","find"]`), `file_extension_filters` (array of strings, default `[".log",".txt",".json",".md",".py",".ts",".tsx",".js"]`)
- `.ll/ll-config.json` — add a commented-out `scratch_pad` block as a template (project-local activation is opt-in)
- `.claude/CLAUDE.md:122-130` — replace prose convention with a pointer to `scratch_pad` config keys and fix the `/tmp/ll-scratch/` → `.loops/tmp/scratch/` path
- `docs/reference/CONFIGURATION.md:155,474-481` — document the new properties
- `hooks/scripts/session-cleanup.sh:16-17` — no change (already cleans `.loops/tmp/scratch`); verify this still covers hook-generated files
- `docs/ARCHITECTURE.md:90-95` — hook scripts directory listing; add `scratch-pad-redirect.sh` entry [Agent 1 finding]
- `docs/guides/LOOPS_GUIDE.md:556` — correct `/tmp/ll-scratch` to `.loops/tmp/scratch` in `scratch_dir` CLI override example [Agent 1/2 finding]

### Files to Create

- `hooks/scripts/scratch-pad-redirect.sh` — new PreToolUse hook. Shell pattern following `check-duplicate-issue-id.sh` (stdin via `INPUT=$(cat)`, parse with `jq -r`, early `allow_response()` helper, source `lib/common.sh` for `ll_resolve_config` / `ll_feature_enabled` / `ll_config_value`)

### Dependent / Reference Files (read, do not modify)

- `hooks/scripts/check-duplicate-issue-id.sh:1-129` — PreToolUse structural template (allow/deny), to adapt for `updatedInput` path
- `hooks/scripts/context-monitor.sh:17,45-47` — stdin-parse patterns (single-pass `jq @tsv` for multiple fields)
- `hooks/scripts/lib/common.sh:182-234` — config-loading primitives the new hook calls
- `docs/claude-code/hooks-reference.md:807-828` — `updatedInput` / `additionalContext` contract
- `docs/claude-code/hooks-reference.md:395,712-751` — stdin `permission_mode` field + `Bash`/`Read` `tool_input` schemas
- `scripts/little_loops/subprocess_utils.py:97-105` — confirms `--dangerously-skip-permissions` is set by all automation runners (source of `permission_mode="bypassPermissions"`)
- `scripts/little_loops/issue_history/quality.py:432` — reads `hooks/hooks.json` at runtime to check hook configs and emit suggestions; changes to hook structure cascade to quality analyzer output [Agent 1 finding]

### Tests

- `scripts/tests/test_hooks_integration.py` — add a `TestScratchPadRedirect` class following the `chdir(tmp_path)` + `.ll/ll-config.json` fixture pattern at lines 14-95. Subprocess-invoke the shell hook with synthesized stdin (Bash + Read variants). Also test common-sh integration per lines 1192-1315 pattern if new helpers are added to `lib/common.sh`.
- `scripts/tests/test_config_schema.py:1-27` — extend to assert new `scratch_pad` properties exist with expected defaults
- `scripts/tests/test_create_extension_wiring.py:83-87,162-166` — reads `.claude/CLAUDE.md` and asserts `"ll-create-extension"` and `"ll-generate-schemas"` strings are present; low break risk if edits stay within lines 122-130, but verify after CLAUDE.md edit [Agent 3 finding]

### Behavioral Interaction Notes

_Wiring pass added by `/ll:wire-issue`:_

The new hook, when `enabled: true` in automation contexts, will intercept `Read` calls against `.loops/tmp/` files. Several built-in loop YAMLs issue `Read` against their own temp output files — these will be denied with a Bash scratch suggestion, changing loop behavior for large outputs. The loops themselves do **not** require code changes, but the behavioral interaction should be noted during Step 9 (integration verify):

- `scripts/little_loops/loops/fix-quality-and-tests.yaml:87` — `Read .loops/tmp/ll-test-results.txt`
- `scripts/little_loops/loops/dead-code-cleanup.yaml:84` — `Read .loops/tmp/ll-dead-code-tests.txt`
- `scripts/little_loops/loops/test-coverage-improvement.yaml:94,165` — `Read .loops/tmp/ll-coverage-report.txt`, `Read .loops/tmp/ll-coverage-tests.txt`

The hook's deny-with-hint approach (returning a Bash scratch command suggestion) means the model will adapt in-flight. This is expected behavior, not a bug. Verify during integration that the loop completes correctly when the hook redirects a Read.

### Similar Patterns

- `hooks/scripts/check-duplicate-issue-id.sh:1-129` — closest structural analogue (shell PreToolUse with JSON stdin → JSON stdout)
- `config-schema.json:447-525` (`context_monitor`) — reference for adding a richer properties block with bounds, defaults, nested objects

## Implementation Steps

1. **Schema-first**: extend `config-schema.json:526-544` with the four new `scratch_pad` properties (defaults + bounds as specified under Acceptance Criteria). Add a `test_config_schema.py` assertion so drift is caught.
2. **Hook skeleton**: create `hooks/scripts/scratch-pad-redirect.sh` using `check-duplicate-issue-id.sh` as a template. Source `lib/common.sh`. Early-exit `allow_response` when `ll_feature_enabled "scratch_pad.enabled"` is false. Parse stdin fields `tool_name`, `tool_input.command`, `tool_input.file_path`, `permission_mode` in a single `jq @tsv` pass per the `context-monitor.sh:45-47` pattern.
3. **Automation gate**: when `scratch_pad.automation_contexts_only` is true (default), allow-unchanged unless `permission_mode == "bypassPermissions"`.
4. **Bash rewrite path**: if `tool_name == "Bash"`, tokenize the first word of `.tool_input.command`, check against `command_allowlist`; if matched, generate a scratch filename (e.g. `pytest-$(date +%s).txt`), construct the rewritten command `<original> > .loops/tmp/scratch/<name> 2>&1; tail -<tail_lines> .loops/tmp/scratch/<name>`, and emit `hookSpecificOutput.permissionDecision=allow` + `updatedInput.command=<new>` + `additionalContext` naming the scratch path. `mkdir -p .loops/tmp/scratch` before emitting.
5. **Read deny path**: if `tool_name == "Read"` and the target file matches `file_extension_filters` and `wc -l` exceeds `threshold_lines`, return `permissionDecision=deny` with `permissionDecisionReason` naming the scratch command the model should use instead.
6. **Register hook**: add the matcher to `hooks/hooks.json` as a second PreToolUse entry with matcher `Bash|Read`, 5s timeout. Confirm ordering: it runs after the existing `Write|Edit` matcher (different matcher, so they don't collide).
7. **Tests**: add `TestScratchPadRedirect` in `scripts/tests/test_hooks_integration.py` with the six cases enumerated in Acceptance Criteria. Run `python -m pytest scripts/tests/test_hooks_integration.py -v` and `python -m pytest scripts/tests/test_config_schema.py -v`.
8. **Docs**: update `.claude/CLAUDE.md:122-130` and `docs/reference/CONFIGURATION.md` per Acceptance Criteria. Correct the scratch path everywhere (`/tmp/ll-scratch/` → `.loops/tmp/scratch/`).
9. **Integration verify**: enable `scratch_pad` in `.ll/ll-config.json`, run a real `ll-auto` pass, inspect transcript for scratch-path references and confirm large outputs are no longer inlined.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Update `docs/ARCHITECTURE.md:90-95` — add `scratch-pad-redirect.sh` to the hook scripts directory listing
11. Update `docs/guides/LOOPS_GUIDE.md:556` — correct `/tmp/ll-scratch` to `.loops/tmp/scratch` in the `scratch_dir` CLI override example
12. After editing `.claude/CLAUDE.md`, run `python -m pytest scripts/tests/test_create_extension_wiring.py -v` to confirm `"ll-create-extension"` and `"ll-generate-schemas"` string assertions still pass

## Open Decisions (surfaced by research)

- **`.ll/ll.local.md` override support** — the deep-merge logic currently lives only in `session-start.sh:30-43`. Either extract it to `lib/common.sh` (new work, affects all hooks), or explicitly drop the local-override requirement from ENH-1111 and track it as a follow-up. Recommendation above: defer.
- **Automation detection via `permission_mode`** — cheapest option, but couples hook behavior to the CLI's `--dangerously-skip-permissions` choice. Alternative: have `subprocess_utils.py` export `LL_AUTOMATION=1` and detect that instead. Choose in implementation; `permission_mode` is simpler and needs zero CLI changes.
- **Read rewrite vs deny** — Read cannot have its output redirected via `updatedInput`. Denying with a suggested Bash scratch command is the documented path; truncating via `limit` injection is an inferior alternative (model still sees a page, just fewer lines). Recommendation: deny-with-hint.

## References

- Inspiration: context-mode sandbox tools (`ctx_execute`, `ctx_batch_execute`)
- Related completed: ENH-498 observation masking in ll-auto/parallel; BUG-817 scratch path migration
- Related: ENH-1114 (intent parameter), FEAT-1116 (hook-intent abstraction — ENH-1111 is a candidate to port into that framework later)
- Hook contract: `docs/claude-code/hooks-reference.md:807-828` (updatedInput), `:395` (permission_mode), `:712-751` (Bash/Read tool_input schemas)


## Session Log
- `hook:posttooluse-git-mv` - 2026-04-17T03:12:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4fc25386-a9f0-4e75-8434-c659db481895.jsonl`
- `/ll:wire-issue` - 2026-04-17T02:55:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b9cf8e5d-d945-479d-bcdd-09d094c9ac7d.jsonl`
- `/ll:refine-issue` - 2026-04-17T02:33:48 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0250b1b5-0604-41a3-be90-93a88c6d2fd2.jsonl`
- `/ll:confidence-check` - 2026-04-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b4e1b2df-844b-44d0-b226-babe74a26efd.jsonl`
- `/ll:issue-size-review` - 2026-04-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4fc25386-a9f0-4e75-8434-c659db481895.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-16
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into
- ENH-1128: Extend config-schema.json with scratch_pad Properties
- ENH-1129: Implement scratch-pad-redirect.sh PreToolUse Hook
- ENH-1130: Documentation and Path Updates for Scratch-Pad Hook
