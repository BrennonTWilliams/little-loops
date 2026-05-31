---
id: EPIC-1751
title: Design Tokens System
type: EPIC
priority: P3
status: done
captured_at: "2026-05-27T20:30:00Z"
discovered_date: "2026-05-27"
discovered_by: issue-size-review
labels: [epic, design-system, config, loops, init]
relates_to: [FEAT-1747, FEAT-1748, FEAT-1749, FEAT-1750, ENH-1768]
---

# EPIC-1751: Design Tokens System

## Summary

Add a semantically layered design-token system to little-loops so that built-in artifact-generating loops produce visually coherent output that matches the project's design system instead of inventing ad-hoc colors per run. Covers config schema, Python loader, default high-contrast palette, loop wiring (6 loops), and `/ll:init` / `/ll:configure` UX.

## Goal

When this epic is done:
- `ll-config.json` has a `design_tokens` section pointing at a directory of layered JSON token files.
- `/ll:init` prompts about design tokens and materializes `.ll/design-tokens/` from a bundled high-contrast, WCAG AA–compliant default palette.
- `ll-loop run` and `ll-loop resume` pre-inject `design_tokens_context` into `fsm.context` so the six built-in artifact loops (`hitl-compare`, `hitl-md`, `html-website-generator`, `html-anything`, `svg-image-generator`, `svg-textgrad`) reference semantic token names instead of inventing colors.
- When `design_tokens.enabled: false` or the path is missing, all loops fall back to current behavior with no errors.

## Motivation

Every run of `html-anything` / `svg-image-generator` is a fresh aesthetic guess today. Two runs produce visually unrelated artifacts; runs across loops share no palette. Once a project sets `design_tokens.path`, all built-in loops (and user-authored loops) get a clean injection point — no per-loop palette duplication, no drift between `hitl-md` styling and `html-website-generator` output.

## Scope

### In scope

- `design_tokens` block in `config-schema.json` and `DesignTokensConfig` dataclass (FEAT-1747)
- `design_tokens.py` loader with reference-resolution and renderers (FEAT-1747)
- Four-file default palette under `templates/design-tokens/` with WCAG AA verification (FEAT-1748)
- Pre-injection of `design_tokens_context` into `fsm.context` at `run.py` and `lifecycle.py` (FEAT-1749)
- Six built-in loop YAML updates to reference `${context.design_tokens_context}` (FEAT-1749)
- `/ll:init` interactive round + materialization step (FEAT-1750)
- `/ll:configure` `design_tokens` area (FEAT-1750)
- Docs: `CONFIGURATION.md`, `ARCHITECTURE.md`, `API.md`, README (FEAT-1750)

### Out of scope

- Style Dictionary / Theo CSS-var transforms (future)
- Runtime WCAG contrast validation (verified at palette-author time only)
- User-authored loop support beyond the pattern being available

## Children

- **FEAT-1747** — Core infrastructure: schema field, `DesignTokensConfig`, `design_tokens.py` loader, baseline tests
- **FEAT-1748** — Default palette: four-file WCAG AA–verified template set under `templates/design-tokens/`
- **FEAT-1749** — Loop wiring: pre-inject `design_tokens_context` into `fsm.context` for all 6 artifact loops
- **FEAT-1750** — Init / Configure UX + docs
- **ENH-1768** — Multi-profile system with `design_tokens.active` selector; ships 2–3 starter profiles, init picker, configure switcher (follow-up to FEAT-1747/1748/1750)

## Implementation Order

```
FEAT-1747 (core infra) ──┬──→ FEAT-1749 (loop wiring)
FEAT-1748 (palette)    ──┤
                          └──→ FEAT-1750 (init/configure/docs)
```

1. **FEAT-1747** and **FEAT-1748** — start in parallel; no interdependence.
2. **FEAT-1749** — unblocks when FEAT-1747 merges (loader must exist for injection sites).
3. **FEAT-1750** — unblocks when both FEAT-1747 (schema/dataclass) and FEAT-1748 (template files) merge.

## Integration Map

### Primary Files

- `config-schema.json` — new `design_tokens` block
- `scripts/little_loops/config/features.py` — `DesignTokensConfig`
- `scripts/little_loops/config/core.py` — `BRConfig` wiring
- `scripts/little_loops/design_tokens.py` (new) — loader + renderers
- `templates/design-tokens/` (new) — four-file default palette
- `scripts/little_loops/cli/loop/run.py` — first injection site
- `scripts/little_loops/cli/loop/lifecycle.py` — second injection site (resume)
- `scripts/little_loops/loops/{hitl-compare,hitl-md,html-website-generator,html-anything,svg-image-generator,svg-textgrad}.yaml`
- `skills/init/interactive.md`, `skills/init/SKILL.md`
- `skills/configure/SKILL.md`, `skills/configure/areas.md`

### Tests

- `scripts/tests/test_design_tokens.py` (new)
- `scripts/tests/test_config.py` — `TestDesignTokensConfig`, `TestBRConfigDesignTokensIntegration`
- `scripts/tests/test_config_schema.py` — `test_design_tokens_in_schema`
- `scripts/tests/test_hook_session_start.py` — fixture fixes + `test_warns_design_tokens_enabled_without_path`
- `scripts/tests/test_hooks_integration.py` — fixture fixes
- `scripts/tests/test_ll_loop_program_md.py` — context injection test
- `scripts/tests/test_builtin_loops.py` — per-loop `test_context_has_design_tokens_context`

## Impact

- **Priority**: P3 — quality-of-life and visual coherence; no user is blocked
- **Effort**: Medium aggregate (~26 files across 4 children)
- **Risk**: Low — feature is opt-out via `enabled: false`; loops fall back to current behavior when tokens are absent
- **Breaking Change**: No

---

**Open** | Created: 2026-05-27 | Priority: P3

## Verification Notes

_Added by `/ll:verify-issues` on 2026-05-31_

**Verdict: RESOLVED** — All children are done and referenced files exist:
- FEAT-1747, FEAT-1748, FEAT-1749, FEAT-1750, ENH-1768: all `status: done` ✓
- `scripts/little_loops/design_tokens.py` exists ✓
- Action: Set `status: done` in frontmatter

## Session Log
- `/ll:verify-issues` - 2026-05-31T05:53:48 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
