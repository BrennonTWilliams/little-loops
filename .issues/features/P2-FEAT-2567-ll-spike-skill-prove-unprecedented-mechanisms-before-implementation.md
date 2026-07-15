---
id: FEAT-2567
title: "/ll:spike skill \u2014 prove unprecedented mechanisms in isolation before\
  \ implementation"
type: FEAT
priority: P2
status: done
labels:
- skills
- confidence
- risk-reduction
- captured
captured_at: '2026-07-10T01:34:59Z'
completed_at: '2026-07-15T17:30:37Z'
discovered_date: '2026-07-10'
discovered_by: capture-issue
parent: EPIC-2570
confidence_score: 98
outcome_confidence: 75
score_complexity: 17
score_test_coverage: 18
score_ambiguity: 20
score_change_surface: 20
---

# FEAT-2567: /ll:spike skill — prove unprecedented mechanisms in isolation before implementation

## Summary

Add a `/ll:spike` skill that retires concentrated technical risk on an issue by planning, implementing, and verifying a code spike — a standalone library + test class proving a novel mechanism in isolation — before the real integration point is touched. On success it appends `## Spike Results` to the issue, sets `spike_completed: true` in frontmatter, and re-scoring via `/ll:confidence-check` should recover the outcome-confidence points the unproven mechanism cost.

The ENH-2565 spike plan (readiness-gated pop + concurrency core for `rn-refine` `synth_pop`) is the golden example of the deliverable shape this skill should produce.

## Current Behavior

When `/ll:confidence-check` scores outcome confidence low because a mechanism has zero precedent in the codebase and no test exercises the risky core (ENH-2565: 66/100 for exactly these two reasons), there is no `/ll:` skill that produces the correct remedy. The existing remediation skills cover other failure modes:

- `/ll:decide-issue` — unresolved Option A/B ambiguity (`decision_needed`)
- `/ll:wire-issue` + `/ll:refine-issue --gap-analysis` — absent files / unwired integration (`missing_artifacts`)
- `/ll:issue-size-review` — issue too large; decompose
- `/ll:explore-api` + Learning-Test Registry — unproven **external** API assumptions

None of these applies when the risk is a novel **internal** mechanism (e.g., a flock-guarded readiness-gated queue pop with N-worker fan-out). Today the spike is planned ad-hoc by the coding agent, with no standard plan shape, no standard spike directory, no frontmatter signal, and no write-back to the issue.

## Expected Behavior

```bash
/ll:spike ENH-2565                 # plan + implement + verify spike for the issue's risk factors
/ll:spike ENH-2565 --plan-only     # produce/refresh the spike plan file, do not implement
/ll:spike ENH-2565 --plan path.md  # use a caller-supplied plan file (skip plan generation)
/ll:spike ENH-2565 --auto          # non-interactive (automation contexts)
/ll:spike ENH-2565 --check         # FSM evaluator: exit 0 if spike ACs pass, 1 otherwise; no writes
```

Workflow: read the issue's `Outcome Risk Factors` / `Confidence Check Notes` → identify which risks a spike retires → write a spike plan (Context, Approach, Critical files, Implementation, AC-per-risk test table, Verification commands, Out of scope, Promotion) → implement in an isolated spike package → run the AC suite plus the named regression suites → on pass, write back `## Spike Results` (retired risks, spike location, verification transcript summary, promotion path) and set `spike_completed: true`.

## Use Case

An AI coding agent (or human) refining ENH-2565 gets outcome-confidence 66/100 with risk factors "(a) the flock-guarded readiness-gated pop has zero precedent in any loop YAML, (b) no existing test exercises N-worker FSM fan-out with a real barrier." Running `/ll:spike ENH-2565` produces `scripts/tests/spike/rn_refine_synth_pop/` (library + driver + `TestSynthPopReadinessGate`), runs the three verification pytest commands, appends Spike Results to the issue, and the downstream loop-YAML work proceeds against a proven core.

## Proposed Solution

New skill at `skills/spike/SKILL.md` (invocable as `/ll:spike`), following the argument-parsing, `--auto`/`--check`, session-log, and frontmatter-flag conventions of `skills/confidence-check/SKILL.md` and `commands/ready-issue.md`.

### Phases

1. **Parse args & locate issue** — `ll-issues path`, standard flag parsing (`--auto`, `--check`, `--plan-only`, `--plan <file>`; auto-enable AUTO_MODE under `LL_NON_INTERACTIVE` / `--dangerously-skip-permissions`).
2. **Risk extraction** — read `## Confidence Check Notes` → `### Outcome Risk Factors` (and `## Spike Plan` if present). Each risk factor that names an unproven mechanism becomes a row in the spike's AC table. If no risk factors exist and no `--plan` given, run standalone analysis of the Proposed Solution to identify the riskiest unprecedented mechanism; in interactive mode confirm scope with AskUserQuestion.
3. **Plan** — write `<run-artifacts>/spike-<ISSUE-ID>.md` in the ENH-2565 plan shape. Mandatory sections: Context (why confidence was low), Approach, Critical files, Implementation (package layout under `scripts/tests/spike/<slug>/`, API sketch), test-class table mapping each test → the AC/risk it retires, at least one regression-guard test (e.g., AST sniff preventing a forbidden import), Acceptance criteria, Verification (exact pytest commands incl. existing regression suites), Out of scope, Promotion (post-spike move to `scripts/little_loops/spike/<slug>/`, separate PR).
4. **Implement** — build the spike package + test class exactly as planned. Spike code lives only under `scripts/tests/spike/`; production files are read-only in this skill.
5. **Verify** — run the plan's Verification commands. All must exit 0.
6. **Write-back** — append `## Spike Results` to the issue (retired risks table, spike paths, verification summary, promotion path); set `spike_completed: true` and record `spike_attempted: true` in frontmatter (idempotent, CLI/Edit pattern per confidence-check Phase 4); append session log via `ll-issues append-log`. On failure: set only `spike_attempted: true`, append `## Spike Findings` with what was disproven — a *failed* spike is also signal (the approach is wrong; route to decide/size-review).
7. **Recommend next step** — `Run /ll:confidence-check [ID]` to re-score, then proceed to implementation.

### Budget discipline

One spike per issue by default: if `spike_attempted: true` is already set, refuse unless `--force` (mirrors `max_refine_count` discipline). The skill itself is bounded to the plan's AC suite — no open-ended exploration.

## Scope Boundaries

- **Not** the FSM/loop integration — `spike_needed` flag detection in confidence-check, autodev triage routing, and a `spike-gate.yaml` wrapper loop are ENH-2568.
- **Not** promotion — moving accepted spike code into `scripts/little_loops/spike/` stays a manual, separate-PR step documented in the plan's Promotion section.
- **Not** external-API proving — that remains `/ll:explore-api` + Learning-Test Registry; the skill should point there when a risk factor names a third-party API.
- Python/pytest spikes only in v1 (matches the ENH-2565 precedent). Other harnesses out of scope.

## API/Interface

- New skill directory `skills/spike/` (SKILL.md + `agents/openai.yaml` stub, matching sibling skills).
- New `/ll:spike` command surface: `[issue-id]` + `--auto | --check | --plan-only | --plan <file> | --force`.
- New frontmatter fields consumed/produced: `spike_attempted`, `spike_completed` (read by ENH-2568's routing later).
- Exit-code contract for `--check`: 0 = spike ACs pass, 1 = fail (FSM `evaluate: type: exit_code` compatible).

## Integration Map

### Files to Create
- `skills/spike/SKILL.md` — the skill.
- `skills/spike/plan-template.md` — the ENH-2565-shaped plan template with per-section guidance.
- `skills/spike/agents/openai.yaml` — parity stub like sibling skills.
- `scripts/tests/spike/__init__.py` — spike package root (if not already created by ENH-2565's spike).

### Files to Modify
- `commands/help.md` — register the new skill.
- `skills/ll-help/SKILL.md` (and any skill-count doc checks; see [[readme_conventions]] `ll-verify-docs` count checks) — update counts/listings.
- `docs/` skills reference — add `/ll:spike` entry.
- `.claude-plugin/` manifest if skills are enumerated there.

### Dependent Files
- ENH-2568 (autodev triage + spike-gate loop) will invoke `/ll:spike --auto` and `--check`.

### Similar Patterns
- `skills/confidence-check/SKILL.md` — flag parsing, frontmatter write-back via CLI, findings write-back, `--check` evaluator contract.
- `skills/explore-api/SKILL.md` — "prove an assumption with running code, record the proof" (external-API analogue).
- `skills/wire-issue/SKILL.md` — issue-mutating remediation skill invoked from autodev triage.
- ENH-2565 spike plan (readiness-gated pop) — golden example of the plan deliverable.

### Tests
- Doc-count / plugin-manifest checks (`ll-verify-docs`) must pass with the new skill registered.
- Optional: a fixture-level test that the plan template contains all mandatory sections.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_adapt_skills_for_codex.py` — `TestRealSkillsIntegrationGuard` (`test_all_real_skills_have_name_field` ~:343, `test_all_real_skills_have_metadata_short_description` ~:370 [≤80 chars], `test_all_real_skills_have_openai_yaml` ~:403) globs every `skills/*/SKILL.md` and **will fail** unless `skills/spike/` has matching `name:` frontmatter, a `metadata.short-description` ≤80 chars, and `agents/openai.yaml`. **Do NOT hand-author `agents/openai.yaml`** — run `ll-adapt-skills-for-codex --apply` to auto-generate it (established path; `_make_openai_yaml` in `cli/adapt_skills_for_codex.py:~147`) [Agent 3 finding].
- `scripts/tests/test_wiring_skills_and_commands.py` — append rows to the `DOC_STRINGS_PRESENT` parametrize list (~:20) so the existing `test_string_present_in_doc` (~:182) enforces the `commands/help.md` + `skills/ll-help/SKILL.md` registrations, e.g. `("commands/help.md", "spike", "FEAT-2567")` [Agent 3 finding].
- `scripts/tests/test_wiring_reference_docs.py` — same parametrize-append pattern for any new `docs/reference/*.md` / README prose (model on the `("docs/reference/ISSUE_TEMPLATE.md", "spike_needed", "ENH-2569")` sibling entry at ~:25) [Agent 3 finding].
- **New test to write** — `scripts/tests/test_spike_skill.py` (keep it a **flat file**, not under a `scripts/tests/spike/` subpackage — no in-repo precedent for test subpackages; all test files are flat). Model the plan-template mandatory-sections fixture on the anchor-slicing `_phase_text()` helper in `test_confidence_check_skill.py:15-19,90-95` [Agent 3 finding].
- `ll-verify-triggers` (`scripts/tests/test_verify_triggers.py`) — the new skill needs should-fire / should-not-fire trigger phrasings or it risks dropping the suite below threshold / colliding with a sibling; author a clean, non-colliding description [Agent 1 finding].
- `ll-verify-skill-budget` — the skill description counts against the listing token budget; keep it within budget (exit 1 if over) [Agent 1 finding].
- `scripts/tests/test_enh494_skill_companions.py::TestSkillLineLimit` (~:74) — glob-based 500-line cap; auto-covers `SKILL.md`. `plan-template.md` is a **template**, not an ENH-494 overflow companion, so do NOT add it to the `EXPECTED_COMPANIONS` list (~:24-35) unless SKILL.md later overflows into it [Agent 3 finding].
- **No hardcoded real-skill-count pytest assertion exists** — the `ll-verify-docs` count check reads the live `skills/` dir vs. doc prose, so only the README/CLAUDE.md prose counts need bumping (no fixture edit) [Agent 3 finding].

### Documentation
- README / docs skills tables per [[readme_conventions]].
- CHANGELOG entry.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/ISSUE_TEMPLATE.md` (~:889) — **already documents** `spike_needed`/`spike_attempted`/`spike_completed` frontmatter fields (landed with ENH-2569). The spike skill should **reference** this rather than re-document; verify the field descriptions still match the write-back semantics in Phase 6 [Agent 1 finding].
- `commands/ready-issue.md` — has **no** remediation-skill table to add a row to; recommendations are inline conditional text (`explore-api` at ~:181-183, `issue-size-review` at ~:402). If `/ll:spike` should be recommended when `spike_needed: true`, add a **new inline conditional line** mirroring ~:402's style — not a table edit [Agent 2 finding].
- `commands/help.md:331` and `.claude/CLAUDE.md:66` `Planning & Implementation` rollups are **already out of sync** (help.md lacks `confidence-check`/`go-no-go` that CLAUDE.md has) — pre-existing drift, not from this issue. When adding `spike` to both, avoid widening the drift [Agent 2 finding].
- `skills/confidence-check/reference.md` / `rubric.md` — **unverified**: confirm whether the confidence-check terminal-output templates print a "Run `/ll:spike`" recommendation when `spike_needed: true` is set (Phase 4.10 sets the flag but the recommendation wiring wasn't inspected). If absent, that recommendation line is a small follow-on (arguably ENH-2568 scope) [Agent 2 finding].

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config-schema.json` — confirmed **no** `commands.spike.*` precedent (the `commands` object at ~:447 has a `confidence_gate` sibling at ~:465 but no `spike`). Schema edit is optional/deferred for v1 — **not** load-bearing. Note: the schema lives at `scripts/little_loops/config-schema.json`, not repo-root [Agent 2 finding].
- `.claude-plugin/plugin.json` — confirmed **no edit needed**; `"skills": ["./skills"]` auto-discovers the new dir [Agent 2 finding].

### Configuration
- Optional future key `commands.spike.*` (e.g., default spike dir) — not required for v1.

## Implementation Steps

1. Draft `skills/spike/plan-template.md` by generalizing the ENH-2565 spike plan.
2. Write `skills/spike/SKILL.md` with Phases 1–7 above, mirroring confidence-check's conventions.
3. Register the skill (help.md, docs, plugin manifest); run `ll-verify-docs`.
4. Dogfood against ENH-2565: `/ll:spike ENH-2565 --plan <existing plan>` should implement and verify the already-written plan unchanged.
5. Capture dogfood learnings back into the template.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Ensure `skills/spike/SKILL.md` has `name: spike` frontmatter + a `metadata.short-description` ≤80 chars, then run `ll-adapt-skills-for-codex --apply` to auto-generate `skills/spike/agents/openai.yaml` (do not hand-author) — satisfies `test_adapt_skills_for_codex.py::TestRealSkillsIntegrationGuard`.
7. Write a clean, non-colliding skill description with should-fire/should-not-fire trigger phrasings so `ll-verify-triggers` stays above threshold and `ll-verify-skill-budget` stays in budget.
8. Add `skills/spike/` registration rows to `test_wiring_skills_and_commands.py` `DOC_STRINGS_PRESENT` (and `test_wiring_reference_docs.py` if new reference-doc prose is added).
9. Write `scripts/tests/test_spike_skill.py` (flat file) asserting the plan-template's mandatory sections, modeled on `test_confidence_check_skill.py`'s `_phase_text()` slicing helper.
10. Add `/ll:spike` to both `commands/help.md:331` and `.claude/CLAUDE.md:66` `Planning & Implementation` rollups (mind the pre-existing drift between them); bump the `README.md:177` skill count 67 → 68; run `ll-verify-docs`.
11. (Optional/deferred) Confirm whether `skills/confidence-check/reference.md`/`rubric.md` should print a "Run `/ll:spike`" recommendation when `spike_needed: true`; if so, it's a small follow-on (likely ENH-2568 scope).

## Impact

- **Priority**: P2 — needed now for ENH-2565; closes the only outcome-confidence failure mode with no skill-level remedy.
- **Effort**: Medium — one skill + template + registration; no engine changes.
- **Risk**: Low — additive; touches no loop YAML or Python engine code.
- **Breaking Change**: No.

## Related Issues

- **ENH-2565** — first consumer; its spike plan is the template source.
- **ENH-2569** — confidence-check phase that sets `spike_needed` (not blocked by this issue; can land in parallel).
- **ENH-2568** — downstream FSM integration (autodev routing + spike-gate loop). Blocked by this issue and ENH-2569.
- **ENH-2209 / explore-api** — external-API analogue of the same prove-before-implement principle.

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Frontmatter write-back mechanics (Phase 6)

- **No generic `set-flag` CLI verb exists.** Simple boolean flags (`spike_attempted`, `spike_completed`) must be written with the **Edit tool** directly against the `---` block — the exact inline-block convention confidence-check uses for `spike_needed`/`decision_needed`/`missing_artifacts` (`skills/confidence-check/SKILL.md:447-473`, Phase 4.10). Always set `true`, never `false`; absence is the negative. Idempotency: skip the write if the flag is already `true`.
- **Underlying primitive** if a dedicated CLI is preferred: `update_frontmatter(content, updates)` at `scripts/little_loops/frontmatter.py:243` — regex-matches the block, `yaml.safe_load`s, `dict.update`s, re-dumps with `sort_keys=False` (preserves order, overwrites existing keys, preserves unrelated ones). `ll-issues set-scores` (`scripts/little_loops/cli/issues/set_scores.py`, registered `cli/issues/__init__.py:~669`) is the template for a typed-field CLI subcommand if one is ever added; not required for v1.
- **Read side**: `parse_frontmatter(text, coerce_types=True)` (used by `cli/issues/check_readiness.py`) — the nearest precedent for a `--check` exit-code CLI that reads a frontmatter threshold.

### `## Spike Results` write-back (append-only)

- Follow wire-issue's append-only section pattern (`skills/wire-issue/SKILL.md:319-400`, Phase 8/8c preservation rule): locate insertion point, append a new `##`/`###` block, tag it with a provenance sentinel (e.g. `_Added by \`/ll:spike\` on [date]_`). **Insert before `## Session Log`** (or before `## Status` if no session log), matching confidence-check's `## Confidence Check Notes` insertion rule.

### Session log (Phase 6)

- Primary: `ll-issues append-log <issue-path> /ll:spike` → `cmd_append_log` (`cli/issues/append_log.py:13`) → `append_session_log_entry` (`scripts/little_loops/session_log.py:116`). Auto-resolves the session JSONL, writes **only the JSONL filename** (not abs path), atomic-writes, returns `False`/exit 1 if the session can't be resolved.

### `--check` exit-code evaluator (Phase for FSM)

- Directly model on `skills/format-issue/SKILL.md:381-393` and `skills/confidence-check/SKILL.md:485-489`: run analysis with **no writes**, print `[ID] check: ...` per failure, `exit 1` if any fail else `exit 0`. `--check` should also imply `AUTO_MODE=true`. FSM contract: `evaluate: type: exit_code` (0=pass, 1=fail, 2+=error).

### Skill scaffolding precedent

- **Golden directory-layout precedent**: `skills/format-issue/` (`SKILL.md` + companion `templates.md` + `agents/openai.yaml`). Multi-companion is also fine (`skills/confidence-check/` has `reference.md` + `rubric.md`), which matters given the 500-line SKILL.md cap (`ll-verify-skills`) — overflow the plan-template guidance into `skills/spike/plan-template.md`.
- **`agents/openai.yaml` is a 3-line stub** — copy shape verbatim: `interface: { display_name: "Spike", short_description: "<same as SKILL.md description>" }`.
- **Scope-restriction via `allowed-tools` globs**: `skills/ll-refine-issue/SKILL.md` uses `Edit(.issues/**)`. Spike's inverse boundary ("production files read-only; spike code only under `scripts/tests/spike/`") should be enforced with `Write`/`Edit(scripts/tests/spike/**)` **plus** `Edit(.issues/**)` for write-back. Consider `disable-model-invocation: true` (as refine-issue sets) if the skill should be command-only.
- **Budget-discipline precedent**: there is no literal `max_refine_count` config key — the "refuse unless `--force`" shape is the idempotent flag guard above, closest literal wording being `--force-implement` HALT gates in `skills/manage-issue/SKILL.md:166,176`.

### Registration & doc-count gate (Integration Map corrections)

- **`.claude-plugin/plugin.json` needs NO edit** — it already sets `"skills": ["./skills"]`, so `skills/spike/SKILL.md` is auto-discovered. (The Integration Map's "`.claude-plugin/` manifest if skills are enumerated there" resolves to: not enumerated, no change.)
- **`ll-verify-docs` WILL fail unless the skill count is bumped.** `COUNT_TARGETS["skills"] = ("skills", "*/SKILL.md")` (`scripts/little_loops/doc_counts.py:19-34`) counts real skills minus `BRIDGE_MARKER` stubs. The documented count lives at **`README.md:177`** (`**67 skills**` at research time) and must increment by 1.
- **Two rollup lists must gain the new skill name**: `commands/help.md` category rollup (`~:329-333`) **and** `.claude/CLAUDE.md` § Commands & Skills rollup line (`**Planning & Implementation**` group). `ll-verify-docs` cross-checks documented lists against the `skills/*/SKILL.md` glob.
- **`scripts/tests/spike/` does not exist yet** (confirmed on disk). Create `scripts/tests/spike/__init__.py` as the package root (Integration Map "if not already created by ENH-2565's spike" — it wasn't).

### Related-issue status update

- **ENH-2569** (`spike_needed` detection in confidence-check) is **already `done`** (landed 2026-07-14 as Phase 4.10; see `cf32c898`). Its guard already reads `spike_attempted`/`spike_completed`, so spike's frontmatter contract is already consumed upstream. **ENH-2565** (golden-example spike source) is also `done`. **ENH-2568** (autodev routing + spike-gate loop) remains `open`, blocked by this issue.

## Resolution

_Implemented via `/ll:manage-issue` on 2026-07-15._

Delivered the `/ll:spike` skill and supporting scaffolding:

- `skills/spike/SKILL.md` — Phases 1–7 (locate → risk extraction → plan → implement
  → verify → write-back → recommend), mirroring confidence-check conventions:
  flag parsing (`--auto`/`--check`/`--plan-only`/`--plan <file>`/`--force`),
  budget-discipline `spike_attempted` guard, `--check` FSM exit-code evaluator,
  external-API suppression routing to `/ll:explore-api`, and `## Spike Results` /
  `## Spike Findings` write-back setting `spike_completed`/`spike_attempted`.
  `allowed-tools` enforces the production-read-only / spike-write-only boundary
  (`Write`/`Edit(scripts/tests/spike/**)` + `Edit(.issues/**)`).
- `skills/spike/plan-template.md` — the ENH-2565-shaped plan (all mandatory
  sections + mandatory regression-guard test row).
- `skills/spike/agents/openai.yaml` — Codex parity stub (generated via the
  `ll-adapt-skills-for-codex` helper; the editable install pins plugin-root to the
  main tree, so the tool's own `_make_openai_yaml_content` generator was invoked
  directly against the worktree).
- `scripts/tests/spike/__init__.py` — spike package root.
- `scripts/tests/test_spike_skill.py` — asserts plan-template mandatory sections,
  scaffolding layout, short-description ≤80 chars, and the skill's flag/write-back
  contract.
- Registration: `commands/help.md`, `.claude/CLAUDE.md`, `README.md` (67→68
  skills), wiring rows in `test_wiring_skills_and_commands.py` and the
  `68 skills` bump in `test_wiring_guides_and_meta.py`; CHANGELOG 1.145.0.

Verification: full suite `14962 passed`; the only failures (`test_cli_decisions`,
`test_issues_cli` cluster rendering) are pre-existing on the worktree base and
touch none of the files changed here (confirmed independent). `ruff`, `ruff
format --check`, `ll-verify-skills`, `ll-verify-skill-budget`, `ll-verify-triggers`
all pass. Dogfooding a live `/ll:spike ENH-2565` run (Implementation Step 11)
requires an interactive agent session and is deferred to first real use.

## Status

**Done** | Created: 2026-07-10 | Completed: 2026-07-15 | Priority: P2

## Session Log

- `/ll:refine-issue` - 2026-07-15T17:10:37 - `f6dc4f1c-6ed9-47de-9770-a43a3aa5e5c9.jsonl`
- `/ll:capture-issue` - 2026-07-10T01:34:59Z - `manual capture via Claude Cowork session`
- `/ll:wire-issue` - 2026-07-15T12:17:00 - `session JSONL unresolved`
- `/ll:ready-issue` - 2026-07-15T12:20:00 - `session JSONL unresolved`
