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
confidence_score: 100
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
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

- `--save-snapshot [PATH]` — atomically write a versioned snapshot envelope containing findings and scan identity (the CLI does the write; no extra tool permission). **The CLI allocates the path**: with no `PATH` (or `auto`) it writes `.loops/tmp/scratch/evidence-snapshot-<uuid4>-<pid>.json` under the project root and returns it as `snapshot_path` in the JSON payload. The refine command cannot build a unique path itself (no `uuidgen`/`mktemp`/`mkdir` in its `allowed-tools`, and a command has no `run_dir`). Write with `little_loops.file_utils.atomic_write_json` (creates parent dirs; plain `atomic_write` does not). The `-<pid>` suffix makes the file eligible for the `SessionStart` `scratch-cleanup.sh` prune, since the command cannot `rm`. An explicit `PATH` stays supported for tests and other callers. Publish a snapshot only after a successful scan, including exit 1 with valid findings; never publish an empty-success snapshot on an execution failure.
- `--delta-from PATH` — scan, then compare occurrence counts keyed by `(normalized_span, resolved_artifact)`, excluding line numbers, against the snapshot. `resolved_artifact` is the repo-relative path `resolve_artifact` returns — the identity the scanner already groups and matches by — carried as a new field on `EvidenceFinding` and in the findings/snapshot JSON (decided: the verifier's claim is "this text exists in this file"; citation spelling is presentation). Respelling a citation of the same artifact (`ENH-3283` → its file path) is therefore not new; re-attributing a quote to a different artifact is. `normalized_span` is the scanner's existing `normalize_query` (the same identity `_span_hash` and the corpus baseline use: whitespace collapsed, markdown emphasis characters and trailing sentence punctuation stripped, case preserved) — one span identity in the module, so a span the scanner treats as unchanged can never surface as new in the delta. Keep raw span text and the original per-occurrence attribution spelling (`artifact`) for display only; neither participates in the key. Report positive count differences as `new_findings` groups, each with `added_count` and all current candidate occurrences (raw text, section, and line), plus `preexisting_count` for the matched occurrence counts. This is a **net-count delta**, not edit provenance: an equal-count removal/reinsertion of identical evidence cancels. A positive count does not identify which duplicate was newly authored; candidate locations are not automatic repair instructions. Exit 0 = no new findings, 1 = new findings, exit 2 = snapshot/input/compatibility or scan-execution failure (**verification incomplete**, never clean).

**Per-occurrence attribution:** fix `scan_file` so each candidate retains its original artifact reference through grouping by resolved path and normalized text. The current resolved-path-to-reference map retains only the last spelling, so a later path citation can relabel an earlier issue-ID citation to the same artifact. A focused reproduction confirmed this behavior. Add a regression in which both spellings resolve to one file; adding the alias must not change an untouched finding's displayed `artifact`. The delta key no longer depends on this fix (it keys on `resolved_artifact`), but the fix stays in scope because `artifact` is what each reported candidate shows the repairer. This metadata correction does not change matching rules or corpus-baseline semantics.

**JSON contract of the new modes:** `--save-snapshot` emits the normal file-mode payload plus `snapshot_path`. `--delta-from` emits `{"ok", "mode": "delta", "status": "clean"|"new_findings", "new_findings": [{"span", "resolved_artifact", "added_count", "preexisting_count", "candidates": [{"line", "section", "span", "artifact"}]}], "count", "new_count", "findings": [...]}` — every `findings` entry (here, in plain file mode, and in the snapshot) gains `resolved_artifact` alongside the existing `artifact`; the addition is backward compatible for current consumers. `findings` remains the full current scan so the caller never loses known findings. On completed delta scans, `count == len(findings)`, `new_count == sum(group["added_count"] for group in new_findings)`, and `ok == (new_count == 0)`; `status` and exit 0/1 follow `new_count`, even when grandfathered findings remain. Validate new-mode flag combinations and input cardinality after argument parsing so mutually exclusive flags, incompatible flags, and zero/multiple input files receive the same incomplete JSON response. Only syntactic argparse errors (unknown options, missing option values, invalid argument types) retain argparse stderr/exit 2 behavior. Every semantic-validation or execution exit 2 raised by the new modes prints a JSON body under `--json`: `{"ok": false, "mode", "status": "incomplete", "error": "<reason>", "findings": [...]}`, where `findings` carries the snapshot's findings when the snapshot loaded but the after-scan failed, else `[]`. "A failed after-scan retains known findings" is delivered by this body; a bare stderr message cannot carry them. The CLI has only the original snapshot and cannot recover findings from an earlier delta invocation; retaining the latest successful delta is the command's responsibility below.

**Text output:** without `--json`, snapshot mode prints the normal findings report plus `Snapshot saved: <absolute path>` on stdout whenever publication succeeds (including exit 1). Delta mode prints clean/new-findings status, added occurrence counts and candidate locations, clearly distinguishing pre-existing findings from additions; exit 0/1 follows the delta. New-mode semantic/execution failures print an explicit incomplete status and reason, plus any retained snapshot findings, and exit 2. Document and test these outputs; neither mode requires `--json`.

**Repair ownership (single rule):** counts establish detection, not ownership. The pass repairs a finding only when its span is a quote **this pass authored** — the command keeps a record of the quotes it wrote (its `fold-findings` payloads and section fills), their artifact attribution, and insertion context (section and surrounding inserted text). Repair requires mapping a current candidate to that recorded insertion using span, resolved attribution, and context; membership in a text-only quote list is insufficient. A finding whose span is not in that list, or an `added_count` that cannot be mapped to this pass's own insertions (ambiguous duplicates), is reported unresolved and left untouched. If intervening edits make occurrence ownership uncertain, preserve the content and report it unresolved. This is a conservative repair policy, not a concurrency guarantee; concurrent refinement of the same issue remains a non-goal (see Scope Boundaries). Insertion before and after an existing duplicate is tested at the CLI level (count/candidate reporting); the ownership rule itself is a command-text contract.

**Strict scan completion:** snapshot/delta modes must propagate execution failures from issue reads, tracked-index enumeration, and required history/blob operations instead of inheriting legacy empty-result fallbacks. Input preflight alone is insufficient because a later read can fail. Distinguish legitimate absent artifacts under existing matching rules from failed infrastructure operations. **Failure vs. absence rule:** a subprocess exception or nonzero return code from `git ls-files` (`build_tracked_index`) or `git log` (`HistoryIndex._run_full`, `HistoryIndex.ensure_paths`) is a failure; a zero-exit command with empty output is absence. In `BlobReader`, a failed `Popen`, a broken pipe, or an empty header line is a failure. Only a well-formed `<requested-oid> missing` response is absence; an arbitrary short header is not. A successful response must identify the requested OID and blob type, declare a valid nonnegative integer size, contain exactly that many payload bytes, and end with the expected newline terminator. Malformed headers, invalid/negative sizes, truncated payloads, and missing/incorrect terminators raise `ScanExecutionError` in strict mode. Validate the complete response before returning any bytes, even when a truncated prefix contains the requested quote. A working-tree or issue-file read raising `FileNotFoundError` for an artifact is absence; any other `OSError`, and any failure to read the issue file itself, is a failure. Mechanism: a keyword-only `strict: bool = False` threaded through these call sites raises `ScanExecutionError` instead of returning the legacy empty value; `main_verify_evidence` converts it to exit 2. A failed before-scan publishes no new valid snapshot; a failed after-scan returns exit 2, retains known findings in the report, and never claims a clean delta. Inject these failures in both phases. Keep strict failure behavior scoped to the new modes so legacy callers retain their contracts.

**Snapshot contract:** both flags require exactly one existing, readable issue file. They are mutually exclusive and incompatible with `--all`, `--update-baseline`, and `--added-only`. Reject missing/unreadable inputs rather than letting a skipped scan count as clean. The snapshot envelope records a schema version, canonical project root and issue path, verifier compatibility version, and effective scan options (including `max_revisions`). Validate the envelope and finding field types before comparison; reject unsupported versions, wrong project/file identity, and incompatible options with exit 2. Issue-body edits between scans are expected and must not invalidate identity. Reject a snapshot destination that aliases the issue file; write failures must be explicit and leave no partial snapshot usable as a baseline.

**Invocation isolation:** the refinement command calls `--save-snapshot` with no path and uses the `snapshot_path` the CLI returns, so every invocation gets a fresh uuid4-named file. Never reuse a fixed issue-ID-only path or fall back to a snapshot from an earlier run. Retain that invocation's original snapshot across all repair checks; do not overwrite it with a post-edit scan. A failed creation marks verification incomplete even if another snapshot file exists.

This is a diff between two scans of one file, not a corpus baseline: `--all`/baseline behavior is untouched.

Command changes (`commands/refine-issue.md`):
- Add `Bash(ll-verify-evidence:*)` to `allowed-tools`.
- **Snapshot** before the first body mutation — `ll-verify-evidence "$ISSUE_FILE" --json --save-snapshot`, reading `snapshot_path` from the payload. It must precede Step 5's `ll-issues fold-findings` writes, not merely Step 6's "Update Issue File". Retain the original snapshot throughout the pass. Step 3.1 skips research, not all edits: it still routes through Step 5c and Step 6.7. Snapshot before the first possible body mutation on those paths too, including covered triage followed by gap-analysis additions or stale-dependency prose repairs. Skip both scans only when no relevant body edits will occur; if an initially edit-free path later needs a body edit, take the snapshot before that edit. Report verification as not applicable only when no in-scope content was changed; never infer this from triage coverage alone.
- **Authored-quote list**: the pass records quotes, artifact attribution, and insertion context for every `fold-findings` payload and section fill so repair ownership can be decided per the single rule above.
- **Final check** with `--delta-from` after the last body-changing gate (after Step 6.7).
- **On a new finding**: reuse capture-issue's on-miss contract (ENH-3283): re-read the artifact and correct the quote, or describe the evidence in prose. A reviewed genuine counter-example may use `<!-- ll-evidence-ok: reason -->`; never suppress merely to clear the check. Allow one correction pass and recheck. If findings remain and this pass's ownership of the occurrence is established, remove the newly introduced quote or convert it to accurate prose, then perform one final check. If the span is not in this pass's authored-quote list or the duplicate is ambiguous, preserve the content and report unresolved/incomplete instead of attempting a destructive repair. Do not retry indefinitely or declare success with unresolved findings.
- **Preservation and modes**: explicitly allow correction/removal of this pass's additions in additive-only / `--gap-analysis` mode; preserve pre-existing content and findings. Cover default, `--auto`, `--gap-analysis`, and `--full-rewrite` paths. Under `--dry-run`, do not write, repair, or claim verification of unapplied additions; report verification as not run for the preview.
- **Execution contract**: exit 1 with valid JSON is scan data, not a command failure. Missing CLI, unexpected exit status, malformed JSON, or timeout means **verification incomplete**, never clean; note the reason and continue gracefully as check B7 does. Without a valid initial snapshot, do not treat every later finding as new. Keep the last successful delta report separately from the immutable original snapshot. If a later repair check fails, retain that report's known findings and label their current status unconfirmed; do not replace them with the error body's older snapshot findings or claim they cleared. If no delta has succeeded, retain the snapshot findings supplied by the CLI. Cover the sequence snapshot → successful delta with a new finding → repair → failed recheck in the command-text contract tests.
- Final report distinguishes clean delta, repaired delta, unresolved findings, incomplete verification, and dry-run.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/verify_evidence.py` — `--save-snapshot`, `--delta-from`, the `normalize_query`/`resolved_artifact`-keyed count comparison and grouped candidate locations, the `resolved_artifact` finding field, per-occurrence attribution, strict scan-failure propagation (findings JSON already carries `span` and `artifact`)
- `commands/refine-issue.md` — tool permission; CLI-allocated snapshot before Step 5 writes; delta after all body mutations; authored-quote list and bounded ownership-aware repairs, mode/error handling, final status
- `skills/ll-refine-issue/SKILL.md` and the other host mirrors — re-synced via `ll-adapt --host <host> --apply` (mirror gates trip otherwise)
- `docs/reference/CLI.md` — document the two new flags

### Similar Patterns
- `skills/capture-issue/SKILL.md` — "Verify quoted evidence against the cited artifact" (ENH-3283), the on-miss contract to reuse
- `commands/verify-issues.md` — check B7 invokes `ll-verify-evidence "$ISSUE_FILE" --json`, lists `Bash(ll-verify-evidence:*)`, degrades gracefully when unavailable

### Tests
- `scripts/tests/test_verify_evidence.py` — unit tests for the delta with representative payloads: unchanged old findings, line shifts, a new quote, an additional duplicate of an old bad quote, re-attribution to a different artifact (new) vs. respelling the same artifact (not new), repaired findings, whitespace-only rewrites, mixed aliases resolving to one artifact, duplicates inserted before/after an existing occurrence, emphasis/trailing-punctuation-only rewrites (same `normalize_query` key → not new), and cancelling equal-count replacement; auto-allocated snapshot path (unique per call, `-<pid>` suffix, parent dir created, returned as `snapshot_path`); delta `ok`/`count`/`new_count` semantics (including clean deltas with pre-existing findings), semantic-validation exit-2 JSON versus syntactic argparse errors, and non-JSON snapshot/delta/incomplete output; missing/malformed snapshots and injected before/after infrastructure failures (including malformed blob headers, invalid/negative sizes, short payloads containing the quote, and missing/incorrect terminators) → incomplete exit code with the JSON body; legacy (non-strict) callers keep their empty-result behavior.
- `scripts/tests/test_refine_issue_command.py` — **text-contract** checks only (the file is structural; it cannot exercise an LLM command): allowed tools, snapshot before `fold-findings` with no hand-built path, final check after body-changing gates, bounded repairs, authored-quote ownership using attribution and insertion context, covered triage followed by Step 5c additions or Step 6.7 prose edits, skip only for paths without relevant edits, explicit dry-run / incomplete states, additive-mode repair allowance, and retaining the last successful delta after a failed repair recheck.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_parser.py` — line-anchored allowlist entry `"cli/verify_evidence.py": {108: "_ISSUE_ID_RE ..."}`; any code added above `_ISSUE_ID_RE` (new imports/constants for the snapshot envelope) shifts it and breaks the duplicate-priority-resolver gate. Update the line number or add new code below line 108.
- `scripts/tests/test_wiring_skills_and_commands.py` — `SPAWN_SITE_INVENTORY` pins `("commands/refine-issue.md", 186)`; adding an `allowed-tools` line or any lines above 186 shifts it. Update the pinned line.
- `scripts/tests/test_wiring_cli_registry.py` — pins `("docs/reference/CLI.md", "ll-verify-evidence", "BUG-3282")`; keep the new flag docs under the existing `### ll-verify-evidence` section (CLI.md ~L4791, exit-code text ~L4807).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-20 — based on codebase analysis:_

- **No snapshot/delta code exists.** `compute_findings_delta`, `--save-snapshot`, `--delta-from` appear only in this issue file; `verify_evidence.py` has no envelope, snapshot, or compatibility-version constant for external consumers (only `_CACHE_VERSION = 2`, `_CACHE_ALGO = "blob-v1"`, `DEFAULT_MAX_REVISIONS = 80`, `MIN_SPAN_LEN = 20`). The "verifier compatibility version" the snapshot records is therefore a new identifier that must be defined.
- **Findings JSON shape today** (`_findings_to_json` in `scripts/little_loops/cli/verify_evidence.py`): `{"ok", "mode": "paths"|"all", "count", "findings": [{"file", "line", "section", "span", "artifact"}]}`, with no version field. `span` is the raw `CandidateSpan.text` (not normalized); `artifact` is intended to be the original reference (issue ID or path as written), not the resolved repo path; however, grouping currently reuses the last reference spelling for every candidate resolving to that path. Preserve the reference per occurrence before relying on it for delta identity. The delta keys on `normalize_query` as decided above, while retaining raw display text. Occurrence counts come only from the `EvidenceFinding` list; `scan_file`'s `keyed_hashes` is a `set` and cannot supply counts.
- **Exit-code contract is currently 0/1 only.** Exit 2 arises solely from argparse `parser.error` → `SystemExit(2)` (`--update-baseline` needs `--all`; `--added-only` excludes `--all`; paths required without `--all`). Execution failures are silent: `_scan_path_list` skips non-files, `scan_file` returns `[], {}` on `OSError`, `build_tracked_index` returns an empty frozenset on git failure (→ zero findings). Constraint: for the new flags, "missing/unreadable input → exit 2, never clean" cannot be inherited from existing behavior — an unreadable issue file today reads as a clean scan. `paths` is `nargs="*"`, so "exactly one file" is a new validation. The epilog/docstring and `docs/reference/CLI.md` document only 0 and 1.
- **Atomic-write primitive exists but is not used by this module.** `little_loops.file_utils.atomic_write` (`mkstemp` in the destination dir + `os.replace`, unlinks temp on error, no parent `mkdir`) and `atomic_write_json` (adds `mkdir(parents=True)`, `json.dumps(allow_nan=False)`, round-trip `json.loads` check). `verify_evidence.py` does not import `file_utils`; `write_baseline`/`write_verdict_cache` use plain `write_text` (the cache write swallows `OSError`). Constraint: the snapshot must be atomic, and a failed write must be a reported failure — the verdict-cache swallow-on-error behavior is the opposite contract.
- **Effective scan options available to record:** `max_revisions` (`--max-revisions`), `base_dir` (`-C/--directory` or cwd; `BRConfig(base_dir)`), and the file-mode `paths` handling in `scan_paths` (absolute-ified against `base_dir`, then `relative_to(base_dir.resolve())`, falling back to the path as given on `ValueError`). File mode does not use the verdict cache or a baseline (only `scan_all` does), so neither participates in snapshot identity.
- **Refine command state.** `commands/refine-issue.md` `allowed-tools` today: `Read`, `Glob`, `Edit(.issues/**)`, `Task`, `Bash(git:*, ll-issues:*)`, `Bash(ll-history-context:*)`, `Bash(ll-code:*)`; no `ll-verify-evidence` reference anywhere in the body. Step order: 5a → 5b → 5c → 6 → 6.5 → 6.7 → 7.5 → 8. Step 7.5 writes only frontmatter (`learning_tests_required`), which is outside the verifier's `IN_SCOPE_SECTIONS`; Step 6.7 can revise `## Program Design`/prose and `ll-issues link` edits frontmatter. Constraint: the "last body-changing gate" is 6.7's revisions, and the Session Log append (6.5) also edits the file but outside verified sections. Step 3.1 explicitly continues through Step 5c (with `--gap-analysis`) and Steps 6/6.5/6.7, so covered triage does not establish that no body edits occur.
- **Mirror surface for the command edit:** `skills/ll-refine-issue/SKILL.md` (bridge stub with an identical `allowed-tools` block, plus `skills/ll-refine-issue/agents/openai.yaml`), `.qwen/commands/ll/refine-issue.md`, `.gemini/commands/refine-issue.toml`. `commands/verify-issues.md` + `skills/ll-verify-issues/SKILL.md` already carry `Bash(ll-verify-evidence:*)` and invoke `ll-verify-evidence "$ISSUE_FILE" --json` — evidence for how a command declares this tool and degrades when it is missing.
- **Test-surface facts.** `scripts/tests/test_verify_evidence.py`: `TestCli` calls `main_verify_evidence([...])` in-process with `-C repo` and uses `pytest.raises(SystemExit)` for parser errors; fixtures `repo`, `config`, `pinned_repo`, helpers `_write`, `_commit_all`; `TestRepoGate` is the only subprocess (`gate_cli`) user. `scripts/tests/test_refine_issue_command.py` is a structural test (ENH-1237) that slices the command text between step headings (e.g. from `### 5a. Fill Gaps…` to `### 5b. Interactive Refinement`) and has no `allowed-tools` assertions — ordering claims ("snapshot before `fold-findings`") must be expressed as text-position checks against the command body.
- **Conventions in force (evidence):** JSON-emitting CLIs take `--json` via `add_json_arg` (`little_loops.cli_args`) and print via `print_json`; versioned on-disk envelopes carry an integer version field and consumers reject or ignore mismatches (`_CACHE_VERSION` in `verify_evidence.py` — silently empties; `EvidenceBundle.schema_version` in `cli/loop/evidence.py`; `BUILDER_PROJECT_SCHEMA_VERSION` in `policy_builder_core.mjs` — rejects). The two disagree on mismatch handling (silent-reset vs reject); this issue's contract (exit 2 on unsupported version) follows the reject shape.

### Dependent Files (Callers/Importers)
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py` — imports/re-exports `main_verify_evidence`; the entry point is registered at `scripts/pyproject.toml` (`ll-verify-evidence`). No change needed for new flags.
- `scripts/little_loops/init/writers.py` — permission allowlist already contains `Bash(ll-verify-evidence:*)`; no change needed.
- `.kimi-code/skills/ll-refine-issue/SKILL.md` — additional host mirror carrying the `allowed-tools` block (alongside `skills/ll-refine-issue/`, `.qwen/commands/ll/refine-issue.md`, `.gemini/commands/refine-issue.toml`); re-sync via `ll-adapt`.

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` `### ll-verify-evidence` — beyond the flags, the exit-code contract (currently 0/1) must gain exit 2 for the new flags, and the mode list (`changed-files`, `--all`) needs the snapshot/delta usage examples.

## Program Design

### Signatures

- `compute_findings_delta(before: list[dict], after: list[dict]) -> list[dict]` — groups of positive net-count differences keyed by `(normalize_query(span), resolved_artifact)`, with added counts and all current candidate locations
- `EvidenceFinding.resolved_artifact: str` — new dataclass field (repo-relative resolved path), emitted by `_findings_to_json` next to `artifact`
- `class ScanExecutionError(Exception)` — raised in strict mode when an issue read, tracked-index, history, or blob operation fails (as opposed to reporting absence)
- `class EvidenceSnapshot` — dataclass envelope: `schema_version`, `verifier_compat`, `project_root`, `issue_path`, `max_revisions`, `findings`
- `write_snapshot(base_dir: Path, snapshot: EvidenceSnapshot, dest: Path | None) -> Path` — `dest=None` allocates `.loops/tmp/scratch/evidence-snapshot-<uuid4>-<pid>.json`; writes via `atomic_write_json`; rejects a destination aliasing the issue file
- `load_snapshot(path: Path, *, base_dir: Path, issue_path: Path, max_revisions: int) -> EvidenceSnapshot` — validates envelope, field types, identity, and options; raises on any mismatch
- `scan_file(..., strict: bool = False)`, `scan_paths(..., strict: bool = False)`, `build_tracked_index(base_dir, *, strict: bool = False)`, and a `strict` constructor flag on `ArtifactMatcher` forwarded to `HistoryIndex` / `BlobReader` — default `False` preserves every legacy caller

### Call Path

`refine-issue` -> `ll-verify-evidence <issue-file> --json --save-snapshot` (CLI allocates and returns `snapshot_path`) before the first possible body mutation (including Step 5c/6.7 on covered-triage paths) -> body edits / `fold-findings` / body-changing gates -> `ll-verify-evidence <issue-file> --json --delta-from <path>` -> `main_verify_evidence` -> `compute_findings_delta` -> bounded repair, retention of the last successful delta report, and explicit status.

## Implementation Steps

1. Add `--save-snapshot` / `--delta-from`, the validated snapshot envelope, atomic writes, and `compute_findings_delta` to `little_loops.cli.verify_evidence`; preserve per-occurrence attribution and propagate strict scan failures in the new modes; test normalization/grouped locations, aliases, identity/option checks, flag exclusions, input/write/infrastructure failures including complete blob-response validation, explicit JSON/text contracts, and exit 2 (tests first — `tdd_mode`).
2. Update `commands/refine-issue.md`: tool permission, CLI-allocated snapshot path and original-snapshot retention, snapshot before the first possible body mutation even on covered-triage paths (skip only without relevant edits), final delta ordering, quote/attribution/insertion-context ownership records and bounded repairs, preservation/mode rules, and incomplete reporting that retains the last successful delta.
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

- [ ] `--delta-from` reports positive `(normalize_query(span), resolved_artifact)` net-count differences with added counts and all current candidate locations, in the documented `mode: "delta"` JSON shape (full `findings` retained). Line shifts and whitespace/emphasis/trailing-punctuation-only rewrites are ignored; new duplicates (inserted before or after an existing occurrence) and re-attribution to a different artifact are detected; respelling a citation of the same artifact is not new. Findings JSON carries `resolved_artifact`. Equal-count replacement cancellation is documented and tested. Completed delta reports use `count == len(findings)`, `new_count == sum(added_count)`, and `ok == (new_count == 0)`; status/exit 0/1 follow new findings, including a clean delta with nonempty pre-existing findings.
- [ ] Mixed issue-ID/path citations resolving to one artifact retain their original per-occurrence attributions; adding an alias cannot relabel an untouched finding's displayed `artifact` (scanner regression).
- [ ] **Never clean on failure (CLI tests):** injected issue-read, tracked-index, and history/blob failures in either scan; missing/malformed snapshots; unsupported schema or invalid finding types; wrong project/file identity; incompatible scan options; missing/unreadable issue files; incompatible flags; and multiple input files all yield exit 2 with the `status: "incomplete"` JSON body under `--json`. A failed before-scan publishes no snapshot; a failed after-scan's body carries the snapshot's known findings. Semantic flag/cardinality errors use this JSON contract; only syntactic argparse errors retain stderr-only usage errors. Legitimate absence (per the failure-vs-absence rule) still scans normally, and non-strict legacy callers keep their existing behavior. Strict blob reads reject malformed headers, invalid/negative sizes, truncated payloads (including a prefix containing the quote), and missing/incorrect terminators before any matching; inject each failure in both phases.
- [ ] **Snapshot writes (CLI tests):** `--save-snapshot` with no path allocates a unique `evidence-snapshot-<uuid4>-<pid>.json` under `.loops/tmp/scratch/`, creates the parent dir, and returns `snapshot_path`; two calls for the same issue yield distinct paths. Writes are atomic; a failed scan/write leaves no usable partial snapshot; the issue file is rejected as a destination. Exit 1 with valid findings still produces a valid snapshot. Without `--json`, snapshot mode prints the absolute saved path, delta mode distinguishes new from pre-existing findings with added counts/candidate locations, and failures explicitly report incomplete verification; test these outputs and exit codes.
- [ ] `commands/refine-issue.md` (text-contract test) allows `Bash(ll-verify-evidence:*)`; snapshots before Step 5 / `fold-findings` using the CLI-returned `snapshot_path` (no hand-built path, no reuse of an earlier snapshot, original retained across repair checks); runs the delta after every body-changing gate across default, auto, gap-analysis, and full-rewrite paths; does not skip solely on Step 3.1 covered triage. Contract tests cover covered triage followed by Step 5c additions and Step 6.7 prose repairs, with a snapshot before either; skip scans only when no relevant body edits occur.
- [ ] The command text states the single ownership rule (repair only occurrences mapped to this pass's authored quote, resolved attribution, and insertion context; text-only matches or uncertain ownership remain unresolved and untouched), bounds repairs (one correction pass, then remove/convert, then one final check), forbids reporting success with unresolved findings, and limits suppression to reviewed counter-examples.
- [ ] Additive-only mode permits repairing this pass's additions while preserving earlier content. Dry-run makes no issue edits and does not claim verification. A failed snapshot is not treated as an empty baseline; incomplete verification is reported explicitly. The command retains its last successful delta separately from the original comparison snapshot: contract tests cover snapshot → new finding → repair → failed recheck, requiring the latest known findings to remain visible as unconfirmed rather than replaced by the snapshot's older findings.
- [ ] `--all` / baseline behavior and the repo-wide suite gate are unchanged.
- [ ] `docs/reference/CLI.md` `### ll-verify-evidence` documents `--save-snapshot` / `--delta-from` and the new exit 2; the line-pinned entries in `test_issue_parser.py` (`_ISSUE_ID_RE`, line 108) and `test_wiring_skills_and_commands.py` (`SPAWN_SITE_INVENTORY`, `refine-issue.md` 186) are re-pinned if the edits shift them.
- [ ] Mirror gates pass after the command edit; `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- **Non-goal (decided): no verification step in `/ll:reconcile-issue` or `/ll:format-issue`.** The verifier scans only `IN_SCOPE_SECTIONS` (Current Behavior, Steps to Reproduce, Root Cause, Motivation, Codebase Research Findings). Reconcile rewrites other sections and preserves the in-scope ones; format-issue restructures rather than authors quotes.
- **Non-goal: a corpus-baseline-aware file mode.** `--delta-from` compares two scans of one file only.
- **Non-goal: concurrent refinement of the same issue.** No locking, serialization, or overlap detection. Quote-list membership alone cannot distinguish identical concurrent insertions. Require resolved attribution and insertion context when identifying a repairable occurrence, preserve content whenever ownership is uncertain, and make no guarantee of concurrency safety.
- Out of scope, optional low-priority follow-up: verifier leniency for a span whose whitespace-split tokens all appear close together in the attributed file (the BUG-3484 shape). Arguably the joined quote was genuinely inaccurate.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-19 | Priority: P3


## Verification Notes

Verdict at time of check: **PROPOSAL_UNSOUND** (AC-coverage gaps corrected in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

All referenced files, line numbers and code claims verified against the current tree; `ll-verify-evidence` reports no unverifiable quotes. Graph provider: codegraph (fresh) available; not needed.

- AC coverage: `docs/reference/CLI.md` flag/exit-2 docs and the two line-pinned test re-pins (`test_issue_parser.py` line 108, `SPAWN_SITE_INVENTORY` `refine-issue.md` 186) were in the Integration Map but had no acceptance criterion — added.
- Confirmed: `scan_file` `resolved_ref[resolved] = artifact` keeps only the last spelling per resolved path (per-occurrence attribution defect is real); `refine-issue.md` lacks `Bash(ll-verify-evidence:*)`; no snapshot/delta code exists.

### Re-verification (2026-09-20, after ownership/strict-scan/JSON-contract revisions)

Verdict at time of check: **VALID** (no corrections needed). Re-checked against the current tree: `_ISSUE_ID_RE` still at `verify_evidence.py:108` (matches the `test_issue_parser.py` pin); `resolved_ref[resolved] = artifact` at line 1472 and its use at line 1501 (attribution defect real); `build_tracked_index`, `HistoryIndex._run_full`/`ensure_paths`, `BlobReader`, `normalize_query`, `EvidenceFinding` all present with no `strict`/snapshot/delta code; `file_utils.atomic_write`/`atomic_write_json` exist; `SPAWN_SITE_INVENTORY` still pins `("commands/refine-issue.md", 186)`; `refine-issue.md` still lacks `ll-verify-evidence`; all four host mirrors and `docs/reference/CLI.md` `### ll-verify-evidence` exist. `ll-verify-evidence` reports no unverifiable quotes. Proposal consequence check (B6): no new exception-handler, fixture, or AC-coverage gaps. Graph: provider=codegraph freshness=fresh (not needed for verdict).

## Session Log
- `/ll:confidence-check` - 2026-09-20T03:58:47 - `85b20279-96d0-4b4d-a210-49fd46d89eea.jsonl`
- `/ll:verify-issues` - 2026-09-20T03:56:10 - `21db537a-a4a5-4aeb-96ea-183b65d27383.jsonl`
- `/ll:confidence-check` - 2026-09-20T02:58:11 - `4ac1f770-fd60-4b79-879d-3dc59e1d8d4b.jsonl`
- `/ll:verify-issues` - 2026-09-20T01:36:18 - `58521fbd-d3a2-45c1-879f-6abf803572a3.jsonl`
- `/ll:wire-issue` - 2026-09-20T00:32:31 - `1b17328e-89d8-45f8-a318-abba67ffafef.jsonl`
- `/ll:refine-issue` - 2026-09-20T00:19:02 - `09e2af9d-eb90-432a-a570-962fb9c5f142.jsonl`
- `/ll:format-issue` - 2026-09-20T00:10:57 - `d0eb6446-04cf-4c6e-ada1-f1ab3056d581.jsonl`
