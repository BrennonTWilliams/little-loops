---
discovered_date: "2026-04-20"
discovered_by: parallel-family-review
depends_on: [FEAT-1075, FEAT-1076]
status: deferred
---

# FEAT-1189: Parallel Worker Shared-Context Mutation Contract

## Summary

FEAT-1075 specifies that `context_passthrough: true` deep-copies the parent's captured dict into each worker, but does not specify what happens to mutations of env vars, process-wide module state, working directory, or any other ambient state that can leak between sibling workers or back to the parent. Without an explicit contract, sub-loops that mutate anything beyond their own `captures` dict can cause non-deterministic cross-worker interference that is invisible until the second run behaves differently from the first.

## Current Behavior (as of FEAT-1075)

Only `parent_context` (the captured dict) has a defined copy boundary. Undefined for workers:

- Environment variables (`os.environ`) — shared process-wide
- Working directory (`os.chdir`) — shared process-wide in thread mode; worktree-isolated in worktree mode
- `self.captured` mutations that are NOT merged back via `ParallelItemResult.captures` — do they leak anywhere?
- Module-level state mutations a sub-loop might make (e.g., a sub-loop that configures logging, registers a signal handler, writes to a module-level cache)

Worker-scoped state (thread-local, worker-constructed `FSMExecutor`, per-worker `session.jsonl`) is defined; shared ambient state is not.

## Expected Behavior

A documented, tested contract: worker actions to shared process state are **forbidden or isolated** in v1, enumerated explicitly so sub-loop authors know the rules.

1. **`parent_context` mutations**: each worker's deep-copy is independent; mutations stay in the worker's copy and return via `ParallelItemResult.captures`. Sibling workers and the parent do not observe them. *(Already in FEAT-1075 — this issue re-tests and documents.)*
2. **`os.environ` mutations**: forbidden in thread mode (shared process-wide, would race sibling workers). Allowed in worktree mode (each worker runs in a subprocess or on the same process but workflow-isolated per `ll-parallel` semantics — validate which). Document and enforce via a test that sets an env var in one worker and asserts another worker does not observe it (thread mode only — expect failure as a KNOWN v1 limitation, flagged in ENH-1186).
3. **`os.chdir`**: thread mode = forbidden (racy); worktree mode = isolated per-worker. Test that cwd changes in worker A are not observed by sibling worker B in worktree mode.
4. **Module-level mutations**: covered by ENH-1185 (singleton-safety audit). This issue links to ENH-1185 rather than re-implementing.
5. **`self.captured` mutations from inside a sub-loop**: only the worker's `FSMExecutor.captured` is mutated; the parent's `self.captured[state_name]` is written once, atomically, after `runner.run()` returns. Explicit test: a sub-loop that writes to `captures["global_flag"] = true` does not cause `captured["global_flag"]` at the parent level — only `captured.<state>.results[i].captures["global_flag"]`.

## Proposed Solution

1. A new doc section `docs/generalized-fsm-loop.md#parallel-state-shared-state-contract` enumerating the rules above (thread mode vs worktree mode columns).
2. Four new tests in `test_parallel_runner.py`:
   - `test_worker_environ_mutation_leaks_in_thread_mode` — documents the known limitation (v1 thread mode is racy for env vars); test is an **expected-xfail** with a clear message pointing at worktree mode as the mitigation.
   - `test_worker_chdir_isolated_in_worktree_mode` — cwd change in one worker is not seen by sibling.
   - `test_worker_subloop_captures_do_not_leak_to_parent` — `captures["x"] = 1` in a sub-loop does not materialize as `captured["x"]` at the parent; it appears only at `captured.<state>.results[i].captures["x"]`.
   - `test_parent_context_deepcopy_comprehensive` — already in FEAT-1075; this issue adds a cross-reference and asserts nested containers (`list`, `dict`, `set`) all deep-copy, including the identity check.
3. Validation-time warning: if `isolation: thread` is used AND a sub-loop YAML contains `action: shell` with `env:` overrides, surface an info-level log (authoring-time signal that env mutations in thread mode are racy). Do not block — it's only racy if mutations are visible to siblings, which is workload-specific.

## Files to Modify

- `scripts/tests/test_parallel_runner.py` — four new tests
- `docs/generalized-fsm-loop.md` — new "Shared-State Contract" subsection
- `docs/reference/parallel-state-v1-scope.md` (ENH-1186) — link to the contract
- `skills/create-loop/loop-types.md` — add shared-state rule row to the `parallel:` entry

## Acceptance Criteria

- Doc section exists and enumerates rules for `parent_context`, `os.environ`, `os.chdir`, `self.captured` mutations, and points at ENH-1185 for module state
- Four tests exist in `test_parallel_runner.py`; the env-leak test is `@pytest.mark.xfail(reason="v1 limitation — see ENH-1186")` with a docstring pointing at the contract
- `test_worker_subloop_captures_do_not_leak_to_parent` is a pure assertion (no xfail) and passes reliably
- `test_worker_chdir_isolated_in_worktree_mode` passes for worktree mode and xfails for thread mode with explicit reason
- Validation-time info log fires when `isolation: thread` + `action: shell` with `env:` overrides are detected in the same parallel state's sub-loop

## Impact

- **Priority**: P2 — Absent this contract, authors write sub-loops that mutate ambient state and get flaky cross-worker interference that is invisible until a race materializes. Documentation + tests are the v1 deliverable; full enforcement is post-v1.
- **Effort**: Small — four tests + one doc section + a small validation-warning hook
- **Risk**: Low — additive; xfail tests document known v1 limitations cleanly
- **Breaking Change**: No

## Labels

`fsm`, `parallel`, `contract`, `tests`, `docs`

## Related / See Also

- **FEAT-1075** — `parent_context` deep-copy rule (this issue extends it to other ambient state)
- **ENH-1185** — singleton-safety audit (module-level mutations)
- **ENH-1186** — v1 scope doc (links to this contract)
- **FEAT-1184** — worker side-effect cleanup (file-system side of the mutation story)

---

## Session Log
- `parallel-family-review` - 2026-04-20T00:00:00Z - Created during issue-set review. `parent_context` deep-copy is specified but no issue enumerates env/cwd/captures mutation boundaries, so authors will land on silent races until the contract is written down and tested.

---

**Open** | Created: 2026-04-20 | Priority: P2
