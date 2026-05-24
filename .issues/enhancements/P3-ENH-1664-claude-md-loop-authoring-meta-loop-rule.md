---
id: ENH-1664
type: ENH
status: open
priority: P3
discovered_date: 2026-05-23
discovered_by: manual
labels: [docs, claude-md, loops, meta-loop, harness, shor]
parent: EPIC-1663
relates_to: [ENH-1665, ENH-1666]
---

# ENH-1664: CLAUDE.md "Loop Authoring" section — meta-loop design rule

## Summary

Add a "Loop Authoring" section to `.claude/CLAUDE.md` that declares two
project-wide rules for loops that modify other harness artifacts. This is the
declarative layer of EPIC-1663; ENH-1665 (validator) and ENH-1666 (wizard) are
the enforcement layers.

## Motivation

The wizard, validator, and loop-specialist agent each enforce parts of the
SHOR design rules, but a human or assistant authoring a loop YAML by hand
needs a single high-level rule to read before writing. CLAUDE.md is loaded
into every session, so it's the right place for a one-paragraph
constraint that says "if your loop writes another loop, follow these rules"
and links to the enforcing tooling.

## Proposed Content

Add a new section to `.claude/CLAUDE.md` after the "Development Preferences"
section:

```markdown
## Loop Authoring

Loops that modify other harness artifacts (loop YAMLs, skill files, agent
definitions, commands, or `.claude/CLAUDE.md` itself) are **meta-loops** and
follow stricter design rules than data-operating loops:

1. **Diagnosis-first scaffolding.** Meta-loops should follow a
   `diagnose → propose → apply → measure-externally` shape, not the generic
   harness 5-phase pipeline. The `create-loop` wizard's "Optimize a harness"
   branch generates this template; do not adapt the standard "Harness a skill"
   template for meta-loops.
2. **Non-LLM evaluator required.** Every `check_semantic` (`llm_structured`)
   state in a meta-loop MUST be paired with at least one non-LLM evaluator
   in the routing chain: `exit_code`, `output_numeric`, `convergence`,
   `diff_stall`, or `mcp_result`. LLM self-grades on harness updates are
   ~33–55% accurate (SHOR Table 1; Sonnet 4.6 = 33.4%) — pair with
   measurable external evidence or the loop will optimize for what the
   judge prompt rewards, not what users observe.

`ll-loop validate` enforces rule 2 as ERROR severity (rule MR-1). Use
`meta_self_eval_ok: true` at the loop top-level to suppress the check in
the rare case where you have a justified reason. See ENH-1665.

The `loop-specialist` agent diagnoses violations post-hoc as
`self-evaluation bias` / `feature-stubbing` failure modes
(`agents/loop-specialist.md`); this section shifts the gate left.
```

## Implementation Steps

1. Add the section above to `.claude/CLAUDE.md`, placed after "Development
   Preferences" and before "Issue File Format".
2. Cross-link from `docs/guides/LOOPS_GUIDE.md` (one-line "see CLAUDE.md
   Loop Authoring" reference in the harness section).
3. Verify the section is included in `ll-doctor` config inventory (no code
   change expected; this is a sanity check that the new section is picked
   up by any tooling that scans CLAUDE.md).

## Scope Boundaries

**In scope:**
- One new section in `.claude/CLAUDE.md`
- One cross-link in `docs/guides/LOOPS_GUIDE.md`

**Out of scope:**
- The validator rule itself (ENH-1665)
- The wizard branch itself (ENH-1666)
- Changes to `loop-specialist` agent (taxonomy already covers this)

## Impact

- **Priority**: P3 — declarative; the load-bearing enforcement is in
  ENH-1665. This is the discoverability layer.
- **Effort**: Low — ~20 lines of markdown plus one cross-link.
- **Risk**: None — additive prose.
- **Breaking Change**: No

## Dependencies

- Should land **after** or **concurrent with** ENH-1665 so the CLAUDE.md
  reference to MR-1 isn't dangling.

## Labels

- docs
- claude-md
- loops
- meta-loop
- harness
- shor
