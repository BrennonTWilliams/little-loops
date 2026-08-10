---
id: EPIC-2938
title: Offload mechanical work from /ll: skills/commands into ll-* Python CLIs
type: EPIC
priority: P2
status: open
discovered_by: skill-audit
discovered_date: 2026-07-31
relates_to: [FEAT-3048]
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
2. **Non-determinism**: `--check` exit codes are *narrated* by the model in **24** skill/command files (measured 2026-07-31), so FSM `evaluate: type: exit_code` gates depend on the model remembering to exit correctly. This epic's children convert ~6 of them (ENH-2944, ENH-2953, ENH-2946, ENH-2949); the remainder is explicitly out of scope and needs a follow-up sweep — see Success Criteria.
3. **Context waste**: every invocation pays hundreds of lines of mechanical instruction that a subprocess would execute in milliseconds with zero tokens.

`skills/map-dependencies` is the proven target architecture: a thin wrapper over `ll-deps` where all scoring/detection happens in Python and the LLM only accepts or rejects proposals.

## Shared Conventions (apply to every child)

- Every new subcommand gets `--json` output.
- `--check` / `--dry-run` modes are deterministic Python exit codes, never LLM-narrated.
- Runtime config reads use `ll-config get <key>`, never `{{config.*}}` (which only expands under `ll-auto`'s `skill_expander.py`).
- Prefer extending existing CLIs (`ll-issues`, `ll-loop`) over new entry points. Only FEAT-2940 (`ll-help`) and ENH-2951 (`ll-verify-skill-prose`) add entry points; each pays the BUG-2764 triple registration: `scripts/pyproject.toml` + `skills/configure/areas.md` preset + `little_loops/init/writers.py::_LL_PERMISSIONS`.
- **Never add a new `_find_plugin_root`.** Eight copies already exist; delegate to `skill_expander._find_plugin_root` (the pattern `cli/action.py:174` and `cli/verify_cli_allowlist.py:34` follow).
- **Degrade gracefully on pip-only installs.** The wheel ships `little_loops/**` only, so a project with `install_source: pypi` and no plugin has no `skills/`/`commands/` on disk. Anything reading those dirs exits with a clear message, not a traceback.
- Each conversion includes the markdown slimming itself plus pytest coverage in `scripts/tests/` (the only CI).
- Skills that render judgments should emit the `VERDICT_JSON:` / `REVIEW_JSON:` tagged line that `cli/action.py` already parses (adopted in ENH-2949).

## Children

- **ENH-2939** — Delete session-log JSONL-hunting prose in favor of `ll-issues append-log` (Wave 1)
- **ENH-2941** — Similarity foundation: `ll-issues find-similar` + batch fingerprint compare (Wave 1)
- **ENH-2950** — `ll-issues locate-options --json` so decide-issue stops re-implementing Patterns 1–5 (Wave 1)
- **ENH-2951** — `ll-verify-skill-prose`: the lint gate that makes Success Criterion 1 enforceable (Wave 1)
- **FEAT-2940** — `ll-help`: generate the command catalog from frontmatter, retire hardcoded help.md (Wave 2)
- **FEAT-2942** — `ll-issues link-epics --mode assign|synthesize` (Wave 2)
- **ENH-2979** — `--deep` flag: LLM-adjudicated clustering for `--mode synthesize`,
  gated behind Jaccard pre-filtering (Wave 2, after FEAT-2942; parented 2026-08-03 —
  see its Note re: tension with this epic's determinism motivation)
- **ENH-2943** — `ll-loop rename` + `ll-loop cleanup` (Wave 2)
- **ENH-2944** — `ll-issues normalize` (Wave 2)
- **ENH-2953** — `ll-issues prioritize --apply` (Wave 2)
- **ENH-2945** — `ll-issues size <id> --json` deterministic size scoring (Wave 2, after FEAT-2947)
- **ENH-2946** — `ll-issues set-flags --from-notes` + extend `format-check` (Wave 2)
- **FEAT-2947** — `ll-issues create` + `scaffold-epic` (Wave 2, early)
- **FEAT-2948** — `ll-loop scaffold-eval` / `scaffold-verify` (Wave 3)
- **ENH-2949** — `ll-loop audit <run> --json` + VERDICT_JSON adoption (Wave 3)
- **FEAT-3048** — Verify symbol and CLI-flag claims in issue bodies; extends the
  FEAT-2846/2849/2850 prose-claim gap taxonomy to the claim classes that survive
  refine/wire/confidence review (Wave 3; captured 2026-08-04 from a FEAT-2942 review)
- **ENH-2952** — Flag-parse boilerplate consolidation — *measure before applying* — **resolved
  Option C (leave as-is, documented)**: measured ~150 tokens/site, paid per-invocation not
  cumulatively; Options A/B yielded ~0 or marginal net savings against their own build cost.
  No CLI or markdown changes; dropped from the epic's remaining work (Wave 3)

## Dependency Graph

```
ENH-2951 (prose lint gate)        — no deps, do first; makes the rest enforceable
ENH-2939 (session-log sweep)      — no deps
ENH-2950 (locate-options)         — no deps; unblocks decide-issue prose deletion
ENH-2941 (similarity foundation)  ──hard──> FEAT-2942 (link-epics)
ENH-2941                          ──soft──> ENH-2944 (normalize dup-flagging)
FEAT-2947 (create)                ──soft──> ENH-2945 (size Phase 6), FEAT-2942 (synthesize)
ENH-2944 (rename helper)          ──soft──> ENH-2953 (prioritize)
ENH-2946 (set-flags)              ──soft──> ENH-2949 (VERDICT adoption)
FEAT-2940, ENH-2943               — independent
ENH-2952                          — gated on its own measurement, not on siblings
```

Waves: **1** = ENH-2951, ENH-2939, ENH-2950, ENH-2941. **2** = FEAT-2947 (first), FEAT-2940, FEAT-2942, ENH-2943, ENH-2944, ENH-2953, ENH-2945, ENH-2946. **3** = FEAT-2948, ENH-2949, ENH-2952.

## Review Notes (2026-07-31)

A post-scoping review made four structural corrections:

1. **ENH-2939 was over-scoped.** Its decide-issue item could not be done markdown-only —
   `check-decidable` is exit-code only and Phase 3b *materializes* option blocks into the
   file — so it became **ENH-2950**. Its 17-site flag-parse item became **ENH-2952**
   because consolidation is not a guaranteed context win and needs measuring first.
2. **The epic had no enforcement mechanism.** Success Criterion 1 was unverifiable, and it
   regressed within three commits of scoping: `5e29c4d4` (ENH-2936) added Pattern E option
   prose to `decide-issue/SKILL.md` *and* duplicated it into `issue_parser.py:449`.
   **ENH-2951** adds the gate.
3. **ENH-2944 was two issues.** `prioritize` (233 lines, thin) split to **ENH-2953** rather
   than waiting on `normalize` (511 lines).
4. **Two undeclared soft deps on FEAT-2947** (ENH-2945's Phase 6, FEAT-2942's synthesize
   mode) were declared, so neither child re-implements ID allocation.

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

In scope: the 15 children listed above — CLI subcommand additions/extensions in `scripts/little_loops/cli/{issues,loop,help}.py`, the `ll-verify-skill-prose` gate, and the corresponding markdown slimming across ~18 skill/command files. Out of scope: rewriting skills whose bulk is genuine reasoning (refine-issue, go-no-go, manage-issue core), the FSM engine itself, any hosted CI, and the ~18 narrated-`--check` files no child touches. **ENH-2952 is also out of scope for further work**: its own measurement resolved it as Option C (leave the 17-site flag-parse duplication as documented prose, no CLI/markdown change) — recorded in `.ll/decisions.d/` and above under Children.

## Impact

- **Priority**: P2 - Systemic drift + non-determinism affecting automation reliability, but no user-facing breakage today
- **Effort**: Large - 11 children across two CLI families; each child is Small–Medium
- **Risk**: Low-Medium - Conversions are behavior-preserving with fixture tests; markdown slimming is reversible

## Status

**Open** | Created: 2026-07-31 | Priority: P2

## Success Criteria

- [ ] No skill/command markdown contains a prose reimplementation of an algorithm that exists in `scripts/little_loops/` — **enforced by `ll-verify-skill-prose` (ENH-2951), not by inspection**
- [ ] Every `--check` gate in a file this epic touches is a Python exit code; the remaining narrated-exit files (24 at scoping, ~18 untouched) are enumerated in a follow-up issue rather than left implicit
- [ ] Each converted file shrinks materially — every child records its before/after line count in its commit; `ll-verify-skills` stays green
- [ ] `python -m pytest scripts/tests/` covers every new subcommand
- [ ] No new `_find_plugin_root` copy and no second frontmatter-enumeration path was introduced (the epic must not create the drift it deletes)

## Related Key Documentation

- `.claude/CLAUDE.md` — the `ll-issues`/`ll-loop` CLI catalog this epic extends with new subcommands, and the "Prefer Skills over Agents" development preference the conversions embody.
- `CONTRIBUTING.md` — governs the markdown slimming of skills/commands and the 500-line skill-file limit the children must stay under while shrinking prose.
- `docs/reference/API.md` — module reference for `cli/issues/*`, `cli/loop/*`, and `text_utils` that each child extends or consolidates into.

## Verification Notes

- 2026-08-10: Verified 2026-08-10: most children done; ENH-2979 and ENH-2943 remain open. ENH-2952 is narrated in-body as resolved/dropped from epic scope (Option C) but its frontmatter still shows status: open — reconcile that issue's own status separately; does not block this epic's overall progress tracking.


## Session Log
- `/ll:audit-issue-conflicts` - 2026-08-10T18:52:51 - `ffa08fd4-dce7-4108-91f7-6bb57e5df4c8.jsonl`
- `/ll:verify-issues` - 2026-08-10T16:25:07 - `50b69f30-8ca9-4ab9-8b06-6ee21c203b10.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This epic's new subcommands (ENH-2943, FEAT-2948, ENH-2949) land in `scripts/little_loops/cli/loop/`, the same directory EPIC-2789's ENH-2776 restructures ("Dissolve `cli/loop/_helpers.py` grab-bag into named modules"). Sequence ENH-2776 before this epic's `cli/loop/*` additions, or rebase whichever lands second onto the other's resulting module layout.

**Note** (added by `/ll:audit-issue-conflicts`): This epic's `.claude/CLAUDE.md` CLI-catalog edits (new `ll-issues`/`ll-loop` subcommands) target the same CLI Tools section EPIC-1867 also edits (its ENH-1903/FEAT-2002 children). Whichever epic's edits land second should rebase against the other's changes rather than editing independently.

**Note** (added by `/ll:audit-issue-conflicts`): This epic's FEAT-2948 ("ll-loop scaffold-eval / scaffold-verify") and EPIC-2856's FEAT-2878 ("Trace-level assertions in the eval harness, with optional multi-host divergence runs") both modify eval-harness templates/scaffolding. Whichever lands second should confirm its changes are additive to the other's.
