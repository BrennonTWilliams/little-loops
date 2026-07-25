---
id: BUG-2816
type: BUG
priority: P1
status: open
captured_at: '2026-07-25T22:08:07Z'
discovered_date: 2026-07-25
discovered_by: capture-issue
labels: [loops, cli, docs, skills]
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

## Integration Map

### Files to Modify
- Loops: `adopt-third-party-api`, `apply-research`, `lib/cli`, `brainstorm`,
  `sprint-build-and-validate`, `backlog-flow-optimizer`, `prompt-across-issues`,
  `adversarial-redesign`, `sprint-refine-and-implement`, `cli-anything-bootstrap`,
  `loop-router`, `loop-composer`, `loop-composer-adaptive`, `rl-coding-agent`
- Docs: `scripts/little_loops/loops/README.md`, `docs/guides/LOOPS_REFERENCE.md`,
  `docs/reference/loops.md`, `docs/guides/LEARNING_TESTS_GUIDE.md`,
  `skills/create-loop/loop-types.md`
- Possibly `commands/create-sprint.md`, `commands/tradeoff-review-issues.md`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/__init__.py:172-196`, `cli/deps.py`,
  `cli/loop/__init__.py:126-133` (surfaces of record)
- `scripts/little_loops/fsm/runners.py:224` (no-`pipefail` behavior)

### Similar Patterns
- `skills/explore-api/SKILL.md:109` — correct prefix-free `scrape-docs` form
- Newer loops correctly document `--context k=v`

### Tests
- New: assert loop-YAML `ll-*` invocations resolve against installed argparse parsers
- `ll-check-links` / doc verification for the prose sweep

### Documentation
- Consolidate on `ll-loop run <loop> "<input>"` + `--context k=v` everywhere

### Configuration
- N/A

## Implementation Steps

1. Fix the live shell breakages (`apply-research`, `lib/cli`).
2. Fix the prompt-text breakages (`brainstorm`, `prompt-across-issues`, `--auto` ×2).
3. Resolve the `scrape-docs` packaging/namespace question.
4. Sweep `--input` prose across loops + docs (`cli-anything-bootstrap:480` first).
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

## Session Log
- `/ll:capture-issue` - 2026-07-25T22:08:07Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8a36a68e-d365-4ea1-9394-a9e5904b5739.jsonl`

---

## Status

- **Current**: open
