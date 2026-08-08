---
id: FEAT-3077
title: Decide and document the smoke-test/go-no-go carve-out policy for CLAUDE_CODE_DISABLE_BACKGROUND_TASKS
type: FEAT
priority: P3
status: done
completed_at: 2026-08-08
testable: true
parent: FEAT-3060
depends_on:
- FEAT-3076
labels:
- automation
- headless
- host-runner
relates_to:
- BUG-3093
decision_needed: false
verify_verdict: VALID
confidence_score: 100
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
size: Very Large
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

A third skill mentions backgrounding but is **already compliant**:
`skills/decide-issue/SKILL.md:335` spawns one
`ll:codebase-pattern-finder` agent per option in a single message, explicitly
specifying `run_in_background: false` and waiting synchronously. It needs no
disposition. It is named here because the "two carve-outs" inventory was a
point-in-time grep with nothing defending it, and `decide-issue` sits on the
`ll-auto` path (`issue_manager.py:1089`) — see AC7 for the guard that makes
the inventory durable.

**The decision is made and recorded below** (see `### Decision Rationale`):
the flag defaults to `true`, the `manage-issue` carve-out is retired at the
tool level and restated in terms of shell-level backgrounding (zero capability
loss, empirically verified), and the `go-no-go` carve-out is preserved
unchanged because it is not reachable under automation today and degrades to
sequential execution rather than failure.

What remains in this issue is the documentation edit implementing that
decision, plus an inventory-guard test. FEAT-3078 consumes the default
(`true`) from `### Decision Rationale`.

**Size note.** This is a ~20-line change across four files (one SKILL.md, two
generated mirrors, one test). The `depends_on: FEAT-3077` edge on FEAT-3078 is
ordering-only — the two issues touch disjoint files — so landing both in a
single pass is fine, provided this one's SKILL.md edit precedes FEAT-3078's
default-on flag.

## Current Behavior

`skills/manage-issue/SKILL.md:367,394-396` grants a blanket permission to
background the smoke-test server via the `Bash` tool's `run_in_background`
parameter, and `skills/go-no-go/SKILL.md:172-176,272-278` launches its two
adversarial agents concurrently via the `Agent` tool's `run_in_background`
parameter. Neither carve-out is documented against
`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`, and no policy exists for which
carve-outs survive once FEAT-3078 makes the flag default `true` in
automation children.

## Expected Behavior

The recorded decision (`### Decision Rationale`, Option C) is applied:
`skills/manage-issue/SKILL.md`'s smoke-test carve-out is retired at the tool
level and restated as a shell-level `cmd & pid=$!; sleep N; kill $pid`
pattern inside a single foreground `Bash` call (no capability lost);
`skills/go-no-go/SKILL.md` is left byte-identical because its carve-out is
not reachable under today's `automation_profile` gate and degrades to
sequential-but-correct if it ever is; the host-adapter mirrors are
regenerated to match; and a new test pins the carve-out inventory so future
`run_in_background: true` additions don't silently invalidate this decision.

## Impact

- **Severity**: Medium - blocks FEAT-3078 from having a decided default for
  `disable_background_tasks`, and leaves FEAT-3060's motivating failure
  (`ll-auto` runs losing completed work to background-task confusion)
  without a documented resolution path for the two affected skills.
- **Effort**: Small - a ~20-line documentation edit across four files plus
  one inventory-guard test; the decision itself is already made and
  evidenced, so this issue is transcription, not deliberation.
- **Risk**: Low - `go-no-go` is unchanged, and the `manage-issue` restatement
  was verified empirically (`postmortems/feat-3077-verify/`) to preserve the
  smoke-test's start/wait/terminate capability.

## Status

**Done** | Priority: P3

---

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
2. Leave `skills/go-no-go/SKILL.md` byte-identical, per AC3.
3. Regenerate the host-adapter mirrors (see Wiring Phase).
4. Add the carve-out inventory guard test (AC7), so the "two carve-outs"
   finding is enforced rather than re-derived by grep next time.

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
- Extend the ENH-2996 mirror-drift guard so AC4 (mirror regeneration) is test-enforced, not just instructed. `scripts/tests/test_wiring_skills_and_commands.py:351-375` (`WIRE_ISSUE_SKILL_MIRRORS` / `test_wire_issue_skill_mirror_matches_source`) currently asserts mirror-body equality only for `wire-issue`; add `.kimi-code/skills/manage-issue/SKILL.md` and `.gemini/skills/manage-issue/SKILL.md` to that parametrized list (the `_body_after_frontmatter()` helper is reusable as-is). Today the only mirror-currency test covers `wire-issue`, so skipping the `ll-adapt --host ... --apply` regeneration after this edit would pass CI silently — the very gap ENH-2996 was filed to close. `go-no-go` mirrors need no guard (unchanged). [Agent 1/2/3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis; reachability correction and probe added 2026-08-06 during decision review:_

- FEAT-3076 (now `done`) confirmed empirically, via real `claude -p` child-process invocations, that `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` disables **both** `Bash run_in_background` **and** `Agent`-tool `run_in_background` subagent launches — not a Bash-only scope. Key evidence: `.issues/features/P3-FEAT-3076-verify-claude-code-disable-background-tasks-scope.md` § Findings, citing `postmortems/feat-3076-verify/bash_control.jsonl` vs. `bash_disabled.jsonl` and `agent_control.jsonl` vs. `agent_disabled.jsonl`.
- **Correction to an earlier reading of that finding.** A previous revision of this issue concluded "both carve-outs would break under the flag. Neither is exempt by mechanism." That conflates the flag's *scope* with the carve-outs' *reachability*. FEAT-3078 gates injection on `automation_profile is not None`, and only the `manage-issue` carve-out sits on a path that sets it. See `### Reachability Analysis` under `## Proposed Solution` for the full derivation — one live site, one latent site.
- **Shell-level backgrounding is out of the flag's reach.** Probed directly for this decision: `postmortems/feat-3077-verify/README.md` (probes C1 and C2, `claude --version` 2.1.219). This is what makes Option C available and is the load-bearing fact behind the recorded decision.
- `.issues/features/P3-FEAT-3078-thread-disable-background-tasks-config-flag-through-host-runner.md` already exists as the sibling implementation issue (`depends_on: FEAT-3077`) and follows the `automation_profile`-style per-call threading pattern (its own `### Decision Rationale`, Option A) — this issue's decision is a direct input to that work's flag default, not a parallel implementation track.

_Added by `/ll:refine-issue` — 2026-08-07 — based on codebase analysis:_

- **Shell-level start/stop-with-PID is already an established pattern here.** `scripts/little_loops/loops/oracles/code-run-gate.yaml:334-390` (`service_health` state) backgrounds a server and manages its PID entirely at the shell level inside one foreground call: `bash -c "$RUN_CMD" > service.log 2>&1 &` → `SERVICE_PID=$!` → PID written to `service.pid` → teardown/ensure `kill "$SERVICE_PID"` / `kill "$(cat ${run_dir}/service.pid)"` under `trap cleanup EXIT`. It polls via curl `--max-time` against a PID-file rather than `sleep N; kill $pid`, but it is the closest existing relative of the Option C pattern the manage-issue restatement proposes, and the documented consumer of the smoke-test config fields (`run_cmd`/`health_url` at `docs/reference/CONFIGURATION.md:304-305` and `docs/reference/loops.md:834-835`). Restating `skills/manage-issue/SKILL.md:367` in shell terms therefore aligns with an existing codebase idiom, not an invented one. [codebase-pattern-finder]

## Use Case

An `ll-auto` run drives `/ll:manage-issue` on a FEAT that needs a smoke test.
With `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` set in the child (per
FEAT-3078's default), the skill's smoke-test step still starts the server,
waits briefly, hits it, and kills it — using `cmd & pid=$!; sleep N; kill
$pid` inside one foreground `Bash` call instead of the disabled
`run_in_background` tool parameter — so the automation path that motivated
FEAT-3060 keeps its smoke-test capability instead of losing it.

## Acceptance Criteria

> **The decision is already made and recorded** in `### Decision Rationale`
> (Option C; `disable_background_tasks` defaults to `true`). Do not re-derive
> it. The deliverable below is a documentation edit plus one test, roughly 20
> lines across four files.

1. The recorded decision survives implementation unchanged: `manage-issue`
   smoke test **retired at the tool level** and restated in shell terms;
   `go-no-go` concurrent agent launch **preserved unchanged**;
   FEAT-3078's default **`true`**. Satisfied by `### Decision Rationale`
   already being in this file — this AC is a no-change assertion, not work.
2. `skills/manage-issue/SKILL.md:367` no longer grants a blanket permission to
   background, and instead names the shell-level pattern (`cmd & pid=$!;
   sleep N; kill $pid` in one foreground `Bash` call). The carve-out sentence
   at `:394-396` is updated to match, without reflowing lines 389-393.
3. `skills/go-no-go/SKILL.md` is byte-identical to its pre-change state. The
   reason is recorded in `### Reachability Analysis` (not reachable under the
   `automation_profile` gate today; degrades to sequential-but-correct if it
   ever is) — no edit, no new prose.
4. `.kimi-code/skills/manage-issue/SKILL.md` and
   `.gemini/skills/manage-issue/SKILL.md` are regenerated so the mirrors match
   the edited source.
5. `skills/manage-issue/SKILL.md` stays at or under 500 lines. It is currently
   **497** — 3 lines of headroom. The shell-pattern restatement is likely to
   need 2-3 lines where one stood, so measure before and after; extract to a
   companion file (ENH-494 pattern) if it overflows.
6. `python -m pytest scripts/tests/test_wiring_skills_and_commands.py
   scripts/tests/test_enh494_skill_companions.py
   scripts/tests/test_skill_expander.py` passes (BUG-2408 literals intact;
   500-line cap not exceeded; `{{config.project.run_cmd}}` interpolation
   preserved at `:367`).
7. A new test pins the carve-out inventory: grep `skills/` for
   `run_in_background: true` and assert the matches equal an explicit
   allowlist (`go-no-go` only, after AC2 lands). Without this, AC1's "both
   known carve-outs" is a point-in-time snapshot that the next skill author
   silently invalidates. `scripts/tests/test_wiring_skills_and_commands.py` is
   the natural home.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-07 — based on codebase analysis:_

- **Correction — `config-schema.json` `orchestration` is not "currently only `host_cli`/`request_path`".** The object at `scripts/little_loops/config-schema.json:1554-1632` (`additionalProperties: false`) now declares four properties: `host_cli`, `request_path`, `composer`, `cluster` (corroborated by `scripts/little_loops/config/orchestration.py:62-93`). The load-bearing half of that Dependent-Files bullet still holds — no `disable_background_tasks` entry exists (grep of `scripts/` matches nothing) — so FEAT-3078 adds a fifth property to this object. [codebase-analyzer]
- **The inverse description phrasing FEAT-3078 needs for a default-`true` flag is already conventional.** The Conventions-in-Force bullet above predicts FEAT-3078's `disable_background_tasks` schema `description` must state what changes when on and that setting it `false` restores today's behavior. Existing default-`true` flags already use exactly that shape in `config-schema.json`: `learning_tests.auto_prove_learning_gate` (~1042-1043, "Default true (self-healing); set false to keep the gates check-only"), `epic_branches.merge_to_base_on_complete` (~400, "When true (default), the EPIC integration branch is itself merged back..."), `learning_tests.enabled` (~1037-1038). So the phrasing is not first-of-kind. [codebase-pattern-finder]
- **Caveat on the "no `> Note:` callout convention exists for this" claim.** The narrow claim is accurate — carve-out exceptions are written as plain prose, not callouts. But `> **Note:**` callouts are otherwise idiomatic in this codebase and in `skills/manage-issue/SKILL.md` itself (`:327`), plus `skills/map-dependencies/SKILL.md:109`, `skills/link-epics/SKILL.md:333`, `skills/scope-epic/SKILL.md:424`. If the implementer prefers a callout shape for the restated carve-out, it would not be stylistically foreign. [codebase-pattern-finder]

_Added by `/ll:refine-issue` — 2026-08-07 — based on codebase analysis:_

- **Re-verification pass (2026-08-07, `--auto`) — all substantive claims still hold.** The `manage-issue` carve-out prose sits at `skills/manage-issue/SKILL.md:367` (backgrounding sentence) and `:394-396` (carve-out sentence); the `go-no-go` carve-out at `skills/go-no-go/SKILL.md:174-176` (concurrent launch) and `:278` (foreground judge); no `disable_background_tasks` string exists under `scripts/` (tree-wide grep matches nothing). File sizes now: `manage-issue/SKILL.md` is **497**/500 lines, `go-no-go/SKILL.md` **481**/500 (re-measured 2026-08-07; earlier revisions of this issue quoted 498/482, off by one) — the Option C edit must stay within the 3-line headroom as AC5 requires. [codebase-analyzer]
- **Anchor drift — current line numbers for previously cited sites.** `issue_manager.py` hardcodes `automation_profile="ll-auto"` at `:1237` (implement subprocess) and `:1425` (finalize-retry), not `:1213,1401`; the smoke test runs inside those `claude -p` children. `cli/action.py` `cmd_invoke` at `:214` sets no `automation_profile` (repo-wide grep of `action.py` = zero matches); `_VERIFIER_SKILLS` is at `:30`. `runner_spec.py:128` still sources `automation_profile` from `spec.args.get("automation_profile")`; `fsm/executor.py:1902` still maps `pruning_profile` → `automation_profile`; the only `/ll:go-no-go` mention in any loop YAML is a comment at `scripts/little_loops/loops/autodev.yaml:1954`. [codebase-analyzer]
- **`build_streaming()` signature drift.** `ClaudeCodeRunner.build_streaming` def is at `scripts/little_loops/host_runner.py:299` (not `:297`), `automation_profile: str | None = None` at `:308`, and the signature gained `workspace_root: Path | None = None` (FEAT-2878) — it is not the bare `(prompt, automation_profile=None)` the Signatures section implies; it still has no `disable_background_tasks` parameter. [codebase-analyzer]
- **BUG-2408 literal anchors.** `scripts/tests/test_wiring_skills_and_commands.py:196-197` asserts the `"foreground-blocking"` / `"scheduled wakeup"` literals, which live in `skills/manage-issue/SKILL.md` at `:380-391` (immediately above the carve-out at `:394-396`) — this issue's "lines 389-393" phrasing refers to the SKILL file, not the test file. [codebase-analyzer]

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- **Re-verification pass (2026-08-08, `--auto`) — carve-out sentence anchors and line counts still hold exactly.** `skills/manage-issue/SKILL.md` is 497 lines total; the backgrounding sentence sits at `:367` inside the "Run smoke test" comment block (`:355-372`), and the carve-out sentence at `:394-396` within the "Headless-Safe Final Test Run" section (`:376-398`). `skills/go-no-go/SKILL.md` is 481 lines total; the concurrent-launch carve-out is at `:174` (inside "Step 3b: Launch Adversarial Agents", `~172-189`) and the foreground-judge marker at `:278` (inside "Step 3d: Launch Judge Agent", `~276-289`) — note the issue's cited range "272-278" for the second site sits at the tail edge of that section's actual span (`276-289`); not a broken reference, but AC3's range is slightly narrower than the section it points into. No new `run_in_background: true` occurrence exists in `go-no-go/SKILL.md` beyond these two. [codebase-analyzer]
- **No additional shell-level background/wait/kill idiom exists beyond the already-cited `code-run-gate.yaml`.** Searched the codebase for other examples of a single foreground `Bash` call backgrounding a process, waiting, then killing it (the pattern Option C proposes restating `manage-issue/SKILL.md:367` in terms of). `scripts/little_loops/loops/oracles/code-run-gate.yaml:334-390` (`service_health` state) remains the only match — it polls via `curl --max-time` against a PID file rather than a fixed `sleep N; kill $pid`, so the restatement is a simplification of that idiom, not a verbatim copy. `skills/go-no-go/SKILL.md:174` uses a structurally different mechanism (tool-level `Agent` `run_in_background: true`, not shell job control) and `skills/decide-issue/SKILL.md:335` is foreground-synchronous (`run_in_background: false`) — neither is a background/wait/kill example. [codebase-pattern-finder]
- **AC7's inventory-guard test has no exact existing precedent; two structurally different antecedents exist.** No test in the repo currently does "grep a directory for a text pattern → assert the match-set equals an explicit allowlist" as a single operation — AC7 would be the first of that shape. The two closest antecedents: (a) `scripts/tests/test_verify_cli_allowlist.py::TestRun::test_clean_state_returns_zero` — a real product function (`little_loops.cli.verify_cli_allowlist._run`) computes an inventory-drift dict, test asserts it equals an all-clear expected dict; (b) `scripts/tests/test_enh494_skill_companions.py::TestSkillLineLimit::test_all_skills_within_limit` — inline `SKILLS_DIR.glob("*/SKILL.md")` + `.read_text()` loop building an `offenders` list, asserted empty (no separate named allowlist). Neither is a template to copy; they disagree on whether the check is one aggregate assertion or a parametrized per-item comparison against a named list — a shape decision AC7's implementer still needs to make. No existing utility parses skill-body `key: value` lines (like `run_in_background: true`); every precedent does whole-file substring search or frontmatter-only parsing (`little_loops.doc_counts.check_skill_budget`). [codebase-pattern-finder]
- **FEAT-3078 (this issue's dependent) was substantially revised 2026-08-07T16:56 (UTC 21:56), after this issue's last refine pass (2026-08-07T20:05 UTC — refine ran first, FEAT-3078's edit landed after).** ENH-3081 (`bab8c1fc`) extracted the shared `_apply_automation_env()` helper described above; FEAT-3078's own file now carries a "⚠️ Superseding correction" subsection documenting the resulting design question (host-agnostic helper vs. Claude-only guard) and a revised AC2 (explicit neutralization, not mere absence). Two new sibling issues were also captured the same day: BUG-3093 (three `ll-auto` subprocess call sites omit `automation_profile`) and ENH-3094 (collapse per-call automation kwargs into an `AutomationContext` dataclass, sequenced after FEAT-3078). None of this changes FEAT-3077's own recorded decision (Option C, `disable_background_tasks` defaults `true`) or its Acceptance Criteria — FEAT-3077's scope is the skill-markdown edit and inventory test only — but a reader following the Dependent Files link to FEAT-3078 should expect a file that has moved since this issue's Program Design/Dependent Files prose was last synced to it. [codebase-locator, codebase-analyzer]

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- **AC7 concrete scan target and match set (analyzer, 2026-08-08 re-verification).** The literal string `run_in_background: true` occurs exactly once under `skills/` today, at `skills/go-no-go/SKILL.md:174` (confirmed by direct grep). `skills/manage-issue/SKILL.md` never uses that literal — its carve-out is prose-only. So AC7's allowlist, if authored before AC2's edit lands, is `["skills/go-no-go/SKILL.md"]`; it stays that single entry after AC2 too, since the `manage-issue` restatement is shell-level, not the `run_in_background` tool parameter.
- **AC7 has no drop-in extension point in this file; two structurally different antecedents exist, neither copy-paste ready.** `DOC_STRINGS_PRESENT` (`test_wiring_skills_and_commands.py:20+`) is a flat per-string presence-assertion list (the BUG-2408 rows at `:196-197`), not a set-equality/inventory check, so it is not where AC7 fits. The two closest antecedents disagree on where inventory logic should live: `test_enh494_skill_companions.py::TestSkillLineLimit.test_all_skills_within_limit` (`:74-84`) computes an `offenders` list inline in the test via `sorted(SKILLS_DIR.glob("*/SKILL.md"))` + `.read_text()`, asserted empty; `test_verify_cli_allowlist.py::TestRun.test_clean_state_returns_zero` instead asserts a real product function's (`little_loops.cli.verify_cli_allowlist._run`) computed inventory-drift dict against an all-clear expected dict, i.e. the inventory logic lives in application code, not the test. No existing utility in this codebase parses skill-body `key: value` lines — every existing check here does plain substring search over `.read_text()`, not YAML/markdown parsing. [codebase-analyzer]

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
- `scripts/tests/test_skill_expander.py:292-313` (`TestExpandSkillAgainstRealManageIssue`) — expands the real `manage-issue/SKILL.md` and asserts no unresolved `{{config.` / `$ARGUMENTS` tokens. The `:367` restatement must keep the `{{config.project.run_cmd}}` interpolation (and the `:394-396` carve-out sentence must not introduce a new template token), or this test fails — the one new may-break risk beyond the BUG-2408 literals. [Agent 3 finding]
- `scripts/tests/test_manage_issue_changelog_gate.py:16` (`SKILL_FILE`) and `scripts/tests/test_feat1896_skill_bridges.py:14` (`GO_NO_GO_SKILL`) — read the two changed files' real content (changelog-gate/Deviations prose; go-no-go frontmatter + Step-3f bridge). Both target regions outside this issue's edit scope (go-no-go is unchanged per AC4), so they are safe — listed so a reflow beyond the carve-out region is caught. [Agent 3 finding]
- `scripts/tests/test_issue_manager.py:1310-1316` (`TestFinalizeRetryPrompt::test_prompt_forbids_backgrounding_the_test_run`, BUG-3058) — asserts the Python constant `FINALIZE_RETRY_PROMPT` in `scripts/little_loops/issue_manager.py` forbids backgrounding the final test run. Code-side sibling of the same foreground-only rule: it corroborates that the rule already has Python-level enforcement on the finalize-retry path (`issue_manager.py:1425`), independent of this skill's prose — the skill edit changes nothing about that enforcement. [Agent 3 finding]

### Documentation
- `docs/claude-code/settings.md:772` — vendored flag scope description, confirmed accurate by FEAT-3076's findings (covers both Bash and Agent-tool `run_in_background`).

- `postmortems/feat-3077-verify/README.md` — this issue's own probe record (C1: shell-level `&` survives the flag; C2: existing SKILL.md wording already elicits the surviving pattern). Cited by `### Decision Rationale`.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md:396` — the `/ll:go-no-go` command description paraphrases the concurrent-launch carve-out ("Launches two isolated background agents concurrently — one arguing for implementation, one against..."). This was flagged as conditionally stale if the carve-out were retired; **under the recorded decision it is not retired, so this line stays accurate and needs no edit**. No equivalent paraphrase of the `manage-issue` smoke-test carve-out exists elsewhere. [Agent 2 finding, disposition updated]

### Behavior Parity

| Artifact | Behavior | Disposition | Notes |
|---|---|---|---|
| `skills/manage-issue/SKILL.md:367` | Smoke-test step grants blanket permission to background long-running processes via `run_in_background` | CHANGED | Restated as shell-level `cmd & pid=$!; sleep N; kill $pid` in a single foreground `Bash` call — the start/wait/terminate capability is preserved, verified empirically (probes C1/C2, `postmortems/feat-3077-verify/`) |
| `skills/manage-issue/SKILL.md:394-396` | Carve-out sentence exempting the `run_cmd` smoke test from the foreground-only rule | CHANGED | Updated to name the shell-level pattern; must not reflow lines 389-393 (BUG-2408 literals `"foreground-blocking"` / `"scheduled wakeup"`) |
| `skills/go-no-go/SKILL.md:172-176,272-278` | Concurrent background launch of pro/con agents, then a foreground judge | PRESERVED | Not reachable under the `automation_profile` gate today (AC1/AC4); degrades to sequential-but-correct if ever reached |

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-07 — based on codebase analysis:_

- **Correction — `build_streaming()` signature anchor is `:299-310`, not `:297`.** `def build_streaming(` is at `scripts/little_loops/host_runner.py:299`, `automation_profile: str | None = None` at `:308`; `:297` is inside `detect()` (`return shutil.which("claude") is not None`). Verified 299-369: no `disable_background_tasks` parameter exists. The substantive Program Design claim (takes `automation_profile=None`, unmodified by this issue) is unchanged. FEAT-3078's Program Design carries the same `:297` drift and should be corrected there too. [codebase-analyzer]

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- **Further correction — env injection now routes through a shared helper (ENH-3081, landed after the 2026-08-07T20:05 refine pass).** `ClaudeCodeRunner.build_streaming()` (confirmed at `host_runner.py:299`) no longer hand-rolls its env dict inline; at `:353` it calls `_apply_automation_env(env, automation_profile)`, a helper now shared by all five host runners' `build_streaming()` methods (`host_runner.py:353,644,1034,1219,1412`), defined at `host_runner.py:1547-1562`. The helper sets exactly two keys — `LL_AUTOMATION` and `LL_AUTOMATION_PROFILE` — nothing related to background-task disabling; it has no `disable_background_tasks`/`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` handling. This does not change this issue's own N/A Types/Call-Path conclusion (FEAT-3077 produces no code), but the `### Signatures`/`### Call Path` prose's mental model of "an inline env block at build_streaming()" is now the pre-refactor shape; a reader relying on it to orient in FEAT-3078 would be misled about where the eventual `disable_background_tasks` conditional would actually need to be added (inside or alongside `_apply_automation_env()`, not inline in `build_streaming()`). FEAT-3078's own issue file already documents this correction in full (its "⚠️ Superseding correction — ENH-3081" subsection) and records the open design question it creates (host-agnostic helper vs. Claude-only guard) — this issue's Program Design section need not re-litigate that, only stop citing the stale pre-refactor shape. [codebase-analyzer]

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
- `/ll:ready-issue` - 2026-08-08T06:28:47 - `2986e885-ae67-452e-a892-b46a3bf892e5.jsonl`
- `/ll:refine-issue` - 2026-08-08T06:23:37 - `7f658e61-564b-4210-ba49-e4bd14083c5a.jsonl`
- `/ll:verify-issues` - 2026-08-08T06:20:42 - `910c2a44-1e61-4858-a98f-34a32f52b83f.jsonl`
- `/ll:refine-issue` - 2026-08-08T06:13:34 - `c97ca0ac-ef75-4ebe-8deb-58c2e56b41af.jsonl`
- `/ll:confidence-check` - 2026-08-07T20:21:09 - `88962bfb-2ed2-4d72-ace5-bef5a2160a60.jsonl`
- `/ll:wire-issue` - 2026-08-07T20:17:00 - `23d10d83-6e93-491c-a17a-3b2dcb204ab4.jsonl`
- `/ll:refine-issue` - 2026-08-07T20:05:20 - `cf7d98cd-deb3-45fb-9bdf-d58c491714ab.jsonl`
- `/ll:refine-issue` - 2026-08-07T18:30:38 - `9d4f2cf6-011f-4121-9477-800003034eb9.jsonl`
- `/ll:confidence-check` - 2026-08-06T20:25:05 - `e7f6993a-a8d5-48b8-8d90-4645279ad635.jsonl`
- `/ll:confidence-check` - 2026-08-06T18:48:21 - `4dc5300f-8d50-475c-a216-8456e00992c3.jsonl`
- `/ll:verify-issues` - 2026-08-06T18:46:47 - `8cd4c2d4-8653-49ff-88ec-c6c2607521de.jsonl`
- `/ll:wire-issue` - 2026-08-06T18:44:48 - `08b79b3e-5c18-4839-ac47-1fa43e1850b9.jsonl`
- `/ll:refine-issue` - 2026-08-06T18:36:03 - `f3363a9b-2bcc-449b-a88d-03fda07c47da.jsonl`
- `/ll:issue-size-review` - 2026-08-06T05:11:26 - `c21cd57e-cb03-41ae-b233-cd39e3e2a29a.jsonl`
