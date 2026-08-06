---
id: FEAT-3077
title: Decide and document the smoke-test/go-no-go carve-out policy for CLAUDE_CODE_DISABLE_BACKGROUND_TASKS
type: FEAT
priority: P3
status: open
testable: true
parent: FEAT-3060
depends_on:
- FEAT-3076
labels:
- automation
- headless
- host-runner
decision_needed: false
verify_verdict: VALID
confidence_score: 90
outcome_confidence: 81
score_complexity: 24
score_test_coverage: 15
score_ambiguity: 22
score_change_surface: 20
---

# FEAT-3077: Decide and document the smoke-test/go-no-go carve-out policy for CLAUDE_CODE_DISABLE_BACKGROUND_TASKS

## Summary

Two skills rely on backgrounding that `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`
affects:

- `skills/manage-issue/SKILL.md:367,394-396` permits backgrounding
  long-running processes (servers) for smoke tests: "start in background,
  wait briefly for startup, then terminate."
- `skills/go-no-go/SKILL.md:172-176,272-278` launches two agents concurrently
  with `run_in_background: true`, then waits for both before a foreground
  judge step.

**The decision is made and recorded below** (see `### Decision Rationale`):
the flag defaults to `true`, the `manage-issue` carve-out is retired at the
tool level and restated in terms of shell-level backgrounding (zero capability
loss, empirically verified), and the `go-no-go` carve-out is preserved
unchanged because it is not reachable under automation today and degrades to
sequential execution rather than failure.

What remains in this issue is the documentation edit implementing that
decision. FEAT-3078 consumes the default from AC2.

## Parent Issue

Decomposed from FEAT-3060: Hard-disable background tasks in headless
automation instead of instructing against them. Resolves that issue's
Acceptance Criterion 3.

## Dependency

FEAT-3076 (`done`) answered whether `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`
blocks only `Bash run_in_background` or also subagent-tool backgrounding: it
blocks both. A follow-on probe run for this issue
(`postmortems/feat-3077-verify/`) answered the question FEAT-3076 left open —
whether *shell-level* backgrounding survives the flag. It does. Both findings
are folded into the analysis below.

## Proposed Solution

Apply the recorded decision as a documentation edit:

1. Rewrite `skills/manage-issue/SKILL.md:367` (and the carve-out sentence at
   `:394-396`) to state the shell-level pattern explicitly instead of a
   blanket permission to background.
2. Leave `skills/go-no-go/SKILL.md` unchanged, per AC3's "explicitly confirmed
   to need no change" disposition.
3. Regenerate the host-adapter mirrors (see Wiring Phase).

### Reachability Analysis

FEAT-3076 established the flag's *scope* (both `Bash` and `Agent`
`run_in_background`). Scope alone does not determine risk, because FEAT-3078's
injection is gated on `automation_profile is not None` — the variable only
ever reaches a child that an automation path spawned. The two carve-outs sit
very differently against that gate:

- **`manage-issue` smoke test — live.** `issue_manager.py:1213,1401` hardcode
  `automation_profile="ll-auto"`, so every `ll-auto` / `ll-sprint` /
  `ll-parallel` drive of this skill runs in a child carrying the flag. This
  carve-out is squarely in the blast radius.
- **`go-no-go` concurrent agents — latent, not live.** `/ll:go-no-go` is
  user-invoked, or bridged through `ll-action invoke` (`cli/action.py:34`,
  `_VERIFIER_SKILLS` → `runner_spec.run_action`). `cmd_invoke`
  (`cli/action.py:214-320`) never populates `automation_profile`, and
  `runner_spec.py:128` sources it from `spec.args.get("automation_profile")`,
  which that `ActionSpec` does not set — so it resolves to `None` and no flag
  is injected. The only path that would inject it is an FSM loop state
  invoking the skill with a `pruning_profile` set
  (`fsm/executor.py:1902`); no built-in loop does this today
  (`autodev.yaml:1926` mentions `/ll:go-no-go` only in a comment).

Correcting the earlier framing: this is **one live site and one latent site**,
not two equally-at-risk sites.

### Degradation Analysis

Even in the latent case, `go-no-go` does not break. FEAT-3076's
`agent_disabled.jsonl` capture found that under the flag the `Agent` tool
still runs the subagent and returns its full final response — synchronously,
in the same turn — rather than erroring. So a `go-no-go` run inside a
future automation path would lose *concurrency* between the pro and con
agents, not correctness: both arguments are still produced, still fed to the
foreground judge, and the verdict is unchanged. The cost is wall-clock, in a
path that does not exist yet.

### Options

**Option A — Retire both carve-outs, flag defaults `true`.** Rewrite
`manage-issue`'s smoke-test step to run the server in the foreground (losing
the start/wait/terminate capability), and rewrite `go-no-go` to launch its two
agents sequentially. Delivers FEAT-3060's value but pays a real capability
loss in `manage-issue` and a needless rewrite in `go-no-go`.

**Option B — Preserve both carve-outs, flag defaults `false`.** Nothing
changes unless a project opts in. Preserves both behaviors, but FEAT-3060's
motivating failure (BUG-3026's 30% recurrence; the 2026-08-04 `ll-auto
--only ENH-3046` run that lost 21.6 minutes of completed work) stays open by
default in every project, and no further issue in this decomposition would
own turning it on — FEAT-3060, FEAT-3076 are `done` and FEAT-3078 is the last
child. Shipping FEAT-3078 would be a no-op deliverable.

**Option C — Retire `manage-issue`'s carve-out at the *tool* level only,
restating it as shell-level backgrounding; preserve `go-no-go` unchanged;
flag defaults `true`.** The smoke-test workflow ("start in background, wait
briefly for startup, then terminate") does not require the `run_in_background`
tool parameter — `cmd & pid=$!; sleep 3; kill $pid` inside a single foreground
`Bash` call does the same job, and the flag does not reach POSIX job control
inside a command string. `go-no-go` needs no edit per the reachability and
degradation analyses above.

### Decision Rationale

**Selected: Option C** — retire the `manage-issue` carve-out at the tool level
and restate it in shell terms; leave `go-no-go` unchanged; `FEAT-3078`'s
`orchestration.disable_background_tasks` defaults to **`true`**.

Option C is the only option that delivers FEAT-3060's value without paying for
it in lost capability. Option B is disqualified on outcome: it makes the entire
three-issue decomposition end in a flag nobody turns on, leaving the exact
failure the epic was filed to close fully open by default. Option A delivers
the value but discards a working smoke-test pattern and rewrites `go-no-go`
for a risk that does not exist on any current code path.

The premise Option C rests on was verified empirically rather than assumed,
using FEAT-3076's methodology (real `claude -p` children, `claude --version`
2.1.219, stream-json capture) — full record:
`postmortems/feat-3077-verify/README.md`.

| Dimension | Option A | Option B | Option C |
|---|---|---|---|
| Delivers FEAT-3060's value | 3 | 0 | 3 |
| Capability preserved | 1 | 3 | 3 |
| Simplicity of edit | 1 | 3 | 2 |
| Risk | 1 | 2 | 3 |
| **Total** | **6/12** | **8/12** | **11/12** |

Key evidence:

- **Shell-level backgrounding survives the flag.** With
  `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` set, a single foreground `Bash`
  call `python3 server.py & SRV_PID=$!; sleep 3; curl -s
  http://localhost:8731/ ; echo; kill $SRV_PID` started the server, served
  the request (`ll-smoke-ok`), and terminated it — with no
  `run_in_background` key in the emitted tool call. Evidence:
  `postmortems/feat-3077-verify/c1_shellamp_disabled.jsonl`, § Probe C1.
- **The existing carve-out prose already elicits the surviving pattern.**
  Given `SKILL.md:367`'s wording verbatim and no hint toward shell syntax,
  the model under the flag independently chose `python3 server.py >
  smoke_out.log 2>&1 & SRV=$! ... kill $SRV`, got `HTTP/1.0 200 OK` /
  `ll-smoke-ok`, and cleaned up. So the retirement costs nothing in practice;
  the rewrite exists to make the behavior deterministic rather than
  incidentally correct. Evidence:
  `postmortems/feat-3077-verify/c2_generic_disabled.jsonl`, § Probe C2.
- **`go-no-go` is not reachable under the gate today**, and degrades to
  sequential-but-correct if it ever is. Evidence: `cli/action.py:214-320`
  (no `automation_profile` set), `runner_spec.py:128`,
  `postmortems/feat-3076-verify/agent_disabled.jsonl` (subagent runs and
  returns its full response synchronously under the flag).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- `docs/reference/COMMANDS.md:396` needs **no** change — it paraphrases the `/ll:go-no-go` concurrent-launch behavior, and Option C leaves that behavior intact. (This bullet previously read as conditional on retiring the `go-no-go` carve-out; the decision is not to retire it.)
- After editing `skills/manage-issue/SKILL.md`, regenerate the stale host-adapter mirrors via `ll-adapt --host kimi-code --apply` and `ll-adapt --host gemini --apply` (or confirm the project's adapter-sync convention) so `.kimi-code/skills/manage-issue/SKILL.md` and `.gemini/skills/manage-issue/SKILL.md` don't diverge from source. The `go-no-go` mirrors need no regeneration.
- Edit `manage-issue/SKILL.md:394-396` as an append, not a reflow of the surrounding paragraph — `scripts/tests/test_wiring_skills_and_commands.py` asserts the literal strings `"foreground-blocking"` and `"scheduled wakeup"` at lines 389-393 (BUG-2408).
- Mind the 500-line cap enforced by `scripts/tests/test_enh494_skill_companions.py`: `manage-issue/SKILL.md` has only 3 lines of headroom (497/500). The Option C edit is a restatement of two existing sentences (`:367` and `:394-396`), not an addition, so it should be net-neutral on line count — but verify, and extract to a companion file (ENH-494 pattern) if it isn't.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis; reachability correction and probe added 2026-08-06 during decision review:_

- FEAT-3076 (now `done`) confirmed empirically, via real `claude -p` child-process invocations, that `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` disables **both** `Bash run_in_background` **and** `Agent`-tool `run_in_background` subagent launches — not a Bash-only scope. Key evidence: `.issues/features/P3-FEAT-3076-verify-claude-code-disable-background-tasks-scope.md` § Findings, citing `postmortems/feat-3076-verify/bash_control.jsonl` vs. `bash_disabled.jsonl` and `agent_control.jsonl` vs. `agent_disabled.jsonl`.
- **Correction to an earlier reading of that finding.** A previous revision of this issue concluded "both carve-outs would break under the flag. Neither is exempt by mechanism." That conflates the flag's *scope* with the carve-outs' *reachability*. FEAT-3078 gates injection on `automation_profile is not None`, and only the `manage-issue` carve-out sits on a path that sets it. See `### Reachability Analysis` under `## Proposed Solution` for the full derivation — one live site, one latent site.
- **Shell-level backgrounding is out of the flag's reach.** Probed directly for this decision: `postmortems/feat-3077-verify/README.md` (probes C1 and C2, `claude --version` 2.1.219). This is what makes Option C available and is the load-bearing fact behind the recorded decision.
- `.issues/features/P3-FEAT-3078-thread-disable-background-tasks-config-flag-through-host-runner.md` already exists as the sibling implementation issue (`depends_on: FEAT-3077`) and follows the `automation_profile`-style per-call threading pattern (its own `### Decision Rationale`, Option A) — this issue's decision is a direct input to that work's flag default, not a parallel implementation track.

## Acceptance Criteria

1. Both known carve-outs have an explicit, recorded disposition:
   `manage-issue` smoke test → **retired at the tool level**, restated in
   shell terms; `go-no-go` concurrent agent launch → **preserved unchanged**.
   (Satisfied by `### Decision Rationale`; verify it survives implementation
   rather than re-deciding.)
2. FEAT-3078's `orchestration.disable_background_tasks` default is
   **`true`**. This is the single value FEAT-3078 consumes from this issue.
3. `skills/manage-issue/SKILL.md:367` no longer grants a blanket permission to
   background, and instead names the shell-level pattern (`cmd & pid=$!;
   sleep N; kill $pid` in one foreground `Bash` call). The carve-out sentence
   at `:394-396` is updated to match, without reflowing lines 389-393.
4. `skills/go-no-go/SKILL.md` is confirmed unchanged, with the reason recorded
   (not reachable under the `automation_profile` gate today; degrades to
   sequential-but-correct if it ever is).
5. `.kimi-code/skills/manage-issue/SKILL.md` and
   `.gemini/skills/manage-issue/SKILL.md` are regenerated so the mirrors match
   the edited source.
6. `python -m pytest scripts/tests/test_wiring_skills_and_commands.py
   scripts/tests/test_enh494_skill_companions.py` passes (BUG-2408 literals
   intact; 500-line cap not exceeded).

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

### Files to Modify
- `skills/manage-issue/SKILL.md:367,394-396` — smoke-test carve-out (Bash `run_in_background`). **Retire at the tool level; restate as shell-level backgrounding.**
- `skills/go-no-go/SKILL.md:172-176,272-278` — concurrent adversarial-agent launch carve-out (Agent-tool `run_in_background`). **No change** (AC4); listed for the record only.

### Dependent Files
- `.issues/features/P3-FEAT-3078-thread-disable-background-tasks-config-flag-through-host-runner.md` — depends_on this issue; consumes this issue's decision to set the new `disable_background_tasks` flag's default value. **Resolved: `true`** (see AC2 and `### Decision Rationale`).
- `scripts/little_loops/config-schema.json` `orchestration` object (~line 1554, currently only `host_cli`/`request_path`) — where FEAT-3078 will add the `disable_background_tasks` schema entry; no entry exists yet.
- `scripts/little_loops/host_runner.py:297-368` (`ClaudeCodeRunner.build_streaming()`) — FEAT-3078's threading point; out of this issue's scope, cited for context only.

_Wiring pass added by `/ll:wire-issue`:_
- `.kimi-code/skills/manage-issue/SKILL.md`, `.kimi-code/skills/go-no-go/SKILL.md`, `.gemini/skills/manage-issue/SKILL.md`, `.gemini/skills/go-no-go/SKILL.md` — host-adapter mirrors (`scripts/little_loops/cli/adapt.py` → `little_loops.adapters.core.process_skills`) currently contain copies of the exact carve-out prose being edited (`.kimi-code/skills/manage-issue/SKILL.md:366-393`, `.gemini/skills/go-no-go/SKILL.md:173,277`). They are git-tracked but regenerated, not hand-edited — editing only the `skills/` source leaves these stale until `ll-adapt --host kimi-code --apply` / `--host gemini --apply` (or equivalent) is re-run. [Agent 1 finding]

### Conventions in Force
- Decision recording: a `### Decision Rationale` subsection at the end of `## Proposed Solution`, containing a `**Selected:** ...` line, a reasoning paragraph, and (when scoring options) a Consistency/Simplicity/Testability/Risk table — evidence: this issue's own parent `P3-FEAT-3060-hard-disable-background-tasks-in-headless-automation.md:105-122`, and the general convention formalized in `skills/decide-issue/SKILL.md:383-409`.
- Config flags that preserve existing behavior when off state that explicitly in their JSON-Schema `description`, naming what stays unchanged — evidence: `config-schema.json` `orchestration.epic_worktree.enabled` (~388-392): "Master switch — when false (default), today's per-worker branch behavior is preserved unchanged."; `rubric_gated_compaction.enabled` (~1395-1401): "When false (default), falls back to threshold-only behaviour." **Not applicable under the recorded decision** — `disable_background_tasks` defaults to `true`, so FEAT-3078's schema `description` needs the inverse phrasing: state what changes when on (tool-level backgrounding unavailable in automation children) and that setting it `false` restores today's behavior.
- Skill-doc carve-out exceptions are written as plain prose stating the exception and re-drawing the general rule's boundary (no `> Note:` callout convention exists for this) — evidence: `skills/manage-issue/SKILL.md:394-396`, "This does **not** apply to the `run_cmd` smoke test above: ... Only the result-blocking final test suite must be foreground." `go-no-go/SKILL.md` instead states each step's backgrounding mode directly at point of use (`:174` vs. `:278` "**foreground**"), with no separate carve-out-explanation subsection — if `go-no-go`'s carve-out is preserved, there is no existing precedent phrasing tying such a sentence to a named config flag; the `manage-issue` sentence shape is the closest structural precedent to extend.

### Tests
- None apply — both carve-outs are skill-markdown prose, not code; no test file covers `skills/manage-issue/SKILL.md` or `skills/go-no-go/SKILL.md` content directly (`ll-verify-skills` checks structure/format, not this decision's substance).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_skills_and_commands.py` (`DOC_STRINGS_PRESENT`, ~lines 190-197) — BUG-2408 asserts the literal strings `"foreground-blocking"` and `"scheduled wakeup"` at `skills/manage-issue/SKILL.md:389-393`, immediately preceding the carve-out sentence at 394-396 this issue edits. No test asserts the carve-out sentence itself, but a reflow of that paragraph (vs. an append-only edit) risks breaking this test — verify after editing. [Agent 3 finding]
- `scripts/tests/test_enh494_skill_companions.py` (`SKILL_LINE_LIMIT = 500`, `test_no_oversized_skills`) — `skills/manage-issue/SKILL.md` is currently 497/500 lines (3 lines of headroom) and `skills/go-no-go/SKILL.md` is 481/500 (19 lines of headroom). If the recorded decision requires adding more than a couple of sentences (e.g. a full carve-out-explanation subsection for `go-no-go`, per this issue's own "Conventions in Force" note that no such subsection precedent exists yet), `manage-issue/SKILL.md` will trip this test and require companion-file extraction (ENH-494 pattern) to stay compliant. [Agent 3 finding]

### Documentation
- `docs/claude-code/settings.md:772` — vendored flag scope description, confirmed accurate by FEAT-3076's findings (covers both Bash and Agent-tool `run_in_background`).

- `postmortems/feat-3077-verify/README.md` — this issue's own probe record (C1: shell-level `&` survives the flag; C2: existing SKILL.md wording already elicits the surviving pattern). Cited by `### Decision Rationale`.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md:396` — the `/ll:go-no-go` command description paraphrases the concurrent-launch carve-out ("Launches two isolated background agents concurrently — one arguing for implementation, one against..."). This was flagged as conditionally stale if the carve-out were retired; **under the recorded decision it is not retired, so this line stays accurate and needs no edit**. No equivalent paraphrase of the `manage-issue` smoke-test carve-out exists elsewhere. [Agent 2 finding, disposition updated]

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

### Types
N/A — this issue produces no new data types; it records a policy decision and edits two skill markdown files.

### Signatures
`ClaudeCodeRunner.build_streaming(prompt, automation_profile=None)` — unmodified by this issue (`scripts/little_loops/host_runner.py:297`); FEAT-3078 will extend it to thread `disable_background_tasks` through, using this issue's decision as the flag's default-value input.

### Call Path
No runtime call path changes in this issue's own scope — it records a decision, not code. The decision's eventual consumer:
`(this issue's recorded decision)` -> `disable_background_tasks` default value -> `ClaudeCodeRunner.build_streaming()` (FEAT-3078, unmodified here)

Analyzer finding: no existing mechanism lets a skill markdown file branch on a `.ll/ll-config.json` boolean at doc-authoring time — `{{config.project.*}}` template interpolation (used elsewhere in `skills/manage-issue/SKILL.md:356,359,362,365,368`) substitutes config *values* into commands, it does not conditionally select prose. So whichever decision this issue records reaches skill authors only as static prose (e.g. extending `skills/manage-issue/SKILL.md:394-396`'s existing "This does **not** apply to..." sentence), not as code — the runtime enforcement side (whether the flag is actually set in the child env) is entirely FEAT-3078's separate scope.

### Decision Rules

The decision is recorded (`### Decision Rationale` under `## Proposed
Solution`); these are the rules it was derived from, retained so the reasoning
is auditable rather than re-litigated.

- **Scope ≠ risk**: a carve-out is only at risk if it runs in a child that
  carries the flag. FEAT-3078 gates injection on `automation_profile is not
  None`, so the test is "does this skill's invocation path set
  `automation_profile`?", not "does the flag cover this tool?".
- **Retirement is free when the capability is reachable another way**: a
  carve-out that names a *tool-level* capability can be retired at no cost if
  the same workflow is expressible at the shell level, since the flag does not
  reach POSIX job control inside a `Bash` command string
  (`postmortems/feat-3077-verify/`).
- **Graceful degradation counts as preservation**: the `Agent` tool under the
  flag still runs the subagent and returns its output synchronously
  (`postmortems/feat-3076-verify/agent_disabled.jsonl`), so a carve-out that
  only loses concurrency does not require a prose change.
- **The default must deliver the parent's value**: FEAT-3060, FEAT-3076 are
  `done` and FEAT-3078 is the last child, so a default of `false` would end
  the decomposition with the motivating failure still open by default and no
  issue owning enablement. That disqualifies Option B independently of the
  carve-out analysis.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `skills/manage-issue/SKILL.md:376-400` | The carve-out this issue retires at the tool level |
| `skills/go-no-go/SKILL.md:174,274,278` | The carve-out this issue preserves unchanged |
| `docs/claude-code/settings.md:772` | The flag's documented scope |
| `postmortems/feat-3077-verify/README.md` | Probe proving shell-level backgrounding survives the flag — the basis for Option C |
| `postmortems/feat-3076-verify/README.md` | FEAT-3076's scope proof, incl. the `Agent`-tool graceful-degradation evidence |


## Session Log
- `/ll:confidence-check` - 2026-08-06T20:25:05 - `e7f6993a-a8d5-48b8-8d90-4645279ad635.jsonl`
- `/ll:confidence-check` - 2026-08-06T18:48:21 - `4dc5300f-8d50-475c-a216-8456e00992c3.jsonl`
- `/ll:verify-issues` - 2026-08-06T18:46:47 - `8cd4c2d4-8653-49ff-88ec-c6c2607521de.jsonl`
- `/ll:wire-issue` - 2026-08-06T18:44:48 - `08b79b3e-5c18-4839-ac47-1fa43e1850b9.jsonl`
- `/ll:refine-issue` - 2026-08-06T18:36:03 - `f3363a9b-2bcc-449b-a88d-03fda07c47da.jsonl`
- `/ll:issue-size-review` - 2026-08-06T05:11:26 - `c21cd57e-cb03-41ae-b233-cd39e3e2a29a.jsonl`
