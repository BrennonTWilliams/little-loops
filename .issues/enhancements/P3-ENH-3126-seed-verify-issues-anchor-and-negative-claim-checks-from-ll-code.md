---
id: ENH-3126
title: Use ll-code graph queries in verify-issues for anchor drift and negative-claim checks
type: ENH
priority: P3
status: open
captured_at: "2026-08-09T05:08:55Z"
discovered_date: 2026-08-09
discovered_by: capture-issue
program_design_not_applicable: true
testable: true
---

# Use ll-code graph queries in verify-issues for anchor drift and negative-claim checks

## Summary

`/ll:verify-issues` (`commands/verify-issues.md`) verifies issue claims entirely with
`Read`/`Glob`/`Grep`; its `allowed-tools` block restricts Bash to `Bash(git:*)`, so the
`ll-code` structural-query surface is unavailable to it. Two of its checks are a poor fit
for grep and a good fit for the code graph:

1. **Line-number/anchor drift** (Process step 2B.2, "Verify line numbers") — currently N
   greps per issue to relocate each `path:line` anchor. `ll-code defines <file>` returns
   every symbol in a file with its current line in one call.
2. **Negative claims** — issue text asserting "X is never called", "no caller handles
   this", "this path is dead". Grep is unreliable here (aliased imports, re-exports,
   dynamic dispatch), and a wrong answer pushes the verdict toward `RESOLVED`/`INVALID`.

Add a narrowly-scoped graph layer for exactly these two uses, under a stricter contract
than the existing consumers get, because verify-issues' output mutates state.

## Current Behavior

- `commands/verify-issues.md:4-9` — `allowed-tools: Read, Glob, Grep, Edit, Bash(git:*)`.
  No `Bash(ll-code:*)`; no Task/Agent tool, so there are no sub-agents (unlike
  `refine-issue`, which seeds an agent wave).
- `ll-code` is wired into `commands/refine-issue.md:11,212` (Step 3.05) and
  `skills/wire-issue/SKILL.md:15,142` + `skills/wire-issue/graph-discovery-layer.md`,
  both governed by `docs/guides/GRAPH_DISCOVERY_GUIDE.md`.
- In those two consumers the graph is a **discovery accelerator**: wrong seeds cost one
  wasted Grep. verify-issues has no such slack — it writes `## Verification Notes`,
  rewrites line numbers, can set `status: done`, and persists
  `verify_verdict: VALID|NON_VALID` to frontmatter, which gates FSM loops such as
  `refine-to-ready-issue.yaml`'s `verify_issue` → `check_verify_verdict` pair.

## Expected Behavior

`/ll:verify-issues` may query `ll-code` for two purposes only — anchor relocation and
corroboration of negative reference claims — with graph output treated as **evidence that
may confirm or correct a verdict, never as evidence that originates one**.

- Anchor drift: on a `path:line` mismatch, one `ll-code defines <file>` locates the named
  symbol's current line; the verdict becomes `OUTDATED` with the corrected line written
  back, instead of an unresolved "not found at line N".
- Negative claims: `ll-code callers-of` / `ll-code references` corroborates or refutes
  "never called"/"dead" assertions. A graph result showing callers **refutes** the claim
  (evidence of presence, safe). A graph result showing *no* callers is never sufficient on
  its own to mark an issue `RESOLVED` or `INVALID` — the existing exploratory Grep pass
  still runs and decides.
- Provider absent, `status.available: false`, or a query exiting `2` → silent fallback to
  today's flow, zero behavior change.
- `freshness: stale` → all graph results demoted to leads; every positive hit still
  confirmed by one targeted Grep at its `path:line` before it informs a verdict.

## Motivation

Two distinct wins, one correctness and one cost:

- **Correctness**: negative reference claims are the class of claim verify-issues most
  plausibly gets wrong today, and wrong in the destructive direction — a false "no callers"
  reads as `RESOLVED`, which in `--auto` mode adds a resolution note and in `--check` mode
  writes `verify_verdict`, gating a loop.
- **Cost**: the no-argument invocation walks the entire active backlog (`ll-issues list`
  filtered to `open|in_progress|blocked`). Anchor relocation is the per-issue hot path, and
  one `defines` call per file replaces a grep per anchor. The saving scales with backlog
  size, which is exactly where this command is slowest.

## Proposed Solution

Follow the established consumer pattern (`refine-issue` Step 3.05 / `wire-issue`
`graph-discovery-layer.md`), delegating the contract to
`docs/guides/GRAPH_DISCOVERY_GUIDE.md` rather than restating it, but add one rule that
does not exist for the other consumers.

1. Add `Bash(ll-code:*)` to `commands/verify-issues.md` `allowed-tools`.
2. Insert a step (proposed §2B.0, "Graph-assisted checks") before the manual verification
   sweep, active only when the issue names concrete symbols/files and
   `ll-code --json status` reports `available: true`.
3. Restrict the query surface to `defines`, `callers-of`, `references`. Explicitly exclude
   `impact-of` (see Scope Boundaries).
4. State the verdict-origination prohibition as a hard rule in the command body:

   > A graph result may corroborate or correct a verdict. It may never originate one. In
   > particular, `callers-of` exiting `1` ("no callers") must never by itself produce
   > `RESOLVED` or `INVALID`; run the exploratory Grep pass and decide from that.

5. Record provider + freshness in the verification output so a reader can distinguish an
   index-accelerated run from a grep-fallback one — the two are not equally trustworthy.
   Do **not** write it into the Session Log line: that format is parsed by
   `issue_design_timestamp()` (`scripts/little_loops/issues/program_design.py:406-427`) and
   extra text breaks the Program Design gate's arming.

### Current Pain Point

Anchor drift resolution is O(anchors) greps per issue across a whole-backlog run, and
"never called" claims are verified with the one tool that is structurally bad at proving
absence — while the command has authority to close issues and gate loops on the answer.

### API/Interface

No Python API change. Command-surface change only:

```yaml
# commands/verify-issues.md frontmatter
allowed-tools:
  - Read
  - Glob
  - Grep
  - Edit
  - Bash(git:*)
  - Bash(ll-code:*)   # new
```

```bash
# permitted query surface (verify-issues only)
ll-code --json status
ll-code --json defines <file>            # anchor relocation
ll-code --json callers-of <symbol>       # negative-claim corroboration
ll-code --json references <symbol>       # negative-claim corroboration
# NOT permitted: callees-of, importers-of, impact-of
```

### Backwards Compatibility

Fully backward compatible. With no provider available the command behaves exactly as it
does today (silent fallback). Verdict semantics are unchanged; the prohibition rule means
no verdict reachable today becomes unreachable, and no new verdict can be reached solely
from graph output.

## Integration Map

### Files to Modify
- `commands/verify-issues.md` — `allowed-tools` + new §2B.0 + prohibition rule + output line

### Dependent Files (Callers/Importers)
- `skills/ll-verify-issues/SKILL.md` — Codex-discovery bridge; check whether its
  `allowed-tools` mirror needs the same `Bash(ll-code:*)` entry
- FSM loops invoking `/ll:verify-issues --check`, notably
  `refine-to-ready-issue.yaml` (`verify_issue` → `check_verify_verdict`) — behavior must
  be unchanged; verify no new failure mode on the `verify_verdict` gate

### Similar Patterns
- `commands/refine-issue.md:205-245` (Step 3.05) — the canonical consumer shape
- `skills/wire-issue/graph-discovery-layer.md` — contract + three safety rules
- `docs/guides/GRAPH_DISCOVERY_GUIDE.md` — binding rules to reference, not restate

### Tests
- `scripts/tests/` — CLI-allowlist / command-frontmatter validation covering
  `Bash(ll-code:*)` (confirm which suite owns allowed-tools assertions)
- `ll-verify-cli-allowlist` — ensure the new tool grant is registered

### Documentation
- `docs/guides/GRAPH_DISCOVERY_GUIDE.md` — add verify-issues as a consumer and document
  the stricter verdict-origination rule, which does not apply to the other two
- `docs/reference/CLI.md` — only if the consumer list is enumerated there

### Configuration
- N/A — gated by `ll-code --json status`, no new config key

## Implementation Steps

1. Add `Bash(ll-code:*)` to `commands/verify-issues.md` allowed-tools and mirror in
   `skills/ll-verify-issues/SKILL.md` if it carries its own list.
2. Write §2B.0 (graph-assisted checks) referencing `GRAPH_DISCOVERY_GUIDE.md` for the
   contract, plus the verify-issues-specific verdict-origination prohibition; wire the
   `defines` result into the 2B.2 line-number check and the reference queries into the
   negative-claim path.
3. Add provider/freshness to the verification report (not the Session Log line).
4. Extend `GRAPH_DISCOVERY_GUIDE.md` with the verify-issues consumer entry and its stricter
   rule.
5. Verification: run `/ll:verify-issues <ID>` on an issue with a deliberately stale
   `path:line` anchor and confirm the corrected line is written; run one with a "never
   called" claim against a symbol that *does* have callers and confirm the claim is
   refuted; run both again with the provider forced unavailable and confirm output is
   identical to today's; run `python -m pytest scripts/tests/`.

## Scope Boundaries

**In scope**: `defines` for anchor drift; `callers-of`/`references` for negative-claim
corroboration; `allowed-tools` change; the verdict-origination prohibition; provider and
freshness reporting.

**Out of scope**:

- `impact-of` in regression detection (Process step 2D). The git-history path (fix commit
  → files changed since) is already deterministic evidence; a transitive-closure guess on
  top only widens the blast radius of a wrong `REGRESSION` verdict.
- Any agent-seeding structure. verify-issues spawns no sub-agents, so the per-axis seeding
  table in `graph-discovery-layer.md` does not transfer.
- Changing `ll-code` itself, or any provider/index work.
- The dependency-reference (2E) and decisions-rule checks — unrelated corpora.

## Impact

- **Priority**: P3 - Correctness improvement on a real but bounded failure class; no active
  incident forcing it.
- **Effort**: Small - Command-markdown change plus a guide update; no Python.
- **Risk**: Low - Silent fallback preserves today's behavior exactly, and the
  verdict-origination prohibition keeps graph data out of the destructive path. The residual
  risk is prose drift: the rule is enforced by wording, not by code.
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log
- `/ll:refine-issue` - 2026-08-09T20:34:00 - `20730683-2565-4a26-b2cc-54e8c3853f7b.jsonl`
- `/ll:format-issue` - 2026-08-09T20:26:10 - `094e7212-923b-4b82-873b-48d193f4afe0.jsonl`
- `/ll:capture-issue` - 2026-08-09T05:10:04 - `b7457e6e-9654-45e5-a9bd-43e1bcddbd28.jsonl`

---

## Status

- [ ] Not started
