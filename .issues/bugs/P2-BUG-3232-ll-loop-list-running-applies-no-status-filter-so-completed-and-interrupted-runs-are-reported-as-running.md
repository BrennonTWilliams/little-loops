---
id: BUG-3232
type: BUG
title: 'll-loop list --running: no status filter is applied, so completed, interrupted
  and user_stopped runs are reported as running'
priority: P2
status: done
discovered_by: little-loops-hermes-audit
discovered_date: '2026-08-17'
completed_at: '2026-08-17T15:34:33Z'
labels:
- loops
- cli-json
testable: true
confidence_score: 98
outcome_confidence: 72
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 15
verify_verdict: VALID
---

# BUG-3232: ll-loop list --running applies no status filter

## Summary

`--running` does not filter by status. It returns every `*.state.json` in
`.loops/.running/`, whatever state those runs ended in.

`list_running_loops` (`scripts/little_loops/fsm/persistence.py:1109`) is
documented on its own next line as *"List all loops with saved state"* — which
is exactly what it does, and is not what `--running` advertises.
`cmd_list` (`scripts/little_loops/cli/loop/info.py:113`) calls it for
`--running` and applies a status filter **only** when the separate `--status`
flag is present (`info.py:114-115`). Meanwhile the flag's own help text
(`scripts/little_loops/cli/loop/__init__.py:365`) reads `Only show running
loops`.

This is not a stale-directory problem that cleanup would fix. Those files are
*meant* to persist: `_reconcile_stale_runs` (`persistence.py:605`) archives
only `{completed, failed, timed_out}` (`persistence.py:622`), deliberately
spares `interrupted` so runs stay resumable, does not list `user_stopped` at
all, and is called at **loop startup** — never from `list`. So on any project
that has ever run a loop, `--running` reports that project's history.

Related to BUG-3231, which concerns what this same command *destroys* on the
empty path. This one concerns what it *returns* on the success path. They are
independent and either can be fixed without the other.

## Current Behavior

Probed live against `little-loops-hermes`, same directory, same process,
seconds apart:

```console
$ ll-loop list --running --json | python -c "import json,sys; [print(s['loop_name'], s['status']) for s in json.load(sys.stdin)]"
general-task user_stopped
general-task interrupted
general-task interrupted
general-task completed

$ ll-loop list --status running
No loops with status: running
```

Four "running" loops, zero running loops. The most recent of the four last
updated 2026-07-26; the oldest, 2026-06-18.

The human-readable path is aware of this and accommodates it rather than
preventing it — `_STATUS_COLORS` in `info.py` assigns colors to `interrupted`,
`user_stopped` and `stopped`, printed under a header that reads
`Running loops:`. So in a terminal the output is merely misleading, and colour
is the only thing distinguishing a live run from a month-old one.

`--json` has no colour. The machine-readable consumer gets four entries and
nothing in the payload marks them as finished unless it inspects `status`
itself — which is the field the flag was supposed to have filtered on.

## Expected Behavior

`ll-loop list --running` returns only dispatches that are actually executing,
and `ll-loop list --all-runs` returns every loop with saved state — the behavior
`--running` has today, under a name that describes it.

## Steps to Reproduce

1. In a project with `.loops/.running/` state files spanning multiple
   statuses (e.g. `completed`, `interrupted`, `user_stopped`, `running`), run:
   `ll-loop list --running --json | python -c "import json,sys; [print(s['loop_name'], s['status']) for s in json.load(sys.stdin)]"`
2. Observe that entries with `status` values other than `running` (e.g.
   `completed`, `interrupted`, `user_stopped`) are included in the output.
3. Run `ll-loop list --status running` against the same directory and observe
   it returns a strict subset (often empty) — confirming `--running` alone
   applies no status filter.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` (`cmd_list()`, lines 104-127) — the `--running` branch (entered via `getattr(args, "running", False) or status_filter` at line 110) calls `list_running_loops(loops_dir)` at line 113 and applies a `status == status_filter` list-comprehension filter at lines 114-115 **only when `--status` is also set**. No equivalent filter line exists for the `--running`-alone case. The branch condition at line 110 must also admit `--all-runs`, and the allowlist must be applied in an `elif`-style relationship to the `--status` filter (see Proposed Fix ▸ Flag interaction).
- `scripts/little_loops/cli/loop/__init__.py` (lines 363-370, plus the usage epilog at line 119) — declares the `list` subparser's flags; `--all-runs` is added here.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/transport.py:588` (`_make_seed_callback()._seed()`) — the **other** caller of `list_running_loops()`. It emits a `state_change` event for every returned state, regardless of status, to seed a freshly-connected observability/dashboard client with the full on-disk snapshot (including recently-finished runs). This caller depends on `list_running_loops()` itself continuing to return the unfiltered set — filtering must happen in `cmd_list()`, not inside `list_running_loops()`, or this caller silently stops seeding terminal-status history to new clients.
- `scripts/little_loops/cli/loop/__init__.py:365-369` — declares `--running` (`store_true`, help "Only show running loops") and `--status` (free-form string, help already names `interrupted`/`awaiting_continuation` as example filter values) as independent, non-mutually-exclusive arguments.
- `scripts/little_loops/fsm/persistence.py:1011` (`PersistentExecutor.resume()`) — the one existing consumer of `RESUMABLE_STATUSES`, a precedent for a shared status-set constant, but its membership (`running`, `awaiting_continuation`, `interrupted`, `user_stopped`) answers "can this be resumed," not "is this currently executing," so it is not reusable as-is for this filter.

_Wiring pass added by `/ll:wire-issue`:_
- `skills/cleanup-loops/SKILL.md:34` — Step 1 enumeration runs `ll-loop list --running --json` and its own prose documents the *current* unfiltered behavior as the mechanism: "returns all loops that have a `.state.json` file... regardless of whether they are actually running." That is exactly the pre-fix behavior this issue reports as a bug. Once `--running` alone starts applying the `{running, starting}` allowlist, this skill will stop seeing `interrupted`/`failed`/`timed_out`/`completed` entries through this call and its stale-loop discovery step will silently narrow.
- `skills/debug-loop-run/SKILL.md:53-64` — calls `ll-loop list --running --json` then applies its own client-side filter for `running`/`interrupted`/`failed`/`timed_out`/`awaiting_continuation` candidates. After the fix, the CLI call itself will already exclude everything but `running`/`starting`, so this skill's client-side filter for the other statuses becomes permanently dead — it will never see those candidates through this path again.
- `skills/audit-loop-run/SKILL.md:54-57` — same pattern and same impact as `debug-loop-run/SKILL.md` above.
- `scripts/tests/test_ll_loop_integration.py:327` (`test_list_running_reconciles_dead_pid_entries`, a BUG-1731 regression test) — issues a bare `ll-loop list --running` (no `--status`) against one live `running` state and one dead-PID state reconciled to `interrupted`, and asserts (lines 397-406) **both** rows appear in the output, with the reconciled one shown as `[paused]`. This directly contradicts the planned allowlist filter: under the fix, the reconciled `interrupted` entry must no longer appear under bare `--running`. This test's assertions must change as part of implementing this fix, not just be left standing.

### Conventions in Force
- This codebase holds two different, disagreeing styles for status-set filters — a module-level shared `frozenset` constant reused across call sites (`RESUMABLE_STATUSES`, `persistence.py:46-51`) vs. an ad hoc local `set` literal defined once inline (`terminal_statuses` in `_reconcile_stale_runs()`, `persistence.py:622`). Neither precedent is settled; a new "active/running" status set can follow either shape.
- Bug-fix test coverage in this codebase adds new test *methods* into the existing class that already covers the touched function, citing the bug ID in a docstring or leading comment — it does not create a new class per bug ID. Evidence: `test_fsm_persistence.py:2148` (`# list_running_loops skip/unreadable diagnostics (BUG-3231)` above two methods added to the pre-existing `class TestCorruptedStateFiles:`); `test_sprint.py:401,432,464,3021` (four methods citing `(BUG-3229)` spread across existing classes).
- `cmd_list()`'s existing `--status` filter idiom (`info.py:114-115`, `[s for s in states if s.status == status_filter]`) and its test scaffolding (`test_ll_loop_commands.py:670-737`, notably a `make_state(name, status)` helper at line 714) are the established pattern for constructing mixed-status `LoopState` lists and asserting on `cmd_list()` output — mocking `little_loops.fsm.persistence.list_running_loops` directly rather than writing real state files to disk.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/json-output-contracts.md:119-124` (section "Alternate entry point: `ll-loop list --running --json`") — explicitly documents current behavior as returning "the same base state objects" with no status filter; needs updating to describe the new `{running, starting}` allowlist and to clarify that `--status` still selects arbitrary statuses independently.
- `docs/reference/CLI.md:1216` — the flags table describes `--status` as meaningful only "with `--running`," implying bare `--running` returns everything unfiltered today; needs rewording once bare `--running` gets a default allowlist.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_persistence.py:1977-2002` (`TestUtilityFunctions::test_list_running_loops_returns_running_status`) — currently seeds `running`/`completed`/`failed` states and asserts `len(states) == 3` and all three statuses are returned. This test's docstring already claims the AC is "returns all loops with 'running' status," but its assertions currently lock in the no-filtering behavior this issue reports as the bug. If the fix filters inside `list_running_loops()` itself, this test's assertions need updating to match; if the fix filters only in `cmd_list()` (per the transport.py constraint above), this test's current assertions remain correct as-is for `list_running_loops()`'s own contract.
- `scripts/tests/test_ll_loop_commands.py:3830-3906` (`TestCmdListRunningJson`) — its 3 existing tests (`test_list_running_json_output`, `test_list_running_json_empty`, `test_list_running_without_json_unchanged`) all mock `list_running_loops` directly and only ever pass single-status or empty state lists; none currently exercises a mixed-status list to assert `--running` filters out terminal statuses. Add a new test here (or in `TestCmdList`) with a mixed-status mocked return (`running`, `completed`, `interrupted`, `user_stopped`) asserting only `running`/`starting` survive — model on the `make_state()` helper and `test_status_filter_matches` (`test_ll_loop_commands.py:714-737`).
- `scripts/tests/test_ll_loop_commands.py:732-771` (`TestCmdList::test_status_filter_matches`, `test_status_filter_no_match_returns_1`, `test_status_filter_no_match_json_emits_empty_array`) — establish the mocking/assertion idiom (see Conventions above) directly reusable for a new `--running`-alone filtering test.
- **New test needed**: a synthesized `status="starting"` entry surviving `--running` filtering — no existing `cmd_list`-level fixture constructs this (only `list_running_loops()`-level tests in `test_fsm_persistence.py:1546-1562` do, via a bare `.pid` file). Build inline via `make_state("loop-x", "starting")` per AC 3.
- **New test needed**: `--running` returns a superset of `--status running` for an identical mixed-status input, differing only by `starting` entries, per the revised AC 2 — no existing test combines both flags in one assertion. (The original wording of this item asked for *equality*, which is unsatisfiable once a `starting` entry is present.)
- `scripts/tests/test_ll_loop_integration.py:327` (`test_list_running_reconciles_dead_pid_entries`) — **must be updated**, not just noted; see Dependent Files above for why it currently conflicts with the fix, and Implementation Steps for which of its assertions must survive verbatim.

_Added by 2026-08-17 pre-implementation review:_
- **New test needed**: `--all-runs` returns the full mixed-status set (`running`, `starting`, `completed`, `interrupted`, `user_stopped`, `awaiting_continuation`) — i.e. the pre-fix `--running` behavior — using the same `make_state()` mocking idiom.
- **New test needed**: `--running --status interrupted` returns the `interrupted` entries, not `[]`. This pins the precedence decision (explicit `--status` overrides the allowlist) that the two flags' non-mutually-exclusive declaration makes reachable.
- **New test needed**: `awaiting_continuation` is absent from `--running` and present under both `--all-runs` and `--status awaiting_continuation`.
- **New test needed**: exit codes on the empty path — `--running` → 0, `--all-runs` → 0, `--status <no match>` → 1 — asserted in both `--json` and human-readable modes. This block (`info.py:116-124`) is also rewritten by BUG-3231; whichever lands second must not regress the other's assertions.
- **Verified, no change needed**: `scripts/tests/test_json_output_contracts.py:245-266` (`test_json_output_via_cmd_list_running`) — its mocked state defaults to `status="running"` and survives the allowlist.
- **Check on implementation**: `scripts/tests/test_cli_e2e.py:448` and `scripts/tests/test_cli.py:803` both run bare `--running` against an empty/fresh `.loops` and assert only `exit_code == 0`. They pass unchanged provided the empty-path exit code stays 0 (see AC) — they are the tripwire if it does not.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

### Types
- `LoopState.status: str` (`scripts/little_loops/fsm/persistence.py:268-329`) — a bare `str` field, no enum/Literal enforcement; any string round-trips through `to_dict()`/`from_dict()`.
- Observed producers of concrete `status` values: `"running"` (default, `_save_state()` line 879), `"completed"`/`"failed"` (`map_final_status()`, lines 117-153), `"interrupted"` (`map_final_status()` lines 137-143, and the dead-PID self-heal in `_reconcile_stale_running()` line 262), `"awaiting_continuation"` (`map_final_status()` line 144-145), `"timed_out"` (`map_final_status()` line 146-147), `"user_stopped"` (`cli/loop/lifecycle.py:476,486`, set directly by `ll-loop stop`, not via `map_final_status()`), `"system_signal"` (`fsm/executor.py:471`), `"starting"` (synthesized only in `list_running_loops()`, `persistence.py:1170`, never persisted to a state file).

### Signatures
- `list_running_loops(loops_dir: Path) -> list[LoopState]` — defined at `persistence.py:1109`; globs `.running/*.state.json`, applies the `_reconcile_stale_running()` liveness self-heal (running → interrupted on dead PID) to each, then appends a synthesized `status="starting"` entry per live-PID `.pid` file with no matching state file. No status-based filtering exists in this function today.
- `cmd_list(args, loops_dir)` — defined at `info.py:104`; reads `getattr(args, "running", False)` and `getattr(args, "status", None)`. Both flags share one entry branch (line 110) but only `--status` currently narrows the result set (lines 114-115). Post-fix it also reads `getattr(args, "all_runs", False)` — argparse derives `dest="all_runs"` from `--all-runs` by default, matching the existing idiom at lines 109-110.

### Call Path
`cmd_list` (`info.py:104`) -> `list_running_loops` (`persistence.py:1109`) -> [no status filter applied when only `--running` is set] -> JSON emission (`info.py:125-127`, `print_json([s.to_dict() for s in states])`) or human-readable table (colorized via `_STATUS_COLORS`, `info.py:132-139`, and `display_status` remapping `interrupted`/`user_stopped` → `"paused"` at `info.py:158-163`).

Separately: `transport.py:588` (`_make_seed_callback()._seed()`) -> `list_running_loops` (`persistence.py:1109`) -> unconditional `state_change` event emission for every returned state, regardless of status — this path must keep receiving the unfiltered result set from `list_running_loops()` itself.

### Decision Rules

_Revised by 2026-08-17 pre-implementation review — the three rules below are
decisions the original draft left implicit:_

1. **Allowlist vs. `--status` precedence.** `--running` and `--status` are declared as independent, non-mutually-exclusive `store_true`/free-form arguments (`__init__.py:365-369`) and share one `cmd_list` branch (`info.py:110`), so `--running --status interrupted` is reachable — and is the shape the affected skills are most likely to be edited into. Rule: the `{running, starting}` allowlist applies **only when `status_filter` is falsy**; an explicit `--status` selects exactly that status irrespective of `--running`/`--all-runs`. The intersection reading (allowlist AND `--status`) is rejected: it makes every `--running --status <non-running>` invocation silently return `[]`.
2. **Empty-path exit codes are frozen at current values.** `info.py:116-124` returns 0 for the `--running` empty path and 1 for the `--status` empty path. The fix dramatically increases how often `--running` reaches that path, and BUG-3231 rewrites the same block — so this is stated as a rule rather than left to whichever change lands first: `--running` → 0, `--all-runs` → 0, `--status <no match>` → 1, in both output modes. Liveness is signalled to `--json` consumers by array length, not exit status.
3. **`awaiting_continuation` is excluded from "genuinely executing."** A spawn-mode handoff may have a live successor process, but the state itself is parked awaiting resume, and `--status`'s own help text already names `awaiting_continuation` as the way to select it. Escape hatch: `/ll:cleanup-loops`'s "abandoned-handoff" classification must source it via `--all-runs` or `--status awaiting_continuation`.

**On the naming remedy:** `list_running_loops`'s *docstring* is accurate ("List all loops with saved state"); the *name* is what misleads. Renaming is rejected as out of proportion — `transport.py:588`, `cmd_list`, and the `test_fsm_persistence.py` suite all bind to it. Instead the docstring is strengthened to state the contract affirmatively (returns every saved state regardless of status; callers wanting live-only must filter; `transport.py` depends on this), and the honest name is delivered at the CLI surface as `--all-runs`.

---

- The fix introduces a new "genuinely executing" status allowlist gating what `--running` (alone, without `--status`) returns. Exact inputs: the `LoopState.status` string field. No existing constant already expresses this set — `RESUMABLE_STATUSES` (`persistence.py:46-51`, `{"running", "awaiting_continuation", "interrupted", "user_stopped"}`) answers resume-eligibility, not liveness, and explicitly includes `interrupted`/`user_stopped`, which this issue's Acceptance Criteria requires `--running` to exclude. `terminal_statuses` (`persistence.py:622`, `{"completed", "failed", "timed_out"}`, local to `_reconcile_stale_runs()`) is a denylist that itself omits `interrupted`/`user_stopped`/`system_signal`/`awaiting_continuation` — none of which are "genuinely executing" either. Per the issue's own Proposed Fix, an allowlist (e.g. `{"running", "starting"}`) is preferred over a denylist so a future status added to the system defaults to excluded, not silently reappearing as "running." Escape hatch / where this must NOT apply: `list_running_loops()` itself must keep returning the unfiltered set unconditionally — `transport.py:588` depends on receiving every status, including terminal ones, to seed newly-connected dashboard clients with recent history. The filter therefore belongs in `cmd_list()`'s `--running` branch, not inside `list_running_loops()`.

## Impact

Any programmatic consumer of `--running --json` that trusts the flag name
over-reports. Found by `little-loops-hermes`, whose portfolio sync fed the
result into a field named `in_flight` and from there into a morning briefing
for the user: the briefing announced four loops in flight for a project with
none. Hermes now filters on `status` itself
(`db/sync.py:_parse_in_flight`) and does not depend on this being fixed.

The narrower consequence is that `--running` is currently unusable as a
liveness check — "is anything running right now" cannot be answered by the
flag named for it, only by `--status running`.

## Proposed Fix

**Decided (2026-08-17): do both halves — filter `--running`, *and* add `--all-runs`
as the supported unfiltered enumeration path.** The two directions originally
sketched here were framed as alternatives; they are not. Filtering `--running`
without providing a replacement enumeration surface deletes the data source
that `/ll:cleanup-loops` exists to consume.

1. **Filter in `cmd_list`.** Restrict the `--running` branch to genuinely
   running dispatches via an allowlist (`{"running", "starting"}`) rather than
   a denylist of terminal statuses, so a status added later defaults to
   *excluded* rather than silently reappearing as running. `--status`
   filtering already exists two lines below and can be reused; `starting`
   entries are synthesized further down in `list_running_loops` for loops with
   a live PID and no state file yet, and must survive the filter.

2. **Add `--all-runs`** (`store_true`, help: *"Show every loop with saved state,
   whatever status it ended in"*) to the `list` subparser, entering the same
   `cmd_list` branch and emitting `list_running_loops()`'s result set
   unfiltered. This is the flag whose behavior `--running` accidentally has
   today, given a name that tells the truth.

   **Naming — corrected during `/ll:ready-issue` (2026-08-17).** `ll-loop
   list` has two distinct modes: with `--running`/`--status` it lists *runs*
   (state files in `.loops/.running/`); bare, it lists *loop definitions*
   (`*.yaml`, filtered by `--builtin`/`--category`/`--label`,
   `info.py:183-208`). The plain spelling `--all`/`-a` is **already taken** on
   this same `list_parser` (`__init__.py:406-411`), with an unrelated meaning
   — "Include internal sub-loops and examples (hidden by default)" for the
   loop-definitions mode. Reusing `--all` for the unfiltered-runs meaning
   would collide with that existing flag on the same subparser, not merely
   read confusingly against it. The flag this fix adds is therefore
   `--all-runs` (one of the two alternatives this section had already named
   as acceptable substitutes), with help text disambiguating explicitly
   ("every loop **run** with saved state, whatever status it ended in").

   Rejected alternative: leave `--all-runs` out and have the three affected skills
   iterate `--status` once per value. That is up to nine subprocess
   invocations against a status vocabulary that is not enumerated anywhere in
   code (`LoopState.status` is a bare `str`, no enum — see Program Design ▸
   Types), and it would silently miss any status added later. `--all-runs` is one
   flag and three one-line skill edits.

Do **not** filter inside `list_running_loops()` — `transport.py:588` depends
on the unfiltered set (see Dependent Files).

### Flag interaction and exit codes

These are behavioral decisions the fix must make explicitly, not fall into:

- **`--status` overrides the allowlist.** `--running` and `--status` are
  independent, non-mutually-exclusive arguments sharing one branch
  (`info.py:110`), so `--running --status interrupted` is reachable and is
  what the affected skills will most naturally be edited into. The allowlist
  applies **only when `--status` is absent**; when `--status` is given it
  selects exactly that status, `--running`/`--all-runs` notwithstanding. An
  allowlist AND `--status interrupted` intersection (always empty) would be
  the wrong answer.
- **Exit code on the empty path is unchanged.** Today bare `--running` with no
  results prints `No running loops` and returns 0, while `--status` with no
  match returns 1 (`info.py:116-124`). The fix makes many more projects reach
  that empty path via `--running`, and BUG-3231 rewrites the same block —
  pin the current semantics (`--running`/`--all-runs` empty → 0; `--status` empty →
  1) so neither fix flips it by accident. `--json` consumers distinguish
  liveness by array length, not exit status.
- **`awaiting_continuation` is excluded** from the `--running` allowlist. A
  spawn-mode handoff may have a live successor process, but the state itself
  is not executing, and the `--status` help text already advertises
  `awaiting_continuation` as the way to select it. `/ll:cleanup-loops`'s
  "abandoned-handoff" classification must therefore source it via `--all-runs` or
  `--status awaiting_continuation`, not `--running`.

### On `list_running_loops`'s name vs. docstring

The docstring (*"List all loops with saved state"*) is **accurate**; the
function *name* is what misleads. Renaming is not cheap — `transport.py:588`,
`cmd_list`, and the `test_fsm_persistence.py` suite all bind to it — so keep
the name and strengthen the docstring to state the contract affirmatively:
returns every saved state regardless of status, callers wanting live-only must
filter, and `transport.py` depends on the unfiltered behavior.

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add `--all-runs` to the `list` subparser (`scripts/little_loops/cli/loop/__init__.py:365-369`, alongside `--running`/`--status`) and handle it in `cmd_list`'s branch condition (`info.py:110`) so it enters the same path and skips the allowlist. Also update the usage epilog example block at `__init__.py:119`.
- Update `scripts/tests/test_ll_loop_integration.py::test_list_running_reconciles_dead_pid_entries` (BUG-1731 regression, line 327) — its current assertions require the dead-PID-reconciled `interrupted` entry to appear under bare `--running`, which directly contradicts the planned allowlist filter. Update it to assert the entry is excluded from `--running` output while confirming reconciliation itself still happens (e.g. via `--all-runs`, `--status interrupted`, or directly against the rewritten state file). **Note this is not a weakening of the regression:** the test's own docstring (line 333) already claims it "flips stale running entries to interrupted **and excludes them from output**" — the assertions have always contradicted the docstring. The fix brings the test in line with its stated intent, and the on-disk `written["status"] == "interrupted"` + `reconciled_at` assertions (the actual BUG-1731 guarantee) must be preserved verbatim.
- Update `skills/cleanup-loops/SKILL.md` (Step 1, line 34) — switch `ll-loop list --running --json` to `ll-loop list --all-runs --json` and rewrite the accompanying prose, which currently documents the pre-fix bug as the mechanism ("returns all loops that have a `.state.json` file... regardless of whether they are actually running"). That sentence becomes true of `--all-runs` and false of `--running`.
- Update `skills/debug-loop-run/SKILL.md:53-64` and `skills/audit-loop-run/SKILL.md:54-57` — same switch to `--all-runs`. Their existing client-side filters for `running`/`interrupted`/`failed`/`timed_out`/`awaiting_continuation` candidates then keep working unchanged; with `--running` they would go permanently dead.
- Update `docs/reference/json-output-contracts.md:119-124` — the "Alternate entry point" section documents `--running --json` as returning "the same base state objects" unfiltered. Describe the `{running, starting}` allowlist, document `--all-runs` as the unfiltered entry point, and note that `--status` selects arbitrary statuses independently.
- Update `docs/reference/CLI.md:1216` — the flags table describes `--status` as meaningful only "with `--running`", which implies bare `--running` is unfiltered. Reword and add the `--all-runs` row.
- **(Added 2026-08-17 review)** Update `docs/reference/COMMANDS.md:950` — the `/ll:cleanup-loops` entry repeats the same stale claim as the skill it documents: "Runs `ll-loop list --running --json` to enumerate all loops with state files". Must track the skill's switch to `--all-runs`.
- **(Added 2026-08-17 review)** Update `docs/guides/LOOPS_GUIDE.md:1321` — scope-conflict troubleshooting tells the reader to find the conflicting lock holder with `ll-loop list --running`. The blocking holder is frequently a stale-`interrupted` entry whose lock PID is still alive (exactly the case `/ll:cleanup-loops` step 5 handles), which disappears from `--running` post-fix. Redirect to `--all-runs`.
- **(Added 2026-08-17 review)** `docs/generalized-fsm-loop.md:1619` — bare `ll-loop list --running` in an example; verify the surrounding prose does not promise unfiltered output before leaving it as-is.
- **(Added 2026-08-17 review)** No change needed at `scripts/tests/test_json_output_contracts.py:245-266` (`test_json_output_via_cmd_list_running`) — verified: it mocks `list_running_loops` with a single state from `_make_loop_state()`, whose default `status` is `"running"` (line 181), so the entry survives the allowlist and the contract assertions hold. Recorded here so implementation does not re-derive it.
- **(Added 2026-08-17 review)** Do **not** delete `_STATUS_COLORS`' non-running entries or the `interrupted`/`user_stopped` → `"paused"` `display_status` remapping (`info.py:132-163`). They become unreachable on the `--running` path but are still required by `--all-runs` and `--status`.

## Acceptance Criteria

- [ ] `ll-loop list --running --json` on a project whose `.loops/.running/`
      holds only `completed` / `interrupted` / `user_stopped` state files
      returns `[]`.
- [ ] On any given directory, `--running` returns a **superset** of
      `--status running`, differing only by synthesized `starting` entries.
      (Supersedes the original "they agree" wording, which contradicted the
      `starting` criterion below: `--status running` matches
      `s.status == "running"` exactly and can never return a `starting`
      entry.)
- [ ] A loop with a live PID and no state file yet (`status="starting"`) is
      still reported by `--running`.
- [ ] `ll-loop list --all-runs --json` returns every state in `.loops/.running/`
      regardless of status — the pre-fix `--running` behavior, under an
      honest name.
- [ ] `--status` overrides the allowlist: `ll-loop list --running --status
      interrupted` returns the `interrupted` entries, not `[]`.
- [ ] Exit codes on the empty path are unchanged: `--running` and `--all-runs`
      return 0, `--status <no match>` returns 1, in both `--json` and
      human-readable modes.
- [ ] `awaiting_continuation` entries do **not** appear under `--running`, and
      do appear under `--all-runs` and `--status awaiting_continuation`.
- [ ] State files are not deleted or archived as a side effect of `list` —
      `interrupted` runs remain resumable, and dead-PID reconciliation
      (`running` → `interrupted`, written to disk) still happens on the
      `--running` read path even though the reconciled entry is then filtered
      out of the output.
- [ ] `list_running_loops`'s docstring states affirmatively that it returns
      all saved states regardless of status and that callers wanting live-only
      must filter; the `--running` help text says "Only show loops currently
      executing"; the `--all-runs` help text describes the unfiltered set.
- [ ] `/ll:cleanup-loops`, `/ll:debug-loop-run`, and `/ll:audit-loop-run` still
      discover terminal- and paused-status loops after the fix (via `--all-runs`).


## Status

**Open** | Created: 2026-08-17 | Priority: P2

## Session Log
- `/ll:manage-issue` - 2026-08-17T15:34:02 - `82413b78-5f49-49d2-809f-b74ee621f3c7.jsonl`
- `/ll:ready-issue` - 2026-08-17T15:22:00 - `be92c547-fe8a-4348-a51a-3b680c72f920.jsonl`
- `/ll:confidence-check` - 2026-08-17T05:59:39 - `2842c23a-3637-4e5a-8f3a-147fcbcc8790.jsonl`
- `/ll:verify-issues` - 2026-08-17T05:56:54 - `1741dcb3-c773-4b6b-b0db-7b1b7643db32.jsonl`
- `/ll:wire-issue` - 2026-08-17T05:54:24 - `4a3da90a-08c0-47c7-883c-30dda4587b68.jsonl`
- `/ll:refine-issue` - 2026-08-17T05:46:45 - `91036e81-5f4e-4cae-b94f-27ddba124891.jsonl`
