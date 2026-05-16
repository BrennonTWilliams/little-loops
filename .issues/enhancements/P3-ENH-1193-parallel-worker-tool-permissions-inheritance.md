---
discovered_date: "2026-04-20"
discovered_by: parallel-family-review
depends_on: [FEAT-1075, FEAT-1076]
status: deferred
---

# ENH-1193: Document and Test Tool-Permission Inheritance for Parallel Workers

## Summary

No issue in the parallel family specifies whether workers inherit the parent's tool permissions, environment, or credentials. If the parent loop runs with a restricted Claude Code permission set (e.g., `tools: [Read, Grep]`), do all fan-out workers also get only those tools, or do they start with default permissions? Same question for environment variables and any credentials in the parent's process state. Document and test the actual behavior so users don't get surprised by unintended privilege escalation or denial.

## Current Behavior (as of FEAT-1075 / FEAT-1076)

Workers run `FSMExecutor.run()` inside a worker thread (thread mode) or a worktree (worktree mode). In thread mode, workers share the parent Python process — so `os.environ`, open file handles, and any in-memory credentials are shared. In worktree mode, workers are launched as subprocesses (per `FSMExecutor` sub-loop invocation), which inherit env by default.

Tool-permission inheritance is Claude-Code-specific and depends on how the parent FSM was invoked — whether the permissions are read from `.claude/settings.json`, passed via CLI flag, or resolved from the harness state. No parallel-family issue clarifies this.

## Expected Behavior

1. **Documented contract**: one subsection in `docs/generalized-fsm-loop.md` (parallel state chapter) enumerating what workers inherit:
   - `os.environ` — inherited; thread-mode writes race siblings (see FEAT-1189)
   - File handles opened by parent — inherited at fork/spawn time; workers should not reuse parent-owned handles
   - Claude Code tool permissions — inherited from the parent FSM's permission scope; workers do NOT get broader permissions than the parent
   - Credentials in `os.environ` (e.g., `ANTHROPIC_API_KEY`) — inherited; workers can use them. Document as expected.
2. **Test**: a test that launches a parent FSM with a narrow permission scope and verifies workers observe the same scope — either via a permission-check assertion in the worker body or via a subprocess that runs `claude --dry-run` and reports its effective permissions. If Claude Code's permissions are not introspectable from inside a sub-loop, stub the check with a fixture that records effective permissions at worker-body invocation and asserts parity.
3. **Security note**: explicit callout that workers DO inherit parent credentials (API keys, SSH keys, git credentials) — not a restriction, but a documented fact so users know not to run a parallel state with a sub-loop they don't trust.

## Proposed Solution

1. Research step: read `scripts/little_loops/fsm/executor.py` and `scripts/little_loops/cli/loop/run.py` to identify where permissions / env are applied; trace whether they flow to worker-constructed `FSMExecutor` instances correctly.
2. Write the docs subsection in `docs/generalized-fsm-loop.md`.
3. Add one inheritance test in `test_parallel_runner.py`:
   - Set a unique env var in the parent before `runner.run()`; assert a worker's sub-loop observes it (by having the sub-loop echo it into `captures`).
   - If permission introspection is feasible, assert worker permission scope equals parent.

## Files to Modify

- `docs/generalized-fsm-loop.md` — new "Worker Inheritance" subsection
- `docs/reference/parallel-state-v1-scope.md` (ENH-1186) — link to the contract
- `scripts/tests/test_parallel_runner.py` — inheritance test
- `skills/create-loop/loop-types.md` — brief note on the `parallel:` entry

## Acceptance Criteria

- Docs enumerate env, file handles, Claude permissions, credentials — each classified as inherited-safe, inherited-with-caveat, or not-inherited
- Test asserts a parent-set env var is observed by a worker
- Test asserts (or documents if introspection is not feasible) that workers do not observe broader Claude Code tool permissions than the parent
- Security note on credential inheritance is present in the docs
- No code behavior change expected — this is documenting and testing existing behavior

## Impact

- **Priority**: P3 — Docs/test-only; no user-visible functionality change. Important for security clarity when workers run third-party sub-loops, and to prevent future regressions.
- **Effort**: Small — research + docs + one test
- **Risk**: Very Low
- **Breaking Change**: No

## Labels

`fsm`, `parallel`, `docs`, `security`, `tests`

## Related / See Also

- **FEAT-1189** — shared-context mutation contract (env/cwd mutations; this issue covers inheritance at invocation, 1189 covers mutation during execution)
- **FEAT-1075** — `ParallelRunner` which constructs worker `FSMExecutor` instances
- **ENH-1186** — v1 scope doc; inheritance rule belongs in the consolidated doc

---

## Session Log
- `parallel-family-review` - 2026-04-20T00:00:00Z - Created during issue-set review. Permission/env/credential inheritance is unspecified; writing it down prevents security-relevant surprises and future test regressions.

---

**Open** | Created: 2026-04-20 | Priority: P3
