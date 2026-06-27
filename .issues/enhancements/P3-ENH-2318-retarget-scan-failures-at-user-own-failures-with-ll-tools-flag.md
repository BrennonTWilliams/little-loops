---
id: ENH-2318
title: 'Retarget ll-logs scan-failures at the user''s own failures; keep current behavior behind a flag'
type: ENH
priority: P3
status: open
captured_at: '2026-06-26T22:05:51Z'
discovered_date: '2026-06-26'
discovered_by: capture-issue
decision_needed: false
relates_to:
- EPIC-1918
- ENH-1922
- ENH-2093
- ENH-2070
- FEAT-1925
- FEAT-2315
- FEAT-2316
- ENH-2317
labels:
- captured
- ll-logs
- target-project
- scan-failures
depends_on:
- ENH-2317
---

# ENH-2318: Retarget `ll-logs scan-failures` at the user's own failures (keep current behavior behind a flag)

## Summary

Give `ll-logs scan-failures` two modes. The new **project mode** mines the
target-project user's *own* recurring failures — failing tests, erroring
commands, repeated corrections — and `--capture`s them into **their** backlog.
The **current behavior** (mining failed `ll-*` tool calls to file bugs against
the little-loops plugin) is preserved behind an explicit flag so it stays usable
for little-loops plugin development.

## Current Behavior

`_cmd_scan_failures()` in `scripts/little_loops/cli/logs.py` mines failed `ll-*`
CLI calls from session logs and proposes/creates BUG issues describing **plugin**
defects (`--capture`, `--capture-foreign`). This is valuable for little-loops
maintainers but meaningless in a target project, where the user cares about
*their* failing tests/commands, not ll-tool bugs.

## Expected Behavior

- **Project mode** (new): cluster the user's own recurring failures — repeated
  non-zero test runs, erroring shell commands, repeated corrections on the same
  topic — and with `--capture` write issues into the user's backlog.
- **ll-tools mode** (current behavior, preserved): a flag (proposed
  `--ll-tools`, or `--scope ll-tools`) reproduces today's exact behavior — mine
  failed `ll-*` calls and file plugin bugs. This is the mode little-loops
  maintainers keep using.
- Mode selection is explicit and discoverable; `--capture` semantics are
  identical within each mode.

## Motivation

`scan-failures` today only helps the people building the plugin. The same failure
-mining machinery, pointed at the user's signal, becomes a real intake path for a
target project (it pairs with the "recurring corrections" the SessionStart hook
already surfaces). The user explicitly wants the current behavior retained for
ll plugin development — so this is additive, not a replacement.

## Proposed Solution

- Add a mode selector. Recommended: `--ll-tools` boolean (or `--scope
  {project,ll-tools}`) that selects the existing code path unchanged.
- **Default-selection (decision point):** default to **project mode** in a
  target project, but **auto-detect the little-loops source repo** (e.g.
  `.claude-plugin/plugin.json` name == `little-loops`, or catalog root == this
  repo) and default to `--ll-tools` there. This keeps existing maintainer
  workflows working without edits — notably the **FEAT-1925** telemetry-digest
  loop and any **ENH-2070** automated bug-intake — which invoke `scan-failures`
  expecting current behavior. Confirm this default with the maintainer before
  implementing.
- Carry forward all noise/project-scoping hardening from **ENH-2093** into
  project mode (don't scan foreign projects, filter sandbox/OOM/cancel/non-bug
  failures).
- Project mode benefits from the whole-session corpus ([FEAT-2316]) and the
  CWD/host scoping defaults ([ENH-2317]).

### Codebase Research Findings — Open Decisions

_Added by `/ll:refine-issue` — the default-selection policy is genuinely undecided and
needs a maintainer pick (`decision_needed: true`):_

**Decision: default-selection policy.** Because no ll-source-repo detector exists yet
(see Integration Map § Codebase Research Findings), *how* and *whether* to auto-default
has distinct implementation / back-compat tradeoffs:

- **Option A — auto-detect (issue's proposal):** build `is_ll_source_repo(root)`; default
  `--scope ll-tools` in the ll repo, `project` elsewhere. Zero edits to the FEAT-1925 loop
  or ENH-2070 intake. Cost: a new detector + an implicit default that differs by location.

  > **Selected:** Option A — auto-detect — uniquely satisfies the "no edits to maintainer
  > workflows" requirement and matches recorded decision ARCHITECTURE-061. Build the detector
  > on the existing `_load_cli_allowlist()` / `scripts/pyproject.toml` `ll-*` probe
  > (`logs.py:887`), **not** the issue's `plugin.json` `name == "little-loops"` check — the
  > actual `name` field is `"ll"`, so that check would never fire.
- **Option B — explicit `--scope` required (no default):** mirrors today's required
  `--project`/`--all` mutex group; no detector needed. Cost: must edit
  `.loops/ll-logs-telemetry-digest.yaml` (and any ENH-2070 intake) to pass
  `--scope ll-tools`. Most predictable, least magic.
- **Option C — default `project` everywhere; ll-tools only via explicit flag:** simplest
  default, but **breaks** the FEAT-1925 loop unless edited — contradicts the "retain
  current behavior for ll dev without edits" requirement.

Recommendation: **Option A** uniquely satisfies the stated "no edits to maintainer
workflows" constraint; resolve via `/ll:decide-issue` before wiring.

**Flag-naming (resolved by precedent, not a decision):** favor `--scope {project,ll-tools}`
(named enum) over a `--ll-tools` boolean — consistent with the existing
`--sort choices=[...]` selector on the `stats` subparser (`logs.py:1787`).

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-26.

**Selected**: Option A — auto-detect (`is_ll_source_repo`)

**Reasoning**: Option A is the only option that satisfies the issue's hard requirement —
"retain current behavior for ll dev *without edits*" — because the auto-detect default keeps
the FEAT-1925 telemetry-digest loop (`.loops/ll-logs-telemetry-digest.yaml:41`, which invokes
`scan-failures --json` with no scope flag) working untouched, and it matches the already-recorded
architecture decision **ARCHITECTURE-061**. **Correction to the issue's spec:** build the detector
on the existing `_load_cli_allowlist()` / `scripts/pyproject.toml` `ll-*` probe (`logs.py:887`),
**not** the proposed `.claude-plugin/plugin.json` `name == "little-loops"` check — the actual
`name` field is `"ll"`, so that check would never fire.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A — auto-detect | 2/3 | 1/3 | 2/3 | 2/3 | 7/12 |
| B — explicit `--scope` | 3/3 | 3/3 | 3/3 | 1/3 | 10/12 |
| C — default `project` everywhere | 1/3 | 3/3 | 2/3 | 0/3 | 6/12 |

**Key evidence**:
- Option A: detector basis already exists as `_load_cli_allowlist()` (`logs.py:887`, probes
  `scripts/pyproject.toml` for `ll-*` entries); `--sort choices=[...]` (`logs.py:1786`) is the
  in-module precedent for the `--scope` enum. Its lower raw score reflects the implicit
  location-varying default and a net-new detector, but it uniquely meets the no-edits constraint.
- Option B: highest code-fit — reuses the `required=True` mutex group on all 5 sibling
  subcommands (`logs.py:1699,1721,1767,1798,1833`) and the `pytest.raises(SystemExit)` mutex
  test — but forces a one-line edit to the live FEAT-1925 loop YAML and diverges from
  ARCHITECTURE-061. Rejected despite the higher score.
- Option C: silently inverts the FEAT-1925 loop's behavior (project-mode mining instead of
  ll-tool mining) with no crash; self-labeled as breaking in the issue. Rejected.

**Note**: Option B scored higher on pure codebase fit (10/12 vs 7/12). Option A was selected by
maintainer decision because the stated "no maintainer-workflow edits" requirement and the recorded
ARCHITECTURE-061 decision outweigh raw code-fit.

## Implementation Steps

1. Add the mode flag + default-selection (with ll-repo auto-detect) to the
   `scan-failures` subparser and `_cmd_scan_failures()`.
2. Factor today's ll-tool failure mining behind the `--ll-tools` path
   unchanged (back-compat: identical output for existing callers).
3. Implement project-mode failure clustering (tests/commands/corrections) with
   ENH-2093 noise filters.
4. Tests: ll-tools mode output unchanged; project mode clusters user failures;
   ll-repo auto-detect picks ll-tools by default; target repo picks project.
5. Docs: CLI reference, `/ll:help`, CLAUDE.md; note the FEAT-1925 loop continues
   to work.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. **Resolve argparse blocker for `.loops/ll-logs-telemetry-digest.yaml`** — the loop calls `ll-logs scan-failures --json` with no `--project`/`--all`; this currently fails at argparse (required mutex group). ENH-2318 must either (a) make `--project`/`--all` optional when auto-detect provides a root, (b) default to `--all` implicitly, or (c) add `--all` to the loop YAML. Decide before implementing the `--scope` flag so the back-compat protection actually works.
7. Fix `test_scan_failures_capture_scoped_to_current_project` (test_ll_logs.py:2622) — add `"--scope", "ll-tools"` to its `sys.argv` patch to prevent breakage from auto-detect.
8. Update `logs.py:1796` subparser `help=` string and `logs.py:1820` `--capture` `help=` string to reflect two modes.
9. Update `scripts/tests/test_cli.py` — add `test_scan_failures_ll_tools_scope_returns_0` and `test_scan_failures_project_scope_returns_0` variants.
10. Update `docs/reference/API.md:3714` — revise `scan-failures` description; update JSON schema documentation for both modes.
11. Update `docs/reference/CLI.md:1983, 2042–2051, 2091–2094` — add `--scope` flag, two-mode description, and project-mode examples.
12. Update `docs/guides/HISTORY_SESSION_GUIDE.md:302-309` — add project-mode example and auto-detect explanation.
13. Update `scripts/little_loops/cli/__init__.py:15` — revise module docstring.
14. Update `commands/help.md:293` — revise `ll-logs` entry description.
15. Update `scripts/little_loops/init/writers.py:90` — revise `_CLAUDE_MD_COMMANDS_BLOCK` scan-failures characterization.
16. Minor update `docs/ARCHITECTURE.md:228` if module description phrasing needs refresh.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` — `_cmd_scan_failures()` and the
  `scan-failures` subparser (add mode flag + ll-repo auto-detect + project-mode
  failure clustering).

### Dependent Files (Callers/Importers)
- **FEAT-1925** telemetry-digest loop and **ENH-2070** bug-intake automation
  invoke `scan-failures` expecting today's behavior — protected by the ll-repo
  auto-detect default rather than code edits.

_Wiring pass added by `/ll:wire-issue`:_
- `.loops/ll-logs-telemetry-digest.yaml` (lines 40–41, `scan_failures` FSM state) — invokes `ll-logs scan-failures --json` with **no** `--project`/`--all`/`--scope` flags. The current code has `required=True` on the `--project`/`--all` mutex group, so this invocation **currently fails at argparse** (silently, because output goes to `$OUT 2>&1`). ENH-2318 must decide: either (a) make `--project`/`--all` optional when auto-detect can provide a root, (b) default to `--all` when neither is specified, or (c) update the loop YAML to pass `--all`. This is a **blocker** — the "back-compat caller" protection only works if the call doesn't fail at argparse first.
- `.loops/ll-logs-telemetry-digest.yaml` (line 69, `triage_failures` FSM state) — prompt text says "ll-logs scan-failures found failed ll-* tool invocations in interactive sessions"; advisory phrasing issue only, no functional impact since auto-detect runs this in ll-tools scope inside the ll repo.
- `scripts/tests/test_cli.py` (`test_scan_failures_returns_0`, line 2965) — smoke test that invokes `ll-logs scan-failures --all`; will continue to pass with auto-detect selecting project mode (empty corpus → exit 0), but should be extended with a scope-explicit variant.
- `scripts/little_loops/session_store.py` — provides `is_correction()` and `mine_corrections_from_messages()`; imported by `logs.py` at line 24. Project mode adds `_query_recurring_corrections()` / `find_user_corrections()` from `scripts/little_loops/history_reader.py` as a new data source for this command (currently `_cmd_scan_failures` reads only raw JSONL, never touches history.db).
- `scripts/little_loops/issue_lifecycle.py` — exports `classify_failure()` (line 57); already imported by logs.py:956. Reuse unchanged for project-mode noise filtering.

### Similar Patterns
- **ENH-2093** noise/project-scoping filters — reuse the same hardening
  (skip foreign projects; drop sandbox/OOM/cancel/non-bug failures) in project
  mode for consistency.

### Tests
- `scripts/tests/test_ll_logs.py` — assert ll-tools mode output is byte-for-byte
  unchanged; project mode clusters user failures (tests/commands/corrections);
  auto-detect picks ll-tools in this repo and project mode in a target repo.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli.py` (`test_scan_failures_returns_0`, line 2965) — existing smoke test for `scan-failures --all`; add `test_scan_failures_ll_tools_scope_returns_0` and `test_scan_failures_project_scope_returns_0` with explicit `--scope` flags; no change needed to the existing test since `--all` still works.
- `scripts/tests/test_ll_logs.py` (`test_scan_failures_capture_scoped_to_current_project`, line 2622) — **WILL BREAK**: patches `Path.cwd()` to a plain tempdir with no `scripts/pyproject.toml`; after ENH-2318, `is_ll_source_repo(Path.cwd())` returns `False` → auto-selects project mode → existing ll-tools-mode assertions fail. Fix: add `"--scope", "ll-tools"` to the patched `sys.argv` in this test.
- **6 tests asserting `"No ll-* failures found."`** (`test_scan_failures_suppresses_transient_errors`, `test_scan_failures_suppresses_non_recoverable_auth_errors`, `test_scan_failures_excludes_verify_tools`, `test_scan_failures_no_failures_returns_0`, `test_scan_failures_non_cli_token_filtered`, `test_scan_failures_content_free_cluster_suppressed`) — safe when run inside the ll repo (auto-detect → ll-tools → same message), but should add explicit `--scope ll-tools` for robustness and to document intent.
- **`test_scan_failures_json_output_schema`** (line 2469) and **`test_scan_failures_clusters_same_error`** (line 2337) — assert ll-tools-specific JSON key `"tool"` and value `"ll-history"`; safe when run inside the ll repo (auto-detect → ll-tools), but should be guarded with explicit `--scope ll-tools`.
- **New unit tests for `is_ll_source_repo`**: (a) `test_is_ll_source_repo_true_when_pyproject_has_ll_entries` — tmp_path with `scripts/pyproject.toml` containing `ll-*` entry → `True`; (b) `test_is_ll_source_repo_false_when_pyproject_missing` → `False`; (c) `test_is_ll_source_repo_false_when_no_ll_scripts` → `False`. No pattern to follow (function is new).
- **New `--scope` argparse tests** inside `TestScanFailures`: `test_scan_failures_scope_ll_tools_flag_parsed`, `test_scan_failures_scope_project_flag_parsed`, `test_scan_failures_invalid_scope_rejected`. Follow the existing argparse-only tests (lines 2113–2132).
- **New auto-detect tests**: `test_scan_failures_auto_detect_defaults_to_ll_tools_in_ll_repo` and `test_scan_failures_auto_detect_defaults_to_project_in_target_repo` — patch `little_loops.cli.logs.is_ll_source_repo` to return `True`/`False`; assert the resulting behavior differs accordingly.
- **New project-mode clustering tests**: `test_scan_failures_project_mode_clusters_failing_shell_commands`, `test_scan_failures_project_mode_surfaces_corrections` (uses module-level `_insert_correction` helper at line 1455 — currently zero coverage for `_query_recurring_corrections`), `test_scan_failures_project_mode_json_schema`. Use `_assistant_bash_record` + `_user_tool_result_record` helpers already in `TestScanFailures`.
- `scripts/tests/test_issue_lifecycle.py` (`TestClassifyFailure`, ≈line 551) — extend only if `classify_failure` gains project-mode signals; otherwise use as-is for noise filtering.

### Documentation
- `docs/reference/CLI.md`, `commands/help.md` (`/ll:help`), and `.claude/CLAUDE.md`
  (the `ll-logs` description) — document the two modes and default selection.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:3714` — full inline description of `scan-failures` currently says "Mine failed `ll-*` Bash calls from interactive session JSONL logs … JSON schema: `[{tool, count, normalized_sig, sample_error, session_ids}]`"; update to document `--scope {project,ll-tools}`, auto-detect default, and that the JSON schema differs per mode.
- `docs/reference/CLI.md:1983` — subcommand table row describes only ll-tools behavior; `CLI.md:2042–2051` flag table missing `--scope`; `CLI.md:2091–2094` examples are all ll-tools-mode; add project-mode examples and `--scope` flag.
- `docs/guides/HISTORY_SESSION_GUIDE.md:302-309` — "Mine failed commands for bugs" section shows only old ll-tools examples; add project-mode example (`ll-logs scan-failures --project . --scope project --capture`) and note on auto-detect.
- `docs/ARCHITECTURE.md:228` — module description mentions `scan-failures` subcommand; minor update if the subcommand's one-line purpose changes.
- `scripts/little_loops/cli/__init__.py:15` — module docstring currently says "(scan-failures mines failed ll-* calls)"; update to reflect two modes.
- `commands/help.md:293` — `ll-logs` entry currently says "scan-failures for mining failed ll-* calls into bug candidates"; update to reflect two-mode operation and auto-detect.
- `scripts/little_loops/init/writers.py:90` — `_CLAUDE_MD_COMMANDS_BLOCK` template says "scan-failures" mines "ll-relevant log entries"; this template is written into `.claude/CLAUDE.md` for newly initialized projects via `write_config()`. Update to characterize scan-failures as also supporting user's own failures.
- `logs.py:1796` — `scan_failures_parser` `help=` string currently says "Mine failed ll-* calls from interactive session logs and propose bug issues"; update to reflect two modes.
- `logs.py:1820` — `--capture` `help=` string says "Create bug issue files for each failure cluster (one per tool+error signature)"; "tool+error-signature" keying is ll-tools-mode-specific; update to reflect that project mode uses a different clustering key.

### Configuration
- N/A — mode is selected via flag + auto-detect; no config-schema change required
  unless a persisted `--scope` default is added later.

### Codebase Research Findings

_Added by `/ll:refine-issue` — anchors verified against current source:_

**Core anchors in `scripts/little_loops/cli/logs.py`:**
- `_cmd_scan_failures()` (line 954) — the scan loop. Today it matches **only** `ll-*`
  Bash commands via `_LL_BASH_RE` (line 207) and a `_load_cli_allowlist()` gate (used at
  line 958/1011). Project mode must widen this past the `ll-*` allowlist.
- `scan-failures` subparser in `_build_parser()` (≈line 1794) — add the mode flag
  alongside the existing required `--project`/`--all` mutex group, `--window-days`,
  `--capture`, `--capture-foreign`, `--json`.
- `_FailureCluster` (line 943, already carries `cwd_path`) + `_normalize_error_sig()`
  (line 916) — clustering primitives reusable for project-mode failure grouping.
- `_capture_failure_clusters()` (line 1132) — the capture path. It builds a synthetic
  `IssueInfo(issue_type="bugs", priority="P1", title="Tool failure in <tool>")` and the
  generated body hardcodes a `/ll:manage-issue … fix` reproduction step. **This template
  is plugin-bug-shaped**; project mode (failing tests/commands/corrections) needs a
  distinct issue template, not the "Tool failure in X" one.

**⚠ No ll-source-repo detector exists.** The Proposed Solution assumes detecting the ll
repo via `.claude-plugin/plugin.json` name=="little-loops". A grep confirms **no such
detector, and no `plugin.json` name check, exists anywhere in non-test code.** The only
existing implicit probe is `_load_cli_allowlist(root)` (lines 887–902), which identifies
the ll repo as a side effect by reading `root/scripts/pyproject.toml [project.scripts]`
for `ll-*` entries (empty set ⇒ not the ll repo). Recommend extracting a single explicit
detector (e.g. `is_ll_source_repo(root)`) shared by both the new default-selection and the
allowlist probe, rather than duplicating the heuristic.

**Reusable "repeated corrections" machinery (project mode's correction signal):**
- `session_store.is_correction(text)` (line 150) — the correction classifier.
- `session_store.mine_corrections_from_messages()` (line 1417) — populates the
  `user_corrections` table in `.ll/history.db`.
- `history_reader._query_recurring_corrections()` (lines 926–972) — `GROUP BY content
  ORDER BY seen_count`; this is exactly the "recurring corrections" the SessionStart hook
  already surfaces (the motivation's pairing target).
- `history_reader.find_user_corrections(topic)` (line 197) — topic LIKE search →
  `UserCorrection` objects.
- Note: `_cmd_scan_failures` today reads **only raw JSONL and never touches history.db.**
  The corrections signal should source from `user_corrections` (history.db) via these
  helpers — a new data source for this command.

**ENH-2093 noise filters are mode-agnostic — reuse as-is in project mode:**
- `classify_failure(error_output, returncode)` (issue_lifecycle.py:57) returns
  TRANSIENT/NON_RECOVERABLE for sandbox / OOM(SIGKILL) / user-cancel / inline-snippet
  traceback / auth failures. Run project-mode failures through it unchanged.
- `_is_content_free_error()` (≈line 1078) drops bare `exit code N` clusters; the
  foreign-project skip lives in `_capture_failure_clusters()` (≈line 1145).

**Data-source widening is net-new.** There is **no existing extraction** for failing test
runs or erroring non-`ll-*` shell commands — the current scan is hard-scoped to the `ll-*`
allowlist. Project mode must (a) match arbitrary non-ll shell/test commands from
`assistant` Bash `tool_use` + `user` `tool_result` records, and (b) add the corrections
signal above.

**Consistency precedent for the mode flag:** the `stats` subparser already uses a named
enum selector — `--sort choices=["freq","corrections"]` (line 1787). This favors
`--scope {project,ll-tools}` over a bare `--ll-tools` boolean for in-module consistency.

**Test scaffolding to model after:**
- `scripts/tests/test_ll_logs.py` `TestScanFailures` (≈lines 2033–2294) with helpers
  `_make_project_dir`, `_assistant_bash_record`, `_user_tool_result_record`; module-level
  `_insert_correction()` / `_populate_skill_events()` (≈lines 1437–1466) seed
  `user_corrections` / `skill_events` in history.db for project-mode correction tests.
- `scripts/tests/test_issue_lifecycle.py` `TestClassifyFailure` (≈line 551) — extend only
  if `classify_failure` gains project-mode signals.

**Back-compat caller (confirmed):** `.loops/ll-logs-telemetry-digest.yaml` (line 41)
invokes `ll-logs scan-failures --json` with **no scope flag**. It is protected by the
auto-detect default **only when run inside the ll repo**. If the default-selection policy
changes to "explicit scope required" (Option B in Proposed Solution), this loop YAML must
be edited to pass `--scope ll-tools`.

## Scope Boundaries

**In scope:** the mode selector, project-mode failure clustering
(tests/commands/corrections), and the ll-repo auto-detect default.

**Out of scope:**
- Removing or altering the existing ll-tools mining behavior — it is preserved
  unchanged behind the flag/auto-detect default.
- Implementing the whole-session corpus ([FEAT-2316]) or the CWD/host scoping
  defaults ([ENH-2317]); project mode benefits from them but they ship
  separately.
- New failure signals beyond tests / erroring commands / repeated corrections
  (e.g. parsing arbitrary application logs).
- Finalizing the default-selection policy without maintainer confirmation — the
  default is proposed here, not decided (see Proposed Solution).

## Impact

- **Priority**: P3 — additive intake path that makes `scan-failures` useful in a
  target project; valuable but non-blocking and sequenced behind related work
  ([FEAT-2316] / [ENH-2317]).
- **Effort**: Medium — factoring today's path behind a flag is low-risk, but
  project-mode clustering plus ll-repo auto-detect is net-new code (reuses
  ENH-2093 noise filters).
- **Risk**: Medium — back-compat for FEAT-1925 / ENH-2070 callers that expect
  current behavior; mitigated by the ll-repo auto-detect default and
  "identical output" regression tests for ll-tools mode.
- **Breaking Change**: No — current behavior is preserved behind
  `--ll-tools` / the auto-detect default.

## Relationship to existing issues

- **ENH-1922** (done) added `scan-failures` auto-file-bugs; **ENH-2093** (done)
  fixed its near-100% noise — both inform the *current* (ll-tools) mode that this
  issue preserves.
- **FEAT-1925** (done, telemetry-digest loop) and **ENH-2070** (automated bug
  intake) are the back-compat callers the auto-detect default protects.
- Completes the target-project cluster with [FEAT-2315] / [FEAT-2316] /
  [ENH-2317]; distinct from EPIC-1918's "telemetry for ll itself" framing.


## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Two coordination requirements with sibling ll-logs issues:

1. **`--scope` flag ownership.** This issue introduces `--scope {project,ll-tools}` on `scan-failures` as the failure-source dimension selector. FEAT-2316 must not introduce a second `--scope` flag with a different value space (`{ll,all}`) on the same subcommand. Agreed split: `--scope` = failure-source selector on `scan-failures` (this issue); `--all-tools` = corpus-breadth selector everywhere (FEAT-2316). Update the flag-naming section of this issue and FEAT-2316's integration notes to document the agreed split explicitly.

2. **`scan-failures` argparse group.** This issue's wiring step 6 identifies the required `--project`/`--all` mutually-exclusive group on `scan-failures` (logs.py:1798) as a blocker and leaves the resolution open with three options (a/b/c). ENH-2317 already commits to option (a) — CWD-default three-way resolver — which resolves this blocker. Implement ENH-2317 first (hence `depends_on: ENH-2317`), then remove wiring step 6 from this issue's scope: the argparse group blocker is resolved by ENH-2317 and need not be re-solved here. Related issues: ENH-2317, FEAT-2316.

## Session Log
- `/ll:audit-issue-conflicts` - 2026-06-27T22:09:56 - `60b514f4-3db2-4641-831b-e2895943cc2b.jsonl`
- `/ll:wire-issue` - 2026-06-26T23:05:35 - `64adeb74-858e-4aba-8e05-0d67aa559f7c.jsonl`
- `/ll:decide-issue` - 2026-06-26T22:54:54 - `585197a2-6eeb-4c75-8344-69370d9d5505.jsonl`
- `/ll:refine-issue` - 2026-06-26T22:44:38 - `05b90e4c-3bca-408a-b27e-c7f150dd4fb0.jsonl`
- `/ll:format-issue` - 2026-06-26T22:28:02 - `c2159b1e-229a-4c36-b3de-63e69443f041.jsonl`
- `/ll:capture-issue` - 2026-06-26T22:05:51Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/afe96ddb-ff74-49fc-b0a9-7bd525432c1d.jsonl`

---

## Status

- [ ] open
