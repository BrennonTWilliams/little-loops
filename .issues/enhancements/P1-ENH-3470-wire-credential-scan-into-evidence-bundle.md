---
id: 3470
title: Wire credential scan into the FEAT-3182 EvidenceBundle
type: ENH
priority: P1
status: open
discovered_date: '2026-09-13'
parent: ENH-3466
depends_on:
- 3469
labels:
- goal-7,security,verification
decision_needed: false
confidence_score: 80
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-3470: Wire credential scan into the FEAT-3182 EvidenceBundle

## Summary

Add `credential_scan.*` entries to `EvidenceBundle`
(`scripts/little_loops/cli/loop/evidence.py`), backed by the scanner built
in ENH-3469 (blocked on it — this issue calls the scanner, it does not
build it). The bundle re-reads the **archived run-directory files and its
own non-evidentiary context section**, records `tool`/`version`/`rules_sha`
and redacted hits, and turns any hit into an explicit `GapEntry` plus a
non-zero exit from `ll-loop evidence`. No `scanned_at` field is added: the
bundle's byte-identical reproducibility invariant stands unchanged.

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
2. **`context_non_evidentiary`**: every `ContextEntry.value` (stringified
   via `json.dumps(value, sort_keys=True, default=str)` when not already a
   `str`), scanned after the section is complete.

The `loop_runs.error`/`evaluator_score` context entries are currently
appended by `cmd_evidence` **after** `assemble_bundle` returns
(`evidence.py:506`). Move that `extend` into `assemble_bundle` via a new
`context_extra: list[ContextEntry] | None = None` parameter so the scan
sees the full section; `cmd_evidence` passes what it already computes.

### Entry shape

Flat keys with scalar values, matching the existing convention
(`file.state.json.sha256`, `probe_file_count`), all with a new `source`
value `"scanner"`:

| key | value |
|---|---|
| `credential_scan.tool` | `"little_loops.pii"` |
| `credential_scan.version` | `CREDENTIAL_SCANNER_VERSION` (int) |
| `credential_scan.rules_sha` | `credential_rules_sha()` |
| `credential_scan.hit_count` | int |
| `credential_scan.hits` | list of `{"target", "line", "rule", "fingerprint"}`, sorted |

`target` is the run-dir file name (`events.jsonl`) or the context key
(`context:evaluate.probe-1.raw`). **No excerpt, ever** — `CredentialFinding`
has no excerpt field by design (ENH-3469); do not reconstruct one here.

Append these entries in `assemble_bundle` as the last evidentiary step,
after the `context_non_evidentiary` section is fully built. When the run
dir is missing the function already returns early with `missing_run_dir`;
no `credential_scan.*` entries are emitted in that case (absence is the gap,
same as every other run-dir-derived fact).

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
  `credential_scan.*` keys to the "Bundle shape" list, and document exit
  code 2.
- `docs/reference/API.md:4504-4568` — `assemble_bundle` signature
  (`context_extra`), the fourth source value, the `credential_scan.*` entry
  keys, and the no-excerpt rule.
- `docs/ARCHITECTURE.md` — no direct bundle-shape reference found; no
  change expected.

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
and `run_dir.glob("probe-*.json")`) and each `ContextEntry.value`, call
`scan_text` (ENH-3469) → any hit appends an `EvidenceEntry` with
`source="scanner"` and a `GapEntry("credential_hits", ...)` (`GapEntry` —
`evidence.py:82`) → back in `cmd_evidence`, `bundle.has_gaps`
(`EvidenceBundle.has_gaps` — `evidence.py:102`) is checked to select exit
code `2` instead of the existing `return 0` (`evidence.py:521`).

### Decision Rules

N/A — no new classification logic; `hit_count > 0` is the only branch,
already covered under Design › Fail behavior.

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
- **No-leak invariant**: in both hit tests, the assembled fake token string
  does not appear anywhere in `canonical_json()`. This is the test that
  matters most.
- **Reproducibility with hits**: two `assemble_bundle` calls over the
  hit fixture produce byte-identical `canonical_json()`.
- **Exit code**: `cmd_evidence` over a hit fixture returns 2 and still
  writes `--output`; over a clean fixture returns 0.
- **Segregation**: `credential_scan.*` keys never appear in
  `context_non_evidentiary`; no `captured.`/`evaluate.` key gains the
  `"scanner"` source.

## Blocked By

ENH-3469 (credential-pattern scanner in `pii.py`) — this issue imports
`scan_text`, `credential_rules_sha`, and `CREDENTIAL_SCANNER_VERSION`; it
cannot be implemented until those exist.

## Out of Scope

- `scanned_at` (dropped; see Design).
- The longitudinal `history.db` leakage signal (parent's third consumer) —
  not covered by either child; see ENH-3466 Resolution.

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
- Critical dependency still unresolved: ENH-3469 (credential-pattern scanner
  in `pii.py`) is still `open`; this issue's design imports `scan_text`,
  `credential_rules_sha`, and `CREDENTIAL_SCANNER_VERSION` from it and cannot
  be implemented until ENH-3469 lands. Criterion 5 (Dependencies Satisfied) is
  scored 0 on this basis.
- That dependency is tracked via `depends_on: [3469]` in frontmatter, not
  `blocked_by`. The BUG-3051 Dependencies Hard Override (Phase 1.7) only
  inspects `blocked_by`, so it stays inert here despite the dependency being
  genuinely blocking. Consider adding `blocked_by: [3469]` alongside
  `depends_on` so this gate (and `ll-auto`'s pre-flight check) catch it
  automatically instead of relying on the prose `## Blocked By` section.

## Session Log
- `/ll:confidence-check` - 2026-09-14T16:52:58 - `b233366b-10ab-4e31-a82f-311f95b747f5.jsonl`
- `/ll:issue-size-review` - 2026-09-13T17:50:41 - `d24791a3-28b5-4b07-851d-ac809549dbb5.jsonl`
- manual review - 2026-09-13 - resolved scan target, dropped scanned_at, fixed entry shape/source/fail behavior, added no-leak test
