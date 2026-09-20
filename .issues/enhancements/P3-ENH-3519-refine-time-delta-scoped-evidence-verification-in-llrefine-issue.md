---
id: ENH-3519
type: ENH
title: Refine-time delta-scoped evidence verification in /ll:refine-issue
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-19'
captured_at: '2026-09-19T23:24:10Z'
labels:
- enhancement
- verify-evidence
- issue-refinement
relates_to:
- ENH-3283
- BUG-3282
- BUG-3484
- ENH-3518
parent: ENH-3515
---

# ENH-3519: Refine-time delta-scoped evidence verification in /ll:refine-issue

## Summary

`/ll:refine-issue` authors new quoted evidence with no verification, so a fabricated or misattributed quote only surfaces minutes later in the repo-wide pytest gate. Verify at refine time, scoped to the quotes this pass added. Split out of ENH-3515.

## Current Behavior

Only `/ll:capture-issue` verifies quoted spans before writing (ENH-3283). `/ll:refine-issue` authors new quoted evidence (its Codebase Research Findings, plus Root Cause / Current Behavior fills) with no check. `/ll:verify-issues` runs the CLI (check B7), but only when invoked separately. Observed 2026-09-19: BUG-3484's Root Cause quoted two pytest flags as one joined string while `scripts/pyproject.toml` lists them on separate addopts lines; it surfaced as the single failure in an unrelated full-suite run.

## Expected Behavior

A fabricated or misattributed quote is reported next to the refine edit that introduced it, and repaired before the command completes. Pre-existing (grandfathered) findings in the same file are neither reported as new nor touched.

## Motivation

Late feedback is the defect: the error is made at write time and paid for in an unrelated 4-minute run, possibly by a different agent or session. Automation (ll-auto / refine loops) runs refine-issue, so this is also the write-time coverage for automation.

## Proposed Solution

File mode (`ll-verify-evidence FILE`) is a whole-file scan with **no baseline**, and ~400 grandfathered spans exist, so a naive post-write check on an older issue would report quotes refine did not write. The check must be a before/after delta.

**Delta lives in code, not in command prose (decided — reverses ENH-3515's "comparison belongs to the command").** `commands/refine-issue.md` allows only `Read`, `Glob`, `Edit(.issues/**)`, `Task`, and `Bash(git:*, ll-issues:*, ll-history-context:*, ll-code:*)` — no `Write`, no python/jq, so the command can neither persist a snapshot nor compute an occurrence-count diff deterministically, and a prose-described comparison cannot be validated with representative payloads. Add two flags to `ll-verify-evidence` file mode:

- `--save-snapshot PATH` — atomically write a versioned snapshot envelope containing findings and scan identity to `PATH` (the CLI does the write; no extra tool permission). Publish a snapshot only after a successful scan, including exit 1 with valid findings; never publish an empty-success snapshot on an execution failure.
- `--delta-from PATH` — scan, then compare occurrence counts keyed by `(normalized_span, artifact)`, excluding line numbers, against the snapshot. Normalize span whitespace only (collapse runs of whitespace to one space and trim); preserve case, punctuation, and the original per-occurrence attribution spelling. Keep raw span text for display. Report positive count differences as `new_findings` groups, each with `added_count` and all current candidate occurrences (raw text, section, and line), plus `preexisting_count` for the matched occurrence counts. This is a **net-count delta**, not edit provenance: an equal-count removal/reinsertion of identical evidence cancels. A positive count does not identify which duplicate was newly authored; candidate locations are not automatic repair instructions. Exit 0 = no new findings, 1 = new findings, exit 2 = snapshot/input/compatibility or scan-execution failure (**verification incomplete**, never clean).

**Per-occurrence attribution:** fix `scan_file` so each candidate retains its original artifact reference through grouping by resolved path and normalized text. The current resolved-path-to-reference map retains only the last spelling, so a later path citation can relabel an earlier issue-ID citation to the same artifact. A focused reproduction confirmed this behavior. Add a regression in which both spellings resolve to one file; adding the alias must not change untouched findings' keys. This metadata correction does not change matching rules or corpus-baseline semantics.

**Repair ownership:** counts establish detection, not ownership. The refinement command must retain enough information about its own edits to identify an added occurrence before correcting/removing it. Report ambiguous duplicates as unresolved, preserving earlier content. Test insertion both before and after an existing duplicate. Separate snapshot filenames do not isolate concurrent edits to the same issue: serialize same-issue refinement or detect overlapping edits and stop automatic repair with an explicit conflict/incomplete status. Never repair another invocation's additions; test overlapping passes on the same file.

**Strict scan completion:** snapshot/delta modes must propagate execution failures from issue reads, tracked-index enumeration, and required history/blob operations instead of inheriting legacy empty-result fallbacks. Input preflight alone is insufficient because a later read can fail. Distinguish legitimate absent artifacts under existing matching rules from failed infrastructure operations. A failed before-scan publishes no new valid snapshot; a failed after-scan returns exit 2, retains known findings in the report, and never claims a clean delta. Inject these failures in both phases. Keep strict failure behavior scoped to the new modes so legacy callers retain their contracts.

**Snapshot contract:** both flags require exactly one existing, readable issue file. They are mutually exclusive and incompatible with `--all`, `--update-baseline`, and `--added-only`. Reject missing/unreadable inputs rather than letting a skipped scan count as clean. The snapshot envelope records a schema version, canonical project root and issue path, verifier compatibility version, and effective scan options (including `max_revisions`). Validate the envelope and finding field types before comparison; reject unsupported versions, wrong project/file identity, and incompatible options with exit 2. Issue-body edits between scans are expected and must not invalidate identity. Reject a snapshot destination that aliases the issue file; write failures must be explicit and leave no partial snapshot usable as a baseline.

**Invocation isolation:** the refinement command supplies a fresh UUID-based snapshot path under its run/scratch directory for each invocation, including concurrent passes on the same issue. Never reuse a fixed issue-ID-only path or fall back to a snapshot from an earlier run. Retain that invocation's original snapshot across all repair checks; do not overwrite it with a post-edit scan. A failed creation marks verification incomplete even if another snapshot file exists.

This is a diff between two scans of one file, not a corpus baseline: `--all`/baseline behavior is untouched.

Command changes (`commands/refine-issue.md`):
- Add `Bash(ll-verify-evidence:*)` to `allowed-tools`.
- **Snapshot** before the first body mutation — it must precede Step 5's `ll-issues fold-findings` writes, not merely Step 6's "Update Issue File". Retain the original snapshot throughout the pass.
- **Final check** with `--delta-from` after the last body-changing gate (after Step 6.7).
- **On a new finding**: reuse capture-issue's on-miss contract (ENH-3283): re-read the artifact and correct the quote, or describe the evidence in prose. A reviewed genuine counter-example may use `<!-- ll-evidence-ok: reason -->`; never suppress merely to clear the check. Allow one correction pass and recheck. If findings remain and this pass's ownership of the occurrence is established, remove the newly introduced quote or convert it to accurate prose, then perform one final check. If ownership is ambiguous or conflicting edits are detected, preserve the content and report unresolved/incomplete instead of attempting a destructive repair. Do not retry indefinitely or declare success with unresolved findings.
- **Preservation and modes**: explicitly allow correction/removal of this pass's additions in additive-only / `--gap-analysis` mode; preserve pre-existing content and findings. Cover default, `--auto`, `--gap-analysis`, and `--full-rewrite` paths. Under `--dry-run`, do not write, repair, or claim verification of unapplied additions; report verification as not run for the preview.
- **Execution contract**: exit 1 with valid JSON is scan data, not a command failure. Missing CLI, unexpected exit status, malformed JSON, or timeout means **verification incomplete**, never clean; note the reason and continue gracefully as check B7 does. Without a valid initial snapshot, do not treat every later finding as new. If a later scan fails, retain the known findings in the report rather than claiming they cleared.
- Final report distinguishes clean delta, repaired delta, unresolved findings, incomplete verification, and dry-run.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/verify_evidence.py` — `--save-snapshot`, `--delta-from`, the whitespace-normalized count comparison and grouped candidate locations, per-occurrence attribution, strict scan-failure propagation (findings JSON already carries `span` and `artifact`)
- `commands/refine-issue.md` — tool permission; snapshot before Step 5 writes; delta after all body mutations; bounded ownership-aware repairs, same-issue conflict handling, mode/error handling, final status
- `skills/ll-refine-issue/SKILL.md` and the other host mirrors — re-synced via `ll-adapt --host <host> --apply` (mirror gates trip otherwise)
- `docs/reference/CLI.md` — document the two new flags

### Similar Patterns
- `skills/capture-issue/SKILL.md` — "Verify quoted evidence against the cited artifact" (ENH-3283), the on-miss contract to reuse
- `commands/verify-issues.md` — check B7 invokes `ll-verify-evidence "$ISSUE_FILE" --json`, lists `Bash(ll-verify-evidence:*)`, degrades gracefully when unavailable

### Tests
- `scripts/tests/test_verify_evidence.py` — unit tests for the delta with representative payloads: unchanged old findings, line shifts, a new quote, an additional duplicate of an old bad quote, changed attribution, repaired findings, whitespace-only rewrites, mixed aliases resolving to one artifact, duplicates inserted before/after an existing occurrence, and cancelling equal-count replacement; missing/malformed snapshots and injected before/after infrastructure failures → incomplete exit code.
- `scripts/tests/test_refine_issue_command.py` — contract checks: allowed tools, snapshot before `fold-findings`, final check after body-changing gates, bounded repairs, explicit dry-run / incomplete states, additive-mode repair allowance, ownership checks, and same-issue concurrency/conflict behavior.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-20 — based on codebase analysis:_

- **No snapshot/delta code exists.** `compute_findings_delta`, `--save-snapshot`, `--delta-from` appear only in this issue file; `verify_evidence.py` has no envelope, snapshot, or compatibility-version constant for external consumers (only `_CACHE_VERSION = 2`, `_CACHE_ALGO = "blob-v1"`, `DEFAULT_MAX_REVISIONS = 80`, `MIN_SPAN_LEN = 20`). The "verifier compatibility version" the snapshot records is therefore a new identifier that must be defined.
- **Findings JSON shape today** (`_findings_to_json` in `scripts/little_loops/cli/verify_evidence.py`): `{"ok", "mode": "paths"|"all", "count", "findings": [{"file", "line", "section", "span", "artifact"}]}`, with no version field. `span` is the raw `CandidateSpan.text` (not normalized); `artifact` is intended to be the original reference (issue ID or path as written), not the resolved repo path; however, grouping currently reuses the last reference spelling for every candidate resolving to that path. Preserve the reference per occurrence before relying on it for delta identity. The delta will normalize whitespace only as decided above, while retaining raw display text. Occurrence counts come only from the `EvidenceFinding` list; `scan_file`'s `keyed_hashes` is a `set` and cannot supply counts.
- **Exit-code contract is currently 0/1 only.** Exit 2 arises solely from argparse `parser.error` → `SystemExit(2)` (`--update-baseline` needs `--all`; `--added-only` excludes `--all`; paths required without `--all`). Execution failures are silent: `_scan_path_list` skips non-files, `scan_file` returns `[], {}` on `OSError`, `build_tracked_index` returns an empty frozenset on git failure (→ zero findings). Constraint: for the new flags, "missing/unreadable input → exit 2, never clean" cannot be inherited from existing behavior — an unreadable issue file today reads as a clean scan. `paths` is `nargs="*"`, so "exactly one file" is a new validation. The epilog/docstring and `docs/reference/CLI.md` document only 0 and 1.
- **Atomic-write primitive exists but is not used by this module.** `little_loops.file_utils.atomic_write` (`mkstemp` in the destination dir + `os.replace`, unlinks temp on error, no parent `mkdir`) and `atomic_write_json` (adds `mkdir(parents=True)`, `json.dumps(allow_nan=False)`, round-trip `json.loads` check). `verify_evidence.py` does not import `file_utils`; `write_baseline`/`write_verdict_cache` use plain `write_text` (the cache write swallows `OSError`). Constraint: the snapshot must be atomic, and a failed write must be a reported failure — the verdict-cache swallow-on-error behavior is the opposite contract.
- **Effective scan options available to record:** `max_revisions` (`--max-revisions`), `base_dir` (`-C/--directory` or cwd; `BRConfig(base_dir)`), and the file-mode `paths` handling in `scan_paths` (absolute-ified against `base_dir`, then `relative_to(base_dir.resolve())`, falling back to the path as given on `ValueError`). File mode does not use the verdict cache or a baseline (only `scan_all` does), so neither participates in snapshot identity.
- **Refine command state.** `commands/refine-issue.md` `allowed-tools` today: `Read`, `Glob`, `Edit(.issues/**)`, `Task`, `Bash(git:*, ll-issues:*)`, `Bash(ll-history-context:*)`, `Bash(ll-code:*)`; no `ll-verify-evidence` reference anywhere in the body. Step order: 5a → 5b → 5c → 6 → 6.5 → 6.7 → 7.5 → 8. Step 7.5 writes only frontmatter (`learning_tests_required`), which is outside the verifier's `IN_SCOPE_SECTIONS`; Step 6.7 can revise `## Program Design`/prose and `ll-issues link` edits frontmatter. Constraint: the "last body-changing gate" is 6.7's revisions, and the Session Log append (6.5) also edits the file but outside verified sections.
- **Mirror surface for the command edit:** `skills/ll-refine-issue/SKILL.md` (bridge stub with an identical `allowed-tools` block, plus `skills/ll-refine-issue/agents/openai.yaml`), `.qwen/commands/ll/refine-issue.md`, `.gemini/commands/refine-issue.toml`. `commands/verify-issues.md` + `skills/ll-verify-issues/SKILL.md` already carry `Bash(ll-verify-evidence:*)` and invoke `ll-verify-evidence "$ISSUE_FILE" --json` — evidence for how a command declares this tool and degrades when it is missing.
- **Test-surface facts.** `scripts/tests/test_verify_evidence.py`: `TestCli` calls `main_verify_evidence([...])` in-process with `-C repo` and uses `pytest.raises(SystemExit)` for parser errors; fixtures `repo`, `config`, `pinned_repo`, helpers `_write`, `_commit_all`; `TestRepoGate` is the only subprocess (`gate_cli`) user. `scripts/tests/test_refine_issue_command.py` is a structural test (ENH-1237) that slices the command text between step headings (e.g. from `### 5a. Fill Gaps…` to `### 5b. Interactive Refinement`) and has no `allowed-tools` assertions — ordering claims ("snapshot before `fold-findings`") must be expressed as text-position checks against the command body.
- **Conventions in force (evidence):** JSON-emitting CLIs take `--json` via `add_json_arg` (`little_loops.cli_args`) and print via `print_json`; versioned on-disk envelopes carry an integer version field and consumers reject or ignore mismatches (`_CACHE_VERSION` in `verify_evidence.py` — silently empties; `EvidenceBundle.schema_version` in `cli/loop/evidence.py`; `BUILDER_PROJECT_SCHEMA_VERSION` in `policy_builder_core.mjs` — rejects). The two disagree on mismatch handling (silent-reset vs reject); this issue's contract (exit 2 on unsupported version) follows the reject shape.

### Dependent Files (Callers/Importers)
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py` — imports/re-exports `main_verify_evidence`; the entry point is registered at `scripts/pyproject.toml` (`ll-verify-evidence`). No change needed for new flags.
- `scripts/little_loops/init/writers.py` — permission allowlist already contains `Bash(ll-verify-evidence:*)`; no change needed.
- `.kimi-code/skills/ll-refine-issue/SKILL.md` — additional host mirror carrying the `allowed-tools` block (alongside `skills/ll-refine-issue/`, `.qwen/commands/ll/refine-issue.md`, `.gemini/commands/refine-issue.toml`); re-sync via `ll-adapt`.

### Tests
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_parser.py` — line-anchored allowlist entry `"cli/verify_evidence.py": {108: "_ISSUE_ID_RE ..."}`; any code added above `_ISSUE_ID_RE` (new imports/constants for the snapshot envelope) shifts it and breaks the duplicate-priority-resolver gate. Update the line number or add new code below line 108.
- `scripts/tests/test_wiring_skills_and_commands.py` — `SPAWN_SITE_INVENTORY` pins `("commands/refine-issue.md", 186)`; adding an `allowed-tools` line or any lines above 186 shifts it. Update the pinned line.
- `scripts/tests/test_wiring_cli_registry.py` — pins `("docs/reference/CLI.md", "ll-verify-evidence", "BUG-3282")`; keep the new flag docs under the existing `### ll-verify-evidence` section (CLI.md ~L4791, exit-code text ~L4807).

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` `### ll-verify-evidence` — beyond the flags, the exit-code contract (currently 0/1) must gain exit 2 for the new flags, and the mode list (`changed-files`, `--all`) needs the snapshot/delta usage examples.

## Program Design

### Signatures

- `compute_findings_delta(before: list[dict], after: list[dict]) -> list[dict]` — groups of positive net-count differences keyed by `(normalized_span, artifact)`, with added counts and all current candidate locations

### Call Path

`refine-issue` -> `ll-verify-evidence <issue-file> --json --save-snapshot <path>` before Step 5 writes -> body edits / `fold-findings` / body-changing gates -> `ll-verify-evidence <issue-file> --json --delta-from <path>` -> `main_verify_evidence` -> `compute_findings_delta` -> bounded repair and explicit status.

## Implementation Steps

1. Add `--save-snapshot` / `--delta-from`, the validated snapshot envelope, atomic writes, and `compute_findings_delta` to `little_loops.cli.verify_evidence`; preserve per-occurrence attribution and propagate strict scan failures in the new modes; test normalization/grouped locations, aliases, identity/option checks, flag exclusions, input/write/infrastructure failures, and exit 2 (tests first — `tdd_mode`).
2. Update `commands/refine-issue.md`: tool permission, unique per-invocation snapshot path and original-snapshot retention, early snapshot, final delta ordering, bounded ownership-aware repairs, same-issue serialization or conflict detection, preservation/mode rules, incomplete-verification reporting.
3. Extend `test_refine_issue_command.py` contract checks; document the flags in `docs/reference/CLI.md`.
4. Re-sync host mirrors (`ll-adapt --host <host> --apply`); run the mirror gates and the full suite.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_issue_parser.py` — re-pin the `cli/verify_evidence.py` line-108 allowlist entry if the CLI edit shifts `_ISSUE_ID_RE`
- Update `scripts/tests/test_wiring_skills_and_commands.py` — re-pin `SPAWN_SITE_INVENTORY` `("commands/refine-issue.md", 186)` after the command edit
- Re-sync `.kimi-code/skills/ll-refine-issue/SKILL.md` with the other mirrors via `ll-adapt --host <host> --apply`
- Update `docs/reference/CLI.md` `### ll-verify-evidence` — exit-code table (add exit 2) as well as the flags

## Impact

- **Priority**: P3 — workflow friction; no data risk.
- **Effort**: Moderate — snapshot/delta API, scanner metadata/error handling, ownership-safe command repairs, and mirror/test updates.
- **Risk**: Moderate — repair ownership and swallowed scan failures can violate preservation or report false success; targeted regression tests are required.

## Parent Issue

Decomposed from ENH-3515: Shift-left evidence verification to refine-time and make the pre-commit hook visible

## Acceptance Criteria

- [ ] `--delta-from` reports positive `(normalized_span, artifact)` net-count differences with added counts and all current candidate locations. Line shifts and whitespace-only rewrapping are ignored; new duplicates and changed attributions are detected. Equal-count replacement cancellation is documented and tested.
- [ ] Mixed issue-ID/path citations resolving to one artifact retain their original per-occurrence attributions; adding an alias cannot relabel an untouched finding (scanner regression).
- [ ] Duplicate additions before/after existing occurrences are repaired only when this pass's edit history establishes ownership; ambiguous candidates remain unresolved and unchanged. Concurrent same-issue passes are serialized or detected as conflicts before repair, even with distinct snapshots (behavioral tests).
- [ ] Injected issue-read, tracked-index, and required history/blob failures in before/after scans yield exit 2. Failed before-scans publish no valid new snapshot; failed after-scans cannot clear known findings or report clean (scanner/CLI tests).
- [ ] Missing/malformed snapshots, unsupported schema or invalid finding types, wrong project/file identity, incompatible scan options, missing/unreadable issue files, incompatible flags, and multiple input files yield exit 2, never clean success (CLI tests).
- [ ] Snapshot writes are atomic; failed scans/writes leave no usable partial snapshot, and the issue file cannot be used as the snapshot destination. Exit 1 with valid findings still produces a valid snapshot (tests).
- [ ] Independent invocations use distinct snapshot paths, including for the same issue; failed creation never reuses an old snapshot. All repair checks retain the original snapshot. Tests cover invocation isolation and command path construction.
- [ ] `commands/refine-issue.md` allows `Bash(ll-verify-evidence:*)`, snapshots before Step 5 / `fold-findings`, and runs the delta after every body-changing gate across default, auto, gap-analysis, and full-rewrite paths (contract test).
- [ ] The command text bounds repairs (one correction pass, then remove/convert, then one final check) and forbids reporting success with unresolved findings; suppression is only for reviewed counter-examples.
- [ ] Additive-only mode permits repairing this pass's additions while preserving earlier content. Dry-run makes no issue edits and does not claim verification.
- [ ] A failed snapshot is not treated as an empty baseline; incomplete verification is reported explicitly.
- [ ] `--all` / baseline behavior and the repo-wide suite gate are unchanged.
- [ ] Mirror gates pass after the command edit; `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- **Non-goal (decided): no verification step in `/ll:reconcile-issue` or `/ll:format-issue`.** The verifier scans only `IN_SCOPE_SECTIONS` (Current Behavior, Steps to Reproduce, Root Cause, Motivation, Codebase Research Findings). Reconcile rewrites other sections and preserves the in-scope ones; format-issue restructures rather than authors quotes.
- **Non-goal: a corpus-baseline-aware file mode.** `--delta-from` compares two scans of one file only.
- Out of scope, optional low-priority follow-up: verifier leniency for a span whose whitespace-split tokens all appear close together in the attributed file (the BUG-3484 shape). Arguably the joined quote was genuinely inaccurate.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-19 | Priority: P3


## Session Log
- `/ll:wire-issue` - 2026-09-20T00:32:31 - `1b17328e-89d8-45f8-a318-abba67ffafef.jsonl`
- `/ll:refine-issue` - 2026-09-20T00:19:02 - `09e2af9d-eb90-432a-a570-962fb9c5f142.jsonl`
- `/ll:format-issue` - 2026-09-20T00:10:57 - `d0eb6446-04cf-4c6e-ada1-f1ab3056d581.jsonl`
