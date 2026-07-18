---
id: ENH-2678
title: Wire go-no-go correction_penalty into scoring + add ll-config get CLI
status: open
priority: P3
type: ENH
discovered_date: 2026-07-18
discovered_by: ll:decide-issue
labels:
- history-db
- config
decision_needed: false
parent: ENH-2677
relates_to:
- ENH-2677
confidence_score: 100
outcome_confidence: 83
score_complexity: 17
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 22
---

# ENH-2678: Wire go-no-go correction_penalty into scoring + add ll-config get CLI

## Summary

Follow-up to ENH-2677, which was closed as substantially already implemented
(schema, `HistoryConfig` dataclass, `BRConfig.history` property, and the
`analysis.evolution.*` → `history.evolution.*` namespace migration were all
already done under prior ENH-1913/1907/1914 work). Two concrete gaps remained
unaddressed and are scoped here.

## Problem

1. **`correction_penalty` is not consumed at runtime.** `GoNoGoConfig.correction_penalty`
   (`scripts/little_loops/config/features.py:989`, default `-0.2`) is
   schema-exposed and round-tripped in `to_dict()`
   (`scripts/little_loops/config/core.py:745`), but `skills/go-no-go/SKILL.md:145`
   only references it as prose (`{{config.history.go_no_go.correction_penalty}}`)
   describing what the judge agent *should* weigh. No Python code path reads
   `.history.go_no_go.correction_penalty` and applies it to a score.

2. **No `ll-config get <key>` CLI.** `scripts/pyproject.toml`'s
   `[project.scripts]` has no `ll-config` entry point and no `main_config`-style
   function exists under `little_loops.cli`. The closest primitive is
   `BRConfig.resolve_variable(var_path: str)`
   (`scripts/little_loops/config/core.py:830-852`), which walks a dot-path
   through `to_dict()` but is currently only consumed internally by
   `scripts/little_loops/skill_expander.py` for template variable substitution
   — not exposed as a standalone CLI a skill could shell out to.

## Current Behavior

`GoNoGoConfig.correction_penalty` is schema-exposed and round-tripped through
`BRConfig.to_dict()`, but the only reference to it is the unexpanded prose
token `{{config.history.go_no_go.correction_penalty}}` in
`skills/go-no-go/SKILL.md:145` — that token is never substituted outside
`ll-auto`'s `skill_expander.py` pre-expansion pass, so interactive/slash-command
runs of `/ll:go-no-go` never see a resolved value. Separately, there is no
`ll-config get <key>` CLI; `BRConfig.resolve_variable()` exists as the
underlying primitive but is only invoked internally by `skill_expander.py`,
so no skill can shell out to resolve a config value on demand.

## Expected Behavior

The go-no-go judge agent reads the resolved `correction_penalty` value (via a
new `ll-config get history.go_no_go.correction_penalty` CLI call, matching the
"config is read only in Python, never in markdown skills" convention) and
factors it into the GO/NO-GO verdict as a qualitative signal. A general-purpose
`ll-config get <key>` CLI exists, wrapping `BRConfig.resolve_variable()` with
the same never-raise, config-or-default contract as other `ll-*` config
readers, and is documented alongside the other CLI tools. The stale
`analysis.evolution.*` references in `skills/analyze-history/SKILL.md` are
updated to `history.evolution.*`.

## Impact

- **Priority**: P3 - narrow follow-up scoped from ENH-2677; not blocking
  other work, but leaves a documented config value silently inert until fixed
- **Effort**: Small - new CLI wraps an existing, already-tested primitive
  (`resolve_variable()`); skill edits are prose-only
- **Risk**: Low - additive CLI entry point and prose changes to two skill
  files; no changes to existing config schema or scoring logic paths
- **Breaking Change**: No

## Additional scope note

`skills/analyze-history/SKILL.md:143,158` still references the stale
`analysis.evolution.*` namespace in prose and should be updated to
`history.evolution.*` as part of this issue (found during ENH-2677's
decision review).

## Proposed Implementation

1. Add a `main_config()` CLI entry point (`ll-config`) wrapping
   `BRConfig.resolve_variable()`, following the `AnalyticsCaptureConfig`/
   `HistoryConfig` "config-or-default, never-raise" contract. Register it in
   `scripts/pyproject.toml`'s `[project.scripts]`.
2. Wire `GoNoGoConfig.correction_penalty` into the go-no-go skill's actual
   scoring path — either via a Python entry point the skill shells out to
   (matching the `history.* is read only in Python, never in markdown skills`
   convention from ENH-2677), or by having the judge agent's prompt read the
   resolved value through the new `ll-config get` CLI.
3. Update `skills/analyze-history/SKILL.md:143,158` from `analysis.evolution.*`
   to `history.evolution.*`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation:_

4. Add a `### ll-config` section to `docs/reference/CLI.md` and a one-line
   catalog entry to `commands/help.md` — this repo's doc-wiring convention for
   every new `ll-*` CLI, gated by `scripts/tests/test_wiring_cli_registry.py`
5. Bump `"38 typed CLI tools"` → `"39 typed CLI tools"` in `README.md:178` and
   update the matching tuple in
   `scripts/tests/test_wiring_guides_and_meta.py:86`
6. Add `ll-config` `DOC_STRINGS_PRESENT` tuples to
   `scripts/tests/test_wiring_cli_registry.py` so the new doc entries in step 4
   are test-enforced

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **No numeric score exists in `skills/go-no-go/SKILL.md` today.** The entire
  verdict is prose-driven: Step 3d's judge agent (lines 269-330) outputs a
  free-text `VERDICT: [GO | NO-GO]` and `NO-GO REASON: [...]`; there is no
  `score`/`confidence` variable anywhere in the skill's Phase 1-5 pseudocode.
  "Wiring `correction_penalty` into scoring" therefore cannot adjust an
  existing numeric score — it can only have the judge agent read the
  *resolved* penalty value and use it as an additional qualitative input to
  its GO/NO-GO judgment. `Phase 5` (Check Mode, line 439) branches only on the
  literal `GO`/`NO-GO` string, so resolving the value via the new
  `ll-config get` CLI and handing the actual number (not the literal
  `{{config...}}` token) to the judge is the minimal-blast-radius fix and
  matches sub-bullet 2 of Proposed Implementation above.
- `BRConfig.resolve_variable()` (`scripts/little_loops/config/core.py:830-852`)
  never raises — unknown paths return `None`, list values join with `" "`,
  everything else is `str()`-coerced (so `-0.2` resolves to the string
  `"-0.2"`, not a float — the `ll-config get` CLI output is plain text,
  matching `resolve_variable`'s existing contract).
- Confirmed via grep: no `ll-config` or `main_config` symbol exists anywhere
  in the repo today, and no CLI-level test file for it exists — both are
  fully net-new, not partial/stale implementations.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/config.py` (NEW) — add `main_config()` CLI entry
  point with a `get <key>` subcommand wrapping `BRConfig.resolve_variable()`
- `scripts/little_loops/cli/__init__.py` — import `main_config` and add to
  `__all__` (follow the `main_history_context` wiring at lines 66, 114)
- `scripts/pyproject.toml` — add `ll-config = "little_loops.cli:main_config"`
  to `[project.scripts]` (alongside the other `ll-*` entries, lines 51-96)
- `skills/go-no-go/SKILL.md:145` — replace the dead
  `{{config.history.go_no_go.correction_penalty}}` prose token (never
  expanded outside `ll-auto`/`skill_expander.py`) with an instruction to
  shell out to `ll-config get history.go_no_go.correction_penalty` and apply
  the resolved value
- `skills/analyze-history/SKILL.md:143,158` — `analysis.evolution.*` →
  `history.evolution.*` (confirmed stale: `BRConfig.to_dict()` has no
  top-level `analysis` key; `resolve_variable("analysis.evolution.feedback_min_recurrence")`
  returns `None`)

### Dependent Files (Callers/Reference Consumers)
- `scripts/little_loops/skill_expander.py:55-69` (`_substitute_config`/
  `_replacer`) — the only existing consumer of `resolve_variable()`; confirms
  the `None`-returns-blank contract a new CLI should mirror, but does NOT
  fire for interactive/slash-command skill execution (only `ll-auto`
  pre-expansion) — this is why the go-no-go prose token currently sits
  unexpanded
- `scripts/little_loops/cli/issues/check_readiness.py` (`cmd_check_readiness()`)
  — existing precedent for reading a config value in Python and applying it
  to a gate/score decision with a `try/except Exception` never-raise fallback

### Similar Patterns
- `scripts/little_loops/cli/history_context.py` (`_build_parser()` /
  `main_history_context()`) — closest CLI template: `_build_parser()` split
  out, `main_*()` wraps the body in
  `cli_event_context(DEFAULT_DB_PATH, "<name>", sys.argv[1:])`,
  `configure_output()` + `Logger(use_color=use_color_enabled())`, positional
  arg via `nargs="?"`
- `scripts/little_loops/cli/docs.py` (`main_verify_docs()`) — leaner
  single-purpose CLI shape if `ll-config get` doesn't need the full
  event-context wrapper
- `scripts/little_loops/config/features.py:986-996`
  (`GoNoGoConfig.from_dict()`) — existing "config-or-default, never-raise"
  contract to mirror in `main_config()`

### Tests
- `scripts/tests/test_config.py:3248-3261` (`TestGoNoGoConfig`) —
  `correction_penalty` is already covered at the dataclass layer
  (`test_defaults`, `test_per_key_override`, `test_unknown_key_ignored`); no
  changes needed here
- `scripts/tests/test_config_schema.py:867-901,1072,1835,2212,2289`
  (`resolve_variable` tests) — the underlying primitive is already
  exhaustively tested; new tests should cover the CLI wrapper, not duplicate
  these
- `scripts/tests/test_history_context_cli.py` (`TestArgumentParsing`, lines
  15-35) — template for a new `test_config_cli.py`:
  `patch("sys.argv", [...])` + call `main_config()` directly, assert on
  return code / `capsys.readouterr().out`. No `ll-config`/`main_config`/
  CLI-level config test currently exists anywhere in the repo (confirmed via
  grep) — this is net-new.

### Documentation
- `docs/reference/API.md` — add `ll-config` under the CLI reference (mirrors
  other `ll-*` entries)
- `.claude/CLAUDE.md` § CLI Tools — add an `ll-config` bullet alongside the
  other `ll-*` tools list

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — add a `### ll-config` section (this repo's
  established per-tool doc-reference pattern for every `ll-*` CLI, e.g.
  `### ll-doctor`, `### ll-history-context`; the issue's own API.md/CLAUDE.md
  bullets don't cover this file)
- `commands/help.md` — add a one-line `ll-config` catalog entry (matches the
  existing flat CLI list format, e.g. `ll-doctor  Check host CLI capability...`)
- `README.md:178` — bump `"38 typed CLI tools"` → `"39 typed CLI tools"`
  (adding a 40th... following the established count-bump convention every
  prior CLI-adding issue applies, e.g. FEAT-1504, FEAT-1625, ENH-2308)

### Tests
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_guides_and_meta.py:86` — update the
  `("README.md", "38 typed CLI tools", "FEAT-1045")` parametrized tuple to
  match the bumped count string, or the doc-wiring test will fail
- `scripts/tests/test_wiring_cli_registry.py` — this is the central
  parametrized `DOC_STRINGS_PRESENT` test gating `commands/help.md` /
  `docs/reference/CLI.md` doc-presence for every `ll-*` CLI (see existing
  tuples like `("commands/help.md", "ll-doctor", "FEAT-1504")`); add matching
  `ll-config` tuples here so the new doc entries above are test-enforced, not
  just prose
- `scripts/tests/test_cli_docs.py` (`TestMainVerifyDocs` /
  `TestMainVerifySkills`) — a leaner alternative test template to
  `test_history_context_cli.py`: mocks the underlying resolver function and
  asserts via `patch("builtins.print")` / `capsys` + `json.loads(...)`, with
  no DB/filesystem fixtures. Since `ll-config get <key>` is a pure
  resolve-and-print CLI (no DB access), this shape is the closer structural
  fit for the new `test_config_cli.py` than the DB-fixture-heavy
  `test_history_context_cli.py` pattern already cited above — use both as
  reference, but prefer this one for the actual test body shape

## Test patterns to follow

- `scripts/tests/test_config.py:3230-3362` — `TestHistoryConfig` /
  `TestGoNoGoConfig` 3-test shape (`test_defaults`, `test_per_key_override`,
  `test_unknown_key_ignored`).
- `scripts/tests/test_config_schema.py:388-522` — schema-declaration tests.

## Status

**Open** | Created: 2026-07-18 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-07-18T19:33:12 - `34636038-c9ad-4b77-b634-680b13ded0fc.jsonl`
- `/ll:confidence-check` - 2026-07-18T19:30:26 - `95343d66-04c7-4f2e-a817-6f6248fe4ccf.jsonl`
- `/ll:wire-issue` - 2026-07-18T19:28:26 - `3e112afc-3c22-448d-a90d-3c16370e99f2.jsonl`
- `/ll:refine-issue` - 2026-07-18T19:23:18 - `6ca6021c-5738-4570-810b-6a53a46fe492.jsonl`
- `/ll:decide-issue` (via ENH-2677) - 2026-07-18 - created as follow-up to closing ENH-2677
