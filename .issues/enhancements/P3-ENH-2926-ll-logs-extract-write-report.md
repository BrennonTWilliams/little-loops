---
id: ENH-2926
title: 'll-logs extract: report what was written instead of succeeding silently'
type: ENH
status: open
testable: true
priority: P3
discovered_date: 2026-07-29
discovered_by: scope-review
relates_to:
- ENH-2925
- BUG-3216
labels:
- ll-logs
- cli-consistency
parent: EPIC-1918
verify_verdict: VALID
confidence_score: 98
outcome_confidence: 90
score_complexity: 20
score_test_coverage: 23
score_ambiguity: 22
score_change_surface: 25
---

# ENH-2926: `ll-logs extract` — report what was written instead of succeeding silently

## Summary

`_cmd_extract` (`scripts/little_loops/cli/logs.py:740`) walks every discovered
project's JSONL, buckets ll-relevant records by session, writes one file per
session under `logs/<slug>/`, regenerates `logs/index.md`, and returns 0 —
printing **nothing** on the success path. Only errors reach stdout/stderr
(a missing project folder, via `logger.error`).

A user cannot tell from the output whether extract wrote 3 files or 300, which
projects it covered, whether a `--cmd` filter matched anything at all, or which
JSONL files it skipped on `OSError` (silently swallowed at logs.py:776).

## Current Behavior

```
$ ll-logs extract --all
$                      # no output; N files appeared under logs/
$ ll-logs extract --all --cmd ll-nonexistent
$                      # no output; nothing written, indistinguishable from success
```

Failure modes hidden today:

- Per-file `OSError` is caught and `continue`d with no diagnostic — an
  unreadable JSONL is silently absent from the extraction.
- A `--cmd` filter that matches zero records produces the same output (none)
  as a filter that matches everything.
- Projects whose folder resolves to `None` under `--all` are skipped without
  the `logger.error` the `--project` path emits.

## Expected Behavior

`extract` prints a summary of what it did, and supports `-j/--json` for the
same payload — bringing it in line with the rest of `ll-logs`, where every
other subcommand emits a structured result.

Text form:

```
$ ll-logs extract --all
little-loops       12 sessions, 3,481 records -> logs/little-loops/
other-project       2 sessions,   204 records -> logs/other-project/
2 projects, 14 sessions, 3,685 records written; 1 file unreadable (skipped)
```

JSON form: one object per project (`project`, `slug`, `out_dir`, `sessions`,
`records`), plus totals and a `skipped` list of unreadable paths.

When a `--cmd` filter matches nothing, say so explicitly rather than exiting 0
silently.

## Motivation

Extract is the entry point for every downstream `ll-logs` workflow
(`sequences`, `stats`, `diff`, `eval-export` all consume what it produces), so
a silent no-op there surfaces later as a confusing empty analysis rather than
an obvious extraction problem. It is also the only `ll-logs` subcommand with no
machine-readable output, which blocks scripting an extract-then-analyze
pipeline.

Split out of ENH-2925's parity sweep because this is a new output surface, not
`add_json_arg` wiring — there is currently no report to serialize.

## Proposed Solution

In `_cmd_extract`:

1. Accumulate a per-project record as the loop runs: resolved project path,
   slug, output dir, session count, record count.
2. Collect `OSError` paths into a `skipped` list instead of discarding them;
   report the count in text mode and the paths in JSON mode.
3. Emit a `logger.warning` (not silent skip) when `--all` encounters a project
   whose session folder does not resolve.
4. Distinguish "filter matched nothing" from "nothing to do" in the summary
   line.
5. Add `add_json_arg(extract_parser)` and a `print_json(...)` branch, matching
   the file's existing convention.

Keep exit code 0 for a successful-but-empty extraction — this is a reporting
change, not a gating one.

## Scope Boundaries

**In scope:** `_cmd_extract`'s success-path reporting, its swallowed `OSError`
diagnostics, and one `add_json_arg(extract_parser)` line.

**Out of scope:** what records `_is_ll_relevant` selects or how sessions are
bucketed (extraction logic is unchanged — only its reporting); `logs/index.md`
generation via `generate_index`; `--project`/`--all` resolution semantics
(ENH-2317); the shared target/window parser extraction and the `--since`/
`--sort`/`--limit` additions (ENH-2925). Exit codes stay as they are — this is
reporting, not gating.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-16 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/cli/logs.py` — `_cmd_extract` (lines 740-796) needs summary/JSON reporting; `extract_parser` (lines 2103-2112) needs `add_json_arg(extract_parser)` added, matching the wiring used by `discover_parser`, `sequences_parser`, `stats_parser`, `dead_skills_parser`, `scan_failures_parser`, `diff_parser`, `eval_export_parser`, `loop_fleet_parser`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/logs.py:2328` — `main_logs()` dispatches to `_cmd_extract`; its call site is unaffected by an output-only change.
- `.loops/ll-logs-telemetry-digest.yaml:13-23` — the only current caller of `ll-logs extract` in the loop corpus (`refresh_corpus` state). Confirmed via direct read: its `output_contains: "REFRESHED"` gate matches the shell wrapper's own `echo "REFRESHED"`/`echo "REFRESH_FAILED"` text, not `extract`'s raw stdout — the gate depends only on `extract`'s exit code via `&&`/`||` chaining, and stderr is discarded (`2>/dev/null`). Changing what `extract` prints to stdout on success does not affect this consumer, which corrects the issue's `## Impact` claim that low risk stems from "extract currently prints nothing" — the actual invariant this loop needs preserved is exit-code semantics, not stdout silence.
- Separately (pre-existing, not introduced by this issue): that same loop state invokes `ll-logs extract --quiet` with no `--project`/`--all` target. Both are argument-surface errors and the state resolves to `REFRESH_FAILED` on every run today, independent of ENH-2926. **Split out as BUG-3216** — do not fix it here; this issue's scope stays on `_cmd_extract`'s reporting. Note the sequencing interaction: BUG-3216 optionally wires a real `--quiet` via `add_quiet_arg`, which is most meaningful *after* this issue gives `extract` output worth suppressing. Neither issue blocks the other.

### Conventions in Force
- Dual-mode `_cmd_*` functions build one plain `list[dict]`/dataclass once, then branch a single time on `args.json`: `print_json(...)` vs. text/`table()` built from the same structure — evidence: `_cmd_stats` (`logs.py:1336-1396`), `_cmd_sequences` (`logs.py:630-683`), `_cmd_dead_skills` (`logs.py:972-1028`), `_cmd_diff` (`logs.py:1519-1576`).
- The `-j/--json` flag is always wired through the shared `add_json_arg(parser)` helper (`cli_args.py:324-331`), never hand-rolled — evidence: `discover`, `sequences`, `stats`, `dead-skills`, `scan-failures`, `diff`, `eval-export` parsers all call it; `extract_parser` (`logs.py:2103-2112`) does not yet.
- Zero-match handling is a contested convention, not a single rule: `_cmd_sequences`/`_cmd_dead_skills` check `args.json` first and let an empty result fall through to `print_json([])`, printing a text sentence only in the non-JSON branch; `_cmd_scan_failures` (`logs.py:1263-1268`) instead branches explicitly in both modes (`if not args.json: print(...)` / `else: print_json([])`). **Decided: follow `_cmd_scan_failures`.** It is the only one of the two that satisfies this issue's "a `--cmd` filter matching zero records says so" criterion in JSON mode — the fall-through-to-`print_json([])` idiom emits a bare empty array, which is exactly the ambiguity between "filter matched nothing" and "nothing to do" that this issue exists to remove. The JSON payload must carry the distinction structurally (e.g. a zero-match indicator alongside the empty rows), not only in the text branch.
- Aggregate + per-item summary text (closest existing shape to what this issue's `## Expected Behavior` mocks up): `_print_sync_result` (`cli/sync.py:228-259`) prints a `"## SUMMARY"` block of right-aligned `"- Label: count"` lines, followed by per-item detail sections only when non-empty.
- Swallow-and-continue `except OSError: continue` on a per-file loop is `logs.py`'s dominant existing idiom, appearing silently at `logs.py:125-126`, `:158-159`, `:714-715` (`generate_index`), `:776-777` (the site this issue targets), `:1226-1227`, `:1448-1449`, `:1763-1764` — there is no existing in-file example of this being converted to a reported skip list; `migrate_status.py:73-105` and `little_loops/sync.py:49-51`/`cli/sync.py:250-258` are the two out-of-file examples, and they disagree on whether the skip list gets folded into the `--json` payload (`sync.py`'s `to_dict()` includes it) or only surfaced via stderr text outside the JSON body (`_cmd_eval_export`, `logs.py:1783-1821`, the closest same-file sibling). **Decided: follow `sync.py`'s `to_dict()` — `skipped` goes inside the JSON payload.** This issue's Expected Behavior already commits to it ("plus totals and a `skipped` list of unreadable paths"), and the stated motivation is scripting an extract-then-analyze pipeline: a consumer that has to parse stderr to learn its input was incomplete is not scriptable in the sense this issue is asking for.
- No shared pluralization helper exists in `cli/output.py`; every call site inlines `f"{n} <noun>{'s' if n != 1 else ''}"` ad hoc (`loop/next_loop.py:190`, `issues/impact_effort.py:237`, `gitignore.py:91`).

### Tests
- `scripts/tests/test_ll_logs.py` — existing `TestExtract` coverage (from `test_extract_project_creates_output_file` around line 1533) asserts on side effects (`logs/index.md` contents, return codes), not stdout — no current test asserts on printed summary output, since none exists today.
- Dual-mode JSON test convention elsewhere in the same file: a shape-locking test asserting exact `set(row.keys())` equality (`test_stats_json_keys:2154`, `test_dead_skills_json_output_shape:2627-2647`, `test_diff_json_output_schema:3685-3703`), paired with a cheap flag-parses smoke test (`test_stats_json_flag`, `test_dead_skills_json_flag`), and at least one `-j` short-flag variant test (`test_discover_json_short_flag:473`, `test_eval_export_json_short_flag:3869`).

### Documentation
- `docs/reference/CLI.md` (`## ll-logs` section beginning ~line 3129; `extract` subcommand ~line 3139, flags ~3161, examples ~3260) documents extract's current flags/output and will need its output-shape description updated.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-16 — based on codebase analysis:_

### Types
- No new type is strictly required if following the `_cmd_stats`/`_cmd_dead_skills` convention (plain `list[dict]` per-project rows). If a dataclass is preferred instead (matching `_cmd_diff`'s `SessionDiff`/`to_dict()` shape), it needs fields for `project`, `slug`, `out_dir`, `sessions`, `records` per row, plus a run-level `skipped: list[str]`.

### Signatures
- `_cmd_extract(args: argparse.Namespace, logger: Logger) -> int` (`logs.py:740`) — signature is unchanged; behavior gains accumulation of per-project session/record counts and an `OSError`-skip list within the existing loop bodies (project loop `logs.py:757-793`, file-read loop `logs.py:761-777`).
- `add_json_arg(extract_parser)` — not currently called at `logs.py:2103-2112`; every other dual-mode `_cmd_*` parser in this file calls it (`cli_args.py:324-331`).
- `print_json(data: Any) -> None` (`cli/output.py:227`) — existing helper to reuse for the `--json` branch.

### Call Path
`main_logs` (`logs.py:2328`) -> `_cmd_extract` (`logs.py:740`) -> per-project loop (`logs.py:757`) -> `get_project_folder` (`user_messages.py:744,753`) / `discover_all_projects` (`logs.py:750`) -> per-file read loop (`open(jsonl_file)`, `logs.py:763-777`) -> `_is_ll_relevant` (`logs.py:773`) -> optional `_cmd_matches` filter (`logs.py:782`) -> per-session write (`logs.py:789-793`) -> `generate_index` (`logs.py:795`, itself reading files at `logs.py:700-715` with the same silent `except OSError: continue` pattern) -> `return 0`.

### Decision Rules
- Zero-match `--cmd` filter: fires when `--cmd` is supplied AND a project's final `buckets` dict is empty after filtering (`logs.py:779-785`). No numeric threshold; boolean per-project (or per-run, if aggregated) condition. Reported via the `_cmd_scan_failures` explicit-both-modes idiom — decided under Conventions in Force above; the distinction must be visible in the `--json` payload, not only in text.
- Unresolvable `--all` project folder: fires when `get_project_folder(decoded_path)` returns `None` inside the `--all` branch's `for decoded_path in discover_all_projects(logger)` loop (`logs.py:749-755`); today this is a silent skip via the `if folder is not None:` guard with no counterpart precedent elsewhere in `logs.py`'s `--all` handling (`_cmd_stats` never calls `get_project_folder`). No threshold — a `logger.warning` per unresolved project is the ask, with no existing same-file idiom to model.

## Impact

- **Priority**: P3 — diagnosability improvement; no workflow is blocked today.
- **Effort**: Small — one function plus one argparse line.
- **Risk**: Low, but not for the reason originally stated. The earlier
  rationale ("`extract` prints nothing, so any script parsing its stdout parses
  the empty string") was superseded by the Integration Map research: the sole
  corpus consumer, `.loops/ll-logs-telemetry-digest.yaml`, gates on its own
  `echo "REFRESHED"` text and discards stderr, so it depends on `extract`'s
  **exit code**, not on its stdout being empty. The invariant to preserve is
  therefore exit-code semantics (pinned as an AC above), and added stdout is
  free. That consumer is separately broken for unrelated reasons (BUG-3216),
  so it will not exercise this change until BUG-3216 lands.
- **Breaking Change**: No

## Acceptance Criteria

- [ ] `ll-logs extract --project DIR` and `--all` print a per-project +
      totals summary on success.
- [ ] `-j/--json` emits the same data structurally (per-project rows, totals,
      `skipped` paths).
- [ ] Under `-j/--json`, stdout is a single valid JSON document and nothing
      else — the text summary is fully suppressed and no `logger` output is
      interleaved into stdout. (`json.loads(stdout)` succeeds. This is the
      actual requirement behind the "scriptable extract-then-analyze pipeline"
      motivation; warnings go to stderr.)
- [ ] The text summary is written to stdout, not stderr.
- [ ] Unreadable JSONL files are reported, not silently dropped.
- [ ] A `--cmd` filter matching zero records says so — in both text and JSON
      mode (an empty rows array alone does not satisfy this).
- [ ] Under `--all`, an unresolvable project folder emits a warning.
- [ ] Exit code remains 0 for a successful-but-empty extraction, and for a run
      with skipped unreadable files. This is a reporting change, not a gating
      one — the loop corpus depends on `extract`'s exit-code semantics (see
      Integration Map).
- [ ] Tests cover: multi-project summary, JSON shape, zero-match filter,
      an unreadable-file skip, and exit-code-0-on-empty.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Related Key Documentation

- `.claude/CLAUDE.md` — `ll-logs` and its `extract` subcommand are documented in the § CLI Tools catalog; this issue changes `extract`'s reported output shape (text summary + `-j/--json`), which that catalog entry should continue to match.

## Verification Notes

**2026-08-12** (`/ll:verify-issues`): `_cmd_extract` has shifted from
`logs.py:666` to `logs.py:698`, and the swallowed `OSError` from `:702-703`
to `:734`; both citations updated. `blocked_by: ENH-2925` is stale — ENH-2925
shipped (`done`, completed 2026-07-31) — so that blocker was cleared; the
issue is unblocked and its core ask is unchanged.

- 2026-08-16: Core ask (extract prints nothing on success, `OSError` silently swallowed, no `--json`) still accurate and unimplemented; `_cmd_extract` has drifted further to `logs.py:740` and the swallowed `OSError` to `logs.py:776` — both citations corrected above. Verdict at the time: OUTDATED (citations stale, ask intact).

- 2026-08-16 (pre-implementation review): citations re-confirmed against `logs.py:740-796` and `logs.py:2103-2112`. Frontmatter `verify_verdict` corrected `NON_VALID` -> `VALID` — it had never been updated after the citation refresh above, and the issue's core claims all hold. The two conventions the refine pass left open (zero-match reporting style; `skipped` in the JSON body vs. stderr) are now decided in place. The `--quiet` observation in the Integration Map was split out as BUG-3216.

## Session Log
- `/ll:confidence-check` - 2026-08-16T21:37:50 - `1dcb449c-4f4b-4f5f-adf6-409fd8c076d0.jsonl`
- `/ll:refine-issue` - 2026-08-16T21:02:31 - `a6423fbb-ab55-421d-8910-104e95cc23b4.jsonl`
- `/ll:verify-issues` - 2026-08-16T16:40:22 - `688cfc38-322a-447f-94a0-315f2c2aee33.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:04:57 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`

---

## Status

**Open** | Created: 2026-07-29 | Priority: P3
