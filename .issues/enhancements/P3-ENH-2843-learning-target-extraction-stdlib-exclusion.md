---
id: ENH-2843
type: ENH
priority: P3
status: open
captured_at: '2026-07-27T00:43:13Z'
discovered_date: 2026-07-27
discovered_by: capture-issue
relates_to: [ENH-2836, FEAT-1283, ENH-2209]
labels:
- learning-tests
- fsm
- automation
---

# ENH-2843: Widen learning-target extraction exclusion list to cover contract-stable stdlib

## Summary

`extract_learning_targets()` in `scripts/little_loops/learning_tests/extractor.py`
relies solely on LLM prompt wording (`_EXTRACTION_PROMPT`) to decide which names
are "external API surfaces" worth proving via `/ll:explore-api`. The exclusion
clause names only six stdlib modules (`os`, `sys`, `pathlib`, `json`, `re`,
`datetime`), so other contract-stable stdlib modules — `urllib`, `http`,
`socket`, `subprocess`, `csv`, `sqlite3`, `shutil`, `tempfile`, `argparse`,
`logging` — are routinely extracted as learning targets. Each spurious target
costs a full `/ll:explore-api` proving run, and on failure blocks the
learning gate.

Widen the exclusion list, and add a deterministic post-filter so the guarantee
does not depend on the model honouring prose.

## Current Behavior

Running `ll-loop run autodev ENH-2836` on 2026-07-26, JIT extraction returned
`["urllib", "requests"]` for an issue about `ll-check-links` timeout handling:

```
[19:32:04] Learning gate: checking 2 target(s): urllib, requests
[19:32:05] Learning gate blocked ENH-2836: unproven external-API deps
```

`urllib` is stdlib with a contract as stable as `json` or `pathlib` — it is
exactly the class of module the prompt's exclusion clause intends to filter, but
it is not enumerated, so the model kept it.

The prompt's own inclusion clause invites this: *"Non-obvious stdlib components
whose contract is non-trivial (e.g. asyncio, multiprocessing)"*. Without a
concrete boundary the model has to guess where "non-trivial" starts, and it
guesses generously.

Note: in that run the gate blocked for an unrelated reason — the
`type: learning` state dispatched `/ll:explore-api` in shell mode (exit 127),
so the remedy never ran. That dispatch bug is fixed separately
(`_execute_learning_state` in `fsm/executor.py`). With it fixed, over-extraction
no longer causes a spurious deferral — it causes wasted proving runs instead.
That is the cost this issue addresses.

## Expected Behavior

`extract_learning_targets("...urllib...")` returns `[]` (or omits `urllib`)
for contract-stable stdlib modules, regardless of how the LLM responds.
Genuinely non-trivial stdlib (`asyncio`, `multiprocessing`, `concurrent.futures`)
and all third-party/network surfaces (`requests`, `anthropic`, `boto3`) continue
to be extracted.

## Motivation

Every spurious target is one wasted `/ll:explore-api` run per issue that mentions
the module — a full host-CLI invocation, plus a registry record that then goes
stale after `learning_tests.stale_after_days` (30) and gets re-proven. Because
extraction is JIT (no `learning_tests_required` frontmatter), the same module is
re-extracted for every issue that mentions it. `urllib`, `subprocess`, and
`logging` are pervasive in this codebase, so the recurrence rate is high.

Secondarily, it makes the learning gate noisier and less trustworthy: an operator
who sees `checking 2 target(s): urllib, requests` learns to discount the signal.

## Proposed Solution

Two changes, both in `learning_tests/extractor.py`. The post-filter is the load-bearing
one — the prompt edit alone reproduces the current failure mode with a longer list.

### 1. Deterministic post-filter (primary)

Add a module-level frozenset and apply it after JSON parsing in
`extract_learning_targets()`, before the dedup loop:

```python
# Contract-stable stdlib: proving these teaches nothing an implementer does not
# already get from the type stubs. Kept as a deterministic filter rather than
# prompt wording alone, because the LLM cannot be relied on to honour an
# open-ended "contract-stable" judgement (ENH-2843: `urllib` slipped through a
# prompt that already excluded os/sys/pathlib/json/re/datetime).
_STDLIB_EXCLUDED = frozenset({
    "argparse", "collections", "copy", "csv", "dataclasses", "datetime",
    "enum", "functools", "glob", "hashlib", "http", "io", "itertools",
    "json", "logging", "math", "os", "pathlib", "random", "re", "shutil",
    "socket", "sqlite3", "string", "subprocess", "sys", "tempfile",
    "textwrap", "time", "typing", "urllib", "uuid", "warnings",
})
```

Match on the **first dotted component**, lowercased, so `urllib.request` and
`http.client` are both caught, while a phrase target like
`"GitHub API rate limits"` (which contains no dot and no bare match) is not:

```python
for t in raw_targets:
    name = t.strip()
    if not name:
        continue
    if name.split(".", 1)[0].lower() in _STDLIB_EXCLUDED:
        logger.debug("extract_learning_targets: dropped stdlib target %r", name)
        continue
    ...
```

**Deliberately not excluded** (non-trivial contracts worth proving):
`asyncio`, `multiprocessing`, `concurrent.futures`, `threading`, `signal`,
`selectors`, `ctypes`, `ssl`.

### 2. Prompt wording (secondary)

In `_EXTRACTION_PROMPT`, replace the narrow exclusion bullet:

```
- Contract-stable stdlib modules (os, sys, pathlib, json, re, datetime)
```

with one that states the rule and gives a wider sample, so the filter usually
does not have to fire:

```
- Contract-stable stdlib modules — anything in the Python standard library whose
  API is stable and fully described by its type stubs (os, sys, pathlib, json,
  re, datetime, urllib, http, socket, subprocess, csv, sqlite3, logging,
  argparse, shutil, tempfile). Only include stdlib when its *runtime* behavior
  is genuinely non-obvious (asyncio, multiprocessing, concurrent.futures).
```

### Open question for refinement

Should the denylist be config-surfaced (e.g. `learning_tests.excluded_targets`)
so a project can extend it for its own vendored/internal names? Defaulting to a
hardcoded frozenset is simpler and matches how `_EXTRACTION_PROMPT` is already
treated; config-surfacing is the safer long-term shape but adds a config-schema
change. Recommend hardcoded for this issue, config as a follow-up if requested.

## Integration Map

### Files to Modify
- `scripts/little_loops/learning_tests/extractor.py` — `_EXTRACTION_PROMPT`,
  new `_STDLIB_EXCLUDED`, filter inside `extract_learning_targets()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/learning_tests/extractor.py::resolve_learning_targets` —
  the field-first wrapper; unaffected when `learning_tests_required` is set
- `scripts/little_loops/issue_manager.py` (~line 876) — `ll-auto` per-issue gate
- `scripts/little_loops/cli/sprint/run.py` (~line 216) — sprint pre-flight
- `scripts/little_loops/parallel/worker_pool.py` (~line 83) — `ll-parallel` gate

Note the filter must live in `extract_learning_targets()`, not in any one caller
— all three gates share it.

### Similar Patterns
- The stopword denylist in `skills/capture-issue/SKILL.md`'s history-DB keyword
  extraction is the same shape (deterministic filter over LLM/regex output)

### Tests
- `scripts/tests/test_learning_extractor.py` (if present; else the extractor's
  existing test module) — add cases asserting `urllib`, `urllib.request`,
  `subprocess` are dropped and `asyncio`, `requests`, `anthropic` survive
- Cases inject `llm_call` returning a canned `TARGETS_JSON:` line, per the
  existing mock-injection pattern documented in the module docstring

### Documentation
- `docs/reference/API.md` — `little_loops.learning_tests.extractor` entry, if it
  documents the exclusion policy

### Configuration
- N/A unless the open question above is resolved toward `learning_tests.excluded_targets`

## Implementation Steps

1. Add `_STDLIB_EXCLUDED` frozenset with the rationale comment.
2. Apply the first-dotted-component filter in `extract_learning_targets()`'s
   dedup loop; log dropped targets at debug level.
3. Widen the `_EXTRACTION_PROMPT` exclusion bullet.
4. Add unit tests with injected `llm_call` covering: dropped stdlib, dotted
   stdlib, surviving non-trivial stdlib, surviving third-party, phrase targets.
5. Run `python -m pytest scripts/tests/` — full suite must exit 0.

## Impact

- **Scope**: one module, one function; no schema or config change
- **Risk**: low — narrows what reaches the gate, so the failure mode is
  under-proving a module someone considered worth proving. Mitigated by keeping
  `asyncio`/`multiprocessing`/`threading`/`ssl` out of the denylist.
- **Backwards compatibility**: an issue with an explicit
  `learning_tests_required:` frontmatter list bypasses extraction entirely
  (`resolve_learning_targets`'s `is not None` sentinel), so a project that
  deliberately pins `urllib` as a target keeps it.

## Success Metrics

- `extract_learning_targets()` returns no denylisted stdlib name for any input,
  asserted directly in unit tests (not measured via gate-block rate)
- Re-running the ENH-2836 extraction yields `["requests"]`, not
  `["urllib", "requests"]`

## Scope Boundaries

**In scope**: the exclusion list and post-filter in `extractor.py`.

**Out of scope**:
- The `/ll:explore-api` shell-dispatch bug in
  `fsm/executor.py::_execute_learning_state` (fixed separately)
- Whether `requests` should be extracted for a docs-tooling issue — that is a
  correct extraction; the gate proving it is working as designed
- Config-surfacing the denylist (see open question)

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `.claude/CLAUDE.md` | Learning-test registry, `ll-learning-tests` CLI, gate wiring |
| `docs/reference/API.md` | `little_loops.learning_tests` module reference |

## Session Log
- `/ll:capture-issue` - 2026-07-27T00:43:13Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d34e8adf-b030-413f-88bd-1c3c4ef7a366.jsonl`

---

## Status

- **Status**: open
- **Created**: 2026-07-27
