---
id: ENH-1718
title: Enable `PreToolUse` by default for Codex adapter
type: ENH
priority: P4
status: open
testable: true
captured_at: '2026-05-26T02:23:05Z'
discovered_date: 2026-05-26
discovered_by: capture-issue
parent: EPIC-1463
labels:
- codex
- hooks
- host-compat
verify_verdict: VALID
confidence_score: 95
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-1718: Enable `PreToolUse` by default for Codex adapter

## Summary

`PreToolUse` was shipped opt-in only in FEAT-1489 despite the FEAT-1488 benchmark measuring p95 ≈ 10ms — well under the 200ms wire-by-default threshold. The conservative opt-in decision means the one consumer of this intent — the FEAT-1742 learning-test discoverability gate — does not fire for default Codex users, even in projects that have `learning_tests.enabled: true`.

## Motivation

FEAT-1489's resolution explicitly tied the opt-in/default decision to the benchmark gate: wire `pre_tool_use` opt-in-only if p95 < 200ms, or implement a sidecar if p95 ≥ 400ms. The measured p95 ≈ 10ms satisfies the threshold. Shipping as opt-in was therefore more conservative than the stated criteria required. Default enablement closes the gap with no user-visible latency cost.

**Scope of the payoff, stated plainly.** The only handler behind the
`pre_tool_use` intent is `learning_tests_gate` (see Codebase Research Findings
below). The Claude Code hooks that *look* like `PreToolUse` consumers —
`check-duplicate-issue-id.sh`, `check-decisions-yaml.sh`,
`check-private-refs.sh` — are standalone scripts wired directly in
`hooks/hooks.json`; they never route through this intent and are unaffected by
this issue. The two issues that formerly declared `blocked_by: ENH-1718`
(FEAT-1719, FEAT-1720) are both `cancelled`, so nothing downstream is waiting
on this either; the `blocks:` list has been dropped from frontmatter
accordingly.

So the concrete user-visible outcome is narrow and worth naming: a Codex user
in a project with `learning_tests.enabled: true` gets the discoverability
nudge on `Write`/`Edit` that a Claude Code user in the same project already
gets. That is a real host-parity gap, and it is why this is P4 rather than
higher.

## Current Behavior

`scripts/little_loops/hooks/adapters/codex/hooks.json` has no `PreToolUse` entry. The Python handler (`scripts/little_loops/hooks/pre_tool_use.py`) exists and is registered in `scripts/little_loops/hooks/__init__.py:_dispatch_table` (line 134), but neither the Codex `hooks.json` nor the OpenCode `index.ts` enables it by default. Codex users who want PreToolUse must manually add the entry to their `.codex/hooks.json`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-16 — based on codebase analysis:_

- `scripts/little_loops/hooks/pre_tool_use.py:handle()` is **not** a pure no-op: it passes through (`exit_code=0`) for every tool *except* `Write`/`Edit`, which route to `learning_tests_gate.gate()` (`scripts/little_loops/hooks/learning_tests_gate.py`). That gate is itself config-gated (`learning_tests.enabled`, default `False`; `learning_tests.discoverability.mode`, default `"warn"`, with an explicit `"off"` short-circuit). This project's own `.ll/ll-config.json` sets `learning_tests.enabled: true`, so on this repo (and any consuming project with the same setting) default-enabling `PreToolUse` for Codex activates the gate's `Write`/`Edit` path, not just a pass-through — the FEAT-1488 p95≈10ms benchmark was measured against this gated-but-mostly-no-op path, so latency is still covered, but the "no behavioral change" framing in this issue's Notes section understates the effect for projects with learning tests enabled.
- Two other adapters already ship a `pre-tool-use.sh` shim for a non-default host: `scripts/little_loops/hooks/adapters/kimi/pre-tool-use.sh` and `scripts/little_loops/hooks/adapters/qwen/pre-tool-use.sh`. Both follow the Codex `post-tool-use.sh` shim shape (`export LL_HOOK_HOST=<host>`, stdin pipe, exit passthrough) but additionally `cd` to a `PAYLOAD_CWD` extracted from the JSON via `sed` (BUG-2921 hardening) — a step absent from every existing Codex adapter script. **Decided: omit the `cd` for Codex.** The Kimi/Qwen shims carry it because those hosts spawn plugin hooks with cwd = plugin root, so config and telemetry would otherwise resolve against the managed plugin copy instead of the project's `.ll/` (that is the literal BUG-2921 comment in `kimi/pre-tool-use.sh`). Codex does not have that problem, which is why not one of its four existing shims (`post-tool-use.sh`, `prompt-submit.sh`, `session-start.sh`, `pre-compact.sh`) does it. Adding it here would make the new script the odd one out on its own host for no benefit; if Codex's cwd behavior is ever found to differ, that is a separate change applied uniformly to all Codex shims, not a one-off in this file.

## Expected Behavior

`scripts/little_loops/hooks/adapters/codex/hooks.json` includes a `PreToolUse`
entry pointing to a `pre-tool-use.sh` adapter script, scoped by an
`"Edit|Write"` matcher with a 5s timeout. Codex users get PreToolUse firing
automatically after `/ll:init --codex`, consistent with the Claude Code default
behavior.

**The matcher is required, not cosmetic.** `pre_tool_use.handle()` acts only on
`Write`/`Edit` and returns `LLHookResult(exit_code=0)` for every other tool, so
an unmatched entry would spawn a bash shim plus a Python interpreter on every
`Read`, `Grep`, and `Bash` call to do nothing. Claude Code wires the same shim
behind `"matcher": "Write|Edit"` in `hooks/hooks.json`, and Codex's own
`hooks.json` already proves matcher support on this host via the
`edit-batch-nudge.sh` `PostToolUse` entry (`"matcher": "Edit|Write|MultiEdit"`).
Do **not** copy `PostToolUse`'s matcher-less shape here — `post_tool_use` is
genuinely a per-call analytics recorder; `pre_tool_use` is not.

## Acceptance Criteria

- `scripts/little_loops/hooks/adapters/codex/hooks.json` includes a `PreToolUse` entry with `"matcher": "Edit|Write"`, `timeout: 5`, and `statusMessage: "Checking learning-test coverage..."` (matching Claude Code's `statusMessage` for the same shim, not `PostToolUse`'s generic "Recording tool use...")
- A test asserts the `PreToolUse` entry carries a matcher scoping it to `Edit|Write` — i.e. the hook does not fire for `Read`/`Grep`/`Bash`
- `scripts/little_loops/hooks/adapters/codex/pre-tool-use.sh` exists, is executable, sets `LL_HOOK_HOST=codex`, invokes `python -m little_loops.hooks pre_tool_use`
- `scripts/tests/test_codex_adapter.py` covers the new script (file-exists, executable, LL_HOOK_HOST sentinel, hooks.json presence)
- `docs/reference/HOST_COMPATIBILITY.md` `pre_tool_use` Codex CLI cell updated from `(opt-in)[^hot]` to `✓ (active)[^hot]`
- `docs/reference/HOST_COMPATIBILITY.md` `[^hot]` footnote's `pre_tool_use` sub-bullet no longer lists Codex as opt-in (OpenCode clause preserved)
- `hooks/adapters/codex/README.md` updated in both places: the event table row (line 35) and the `### Opt-in: PreToolUse` section (lines 99-109) reflect default enablement

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-16 — based on codebase analysis:_

- The shared `[^hot]` footnote in `docs/reference/HOST_COMPATIBILITY.md` (lines ~91-95) has a `pre_tool_use` sub-bullet that names **both** OpenCode and Codex as still-opt-in: "It remains opt-in for OpenCode (`tool.execute.before`) and Codex (`PreToolUse`) — see the adapter READMEs." This issue's stated scope is Codex only (OpenCode's `pre_tool_use` is unaffected). The footnote sentence needs editing to drop the Codex clause while preserving the OpenCode clause, not just the table cell (which the existing 4th AC already covers).
- Two coexisting conventions exist in the same table for how an "active" `pre_tool_use` cell is formatted: Claude Code uses `✓ (active)[^hot]` (routes to the shared `[^hot]` footnote), while Kimi/Qwen use `✓ (active, blockable)[^kimi|qwen]` (routes to their own per-host footnote, no `[^hot]` reference). **Decided: use `✓ (active)[^hot]`** — Codex has no per-host footnote to route to, and the flipped cell still needs the `[^hot]` latency note. The ACs above now prescribe this form rather than the bare `✓` the original AC text implied.
- Claude Code scopes this same shim with `"matcher": "Write|Edit"` in `hooks/hooks.json`, while Codex's `hooks.json` already demonstrates matcher support on this host via the `edit-batch-nudge.sh` `PostToolUse` entry (`"matcher": "Edit|Write|MultiEdit"`). Together these settle the matcher question the original Implementation Steps got wrong — see Expected Behavior.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-16 — based on codebase analysis:_

### Types
- `host: str` — `LLHookEvent.host` (`scripts/little_loops/hooks/types.py`), resolved in `main_hooks()` from `os.environ.get("LL_HOOK_HOST", "claude-code")`; the new shim's `export LL_HOOK_HOST=codex` is what makes `event.host == "codex"` for this intent
- `intent: str` — `LLHookEvent.intent`; the dispatch-table key, `"pre_tool_use"`
- `payload: dict` — `LLHookEvent.payload`; raw hook JSON, `pre_tool_use.handle()` reads `payload["tool_name"]`
- `exit_code: int` — `LLHookResult.exit_code`; `0` on the pass-through branch

### Signatures
- `pre_tool_use.handle(event: LLHookEvent) -> LLHookResult` — existing, unmodified by this issue (`scripts/little_loops/hooks/pre_tool_use.py`); branches on `event.payload.get("tool_name", "")`: `Write`/`Edit` routes to `learning_tests_gate.gate(event)`, everything else returns `LLHookResult(exit_code=0)`
- `main_hooks()` — existing entry point (`scripts/little_loops/hooks/__init__.py:168`), invoked by `python -m little_loops.hooks pre_tool_use`; looks up `"pre_tool_use"` in `_dispatch_table()` (already registered, `__init__.py:159`), reads/parses stdin JSON, builds `LLHookEvent`, calls the handler, translates `LLHookResult` to stderr + exit code

### Call Path
Codex `PreToolUse` host event -> `hooks.json` `PreToolUse` group command (new) -> `pre-tool-use.sh` (new: `export LL_HOOK_HOST=codex`; `INPUT=$(cat)`; pipe into `python -m little_loops.hooks pre_tool_use`) -> `main_hooks()` -> `_dispatch_table()["pre_tool_use"]` -> `pre_tool_use.handle(event)` -> (`Write`/`Edit` only) `learning_tests_gate.gate(event)`

### Decision Rules
N/A — no new decision logic. This issue wires an existing, unmodified handler into a new host's config; it does not introduce a new gate, threshold, or keyword list.

## Scope Boundaries

**In scope:** the Codex adapter's `PreToolUse` wiring — a new
`pre-tool-use.sh` shim, the `hooks.json` entry with its `Edit|Write` matcher,
`test_codex_adapter.py` coverage, and the three doc surfaces
(`HOST_COMPATIBILITY.md` table cell + `[^hot]` footnote,
`hooks/adapters/codex/README.md`).

**Out of scope:** OpenCode's `pre_tool_use`, which stays opt-in — the `[^hot]`
footnote edit preserves its clause. `pre_tool_use.py` and
`learning_tests_gate.py` are used unmodified; this issue changes no handler
behavior, adds no gate, and does not touch `learning_tests.*` config defaults
(the gate stays off unless a project opts in). Kimi/Qwen shims are referenced
as precedent only. The Claude Code `PreToolUse` scripts
(`check-duplicate-issue-id.sh`, `check-decisions-yaml.sh`,
`check-private-refs.sh`) are unrelated to this intent and unaffected.

## Impact

- **Priority**: P4 — a genuine host-parity gap, but the only consumer is a
  default-off gate, so no user is blocked. Nothing downstream depends on it:
  both former `blocks:` targets are `cancelled`.
- **Effort**: Small — one 4-line shim, one JSON entry, two tests, three doc
  edits.
- **Risk**: Low. The `Edit|Write` matcher keeps the shim off the hot path for
  most tool calls, and the handler's non-`Write`/`Edit` branch is a bare
  `exit_code=0`. The one real user-visible consequence is that Codex users in
  projects with `learning_tests.enabled: true` begin seeing discoverability
  nudges on `Write`/`Edit` where they previously saw none — intended, and
  identical to what Claude Code users in the same project already get.
- **Trust-hash churn**: editing `hooks.json` re-prompts existing Codex users to
  re-trust on next startup. Call this out in the PR description.
- **Breaking Change**: No

## Implementation Steps

1. Create `scripts/little_loops/hooks/adapters/codex/pre-tool-use.sh` — 4-line shim mirroring `post-tool-use.sh`, replacing intent with `pre_tool_use`. **Omit the `PAYLOAD_CWD` `cd` step** that `kimi/pre-tool-use.sh` and `qwen/pre-tool-use.sh` carry: that step exists because Kimi spawns plugin hooks with cwd = plugin root (BUG-2921). Codex spawns hooks with cwd = project root, which is why no existing Codex shim (`post-tool-use.sh`, `prompt-submit.sh`, `session-start.sh`, `pre-compact.sh`) does it. Stay consistent with the Codex siblings.
2. Add `PreToolUse` entry to `scripts/little_loops/hooks/adapters/codex/hooks.json` with `"matcher": "Edit|Write"`, `timeout: 5`, `statusMessage: "Checking learning-test coverage..."` — see Expected Behavior for why the matcher is load-bearing
3. Update `scripts/tests/test_codex_adapter.py` — add `PRE_TOOL_USE` path constant; extend `test_adapter_files_exist`, `test_adapter_scripts_are_executable`; add `test_hooks_json_has_pre_tool_use` (asserting the `Edit|Write` matcher) and `test_pre_tool_use_sets_ll_hook_host_codex`
4. Flip `pre_tool_use` Codex CLI cell in `docs/reference/HOST_COMPATIBILITY.md` from `(opt-in)[^hot]` to `✓ (active)[^hot]` — matching Claude Code's form in the same row, since the flipped cell still needs the `[^hot]` latency footnote. (The `✓ (active, blockable)[^kimi|qwen]` form routes to a per-host footnote Codex does not have.)
5. Edit the `[^hot]` footnote's `pre_tool_use` sub-bullet (`docs/reference/HOST_COMPATIBILITY.md:91-95`): drop the Codex clause from "It remains opt-in for OpenCode (`tool.execute.before`) and Codex (`PreToolUse`)", preserving the OpenCode clause — OpenCode's `pre_tool_use` is out of scope here. Note Codex's `Edit|Write` matcher alongside Claude Code's.
6. Update `hooks/adapters/codex/README.md` — event table row (line 35) and the `### Opt-in: PreToolUse` section (lines 99-109), which documents the manual `hooks.json` snippet users currently paste and must now describe default enablement instead

## Notes

- Trust-hash churn: adding `PreToolUse` to `scripts/little_loops/hooks/adapters/codex/hooks.json` changes the file hash; existing Codex users will be prompted to re-trust on next startup. Document in PR.
- Benchmark evidence on record: `scripts/tests/bench_opencode_adapter.py` p95 ≈ 10ms (from FEAT-1489 resolution), well under `_DECISION_TARGET_MS = 200`. With the `Edit|Write` matcher the shim fires on a strict subset of the calls that benchmark assumed, so the measured headroom is conservative.
- This is **not** a behavior-free change for projects with `learning_tests.enabled: true` — see Codebase Research Findings under Current Behavior. An earlier revision of this issue claimed the handler was "already a no-op"; that was wrong and has been removed.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `scripts/little_loops/hooks/adapters/codex/hooks.json` | File to modify — add `PreToolUse` entry |
| `scripts/little_loops/hooks/adapters/codex/post-tool-use.sh` | Direct template for the new script |
| `docs/reference/HOST_COMPATIBILITY.md` | `pre_tool_use` row to flip |
| `scripts/tests/bench_opencode_adapter.py` | Benchmark evidence justifying default enablement |

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-16 — based on codebase analysis:_

- `scripts/little_loops/hooks/adapters/kimi/pre-tool-use.sh` and `scripts/little_loops/hooks/adapters/qwen/pre-tool-use.sh` — existing `pre-tool-use.sh` shims for other non-default hosts; evidence for the `LL_HOOK_HOST=<host>` + stdin-pipe + exit-passthrough shape shared across every adapter's shim scripts, Codex's `post-tool-use.sh` included.
- `scripts/tests/test_codex_adapter.py:265-274` (`test_hooks_json_has_post_tool_use`) and `:276-319` (`test_post_tool_use_sets_ll_hook_host_codex`) — exact test-function shapes the new `test_hooks_json_has_pre_tool_use` / `test_pre_tool_use_sets_ll_hook_host_codex` tests should mirror, including the sentinel-file fake-package subprocess pattern and the JSON payload shape (`{"hook_event_name":"PostToolUse","tool_name":"Bash","tool_response":{}}` for the Post variant — a PreToolUse-shaped payload needs `hook_event_name":"PreToolUse"` and a `tool_input` key instead of `tool_response`, since that's what `pre_tool_use.handle()` reads to decide the `Write`/`Edit` branch).

## Status

**Open** | Created: 2026-05-26 | Priority: P4


## Verification Notes

**Verdict**: VALID — 2026-06-05T21:00:23

- Issue describes a planned feature/enhancement that has not yet been implemented
- Referenced files and directories verified to exist (where applicable)
- No claims about current code behavior are contradicted by the codebase
- Dependency references are valid (no broken refs, missing backlinks, or cycles)

2026-06-18 (VALID): Confirmed — `hooks/adapters/codex/hooks.json` still has no `PreToolUse` entry (only SessionStart, PreCompact, UserPromptSubmit, PostToolUse). `hooks/adapters/codex/pre-tool-use.sh` does not exist (expected — to be created by this issue). `pre_tool_use` Codex cell in HOST_COMPATIBILITY.md still reads `(opt-in)[^hot]`. Issue accurately describes unimplemented work; all Current Behavior claims are correct.

- **2026-08-16** (pre-implementation review): Three corrections applied. (1) Implementation Step 2 specified a matcher-less `PreToolUse` entry copied from `PostToolUse`'s shape; since `pre_tool_use.handle()` acts only on `Write`/`Edit`, that would have spawned a bash shim plus a Python interpreter on every `Read`/`Grep`/`Bash` call for no effect, and contradicted the issue's own "consistent with Claude Code" goal — Claude Code scopes the same shim with `"matcher": "Write|Edit"`. Now specified as `"matcher": "Edit|Write"` with an AC pinning it. (2) The Summary/Motivation cited `PreToolUse` consumers that do not route through this intent (`check-duplicate-issue-id.sh` and siblings are standalone Claude-Code hooks), and the `blocks: [FEAT-1719, FEAT-1720]` frontmatter pointed at two `cancelled` issues; both corrected, and the real payoff — the FEAT-1742 learning-test gate reaching Codex — stated plainly. (3) The Notes bullet asserting the handler is "already a no-op ... no behavioral change" was refuted by this issue's own Codebase Research Findings and has been removed. The two questions the refine pass left open (the `PAYLOAD_CWD` `cd` step; the HOST_COMPATIBILITY cell format) are now decided in place. Core ask unchanged and still unimplemented.

- **2026-06-26** (/ll:verify-issues): Confirmed all substantive moved-file path references (hooks.json, post-tool-use.sh, pre-tool-use.sh) already point at the post-FEAT-2274 in-package location `scripts/little_loops/hooks/adapters/codex/`; the remaining bare `hooks/adapters/codex/README.md` refs are correct since that README legitimately stays at the repo root. PreToolUse-not-default gap remains real and unimplemented — no substantive change needed.

## Session Log
- `/ll:confidence-check` - 2026-08-16T20:59:10 - `7e0c4df2-cf1e-458e-8242-dd501680bfd2.jsonl`
- `/ll:refine-issue` - 2026-08-16T20:53:33 - `08baf035-dd8f-42d7-8612-8a15da0895a0.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:05:11 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:verify-issues` - 2026-06-09T18:30:00 - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:35 - `a5f82118-5be7-4fc3-afac-e29effcffd8b.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:17 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:16 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:capture-issue` - 2026-05-26T02:23:05Z - `1e210ff4-bcab-4372-9c8c-a0ba98da62d5.jsonl`
