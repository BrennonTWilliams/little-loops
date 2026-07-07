# ENH-2515: Add per-event flush+fsync at StatePersistence append sites

## Goal

Close the SIGKILL data-loss gap in `StatePersistence` and sister append-only
writers by issuing `f.flush()` + `os.fsync(f.fileno())` after every write. The
user-space → kernel cache drain is already in place (open/close per call); what
is missing is the kernel cache → disk drain that only `os.fsync` provides.

## Scope

Four append-only write sites in `scripts/little_loops/fsm/persistence.py`:

| # | Site | Lines | File written |
|---|------|-------|--------------|
| 1 | `append_event` | 425-432 | `events.jsonl` |
| 2 | `_handle_event` usage branch | 696-697 | `usage.jsonl` |
| 3 | `_handle_event` messages branch | 710-711 | `messages.jsonl` |
| 4 | `_write_meta_eval_entry` | 776-777 | `meta_eval.jsonl` |

No public API changes. Existing callers (`PersistentExecutor._save_state`,
executor state-machine main loop, orchestrator, `_helpers`) are unchanged.

## Approach

Refactor all four write blocks to delegate to a private helper:

```python
def _append_jsonl(path: Path, entry: dict[str, Any]) -> None:
    """Append one JSONL row and durably sync to disk.

    ``f.flush()`` drains Python's user-space buffer to the OS; ``os.fsync``
    then forces the kernel page cache to disk. Pairing both preserves the
    row across SIGKILL (which Python cannot trap) — closing the audit-trail
    gap surfaced by BUG-2501.
    """
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
        f.flush()
        os.fsync(f.fileno())
```

Helper location: `_write_meta_eval_entry`'s enclosing class (`StatePersistence`)
or as module-private function — chosen as instance method on
`StatePersistence` so `append_event` (also on `StatePersistence`) and the
other call sites in `PersistentExecutor` can both reach it via
`self.persistence._append_jsonl(...)`.

Wait — sites 2 and 3 sit inside `PersistentExecutor._handle_event` and write
to a `Path(run_dir)`, not `self.persistence.meta_eval_file`. The helper must
take an explicit `path` argument so all four sites can reuse it.

Helper signature (module-private, no class affinity):

```python
def _append_jsonl(path: Path, entry: dict[str, Any]) -> None:
    """..."""
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
        f.flush()
        os.fsync(f.fileno())
```

Call sites then collapse to one-liners:

```python
# append_event:
_append_jsonl(self.events_file, event)

# _handle_event usage branch:
_append_jsonl(usage_path, entry)

# _handle_event messages branch:
_append_jsonl(messages_path, entry)

# _write_meta_eval_entry:
_append_jsonl(self.persistence.meta_eval_file, entry)
```

Why one helper: removes 4 hand-patched write blocks (MR-6-friendly —
single source of truth for the flush+fsync contract, future readers can't
forget one of the two calls).

## Phase 0: Write Tests (Red)

Tests added to `scripts/tests/test_fsm_persistence.py` inside the existing
`TestStatePersistence` class. Two flavors:

### (a) Mock-based — verify the helpers actually call `flush` + `fsync`

`mock.patch("os.fsync")` plus a `MagicMock`-ish file object lets us assert
call counts without relying on side-effects of real disk I/O.

```python
def test_append_event_flushes_and_fsynces(tmp_loops_dir, monkeypatch):
    """append_event must fsync so SIGKILL preserves the row."""
    fsync_mock = MagicMock()
    monkeypatch.setattr("os.fsync", fsync_mock)
    flush_mock = MagicMock()
    monkeypatch.setattr("scripts.little_loops.fsm.persistence._append_jsonl.__globals__['os'].fsync", fsync_mock)
    # ... use a wrapping context-manager mock to verify f.flush() called
```

Simpler approach: monkeypatch `builtins.open` to return a `MagicMock` whose
`__enter__` yields a mock file with `fileno() -> 7`. Inspect `flush.assert_called_once()`
and `os.fsync.assert_called_once_with(7)`.

Tests cover all four writers:
1. `append_event` → events.jsonl
2. `messages_append` event → messages.jsonl (via `PersistentExecutor._handle_event`)
3. `action_complete` event with `input_tokens` → usage.jsonl (via `PersistentExecutor._handle_event`)
4. `evaluate` event with type `llm_structured` on a meta-loop → meta_eval.jsonl (via `PersistentExecutor._handle_event` → `_write_meta_eval_entry`)

### (b) Partial-trail visibility — open events.jsonl from a separate fd

```python
def test_append_event_visible_to_separate_fd(tmp_loops_dir):
    """A reader opening events.jsonl after append_event sees every event (no kernel-buffer lag)."""
    persistence = StatePersistence(loop_name="x", loops_dir=tmp_loops_dir)
    persistence.initialize()
    for i in range(3):
        persistence.append_event({"event": "loop_start", "i": i})
        # open from outside the persistence object
        with open(persistence.events_file, encoding="utf-8") as f:
            lines = [l for l in f if l.strip()]
            assert len(lines) == i + 1
```

This implicitly verifies the helper's behavior because Python's open sync path
combined with `fsync` on every call guarantees the data lands at the inode
before the file is closed (and thus before the next caller reads it).

Tests verify Red phase by running pytest against the unmodified persistence.py
and asserting they FAIL with the current behavior (no fsync call).

## Phase 1: Implement (Green)

1. Add `_append_jsonl` module-private helper to `persistence.py` (after imports,
   before `LoopState`). Add the inline comment with the SIGKILL rationale.
2. Replace four write blocks with `_append_jsonl(...)` calls.
3. Run pytest on the new tests — confirm Green.
4. Run full `python -m pytest scripts/tests/` — confirm no regressions.

## Phase 2: Verify

```bash
python -m pytest scripts/tests/test_fsm_persistence.py -v   # new + existing
python -m pytest scripts/tests/                              # full suite
ruff check scripts/little_loops/fsm/persistence.py scripts/tests/test_fsm_persistence.py
python -m mypy scripts/little_loops/fsm/persistence.py
```

Success:

- New tests pass.
- Existing `test_append_events`, `test_events_file_is_append_only`, etc. unchanged.
- Full test suite green.
- Lint + type-check clean.

## Performance note

Per-event `os.fsync()` is ~1-10 ms on SSD. `loop_start` is appended once per
run; per-state transitions are append_event + potentially one of {usage,
messages, meta_eval}. In the worst case a 100-iteration loop pays ~1 second
of fsync overhead — acceptable. If profiled impact is worse, escalate to
interval-batched fsync (out of scope here, parent ENH-2514 already tracks
potential follow-ups).

## Risk / rollback

Pure additive: introducing a helper that wraps the existing pattern. Revert
= `git revert` the helper + four call sites. No public signature changes.

## Success criteria

- [ ] `_append_jsonl` helper added with the inline SIGKILL comment.
- [ ] Four write sites reduced to one-line helper calls.
- [ ] Mock-based tests for all four writers pass (flush + fsync called exactly once per call).
- [ ] Partial-trail test passes (separate-fd reader sees every event).
- [ ] Full pytest suite green.
- [ ] ruff + mypy clean.
- [ ] Issue status moved to `done`.
