---
discovered_date: "2026-04-20"
discovered_by: parallel-family-review
depends_on: [FEAT-1075, FEAT-1076, FEAT-1174]
status: deferred
---

# ENH-1185: Parallel State Singleton Thread-Safety Audit

## Summary

Audit every module-level singleton, cache, and shared writer touched during parallel fan-out execution and either (a) prove it is safe to use from worker threads, (b) isolate it so workers never reach it, or (c) protect it with a lock. Silent corruption of config state, checkpoint files, or session JSONL logs from concurrent worker-thread access is the worst bug class this family could ship — invisible until data is already lost, and reproducible only under real scheduling pressure.

FEAT-1075 specifies the **contract** (see its "Thread-safety contract" subsection); this issue specifies the **audit and enforcement** that proves the contract is honored by every singleton in the codebase, not just the three called out by name.

### Ownership boundary vs FEAT-1077 (clarified 2026-04-20)

FEAT-1077 **owns** the `TestParallelRunnerSingletonSafety` class and its scaffolding (the four seed tests: parent-checkpoint-not-written-from-workers, session-JSONL-atomic, config-snapshot-read-only, module-level-caches-not-lazily-written). This issue **contributes** to that same class:

1. The audit step (enumerate every module-level singleton reachable from `_run_worker()`); audit output lands in `docs/ARCHITECTURE.md`.
2. Additional test methods for singletons discovered by the audit that are not already covered by FEAT-1077's four seed tests (one test per newly-classified singleton per the classification categories below).
3. The summary test `test_no_module_level_state_mutates_during_fan_out`.

No duplicate class definition — tests added here are appended to the same class scaffolded by FEAT-1077. Do not create a parallel test class.

## Current Behavior (as of FEAT-1075 / FEAT-1076)

FEAT-1075's contract names three singletons explicitly:

- **Config loader** (`BRConfig` / `.ll/ll-config.json` / `ll-config.toml`) — workers must use a frozen snapshot, never re-load from disk
- **Checkpoint persistence** (`PersistentExecutor._save_state()`) — parent checkpoint is written only from the main thread
- **Session JSONL writer** (`get_current_session_jsonl()`) — one-line atomic appends only; no shared file handle across threads

This is a strong starting point. The gap: **there is no systematic audit** confirming no *other* module-level state is touched from workers, and no automated regression gate preventing a future refactor from introducing a new unsafe singleton (e.g., a module-level memoization decorator added to a helper that a worker happens to call).

Concrete risk surface that the existing contract does not enumerate:

- `scripts/little_loops/fsm/schema_loader.py` (or equivalent) — any `@lru_cache` on `load_loop()` / `load_fragment()` performs write-on-read into the cache dict; if the first access happens inside a worker, the dict's `__setitem__` runs in that worker's thread. CPython's GIL protects the dict itself, but if the cache is combined with a validator that holds separate mutable state (e.g., a `Dataclass` validator with a reused error buffer), that secondary state is unprotected.
- Rich / Click / Prompt-Toolkit console singletons — if a worker emits status output via a parent-constructed console, terminal escape sequences from interleaved workers can corrupt the output; the contract covers "session JSONL" but not "stderr/stdout console writes" which are separate sinks.
- Any `logging.getLogger(__name__)` use inside a worker — logger handlers are thread-safe per the stdlib, but module-level `logging.basicConfig()` invocations during a worker's first import path (e.g., a lazy-imported CLI module) are not.
- Plugin / extension registries (`extension.py`) — are interceptor registrations immutable post-`wire_extensions()`? Or can a late-loading extension mutate the list during a worker's execution?

## Expected Behavior

A documented, tested audit result: for every module-level singleton / cache / shared writer that could be transitively reached from `ParallelRunner._run_worker()`, one of the following is true and is enforced:

1. **Worker-unreachable**: the singleton is only touched before `runner.run()` or after it returns; a test asserts workers cannot reach the call site.
2. **Read-only after init**: the singleton is fully populated in the main thread before fan-out; workers only read; a test asserts the cache's size / identity is unchanged across fan-out.
3. **Worker-scoped replacement**: each worker constructs its own instance (e.g., per-worker `PersistentExecutor` writes to a per-worker checkpoint path per FEAT-1174); a test asserts no two workers' writes land in the same file.
4. **Lock-protected**: if none of the above fits, the singleton is protected by a `threading.Lock` acquired around every write, and the lock boundary is narrower than any I/O; a test asserts serialized access under contention.

Explicit inventory covered (minimum):

- [ ] `BRConfig.load()` — worker-unreachable, snapshot passed in
- [ ] `PersistentExecutor._save_state()` — parent file worker-unreachable, per-worker file worker-scoped
- [ ] `get_current_session_jsonl()` — one-line atomic appends, no shared handle
- [ ] `load_loop()` / `load_fragment()` caches — read-only after init (pre-warmed main-thread before fan-out)
- [ ] Schema validator singletons (`fsm-loop-schema.json` loaded validator) — read-only after init
- [ ] `logging` configuration — `basicConfig()` called in main thread only; workers inherit
- [ ] Rich / Click console — audit use inside `ParallelRunner` worker bodies; if workers write to a shared console, document or replace with per-worker handle
- [ ] Extension interceptor registry — immutable after `wire_extensions()` or locked

## Proposed Solution

1. **Static audit pass**: trace every import reachable from `_run_worker()` and grep for module-level mutable state (`_cache = {}`, `@lru_cache`, `logging.basicConfig`, `threading.Lock` usage). Document the audit output in `docs/ARCHITECTURE.md` under the "FSM Loop Mode (ll-loop)" section added by FEAT-1086.
2. **Regression gate**: add `TestParallelRunnerSingletonSafety` class (already scoped by FEAT-1077, reinforced here) covering the four categories above. A new test in this class — `test_no_module_level_state_mutates_during_fan_out` — snapshots the `dict`/`list` size of every identified cache before `runner.run()` and asserts no change after for caches expected to be read-only.
3. **Documentation**: a "Singleton Safety" subsection in `docs/ARCHITECTURE.md` listing every audited singleton and its category (1/2/3/4 above). Adding a new singleton requires updating this list — enforceable by a lint rule that fails CI if the list is out of date (future follow-up if the audit itself catches something).
4. **Locks only where needed**: prefer categories 1–3 over category 4. Introduce a `threading.Lock` only when a singleton genuinely must be shared and mutated; document the lock-holding duration and asserted invariant.

## Files to Modify

- `scripts/little_loops/fsm/parallel_runner.py` — worker-body instrumentation if any singleton needs replacement/isolation
- `scripts/little_loops/fsm/executor.py` — if any `_execute_parallel_state()` helper reaches into shared state
- `scripts/little_loops/fsm/schema_loader.py` (or wherever `load_loop`/`load_fragment` caches live) — pre-warm hook
- `scripts/tests/test_parallel_runner.py` — `TestParallelRunnerSingletonSafety` class expansion
- `docs/ARCHITECTURE.md` — "Singleton Safety" subsection under FSM Loop Mode

## Acceptance Criteria

- Every module-level singleton / cache / shared writer reachable from a parallel worker is classified as one of {worker-unreachable, read-only, worker-scoped, lock-protected}
- `TestParallelRunnerSingletonSafety` class in `test_parallel_runner.py` contains one test per classified singleton, asserting the classification holds under a real-threading fan-out of ≥4 workers with ≥50 iterations each (enough to trigger OS-scheduling races)
- `test_no_module_level_state_mutates_during_fan_out` snapshots each read-only cache's size before/after fan-out and asserts invariance
- `docs/ARCHITECTURE.md` lists every audited singleton with its category and rationale
- All tests run in the default CI suite (no `@pytest.mark.slow` gate)

## Impact

- **Priority**: P2 — Silent corruption is the worst bug class a concurrent feature can ship. The audit must complete before v1 tags, not after the first incident reveals a missing entry. Paired with FEAT-1076 / FEAT-1174 / FEAT-1075 in the v1 ship train.
- **Effort**: Medium — mostly careful reading + targeted tests; actual code changes expected to be small (pre-warm hooks and maybe one lock)
- **Risk**: Low — audit itself is read-only; tests are additive; any surfaced issue is a bug this issue exists to catch
- **Breaking Change**: No — the contract is additive; existing non-parallel code paths are unchanged

## Labels

`fsm`, `parallel`, `safety`, `concurrency`, `audit`, `testing`

## Related / See Also

- **FEAT-1075** — "Thread-safety contract" section defines the contract this issue audits
- **FEAT-1077** — `TestParallelRunnerSingletonSafety` scaffolding this issue expands
- **FEAT-1174** — per-worker checkpoint paths (category 3 singleton: `PersistentExecutor._save_state`)
- **ENH-1186** — v1 scope doc; singleton-safety guarantees documented as part of the v1 contract

---

## Session Log
- `parallel-family-review` - 2026-04-20T00:00:00Z - issue created during parallel-family review to capture the audit-and-enforce work that complements FEAT-1075's thread-safety contract. Not a separate deliverable from FEAT-1075 at the contract level, but a separate work item because the audit spans modules FEAT-1075 does not touch (schema loader caches, logging config, console singletons, extension registry). Must ship alongside v1.

---

**Open** | Created: 2026-04-20 | Priority: P2
