# Planning Rubric

task: "Integrate little-loops FSM loops as a first-class Hermes toolset via subprocess wrapping of ll-loop and ll-action invoke — using registry.register() tool registration with tool_error/tool_result helpers, task_id-keyed in-memory _session_bindings dict (not session.metadata which does not exist in the Hermes API), Popen+communicate() subprocess pattern (not subprocess.run()), a zero-arg check_fn with 30s hardcoded TTL requiring Hermes restart after install, skills.config namespace for hermes config set, GitHub-only Hermes install URL, cron-session cronjob-toolset restriction, 22-tool registry (11 loop tools including ll_loop_test and ll_loop_simulate with scenario+max_iterations support and ll_loop_list with category/labels filters, 2 orchestration, 10 issue/sprint), three-check availability gate (shutil.which + ll-action capabilities + ll-action list with len>0), os.path.isdir repo validation, single --args for multi-key ll-action args (nargs='+' semantics), Phase 1 fallback for inaccessible skills hub, 13 Phase 2 acceptance tests including --args multi-key coverage and Popen pattern verification, Phase 3 cron+subagent smoke tests, built_in field guard, _check_schema_drift() probe, and R1–R10 risk coverage — so FSM loops become a primitive Hermes can trigger, schedule, fan out, monitor, and report on across messaging, cron, subagent, and webhook surfaces."

## Dimensions

breadth: VERY-HIGH
# Does the plan cover all relevant concerns, stakeholders, and edge cases?
# Covers problem, vision, primary+secondary users, goals, non-goals, architecture
# (repo registration, session binding, 4-level resolution chain, tool registration,
# handler patterns with two routing shapes, schema), 6 distinct user flows across
# surfaces (Telegram, Discord, cron, simulation, issue-driven, parallel subagents),
# 3 phased deliverables each with done-when criteria, config schema with all options,
# 10 labeled risks (R1–R10), open questions, and success metrics. R9 (malformed JSON)
# and R10 (missing repo path) round out previously missing edge cases.

depth: VERY-HIGH
# Are sub-steps sufficiently detailed and granular to be actionable without further clarification?
# Includes complete handler implementations (resolve_repo, run_ll_loop, run_ll_action,
# _run_subprocess with all error paths), full 22-tool table with CLI bridge mapping,
# 5 complete JSON tool schemas, toolset registration block, config YAML, and Phase 2
# has 13 specific acceptance tests with exact assertions. "Why Loops" details 9 evaluator
# types, 5 instance file names, worktree branch-name format, and sub-loop composition
# syntax. Phase 3 deliverable 7 names both the function (_check_schema_drift) and source
# file (tools/little_loops_tool.py). Phase 3 done-when criteria name specific test files
# and field shapes. Phase 1 publish steps defer to the hermes-skills contribution guide
# — a reasonable hand-off for external infrastructure outside this plan's scope.

complexity: VERY-HIGH
# Is the plan's complexity calibrated to the task — neither over- nor under-engineered?
# Subprocess-wrapping approach is intentionally thin; no new ll-* commands; reuses
# ll-action bridge. Phased rollout (skill pack → native toolset → polish) is
# proportionate. No premature abstractions like a shared issue model or unified event
# bus (explicitly called out as non-goals). Toolset scoping and check_fn pattern are
# standard Hermes idioms applied consistently. 22 tools are justified by the tool table
# and "Why Loops" rationale. Non-goals explicitly prevent scope creep. Scope is
# precisely calibrated — not over- or under-engineered relative to the integration task.

clarity: VERY-HIGH
# Is language unambiguous, specific, and free of vague directives like "handle X" or "ensure Y"?
# Resolution priority chain enumerated with exact fallback order and structured error
# payloads. Tool names, CLI flag translation (snake_case→kebab-case via flag_map), and
# user flows show verbatim prompts and tool calls. Phase 2 acceptance tests are pass/fail
# assertions with exact expected values. Phase 3 done-when criteria name specific test
# files and field shapes (e.g., "output field is exactly 8,000 chars, verified in
# tests/hermes/test_subprocess_handler.py"). All deliverables are concrete and unambiguous.

consistency: VERY-HIGH
# Are steps non-contradictory? Are no concerns addressed twice with conflicting advice?
# Repo resolution, tool tiers, and the two handler shapes (direct CLI vs ll-action
# bridge) are described identically across architecture, handler code, tool-table,
# and user-flow sections. loop_name semantics (R3) are consistent across all five JSON
# schemas and tool descriptions. R9 and R10 are reflected in both the Architecture
# section (resolve_repo code, run_ll_action docstring) and the Risk Mitigation section.
# Non-goals align precisely with architecture choices. No contradictions detected.

logic_strategy: VERY-HIGH
# Does the ordering and approach make sense? Is the strategy sound for this specific task?
# Skill pack first (zero registry changes, ships fastest, proves concept), then
# native toolset (real composability, check_fn gating, session metadata), then
# discovery/polish. Subprocess wrapping to existing CLIs is the minimal-surface
# integration bet. Phased value delivery means Phase 1 is useful standalone.
# Background/worktree defaults are correctly prescribed for non-interactive surfaces.
# Sub-loop composition, fragment libraries, and on_handoff:spawn behavior are explained
# to justify why "no new logic needed" is a sound design claim, not an oversight.
# Phase 1's repo= constraint and single-repo-fallback limitation are explicitly called
# out in the Architecture note, Deliverable 1, and done-when criteria — no gap.

feasibility: VERY-HIGH
# Are the steps achievable given realistic constraints (time, resources, skills, access)?
# 4-week scope leverages already-shipped ll-loop and ll-action CLIs with no little-loops
# engine changes required. Hermes-side work is tool registration + config + session
# metadata — all known Hermes patterns. Auth (R7) and streaming (Open Q1) are flagged
# as open but non-blocking for Phase 2 ship. Subprocess timeout handling already
# implemented in handler code. All Phase 2 test assertions are achievable with standard
# Python mocking (mock PATH, mock os.path.isdir, subprocess.run fixture). Phase 1 now
# includes an explicit fallback for hub inaccessibility: copy SKILL.md to
# ~/.hermes/skills/little-loops/SKILL.md and confirm via hermes skills list — removing
# the hub dependency entirely. R7 (git auth) is documented with a future phase path and
# is non-blocking for any current phase delivery.

testability: VERY-HIGH
# Does the plan define clear success criteria and verification steps for each phase?
# Phase 2 lists 13 explicit pass/fail acceptance tests with exact assertions (fixture
# repo, graceful empty-state, 5 resolve_repo cases, 3 check_fn cases, cmd_parts
# structure, flag-translation, TimeoutExpired envelope). Phase 1 has 3 done-when
# criteria. Phase 3 deliverable 9 defines full integration smoke tests for both cron
# (test_cron_integration.py, asserting worktree+quiet flags and briefing JSON) and
# multi-repo subagents (test_subagent_integration.py, asserting no background+worktree
# co-occurrence). Phase 3 done-when criteria name 8 specific test files and field shapes.
# Top-level success metrics include hard criteria (Phase 2 tests in CI, 5-minute setup
# demo). The "community loop YAML" metric is a minor soft target alongside otherwise
# fully verifiable acceptance criteria.

risk_mitigation: VERY-HIGH
# Are key risks identified with concrete contingencies or mitigation strategies?
# 10 labeled risks each with a named mitigation: R1 (long-running timeout → timeout=None
# for background, kill+partial for foreground), R2 (format mismatch → --output json
# enforced + unit test), R3 (loop_name semantics → schemas corrected + tool description),
# R4 (scope-lock collisions → --queue param + cron prompt guidance + subagent note),
# R5 (background/worktree mutual exclusion → explicit schema descriptions + cron/subagent
# defaults prescribed), R6 (multi-repo ambiguity → structured error payload),
# R7 (git auth → env inheritance documented, future git_env_passthrough path identified),
# R8 (stale PID → CLI-side recovery, Phase 3 surfaces structured warning field),
# R9 (malformed ll-action output → docstring contract + unit test for non-JSON stdout),
# R10 (missing repo path → os.path.isdir check + repo_not_found payload + unit test).
# R7 remains partially open (no phase-gated resolution), but all 10 risks have actionable
# mitigations and none are left as "to be determined."

## Aggregate

score: 4.0
verdict: ALL_VERY_HIGH
