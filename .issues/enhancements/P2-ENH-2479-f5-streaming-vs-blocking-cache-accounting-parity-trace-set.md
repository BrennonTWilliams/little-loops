---
id: ENH-2479
title: "F5 \u2014 Streaming-vs-blocking cache-accounting parity trace set"
type: ENH
priority: P2
status: open
captured_at: '2026-07-04T20:05:34Z'
discovered_date: 2026-07-04
discovered_by: capture-issue
parent: EPIC-2456
relates_to:
- FEAT-2478
- ENH-2471
blocks:
- FEAT-2478
learning_tests_required:
- anthropic
labels:
- token-cost
- testing
- streaming
- parity
- measurement
- tier-1
confidence_score: 89
outcome_confidence: 80
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 16
score_change_surface: 25
decision_needed: false
---

# ENH-2479: F5 — Streaming-vs-blocking cache-accounting parity trace set

## Summary

Lock a 3-trace set that proves `cache_read_input_tokens` matches between
`client.messages.create()` and `client.messages.stream()` within 0.1%
across three canonical patterns: static-prefix-stable turn 2+, cache-
write-then-read across tool result, tool-result-only cache hit. This is
EPIC-2456 § Children [TBD-7] and partially resolves the EPIC's Open
Question #6 (locked trace sets need owners — this issue owns the
streaming-parity trace set).

## Motivation

When FEAT-2478 emits `gen_ai.usage.*` rows, it has to decide which
client path (`create()` vs `stream()`) is the source of truth. Today
these paths can return `cache_read_input_tokens` with small fractional
drift. Without a locked parity gate, drift accumulates silently until
cost attribution graphs under-report.

This child locks the trace set + fixtures that gate the 0.1% threshold
in `scripts/tests/test_streaming_cache_parity.py`. The traces must be
representative of the patterns hit by production loops so the gate
recovers regressions, not just textbook cases.

## Current Behavior

No locked trace set exists for streaming-vs-blocking parity; any
"match" is measured against moving targets. Future drift in either
client path will silently degrade cost attribution accuracy.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- The four-field capture (`input_tokens`, `output_tokens`,
  `cache_read_input_tokens`, `cache_creation_input_tokens`) already
  exists in `scripts/little_loops/subprocess_utils.py:449-470` (the
  stream-json `result` event parser inside `run_claude_command()`).
  The `TokenUsage` dataclass is at `subprocess_utils.py:44-52` with
  internal names `cache_read_tokens` / `cache_creation_tokens`.
- The internal-vs-canonical rename happens at
  `scripts/little_loops/subprocess_utils.py:462-465`: upstream field
  `cache_read_input_tokens` is renamed to internal `cache_read_tokens`.
  This is the boundary FEAT-2478's `OTelAttributes.from_usage(...)` will
  sit at — the parity fixture must use the **internal** field name to
  stay consistent with the executor aggregation.
- The per-state aggregation that consumes those fields is at
  `scripts/little_loops/fsm/executor.py:1382-1392` (NOT
  `executor.py:1295-1305` as FEAT-2478 cited — that range is
  interceptor `before_route` / `after_route` handling, unrelated to
  tokens). ENH-2479 should not propagate that line error.
- Downstream consumers today: `scripts/little_loops/cli/loop/_helpers.py:1671,1687,1693,1709`
  (per-state cost table), `scripts/little_loops/cli/ctx_stats.py:378,226`
  (cache-hit rate), and `scripts/little_loops/history_reader.py` (cross-run
  rollups). All read the internal `cache_read_tokens` name.
- The `anthropic` Python SDK is **not** invoked anywhere in production
  code today — `grep -r "import anthropic\|from anthropic" scripts/little_loops`
  returns zero hits outside of BUG-2355's prior (removed) call. The
  parity test must run against an externally-installed SDK gated by
  `importlib.util.find_spec("anthropic")`; it cannot exercise the
  production code path until FEAT-2478's F1 prerequisite lands.
- Reference for real-world shape of recorded usage blocks:
  `scripts/little_loops/cli/ctx_stats.py:180-241` (`_compute_cache_rate_from_jsonl`)
  parses `cache_read_input_tokens` from JSONL transcripts — this is the
  closest in-tree precedent for the `usage` payload each fixture turn
  must contain.

## Expected Behavior

A locked 3-trace set with:
- Stable, reproducible token counts (fixtures checked in or
  deterministically rebuildable from recorded host invocations)
- `scripts/tests/test_streaming_cache_parity.py` asserts 0.1%
  parity on each trace
- README/notes describing what each trace covers and how to rebuild

## Proposed Solution

1. **Trace selection** (3 traces):
   - **`trace_a_static_prefix_stable_turn_2`**: Same system + skill
     blocks across 2+ turns; cache_read jumps on turn 2. Verifies the
     prefix-stable case path.
   - **`trace_b_write_then_read_across_tool_result`**: First turn
     writes cache; tool result lands; second turn reads it. Verifies
     the cache hits *across* a tool result, which is the hardest case.
   - **`trace_c_tool_result_only_cache_hit`**: Pure tool-result-only
     cache hit with no system-prefix change.

2. **Fixture format**: recorded host invocations stored under
   `scripts/tests/fixtures/streaming_parity/{trace_a,b,c}/` with
   expected `usage` block per turn in JSON. Fixture loader rebuilds
   the parity assertion from the recorded block.

3. **Test wiring** (`scripts/tests/test_streaming_cache_parity.py`):
   - Parametrize over the 3 fixtures
   - For each, run *both* `messages.create()` and `messages.stream()`;
     diff the `cache_read_input_tokens`; assert diff ≤ 0.1%
   - Skip gracefully when the SDK isn't installed (the `anthropic`
     package install arrives with FEAT-2478's F1 prerequisite; this
     test is gated on `importlib.util.find_spec("anthropic")`)

4. **Recovery**: each trace ships a `rebuild.sh` that re-records from
   scratch if Anthropic ships a meaningfully new SDK version.

## Integration Map

### Files to Modify

- `scripts/tests/test_streaming_cache_parity.py` (new)
- `scripts/tests/fixtures/streaming_parity/trace_a_*/...json` (new
  fixtures)
- `scripts/tests/fixtures/streaming_parity/trace_b_*/...json`
- `scripts/tests/fixtures/streaming_parity/trace_c_*/...json`
- `scripts/tests/fixtures/streaming_parity/{trace,rebuild}.sh` (helpers)

### Dependent Files (Callers/Importers)

- `FEAT-2478` (`observability/tracing.py:StreamingParityChecker`) —
  the production parity check references these fixtures for behavior
  matching

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

The new test file will land in the same tree as the existing fixture
consumers; these are the read-only drift-detection surface the parity
gate protects (NO modifications required from ENH-2479, but the new
test's existence is what gives them drift coverage):

- `scripts/tests/test_usage_journal.py` (whole file) — exercises the
  `executor.py:1382-1392` aggregation block via `action_complete`
  payloads; uses internal `cache_read_tokens` / `cache_creation_tokens`
  field names (the boundary FEAT-2478's `OTelAttributes.from_usage()`
  will sit at).
- `scripts/tests/test_subprocess_utils.py:1552-1625` — verifies the
  upstream `cache_read_input_tokens → cache_read_tokens` rename at
  `subprocess_utils.py:462-465`; the new fixture's `expected.json`
  MUST use the internal name to stay consistent.
- `scripts/tests/test_subprocess_utils.py:1715-1755` — BUG-1897 model
  fallback (`init-event model`); parity fixture must record the same
  model in both `create()` and `stream()` payloads.
- `scripts/tests/test_usage_reporter.py:18-201` — `_print_usage_summary`
  aggregation tests; per-trace `baseline_cost_usd` must match this
  aggregator's per-state order for downstream diff parity.
- `scripts/tests/test_cli_ctx_stats.py:621` — asserts
  `data["cache_read_tokens"] == 500`; fixture shape must round-trip
  through this reader.
- `scripts/tests/test_generate_schemas.py:162-168` — schema assertion
  for `cache_read_tokens` / `cache_creation_tokens`; fixture must not
  regress this.
- `scripts/tests/test_hooks_integration.py:114,333,395,467,769,830,993,
  1060,1242,1262` — recorded-transcript fixtures use upstream
  `cache_read_input_tokens`; the new fixtures live in a separate
  `streaming_parity/` namespace and do NOT collide.
- `scripts/tests/test_subprocess_mocks.py:220` — synthesizes a
  stream-json line with `cache_read_input_tokens`; close-shape
  precedent for the `recorded.jsonl` fixture rows.

### Test Infrastructure Coupling

_Wiring pass added by `/ll:wire-issue`:_

`scripts/pyproject.toml:142-174` declares the pytest runtime the new
test inherits automatically:

- `testpaths = ["tests"]` + `python_files = ["test_*.py"]` — no manual
  registration needed; `test_streaming_cache_parity.py` is auto-
  discovered.
- `addopts = ["--strict-markers", "--strict-config", "--timeout=120",
  "--timeout-method=thread", "-n", "logical"]`:
  - **`--strict-markers`** — the new test MUST NOT introduce new
    pytest markers (no `@pytest.mark.streaming_parity`); use
    `pytest.mark.skipif` with a module-level `_HAS_ANTHROPIC` flag
    (per the Implementation Step 1 below).
  - **`--timeout=120`** — the per-test timeout cap. Live SDK calls
    may exceed this on slow networks. Document any opt-out in the
    test's module docstring; if a single trace takes longer than 120s,
    use `@pytest.mark.timeout(N)` once the marker is declared in
    `pyproject.toml` `[tool.pytest.ini_options].markers`.
  - **`-n logical`** (xdist) — fixture discovery happens in worker-
    local copies; the parametrized fixture-dir enumeration is safe
    because xdist serializes `iterdir()` per worker.
- `markers` list — only `integration`, `slow`, `conformance` are
  declared; do not add new markers without extending this list.
- `[project.optional-dependencies]` (`pyproject.toml:115-122`) —
  declares `[otel]` and `[webhooks]` extras; **no** `[anthropic]`
  extra yet. FEAT-2478 F1 owns adding it. Until then, the test SKIPs
  cleanly via the `_HAS_ANTHROPIC` gate.
- `[tool.hatch.build.targets.wheel] packages = ["little_loops"]` —
  test fixtures under `scripts/tests/fixtures/` are NOT packaged into
  the wheel; no `package-data` declaration needed.

`scripts/tests/conftest.py:442-540` declares autouse session- and
function-scoped fixtures the new test inherits automatically (NO
action required, but flagging so the implementer does not duplicate
or accidentally disable):

- `_isolate_history_db_session` (line 443) — autouse session-scoped
  redirect of `.ll/history.db` to a tmp dir.
- `_isolate_history_db` (line 457) — autouse function-scoped isolation.
- `_guard_real_history_db` (line 475) — autouse session-scoped guard
  preventing accidental opens of production `.ll/history.db`.
- `_restore_cmd_run_env_vars` (line 535) — autouse env-var isolation.
- `load_fixture` (line 59) — returns a `str` only; the new test will
  need to compose `json.loads(load_fixture(...))` or a sibling helper.

### Conftest autouse isolation

_Wiring pass added by `/ll:wire-issue`:_

`scripts/tests/conftest.py:442-540` declares autouse session- and
function-scoped fixtures the new test inherits automatically (NO
action required, but flagging so the implementer does not duplicate
or accidentally disable):

- `_isolate_history_db_session` (line 443) — autouse session-scoped
  redirect of `.ll/history.db` to a tmp dir.
- `_isolate_history_db` (line 457) — autouse function-scoped isolation.
- `_guard_real_history_db` (line 475) — autouse session-scoped guard
  preventing accidental opens of production `.ll/history.db`.
- `_restore_cmd_run_env_vars` (line 535) — autouse env-var isolation.
- `load_fixture` (line 59) — returns a `str` only; the new test will
  need to compose `json.loads(load_fixture(...))` or a sibling helper.

### Coverage-gap anchor

_Wiring pass added by `/ll:wire-issue`:_

The proposed scope is `cache_read_input_tokens` parity only, but the
production aggregation block (`scripts/little_loops/fsm/executor.py:
1382-1392`) and the per-state cost table (`scripts/little_loops/cli/
loop/_helpers.py:1665-1713`) consume **all four** token fields. If
the test only asserts cache_read parity, drift in `input_tokens` /
`output_tokens` / `cache_creation_input_tokens` would silently pass.
**Recommendation:** extend the parity assertion to cover all four
fields with the same 0.1% threshold, OR explicitly document in the
issue why cache_read is the only one in scope (e.g. "the other three
are SDK-stable; only cache_read drifts between `create()` and
`stream()`"). Update Implementation Step 3 to match.

### Similar Patterns

- Existing pytest `parametrize` over fixtures pattern is well-
  established in `scripts/tests/test_fsm_*` — follow it
- The `importlib.util.find_spec("anthropic")` skip pattern is used in
  other SDK-gated tests — confirm before adding

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**SDK-gate skip pattern (most direct precedent)**

`scripts/tests/test_transport.py:35-47` declares module-level
`_HAS_OTEL_SDK = True/False` via `try/except ImportError`, then
applies it with `@pytest.mark.skipif(not _HAS_OTEL_SDK, ...)` at
line 669 (and again at line 840). ENH-2479 should mirror this for
`_HAS_ANTHROPIC` so contributors without the SDK see a clean skip,
not a hard fail.

The exact `importlib.util.find_spec` form the issue cites is used in
`scripts/tests/test_cli_loop_background.py:1250-1258` for asserting a
module is importable. Both idioms (`_HAS_X` flag and `find_spec`) are
correct; combining them as `_HAS_ANTHROPIC = importlib.util.find_spec("anthropic") is not None`
plus the `pytest.mark.skipif` decorator is the cleanest fit.

**Parametrize-over-fixtures patterns**

- `scripts/tests/conformance/test_host_conformance.py:62-68` —
  `@pytest.mark.parametrize("host", list(_HOST_RUNNER_REGISTRY.keys()))`
  with `ids=[p[0] for p in _GOLDEN_PATHS]` — **closest analog** to
  parametrize-over-3-fixtures-with-readable-IDs.
- `scripts/tests/test_review_loop.py:26,96,712` — defines
  `FIXTURES_DIR = Path(__file__).parent / "fixtures" / "fsm"` and
  iterates with a `_load_fixture(name)` helper; canonical "review
  each fixture" pattern.
- `scripts/tests/test_debug_loop_run_synthesis.py:13,33-37` and
  `scripts/tests/test_audit_loop_run_skill.py:15,33-37` — same
  `FIXTURES_DIR + _load_fixture` shape.
- `scripts/tests/test_fsm_schema.py:41-44` — `@pytest.fixture
  def fsm_fixtures() -> Path` pattern that returns the fixtures dir.

**Fixture directory organization (closest precedent)**

`scripts/tests/fixtures/harbor/` with per-task subdirs containing
`task.md` + `expected.json` is the established "recorded host
invocation" layout. ENH-2479's `streaming_parity/trace_{a,b,c}_*/` dirs
should mirror this:

```
fixtures/streaming_parity/
├── README.md                    # trace-set manifest + rebuild instructions
├── trace_a_static_prefix_stable_turn_2/
│   ├── recorded.jsonl           # captured host invocation stream-json
│   └── expected.json            # {"create": {...}, "stream": {...}, "diff_pct": <float>}
├── trace_b_write_then_read_across_tool_result/
│   └── ...
└── trace_c_tool_result_only_cache_hit/
    └── ...
```

Sanity-check precedent:
`scripts/tests/test_benchmark_fragment.py:299-335` (`TestHarborFixtures`)
asserts each task dir has `task.md`; the streaming parity test should
ship an analogous `TestStreamingParityFixtures` that asserts each
trace dir has `recorded.jsonl` and `expected.json`.

**Fixture JSON load helpers (use directly, do not redefine)**

`scripts/tests/conftest.py:41-70` already exposes `fixtures_dir`
(line 42) and `fsm_fixtures` (line 53) plus a `load_fixture(...)`
helper. The new test should consume these directly rather than
re-deriving paths. Add a sibling `streaming_parity_fixtures` fixture
in conftest if needed, or use `fixtures_dir / "streaming_parity"`.

**Sibling precedent — Tier-0 trace set**

`scripts/little_loops/loops/integrate-sdk.yaml` (the only existing
`client.messages.stream(...)` reference in the repo, at line 154 — but
template text only, not executed) and the issue body of
`.issues/enhancements/P2-ENH-2471-tier-0-verification-trace-set-and-hook-regression-test.md:115-129`
(sibling under same EPIC-2456) lay out the trace-set manifest pattern
ENH-2479 should mirror — including the explicit note that **`rebuild.sh`
has no precedent in this repo**; the codebase convention is "rerun the
loop to regenerate." ENH-2479's `rebuild.sh` is the first such helper.

**`usage` payload shape (real-world reference)**

Recorded usage blocks today follow the shape in
`.loops/runs/general-task-20260608T194041/usage.jsonl`:

```json
{"iteration": 1, "state": "define_done", "action_type": "prompt",
 "input_tokens": 3, "output_tokens": 883, "cache_read_tokens": 56828,
 "cache_creation_tokens": 14065, "model": "claude-sonnet-4-6",
 "timestamp": "..."}
```

Each fixture's `expected.json` should mirror this layout per turn, with
both `messages.create()` and `messages.stream()` variants for diff.

**Bug-context precedent for SDK-gated tests**

`.issues/bugs/P2-BUG-2355-learning-gate-direct-anthropic-sdk-crashes-ll-auto-on-non-anthropic-host.md`
established the rule that a direct Anthropic SDK call must tolerate a
non-Anthropic backend. The `pytest.mark.skipif(not _HAS_ANTHROPIC)`
gate ENH-2479 introduces is the correct containment for that concern.

**Coordination requirement with FEAT-2478**

FEAT-2478's production `StreamingParityChecker` in
`scripts/little_loops/observability/tracing.py` (does not exist yet)
will consume the same fixtures per the Integration Map line 102-104.
The fixture JSON format must therefore satisfy both (a) the pytest
parametrize loader (turn-key, diff-ready) and (b) the production
checker (record-keyed, attributable). Land a shared schema doc in
`docs/observability/streaming-parity-traces.md` so both readers agree
on the field names.

**Configuration surface**

- `scripts/pyproject.toml:116-119` declares the `[otel]` extra
  (`opentelemetry-sdk>=1.20.0` + `opentelemetry-exporter-otlp-grpc>=1.20.0`)
  but **no** `[anthropic]` extra yet — FEAT-2478 F1 will add it.
- `scripts/tests/conftest.py:42-56` exposes `fixtures_dir` /
  `fsm_fixtures` helpers; add `streaming_parity_fixtures` if the
  test needs a non-trivial path resolution.
- `scripts/little_loops/config/features.py:786` — `EventsConfig.otel`
  exists; `observability.streaming_parity.check` config key does not
  yet (FEAT-2478 territory).

**Production surface ENH-2479 anchors against (not modifies)**

- `scripts/little_loops/subprocess_utils.py:run_claude_command()`
  lines 450-470 — the four-field token callback that already does the
  `cache_read_input_tokens → cache_read_tokens` rename.
- `scripts/little_loops/fsm/executor.py:1382-1392` — the aggregation
  block whose totals the parity test indirectly validates.
- `scripts/little_loops/cli/loop/_helpers.py:1665-1690` — per-state
  cost table whose drift is what the parity gate prevents.

### Tests

- The test file itself is the deliverable; verifies 3 traces pass
  0.1% parity

### Documentation

- `docs/observability/streaming-parity-traces.md` (new) — describes
  trace A/B/C, what each covers, how to rebuild
- Brief mention in `docs/reference/API.md` `observability/tracing.py`
  docs

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

`docs/observability/` is greenfield today (`Glob "docs/observability/
**"` returns zero results). Three sibling issues reference this
directory as a future landing zone:

- `ENH-2471` (sibling tier-0 trace set) — `docs/observability/
  tier0-traces.md` at line 137; explicitly requires same-PR
  coordination with ENH-2479 at lines 131, 150, 199, 263, 288, 320.
- `ENH-2475` — `docs/observability/des-audit.md` at line 80.
- `FEAT-2478` — `docs/observability/otel-mapping.md` at line 150.

**Required same-PR coordination:** `docs/observability/streaming-
parity-traces.md` SHOULD include a forward-compat note naming these
sibling docs so the next writer finds the conventions. A central
follow-on doc pass will reconcile the ENH-2471 vs ENH-2479 fixture
taxonomies (per ENH-2471:200 "reconcile in a follow-on central doc
pass").

No other doc files (`docs/reference/API.md`, `docs/ARCHITECTURE.md`,
`docs/reference/CONFIGURATION.md`, `docs/reference/loops.md`,
`docs/reference/HOST_COMPATIBILITY.md`, `CHANGELOG.md`, `docs/
index.md`) require modification — those are FEAT-2478-owned or out
of scope for ENH-2479.

### FEAT-2478 coordination schema contract

_Wiring pass added by `/ll:wire-issue`:_

Per FEAT-2478:140-144, the production `StreamingParityChecker` reads
the same fixtures via `importlib.resources`. The shared contract:

- **Path:** `scripts/tests/fixtures/streaming_parity/<trace_dir>/`
  (pytest-side) and the same directory resolved via `importlib.
  resources` from the installed package (FEAT-2478-side). `<trace_
  dir>` is the directory name and serves as the trace ID.
- **Files per trace:** `recorded.jsonl` (one JSONL row per turn
  capturing the host invocation stream-json) + `expected.json`
  (the locked diff target).
- **`expected.json` shape:** `{"create": {...}, "stream": {...},
  "diff_pct": <float>}` per the Integration Map § `expected.json`
  at line 198. Use INTERNAL field names (`cache_read_tokens`,
  `cache_creation_tokens`) to match `subprocess_utils.py:462-465`
  rename boundary; record BOTH the internal-name view (for pytest
  loader) AND the upstream-name view (`cache_read_input_tokens`)
  to satisfy FEAT-2478's reader.
- **Forward-compat:** `schema_version` envelope and `_meta` reserved
  slot should be added to `expected.json` per ENH-2471:187-215's
  "Wiring Pass — forward-compat invariants" so future writers of
  sibling fixtures share a common envelope.

### Configuration

- N/A — fixture-driven; no config schema change

### Configuration

_Wiring pass added by `/ll:wire-issue`:_

`scripts/pyproject.toml:115-122` declares `[otel]` and `[webhooks]`
optional-dependency extras but **no** `[anthropic]` extra. FEAT-2478
F1 owns adding it. Until then, the test SKIPs cleanly via
`_HAS_ANTHROPIC = importlib.util.find_spec("anthropic") is not None`.

`config-schema.json` has no `streaming_parity` or `observability`
key (FEAT-2478-owned). `.ll/ll-config.json` has no `observability`
block (FEAT-2478-owned). `scripts/little_loops/config/features.py:
786` (`EventsConfig.otel`) is the parallel block FEAT-2478 extends
into `ObservabilityConfig`.

`scripts/little_loops/doc_counts.py:26-31` enumerates
`COUNT_TARGETS` for `commands/`, `agents/`, `skills/`, and
`scripts/little_loops/loops`; the new `scripts/tests/fixtures/
streaming_parity/` dir is NOT counted, so no `doc_counts` reference
is needed.

## Implementation Steps

1. Pick initial 3 traces (owner's pick; mine from any
   `claude -p` runs against `general-task` or `deep-research` that hit
   the 3 patterns)
2. Record host invocations + token counts into fixtures
3. Author `test_streaming_cache_parity.py` parametrized over the 3
   fixtures
4. Skip gracefully when `anthropic` is not installed
5. Document trace A/B/C in
   `docs/observability/streaming-parity-traces.md`
6. Verify `python -m pytest scripts/tests/test_streaming_cache_parity.py
   -v` passes
7. Coordinate with FEAT-2478: same fixtures used by production
   `StreamingParityChecker` for runtime verification

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The above steps should land in this concrete order with these
file/anchor references:

1. **Author the SDK-gate prelude** (copy the `_HAS_OTEL_SDK` shape
   from `scripts/tests/test_transport.py:35-47`):
   ```python
   import importlib.util
   _HAS_ANTHROPIC = importlib.util.find_spec("anthropic") is not None
   pytestmark = pytest.mark.skipif(
       not _HAS_ANTHROPIC, reason="anthropic SDK not installed"
   )
   ```
   Module-level `pytestmark` (Pattern B in pattern-finder output) keeps
   the gate uniform across all 3 parametrized cases.

2. **Pick initial 3 traces** from real `claude -p` runs. Mine the
   `usage.jsonl` output (e.g.
   `.loops/runs/general-task-20260608T194041/usage.jsonl`) for
   representative turns; the trace names align with the patterns in
   `subprocess_utils.py:449-470`'s captured `usage` block.

3. **Author the fixtures** in
   `scripts/tests/fixtures/streaming_parity/{trace_a,b,c}_*/`, each
   with `recorded.jsonl` + `expected.json` (per the harbor pattern
   in `scripts/tests/fixtures/harbor/task_0{1,2,3}/`). Land a
   `README.md` alongside that documents the trace-set manifest
   (mirror the manifest shape from
   `.issues/enhancements/P2-ENH-2471-tier-0-verification-trace-set-and-hook-regression-test.md:150-172`).

4. **Parametrize the test** using
   `scripts/tests/conformance/test_host_conformance.py:62-68` as the
   template:
   ```python
   FIXTURES_DIR = Path(__file__).parent / "fixtures" / "streaming_parity"
   TRACE_DIRS = sorted(p for p in FIXTURES_DIR.iterdir() if p.is_dir())

   @pytest.mark.parametrize("trace_dir", TRACE_DIRS,
                            ids=[p.name for p in TRACE_DIRS])
   def test_streaming_vs_blocking_cache_parity(trace_dir: Path) -> None:
       ...
   ```
   For each trace, load `recorded.jsonl`, replay through both
   `anthropic.Anthropic().messages.create(...)` and
   `anthropic.Anthropic().messages.stream(...)`, diff
   `cache_read_input_tokens` against `expected.json`'s recorded
   values, assert diff ≤ 0.1%.

5. **Sanity-check the fixture set** with a
   `TestStreamingParityFixtures` class modeled on
   `scripts/tests/test_benchmark_fragment.py:299-335` (`TestHarborFixtures`)
   — assert the dir exists, exactly 3 trace subdirs exist, and each
   has both `recorded.jsonl` and `expected.json`.

6. **Document trace A/B/C** in
   `docs/observability/streaming-parity-traces.md`. The new
   `docs/observability/` dir is greenfield; create it. Mirror the
   rebuild-instructions format from the harbor `README.md`.

7. **Verify the test gate**:
   ```bash
   python -m pytest scripts/tests/test_streaming_cache_parity.py -v
   python -m pytest scripts/tests/                       # full suite, must exit 0
   ```

8. **Coordinate fixture schema with FEAT-2478** — confirm the
   `expected.json` shape satisfies both the pytest loader
   (turn-key, diff-ready) and FEAT-2478's
   `observability/tracing.py:StreamingParityChecker.diff(...)` (record-
   keyed, attributable). Document the shared schema in
   `docs/observability/streaming-parity-traces.md`.

### Wiring Phase (added by `/ll:wire-issue`)

_Concrete touchpoints identified by wiring analysis. Each is grounded
in a specific file path + line number from the agent research. Append
these to the Implementation Steps above:_

9. **Use INTERNAL field names in `expected.json`** — record
   `cache_read_tokens` / `cache_creation_tokens` (per
   `scripts/little_loops/subprocess_utils.py:462-465` rename
   boundary) so the pytest loader stays consistent with
   `scripts/tests/test_subprocess_utils.py:1623-1624` and
   `scripts/tests/test_cli_ctx_stats.py:621`. Optionally also
   record the upstream `cache_read_input_tokens` view for
   FEAT-2478's reader.

10. **Document the `expected.json` schema for FEAT-2478 in
    `docs/observability/streaming-parity-traces.md`** — include
    the shared-schema contract from the "FEAT-2478 coordination
    schema contract" subsection above. Add a forward-compat note
    naming `docs/observability/tier0-traces.md` (ENH-2471
    sibling), `docs/observability/des-audit.md` (ENH-2475), and
    `docs/observability/otel-mapping.md` (FEAT-2478).

11. **Land `docs/observability/streaming-parity-traces.md` in the
    same PR as ENH-2471's `docs/observability/tier0-traces.md`**
    (per ENH-2471:131, 150, 199, 263, 288, 320 explicit
    coordination). Both issues create `docs/observability/` for
    the first time — two competing "first commit" claims should
    resolve into one shared landing PR.

12. **Document the `rebuild.sh` contract in `README.md`** —
    `rebuild.sh` is the **first such helper in the entire repo**
    (verified via `Glob '**/rebuild.sh'` returning zero results);
    explicitly document when to re-run, what changes between
    runs, and the SDK-version trigger so future contributors
    have a reference.

13. **Decide on parity-scope coverage** — Implementation Step 4
    currently asserts 0.1% parity on `cache_read_input_tokens`
    only. Per the "Coverage-gap anchor" finding in the wiring
    additions, decide: (a) extend to all 4 token fields
    (`input_tokens`, `output_tokens`, `cache_read_input_tokens`,
    `cache_creation_input_tokens`) since
    `scripts/little_loops/fsm/executor.py:1382-1392` aggregates
    all four; OR (b) explicitly document why cache_read is the
    only one in scope. Update Implementation Step 4 to match.

14. **Respect `--timeout=120`** (`pyproject.toml:153`) — the
    per-test timeout cap. Live SDK calls may exceed it on slow
    networks. Document any opt-out in the test's module
    docstring; if a single trace takes longer than 120s, opt
    out by extending the `markers` list with a `streaming_
    parity` marker and using `@pytest.mark.timeout(N)`. If 120s
    is sufficient (recommended; SDK calls are normally < 60s),
    document this in the test's module docstring.

15. **Do NOT disable conftest autouse isolation** — the new
    test inherits `_isolate_history_db_session`,
    `_isolate_history_db`, `_guard_real_history_db`, and
    `_restore_cmd_run_env_vars` from `scripts/tests/conftest.py:
    442-540`. These are required to prevent the test from
    accidentally writing to production `.ll/history.db` or
    polluting env vars across tests. No conftest edit needed;
    just don't override them.

16. **No new pytest markers** — `pyproject.toml:147-149` lists
    `integration`, `slow`, `conformance`. The new test should
    rely on `pytest.mark.skipif` with `_HAS_ANTHROPIC` (per
    Implementation Step 1); do NOT add `@pytest.mark.
    streaming_parity` without also extending the `markers`
    list in `pyproject.toml`.

## Decisions Locked — 2026-07-08 (post-`/ll:refine-issue`)

_Added by `/ll:refine-issue` on 2026-07-08 — locks the four open
architectural decisions surfaced by the Drift Audit (Sections B4,
C1, C3, and Implementation Step 13). Additive only; the prior
text above is preserved verbatim and remains accurate as a
historical record of the option space._

### Decision 1 — Parity scope: all four token fields (Implementation Step 13)

The 0.1% parity assertion covers **all four token fields**
(`input_tokens`, `output_tokens`, `cache_read_input_tokens`,
`cache_creation_input_tokens`), not `cache_read` only.

**Rationale (locked, do not re-debate during implementation):**
the production aggregation at `scripts/little_loops/fsm/executor.py:
1462-1474` sums all four fields into `usage.jsonl`, and three
independent downstream consumers read them with no
reconciliation layer:

1. `scripts/little_loops/fsm/persistence.py:710-727` — writer
2. `scripts/little_loops/fsm/cost_graph.py:184-254`
   (`CostReport.from_usage_jsonl(...)`) — reader
3. `scripts/little_loops/cli/loop/_helpers.py:1699-1702` → `:1742`
   (`_print_usage_summary`) — CLI table aggregator

A `cache_read`-only gate would silently pass drift in three of
the four fields the executor aggregates. The fixture's
`expected.jsonl` rows (Decision 2 below) carry all four fields
per turn, and the parity assertion is
`abs(create.{f} - stream.{f}) / max(stream.{f}, 1) <= 0.001`
applied to each of the four fields independently.

### Decision 2 — Fixture shape: `expected.jsonl` (Drift Audit C1)

The per-trace expected file is **`expected.jsonl`**, one row per
turn, structurally parallel to `recorded.jsonl`. The original
`Implementation Step 9` phrase ("`expected.json` as a single dict
keyed by `create` / `stream` / `diff_pct`") is superseded.

**`expected.jsonl` row schema (locked):**
```json
{"turn": 1, "model": "claude-sonnet-4-6",
 "create": {"input_tokens": ..., "output_tokens": ...,
            "cache_read_input_tokens": ...,
            "cache_creation_input_tokens": ...},
 "stream": {...},
 "phase": "write_then_read_across_tool",
 "diff_pct": <float>}
```

**`recorded.jsonl` row shape (locked):** the raw upstream
stream-json events verbatim — first row is
`{"type": "system", "subtype": "init", "model": "...}"`,
subsequent rows are
`{"type": "result", "model": "...", "usage": {...}}`. Per
Drift Audit C2, the init→result model-fallback chain must be
preserved so `scripts/tests/test_subprocess_utils.py:1715-1762`
(BUG-1897) keeps its coverage surface intact.

### Decision 3 — Test strategy: recorded-diff, no live SDK at test time (Drift Audit C3)

The test is a **recorded-diff** assertion, NOT a live-replay
test. The phrase "for each, run *both* `messages.create()` and
`messages.stream()`" in Implementation Step 4 is superseded.

**Mechanism:** `recorded.jsonl` and `expected.jsonl` are
**frozen at recording time** from real `claude -p` runs (or
equivalent). Test runtime only loads both JSONL files via
`Path.read_text().splitlines()` + `json.loads` per line and
asserts the per-field diff (Decision 1). No `anthropic` import
is required at test time — the only effect of
`_HAS_ANTHROPIC = importlib.util.find_spec("anthropic") is not None`
is to gate `rebuild.sh` execution; the test itself runs
unconditionally under `python -m pytest scripts/tests/`.

**Implications:**
- CI runs the test without `ANTHROPIC_API_KEY` set.
- Drift detection works against frozen baselines; fixture
  baseline updates flow through `rebuild.sh` as an explicit
  opt-in, not a silent rerun.
- The `--timeout=120` cap (`pyproject.toml:174`) is not at risk
  from network variance on fixture loading — only from
  `rebuild.sh` execution, which is a maintainer-time concern.
- The fixture format intentionally mirrors a real recorded
  `usage.jsonl` row shape (per
  `.loops/runs/rn-implement-20260608T220935/usage.jsonl` — see
  Drift Audit C5: simultaneous `cache_read + cache_creation`
  when prefix is pre-warmed; the fixture must reflect this).

### Decision 4 — Fixture packaging: wheel-side mirror (Drift Audit B4)

FEAT-2478's production `StreamingParityChecker` ships its own
copy of the fixtures under
`scripts/little_loops/observability/fixtures/streaming_parity/`
(wheel-packagable via `[tool.hatch.build.targets.wheel]`).
ENH-2479 ships its pytest-side copy under
`scripts/tests/fixtures/streaming_parity/`. The two are kept in
sync via `rebuild.sh`, which regenerates both directories from
the same captured run.

**Coordination contract with FEAT-2478 (now locked):**
- **Pytest side:** `scripts/tests/fixtures/streaming_parity/<trace_dir>/{recorded.jsonl,expected.jsonl}`
- **Wheel side:** `scripts/little_loops/observability/fixtures/streaming_parity/<trace_dir>/{recorded.jsonl,expected.jsonl}`
  (FEAT-2478 owns adding `package_data` declarations if not
  picked up by default `little_loops/**` packaging — `[tool.hatch.build.targets.wheel] packages = ["little_loops"]`
  auto-picks `little_loops/observability/fixtures/` once the
  file lands.)
- **Trace IDs:** `<trace_dir>` names are the canonical IDs
  (`trace_a_static_prefix_stable_turn_2`,
  `trace_b_write_then_read_across_tool_result`,
  `trace_c_tool_result_only_cache_hit`); both copies must use
  the same names.
- **Drift alert:** both copies carry a `schema_version`
  envelope (per ENH-2471:187-215 forward-compat invariants); a
  `_meta` reserved slot is reserved for future per-trace
  metadata. Mismatched schema_version between the two copies is
  a coordination break.

This supersedes the prior "FEAT-2478 coordination schema
contract" subsection above (which described an `importlib.
resources`-from-pytest-side single-copy approach that Drift
Audit B4 correctly identified as structurally impossible).

### Residual execution-task TBDs (not blocking)

These remain in Implementation Steps 1 and 12 as before; they
are execution tasks, not architectural decisions, so
`decision_needed: false` stands.

- **Trace selection owner pick** (Step 1): the implementer
  picks the specific `claude -p` runs to capture from
  `.loops/runs/*/usage.jsonl`. The three trace patterns are
  named; the specific recordings are TBD.
- **`rebuild.sh` canonical content** (Step 12): the helper's
  exact contents are TBD; the convention "no precedent in repo,
  document when to re-run + SDK-version trigger" is locked.

## Acceptance Criteria

- 3 fixtures in `scripts/tests/fixtures/streaming_parity/`
- `test_streaming_cache_parity.py` parametrize-over-fixtures, asserts
  0.1% diff per trace
- Skip when `anthropic` SDK is not installed (no hard-fail for
  contributors without the SDK)
- Each fixture has a `rebuild.sh` that records fresh tokens after SDK
  upgrade
- Trace docs in `docs/observability/streaming-parity-traces.md`
- `python -m pytest scripts/tests/` exits 0

## Scope Boundaries

- **In**: 3 locked fixtures + parity test
- **Out**: Production parity check itself (FEAT-2478); OTel emission
  (FEAT-2478); `anthropic` SDK install (lands with F1)

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `.issues/epics/P2-EPIC-2456-token-cost-reduction.md` | Parent; § Tier 1 [TBD-7], Open Question #6 |
| `FEAT-2478` | Consumer of these fixtures in production `StreamingParityChecker` |
| `scripts/tests/test_fsm_*.py` | Established parametrize-over-fixture pattern |

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

| Document | Why Relevant |
|----------|--------------|
| `.issues/enhancements/P2-ENH-2471-tier-0-verification-trace-set-and-hook-regression-test.md` | Sibling trace-set precedent under EPIC-2456; lays out trace manifest + `rebuild.sh` discussion at lines 115-129 |
| `.issues/bugs/P2-BUG-2355-learning-gate-direct-anthropic-sdk-crashes-ll-auto-on-non-anthropic-host.md` | Bug precedent that established "direct Anthropic SDK must tolerate non-Anthropic backend"; ENH-2479's `_HAS_ANTHROPIC` gate contains this concern |
| `.issues/enhancements/P3-ENH-1797-cost-token-telemetry-per-state.md` | Already-shipped row layout (`cache_read_tokens` / `cache_creation_tokens`) at `fsm/executor.py:1382-1392` |
| `scripts/little_loops/subprocess_utils.py:449-470` | The four-field capture path; rename boundary at lines 462-465 |
| `scripts/little_loops/fsm/executor.py:1382-1392` | Aggregation block whose totals the parity gate indirectly validates (correct line range — FEAT-2478 mis-cited 1295-1305) |
| `scripts/little_loops/cli/loop/_helpers.py:1665-1690` | Per-state cost table consumer; drift here is what the parity gate prevents |
| `scripts/little_loops/transport.py:338-484` | `OTelTransport` wiring where `gen_ai.usage.*` will be emitted (FEAT-2478 territory) |
| `scripts/tests/test_transport.py:35-47,669` | Canonical `_HAS_*` SDK-gate skip pattern — copy verbatim |
| `scripts/tests/test_cli_loop_background.py:1250-1258` | Existing `importlib.util.find_spec` usage |
| `scripts/tests/conformance/test_host_conformance.py:62-68` | Closest analog for `parametrize` + `ids=` over a fixture list |
| `scripts/tests/fixtures/harbor/` | Per-task subdir fixture layout (closest precedent for `streaming_parity/trace_*/`) |
| `scripts/tests/test_benchmark_fragment.py:299-335` | `TestHarborFixtures` sanity-check class — model for a `TestStreamingParityFixtures` |
| `scripts/tests/conftest.py:41-70` | `fixtures_dir` + `load_fixture` helpers; use directly, do not redefine |
| `.loops/runs/general-task-20260608T194041/usage.jsonl` | Real-world recorded-usage shape; each fixture `expected.json` should mirror this layout per turn |
| `scripts/little_loops/loops/integrate-sdk.yaml:154` | Only existing `client.messages.stream(...)` reference (template text only) — informs the SDK-install prerequisite |

## Impact

- **Priority**: P2 — gates the credibility of F5's streaming-vs-blocking
  parity metric
- **Effort**: Small — 3 fixture recordings + 1 parametrized test
- **Risk**: Low — test-only; production parity check is FEAT-2478
- **Breaking Change**: No — tests are additive; no runtime behavior
  changes

## Status

**Open** | Created: 2026-07-04 | Priority: P2

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-08_

**Readiness Score**: 82/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 74/100 → MODERATE

### Concerns
- **Open parity-scope decision** (Implementation Step 13): the test asserts 0.1% parity on `cache_read_input_tokens` only, but `scripts/little_loops/fsm/executor.py:1382-1392` aggregates all four token fields (`input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`). Drift in the other three would silently pass this gate. The implementation must either extend the assertion to all four fields or explicitly document why cache_read is the only in-scope field. Resolve before recording fixtures (cost-of-change is much lower on paper than on locked traces).
- **Trace selection deferred to "owner's pick"** (Implementation Step 1): the 3 trace patterns are named, but the specific `claude -p` runs that will be recorded into fixtures are TBD. Pick them up-front (any `general-task` or `deep-research` loop run that hits the 3 patterns) — the `usage.jsonl` rows in `.loops/runs/` are the canonical source.
- **Same-PR coordination with ENH-2471**: both ENH-2471 and ENH-2479 create `docs/observability/` for the first time. Per ENH-2471:131,150,199,263,288,320, land `docs/observability/streaming-parity-traces.md` in the same PR as `docs/observability/tier0-traces.md` to avoid two competing "first commit" claims. Coordinate at PR time.
- **`rebuild.sh` is the first in the repo** (verified `Glob '**/rebuild.sh'` returns zero results): explicitly document when to re-run, what changes between runs, and the SDK-version trigger so future contributors have a reference precedent.

### Outcome Risk Factors
- **Open decision on parity-scope coverage**: Implementation Step 13's "decide: (a) extend to all 4 token fields OR (b) explicitly document why cache_read is the only one in scope" is unresolved; locking the wrong scope means re-recording fixtures or shipping a gate that misses drift in 3 of the 4 fields the executor aggregates. Resolve before recording fixtures (cost-of-change is much lower on paper than on locked traces).
- **Trace selection is "owner's pick" with no recorded exemplar**: Implementation Step 1 leaves which specific `claude -p` runs to record entirely to the implementer; if the picked traces don't hit all 3 patterns robustly (especially the cache-hit-across-tool-result case), the gate recovers regressions poorly and re-recording is expensive.

## Session Log
- `/ll:refine-issue` - 2026-07-08T16:52:59 - `28b992b1-e4e9-4155-a8ba-e57b7494e278.jsonl`
- `/ll:decide-issue` - 2026-07-08T16:21:07 - `8d696055-7781-45b9-8bd6-a1d624496851.jsonl`
- `/ll:refine-issue` - 2026-07-08T16:12:12 - `578de1eb-3694-416c-86d4-15ce68048d56.jsonl`
- `/ll:confidence-check` - 2026-07-08T20:00:00 - `21c4ca12-8459-4830-980d-9c6b48436021.jsonl`
- `/ll:wire-issue` - 2026-07-05T04:48:27 - `6fd14997-4081-4bdd-9b13-bc7e438a05c9.jsonl`
- `/ll:refine-issue` - 2026-07-05T01:09:15 - `b5376f77-ab19-4ac6-88a0-b8ad4c01a6e9.jsonl`
- `/ll:refine-issue` - 2026-07-05T01:08:51 - `b5376f77-ab19-4ac6-88a0-b8ad4c01a6e9.jsonl`

- `/ll:capture-issue` - 2026-07-04T20:05:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a4ee548-94b7-4694-b8c1-49e3f31cc127.jsonl`
- `/ll:refine-issue` - 2026-07-08T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/refine-enh-2479-2026-07-08.jsonl`

## Drift Audit — Anchor Corrections & Net-New Findings (2026-07-08)

_Added by `/ll:refine-issue` on 2026-07-08 — additive-only gap audit; older Codebase Research Findings remain valid as historical record, but the cited line ranges below have drifted since prior refinement passes. Per the gap-analysis contract, no prior content is removed; this block documents drift for the implementer._

### A. Drifted Anchor References (line-range corrections)

| # | Section citing anchor | Cited range | Actual on disk | Notes |
|---|----------------------|-------------|----------------|-------|
| A1 | Current Behavior / Integration Map | `scripts/little_loops/fsm/executor.py:1382-1392` (per-state token aggregation) | `scripts/little_loops/fsm/executor.py:1462-1474` | Lines 1382-1392 are the ENH-2486 prompt-size guard, not the aggregation. The aggregation block is `total_input = sum(u.input_tokens for u in result.usage_events)` → `payload["cache_read_tokens"] = total_cache_read` at lines 1463-1473. The earlier "NOT 1295-1305" call-out (rate-limit detection, still correct) is preserved. **Use 1462-1474, not 1382-1392.** |
| A2 | Integration Map | `scripts/little_loops/cli/loop/_helpers.py:1665-1713` (per-state cost table) | Call site at `_helpers.py:1699-1702` (`_print_usage_summary(...)`); function definition at `_helpers.py:1742` | Lines 1665-1713 are mostly the failure-reason printer + completion prefix block. The actual cost-table call is at 1699-1702 and the table aggregator (`_print_usage_summary`) is defined at 1742. ENH-2471:264, 421 cite the same range (1652-1714) with the same drift. |
| A3 | Current Behavior / code shape | `scripts/tests/test_cli_loop_background.py:1250-1258` (find_spec) | `scripts/tests/test_cli_loop_background.py:1353-1361` (`test_main_module_is_importable`) | Lines 1250-1258 are `test_status_without_pid_file` (no find_spec / importlib). The actual `importlib.util.find_spec(...)` usage is at line 1357. |
| A4 | Integration Map / Similar Patterns | `scripts/tests/conftest.py:41-70` (fixtures_dir, fsm_fixtures, load_fixture) | `scripts/tests/conftest.py:131-160` | Lines 41-70 contain `pytest_xdist_auto_num_workers` (31-53) and `pytest_configure` (56-onward). The fixture helpers are at: `fixtures_dir` (131-134), `issue_fixtures` (137-140), `fsm_fixtures` (143-146), `load_fixture` (149-159). **The new test must use 131-160, not 41-70.** |
| A5 | Implementation Step 15 | `scripts/tests/conftest.py:442-540` autouse block (`_isolate_history_db_session`, `_isolate_history_db`, `_guard_real_history_db`, `_restore_cmd_run_env_vars`) | Partially correct | The autouse session/function-scoped isolation fixtures DO live in roughly 532-561 (`_isolate_history_db_session` at 532, `_isolate_history_db` at 546). **`_guard_real_history_db` and `_restore_cmd_run_env_vars` are NOT in conftest.py** — those names were invented in earlier refinement passes and do not exist on disk. The real autouse isolation fixtures need to be re-verified before Implementation Step 15 lands. |
| A6 | Current Behavior (line 87) | `scripts/little_loops/cli/ctx_stats.py:378,226` (cache-hit rate readers) | Both anchors wrong | Line 226 is `_load_fallback_state` (a JSON loader, not a cache reader). Line 378 is `rate = round(100 * corr / inv) if inv > 0 else 0` inside `_render_skill_stats_section` (skill-correction rate, NOT cache rate). The actual `_compute_cache_rate_from_jsonl` is at lines 180-241 as cited; the additional 226 / 378 anchors are stale and should be ignored. |
| A7 | Current Behavior (line 88) | `scripts/little_loops/history_reader.py` (cross-run rollups of `cache_read_tokens` / `cache_creation_tokens`) | Not currently a consumer | `history_reader.py` exposes session-store dataclasses (UserCorrection, FileEvent, IssueEvent, SkillEvent, CommitEvent, RunEvent, SessionRef, SummaryNode, GrepResult, etc.) for `SELECT` queries. It does **NOT** consume `cache_read_tokens`, `cache_creation_tokens`, or the `usage_event` table today. Per the file's own docstring, ENH-2461 is the planned work that materializes the `usage_event` table. The "all read the internal `cache_read_tokens` name" claim from prior passes is unsupported by the file. |
| A8 | Similar Patterns | `scripts/tests/fixtures/harbor/task_0{1,2,3}/` (per-task fixture directories) | Missing on disk | `scripts/tests/fixtures/harbor/` contains only `README.md` today; the `task_01/`, `task_02/`, `task_03/` subdirs are absent. **`TestHarborFixtures` (`scripts/tests/test_benchmark_fragment.py:299-335`) is currently failing on disk** — it asserts `len(task_dirs) == 3` and `(d / "task.md").exists()`. The cited class shape is still a valid code template, but the runtime precedent is broken. ENH-2479's new test should be self-contained (`streaming_parity/trace_a_*/...`) and not depend on the harbor fixture layer. |

### B. Net-New Concept Findings (post-2026-07-05)

#### B1. `docs/observability/` is NO LONGER greenfield

`docs/observability/des-audit.md` already exists, auto-generated by `ll-verify-des-audit` on **2026-07-07** with 65 DES variants (ENH-2475 territory). The earlier "greenfield" framing from refinement passes on 2026-07-05 is now stale — same-PR coordination still applies (with ENH-2518 + ENH-2475), but the framing should shift from "first commit creates the directory" to "second hand-authored doc joins `des-audit.md`." ENH-2479's `streaming-parity-traces.md` will land after ENH-2518's `tier0-traces.md` (per the ordering on 2026-07-08).

#### B2. `.ll/learning-tests/anthropic.md` is PROVEN (not pending)

Per the `ll-history-context` output on 2026-07-08: the anthropic SDK target has a **proven** Learning Test record dated 2026-07-07 (status: proven, 5/0/1 pass/fail/untested). The earlier claim that "`anthropic` Python SDK is not invoked anywhere in production code today" remains true for **production code** (`scripts/little_loops/`), but the test-side gate has changed:

- The `anthropic` package is **already installed** in this dev environment.
- `_HAS_ANTHROPIC = importlib.util.find_spec("anthropic") is not None` evaluates to `True` on this machine.
- The `pytest.mark.skipif(not _HAS_ANTHROPIC, ...)` gate would NOT skip on this machine — the test would actually run.
- The test fixture can therefore be written and exercised today; FEAT-2478 F1 (which adds `[anthropic]` to `pyproject.toml`'s optional extras) is only required for contributors without the SDK.

This means Implementation Step 1's framing — "the `anthropic` package install arrives with FEAT-2478's F1 prerequisite; this test is gated on `importlib.util.find_spec("anthropic")`" — should be updated to: "the test is gated on `_HAS_ANTHROPIC`; with the SDK already installed on the maintainer's machine, contributors without it see a clean `SKIPPED` not a `FAILED`."

#### B3. `cost_graph.py` is a THIRD independent consumer of the four-token shape

Prior refinement passes identified two consumers of `cache_read_tokens` / `cache_creation_tokens`: (a) `fsm/persistence.py:710-727` writes `usage.jsonl`; (b) `OTelTransport` (`scripts/little_loops/transport.py:338-484`) emits `gen_ai.usage.*` (FEAT-2478). A third consumer exists: **`scripts/little_loops/fsm/cost_graph.py:184-254`** (`CostReport.from_usage_jsonl(...)`) reads the same `usage.jsonl` format and renders it into a cost graph (used by `ll-loop` and `ll-auto` dashboards, lines 84-138). Drift in any of the four fields would affect all three consumers. The implementation must therefore consider all three downstream readers when designing the `expected.jsonl` schema.

#### B4. `pyproject.toml:129-131` wheel excludes test fixtures → FEAT-2478's "production reads same fixtures" is structurally false

Per the analyzer: `[tool.hatch.build.targets.wheel] packages = ["little_loops"]` (line 129-131) only packages `little_loops/**`, NOT `scripts/tests/fixtures/`. The proposed path `scripts/tests/fixtures/streaming_parity/<trace_dir>/` is therefore unreachable from an installed wheel via `importlib.resources`. This means FEAT-2478's planned production `StreamingParityChecker` (which the issue cites as consuming the same fixtures) **cannot** read pytest-side fixtures when running against an installed distribution. Either:

1. FEAT-2478 ships its own fixtures under `scripts/little_loops/observability/fixtures/streaming_parity/` (wheel-packagable), OR
2. The parity-checker contract is satisfied only by running tests in a dev checkout, not from the wheel, OR
3. ENH-2479 ships dual fixtures: pytest-side (`tests/fixtures/`) AND a wheel-side copy via `package_data` extension.

This is now a **cross-issue coordination blocker** between ENH-2479 and FEAT-2478 and should be resolved by the `/ll:wire-issue FEAT-2478` pass. Implementation Step 7 ("Coordinate fixture schema with FEAT-2478") should be expanded to pick one of the three options.

#### B5. `pyproject.toml:183` has a 4th marker `no_parallel`

The issue cites `markers` as listing only `integration`, `slow`, `conformance` — but `pyproject.toml:183` now declares `no_parallel` as well. Implementation Step 16's "no new pytest markers" rule should be updated to: "do NOT add new markers beyond the 4 declared in `pyproject.toml:183` (integration, slow, conformance, no_parallel)." If a streaming-parity test ever needs to opt out of xdist (because of fixture-discovery race in workers), the existing `no_parallel` marker is the correct path — declare it once at `pyproject.toml:183` and apply `@pytest.mark.no_parallel` per test.

#### B6. `scripts/tests/test_transport.py:840` has a second `_HAS_*` skipif precedent

The issue cites only `_HAS_OTEL_SDK` (line 35-47, applied at line 669 for `TestOTelTransport`). The same file also declares `_HAS_HTTPX` at lines 35-37 and applies it at line 840 for `TestWebhookTransport`. The dual-flag pattern (`_HAS_OTEL_SDK` + `_HAS_HTTPX` in the same module) is direct precedent for ENH-2479 adding `_HAS_ANTHROPIC` alongside any other future SDK flags. The combined idiom (`try/except ImportError` → boolean → `@pytest.mark.skipif(not _HAS_X)` at class level) is established; `_HAS_HTTPX` at line 840 confirms it generalizes cleanly.

#### B7. `ENH-2518` supersedes `ENH-2471` as the current sibling

A new sibling issue **`P2-ENH-2518-lock-tier-0-verification-trace-set.md`** now covers the tier-0 trace set work originally scoped under ENH-2471. References to ENH-2471 in this issue (line 357, 699-702, 444-448, 622-623) should be updated to ENH-2518 where the cross-issue coordination is current. ENH-2471 remains a historical reference but is no longer the active sibling for tier-0 trace-set work.

#### B8. `pyproject.toml` extras — `[anthropic]` should NOT be bundled into `[dev]`

The implementation's `_HAS_ANTHROPIC` gate only works correctly if the `[anthropic]` extra stays OPT-IN. If FEAT-2478 F1 bundles it into `[dev]` (which is what every developer installs), the gate becomes always-True and contributors without an Anthropic API key would see real SDK errors instead of clean skips. ENH-2479's coordinate-with-FEAT-2478 step should include this constraint: keep `[anthropic]` as a separate `[anthropic]` extra, not in `[dev]`.

### C. Implementation Step Refinements (additive — preserve existing steps)

#### C1. Replace `expected.json` with `expected.jsonl` (per-turn row parallelism)

**Current Implementation Step 9** says: `expected.json: {"create": {...}, "stream": {...}, "diff_pct": <float>}` as a single dict.

**Refinement**: rename to **`expected.jsonl`** with one row per turn (parallel to `recorded.jsonl`), each row shaped as:
```json
{"turn": 1, "model": "claude-sonnet-4-6", "create": {"input_tokens": ..., "output_tokens": ..., "cache_read_input_tokens": ..., "cache_creation_input_tokens": ...}, "stream": {...}, "diff_pct": <float>}
```
This keeps the recorded/expected files structurally parallel (one row per turn, JSONL throughout) and avoids the awkward "one giant dict keyed by turn" structure. The Implementation Step 5 parameter loader does not need to change — `Path.read_text().splitlines()` + per-line `json.loads` is the obvious helper.

#### C2. Include both `init` AND `result` events in `recorded.jsonl`

The parser at `scripts/little_loops/subprocess_utils.py:449-470` reads `event.get("model", detected_model)` where `detected_model` is captured from a prior `{"type": "system", "subtype": "init", "model": ...}` event (lines 428-430). `model` is a sibling of `usage` in the `result` event, NOT a child. Recording only `result` events would lose the init→result model-fallback chain that `test_subprocess_utils.py:1715-1762` (BUG-1897) exercises. Each turn's `recorded.jsonl` should include:
- Line 1: `{"type": "system", "subtype": "init", "model": "claude-sonnet-4-6"}` (once per session)
- Line 2+: `{"type": "result", "model": "...", "usage": {...}}` (once per turn)

#### C3. Adopt a recorded-diff testing strategy, not a live-replay strategy

**Current Implementation Step 4** says: "for each, run *both* `messages.create()` and `messages.stream()`; diff the `cache_read_input_tokens`; assert diff ≤ 0.1%."

**Refinement**: This phrasing implies live SDK calls at test time, but per the analyzer, that has three problems:
1. **Requires an API key** — `anthropic.Anthropic(api_key=...)` needs `ANTHROPIC_API_KEY` to succeed; without it, the SDK fails.
2. **Non-deterministic** — live SDK calls produce drift (network latency, model version) that exceeds 0.1% trivially.
3. **Exceeds `--timeout=120`** — even mocked SDK calls may exceed the per-test cap.

**Adopt a recorded-diff strategy instead**: `recorded.jsonl` holds the captured upstream `result` events (per-trace, multi-turn, frozen verbatim from real `claude -p` runs); `expected.jsonl` holds the same payload as observed through both `messages.create()` and `messages.stream()` AT RECORDING TIME (frozen). Test runtime only loads both and asserts `abs(create.cache_read - stream.cache_read) / max(stream.cache_read, 1) <= 0.001`. No SDK import needed at test time — `_HAS_ANTHROPIC` only needs to be True at recording time, not at test time. The harness-loop rerun path (`recorded.jsonl` regenerated + `expected.jsonl` regenerated together via `rebuild.sh`) ensures the captured diff stays current as the SDK evolves.

This shifts `_HAS_ANTHROPIC` from a test-time gate to a recording-time gate; the test itself does NOT need the SDK installed and can run in CI without the SDK.

#### C4. Note: production code does NOT distinguish write vs read semantics

The 3 trace patterns (write→read on turn 2, cache hit across tool result, tool-result-only cache hit) are properties of the **upstream SDK response** — the production parser (`subprocess_utils.py:449-470`) is purely additive and forwards all four fields without semantic interpretation. The aggregation block (`fsm/executor.py:1462-1474`) is a flat sum. The fixtures must therefore encode the write→read transition *themselves* via the per-turn row sequence, not via any production-side flag. The `expected.jsonl` should carry an optional `phase` field per row (`"write"`, `"read"`, `"write_then_read_across_tool"`, `"tool_result_only_hit"`) to document the intended semantic of each row at recording time, even though production ignores it.

#### C5. Real-world data: simultaneous `cache_read + cache_creation` when prefix is pre-warmed

From `.loops/runs/rn-implement-20260608T220935/usage.jsonl` (the cleanest real-world exemplar with 15+ rows), the first row has both `cache_read_tokens=56828` AND `cache_creation_tokens=14065` non-zero. This is because the system+skill block has been cache-warmed by a PRIOR session, so the system block is `cache_read` while the user-message/iteration-suffix is `cache_creation`. Pure "first turn: write only, zero reads" is not the canonical pattern in practice — pre-warmed prefixes dominate. **Trace A's `expected.jsonl` row 1 should reflect this dual-write behavior** (cache_read > 0 AND cache_creation > 0 on turn 1), not the textbook single-write.

### D. Genuinely New Patterns (no precedent in repo)

The pattern-finder confirmed that the proposed test combines four patterns that DO NOT exist anywhere else in `scripts/tests/`:

1. **Module-level `pytestmark = pytest.mark.skipif(...)`** — all existing `_HAS_X` skips are at class level (`test_transport.py:669, 840`). The module-level form proposed in Implementation Step 1 is the first.
2. **`_HAS_X = importlib.util.find_spec(...)`** — no existing test uses `find_spec` for an SDK-gate skip; only `try/except ImportError` is used (`test_transport.py:35-47`). The combined form is new.
3. **Per-trace `recorded.jsonl` fixture under `scripts/tests/fixtures/`** — `Glob "scripts/tests/fixtures/**/*.jsonl"` returns zero. The recorded-JSONL fixture is new.
4. **Live SDK-recorded-and-replayed parity test** — no existing test invokes a real SDK to record token counts then asserts parity. All host-invocation tests are mock-based.

The implementation is therefore a **first-of-its-kind** test pattern in this repo. Document this in the test's module docstring as "first streaming-parity test in this repo; no in-tree precedent for live SDK + recorded-fixture diff gating."

### E. Pre-Flight Coordination Required Before Implementation

Before Implementation Step 1 lands, three open questions need resolution (per the prior `/ll:confidence-check` notes, but re-scoped after drift audit):

1. **Fixture wheel-packaging** (B4 above) — choose one of the three options for FEAT-2478's `StreamingParityChecker` to share fixtures.
2. **Parity scope** (Implementation Step 13) — extend to all 4 token fields, or document why `cache_read` is the only in-scope field.
3. **`[anthropic]` opt-in** (B8 above) — confirm FEAT-2478 F1 ships as a separate optional extra, not bundled into `[dev]`.

These three resolutions should happen BEFORE recording fixtures (cost-of-change is much lower on paper than on locked traces).

### F. Files Referenced (with corrected line ranges)

- `/Users/brennon/AIProjects/brenentech/little-loops/scripts/little_loops/subprocess_utils.py` (lines 44-52 TokenUsage, 313-317 on_usage 2-tuple back-compat, 328-499 run_claude_command streaming loop, 426 json.loads per line, 428-433 init-event model capture, 434-447 assistant text extraction, **449-470 result-event token callback with rename boundary 462-467**)
- `/Users/brennon/AIProjects/brenentech/little-loops/scripts/little_loops/fsm/executor.py` (lines **1462-1474** token aggregation block — CORRECTED from 1382-1392)
- `/Users/brennon/AIProjects/brenentech/little-loops/scripts/little_loops/fsm/persistence.py` (lines 710-727 `_handle_event` writes usage.jsonl)
- `/Users/brennon/AIProjects/brenentech/little-loops/scripts/little_loops/fsm/cost_graph.py` (lines 84-102 table_row, 124-138 table, **184-254 from_usage_jsonl** — third consumer of the four-token shape)
- `/Users/brennon/AIProjects/brenentech/little-loops/scripts/little_loops/cli/loop/_helpers.py` (lines **1699-1702** cost-table call, **1742** _print_usage_summary definition — CORRECTED from 1665-1713)
- `/Users/brennon/AIProjects/brenentech/little-loops/scripts/little_loops/cli/ctx_stats.py` (lines 180-241 _compute_cache_rate_from_jsonl — parses a DIFFERENT raw session JSONL with upstream field names)
- `/Users/brennon/AIProjects/brenentech/little-loops/scripts/little_loops/transport.py` (lines 338-484 OTelTransport — FEAT-2478 owns adding `gen_ai.usage.*` emission)
- `/Users/brennon/AIProjects/brenentech/little-loops/.ll/learning-tests/anthropic.md` (PROVEN 2026-07-07 — SDK is installed)
- `/Users/brennon/AIProjects/brenentech/little-loops/docs/observability/des-audit.md` (auto-generated 2026-07-07, 65 DES variants — second doc in directory)
- `/Users/brennon/AIProjects/brenentech/little-loops/.issues/enhancements/P2-ENH-2518-lock-tier-0-verification-trace-set.md` (current sibling under EPIC-2456, supersedes ENH-2471)
- `/Users/brennon/AIProjects/brenentech/little-loops/.loops/runs/rn-implement-20260608T220935/usage.jsonl` (15+ row multi-state exemplar with simultaneous cache_read + cache_creation when prefix pre-warmed — closest real-world shape)
- `/Users/brennon/AIProjects/brenentech/little-loops/.loops/runs/deep-research-20260604T111729/usage.jsonl` (10-row pure cache-read steady-state exemplar)
- `/Users/brennon/AIProjects/brenentech/little-loops/scripts/tests/test_transport.py` (lines 35-47 _HAS_HTTPX + _HAS_OTEL_SDK flags, **840** second skipif precedent, 669 OTel skip)
- `/Users/brennon/AIProjects/brenentech/little-loops/scripts/tests/test_subprocess_utils.py` (1552-1625 on_usage + on_usage_detailed tests, 1715-1762 BUG-1897 init-event model-fallback tests)
- `/Users/brennon/AIProjects/brenentech/little-loops/scripts/tests/test_subprocess_mocks.py` (lines 216-260 — synthesized stream-json events)
- `/Users/brennon/AIProjects/brenentech/little-loops/scripts/tests/test_init_core.py` (lines 2536-2547 — `@pytest.mark.parametrize("filename", LIST)` precedent, JSON read inside test)
- `/Users/brennon/AIProjects/brenentech/little-loops/scripts/tests/conftest.py` (lines **131-160** fixture helpers — CORRECTED from 41-70; **532-561** autouse isolation — `_guard_real_history_db` and `_restore_cmd_run_env_vars` are NOT in conftest)
- `/Users/brennon/AIProjects/brenentech/little-loops/scripts/tests/conftest.py:1357` (only existing `importlib.util.find_spec` use — for asserting module importability, not skip-gating)
- `/Users/brennon/AIProjects/brenentech/little-loops/scripts/tests/test_benchmark_fragment.py` (lines 299-335 `TestHarborFixtures` — sanity-check class shape still valid; the class itself is failing on disk because harbor task subdirs are missing)
- `/Users/brennon/AIProjects/brenentech/little-loops/scripts/tests/conformance/test_host_conformance.py` (lines 62-68 `parametrize("host", ...)` + `parametrize("golden_path", ...)` + `ids=[...]`)
- `/Users/brennon/AIProjects/brenentech/little-loops/scripts/tests/fixtures/harbor/` (currently contains only `README.md`; `task_0{1,2,3}/` subdirs missing)
- `/Users/brennon/AIProjects/brenentech/little-loops/scripts/pyproject.toml` (lines 103-127 optional extras including `[otel]` + `[webhooks]` but no `[anthropic]` yet, 129-131 wheel excludes test fixtures, **147-184** addopts with `--timeout=120`, `--strict-markers`, `-n logical`, **markers** now lists `integration`, `slow`, `conformance`, **`no_parallel`** — 4 markers, not 3)
- `/Users/brennon/AIProjects/brenentech/little-loops/scripts/little_loops/host_runner.py` (resolve_host + build_streaming abstraction)
- `/Users/brennon/AIProjects/brenentech/little-loops/.issues/bugs/P2-BUG-2355-learning-gate-direct-anthropic-sdk-crashes-ll-auto-on-non-anthropic-host.md` (precedent: "direct Anthropic SDK must tolerate non-Anthropic backend"; ENH-2479's `_HAS_ANTHROPIC` gate contains this concern)
- `/Users/brennon/AIProjects/brenentech/little-loops/.issues/features/P2-FEAT-2478-f5-otel-gen-ai-usage-emission-des-schema-uuid-and-streaming-parity.md` (production consumer; needs to coordinate fixture wheel-packaging decision)

### Drift Audit Corrections (Verified 2026-07-08)

_Added by `/ll:decide-issue` Phase 2.5 auto-recovery (via `/ll:refine-issue` parallel research). Additive only; supersedes nothing above._

- **Drift Audit A8 is incorrect**: `scripts/tests/fixtures/harbor/task_0{1,2,3}/` subdirs DO exist on disk. The locator confirmed: `task_01/{task.md, expected.json}`, `task_02/{task.md, expected.json}`, `task_03/{task.md, expected.json}` are present (each with shape `{"score": float, "criteria": [str]}` per `fixtures/harbor/README.md:1-21`). `TestHarborFixtures` at `scripts/tests/test_benchmark_fragment.py:299-335` therefore IS passing on disk. The harbor precedent is intact and usable as the fixture-subdir template for `streaming_parity/trace_*/`.
- **Drift Audit A3 confirmed**: `importlib.util.find_spec` is exclusively at `scripts/tests/test_cli_loop_background.py:1357` (verified `Grep "find_spec" scripts/tests` returns only one match). `conftest.py` is 665 lines and contains no `find_spec`. The drift audit's citation at `conftest.py:1357` is wrong but the substantive correction (use the `try/except ImportError` shape from `test_transport.py:35-47` for the `_HAS_ANTHROPIC` gate) stands.
- **`scripts/tests/fixtures/streaming_parity/` is greenfield**: confirmed `Glob "scripts/tests/fixtures/**/*.jsonl"` returns zero results — the proposed `recorded.jsonl` + `expected.jsonl` pair would be the first JSONL fixtures under `scripts/tests/fixtures/`. Drift Audit Section D claim is accurate.
- **No live `messages.create`/`messages.stream` runtime tests exist**: confirmed `Grep "messages\.create|messages\.stream" scripts/tests` returns zero matches. Drift Audit Section D claim is accurate.
- **`anthropic` SDK importability verified**: `importlib.util.find_spec("anthropic")` returns a non-None spec on this machine (consistent with `.ll/learning-tests/anthropic.md` proven status 2026-07-07, 5/0/1). The `_HAS_ANTHROPIC` gate would NOT skip here; contributors without the SDK see clean SKIPPED.
- **`scripts/little_loops/observability/` exists but is partial**: contains `__init__.py`, `audit.py`, `schema.py` (ENH-2475 DES registry). `tracing.py` (FEAT-2478 territory) does not yet exist.
- **Three independent downstream consumers of `usage.jsonl` confirmed by analyzer**:
  - `scripts/little_loops/fsm/persistence.py:710-727` — writer (one JSONL row per `action_complete`)
  - `scripts/little_loops/fsm/cost_graph.py:184-254` — `CostReport.from_usage_jsonl(...)` reader (per-state table + run totals via `_compute_totals` at 257-269)
  - `scripts/little_loops/cli/loop/_helpers.py:1699-1702` call site → `_print_usage_summary` definition at `:1742` (CLI-rendered table via `cost_graph`)
  - Drift in `cache_read_tokens` propagates to all three with no reconciliation layer in between.
- **A fourth parallel consumer reads UPSTREAM names from a DIFFERENT raw JSONL**: `scripts/little_loops/cli/ctx_stats.py:236-308` (`_compute_cache_rate_from_jsonl`) reads raw session transcript JSONL with `cache_read_input_tokens` / `cache_creation_input_tokens` (not internal names) — deliberately bypasses the rename boundary at `subprocess_utils.py:462-465` because it reads raw transcripts.
- **`OTelTransport` (FEAT-2478 territory) currently ignores token fields**: `scripts/little_loops/transport.py:457-460` (`_handle_action_complete`) just calls `self._action_span.end()` — does NOT read `payload["cache_read_tokens"]` or any of the four token fields. No `gen_ai.usage.*` attribute emission today.
- **`_OTEL_EVENT_TYPES` frozenset at `scripts/little_loops/transport.py:330-334` does NOT include `action_complete`** — that event type routes to `_handle_action_complete` directly. FEAT-2478 will need to either extend `_OTEL_EVENT_TYPES` or extract fields inside `_handle_action_complete`.
