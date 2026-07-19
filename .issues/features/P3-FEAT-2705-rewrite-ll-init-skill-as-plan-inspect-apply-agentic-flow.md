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

## Open Questions

1. `--upgrade` composition: run `apply` then invoke the upgrade refresh, or
   fall back to `--yes --upgrade` when `--upgrade` is passed?
2. Should the smoke-check results be written anywhere durable (e.g. a note in
   the init summary only, vs. `.ll/` state)? Lean: summary only.

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
