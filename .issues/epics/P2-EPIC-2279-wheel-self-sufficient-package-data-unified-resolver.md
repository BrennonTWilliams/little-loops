---
id: EPIC-2279
title: Wheel-self-sufficient package data + unified asset resolver
type: epic
status: done
priority: P2
discovered_date: 2026-06-24
discovered_by: capture-issue
decision_ref: ARCHITECTURE-053
relates_to:
- EPIC-2257
- BUG-938
- BUG-885
- BUG-2266
- ENH-2285
- ENH-2286
- ENH-2287
- ENH-2288
- ENH-2291
labels:
- epic
- packaging
- templates
- host-compat
- cross-host
- install
- path-resolution
---

# EPIC-2279: Wheel-self-sufficient package data + unified asset resolver

## Summary

A single defect class spans eight issues: **package code under `little_loops/`
reaches outside the package — via `Path(__file__)` traversal or a hardcoded
`claude` literal — to read a repo-root asset that the pip wheel does not contain
and non-Claude hosts never deliver, and degrades silently.** Today these assets
(`templates/`, `hooks/prompts/`, `hooks/adapters/`, `assets/`) reach users only
because Claude Code's `marketplace.json` (`source: "./"`) pulls the whole repo —
a Claude-only crutch. Every other delivery path (`pip install little-loops` for
both Claude users **and** Codex / Gemini / omp) gets only the wheel, which omits
them.

This epic owns the structural fix as one coherent unit: **make the wheel
self-sufficient for the data its own code reads, behind one shared resolver, and
gate the class so it cannot recur.**

## Motivation

- **Two failure axes, one cause.** (A) The dominant `pip install` →
  `ll-init` onboarding path silently misconfigures projects (templates, design
  tokens, goals, project-type detection) even for Claude users. (B) Every
  non-Claude host on the roadmap is broken at its first step (Codex adapter,
  section loading, prompt hook). Both trace to the same package-data-escapes-the-
  wheel root.
- **The dev loop hides it.** Editable installs (`pip install -e ./scripts`)
  resolve every escaping `__file__` path into the source tree, so maintainers
  never reproduce the failure — it ships undetected.
- **It recurs.** Six instances to date (BUG-885, 2271, 2273, 2275, 2276, plus the
  2278 variant); without a gate there will be a seventh.

## Scope

**In scope:**
- Packaging the host-agnostic, code-consumed assets into the wheel (FEAT-2274,
  extended to `hooks/prompts/`, `hooks/adapters/`, `assets/` per BUG-2275 /
  BUG-2276).
- One shared template/asset resolver (in-package → `.ll/templates/` → config
  override → `CLAUDE_PLUGIN_ROOT` / `__file__` fallbacks) consumed by every
  loader, replacing the per-callsite `__file__` traversals.
- The `ll-issues sections` accessor + project-local deploy (ENH-2272).
- A prevention gate keyed on the defect: manifest-completeness check (primary) +
  `__file__`-escape lint + wheel smoke test (ENH-2277).

**Out of scope:**
- Host-plugin assets adapted per host (`skills/`, `commands/`, `agents/`,
  `.claude-plugin/`, host-plugin hook glue) — stay out of the wheel (BUG-938
  stance preserved; ARCHITECTURE-053 refines the boundary to "package data the
  CLIs read goes in; per-host-adapted plugin assets stay out").
- Install-scope *detection* (BUG-2266) — adjacent but a different root cause
  (Claude `plugin list` parsing); tracked directly under EPIC-2257 via FEAT-2267.

## Children

Sequencing — FEAT-2274 is the structural enabler; the resolver fixes consume it;
ENH-2277 gates the result:

- **FEAT-2274** (P2) — Package host-agnostic package data into the wheel
  (templates + hooks/prompts + hooks/adapters + assets). *Enabler.*
- **BUG-2271** (P3) — `issue_template._default_templates_dir()` resolver
  (section-template loaders).
- **BUG-2273** (P2) — `ll-init` `_plugin_root()` resolver (design-tokens / goals
  / project-type).
- **BUG-2275** (P2) — `hooks/` package data (prompt-optimization template +
  Codex adapter) excluded from the wheel.
- **BUG-2276** (P4) — CLI logo asset excluded from the wheel.
- **BUG-2278** (P4) — `skill_expander` pre-expansion silently disabled on
  non-editable / non-Claude; no host-skill-dir awareness.
- **ENH-2272** (P3) — `ll-issues sections` accessor + project-local template
  deploy + unified resolver precedence.
- **ENH-2277** (P3) — Left-shift gates (manifest-completeness check + escape lint
  + wheel smoke test). *Closes the class.*
- **ENH-2291** (P3) — Update doc/agent/skill path references after BUG-2275
  hooks in-package move. *Documentation follow-up; depends on BUG-2275.*

## Acceptance Criteria

- `pip install little-loops` (non-editable) + `ll-init` in a target project, in a
  plain shell with `CLAUDE_PLUGIN_ROOT` unset, deploys design tokens + goals,
  detects project type correctly, loads issue sections, renders the
  prompt-optimization hook, installs the Codex adapter, and shows the CLI logo —
  none silently no-op.
- All code-consumed assets are reachable via the single shared resolver; no
  remaining per-callsite `__file__` escapes outside the resolver + allowlist.
- ENH-2277's manifest-completeness check is green and wired into CI, so a future
  unshipped asset fails the build rather than an end user.
- Host-plugin assets (`skills/` etc.) remain absent from the wheel (BUG-938
  preserved).

## Impact

- **Priority**: P2 — unblocks correct onboarding on the dominant `pip install`
  path (Claude included) and every non-Claude host; currently silent and
  shipping.
- **Effort**: Medium — one packaging move + one shared resolver + accessor/deploy
  + prevention gate; the per-issue surface is small.
- **Risk**: Medium — touches packaging and a repo-root directory move; editable
  installs and Claude plugin delivery must both keep working.
- **Breaking Change**: No (internal layout / packaging).

## Related

- EPIC-2257 — tracked under (sibling, **not** a `parent:` child: epic-progress
  aggregation is non-recursive, so this epic is linked via `relates_to` + 2257's
  "Tracked sub-epics" prose, matching EPIC-1463 / 2178 / 2258). Multi-host
  generalization portfolio; this epic also fixes the pip-install Claude path,
  not only cross-host hosts.
- BUG-2266 — install-scope detection (adjacent, different cause; under EPIC-2257).
- BUG-938 — closed invalid; ARCHITECTURE-053 refines its rule here.
- BUG-885 — precedent: moved `loops/` into the package for the same class.

## Resolution

**Closed 2026-06-26.** All 12 children are `done`
(`ll-issues epic-progress EPIC-2279` = 12/12 resolved, 100%) — FEAT-2274 plus
BUG-2271 / BUG-2273 / BUG-2275 / BUG-2276 / BUG-2278 and the ENH-2272 /
ENH-2277 / ENH-2291 follow-ups. The defect class is now gated: the
package-data prevention gate (`ll-verify-package-data`) ships and is wired as a
console entry point (`scripts/pyproject.toml:85`), the Codex adapter is packaged
in-wheel (`scripts/little_loops/hooks/adapters/codex/hooks.json`), and the
per-callsite `__file__` traversals are consolidated behind the shared resolver
(`skill_expander._find_plugin_root`). Both acceptance axes — the dominant
`pip install` → `ll-init` Claude path and the non-Claude host surface — are
satisfied, and a future unshipped asset fails the build rather than an end user.

## Verification Notes

- **2026-06-26** (/ll:verify-issues): Closed EPIC-2279 — set `status: done` and
  added a Resolution note; all 12 children verified `done` (epic-progress 100%)
  and the `ll-verify-package-data` prevention gate confirmed wired at
  `scripts/pyproject.toml:85`.

## Status

**Done** | Created: 2026-06-24 | Closed: 2026-06-26 | Priority: P2
