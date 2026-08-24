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
confidence_score: 96
outcome_confidence: 80
score_complexity: 22
score_test_coverage: 14
score_ambiguity: 20
score_change_surface: 24
size: Small
reconcile_attempted: true
relates_to:
- FEAT-3120
---

# FEAT-3121: `/ll:advise` skill wrapping the `ll-advise` CLI

> **Provenance note — 2026-08-08.** Authored as `FEAT-3112` inside a
> non-worktree sandbox whose stray `.ll/` shadowed the project root, so its
> IDs were minted against a shadow issue tree. Salvaged and re-IDed to
> `FEAT-3121`; sibling `FEAT-3111` → `FEAT-3120`, `FEAT-3110` → `FEAT-3122`,
> and the redundant `FEAT-3109` grouping layer collapsed into `FEAT-3044`.
> _2026-08-23: the two stale claims this note used to flag (a research note
> asserting `FEAT-3042`/`FEAT-3043` have no issue files; `FEAT-3120`
> described as `Deferred`) have now been corrected in place below._

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

**Decided 2026-08-23 — `disable-model-invocation: false`.** This issue's
Summary and Use Case both define `/ll:advise` as the *model-decided*
invocation path (as distinct from FEAT-3038's gate-wired auto-consult and
from a hand-typed `ll-advise` shell call). `disable-model-invocation: true`
would make the skill user-typed-only and defeat that premise, so the skill
ships model-invocable. Consequences, all in scope here:

- **Shape precedent is `skills/audit-issue-conflicts/SKILL.md:1-30`**, the
  nearest model-invocable decision-support skill, not `skills/init/SKILL.md`
  (a user-typed install skill).
- A trigger-shaped `description:` plus a `metadata.short-description:`
  (truncated form, consumed by the codex/gemini adapters) are required.
- A `trigger_fixtures:` block (`should_fire` / `should_not_fire` phrasings)
  is required — `ll-verify-triggers` measures only the skills that declare
  one (18 of 18 measured today); an unfixtured model-invocable skill lands
  as unmeasured coverage. Its `should_not_fire` list must include at least
  one `/ll:go-no-go`-shaped phrasing, since that is the nearest colliding
  surface.
- The **500-line SKILL.md cap now applies** (`ll-verify-skills` skips only
  `disable-model-invocation: true` skills), and the skill's description
  counts against the `ll-verify-skill-budget` listing budget (503 / 2000
  tokens consumed today — ample headroom, but not free).

**`allowed-tools`: follow `skills/compact-session/SKILL.md:5-7`, not
`skills/init/SKILL.md`.** `init` pairs a scoped entry with a separate bare
`Bash` entry because it does substantial non-wrapped-CLI shell work;
`/ll:advise` makes exactly one `ll-advise` call, so bare `Bash` is a strictly
wider permission grant with nothing to justify it. Ship
`Bash(ll-advise:*)`, `Read`, and `Write` (the last for Process step 1's
`--context-file` payload).

**No `<!-- PLUGIN_VERSION: x.y.z -->` marker.** It is carried by exactly
three skills (`init`, `configure`, `update`) and is read programmatically to
detect install/config-schema drift — a mechanism `/ll:advise` has nothing to
compare itself against. It is also already stale in all three (`1.106.0` vs
plugin.json `1.156.0`), so copying it would add a drift liability for no
behavior.

The skill body carries a numbered `## Process`, which should:

1. Assemble the decision context the model already has in the current
   transcript (the question, and any relevant file/diff excerpts) into
   the `--context-file` payload `ll-advise` expects — never an
   auto-slurp of the working tree (per FEAT-3044's deferred "Context
   assembly" note).
2. Require an explicit `--signal` value be chosen or supplied by the
   invoker before calling `ll-advise`, mirroring the CLI's own
   required-signal contract (FEAT-3120 AC 2) — the skill must not paper
   over a missing signal by defaulting one silently.
3. Invoke `ll-advise ... --json` via `Bash(ll-advise:*)`, capturing
   **both stdout and stderr and the exit code**. On exit 0, parse stdout's
   7-key payload and surface `recommendation`, `risks`, `confidence`, and
   `dissent` back into the transcript as the skill's response.
4. On a non-zero exit, surface the failure as a clear message rather than
   swallowing it. **The failure output is plain stderr text, never JSON**
   (see Program Design → Call Path): render the stderr line verbatim,
   following `skills/format-issue/SKILL.md:400-416`'s pass-the-CLI's-own-text-
   through convention rather than paraphrasing. Two distinct cases:
   - exit 2 with `could not read --context-file ...` — the payload file was
     unwritable/unreadable; the consult never ran and no budget was spent.
   - exit 2 with one of the seven fail-soft `skipped_reason` messages
     (`disabled`, `trigger_not_allowed`, `budget_exhausted`,
     `not_configured`, `floor_violation`, `failed`, `timeout`, from
     `cli/advise.py:_SKIP_MESSAGES`), optionally suffixed `: <outcome.error>`.
5. State the budget side effect. `ll-advise` always calls
   `consult_for_trigger(..., manual=True)`, which bypasses the
   `advisor.enabled` / `advisor.triggers` allowlist but **still spends
   `advisor.max_consults_per_task`, reserved before the host call** — so a
   hung or failed consult still counts, and repeated `/ll:advise`
   invocations drain the same per-task budget that FEAT-3038's
   gate-wired auto-consult will later draw from. The skill body must say
   this so a model invoking it autonomously does not silently exhaust the
   budget.
6. Disambiguate against `/ll:go-no-go` in one line, since the two are
   overlapping second-opinion surfaces until the overlap is resolved (see
   Out of Scope): *go-no-go = same-model adversarial debate via `Agent`
   subagents; advise = different-model one-shot consult.* Add the mirror
   line to `skills/go-no-go/SKILL.md`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- Required-flag enforcement convention across this codebase's skills: a missing required argument is checked with an explicit conditional at the top of flag parsing, printing `Error: ... is required` + a `Usage:` line, then stopping — never falling through with a default. Evidence: `skills/wire-issue/SKILL.md:75-82`, `skills/verify-issue-loop/SKILL.md:84-93` (which also shows the same pattern applied to a closed-enum flag, `--mode`), `skills/decide-issue/SKILL.md:85`, `skills/create-eval-from-issues/SKILL.md:79-84`. No example in the codebase silently defaults a required flag; `skills/verify-issue-loop/SKILL.md:96-97` shows the codebase's contrasting rule for *optional* args (state the default explicitly, resolve silently) — the two rules are drawn per-argument, not per-skill.
- Fail-soft error surfacing has no existing skill-layer precedent to copy: no skill markdown in the repo today parses a wrapped CLI's JSON `"error"` field back into transcript prose (searched; none found). The CLI-layer convention this skill's output will need to consume is a top-level `"error"` string key alongside `"result": "ERROR"`, e.g. `scripts/little_loops/cli/harness.py:454-464`. The closest skill-layer precedent for the *general shape* of "branch on exit code / error content and state a labeled outcome" is `skills/explore-api/SKILL.md:216-234` and `skills/manage-issue/SKILL.md:221-234` (explicit `HALT:`/`LOG:` prose labels keyed off exit code and scanned output content), and `skills/format-issue/SKILL.md:400-416`'s convention of passing a wrapped CLI's own text through verbatim rather than re-deriving a paraphrased summary.

## Integration Map

### Files to Modify

- `skills/configure/areas.md` — **already done, no-op.** `ll-advise` is
  present in the "All ll- commands" preset-tools list (`areas.md:862`,
  between `ll-adapt-skills-for-codex` and `ll-artifact`) as a side effect of
  FEAT-3120 landing, and `ll-verify-cli-allowlist` passes today. Retained
  here only so a reader does not re-derive it.
- `skills/go-no-go/SKILL.md` — add the one-line disambiguation against
  `/ll:advise` (Proposed Solution, Process step 6). Confirmed to carry no
  advisor reference today.
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

- `skills/audit-issue-conflicts/SKILL.md:1-30` — model-invocable frontmatter
  shape to mirror, including `trigger_fixtures` (see Proposed Solution).
  Supersedes the earlier `skills/init/SKILL.md` citation, which is a
  user-typed install skill and the wrong precedent here.
- `skills/compact-session/SKILL.md:5-7,44-61` — scoped-only `allowed-tools`
  for a single wrapped CLI, and the convention of naming each JSON field to
  parse in prose right after the invocation.
- `skills/create-eval-from-issues/SKILL.md:180-257` — fullest "call CLI with
  `--json`, read the result, report the failure and stop" precedent.

### Tests

- `scripts/tests/test_advise_skill.py` (new). The real drift risk for an
  untestable prose artifact is the skill naming a flag, JSON key, or error
  reason that does not exist in the CLI. Assert, importing from the source
  rather than hardcoding literals:
  1. Every `--flag` token appearing in `skills/advise/SKILL.md` is present
     in `ll-advise --help` output.
  2. All 7 `AdvisorVerdict` JSON keys (`advisor.py:161-171`) are named in
     the skill body.
  3. All 7 keys of `cli.advise._SKIP_MESSAGES` are named in the skill body.
  4. Frontmatter shape: `disable-model-invocation: false`,
     `metadata.short-description` present, `trigger_fixtures` present with
     non-empty `should_fire` and `should_not_fire`, and `allowed-tools`
     containing `Bash(ll-advise:*)` but **not** a bare `Bash` entry.
- Existing lints that now apply because the skill is model-invocable:
  `ll-verify-skills` (500-line cap — no longer exempt),
  `ll-verify-triggers` (precision/recall ≥ 0.5 on the declared fixtures),
  `ll-verify-skill-budget` (description listing budget).
- Plus a manual smoke invocation of `/ll:advise` against the live CLI —
  unblocked now that FEAT-3120 has landed — confirming the skill surfaces
  both a successful verdict and a fail-soft stderr error correctly.

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
  the source tree — only relevant if this skill were authored ahead of
  FEAT-3120 (`status: open`; the planned order lands the CLI first).
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
- `<!-- PLUGIN_VERSION: x.y.z -->` is carried by exactly 3 skills today (`skills/init/SKILL.md:22`, `skills/configure/SKILL.md:32`, `skills/update/SKILL.md:21`), all currently `1.106.0`. It is read programmatically, not decorative (`skills/configure/SKILL.md:62-63`, `skills/update/SKILL.md:72-78`). Note: this value has visibly drifted from `.claude-plugin/plugin.json`'s version (`1.154.0` at research time, `1.156.0` as of 2026-08-23) — the marker is not kept in lockstep automatically; whatever value this skill ships with will need the same manual-sync awareness.
- Confirmed via Glob + `scripts/pyproject.toml` entry-point search: `scripts/little_loops/cli/advise.py`, `skills/advise/SKILL.md`, and `consult()`/`AdvisorVerdict` in `advisor.py` do not exist yet anywhere in the main tree — only the capability-floor slice (FEAT-3108: `MODEL_RANKS`, `rank_model`, `check_floor`, `FloorResult`) has landed, in `scripts/little_loops/advisor.py` (113 lines total).
- `skills/go-no-go/SKILL.md` (481 lines) confirmed to have **no** advisor/`Bash(ll-advise:*)` reference today — its "second opinion" is produced via same-model `Agent`-tool subagent spawns (`go-no-go/SKILL.md:172-337`), not a distinct advisor host/model. The overlap this issue's Out of Scope section defers to Slice 2 is real and still unresolved as of this research pass. `skills/ll-go-no-go/SKILL.md` is an unrelated 27-line Codex-bridge pointer to the same file, not a second implementation.
- `scripts/little_loops/cli/doctor.py`'s `CheckResult` dataclass (`doctor.py:54-73`, fields `name/status/note/severity/findings`) is the "structured JSON, never hard-fail" shape this issue's Expected Behavior cites; `severity: Literal["error","informational"]` decides exit-code impact independently of `status` (`doctor.py:60-67`), and `_capability_check_results` (`doctor.py:98-113`) is a deliberately non-`@register_check` function because it needs a resolved `HostRunner` at call time — the same shape `/ll:advise`'s Bash invocation needs for a resolved advisor host.

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

- `skills/configure/areas.md:862` (not `:849` as previously noted — file has grown since) — the "All ll- commands" preset-tools list. `ll-advise` is **already present** in this list's allow-entries string, alphabetically between `ll-adapt-skills-for-codex` and `ll-artifact`. This issue's remaining work here is unchanged: the *skill's own* `allowed-tools` frontmatter still needs `Bash(ll-advise:*)`, and `/ll:advise` itself still needs adding to any command-catalog list — only the CLI-name entry in this specific preset string was already done as a side effect of FEAT-3120 landing.
- `docs/reference/COMMANDS.md:1070` (not `:1067`) — the `go-no-go`^ row in the Quick Reference table has shifted by 3 lines; insertion point is still immediately after that row.

## Acceptance Criteria

1. `/ll:advise` exists at `skills/advise/SKILL.md` and follows the
   `skills/audit-issue-conflicts/SKILL.md` model-invocable frontmatter shape:
   `disable-model-invocation: false`, a trigger-shaped `description`,
   `metadata.short-description`, `argument-hint`, an `arguments:` block, a
   `trigger_fixtures:` block with non-empty `should_fire` /
   `should_not_fire`, and `allowed-tools` of exactly `Bash(ll-advise:*)`,
   `Read`, `Write` — no bare `Bash`, no `PLUGIN_VERSION` marker. It is
   listed in `.claude/CLAUDE.md`'s command list and
   `docs/reference/COMMANDS.md`'s Quick Reference table.
2. Invoking `/ll:advise` with a question and an explicit signal calls
   `ll-advise --json` and surfaces the parsed `recommendation`, `risks`,
   `confidence`, and `dissent` fields back into the transcript.
3. Invoking `/ll:advise` without a resolvable `--signal` does not call
   `ll-advise` with a silently-defaulted signal — it surfaces the
   same required-signal contract `ll-advise` itself enforces
   ([FEAT-3120](P3-FEAT-3120-advisor-consult-core-and-ll-advise-cli.md) AC 2).
4. On a non-zero `ll-advise` exit, `/ll:advise` renders the CLI's **stderr
   line verbatim** — not a paraphrase, not a raw traceback, not a silent
   swallow, and not a parsed JSON `error` field (no such field exists on
   this path). Both failure shapes are covered: the unreadable
   `--context-file` case, and each of the seven fail-soft `skipped_reason`
   messages in `cli/advise.py:_SKIP_MESSAGES`.
5. The skill body states that every invocation spends one unit of
   `advisor.max_consults_per_task`, reserved before the host call, shared
   with FEAT-3038's future auto-consult triggers.
6. `skills/advise/SKILL.md` and `skills/go-no-go/SKILL.md` each carry a
   one-line pointer distinguishing the two surfaces, and `/ll:advise`'s
   `trigger_fixtures.should_not_fire` includes at least one go-no-go-shaped
   phrasing.
7. `ll-verify-skills`, `ll-verify-triggers`, `ll-verify-skill-budget`, and
   `scripts/tests/test_advise_skill.py` all pass.

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
  _2026-08-23 caveat:_ Slice 2 (FEAT-3038) is scoped to auto-consult
  *wiring*, not surface consolidation, so nothing currently on the board
  resolves this — the ambiguity would otherwise ship unbounded. Mitigated
  here at zero cost by the reciprocal one-line pointers in both skill bodies
  plus the go-no-go `should_not_fire` fixture (Proposed Solution step 6,
  AC 6). The architectural decision itself remains deferred.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- Dependency-chain check (2026-08-08; **corrected 2026-08-23** — the original note was written against a shadow issue tree, see the provenance note at the top of this file): `depends_on: FEAT-3120` is `status: open` with `depends_on: [FEAT-3042, FEAT-3043, FEAT-3108]`. `FEAT-3042` and `FEAT-3043` **do** exist as canonical issue files under `.issues/features/`, both `status: open`; `FEAT-3108` is `done`. The blocking chain for this skill's end-to-end smoke test is therefore ordinary open-issue sequencing (FEAT-3042 → FEAT-3043 → FEAT-3120 → this), not missing tracker entries.

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

- **FEAT-3120 status correction**: listed above as an Out-of-Scope dependency this skill wraps — it is now `status: done` (landed 2026-08-23, commit `3c9c42b1`), not `open` as the `## Confidence Check Notes` and earlier research passes describe. `blocked_by` is empty and `depends_on: [FEAT-3120]` now resolves per the repo's dependency semantics (`.claude/CLAUDE.md` § Issue File Format: only `done`/`cancelled` resolve `depends_on`), so this issue is no longer blocked on CLI/core availability. The landing-order risk noted in `## Outcome Risk Factors` ("authoring the skill today references a CLI entry point that doesn't exist yet") no longer applies — `scripts/little_loops/cli/advise.py` and `skills/advise/SKILL.md`'s dependency, `scripts/little_loops/advisor.py`'s `consult()`, are both implemented and covered by `scripts/tests/test_cli_advise.py`. A real end-to-end smoke test of `/ll:advise` against the live CLI is now possible, not blocked.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

- **FEAT-3120 has landed** (`status: done`, commit `3c9c42b1`, 2026-08-23). `scripts/little_loops/advisor.py` is now 523 lines with the full `consult()`/`consult_for_trigger()`/budget pipeline implemented, and `scripts/little_loops/cli/advise.py` (150 lines) plus `scripts/tests/test_cli_advise.py` both exist. The `## Confidence Check Notes` and earlier `## Program Design` research below describing these as "not yet implemented" / "113 lines total" is now stale.
- **Real `ll-advise` CLI flags** (`cli/advise.py:main_advise`, lines 87-149): `--signal` (required, `argparse` `required=True`, no default — confirmed by `test_requires_signal`), `--question` (required), `--context-file` (optional; an `OSError` reading it returns exit `2` before any consult attempt), `--main-host`, `--main-model`, `--host`, `--model`, `--json` (via shared `add_json_arg`).
- **`consult()`'s real signature** (`advisor.py:190`) includes `main_host: str | None = None` in addition to the fields this issue's Signatures subsection already lists — the prior signature citation omitted it.
- **Correction — fail-soft output is NOT JSON.** This issue's Call Path and AC 4 assume `ll-advise`'s fail-soft failures surface via a JSON `"error"` key mirroring `cli/harness.py:454-464`. That is not what the shipped CLI does: `cmd_invoke()`'s failure branch (`advise.py:55-61`) looks up `outcome.skipped_reason` in `_SKIP_MESSAGES` (`disabled`, `trigger_not_allowed`, `budget_exhausted`, `not_configured`, `floor_violation`, `failed`, `timeout`), appends `outcome.error` if set, calls `logger.error(message)` (plain stderr text), and exits `2` — **regardless of `--json`**. There is no JSON-shaped error payload on this path; `harness.py`'s `"error"` key pattern lives in a different function (`_report()`, `harness.py:799-818`) that `advise.py` does not follow. `/ll:advise`'s own fail-soft surfacing (Proposed Solution item 4) must read `ll-advise`'s stderr/exit-code-2 text, not parse a JSON error field that will not be present.
- **Confirmed on the success path**: `AdvisorVerdict`'s dataclass fields match this issue's claimed shape exactly (`recommendation: str`, `risks: list[str]`, `confidence: float`, `dissent: str`, `signal: str`, `host: str`, `model: str`, `advisor.py:161-171`), and `--json` output is exactly those 7 keys (`test_success_prints_exact_json_keys`, `test_cli_advise.py:53-89`).
- Test coverage for the CLI layer this skill wraps already exists and is not something FEAT-3121 needs to add: `scripts/tests/test_cli_advise.py` covers required `--signal`, the 7-key JSON payload, unwired-host/unconfigured/floor-violation/budget-exhausted fail-soft paths (all exit `2`, no traceback), and manual-mode bypass of `advisor.enabled`. This issue's proposed `scripts/tests/test_advise_skill.py` is still needed, but only for the skill markdown's own frontmatter shape — not for re-testing the CLI.

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

- **Actual CLI call site is `consult_for_trigger()`, not `consult()` directly** — `advise.py:cmd_invoke` (line 46) calls `consult_for_trigger(args.signal, question=..., context=..., config=..., main_host=args.main_host, main_model=args.main_model, manual=True)` (`advisor.py:451-522`), which wraps `consult()` with budget tracking and exception-to-`skipped_reason` mapping. `manual=True` (the path `ll-advise` always uses) bypasses the `advisor.enabled`/`advisor.triggers` allowlist checks inside `should_consult()` (`advisor.py:408-448`), but the per-task `advisor.max_consults_per_task` budget still applies and is spent via `record_consult` *before* the host call (reserve-before-consult, so a hung/failed consult still counts). `/ll:advise`'s Call Path should read: skill (`Bash(ll-advise:*)`) -> `advise.py:cmd_invoke` -> `consult_for_trigger()` -> `consult()` -> `check_floor()` -> `AdvisorVerdict` or a mapped `skipped_reason`.
- **Confirmed exit-code / output contract** (verified against current `advise.py` source, supersedes the earlier draft table): success = exit 0, `--json` prints the 7-key `AdvisorVerdict` payload to stdout; `--signal`/`--question` missing = argparse's own non-zero exit before `cmd_invoke` runs; `--context-file` unreadable = exit 2, plain stderr (`could not read --context-file ...: <OSError>`), never reaches `consult_for_trigger`; any fail-soft `skipped_reason` (`disabled`, `trigger_not_allowed`, `budget_exhausted`, `not_configured`, `floor_violation`, `failed`, `timeout`) = exit 2, `logger.error(_SKIP_MESSAGES[reason] + (": " + outcome.error if set))` on stderr — `--json` has no effect on this branch, matching this section's earlier correction that fail-soft output is never JSON-shaped.
- **Only existing Python caller of `consult_for_trigger()`**: `scripts/little_loops/issue_manager.py:821-843` (FEAT-3117's confidence-gate auto-consult trigger) — confirms the manual/auto split in `should_consult()` is already exercised in production code, useful as a second read of the same gate `/ll:advise`'s manual path bypasses.
- **`allowed-tools` precedent refinement**: `skills/compact-session/SKILL.md:5-7` wraps a single CLI with `--json` output using a scoped-only `Bash(ll-compact-session:*)` entry (no bare `Bash`), naming each JSON field to parse in prose right after the invocation (`compact-session/SKILL.md:44-61`) — this is a closer match to `/ll:advise`'s single-call shape than `skills/init/SKILL.md`'s bare-`Bash`-inclusive form, since `/ll:advise` does no other shell work beyond the one `ll-advise` call. Worth weighing against `skills/init`'s precedent when the skill is authored.

_All three subsections below rewritten 2026-08-23 against the shipped
FEAT-3120 source. The prior text described `advise.py`/`consult()` as
unimplemented and instructed parsing a JSON `"error"` key — both wrong; see
the research findings above._

### Types
- `AdvisorVerdict` (**implemented**, `scripts/little_loops/advisor.py:161-171`) — frozen dataclass: `recommendation: str`, `risks: list[str]`, `confidence: float`, `dissent: str`, `signal: str`, `host: str`, `model: str`. These 7 fields are exactly the `--json` stdout payload (`cli/advise.py:64-72`, pinned by `test_cli_advise.py:53-89`), and are what `/ll:advise`'s `## Process` parses on exit 0.
- `FloorResult` (**implemented**, `advisor.py:39-52`) — frozen dataclass: `status: Literal["ok", "violation", "advisory", "unknown"]`, `detail: str`. **Note: `/ll:advise` never sees this type.** A floor violation reaches the CLI only as `skipped_reason == "floor_violation"`; `FloorResult.detail` is not propagated to CLI output. The skill has nothing to render but `_SKIP_MESSAGES["floor_violation"]` (the fixed string `"capability floor violation"`) plus `outcome.error` when set.
- `_SKIP_MESSAGES` (`cli/advise.py:19-28`) — the 7-key reason→prose map that produces every fail-soft stderr line the skill must handle.

### Signatures
- `main_advise()` / `cmd_invoke(args, logger) -> int` (`cli/advise.py:31-149`) — the real CLI entry point. Flags: `--signal` (**required**, `argparse required=True`, no default — pinned by `test_requires_signal`), `--question` (required), `--context-file` (optional), `--main-host`, `--main-model`, `--host`, `--model`, `--json` (via `add_json_arg`).
- `consult_for_trigger(signal, *, question, context, config, main_host, main_model, manual) -> ConsultOutcome` (`advisor.py:451-522`) — the actual call site, **not `consult()` directly**. Wraps `consult()` with budget reservation and exception→`skipped_reason` mapping.
- `consult(*, question, signal, context="", config=None, main_host=None, main_model=None) -> AdvisorVerdict` (`advisor.py:190`) — note `main_host`, omitted from the prior citation here.
- `rank_model(host, model) -> int | None` and `check_floor(advisor_host, advisor_model, main_host, main_model) -> FloorResult` (`advisor.py:54-61`, `:64-112`).

### Call Path
`/ll:advise` skill (`Bash(ll-advise:*)`) -> `ll-advise` CLI (`cli/advise.py:cmd_invoke`) -> `consult_for_trigger(..., manual=True)` (`advisor.py:451-522`, spends `max_consults_per_task` via `record_consult` **before** the host call) -> `consult()` -> `check_floor()` -> either an `AdvisorVerdict` or a mapped `skipped_reason`.

Output contract, verified against source:

| Case | Exit | Output |
|---|---|---|
| Success | 0 | `--json`: the 7-key `AdvisorVerdict` payload on **stdout**. Without `--json`: `logger.info` prose. |
| `--signal` / `--question` missing | argparse non-zero | argparse usage error, before `cmd_invoke` runs |
| `--context-file` unreadable | 2 | plain **stderr**: `could not read --context-file '<path>': <OSError>`; never reaches `consult_for_trigger`, no budget spent |
| Any fail-soft `skipped_reason` | 2 | plain **stderr**: `_SKIP_MESSAGES[reason]` + `": " + outcome.error` if set |

**`--json` has no effect on any failure branch** (`advise.py:55-61`). There is no JSON-shaped error payload anywhere on this path; `harness.py`'s `"error"` key convention lives in `_report()` (`harness.py:799-818`), which `advise.py` does not follow. The skill must read stderr and the exit code — parsing stdout for an `error` key will find nothing.

### Decision Rules
- Required-signal enforcement: the skill must not invoke `ll-advise` when no `--signal` value is resolvable from the invocation — this mirrors the CLI's own required-argparse-argument contract (AC 3) rather than adding a separate keyword/threshold check. The "decision" is binary presence/absence of an explicit signal string; no default is ever substituted. Established codebase convention for this shape (required arg → `Error: ... is required` + `Usage:` line + stop, never a silent fallthrough): `skills/wire-issue/SKILL.md:75-82`, `skills/verify-issue-loop/SKILL.md:84-93`, `skills/decide-issue/SKILL.md:85`, `skills/create-eval-from-issues/SKILL.md:79-84`.
- Fail-soft surfacing (**rewritten 2026-08-23 — the prior rule pointed at a JSON `"error"` field and `FloorResult.detail`, neither of which the CLI emits**): branch on **exit code**, and on a non-zero exit render the captured **stderr** text verbatim as the transcript message — never a traceback, never a silent swallow, never a paraphrase. `FloorResult.detail` is unreachable from the skill; a floor violation arrives as the fixed `_SKIP_MESSAGES["floor_violation"]` string. Conventions to follow: `skills/explore-api/SKILL.md:216-234` and `skills/manage-issue/SKILL.md:221-234` for exit-code-keyed HALT/PROCEED labels with stderr always captured rather than discarded, and `skills/format-issue/SKILL.md:400-416` for passing the wrapped CLI's own text through verbatim.
- Budget accounting: every invocation is a spend. `manual=True` bypasses the `advisor.enabled` / `advisor.triggers` allowlist in `should_consult()` (`advisor.py:408-448`) but not the `max_consults_per_task` budget, which is reserved *before* the host call — so `budget_exhausted` is a legitimate first-invocation outcome if a gate-wired consult already ran this task. The skill states this; it does not attempt to pre-check or work around the budget.

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

> ⚠ **Superseded 2026-08-23 — historical record only, do not implement
> from this block.** Both concerns below are resolved: FEAT-3120 landed
> (`done`, commit `3c9c42b1`), so the CLI/core exist and an end-to-end
> smoke test is unblocked; and the test plan is no longer "plan-only"
> (see Integration Map → Tests, which now specifies
> `scripts/tests/test_advise_skill.py`'s assertions and the four lints that
> apply). The scores here (80/71) are stale — frontmatter carries 96/80.

_Added by `/ll:confidence-check` on 2026-08-08. A near-duplicate of this
block (same date, same scores) was pruned 2026-08-23; full text in git
history. Two claims below were minted against the shadow issue tree and are
corrected inline in brackets._

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 71/100 → MODERATE

### Concerns
- `depends_on: FEAT-3120` is `status: deferred` _[now `open`]_, and its own `depends_on` chain bottoms out on `FEAT-3042`/`FEAT-3043`, neither of which exists as an authored issue file _[both exist canonically under `.issues/features/`, `status: open`]_ — the `ll-advise` CLI and `consult()` core this skill wraps do not exist in the tree yet (confirmed: no `scripts/little_loops/cli/advise.py`, no `skills/advise/`, no `consult()` in `advisor.py`), so this skill cannot be smoke-tested end-to-end until FEAT-3120 lands. `blocked_by` is empty, so this does not trip the Dependencies hard override, but Criterion 5 scores 0 to reflect that verification is currently impossible, not just delayed.
- Test coverage for the new skill is plan-only: `scripts/tests/test_advise_skill.py` is proposed but not yet written, and `ll-verify-skills` only checks SKILL.md line count, not frontmatter shape (`allowed-tools`, `arguments:`, `PLUGIN_VERSION`).

### Outcome Risk Factors
- Landing-order risk: authoring `skills/advise/SKILL.md` with `Bash(ll-advise:*)` today references a CLI entry point that doesn't exist yet, so a real smoke test of the skill is blocked until FEAT-3120 ships — mitigate by writing the skill against the FEAT-3120 spec now but deferring the smoke-test AC to right after FEAT-3120 merges.

_Added by `/ll:confidence-check` on 2026-08-23._

**Readiness Score**: 96/100, but **`ll-issues check-design` hard override fires → STOP — ADDRESS GAPS**
regardless of that score. `ll-issues format-check --format json` returns
`program_design_nonspecific: ["Program Design: no signature-shaped line found in Types,
Signatures, Call Path, or the section preamble"]`.

### Gaps to Address
- **Likely gate false-positive, not a real specification gap.** Every line in `##
  Program Design → Signatures` (this file, lines 393-397) states a real signature with a
  `(file:line)` citation sitting between the signature and its em-dash description, e.g.
  `` `main_advise()` / `cmd_invoke(args, logger) -> int` (`cli/advise.py:31-149`) — the
  real CLI entry point.``. `program_design.py`'s `_SIG_CALL`/`_TAIL` regex (lines 89-101)
  only accepts optional trailing punctuation or an em-dash clause immediately after the
  signature/return-type — a parenthesized `` `file:line` `` citation in between breaks the
  match, so all four Signatures lines and the Types-section dataclass-field line fail to
  register as signature-shaped even though they name real, verified symbols
  (`AdvisorVerdict`, `main_advise`, `consult_for_trigger`, `consult`, `rank_model`,
  `check_floor`) with correct file:line anchors. This is the same root cause as
  `program_design.py`'s citation-placement limitation on `_TAIL`. Two remedies, either
  sufficient: (a) fix `_SIG_CALL`/`_TAIL` to tolerate a `` `(file:line)` `` citation before
  the em-dash, or (b) reformat this issue's Signatures/Types bullets to move the citation
  after the em-dash clause (cosmetic, no content change). Recommend (a) since this pattern
  (signature — citation — em-dash description) is used throughout this issue and is likely
  to recur in other well-researched issues.
- Minor, non-blocking: `format-check` also flags `stale_file_ref: ["skills/advise/SKILL.md"]`
  (expected — the file doesn't exist until this issue is implemented) and
  `empty_provenance_stub: ["line 365"]` (a `` _Added by `/ll:refine-issue`_ `` provenance
  line under Program Design with no content before the next one — cosmetic).

## Verification Notes

### 2026-08-23 (pre-implementation review pass)

Reviewed against the shipped FEAT-3120 source before implementation. Ten
changes applied:

1. **Resolved a design contradiction.** The issue defined `/ll:advise` as
   the model-decided path while mandating `disable-model-invocation: true`,
   which would have made it user-typed-only. Decided
   `disable-model-invocation: false`; pulled in the consequences
   (trigger-shaped `description`, `metadata.short-description`,
   `trigger_fixtures`, loss of the 500-line-cap exemption, skill-description
   budget).
2. **Rewrote `## Program Design` → Types / Signatures / Call Path.** They
   still described `advise.py` / `consult()` / `AdvisorVerdict` as
   unimplemented and instructed parsing a JSON `"error"` key. Verified
   against `cli/advise.py:55-61`: failures are plain stderr + exit 2
   regardless of `--json`. Added the verified exit-code/output table.
3. **Restated AC 4** — `FloorResult.detail` never reaches CLI output;
   enumerated the seven real `_SKIP_MESSAGES` reasons plus the unreadable
   `--context-file` case.
4. **Strengthened the test plan** — flag/JSON-key/skip-reason cross-checks
   against the source, replacing three literal-string assertions.
5. **`allowed-tools` switched** from `init`'s bare-`Bash`-inclusive form to
   `compact-session`'s scoped-only form (`Bash(ll-advise:*)`, `Read`,
   `Write`).
6. **Dropped the `PLUGIN_VERSION` marker** — cargo-culted from three
   install/upgrade skills that read it programmatically; already drifted.
7. **Documented the budget side effect** — `manual=True` still spends
   `max_consults_per_task`, reserved before the host call.
8. **Added reciprocal `/ll:go-no-go` disambiguation** as a zero-cost
   mitigation, since FEAT-3038 does not actually resolve the overlap.
9. **Marked `## Confidence Check Notes` superseded** — both concerns
   resolved, scores stale vs frontmatter.
10. **Minor**: noted `areas.md` wiring is already a no-op; aligned
    frontmatter `depends_on` with the body (`FEAT-3120`, now `done`).

### 2026-08-23 (manual staleness pass)

Corrected in place the two stale claims the provenance note flagged (the shadow-tree "FEAT-3042/FEAT-3043 have no issue files" research note; two "FEAT-3120 is deferred" mentions — it is `open`). Frontmatter `size: Very Large` corrected to `Small`: the deliverable is one skill markdown file plus catalog wiring, matching this issue's own Impact section ("Effort: Small") — the prior value was minted against the shadow tree and would have invited a pointless decomposition pass. Refreshed the plugin.json version note (now 1.156.0).

## Session Log
- `/ll:confidence-check` - 2026-08-24T02:15:31 - `1b6a6218-c48a-41dc-8e35-19ce0c49ff36.jsonl`
- `/ll:confidence-check` - 2026-08-24T02:02:45 - `71b7c246-2810-4260-a931-7b7ac8e9fba1.jsonl`
- `/ll:refine-issue` - 2026-08-24T01:47:00 - `8963b656-d221-49d9-8449-7169844dd5fd.jsonl`
- `/ll:refine-issue` - 2026-08-24T00:20:43 - `68b44843-12dc-4a31-a007-13664d319cc4.jsonl`
- `/ll:refine-issue` - 2026-08-24T00:20:30 - `2d526007-ac76-47ba-8e11-570bf6448f6e.jsonl`
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
