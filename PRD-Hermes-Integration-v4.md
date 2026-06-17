---
type: project
tags:
  - project/little-loops
  - project/hermes-agent
  - genai/agents
  - status/planning
created: 2025-05-29
updated: 2026-06-16
status: portfolio-pm-model
supersedes: PRD-Hermes-Integration-v3.md
reality_check_date: 2026-06-16
reality_check: "Reviewed against little-loops v1.125.0 (1,785 commits / 45 releases since v3). Extension protocol, 6 transports, 37 event schemas, hooks system, session store, and host adapters all now exist in production — some Phase 1 deliverables are de-risked, others need re-scoping."
---

# PRD: little-loops × Hermes Integration v4

*Hermes is your PM. It holds your portfolio, has opinions, runs your rituals. little-loops is the execution layer. You're the CEO.*

*This is a living document — not complete, not final, but honest about what we know and what we don't. New information has and will revise this document.*

---

## Reality Check (June 16, 2026)

v3 was written May 29 against approximately v1.80. As of v1.125.0:

- **The extension protocol ships.** `LLExtension`, `ExtensionLoader`, `wire_extensions()`, and the `little_loops.extensions` entry point group are production code. This was v3 Phase 1 Step 1 — done.
- **Five transports ship.** `JsonlTransport`, `WebhookTransport`, `SQLiteTransport`, `UnixSocketTransport`, `OTelTransport` — all production (`SQLiteTransport` lives in `session_store.py`, the other four in `transport.py`). v3's "dual sink (JSONL + HTTP webhook)" is mostly built; we need the Hermes-side endpoint.
- **37 event schemas documented.** v3's event catalog was ~15-20 types. The real catalog is 37 types with JSON Schema (draft-07) files. Includes `issue.skipped`, `issue.started`, `learning_*` (6 events), `rate_limit_*` (3 events), `stall_detected`, `max_iterations_summary`, `cycle_detected`, `throttle_*` (3 events) — all added since v3.
- **Hooks system exists.** `LLHookEvent`/`LLHookResult` dataclasses, adapters for Claude Code, OpenCode, Codex CLI. Five hook intents: `session_start`, `pre_compact`, `pre_tool_use`, `post_tool_use`, `session_end`. This is a separate integration surface the PRD didn't know about.
- **Session store (`history.db`) ships.** Per-project SQLite+FTS5 with `loop_events`, `issue_events`, `message_events`, `skill_events`, `user_corrections`, `issue_snapshots`, `sessions`, `cli_events`, `summary_nodes`. Partially overlaps with v3's proposed portfolio model.
- **Loop inheritance ships.** `from:` stubs with `is_runnable_loop()` resolution. `public`/`internal`/`example` visibility tiers. Affects loop discovery.
- **Provider architecture is different.** v3's Option A ("inject `ANTHROPIC_API_KEY`") doesn't match reality. little-loops uses per-state `StateConfig.model` overrides (v1.121.0; the FSM passes `--model` to the host CLI in prompt-mode for that state). No API key injection in the codebase. **GAP:** there is *no* run-level `ll-loop run --model` flag that overrides the host-CLI action model across states — only `--llm-model`, which sets the *evaluator/judge* model. Hermes's `ll_route` provider strategy depends on a run-level flag that does not yet exist (see Enablement Gaps).
- **New subcommands:** `ll-init`, `ll-logs` (eval-export, diff, scan-failures, stats, sequences, telemetry-digest), `ll-harness`, `ll-ctx-stats`, `ll-decision-log`. These are data sources for rituals and portfolio health.

**What still holds:** The three-layer model (CEO → PM → Execution), portfolio state as first-class primitive, read/action tool split, rituals as first-class, and the Phase 2/3 judgment primitives. The architecture was right — little-loops grew into it independently.

---

## The Reframe (unchanged, validated)

v2 framed Hermes as a **translator with dispatch capability**. v3 reframed Hermes as a **stateful collaborator with portfolio awareness.** A real PM holds the backlog across all your projects, prioritizes, pushes back on bad scope, runs weekly rituals, and *initiates*.

**Three-layer model:**

| Layer | Who | Responsibility |
|---|---|---|
| **CEO** | You | Direction, judgment, review. "We're focused on stability this quarter." |
| **PM** | Hermes | Portfolio, prioritization, rituals, opinions. Holds state across all projects. |
| **Execution** | little-loops | FSM loops doing the work. Issue refinement, autodev, sprints, research. |

The integration succeeds when the CEO can run their daily flow at the CEO level — set direction, review results, make calls — and never have to be the PM.

---

## What Changed from v3

| v3 (May 2026) | v4 (June 2026) |
|---|---|
| Build extension protocol from scratch | Build Hermes extension atop shipping `LLExtension` Protocol |
| Build "dual sink" JSONL+webhook transports | Use existing `WebhookTransport`; build Hermes webhook endpoint |
| ~15-20 event types in portfolio model | 37 event types with JSON Schema — fuller signal |
| Portfolio model as only state store | Portfolio model as cross-project layer above per-project `history.db` |
| No mention of hooks system | Hooks as separate integration surface for session lifecycle |
| Provider Option A: inject `ANTHROPIC_API_KEY` | Provider Option A: per-state `model:` overrides + host CLI model flag; no API key injection needed |
| Loop discovery via `ll-loop list` | Loop discovery via `ll-loop list --visibility` (inheritance-aware) |
| Basic SLA/health metrics | Rich event signals: `stall_detected`, `rate_limit_storm`, `throttle_*`, `cycle_detected` |

**What we kept from v3:** The three-layer model. The read/action tool split. Rituals as first-class. PM intelligence primitives (goal elaboration, scope pushback, portfolio prioritization, proactive surfacing). Config schema. Persona file. Success metrics. All still correct.

---

## Architecture

### Extension Surface: Build On, Not Build

The v3 framing of "build the EventBus extension protocol" is obsolete. The protocol exists. The work is building a Hermes-specific `LLExtension` that consumes events and a Transport that delivers them.

**What exists (no Hermes work needed):**

```python
# Already shipping in little-loops
from little_loops.extension import LLExtension, ExtensionLoader, wire_extensions
from little_loops.events import EventBus, LLEvent
from little_loops.transport import WebhookTransport, JsonlTransport, SQLiteTransport
```

**The `LLExtension` Protocol:**

```python
class LLExtension(Protocol):
    event_filter: str | list[str] | None  # e.g. "issue.*", ["loop_start", "loop_complete"]
    def on_event(self, event: LLEvent) -> None: ...
```

Extensions are discovered via:
1. **Entry points:** `little_loops.extensions` group → auto-discovered from installed packages
2. **Config paths:** `extensions.paths: ["my_package.hermes:HermesExtension"]` in `ll-config.json`
3. **Both:** `ExtensionLoader.load_all()` combines both sources

**The Transport Protocol:**

```python
class Transport(Protocol):
    def send(self, event: dict[str, Any]) -> None: ...  # non-blocking
    def close(self) -> None: ...
```

Existing transports include `WebhookTransport` which does batched HTTP POSTs with retry/backoff. The Hermes integration needs a webhook *endpoint* on the Hermes API server — the client-side transport already exists.

**What to build (Hermes side):**

1. **`hermes_little_loops` pip package** — a `LLExtension` implementation that:
   - Subscribes to `issue.*` and FSM lifecycle events
   - On each event, enqueues to a local buffer
   - Flushes batched events to Hermes's API server via HTTP
   - Falls back to JSONL file (`~/.hermes/ll-events.jsonl`) when Hermes is unreachable

2. **Hermes API endpoint** — `POST /hermes/v1/ll-event` accepting batched LLEvent dicts, upserting into the portfolio SQLite store

3. **Dual-sink is automatic** because little-loops already has both transports:
   - `JsonlTransport` → file sink (survives Hermes downtime)
   - `WebhookTransport` → live updates (sub-second when Hermes is running)

### Portfolio Model (cross-project layer)

The portfolio model is still the core primitive. But v4 delineates more carefully between what lives per-project in `history.db` and what lives cross-project in Hermes.

**Per-project (`history.db`) — ships with little-loops:**

- `loop_events` — FSM state transitions, outcomes, model info
- `issue_events` — issue lifecycle (captured, completed, deferred, skipped, started)
- `skill_events` — skill invocation frequency, corrections
- `cli_events` — binary invocations with exit codes
- `issue_snapshots` — point-in-time issue state for trend analysis
- `summary_nodes` / `summary_spans` — compacted session summaries
- `user_corrections` — correction-topic fingerprints with retirement tracking

**Hermes-side (`portfolio.db`) — cross-project aggregation:**

```yaml
portfolio:
  projects:
    - name: little-loops
      path: /Users/brennon/AIProjects/brenentech/little-loops
      registered_at: 2026-05-29
      last_sync: 2026-06-16T12:00:00Z

      # Aggregated from per-project history.db + EventBus
      health:
        score: 0.82
        signal: "green"
        # Derived from: stall_detected, rate_limit_storm, throttle_stop,
        # cycle_detected, retry_exhausted, action_error — all from event stream
        top_concern: null

      activity_7d:
        loops_run: 23
        issues_completed: 8
        issues_deferred: 2
        rate_limits_hit: 1
        stalls_detected: 0
        cycles_detected: 0

      in_flight:
        - loop: autodev
          state: implement
          iteration: 12
          model: claude-sonnet-4-6    # from action_complete.model
          started_at: 2026-06-16T11:00:00Z

      backlog_snapshot:               # from ll-issues list --json
        open: 47
        by_priority: { P0: 2, P1: 8, P2: 15, P3: 22 }
        by_type: { BUG: 12, FEAT: 18, ENH: 15, EPIC: 2 }
        stale_30d: 5
        blocked: 1

      focus:
        theme: "Hermes integration validation"
        active_epic: EPIC-042
```

**Storage:** Hermes-side SQLite. Two tables in Hermes's existing DB:

- `ll_projects` — one row per registered project, JSON column for snapshot
- `ll_events` — append-only event stream from Hermes endpoint, indexed by `(project, event_type, ts)`

**Sync strategy:**

1. **Event-driven** (real-time) — WebhookTransport POSTs events to Hermes endpoint → upsert into portfolio
2. **Polled** (periodic) — every 5 minutes, Hermes runs per-project sync: `ll-issues list --json` (counts), `ll-loop status --json` (in-flight), queries `history.db` for recent activity
3. **On-demand** — `ll_portfolio` triggers sync before returning, ≤30s staleness

**Why Hermes-side + per-project, not just one or the other:** Per-project `history.db` is the durable source of truth — it captures every event whether Hermes is running or not. Hermes-side `portfolio.db` is the cross-project layer — it knows about all projects simultaneously, enables cross-project queries ("which project has the most stalls this week?"), and supports the PM persona's prioritization. Hermes queries the per-project DBs via CLI when it needs details; the Hermes-side store is a cache + aggregation layer.

### Event Catalog (the 37-type reality)

The portfolio model's health signals derive from the full event catalog. Key additions since v3:

**Health-impacting events (new since v3):**

| Event | Health signal |
|---|---|
| `stall_detected` | Loop repeating same state/exit/verdict — stuck |
| `cycle_detected` | Same edge traversed > max — loop level |
| `rate_limit_exhausted` | Retry budget spent across both tiers |
| `rate_limit_storm` | Consecutive exhausted events ≥3 across states |
| `throttle_hard` | Tool-call cap reached → transitioned |
| `throttle_stop` | Tool-call cap reached → hard stop |
| `retry_exhausted` | State retry budget consumed |

**Issue-lifecycle events (new):**

| Event | Significance |
|---|---|
| `issue.skipped` | Filtered out by type/priority — not processed |
| `issue.started` | Undeferred → returned to active — blockage resolved |

**Learning events (new subsystem):**

| Event | Significance |
|---|---|
| `learning_target_proven` | API target verified — learning progressing |
| `learning_target_stale` | Registry missing/stale → explore invoked |
| `learning_complete` | All targets proven for a state |
| `learning_blocked` | Target refuted or retries exhausted |

**Loop execution events (enriched):**

| Event | Significance |
|---|---|
| `action_complete` | Now includes `model`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens` |
| `max_iterations_summary` | Iteration cap fired → summary state about to run |
| `handoff_detected` | Loop requesting fresh session |
| `handoff_spawned` | Child process spun up for continuation |

**Full event reference:** See `little-loops/docs/reference/EVENT-SCHEMA.md` for the authoritative catalog. All 37 event types have JSON Schema (draft-07) files for programmatic validation.

### Hooks System (separate integration surface)

The hooks system is distinct from the EventBus. EventBus = pub/sub for FSM lifecycle events. Hooks = request/response for host agent lifecycle events.

**Relevant hook intents:**

| Intent | What it tells Hermes | Integration value |
|---|---|---|
| `session_start` | Session beginning, merged config available | Know when a coding session starts in a registered project |
| `session_end` | Session ending, stale-ref sweep results | Know when coding work concludes |
| `pre_tool_use` | Tool invocation about to happen (Claude Code active) | Awareness of what the host agent is doing |
| `post_tool_use` | Tool invocation completed, byte metrics available | Track tool usage patterns across sessions |

**Why hooks matter to the PM:** Session boundaries give portfolio context. "Brennon just started a Claude Code session in blender-agents — that project is active." "Post-tool-use metrics show a spike in file writes in the auth module — FYI." These are signals the EventBus doesn't capture because they're about the host agent, not the FSM loop.

**Integration approach:** Phase 1 defers hooks. The EventBus gives us everything we need for portfolio awareness and rituals. Hooks add session-level richness in Phase 2 when the basics are solid.

### Provider Architecture (reality-corrected)

v3's Option A assumed `ANTHROPIC_API_KEY` injection into the subprocess environment before `ll-loop run`. That mechanism doesn't exist in the codebase and there's no sign it's needed.

**What actually works:**

- **Per-state model override (ships):** `StateConfig.model` field (v1.121.0, `fsm/schema.py:453`) — individual FSM states can specify `model: anthropic/claude-sonnet-4-6` and the FSM executor passes `--model <id>` to the host CLI for that state (prompt-mode, `fsm/runners.py`)
- **Global model:** Host CLI's default model (Claude Code picks from its config)
- **Host CLI model flag (GAP — not yet shipped):** `ll-loop run --model <id>` to pass a model through to the host as `--model <id>` does **not** exist today. The only run-level flag is `--llm-model`, which overrides the FSM evaluator/judge model, not the host action model. Building this flag is the keystone enablement issue for `ll_route`.

**Hermes v4 provider strategy:**

1. **Interactive (Phase 1):** Hermes passes `--model` to `ll-loop run` based on persona/user preference. The host CLI handles auth.
2. **Cron (Phase 3):** Per-ritual model selection through the same `--model` flag. Cron safety manifest controls what can run unattended.
3. **Per-state cheap model (Phase 3+):** For loops that self-select cheap models per-state, Hermes doesn't need to do anything — the loop YAML's `model:` fields handle it.

**No API key management needed.** Host CLI auth is already configured by the user. Hermes doesn't touch keys.

---

### PM Persona (unchanged from v3)

The persona is the durable answer to "what kind of PM are you, for which CEO, on which projects?"

**File:** `~/.hermes/pm-persona.yaml`

```yaml
ceo:
  name: Brennon
  voice_style: "terse, declarative, prefers ship velocity over polish"

current_focus:
  quarter: "Q2 2026"
  theme: "Hermes integration validation"
  pinned_projects: [little-loops, hermes-agent]
  deprioritized: [old-blender-stuff]

values:
  - "ship velocity > polish, but never broken main"
  - "extensions are sacred — don't break the API"
  - "tests are a tool, not a religion"
  - "PRs > issues for tracking small work"

defaults:
  goal_specificity: "high"
  scope_pushback: "active"
  surface_threshold: 0.7

projects:
  little-loops:
    focus: "stability and Hermes adoption"
    sensitivity: [docs/ARCHITECTURE.md, .claude/CLAUDE.md, hooks/]
    velocity_target: "5 PRs/week"
    model: "anthropic/claude-sonnet-4-6"     # new in v4
  blender-agents:
    focus: "feature parity with v1"
    model: "anthropic/claude-sonnet-4-6"     # new in v4
```

**New in v4:** Per-project `model:` preference. Hermes passes `--model <value>` when dispatching `ll_route` for that project.

### Loop Discovery (inheritance-aware)

v3 assumed a flat loop catalog. v4 accounts for loop inheritance:

- **`from:` stubs** — non-runnable loop fragments that exist only as inheritance bases. `ll-loop list` hides them by default; `--visibility all` reveals them.
- **Visibility tiers** — `public` (routable), `internal` (sub-loop only), `example` (reference only)
- **Resolution** — `is_runnable_loop()` resolves `from:` chains before deciding routability

The loop-router's dispatch catalog should use `ll-loop list --json --visibility public` to get only routable loops. **GAP — not yet shipped:** `ll-loop list` today exposes `--json`, `--label`, and `--builtin`, but **no `--visibility` flag**. Adding `--visibility public|internal|example` (inheritance-aware, resolving `from:` chains via `is_runnable_loop()`) is an enablement issue.

---

## Tool Surface (v4)

Same read/action split as v3. Updated for CLI reality.

**Read tools** — Hermes reads portfolio/execution state. No loop-router dispatch.

| Tool | Purpose | Impl notes |
|---|---|---|
| `ll_portfolio` | Cross-project state. "What's going on?" → all projects' health + top concerns. Filterable by project, priority, type. | Queries Hermes-side `portfolio.db`; triggers per-project sync if staleness >30s |
| `ll_briefing` | Synthesized digest. "Morning briefing" / "weekly digest" / "what changed since Friday." Format-aware (Telegram-short vs. Discord-long). | Queries portfolio + per-project `history.db` diff since last briefing |
| `ll_status` | Active loops across all projects. "What's running?" → one-line per in-flight dispatch including model, iteration, state. | Aggregates from `ll-loop status --json` per project |
| `ll_events` | Raw event stream, filterable by project, event type, time window. Debugging tool. | Queries Hermes-side `ll_events` table |

**Action tools** — Hermes drives little-loops execution.

| Tool | Purpose | Impl notes |
|---|---|---|
| `ll_route` | Dispatch a goal to the loop-router. Forms goal, selects loop, runs. | Passes `--model <pref>` from persona project config |
| `ll_ritual` | Run a named ritual workflow (Monday planning, weekly review, etc.). Each ritual = read state + dispatch loops + synthesize. | Calls read tools + dispatches `ll_route` as needed |

**Slash commands** (one-shot config ops, no model reasoning needed):

- `/setup` — guided first-run: discover little-loops installation, validate CLI, register projects, install Hermes extension
- `/project <name>` — bind session to a project
- `/persona edit` — open persona file for editing

---

## PM Rituals (unchanged from v3)

Rituals are recurring, structured workflows that mirror how a real PM operates.

**Phase 1 ritual:** `morning-briefing` — weekdays 7am, reads portfolio, reports top 3 concerns, suggests first action.

**Phase 2 rituals:** `monday-planning`, `friday-retro`, `weekly-portfolio-digest` (see v3 for full spec — unchanged).

**Phase 3 rituals:** `midweek-check-in`, `staleness-sweep`, `dependency-audit`, `quarterly-review`, `capacity-planning` (see v3).

**Each ritual** = read portfolio state + dispatch loops as needed + synthesize report + update portfolio. Defined as YAML workflow with `scope: portfolio|project`, ordered steps, template synthesis, and delivery target.

---

## PM Intelligence (unchanged from v3)

Four judgment primitives, ordered by phase:

1. **Goal elaboration** (Phase 1) — Hermes enriches terse user goals with portfolio context: active sprint, dependencies, in-flight conflicts
2. **Scope pushback** (Phase 2) — Hermes challenges questionable scope with concrete portfolio evidence
3. **Portfolio prioritization** (Phase 2) — "What should I work on?" returns ranked, justified list across all projects
4. **Proactive surfacing** (Phase 2) — Without being asked, Hermes surfaces stalled P0s, drifting projects, failed dispatches, rate-limit storms

See v3 for detailed specifications. These are the PM's judgment layer and haven't changed.

---

## little-loops Enablement Gaps (this repo's work)

Most of v4 is split across two repos (see [Repo Architecture](#repo-architecture) below). The little-loops side is a small, well-bounded set of enabling gaps that Hermes depends on. These are the only items that become little-loops issues:

| # | Gap | Verified state | Blocks |
|---|---|---|---|
| EG-1 | **`ll-loop run --model` host-action passthrough** | Absent. Only `--llm-model` (evaluator/judge) and per-state `StateConfig.model` exist. | `ll_route` (Phase 1 #5), per-ritual model selection (Phase 3) |
| EG-2 | **`ll-loop list --visibility public\|internal\|example`** | Absent. `--json`/`--label`/`--builtin` exist; no `--visibility`. | loop-router dispatch catalog (Q5) |
| EG-3 | **`--json` output contract stability** for the surfaces Hermes consumes (`ll-loop list/status`, `ll-issues list`) | All three `--json` outputs exist; no documented stability/version guarantee. | `ll_portfolio`, `ll_status`, polling sync |
| EG-4 | **`session_end` hook handler** | Intent referenced in `hooks/__init__.py`; no handler. Tracked by **FEAT-1680** — link, don't duplicate. | Phase 2 session activity signals |
| EG-5 | **Doc fixes** in `EVENT-SCHEMA.md` / transport docs (count + locations) | "Six transports" → five; `SQLiteTransport` in `session_store.py`. | Accuracy of integration docs |

Already de-risked (no work): `LLExtension`/`ExtensionLoader`/`wire_extensions()`, `little_loops.extensions` entry point, 37 event schemas, `WebhookTransport`+`JsonlTransport`, `ll-loop list/status --json`, `ll-issues list --json`, `--label` cron filter, per-state `StateConfig.model`.

---

## Repo Architecture

The integration splits across two repos following the dependency seam: extension code imports from `little_loops.*` internals, Hermes tools import from Hermes internals. They share no dependencies and have different release cadences.

### Extension: in-tree with little-loops

The `LLExtension` implementation lives in the little-loops source tree as a first-party extension package. It imports `LLExtension`, `EventBus`, and `Transport` from `little_loops.*` — stable public protocols that haven't changed in 45 releases — so coupling risk is low. Co-location means any future API change to those protocols updates the extension atomically in the same commit and CI run. It also signals first-party status: users browsing little-loops docs see the Hermes integration as official, not a third-party bolt-on.

```
little-loops/
├── extensions/hermes/           # first-party extension package
│   ├── pyproject.toml
│   ├── src/little_loops_hermes/
│   │   ├── __init__.py
│   │   ├── extension.py         # LLExtension subclass
│   │   ├── buffer.py            # In-memory event buffer
│   │   └── fallback.py          # JSONL fallback sink
│   └── tests/
├── scripts/little_loops/        # core (extension.py, events.py, transport.py)
└── ...
```

Discovered automatically via `little_loops.extensions` entry point when installed (`pip install -e extensions/hermes` during dev, or shipped as `pip install little-loops[hermes]` via an extras entry in the main `pyproject.toml`).

### Hermes tools: `little-loops-hermes` pip package

Everything that imports from Hermes internals lives in a standalone pip package. This is the codebase that will iterate rapidly as PM intelligence (portfolio prioritization, scope pushback, proactive surfacing) grows across Phases 1-3.

```
little-loops-hermes/
├── pyproject.toml
├── src/little_loops_hermes/
│   ├── __init__.py
│   ├── tools/                   # ll_portfolio, ll_route, ll_briefing, ll_status, ll_events, ll_ritual
│   ├── endpoints/               # POST /hermes/v1/ll-event webhook handler
│   ├── db/                      # Portfolio SQLite schema + queries
│   ├── persona.yaml             # Default persona template
│   └── config.yaml              # Default config fragment
├── commands/                    # /setup, /project, /persona edit slash command definitions
└── tests/
```

Installed as `pip install little-loops-hermes` and registered as a Hermes skill. Consumes `little-loops` CLI for polling sync (`ll-issues list --json`, `ll-loop status --json`). Communicates with the extension via the Hermes webhook endpoint — the extension pushes events to Hermes, never the reverse.

### Why not a single repo

The extension and Hermes tools have different dependency trees, different consumers, and different release cadences. The extension is a thin bridge (~200 lines) that will be dormant once stable. The Hermes tools will iterate rapidly. Separating them keeps each repo's changelog and versioning honest — an extension fix for a little-loops API change doesn't force a Hermes tools release, and a new ritual doesn't force an extension release. The "one install" loss is mitigated by the extension being invisible to end users (auto-discovered via entry point) and the Hermes tools being a single `pip install`.

---

## Implementation Phases (re-anchored for v4)

Phases re-anchored: the infrastructure gap is much smaller than v3 assumed. Phase 1 is integration + wiring, not building from scratch.

### Phase 1: PM with Eyes (Week 1-3)

The PM can see across all your projects in real time.

**Deliverables:**

1. **little-loops extension** (`extensions/hermes/` in-tree) — `LLExtension` subclass registering on `little_loops.extensions` entry point. Subscribes to `issue.*` and FSM lifecycle events. Writes to Hermes webhook endpoint; falls back to JSONL when unreachable.
2. **`little-loops-hermes` pip package** — Hermes tools (`ll_portfolio`, `ll_route`, `ll_briefing`, `ll_status`, `ll_events`, `ll_ritual`), webhook endpoint handler, portfolio SQLite schema, persona template, and slash command definitions. Registered as a Hermes skill.
3. **Hermes webhook endpoint** — `POST /hermes/v1/ll-event` accepting `{"project": "...", "events": [...]}`. Upserts into portfolio SQLite.
4. **Portfolio model** in Hermes SQLite (`ll_projects` + `ll_events` tables). Event-driven updates + 5-minute polling sync + on-demand refresh.
5. **Read tools**: `ll_portfolio`, `ll_briefing` (morning briefing only), `ll_status`, `ll_events`.
6. **Action tool**: `ll_route` — forms goals, dispatches to loop-router. Passes `--model` from persona.
7. **Slash commands**: `/setup`, `/project`, `/persona edit`.
8. **Multi-project config** in `~/.hermes/config.yaml` (`little-loops.projects` map).
9. **Basic persona** — `~/.hermes/pm-persona.yaml` with CEO name, project list, focus, model preferences.

**Phase 1 acceptance:**

- I can ask "what's going on?" and get a useful one-screen answer about all my projects
- New issues created in any project show up in the portfolio within 30s (webhook) or 5min (poll)
- `ll_route` dispatches work, passing appropriate model flags
- A morning briefing fires automatically at 7am with portfolio health
- `/setup` in a new repo registers it and within 30 minutes the portfolio includes it

**Phase 1 explicitly defers:**

- Rituals beyond morning briefing
- Scope pushback / portfolio prioritization
- Proactive nudges
- Hooks integration
- Cron safety manifest
- Multi-step workflows

### Phase 2: PM with Judgment (Week 3-6)

The PM has opinions, runs rituals, and initiates.

**Deliverables:**

1. **Persona richness**: full schema (values, defaults, per-project sensitivities). Conversational update flow.
2. **Rituals**: `monday-planning`, `friday-retro`, `weekly-portfolio-digest`.
3. **Goal elaboration with portfolio awareness** — `ll_route` enriches goals with active sprint, dependencies, in-flight conflicts.
4. **Scope pushback** — Hermes-side classifier flags high-scope, persona drives pushback, response uses portfolio evidence.
5. **Portfolio prioritization** — ranked next-action list with rationale.
6. **Proactive surfacing** — daemon watches portfolio for surface-worthy signals (stale P0s, rate-limit storms, stall_detected), posts via Telegram/Discord subject to throttle.
7. **Judgmental result interpretation** — Hermes interprets dispatch results against persona values.
8. **Hooks integration** — `session_start` and `session_end` hooks inform portfolio activity signals.

### Phase 3: PM with Stamina (Week 6-9)

Unattended execution, multi-day workflows, cross-project coordination.

1. **Cron safety manifest** — `[safe-for-cron]` label work (loop YAML edits + `ll-loop list --label` filter)
2. **Long-running dispatch monitoring** — spawned Hermes pattern for >2h loops
3. **Multi-day workflows** — sprint cycles spanning multiple rituals with shared context
4. **Per-ritual model selection** — cheap model for cron (`--model`), capable for interactive
5. **Cross-project workflows** — `ll_ritual` supports `scope: portfolio` with subagent fan-out
6. **Phase 2 ritual set additions**: `midweek-check-in`, `staleness-sweep`, `dependency-audit`

---

## Config Schema (v4)

```yaml
# ~/.hermes/config.yaml
little-loops:
  projects:
    little-loops:
      path: /Users/brennon/AIProjects/brenentech/little-loops
      pinned: true
      model: "anthropic/claude-sonnet-4-6"      # new in v4
    blender-agents:
      path: /Users/brennon/dev/blender-agents
      model: "anthropic/claude-sonnet-4-6"      # new in v4

  defaults:
    auto: true
    confidence_threshold: 0.7
    command_timeout: 3600

  portfolio:
    poll_interval_seconds: 300
    event_webhook_port: 8421
    on_demand_max_staleness: 30

  rituals:
    morning-briefing:
      cadence: "0 7 * * 1-5"
      delivery: telegram
    monday-planning:
      cadence: "0 8 * * 1"
      delivery: telegram
    friday-retro:
      cadence: "0 17 * * 5"
      delivery: telegram
    weekly-portfolio-digest:
      cadence: "0 20 * * 0"
      delivery: telegram

  surfacing:
    max_per_window: 1
    window_hours: 6
    quiet_hours: "22:00-07:00"

  # Phase 3
  cron_safety:
    defaults:
      auto: true
      confidence_threshold: 0.85
      max_iterations_override: 15
      require_safe_label: true
    allowed_unsafe: []
    deny: [recursive-refine]
```

---

## What v4 Drops from v3

| v3 item | v4 disposition | Why |
|---|---|---|
| "Build EventBus extension protocol" | Removed — already ships in little-loops | Infrastructure exists; v4 builds on top |
| "Dual sink JSONL+webhook from scratch" | Reduced to Hermes endpoint only | `WebhookTransport` + `JsonlTransport` ship; just need the endpoint |
| "Option A: inject ANTHROPIC_API_KEY" | Replaced with `--model` pass-through | Per-state model overrides exist; no key injection needed |
| "15-20 event types for portfolio" | Expanded to 37-type catalog | Reality is richer; portfolio model reflects it |
| `ll_setup` as a tool | `/setup` slash command | Deterministic one-shot, kept from v3 |
| `ll_project_bind` as a tool | `/project <name>` slash command | Deterministic one-shot, kept from v3 |

---

## Open Questions for v4

**Q1: How does the extension get installed?** The extension lives in-tree (`extensions/hermes/`) and ships with little-loops. Installed via `pip install little-loops[hermes]` (extras entry in `pyproject.toml`). The Hermes tools package is a separate `pip install little-loops-hermes`. The `/setup` slash command validates both are installed and configured.

**Q2: Portfolio polling — Hermes cron or in-process thread?** 5-minute polling sync needs to run even when the user isn't chatting. Recommendation: **Hermes cron job** — cron is already robust for this. A dedicated `ll-sync` cron job runs on the polling interval.

**Q3: Hermes webhook endpoint — auth?** Should the webhook endpoint require auth or trust localhost? Recommendation: **localhost-only** for Phase 1. Bind to `127.0.0.1`. For Phase 3+ remote setups, add a shared secret.

**Q4: What happens when a project doesn't have the extension installed?** Portfolio degrades to polling-only (5min latency, lossy between polls). Recommendation: `/setup` validates extension presence per project and nags if missing. Rituals still work; data is just less timely.

**Q5: Loop inheritance — does the router need to understand `from:` stubs?** The router should only dispatch to `public`-visibility, runnable loops. **Correction:** `ll-loop list --json --visibility public` does **not** exist yet — it's an enablement issue (see below). Recommendation: **ship `--visibility` on the little-loops side, then the router uses this flag; no special inheritance logic needed in Hermes.**

**Q6: Persona portability (retained from v3).** Is `pm-persona.yaml` per-user or per-machine? Recommendation: **per-user, `~/.hermes/`, document dotfile-sync recipe.**

**Q7: Multi-CEO (retained from v3).** Single-user in Phase 1-3. Defer to future v5.

**Q8: New — hooks integration sequencing.** When do we wire `session_start`/`session_end` hooks? Recommendation: **Phase 2.** EventBus covers portfolio awareness; hooks add session-level richness that's nice but not essential for Phase 1.

---

## Success Metrics (unchanged from v3)

The integration succeeds when the CEO/PM/Execution model holds in daily use:

- I can run my whole workday at the CEO level without manually tracking project state
- Monday morning, I get a planning proposal across all active projects and edit it instead of writing it
- Hermes notices things I would have missed: stale P0s, drifting projects, failed dispatches I didn't see
- When I propose questionable scope, Hermes pushes back with portfolio evidence and I find the pushback right >75% of the time
- Weekly retro fires unprompted and I find it accurate
- I can install little-loops in a new repo, register it with `/setup`, and within 30 minutes the portfolio includes it with real signal
- Loop-router execution remains invisible — I never type `ll-loop` directly in normal use

Stretch:
- A Hermes user discovers little-loops through this integration and adopts it as their primary execution layer
- I can describe my workday to someone else as "I'm the CEO, Hermes is my PM, little-loops ships the code" and have it actually be true

---

## Related

- [PRD-Hermes-Integration-v3.md](./PRD-Hermes-Integration-v3.md) — superseded; execution-layer details, PM intelligence specifications, and multi-agent patterns carry forward
- [little-loops Extension System](../scripts/little_loops/extension.py) — `LLExtension` Protocol, `ExtensionLoader`, `wire_extensions()`
- [little-loops Transport System](../scripts/little_loops/transport.py) — `WebhookTransport`, `JsonlTransport`, `SQLiteTransport`, `UnixSocketTransport`, `OTelTransport`
- [little-loops Event Schema](../docs/reference/EVENT-SCHEMA.md) — 37 event types with JSON Schema files
- [little-loops Session Store](../scripts/little_loops/session_store.py) — Per-project `history.db` schema
- [little-loops Hooks System](../scripts/little_loops/hooks/) — `LLHookEvent`/`LLHookResult`, host adapters
- [little-loops Host Compatibility](../docs/reference/HOST_COMPATIBILITY.md) — Hook intent parity matrix
- [Loop-Router FSM](scripts/little_loops/loops/loop-router.yaml)
