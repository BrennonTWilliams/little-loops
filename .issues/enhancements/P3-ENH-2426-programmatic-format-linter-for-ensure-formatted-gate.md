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
- `scripts/little_loops/cli/issues/format_check.py` — **new file**, `cmd_format_check(config, args) -> int` modeled after `check_flag.py:13-33` (with `_resolve_issue_id` import from `cli/issues/show.py:39-124`, `BRConfig` under `TYPE_CHECKING`, heavy imports deferred inside the function)
- `scripts/little_loops/cli/issues/__init__.py` — register `format-check` (import at lines 22-57 or lazy at lines 796-799; `subs.add_parser` + `add_config_arg(format_check)` at lines 564-572 following `check-flag`; dispatch `if args.command == "format-check": return cmd_format_check(config, args)` near lines 774-777; epilog line at lines 65-134 between `fingerprint` and `decisions`)
- `scripts/little_loops/loops/rn-remediate.yaml` — rewire `ensure_formatted` gate body (lines 100-153) to call `ll-issues format-check "$ID"`; keep `evaluate: exit_code` routing and `format_issue` repair state at line 155-174 untouched

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_template.py` — `load_issue_sections` (source of `creation_template` / `deprecated` metadata; no change)
- `cli/issues/refine_status.py`, `cli/issues/show.py`, `cli/issues/next_action.py` — current `is_formatted()` callers; could optionally adopt the richer check later (out of scope here)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/check_flag.py:23` — canonical pattern for `_resolve_issue_id` import + `cmd_<name>(config, args) -> int` signature; `format-check` mirrors this structure [Agent 1]
- `scripts/little_loops/cli/issues/check_readiness.py:28` — second canonical pattern for the same shape [Agent 1]
- `scripts/little_loops/cli/issues/path_cmd.py`, `set_status.py`, `set_scores.py`, `skip.py`, `history_context.py` — additional `_resolve_issue_id` consumers confirming the shared-resolver convention; new `format-check` follows [Agent 1]
- `scripts/little_loops/sync.py:21,700` — also calls `load_issue_sections` (cached per-type for GitHub sync); shares the JSON shape but is unaffected by the new checker [Agent 1]
- `scripts/little_loops/cli/verify_package_data.py:55-66` — `LintResult`/`EscapeViolation` dataclasses and `_format_text_report`/`_format_json_report` formatters; second lint-style precedent for the new checker's report shape (alongside `EpicDrift`) [Agent 1, Agent 2]
- `scripts/little_loops/cli/issues/epic_consistency.py:33-67` — `EpicDrift` dataclass + `has_drift` property + `to_dict()` for `--format json`; **primary** model for the new `FormatGaps` dataclass [Agent 1, Agent 3]
- `scripts/little_loops/loops/rn-implement.yaml` — contains a separate `MISSING=$(...)` heredoc pattern in another state; shares the linter-rework value but is **out of scope** for this issue (file/awareness only) [Agent 1]

### Similar Patterns
- `is_formatted()` deprecated-skip loops (`issue_parser.py:86,89`) — the checker should share this logic, not re-implement it
- ENH-2398 added the same `deprecated` guard to the gate's inline Python — this issue supersedes that inline block with the subcommand call

### Tests
- `scripts/tests/test_rn_remediate.py::TestEnsureFormatted` (~line 1446) — extend `_run_gate()` cases: renamed/empty/boilerplate section → exit 1; fully-clean → exit 0
- New `scripts/tests/` unit tests for `ll-issues format-check` covering each gap class per type (bug/feat/enh/epic), plus fail-open on unresolved template / unreadable file

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_rn_remediate.py::_extract_gate_script` (lines 1461-1467) — **WILL BREAK** when the inline `MISSING=$(...)` heredoc is replaced with `ll-issues format-check "$ID"`. Hardcodes `action.find("MISSING=$(")` and asserts `"Could not locate MISSING=$( in ensure_formatted action"`. Replace with a shell that runs `subprocess.run(["python", "-m", "little_loops.cli", "ll-issues", "format-check", tmp_issue_id, "--config", str(tmp_path)])` or re-key to a shorter sentinel like `"ll-issues format-check"` [Agent 1, Agent 3]
- `scripts/tests/test_ll_issues_format_check.py` — **new file**, modeled after `test_ll_issues_sections.py` (`_invoke()` at line 19, `_write_config()`, `sample_config` from conftest) + `test_epic_consistency.py` (class-per-gap-class structure with `_write_epic()`/`_write_child()` helpers at lines 31-53). Suggested classes: `TestFormatCheckClean`, `TestFormatCheckRenamed`, `TestFormatCheckEmpty`, `TestFormatCheckBoilerplate`, `TestFormatCheckJsonOutput`, `TestFormatCheckIssueNotFound`, `TestFormatCheckFailOpen` [Agent 3]
- `scripts/tests/test_issue_parser.py::TestFormatGradedChecker` — **new class** beside `TestIsFormatted` (line 3130), direct-Python tests mirroring the `_make_issue` / `tmp_path` / `TEMPLATES_DIR` pattern. Suggested tests: `test_renamed_deprecated_section_reports_renamed`, `test_empty_required_section_reports_empty`, `test_boilerplate_body_reports_boilerplate`, `test_clean_issue_returns_empty_gap_list`, `test_template_load_failure_returns_empty_gap_list` (fail-open mirror of `is_formatted()` lines 64-67) [Agent 3]
- `scripts/tests/test_rn_remediate.py::TestEnsureFormatted` — extend existing class with new gap-class cases: `test_renamed_section_exits_1` (use `## Reproduction Steps` from `feat-sections.json:9-25`), `test_empty_section_exits_1`, `test_boilerplate_only_section_exits_1`, `test_clean_issue_exits_0`. Copy `creation_template` strings verbatim from `templates/bug-sections.json` for fixture bodies [Agent 3]
- `scripts/tests/test_builtin_loops.py::TestRnRemediateEnsureFormatted` — **optional symmetric class** beside `TestRnRemediateFormatIssue` (line 7823), using the `LOOP_FILE = BUILTIN_LOOPS_DIR / "rn-remediate.yaml"` fixture (line 7717) to YAML-load and assert the `evaluate: exit_code` routing contract on the rewired gate [Agent 3]
- `scripts/tests/test_refine_status.py::TestIssuesCLIRefineStatus` (line ~1204) — **stays valid**, indirect coverage via `is_formatted()` (which is unchanged); confirm no assertions break after refactor [Agent 3]
- `scripts/tests/test_next_action.py::test_needs_format` (line 68) — **stays valid**, indirect coverage via `is_formatted()` (which is unchanged); confirm `NEEDS_FORMAT BUG-001` exit-code assertion still holds [Agent 3]
- `scripts/tests/test_show.py` — direct tests of `_resolve_issue_id` (line 50 test class); ensure the shared resolver behaves identically for the new subcommand [Agent 1]
- `scripts/tests/conftest.py` — `temp_project_dir` (line 130), `make_project` (line 140), `sample_config` (line 189), `config_file` (line 244), `issues_dir` (line 252) are the fixtures `test_ll_issues_format_check.py` should reuse; no new conftest additions needed [Agent 3]

### Documentation
- `docs/reference/API.md` — document the new checker and `ll-issues format-check`
- `.claude/CLAUDE.md` — add `format-check` to the `ll-issues` subcommand list

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — **missing from existing plan**; the new `ll-issues format-check` entry must land beside `ll-issues check-flag / ll-issues cf` at line 1379 (and example invocations at line 1390). The CLI.md file is the user-facing reference for `ll-issues` subcommands and is the parallel doc to API.md for the Python surface [Agent 2]
- `skills/format-issue/SKILL.md:344-346` — the prose "This programmatic write guarantees `is_formatted()` returns `True` for this issue in subsequent `ll-issues refine-status` calls" describes the **Criterion-1 session-log shortcut** that the new graded checker intentionally **does not honor** (per the issue's Codebase Research at line 192-201). Optional: add a sentence clarifying that the deterministic gate uses the richer structural check, so post-`format-issue` issues still get graded. No code change required [Agent 2]
- `CHANGELOG.md` — entry needed at release prep. **Do not place under `[Unreleased]`**; promote to a concrete `## [X.Y.Z] - DATE` section per project memory `feedback_changelog_no_unreleased.md`. The previous `ensure_formatted` gate change entry (ENH-2398) lives at line 96; the new entry should sit beside it [Agent 2]

### Configuration
- N/A

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_parser.py` `__all__` — per ENH-507 (`P5-ENH-507-add-all-exports-to-public-root-modules.md:149`), the new graded checker should be added to the `__all__` list alongside `"is_formatted"`. Cosmetic; out of scope for this issue's PR but flagged for the ENH-507 follow-on to land complete [Agent 2]
- `config-schema.json:130` — only contains a `format-issue` mention in the `capture_template` enum description. **No schema change needed** for the new subcommand (no new config keys introduced); confirm the description prose is not paraphrased in a way that contradicts the new subcommand [Agent 2]

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Replace `scripts/tests/test_rn_remediate.py::_extract_gate_script` (lines 1461-1467) — currently hardcodes `action.find("MISSING=$(")`; re-key to a `"ll-issues format-check"` sentinel or invoke `main_issues(["ll-issues", "format-check", issue_id, "--config", tmp_path])` via `subprocess.run` instead of running the inline heredoc.
7. Create `scripts/tests/test_ll_issues_format_check.py` — new file with class-per-gap-class structure (`TestFormatCheckClean`/`Renamed`/`Empty`/`Boilerplate`/`JsonOutput`/`IssueNotFound`/`FailOpen`); reuse `_invoke()` from `test_ll_issues_sections.py:19` and the conftest fixtures (`temp_project_dir`, `sample_config`, `config_file`).
8. Add `scripts/tests/test_issue_parser.py::TestFormatGradedChecker` — direct-Python tests beside `TestIsFormatted` (line 3130), one per gap class, plus a `test_clean_issue_returns_empty_gap_list` and `test_template_load_failure_returns_empty_gap_list` (fail-open mirror of `is_formatted()` lines 64-67).
9. Extend `scripts/tests/test_rn_remediate.py::TestEnsureFormatted` with renamed/empty/boilerplate/clean cases; copy `creation_template` strings verbatim from `templates/bug-sections.json` for fixture bodies.
10. Add `scripts/reference/CLI.md` `ll-issues format-check` entry beside `ll-issues check-flag / ll-issues cf` at line 1379 (with example invocations near line 1390).
11. Update `docs/reference/API.md` to document the new graded checker beside `#### is_formatted` at line 791; keep `is_formatted()` semantics section intact (function is unchanged).
12. Update `.claude/CLAUDE.md` `ll-issues` subcommand list — add `format-check` alongside `fingerprint`/`decisions` (the project commands reference).
13. Add CHANGELOG entry at release prep (not under `[Unreleased]`); site at the `[X.Y.Z] - DATE` section beside the ENH-2398 entry at `CHANGELOG.md:96`.
14. Optional: add `scripts/little_loops/issue_parser.py` `__all__` entry for the new checker per ENH-507 (`P5-ENH-507-add-all-exports-to-public-root-modules.md:149`); cosmetic for this PR, completes the ENH-507 follow-on.
15. Optional: clarify `skills/format-issue/SKILL.md:344-346` prose so the post-`format-issue` Criterion-1 shortcut is not confused with the deterministic gate behavior (gate intentionally does not honor the session-log shortcut).

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
- `/ll:wire-issue` - 2026-07-02T02:26:48 - `c3a7f0c3-4e31-4aac-86c9-4c5dbb847636.jsonl`
- `/ll:confidence-check` - 2026-07-01T00:00:00 - `a2e654ea-d551-40b4-8922-3942a9e835f3.jsonl`
- `/ll:refine-issue` - 2026-07-01T18:23:28 - `9f1c67b2-4389-4a41-9eca-2017def791ef.jsonl`
- `/ll:format-issue` - 2026-07-01T18:15:41 - `771898ce-5217-4c16-8aa1-2394b36bffd0.jsonl`
- `/ll:capture-issue` - 2026-07-01T18:13:20Z - `9f1c67b2-4389-4a41-9eca-2017def791ef.jsonl`
</content>
