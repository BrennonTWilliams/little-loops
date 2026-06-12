---
id: ENH-1982
title: Deprecate /ll:init skill to a redirect stub
type: enhancement
status: open
priority: P2
discovered_date: 2026-06-05
discovered_by: capture-issue
parent: EPIC-1978
blocked_by:
- BUG-2042
- ENH-2092
relates_to:
- EPIC-1978
- FEAT-1979
- FEAT-1980
- FEAT-1981
- ENH-2043
labels:
- init
- cleanup
- skill
confidence_score: 100
outcome_confidence: 72
score_complexity: 17
score_test_coverage: 15
score_ambiguity: 20
score_change_surface: 20
decision_needed: false
---

# ENH-1982: Deprecate /ll:init skill to a redirect stub

## Summary

Once `ll-init` (FEAT-1979/1980/1981) reaches parity, collapse the ~1,250-line
`/ll:init` skill into a thin redirect stub and delete the prose wizard. This
removes the parallel implementation so there is one source of truth for init.

## Current Behavior

`/ll:init` is a ~1,250-line interactive prose wizard (`skills/init/SKILL.md` + `skills/init/interactive.md`) that runs a multi-round in-session wizard to scaffold project configuration. It duplicates init logic now owned by `ll-init` (Python CLI, FEAT-1979/1980/1981), creating drift risk between the two parallel implementations.

## Expected Behavior

`/ll:init` is a thin redirect stub (< 60 lines) that prints a one-line handoff banner and auto-invokes `ll-init --yes`, passing through recognized flags (`--force`, `--dry-run`, `--codex`/`--hosts`). The generated config is identical to before; only the in-session interaction path changes.

## Motivation

EPIC-1978's whole point is that init logic should live once, in Python.
Leaving the prose skill in place would guarantee drift between it and
`ll-init`. The user's decision (2026-06-05) is to **deprecate the skill
entirely** rather than convert it to a `--plan`/`apply` wrapper — the
in-session interactive path needs a real PTY the host `!`-prefix can't reliably
provide, and first-run almost always happens in a terminal where `ll-init` runs
natively.

## What to Build

Replace `skills/init/SKILL.md` body with a short stub that, when invoked
in-session as `/ll:init`:

1. Detects whether stdin is interactive. It generally is not (the skill runs
   inside the host), so:
2. **Decision resolved**: the stub will auto-run `ll-init --yes` (non-interactive
   defaults). Rationale: the config it produces is safe to write unprompted
   (same output as `--yes` always was), and auto-run is friendlier than forcing
   the user to switch terminals. The stub should print a one-line banner before
   running: "Guided init moved to CLI — running `ll-init --yes` with detected
   defaults…" so the handoff is visible.
3. Passes through recognized flags (`--force`, `--dry-run`, `--codex`/`--hosts`)
   to `ll-init` so existing muscle-memory invocations keep working.

Cleanup:
- Delete `skills/init/interactive.md` (967 lines, not 925 — measured 2026-06-11).
- Reduce `skills/init/templates.md` to only what the stub still needs (or
  remove if fully owned by the Python core).
- Update the skill description/frontmatter to reflect the redirect role.

## Acceptance Criteria

- `skills/init/SKILL.md` is a short stub (target < 60 lines) with no
  duplicated procedure.
- `interactive.md` removed; `ll-verify-skills` (≤ 500 lines) trivially passes.
- `/ll:init` in-session still does something correct and non-confusing
  (either writes a default config or cleanly redirects).
- Recognized flags pass through to `ll-init`.
- README / `.claude/CLAUDE.md` / HOST_COMPATIBILITY reflect `ll-init` as the
  canonical init path.
- No remaining doc points users at the old multi-round wizard.

## Dependencies

- **Blocked by** BUG-2042 — three parity gaps in `ll-init` (`deploy_design_tokens`
  not called, `history.session_digest` missing from generated config,
  `Skill(ll:explore-api)` permission not wired for learning-tests). Fix BUG-2042
  before deleting the prose wizard.
- FEAT-1979, FEAT-1980, FEAT-1981 are all `done` — dependency unblocked.
- ENH-2043 (TUI CLAUDE.md screen) is P3 and can follow in a separate PR;
  it does not block this stub.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **BUG-2042 is `done`** (completed 2026-06-09) — all three parity gaps resolved; this blocker is cleared.
- **ENH-2092 is `done`** — TUI config-capability parity with `/ll:init` is complete; this blocker is also cleared.
- **ENH-1982 is now fully unblocked.** Implementation can begin immediately.

## Integration Map

### Files to Modify
- `skills/init/SKILL.md` — collapse to stub.
- `.claude/CLAUDE.md`, `README.md`, `docs/reference/HOST_COMPATIBILITY.md` —
  point at `ll-init`.

### Files to Delete
- `skills/init/interactive.md`.
- `skills/init/templates.md` (if fully absorbed by the Python core).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `skills/init/agents/openai.yaml` — Codex Skills API frontmatter for this skill; must be updated (description) or deleted alongside the stub rewrite. Currently has `display_name: "Init"` and `short_description` tied to wizard behavior.
- `templates.md` **can be fully deleted**: all referenced procedures are already in the Python core (`writers.py`). The only `templates.md` content not in Python (summary display, command availability check, hook dependency validation) are wizard-only behaviors that disappear with the redirect stub — nothing survives to the stub.

### Dependent Files (Callers/Importers)
- `scripts/tests/test_wiring_reference_docs.py` — asserts `/ll:init` appears in `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` and `docs/reference/CONFIGURATION.md`; fixture list must be updated in the same commit

_Wiring pass added by `/ll:wire-issue`:_
- `commands/help.md` — lines 230–232 list `--interactive` in the `/ll:init` flags entry; remove `--interactive`, add `--hosts`
- `commands/align-issues.md` — lines 46, 448, 459 reference `/ll:init --interactive` and "Round 5" wizard language; replace with `ll-init` + `/ll:configure documents`
- `skills/configure/SKILL.md` — lines 27, 427 describe `/ll:init` as a "full interactive initialization wizard"; update wizard framing to reflect redirect stub
- `hooks/scripts/session-start.sh` — lines 101, 152 emit a warning pointing users to `/ll:init` when config is missing; update to `ll-init`
- `scripts/little_loops/hooks/session_start.py` — line 217, Python version of the same session-start warning; update to `ll-init`

### Similar Patterns

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `skills/update/SKILL.md` — **closest analogue**: uses `disable-model-invocation: true`, declares a `flags` argument, parses `*"--flag"*` glob matching, and delegates to a single CLI command via `Bash(...)`. This is the canonical pattern for a redirect stub with flag pass-through.
- `skills/analyze-history/SKILL.md` — minimal `disable-model-invocation: true` + `Bash(ll-history:*)` pattern; demonstrates a narrow allowed-tools list.
- `skills/ll-toggle-autoprompt/SKILL.md` — shortest existing stub (12 lines); pure bridge with no body logic. Too thin for this use case but shows minimum viable frontmatter.
- **`disable-model-invocation: true` note**: setting this flag in frontmatter makes the skill exempt from the `ll-verify-skills` 500-line check (`doc_counts.py:check_skill_sizes()` line 369 skips these). The stub should set this regardless since it will be <60 lines.
- **Allowed-tools for stub**: `Bash(ll-init:*)` — no existing skill calls `ll-init`, but the `Bash(<cmd>:*)` pattern is used throughout (e.g., `Bash(ll-history:*)`, `Bash(ll-loop:*)`).
- **`--hosts` flag note**: the current skill only exposes `--codex` (deprecated alias) in its frontmatter; `--hosts` is Python CLI-only. The stub's `argument-hint` and `arguments.flags.description` should add `--hosts` since it is now the canonical host-selection flag.

### Tests
- `scripts/tests/test_wiring_reference_docs.py` — update fixture to reference `ll-init` (not `/ll:init`) in targeted docs
- Manual: invoke `/ll:init --dry-run` after stub is written; confirm flag pass-through and banner display

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh494_skill_companions.py` — line 27: `SKILLS_DIR / "init" / "templates.md"` is in `EXPECTED_COMPANIONS`; three tests in `TestCompanionFilesExist` will break when `templates.md` is deleted (`test_companion_exists`, `test_companion_non_empty`, `test_skill_links_to_companion`); remove this entry from the list
- `scripts/tests/test_enh1768_profile_system.py` — three test methods will break: `test_init_round_7_offers_profile_picker` (reads `interactive.md` directly → file not found), `test_init_skill_references_profiles_dir` (asserts SKILL.md contains `"profiles/"`), `test_init_skill_references_active` (asserts SKILL.md contains `"design_tokens.active"`); all three must be removed (stub contains none of this content)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`scripts/tests/test_wiring_init_and_configure.py`** — **critical, not in issue**: this file has **72 lines** of string-presence assertions against `skills/init/SKILL.md` and `skills/init/interactive.md` wizard content. All of these will fail when the stub is written and `interactive.md` is deleted. Examples of failing assertions:
  - Lines 22–25: Learning tests content in `interactive.md` and `SKILL.md`
  - Lines 35–36: Design tokens references
  - Lines 53–54: Analytics round
  - Lines 87–115: Various SKILL.md wizard-step strings (ll-create-extension, ll-harness, product.enabled, ll-goals.md, Round 4, etc.)
  - Lines 116–120: interactive.md product-opt-in strings
  - Line 125: `Bash(ll-history-context:*)` in SKILL.md
  - The full list of assertions targeting these two files must be removed (or commented out with `# REMOVED (stub):` prefix matching the pattern already in use at lines 114, 121) in the same commit as SKILL.md replacement.
- **`test_wiring_reference_docs.py` update pattern**: replace `("/ll:init", "ENH-1401")` entries at lines 101–102 with `("ll-init", "ENH-1982")` entries after updating the doc files; do not just comment them out (the docs will now contain `ll-init`).

### Documentation
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — remove prose-wizard references, add `ll-init` CLI guidance
- `docs/reference/CONFIGURATION.md` — update init section to reference `ll-init`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/development/TROUBLESHOOTING.md` — line 31: `"Run /ll:init to create config"` in the "Config file not found" section; update to `ll-init` (low-priority; stub still handles the invocation but pointing directly to `ll-init` is clearer)
- `config-schema.json` — `learning_tests.enabled` description at line 901 contains `"Set via /ll:init or /ll:configure."`; update to `ll-init` (cosmetic/low-priority)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`docs/reference/CONFIGURATION.md`**: `/ll:init` appears at **lines 3, 350, and 1235** — all three need updating. Line 350 also mentions `--interactive` mode which goes away.
- **`docs/guides/ISSUE_MANAGEMENT_GUIDE.md`**: `/ll:init` at **line 184**.
- **`docs/reference/COMMANDS.md`**: contains `/ll:init` documentation — not in the issue's doc list; needs review and update.
- **`docs/guides/GETTING_STARTED.md`**: references both `/ll:init` and `ll-init` — references to the wizard should be updated.
- **`README.md`**: `/ll:init` at **lines 92 and 128** (line 92 mentions `/ll:init --codex`, line 128 shows it in a usage example).

### Configuration
- N/A

## Implementation Steps

1. ~~Confirm BUG-2042 is resolved~~ — **done** (2026-06-09); ~~confirm ENH-2092 is resolved~~ — **done**. Implementation can begin.
2. Write redirect stub in `skills/init/SKILL.md` (< 60 lines): set `disable-model-invocation: true`, `Bash(ll-init:*)` in allowed-tools, banner message + `ll-init --yes` + flag pass-through for `--force`, `--dry-run`, `--hosts`, `--codex`. Model after `skills/update/SKILL.md` flag-parsing pattern.
3. Delete `skills/init/interactive.md` (967 lines) and `skills/init/templates.md` (329 lines — fully owned by Python core; safe to delete).
4. Update `skills/init/agents/openai.yaml` description to reflect redirect role (or delete if appropriate).
5. Update skill frontmatter: remove `--interactive` from `argument-hint` and `arguments.flags.description`; add `--hosts`; update `description:` and `metadata.short-description:`.
6. Update `README.md` (lines 92, 128), `.claude/CLAUDE.md`, `docs/reference/HOST_COMPATIBILITY.md`, `docs/reference/COMMANDS.md`, `docs/guides/GETTING_STARTED.md`.
7. Update `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` (line 184), `docs/reference/CONFIGURATION.md` (lines 3, 350, 1235) — replace `/ll:init` with `ll-init`; remove `--interactive` references.
8. Update `scripts/tests/test_wiring_reference_docs.py` lines 101–102: change needle from `/ll:init` to `ll-init` and issue_id to `ENH-1982`.
9. Update `scripts/tests/test_wiring_init_and_configure.py`: remove or comment out all ~72 assertions targeting `skills/init/SKILL.md` wizard-content strings and `skills/init/interactive.md` — the stub will not contain any of this content. Use `# REMOVED (stub ENH-1982):` prefix, matching existing commenting pattern.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Update `commands/help.md` — remove `--interactive` from the `/ll:init` flags list (lines 230–232); add `--hosts`
11. Update `commands/align-issues.md` — replace `/ll:init --interactive` at lines 46, 448, 459 with `ll-init` (or `/ll:configure documents` for feature-flag context); remove "Round 5" wizard framing
12. Update `skills/configure/SKILL.md` — remove "full interactive initialization wizard" framing at lines 27 and 427; rewrite to reference `ll-init` or the redirect stub
13. Update `hooks/scripts/session-start.sh` — change "run `/ll:init`" warning (lines 101, 152) to `ll-init` so the cold-start message points directly to the CLI
14. Update `scripts/little_loops/hooks/session_start.py` — same warning at line 217; update to `ll-init`
15. Update `scripts/tests/test_enh494_skill_companions.py` — remove `SKILLS_DIR / "init" / "templates.md"` entry from `EXPECTED_COMPANIONS` (line 27)
16. Update `scripts/tests/test_enh1768_profile_system.py` — remove `test_init_round_7_offers_profile_picker`, `test_init_skill_references_profiles_dir`, and `test_init_skill_references_active` (all three methods will fail after `interactive.md` is deleted and SKILL.md loses wizard content)
17. Update `docs/development/TROUBLESHOOTING.md` — line 31: change `"/ll:init"` to `"ll-init"` in "Config file not found" section (low-priority)
18. Update `config-schema.json` — `learning_tests.enabled` description at line 901: change `"/ll:init"` to `"ll-init"` (low-priority cosmetic)
19. Run `ll-verify-skills` and full test suite (`python -m pytest scripts/tests/`). All tests must pass.

## Impact

- **Priority**: P2 — completes the epic; without it the drift risk remains.
- **Effort**: Small.
- **Risk**: Low — gated behind parity; pure deletion + redirect.
- **Breaking Change**: Soft — `/ll:init` no longer runs the in-session wizard;
  produced config is unchanged.

## Scope Boundaries

**In scope:**
- Replace `skills/init/SKILL.md` body with redirect stub (< 60 lines)
- Delete `skills/init/interactive.md` (967 lines, not 925 — measured 2026-06-11)
- Reduce or remove `skills/init/templates.md` (if fully absorbed by Python core)
- Update `README.md`, `.claude/CLAUDE.md`, `docs/reference/HOST_COMPATIBILITY.md` to reference `ll-init`

**Out of scope:**
- ENH-2043 (TUI CLAUDE.md screen) — follows in a separate PR, does not block this stub
- Changes to `ll-init` Python CLI behavior — BUG-2042 is a prerequisite, not part of this issue
- Modifying the generated config format or init logic

## Labels

`init`, `cleanup`, `skill`

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-06-11 (original: 2026-06-08)_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 72/100 → MODERATE

### Outcome Risk Factors
- **No automated coverage for stub behavior**: The redirect stub in `skills/init/SKILL.md` has no unit tests (`disable-model-invocation: true` skills have none by convention). Flag pass-through and banner display require manual verification after implementation.
- **Test suite will regress unless wiring fixtures are updated atomically**: `test_wiring_reference_docs.py` (lines 101–102) and `test_wiring_init_and_configure.py` (~72 assertions) must be updated in the same commit as their corresponding doc/skill changes (Implementation Steps 8–9).
- **Wide change surface (~22 files) demands atomic commit discipline**: A partial implementation leaves inconsistent `/ll:init` references across docs, commands, hooks, and tests. Follow Implementation Steps through Step 19 (`ll-verify-skills` + full pytest) before committing.

## Verification Notes

**Verdict: BLOCKED** — 2026-06-09. FEAT-1979/1980/1981 are all `done`; `ll-init`
is functional. Three parity gaps remain (BUG-2042): `deploy_design_tokens` not
called, `history.session_digest` absent from generated config, and
`Skill(ll:explore-api)` permission not wired for learning-tests. The redirect
behavior decision (auto-invoke vs. message only) is now resolved: auto-run
`ll-init --yes` with a one-line handoff banner. Ready to implement once BUG-2042
is fixed.

## Session Log
- `/ll:wire-issue` - 2026-06-12T00:12:56 - `421907b7-eeef-46d2-b4eb-d698176407f2.jsonl`
- `/ll:refine-issue` - 2026-06-12T00:03:15 - `b8539015-3d2c-4e3f-84f9-37010ba5ba93.jsonl`
- `/ll:format-issue` - 2026-06-11T23:49:58 - `2ec440c1-aa4c-45d8-abed-c897ed087b60.jsonl`
- `/ll:verify-issues` - 2026-06-09T18:30:00 - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:verify-issues` - 2026-06-09T09:21:00 - `e40557ae-4da3-4ea7-b023-bf5e57e8b61a.jsonl`
- `/ll:confidence-check` - 2026-06-11T00:00:00Z - `59ba1f73-a50f-4768-a7e5-e52acf93219a.jsonl`
- `/ll:confidence-check` - 2026-06-08T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2f4b8008-562a-49e0-b070-2b75fe480d05.jsonl`

## Status

**Open** | Created: 2026-06-05 | Priority: P2
