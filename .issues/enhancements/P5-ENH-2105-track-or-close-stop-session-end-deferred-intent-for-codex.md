---
id: ENH-2105
title: Track or close `stop/session_end` deferred intent for Codex adapter
type: ENH
priority: P5
status: cancelled
captured_at: "2026-06-12T00:00:00Z"
discovered_date: 2026-06-12
discovered_by: review-epic
parent: EPIC-1463
relates_to: [FEAT-1719]
decision_needed: true
labels:
  - codex
  - hooks
  - host-compat
---

# ENH-2105: Track or close `stop/session_end` deferred intent for Codex adapter

## Summary

The `stop/session_end` hook intent shows `(deferred)` in the Codex column of
`docs/reference/HOST_COMPATIBILITY.md` with no footnote linking to a tracking
issue. Either wire the intent for Codex (following the FEAT-1719 handler
pattern) or formally close it as not-applicable with a tracking footnote.

## Current Behavior

The `stop/session_end` hook intent renders as `(deferred)` in the Codex column
of `docs/reference/HOST_COMPATIBILITY.md` (line 28) with no footnote linking to
a tracking issue. The deferred state is therefore untracked — a reader cannot
tell whether the gap is intentional, scheduled, or simply unaddressed. This
contradicts EPIC-1463's bookkeeping standard that every deferred/✗ cell in the
Codex matrix link to a real issue: `post_compact` (→ FEAT-1719) and
`permission_request` (→ absorbed into FEAT-1719) are tracked, while
`stop/session_end` is not.

## Expected Behavior

The `stop/session_end` Codex cell reaches a tracked terminal state — either:
- **Wired**: the intent is implemented for Codex following the FEAT-1719 handler
  pattern (`hooks/adapters/codex/*.sh` + dispatch entry + tests), or
- **Closed as not-applicable**: `HOST_COMPATIBILITY.md` gains a footnote on the
  cell linking to this issue and recording the Codex CLI capability evidence.

In both cases, no unannotated `(deferred)` cell remains in the Codex column.

## Motivation

EPIC-1463's success metric is that every deferred/✗ cell in the Codex
compatibility matrix links to a real issue. The epic scope explicitly tracks
`post_compact` (FEAT-1719) and `permission_request` (absorbed into FEAT-1719
after FEAT-1720's supersession) as deferred intents, but omits
`stop/session_end` — leaving an untracked gap that contradicts the epic's
own bookkeeping standard.

## Proposed Solution

Two terminal states satisfy the Acceptance Criteria. Codebase research (see
Integration Map → Codebase Research Findings) makes **Option A the
lower-friction, more accurate resolution** and weakens Option B's
"not-applicable" framing.

### Option A — Wire `session_end` for Codex (research-favored)

The host-agnostic consumer already exists and is already registered, so wiring
is **transport-only** — steps 1–2 of the FEAT-1719 six-step pattern are already
complete for this intent:

- `sweep_stale_refs.handle` (`scripts/little_loops/hooks/sweep_stale_refs.py`,
  shipped by FEAT-1680, status `done`) is the `session_end` handler and always
  returns `LLHookResult(exit_code=0)` — it can never block session end.
- It is already registered in `_dispatch_table()`
  (`scripts/little_loops/hooks/__init__.py`) as
  `"session_end": sweep_stale_refs.handle`, and `_USAGE` already lists
  `session_end`. **No Python handler or dispatch changes are required.**

Remaining work is the Codex transport layer plus bookkeeping:
1. Add `scripts/little_loops/hooks/adapters/codex/session-end.sh` — 4-line shim
   mirroring `pre-compact.sh` (`export LL_HOOK_HOST=codex` → `INPUT=$(cat)` →
   `echo "$INPUT" | python -m little_loops.hooks session_end` → `exit $?`);
   `chmod +x`.
2. Add a `Stop` entry to `scripts/little_loops/hooks/adapters/codex/hooks.json`
   invoking `bash {{LL_PLUGIN_ROOT}}/hooks/adapters/codex/session-end.sh`
   (Codex's end-of-turn lifecycle event is named `Stop`; it has no separate
   `SessionEnd` event).
3. Add the four-test quartet to `scripts/tests/test_codex_adapter.py`
   (path constant + file-exists + executable-bit + `Stop` key presence +
   `LL_HOOK_HOST=codex` sentinel), mirroring the `post-tool-use.sh` tests.
4. Flip the Codex cell on `docs/reference/HOST_COMPATIBILITY.md:30` from
   `(deferred)` to `✓`.

Supporting evidence: Codex fires a `Stop` event (confirmed in
`hooks/adapters/codex/README.md`, `docs/codex/README.md`,
`docs/codex/usage.md`); the stale-cross-issue-ref sweep is host-agnostic, so a
real consumer now exists.

### Option B — Close as not-applicable with a tracking footnote

- Append `[^sessionend]` to the Codex `(deferred)` cell on
  `docs/reference/HOST_COMPATIBILITY.md:30` and add a matching `[^sessionend]:`
  definition block beside `[^postcompact]` (line 58) and `[^permreq]`
  (line 63), linking to ENH-2105 with the Codex CLI capability evidence.
- **Caveat from research:** "not-applicable" is factually inaccurate — Codex
  *does* emit `Stop`, and a host-agnostic consumer already exists. An honest
  footnote would read "deferred; consumer exists; wiring is ~4 small transport
  steps" (mirroring `[^postcompact]`'s "flips to ✓ when wired" phrasing), not
  "not applicable." This makes Option A the cleaner terminal state.

## Acceptance Criteria

- [ ] Decision recorded: wire `session_end` for Codex, or close as
  not-applicable (with the Codex CLI capability evidence either way)
- [ ] If wiring: handler follows the established adapter pattern
  (`hooks/adapters/codex/*.sh` + dispatch entry + tests), mirroring
  FEAT-1719's implementation
- [ ] If closing: `docs/reference/HOST_COMPATIBILITY.md` Codex
  `stop/session_end` cell gains a footnote linking to this issue with the
  rationale
- [ ] No remaining unannotated `(deferred)` cells in the Codex column

## Integration Map

### Files to Modify
- `docs/reference/HOST_COMPATIBILITY.md` — Codex column annotation
- (If wiring) `hooks/adapters/codex/` + `scripts/little_loops/hooks/` +
  `scripts/tests/test_codex_adapter.py`

### Similar Patterns
- FEAT-1719 — PostCompact intent wiring for Codex (same decision shape and
  handler pattern)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Stale path correction:** the Integration Map's `hooks/adapters/codex/` is
  README-only since FEAT-2274 moved the shims. The live Codex adapter directory
  is `scripts/little_loops/hooks/adapters/codex/` (contains `session-start.sh`,
  `pre-compact.sh`, `prompt-submit.sh`, `post-tool-use.sh`, `hooks.json`).
  `hooks/adapters/codex/` now holds only `README.md` (which already marks `Stop`
  as "Deferred").
- **Handler already exists — wiring is transport-only.** `session_end` is
  registered in `_dispatch_table()` (`scripts/little_loops/hooks/__init__.py`)
  → `sweep_stale_refs.handle` (`scripts/little_loops/hooks/sweep_stale_refs.py`,
  FEAT-1680, `done`). Contrast FEAT-1719 (post_compact), which still needs a new
  handler module *and* a dispatch entry; `session_end` needs neither.
- **Exact target cell:** `docs/reference/HOST_COMPATIBILITY.md:30`, row
  `` `stop` → `session_end` ``, 3rd data column (Codex) = the second bare
  `(deferred)`. The Current Behavior and Verification Notes cite "line 28" —
  stale; the row has drifted to line 30 as intents were added above it.
- **Codex `hooks.json` today** (`scripts/little_loops/hooks/adapters/codex/hooks.json`)
  registers only `SessionStart`, `PreCompact`, `UserPromptSubmit`, `PostToolUse`
  — no `Stop`/`SessionEnd` key.
- **Codex `Stop` payload schema is undocumented** — no research note records
  whether Codex's `Stop` event carries `cwd`. `sweep_stale_refs.handle` reads
  `event.payload.get("cwd")` with a fallback to `event.cwd` (adapter working
  dir), so it degrades gracefully if `cwd` is absent. (UNKNOWN — verify against
  a live Codex `Stop` payload if wiring.)
- **Out-of-scope sibling gap:** the OpenCode cell on the same row (line 30, 2nd
  data column) is *also* an unannotated `(deferred)`, but ENH-2105's Scope
  Boundaries limit it to the Codex column — leave the OpenCode cell alone.
- **Footnote precedent (Option B):** `[^postcompact]` (line 58) and
  `[^permreq]` (line 63) are the in-file patterns to match; `[^runnercap]`
  (line 121, → ENH-2124) is the precedent for a "documented permanent /
  unresearched gap" footnote.

### Documentation (Option A only)

_Wiring pass added by `/ll:wire-issue`:_

If Option A is chosen, **five additional doc files** each assert the current
"Stop is deferred / four-hooks" state and drift stale the moment `Stop` is
wired. Option B touches none of these (only `HOST_COMPATIBILITY.md`). All
references are Codex-adapter-scoped; leave OpenCode/Claude-Code docs alone.

- `hooks/adapters/codex/README.md` — 3 locations [Agent 2 finding]:
  (a) `## Event → Intent Mapping (MVP)` table — `Stop` row currently
  `| `Stop` | — | — | Deferred |`; flip to `session_end` /
  `python -m little_loops.hooks session_end` / `Implemented`.
  (b) `## Trust Model` key code block — add the 5th trust key
  `file:<project>/.codex/hooks.json:stop:0:0`.
  (c) `## Smoke Test` shim enumeration — add `session-end.sh` as the 5th
  sibling shim.
- `docs/codex/README.md` — 2 locations [Agent 2 finding]:
  (a) `## What works → Hook intents` table — `stop` row `deferred` → `✓ wired`.
  (b) `## What is deferred` prose — remove `stop` from the deferred list
  (leave `post_compact` / `permission_request`).
  **CAUTION:** `test_wiring_guides_and_meta.py:59` asserts the substring
  `"deferred"` must remain in this file — it stays satisfied because the two
  sibling intents are still deferred; do **not** delete the word `deferred`.
- `docs/codex/getting-started.md` — 3 locations [Agent 2 finding]:
  (a) "little-loops registers **four** hooks…" prose → five (two count refs:
  `## Trust prompt` intro and `## First-run verification`).
  (b) trust-key code block — add `stop:0:0`.
  **CAUTION:** `test_wiring_guides_and_meta.py:68` asserts the substring
  `"session_start:0:0"` must remain here — adding `stop:0:0` is additive and
  safe; do not remove the existing key.
- `docs/codex/usage.md` — 1 location [Agent 2 finding]:
  `### Hook intents without consumers` — remove `stop` from the
  "fire but have no consumer" list (keep `post_compact`, `permission_request`).
- `docs/reference/API.md` — 1 location [Agent 2 finding]:
  `**Adapter integration:**` bullet under `little_loops.hooks` — add
  `session-end.sh` to the enumerated Codex shim list
  (`session-start.sh`, `pre-compact.sh`, …).

### Tests

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_codex_adapter.py::test_adapter_files_exist` — **extend**
  (not new): add `SESSION_END = ADAPTER_DIR / "session-end.sh"` constant and
  `assert SESSION_END.is_file()`. Note this test also asserts the repo-root
  `hooks/adapters/codex/README.md` exists [Agent 3 finding].
- `scripts/tests/test_codex_adapter.py::test_adapter_scripts_are_executable` —
  **extend**: add `assert os.access(SESSION_END, os.X_OK)` [Agent 3 finding].
- `scripts/tests/test_codex_adapter.py::test_hooks_json_has_stop` — **new**,
  mirror `test_hooks_json_has_post_tool_use` (assert `"Stop"` key + command
  references `session-end.sh`) [Agent 3 finding].
- `scripts/tests/test_codex_adapter.py::test_session_end_sets_ll_hook_host_codex`
  — **new**, clone `test_post_tool_use_sets_ll_hook_host_codex` (fake
  `__main__.py` sentinel pattern; assert `LL_HOOK_HOST=codex`) [Agent 3 finding].
- `scripts/tests/test_codex_adapter.py::test_session_end_exits_zero_without_config`
  — **new** (not listed in current Implementation Steps): real-dispatcher path
  against empty `tmp_path`, mirror `test_session_start_runs_without_config`;
  confirms the shim wires through to `sweep_stale_refs.handle` and exits 0
  [Agent 3 finding].
- `scripts/tests/test_hook_intents.py::test_dispatch_session_end_happy_path`
  and `::test_dispatch_table_merges_hook_intent_registry` — **already green,
  no change**: `session_end` is already in `_dispatch_table()`. These cover the
  Python side; the new Codex tests cover the transport side [Agent 3 finding].
- `scripts/tests/test_sweep_stale_refs.py` and
  `scripts/tests/test_hooks_integration.py::TestSessionEndSweep` — unaffected
  (handler-logic and claude-code-adapter coverage respectively) [Agent 3].

### Verified Clean — No Wiring Needed (Option A)

_Wiring pass added by `/ll:wire-issue`:_

These surfaces were checked and require **no** change; recording so the
implementer doesn't re-investigate [Agent 1 + Agent 2 findings]:

- `scripts/little_loops/package_data.py` — `("hooks","adapters","codex","hooks.json")`
  already registered; `.sh` shims are not read via `importlib.resources`, so
  `session-end.sh` needs no manifest entry.
- `scripts/pyproject.toml` — `[tool.hatch.build.targets.wheel]`
  `include = ["little_loops/**", …]` glob auto-captures the new `.sh`.
- `scripts/little_loops/hooks/__init__.py` — `session_end` → `sweep_stale_refs.handle`
  already in `_dispatch_table()`; `_USAGE` already lists it.
- `scripts/little_loops/init/writers.py` (`install_codex_adapter`) — copies
  `hooks.json` verbatim; the new `Stop` key is picked up with no code change.
- `ll-doctor` (`describe_capabilities()`) — reflects the new key automatically
  after `ll-init --hosts codex` re-runs.
- `.claude/CLAUDE.md` — `## Key Directories` notes the FEAT-2274 path move but
  does not enumerate Codex hook events; no update needed.

## Implementation Steps

_The branch depends on the decision recorded in Proposed Solution._

**Option A — wire (research-favored):**
1. Create `scripts/little_loops/hooks/adapters/codex/session-end.sh` by copying
   `scripts/little_loops/hooks/adapters/codex/pre-compact.sh` and swapping the
   intent to `session_end`; `chmod +x`.
2. Add a `"Stop"` key to `scripts/little_loops/hooks/adapters/codex/hooks.json`
   (array → matcher group → `{ "type": "command", "command": "bash
   {{LL_PLUGIN_ROOT}}/hooks/adapters/codex/session-end.sh", "timeout": 15,
   "statusMessage": "Sweeping stale cross-issue status references..." }`),
   mirroring the Claude Code `Stop` block in `hooks/hooks.json:144`.
3. Extend `scripts/tests/test_codex_adapter.py`: add
   `SESSION_END = ADAPTER_DIR / "session-end.sh"`, include it in
   `test_adapter_files_exist` / `test_adapter_scripts_are_executable`, and add a
   `test_hooks_json_has_stop` plus a `test_session_end_sets_ll_hook_host_codex`
   sentinel test (clone `test_post_tool_use_sets_ll_hook_host_codex`).
4. Edit `docs/reference/HOST_COMPATIBILITY.md:30`, Codex column (3rd data cell):
   `(deferred)` → `✓`.
5. Verify: `python -m pytest scripts/tests/test_codex_adapter.py -v` and
   `python -m pytest scripts/tests/test_hook_intents.py -k session_end`.

### Wiring Phase — Option A doc-sync (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included if
Option A is implemented; the original steps 1–5 cover only the shim, hooks.json,
tests, and HOST_COMPATIBILITY.md. Skip this entire phase for Option B._

6. Add the third new test from step 3: `test_session_end_exits_zero_without_config`
   in `scripts/tests/test_codex_adapter.py` (clone `test_session_start_runs_without_config`).
7. Update `hooks/adapters/codex/README.md` (repo-root copy): flip the `Stop`
   row in `## Event → Intent Mapping (MVP)` to Implemented, add `stop:0:0` to
   the `## Trust Model` key block, and add `session-end.sh` to the `## Smoke Test`
   shim list.
8. Update `docs/codex/README.md`: flip the `stop` row in `## What works → Hook
   intents` to `✓ wired` and drop `stop` from `## What is deferred` (keep the
   word `deferred` — `test_wiring_guides_and_meta.py:59` asserts it).
9. Update `docs/codex/getting-started.md`: bump the two "four hooks" counts to
   five and add `stop:0:0` to the trust-key block (keep `session_start:0:0`).
10. Update `docs/codex/usage.md`: drop `stop` from `### Hook intents without
    consumers`.
11. Update `docs/reference/API.md`: add `session-end.sh` to the Codex shim list
    in the `**Adapter integration:**` bullet under `little_loops.hooks`.
12. Verify docs: `python -m pytest scripts/tests/test_wiring_guides_and_meta.py -v`
    (content-presence guards still pass) and `ll-check-links docs/codex/README.md
    docs/codex/getting-started.md docs/codex/usage.md docs/reference/API.md`.

**Option B — close (annotate-only):**
1. Edit `docs/reference/HOST_COMPATIBILITY.md:30` Codex cell →
   `(deferred)[^sessionend]`; add a `[^sessionend]:` block near line 58 linking
   ENH-2105 with the Codex CLI capability evidence.
2. Verify: `ll-check-links docs/reference/HOST_COMPATIBILITY.md` (footnote
   resolves) and re-read the row to confirm no unannotated Codex `(deferred)`
   remains.

## Scope Boundaries

- Only the `stop/session_end` intent for the Codex adapter is in scope; other
  deferred Codex intents (`post_compact`, `permission_request`) are tracked
  separately under FEAT-1719.
- No changes to the Claude Code or OpenCode adapters.
- Wiring is not mandated — closing the cell as not-applicable with a tracking
  footnote is an acceptable resolution.

## Impact

- **Priority**: P5 — bookkeeping/parity tracking, matches sibling priorities
- **Effort**: Small
- **Risk**: Low
- **Breaking Change**: No

## Verification Notes

2026-06-18 (ACCURATE): `HOST_COMPATIBILITY.md` line 28 shows `(deferred)` in the Codex column for `stop → session_end`. No footnote links to ENH-2105. The issue's goal of annotating the cell with a tracking link is still unmet.

## Status

**Open** | Created: 2026-06-12 | Priority: P5


## Session Log
- backlog-grooming - 2026-07-03T00:00:00Z - EPIC-1463 tail cleanup: status -> cancelled per decision SCOPE-040 in .ll/decisions.yaml (epic 23/30 done; value delivered).
- `/ll:wire-issue` - 2026-06-26T23:21:13 - `80f7e865-5668-4056-97f7-9794b7b8c70e.jsonl`
- `/ll:refine-issue` - 2026-06-26T23:06:53 - `dd615d1a-afd0-4f66-9794-e4db982d1247.jsonl`
- `/ll:format-issue` - 2026-06-26T22:55:38 - `de5d48f0-01ea-4558-81b3-5f768a6c1cdf.jsonl`
