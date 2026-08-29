---
id: ENH-2926
title: 'll-logs extract: report what was written instead of succeeding silently'
type: ENH
status: done
testable: true
priority: P3
discovered_date: 2026-07-29
discovered_by: scope-review
completed_at: '2026-08-29T23:18:37Z'
relates_to:
- ENH-2925
- BUG-3216
labels:
- ll-logs
- cli-consistency
parent: EPIC-1918
verify_verdict: VALID
confidence_score: 90
outcome_confidence: 96
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 25
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

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- **Correction — `extract_parser` construction**: now spans `logs.py:2166-2175` (drifted from the previously-cited `logs.py:2103-2112`). Still no `add_json_arg(extract_parser)` call — confirmed by the full current list of `add_json_arg(` call sites in this file: `logs.py:2149,2204,2218,2257,2282,2294,2328,2362` (`extract_parser` absent).
- **Correction — `docs/reference/CLI.md`**: the `## ll-logs` section now begins at line 3324 (not ~3129); the `extract` subcommand row is at line 3334; the **`extract` flags** table is at lines 3356-3362 (only `--all`/`--project DIR`/`--cmd TOOL` — no `-j/--json` row, consistent with the parser gap above); usage examples are at lines 3459-3461 (not ~3260).
- **Correction — OSError-swallow sibling citations** (Conventions in Force): the previously-cited sibling sites `logs.py:1226-1227`, `:1448-1449`, `:1763-1764` have drifted to `logs.py:1274` (`_cmd_scan_failures`), `:1511`, `:1826` respectively — same bare `except OSError: continue` idiom, no logging, no count, at every site.
- **Correction — `_cmd_scan_failures`'s zero-result block** (the cited model for the decided zero-match convention): now at `logs.py:1325-1330`, not the previously-cited `:1263-1268`.
- **New — the decided zero-match convention is contested by a third, previously-uncatalogued variant**: `_cmd_stats` (`logs.py:1420-1425`) and `_cmd_dead_skills`'s catalog-empty check (`logs.py:992-997`) test emptiness *before* branching on `args.json` at all, so `--json` degrades to a `logger.warning`/plain `print()` line rather than valid JSON on that path — `_cmd_dead_skills` contains both this variant (catalog-empty) and the fall-through-to-`print_json([])` variant (rows-empty, `:1017-1023`) in the same function. This issue's own Acceptance Criteria ("stdout is a single valid JSON document... under -j/--json") already rules this variant out for `_cmd_extract`; noted so the implementer knows `_cmd_scan_failures`'s shape, not `_cmd_stats`'s, is the one to follow.
- **New — a private (non-shared) pluralization helper already exists**: `_plural(n: int, word: str) -> str` (`scripts/little_loops/cli/issues/clusters.py:91-93`), module-private and not imported elsewhere — confirms no shared helper exists in `cli/output.py` today; a concrete existing precedent either to model inline or to promote.
- **New (Tests) — stdout assertion convention in this file**: summary-line assertions run via pytest's `capsys` against `main_logs()` (not `_cmd_*` in isolation) — e.g. `test_ll_logs.py:123-154` (plain text) and `:432-471` (`json.loads(capsys.readouterr().out)`); `logger.warning` presence/absence is asserted via `caplog.at_level(logging.WARNING, logger="little_loops.cli.logs")` (`test_ll_logs.py:259-295`).
- **New (Tests) — no existing test combines an induced `OSError` with a reported-message assertion**: the two existing unreadable-file tests in this codebase (`test_des_audit.py:77-86`, a directory disguised as a file; `test_tool_catalog.py:107-121`, `monkeypatch.setattr(Path, "read_text", ...)` raising `OSError`) both assert silent-degrade-but-succeed, never a `capsys`/`caplog` assertion on a reported message. The "unreadable-file skip is reported" acceptance criterion has no same-shape existing test to copy — it combines two previously-separate test idioms (induce-`OSError` + assert-on-output).
- **New (edge case, not covered by Root Cause/Current Behavior)**: a record with a missing/empty `sessionId` is bucketed under the empty string (`buckets[""]`, `logs.py:774-775`) and would be written as `logs/<slug>/.jsonl` — a dot-file with no stem — rather than flagged or dropped.
- **New (edge case)**: `slug = cwd_path.resolve().name` (`logs.py:758`) is just the resolved directory's basename with no collision handling — two different `cwd_path`s sharing a basename would write into the same `logs/<slug>/` output directory in the same run. Relevant to any per-project summary keyed by `slug`.

### Files to Modify
- `scripts/little_loops/cli/logs.py` — `_cmd_extract` (lines 740-796) needs summary/JSON reporting; `extract_parser` (lines 2103-2112) needs `add_json_arg(extract_parser)` added, matching the wiring used by `discover_parser`, `sequences_parser`, `stats_parser`, `dead_skills_parser`, `scan_failures_parser`, `diff_parser`, `eval_export_parser`, `loop_fleet_parser`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/logs.py:2328` — `main_logs()` dispatches to `_cmd_extract`; its call site is unaffected by an output-only change.
- `.loops/ll-logs-telemetry-digest.yaml:13-23` — the only current caller of `ll-logs extract` in the loop corpus (`refresh_corpus` state). Confirmed via direct read: its `output_contains: "REFRESHED"` gate matches the shell wrapper's own `echo "REFRESHED"`/`echo "REFRESH_FAILED"` text, not `extract`'s raw stdout — the gate depends only on `extract`'s exit code via `&&`/`||` chaining, and stderr is discarded (`2>/dev/null`). Changing what `extract` prints to stdout on success does not affect this consumer, which corrects the issue's `## Impact` claim that low risk stems from "extract currently prints nothing" — the actual invariant this loop needs preserved is exit-code semantics, not stdout silence.
- Separately (pre-existing, not introduced by this issue): that same loop state invokes `ll-logs extract --quiet` with no `--project`/`--all` target. Both are argument-surface errors and the state resolves to `REFRESH_FAILED` on every run today, independent of ENH-2926. **Split out as BUG-3216** — do not fix it here; this issue's scope stays on `_cmd_extract`'s reporting. Note the sequencing interaction: BUG-3216 optionally wires a real `--quiet` via `add_quiet_arg`, which is most meaningful *after* this issue gives `extract` output worth suppressing. Neither issue blocks the other.
- **Correction (2026-08-29 refine pass)**: the `main_logs()` dispatch call site above has drifted from `logs.py:2328` to `logs.py:2405` (`main_logs()` itself now defined at `logs.py:2372`) — confirmed via the code graph (`callers-of _cmd_extract`) plus a direct read. Behavior is otherwise unchanged: the call site remains unaffected by an output-only change.

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

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- **Correction — Signatures**: `extract_parser` construction now spans `logs.py:2166-2175` (drifted from the previously-cited `logs.py:2103-2112`); `add_json_arg(extract_parser)` is still absent — confirmed against the current full list of `add_json_arg(` call sites (`logs.py:2149,2204,2218,2257,2282,2294,2328,2362`).

### Types
- No new type is strictly required if following the `_cmd_stats`/`_cmd_dead_skills` convention (plain `list[dict]` per-project rows). If a dataclass is preferred instead (matching `_cmd_diff`'s `SessionDiff`/`to_dict()` shape), it needs fields for `project`, `slug`, `out_dir`, `sessions`, `records` per row, plus a run-level `skipped: list[str]`.

### Signatures
- `_cmd_extract(args: argparse.Namespace, logger: Logger) -> int` (`logs.py:740`) — signature is unchanged; behavior gains accumulation of per-project session/record counts and an `OSError`-skip list within the existing loop bodies (project loop `logs.py:757-793`, file-read loop `logs.py:761-777`).
- `add_json_arg(extract_parser)` — not currently called at `logs.py:2103-2112`; every other dual-mode `_cmd_*` parser in this file calls it (`cli_args.py:324-331`).
- `print_json(data: Any) -> None` (`cli/output.py:227`) — existing helper to reuse for the `--json` branch.

### Call Path
`main_logs` (`logs.py:2328`) -> `_cmd_extract` (`logs.py:740`) -> per-project loop (`logs.py:757`) -> `get_project_folder` (`user_messages.py:744,753`) / `discover_all_projects` (`logs.py:750`) -> per-file read loop (`open(jsonl_file)`, `logs.py:763-777`) -> `_is_ll_relevant` (`logs.py:773`) -> optional `_cmd_matches` filter (`logs.py:782`) -> per-session write (`logs.py:789-793`) -> `generate_index` (`logs.py:795`, itself reading files at `logs.py:700-715` with the same silent `except OSError: continue` pattern) -> `return 0`.

**Correction (2026-08-29 refine pass)**: `main_logs`'s dispatch call to `_cmd_extract` has drifted to `logs.py:2405` (`main_logs` def at `logs.py:2372`); `generate_index`'s own `except OSError: continue` is precisely at `logs.py:714-715` (def spans `logs.py:686-737`). Every other hop in the chain above was re-confirmed unchanged: `get_project_folder` calls at `user_messages.py:744,753`, `discover_all_projects` at `logs.py:750`, the file-read loop opening at `logs.py:764` with its `OSError` swallow at `logs.py:776-777`, `_is_ll_relevant` at `logs.py:773`, `_cmd_matches` at `logs.py:782`, and the per-session write loop at `logs.py:787-793`.

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

- [x] `ll-logs extract --project DIR` and `--all` print a per-project +
      totals summary on success.
- [x] `-j/--json` emits the same data structurally (per-project rows, totals,
      `skipped` paths).
- [x] Under `-j/--json`, stdout is a single valid JSON document and nothing
      else — the text summary is fully suppressed and no `logger` output is
      interleaved into stdout. (`json.loads(stdout)` succeeds. This is the
      actual requirement behind the "scriptable extract-then-analyze pipeline"
      motivation; warnings go to stderr.)
- [x] The text summary is written to stdout, not stderr.
- [x] Unreadable JSONL files are reported, not silently dropped.
- [x] A `--cmd` filter matching zero records says so — in both text and JSON
      mode (an empty rows array alone does not satisfy this).
- [x] Under `--all`, an unresolvable project folder emits a warning.
- [x] Exit code remains 0 for a successful-but-empty extraction, and for a run
      with skipped unreadable files. This is a reporting change, not a gating
      one — the loop corpus depends on `extract`'s exit-code semantics (see
      Integration Map).
- [x] Tests cover: multi-project summary, JSON shape, zero-match filter,
      an unreadable-file skip, and exit-code-0-on-empty.
- [x] `python -m pytest scripts/tests/` exits 0 modulo 4 pre-existing failures
      unrelated to this change (`test_packaging_duplicate_files`,
      `test_issue_parser::TestBug3293...`, `test_subprocess_utils::...guillatine_prompt`,
      `test_verify_evidence::TestRepoGate`) — none reference `logs.py`,
      `_cmd_extract`, or `extract_parser`; verified untouched by this diff.
      `scripts/tests/test_ll_logs.py` (23 `TestExtract` cases) passes clean.

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
- `/ll:manage-issue` - 2026-08-29T23:17:45 - `3877ebdc-d9d3-4449-9bcf-1a7f4ef3ce26.jsonl`
- `/ll:ready-issue` - 2026-08-29T23:07:06 - `ed9b2f61-6325-4a0c-aa2f-badcd208e1b6.jsonl`
- `/ll:confidence-check` - 2026-08-29T23:01:50 - `5eb49b5f-91aa-4f15-a849-be73909ec012.jsonl`
- `/ll:refine-issue` - 2026-08-29T22:57:50 - `aa00f654-f91b-4b9a-bd21-42a5197c668d.jsonl`
- `/ll:confidence-check` - 2026-08-16T21:37:50 - `1dcb449c-4f4b-4f5f-adf6-409fd8c076d0.jsonl`
- `/ll:refine-issue` - 2026-08-16T21:02:31 - `a6423fbb-ab55-421d-8910-104e95cc23b4.jsonl`
- `/ll:verify-issues` - 2026-08-16T16:40:22 - `688cfc38-322a-447f-94a0-315f2c2aee33.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:04:57 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`

---

## Status

**Open** | Created: 2026-07-29 | Priority: P3
