---
id: ENH-2479
title: "F5 — Streaming-vs-blocking cache-accounting parity trace set"
type: ENH
priority: P2
status: open
captured_at: "2026-07-04T20:05:34Z"
discovered_date: 2026-07-04
discovered_by: capture-issue
parent: EPIC-2456
relates_to: [FEAT-2478]
learning_tests_required: [anthropic]
labels:
  - token-cost
  - testing
  - streaming
  - parity
  - measurement
  - tier-1
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

## Session Log
- `/ll:wire-issue` - 2026-07-05T04:48:27 - `6fd14997-4081-4bdd-9b13-bc7e438a05c9.jsonl`
- `/ll:refine-issue` - 2026-07-05T01:09:15 - `b5376f77-ab19-4ac6-88a0-b8ad4c01a6e9.jsonl`
- `/ll:refine-issue` - 2026-07-05T01:08:51 - `b5376f77-ab19-4ac6-88a0-b8ad4c01a6e9.jsonl`

- `/ll:capture-issue` - 2026-07-04T20:05:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a4ee548-94b7-4694-b8c1-49e3f31cc127.jsonl`
