---
id: ENH-2953
title: 'll-issues prioritize --apply: priority-rename mechanics out of prioritize-issues.md'
type: ENH
priority: P2
status: done
discovered_by: skill-audit
discovered_date: 2026-07-31
completed_at: '2026-08-02T04:40:35Z'
parent: EPIC-2938
epic: EPIC-2938
testable: true
relates_to:
- ENH-2944
labels:
- cli
- issues
- normalization
confidence_score: 95
outcome_confidence: 90
score_complexity: 20
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 23
---

# ENH-2953: `ll-issues prioritize --apply`

## Summary

`commands/prioritize-issues.md` (233 lines) is discovery + rename bookkeeping around a
single genuine judgment step. Split out of ENH-2944 so it ships independently of
`normalize` (511 lines, the largest file in the epic's scope) rather than waiting on it.

## Current Behavior

`commands/prioritize-issues.md` has **two** modes, both mechanical outside one judgment step:

- **Initial prioritization** (Steps 1–4, L52–67 + L145–209): glob + `^P[0-5]-` regex
  discovery (L54–67), `git mv` prepend (L169–173), fixed report table (L177–209).
- **Re-prioritization** (Steps 1.5/2-RE/3-RE/4-RE, L69–141): fires when *all* issues
  already carry a prefix — re-evaluates every active issue, renames only those whose
  priority changed by **replacing** the existing `P[X]-` prefix (L108–112), and emits a
  second fixed report table (L118–139). Gated by a mandatory `AskUserQuestion` call
  (L73–83) unless `AUTO_MODE`.
- Narrated check-mode exit codes (L48–50), which makes any FSM
  `evaluate: type: exit_code` gate over this command model-dependent.
- Only Steps 2 / 2-RE (assigning P0–P5 from impact/severity/effort) are judgment.
- Notably the command uses no `ll-issues` subcommand at all today.

## Expected Behavior

- `ll-issues prioritize [--check] [--all] [--json]` — discovery + report data. Default
  lists **unprioritized** issues (no `^P[0-5]-` prefix); `--all` lists every active issue
  with its `current_priority`, which is what the re-prioritize mode consumes.
- `--check` is a deterministic exit-code gate (0 = every active issue carries a prefix /
  1 = one or more unprioritized), per the EPIC convention that no `--check` exit is
  LLM-narrated. `--check` ignores `--all` (re-prioritization is never a gate failure).
- `ll-issues prioritize --apply -` — reads a `{"ENH-2953": "P2", ...}` JSON map from
  stdin, performs all renames, returns `{id, old_path, new_path, old_priority}` per
  entry. Handles both **prepend** (no existing prefix) and **replace** (`P[X]-` → `P[Y]-`);
  an entry already at its target priority is a no-op, not an error.
- `/ll:prioritize-issues` shrinks to ~60 lines: call `--json` (or `--all --json`), judge
  priorities, pipe the map to `--apply -`.

## Proposed Solution

Discovery reuses `issue_parser.find_issues()`; the "is it prioritized" test is a narrow
`^P[0-5]-` match, **not** `is_normalized()` (see Codebase Research Findings — that
predicate checks the whole filename and would misclassify a prefixed-but-malformed file
as unprioritized, causing a double prefix). Renames go through the shared
`git_mv_with_fallback()` helper in `issue_lifecycle.py` (ENH-2944 owns creating it;
whichever issue lands first extracts it, under exactly that name).

`--apply` reads a JSON map from stdin rather than a `k=v` comma string: there is no
`ID=P2,...` precedent in `ll-issues` (`set-scores` is per-issue flags), stdin matches the
`set-flags --from-notes -` convention from ENH-2946, and it avoids shell-quoting hazards
when an FSM `shell:` body drives the call.

## Codebase Research Findings

_Verified 2026-08-01 against the working tree._

- **No `ID=P2,...` precedent exists.** `scripts/little_loops/cli/issues/set_scores.py`
  and its parser (`cli/issues/__init__.py:705-730`) take `set-scores ISSUE_ID
  --confidence N --outcome N ...` — per-issue flags. Nothing in `ll-issues` parses a
  comma-separated `k=v` map. The stdin-JSON shape above replaces it.
- **`is_normalized()` is the wrong predicate.** `issue_parser.py:94` matches the entire
  filename against `^P[0-5]-(BUG|FEAT|ENH|EPIC)-[0-9]{3,}-[a-z0-9-]+\.md$`. A file with a
  malformed ID or non-slug tail is "not normalized" while already carrying a `P2-` prefix
  — prioritize would prepend a second one. ID/slug defects are ENH-2944's job.
- **The git-mv block to reuse** is `issue_lifecycle.py:966-990`, inside `skip_issue()`:
  `_is_git_tracked()` (line 393, via `git ls-files`) → `git mv`, with `atomic_write()` +
  `Path.rename()` fallback for untracked files or on `git mv` failure/timeout. A bare
  `subprocess` `git mv` fails on untracked issue files. `skip_issue()` itself is **not**
  reusable — it appends a `## Skip Log` section. `docs/reference/CLI.md:1772` already
  names the extracted helper `git_mv_with_fallback()`; ENH-2944 line 141 claims ownership
  of creating it. Import it, do not duplicate.
- **`re.sub(r"^P\d-", ...)`** (`cli/issues/skip.py:47`) is the existing prefix-replace
  idiom — but it is a no-op on an unprefixed file, so `apply_priorities()` needs an
  explicit prepend branch.
- **Status filtering**: `find_issues(status_filter=None)` skips `done/cancelled/deferred`
  (`issue_parser.py:1876-1878`). That default is **correct here** — prioritization only
  concerns active work. This deliberately differs from ENH-2944, which passes
  `status_filter=set(_ALL_STATUSES)` so terminal issues with malformed filenames aren't
  skipped; the divergence is intentional, not an oversight.
- **Sibling to model**: `cli/issues/format_check.py` — `--check` exit-code convention
  (0 clean / 1 violations), scan-vs-apply split, and `add_*_parser(subs)`
  self-registration.

### Codebase Research Findings — refine-issue pass (2026-08-01)

_Added by `/ll:refine-issue` — corrections and additions verified against the
working tree:_

- **CORRECTION — `git_mv_with_fallback()` already exists; there is nothing left
  to extract.** ENH-2944 (status: `done`) already created it at
  `issue_lifecycle.py:1289`, and its docstring explicitly names this issue as an
  intended caller: `"Shared by :func:`skip_issue` and \`\`ll-issues normalize\`\`
  (ENH-2944/ENH-2953)."` `cli/issues/normalize.py:apply_normalize()` (line 432)
  already imports and calls it (`normalize.py:444,465`). The "whichever issue
  lands first extracts it" framing above (and in Implementation Steps item 2) is
  stale — this issue only needs to **import** `git_mv_with_fallback`, not build
  it.
- **CORRECTION — `skip_issue()` line numbers.** It is at `issue_lifecycle.py:1340`,
  not `966-990`. Lines `966-990` fall inside `close_issue()` (starts at line
  890), a different function with its own rename-adjacent logic — do not model
  against that range.
- **CORRECTION — `format_check.py` is not the `--check`-flag model.**
  `format_check.py` has no dedicated `--check` flag; its exit code is folded
  into `--format json`'s return value (`format_check.py:316`) with no LLM
  narration either way, so the *no-narration* rule still holds, but there's no
  literal `--check` argparse flag to copy. `cli/issues/normalize.py` is the
  closer model for an explicit `--check` boolean flag
  (`add_normalize_parser()`, `normalize.py:521-526`) whose presence alone
  toggles gate semantics (`cmd_normalize()`, lines `562-589`: `if check_mode:
  return 1 if gate_failed else 0`).
- **No existing precedent for JSON-from-stdin parsing in a `cli/issues/*.py`
  module.** `set_flags.py`'s `--from-notes -` (`cmd_set_flags()`, lines
  `369-380`) is the only `sys.stdin`-reading code in `cli/issues/`, and it
  reads plain text (`sys.stdin.read()`), not JSON. `json.load(sys.stdin)`
  precedent exists only inside FSM loop YAML `shell:` blocks (e.g.
  `loops/autodev.yaml:115`), not in a Python CLI module — `--apply -` combines
  the `-` sentinel idiom with JSON parsing in a way nothing else in `cli/issues/`
  currently does.
- **Dataclass/serialization convention to follow for `PrioritizeEntry`/
  `RenameResult`**: plain `@dataclass` (not frozen), a `to_dict()` instance
  method (not `dataclasses.asdict`) stringifying `Path` fields explicitly, and
  output via the shared `little_loops.cli.output.print_json()` helper — not raw
  `print(json.dumps(...))`. Modeled on `NormalizeFinding.to_dict()`
  (`normalize.py:107`) and `FlagResult.to_dict()` (`set_flags.py:105-120`).
- **Two co-existing subcommand-registration conventions** exist in
  `cli/issues/__init__.py`: an `add_*_parser(subs)`-function style (used by
  `format-check`, `normalize`, `decisions`, `size`, `set-flags`) and an inline
  style built directly in `main_issues()` (used by `set-scores`, `skip`, lines
  `887-901` for `skip`). Given this issue's Program Design section already
  specifies `cmd_prioritize(config, args)` as a standalone function, follow the
  `add_*_parser()`-function style (matching `normalize`/`format-check`), not
  the inline `set-scores`/`skip` style.
- **`_VERIFIER_SKILLS`** (AC 7's `ll-action invoke prioritize-issues` check) is
  a `frozenset` at `cli/action.py:30`, already including `"prioritize-issues"`.
- **`scripts/tests/test_ll_issues_skip.py` does not exist** — there is no
  existing dedicated test file for `skip.py`'s rename behavior to model
  against beyond the `normalize`/`format_check` fixture patterns already cited.
  The fixture-tree idiom to follow (both suites use it): a `temp_project_dir`-
  scoped fixture pre-creating `bugs/`/`features/`/`enhancements/`/`epics/`
  under `.issues/`, a `_write`/`_write_issue` helper writing filename+body
  strings directly (no issue-creation API), invocation via
  `patch.object(sys, "argv", argv)` + `main_issues()` (not a subprocess), and
  renamed-file assertions via `Path.glob()` against the target directory
  (`test_ll_issues_normalize.py:110`).

## Implementation Steps

1. `prioritize` discovery (`--json`, `--all`) + `--check` exit code.
2. `--apply -` stdin JSON map parsing; prepend/replace renames via
   `git_mv_with_fallback()`.
3. Slim `commands/prioritize-issues.md` (233 → ~60): keep the P0–P5 criteria table, the
   judgment step, and the `AskUserQuestion` re-prioritize gate; delete flag-parsing bash,
   glob discovery, `git mv` blocks, both report tables, and the narrated `--check` exits.
4. Docs + mirrors (see Integration Map).
5. Tests (see Acceptance Criteria).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the
implementation:_

6. `scan_prioritize()`/`apply_priorities()` read `config.issues.priorities` (via
   `BRConfig`) instead of hardcoding `P[0-5]`, matching the current
   `{{config.issues.priorities}}` template token in `commands/prioritize-issues.md`.
7. Regenerate `.gemini/commands/prioritize-issues.toml` via `ll-adapt --apply`
   alongside the `.kimi-code` mirror — it is a second git-tracked full-body duplicate
   not covered by `ll-verify-skill-prose` or `test_adapt_golden_corpus.py`.
8. New `git log --follow` continuity test (AC 4) needs a real git-repo fixture
   (`git init`/`git add`/`git commit` in `tmp_path`) — no existing test in the repo
   covers rename-history continuity for `git_mv_with_fallback()` to model against.

## Program Design

### Types

- `PrioritizeEntry: dataclass`
  - `id: str`
  - `path: Path`
  - `current_priority: str | None`  # `None` only in the unprioritized listing

- `RenameResult: dataclass`
  - `id: str`
  - `old_path: Path`
  - `new_path: Path`
  - `old_priority: str | None`

### Signatures

- `scan_prioritize(config: BRConfig, *, include_prioritized: bool = False) -> list[PrioritizeEntry]`
- `apply_priorities(config: BRConfig, mapping: dict[str, str]) -> list[RenameResult]`
- `cmd_prioritize(config: BRConfig, args: argparse.Namespace) -> int`

### Call Path

- `scan_prioritize()` -> `find_issues()` (existing, `issue_parser.py:1855`) -> `^P[0-5]-`
  prefix match
- `apply_priorities()` -> `_resolve_issue_id()` (existing, `cli/issues/show.py`) ->
  prefix prepend/replace -> `git_mv_with_fallback()` (`issue_lifecycle.py`, extracted from
  `skip_issue()`)

## Integration Map

- **`ll-action` bridge**: `prioritize-issues` is one of the nine `ll-action`-bridged
  verifiers writing `verdict_events` (`docs/ARCHITECTURE.md:697`,
  `docs/guides/HISTORY_SESSION_GUIDE.md:118`). `ll-action invoke prioritize-issues
  --output json` must still work after slimming.
- **`docs/reference/CLI.md`**: has **no** `prioritize` section today (unlike ENH-2944's
  prewritten one) — add a new one alongside `ll-issues skip` (L1419).
- **`.claude/CLAUDE.md`**: the `ll-issues` bullet enumerates every subcommand — add
  `prioritize`.
- **`docs/guides/LOOPS_GUIDE.md:1004`** lists `prioritize-issues` among skills whose
  `--check` needs `evaluate: type: exit_code`; it becomes a CLI `--check`, so update.
- **Host mirror**: `.kimi-code/skills/ll-prioritize-issues/SKILL.md` is git-tracked and
  duplicates the full 233-line body (incl. the `--check` narration at L221). Regenerate
  via `ll-adapt`; `scripts/tests/test_adapt_golden_corpus.py` covers this surface.
  (`.gemini/skills/` is untracked — ignore.)
- **`scripts/tests/test_verify_skill_prose.py:19`** `BASELINE_COUNT = 23`. This issue
  removes exactly 2 findings (`prioritize-issues.md:110` and `:171`, both
  `git_mv_glob_loop` — confirmed by running `ll-verify-skill-prose`). Ratchet to 21,
  coordinating with ENH-2944's own decrement.
- **ENH-2944**: shares `git_mv_with_fallback()`. Not a hard dependency — whichever lands
  first extracts the helper under that exact name.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `.gemini/commands/prioritize-issues.toml` — a **second** git-tracked mirror not named
  in the "Host mirror" bullet above. It is a byte-for-byte duplicate of the current
  233-line `commands/prioritize-issues.md` body (same `--check` narration, `git mv`
  blocks, report tables), emitted by `GeminiEmitter` in
  `scripts/little_loops/adapters/gemini.py`. Unlike `.gemini/skills/` (untracked,
  correctly ignored above), `.gemini/commands/` is **not** in `.gitignore` — it must be
  regenerated via `ll-adapt --apply` alongside the `.kimi-code` mirror. Not covered by
  `ll-verify-skill-prose`'s `BASELINE_COUNT` (that gate only globs `skills/*/SKILL.md` +
  `commands/*.md`) or by `test_adapt_golden_corpus.py` (its Gemini/Codex cases run
  against synthetic fixtures in `command_cases.json`, which have no `prioritize` entry)
  — so this file needs manual regeneration but no test-suite change.
- `scripts/little_loops/loops/issue-discovery-triage.yaml` (`prioritize` state,
  L39-44) — the only FSM loop caller of `prioritize-issues`. It invokes `--auto` via
  `action_type: prompt` with no `evaluate:` block and an unconditional `next:`, so it
  is unaffected by removing the narrated `--check` exit-code text. No change required;
  listed for completeness, not as a touchpoint.
- `_record_verdict()` (`scripts/little_loops/cli/action.py:68-116`) — confirms AC 7 is
  low-risk: `commands/prioritize-issues.md` emits no `VERDICT_JSON` tag today, so
  `ll-action invoke prioritize-issues` already degrades to the coarse
  `exit_code == 0 → pass` rule. Removing the narrated report tables/exit text does not
  touch this path. No code change needed in `action.py`.

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config-schema.json:127-129` (`issues.priorities`) — the current
  `commands/prioritize-issues.md` templates the valid-priority list via
  `{{config.issues.priorities}}` (line 22) rather than hardcoding `P[0-5]`.
  `scan_prioritize()`/`apply_priorities()` must read `config.issues.priorities` (via
  `BRConfig`) to preserve that behavior — a read-only dependency, not a schema change,
  but missing from the Program Design section above.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- AC 4's `git log --follow` continuity check has **zero existing test coverage
  anywhere in the repo** — `git_mv_with_fallback()` is only exercised indirectly (via
  `skip_issue()` in `test_issue_lifecycle.py` and `--auto` in
  `test_ll_issues_normalize.py`), and neither asserts on rename-history continuity.
  This needs a genuinely new test with a real git-repo fixture (`git init` + `git add`
  + `git commit` in `tmp_path`), since `--follow` is meaningless without actual commit
  history to walk — there is no existing test to copy for this specific assertion.
- `--json`/`--apply` output envelope: `test_ll_issues_normalize.py`'s
  `TestJsonOutput.test_json_shape` (`assert set(data) == {"findings", "applied"}`) is
  the sibling convention `prioritize`'s `--json` output should match, matching the
  `{findings: [...]}` / `applied: [...]` shape implied by `scan_prioritize()`/
  `apply_priorities()` in Program Design but not yet spelled out as a literal envelope.
- Idempotency test model: `test_ll_issues_format_check.py::TestFormatCheckFix::test_fix_apply_is_idempotent`
  (snapshot content after first apply, re-apply, assert byte-identical + clean exit) is
  the closer template than the issue's cited `TestFormatCheckFix` class reference alone
  — note the post-rename wrinkle: unlike format-check (stable path across runs),
  prioritize's idempotency test must re-glob for the renamed path before the second
  `.read_text()` comparison, since the file path itself changes on the first apply.

## Scope Boundaries

- In scope: the `prioritize` subcommand (`--json`, `--all`, `--check`, `--apply -`),
  slimming `commands/prioritize-issues.md`, and the doc/mirror updates above.
- Out of scope: the P0–P5 taxonomy itself, priority *judgment* (stays LLM), `normalize`
  (ENH-2944), `ll-issues skip`'s existing priority-bump path, and any change to the
  `AskUserQuestion` re-prioritize UX (it stays in the command, unchanged).

## Impact

- **Priority**: P2 - Thin, independently shippable, and removes a narrated exit-code gate
- **Effort**: Small - Discovery + a rename map, plus doc/mirror follow-through
- **Risk**: Low-Medium - `--check` previews and renames go through the tracked/untracked
  fallback helper, but the re-prioritize (prefix-replace) mode is easy to drop silently;
  it is the main regression surface and is explicitly covered by AC 3 and AC 6

## Status

**Open** | Created: 2026-07-31 | Priority: P2

## Acceptance Criteria

- [ ] `ll-issues prioritize --check` exit code is the FSM-usable gate (0 = all active issues prefixed / 1 = one or more unprioritized), with no LLM narration
- [ ] `--json` lists unprioritized issues; `--all --json` lists every active issue with its `current_priority` (the re-prioritize mode's input)
- [ ] `--apply -` **prepends** a prefix to an unprioritized file and **replaces** `P[X]-` with `P[Y]-` on an already-prioritized one; an entry already at its target priority is a reported no-op, not an error
- [ ] Renames preserve git history for tracked files — asserted via `git log --follow` continuity across the rename — and fall back to `atomic_write()` + `Path.rename()` for untracked files without raising
- [ ] `--apply` is idempotent: re-applying the same map reports no further change and leaves files byte-identical (model on `scripts/tests/test_ll_issues_format_check.py::TestFormatCheckFix`)
- [ ] `commands/prioritize-issues.md` ≤ ~60 lines, containing no glob/regex discovery, no `git mv`, no report tables, and no narrated exit codes — while still supporting **both** initial prioritization and re-prioritization, and retaining the `AskUserQuestion` re-prioritize gate
- [ ] `ll-action invoke prioritize-issues --output json` still succeeds against the slimmed command
- [ ] `ll-verify-skill-prose` reports no findings in `commands/prioritize-issues.md`, and `BASELINE_COUNT` in `scripts/tests/test_verify_skill_prose.py` is ratcheted down accordingly
- [ ] pytest coverage in `scripts/tests/test_ll_issues_prioritize.py` (fixture tree of prioritized/unprioritized/terminal-status issues; `done`/`cancelled`/`deferred` issues are excluded from discovery)
- [ ] Docs updated: new `ll-issues prioritize` section in `docs/reference/CLI.md`, `ll-issues` bullet in `.claude/CLAUDE.md`, `docs/guides/LOOPS_GUIDE.md:1004`, and `.kimi-code` mirror regenerated via `ll-adapt`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): the "Ratchet to 21" target in this
issue's Codebase Research Findings / AC 6 is stale as of ENH-2944's 2026-08-01
revision. ENH-2944 now reports the tree's *actual* live finding count is 21 (not
23, the current `BASELINE_COUNT` constant), and plans to drop `BASELINE_COUNT`
directly `23 → 19` on its own landing — anticipating this issue's 2 findings as
well as its own. If this issue lands **before** ENH-2944, dropping `BASELINE_COUNT`
to 21 would be correct (23 - this issue's 2). If it lands **after** ENH-2944,
`BASELINE_COUNT` will already be at 19, and this issue must drop it to 17, not 21.
Do not hardcode 21 — re-run `ll-verify-skill-prose` and ratchet
`BASELINE_COUNT` to whatever the actual live finding count is after removing this
issue's own two `prioritize-issues.md` findings, per ENH-2944's own instruction
("whichever lands second must re-verify and re-lower rather than assume its own
delta").


## Session Log
- `/ll:manage-issue` - 2026-08-02T04:40:35 - `ff4bd2ff-759f-495b-ac87-7d656baf9f74.jsonl`
- `/ll:ready-issue` - 2026-08-02T04:20:09 - `3a9faa41-1510-47ad-9f40-51a9e8c896a6.jsonl`
- `/ll:confidence-check` - 2026-08-02T04:18:13 - `9ce2895b-bc39-430e-a14f-d0d1c4f93fe5.jsonl`
- `/ll:wire-issue` - 2026-08-02T04:16:05 - `c01ac7d1-aa5c-4397-92ed-055a0fdc6d55.jsonl`
- `/ll:refine-issue` - 2026-08-02T04:08:21 - `3d8b066a-21a6-42a4-862b-cb329564d710.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-01T17:53:29 - `92537019-48b2-41a8-b0c0-d76fae16dd95.jsonl`
