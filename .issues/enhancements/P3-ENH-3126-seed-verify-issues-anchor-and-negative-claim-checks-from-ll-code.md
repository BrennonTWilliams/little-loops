---
id: ENH-3126
title: Use ll-code graph queries in verify-issues for anchor drift and negative-claim
  checks
type: ENH
priority: P3
status: open
captured_at: '2026-08-09T05:08:55Z'
discovered_date: 2026-08-09
discovered_by: capture-issue
program_design_not_applicable: true
testable: true
confidence_score: 100
outcome_confidence: 73
score_complexity: 18
score_test_coverage: 22
score_ambiguity: 15
score_change_surface: 18
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
- `commands/verify-issues.md` — `allowed-tools` (lines 4-9, add `Bash(ll-code:*)`) + new
  §2B.0 + prohibition rule + output line
- `skills/ll-verify-issues/SKILL.md` — currently a **bare bridge stub** with no
  `allowed-tools` field at all (unlike `skills/ll-refine-issue/SKILL.md`, which mirrors
  its command's full `allowed-tools` block verbatim, `skills/ll-refine-issue/SKILL.md:5-12`
  incl. `Bash(ll-code:*)`). Decide: add a matching `allowed-tools` block here to keep the
  bridge pattern consistent, or confirm the bridge intentionally carries none (it currently
  just says "Bridged from `commands/verify-issues.md`... see the source command file").

_Wiring pass added by `/ll:wire-issue`:_
- `.gemini/commands/verify-issues.toml` — generated host-adapter mirror (`ll-adapt --host
  gemini --apply`) duplicating `commands/verify-issues.md`'s frontmatter/body verbatim; no
  test enforces command-level mirror parity (only 3 *skills* are covered by
  `SKILL_MIRRORS_MUST_MATCH_SOURCE` in `test_wiring_skills_and_commands.py:368`, and
  `verify-issues` is not among them) — regenerate manually after editing the source, or it
  silently drifts
- `.kimi-code/skills/ll-verify-issues/SKILL.md` — generated host-adapter mirror
  (`ll-adapt --host kimi-code --apply`) of `skills/ll-verify-issues/SKILL.md`; same
  no-test-enforced-parity gap as the Gemini mirror above

### Dependent Files (Callers/Importers)
- `skills/ll-verify-issues/SKILL.md` — Codex-discovery bridge; check whether its
  `allowed-tools` mirror needs the same `Bash(ll-code:*)` entry
- FSM loops invoking `/ll:verify-issues --check`, notably
  `scripts/little_loops/loops/refine-to-ready-issue.yaml` (`verify_issue` state at
  lines 276-284 → `check_verify_verdict` state at lines 286-296) — behavior must be
  unchanged; verify no new failure mode on the `verify_verdict` gate

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/check_verify_verdict.py` — `cmd_check_verify_verdict()`
  (~line 41) reads only the `verify_verdict` frontmatter enum value (`VALID`/`NON_VALID`),
  not the `## Verification Notes` markdown body — confirmed unaffected by adding a
  provider/freshness line to that section, but cite this as the concrete gate consumer the
  "verdict-origination prohibition" is protecting
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` (lines 28, 364, 967-974) —
  also references a `verify_verdict` field in `summary.json`, but that's a distinct,
  post-implementation verdict, unrelated to this issue's claim-verification `verify_verdict`
  — noted only to rule it out, no change needed

### Similar Patterns
- `commands/refine-issue.md:205-245` (Step 3.05) — the canonical consumer shape
- `skills/wire-issue/graph-discovery-layer.md` — contract + three safety rules
- `docs/guides/GRAPH_DISCOVERY_GUIDE.md` — binding rules to reference, not restate

### Tests
- `scripts/tests/` — CLI-allowlist / command-frontmatter validation covering
  `Bash(ll-code:*)` (confirm which suite owns allowed-tools assertions)
  > ⚠ Superseded — `ll-verify-cli-allowlist` validates a different surface; see below
- `ll-verify-cli-allowlist` — ensure the new tool grant is registered
  > ⚠ Superseded — validates `ll-*` presets, not command frontmatter; see below

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_skills_and_commands.py` — append
  `("commands/verify-issues.md", "Bash(ll-code:*)", "ENH-3126")` to the
  `DOC_STRINGS_PRESENT` list (starts line 26; feeds `test_string_present_in_doc` at
  line 257) — this is the actual mechanism that would have caught the missing grant, not
  `ll-verify-cli-allowlist`
- New test file modeled directly on `scripts/tests/test_enh3098_refine_issue_graph_seeding.py`
  (the precedent for `refine-issue`'s `Bash(ll-code:*)` grant + Step 3.05 seeding +
  delegation-to-guide checks) — add `TestVerifyIssuesFrontmatter` (parametrized over
  `commands/verify-issues.md`, plus `skills/ll-verify-issues/SKILL.md` only if that bridge
  is updated to carry `allowed-tools`), a §2B.0 step-existence/ordering check, a
  delegates-rather-than-restates-the-contract check against `GRAPH_DISCOVERY_GUIDE.md`, and
  a provenance-recorded-outside-Session-Log check (mirroring
  `TestStep305Seeding.test_provenance_recorded_outside_session_log`)
- Correction: `ll-verify-cli-allowlist` (`scripts/little_loops/cli/verify_cli_allowlist.py`,
  test in `scripts/tests/test_verify_cli_allowlist.py`) validates that `ll-*` console-script
  entry points appear in two permission presets (`skills/configure/areas.md`,
  `scripts/little_loops/init/writers.py::_LL_PERMISSIONS`) — it does not inspect
  command-frontmatter `allowed-tools` at all, so it will not catch a missing
  `Bash(ll-code:*)` grant on `commands/verify-issues.md`. No change needed there since
  `ll-code` is presumably already registered in both presets (given `refine-issue`/
  `wire-issue` already ship with the grant).

### Documentation
- `docs/guides/GRAPH_DISCOVERY_GUIDE.md` — add verify-issues as a consumer and document
  the stricter verdict-origination rule, which does not apply to the other two
- `docs/reference/CLI.md` — only if the consumer list is enumerated there

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/GRAPH_DISCOVERY_GUIDE.md:12-17` — `## Consumers` table with rows
  `| Skill / command | Phase | Consumer doc |`; add a
  `| \`/ll:verify-issues\` | §2B.0 | \`commands/verify-issues.md\` § 2B.0 |` row, following
  the existing `/ll:wire-issue` / `/ll:refine-issue` row format exactly
- `docs/reference/CLI.md:2663-2668` — confirmed: the "Skill consumers" line under `ll-code`
  explicitly names `/ll:wire-issue (Phase 3.6)` and `/ll:refine-issue (Step 3.05)`; append
  `/ll:verify-issues (§2B.0)` to that same sentence

### Configuration
- N/A — gated by `ll-code --json status`, no new config key (confirmed:
  `scripts/little_loops/config-schema.json` has zero `ll_code`/`ll-code` references;
  `refine-issue`/`wire-issue` don't read a provider-config key either, so no precedent to
  follow)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-12 — based on codebase analysis:_

- `docs/reference/CLI.md` — the "Skill consumers" sentence under `ll-code` has shifted to lines 2664-2668 (previously cited as 2663-2668); content and required edit (append `/ll:verify-issues (§2B.0)`) are otherwise unchanged from this issue's existing citation.
- Locator re-check confirms all other citations still current: `docs/guides/GRAPH_DISCOVERY_GUIDE.md:12-17` (2-row Consumers table), `commands/verify-issues.md:4-9` (allowed-tools still `Read, Glob, Grep, Edit, Bash(git:*)`, no `Bash(ll-code:*)`), `skills/ll-verify-issues/SKILL.md` (still a bare bridge stub with no `allowed-tools` field), `scripts/tests/test_wiring_skills_and_commands.py` `DOC_STRINGS_PRESENT` (still ends at the ENH-3050 entry, ready for append), `scripts/little_loops/cli/issues/check_verify_verdict.py:41-70` (still reads only the `verify_verdict` enum), and `scripts/little_loops/loops/refine-to-ready-issue.yaml:276-296` (`verify_issue`/`check_verify_verdict` state pair unchanged).

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `docs/guides/GRAPH_DISCOVERY_GUIDE.md:12-17` — add the `/ll:verify-issues` row to
  the `## Consumers` table
- Update `docs/reference/CLI.md:2663-2668` — append `/ll:verify-issues (§2B.0)` to the
  "Skill consumers" sentence under `ll-code`
- Update `scripts/tests/test_wiring_skills_and_commands.py` — append
  `("commands/verify-issues.md", "Bash(ll-code:*)", "ENH-3126")` to `DOC_STRINGS_PRESENT`
- Add a new test file modeled on `scripts/tests/test_enh3098_refine_issue_graph_seeding.py`
  covering `commands/verify-issues.md`'s frontmatter grant, §2B.0 structure, delegation to
  `GRAPH_DISCOVERY_GUIDE.md`, and provenance recorded outside the Session Log
- Decide and, if needed, update `skills/ll-verify-issues/SKILL.md` — currently a bare bridge
  stub with no `allowed-tools` field (unlike `skills/ll-refine-issue/SKILL.md`, which mirrors
  its command's grant verbatim)
- Regenerate host-adapter mirrors after the source edit:
  `ll-adapt --host gemini --apply` (updates `.gemini/commands/verify-issues.toml`) and
  `ll-adapt --host kimi-code --apply` (updates `.kimi-code/skills/ll-verify-issues/SKILL.md`)
  — no test enforces command-level mirror parity, so this is a manual step, not an
  automatically-caught gap

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
- `/ll:confidence-check` - 2026-08-12T04:21:31 - `5df644f7-db35-4699-9e26-c26f5863985c.jsonl`
- `/ll:decide-issue` - 2026-08-12T03:53:22 - `22039bd3-8110-4496-8778-17b575764718.jsonl`
- `/ll:refine-issue` - 2026-08-12T03:52:43 - `22039bd3-8110-4496-8778-17b575764718.jsonl`
- `/ll:confidence-check` - 2026-08-12T03:47:35 - `3c4325ca-846c-4b88-b34b-72a9800d6c53.jsonl`
- `/ll:wire-issue` - 2026-08-12T02:34:44 - `dde9bdb7-36e0-4b13-9d7d-138bf8ed09fd.jsonl`
- `/ll:refine-issue` - 2026-08-09T20:34:00 - `20730683-2565-4a26-b2cc-54e8c3853f7b.jsonl`
- `/ll:format-issue` - 2026-08-09T20:26:10 - `094e7212-923b-4b82-873b-48d193f4afe0.jsonl`
- `/ll:capture-issue` - 2026-08-09T05:10:04 - `b7457e6e-9654-45e5-a9bd-43e1bcddbd28.jsonl`

---

## Status

- [ ] Not started
