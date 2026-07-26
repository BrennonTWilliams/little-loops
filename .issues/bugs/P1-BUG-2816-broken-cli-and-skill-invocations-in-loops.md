---
id: BUG-2816
type: BUG
priority: P1
status: open
captured_at: '2026-07-25T22:08:07Z'
discovered_date: 2026-07-25
discovered_by: capture-issue
labels:
- loops
- cli
- docs
- skills
confidence_score: 88
outcome_confidence: 68
score_complexity: 18
score_test_coverage: 15
score_ambiguity: 15
score_change_surface: 20
decision_needed: true
deferred_by: automation
deferred_date: '2026-07-26T03:24:56Z'
deferred_reason: decision_unresolved
reconcile_attempted: true
---

# BUG-2816: Broken CLI/skill invocations in built-in loops that silently no-op or teach non-existent flags

## Summary

Built-in loop YAMLs (and the docs around them) invoke CLI subcommands and skill
flags that do not exist. Some fail silently (output suppressed, `on_error` never
fires), some are prompt text that teaches the model a non-existent command, and
one is a loop's **final success output telling the operator what to run**. Audit
§1.5 / `thoughts/builtin-loops-audit-2026-07-24.md` (third-pass corrected — the
second pass's `--auto` table was wrong in 4 of 6 rows; only 2 sites survive).

## Current Behavior

| Where | Problem | Effect |
|---|---|---|
| `adopt-third-party-api.yaml:21` — `/ll:scrape-docs` (`action_type: slash_command`) | Not in the packaged plugin (no `skills/scrape-docs/`, no `commands/scrape-docs.md`). A repo-local `.claude/skills/scrape-docs/` exists, but project skills resolve **without** the `ll:` namespace — so the `/ll:`-prefixed call is unresolvable even here | Breaks for any plugin consumer; stale refs also in `loops/README.md:79`, `docs/guides/LEARNING_TESTS_GUIDE.md:67`, `skills/create-loop/loop-types.md:647` (`skills/explore-api/SKILL.md:109` uses the prefix-free form and is fine). Moot for this loop until BUG-2812's crash is fixed |
| `apply-research.yaml:63` — `ll-issues list --status open --format table 2>/dev/null \| head -30 \|\| echo "(none)"` | `--format` only exists on `search` (and `refine-status`), not `list` (`cli/issues/__init__.py:172-196`); argparse exits 2, hidden by `2>/dev/null`. **The `\|\| echo` fallback never fires either**: FSM shell actions run via `bash -c` with no `pipefail` (`fsm/runners.py:224`), so the pipeline exits with `head`'s 0 | The "Open Issues" section of the context file is silently empty; `on_error` never triggers |
| `lib/cli.yaml:94` — `ll-deps check` | No `check` subcommand (valid: `analyze`, `validate`, `fix`, `apply`, `tree` — `cli/deps.py`); intended is `ll-deps validate` | **Latent, not live**: the `ll_deps` fragment has zero consumers (its only importer, `docs-sync.yaml`, uses only `shell_exit`/`ll_check_links`/`ll_commit`). Breaks the first loop that adopts it |
| `brainstorm.yaml:373` — "using `ll-issues set-flag`" | No `set-flag` subcommand (only read-only `check-flag`; write-side is `set-scores`/`set-status`) | Prompt text handed to the LLM — it *will* attempt the nonexistent command and fail |
| `sprint-build-and-validate.yaml:45` (`/ll:create-sprint --auto`); `backlog-flow-optimizer.yaml:94` (`/ll:tradeoff-review-issues --auto`) | Neither `commands/create-sprint.md` nor `commands/tradeoff-review-issues.md` declares an `--auto` argument. (`map-dependencies`, `audit-issue-conflicts`, `commit` all *do* declare it — those 4 sites were false positives.) The real pattern is two *commands* predating the `--auto` convention | Undefined behavior at 2 sites (the skill ignores or misreads the flag) |
| `prompt-across-issues.yaml:19` — `/ll:normalize-issues {issue_id} --quick` | `commands/normalize-issues.md` documents only `--auto`/`--check`; no `--quick` | The loop's canonical usage example teaches a non-existent flag |
| `ll-loop run <loop> --input "..."` in `adversarial-redesign.yaml:18` (comment), `sprint-refine-and-implement.yaml:7` (description), `cli-anything-bootstrap.yaml:480`, `loop-router.yaml:162,220`, `loop-composer.yaml:59`, `loop-composer-adaptive.yaml:66` (prompt text), `loops/README.md:12,166,168`, `docs/guides/LOOPS_REFERENCE.md:2508`, `docs/reference/loops.md` ×8 | No `--input` flag exists; input is positional (`cli/loop/__init__.py:126-133`); argparse hard-rejects it | No occurrence is executed shell, but `cli-anything-bootstrap.yaml:480` is the loop's **final success output telling the operator what to run** — following it produces "unrecognized arguments". (`loop-router` itself dispatches natively via `loop:` at `:361`, so it works despite its own prose) |
| `rl-coding-agent.yaml:22,27` | References `ll-manage-issue` as a CLI in template-stub comments; no such entry point in `pyproject.toml`'s `[project.scripts]` (it's the `/ll:manage-issue` skill) | Comments only — zero runtime impact, misleads maintenance |

## Expected Behavior

- Every CLI invocation in a loop names a real subcommand/flag.
- Failures surface rather than being swallowed by `2>/dev/null` + a
  non-`pipefail` pipeline.
- Prompt text and success output teach only syntax that actually works
  (`ll-loop run <loop> "<input>"`, `--context k=v`).

## Root Cause

Loop YAMLs and docs drifted from the CLI/skill surface with no cross-check.
Compounding factors: `2>/dev/null` hides argparse's exit 2, and FSM shell actions
run without `pipefail` (`fsm/runners.py:224`) so `|| fallback` after a pipeline
never fires.

## Proposed Solution

1. `apply-research.yaml:63` — drop `--format table` (or switch to `ll-issues
   search`), remove `2>/dev/null`, and restructure so the fallback can fire
   (or set `pipefail`).
2. `lib/cli.yaml:94` — `ll-deps check` → `ll-deps validate`.
3. `brainstorm.yaml:373` — replace `set-flag` with `set-scores`/`set-status`.
4. `adopt-third-party-api.yaml:21` — either package `scrape-docs` as a plugin
   skill or drop the `ll:` prefix / remove the step.
5. Two `--auto` sites — either declare `--auto` in `commands/create-sprint.md`
   and `commands/tradeoff-review-issues.md`, or drop the flag from the loops.
6. `prompt-across-issues.yaml:19` — `--quick` → `--auto` (or remove).
7. Mechanical `--input` prose sweep across the 7 loop sites + `loops/README.md`,
   `docs/guides/LOOPS_REFERENCE.md`, `docs/reference/loops.md` (×8); fix
   `cli-anything-bootstrap.yaml:480` first — it's operator-facing output.
8. `rl-coding-agent.yaml:22,27` — comment fix.
9. Consider a test that greps loop YAMLs for `ll-*` invocations and validates
   subcommands against the installed parsers.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **No existing CLI-invocation validator** for loop YAMLs was found — item 9 is
  genuinely new territory, not a duplicate of an existing check.
- **Two candidate extension points for item 9**, both already established in
  this codebase:
  - The MR-rule validator architecture in `fsm/validation.py` (e.g.
    `_validate_overescaped_shell` for MR-9 at line 1952, `_validate_parse_swallow`
    for MR-10 at line 2087) — each rule is a `_validate_<rule>(fsm) ->
    list[ValidationError]` function with a suppression flag as a top-level
    `FSMLoop` boolean (documented in `.claude/CLAUDE.md`'s MR-rule table). A new
    rule here would run as part of `ll-loop validate` and could gate on a new
    `cli_invocation_ok` suppression flag.
  - The standalone `ll-verify-*` drift-detection pattern in
    `scripts/little_loops/cli/verify_cli_allowlist.py` (`_all_ll_entry_points()`
    + `_areas_md_preset_tools()` diffed in `_run()`) — regex-extracts `ll-*`
    tokens from a source-of-truth, diffs against a canonical set, exits 1 on
    drift. This shape would need extending beyond tool-name diffing to also
    introspect each subcommand's registered flags (walk `subparsers.choices`
    and each subparser's `_actions`), since BUG-2816 is about
    subcommand/flag drift, not just tool-name drift. Test pattern to follow:
    `scripts/tests/test_verify_cli_allowlist.py`.
- **Correct `ll-loop run` usage to model the fix on**: `--context k=v` sites
  already do this right, e.g. `loops/vega-viz.yaml:45`,
  `loops/prompt-across-issues.yaml:20-22`, `loops/rn-build.yaml:16,41`.
- **Correct `pipefail` handling to model the `apply-research.yaml:63` fix on**:
  8 loops already opt into `set -o pipefail` before a `| tee` pipeline (e.g.
  `loops/fix-quality-and-tests.yaml:72`, `loops/rn-remediate.yaml:507-508` which
  has an explanatory comment: "`set -o pipefail` preserves ll-auto's exit code
  through the `tee` pipe").
- **Line-number drift since the audit** (all claims otherwise confirmed
  accurate, verified by `ll:codebase-analyzer`): `cli-anything-bootstrap.yaml`'s
  operator-facing `--input` output is at line **479**, not 480; the `ll-issues
  list` subparser (no `--format` flag) now spans `cli/issues/__init__.py:172-229`
  (was 172-196).
- **`scrape-docs` skill confirmed repo-local only**:
  `.claude/skills/scrape-docs/SKILL.md` exists but is not packaged under
  `skills/` — consistent with the issue's existing claim.

## Integration Map

### Files to Modify
- Loops (live/prompt-text fixes, item 1-2): `apply-research`, `lib/cli`,
  `brainstorm`, `prompt-across-issues`
- Loops (`--auto` sweep, item 2 — dropped from the loops, not added to the
  commands; see decision below): `sprint-build-and-validate`,
  `backlog-flow-optimizer`
- Loops (`adopt-third-party-api`, item 3): pending the scrape-docs
  packaging/namespace decision (still open, see Confidence Check Notes)
- Loops (`--input` prose sweep, item 4): `adversarial-redesign`,
  `sprint-refine-and-implement`, `cli-anything-bootstrap` (fix line 479 first —
  it is operator-facing output), `loop-router`, `loop-composer`,
  `loop-composer-adaptive` (prose-only sites, not executed shell)
- `rl-coding-agent` (item 8, comment-only fix)
- Docs: `scripts/little_loops/loops/README.md`, `docs/guides/LOOPS_REFERENCE.md`,
  `docs/reference/loops.md`, `docs/guides/LEARNING_TESTS_GUIDE.md`,
  `skills/create-loop/loop-types.md`, `skills/create-loop/SKILL.md:175-177`
  (3 more `--input` prose sites: `loop-composer`, `loop-composer-adaptive`,
  `goal-cluster`), `skills/create-loop/reference.md:1162,1169,1184` (3 more
  `--input` prose sites)

**Decided:** `commands/create-sprint.md` / `commands/tradeoff-review-issues.md`
are **not** modified — the wiring pass found that supporting `--auto` there
needs a new `arguments:` entry *and* real non-interactive branching (skipping
each command's `AskUserQuestion` calls), which tips the cost/benefit toward
dropping `--auto` from the two loop call sites instead.

**Confirmed clean (no edit needed):**
- `docs/reference/CLI.md` — grepped directly; contains no `set-flag`,
  `ll-deps check`, or `scrape-docs` references and already documents the
  correct surfaces. An earlier locator pass flagged it in error.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/__init__.py:172-196`, `cli/deps.py`,
  `cli/loop/__init__.py:126-133` (surfaces of record)
- `scripts/little_loops/fsm/runners.py:224` (no-`pipefail` behavior)

_Wiring pass added by `/ll:wire-issue`:_
- `commands/create-sprint.md` frontmatter `arguments:` (lines 8-17) — declares only
  `name`/`description`/`issues`; body has no non-interactive branch anywhere (Step
  1.5 auto-grouping `AskUserQuestion`, Step 4 warnings, Step 5b overwrite prompt
  all assume interactive confirmation)
- `commands/tradeoff-review-issues.md` frontmatter `arguments:` (lines 14-17) —
  declares only `issues`; Phase 4b issues an unconditional per-issue
  `AskUserQuestion` with no flag-gated skip path
  — **implication for Proposed Solution item 5**: "declare `--auto` in the docs"
  is not sufficient by itself; supporting `--auto` on either command requires a
  new `arguments:` entry *and* real non-interactive branching logic in the body
  (skip the `AskUserQuestion` calls, auto-select defaults). This tips the
  cost/benefit toward the other option already listed — drop `--auto` from
  `sprint-build-and-validate.yaml:45` and `backlog-flow-optimizer.yaml:94`
  instead of adding it to the commands.

### Similar Patterns
- `skills/explore-api/SKILL.md:109` — correct prefix-free `scrape-docs` form
- Newer loops correctly document `--context k=v`

### Tests
- New: assert loop-YAML `ll-*` invocations resolve against installed argparse parsers
- `ll-check-links` / doc verification for the prose sweep

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles::test_all_validate_as_valid_fsm`
  — existing sweep over every file in `scripts/little_loops/loops/`; will pick up
  a new MR-rule ERROR (item 9) across all 14 affected loops with zero new test
  code once the rule lands. No edit needed, but note it as the regression
  backstop.
- `scripts/tests/test_loop_router.py:107,121` — existing precedent for asserting
  a specific CLI flag substring is present/absent inside a loop's `action:`
  field (`assert "ll-loop list" in state.get("action", "")`,
  `--visibility public` check). Model new per-site regression assertions
  (`--format table` removed, `ll-deps check` → `validate`, etc.) on this idiom.
- `scripts/tests/test_brainstorm.py::TestBrainstormYaml` — dedicated per-loop
  test file for `brainstorm.yaml`; extend with an assertion that `set-flag` no
  longer appears in the loop's prompt text (issue item 2's `brainstorm.yaml:373`
  fix).
- **No dedicated test file exists** for `apply-research`, `lib/cli`,
  `adopt-third-party-api`, `sprint-build-and-validate`,
  `backlog-flow-optimizer`, `prompt-across-issues`, `cli-anything-bootstrap`,
  `adversarial-redesign`, `sprint-refine-and-implement`,
  `loop-composer`/`loop-composer-adaptive`, `rl-coding-agent` — new
  content-string regression tests for these can follow
  `test_brainstorm.py`'s `TestBrainstormYaml` shape (load via
  `BUILTIN_LOOPS_DIR / "<name>.yaml"`, `yaml.safe_load`, assert broken string
  absent / correct string present).
- If Proposed Solution item 9 (new CLI-invocation validator) is implemented as
  an MR-rule per the existing Codebase Research Findings: follow
  `scripts/tests/test_fsm_validation.py`'s MR-9 (`_validate_overescaped_shell`,
  ~line 3627) / MR-10 (`_validate_parse_swallow`, ~line 4207) test quartet —
  fire case(s), non-fire case(s), suppression-flag test, `validate_fsm()`
  integration test, plus an "unknown top-level key" recognition test for the
  new suppression flag.
- If item 9 is instead implemented as a standalone `ll-verify-*` CLI:
  `scripts/tests/test_verify_cli_allowlist.py` is a workable four-class test
  template (`TestAllLlEntryPoints`, `TestPresetParsers`, `TestRun`,
  `TestMainVerifyCliAllowlist`), but note its production counterpart
  (`cli/verify_cli_allowlist.py`) only diffs tool *names* — the new validator
  needs additional subparser/flag introspection (`subparsers.choices` + each
  subparser's `_actions`) that isn't reusable as-is from that file.
- `scripts/tests/test_link_checker.py` — covers markdown *link* resolution only,
  not prose-content correctness; it will **not** catch the `--input` prose drift
  (plain text, not a markdown link). The doc-prose sweep (Implementation Steps
  item 4) has no automated regression coverage today — flagged as a gap, not
  something to wire up as part of this fix unless scope is extended.

### Documentation
- Consolidate on `ll-loop run <loop> "<input>"` + `--context k=v` everywhere

### Configuration
- N/A

### Registration Note (`/ll:wire-issue`)
If Proposed Solution item 9 is implemented as a new `fsm/validation.py` MR-rule,
two documentation tables must be updated as part of that work (both already
tracked by this project's own "keep source-of-truth tables in sync" convention):
1. `.claude/CLAUDE.md` § "Loop Authoring" MR-rule table — add the new row.
2. `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — the canonical source table
   (heading currently reads "MR-1...MR-12", would need bumping), plus the
   enumerated ERROR/WARNING rule list further down the guide.
This is scoped as a follow-on to item 9, not required for the core BUG-2816
fix (items 1-8), and is not being added to Implementation Steps to avoid
overloading this bug with the validator's full design — captured here so it
isn't lost if item 9 is picked up.

## Implementation Steps

1. Fix the live shell breakages (`apply-research`, `lib/cli`).
2. Fix the prompt-text breakages (`brainstorm`, `prompt-across-issues`), and
   drop `--auto` from `sprint-build-and-validate.yaml:45` and
   `backlog-flow-optimizer.yaml:94` (per wiring-pass finding: adding `--auto`
   support to `create-sprint`/`tradeoff-review-issues` needs new `arguments:`
   entries plus non-interactive branching around each command's
   `AskUserQuestion` calls — not justified for these 2 call sites).
3. Resolve the `scrape-docs` packaging/namespace question (still open — see
   Confidence Check Notes).
4. Sweep `--input` prose across loops + docs (`cli-anything-bootstrap:480` first) —
   also covers `skills/create-loop/SKILL.md:175-177` and
   `skills/create-loop/reference.md:1162,1169,1184`, found by the wiring pass.
5. Add the invocation-validation test.

## Impact

- **Severity**: Medium-High — one silently-empty context section, one latent
  fragment break, several prompts that reliably send the model down a failing
  path, and one operator-facing instruction that does not work.
- Mostly mechanical; ~14 files including docs.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `thoughts/builtin-loops-audit-2026-07-24.md` §1.5, §3.4, rec #5 | Source finding, per-site verification |
| `docs/reference/CLI.md` | Canonical CLI surface |

## Steps to Reproduce

1. `ll-issues list --status open --format table` → argparse exits 2
   (`unrecognized arguments: --format`). In `apply-research.yaml:63` this is
   hidden by `2>/dev/null`, and the `|| echo "(none)"` fallback never fires
   because the pipeline exits with `head`'s 0 (no `pipefail`,
   `fsm/runners.py:224`) — the context file's "Open Issues" section is silently
   empty.
2. `ll-deps check` → no such subcommand (valid: `analyze`, `validate`, `fix`,
   `apply`, `tree`).
3. `ll-issues set-flag ...` → no such subcommand (only read-only `check-flag`).
4. `ll-loop run <loop> --input "x"` → `unrecognized arguments: --input` (input
   is positional). This is exactly what `cli-anything-bootstrap.yaml:480` tells
   the operator to run on success.
5. `grep -rn "scrape-docs" skills/ commands/` → no packaged plugin skill or
   command, so `/ll:scrape-docs` (`adopt-third-party-api.yaml:21`) cannot
   resolve.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-25_

**Readiness Score**: 88/100 → READY
**Outcome Confidence**: 68/100 → MODERATE

### Concerns
- Item 4 (`scrape-docs` packaging) is an open either/or decision (package as plugin skill vs. drop the `ll:` prefix) not yet resolved in the issue.
- Item 4's `adopt-third-party-api.yaml:21` fix is noted as "moot ... until BUG-2812's crash is fixed" — a soft dependency on another open bug.

### Gaps to Address
_(none — the refine/wire passes already closed the major gaps)_

### Outcome Risk Factors
- Open decision on `scrape-docs` packaging (either package as a plugin skill or drop the `ll:` prefix) — resolve before implementing that sub-item.
- New CLI-invocation validator (item 9) is broad enumeration across ~14 loop files with no dedicated regression tests written yet for most of the affected loops (only `test_brainstorm.py` and the generic FSM-validity sweep exist today).

## Session Log
- `/ll:decide-issue` - 2026-07-26T03:46:33 - `8e7d2c8e-89fd-4b78-a923-3530d55d8695.jsonl`
- `/ll:reconcile-issue` - 2026-07-26T03:44:39 - `9c569214-a4ba-4915-a53d-dcaf022d30fc.jsonl`
- `/ll:decide-issue` - 2026-07-26T03:42:04 - `52b78b43-eea9-4ce2-9628-3de02955a2a1.jsonl`
- `/ll:confidence-check` - 2026-07-25T22:30:00 - `1e73f98a-e50a-468b-8810-349ebe4e809e.jsonl`
- `/ll:wire-issue` - 2026-07-26T03:22:46 - `7c406d5e-0dcb-4d02-a823-28c2fe4170b3.jsonl`
- `/ll:refine-issue` - 2026-07-26T03:17:16 - `9cb6cf7d-6504-456e-89fb-d23fbf5507ad.jsonl`
- `/ll:capture-issue` - 2026-07-25T22:08:07Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8a36a68e-d365-4ea1-9394-a9e5904b5739.jsonl`

---

## Status

- **Current**: open
