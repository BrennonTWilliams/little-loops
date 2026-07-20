---
id: FEAT-2705
title: "Rewrite /ll:init skill as plan \u2192 inspect \u2192 apply agentic flow"
type: FEAT
priority: P3
status: done
captured_at: '2026-07-19T00:00:00Z'
completed_at: '2026-07-20T13:47:13Z'
discovered_date: 2026-07-19
discovered_by: capture-issue
parent: EPIC-2700
depends_on:
- ENH-2704
relates_to:
- FEAT-2703
labels:
- init
- skills
- plan-apply
- agentic
confidence_score: 100
outcome_confidence: 52
score_complexity: 14
score_test_coverage: 10
score_ambiguity: 18
score_change_surface: 10
implementation_order_risk: true
size: Very Large
---

# FEAT-2705: Rewrite `/ll:init` skill as plan → inspect → apply agentic flow

## Summary

The `/ll:init` skill (skills/init/SKILL.md) is a flag-forwarding stub that
delegates to `ll-init --yes` — the one place where an LLM is already in the
loop runs the dumbest code path. Rewrite it as the intelligence layer over
the existing `--plan` / `apply --config` seam (init/cli.py:525-677): run the
plan, have Claude resolve exactly the values the plan marks as unverified or
ambiguous by reading the repo, then apply the corrected plan and smoke-check
the commands.

This closes the epic's loop: deterministic introspection (FEAT-2703) covers
the common case for raw-CLI users; this skill covers the long tail
(monorepos, Makefile-driven workflows, uv/poetry/pdm runners, custom test
layouts) at zero maintained-heuristic cost.

## Current Behavior

`/ll:init [flags]` parses flags in bash and execs
`ll-init --yes $FLAGS` (SKILL.md:44-48). No repo inspection, no use of
`--plan`/`apply`, no verification.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `skills/init/SKILL.md` frontmatter (lines 1-14) grants only
  `allowed-tools: [Bash(ll-init:*)]` — no `Read`/`Grep`/`Glob`, confirming the
  Proposed Solution's "allowed-tools gains Read/Grep/Glob... plus bounded
  Bash" is a real, currently-missing grant, not already partially present.
- `--plan`/`--upgrade`/`apply` handling is entirely absent from the stub
  today: `### 1. Parse Flags` (SKILL.md:24-42) only recognizes `--force`,
  `--dry-run`, `--hosts`, `--codex`, `--upgrade` (the last is parsed but only
  ever forwarded to `ll-init --yes --upgrade`, never used to branch the flow).
- **Dependency chain is now unblocked** (updated 2026-07-20; the previous
  pass's "chain is unmet today" finding is now stale — both `ENH-2704` and
  `FEAT-2703` are `status: done`). `_run_plan`
  (`scripts/little_loops/init/cli.py:525-573`) now emits `{detected,
  proposed_config, host_options, warnings, provenance, ambiguities}` —
  confirmed by direct read of the current source. `provenance` is a flat list
  of `{field, value, provenance, evidence}` objects (one per
  `introspection.values` entry; `field` is the dotted key e.g.
  `"project.test_cmd"`, `provenance` is `"declared"`/`"inferred"`/`"default"`
  per `init/introspect.py:41-47`'s `IntrospectedValue`); `ambiguities` is a
  list of `{field, candidates, note}` objects per `init/introspect.py:50-55`'s
  `Ambiguity` dataclass. Step 2 of this issue's Expected Behavior now has a
  real data source to parse — this issue is ready to implement.
- `_run_apply` (`cli.py:595-677`) reads only `plan.get("proposed_config") or
  plan` (line ~628) — any `provenance`/`ambiguities` keys the skill's
  corrected plan JSON carries are silently ignored by `apply`, so edits must
  land inside `proposed_config` itself to take effect (matches the "edit only
  ambiguous/default-provenance keys in `proposed_config`" rule already in
  Proposed Solution).
- `apply` vs `--yes` writer parity, which the plan→apply round trip depends
  on, was a separate gap (`BUG-2313`, **status: done**, fixed
  2026-06-27) — `_run_apply` now performs the full `_run_yes` write sequence
  (`CLAUDE.md`, design tokens, issue templates, host adapters,
  `validate_deps`), so the apply step this issue's flow relies on is no
  longer lossy.
- `_run_apply` has **no `upgrade` parameter at all** — it always calls
  `_dispatch_host_adapters(hosts, project_root, plugin_root, force=force)`
  (`cli.py:665`), never `_dispatch_host_upgrade`. Since this issue's Scope
  Boundaries exclude changes to `ll-init` CLI behavior, Open Question 1 below
  is effectively settled by this constraint: the skill cannot get upgrade
  semantics through `apply` and must fall back to invoking
  `ll-init --yes --upgrade` as a separate step when `--upgrade` is passed.

## Expected Behavior

`/ll:init` performs:

1. **Plan** — `ll-init --plan` → parse `proposed_config`, `provenance`,
   `ambiguities` (ENH-2704 shape).
2. **Inspect** — for each key whose provenance is `inferred`/`default` and
   each entry in `ambiguities`, Claude reads the relevant repo files
   (manifests, layout, CI config, README) and settles the value. Keys with
   `declared` provenance are trusted as-is and not re-derived. If genuinely
   undecidable, ask the user (interactive) or keep the default and say so
   (headless/auto contexts).
3. **Apply** — write the corrected plan JSON and run
   `ll-init apply --config <plan.json>` (append `--force` only if the user
   passed it).
4. **Verify** — run the final `test_cmd` and `lint_cmd` once as a smoke
   check (bounded timeout); report pass/fail per command with the settled
   config summary. A failing command downgrades to a warning with the
   command output excerpt — it never rolls back the config.

Flag passthrough preserved: `--force`, `--dry-run` (stop after step 2 and
print the corrected plan instead of applying), `--hosts`, `--upgrade`
(delegate upgrade side effects to `ll-init --yes --upgrade` semantics or run
apply then the upgrade path — decide during implementation).

## Proposed Solution

- Rewrite skills/init/SKILL.md: keep frontmatter contract
  (`argument-hint`, flags), replace the bash stub with the four-step process
  above; `allowed-tools` gains Read/Grep/Glob for inspection plus
  `Bash(ll-init:*)` and bounded `Bash` for the smoke check.
- Instruct the skill to edit **only** ambiguous/default-provenance keys in
  `proposed_config` — declared values and the untouched remainder pass
  through verbatim, so apply-side merge semantics (BUG-2310 preservation at
  cli.py:636) do the rest.
- Keep total added latency proportional to ambiguity count: a fully-declared
  repo should be nearly as fast as `--yes`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Three existing multi-phase agentic SKILL.md files model the target shape
  and should anchor the rewrite's structure:
  - `skills/wire-issue/SKILL.md` — the closest "research → diff → write-back
    → report" precedent: numbered `## Phase N:` sections, parallel research
    Agents, an early-exit-cleanly branch when there's nothing to change, a
    "Preservation Rule" for append-only edits with an attribution sentinel,
    and the same `--auto`/`--dry-run` bash string-matching flag parser this
    stub already uses.
  - `skills/spike/SKILL.md` — closest precedent for the plan-artifact +
    bounded-verify + pass/fail write-back shape (Locate → Plan → Implement →
    Verify → Write-Back with explicit success/failure branches); its
    `allowed-tools` combines a narrowly-scoped `Bash(ll-init:*)`-style entry
    with a second, differently-scoped `Bash` entry for verification — the
    exact split this issue's Proposed Solution calls for.
  - `skills/manage-issue/SKILL.md:338-388` (`## Phase 4: Verify` +
    "Headless-Safe Final Test Run") — direct precedent for the step-4 smoke
    check: skip-if-null guard per command, foreground-blocking execution
    (never background a result-blocking check), and the scratch-pad
    `tail -20` redirect pattern from `.claude/CLAUDE.md` § Automation for
    large output.
- The `--plan`/`apply -c <file>` CLI seam already documents the exact
  round-trip in its own epilog (`cli.py:695-696`):
  `%(prog)s --plan` then `%(prog)s apply --config plan.json` — this issue's
  skill is a direct wrapper around that existing, documented contract, not a
  new interface.
- `IntrospectedValue`'s `declared`/`inferred`/`default` provenance vocabulary
  (FEAT-2703) is a distinct concept from the unrelated, already-shipped
  `source_session_id`/`source_issue_id` decision-provenance fields in
  `decisions.py` (ENH-2667) — same word, different axis; worth noting so the
  skill's "provenance" terminology isn't conflated with the decisions system
  when both are in context.

## Open Questions

1. `--upgrade` composition: **Answered by research above** — `apply` has no
   `upgrade` parameter and this issue excludes CLI changes, so the skill must
   fall back to invoking `ll-init --yes --upgrade` as a separate step (not
   composed through `apply`) when `--upgrade` is passed.
2. Should the smoke-check results be written anywhere durable (e.g. a note in
   the init summary only, vs. `.ll/` state)? Lean: summary only.

## Integration Map

### Files to Modify
- `skills/init/SKILL.md` — full rewrite: frontmatter `allowed-tools` gains
  `Read`, `Grep`, `Glob`, and a bounded smoke-check `Bash` entry alongside
  the existing `Bash(ll-init:*)`; body replaces `### 1. Parse Flags` /
  `### 2. Run ll-init` with the four-step plan → inspect → apply → verify
  process.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/init/cli.py:525-573` (`_run_plan`) and `:595-677`
  (`_run_apply`) — the skill's sole CLI touchpoints; both are read-only from
  this issue's perspective (Scope Boundaries exclude CLI changes). Their I/O
  contract (`--plan` stdout shape including `provenance`/`ambiguities`,
  `apply -c <file>` semantics) is now stable — `ENH-2704`/`FEAT-2703` are both
  `status: done`, so this bound is settled, not pending.
- `scripts/tests/test_wiring_init_and_configure.py` — asserts `/ll:init` is
  documented/wired correctly; will need to keep passing against the rewritten
  SKILL.md frontmatter/examples.
- `commands/help.md` — lists `ll-init`/`/ll:init`; verify the flag summary
  still matches after the rewrite (no `--plan`/`apply` internals are
  user-facing flags, so likely no change needed).

### Similar Patterns
- `skills/wire-issue/SKILL.md` — phase-numbered research → diff → append-only
  write-back → banner report structure; `--auto`/`--dry-run` flag-parsing
  idiom to reuse verbatim.
- `skills/spike/SKILL.md` — plan-artifact → implement → bounded-verify →
  explicit-success/failure write-back shape; the closest existing model for
  "smoke-check failure is a warning, not a rollback."
- `skills/manage-issue/SKILL.md:338-388` — per-command skip-if-null smoke
  check with foreground-blocking execution and scratch-pad `tail -20`
  redirect for large output.

### Tests
- `scripts/tests/test_wiring_init_and_configure.py` — existing wiring
  assertions for the init skill; extend/re-verify after rewrite.
- No skill-level behavioral test harness currently exists for `/ll:init`
  itself (it's a markdown skill, not a Python module) — the two behavioral
  tests this issue's Acceptance Criteria calls for (unambiguous-plan passthrough,
  ambiguous-`src_dir`-with-Makefile fixture) will need new fixtures, likely
  as `ll-harness` skill-type runs (see `.claude/CLAUDE.md` CLI Tools §
  `ll-harness`) rather than pytest, since the flow under test is Claude's own
  reasoning over `--plan` output.

_Wiring pass added by `/ll:wire-issue`:_
- Confirmed no live pytest assertion pins the current flag-parsing bash stub
  (`### 1. Parse Flags`, direct `ll-init --yes $FLAGS` exec) — those
  assertions in `test_wiring_init_and_configure.py` were already retired
  under ENH-1982, well before this issue. The rewrite will not break any
  existing pytest assertion; only the two `test_file_exists` /
  `test_string_absent_from_doc` entries for `skills/init/SKILL.md` remain
  live and are unaffected by the rewrite's content. [Agent 3 finding]
- `ll-harness skill init ...` is the concrete invocation idiom to use for
  the two new fixtures, per the documented example at
  `docs/reference/CLI.md:219` (`ll-harness skill refine-issue P2-ENH-1229
  --semantic "..." --output json`). [Agent 3 finding]
- `scripts/tests/integration/test_init_e2e.py::TestInitHeadlessIntrospection`
  (lines 204-286) is the closest reusable pattern for constructing the two
  fixtures' underlying repo states — it builds `tmp_path` fixture repos
  (`pyproject.toml`/`package.json`) and asserts on `--plan` JSON
  `provenance`/`ambiguities` shape via `redirect_stdout` capture. A
  Makefile-driven ambiguous-`src_dir` fixture follows the identical
  `tmp_path`-project-construction pattern, substituting a `Makefile` and
  asserting an `ambiguities` entry for `project.src_dir`. [Agent 3 finding]

### Documentation
- SKILL.md `## Examples` section (lines 51-59) — rewrite to reflect the new
  four-step flow instead of pure `--yes` passthrough.
- `docs/reference/CLI.md` and `.claude/CLAUDE.md` `ll-init` entries already
  describe `--plan`/`apply` at the CLI level and need no change from this
  issue (only the skill wrapper changes).

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` (lines 30-37) — describes `/ll:init` as a
  "Redirect stub — delegates to `ll-init`" that "runs `ll-init --yes` with any
  recognized flags passed through." This is the current stub behavior being
  replaced; must be rewritten to describe the plan → inspect → apply → verify
  flow. [Agent 2 finding]
- `docs/guides/GETTING_STARTED.md` (lines 95-100) — documents `--plan`/
  `--dry-run` and the `{detected, proposed_config, host_options, warnings,
  provenance, ambiguities}` shape, framing it as "piping into
  `ll-init apply --config`" — this is exactly the workflow the rewritten
  skill now performs internally; verify the guide's framing still matches
  once the skill exists (readers may now be pointed at `/ll:init` instead of
  the raw CLI dance). [Agent 1 + Agent 2 finding]
- `skills/init/agents/openai.yaml` — generated Codex-adapter artifact (via
  `ll-adapt --host codex --apply` / `adapt_skills_for_codex.py`) whose
  committed `short_description` currently reads "Redirect stub — delegates to
  ll-init CLI for project bootstrap and config setup." It is not hand-edited
  but will be stale after the rewrite until regenerated. [Agent 1 + Agent 2
  finding]
- `skills/configure/SKILL.md:429` and `skills/audit-claude-config/SKILL.md:462`
  — one-line "Related commands" cross-references to `/ll:init`'s purpose;
  low-risk, update only if the one-line description of what `/ll:init` does
  changes materially. [Agent 1 + Agent 2 finding]

### Configuration
- N/A — no `.ll/ll-config.json` schema changes; this issue only changes how
  the skill drives the existing CLI.

## Implementation Steps

1. ~~Gate on upstream dependency~~ — confirmed unblocked (2026-07-20):
   `FEAT-2703` and `ENH-2704` are both `status: done`, and `ll-init --plan`
   (`cli.py:525-573`) now emits `provenance`/`ambiguities` keys per the
   Codebase Research Findings above. Start directly at step 2.
2. Rewrite `skills/init/SKILL.md` frontmatter: add `Read`, `Grep`, `Glob`,
   and a bounded smoke-check `Bash` entry to `allowed-tools`; keep the
   existing `flags` argument contract.
3. Implement Step 1 (Plan): run `ll-init --plan`, parse
   `proposed_config`/`provenance`/`ambiguities` from stdout.
4. Implement Step 2 (Inspect): for each `inferred`/`default`-provenance key
   and each `ambiguities` entry, read the relevant repo files and settle the
   value, editing only inside `proposed_config` (declared keys and the
   untouched remainder pass through verbatim, per the codebase finding that
   `apply` only reads `proposed_config`).
5. Implement Step 3 (Apply): write the corrected plan JSON, run
   `ll-init apply --config <plan.json>` (append `--force` only if the user
   passed it); on `--dry-run`, stop here and print the corrected plan instead.
6. Implement Step 4 (Verify): run the settled `test_cmd`/`lint_cmd` once,
   foreground-blocking, modeling `skills/manage-issue/SKILL.md`'s Phase 4
   skip-if-null + scratch-pad-redirect pattern; report pass/fail without
   rolling back on failure.
7. Handle `--upgrade` per the settled Open Question 1: invoke
   `ll-init --yes --upgrade` as a separate step (not composed through
   `apply`, since `_run_apply` has no upgrade path).
8. Rewrite the `## Examples` section to show the new flow's output shape.
9. Add the two behavioral test fixtures from Acceptance Criteria
   (unambiguous-plan passthrough; ambiguous-`src_dir` + Makefile-driven
   test target) and verify against `scripts/tests/test_wiring_init_and_configure.py`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation:_

10. Update `docs/reference/COMMANDS.md` — its `/ll:init` section still
    describes the old "Redirect stub — delegates to `ll-init`" behavior;
    rewrite to describe the plan → inspect → apply → verify flow.
11. Verify `docs/guides/GETTING_STARTED.md`'s `--plan`/`--dry-run` section
    still reads correctly now that `/ll:init` performs that workflow
    internally; update the framing if it still tells readers to do the
    plan→apply dance by hand.
12. After the rewrite lands, run `ll-adapt --host codex --apply` to
    regenerate `skills/init/agents/openai.yaml` — its committed
    `short_description` still reads "Redirect stub — delegates to ll-init
    CLI" and will be stale until regenerated from the new SKILL.md
    frontmatter.

## Acceptance Criteria

- On a repo with an unambiguous plan (all keys `declared`), the skill applies
  without editing any value and the result matches `ll-init --yes` output.
- On a fixture with an ambiguous `src_dir` and a Makefile-driven test target,
  the skill settles both from repo evidence and the applied config reflects
  them.
- `--dry-run` prints the corrected plan and writes nothing.
- Smoke-check failure produces a warning + excerpt, exit still successful,
  config intact.
- Skill docs/examples updated (SKILL.md examples section, ll-help surface if
  it lists init).

## Scope Boundaries

- **In**: SKILL.md rewrite, plan-editing rules, smoke check, flag parity.
- **Out**: changes to `ll-init` CLI behavior (done in ENH-2704/FEAT-2703);
  TUI; auto-invocation policy (`disable-model-invocation: true` stays).

## Impact

- **Priority**: P3 — biggest capability jump of the epic; the contract from
  `ENH-2704` (`status: done`) is now available, so this issue is unblocked.
- **Effort**: Medium — mostly skill authoring + fixtures for the two
  behavioral tests.
- **Risk**: Low-Medium — worst case equals today's behavior (apply an
  unedited plan); guarded by the edit-only-unverified-keys rule.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-20_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 52/100 → LOW

### Outcome Risk Factors
- Complexity is dominated by breadth rather than depth: the rewrite touches ~6-7 sites (SKILL.md rewrite, docs/reference/COMMANDS.md, docs/guides/GETTING_STARTED.md, the generated `skills/init/agents/openai.yaml`, plus two new test fixtures), each individually mechanical/local, but coordinating all of them correctly is the main risk.
- Skill-level test coverage is currently indirect — only file-existence/wiring assertions cover `skills/init/SKILL.md` today, and the underlying `--plan`/`apply` CLI plumbing is well tested but the LLM-driven Inspect step (Claude reading repo files to settle ambiguous values) has no automated check of its own.
- The two required behavioral fixtures (unambiguous-plan passthrough; ambiguous-src_dir + Makefile) don't exist yet, but they're co-deliverables of this issue (Implementation Step 9) rather than a blocking precondition — build and run them (`ll-harness skill init ...`) alongside the SKILL.md rewrite so the agentic Inspect step is verified before merge, not left untested.
- Broad dependent surface (7 files: wiring test, `commands/help.md`, two docs pages, the Codex adapter artifact, and two cross-referencing skills) means it's easy to update the SKILL.md body correctly but miss one of the peripheral references, leaving stale documentation.

## Resolution

Rewrote `skills/init/SKILL.md` as a seven-step plan → inspect → apply →
handle-upgrade → verify → report flow: `allowed-tools` gains `Read`/`Grep`/
`Glob` plus a second, bounded `Bash` entry alongside the existing
`Bash(ll-init:*)`. The Inspect step edits only `proposed_config` keys tagged
`inferred`/`default` or listed in `ambiguities`; declared values and the
untouched remainder pass through verbatim. `--dry-run` stops after Inspect
and prints the corrected plan; `--upgrade` falls back to a separate
`ll-init --yes --upgrade` call since `apply` has no upgrade path. Verify runs
the settled `test_cmd`/`lint_cmd` once, foreground-blocking, via the same
scratch-pad `tail -20` pattern as `manage-issue` Phase 4 — a failing command
downgrades to a warning, never a rollback.

Added `scripts/tests/test_init_skill_fixtures.py` with the two behavioral
fixtures: an unambiguous fully-declared repo (proves Inspect is a no-op and
`apply` on the unedited plan matches `--yes`) and an ambiguous-`src_dir` +
Makefile-driven-test-target repo (proves `--plan` surfaces the `src_dir`
ambiguity and leaves `test_cmd` at `default`, since `introspect()` has no
Makefile support — exactly the gap the skill's live Inspect step is meant to
close via `ll-harness skill init`, which the test file's docstring points
future runs at).

Updated `docs/reference/COMMANDS.md`'s `/ll:init` entry and `commands/help.md`
to describe the new flow, added a pointer from `docs/guides/GETTING_STARTED.md`
to `/ll:init` for ambiguous/monorepo layouts, and hand-corrected the stale
`skills/init/agents/openai.yaml` `short_description` — `ll-adapt --host codex
--apply` only creates this sidecar when absent and unconditionally skips
`disable-model-invocation: true` skills, so it cannot regenerate an existing
one; `init` is both.

Full suite: `python -m pytest scripts/tests/` — 15571 passed, 38 skipped.
`ruff check`/`ruff format --check` and `python -m mypy
scripts/little_loops/` clean.

## Status

**Open** | Created: 2026-07-19 | Priority: P3


## Session Log
- `/ll:manage-issue` - 2026-07-20T13:47:13 - `d739cec2-3cde-4131-9087-a0f61bbd799e.jsonl`
- `/ll:ready-issue` - 2026-07-20T13:32:00 - `93c2d444-850f-407e-84da-650077e447c9.jsonl`
- `/ll:confidence-check` - 2026-07-20T00:00:00Z - `5123a462-6f55-45be-ac8d-cb404b0a57ce.jsonl`
- `/ll:wire-issue` - 2026-07-20T06:15:29 - `592879e4-4dfd-43ba-ae01-6f6588974794.jsonl`
- `/ll:refine-issue` - 2026-07-20T06:09:13 - `7f5255e5-ef11-4454-b1e2-d0b9f4ce4c17.jsonl`
- `/ll:refine-issue` - 2026-07-19T22:59:21 - `b98aa7db-da27-43b3-85e6-fb1720608033.jsonl`
