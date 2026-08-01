---
id: ENH-2961
title: format-check on a single issue ID emits deprecation warnings for every other
  issue in the corpus
type: ENH
priority: P4
status: done
captured_at: '2026-08-01T04:12:30Z'
completed_at: '2026-08-01T07:36:38Z'
discovered_date: 2026-08-01
discovered_by: capture-issue
labels:
- issues
- format-check
- cli
- ergonomics
confidence_score: 100
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-2961: Scope format-check's deprecation warnings to the targeted issue

## Summary

`ll-issues format-check <ID>` targets one issue but emits frontmatter-deprecation warnings for the entire corpus. For `ENH-2941` the run produces 22 lines, 21 of which are `deprecated frontmatter key 'parent_issue'` notices about unrelated FEAT-1081/1200-series files. The single line the user asked for scrolls off the top.

## Current Behavior

```
$ ll-issues format-check ENH-2941 2>&1 | wc -l
22
$ ll-issues format-check ENH-2941 2>&1 | grep -c "deprecated frontmatter key 'parent_issue'"
21
$ ll-issues format-check ENH-2941 2>/dev/null | wc -l
1
```

`cmd_format_check()` (`scripts/little_loops/cli/issues/format_check.py`) unconditionally calls `find_issues(config, status_filter=set(_ALL_STATUSES))` to build the `issue_statuses` map, regardless of whether one ID or a full sweep was requested. Parsing each file trips the deprecation logging in `issue_parser.py` (`deprecated frontmatter key 'parent_issue' — rename to 'parent'`, and its `target_branch`/`related` siblings).

Scope note: the warnings go to **stderr**, so stdout stays clean and piped/scripted consumers are unaffected. This is an interactive-ergonomics problem only, which is why it is filed P4 rather than as a bug.

## Expected Behavior

`format-check <ID>` prints its verdict plus any deprecation warnings **for that issue**. Warnings about other files are suppressed, or collapsed to a single summary line:

```
Formatted: ENH-2941 is structurally compliant
(21 other issues have deprecated frontmatter keys — run `ll-issues format-check` to list)
```

The full sweep (`ll-issues format-check` with no ID) keeps reporting everything, since there the warnings are on-topic.

## Motivation

`format-check <ID>` is the loop an author runs repeatedly while fixing one issue's structure — it ran four times in the session that surfaced this. At a 21:1 noise ratio the useful line is easy to miss, and the warnings are unactionable in that moment because they concern files the author is not editing. The deprecated keys are a real backlog item, but a single-ID check is the wrong place to surface them.

## Proposed Solution

The corpus load itself is **legitimate and must stay** — `issue_statuses` is what lets `check_format_gaps()` distinguish `prose_dep_drift` (dependency on an active issue) from `stale_prose_dep` (dependency on a done/cancelled one). Only the warning emission should be scoped. Options, cheapest first:

1. **Suppress during the status-map load** — wrap the `find_issues(...)` call that builds `issue_statuses` in a logging filter that drops the deprecation records, then parse the *targeted* issue normally so its own warnings still surface. Smallest diff; keeps warning text and levels untouched.
2. **Count and summarize** — capture the suppressed records and print a one-line tally as shown in Expected Behavior. Preserves discoverability of the backlog.
3. **Deduplicate globally** — emit each deprecated-key class once per run rather than once per file. Helps the full sweep too (currently 21 near-identical lines), but does not fully solve the single-ID case.

Recommend 1 + 2 together. If the warnings are wanted on demand, gate the full list behind an existing verbosity flag rather than adding a new one — check the current `ll-issues` flag surface before introducing anything.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Verbosity-flag question resolved**: no `--quiet`/`-v`/`--verbose` flag exists on `format-check`'s parser (`add_format_check_parser()`, `scripts/little_loops/cli/issues/format_check.py:14-56` — current flags are `issue_id`, `--all`/`-a`, `--format`/`-f`, `--fix`, `--apply`) or on **any** `ll-issues` subcommand (repo-wide grep across `cli/issues/*.py` for these flags returns zero matches). "Gate behind an existing verbosity flag" is not available as written — go with the tally-line summary (Option 2) alone; do not add a new flag for this pass.
- **Exact source location confirmed**: `cmd_format_check()` spans lines 106–215. The corpus-wide load is line 132 (`all_issues = find_issues(config, status_filter=set(_ALL_STATUSES))` → `issue_statuses = {...}`), executed unconditionally *before* the `if check_all:` branch at line 136. The single-ID path is lines 180–215; it resolves the target via `_resolve_issue_id(config, issue_id)` (line 183) and calls `check_format_gaps(...)` (line 188) using the same `issue_statuses` map built at line 132.
- **`format_check.py` has no logger of its own** — no `import logging` / `logging.getLogger(__name__)` anywhere in the file. Every warning the user sees is emitted by `issue_parser.py`'s module logger `little_loops.issue_parser` (`logger = logging.getLogger(__name__)`, line 26), via `_warn_deprecated_key()` (lines 43–70, `logger.warning(...)` at line 65), called from `IssueParser.parse_file()` at lines 1376 (`parent_issue`), 1381 (`target_branch`), 1388 (`related`).
- **Confirms the proposed approach is sound**: the targeted issue's own deprecated-key warnings (if any) fire through a *separate* parse — `_resolve_issue_id()` + `check_format_gaps()`'s own frontmatter read at line 188 — not through the line-132 `find_issues()` call. So wrapping only the line-132 call in a suppression contextmanager will not swallow the targeted issue's own warnings; they still surface normally.
- **`find_issues()` has no `only_ids`-based short-circuit before parsing** (`scripts/little_loops/issue_parser.py`, function starting line 1718): it calls `parser.parse_file(issue_file)` for every `*.md` in every category directory (lines 1795 and 1822–1823) *before* applying `_matches_status`/`_matches_filters`. `only_ids` only filters the already-parsed result list (line 1769) — it cannot be used to skip parsing other files, which is why the corpus-wide warnings fire even for a single-ID call.
- **No existing `logging.Filter` pattern in this codebase** (repo-wide grep for `logging.Filter`/`addFilter`/`removeFilter` returns zero hits). The closest reusable shape for "install temporarily, yield, guaranteed teardown" is the plain `@contextmanager` function `acquire_lock()` in `scripts/little_loops/file_utils.py` (no custom class) — supports the issue's own preference for a contextmanager over a `logging.Filter` subclass.
- **Tally-message precedent**: `cmd_check_open_questions()` in `scripts/little_loops/cli/issues/check_open_questions.py` prints a one-line `"{count} ...; run {command}"` advisory to stderr — model the new suppressed-count summary line after this shape.
- **Test pattern for asserting on the warnings**: `scripts/tests/test_issue_parser.py` uses `with caplog.at_level(logging.WARNING, logger="little_loops.issue_parser"):` around `parser.parse_file(...)`, then asserts on `caplog.records`. Reuse this in the new `test_ll_issues_format_check.py` cases. Note `_WARNED_DEPRECATED_KEYS` (line 40) is a **process-wide, once-per-file dedup ledger** reset per-test by the `autouse` fixture `_reset_deprecated_key_warnings()` in `scripts/tests/conftest.py:739-750` — new tests will pick this fixture up automatically, no extra wiring needed.
- **Out of scope, noted for awareness**: a second, independent warning emitter with the same shape but no dedup ledger exists at `scripts/little_loops/dependency_mapper/analysis.py:491-515` (`validate_frontmatter_fields()`). It is not triggered by `format-check`'s code path, so it's unaffected by this fix — flagging only in case a future consolidation pass wants to unify both emitters' suppression story.

## Integration Map

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/issues/format_check.py:106-215` — `cmd_format_check()`; the corpus-wide `find_issues(config, status_filter=set(_ALL_STATUSES))` call is line 132 (before the `if check_all:` branch at line 136); single-ID branch is lines 180-215
- `scripts/little_loops/issue_parser.py:43-70` — `_warn_deprecated_key()`, called from `IssueParser.parse_file()` at lines 1376/1381/1388; emits the three deprecation warnings (`parent_issue`, `target_branch`, `related`) on logger `little_loops.issue_parser`; no change to the warnings themselves
- `scripts/little_loops/issue_parser.py:1718` — `find_issues()`; unconditionally parses every file before filtering (lines 1795, 1822-1823) — the actual corpus-wide parse/warn trigger
- `scripts/little_loops/issue_progress.py:12` — `_ALL_STATUSES` constant imported by `format_check.py`
- `scripts/little_loops/file_utils.py` — `acquire_lock()`; closest existing `@contextmanager` precedent to model the new suppression contextmanager after
- Full-sweep behavior (no ID) must be preserved apart from any intentional dedup

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/__init__.py:54-56,857` — registers `add_format_check_parser`/`cmd_format_check` as the `format-check` subparser; no change needed, confirms this is the only registration site
- `scripts/little_loops/loops/rn-remediate.yaml:111-117` (`ensure_formatted` state) — calls `ll-issues format-check "$ID"` with no `--format json` and no stderr redirect, evaluated via `evaluate: {type: exit_code}`; verified the new tally line is exit-code-neutral (stderr-only addition), but this is the one caller that would actually *see* the new line if it inspected output — worth a sanity note in the PR, no code change required
- `scripts/little_loops/loops/autodev.yaml:1094,1593,1757` and `scripts/little_loops/loops/rn-remediate.yaml:1094-ish` (`--format json 2>/dev/null` call sites) — already redirect stderr, verified safe by construction, no change required

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `#### \`ll-issues format-check\`` section's flag table + Examples block documents the exact single-ID output shape; needs a line/example added describing the new stderr tally summary so the doc doesn't undersell what a single-ID run now prints

### Tests

- `scripts/tests/test_ll_issues_format_check.py` — add a case asserting a single-ID `format-check` on a corpus containing a deprecated-key file emits no warning for that unrelated file, and still emits one when the *targeted* issue itself carries a deprecated key. Use the `caplog.at_level(logging.WARNING, logger="little_loops.issue_parser")` pattern from `scripts/tests/test_issue_parser.py`
- Assert the full sweep still reports deprecated keys
- The `autouse` fixture `_reset_deprecated_key_warnings()` (`scripts/tests/conftest.py:739-750`) already resets the per-process dedup ledger between tests — no new fixture needed

_Wiring pass added by `/ll:wire-issue`:_
- Fixture design note: `_warn_deprecated_key()` dedupes once-per-process per `(resolved_path, old_key)` pair (`issue_parser.py:40-70`), so the "21 warnings" repro requires the corpus fixture to contain **several distinct other issues each with their own deprecated key** — a single other-issue fixture would only ever emit one warning regardless of how many times it's parsed. Size the test fixture accordingly (2+ separate deprecated-key-bearing issue files, not one file reused).
- Model the stderr-capture shape after `scripts/tests/test_ll_issues_format_check.py::TestFormatCheckIssueNotFound.test_not_found_exits_one` (lines 372-384) — the only existing test in this file already reading `err` via `capsys.readouterr()`.
- Verified no-change-needed (searched broadly for stderr/warning-count assertions against format-check): `scripts/tests/test_program_design_gate.py`, `scripts/tests/test_decide_issue_skill.py`, `scripts/tests/test_autodev_loop.py`, `scripts/tests/test_rn_remediate.py` (`TestFormatCheckGateEndToEnd` asserts exit code only), `scripts/tests/test_prose_dep_sweep_gate.py` — none assert on stderr line count/content, so none require updating for this change.

## Implementation Steps

1. ~~Confirm which `find_issues` call is the warning source~~ — confirmed: `cli/issues/format_check.py:132`, the `_ALL_STATUSES` status-map load (see Codebase Research Findings above), not the targeted-issue read at line 188.
2. Add a `_suppress_frontmatter_deprecations()` contextmanager (modeled on `acquire_lock()` in `file_utils.py`) around the line-132 call only, on the single-ID path (lines 180-215).
3. Tally suppressed records; print the summary line (styled after `check_open_questions.py`'s `cmd_check_open_questions()`) when the count is non-zero.
4. Add tests to `scripts/tests/test_ll_issues_format_check.py` using the `caplog.at_level(logging.WARNING, logger="little_loops.issue_parser")` pattern for both the single-ID and full-sweep paths; verify the full sweep is unchanged. Use a fixture with 2+ distinct deprecated-key-bearing issues (see Tests note above), not one file reused.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `docs/reference/CLI.md`'s `ll-issues format-check` section (flag table/Examples) to document the new stderr tally line.
6. Sanity-check `rn-remediate.yaml`'s `ensure_formatted` state (line ~111-117, exit-code-only evaluator, no stderr redirect) still passes — it's the one FSM caller with visibility into unredirected stderr, though no code change to the loop itself is expected.

## Program Design

### Types

No new types. A `logging.Filter` subclass (or a `contextlib.contextmanager` wrapping one) is sufficient; prefer the contextmanager so the suppression window is explicit and cannot leak past the status-map load.

### Signatures

- `_suppress_frontmatter_deprecations() -> Iterator[list[logging.LogRecord]]`
  - Contextmanager installing a filter on the `issue_parser` logger; yields the list of records it swallowed so the caller can tally them for the summary line.
- `cmd_format_check(config: BRConfig, args: Namespace) -> int`
  - Unchanged signature; wraps only the `_ALL_STATUSES` status-map load in the contextmanager, and only on the single-ID path.

### Call Path

- `cmd_format_check()` -> `find_issues()` -> `check_format_gaps()`

### Deviations

- 2026-08-01: `_suppress_frontmatter_deprecations()` gained a `keep: str | None = None`
  keyword-only parameter beyond the designed signature. Reason: the corpus-wide
  status-map load parses the *targeted* issue too (it's part of the corpus), and
  `issue_parser`'s once-per-process dedup ledger records that file as "already
  warned" the moment the (suppressed) warning fires during the corpus load —
  silently absorbing the warning before the target's own dedicated
  `check_format_gaps()` parse gets a chance to emit it. A test asserting the
  target's own deprecated-key warning still surfaces caught this. `keep` lets
  the filter pass the target's own records through live (matched by
  `path.name`) while still swallowing every other file's records, so the
  target's warning fires exactly once, in place, instead of relying on a
  second un-suppressed parse that the dedup ledger would silently skip.

## Scope Boundaries

- In scope: suppressing and tallying frontmatter-deprecation records emitted during the single-ID status-map load, the summary line, and tests for both the single-ID and full-sweep paths.
- Out of scope: the corpus scan itself (required for `prose_dep_drift` vs `stale_prose_dep` resolution), the deprecation warning text/levels in `issue_parser.py`, actually renaming the ~21 offending `parent_issue` keys, adding a new verbosity flag, and the `program_design_nonspecific` false negatives (BUG-2960).

## Impact

- **Priority**: P4 - Ergonomics only; stdout is already clean, so no tooling is broken
- **Effort**: Small - localized to one CLI module, no parser changes
- **Risk**: Low - suppression is scoped to a single code path; the full sweep is the regression to watch

## Status

**Open** | Created: 2026-08-01 | Priority: P4


## Session Log
- `/ll:manage-issue` - 2026-08-01T07:36:14 - `338df524-343e-4703-aeda-c50143cd0451.jsonl`
- `/ll:ready-issue` - 2026-08-01T07:22:42 - `4075b0a1-011e-46e1-8aec-a3b7fb5e9c53.jsonl`
- `/ll:confidence-check` - 2026-08-01T07:21:17 - `ea609e30-e603-4a17-a283-fe9770570550.jsonl`
- `/ll:wire-issue` - 2026-08-01T07:19:55 - `f947bfd7-390f-4015-936e-22ac6d0a8366.jsonl`
- `/ll:refine-issue` - 2026-08-01T07:14:51 - `c87febfc-5bf9-4571-b863-60e755840208.jsonl`
- `/ll:capture-issue` - 2026-08-01T04:14:35 - `955e48a5-4e30-44bc-914f-c2bd87008116.jsonl`
