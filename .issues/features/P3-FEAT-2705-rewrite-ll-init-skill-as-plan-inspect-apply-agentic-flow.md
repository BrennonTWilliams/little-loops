---
id: FEAT-2705
title: Rewrite /ll:init skill as plan → inspect → apply agentic flow
type: FEAT
priority: P3
status: open
captured_at: '2026-07-19T00:00:00Z'
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
---

# FEAT-2705: Rewrite `/ll:init` skill as plan → inspect → apply agentic flow

## Summary

The `/ll:init` skill (skills/init/SKILL.md) is a flag-forwarding stub that
delegates to `ll-init --yes` — the one place where an LLM is already in the
loop runs the dumbest code path. Rewrite it as the intelligence layer over
the existing `--plan` / `apply --config` seam (init/cli.py:455-571): run the
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
- **Dependency chain is unmet today**: `ENH-2704` (`depends_on: FEAT-2703`)
  and `FEAT-2703` are both `status: open`. `_run_plan`
  (`scripts/little_loops/init/cli.py:455-488`) currently emits only
  `{detected, proposed_config, host_options, warnings}` — no `provenance` or
  `ambiguities` keys exist yet. Step 2 of this issue's Expected Behavior has
  no data source to parse until both upstream issues land.
- `_run_apply` (`cli.py:491-571`) reads only `plan.get("proposed_config") or
  plan` (line 528) — any `provenance`/`ambiguities` keys the skill's
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
  (`cli.py:561`), never `_dispatch_host_upgrade`. Since this issue's Scope
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
  cli.py:532) do the rest.
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
  round-trip in its own epilog (`cli.py:591-592`):
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
- `scripts/little_loops/init/cli.py:455-488` (`_run_plan`) and `:491-571`
  (`_run_apply`) — the skill's sole CLI touchpoints; both are read-only from
  this issue's perspective (Scope Boundaries exclude CLI changes) but their
  current I/O contract (`--plan` stdout shape, `apply -c <file>` semantics)
  bounds what the skill can rely on until `ENH-2704`/`FEAT-2703` land.
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

### Documentation
- SKILL.md `## Examples` section (lines 51-59) — rewrite to reflect the new
  four-step flow instead of pure `--yes` passthrough.
- `docs/reference/CLI.md` and `.claude/CLAUDE.md` `ll-init` entries already
  describe `--plan`/`apply` at the CLI level and need no change from this
  issue (only the skill wrapper changes).

### Configuration
- N/A — no `.ll/ll-config.json` schema changes; this issue only changes how
  the skill drives the existing CLI.

## Implementation Steps

1. Gate on upstream dependency: confirm `ENH-2704`'s `provenance`/
   `ambiguities` keys are present in `ll-init --plan` output (i.e. `FEAT-2703`
   + `ENH-2704` are `done`) before starting — this issue's step 2 has no
   data source otherwise.
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

- **Priority**: P3 — biggest capability jump of the epic; depends on the
  contract from ENH-2704.
- **Effort**: Medium — mostly skill authoring + fixtures for the two
  behavioral tests.
- **Risk**: Low-Medium — worst case equals today's behavior (apply an
  unedited plan); guarded by the edit-only-unverified-keys rule.

## Status

**Open** | Created: 2026-07-19 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-07-19T22:59:21 - `b98aa7db-da27-43b3-85e6-fb1720608033.jsonl`
