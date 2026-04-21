---
discovered_date: "2026-04-20"
discovered_by: parallel-family-review
depends_on: [FEAT-1075, ENH-1177]
---

# FEAT-1196: Metrics Export for Parallel States (Prometheus / StatsD)

## Summary

Parallel FSM states produce rich timing and outcome data per worker — duration, verdict, terminated-by reason, retry count, worktree acquisition latency — but today this data is only visible in log scrapes or ad-hoc post-run analysis. Add a metrics-export subsystem that emits Prometheus (pull) and StatsD (push) metrics from parallel runs so operators can build dashboards and alerts without parsing logs.

## Current Behavior

None. `ParallelRunner` emits logs and writes results into `captures`, but has no metrics-emitter integration. Observability is log-based and post-hoc.

## Expected Behavior

1. **Metrics surface**: a set of well-known metrics emitted from `ParallelRunner` during fan-out:
   - `ll_parallel_worker_duration_seconds` (histogram, labels: `state`, `verdict`, `terminated_by`)
   - `ll_parallel_worker_count` (counter, labels: `state`, `verdict`)
   - `ll_parallel_state_active_workers` (gauge, labels: `state`)
   - `ll_parallel_state_duration_seconds` (histogram, labels: `state`)
   - `ll_parallel_worker_retries_total` (counter, labels: `state`) — when ENH-1175 lands
   - `ll_parallel_worktree_acquisition_seconds` (histogram) — worktree-mode only
2. **Exporter abstraction**: a minimal `MetricsExporter` protocol with two in-tree implementations:
   - `PrometheusExporter` — bound to a local HTTP server endpoint `/metrics`
   - `StatsDExporter` — configurable host/port, pushes on emit
   - `NullExporter` — default, no-op
3. **Config surface** in `fsm-loop.yaml`:
   ```yaml
   metrics:
     exporter: prometheus | statsd | null
     prometheus:
       bind: "0.0.0.0:9090"
       namespace: "ll"
     statsd:
       host: "statsd.internal"
       port: 8125
       prefix: "ll.parallel"
   ```
4. **No hard dependency** on `prometheus_client` / `statsd` Python packages — exporters load lazily and exporter config is gated behind optional extras (`pip install "little-loops[metrics]"`).

## Use Case

**Who**: A platform engineer running `ll-parallel` in CI or as a long-running orchestrator; needs to alert on worker-error rate or fan-out latency.

**Context**: Currently detecting "parallel states are getting slower" requires diffing log timestamps across runs. A Prometheus histogram lets them alert on `p99(ll_parallel_worker_duration_seconds) > threshold`.

**Outcome**: Dashboards show per-state worker throughput, error rate, and p50/p99 duration. Alerts fire when a long-running orchestrator's parallel state degrades.

## Proposed Solution

1. Define `MetricsExporter` protocol in `scripts/little_loops/observability/metrics.py`.
2. Implement `NullExporter`, `PrometheusExporter`, `StatsDExporter`.
3. Wire the exporter into `ParallelRunner` — preferably through the lifecycle hooks from ENH-1194 (`before_worker` / `after_worker` / `on_worker_error`) so the runner core stays metrics-agnostic.
4. Config loading in `fsm-loop.yaml` schema (FEAT-1074) — add a top-level `metrics:` section, resolve exporter at loop-start.
5. Mark `prometheus_client` and `statsd` as optional extras; raise a clear error if configured but not installed.

## Files to Modify / Create

- `scripts/little_loops/observability/metrics.py` — new module
- `scripts/little_loops/fsm/parallel_runner.py` — wire exporter via ENH-1194 hooks
- `scripts/little_loops/fsm/schema.py` — add `metrics:` config section (or separate ENH to extend the schema)
- `scripts/little_loops/fsm-loop-schema.json` — JSON Schema entry
- `scripts/pyproject.toml` — add `[project.optional-dependencies] metrics = ["prometheus_client", "statsd"]`
- `docs/generalized-fsm-loop.md` — new "Observability / Metrics" chapter
- `scripts/tests/test_metrics_export.py` — exporter behavior tests with fake clock
- `scripts/tests/test_parallel_runner_metrics.py` — integration test: fake exporter sees expected calls during fan-out

## Dependencies

- **Hard blockers**: FEAT-1075 (runner); ENH-1194 (lifecycle hooks — preferred wiring point)
- **Soft**: ENH-1177 (tagged observability — metrics labels should align with log tags)

## Acceptance Criteria

- `MetricsExporter` protocol defined with ≥ 3 concrete implementations (null, prom, statsd)
- `fsm-loop.yaml` can select and configure the exporter
- Six metrics listed above emit from a `ParallelRunner` run
- `prometheus_client` / `statsd` are optional extras — core install has no new runtime dep
- Configuring an exporter without the required extra raises a clear error at loop-start (not mid-run)
- Tests use an in-memory fake exporter to assert emission counts and labels
- Docs cover config surface, metric names, recommended dashboards

## Impact

- **Priority**: P4 — not required for v1 parallel ship. Becomes important as parallel states are adopted in production orchestrators.
- **Effort**: Medium — new subsystem + two exporter impls + schema wiring + docs
- **Risk**: Low — optional feature, null-exporter default
- **Breaking Change**: No — config surface is additive

## Labels

`fsm`, `parallel`, `observability`, `metrics`

## Related / See Also

- **ENH-1194** — lifecycle hooks (preferred wiring point)
- **ENH-1177** — tagged observability (log-side complement to metrics-side)
- **FEAT-1074** — schema (needs `metrics:` section added)

---

## Session Log
- `parallel-family-review` - 2026-04-20T00:00:00Z - Filed as follow-up from parallel-family review. Deferred post-v1; tracked now so it's not forgotten.

---

**Open** | Created: 2026-04-20 | Priority: P4
