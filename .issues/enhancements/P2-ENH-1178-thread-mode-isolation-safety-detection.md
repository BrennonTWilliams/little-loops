---
discovered_date: "2026-04-18"
discovered_by: parallel-fsm-review
depends_on: [FEAT-1074, FEAT-1075, FEAT-1084]
status: deferred
---

# ENH-1178: Thread-Mode Isolation Safety Detection and Authoring Guidance

## Summary

`isolation: thread` (the default for parallel states) is safe only when concurrent workers do not write to shared filesystem locations. Today, this is documented as a convention ("use `thread` for read-safe sub-loops") with no detection mechanism or authoring signal. An author who starts with `thread` and has sub-loops that write to shared paths will see silent corruption or lost writes with no clear pointer to the root cause. Add detection heuristics and clearer authoring guidance so thread-mode safety is discoverable, not discovered-by-incident.

## Current Behavior (as of FEAT-1074)

`ParallelStateConfig.isolation` defaults to `"thread"`. FEAT-1074 documents the rationale: thread mode is faster, and sub-loops that are read-only (querying issue state, running analysis) are safe in thread mode. Worktree mode is opt-in for sub-loops that modify files.

The problem: there is no way to know ahead of time whether a given sub-loop is read-safe. An author must either:
1. Audit every `shell:` command in the sub-loop's YAML for side effects (fragile, requires reading every tool used)
2. Assume it's not safe and use `worktree` (slower, overhead for no benefit on truly read-only loops)
3. Try `thread` and see what happens (silent data loss on concurrent writes to the same file)

None of these is acceptable for a feature enabled by default.

## Expected Behavior

### Static heuristics at validation time

`validation.py` examines each state's `shell:` command (where present) for patterns indicating filesystem writes: `> `, `>>`, `tee`, `git commit`, `git add`, `ll-issues create`, `ll-issues edit`, `ll-issues promote`, common write-implying commands. If a sub-loop referenced by a `parallel:` state with `isolation: "thread"` contains any of these patterns, emit a VALIDATION WARNING (not error — heuristics have false positives):

```
WARNING: parallel state 'fan_out' uses isolation: thread but sub-loop 'my-loop'
  state 'generate' contains a shell command that looks like a filesystem write
  ('ll-issues create ...'). Concurrent writes across workers can corrupt shared
  state. Use isolation: worktree or explicitly acknowledge with:
    isolation: thread  # acknowledged: loop does not write shared state
```

The "acknowledged" comment is conventional documentation; no schema field needed — the warning triggers on the shell-command heuristic regardless of comments. This is a nudge, not a hard gate.

### Explicit opt-in for thread mode with writes

Add an optional `thread_safety_assertion: Literal["read_only"] | None = None` field on `ParallelStateConfig`. When set to `"read_only"`, validation still warns but the warning is demoted to INFO. This gives authors a way to silence noise in loops they've audited. Null default means the warning is never silenced implicitly.

### Authoring guidance docs

`docs/generalized-fsm-loop.md` (scope of FEAT-1084) gets a new "Choosing isolation mode" section covering:
- What thread vs. worktree actually do (ThreadPoolExecutor vs. git worktree setup)
- When thread is safe (reads, pure computation, non-filesystem side effects like API calls — though API calls may have their own shared state concerns)
- When worktree is required (any filesystem write, any git operation, any `ll-issues create/edit/promote`)
- The static heuristic and how to respond to it
- Performance tradeoff: thread is ~10-100x faster startup per worker; if your sub-loop is short and read-heavy, the difference matters; if it's long and write-heavy, worktree overhead is negligible

## Use Case

**Who**: An author writing their first `parallel:` state, fanning out a sub-loop that runs `ll-issues edit` per item.

**Context**: They leave `isolation: thread` (the default) because the docs said it was fast. The fan-out runs 10 items. Six items' edits land; four are silently lost due to concurrent writes to the same issue-list file.

**Goal**: Validation emits a warning at loop-load time pointing directly at the write pattern, before any fan-out runs. The author sees the warning, switches to `worktree`, and never encounters the silent-corruption scenario.

## Proposed Solution

1. Implement a `_detect_thread_unsafe_patterns(sub_loop_fsm: FSMLoop) -> list[str]` helper in `validation.py` that scans all `shell:` commands in the sub-loop for write patterns and returns a list of offending state names + matched patterns
2. Wire it into FSM validation: when a `parallel:` state with `isolation: "thread"` is loaded, call the detector against the referenced sub-loop; emit warnings per offending state
3. Add `thread_safety_assertion` to `ParallelStateConfig` schema + validation
4. Expand FEAT-1084 docs with the "Choosing isolation mode" section
5. Tests: validation warnings fire for each known write pattern; `thread_safety_assertion: "read_only"` demotes warnings; `isolation: worktree` suppresses them entirely; no warnings on sub-loops with no shell writes

## Dependencies

- **Hard blockers**: FEAT-1074 (schema), FEAT-1075 (runner semantics), FEAT-1084 (docs integration)
- **Related**: ENH-1175 (cleanup contract) — thread-mode failures have cleanup implications discussed there

## Acceptance Criteria

- Loading a parallel state with `isolation: thread` against a sub-loop containing `ll-issues create/edit/promote`, `git commit`, `>`/`>>` redirection, or `tee` emits a validation WARNING naming the offending state and pattern
- `thread_safety_assertion: "read_only"` demotes the warning to INFO (still visible, less noisy)
- `isolation: worktree` suppresses all such warnings
- No false positives on read-only sub-loops (tests cover a representative read-only sub-loop)
- Docs in `docs/generalized-fsm-loop.md` explain mode choice with concrete guidance
- Heuristic pattern list is documented and extensible (adding a new pattern is a one-line change)

## Impact

- **Priority**: P2 — Promoted from P3 on 2026-04-20 during parallel-family review. Rationale: `isolation: thread` is the DEFAULT, and a sub-loop with file-writing actions is a plausible first use (the very first `parallel:` an author writes may well call a loop that runs `Edit`/`Write`/`Bash` with redirection). Silent data loss as the default failure mode on a brand-new feature is exactly the "first-incident" class of bug we should not ship. A validation-time heuristic warning is cheap; catching this at loop-parse time is far better than discovering it via corrupted files in production.
- **Effort**: Small — Heuristic scan is ~30 lines; validation wiring minimal; schema field addition trivial
- **Risk**: Low — Warnings only; no behavior change to runtime; false positives can be silenced with the assertion field
- **Breaking Change**: No — additive warnings; existing loops not using `parallel:` unaffected

## Labels

`fsm`, `parallel`, `validation`, `safety`, `docs`, `authoring`

---

## Session Log
- `parallel-fsm-review` - 2026-04-18T00:00:00Z - spawned during parallel feature review discussion
- `parallel-family-review` - 2026-04-20T00:00:00Z - promoted from P3 to P2. `thread` isolation is the default; silent data loss on the default-mode first use is a ship-blocker class of foot-gun. Validation-time heuristic is cheap and must land in v1. Cross-referenced from FEAT-1084 "v1 Limitations" and from ENH-1186 (v1 scope doc).

---

**Open** | Created: 2026-04-18 | Priority: P2 (promoted from P3 on 2026-04-20)
