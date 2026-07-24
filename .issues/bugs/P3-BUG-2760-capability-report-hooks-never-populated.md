---
id: BUG-2760
type: bug
priority: P3
status: open
captured_at: '2026-07-24T19:36:28Z'
discovered_date: 2026-07-24
discovered_by: capture-issue
parent: EPIC-2765
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
decision_needed: false
---

# BUG-2760: CapabilityReport.hooks never populated — ll-doctor Hooks section is dead

## Summary

`ll-doctor` renders a "Hooks" section from `CapabilityReport.hooks`, but no
`HostRunner` implementation ever populates that list — `HookEntry(...)` is
constructed only inside `scripts/tests/test_cli_doctor.py`. The section
therefore never prints for any real host, while
`docs/reference/HOST_COMPATIBILITY.md:312` explicitly promises a report with one
entry "per registered hook event."

## Steps to Reproduce

1. Run `ll-doctor` (or `ll-doctor --json`) on any host.
2. Observe no `Hooks` section appears in the output; the JSON `hooks` array is empty.
3. `grep -rn "HookEntry(" scripts/` returns matches only in
   `scripts/tests/test_cli_doctor.py`.

## Current Behavior

- `HookEntry` dataclass and the `hooks` field exist and are exported.
- `_print_report` in `scripts/little_loops/cli/doctor.py` has a fully-implemented
  rendering branch for hooks that is unreachable in practice.
- The `"installed" | "registered" | "deferred" | "absent"` statuses in
  `_STATUS_SYMBOLS` exist solely to serve that dead branch.
- Docs advertise per-hook status output that users never see.

## Expected Behavior

Either:
- **(a)** Each runner populates `hooks` with the real installation status of the
  hook intents it supports, so `ll-doctor` reports hook wiring; or
- **(b)** The `hooks` field, its rendering branch, its status symbols, and the
  documentation claim are removed together.

(a) is the more useful outcome given the hook surface has grown substantially
since the field was introduced — `hooks/hooks.json`, the per-host adapters under
`hooks/adapters/{claude-code,opencode,codex}/`, and the host-agnostic Python
handlers under `scripts/little_loops/hooks/` dispatched by `main_hooks()`.

## Root Cause

- **File**: `scripts/little_loops/host_runner.py`
- **Anchor**: every `describe_capabilities()` implementation
- **Cause**: `CapabilityReport.hooks` defaults to an empty list
  (`field(default_factory=list)`) and no runner overrides it. The consumer side
  was built (FEAT-1496/1503/1524 chain) but the producer side never landed, and
  no test asserts a non-empty `hooks` list for a real runner — the only coverage
  constructs `HookEntry` by hand.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `HookEntry` is defined at `host_runner.py:145` (frozen dataclass: `name`,
  `status: Literal["installed", "registered", "deferred", "absent"]`, `note`).
  `CapabilityReport.hooks` field is at `host_runner.py:169`.
- All six `describe_capabilities()` implementations construct `CapabilityReport(...)`
  without a `hooks=` kwarg, confirmed at: `ClaudeCodeRunner` (`host_runner.py:366`),
  `CodexRunner` (`:647`), `OpenCodeRunner` (`:764`), `PiRunner` (`:837`),
  `GeminiRunner` (`:1011`), `OmpRunner` (`:1178`).
- `_print_report` in `cli/doctor.py` (lines 91-98) is fully implemented and
  correctly wired to `_STATUS_SYMBOLS`, but its `if report.hooks:` guard is
  always false in production. The JSON branch (line 73) always emits an empty
  `"hooks": []`.
- **No existing runner probes on-disk config to build a capability entry
  dynamically today** — the recent `json_schema` fix (BUG-2759, `host_runner.py:376-386`)
  only corrected a hardcoded status string, it did not add file-probing logic.
  Any (a)-path implementation would be the first dynamic-probe capability in
  this file.
- **Closest existing pattern for a per-project installed-hook-config probe**:
  `scripts/little_loops/init/writers.py` — `read_adapter_gen_version()` (line 489)
  checks `dest.exists()` and defensively `json.loads()`s `.codex/hooks.json`,
  returning `None` on absent/malformed file. It is Codex-only and returns a
  version stamp, not per-hook status, but is the template to model a hooks
  probe after. `install_codex_adapter()` (line 439) is the sibling writer.
- Claude Code has no equivalent per-project "installed" artifact to read back —
  `hooks/hooks.json` is the plugin manifest itself (loaded directly by Claude
  Code), so for this host `installed` likely just means "the plugin is active,"
  not a separate on-disk check. OpenCode's adapter (`hooks/adapters/opencode/`)
  is a Node/TypeScript plugin package with no `hooks.json` equivalent either —
  no reader exists for its installed state.
- The canonical intent enumeration is `_INTENT_EVENT_NAME` in
  `scripts/little_loops/hooks/__init__.py:66` (not `_USAGE`, which is a
  docstring/banner list per `reference_dispatch_table_usage_banner` — see
  `scripts/little_loops/hooks/__init__.py:50-54`): `pre_compact`,
  `pre_compact_handoff`, `session_start`, `session_end`, `user_prompt_submit`,
  `post_tool_use`, `pre_tool_use`, `edit_batch_nudge`, `subagent_start`,
  `subagent_stop`.
- `scripts/tests/test_host_runner.py`'s `TestDescribeCapabilities` class
  (line 1014) is the test-pattern template to mirror: `report = XRunner().describe_capabilities()`,
  `by_name = {e.name: e for e in report.capabilities}`, assert on `.status`.
  No existing test asserts anything about `report.hooks` from a real runner —
  `test_hooks_populated_for_claude_code`-style coverage would be new.
- **Sibling coordination**: `P2-BUG-2759-ll-doctor-always-exits-1-on-claude-code.md`
  (same EPIC-2765) touches the same `describe_capabilities()` methods and
  `_print_report()` — sequence or coordinate these two fixes to avoid merge
  churn on the same functions.

_Gap-analysis pass 2026-07-24 — anchor re-verification:_

- ⚠ The six `CapabilityReport(` line numbers above have each drifted **+1**
  since the last pass (commit `ea7c10c4` touched `ClaudeCodeRunner`). Current:
  `ClaudeCodeRunner` `host_runner.py:367`, `CodexRunner` `:648`,
  `OpenCodeRunner` `:765`, `PiRunner` `:838`, `GeminiRunner` `:1012`,
  `OmpRunner` `:1179`. All other cited anchors re-verified accurate
  (`HookEntry` `:145`, `hooks` field `:169`, `_INTENT_EVENT_NAME`
  `hooks/__init__.py:66`, `read_adapter_gen_version` `writers.py:489`,
  `install_codex_adapter` `:439`, `TestDescribeCapabilities`
  `test_host_runner.py:1014`, `TestCmdCapabilities` `test_action.py:585`).
- ⚠ The `HOST_COMPATIBILITY.md` claim is at **line 313**, not 312 (cited as
  `:312` in two places below). Verbatim text: "prints a `CapabilityReport` with
  one entry per capability ... and per registered hook event."
- **Path (b) deletion detail**: of the four hook-only `_STATUS_SYMBOLS` keys
  (`cli/doctor.py:14-23`), `installed`/`registered`/`deferred`/`absent` are
  distinct dict keys but their glyphs (`✓`/`○`/`○`/`✗`) duplicate the
  capability-side `full`/`partial`/`unsupported` values — so removing the four
  keys is a safe pure deletion with no glyph loss.
- **Fourth doc site** (beyond `HOST_COMPATIBILITY.md`, `CLI.md`,
  `ARCHITECTURE.md`): `docs/reference/API.md:8752` — the `CapabilityReport`
  field table row `| hooks | list[HookEntry] | One entry per registered hook
  event. |`, plus the `hooks:` line in the dataclass block at `:8741` and the
  `### HookEntry` section at `:8710`. Under path (b) all three must go, and
  `API.md:8595`'s `__all__` listing must drop `"HookEntry"` in lockstep with
  `scripts/little_loops/__init__.py`.

## Motivation

Hook misconfiguration is a common, hard-to-diagnose failure mode (a hook that
silently never fires looks identical to a feature that does not exist).
`ll-doctor` is the natural place to surface it, and the data model for doing so
already ships — it is just never filled in. Meanwhile the documentation makes a
promise the tool does not keep, which erodes trust in the rest of the report.

## Proposed Solution

If pursuing (a): derive hook status per host by reading the host's registered
hook configuration and cross-checking against ll's own hook inventory —
`hooks/hooks.json` plus the adapter directory for the active host — mapping each
declared intent to `installed` / `registered` / `deferred` / `absent`. The
existing `_USAGE` intent list in `scripts/little_loops/hooks/__init__.py` is the
canonical intent enumeration to check against. Hosts with no hook mechanism
should report `absent` (or return an empty list and have `_print_report` skip
the section for them) rather than silently omitting the section everywhere.

If pursuing (b): delete `HookEntry`, the `hooks` field, the `_print_report`
branch, the four hook-only `_STATUS_SYMBOLS` entries, the test that constructs
them, and the `HOST_COMPATIBILITY.md` sentence.

### Codebase Research Findings

_Added by `/ll:refine-issue` (gap-analysis) — the two paths above, restated as
labelled options so the pending `decision_needed: true` can be resolved by
`/ll:decide-issue`:_

**Option A**: Populate `hooks` per host — derive hook status by reading the
host's registered hook configuration and cross-checking against ll's own hook
inventory (`hooks/hooks.json` plus the adapter directory for the active host),
mapping each declared intent to `installed` / `registered` / `deferred` /
`absent`. Hosts with no hook mechanism report `absent` (or return an empty list
and have `_print_report` skip the section for them). Effort Medium — this would
be the first dynamic on-disk-probe capability in `host_runner.py`, and only
Codex has a readable per-project installed artifact today (`.codex/hooks.json`
via `read_adapter_gen_version`); Claude Code and OpenCode have no equivalent
readback, so their statuses must be derived from plugin-active/manifest
presence rather than a per-project file.

> **Selected:** Option B — pure deletion scores 11/12 vs Option A's 6/12; Option A would be the first dynamic on-disk-probe capability in `host_runner.py` with no analogous pattern for 2 of 3 real hosts.

**Option B**: Remove the dead surface — delete `HookEntry`, the `hooks` field,
the `_print_report` branch, the four hook-only `_STATUS_SYMBOLS` entries, the
`HookEntry`-constructing test, the `__init__.py` re-exports and `__all__`
entries, the `WIRING_CASES` tuples in `test_wiring_reference_docs.py`, and the
doc claims in `HOST_COMPATIBILITY.md:313`, `CLI.md:230-259`,
`ARCHITECTURE.md:877`, and `API.md:8710/8741/8752`. Effort Small — a pure
deletion of unreachable code, but it also deletes the `ll-action capabilities
--output json` `hooks` key, which is a live (if always-empty) JSON output field.

**Recommended**: Option A — "the more useful outcome given the hook surface has
grown substantially since the field was introduced," per the Expected Behavior
section above. Note the confidence-check flagged this recommendation as not yet
formally decided.

⚠ **Correction to the paragraph above**: it names `_USAGE` in
`scripts/little_loops/hooks/__init__.py` as "the canonical intent enumeration to
check against." That is wrong — `_USAGE` (line 108) is a static
docstring/usage banner, not a dispatch source. The canonical enumeration is
`_INTENT_EVENT_NAME` at `scripts/little_loops/hooks/__init__.py:66`. Use that
one. (The Integration Map's "Dependent Files" entry repeats the same `_USAGE`
error.)

### Decision Rationale

_Added by `/ll:decide-issue`:_

**Selected**: Option B — remove the dead `CapabilityReport.hooks` surface.

**Reasoning**: Parallel codebase-evidence gathering on both options found Option A
would be the first dynamic on-disk-probe capability in `host_runner.py`, and only
Codex has a per-project readable artifact to model it on (`.codex/hooks.json` via
`read_adapter_gen_version`) — Claude Code and OpenCode have no equivalent, so 2 of
3 real hosts would need a weaker manifest/plugin-active heuristic instead of a
direct file-read. Option A also carries concurrent merge-churn risk with sibling
`BUG-2759`, which touches the same six `describe_capabilities()` methods. Option B
is a mechanically clean deletion of code confirmed dead across all six runners
(`HookEntry(...)` is constructed only in `test_cli_doctor.py`); its main risk — a
JSON schema/`__all__` surface change for external consumers of `ll-action
capabilities --output json` or `little_loops.HookEntry` — is well-understood and
easily called out in the changelog, not a complexity risk. Evidence-gathering also
found the issue's `WIRING_CASES` claim about `test_wiring_reference_docs.py`
inaccurate — those tuples reference an unrelated module and need no edits, which
narrows Option B's touch-point list further. This overturns the issue's own
"Recommended: Option A" note; the rubric evidence favors B on every dimension.

**Scoring Summary**:

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|:-----------:|:----------:|:-----------:|:----:|:-----:|
| A — Populate hooks | 2 | 1 | 2 | 1 | 6/12 |
| B — Remove dead surface | 3 | 3 | 3 | 2 | **11/12** |

**Key Evidence**:
- All six `describe_capabilities()` implementations construct `CapabilityReport`
  without `hooks=`; only `test_cli_doctor.py` constructs `HookEntry` — confirms the
  field is dead in production, not just under-tested.
- `read_adapter_gen_version()` (`init/writers.py:489`) is the only directly
  reusable per-project hook-config probe pattern in the codebase, and it only
  covers Codex.
- `cmd_capabilities()` (`cli/action.py:364`) already serializes `report.hooks` to
  JSON unconditionally — real hosts already emit `"hooks": []` today, so removing
  the key changes shape, not observed value, for any consumer not doing strict
  key-presence checks.

## Integration Map

### Files to Modify
- `scripts/little_loops/host_runner.py` — `HookEntry`, `CapabilityReport`, each `describe_capabilities()`
- `scripts/little_loops/cli/doctor.py` — `_print_report`, `_STATUS_SYMBOLS`

### Dependent Files (Callers/Importers)
- `ll-action capabilities` — consumes the same `CapabilityReport`
- `scripts/little_loops/hooks/__init__.py` — `_USAGE` intent list (see the
  dispatch-table note: it is a static list requiring manual update)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/action.py` — `cmd_capabilities()` (line ~339 calls
  `describe_capabilities()`, line ~364 serializes `report.hooks` to
  `[{"name": h.name, "status": h.status, "note": h.note} for h in report.hooks]`
  for `ll-action capabilities --output json`). This is a **live** JSON consumer
  today: it always emits `"hooks": []` and will start emitting real content
  under path (a) with no schema change needed. [Agent 1/2 finding]
- `scripts/little_loops/__init__.py` — re-exports `CapabilityReport` and
  `HookEntry` in `__all__` (lines ~25-26, ~86-87). Only relevant under path
  (b): both symbols and their `__all__` entries must be removed in lockstep or
  the top-level package import breaks. [Agent 2 finding]

### Similar Patterns
- `hooks/hooks.json` and `hooks/adapters/*/` — the actual hook inventory to check against

### Tests
- `scripts/tests/test_cli_doctor.py` (currently the only `HookEntry` construction site)
- `scripts/tests/test_host_runner.py`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_host_runner.py::TestDescribeCapabilities` — the six
  `test_<host>_runner_returns_capability_report` methods (lines ~1017, 1060,
  1077, 1085, 1093, 1105) only assert on `.capabilities`, never on
  `report.hooks`. Under path (a), extend each with a
  `by_name_hooks = {h.name: h for h in report.hooks}` assertion following the
  existing `by_name = {e.name: e for e in report.capabilities}` idiom
  (line ~1028). This file uses repeated per-host methods, not
  `@pytest.mark.parametrize` — match that convention rather than introducing a
  new decorator. [Agent 3 finding]
- `scripts/tests/test_action.py::TestCmdCapabilities` (~line 598-606) — asserts
  `isinstance(output["hooks"], list)` only, not emptiness; won't break under
  path (a) but doesn't exercise a populated case — consider strengthening.
  [Agent 2 finding]
- `scripts/tests/test_wiring_reference_docs.py` (`WIRING_CASES`, lines ~155,
  157) — hard-asserts `docs/reference/API.md` contains the literal strings
  `CapabilityReport`, `CapabilityEntry`, `HookEntry`, `describe_capabilities`
  (tagged `FEAT-1462`). No change needed under path (a); under path (b) these
  tuples must be marked `# REMOVED (stale/false-positive)` per the file's
  existing convention or the test fails once the symbols/doc mentions are
  deleted. [Agent 2 finding]
- Reference pattern for a new on-disk hook-config probe's own tests:
  `scripts/tests/test_init_core.py:1197-1219` (tests `read_adapter_gen_version`)
  — `tmp_path`-based round-trip (write real file → assert value), missing-file
  → `None`/absent, malformed-JSON → graceful fallback, absent-field →
  fallback. [Agent 3 finding]

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md:312` — the unfulfilled per-hook claim
- `docs/reference/API.md` — `CapabilityReport` / `HookEntry` entries (~line 8732)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` (~line 230-259) — a **second, previously unlisted**
  doc making the same unfulfilled promise: "Produces a `CapabilityReport` with
  one `CapabilityEntry` per capability ... and one `HookEntry` per registered
  hook event," plus a full example output block showing a populated `Hooks`
  section (`✓ pre_tool_use` / `○ post_tool_use`). Needs the same reconciliation
  as `HOST_COMPATIBILITY.md:312` — update the example under path (a), remove
  the block under path (b). [Agent 2 finding]
- `docs/ARCHITECTURE.md` (lines ~875, 877) — `CapabilityReport`/`HookEntry`
  table rows; accurate as-is for path (a), need the `HookEntry` row removed and
  the `CapabilityReport` row's field list trimmed under path (b). [Agent 2
  finding]

### Configuration
- `hooks/hooks.json`

## Implementation Steps

1. Decide (a) populate vs. (b) remove; if (a), settle what each of the four
   statuses means for a hook intent.
2. Implement the producer side (or the removal) across all six runners.
3. Add a test asserting the real runner report matches the on-disk hook
   inventory — not a hand-built `HookEntry` fixture.
4. Reconcile `HOST_COMPATIBILITY.md` and `API.md` with actual behavior.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. If path (a): extend the six `TestDescribeCapabilities` methods in
   `scripts/tests/test_host_runner.py` with `report.hooks` assertions; if path
   (b): remove `HookEntry`/`CapabilityReport.hooks` from
   `scripts/little_loops/__init__.py`'s exports and `__all__`, and mark the
   corresponding `WIRING_CASES` tuples in `test_wiring_reference_docs.py` as
   `# REMOVED (stale/false-positive)`.
6. Reconcile `docs/reference/CLI.md` (~line 230-259) — a second doc making the
   same unfulfilled hooks-reporting promise, not previously listed — alongside
   `HOST_COMPATIBILITY.md` and `API.md`.
7. Under path (b) only: also trim the `CapabilityReport`/`HookEntry` rows in
   `docs/ARCHITECTURE.md` (~line 875, 877).
8. Verify `scripts/little_loops/cli/action.py::cmd_capabilities()` (the live
   `ll-action capabilities --output json` consumer of `report.hooks`) renders
   correctly once hooks are populated — no schema change needed, but exercise
   it manually or via `scripts/tests/test_action.py::TestCmdCapabilities`.

## Impact

- **Priority**: P3 - No incorrect output today, but a documented feature is
  entirely absent and dead code is accumulating around it.
- **Effort**: Medium if populating (needs a per-host hook-inventory probe);
  Small if removing.
- **Risk**: Low - Additive to the report, or a pure deletion of unreachable code.
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/HOST_COMPATIBILITY.md` | Makes the per-hook reporting claim |
| `docs/reference/API.md#capabilityreport` | `HookEntry` / `CapabilityReport` model |
| `docs/ARCHITECTURE.md` | `CapabilityReport` row (~line 875) |

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-24_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 57/100 → LOW

### Concerns
- Sibling issue `P2-BUG-2759` touches the same `describe_capabilities()` methods
  and `_print_report()` — sequence or coordinate the two fixes to avoid merge
  churn on the same functions.
- Path (a) vs (b) is still unresolved, and the two paths have very different
  effort/risk profiles (Medium probe-building vs. Small deletion) — the rest of
  this assessment is scored against path (a) since it's the "more useful
  outcome" the issue itself recommends, but that recommendation hasn't been
  formally decided.

### Outcome Risk Factors
- Fundamental approach unclear — this is an open decision between populating
  hooks (Option A) vs removing the dead field entirely (Option B), with no
  resolution yet in the issue. Resolve before implementing; different code
  actually gets written depending on which path is chosen.
- Broad enumeration across many low-depth sites — 6 `describe_capabilities()`
  implementations, `cli/doctor.py`, `cli/action.py`, `hooks/__init__.py`, 2
  test files, and 3 docs files, each individually a contained/local change but
  collectively a wide surface to touch consistently.

## Session Log
- `/ll:confidence-check` - 2026-07-24T21:20:00 - `66acd153-caee-48f4-966c-575333b4373a.jsonl`
- `/ll:decide-issue` - 2026-07-24T21:05:24 - `fe604afd-9cae-4551-acd4-0503d61e5326.jsonl`
- `/ll:refine-issue` - 2026-07-24T21:02:14 - `b16cc295-c985-4a92-9bd5-e5010f3088b7.jsonl`
- `/ll:confidence-check` - 2026-07-24T21:15:00 - `5698d968-99dc-4eb8-b4c3-57753b3aaea5.jsonl`
- `/ll:wire-issue` - 2026-07-24T20:57:47 - `4e7fc699-8c84-486f-a4ae-2bfee3a60b0c.jsonl`
- `/ll:refine-issue` - 2026-07-24T20:50:52 - `bbe805da-e510-43cb-887a-ebffdbc99b4f.jsonl`
- `/ll:capture-issue` - 2026-07-24T19:36:28Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/00041c0b-3526-41ec-b743-a686380c429a.jsonl`

---

## Status

**Open** | Created: 2026-07-24 | Priority: P3
