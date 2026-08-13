---
id: FEAT-3121
title: /ll:advise skill wrapping the ll-advise CLI
type: FEAT
parent: FEAT-3044
priority: P3
status: open
testable: true
discovered_date: 2026-08-08
depends_on:
- FEAT-3120
labels:
- planning-hub
verify_verdict: VALID
confidence_score: 80
outcome_confidence: 71
score_complexity: 18
score_test_coverage: 10
score_ambiguity: 18
score_change_surface: 25
size: Very Large
reconcile_attempted: true
---

# FEAT-3121: `/ll:advise` skill wrapping the `ll-advise` CLI

> **Provenance note — 2026-08-08.** Authored as `FEAT-3112` inside a
> non-worktree sandbox whose stray `.ll/` shadowed the project root, so its
> IDs were minted against a shadow issue tree. Salvaged and re-IDed to
> `FEAT-3121`; sibling `FEAT-3111` → `FEAT-3120`, `FEAT-3110` → `FEAT-3122`,
> and the redundant `FEAT-3109` grouping layer collapsed into `FEAT-3044`.
> Two claims below are stale as a result: the dependency-chain check under
> `## Verification Notes` asserts `FEAT-3042`/`FEAT-3043` have no issue files
> (they do exist canonically, both `status: open`), and `FEAT-3120` is
> described as `Deferred` (it is now `open`).

## Summary

Ship the `/ll:advise` skill: the model-decided invocation path for a
second-model consult. This is the skill layer half of FEAT-3044's
original scope, split from [FEAT-3120](P3-FEAT-3120-advisor-consult-core-and-ll-advise-cli.md)
(the `consult()` core and `ll-advise` CLI) because it is a genuinely
separate, differently-tested artifact — a Claude Code skill markdown
file, not Python — that composes on top of the CLI rather than sharing
its implementation, and must land strictly after `ll-advise` exists and
is callable.

## Parent Issue

Decomposed from [FEAT-3044](P3-FEAT-3044-advisor-consult-ll-advise-cli-and-skill.md):
Advisor consult() core, `ll-advise` CLI, and `/ll:advise` skill.

## Current Behavior

There is no model-decided path for invoking an advisor consult from
within a Claude Code session. A user or the model itself has no skill
that assembles decision context, calls `ll-advise`, and surfaces the
structured verdict back into the transcript — the only way to trigger a
consult today (once FEAT-3120 lands) is a hand-typed `ll-advise` shell
invocation.

## Expected Behavior

`/ll:advise` wraps the `ll-advise` CLI (shipped by
[FEAT-3120](P3-FEAT-3120-advisor-consult-core-and-ll-advise-cli.md)) for
the model-decided path: assemble decision context → call `ll-advise` →
structured verdict lands in the transcript.

## Use Case

See FEAT-3044's Use Case (unchanged): a `refine-to-ready-issue` loop
stalled on a `check_semantic` gate runs
`ll-advise --signal score_stall --question "..." --context-file ...` and
gets a structured, stronger-model second opinion instead of a same-model
re-grade. `/ll:advise` is the in-session, model-invoked front door to
that same call.

## Proposed Solution

`/ll:advise` skill-shape precedent: `skills/init/SKILL.md` —
frontmatter `disable-model-invocation: true`, `argument-hint`,
`allowed-tools` listing both a scoped `Bash(ll-advise:*)` entry *and* a
separate bare `Bash` entry, an `arguments:` block, a
`<!-- PLUGIN_VERSION: x.y.z -->` marker immediately under the H1, and a
numbered `## Process` body. The 500-line SKILL.md cap does not apply to
`disable-model-invocation` skills.

The skill's `## Process` should:

1. Assemble the decision context the model already has in the current
   transcript (the question, and any relevant file/diff excerpts) into
   the `--context-file` payload `ll-advise` expects — never an
   auto-slurp of the working tree (per FEAT-3044's deferred "Context
   assembly" note).
2. Require an explicit `--signal` value be chosen or supplied by the
   invoker before calling `ll-advise`, mirroring the CLI's own
   required-signal contract (FEAT-3120 AC 2) — the skill must not paper
   over a missing signal by defaulting one silently.
3. Invoke `ll-advise ... --json` via `Bash(ll-advise:*)` and surface the
   parsed verdict (`recommendation`, `risks`, `confidence`, `dissent`)
   back into the transcript as the skill's response.
4. Surface `ll-advise`'s fail-soft failures (unwired host, capability
   floor violation) as a clear message rather than swallowing the
   non-zero exit silently.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- Required-flag enforcement convention across this codebase's skills: a missing required argument is checked with an explicit conditional at the top of flag parsing, printing `Error: ... is required` + a `Usage:` line, then stopping — never falling through with a default. Evidence: `skills/wire-issue/SKILL.md:75-82`, `skills/verify-issue-loop/SKILL.md:84-93` (which also shows the same pattern applied to a closed-enum flag, `--mode`), `skills/decide-issue/SKILL.md:85`, `skills/create-eval-from-issues/SKILL.md:79-84`. No example in the codebase silently defaults a required flag; `skills/verify-issue-loop/SKILL.md:96-97` shows the codebase's contrasting rule for *optional* args (state the default explicitly, resolve silently) — the two rules are drawn per-argument, not per-skill.
- Fail-soft error surfacing has no existing skill-layer precedent to copy: no skill markdown in the repo today parses a wrapped CLI's JSON `"error"` field back into transcript prose (searched; none found). The CLI-layer convention this skill's output will need to consume is a top-level `"error"` string key alongside `"result": "ERROR"`, e.g. `scripts/little_loops/cli/harness.py:454-464`. The closest skill-layer precedent for the *general shape* of "branch on exit code / error content and state a labeled outcome" is `skills/explore-api/SKILL.md:216-234` and `skills/manage-issue/SKILL.md:221-234` (explicit `HALT:`/`LOG:` prose labels keyed off exit code and scanned output content), and `skills/format-issue/SKILL.md:400-416`'s convention of passing a wrapped CLI's own text through verbatim rather than re-deriving a paraphrased summary.

## Integration Map

### Files to Modify

- `skills/configure/areas.md` — add `ll-advise` / `/ll:advise` to the
  "All ll- commands" preset-tools list (`areas.md:849`, alphabetical,
  between `ll-adapt-skills-for-codex` and `ll-artifact`).
- `.claude/CLAUDE.md` — add `advise`^ to the **Planning & Implementation**
  category list (`.claude/CLAUDE.md:90`, alongside `confidence-check`^,
  `go-no-go`^, `spike`^ — the existing decision-support/second-opinion
  commands), not a new category.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` — add a `` | `advise`^ | ... | `` row to
  the "Quick Reference" table (`docs/reference/COMMANDS.md:1067`,
  immediately after the `go-no-go`^ row — the table groups by workflow
  role, not alphabetically, and `go-no-go` is the nearest existing
  decision-support/second-opinion entry). This table is hand-maintained,
  confirmed not auto-generated (unlike `commands/help.md`, which
  FEAT-2940 made a dynamic `ll-help` catalog with no static entries to
  add).

### New Files

- `skills/advise/SKILL.md` — `/ll:advise`.

### Similar Patterns

- `skills/init/SKILL.md` — frontmatter and `## Process` shape to mirror
  (see Proposed Solution).
- `ll-action` / `ll-harness` skill wrappers, if any exist in
  `skills/`, for the "assemble context → shell out → surface structured
  result" pattern at the skill layer (as opposed to the CLI layer, which
  FEAT-3120 already covers).

### Tests

- Skill markdown files in this repo are not exercised by
  `scripts/tests/` unit tests; validate via the repo's existing
  skill-structure lint (e.g. `ll-verify-skills`, if configured) and a
  manual smoke invocation of `/ll:advise` against a mocked/no-op
  `ll-advise` call, confirming the skill surfaces both a successful
  verdict and an `ll-advise` fail-soft error correctly.
  > ⚠ Superseded — `ll-verify-skills` scope confirmed, hedge unneeded

_Wiring pass added by `/ll:wire-issue`:_
- `ll-verify-skills` is a real, unconditional CLI entry point
  (`scripts/pyproject.toml:83` → `main_verify_skills`,
  `scripts/little_loops/cli/docs.py:237-310` →
  `check_skill_sizes()` in `little_loops/doc_counts.py:384-408`) — no
  "if configured" gate. Its scope is narrow: SKILL.md line count vs. a
  500-line cap, skipping skills with `disable-model-invocation: true`
  (this skill qualifies for that exemption per the Proposed Solution).
  It does **not** validate `allowed-tools`, `argument-hint`,
  `arguments:` shape, or the `PLUGIN_VERSION` marker — no such
  generic frontmatter-shape validator exists anywhere in
  `scripts/tests/` today. Citing it as validating anything beyond line
  count would overstate its coverage.
- No test in this repo exercises a skill referencing a CLI
  (`Bash(ll-advise:*)`) whose Python entry point does not yet exist in
  the source tree — this is a genuinely new ordering (skill lands
  ahead of its CLI dependency, since FEAT-3120 is `status: deferred`).
  Authoring `skills/advise/SKILL.md` with `Bash(ll-advise:*)` today
  will not fail any lint (confirmed no allowed-tools-vs-registered-CLI
  cross-check exists).
- New test file suggested: `scripts/tests/test_advise_skill.py`,
  modeled on `scripts/tests/test_update_skill.py`'s per-string
  assertion style (e.g. `test_update_skill.py:53-59` asserts
  `"PLUGIN_VERSION:" in content`) — assert the presence of
  `disable-model-invocation: true`, the `PLUGIN_VERSION:` marker, and
  `Bash(ll-advise:*)` in `skills/advise/SKILL.md`'s frontmatter, since
  no existing test covers `skills/init/SKILL.md`'s own marker either
  (it has zero dedicated test file to copy verbatim).
- If `skills/advise/SKILL.md` is added to `.gemini/skills/` and
  `.kimi-code/skills/` (cross-host mirrors, auto-generated via
  `ll-adapt --host gemini --apply && ll-adapt --host kimi-code
  --apply`), note this is opt-in per skill — only 3 skills are
  currently pinned in `SKILL_MIRRORS_MUST_MATCH_SOURCE`
  (`scripts/tests/test_wiring_skills_and_commands.py:362-369`). Add
  `("skills/advise/SKILL.md", ".gemini/skills/advise/SKILL.md")` and
  the `.kimi-code/` counterpart there only if this skill is meant to
  be test-enforced against drift; otherwise the mirrors can go stale
  silently (FYI, not a blocking requirement for this issue).

### Documentation

- `.claude/CLAUDE.md` — add `/ll:advise` to the command list (see Files
  to Modify above; listed here too since it is command-catalog
  documentation, not just wiring).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- `skills/init/SKILL.md:1-22` — the cited frontmatter/shape precedent, confirmed verbatim: `disable-model-invocation: true`, `argument-hint: "[flags]"`, `allowed-tools` listing `Bash(ll-init:*)` **and** a separate bare `Bash` entry, `arguments:` as a list of `{name, description, required}` objects, and `<!-- PLUGIN_VERSION: 1.106.0 -->` immediately under the H1 (title line, blank line, marker line).
- Closest existing "assemble context → shell to one CLI → parse JSON → surface structured result" precedents, ranked: `skills/create-eval-from-issues/SKILL.md:180-257` (fullest match — Step 4 there shows the exact "call CLI with `--json`, read the JSON result, if it failed report the `errors` field and stop" shape this skill needs) and `skills/compact-session/SKILL.md:44-61` (minimal single-call variant, names each JSON field to parse in prose after the invocation).
- `allowed-tools` scoping is not a single fixed rule — it splits by how much non-wrapped-CLI shell work the skill does: scoped-only (`skills/compact-session/SKILL.md:5-7`), scoped + bare `Bash` (`skills/init/SKILL.md:6-11`, the form this issue's Proposed Solution already specifies), comma-listed multi-scope (`skills/cleanup-loops/SKILL.md:8`), fully bare (`skills/distill-traces/SKILL.md:7-11`).
- `<!-- PLUGIN_VERSION: x.y.z -->` is carried by exactly 3 skills today (`skills/init/SKILL.md:22`, `skills/configure/SKILL.md:32`, `skills/update/SKILL.md:21`), all currently `1.106.0`. It is read programmatically, not decorative (`skills/configure/SKILL.md:62-63`, `skills/update/SKILL.md:72-78`). Note: this value has visibly drifted from `.claude-plugin/plugin.json`'s `1.154.0` at research time — the marker is not kept in lockstep automatically; whatever value this skill ships with will need the same manual-sync awareness.
- Confirmed via Glob + `scripts/pyproject.toml` entry-point search: `scripts/little_loops/cli/advise.py`, `skills/advise/SKILL.md`, and `consult()`/`AdvisorVerdict` in `advisor.py` do not exist yet anywhere in the main tree — only the capability-floor slice (FEAT-3108: `MODEL_RANKS`, `rank_model`, `check_floor`, `FloorResult`) has landed, in `scripts/little_loops/advisor.py` (113 lines total).
- `skills/go-no-go/SKILL.md` (481 lines) confirmed to have **no** advisor/`Bash(ll-advise:*)` reference today — its "second opinion" is produced via same-model `Agent`-tool subagent spawns (`go-no-go/SKILL.md:172-337`), not a distinct advisor host/model. The overlap this issue's Out of Scope section defers to Slice 2 is real and still unresolved as of this research pass. `skills/ll-go-no-go/SKILL.md` is an unrelated 27-line Codex-bridge pointer to the same file, not a second implementation.
- `scripts/little_loops/cli/doctor.py`'s `CheckResult` dataclass (`doctor.py:54-73`, fields `name/status/note/severity/findings`) is the "structured JSON, never hard-fail" shape this issue's Expected Behavior cites; `severity: Literal["error","informational"]` decides exit-code impact independently of `status` (`doctor.py:60-67`), and `_capability_check_results` (`doctor.py:98-113`) is a deliberately non-`@register_check` function because it needs a resolved `HostRunner` at call time — the same shape `/ll:advise`'s Bash invocation needs for a resolved advisor host.

## Acceptance Criteria

1. `/ll:advise` exists at `skills/advise/SKILL.md`, follows the
   `skills/init/SKILL.md` frontmatter shape (`disable-model-invocation`,
   `argument-hint`, `allowed-tools` with a scoped `Bash(ll-advise:*)`
   entry), and is listed in `.claude/CLAUDE.md`'s command list and
   `skills/configure/areas.md`'s preset-tools list.
2. Invoking `/ll:advise` with a question and an explicit signal calls
   `ll-advise --json` and surfaces the parsed `recommendation`, `risks`,
   `confidence`, and `dissent` fields back into the transcript.
3. Invoking `/ll:advise` without a resolvable `--signal` does not call
   `ll-advise` with a silently-defaulted signal — it surfaces the
   same required-signal contract `ll-advise` itself enforces
   ([FEAT-3120](P3-FEAT-3120-advisor-consult-core-and-ll-advise-cli.md) AC 2).
4. When the underlying `ll-advise` call fails soft (unwired host,
   capability floor violation), `/ll:advise` surfaces the reason as a
   clear message, not a raw traceback or a silently-swallowed failure.

## Out of Scope

- **FEAT-3120** — `consult()` core and the `ll-advise` CLI this skill
  wraps.
- **FEAT-3108** — `MODEL_RANKS`, `rank_model`, `FloorResult`.
- **FEAT-3122** — the `ll-doctor` advisor-reachability check.
- **FEAT-3038 (Slice 2)** — wire `confidence_gate` and `pre_done` to
  auto-consult; add `max_consults_per_task` plus the per-task counter.
- **FEAT-3039 (Slice 3)** — FSM stall escalation consuming
  `evaluate_diff_stall` / `evaluate_score_stall` verdicts.

Also unresolved and deferred (inherited from FEAT-3044):

- **Overlap with `/ll:go-no-go`.** Decide in Slice 2 whether the advisor
  becomes go-no-go's different-model engine or stays a separate surface.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- Dependency-chain check (2026-08-08): `depends_on: FEAT-3120` is itself `status: deferred` with `depends_on: [FEAT-3042, FEAT-3043, FEAT-3108]` (confirmed via `ll-issues show FEAT-3120`). `FEAT-3042` and `FEAT-3043` do not exist as issue files anywhere under `.issues/` (`ll-issues show` returns "not found" for both; a repo-wide grep finds them only as references inside FEAT-3108/FEAT-3044/FEAT-3120's own text, never as an authored file). This deepens the "Landing-order risk" already noted in Confidence Check Notes: the blocking chain for this skill's end-to-end smoke test currently bottoms out on two dependency IDs with no corresponding issue in the tracker, not just on a single `deferred` sibling.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

### Types
- `AdvisorVerdict` (target shape, not yet implemented in `advisor.py`) — frozen dataclass: `recommendation: str`, `risks: list[str]`, `confidence: float`, `dissent: str`, `signal: str`, `host: str`, `model: str` (per FEAT-3044's `## API/Interface`; these are the fields `/ll:advise`'s `## Process` must parse out of `ll-advise --json` stdout)
- `FloorResult` (already implemented, `scripts/little_loops/advisor.py:39-52`) — frozen dataclass: `status: Literal["ok", "violation", "advisory", "unknown"]`, `detail: str`; this is what `check_floor()` returns today, and what `/ll:advise` must be able to surface when the underlying `ll-advise` call fails soft on a capability-floor violation

### Signatures
- `consult(*, question: str, signal: str, context: str = "", config: BRConfig | None = None, main_model: str | None = None) -> AdvisorVerdict` — target signature (FEAT-3044's `## API/Interface`), not yet implemented; this is what the `ll-advise` CLI this skill wraps calls into
- `rank_model(host: str, model: str) -> int | None` and `check_floor(advisor_host, advisor_model, main_host, main_model) -> FloorResult` — already implemented (`scripts/little_loops/advisor.py:54-61`, `:64-112`)
- Target `ll-advise` CLI surface (FEAT-3044/FEAT-3120, not yet implemented — FEAT-3120 is status=Deferred): `ll-advise --signal <name> --question <text> [--context-file PATH] [--main-model MODEL] [--host HOST] [--model MODEL] [--json]` — `--signal` is a required argparse argument (non-zero exit, no default substituted, on omission)

### Call Path
`/ll:advise` skill (`Bash(ll-advise:*)`) -> `ll-advise` CLI (`scripts/little_loops/cli/advise.py`, not yet implemented — confirmed absent via Glob and `pyproject.toml` entry-point search) -> `consult()` (`scripts/little_loops/advisor.py`, not yet implemented) -> `check_floor()` (`advisor.py:64-112`, implemented) -> `FloorResult`/`AdvisorVerdict` surfaced through the CLI's `--json` stdout (success) or a JSON `"error"` key (fail-soft, following the shape at `scripts/little_loops/cli/harness.py:454-464`) -> the skill parses stdout and surfaces `recommendation`/`risks`/`confidence`/`dissent` or the error text into the transcript

### Decision Rules
- Required-signal enforcement: the skill must not invoke `ll-advise` when no `--signal` value is resolvable from the invocation — this mirrors the CLI's own required-argparse-argument contract (AC 3) rather than adding a separate keyword/threshold check. The "decision" is binary presence/absence of an explicit signal string; no default is ever substituted. Established codebase convention for this shape (required arg → `Error: ... is required` + `Usage:` line + stop, never a silent fallthrough): `skills/wire-issue/SKILL.md:75-82`, `skills/verify-issue-loop/SKILL.md:84-93`, `skills/decide-issue/SKILL.md:85`, `skills/create-eval-from-issues/SKILL.md:79-84`.
- Fail-soft surfacing: when the underlying `ll-advise` call fails soft (unwired host, or `FloorResult.status in {"violation", "advisory", "unknown"}`), the skill must render `FloorResult.detail` / the CLI's JSON `"error"` field as a clear transcript message, not a raw traceback or a silent swallow. No skill-layer precedent parses this `"error"` key today (searched; none found) — this issue is the first consumer. Related exit-code/HALT-prose conventions exist at `skills/explore-api/SKILL.md:216-234` and `skills/manage-issue/SKILL.md:221-234` (explicit HALT/PROCEED labels keyed off exit code and output content, stderr always captured rather than discarded).

## Impact

- **Priority**: P3 — a capability gap, not a defect.
- **Effort**: Small — a skill markdown file composing on top of an
  already-shipped CLI ([FEAT-3120](P3-FEAT-3120-advisor-consult-core-and-ll-advise-cli.md)).
- **Risk**: Low — additive, no production code path changes; the skill
  only shells out to an existing, independently-tested CLI.
- **Breaking Change**: No.

## Related Key Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — MR-1, self-evaluation bias.
- `skills/init/SKILL.md` — skill-shape precedent.

## Status

open


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-08_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 71/100 → MODERATE

### Concerns
- `depends_on: FEAT-3120` is `status: deferred` — the `ll-advise` CLI and `consult()` core this skill wraps do not exist in the tree yet, so this skill cannot be smoke-tested end-to-end until FEAT-3120 lands. `blocked_by` is empty (only `depends_on` is set), so this did not trip the Dependencies hard override, but Criterion 5 scores 0 to reflect it — sequencing risk, not a scope problem.
- Test coverage for the new skill is currently plan-only: `scripts/tests/test_advise_skill.py` is proposed but not yet written, and `ll-verify-skills` only checks line count, not frontmatter shape (`allowed-tools`, `arguments:`, `PLUGIN_VERSION`).

### Outcome Risk Factors
- Landing-order risk: authoring `skills/advise/SKILL.md` with `Bash(ll-advise:*)` today references a CLI entry point that doesn't exist yet, so a real smoke test of the skill is blocked until FEAT-3120 ships — mitigate by writing the skill against the FEAT-3120 spec now but deferring the smoke-test AC to right after FEAT-3120 merges.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-08_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 71/100 → MODERATE

### Concerns
- `depends_on: FEAT-3120` is `status: deferred`, and its own `depends_on` chain bottoms out on `FEAT-3042`/`FEAT-3043`, neither of which exists as an authored issue file — the `ll-advise` CLI and `consult()` core this skill wraps do not exist in the tree yet (confirmed: no `scripts/little_loops/cli/advise.py`, no `skills/advise/`, no `consult()` in `advisor.py`), so this skill cannot be smoke-tested end-to-end until FEAT-3120 lands. `blocked_by` is empty, so this does not trip the Dependencies hard override, but Criterion 5 scores 0 to reflect that verification is currently impossible, not just delayed.
- Test coverage for the new skill is plan-only: `scripts/tests/test_advise_skill.py` is proposed but not yet written, and `ll-verify-skills` only checks SKILL.md line count, not frontmatter shape (`allowed-tools`, `arguments:`, `PLUGIN_VERSION`).

### Outcome Risk Factors
- Landing-order risk: authoring `skills/advise/SKILL.md` with `Bash(ll-advise:*)` today references a CLI entry point that doesn't exist yet, so a real smoke test of the skill is blocked until FEAT-3120 ships — mitigate by writing the skill against the FEAT-3120 spec now but deferring the smoke-test AC to right after FEAT-3120 merges.

## Session Log
- `/ll:verify-issues` - 2026-08-13T03:05:57 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:confidence-check` - 2026-08-08T20:31:09 - `f7f77e97-8e98-40b1-b864-f9f127450dd0.jsonl`
- `/ll:reconcile-issue` - 2026-08-08T20:28:55 - `60022333-35ea-4687-9164-fa8ca5988a9f.jsonl`
- `/ll:confidence-check` - 2026-08-08T20:25:46 - `d486f611-71e9-4e1b-8a05-24b6be5894fe.jsonl`
- `/ll:verify-issues` - 2026-08-08T20:24:00 - `0762e7f9-8807-4ee0-a9e5-b60666795f71.jsonl`
- `/ll:refine-issue` - 2026-08-08T20:21:04 - `bd4ed4d4-24d8-4bf7-ae8b-60a84a705f01.jsonl`
- `/ll:confidence-check` - 2026-08-08T20:16:39 - `607dbff6-c56d-4cb6-9d6f-94d43940d35e.jsonl`
- `/ll:verify-issues` - 2026-08-08T20:13:26 - `4b822a6e-1d6a-4264-b044-76a580ddd7ad.jsonl`
- `/ll:wire-issue` - 2026-08-08T20:11:03 - `cf0cb0be-6bdf-436b-b626-68fabe345e75.jsonl`
- `/ll:refine-issue` - 2026-08-08T20:04:11 - `9000cc88-ae35-4aa4-8e64-dfde32d7cbc8.jsonl`
- `/ll:issue-size-review` - 2026-08-08T19:27:04 - `a0b28a4d-10ef-4d55-8a0b-7d1cfa69c530.jsonl`
