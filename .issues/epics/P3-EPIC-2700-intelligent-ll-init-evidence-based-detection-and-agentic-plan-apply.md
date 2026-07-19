---
id: EPIC-2700
title: 'Intelligent ll-init: evidence-based detection + agentic plan/apply'
type: EPIC
priority: P3
status: open
captured_at: '2026-07-19T00:00:00Z'
discovered_date: 2026-07-19
discovered_by: capture-issue
labels:
- init
- cli
- detection
- dx
---

# EPIC-2700: Intelligent ll-init — evidence-based detection + agentic plan/apply

## Summary

`ll-init --yes` is a template-driven scaffolder, not a code-aware
configurator. Detection depth is shallow: file-presence globbing picks the
project-type template, and everything else (`src_dir`, `test_cmd`/`lint_cmd`/
`format_cmd`/`type_cmd`, `scan.focus_dirs`, `scan.exclude_patterns`,
`documents.categories`) is a static template literal. On an atypical layout
the first headless init produces a config that is structurally correct but
functionally mis-pointed — this repo itself would get `src_dir: src/` on a
fresh init even though the source lives in `scripts/`.

This epic makes init intelligent via a two-tier split:

1. **Deterministic introspection in Python** — read what the repo *declares*
   (`pyproject.toml` tool tables, `package.json` scripts, Makefile targets,
   package-layout markers), tag every derived value with provenance
   (`declared` / `inferred` / `default`), and never guess beyond unambiguous
   evidence.
2. **Agentic judgment through the existing `--plan` / `apply --config` seam**
   — the `/ll:init` skill stops delegating to `--yes` and instead runs
   plan → inspect ambiguous values with the LLM → apply. The CLI stays
   deterministic, testable, and offline; intelligence lives where a model
   already exists.

Source analysis: `thoughts/shallow-ll-init.md`.

## Motivation

- Fresh `--yes` init on any non-default layout silently writes wrong values
  the user must hand-fix (detect.py:124-211 file-presence only;
  core.py:77-200 template literals).
- The headless flow is strictly dumber than the TUI for no reason —
  `detect_documents()` (detect.py:71-121) is only called from tui.py:557.
- The `--plan`/`apply` machinery (cli.py:455-571) is the perfect seam for an
  LLM-in-the-loop init, but the `/ll:init` skill stub (skills/init/SKILL.md)
  just forwards flags to `ll-init --yes`.

## Design Principle

**Read declarations, don't guess.** Deterministic code asserts only what the
repo declares (manifest entries, package markers); ambiguity is surfaced with
provenance and resolved by the skill layer, not by heuristics baked into the
CLI. Detection output is hints-with-provenance, never silent verdicts.

## Child Issues

| Issue | Scope | Depends on |
|-------|-------|------------|
| ENH-2701 | Call `detect_documents()` from `_run_yes` (headless/TUI parity) | — |
| ENH-2702 | Template scoring by match count instead of first-alphabetical | — |
| FEAT-2703 | `init/introspect.py`: manifest-declared commands + src_dir detection with provenance | — |
| ENH-2704 | Enrich `--plan` with provenance + ambiguities; divergence warnings on re-init | FEAT-2703 |
| FEAT-2705 | Rewrite `/ll:init` skill as plan → inspect → apply agentic flow | ENH-2704 |

Sequencing: 2701 and 2702 are independent quick wins; 2703 → 2704 → 2705 is
the core chain.

## Acceptance Criteria (epic-level)

- Fresh `ll-init --yes` on a repo with a non-`src/` layout and declared
  tooling (e.g. this repo) writes correct `src_dir` and commands, or
  explicitly flags them as unverified defaults — never silently wrong.
- `ll-init --plan` output carries provenance for every proposed value plus an
  explicit ambiguity list.
- `/ll:init` resolves ambiguities by reading the repo and applies via
  `ll-init apply --config`.

## Scope Boundaries

- **In**: detection/introspection, plan enrichment, skill rewrite, provenance
  reporting.
- **Out**: LLM calls inside the `ll-init` CLI itself; exhaustive build-system
  coverage (Bazel, Nix, etc.) — the skill layer handles the long tail;
  changes to merge semantics (BUG-2310 deep-merge behavior stays as-is).

## Impact

- **Priority**: P3 — first-run experience for every new adopter; no one is
  hard-blocked (TUI + hand-editing work today).
- **Effort**: Large across children; each child is Small–Medium.
- **Risk**: Low-Medium — additive detection with existing-config
  pre-population still winning on re-runs.

## Status

**Open** | Created: 2026-07-19 | Priority: P3
