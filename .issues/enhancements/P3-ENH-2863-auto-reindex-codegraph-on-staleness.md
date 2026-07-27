---
id: ENH-2863
title: auto-sync codegraph index on staleness via codegraph CLI sync
type: ENH
priority: P3
status: done
labels:
- code-intelligence
- codegraph
- captured
captured_at: '2026-07-27T16:53:49Z'
completed_at: '2026-07-27T18:49:09Z'
discovered_date: '2026-07-27'
discovered_by: capture-issue
parent: EPIC-2575
relates_to:
- ENH-2577
- ENH-2578
learning_tests_required:
- codegraph
confidence_score: 96
outcome_confidence: 75
score_complexity: 18
score_test_coverage: 21
score_ambiguity: 16
score_change_surface: 20
deferred_by: automation
deferred_date: '2026-07-27T17:47:26Z'
deferred_reason: gate_blocked
---

# ENH-2863: auto-sync codegraph index on staleness via codegraph CLI sync

## Summary

`CodegraphProvider` (`scripts/little_loops/codequery/codegraph.py`) reads
`.codegraph/codegraph.db` strictly read-only and already detects staleness
(`status()`, lines 156-237: `head_moved` git-log-since count + scoped
`dirty_files` count, gated by `config.staleness` policy `strict|warn|off`,
default `warn`). The index itself is built and refreshed by an **external**
tool, `@colbymchenry/codegraph` (npm, installed globally — confirmed present
on this machine at `~/.npm-global/bin/codegraph`), not by anything in this
repo. That CLI already ships the exact incremental primitive needed:
`codegraph sync [path]` diffs the working tree against the last index and
updates only changed files — confirmed cheap in practice (0.18s on a
906-file / 28.5k-node / 65k-edge project with no pending changes; a few
seconds when there are real changes to parse). Nothing in little-loops calls
`sync` automatically, so `.codegraph.db` only advances when a human happens
to run it by hand.

## Current Behavior

Under the default `warn` policy, a stale index still reports
`available: true`, so `/ll:wire-issue` Phase 3.6 (per
`skills/wire-issue/graph-discovery-layer.md`) keeps using it — treating
results as unconfirmed leads and widening confirmation, per the "never trust
negatives" rule. This is graceful degradation, not a failure, but graph
answers quietly get less useful the longer a project goes without a manual
sync. Observed in the wild: `/ll:wire-issue ENH-2852 --auto` ran against an
index 193 commits stale (`indexed_at: 2026-07-22`); running
`codegraph sync --quiet` closed the gap in well under a second and flipped
`ll-code status` back to `freshness: fresh` immediately.

ENH-2577 (which built `CodegraphProvider` + staleness detection) explicitly
scoped "auto-reindex hooks" **out** as a future follow-up once ENH-2578
landed; no issue tracked that follow-up until now.

## Expected Behavior

Wire an auto-trigger that runs `codegraph sync --quiet [path]` whenever the
index is stale, instead of leaving it to accumulate indefinitely:

- **Where to trigger from** — candidates, not mutually exclusive:
  - A `SessionStart` hook (mirrors `session-end.sh`'s existing
    staleness-triggered sweep pattern from FEAT-1680).
  - Inline in `CodegraphProvider`/`ll-code` itself: on a `stale` status read,
    shell out to `codegraph sync --quiet` before answering the query (sync
    cost is low enough — sub-second when clean — that this can likely run
    synchronously rather than needing a background job).
  - A check folded into `ll-doctor --full`.
- **Detect the CLI is absent gracefully.** `codegraph` is an external,
  separately-installed dependency (not vendored, not a `pyproject.toml`
  entry) — if the binary isn't on `PATH`, skip the sync attempt silently and
  fall through to today's `stale`-but-`available` behavior. Do not hard-fail
  a calling skill because the optional sync couldn't run.
- **No configurable threshold needed.** Given sync cost is negligible when
  the tree is clean (confirmed: 0.18s no-op) and proportional to actual
  changed-file count otherwise, simplest correct behavior is "sync whenever
  status reports non-fresh," not a commit-count threshold requiring tuning.

## Motivation

Every project running little-loops with the codegraph provider enabled hits
this same silent decay — the index drifts further from HEAD with every
commit, with no signal beyond a `stale` field buried in `ll-code status`
output, even though closing that gap costs almost nothing. Graph-accelerated
discovery (ENH-2578) was built on the assumption that a usably-fresh index
exists; an auto-sync trigger is a small, cheap wire-up that keeps that
assumption true for the life of a project instead of degrading over time.

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/codequery/codegraph.py` — add `_sync_if_stale()` (or
  similarly named) helper and wire it into `CodegraphProvider.status()`
  (lines 156-238), specifically right after `is_fresh`/`raw_freshness` is
  computed (line ~206) and before the policy branch (lines 209-238) decides
  `available`/`freshness`.
- `scripts/little_loops/config/features.py` — add `auto_sync: bool = True` to
  `CodeQueryCodegraphConfig` (currently only `db_path`, line ~818), plus its
  `from_dict()` (line ~824).
- `scripts/little_loops/config-schema.json` — add `auto_sync` boolean
  property (default `true`) to the `code_query.codegraph` object (lines
  1274-1302).

### Call Sites (Dependents)
- `scripts/little_loops/cli/code.py:main_code()` (line 109) — calls
  `provider.status()` unconditionally on every `ll-code` invocation, before
  subcommand dispatch. This is the natural point where a sync-triggered
  status computation would already propagate to callers without further
  wiring.
- `skills/wire-issue/graph-discovery-layer.md` (Phase 3.6, ~lines 42-70) —
  consumes the `freshness` field echoed in every `ll-code` JSON response;
  no changes needed here, it will simply see `fresh` more often.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/codequery/core.py:103-125` — `resolve_provider()` calls
  `provider.status().available` for **every** registered provider in
  `_PROVIDER_MAP` order when `name == "auto"`, and `"codegraph"` is checked
  before `"fallback"`. This means every `auto`-provider resolution (the
  default `ll-code` path) will synchronously shell out to
  `codegraph sync --quiet <repo_root>` whenever the index is stale, before
  falling through to the fallback provider — the one call site where the new
  subprocess latency/timeout is inherited transitively by all `resolve_provider`
  callers. The `resolve_provider()` docstring (lines 106-109) should be
  updated to note this new side effect, and the `CodeQueryProvider` Protocol
  (`core.py:69-90`) has no documented side-effect contract for `status()`
  today.

### Similar Patterns to Follow
- `_git()` helper in `codegraph.py` (lines 54-68) — the existing
  `subprocess.run(..., timeout=_GIT_TIMEOUT)` wrapped in
  `try/except (OSError, subprocess.TimeoutExpired): return None` is the
  in-file precedent for a non-raising shell-out; model `_sync_if_stale()`'s
  `codegraph sync` invocation after this shape.
- `shutil.which()` binary-presence probe — `HostRunner.detect()` methods in
  `scripts/little_loops/host_runner.py` (e.g. line 276) and the resolver
  loop at lines 1321-1327 are the canonical "probe then no-op if absent"
  pattern for an optional external CLI.
- `doctor.py:_probe_version()` (lines 776-796) — the canonical
  "detect() → build invocation → subprocess.run(timeout=...) → except
  tuple → safe default" shape for calling an optional external binary and
  swallowing all failure modes.
- `hooks/session_start.py:handle()` (lines 194-215) — the detached
  `subprocess.Popen(..., start_new_session=True, stdin=DEVNULL, ...)`
  pattern used to fire an out-of-band task without blocking the hook's 5s
  timeout budget; relevant if the SessionStart-hook trigger option is
  chosen instead of (or in addition to) the inline `status()` sync.
- `cli/doctor.py` check-registry pattern (`CheckResult`, `register_check`/
  `register_full_check`, e.g. `_decisions_store_data()`/
  `_decisions_store_check()` at lines 254-324) — template for an optional
  `--full`-gated codegraph doctor check; absent-but-optional subsystems use
  `severity="informational"`, not `"error"`.

### Tests
- `scripts/tests/test_codequery_codegraph.py` — existing coverage for
  `CodegraphProvider.status()`/staleness; add binary-absent no-op,
  sync-success, and sync-failure/timeout cases here.
- `scripts/tests/test_cli_doctor.py` (lines 562-621) — has the exact
  `subprocess.TimeoutExpired`/binary-absent mocking pattern
  (`test_skips_probe_when_binary_not_detected`,
  `test_probe_timeout_falls_back_to_unknown`) to model new tests after.
- `scripts/tests/test_host_runner.py` (lines 79-97) — `monkeypatch.setattr`
  on `shutil.which` pattern for the binary-presence branch.
- `scripts/tests/test_config_schema.py` — validate the new `auto_sync`
  schema property.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config.py` — `TestCodeQueryConfig` (lines ~2292-2370,
  e.g. `test_codegraph_from_dict_with_defaults`) is the direct sibling test
  class for `CodeQueryCodegraphConfig`; add default/explicit-override/
  partial-omitted round-trip cases for `auto_sync`, mirroring the existing
  `db_path` assertions (including the `to_dict()` check at lines 2356-2359).
- `scripts/tests/test_config_schema.py::test_code_query_in_schema`
  (lines 429-458) — the `code_query.codegraph` schema object has
  `additionalProperties: False` (line 456); **adding `auto_sync` to
  `CodeQueryCodegraphConfig` without also adding it to the schema will make
  any config that sets it explicitly fail schema validation.** Add a
  property assertion (`type: boolean`, `default: true`) alongside the
  existing `db_path` checks.
- `scripts/tests/test_codequery_codegraph.py::TestStalenessMatrix`
  (lines 266-357, e.g. `test_commits_ahead_marks_stale_per_policy`,
  `test_dirty_tree_marks_stale_per_policy`) — these call
  `CodegraphProvider().status()` directly on a stale fixture with no
  `shutil.which`/`subprocess.run` mocking. Once `_sync_if_stale()` is wired
  into `status()`, these will attempt a real shell-out to `codegraph` unless
  `auto_sync` defaults to a value that keeps them inert, or they're updated
  to mock the binary-absent/sync path.
- `scripts/tests/test_cli_code.py` —
  `test_provider_codegraph_status_reports_unavailable_without_index` (line 81)
  exercises the no-index early-return branch (`codegraph.py:162-168`), which
  must stay unaffected since sync only makes sense once an index exists to
  compare against; `test_status_json_output_is_valid_json` (line 31) is
  pinned to `--provider fallback` specifically to avoid touching this repo's
  own real `.codegraph/codegraph.db` — worth a guard/mock if a
  `--provider codegraph` variant is ever added, since that db is live and
  currently reports `freshness: stale` (confirmed via `ll-code -j status`
  during this wiring pass).

### Documentation
- `docs/reference/API.md` — codegraph section needs the new `auto_sync`
  config key and sync-trigger behavior documented.
- `skills/wire-issue/graph-discovery-layer.md` — note that `stale` should
  now be transient/rare rather than a steady-state condition.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — the `status` freshness fields section (documents
  `detail`'s `indexed_at`/staleness-policy reporting and
  `ll-code --provider codegraph status` examples) needs a new bullet
  describing when `auto_sync` fires and what `detail` looks like post-sync.
- `docs/reference/CONFIGURATION.md` — the `code_query` config section (table
  rows for `provider`, `codegraph.db_path`, `staleness`) needs a new row for
  `code_query.codegraph.auto_sync` (default `true`).

## Proposed Solution

Add a `_sync_if_stale()` (or similarly named) helper near
`CodegraphProvider.status()` that, when `is_fresh` is `False`:
1. Locates the `codegraph` binary (e.g. `shutil.which("codegraph")`); no-op
   if absent.
2. Runs `codegraph sync --quiet <repo_root>` with a short timeout.
3. On success, staleness naturally clears on the next `status()` call (no
   need to hand-patch `indexed_at` — re-derive from the tool's own output).
4. On failure/timeout, log at debug level and fall through to existing
   `stale`-but-`available` behavior — never raise.

Call this helper from wherever `status()` first observes `stale` under the
default policy (or gate behind a new `config.codegraph.auto_sync: bool`,
default `true`, if a kill switch is wanted for environments that manage
`codegraph sync` via their own external cron/git-hook).

## Implementation Steps

1. Add the `sync`-shelling helper to `CodegraphProvider` (or a thin wrapper
   module), gated on binary presence via `shutil.which`.
2. Trigger it from `status()` (or from `ll-code` CLI dispatch, whichever
   keeps query paths simplest) when staleness is detected, before returning
   the freshness verdict.
3. Add a `config.codegraph.auto_sync` toggle (default `true`) for opt-out.
4. Tests: binary-absent no-op path, sync-success path (freshness flips to
   `fresh` on next status call), sync-failure/timeout path (falls through
   without raising).
5. Update `docs/reference/API.md` codegraph section and
   `skills/wire-issue/graph-discovery-layer.md` if auto-sync changes how
   often "stale" is realistically encountered in practice.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation:_

6. Add the `auto_sync` property to `config-schema.json`'s `codegraph` object
   in the same commit as the `CodeQueryCodegraphConfig` field —
   `additionalProperties: False` on that schema object means the two land
   together or config validation breaks for anyone who sets it explicitly.
7. Update `resolve_provider()`'s docstring
   (`scripts/little_loops/codequery/core.py:106-109`) to note that `"auto"`
   resolution now has a synchronous shell-out side effect via
   `CodegraphProvider.status()`.
8. Update or mock `scripts/tests/test_codequery_codegraph.py::TestStalenessMatrix`
   (lines 266-357) so its existing stale-fixture tests don't attempt a real
   `codegraph` shell-out once `_sync_if_stale()` is wired in.
9. Add `auto_sync` round-trip cases to `scripts/tests/test_config.py`
   (`TestCodeQueryConfig`) and schema-property assertions to
   `scripts/tests/test_config_schema.py::test_code_query_in_schema`.
10. Add `code_query.codegraph.auto_sync` to `docs/reference/CONFIGURATION.md`
    and the sync-on-stale behavior to `docs/reference/CLI.md`'s `status`
    freshness section.

## Impact

- **Priority**: P3 — graceful degradation already exists (`warn` policy),
  so this is an effectiveness improvement, not a broken-state fix.
- **Effort**: Small — the expensive unknown (would we need to write our own
  indexer?) is resolved: the incremental sync primitive already exists
  externally. This is a shell-out wire-up plus a graceful-absence guard.
- **Risk**: Low — sync is confirmed cheap and non-destructive (updates the
  same db in place); the binary-absent and sync-failure paths must both be
  strictly non-blocking so this never turns an optional acceleration into a
  new failure mode for skills that call `ll-code`.

## Scope Boundaries

Out of scope for this issue:
- Building or vendoring a codegraph indexer — the external `@colbymchenry/codegraph`
  CLI already provides the incremental `sync` primitive; this issue only wires
  a call to it.
- Changing the `staleness` policy semantics (`strict|warn|off`) or the
  `is_fresh`/`head_moved`/`dirty_files` detection logic in
  `CodegraphProvider.status()` — auto-sync runs *in response to* an existing
  stale verdict, it does not alter how staleness is computed.
- A configurable staleness threshold (e.g. "sync only after N stale commits")
  — per Expected Behavior, sync cost is negligible so "sync whenever
  non-fresh" is the whole policy; no tuning knob beyond the `auto_sync`
  on/off toggle.
- Installing or managing the `codegraph` binary itself (e.g. via a package
  manager wrapper) — it remains an optional, separately-installed external
  dependency; this issue only detects presence/absence via `shutil.which`.
- Background/async scheduling of the sync (e.g. a daemon or cron-like
  mechanism) — the sync is confirmed cheap enough to run synchronously inline
  in `status()`; a background job is not part of this issue's scope.

## Resolution

Implemented per the Proposed Solution / Implementation Steps:

- Added `_sync_if_stale()` to `codegraph.py`, wired into `status()` right after
  `is_fresh`/`raw_freshness` is computed, before the policy branch. Gated on
  `shutil.which("codegraph")` (no-op if absent) and `config.codegraph.auto_sync`
  (no-op if disabled); the `codegraph sync --quiet <repo_root>` subprocess call
  never raises (`OSError`/`TimeoutExpired` swallowed), mirroring the existing
  `_git()` non-raising shape.
- Added `auto_sync: bool = True` to `CodeQueryCodegraphConfig` (`from_dict` +
  `BRConfig.to_dict()` round-trip) and the matching `config-schema.json` property.
- Updated `resolve_provider()`'s docstring (`core.py`) to document the new
  `"auto"`-resolution side effect.
- Updated `docs/reference/CONFIGURATION.md`, `docs/reference/CLI.md`, and
  `skills/wire-issue/graph-discovery-layer.md` per the Integration Map.
- Tests: `TestAutoSync` in `test_codequery_codegraph.py` (binary-absent,
  `auto_sync: false`, sync-invoked, sync-timeout paths); pinned
  `TestStalenessMatrix` inert via an autouse `shutil.which` mock so its
  stale-fixture tests don't shell out on machines with `codegraph` on `PATH`;
  `auto_sync` round-trip cases in `test_config.py`/`test_config_schema.py`.

Manually verified against this repo's live `.codegraph/codegraph.db` (`ll-code
--json status`) — the sync shells out without error; `dirty_files` staying
nonzero afterward reflects genuinely uncommitted working-tree changes, not a
sync failure (staleness from uncommitted files is orthogonal to what `sync`
catches up).

## Session Log
- `/ll:ready-issue` - 2026-07-27T17:47:06 - `fac775ae-243f-48a2-bf9a-3431a1f5bd9b.jsonl`
- `/ll:confidence-check` - 2026-07-27T18:15:00 - `9188e54f-5830-4cf3-b9ff-2c70903a6916.jsonl`
- `/ll:wire-issue` - 2026-07-27T17:42:15 - `2ba79734-f873-4dfe-86fb-a252292fbd8f.jsonl`
- `/ll:refine-issue` - 2026-07-27T17:36:13 - `fa4557f5-bd3a-4712-82e8-8be145778d32.jsonl`
- `/ll:capture-issue` - 2026-07-27T16:53:49Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/92005058-34f6-4492-9015-3c5341fed493.jsonl`
- `/ll:manage-issue` - 2026-07-27T18:48:27Z - `532faada-5373-48c8-b996-4421a247de12.jsonl`

---
## Status
- [x] Done
