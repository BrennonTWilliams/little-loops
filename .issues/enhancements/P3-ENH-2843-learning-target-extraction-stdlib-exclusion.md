---
id: ENH-2843
type: ENH
priority: P3
status: done
captured_at: '2026-07-27T00:43:13Z'
completed_at: '2026-07-27T02:44:16Z'
discovered_date: 2026-07-27
discovered_by: capture-issue
relates_to:
- ENH-2836
- FEAT-1283
- ENH-2209
decision_needed: false
labels:
- learning-tests
- fsm
- automation
confidence_score: 100
outcome_confidence: 95
score_complexity: 24
score_test_coverage: 25
score_ambiguity: 24
score_change_surface: 22
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
so a project can extend it for its own vendored/internal names?

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

> **Selected:** Option A — hardcoded `_STDLIB_EXCLUDED` frozenset in `extractor.py`, matching the local module-constant style and avoiding a config surface with no demonstrated demand.

**Option A**: Hardcoded `_STDLIB_EXCLUDED` frozenset in `extractor.py`, no
config surface. Simpler and matches how `_EXTRACTION_PROMPT` itself is already
treated (module-level constant, not config-driven).

**Option B**: Config-surfaced as `learning_tests.excluded_targets` in
`config-schema.json`, merged with the hardcoded default so a project can
extend it for its own vendored/internal names without a code change. Safer
long-term shape but adds a config-schema change and a merge-precedence
decision (extend vs. replace the default list).

**Recommended**: Option A for this issue, config as a follow-up if requested.

### Decision Rationale

**Selected**: Option A — hardcoded `_STDLIB_EXCLUDED` frozenset, no config surface.

Option A matches `extractor.py`'s own existing style (private module-level
constants like `_TARGETS_JSON_RE`, `_LLM_TIMEOUT_S`) and the broader codebase
convention of hardcoded denylist/allowlist frozensets for filtering automated
extraction/classification output (`text_utils._COMMON_WORDS`,
`file_hints._SECTION_KEYWORDS`, `dependency_mapper._DEPRECATED_RELATIONSHIP_KEYS`).
Option B's mechanism is cheap to replicate — `learning_tests.discoverability.skip_packages`
already implements the identical union-with-hardcoded-default shape in the same
config namespace — but no demand for extending the extraction denylist
specifically has been demonstrated, and the issue's own text already defers
config-surfacing to "a follow-up if requested." Config adds schema, dataclass,
docs, and test surface for a speculative need; a hardcoded constant is the
right size for the problem as stated.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|:-:|:-:|:-:|:-:|:-:|
| A — hardcoded frozenset | 2 | 3 | 3 | 3 | **11/12** |
| B — config-surfaced | 3 | 1 | 2 | 2 | 8/12 |

Key evidence:
- `dependency_mapper.analysis.COMMON_FILES_EXCLUDE` / `config-schema.json:exclude_common_files` shows config-surfacing precedent exists for a similar "filter noise from automated results" case (Option A's one point of friction).
- `learning_tests.discoverability.skip_packages` (`hooks/learning_tests_gate.py:114`, unioned with hardcoded `_BUILTIN_SKIP`) proves Option B's merge mechanism works, but was built to spec for FEAT-1742 — not evolved from a hardcoded start on demonstrated demand.
- No issue, TODO, or user request found asking to extend the extraction denylist specifically.

## Integration Map

### Files to Modify
- `scripts/little_loops/learning_tests/extractor.py` — `_EXTRACTION_PROMPT`,
  new `_STDLIB_EXCLUDED`, filter inside `extract_learning_targets()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/learning_tests/extractor.py::resolve_learning_targets`
  (line 197) — field-first wrapper; falls through to `extract_learning_targets`
  at line 218 whenever `issue.learning_tests_required is None`, so the filter
  applies transitively to its callers too
- `scripts/little_loops/issue_manager.py:875` — `ll-auto` per-issue gate; calls
  `resolve_learning_targets(info)`, not `extract_learning_targets` directly
- `scripts/little_loops/cli/sprint/run.py:204` — sprint pre-flight; also calls
  `resolve_learning_targets(info)`
- `scripts/little_loops/parallel/worker_pool.py:78` — `ll-parallel` gate; the
  only one of the three that calls `extract_learning_targets()` directly

Note the filter must live in `extract_learning_targets()`, not in any one caller
— all three gates share it (two indirectly via `resolve_learning_targets`).

### Similar Patterns
- The stopword denylist in `skills/capture-issue/SKILL.md`'s history-DB keyword
  extraction is the same shape (deterministic filter over LLM/regex output)

### Tests
- `scripts/tests/test_learning_tests_extractor.py` — add cases asserting
  `urllib`, `urllib.request`, `subprocess` are dropped and `asyncio`,
  `requests`, `anthropic` survive
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
- `/ll:manage-issue` - 2026-07-27T02:43:49 - `6b493b2d-7fea-497d-8ece-55071295060a.jsonl`
- `/ll:ready-issue` - 2026-07-27T02:39:21 - `57796255-810f-48df-a3d8-67ff457126fc.jsonl`
- `/ll:confidence-check` - 2026-07-27T02:38:18 - `b2e13cc6-cc6d-4f47-88fc-bdd0ddda72e8.jsonl`
- `/ll:decide-issue` - 2026-07-27T02:36:52 - `75ca6086-ddd3-4d9d-a6f2-a54427eeb19f.jsonl`
- `/ll:refine-issue` - 2026-07-27T02:34:15 - `0682060b-a845-4d3b-9c8c-3152b8a6f3dc.jsonl`
- `/ll:capture-issue` - 2026-07-27T00:43:13Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d34e8adf-b030-413f-88bd-1c3c4ef7a366.jsonl`

---

## Status

- **Status**: done
- **Created**: 2026-07-27
