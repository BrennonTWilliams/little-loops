---
id: 3470
title: Wire credential scan into the FEAT-3182 EvidenceBundle
type: ENH
priority: P1
status: done
discovered_date: '2026-09-13'
completed_at: '2026-09-14T18:18:16Z'
parent: ENH-3466
depends_on:
- ENH-3469
labels:
- goal-7,security,verification
decision_needed: false
confidence_score: 95
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-3470: Wire credential scan into the FEAT-3182 EvidenceBundle

## Summary

Add `credential_scan.*` entries to `EvidenceBundle`
(`scripts/little_loops/cli/loop/evidence.py`), backed by the scanner built
in ENH-3469 (now `done` — this issue calls the scanner, it does not
build it). The bundle re-reads the **archived run-directory files and its
own non-evidentiary context section**, records `tool`/`version`/`rules_sha`
and redacted hits, and turns any hit into an explicit `GapEntry` plus a
non-zero exit from `ll-loop evidence`. No `scanned_at` field is added: the
bundle's byte-identical reproducibility invariant stands unchanged.

## Current Behavior

`assemble_bundle` (`scripts/little_loops/cli/loop/evidence.py:193`) builds
`EvidenceBundle` from exactly three evidentiary sources (git, history.db,
archived run directory) and never scans any of that data for credentials.
`ll-loop evidence` archives `state.json`, `events.jsonl`, `summary.json`,
and `probe-*.json` — including `events.jsonl`'s verbatim
`llm_prompt`/`raw`/`reason`/`evidence` fields — into a bundle with no
credential-pattern check, so a leaked credential quoted in a loop
transcript is redistributed undetected.

## Expected Behavior

The bundle scans archived run-dir files and the `loop_runs.error` context
entry with ENH-3469's `scan_text`, adds `credential_scan.tool`/`version`/
`rules_sha`/`hit_count`/`hits` entries with `source="scanner"`, and appends
a `GapEntry("credential_hits", ...)` when any hit is found. `ll-loop
evidence` still writes and prints the bundle but returns exit code `2`
instead of `0` when `credential_hits` is present, per Design › Fail
behavior.

## Impact

- **Priority**: P1 — closes a credential-leak-detection gap in the
  evidence bundle produced by every loop run.
- **Effort**: Medium — one file (`evidence.py`) touched plus doc updates;
  the scanner primitive this issue calls already exists and is done.
- **Risk**: Low — additive `EvidenceEntry`/`GapEntry` shapes, a new
  keyword-only `context_extra` parameter with a default, and the
  reproducibility invariant is explicitly preserved (see Design ›
  `scanned_at`).
- **Breaking Change**: No — existing `assemble_bundle` callers are
  unaffected by the new defaulted parameter; `cmd_evidence` gains one new
  non-zero exit code (`2`) that fires only on a genuine credential hit.

## Parent Issue

Decomposed from ENH-3466: Goal 7 — credential-scan verification primitive
(FEAT-034 extension). This child covers wiring the scanner (ENH-3469) into
the evidence bundle and resolving the bundle-shape decisions that only
exist at the integration point.

## Design

### What is scanned (resolved)

Evidentiary entries are git SHAs, file hashes, counts, and paths — a
credential cannot live there, so "scan the bundle's own evidentiary data"
scans nothing useful. The real leak surface is:

1. **Archived run-dir files**: `state.json`, `events.jsonl`,
   `summary.json`, and every `probe-*.json` — read as text and passed to
   `scan_text`, one call per file so `line` is meaningful. `events.jsonl`
   is the important one: it carries `llm_prompt`, `raw`, `reason`, and
   `evidence` verbatim.
2. **`context_extra` only** — the `loop_runs.error` entry sourced from
   `history.db`. Its value is stringified via
   `json.dumps(value, sort_keys=True, default=str)` when not already a
   `str` and scanned as target `context:loop_runs.error`. The other context
   entries (`captured.*`, `evaluate.*`) are **not** scanned separately: they
   are copied out of `state.json`/`events.jsonl`, which the file scan already
   covers, so scanning them again would double-count every hit.
   `loop_runs.evaluator_score` is numeric and is skipped.

The `loop_runs.error`/`evaluator_score` context entries are currently
appended by `cmd_evidence` **after** `assemble_bundle` returns
(`evidence.py:506`). Move that `extend` into `assemble_bundle` via a new
`context_extra: list[ContextEntry] | None = None` parameter so the scan
sees it; `cmd_evidence` passes what it already computes. **The extend must
happen before the `missing_run_dir` early return** (`evidence.py:224-228`),
otherwise a bundle for a pruned run dir silently loses `loop_runs.error` —
a regression from today's behavior.

### Entry shape

Flat keys matching the existing convention (`file.state.json.sha256`,
`probe_file_count`), scalar-valued except `hits`, all with a new `source`
value `"scanner"`:

| key | value |
|---|---|
| `credential_scan.tool` | `"little_loops.pii"` |
| `credential_scan.version` | `CREDENTIAL_SCANNER_VERSION` (int) |
| `credential_scan.rules_sha` | `credential_rules_sha()` |
| `credential_scan.hit_count` | int |
| `credential_scan.hits` | list of `{"target", "line", "rule", "fingerprint"}`, sorted by `(target, line, rule, fingerprint)` |

`target` is the run-dir file name (`events.jsonl`) or the context key
(`context:loop_runs.error`). The sort key is stated explicitly because
`scan_text` only orders findings *within* one target; cross-target order
must be defined for `hits` to be reproducible, not incidentally stable.
Run-dir files are visited in the fixed tuple order then `sorted(glob)`
order, matching the existing loops. **No excerpt, ever** —
`CredentialFinding` has no excerpt field by design (ENH-3469); do not
reconstruct one here.

The four scalar entries (`tool`, `version`, `rules_sha`, `hit_count`) plus
`hits` are emitted on **every** bundle, including the `missing_run_dir`
early-return path — the scan runs over whatever inputs exist (possibly only
`context_extra`, possibly nothing). This gives one invariant, "every bundle
carries a scan record," instead of a second absence case to reason about.
Structure the scan as a helper called from both the early-return branch and
the end of `assemble_bundle`, or restructure so the scan is the final step
on both paths.

### Bundle-level leak vs. scanner-level leak (resolved)

The bundle copies `evaluate.<state>.raw`/`.reason`/`.evidence`/`.llm_prompt`
and `loop_runs.error` into `context_non_evidentiary` **verbatim**
(`evidence.py:392-405`, `:179`). A credential that the scan finds in
`events.jsonl` therefore *will* also appear in `canonical_json()` through
the context section. This issue does **not** change that: the scan's job is
to flag the bundle as unsafe to redistribute (the parent's stated intent),
not to redact it. Consequently the no-leak invariant is scoped to what the
scanner itself emits — no `credential_scan.*` entry value and no
`GapEntry.detail` may contain the matched text. Redacting matched spans in
the context section is a possible follow-up (see Out of Scope).

### `_EVIDENTIARY_SOURCES` and the "three sources" text

Add `"scanner"` as a fourth value. The scan reads `run_dir_file` bytes but
its `version`/`rules_sha` derive from code, so neither existing value fits.
Update every place that enumerates the sources:

- `_EVIDENTIARY_SOURCES` (`evidence.py:25`)
- `EvidenceEntry.source` comment (`evidence.py:62`)
- module docstring line 3 ("three deterministic sources only")
- `_BUNDLE_COMMENT` (`evidence.py:27-36`, "re-derivable from git,
  history.db, and the archived run directory")
- `test_every_evidentiary_entry_traces_to_deterministic_source`
  (`test_feat3182_evidence_bundle.py:153-159`) — passes mechanically once
  the frozenset grows; add an assertion that `credential_scan.*` entries use
  `"scanner"` and nothing else does.

### `scanned_at` — dropped (resolved)

The parent asked for `scanned_at`. It is **not added**. A wall-clock stamp
carries no deterministic information; `version` + `rules_sha` already make
two scans comparable and make a rule-set change visible as a different
hash. Dropping it means the reproducibility invariant
(`test_rerun_over_unchanged_inputs_is_byte_identical`), the no-timestamp
test, `_BUNDLE_COMMENT`, `canonical_json()`'s docstring, and the CLI.md
sentence all remain true as written. Record this deviation from the parent
in the Resolution when closing.

### Fail behavior (resolved)

- `hit_count > 0` appends
  `GapEntry("credential_hits", "<n> credential-pattern hit(s) in <targets>")`
  so `has_gaps` flips and the human summary lists it with the other gaps.
- `cmd_evidence` **still writes** `--output` and prints `--json` (the
  bundle is the record of the failure), then returns exit code `2` when
  `credential_hits` is present. Exit `1` stays reserved for the existing
  "run not found" path.
- **Exit `2` is deliberate** (answering the refine-issue finding below):
  `1` is already taken by "run not found" for this subcommand, and the only
  other `2` under `cli/loop/` belongs to a different subcommand
  (`edit-routes`, "loop not found"), so there is no collision within
  `ll-loop evidence`'s own contract. The CLI.md line "a gap is not a command
  failure" must be rewritten to name `credential_hits` as the single
  exception.
- `_print_human_summary` prints `credential hits: <n>` after the entry
  counts.

## Integration Map

**Files to modify**
- `scripts/little_loops/cli/loop/evidence.py` — `_EVIDENTIARY_SOURCES`,
  module docstring, `_BUNDLE_COMMENT`, `EvidenceEntry.source` comment,
  `assemble_bundle()` (new `context_extra` param + scan step),
  `_print_human_summary`, `cmd_evidence` (pass `context_extra`, exit 2 on
  hits). Import `scan_text`, `credential_rules_sha`,
  `CREDENTIAL_SCANNER_VERSION` from `little_loops.pii`.

**Dependent files**
- `scripts/tests/test_feat3182_evidence_bundle.py` — source-enforcement
  test gains the `"scanner"` assertion; reproducibility and no-timestamp
  tests are **unchanged** and must keep passing. New tests below.
- `scripts/little_loops/cli/loop/__init__.py:1001-1006,1127-1128` —
  registers/dispatches `ll-loop evidence` → `cmd_evidence()`. No signature
  change; verify exit code 2 propagates through the dispatcher.

**Documentation**
- `docs/reference/CLI.md:1297-1322` — the "no timestamp field" sentence
  stays true; extend the `source` enumeration with `scanner`, add the
  `credential_scan.*` keys to the "Bundle shape" list, add `credential_hits`
  to the "Gap categories" list, and rewrite the exit-code line: `0` = bundle
  assembled (gaps other than `credential_hits` are not a command failure);
  `1` = run not found; `2` = bundle assembled and written, but
  `credential_hits` present.
- `docs/reference/API.md:4504-4568` — `assemble_bundle` signature
  (`context_extra`), the fourth source value, the `credential_scan.*` entry
  keys, `credential_hits` in the gap-taxonomy bullet, the no-excerpt rule,
  and a sentence that the context section stays verbatim (the scan flags,
  it does not redact).
- `docs/ARCHITECTURE.md` — no direct bundle-shape reference found; no
  change expected.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- ENH-3469 (credential-pattern scanner in `pii.py`) is now `done`: `scan_text(text, rules=CREDENTIAL_RULES) -> list[CredentialFinding]` (`pii.py:84`), `credential_rules_sha(rules=CREDENTIAL_RULES) -> str` (`pii.py:115`), and `CREDENTIAL_SCANNER_VERSION: int = 1` (`pii.py:71`) all exist exactly as this issue's Program Design cites them; `CredentialFinding` (`pii.py:75`) confirmed to have only `rule`/`line`/`fingerprint` fields, no `excerpt`.
- `scan_text`/`credential_rules_sha` have no production call site in this codebase today (only their own definitions, the package re-export, and `test_pii.py`). The one other `little_loops.pii` production consumer is `redact_pii` in `_redact_input_context` (`cli/logs.py:1840`), which silently redacts and returns `(text, bool)` with no report/gate — a different contract from `scan_text`'s return-a-list-of-findings shape, so this issue is greenfield wiring with no existing "scan and gate" convention in this codebase to match.
- Every current `GapEntry.category` in `evidence.py` names an absence, disagreement, or staleness (`missing_*`, `*_changed_*`, `*_stale`, `*_not_committed_*` — enumerated across all ~10 construction sites in `assemble_bundle`, `evidence.py:215-368`); none names a positive "found N things" condition. `credential_hits` is the first category of that shape in the taxonomy — a convention departure worth the implementer noting, not a defect.
- `cmd_evidence`'s own documented contract (`docs/reference/CLI.md:1314`) is "0 = bundle assembled (gaps, if any, are reported inside it — a gap is not a command failure); 1 = run directory could not be resolved," matching the code exactly (`return 1` only at `evidence.py:472` for unresolved run, `return 0` unconditionally at `evidence.py:521`). No other command under `cli/loop/` uses exit `2` to mean "ran successfully but found a hit" — the one `return 2` in that directory (`edit_routes.py:48`) means "loop not found." Two nearby CLI families disagree with each other too: `ll-verify-*` uses exit `1` for an unsuppressed finding; `ll-issues check-*` reserves `2` for "target issue not found" and uses `1` for "check failed." This issue's proposed exit `2` for `credential_hits` matches neither existing convention family — confirm the choice is deliberate (distinguishing "gap-only" from "gap-with-credential-hit" via a still-higher severity code) rather than an accidental collision with the `check-*` family's "not found" meaning.

## Program Design

### Types

No new types. Reuses existing `EvidenceEntry` (`key: str`, `value: Any`,
`source: str` — `scripts/little_loops/cli/loop/evidence.py:57`) and `GapEntry`
(`category: str`, `detail: str` — `evidence.py:82`) for the `credential_scan.*`
entries and the `credential_hits` gap. Imports `CredentialFinding` from
ENH-3469 (`little_loops.pii`) but never constructs one itself — it only reads
`scan_text`'s return value.

### Signatures

Existing, signature changes noted:
- `assemble_bundle(loop_runs_row: dict[str, Any] | None, run_dir: Path | None, git_predicates: dict[str, str]) -> EvidenceBundle` — `evidence.py:193`. Gains a new
  `context_extra: list[ContextEntry] | None = None` parameter (optional,
  additive — existing callers unaffected) and a scan step appended after the
  `context_non_evidentiary` section is built.
- `cmd_evidence(args: argparse.Namespace, loops_dir: Path) -> int` — `evidence.py:463`.
  No signature change; passes `context_extra` into `assemble_bundle` instead
  of extending it afterward, and returns `2` instead of `0` when
  `credential_hits` is present.

New (imported, not defined here — built in ENH-3469):
- `scan_text(text: str, rules: tuple[CredentialRule, ...] = CREDENTIAL_RULES) -> list[CredentialFinding]`
- `credential_rules_sha(rules: tuple[CredentialRule, ...] = CREDENTIAL_RULES) -> str`

### Call Path

`cmd_evidence` (`evidence.py:463`) currently calls `assemble_bundle(loop_runs_row, run_dir, git_predicates)` (`evidence.py:505`) then does
`bundle.context_non_evidentiary.extend(context_extra)` (`evidence.py:506`) →
this issue moves that `extend` inside `assemble_bundle` (new `context_extra`
param) so the scan step, appended as the last evidentiary step in
`assemble_bundle`, sees the full `context_non_evidentiary` section → for each
run-dir file (`state.json`/`events.jsonl`/`summary.json`/`probe-*.json`,
already enumerated by `assemble_bundle`'s existing `for name in (...)` loop
and `run_dir.glob("probe-*.json")`) and each string-valued `context_extra`
entry (not the `captured.*`/`evaluate.*` entries, which the file scan
already covers), call `scan_text` (ENH-3469) → any hit appends an `EvidenceEntry` with
`source="scanner"` and a `GapEntry("credential_hits", ...)` (`GapEntry` —
`evidence.py:82`) → back in `cmd_evidence`, `bundle.has_gaps`
(`EvidenceBundle.has_gaps` — `evidence.py:102`) is checked to select exit
code `2` instead of the existing `return 0` (`evidence.py:521`).

### Decision Rules

N/A — no new classification logic; `hit_count > 0` is the only branch,
already covered under Design › Fail behavior.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- `_read_json_file` (`evidence.py:122-128`) catches only `(json.JSONDecodeError, OSError)`, and `_read_events` (`evidence.py:131-145`) only catches per-line `json.JSONDecodeError` — neither catches `UnicodeDecodeError` (a `ValueError` subclass), so a non-UTF8-decodable run-dir file already raises uncaught in current code today, independent of this issue's change. `pii.py`'s own `scan_file()` wrapper (`pii.py:108-112`) decodes with `errors="replace"`, tolerating invalid UTF-8. Since the new scan step must turn each run-dir file's bytes into `str` for `scan_text`, decoding with `errors="replace"` (matching `scan_file`'s own tolerance) avoids inheriting the existing crash-on-invalid-UTF8 gap in `_read_json_file`/`_read_events` for files the scan step reads that those two helpers don't already read cleanly (e.g. `probe-*.json`, which today is only glob-counted, never opened).

## Tests

All fixtures assemble fake tokens from fragments at runtime (never a
committed literal), per ENH-3469 Design › gitleaks. Add to
`scripts/tests/test_feat3182_evidence_bundle.py`:

- **Clean run**: existing `build_archive_dir` fixture yields
  `credential_scan.hit_count == 0`, no `credential_hits` gap, all four
  `credential_scan.*` scalar keys present with `source == "scanner"`.
- **Hit in events.jsonl**: an `evaluate` event whose `raw` carries a
  fragment-assembled AWS key → `hit_count == 1`, hit `target ==
  "events.jsonl"`, rule `aws_access_key`, `credential_hits` gap present,
  `has_gaps` true.
- **Hit in context_extra**: `loop_runs.error` passed via `context_extra`
  containing a fake token → hit with `target == "context:loop_runs.error"`.
- **No-leak invariant (scanner-scoped)**: in both hit tests, the assembled
  fake token string does not appear in any `credential_scan.*` entry value
  nor in any `GapEntry.detail`. It **will** appear in
  `context_non_evidentiary` (verbatim by existing design — see Design ›
  Bundle-level leak); assert that too, so the test documents the boundary
  rather than accidentally passing on a fixture that never reaches the
  context section. This is the test that matters most.
- **No double counting**: a token present once in an `evaluate` event's
  `raw` yields exactly one hit (`events.jsonl`), not a second
  `context:evaluate.*` hit.
- **Missing run dir**: `assemble_bundle(row, None, {}, context_extra=[...])`
  still emits all four scalar `credential_scan.*` keys, still carries
  `loop_runs.error` in `context_non_evidentiary`, and a token in that error
  is reported as `context:loop_runs.error` alongside `missing_run_dir`.
- **Reproducibility with hits**: two `assemble_bundle` calls over the
  hit fixture produce byte-identical `canonical_json()`.
- **Exit code**: `cmd_evidence` over a hit fixture returns 2 and still
  writes `--output`; over a clean fixture returns 0.
- **Segregation**: `credential_scan.*` keys never appear in
  `context_non_evidentiary`; no `captured.`/`evaluate.` key gains the
  `"scanner"` source.

## Blocked By

None. Formerly blocked by `ENH-3469` (credential-pattern scanner in
`pii.py`, providing `scan_text`, `credential_rules_sha`, and
`CREDENTIAL_SCANNER_VERSION`) — that issue is now `done` and all three
exist in `pii.py` exactly as this issue's Program Design cites them
(confirmed 2026-09-14, see Integration Map findings).

## Scope Boundaries

In scope: wiring the ENH-3469 scanner into `assemble_bundle`/
`cmd_evidence`, the `credential_scan.*` entry shape, the `credential_hits`
gap and exit-code-2 behavior, and the doc/test updates listed in
Integration Map. Out of scope: see `## Out of Scope` below.

## Out of Scope

- `scanned_at` (dropped; see Design).
- The longitudinal `history.db` leakage signal (parent's third consumer) —
  not covered by either child; see ENH-3466 Resolution.
- Redacting matched spans inside `context_non_evidentiary` when hits are
  found. The bundle flags; it does not scrub. If wanted, file a follow-up
  that changes the context section's verbatim contract explicitly.

## Resolution

Implemented exactly as designed. `_scan_for_credentials()` (new, `evidence.py`)
scans the archived run-dir files (`state.json`/`events.jsonl`/`summary.json`/
`probe-*.json`, `errors="replace"`) plus `context_extra`'s string/stringifiable
entries with `little_loops.pii.scan_text`, emitting the five
`credential_scan.*` `EvidenceEntry` rows (`source="scanner"`) and a
`credential_hits` `GapEntry` on any hit — called on both the `missing_run_dir`
early-return path and the normal end of `assemble_bundle()`, so every bundle
carries a scan record. `context_extra` (renamed from the post-hoc
`bundle.context_non_evidentiary.extend(...)` in `cmd_evidence`) is now a
keyword-only `assemble_bundle()` parameter applied before the
`missing_run_dir` early return. `cmd_evidence` returns exit code `2` when
`credential_hits` is present (still writes `--output`/prints `--json`); exit
`1` remains "run not found." `scanned_at` was deliberately dropped per Design
— `version`/`rules_sha` already make scans comparable, and the
reproducibility invariant (`canonical_json()` byte-identical across reruns)
stands unchanged, now verified with a hit-bearing fixture too.

Added 11 new tests to `test_feat3182_evidence_bundle.py` (clean run, hit in
`events.jsonl`, hit in `context_extra`, no double counting, missing-run-dir
scan record, reproducibility with hits, segregation, exit-code-2) plus
extended the existing source-enforcement test for the `"scanner"` value.
Updated `docs/reference/CLI.md` and `docs/reference/API.md` per the
Integration Map. Full suite: `python -m pytest scripts/tests/` — 24276
passed, 51 skipped; the only 2 failures (`test_no_malformed_dependency_entries_in_repo`,
`test_no_new_unverifiable_evidence`) are pre-existing repo-gate issues in
unrelated issue files (ENH-3463/ENH-3464, ENH-3467), confirmed present on
unmodified `main` before this change.

## Status

**Done** | Created: 2026-09-13 | Priority: P1

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-14_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 89/100 → HIGH CONFIDENCE

_Updated 2026-09-14: `## Program Design` section added (reuses `EvidenceEntry`/
`GapEntry`, cites `evidence.py:193`/`:463`/`:505-506`); `ll-issues check-design
ENH-3470` now passes and the prior STOP — ADDRESS GAPS hard override is
resolved. Readiness moves from STOP to PROCEED WITH CAUTION on the remaining
concern below._

### Concerns
- _Superseded 2026-09-14 by `/ll:refine-issue`_: ENH-3469 (credential-pattern
  scanner in `pii.py`) is now `done` — `scan_text`, `credential_rules_sha`,
  and `CREDENTIAL_SCANNER_VERSION` all exist in `pii.py` exactly as this
  issue's Program Design cites them (confirmed against source). Criterion 5
  (Dependencies Satisfied) should no longer score 0 on this basis; the
  `blocked_by` vs. `depends_on` gate-inspection question below is now moot
  for this issue since the dependency has resolved, though it may still be
  worth raising as a general gate-coverage question elsewhere. A fresh
  `/ll:confidence-check` pass will recompute the readiness score.

## Session Log
- `/ll:manage-issue` - 2026-09-14T18:17:35 - `4b1da6cb-cda6-4875-933f-04e458d61037.jsonl`
- `/ll:ready-issue` - 2026-09-14T18:05:57 - `d435daa7-da8c-4618-a2cd-999e842b398f.jsonl`
- `/ll:confidence-check` - 2026-09-14T17:58:09 - `ed6df677-344b-44cd-8920-d8f25b2d204a.jsonl`
- `/ll:refine-issue` - 2026-09-14T17:45:45 - `e90ca231-3500-40d5-a5ba-5eac5bbda47d.jsonl`
- `/ll:confidence-check` - 2026-09-14T16:52:58 - `b233366b-10ab-4e31-a82f-311f95b747f5.jsonl`
- `/ll:issue-size-review` - 2026-09-13T17:50:41 - `d24791a3-28b5-4b07-851d-ac809549dbb5.jsonl`
- manual review - 2026-09-14 - scoped no-leak invariant to scanner output (context section is verbatim), dropped context-section rescan (double counting), emit scan entries on missing_run_dir path, context_extra before early return, explicit hits sort key, confirmed exit 2, doc gap-category updates
- manual review - 2026-09-13 - resolved scan target, dropped scanned_at, fixed entry shape/source/fail behavior, added no-leak test
