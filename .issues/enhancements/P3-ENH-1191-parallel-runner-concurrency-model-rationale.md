---
discovered_date: "2026-04-20"
discovered_by: parallel-family-review
depends_on: [FEAT-1075, FEAT-1086]
status: deferred
---

# ENH-1191: Document `ThreadPoolExecutor` Choice and GIL Implications

## Summary

FEAT-1075 picks `concurrent.futures.ThreadPoolExecutor` as the concurrency primitive without justifying the choice over alternatives (`asyncio`, `ProcessPoolExecutor`) or warning users when threads will NOT actually parallelize due to the GIL. Users running CPU-bound pure-Python sub-loops will get the overhead of threading with none of the benefit, and will file performance bugs against the feature unless the docs set the right expectation up front.

## Current Behavior (as of FEAT-1075)

FEAT-1075 specifies `ThreadPoolExecutor`. No rationale, no GIL note, no guidance for when to expect parallelism.

## Expected Behavior

A short authoring-facing docs section that covers:

1. **Choice rationale**: `ThreadPoolExecutor` was chosen because the expected workloads are I/O-bound (subprocess, git, file I/O, network) where the GIL is released. `ProcessPoolExecutor` was rejected because sub-loops need read-access to the parent's `captured` dict and module-level state without serialization overhead; cross-process shared state would require pickling every `parent_context` and losing the deep-copy contract. `asyncio` was rejected because existing sub-loop code is synchronous and rewriting to async is a separate project.
2. **When threads help**: subprocess-heavy loops (shell actions, git ops), file-I/O-heavy loops, network-calling loops (LLM sub-loops) — these release the GIL and parallelize.
3. **When threads don't help**: pure-Python CPU-bound sub-loops (e.g., in-process data processing, pure-Python validation, regex-heavy text processing on large strings) — the GIL serializes these; `max_workers > 1` adds overhead without speedup.
4. **Rule of thumb**: if your sub-loop spawns a subprocess or makes a network call within its first state, threading helps. Pure-Python `action_type: python` states that do non-trivial computation: threads won't help.
5. **What about free-threaded Python?**: One-sentence forward-looking note — Python 3.13+ free-threaded builds change this story; we track this in ENH-XXXX (placeholder, not a blocker).

## Proposed Solution

Add a "Concurrency Model" subsection to `docs/generalized-fsm-loop.md` (chapter: parallel state) with the content above. Cross-link from FEAT-1086's `docs/ARCHITECTURE.md` FSM Loop Mode chapter.

Add a one-paragraph comment in `scripts/little_loops/fsm/parallel_runner.py` at the `ThreadPoolExecutor` construction site:

```python
# ThreadPoolExecutor chosen over ProcessPool/asyncio because expected workloads
# (subprocess, git, file I/O, LLM network calls) release the GIL. Pure-Python
# CPU-bound sub-loops will not parallelize — see docs/generalized-fsm-loop.md
# "Concurrency Model".
```

## Files to Modify

- `docs/generalized-fsm-loop.md` — new "Concurrency Model" subsection
- `docs/ARCHITECTURE.md` — one-paragraph cross-reference under FSM Loop Mode (added by FEAT-1086)
- `scripts/little_loops/fsm/parallel_runner.py` — top-of-file comment

## Acceptance Criteria

- "Concurrency Model" subsection exists in `docs/generalized-fsm-loop.md`
- Docs name the rejected alternatives (ProcessPool, asyncio) with one-sentence reasons each
- Docs give a concrete rule of thumb for when `max_workers > 1` helps
- `parallel_runner.py` has the comment at `ThreadPoolExecutor` construction
- `docs/ARCHITECTURE.md` cross-references the section (added in FEAT-1086)

## Impact

- **Priority**: P3 — Docs-only; prevents user confusion and invalid performance bugs against the feature.
- **Effort**: Small — one doc section + one code comment
- **Risk**: Very Low
- **Breaking Change**: No

## Labels

`fsm`, `parallel`, `docs`, `architecture`

## Related / See Also

- **FEAT-1075** — where `ThreadPoolExecutor` is chosen (this issue documents the choice)
- **FEAT-1086** — architecture/contributing docs (cross-linked)
- **ENH-1186** — v1 scope doc (mention that v1 is thread-pool-based)

---

## Session Log
- `parallel-family-review` - 2026-04-20T00:00:00Z - Created during issue-set review. Absent rationale, users will file flaky performance bugs against the feature for workloads where threading cannot help.

---

**Open** | Created: 2026-04-20 | Priority: P3
