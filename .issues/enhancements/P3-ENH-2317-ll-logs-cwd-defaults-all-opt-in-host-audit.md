---
id: ENH-2317
title: 'll-logs: CWD-default scoping, --all opt-in privacy, finish host-awareness'
type: ENH
priority: P3
status: open
captured_at: '2026-06-26T22:05:51Z'
discovered_date: '2026-06-26'
discovered_by: capture-issue
relates_to:
- ENH-1945
- ENH-2093
- ENH-2297
- FEAT-2315
- FEAT-2316
- ENH-2318
labels:
- captured
- ll-logs
- target-project
- multi-host
- privacy
confidence_score: 96
outcome_confidence: 83
score_complexity: 17
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 21
parent: EPIC-2369
---

# ENH-2317: `ll-logs` CWD defaults, `--all` opt-in, finish host-awareness

## Summary

Make `ll-logs` zero-config inside a target project: default subcommands to the
current project, make global `--all` an explicit opt-in (privacy), and finish
threading host selection through the subcommands so non-Claude-Code hosts get
parity.

## Current Behavior

In `scripts/little_loops/cli/logs.py`:
- `extract`, `sequences`, `stats`, `scan-failures`, `dead-skills` each declare a
  **required** mutually-exclusive `--project`/`--all` group — there is no
  zero-config "this project" default.
- Every subcommand calls `discover_all_projects(logger)` with **no** `host=`
  argument, so they rely on the in-function `LL_HOOK_HOST` default
  (`"claude-code"`). There is no `--host` flag, and the module/`description`
  strings still say "from `~/.claude/projects/`". A user on Codex/OpenCode in a
  target project gets claude-code results unless they set an env var.
- `--all` scans **every** project under `~/.claude/projects/` — a cross-project
  data-exposure default for an end user who only wants their own repo.

## Expected Behavior

- Running a subcommand inside an ll project with no target flag defaults to the
  current project (CWD). `--all` remains available but is explicit opt-in.
- A `--host` flag (and/or `orchestration.host_cli` / `LL_HOOK_HOST` resolution
  consistent with `resolve_host()`) selects the session directory, and is passed
  into `discover_all_projects(host=...)` by every subcommand.
- Help text and the module docstring describe the host-correct source, not a
  hardcoded `~/.claude/projects/`.

## Motivation

Friction and privacy are what make `ll-logs` feel maintainer-only. CWD defaults
remove the "which flag do I pass" papercut; `--all` opt-in stops an end user from
inadvertently aggregating other repos' data; host parity matters now given the
in-flight multi-host generalization work.

## Proposed Solution

- Relax the required `--project`/`--all` group to default to CWD when neither is
  given (keep them mutually exclusive).
- Add a shared `--host` argument; resolve via `resolve_host()` semantics and pass
  `host=` into `discover_all_projects` at all six call sites.
- Update `description`/epilog/docstrings to be host-agnostic.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis. All line/signature
references in this issue verified accurate against current `cli/logs.py`._

**1. `--all` is a dummy flag today — the `else` branch is the privacy trap.**
`grep -n "args.all" cli/logs.py` returns **nothing**. Every one of the five
handlers (`_cmd_sequences` `logs.py:497`, and the four siblings at `:606`,
`:835`, `:960`, `:1171`) uses the dichotomy `if args.project: <single project>
else: discover_all_projects(logger)`. The `else` branch only fires today because
`required=True` forces the caller to pass `--all`. **Dropping `required=True`
without also checking `args.all` would route a *bare* invocation (no flag) into
the `else` branch → aggregate every project — the exact cross-project leak this
issue exists to close.** The shared resolver must therefore branch **three** ways
explicitly, not relax to a two-way default:
- `args.project` set → `[that project]`
- `args.all` set → `discover_all_projects(host=...)` (aggregate; opt-in)
- neither → `[Path.cwd()]` (CWD default — the new behavior)

**2. `resolve_host()` returns a `HostRunner`, not a host string — bridge via
`.name`.** `discover_all_projects(host=...)` keys off a host *string*
(`logs.py:152-161`: `"claude-code"`→`~/.claude/projects`,
`"codex"`→`~/.codex/projects`, `"opencode"`, `"pi"`). `resolve_host()`
(`host_runner.py:797`) returns a `HostRunner` object. The bridge is
**`resolve_host().name`** — `HostRunner` carries a `name` attribute
(`host_runner.py:167`) whose concrete values (`"claude-code"` `:222`, `"codex"`
`:391`, `"opencode"` `:637`, `"pi"` `:709`) match `discover_all_projects`'s host
branches one-for-one. This confirms `--host codex` probes `~/.codex/projects`.

**3. `resolve_host()` raises where `discover_all_projects` softly defaults —
preserve the soft default.** `resolve_host()` raises `HostNotConfigured`
(`host_runner.py:841`) when no host CLI is on `PATH`, whereas
`discover_all_projects` silently falls back to `"claude-code"`
(`logs.py:149-150`). A naive `host = resolve_host().name` would **regress**
environments that have `~/.claude/projects` logs on disk but no `claude` binary
installed (CI, log-only inspection). The new `--host` resolver must catch
`HostNotConfigured` and fall back to the existing `LL_HOOK_HOST`/`claude-code`
soft default — i.e. mirror `resolve_host()` *precedence* without inheriting its
*raise-on-missing* behavior.

**4. The 6th `host=` thread (`discover`, `logs.py:1933`) is NOT one of the five
CWD-default subcommands.** Call site `:1933` lives in the top-level `discover`
command handler (`logs.py:1932-1939`), which has no `--project`/`--all` group and
inherently lists *all* projects. It needs the `host=` thread + a `--host` flag,
but a CWD default would be nonsensical for `discover`. Treat it as host-awareness
only; do **not** add the three-way resolver there.

**5. No parent-parser scaffolding exists for a "shared `--host`".**
`_build_parser` (`logs.py:1665`) constructs each subparser independently — there
is **no** `parents=[...]` pattern in the file. "Add a shared `--host` argument"
therefore requires *introducing* an `argparse.ArgumentParser(add_help=False)`
parent that declares `--host`, then passing `parents=[host_parent]` to each of
the six affected subparsers (`extract`, `sequences`, `stats`, `scan-failures`,
`dead-skills`, **and** `discover`) — or adding `--host` to all six individually.
The former is the lower-drift option.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` — relax the five `required=True`
  mutually-exclusive `--project`/`--all` groups (`extract` ~L1699, `sequences`
  ~L1721, `stats` ~L1767, `scan-failures` ~L1798, `dead-skills` ~L1833) to
  optional with a CWD default; add a shared `--host` argument; pass `host=` into
  the six `discover_all_projects(logger)` call sites (~L505, 614, 839, 968,
  1174, 1933); rewrite `description`/epilog/docstring wording away from a
  hardcoded `~/.claude/projects/`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py` (module docstring ~L15) — the `ll-logs`
  bullet hardcodes `~/.claude/projects/`: _"Discover, extract, and analyze
  ll-relevant JSONL entries from `~/.claude/projects/`"_. This is the
  **source-of-truth** docstring that propagates into `.ll/ll-continue-prompt.md`
  (identical string), so fixing it here is the correct host-agnostic wording fix —
  do **not** hand-edit the generated continue-prompt. [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `discover_all_projects(logger, *, host=...)` already accepts `host=` (defined
  at `cli/logs.py:131`) — no signature change; only the call sites must thread it.
- `resolve_host()` in `scripts/little_loops/host_runner.py` — source of
  host-selection semantics the new `--host` flag must mirror
  (`orchestration.host_cli` / `LL_HOOK_HOST` resolution).

_Wiring pass added by `/ll:wire-issue`:_
- ⚠ **Behavioral coupling — `.loops/ll-logs-telemetry-digest.yaml`** invokes five
  affected subcommands with **no** target flag: `ll-logs extract --quiet` (L16),
  `ll-logs stats` (L29), `ll-logs scan-failures --json` (L41), `ll-logs sequences
  --top 20 --min-count 3` (L86), `ll-logs dead-skills --json` (L99). Under today's
  `required=True` groups these bare calls **error out** (the loop guards several
  with `--help` probes / `|| true` and reports `REFRESH_FAILED`). After this issue
  drops `required=True`, those same calls will newly **succeed and scope to CWD** —
  which is the intended per-project digest behavior, so this is a positive side
  effect, but the loop's runtime behavior changes. Verify a `ll-loop run
  ll-logs-telemetry-digest` post-change actually produces CWD-scoped output rather
  than silently degrading. [Agent 1 finding]
- `scripts/little_loops/cli/ctx_stats.py` (imports `_aggregate_skill_stats` at
  L20, used in `main_ctx_stats()` ~L494) — **no change needed**: this issue does
  not alter the `_aggregate_skill_stats` signature, only the `_cmd_stats` call
  site. Listed for completeness. [Agent 1 finding]
- `scripts/little_loops/cli/history_context.py` — uses its **own** `args.project`
  namespace (separate CLI), not `cli/logs.py`'s; **not affected**. [Agent 1 finding]

### Similar Patterns
- `tail` already defaults `--project` to CWD (`cli/logs.py:1692`) — model the
  shared CWD-default resolver on its behavior so all subcommands agree.
- ENH-2297 (`--project` on `tail`) and ENH-2093 (project-scoped `scan-failures`)
  established the scoping principle this generalizes uniformly.

### Tests
- `scripts/tests/test_ll_logs.py` — add cases: CWD-default path (no target
  flag), `--all` still aggregates across projects, and `--host codex` probes
  `~/.codex/projects`.

_Wiring pass added by `/ll:wire-issue`:_
- ⚠ **`test_ll_logs.py` already exists** (3,437 lines; the **only** test file that
  imports from `cli/logs.py`). Treat the above as edits to an existing file, not a
  new file. [Agent 3 finding]
- **Test to UPDATE (zombie risk):** `test_sequences_project_and_all_mutually_exclusive`
  (~L692) patches `sys.argv` to a bare `["ll-logs", "sequences"]` and wraps
  `_parse_args()` in `try/except SystemExit: pass` with **no assertion**. Once
  `required=True` is dropped, `_parse_args()` returns normally instead of exiting,
  so the test **keeps passing while testing the wrong thing** and its docstring
  becomes false. Rename and re-assert the new CWD-default contract
  (`args.project is None`, `args.all is False`). [Agent 3 finding]
- **Tests that stay valid (no change):** the three `*_project_and_all_mutually_exclusive`
  tests for `stats` (~L1532), `dead-skills` (~L1873), `scan-failures` (~L2264)
  assert that passing **both** `--project` and `--all` raises `SystemExit`. The
  group stays mutually exclusive (only `required=True` drops), so these remain
  correct. [Agent 3 finding]
- **New argparse-level cases** (`TestArgumentParsing`): per-subcommand `--host`
  parsing for all six subparsers (`extract`/`sequences`/`stats`/`scan-failures`/
  `dead-skills`/`discover`); CWD-default parse-OK (`args.project is None`,
  `args.all is False`) for the five non-`discover` subcommands. [Agent 3 finding]
- **New integration cases:** bare invocation routes to CWD (not all projects);
  `--all --host codex` probes `~/.codex/projects`; `discover --host codex` uses
  `~/.codex/projects`. [Agent 3 finding]
- **Patterns to follow:** `patch("little_loops.cli.logs.Path.cwd", return_value=...)`
  (existing in `TestSequences`/`TestExtract`) for CWD isolation;
  `monkeypatch.setenv("LL_HOOK_HOST", "codex")` (`test_hook_intents.py:441`) and
  `resolve_host(env={...})` / `TestResolveHost` (`test_host_runner.py:51`) for host
  resolution; the `isolated_env` fixture (`tests/conformance/conftest.py:24`) clears
  `LL_HOST_CLI`/`LL_HOOK_HOST`. [Agent 3 finding]

### Documentation
- `docs/reference/CLI.md` — `ll-logs` subcommand flags (CWD default, `--host`,
  `--all` as opt-in).
- `.claude/CLAUDE.md` — `ll-logs` CLI Tools bullet (CWD default + host-awareness).
- `docs/reference/COMMANDS.md`, `docs/reference/API.md` — update where they
  describe the `--project`/`--all` requirement.

_Wiring pass added by `/ll:wire-issue`:_
- `commands/help.md` (~L293) — the `ll-logs` entry reads _"…from Claude project
  logs"_, a hardcoded-host phrasing; rewrite host-agnostic. (The wiring test
  `test_wiring_cli_registry.py` only asserts the literal `"ll-logs"` is present, so
  reworded copy will not break it.) [Agent 2 finding]
- `docs/reference/CLI.md` specifics: the mutual-exclusion note (~L2020) stays
  accurate but is **incomplete** — add that both flags are now optional and a bare
  invocation defaults to CWD; add a `--host {claude-code,codex,opencode,pi}` row to
  **all six** subcommand flag tables (`extract`/`sequences`/`stats`/`scan-failures`/
  `dead-skills`/`discover`); add zero-flag (CWD-default) examples. [Agent 2 finding]
- `docs/reference/API.md` specifics: five `main_logs` subcommand blurbs say
  _"requires `--project DIR` or `--all`"_ — drop "requires", describe the three-way
  resolver, add `--host`; the top `main_logs` description line says "Claude Code
  session logs" (hardcoded host). The `discover_all_projects` section needs no edit
  (signature unchanged). [Agent 2 finding]
- ⓘ **Correction:** `docs/reference/COMMANDS.md` (listed above) **needs no change** —
  it references `ll-logs` only in the `loop-suggester --from-sequences` context, not
  in any `--project`/`--all` flag description. [Agent 2 finding]
- ⓘ `config-schema.json` confirmed **no change** — `orchestration.host_cli` is
  already defined with `enum: [claude-code, codex, opencode, pi]`; no schema
  describes the `--project`/`--all` group. [Agent 2 finding]

### Configuration
- `orchestration.host_cli` in `.ll/ll-config.json` participates in host
  resolution (read-only; no schema change).

## Implementation Steps

1. Add a helper that resolves the target project list from
   `(--project | --all | default-CWD)` + `--host`.
2. Apply it across the six subcommand handlers; pass `host=` to
   `discover_all_projects`.
3. Fix help/description/docstring wording.
4. Tests: CWD-default path; `--all` still works; `--host codex` probes
   `~/.codex/projects`.
5. Docs: CLI reference + CLAUDE.md note.

> ⚠ Implementation note (see Proposed Solution → Codebase Research Findings):
> the three-way resolver (`--project` | `--all` | CWD-default) applies to **five**
> handlers; the sixth `host=` thread (`discover`, `logs.py:1933`) gets `--host`
> only, not a CWD default. The resolver MUST check `args.all` explicitly —
> today no handler does, so simply dropping `required=True` would make a bare
> invocation aggregate every project.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the
implementation beyond the core `cli/logs.py` work:_

6. Update the `ll-logs` bullet in the `scripts/little_loops/cli/__init__.py` module
   docstring (~L15) to host-agnostic wording — this is the source string that
   propagates into `.ll/ll-continue-prompt.md`.
7. Update `commands/help.md` (~L293) `ll-logs` entry: "Claude project logs" →
   host-agnostic phrasing.
8. Update `docs/reference/CLI.md`: mutual-exclusion note (~L2020), add `--host` row
   to all six flag tables, add CWD-default examples.
9. Update `docs/reference/API.md`: drop "requires `--project`/`--all`" from the five
   subcommand blurbs, add `--host`, fix the "Claude Code session logs" description.
   (Leave `docs/reference/COMMANDS.md` unchanged — confirmed no flag-level coupling.)
10. Update existing tests in `scripts/tests/test_ll_logs.py`: re-purpose the zombie
    `test_sequences_project_and_all_mutually_exclusive` (~L692) to assert CWD-default;
    add per-subcommand `--host` parse tests and CWD-default routing tests; add
    `--host codex` → `~/.codex/projects` integration tests.
11. After the change, run `ll-loop run ll-logs-telemetry-digest` to confirm the
    loop's previously-failing flag-less subcommand calls now succeed scoped to CWD.

## API/Interface

CLI surface for each affected subcommand (`extract`, `sequences`, `stats`,
`scan-failures`, `dead-skills`):

```text
# Before — one of the two is REQUIRED
ll-logs <sub> (--project DIR | --all)

# After
ll-logs <sub> [--project DIR | --all] [--host {claude-code,codex,opencode,pi}]
#   (no target flag)  -> current project (CWD)
#   --project DIR      -> that project
#   --all              -> every project under the host's session dir (opt-in)
#   --host             -> selects the session source dir;
#                         defaults via resolve_host() (LL_HOOK_HOST /
#                         orchestration.host_cli), falling back to claude-code
```

- `--project` and `--all` stay mutually exclusive, but the group becomes
  **optional** (drops `required=True`).
- `--host` is additive; omitting it preserves the prior `claude-code` default.
- Backwards compatible: existing `--project` / `--all` invocations are unchanged.

## Scope Boundaries

In scope: CWD default, `--all` as explicit opt-in, the shared `--host` flag, and
host-correct help/docstring wording for the five subcommands above.

Out of scope:
- Changing `discover_all_projects` internals beyond passing `host=` (its
  signature already supports the keyword).
- `tail` behavior (already has a `--project` CWD default via ENH-2297) beyond
  docstring-consistency wording.
- The per-project digest / whole-session corpus features themselves
  ([FEAT-2315] / [FEAT-2316]) — this is only the shared UX/privacy/host plumbing
  they assume.
- Re-targeting `scan-failures` at user-own failures ([ENH-2318], separate).
- New output formats, new subcommands, or changes to log parsing/sequencing.

## Impact

- **Priority**: P3 — UX/privacy/plumbing polish; not blocking, but derisks the
  in-flight multi-host generalization and unblocks the FEAT-2315/2316 cluster.
- **Effort**: Medium — one shared CWD/host resolver helper, five argument-group
  changes, six `host=` threads, wording fixes, tests, and docs; no new subsystems.
- **Risk**: Low — relaxing a `required=True` group to optional is backwards
  compatible (existing `--project`/`--all` invocations unchanged), and
  `discover_all_projects` already accepts `host=`.
- **Breaking Change**: No

## Relationship to existing issues (scope to the gap)

- **ENH-1945** (done) made *session-log discovery* host-aware for
  `ll-session backfill` / `session_start` / `session_log` — but it touched
  `user_messages.py` / `cli/session.py` / `hooks/session_start.py` /
  `session_log.py`, **not** `cli/logs.py`. The `ll-logs` subcommands still don't
  thread host. This issue closes that specific gap.
- **ENH-2093** (done) fixed project-scoping + noise for `scan-failures`
  specifically; this generalizes the "don't scan the whole machine by default"
  principle to all subcommands.
- **ENH-2297** (done) added `--project` to `tail`; this makes CWD the *default*
  (not just an option) and extends the pattern to the remaining subcommands.
- Part of the target-project cluster with [FEAT-2315] / [FEAT-2316]; it is the
  UX/privacy/host plumbing those features assume.

## Session Log
- `/ll:wire-issue` - 2026-06-26T22:48:53 - `5abe280f-1381-4870-967b-c1984b8aafbb.jsonl`
- `/ll:refine-issue` - 2026-06-26T22:37:41 - `0738aae2-208f-4800-b6cb-aef4cfec50d1.jsonl`
- `/ll:format-issue` - 2026-06-26T22:28:37 - `22e17d08-0b17-4cda-aa6a-412805c8861d.jsonl`
- `/ll:capture-issue` - 2026-06-26T22:05:51Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/afe96ddb-ff74-49fc-b0a9-7bd525432c1d.jsonl`

---

## Status

**Open** | Created: 2026-06-26 | Priority: P3
