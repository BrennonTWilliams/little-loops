---
id: EPIC-2938
title: Offload mechanical work from /ll: skills/commands into ll-* Python CLIs
type: EPIC
priority: P2
status: open
discovered_by: skill-audit
discovered_date: 2026-07-31
labels:
- epic
- skills
- cli
- context-efficiency
- determinism
---

# EPIC-2938: Offload mechanical work from /ll: skills/commands into ll-* Python CLIs

## Summary

An audit of the 36 substantive skill/command markdown files (~24k lines) found ~2,500+ lines of deterministic, mechanical instruction the LLM is asked to execute by hand: Jaccard similarity computed in prose (diverging from `text_utils.py`, a divergence `skills/link-epics/SKILL.md` itself documents), union-find clustering, regex option-detection duplicating the existing `ll-issues check-decidable` CLI, a hardcoded 373-line help catalog, `git mv`/slug/ID bookkeeping, FSM YAML templating, event counting, and LLM-narrated `--check` exit codes that make FSM evaluator gates non-deterministic. This epic converts each mechanical block into a tested Python CLI subcommand and slims the markdown to invoke the CLI, keeping the LLM only for genuine judgment (naming, split decisions, root-cause narration, prompt authoring).

## Motivation

Three concrete harms today:

1. **Drift**: algorithms specified in prose duplicate (and diverge from) Python implementations — Jaccard in 3 skills vs `text_utils.py`; decide-issue's Phase 3 regexes vs `ll-issues check-decidable`; `commands/help.md`'s catalog vs the actual command surface.
2. **Non-determinism**: `--check` exit codes are *narrated* by the model in 8+ files, so FSM `evaluate: type: exit_code` gates depend on the model remembering to exit correctly.
3. **Context waste**: every invocation pays hundreds of lines of mechanical instruction that a subprocess would execute in milliseconds with zero tokens.

`skills/map-dependencies` is the proven target architecture: a thin wrapper over `ll-deps` where all scoring/detection happens in Python and the LLM only accepts or rejects proposals.

## Shared Conventions (apply to every child)

- Every new subcommand gets `--json` output.
- `--check` / `--dry-run` modes are deterministic Python exit codes, never LLM-narrated.
- Runtime config reads use `ll-config get <key>`, never `{{config.*}}` (which only expands under `ll-auto`'s `skill_expander.py`).
- Prefer extending existing CLIs (`ll-issues`, `ll-loop`) over new entry points. Only FEAT-2940 (`ll-help`) adds a new entry point and pays the BUG-2764 triple registration: `scripts/pyproject.toml` + `skills/configure/areas.md` preset + `little_loops/init/writers.py::_LL_PERMISSIONS`.
- Each conversion includes the markdown slimming itself plus pytest coverage in `scripts/tests/` (the only CI).
- Skills that render judgments should emit the `VERDICT_JSON:` / `REVIEW_JSON:` tagged line that `cli/action.py` already parses (adopted in ENH-2949).

## Children

- **ENH-2939** — Delete skill prose duplicating existing CLIs; codify flag-parse + session-log conventions (Wave 1)
- **ENH-2941** — Similarity foundation: `ll-issues find-similar` + batch fingerprint compare (Wave 1)
- **FEAT-2940** — `ll-help`: generate the command catalog from frontmatter, retire hardcoded help.md (Wave 2)
- **FEAT-2942** — `ll-issues link-epics --mode assign|synthesize` (Wave 2)
- **ENH-2943** — `ll-loop rename` + `ll-loop cleanup` (Wave 2)
- **ENH-2944** — `ll-issues normalize` + `prioritize --apply` (Wave 2)
- **ENH-2945** — `ll-issues size <id> --json` deterministic size scoring (Wave 2)
- **ENH-2946** — `ll-issues set-flags --from-notes` + extend `format-check` (Wave 2)
- **FEAT-2947** — `ll-issues create` + `scaffold-epic` (Wave 2)
- **FEAT-2948** — `ll-loop scaffold-eval` / `scaffold-verify` (Wave 3)
- **ENH-2949** — `ll-loop audit <run> --json` + VERDICT_JSON adoption (Wave 3)

## Dependency Graph

```
ENH-2939 (prose deletion, conventions)  — no deps, do first
ENH-2941 (similarity foundation)  ──hard──> FEAT-2942 (link-epics)
ENH-2941                          ──soft──> ENH-2944 (normalize dup-flagging)
ENH-2946 (set-flags)              ──soft──> ENH-2949 (VERDICT adoption)
FEAT-2940, ENH-2943, FEAT-2947    — independent
```

Waves: **1** = ENH-2939, ENH-2941. **2** = FEAT-2940, FEAT-2942, ENH-2943, ENH-2944, ENH-2945, ENH-2946, FEAT-2947. **3** = FEAT-2948, ENH-2949.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/` — most new subcommands (find-similar, link-epics, normalize, prioritize, size, set-flags, create, scaffold-epic)
- `scripts/little_loops/cli/loop/` — rename, cleanup, scaffold-eval, scaffold-verify, audit
- `scripts/little_loops/text_utils.py` — canonical similarity implementation
- `scripts/pyproject.toml` + `skills/configure/areas.md` + `scripts/little_loops/init/writers.py` — FEAT-2940 only
- ~17 skill/command markdown files slimmed across children

### Tests
- `scripts/tests/` — one test module per new subcommand family

### Documentation
- `.claude/CLAUDE.md` CLI tool list; `docs/reference/API.md` for new subcommands

## Goal

Every `/ll:` skill/command spends LLM turns only on judgment; all deterministic work (scoring, clustering, renames, templating, counting, gates) runs as tested Python via `ll-issues`/`ll-loop` subcommands, with `map-dependencies`→`ll-deps` as the reference shape.

## Scope

In scope: the 11 children listed above — CLI subcommand additions/extensions in `scripts/little_loops/cli/{issues,loop,help}.py` and the corresponding markdown slimming across ~17 skill/command files. Out of scope: rewriting skills whose bulk is genuine reasoning (refine-issue, go-no-go, manage-issue core), the FSM engine itself, and any hosted CI.

## Impact

- **Priority**: P2 - Systemic drift + non-determinism affecting automation reliability, but no user-facing breakage today
- **Effort**: Large - 11 children across two CLI families; each child is Small–Medium
- **Risk**: Low-Medium - Conversions are behavior-preserving with fixture tests; markdown slimming is reversible

## Status

**Open** | Created: 2026-07-31 | Priority: P2

## Success Criteria

- [ ] No skill/command markdown contains a prose reimplementation of an algorithm that exists in `scripts/little_loops/`
- [ ] All `--check` gates used by FSM loops are Python exit codes
- [ ] Each converted file shrinks materially (tracked per-child); `ll-verify-skills` stays green
- [ ] `python -m pytest scripts/tests/` covers every new subcommand
