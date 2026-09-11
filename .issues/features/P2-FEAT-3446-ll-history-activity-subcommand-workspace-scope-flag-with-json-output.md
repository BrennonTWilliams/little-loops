---
id: FEAT-3446
type: FEAT
title: 'll-history activity subcommand: --workspace scope flag with JSON output'
priority: P2
status: open
blocked_by: [FEAT-3445]
discovered_by: ll-issues-create
discovered_date: '2026-09-10'
captured_at: '2026-09-10T23:53:23Z'
---

# FEAT-3446: ll-history activity subcommand: --workspace scope flag with JSON output

## Summary

New `ll-history activity` subcommand exposing the workspace activity reader (FEAT-3445): per-repo and union activity counts over a `--since` window, with `--workspace` following the established scope-flag convention and `--format json` as the primary machine-readable output.

## Context

Companion CLI surface for FEAT-3445 (create that first; this issue is blocked by it). Surfaced by the same little-loops-hermes design review: the `ll_briefing` / `ll_portfolio` consumer needs one command returning per-repo AND union activity counts, machine-readable.

**Premise correction:** the review task claimed "there is NO JSON workspace formatter" — false. `format_agent_quality_json` (agent_quality.py:872-878) already serializes `AggregationResult` via duck-typed `to_dict()`; only text/markdown needed workspace variants. So there is no quality-side JSON gap to fix; this issue's JSON formatter is new code for the new result type only.

## Current Behavior

`ll-history` has no `activity` subcommand. Subcommands today: `summary`, `analyze`, `rework`, `quality`, `sessions`, `collisions`, `root`, `export` (+ `gendocs`). Only `quality` is workspace-scoped (`--workspace` via `nargs="?"`, history.py:315-321), and its four formatters already include JSON (`format_agent_quality_json`, agent_quality.py:872) — there is no quality-side JSON gap. A consumer wanting cross-repo activity counts must shell out per project (`ll-loop list --running --json`, `ll-issues list --json`) because the FEAT-3445 reader has no CLI surface yet.

## Expected Behavior

`ll-history activity [--workspace[=MANIFEST]] [--since ISO_DATE] [--until ISO_DATE] [--format text|json|markdown|yaml]` prints per-repo and union activity counts from FEAT-3445's reader. Bare `--workspace` discovers `ll-workspace.yaml`; zero discovered members falls back to a single-repo result; the scope flag never changes which formatters run; JSON is the machine contract with `null` counts for non-ok members.

## Motivation

- The scope-flag convention ("a scope flag changes WHAT is collected, never WHICH formatter runs") is established by `quality --workspace` (history.py:315-321); activity is the second consumer and should not invent a new convention.
- `ll-history summary` already owns `--since`/`--until` as ISO dates; a second, different window syntax on the same CLI would be churn.

## Proposed Solution

```
ll-history activity [--workspace[=MANIFEST]] [--since ISO_DATE] [--until ISO_DATE]
                    [--format text|json|markdown|yaml]
```

**Flag semantics:**
- `--workspace` — `nargs="?"` exactly like quality's (history.py:315-321): bare flag discovers `ll-workspace.yaml` from the project root outward; a value is an explicit manifest path. Manifest resolution errors print to stderr and exit 1 (mirror history.py:556-560).
- **Zero members → single-repo fallback (decision, resolved: yes):** when `--workspace` discovers no members, report the current repo as a one-member result, mirroring quality's fallback (history.py:562-573). Consistency beats failing empty.
- `--since`/`--until` — ISO dates via `date.fromisoformat`, same convention as `summary`; both optional, default unbounded. `--until` is included for symmetry with `summary` even though the immediate consumer only needs `--since`.
- `--format` — `choices=["text", "json", "markdown", "yaml"]`, default `text`.

**JSON output shape** (exact contract):

```json
{
  "since": "2026-09-03",
  "until": null,
  "per_repo": {
    "little-loops (source)": {
      "status": "ok",
      "instrumented": true,
      "reason": null,
      "loops_run": 12,
      "loops_completed": 10,
      "issues_completed": 4,
      "issues_deferred": 1
    },
    "other-repo (consumer)": {
      "status": "db_missing",
      "instrumented": false,
      "reason": "history.db not found at ...",
      "loops_run": null,
      "loops_completed": null,
      "issues_completed": null,
      "issues_deferred": null
    }
  },
  "totals": {
    "members": 2,
    "instrumented_members": 1,
    "loops_run": 12,
    "loops_completed": 10,
    "issues_completed": 4,
    "issues_deferred": 1
  }
}
```

Non-ok members serialize `null` counts (never `0`) so absence stays distinguishable from zero. `per_repo` keys use quality's `"{repo_path.name} ({role})"` label.

**Formatters:** `format_workspace_activity_json` / `_yaml` / `_text` / `_markdown` live beside the result type or in the CLI module following the quality formatter placement; JSON/YAML go through `to_dict()` duck-typing exactly as quality's do.

**Docs:** `docs/reference/CLI.md` gains the subcommand row; `ll-history --help` epilog examples updated.

## Program Design

### Types

- Result types come verbatim from FEAT-3445 (`WorkspaceActivityResult`, serialized via its `to_dict()`); the CLI defines none of its own.
- Formatter set: `format_workspace_activity_json` / `_yaml` / `_text` / `_markdown`, one per `--format` choice.

### Signatures

- `format_workspace_activity_json(result: WorkspaceActivityResult) -> str` (and `_yaml`/`_text`/`_markdown` siblings) — JSON/YAML serialize the duck-typed `to_dict()` exactly as `format_agent_quality_json` (agent_quality.py:872) does; text/markdown render `per_repo` + `totals` keyed by quality's `"{repo_path.name} ({role})"` labels.

### Call Path

`main_history` (cli/history.py:37) [new `activity` dispatch arm alongside the `quality` arm at history.py:523] -> `discover_workspace_members` (workspace.py:163; manifest errors → stderr + exit 1, zero members → single-repo fallback) -> `aggregate_workspace_activity` [FEAT-3445] -> `format_workspace_activity_json` (or sibling selected by `--format`).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/history.py` — new `activity` subparser + dispatch arm; `--help` epilog examples updated.
- Formatter functions land beside the result type (FEAT-3445's `issue_history/workspace_activity.py`) or in the CLI module, following quality's formatter placement.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_history/workspace_activity.py` [FEAT-3445] — the reader + result types this subcommand exposes.
- hermes `ll_briefing` / `ll_portfolio` — external consumer of the JSON contract (out of repo).

### Similar Patterns
- `quality` subcommand (parser at history.py:272, dispatch at history.py:523, workspace resolution + fallback at history.py:552-573) — the scope-flag convention, manifest-error path, and zero-member fallback to mirror.
- `format_agent_quality_text/markdown/json/yaml` (agent_quality.py:636/743/872/881) — the four-formatter duck-typing pattern.

### Tests
- `scripts/tests/test_cli_history.py` — CLI integration tests: multi-member workspace fixture, db_missing member, single-repo fallback, invalid `--since` error path, exit 0 with `totals: null`.
- Golden-shape JSON test (AC 1/7): exact key order + `null`-count contract.

### Documentation
- `docs/reference/CLI.md` — `ll-history activity` subcommand row.
- `ll-history --help` epilog — example invocation.

### Configuration
- N/A — flags only; manifest discovery reuses `ll-workspace.yaml` conventions unchanged.

## Implementation Steps

1. Wire the subparser in `cli/history.py` following the `quality` handler's structure (history.py:552-590).
2. Add formatter functions; JSON first (it's the contract), then text/markdown.
3. Golden-shape JSON test; CLI integration tests per AC 2/3/5.
4. Update `docs/reference/CLI.md` + epilog examples.

## Impact

- Purely additive CLI surface plus docs; depends on FEAT-3445's reader.
- The FSM-signals limitation documented in FEAT-3445 carries into the CLI docs (`activity` cannot report stalls/cycles/rate-limits — webhook-only).

## Use Case

Hermes sync runs `ll-history activity --workspace --since 2026-09-03 --format json` once per sync instead of N subprocess spawns + N direct sqlite connections; the JSON contract above is consumed verbatim by `ll_briefing` / `ll_portfolio`.

## Acceptance Criteria

1. `ll-history activity --workspace --since <ISO> --format json` emits the exact shape above (stable key order, `null` counts for non-ok members).
2. Bare `--workspace`, `--workspace <path>`, and absent flag (single-repo result) all work; a declared-but-missing manifest exits 1 with the path on stderr.
3. `--since`/`--until` accept ISO dates; invalid input exits non-zero with a clear error (match `summary`'s error path).
4. All four `--format` values render; scope flag never changes which formatters are available.
5. Exit 0 with `totals: null` when no member is `ok`.
6. `docs/reference/CLI.md` and the `--help` epilog document the subcommand.
7. Tests cover: multi-member workspace fixture, db_missing member, single-repo fallback, JSON shape golden test.

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/reference/API.md | Module reference for the reader/formatter placement this CLI exposes |
| guidelines | .claude/CLAUDE.md | Testing & CI policy — new CLI tests belong in `python -m pytest scripts/tests/` |

## Status

**Open** | Created: 2026-09-10 | Priority: P2


## Session Log
- `/ll:format-issue` - 2026-09-10T23:59:04 - `977177b4-c924-4eb0-8524-717b55725bed.jsonl`
- `/ll:capture-issue` - 2026-09-10T23:53:44 - `98b64441-1d76-4822-ab69-c295348ddfd6.jsonl`
