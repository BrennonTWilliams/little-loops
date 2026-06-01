---
id: FEAT-1742
title: Surface proof-first gate via discoverability hook in mainstream impl loops
type: FEAT
priority: P3
status: open
captured_at: '2026-05-27T18:18:58Z'
discovered_date: '2026-05-27'
discovered_by: capture-issue
parent: EPIC-1694
depends_on: [FEAT-1743]
relates_to:
- EPIC-1694
- FEAT-1738
- FEAT-1696
- FEAT-1695
---

# FEAT-1742: Surface proof-first gate via discoverability hook in mainstream impl loops

## Summary

Add a discoverability surface that nudges users toward `proof-first-task` / `assumption-firewall` when a mainstream implementation loop (`general-task`, `autodev`, `scan-and-implement`) is about to touch unfamiliar external-API code. Without this surface, the EPIC-1694 gate primitives stay invisible to the developers who would benefit most — adoption depends entirely on the user already knowing to type a different loop name.

Two viable shapes (one to be chosen during refinement):

1. **`PreToolUse` hook** that intercepts `Write`/`Edit` against files referencing unfamiliar third-party imports (no matching proven LT record) and emits a one-line suggestion: *"No learning-test proof exists for `<package>` — consider re-running this task via `proof-first-task` first."*
2. **`/ll:confidence-check` integration** that, before any implementation-loop kickoff, runs `ll-learning-tests check` against any external APIs referenced in the linked issue file and recommends `assumption-firewall` / `proof-first-task` when proofs are missing or refuted.

## Current Behavior

EPIC-1694 ships four loops (`ready-to-implement-gate`, `assumption-firewall`, `integrate-sdk`, `adopt-third-party-api`) plus the planned `proof-first-task` wrapper (FEAT-1738). All of these are **opt-in by loop choice** — the user must already know:

- That the Learning Test Registry exists.
- That a gate primitive can prove API assumptions before code is written.
- That `proof-first-task` is the entry point bundling proof + implementation.
- That they should type `proof-first-task` instead of the more familiar `general-task` / `autodev` / `scan-and-implement`.

The mainstream impl loops have **zero awareness** of the registry. A developer who runs `general-task` against an issue mentioning Stripe webhooks gets no signal that a proof step is available. The epic explicitly defers "Wiring `ready-to-implement-gate` *into* existing implementation loops" as out of scope, leaving the discoverability gap unaddressed.

## Expected Behavior

### Shape A — `PreToolUse` hook

```bash
# User runs general-task against a task touching unfamiliar Stripe code
ll-loop run general-task --context task="Add webhook signature verification"

# When the impl loop attempts to Write/Edit a file with `import stripe`:
[ll: proof-first hint]
No learning-test record found for "stripe". You're about to write
integration code based on training-data assumptions. Consider:

  ll-loop run proof-first-task \
    --context task="Add webhook signature verification" \
    --context issue_file=".issues/features/P2-FEAT-1234-stripe-webhooks.md"

Continue anyway? [y/N]
```

The hook **does not block** by default — it surfaces a soft nudge. A config knob (`learning_tests.gate_mode: warn | block | off`) lets teams escalate.

### Shape B — `/ll:confidence-check` integration

`/ll:confidence-check` (existing skill) gains a "registry probe" step: it inspects the issue file for external-API references, runs `ll-learning-tests check <target>` for each, and adds to its verdict:

```
Confidence: medium
- Implementation plan is concrete: yes
- Tests defined: yes
- External API proofs:
  - "stripe webhook signature": ❌ no record — recommend `assumption-firewall` first
  - "anthropic streaming":       ✅ proven (2026-04-10)

Recommended next step: ll-loop run proof-first-task --context issue_file=...
```

## Motivation

- **Closes the adoption gap left by EPIC-1694.** The gate primitives are well-designed but invisible — without a surface, they remain niche infrastructure rather than a default behavior.
- **Soft nudges beat opt-in flags.** A one-line hint at the moment of relevant action is far more effective than a doc paragraph the user must remember.
- **Composable with `proof-first-task`.** This issue does not modify the core impl loops (consistent with the epic's "don't pollute core loops" principle) — it adds an orthogonal surface that points users at the opt-in wrapper.
- **Measurable adoption signal.** A hook records when it fires and whether the user accepted the suggestion, giving a feedback signal on registry uptake.

## Use Case

A developer with no prior LT-registry experience runs:

```bash
ll-loop run general-task --context task="Add Stripe webhook signature verification"
```

The impl loop starts editing `webhooks/stripe.py`. The PreToolUse hook fires on the first `Write` attempt, detects `import stripe`, finds no proven record matching `stripe`, and emits the suggestion. The developer chooses to re-run as `proof-first-task`, the gate proves three assumptions, and the implementation proceeds with verified API shapes — preventing a class of bugs that would otherwise survive into review.

## Proposed Solution

### Shape decision

Refinement should pick A or B based on:

- **A (PreToolUse hook)** — higher reach (fires on any tool call regardless of loop), but requires file-content parsing and a package-detection heuristic; risk of noisy false positives.
- **B (`/ll:confidence-check` integration)** — lower reach (only fires when user invokes confidence-check), but cleaner scope and reuses an existing surface; predictable invocation point.

A reasonable compromise: ship B first as a low-risk surface, then ship A as a follow-up once the import-detection heuristic is proven against the existing Learning Test Registry index.

### Configuration surface

The canonical `learning_tests` configuration schema is defined by FEAT-1743 in `config-schema.json`. This issue references that schema and does not define its own. The discoverability hook checks `learning_tests.enabled` (master switch) and `learning_tests.discoverability.mode` (warn/block) as defined by FEAT-1743.

### Package detection heuristic

For Shape A: parse the file content being written/edited for top-level `import <pkg>` / `from <pkg> import` (Python) or `require('<pkg>')` / `import ... from '<pkg>'` (JS/TS), filter against `skip_packages`, and query `ll-learning-tests check <pkg>` for each. Cache per session to avoid repeated checks on the same package.

## Implementation Steps

1. Decide Shape A vs B (or both, B first) during `/ll:refine-issue`.
2. **If Shape B:** locate `/ll:confidence-check` (`skills/confidence-check/SKILL.md`); add a "registry probe" step that scans the linked issue file for external-API references, runs `ll-learning-tests check`, and conditionally appends a "recommended next step" line.
3. **If Shape A:** add a `PreToolUse` hook entry in `hooks/hooks.json` that triggers on `Write`/`Edit` with a prompt referencing a new handler in `scripts/little_loops/hooks/learning_tests_gate.py`. Handler parses imports, queries the registry, and emits the suggestion.
4. Add config schema entries under `learning_tests.discoverability` in `config-schema.json` with `mode`, `enabled`, `skip_packages`.
5. Add tests in `scripts/tests/test_learning_tests_discoverability.py` covering: (a) no-op when registry is empty / feature disabled, (b) suggestion fires when unfamiliar import seen, (c) no suggestion when proven record exists, (d) `skip_packages` is honored.
6. Update `docs/guides/LEARNING_TESTS_GUIDE.md` with a "Discoverability" section explaining the surface and how to tune it.
7. Update `.claude/CLAUDE.md` if Shape A is chosen (PreToolUse hook is a behavior change worth documenting).

## Acceptance Criteria

- A discoverability surface exists that, given an issue or file touching an external API with no proven LT record, recommends `proof-first-task` / `assumption-firewall`.
- The surface is configurable via `learning_tests.discoverability.mode` (off / warn / block).
- When the registry has a proven record for the relevant package/target, no suggestion fires (no nag for already-proven APIs).
- When the user has not enabled the registry at all (empty `.ll/learning-tests/`), the feature is a no-op and does not produce false-positive suggestions on every tool call.
- Tests in `scripts/tests/test_learning_tests_discoverability.py` cover the empty-registry, missing-record, proven-record, and skip-list cases.
- `LEARNING_TESTS_GUIDE.md` documents the surface and tuning knobs.

## Open Questions

- Should the hint mention `assumption-firewall` directly (issue-driven path) or `proof-first-task` (bundled wrapper)? Recommendation: `proof-first-task` because it degrades gracefully.
- For Shape A, should the heuristic also scan changed files in `git diff` (broader signal) rather than only the file being written in the current tool call?
- For Shape B, should the registry probe extract API references via LLM or via simple keyword/regex on the issue body? LLM is more accurate but adds latency to every confidence-check run.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feat`, `loop`, `learning-tests`, `discoverability`, `hook`, `confidence-check`, `adoption`, `captured`

---

**Open** | Created: 2026-05-27 | Priority: P3

## Session Log
- `/ll:audit-issue-conflicts` - 2026-06-01T02:53:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e05c48a-ca16-414b-a869-8184ba394f53.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:capture-issue` - 2026-05-27T18:18:58Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5d67c925-b04f-4086-8575-fc25fa08257e.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue's Shape A PreToolUse hook handler (`learning_tests_gate.py`) must remain **warn-only and non-blocking** — it emits a one-line suggestion and optionally prompts, but does not pause FSM execution. This is distinct from the blocking `action_type: human_approval` FSM state introduced by FEAT-1794, which fully pauses loop execution awaiting a yes/no/edit verdict. These two surfaces are complementary: FEAT-1742 nudges at the tool-call layer; FEAT-1794 gates at the FSM state layer. If Shape A is chosen, the PreToolUse handler must not replicate the blocking semantics of FEAT-1794. Once FEAT-1794 ships, proof-first-task loops could replace the Shape A hook with a `human_approval` state — that refactor is out of scope here.
