---
id: BUG-3354
type: BUG
title: Heredoc terminator collision in LL_RAW capture conversions
priority: P3
status: open
discovered_by: manual-review
discovered_date: '2026-08-28'
captured_at: '2026-08-28T00:00:00Z'
parent: EPIC-3336
relates_to: [BUG-3341, ENH-3347]
---

# BUG-3354: Heredoc terminator collision in LL_RAW capture conversions

## Summary

The BUG-3341 conversions render `${captured.*.output}` inside
`cat > ... << 'LL_RAW_9F3C1A7E_EOF'` heredocs. The terminator
`LL_RAW_9F3C1A7E_EOF` is a **fixed, public string** (checked into this repo's
loop YAMLs). A captured output containing that exact line terminates the
heredoc early, and everything after it in the captured payload executes as
shell — the same class of injection BUG-3341 fixed, surviving through the fix's
own delimiter.

Found during ENH-3347 review (2026-08-28). ENH-3347's case 2 covers `"""` +
newline payloads only; its scope boundary ("representative, not exhaustive")
explicitly does not cover terminator collision, and no other issue tracks it.

## Current Behavior

Every converted class-B site uses the same literal terminator, e.g.
`scripts/little_loops/loops/loop-router.yaml:208-210`:

```bash
cat > "${context.run_dir}/parse_project_score-project_score.txt" << 'LL_RAW_9F3C1A7E_EOF'
${captured.project_score.output}
LL_RAW_9F3C1A7E_EOF
```

Captured output is LLM-produced text. An output containing a line that is
exactly `LL_RAW_9F3C1A7E_EOF` (plausible adversarially, since the marker is
public; conceivable accidentally if a loop ever captures output that quotes a
loop YAML — e.g. a loop-authoring or loop-auditing state) closes the heredoc at
that line, and the remainder of the payload is parsed as shell commands.

## Expected Behavior

Captured-output rendering is injection-proof regardless of payload content —
no fixed delimiter whose presence in the payload changes parsing. Candidate
directions considered:

1. **Per-render unique terminator**: interpolation-time generated marker
   (e.g. UUID-suffixed) guaranteed absent from the payload — requires engine
   support since actions are static YAML text.
2. **Engine-level safe binding**: a first-class FSM mechanism that writes
   captured output to a file *before* shell rendering (sidestepping heredocs
   entirely), with the action referencing the file path.
3. **Detect-and-refuse**: interpolation fails loudly if the rendered payload
   contains the terminator line — turns silent injection into a hard error.

**Decided 2026-08-28 (unparented-issues review): this issue's scope is
option 3** — interpolation fails loudly (hard error, run halts at that state)
when a rendered payload contains a line equal to the heredoc terminator of the
site being rendered. That turns silent arbitrary shell execution into a
deterministic, attributable failure at Small effort with no touch to the ~145
converted sites. Options 1/2 remain the candidate structural fix; file a
follow-up (child of EPIC-3336) only if the hard-error path fires in practice.

## Motivation

The BUG-3341 fix converted ~145 sites to this pattern; all share one public
delimiter. The failure mode is silent arbitrary shell execution inside
automation runs. Likelihood is low (requires the exact marker line in captured
output) but the marker's public visibility makes it a standing adversarial
target, and loops that read/quote loop YAMLs raise the accidental odds above
zero.

## Scope Boundaries

**In scope:** the delimiter-collision failure mode of the `LL_RAW_*_EOF`
heredoc pattern across converted sites; a behavioral test demonstrating the
break; the option-3 detect-and-refuse guard (decided above).

**Out of scope:** options 1/2 (per-render unique terminator; engine-level safe
binding) — the structural fix, deferred to a follow-up if ever needed;
re-litigating the BUG-3341 conversion pattern itself; ENH-3347's four
behavioral cases; non-captured interpolation classes (BUG-3339/3340
territory).

## Impact

- **Priority**: P3 — real injection class, low trigger likelihood, no known
  in-the-wild occurrence.
- **Effort**: Small — option 3 only (interpolation-layer guard plus tests);
  the Medium engine rework belongs to the deferred 1/2 follow-up.
- **Risk**: Low — detect-and-refuse adds a hard error on a payload shape that
  today executes as shell; no rendering change at the converted sites.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-08-28 | Priority: P3
