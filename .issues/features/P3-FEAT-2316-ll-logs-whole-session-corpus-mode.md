---
id: FEAT-2316
title: 'll-logs whole-session corpus mode: analyze non-ll tool activity'
type: FEAT
priority: P3
status: open
captured_at: '2026-06-26T22:05:51Z'
discovered_date: '2026-06-26'
discovered_by: capture-issue
relates_to:
- EPIC-1918
- ENH-1919
- ENH-2103
- ENH-2132
- ENH-2093
- FEAT-2315
- ENH-2317
- ENH-2318
depends_on:
- ENH-2317
- ENH-2318
labels:
- captured
- ll-logs
- target-project
- corpus
confidence_score: 94
outcome_confidence: 78
score_complexity: 15
score_test_coverage: 22
score_ambiguity: 21
score_change_surface: 20
parent: EPIC-2369
---

# FEAT-2316: `ll-logs` whole-session corpus mode (analyze non-ll tool activity)

## Summary

Add a corpus mode (a flag, e.g. `--all-tools`, or the default in non-ll
projects) so the analysis subcommands (`sequences`, and optionally
`scan-failures`) see the **full** tool stream — Edit/Write/Bash/Read/test/git —
not just `/ll:` and `ll-*` invocations. This is what makes the corpus reflect a
target-project user's real workflow.

## Current Behavior

`_is_ll_relevant()` in `scripts/little_loops/cli/logs.py` (and the unified
`_detect_ll_signal()` from [ENH-2132]) only keeps records that invoke `/ll:`
skills or `ll-*` CLI commands. Everything else is discarded before any
subcommand sees it. In the little-loops repo nearly every session is ll-heavy,
so the corpus is rich; in a target project that slice is thin, so
`sequences`/`stats` return sparse, meta-only output.

## Expected Behavior

A whole-session mode treats the user's full tool-use stream as the corpus, so
`ll-logs sequences --all-tools` surfaces real repeated workflows like
`Edit → Bash(pytest) → Edit → Bash(git commit)`. This feeds
`/ll:loop-suggester --from-sequences` ([ENH-2103]) with the user's *actual*
automatable cycles instead of only ll-command chains they already know they run.

## Motivation

This is the foundational unlock for target-project value: the digest ([FEAT-2315])
gives a passive view, but whole-session sequences turn `ll-logs` from "ll-tool
introspection" into "your-project workflow intelligence" that drives loop
proposals — the actual automation win for someone who installed the plugin.

## Proposed Solution

- Generalize the signal detection so `_detect_ll_signal()` ([ENH-2132]) can emit
  a generic tool-use signal (tool name + Bash command head) in addition to the
  ll-specific signal, gated by a corpus-scope parameter.
- Add `--all-tools` (or `--scope all|ll`) to `sequences` (and consider
  `scan-failures` once [ENH-2318] lands). Default scope is `ll` in the
  little-loops source repo for back-compat; consider defaulting to `all` in
  target projects.
- Normalize noisy tool args (e.g. collapse Bash to the leading executable) so
  n-grams group meaningfully.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` — `_detect_ll_signal()` (logs.py:297) to emit a
  generic tool-use signal (tool name + Bash command head) under `all` scope;
  `_cmd_sequences()` (logs.py:495) and `_count_ngrams()` (logs.py:411) to thread a
  `scope` parameter; add `--all-tools` / `--scope {ll,all}` to the `sequences`
  argparse subparser.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py` — module docstring (line 16) describes
  `ll-logs` as discovering "ll-relevant JSONL entries"; update to reflect the
  whole-session scope. The `main_logs` re-export (line 60) and `__all__` entry
  need no signature change. [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `_is_ll_relevant()` (logs.py:31) — the current discard gate; confirm the `all`
  path bypasses it rather than silently dropping non-ll records.
- `/ll:loop-suggester --from-sequences` (`skills/loop-suggester`) — downstream
  consumer of `sequences` output (ENH-2103); must accept the richer corpus
  without schema changes.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/ctx_stats.py` — imports `_aggregate_skill_stats` from
  `little_loops.cli.logs` at module load (line 20, called at line 494). Not in the
  edit set, but any import-time error introduced into `logs.py` breaks `ll-ctx-stats`
  too. Verify the module still imports cleanly after the change. [Agent 1/2 finding]
- `.loops/ll-logs-telemetry-digest.yaml` — the telemetry meta-loop invokes
  `ll-logs sequences` (its `run_sequences` state); a live downstream consumer that
  could opt into `--all-tools`. Confirm the default `--scope ll` keeps this loop's
  source-repo behavior unchanged. [Agent 1 finding]

### Similar Patterns
- `scan-failures` subcommand in `logs.py` — the same corpus-scope generalization
  applies once [ENH-2318] lands; keep the scope flag name and semantics identical.

### Tests
- `scripts/tests/test_ll_logs.py` — add a seeded mixed-corpus JSONL fixture (ll +
  raw Edit/Bash/Read), assert non-ll n-grams appear only under `all` scope and are
  absent under `ll`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_logs.py` (specific touchpoints) —
  - extend `TestDetectLlSignal` (test:3307) with `scope="all"` cases: an `Edit`
    record and a non-ll `Bash` record (e.g. `git status`) return a non-`None`
    signal under `all` and `None` under default `ll` (model after
    `test_detect_ll_signal_bash_tool_use` test:3348);
  - extend `TestArgumentParsingSequences` (test:647) to assert `--all-tools` sets
    `args.all_tools=True`, `--scope all` sets `args.scope="all"`, and the defaults
    are `scope=="ll"` / `all_tools is False` (model after
    `TestArgumentParsingStats.test_stats_sort_default_freq` test:1479);
  - add an `_edit_record()` / raw-`Bash` helper to `TestSequences` (test:702)
    mirroring `_assistant_bash_record` (test:733) for the mixed fixture. [Agent 3 finding]
- `scripts/tests/test_ll_logs.py` (AT-RISK, update when threading scope) —
  - `test_sequences_all_mode` (test:1070) exercises the `--all` all-projects path
    end-to-end; breaks if `discover_all_projects()` gains a `scope` parameter
    (calling convention changes);
  - `test_sequences_project_and_all_mutually_exclusive` (test:692) breaks if
    `--all-tools`/`--scope` are placed in the same `required` mutually-exclusive
    group as `--project`/`--all` — keep them as separate optional flags. [Agent 3 finding]
- `scripts/tests/test_cli.py` — `TestMainLogsIntegration` (test:2921) tests
  top-level `main_logs` dispatch (uses `patch.object(sys, "argv", ...)`); add a
  `--scope`/`--all-tools` smoke case here for entry-point coverage. [Agent 1/3 finding]
- `scripts/tests/test_loop_suggester.py` — `TestFromSequencesModeSchema`
  (test:480–695) asserts the `ChainResult` wire schema (`chain`, `count`, `edges`).
  No schema change is expected under `all` scope; add/verify a case proving the
  richer corpus still conforms (lock the no-schema-change AC in). [Agent 2/3 finding]
- `scripts/tests/test_init_install.py` / `test_init_core.py` — cover
  `detect_installation()` itself but NOT its use as the scope-default selector. If
  the default-scope-by-project-type mechanism uses `detect_installation()`, add a
  `TestScopeDefaultSelection`-style test (`local-editable` → `ll`, `pypi` → `all`).
  [Agent 3 finding]

### Documentation
- `docs/reference/CLI.md` — document `ll-logs sequences --all-tools` / `--scope`
  and the default-by-project-type behavior.
- `.claude/CLAUDE.md` — update the `ll-logs` CLI summary line to mention the
  `sequences` scope flag.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — the `main_logs`/`sequences` description (~line 3711)
  reads "Extract tool-chain n-grams of ll invocations"; document `--scope`/
  `--all-tools`. The JSON output schema line (`[{chain, count, edges}]`) stays
  accurate (field structure unchanged). [Agent 2 finding]
- `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md` — "Sequences-driven loop suggestions"
  (lines ~422–449) describes `sequences` as extracting "ll-* invocations" only;
  the prose becomes inaccurate under `--scope all`. Update the description and the
  source-column examples. [Agent 2 finding]
- `docs/guides/HISTORY_SESSION_GUIDE.md` — "Session Log Tooling (ll-logs)" section
  cross-references `ll-logs sequences`; lower impact, but check the See-Also/flag
  pointers stay consistent with CLI.md. [Agent 2 finding]
- `commands/loop-suggester.md` — From-Sequences Mode step FS-1 (lines ~307–313)
  hardcodes `ll-logs sequences --json --min-count 2`; if whole-session capture is
  the intent, that invocation needs `--all-tools`. Step FS-3's command-matching
  table already absorbs the wider vocabulary (no structural change). [Agent 2 finding]
- `skills/ll-loop-suggester/SKILL.md` — frontmatter description references
  "ll-logs sequences n-gram output"; soft drift, mention the wider corpus. [Agent 2 finding]
- `commands/help.md` — line ~293 `ll-logs` summary "sequences for tool-chain
  n-grams"; mention the scope flag. NOTE: `test_wiring_cli_registry.py`'s
  `DOC_STRINGS_PRESENT` (test:45) only asserts the bare string `"ll-logs"` is
  present — keep that substring. [Agent 2 finding]
- `docs/reference/COMMANDS.md` — line ~647 `--from-sequences` description
  ("repeated command chains") should widen to cover non-ll tool chains. [Agent 2 finding]

### Configuration
- N/A — scope default is derived from project context (ll source repo vs. target
  project), no config key required.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (anchors verified against
`scripts/little_loops/cli/logs.py`):_

**Anchor verification.** All four cited anchors are accurate: `_is_ll_relevant()`
@`logs.py:31`, `_detect_ll_signal()` @`logs.py:297` (its `_InvocationSignal`
dataclass @`logs.py:284`), `_count_ngrams()` @`logs.py:411`, `_cmd_sequences()`
@`logs.py:495`.

**CORRECTION — the sequences discard gate is NOT `_is_ll_relevant()`.** The
Dependent-Files note above calls `_is_ll_relevant()` (logs.py:31) "the current
discard gate," but that function is **never called by the sequences pipeline**.
Its only callers are `_has_ll_activity()` (logs.py:96, project-level) and
`_cmd_extract()` (logs.py:637, the `extract` subcommand). The actual per-record
gate for `sequences` lives in **`_extract_ll_event_streams()` (logs.py:222)** at
`tool_name = _extract_tool_name(record); if tool_name is None: continue`
(logs.py:258–260) — i.e. `_detect_ll_signal()` returning `None`. **This function
(`_extract_ll_event_streams`) is the missing primary edit site** and must be added
to "Files to Modify": it needs the `scope` parameter threaded in, and under
`scope=all` must build `InvocationEvent`s from the generic signal instead of
dropping non-ll records.

**NEW HAZARD — project-level filter drops thin/non-ll projects before sequences
runs.** `_cmd_sequences()` with `--all` calls `discover_all_projects()`
(logs.py:131), which gates each project folder through `_has_ll_activity()`
(logs.py:184 → logs.py:96 → `_is_ll_relevant()`). A pure target project with
*zero* ll activity is therefore excluded from the corpus entirely — defeating the
whole-session purpose. The `scope=all` path must bypass/relax `_has_ll_activity()`
(or `discover_all_projects()` needs a scope-aware variant). Single-project runs
(`--project DIR`) skip this gate, so the hazard is specific to the `--all`
(all-projects) path. Add an acceptance criterion covering it.

**NEW HAZARD — flag-name collision: `--all` already exists on `sequences`.** The
subparser already defines `--all` (logs.py:1728, "Analyze all projects with ll
activity") in a required mutually-exclusive group with `--project`
(logs.py:1721–1732). The proposed `--all-tools` is distinct and safe, but the
`--scope all` value overloads the word "all" (corpus-scope `all` vs.
all-*projects* `--all`). Recommend keeping `--all-tools` as the primary spelling
with `--scope {ll,all}` as the explicit form, and disambiguating both in help text.

**N-gram token packing (no consumer schema change needed).** The n-gram token is
`InvocationEvent.tool_name` (logs.py:214) — `_count_ngrams()` builds
`names = [e.tool_name for e in events]` (logs.py:425) and slides tuples over it.
There is **no** normalization today (the bash path stores the first `ll-<name>`
token via `_LL_BASH_RE` @logs.py:207–208 and discards the rest into
`input_context`, which the n-gram path never reads). For `scope=all`, pack the
normalized generic token (e.g. `Bash(pytest)`, `Bash(git)`, `Edit`, `Read`) into
`InvocationEvent.tool_name`. Because the wire shape of `sequences` output is
unchanged, `/ll:loop-suggester --from-sequences` (ENH-2103) consumes the richer
corpus without schema changes (AC satisfied by construction).

**Bash-head normalization — reuse existing precedents (none in logs.py today).**
- `value.strip().split()[0]` to take the leading executable — `init/validate.py:115`
  (`_check_commands`, collapses `"python -m pytest"` → `"python"`).
- `_extract_skill_from_action()` — `fsm/executor.py:2131` (`split(maxsplit=1)[0]`
  for slash-command heads).
- For non-ll Bash commands prefer `shlex.split(cmd)[0]` (falls back to
  `cmd.strip().split()[0]` on `ValueError`) to get the executable; optionally keep
  the first subcommand (e.g. `git commit`, `pytest`) for useful grouping.

**`--scope` flag precedent (choices+default).** Model after `stats --sort`
(`logs.py:1786`, `choices=["freq","corrections"], default="freq"`, read via
`getattr(args, "sort", "freq")` @logs.py:1201) and `session --kind`
(`session.py:88`, `choices=[...], default=None`). Add `--scope {ll,all}`
(default `ll`) plus a `--all-tools` `store_true` convenience that maps to
`scope="all"`. New flags go in `_build_parser()` near logs.py:1733–1761; dispatch
is `main_logs()` @logs.py:1950–1951.

**Default-scope-by-project-type — detection mechanism (recommendation).** No
`is_ll_source_repo()` helper exists. Recommended: reuse `detect_installation()`
(`init/install_check.py:39`) — returns `"local-editable"` for the ll source-repo
dev install (→ default `scope=ll` for back-compat) vs. `"pypi"`/plugin (→ default
`scope=all`). Alternatives if a lighter probe is preferred: `_load_cli_allowlist()`
(`logs.py:887`, empty frozenset when `scripts/pyproject.toml` is absent) or
`_find_plugin_root()` (`skill_expander.py:25`). This is a narrow mechanism choice,
not a competing whole-feature approach — pick one in implementation; no separate
decision gate required.

**Related module (cross-reference, not an edit site).** `ll-workflows` has its own
n-gram/sequence stack under `scripts/little_loops/workflow_sequence/`
(`analysis.py`, `models.py`, `io.py`). `sequences` here is independent
(`logs.py:_count_ngrams`); keep the implementation in `logs.py` but mirror token
conventions if the two corpora are ever merged.

**Test scaffolding (model after `TestSequences` in `test_ll_logs.py:702`).**
Existing helpers: `_make_project_dir()` (logs test:705), `_assistant_bash_record()`,
`_queue_record()`; integration tests triple-patch `sys.argv`,
`pathlib.Path.home`, and `little_loops.cli.logs.Path.cwd`; argparse-only tests use
`_parse_args()` (`logs.py:1910`) under `TestArgumentParsingSequences`
(`test_ll_logs.py:647`). Add a non-ll record helper (e.g. `_edit_record()`, and a
raw-`Bash` record whose command does **not** match `\bll-[\w-]+`) for the mixed
fixture, plus an argparse test asserting `--all-tools`/`--scope` parse and default
to `ll`.

## Implementation Steps

1. Extend signal detection to optionally yield non-ll tool-use records.
2. Thread a `scope` parameter through `_cmd_sequences` (and the n-gram builder).
3. Add the CLI flag + default-selection logic (ll-repo vs target project).
4. Tests: seeded JSONL with mixed ll + raw tool use; assert n-grams include
   non-ll chains only in `all` scope.
5. Docs + wire the new flag into `/ll:loop-suggester --from-sequences` guidance.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the
implementation:_

6. Update `scripts/little_loops/cli/__init__.py` — refresh the module docstring
   (line 16, "ll-relevant JSONL entries") to reflect whole-session scope; confirm
   the `main_logs` re-export and `__all__` need no signature change.
7. Verify `ll-ctx-stats` import safety — `ctx_stats.py` imports
   `_aggregate_skill_stats` from `logs.py` at module load; an import-time error in
   the edited `logs.py` would break that CLI too. Add it to the smoke run.
8. Confirm `.loops/ll-logs-telemetry-digest.yaml` (`run_sequences` state) keeps its
   source-repo behavior under the default `--scope ll`.
9. Update at-risk tests when threading `scope`/adding flags:
   `test_sequences_all_mode` (if `discover_all_projects()` gains a `scope` param)
   and `test_sequences_project_and_all_mutually_exclusive` (keep `--all-tools`/
   `--scope` as separate optional flags, not in the required `--project`/`--all`
   group).
10. Extend docs beyond CLI.md + CLAUDE.md to `docs/reference/API.md`,
    `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md`, `docs/reference/COMMANDS.md`,
    `commands/help.md`, `commands/loop-suggester.md`, and
    `skills/ll-loop-suggester/SKILL.md`.
11. If default-scope-by-project-type uses `detect_installation()`, add a
    scope-default selection test (`local-editable` → `ll`, `pypi` → `all`); none
    exists today.

## Use Case

A user runs `ll-logs sequences --all-tools --top 10` and `/ll:loop-suggester
--from-sequences` proposes a loop for their recurring "edit → test → fix →
commit" cycle — automation grounded in what they actually do, not in ll commands.

## Acceptance Criteria

- [ ] `ll-logs sequences --all-tools` (alias for `--scope all`) includes non-ll
  tool-use records (Edit/Write/Bash/Read/test/git) in the n-gram corpus.
- [ ] `--scope ll` keeps the current ll-only behavior and remains the default in
  the little-loops source repo (back-compat).
- [ ] `_detect_ll_signal()` emits a generic tool-use signal (tool name + Bash
  command head) when scope is `all`, in addition to the existing ll-specific
  signal — built on the single ENH-2132 detection point, not a re-fork.
- [ ] Noisy tool args are normalized (e.g. Bash collapsed to its leading
  executable) so equivalent invocations group into the same n-gram.
- [ ] A seeded JSONL fixture with mixed ll + raw tool use yields n-grams
  containing non-ll chains only under `all` scope, and excludes them under `ll`.
- [ ] `ll-logs sequences --all-tools` output feeds `/ll:loop-suggester
  --from-sequences` (ENH-2103) without changes to that consumer's input schema.
- [ ] Default scope selection follows project type (source repo → `ll`; target
  project → `all`) and the behavior is documented in `docs/reference/CLI.md`.
- [ ] _(research-derived)_ Under `--scope all` with `--all` (all-projects), the
  project-level `_has_ll_activity()` gate (logs.py:96, via `discover_all_projects`)
  is bypassed/relaxed so a pure non-ll target project is not dropped from the
  corpus before `sequences` runs.
- [ ] _(research-derived)_ The new flag does not collide with the existing
  `sequences --all` (all-projects) flag: `--all-tools` maps to `scope="all"` and
  help text disambiguates corpus-scope `all` from all-*projects* `--all`.

## API/Interface

```bash
# New flags on `ll-logs sequences` (and later `scan-failures`, per ENH-2318)
ll-logs sequences --all-tools          # alias for --scope all
ll-logs sequences --scope {ll,all}     # ll  = ll-only (default in ll source repo)
                                       # all = whole-session tool stream
```

```python
# Internal: corpus-scope parameter threaded through detection and n-gram build
def _detect_ll_signal(record: dict, *, scope: str = "ll") -> _InvocationSignal | None: ...
def _cmd_sequences(args: argparse.Namespace, logger: Logger) -> int: ...  # reads args.scope
```

Breaking change: **No** — `--scope ll` default preserves existing behavior in the
source repo; the `all` corpus is strictly additive and opt-in there.

## Impact

- **Priority**: P3 — foundational unlock for target-project value (turns `ll-logs`
  from ll-tool introspection into your-project workflow intelligence), but not
  blocking; depends on ENH-2132 (done) and pairs with [FEAT-2315] / [ENH-2317].
- **Effort**: Medium — builds on the single `_detect_ll_signal` detection point
  (ENH-2132); the work is the generic-signal branch, arg normalization, and
  threading `scope` through `_cmd_sequences` / `_count_ngrams`, plus the mixed
  fixture and CLI/docs wiring.
- **Risk**: Medium — widening the corpus reintroduces the ENH-2093 noise hazard
  (broadening "failure" signal once generated 71 noise issues); must ship with the
  same project-scoping / noise discipline ([ENH-2317]). Default `--scope ll`
  contains the blast radius in the source repo.
- **Breaking Change**: No

## Relationship to existing issues

- **ENH-2093** (done) is the cautionary tale: broadening what counts as a
  "failure" signal generated 71 noise issues. Whole-session mode deliberately
  widens the corpus, so it must ship with the same project-scoping / noise
  discipline — see [ENH-2317] and the noise lessons in ENH-2093.
- **ENH-2132** (done) unified signal detection into `_detect_ll_signal`; this
  builds on that single detection point rather than re-forking it.
- **ENH-1919 / ENH-2103** are the `sequences` primitive and its loop-suggester
  wiring — the direct consumers that benefit from a richer corpus.
- Part of the target-project cluster with [FEAT-2315] and [ENH-2317]; distinct
  from EPIC-1918's "telemetry for ll itself" framing.


## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Two coordination requirements with ENH-2318:

1. **Repo-detection helper.** Both this issue and ENH-2318 independently implement an "am I in the ll source repo?" detector. ENH-2318's `is_ll_source_repo()` (pyproject.toml probe) is the designated canonical helper — it is more precise about repo identity than `detect_installation()` from `init/install_check.py`, which detects install mode and can diverge on edge installs. This issue must import and call `is_ll_source_repo()` from ENH-2318 for its default-scope-by-project-type logic rather than calling `detect_installation()` directly. This dependency is captured in `depends_on: ENH-2318`.

2. **`--scope` flag collision.** ENH-2318 introduces `--scope {project,ll-tools}` on `scan-failures` as the failure-source dimension selector. This issue must not introduce a second `--scope` flag with different value space on the same subcommand. When extending corpus-breadth selection to `scan-failures`, use `--all-tools` (already the primary spelling elsewhere in this issue) rather than a second `--scope`. Agreed split: `--scope` = failure-source selector on `scan-failures` (ENH-2318); `--all-tools` = corpus-breadth selector everywhere (this issue). Related issue: ENH-2318.

## Session Log
- `/ll:audit-issue-conflicts` - 2026-06-27T22:09:56 - `60b514f4-3db2-4641-831b-e2895943cc2b.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-27T01:23:43 - `14bc42e7-76a4-4427-8347-44e5b2c9966b.jsonl`
- `/ll:wire-issue` - 2026-06-26T22:51:36 - `bbbde623-e8a1-44fe-8766-f891d466029d.jsonl`
- `/ll:refine-issue` - 2026-06-26T22:39:38 - `5f6a6610-169d-4eb1-8f91-368901ce51b9.jsonl`
- `/ll:format-issue` - 2026-06-26T22:27:57 - `6b5f4713-4801-485e-9909-111bcbcf1d9a.jsonl`
- `/ll:capture-issue` - 2026-06-26T22:05:51Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/afe96ddb-ff74-49fc-b0a9-7bd525432c1d.jsonl`

---

## Status

- [ ] open
