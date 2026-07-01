---
id: ENH-2426
title: Fully programmatic issue-format linter (renamed/empty/boilerplate) for the
  ensure_formatted gate
type: enhancement
status: open
priority: P3
captured_at: '2026-07-01T18:13:20Z'
discovered_date: 2026-07-01
discovered_by: capture-issue
relates_to:
- ENH-2360
- ENH-2398
labels:
- rn-remediate
- format-guard
- ll-issues
decision_needed: false
confidence_score: 100
outcome_confidence: 85
score_complexity: 17
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 23
---

# ENH-2426: Fully programmatic issue-format linter (renamed/empty/boilerplate) for the ensure_formatted gate

## Summary

Replace the `ensure_formatted` Phase-0 gate's inline "missing required header"
check (`scripts/little_loops/loops/rn-remediate.yaml`) with a fuller, still
fully-deterministic linter that also catches **renamed**, **empty**, and
**boilerplate-but-present** sections — surfaced as a reusable
`ll-issues format-check <ID>` subcommand. This is the follow-on ENH-2360
explicitly deferred, done programmatically from template metadata instead of via
the token-costing LLM `/ll:format-issue --check` mode.

## Motivation

ENH-2360's own Scope Boundaries names this gap:

> "The deterministic gate catches **missing** required headers only. It does not
> catch renamed, empty, or boilerplate-only sections; those still reach `assess`.
> If malformed-but-not-missing issues later skew scores, the documented follow-on
> is to swap the gate body for a `/ll:format-issue --check` slash_command
> pre-pass."

That documented follow-on uses the **LLM** `--check` mode, which spends tokens on
every gate hit. Every signal the check needs is actually derivable from template
metadata that `ll-issues sections` already returns, so the check can be fully
deterministic (no LLM). The value is correctness, not raw token savings on the
format step: today a boilerplate- or renamed-but-present issue **passes** the gate
and wastes a downstream `/ll:confidence-check` (`assess`) pass — plus the whole
`diagnose → remediate → converge` chain — scoring a malformed issue (garbage-in).
A deterministic linter catches it up front and routes it to `/ll:format-issue`
only when genuinely needed.

## Current Behavior

The `ensure_formatted` gate builds a required-section list and greps for each
`## <title>`. It flags a section only when the header is **absent**. A section
that is present but renamed to a deprecated title, empty, or still holding its
`creation_template` boilerplate passes the gate and reaches `assess`.

`issue_parser.py:is_formatted()` (`issue_parser.py:45`) has the same limitation —
Criterion 2 is a pure required-headers-present subset check.

## Expected Behavior

A deterministic checker (no LLM) grades an issue against its type template and
reports per-gap findings, keyed off metadata `ll-issues sections` already exposes:

| Gap class | Deterministic signal |
|-----------|----------------------|
| Missing (today) | `required: true` / `level: required`, header absent |
| Renamed / stale | a `deprecated: true` section header is present (e.g. `Reproduction Steps`, `Proposed Fix`) |
| Empty | header present, body whitespace-only until the next `##` |
| Boilerplate-but-present | body equals (or is only placeholder tokens of) the section's `creation_template` |

- Exit 0 when structurally compliant; exit 1 with a per-gap report otherwise
  (`renamed: X→Y`, `empty: Z`, `boilerplate: W`) — compatible with the gate's
  existing `evaluate: type: exit_code` routing.
- Content-**quality** judgments (vague / untestable / contradiction, skill Step
  3.5) and content **inference/generation** (skill Step 3.6) stay with the LLM
  skill — the linter gates *whether* to run the skill, it does not replace the
  skill's repair work.

## Scope Boundaries

- **In scope**: a deterministic structural linter (missing + renamed + empty +
  boilerplate) exposed as `ll-issues format-check`, and rewiring the
  `ensure_formatted` gate to call it.
- **Out of scope**: replacing the LLM content-quality pass or the content
  inference/generation in `/ll:format-issue`; changing what "required" means
  (ENH-2398 already aligned the `deprecated` handling).
- **Conservative boilerplate detection**: flag only when the *entire* section body
  is placeholder (matches the gate's fail-open philosophy), to avoid false
  positives on a legit section that contains one `TBD` sub-bullet.

## Proposed Solution

1. Extend `issue_parser.py` (near `is_formatted()`, `issue_parser.py:45`) with a
   graded checker returning structured gaps, reusing the same template-loading and
   `deprecated`-skipping logic `is_formatted()` already has (`issue_parser.py:86,89`).
   - **Renamed**: a section title present in the body that is a `deprecated: true`
     key in the template → report `renamed: <old> → <canonical>` (canonical from
     `deprecation_reason` / v2.0 mapping where available).
   - **Empty**: required header present, body between it and the next `##` is
     whitespace-only.
   - **Boilerplate**: body normalizes to the section's `creation_template` (or is
     only placeholder tokens `TBD`, `[…]`, `N/A`).
2. Add `ll-issues format-check <ID>` (exit 0/1 + per-gap report). Prefer a new
   subcommand over more inline heredoc so it is unit-testable and reusable.
3. Swap the `ensure_formatted` gate body (`rn-remediate.yaml:100-153`) to call
   `ll-issues format-check`, keeping `evaluate: exit_code` and the existing
   `on_yes: assess` / `on_no: format_issue` routing (still at most one format pass,
   no oscillation).

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — add graded structural checker beside `is_formatted()`
- `scripts/little_loops/cli/issues/` — new `format-check` subcommand (register in `cli/issues/__init__.py`)
- `scripts/little_loops/loops/rn-remediate.yaml` — rewire `ensure_formatted` gate body to call `ll-issues format-check`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_template.py` — `load_issue_sections` (source of `creation_template` / `deprecated` metadata; no change)
- `cli/issues/refine_status.py`, `cli/issues/show.py`, `cli/issues/next_action.py` — current `is_formatted()` callers; could optionally adopt the richer check later (out of scope here)

### Similar Patterns
- `is_formatted()` deprecated-skip loops (`issue_parser.py:86,89`) — the checker should share this logic, not re-implement it
- ENH-2398 added the same `deprecated` guard to the gate's inline Python — this issue supersedes that inline block with the subcommand call

### Tests
- `scripts/tests/test_rn_remediate.py::TestEnsureFormatted` (~line 1446) — extend `_run_gate()` cases: renamed/empty/boilerplate section → exit 1; fully-clean → exit 0
- New `scripts/tests/` unit tests for `ll-issues format-check` covering each gap class per type (bug/feat/enh/epic), plus fail-open on unresolved template / unreadable file

### Documentation
- `docs/reference/API.md` — document the new checker and `ll-issues format-check`
- `.claude/CLAUDE.md` — add `format-check` to the `ll-issues` subcommand list

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (2026-07-01):_

**Cited line numbers verified accurate** — `issue_parser.py:45` (`is_formatted()` def),
`issue_parser.py:86,89` (the two `and not defn.get("deprecated", False)` skip clauses —
one in the `common_sections` loop keyed on `required is True`, one in the
`type_sections` loop keyed on `level == "required"`), and `rn-remediate.yaml:100-153`
(the gate's `action_type`/`action`/`evaluate`/routing body) all match the current files
exactly. The Tests reference `TestEnsureFormatted (~line 1446)` is now at **line 1450**
(approximate, not a hard mismatch).

**Report shape — model after `epic_consistency.py`** (`cli/issues/epic_consistency.py`):
the `EpicDrift` dataclass is the closest existing template for a per-gap report. It uses
one `list[str]` field per gap category (`missing_from_body`, `body_without_parent`, …), a
derived `has_drift` property that folds all categories into the exit-code decision, and a
`to_dict()` companion for `--format json`. Map `renamed`/`empty`/`boilerplate` onto three
such `list[str]` fields; return `0 if not has_gaps else 1`. `verify_package_data.py`
(`LintResult`/`EscapeViolation` + `_format_text_report()`/`_format_json_report()`) is a
second lint-style precedent with an explicitly documented exit-code contract in its
`--help` epilog.

**Subcommand skeleton — model after `check_flag.py`** (`cli/issues/check_flag.py`):
universal signature is `cmd_<name>(config: BRConfig, args: argparse.Namespace) -> int`;
`BRConfig` imported under `TYPE_CHECKING`, heavier imports deferred inside the function.
Resolve the issue ID via the shared `_resolve_issue_id(config, args.issue_id)` imported
from `cli/issues/show.py` (lines 39–124; the canonical ID→`Path` resolver every
ID-taking subcommand reuses — do **not** re-implement lookup). Not-found → print to
`sys.stderr`, return `1`.

**Registration triple in `cli/issues/__init__.py:main_issues()`** (needed for the new
subcommand): (a) import `cmd_format_check` alongside the other `cmd_*` imports (lines
23–24) or lazily at the dispatch site (the `sections` subcommand does this at lines
796–799 — both styles coexist); (b) `subs.add_parser("format-check", …)` + `add_config_arg`
following `check-flag` at lines 564–572; (c) dispatch `if args.command == "format-check":
return cmd_format_check(config, args)` near lines 774–777; (d) add a line to the epilog
subcommand list (lines 65–134).

**Boilerplate detection source of truth**: `creation_template` is read in exactly one
other place — `issue_template.py:_append_section()` (line 160):
`content.get(section_name, section_def.get("creation_template", ""))`. This confirms the
JSON shape (`section_def["creation_template"]`) the boilerplate comparator reads. Neither
`is_formatted()` nor the current gate reads `creation_template` or `deprecation_reason`
today, so both the boilerplate-body compare and the `renamed: <old> → <canonical>`
mapping (via `deprecation_reason`) are net-new reads, not rewires.

**Design consideration — Criterion-1 session-log shortcut (not in the issue).**
`is_formatted()` short-circuits to `True` at lines 69–71 whenever `/ll:format-issue`
appears anywhere in the parsed session log, *before* any structural check. Since ENH-2426
exists specifically to catch malformed-but-present issues that slipped past — and every
issue that reaches the gate has already run `/ll:format-issue` (so the shortcut would
always fire) — the new graded checker should **not** honor this shortcut; it must always
run the structural analysis. Sharing `is_formatted()`'s template-load + deprecated-skip
logic is still correct, but the Criterion-1 early return must be excluded from the shared
path (extract the load+skip into a helper both call, rather than calling `is_formatted()`
itself).

**`load_issue_sections()` data shape** (`issue_template.py:66`): returns the raw parsed
`{type}-sections.json` dict (raises `FileNotFoundError` if absent — callers add fail-open).
`common_sections` entries use a boolean `required` key; `type_sections` entries use a
string `level` key (`== "required"`) — this asymmetry is why the skip logic is two loops,
not one. `deprecated` is a per-section bool; `deprecation_reason` carries the canonical
rename target for the `renamed:` report.

**Test models**: for the new `format-check` subcommand module, model on
`scripts/tests/test_ll_issues_sections.py` (the `_invoke()` helper +
`patch.object(sys, "argv", [...])` pattern) and `scripts/tests/test_epic_consistency.py`
(fixture-built temp issue files + `main_issues()` exit-code assertions). For direct-Python
unit tests of the graded checker, model on `test_issue_parser.py::TestIsFormatted`
(line 3130; passes a real `templates_dir`). The gate rewire extends
`test_rn_remediate.py::TestEnsureFormatted` (line 1450) — note its `_extract_gate_script()`
currently keys off `MISSING=$(`; once the gate body becomes an `ll-issues format-check`
call, that extraction helper must be updated (or replaced with a `main_issues()`-invoked
assertion) since the inline `MISSING=$(` heredoc goes away.

## Implementation Steps

1. Add the graded structural checker to `issue_parser.py`, reusing `is_formatted()`'s template load + `deprecated` skip.
2. Implement renamed / empty / boilerplate detection (conservative: whole-body placeholder only).
3. Expose `ll-issues format-check <ID>` (exit 0/1 + per-gap report).
4. Rewire the `ensure_formatted` gate to call it; keep `evaluate: exit_code` routing.
5. Add unit tests (per gap class, per type) and extend `TestEnsureFormatted`; run `ll-loop validate` on `rn-remediate`.

## Impact

- **Priority**: P3 — Quality/correctness improvement; prevents malformed-but-present issues from wasting an LLM `assess` pass and mis-routing the remediation chain.
- **Effort**: Medium — new checker + subcommand + tests + one gate rewire; logic is deterministic and template-driven.
- **Risk**: Low — deterministic, fail-open, bounded to one format pass; the LLM repair path is unchanged. Main risk is boilerplate false-positives, mitigated by the whole-body-only rule.
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-07-01 | Priority: P3

## Session Log
- `/ll:confidence-check` - 2026-07-01T00:00:00 - `a2e654ea-d551-40b4-8922-3942a9e835f3.jsonl`
- `/ll:refine-issue` - 2026-07-01T18:23:28 - `9f1c67b2-4389-4a41-9eca-2017def791ef.jsonl`
- `/ll:format-issue` - 2026-07-01T18:15:41 - `771898ce-5217-4c16-8aa1-2394b36bffd0.jsonl`
- `/ll:capture-issue` - 2026-07-01T18:13:20Z - `9f1c67b2-4389-4a41-9eca-2017def791ef.jsonl`
</content>
