---
id: ENH-2885
type: ENH
priority: P3
status: done
captured_at: '2026-07-28T04:08:05Z'
completed_at: '2026-07-28T07:29:42Z'
discovered_date: 2026-07-28
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 84
score_complexity: 22
score_test_coverage: 20
score_ambiguity: 20
score_change_surface: 22
---

# ENH-2885: Read actual effort from session JSONL instead of resolved config value

## Summary

`_resolve_action_effort()` (`scripts/little_loops/fsm/executor.py:2278`) resolves the
displayed `effort` value purely from loop/state config precedence
(`state.effort or self.run_effort or self.fsm.llm.effort`), per a comment at
`executor.py:1713-1717` claiming "No host surface reports an 'actual' effort value
back". That comment is stale: the Claude Code host CLI's raw session JSONL does
report the actual effort applied, as a top-level `"effort"` field on every
`type: "assistant"` line (verified directly against a live session JSONL —
11/11 assistant lines carried `"effort": "low"`). The executor already opens this
file post-run for other purposes (`get_current_session_jsonl()` at
`executor.py:1732`, right next to the effort-resolution call), so the plumbing to
read it is already present.

## Current Behavior

`ll-loop run` only displays an effort level when the loop/state explicitly sets
`llm.effort` or a per-state `effort:` override. A loop like `autodev.yaml`, which
sets neither, shows no effort in its header/log output at all — even though the
host CLI is still applying some default effort level under the hood and reporting
it in the session JSONL.

## Expected Behavior

`action_complete`'s `effort` payload field reflects the actual effort the host CLI
applied for that call (read from `session_jsonl`'s assistant-line `"effort"`
field), falling back to the resolved config value only when the host doesn't
report one (e.g. non-Claude-Code hosts, or shell/mcp actions with no effort
concept). This makes the effort display meaningful even for loops that never set
an explicit effort override.

## Motivation

Surfaced while investigating why the currently-running `autodev` loop showed no
effort level in its output (ENH-2869's original feature). The proximate cause is
that autodev has no `llm.effort` configured, but the deeper gap is that the
CLI's effort display can never show anything beyond what the loop author
explicitly configured — it can't reveal what the host actually did by default,
even though that information already exists in the session log little-loops is
already reading.

## Impact

- **Priority**: P3 - Display-only correctness gap; no functional breakage,
  affects operator-facing effort reporting only
- **Effort**: Small - The session JSONL path is already resolved at the exact
  call site (`executor.py:1732`); this adds a read-and-parse step and a
  fallback, mirroring the existing `model` observed-value override pattern
- **Risk**: Low - Additive payload field with a config-value fallback; no
  existing behavior changes when the JSONL has no effort field
- **Breaking Change**: No

## Scope Boundaries

Out of scope: parsing the live stream-json subprocess output
(`subprocess_utils.py:463-519`) for effort — this issue only reads the
on-disk session JSONL via the already-resolved `get_current_session_jsonl()`
path. Also out of scope: changing the static, pre-action `effort=fsm.llm.effort`
header display threaded into `run_foreground()`/`StateFeedRenderer`
(`cli/loop/run.py:602`, `cli/loop/lifecycle.py:618,700`) — that is a
config-only, pre-action display and is architecturally separate from the
per-action `action_complete.payload["effort"]` this issue changes.

## Proposed Solution

- In `_resolve_action_effort()` (or the call site at `executor.py:1718`), after
  action execution, parse the `session_jsonl` path already resolved at
  `executor.py:1732` for the most recent `type: "assistant"` line's top-level
  `"effort"` field.
- If found, prefer it over the config-resolved value for the `payload["effort"]`
  written into the `action_complete` event.
- Keep the config-resolved value as the fallback for hosts/action modes where no
  JSONL effort field is available (matches the existing `model` fallback
  pattern already used nearby).
- Update/remove the stale "No host surface reports an actual effort value back"
  comment at `executor.py:1713-1717`.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `_resolve_action_effort()` and the
  `action_complete` payload construction around line 1718-1735

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/_helpers.py:1094` — already consumes
  `event.get("effort")` from `action_complete`; no change needed if the payload
  contract (a string effort level) stays the same

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/run.py:602` and
  `scripts/little_loops/cli/loop/lifecycle.py:618,700` — thread
  `effort=fsm.llm.effort` into `run_foreground()`/`StateFeedRenderer` for the
  loop-start header display. This is a static, pre-action config value and is
  architecturally separate from the per-action `action_complete.payload["effort"]`
  this issue changes — it will **not** automatically pick up the new
  JSONL-observed value. Not a required change for this issue, but confirm
  whether the header display staying config-only-by-design is the intended
  scope boundary (no code change needed unless scope expands).

### Tests
- `scripts/tests/` — add/extend a test covering effort resolution when a
  session JSONL with an `"effort"` field is present but no config-level effort
  is set

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_executor.py` — `TestStderrPreview` (lines
  ~9801-9849) is the closest existing end-to-end shape to copy: its
  `_run_and_collect()` helper runs the executor with a `MockActionRunner` and
  filters emitted `action_complete` events. No existing test asserts
  `payload["effort"]` or `payload["model"]` at all — this is currently
  uncovered at the payload level, not just untested for the new behavior.
- `scripts/tests/test_session_log.py` — existing fixtures (`TestGetCurrentSessionJsonl`,
  lines 20-93) only cover file *discovery* (writing placeholder `"{}"` content
  or mocking `get_current_session_jsonl` directly); none construct real
  newline-delimited JSON *content* with a `type: "assistant"` / `"effort"`
  field for a parser to read. A new fixture writing real JSONL lines is needed.
- Add a fallback-to-config test: when `get_current_session_jsonl()` returns
  `None`, or the resolved file has no `"effort"` field on any assistant line,
  `payload["effort"]` must still fall back to `_resolve_action_effort()`'s
  config-resolved value — mirrors the existing `model` guard's
  `if result.usage_events:` pattern at executor.py:1737.

### Documentation
- N/A

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` (lines ~563, 617, 625, 686) — describes the
  `--effort` flag/display as reflecting "the resolved config value" (state
  override, `--effort` run override, or loop-level `llm.effort` default);
  needs updating once the displayed value can be JSONL-observed.
- `docs/reference/API.md` (lines ~5099, 5304) — `effort: str | None` dataclass
  field docstrings state "resolved via `state.effort` or `self.run_effort` or
  `self.fsm.llm.effort` (ENH-2869)"; needs updating to describe the new
  JSONL-observed resolution path.
- `scripts/little_loops/fsm/schema.py` (`StateConfig.effort` ~lines 673-678,
  `LLMConfig.effort` ~lines 939-943) — inline comments document the same
  stale config-only precedence chain referenced by the executor.py:1713-1717
  comment this issue already plans to update; update these in the same pass
  for consistency.

### Configuration
_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/schemas/action_complete.json` — does not currently declare
  an `"effort"` property at all (`additionalProperties: true` means adding
  one won't break validation, but it stays undocumented otherwise). If this
  issue formalizes `payload["effort"]` as a first-class observed-value field
  (mirroring how `model` is already a declared property), add the schema
  property and regenerate via `ll-generate-schemas`
  (`scripts/little_loops/generate_schemas.py`), gated by
  `scripts/tests/test_generate_schemas.py`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Config-only resolver today** — `_resolve_action_effort()` at
  `executor.py:2278-2286` mirrors `_resolve_action_model()` at
  `executor.py:2265-2276`, both doing pure `state.X or self.run_X or
  self.fsm.llm.X` precedence with no runtime signal. Unlike `model` (which
  always resolves non-empty because `LLMConfig.model` defaults to
  `DEFAULT_LLM_MODEL`), `effort` can legitimately resolve to `None` since
  `LLMConfig.effort` defaults to `None` — this is the exact case the issue
  wants to fill from the JSONL instead.
- **The "model" pattern to mirror is not `_resolve_action_model()` itself** —
  it's the post-hoc override at `executor.py:1736-1747`, where after the
  action runs, `payload["model"] = result.usage_events[-1].model` overwrites
  the payload with the *actually observed* model from the host CLI's own
  usage events, independent of the config value used at dispatch time
  (`executor.py:1709`). The new effort code should follow this same
  "dispatch with resolved config, then overwrite payload with observed
  value if available" shape — read the JSONL after `result` comes back,
  before the `if effort_value is not None: payload["effort"] = effort_value`
  write at line 1734-1735, and prefer the JSONL value over `effort_value`
  when found.
- **`get_current_session_jsonl()` only returns a path, never parses it** —
  defined at `session_log.py:63-96`; already called at `executor.py:1732`
  purely to stash `str(session_jsonl)` into `payload["session_jsonl"]`. It
  race-guards `OSError` on `stat()` per-file (BUG-2489) and returns `None` on
  any resolution failure — the new code must treat that `None` (and any
  read/parse failure on the file itself) as "fall back to `effort_value`",
  not raise.
- **No existing helper reads a specific field from the *on-disk* session
  JSONL** — the closest analog is the `_backfill_*` family in
  `session_store.py` (e.g. `_backfill_tool_events()` at line ~3560), which
  all follow the same shape: iterate lines, `json.loads()`, `except
  json.JSONDecodeError: continue`, `if record.get("type") != "assistant":
  continue`. None of them track "most recent line of a type" — they
  accumulate every match. `cli/logs.py:93-107` is another JSONL-iteration
  reference showing the same `json.loads`-per-line idiom. For "most recent
  assistant line's effort field," a simple last-write-wins loop (`for line
  in handle: ... candidate = value`) is the right idiom — same as
  `usage_events[-1].model` takes the last entry.
- **Distinct from the in-process stream-json parsing** —
  `subprocess_utils.py:463-519` already parses `type: "assistant"` events,
  but from the host CLI subprocess's live stdout (`--output-format
  stream-json`), not the on-disk session JSONL file `get_current_session_jsonl()`
  points to. These are two different JSONL streams; the live stream's
  `assistant` events currently only pull `message.content` text and are not
  inspected for `"effort"` — reading the on-disk session JSONL (per the
  issue's proposal) is the simpler integration point since the path is
  already resolved right where `effort_value` is used.
- **Existing effort-resolution unit tests** —
  `scripts/tests/test_ll_loop_execution.py`: `test_run_effort_used_as_fallback`
  (line 1121-1137), `test_state_effort_overrides_run_effort` (line
  1139-1155), `test_llm_effort_used_when_no_state_or_run_effort` (line
  1157-1174) — all call `_resolve_action_effort()` directly with no JSONL
  involved. A new test should follow `test_session_log.py`'s fixture
  pattern (writes real newline-delimited JSON to a `tmp_path` file, patches
  project-folder resolution) to construct a fixture JSONL with `type:
  "assistant"` lines carrying `"effort"`, then assert the JSONL value wins
  over/without a config-level effort set.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Update `scripts/little_loops/fsm/schema.py` — refresh the stale
   config-only-precedence comments on `StateConfig.effort` and
   `LLMConfig.effort` alongside the `executor.py:1713-1717` comment.
2. Add the JSONL-content-parsing fixture to `scripts/tests/test_session_log.py`
   (or a new test module) and the end-to-end `payload["effort"]` test in
   `scripts/tests/test_fsm_executor.py`, following `TestStderrPreview`'s
   `_run_and_collect` shape.
3. Add a fallback-to-config test for when no session JSONL / no effort field
   is present.
4. Decide and note (in this issue or a follow-up) whether
   `docs/reference/schemas/action_complete.json` needs a formal `"effort"`
   property + `ll-generate-schemas` regen, or whether the field stays
   implicit under `additionalProperties: true`.
5. Update `docs/reference/CLI.md` and `docs/reference/API.md` prose describing
   the effort-resolution chain to reflect the new JSONL-observed behavior.

## Session Log
- `/ll:manage-issue` - 2026-07-28T07:45:00 - `100c3e19-d98d-40b3-9cab-f24527b62ba7.jsonl`
- `/ll:ready-issue` - 2026-07-28T07:20:33 - `eada2722-8f10-4468-86f2-f0083c2ec4a4.jsonl`
- `/ll:wire-issue` - 2026-07-28T07:17:22 - `abd014d0-257a-45e4-9bd0-70df47c35384.jsonl`
- `/ll:refine-issue` - 2026-07-28T07:11:49 - `286ab7da-aefa-41e8-86da-8139a4adfbb2.jsonl`
- `/ll:capture-issue` - 2026-07-28T04:08:05Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4f9bac15-2758-49a3-9cff-cf5c0c7f07ff.jsonl`

---

## Status

**Current State**: Open
