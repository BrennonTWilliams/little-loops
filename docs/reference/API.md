# API Reference

This document provides the public API for the little-loops Python package.

> **Related Documentation:**
> - [Architecture Overview](../ARCHITECTURE.md) - System design and diagrams
> - [Troubleshooting](../development/TROUBLESHOOTING.md) - Common issues and diagnostic commands
> - [README](../../README.md) - Installation and quick start

## Installation

```bash
# End users
pip install little-loops

# Contributors (editable install with test dependencies)
pip install -e "./scripts[dev]"
```

## Module Overview

| Module | Purpose |
|--------|---------|
| `little_loops.config` | Configuration management |
| `little_loops.issue_parser` | Issue file parsing |
| `little_loops.issue_discovery` | Issue discovery and deduplication |
| `little_loops.issue_manager` | Sequential automation |
| `little_loops.issue_lifecycle` | Issue lifecycle operations |
| `little_loops.issue_history` | Issue history and statistics |
| `little_loops.git_operations` | Git utilities |
| `little_loops.dependency_graph` | Dependency graph construction |
| `little_loops.dependency_mapper` | Cross-issue dependency discovery and mapping (sub-package: `models`, `analysis`, `formatting`, `operations`) |
| `little_loops.work_verification` | Verification helpers |
| `little_loops.context_window` | Model→context-window size mapping (`context_window_for()`) |
| `little_loops.subprocess_utils` | Subprocess handling |
| `little_loops.host_runner` | Host-agnostic CLI invocation layer (`HostRunner` Protocol + `ClaudeCodeRunner` + `CodexRunner` + `GeminiRunner` + `OmpRunner` + `OpenCodeRunner` + `PiRunner`) |
| `little_loops.adapters` | Host-parameterised emitter layer (`HostEmitter` Protocol + `resolve_emitter` registry factory) — `CodexEmitter` and `GeminiEmitter` fully implemented (FEAT-2391/2392) |
| `little_loops.state` | State persistence |
| `little_loops.events` | Structured events and EventBus dispatcher |
| `little_loops.hooks` | Host-agnostic hook intent dispatcher and built-in handlers |
| `little_loops.extension` | Extension protocol, loader, and reference implementation |
| `little_loops.testing` | Offline test harness (LLTestBus) for extension development |
| `little_loops.logger` | Logging utilities |
| `little_loops.logo` | CLI logo display |
| `little_loops.frontmatter` | YAML frontmatter read/write utilities |
| `little_loops.decisions` | Decisions and rules log data layer (FEAT-1891) |
| `little_loops.decisions_sync` | Sync active required rules to `.ll/ll.local.md` |
| `little_loops.learning_tests` | Learning test registry — CRUD for `.ll/learning-tests/` records |
| `little_loops.doc_counts` | Documentation count verification |
| `little_loops.link_checker` | Link validation for markdown docs |
| `little_loops.user_messages` | User message extraction from Claude logs |
| `little_loops.workflow_sequence` | Workflow sequence analysis for multi-step patterns |
| `little_loops.goals_parser` | Product goals file parsing |
| `little_loops.history_reader` | Typed read-only query module for `.ll/history.db`. Exports event dataclasses including `UserCorrection`, `FileEvent`, `SearchResult`, `IssueEvent`, `SessionRef` (ENH-1711), `OrchestrationRun` (ENH-2492), `LoopRun` (ENH-2463), `LearningTestEvent` (ENH-2466), and `LifecycleEvent` (ENH-2495); query functions include `find_user_corrections()`, `recent_file_events()`, `search()`, `related_issue_events()`, `sessions_for_issue()`, effort/velocity/session metadata helpers, conversation and compaction readers, skill/commit/test/usage readers, plus `recent_orchestration_runs()` / `aggregate_orchestration_runs()` (ENH-2492), `read_base_sha()` / `read_base_dirty()` (ENH-2866 / ENH-3142, dequeue-time base-commit and dirty-tree readers), `read_prepatch_evidence()` (ENH-2997/ENH-2998, most-recent `PrePatchEvidence` bundle for an issue ID), `recent_loop_runs()` / `find_loop_run()` / `aggregate_loop_runs()` (ENH-2463), `waste_attribution()` (ENH-2722, per-loop tokens-wasted rollup joined on `run_id`), `recent_learning_tests()` / `find_learning_test()` (ENH-2466), and `recent_lifecycle_events()` / `handoff_frequency()` (ENH-2495). All functions return empty lists or `None` on missing/corrupt DB. |
| `little_loops.sync` | GitHub Issues bidirectional sync |
| `little_loops.session_log` | Session log linking for issue files |
| `little_loops.file_utils` | Shared file I/O utilities (atomic writes) |
| `little_loops.text_utils` | Text extraction utilities for issue content |
| `little_loops.pii` | PII detection and redaction utilities (`detect_pii`, `redact_pii`, `apply_pii_action`) |
| `little_loops.cli` | CLI entry points (package) |
| `little_loops.parallel` | Parallel processing subpackage |
| `little_loops.fsm` | FSM loop system subpackage |
| `little_loops.loops` | Loop YAML utilities subpackage (`yaml_state_editor`: round-trip `extract_action`/`replace_action`) |
| `little_loops.cli_args` | CLI argument parsing utilities |
| `little_loops.sprint` | Sprint planning and execution |
| `little_loops.issue_template` | Issue template assembly for sync pull (v2.0-compliant markdown from per-type section files) |
| `little_loops.cli.issues.create` | Atomic single-issue creation (`ll-issues create`) |
| `little_loops.cli.issues.scaffold_epic` | EPIC + pre-wired child stub creation (`ll-issues scaffold-epic`) |
| `little_loops.cli.issues.link_epics` | Orphan-to-EPIC assignment and clustering proposals (`ll-issues link-epics`) |
| `little_loops.output_parsing` | Claude CLI output parsing utilities used by `issue_manager` and `parallel` |
| `little_loops.ready_issue` | Runs `/ll:ready-issue` with a retry on an `UNKNOWN` (non-compliant, unparseable) verdict |
| `little_loops.output.parse` | Stop-sequence / prefill JSON output helpers (`extract_between_tags`, `parse_prefilled_json`) that bound LLM output-token cost |
| `little_loops.output_cleaner` | Anti-event + duplicate-window pre-filter (`filter_output`) that trims tool/log noise before it enters context |
| `little_loops.ab_writer` | A/B baseline results aggregation and `ab.json` writer (FEAT-1790). Provides `ABResults` dataclass + summary calculation + JSON schema generation. |
| `little_loops.cache_marking_oracle` | Cache-marking cost oracle (FEAT-2673, EPIC-2456 F1) — decides whether a stable prompt block is safe to mark `cache_control: ephemeral` via a per-model token-floor gate plus a `FragmentStore` reuse-repeat gate. |
| `little_loops.analytics` | Analytics subpackage — association-rule mining (lift/PMI) and per-evaluator Bernoulli variance for loop diagnostics. |
| `little_loops.design_tokens` | Multi-layer token loader (primitives → semantic → typography → spacing → theme) with profile-aware resolution (ENH-1768). Renders `{token.reference}` aliases for prompts and CSS. Also reads a root `DESIGN.md` as an alternate import source (`design_tokens.source: auto\|profile\|design_md`, ENH-3264); see [CONFIGURATION.md → DESIGN.md import source](CONFIGURATION.md#designmd-import-source-enh-3264). `render_as_design_md(tokens: DesignTokens) -> str` (ENH-3268) is the write side — a lossy, single-theme DESIGN.md export via `ll-artifact design-md export`. Primitives are excluded structurally; semantic colors export under classifier-recognized names (`color.<role>.<leaf>` → a name `_classify_design_md_color_role` re-derives back into `<role>`, so re-import recovers the role though not the original leaf key); typography is synthesized into the spec's role-organized shape from a pinned axis→role table. Dropped groups (`shadow.*`, `border.width.*`, unused typography axes, `components:` on a DESIGN.md → DESIGN.md round trip) are computed by `_design_md_dropped_groups(tokens)`, which the CLI layer writes to stderr — the renderer itself does no I/O, matching `render_as_css_vars`'s shape. |
| `little_loops.extensions` | Reference extension implementations — `ReferenceInterceptorExtension` copy-paste starting point for custom interceptors / event handlers. |
| `little_loops.env_file` | `.env` fallback loader — `parse_env_file(path)` and `load_env_fallback(project_root)` read `<root>/.env` as a fallback source; already-set process environment variables always win. |
| `little_loops.generate_schemas` | Draft-07 JSON Schema generation for every event type — `SCHEMA_DEFINITIONS` table, `generate_schemas(output_dir)`, and `event_type_to_filename()` (dots become underscores). Backs `ll-generate-schemas` and the committed files under `docs/reference/schemas/`. |
| `little_loops.issue_progress` | EPIC progress aggregation: child-issue status rollup (`IssueProgress`), oldest-open detection, and `epic-progress` CLI support. |
| `little_loops.issues` | Issue utility subpackage — anchor generation and sweep utilities used by `ll-issues anchor-sweep`, plus `research_triage` (ENH-2971), the coverage/staleness predicate behind `ll-issues research-triage`, plus `fold_research_findings` (ENH-2993), the H3-under-H2 fold primitive behind `ll-issues fold-findings` — `find_subsections()` returns *every* matching H3 span inside a named H2 slice (the existing extraction helpers are H2-only and read-oriented), and `fold_research_findings()` collapses them to one block, relocation-only. Its `analyzer` axis is additionally overridden by a failing Program Design gate (BUG-3003) — see `docs/reference/CLI.md`'s `ll-issues research-triage` entry. |
| `little_loops.observability` | DES variant registry and audit-tree walker for cross-checking every emit site against registered event shapes (ENH-2475, F5 adoption gate). |
| `little_loops.output` | Output-parsing subpackage — stop-sequence / prefill JSON helpers (`extract_between_tags`, `parse_prefilled_json`) for bounding LLM output-token cost (FEAT-2470). |
| `little_loops.package_data` | Declarative manifest of runtime-read package assets (templates, prompts, adapter configs) — `check_asset_accessible(parts)` and `list_missing_assets()`. Backs `ll-verify-package-data`. |
| `little_loops.paths` | Dependency-free project-root resolution (ENH-2924, relocated from `little_loops.issues.program_design`) — `find_project_root(start)` and `resolve_ll_dir(start, create=False)`. |
| `little_loops.pricing` | Model pricing constants (USD per million tokens) for token cost estimation across the model registry. `INTRO_PRICING` overrides `MODEL_PRICING` for a model while a time-bounded introductory rate is active (e.g. Sonnet 5's $2/$10 rate through 2026-08-31 inclusive, ENH-2835); `estimate_cost_usd()` checks `date.today()` against each entry's `expires` date and falls back to standard `MODEL_PRICING` once it lapses. |
| `little_loops.pytest_history_plugin` | Pytest plugin (registered under `pytest11` entry point) that records test-run pass/fail counts, duration, and failing node IDs into `.ll/history.db` (ENH-2459). |
| `little_loops.queue_store` | Persisted `ll-queue` entry store (`.ll/queue.db`; FEAT-2682) — schema `{id, action, enqueuedAt, priority, status, result, claimedAt, ownerPid}` with tiered `(priority, enqueuedAt)` ordering. |
| `little_loops.recursive_finalize` | Decomposed-parent lifecycle and EPIC re-linking. Powers `ll-issues finalize-decomposition` (ENH-1977 Fix 4), invoked from `rn-decompose` and `autodev`'s decomposition states (ENH-2615). |
| `little_loops.rn_synth_queue` | Readiness-gated concurrent queue for `rn-refine` bottom-up synthesis (ENH-2565) — `try_pop_ready()`, `mark_complete()`, `queue_is_empty()`, plus a `main(argv)` CLI shim; lock-file coordinated. |
| `little_loops.session_store` | Unified per-project SQLite + FTS5 history store (`.ll/history.db`; FEAT-1112) — single source of truth for tool events, file modifications, issue transitions, loop runs, and user corrections. |
| `little_loops.sft_formatter` | SFT (supervised fine-tuning) data format converters — ChatML and siblings — used by `ll-messages --sft-format`. |
| `little_loops.skill_expander` | Pre-expand skill/command Markdown content for subprocess prompts (replaces ToolSearch → Skill deferred-tool dependency in `ll-auto`). |
| `little_loops.stats` | Statistical utilities — Wilson 95% binomial confidence intervals for honest uncertainty reporting at small sample sizes. |
| `little_loops.test_file_patterns` | Test-file classification shared across gates — `is_test_file(path, config=None)` and `filter_test_files(paths, config=None)`. |
| `little_loops.test_tamper_guard` | Test-weakening detection core (ENH-2933) — `snapshot_test_paths()` / `snapshot_test_paths_at_ref()`, `compare_snapshots()`, `measure_test_strength()`, `is_weakening()`, `filter_weakening_findings()`,
`extract_test_functions()`, with `TamperFinding` / `TamperReport` / `TestStrength` / `ConfigTarget` dataclasses. |
| `little_loops.transport` | EventBus transport abstraction (`Transport` Protocol + `send`/`close`) with built-in `JsonlTransport`, `UnixSocketTransport`, `OTelTransport`, `WebhookTransport`, and `LocalBridgeTransport` (ENH-3351 — loopback-only SSE bridge for `ll-loop run --serve`) sinks. |
| `little_loops.worktree_utils` | Shared worktree setup/cleanup utilities used by `ll-parallel`, `ll-sprint`, `ll-loop`, the FSM executor's pre-patch check hook (ENH-2997), and `work_verification`'s non-FSM pre-patch check adapter (ENH-2998). See [WORKTREES.md](WORKTREES.md) for the file-copy contract. |
| `little_loops.prepatch_check` | Pre-patch check core (ENH-3142) — `run_prepatch_check()`, `collect_candidates()`, and the `PrePatchCandidate` / `PrePatchTestOutcome` / `PrePatchEvidence` dataclasses. Deterministic, no LLM/FSM/CLI/database access; runs candidate tests from a step diff against the pre-patch worktree ENH-3141's `setup_prepatch_worktree()` produces to flag evidence that passes without the change it claims to demonstrate. |
| `little_loops.mcp_call` | Thin CLI wrapper for direct MCP tool invocation via JSON-RPC |
| `little_loops.mcp_server` | `ll-mcp` MCP server (2026-07-28 spec, FEAT-3135) — `main_mcp` entry point plus the five read-only tools (`issues_query`, `issue_get`, `history_search`, `deps_check`, `capabilities`), the `ll://` resource surface (FEAT-3136): issue files, `.ll/ll-goals.md`, and `docs/` served under `ll://issues/<ID>`, `ll://goals`, `ll://docs/<relative-path>`, one interactive `ui://issues/view` MCP Apps resource (ENH-3306, `mimeType: "text/html;profile=mcp-app"`, linked from `issue_get` via `_meta.ui.resourceUri`), and the prompts-from-skills surface (FEAT-3137): every discovered `SKILL.md` advertised as an MCP prompt (name/description/args from frontmatter), all resolved against discovery-time enumerations. Serves over stdio by default; `ll-mcp --http` or `LL_MCP_TRANSPORT=http` switches to streamable HTTP on loopback (FEAT-3143), same server, same tool/resource/prompt surfaces. |
| `little_loops.advisor` | Capability-rank comparison (`MODEL_RANKS`, `rank_model`, `check_floor`, FEAT-3108) and the accountable, signal-cited consult path (`consult`, `AdvisorVerdict`, FEAT-3120). |

---

## little_loops.config

Configuration management for little-loops projects.

### BRConfig

Main configuration class that loads and provides access to project settings.

```python
from pathlib import Path
from little_loops.config import BRConfig

config = BRConfig(Path.cwd())
print(config.project.src_dir)  # "src/"
print(config.issues.base_dir)  # ".issues"
```

#### Constructor

```python
BRConfig(project_root: Path)
```

**Parameters:**
- `project_root` - Path to the project root directory

**Behavior:**
- Loads `.ll/ll-config.json` if present
- Merges with sensible defaults
- Creates typed config objects

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `project` | `ProjectConfig` | Project-level settings |
| `issues` | `IssuesConfig` | Issue management settings |
| `automation` | `AutomationConfig` | Sequential automation settings |
| `parallel` | `ParallelAutomationConfig` | Parallel automation settings |
| `commands` | `CommandsConfig` | Command customization (includes `confidence_gate: ConfidenceGateConfig`, `tdd_mode: bool`, `rate_limits: RateLimitsConfig`) |
| `scan` | `ScanConfig` | Codebase scanning settings |
| `sprints` | `SprintsConfig` | Sprint management settings |
| `loops` | `LoopsConfig` | FSM loop settings |
| `sync` | `SyncConfig` | GitHub Issues sync settings |
| `dependency_mapping` | `DependencyMappingConfig` | Overlap detection thresholds |
| `code_query` | `CodeQueryConfig` | Code-query provider selection, codegraph db path, and staleness policy (inert until a provider consumes it, see [CONFIGURATION.md#code_query](CONFIGURATION.md#code_query)) |
| `tamper_guard` | `TamperGuardConfig` | Non-FSM tamper guard default policy (ENH-2935), consumed by `work_verification.verify_work_was_done()`, see [CONFIGURATION.md#tamper_guard](CONFIGURATION.md#tamper_guard) |
| `refine_status` | `RefineStatusConfig` | refine-status display settings |
| `cli` | `CliConfig` | CLI output settings (color toggle and color overrides) |
| `design_tokens` | `DesignTokensConfig` | Design system token settings |
| `orchestration` | `OrchestrationConfig` | Orchestration settings (host CLI selection, composer config, cluster config) |
| `advisor` | `AdvisorConfig` | Advisor settings (host, model, capability floor, per-consult timeout, triggers, per-task budget, `store_verdict_body` opt-in for `advisor_consults` telemetry); config plumbing only, absent means disabled (FEAT-3043, FEAT-3300) |
| `events` | `EventsConfig` | Event transport/emission settings |
| `decisions` | `DecisionsConfig` | Decisions and rules log configuration |
| `learning_tests` | `LearningTestsConfig` | Learning test registry settings |
| `prepatch_check` | `PrePatchCheckConfig` | Pre-patch check configuration (ENH-3142) |
| `analytics_capture` | `AnalyticsCaptureConfig` | Analytics capture sub-settings (see [CONFIGURATION.md#analytics](CONFIGURATION.md#analytics)) |
| `history` | `HistoryConfig` | History.db consumer tuning (see [CONFIGURATION.md#history](CONFIGURATION.md#history)) |
| `extensions` | `list[str]` | Extension module paths to load |
| `repo_path` | `Path` | Resolved repository root path |
| `issue_categories` | `list[str]` | List of category names |
| `issue_priorities` | `list[str]` | List of priority prefixes |

#### CliConfig

Controls ANSI color output across all `ll-*` CLI tools.

```json
{
  "cli": {
    "color": true,
    "colors": {
      "logger": {
        "info": "36",
        "success": "32",
        "warning": "33",
        "error": "38;5;208"
      },
      "priority": {
        "P0": "38;5;208;1",
        "P1": "38;5;208",
        "P2": "33",
        "P3": "0",
        "P4": "2",
        "P5": "2"
      },
      "type": {
        "BUG": "38;5;208",
        "FEAT": "32",
        "ENH": "34",
        "EPIC": "35"
      }
    }
  }
}
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `cli.color` | `bool` | `true` | Enable ANSI color output. Set to `false` for CI or plain-text terminals. |
| `cli.colors.logger.*` | `str` | see above | Raw ANSI SGR codes for each log level (e.g. `"38;5;208"` for orange). |
| `cli.colors.priority.*` | `str` | see above | Raw ANSI SGR codes for priority labels P0–P5. |
| `cli.colors.type.*` | `str` | see above | Raw ANSI SGR codes for issue type labels BUG, FEAT, ENH, EPIC. |

**Notes:**
- Setting `NO_COLOR=1` in the environment disables color regardless of `cli.color`.
- Unspecified `cli.colors` sub-keys retain their defaults.
- Color values are raw SGR parameter strings (e.g. `"32"`, `"38;5;208"`, `"1;34"`).

#### DesignTokensConfig

Controls design system token injection into FSM loops. See [CONFIGURATION.md → `design_tokens`](CONFIGURATION.md#design_tokens) for setup guidance.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | `bool` | `True` | Enable design-token context injection into FSM loops. |
| `path` | `str` | `".ll/design-tokens"` | Directory containing token definition files. |
| `primitives_file` | `str` | `"primitives.json"` | Filename for primitive (raw) token values within `path`. |
| `semantic_file` | `str` | `"semantic.json"` | Filename for semantic (aliased) token values within `path`. |
| `themes_dir` | `str` | `"themes"` | Subdirectory of `path` containing per-theme override files. |
| `active_theme` | `str` | `"dark"` | Name of the active theme; must match a file in `themes_dir`. |
| `active` | `str` | `"default"` | Active design token profile name; selects a bundled profile under `<path>/<profiles_dir>/<active>/`. |
| `profiles_dir` | `str \| None` | `None` | Subdirectory of `path` containing per-profile layouts (ENH-1768). `None` falls back to the legacy flat layout (`<path>/primitives.json`, etc.). |

#### DecisionsConfig

Controls the decisions and rules log. See [CONFIGURATION.md → `decisions`](CONFIGURATION.md#decisions) for setup guidance.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | `bool` | `False` | Enable the decisions log feature. When `False`, all integrations gracefully skip. |
| `log_path` | `str` | `".ll/decisions.yaml"` | Path to the legacy flat decisions file, relative to the project root. The append-only fragment directory is derived as its `.d`-suffixed sibling (`.ll/decisions.d/`); reads union both tiers. |
| `auto_generate` | `list[str]` | `[]` | Issue type prefixes to include during `ll-issues decisions generate` (e.g., `["FEAT", "ENH"]`). Empty list (default) generates entries for all completed issue types. |

#### Methods

##### get_issue_dir

```python
def get_issue_dir(self, category: str) -> Path
```

Get the directory path for an issue category.

**Parameters:**
- `category` - Category key (e.g., `"bugs"`, `"features"`)

**Returns:** `Path` to the issue category directory

**Example:**
```python
bugs_dir = config.get_issue_dir("bugs")
# Returns: Path(".issues/bugs")
```

##### legacy_issue_dirs

```python
def legacy_issue_dirs(self) -> list[Path]
```

Return existing legacy `completed_dir`/`deferred_dir` paths, if any. These
directories are deprecated (status now lives in frontmatter) but a file can
still land there via a stale migration or manual placement; resolvers that
scan `issue_categories` only would otherwise treat it as nonexistent
(BUG-2733). `ll-issues path`/`show` (`show.py:_resolve_issue_id`) and
`ll-issues list --status done --json` (`search.py:_load_issues_with_status`)
both append this to their scan directories.

**Returns:** Existing legacy directories, in `completed_dir`, `deferred_dir` order.

##### get_issue_prefix

```python
def get_issue_prefix(self, category: str) -> str
```

Get the issue ID prefix for a category.

**Parameters:**
- `category` - Category key

**Returns:** Issue prefix (e.g., `"BUG"`, `"FEAT"`)

##### get_category_action

```python
def get_category_action(self, category: str) -> str
```

Get the default action for a category.

**Parameters:**
- `category` - Category key

**Returns:** Action verb (e.g., `"fix"`, `"implement"`)

##### create_parallel_config

```python
def create_parallel_config(
    self,
    *,
    max_workers: int | None = None,
    priority_filter: list[str] | None = None,
    max_issues: int = 0,
    dry_run: bool = False,
    timeout_seconds: int | None = None,
    idle_timeout_per_issue: int | None = None,
    stream_output: bool | None = None,
    show_model: bool | None = None,
    only_ids: set[str] | None = None,
    skip_ids: set[str] | None = None,
    type_prefixes: set[str] | None = None,
    label_filter: set[str] | None = None,
    merge_pending: bool = False,
    clean_start: bool = False,
    ignore_pending: bool = False,
    overlap_detection: bool = False,
    serialize_overlapping: bool = True,
    base_branch: str | None = None,
    remote_name: str | None = None,
    use_feature_branches: bool | None = None,
    skip_learning_gate: bool = False,
    epic_branches: EpicBranchesConfig | None = None,
) -> ParallelConfig
```

`epic_branches` accepts an `EpicBranchesConfig` override (from
`little_loops.config.automation`); when `None` the value falls back to
`parallel.epic_branches` in config. CLI callers build the override with
`dataclasses.replace(config.parallel.epic_branches, enabled=<flag>)` so the
`--epic-branches` / `--no-epic-branches` flag toggles only `enabled` while
preserving the configured `prefix` / `merge_to_base_on_complete` / `open_pr`.

Create a `ParallelConfig` from BRConfig settings with optional overrides.

**Parameters:**
- `max_workers` - Override max workers (default: from config)
- `priority_filter` - Override priority filter
- `max_issues` - Maximum issues to process (0 = unlimited)
- `dry_run` - Preview mode without processing
- `timeout_seconds` - Per-issue timeout in seconds
- `idle_timeout_per_issue` - Kill worker if no output for N seconds (0 to disable)
- `stream_output` - Stream Claude output
- `show_model` - Display model info on setup
- `only_ids` - If provided, only process these issue IDs
- `skip_ids` - Issue IDs to skip (in addition to completed/failed)
- `type_prefixes` - If provided, only process issues with these type prefixes
- `label_filter` - If provided, only process issues with one of these labels
- `merge_pending` - Attempt to merge pending worktrees from previous runs
- `clean_start` - Remove all worktrees without checking for pending work
- `ignore_pending` - Report pending work but continue without merging
- `overlap_detection` - Enable pre-flight overlap detection
- `serialize_overlapping` - If True, defer overlapping issues; if False, just warn
- `base_branch` - Base branch for rebase/merge operations (default: from `parallel.base_branch` config)
- `remote_name` - Git remote name (default: from `parallel.remote_name` config)
- `use_feature_branches` - Override `parallel.use_feature_branches` config
- `skip_learning_gate` - Bypass per-worktree proof-first-task gate

**Returns:** Configured `ParallelConfig`

**Example:**
```python
parallel_config = config.create_parallel_config(
    max_workers=4,
    max_issues=10,
    dry_run=True
)
```

##### to_dict

```python
def to_dict(self) -> dict[str, Any]
```

Convert configuration to dictionary for variable substitution.

**Returns:** Dictionary representation of all config values

##### resolve_variable

```python
def resolve_variable(self, var_path: str) -> str | None
```

Resolve a variable path like `project.src_dir` to its value.

**Parameters:**
- `var_path` - Dot-separated path to configuration value

**Returns:** The resolved value as a string, or `None` if not found

---

### ProjectConfig

Project-level configuration dataclass.

```python
@dataclass
class ProjectConfig:
    name: str = ""
    src_dir: str = "src/"
    test_dir: str = "tests"
    test_cmd: str = "pytest"
    lint_cmd: str = "ruff check ."
    type_cmd: str | None = "mypy"
    format_cmd: str | None = "ruff format ."
    build_cmd: str | None = None
    run_cmd: str | None = None
    health_url: str | None = None
    test_patterns: list[str] = field(default_factory=lambda: [...])  # ENH-2973
```

`test_file_patterns.is_test_file(path, config=None)` is the shared, pure classifier consumers wire against `project.test_patterns` (508c5565): given a repo-relative, POSIX-normalized path, it returns whether the path matches any configured pattern via `git_operations.file_matches_pattern`, with no git calls, filesystem stat, or LLM invocation of its own. Per-project-type defaults live in `scripts/little_loops/templates/*.json`.

`test_tamper_guard.run_tamper_guard(before, changed_files, config, policy, repo_root)` (ENH-2933) is the deterministic tamper-guard core: it diffs a caller-supplied pre-step `TamperSnapshot` (from `snapshot_test_paths`, over the union of `test_file_patterns.filter_test_files` and `resolved_pytest_config_paths`) against current on-disk content, then applies a `TamperPolicy` (`"revert" | "fail" | "allow"`, default `"fail"`) via `apply_tamper_policy` — `revert` restores tracked modified/deleted files via `git checkout --` (never touching newly-added files, which is ENH-2853's job), `fail` reports without mutating, `allow` records findings without blocking. The module has zero imports from `fsm/`, `issue_manager.py`, `parallel/worker_pool.py`, or `work_verification.py`; adapters (ENH-2934's FSM hook, ENH-2935's Python hook) own verification-step timing and call into this module, not the reverse. `resolved_pytest_config_paths` is a thin wrapper over `resolved_pytest_config_targets`, which returns `ConfigTarget(path, section)` pairs — `section` is a dotted TOML table path (e.g. `("tool", "pytest", "ini_options")`) for a multi-purpose config file like `pyproject.toml`, or `None` for a single-purpose file (`pytest.ini`, `tox.ini`, `setup.cfg`). `snapshot_test_paths`/`snapshot_test_paths_at_ref` hash a section-scoped target by its selected section only (`hash_config_target`), so an unrelated edit elsewhere in `pyproject.toml` (a version bump, a dependency change) doesn't produce a finding, while an edit inside `[tool.pytest.ini_options]` still does; unparseable TOML falls back to whole-file hashing, staying fail-closed (BUG-2957).

**`cli/verify_triggers.py` (`ll-verify-triggers`) scoring model:** only skills that declare `trigger_fixtures` (should-fire/should-not-fire phrasings) are scored for precision/recall and cross-skill collisions; every other model-invocable skill is reported as an *unmeasured* coverage gap rather than silently scored at 0% — distinguishing "never validated" from "validated and failing" (BUG-2879's fix). Exit is non-zero only when a *measured* skill falls below threshold or collides with another skill's trigger phrasings.

### IssuesConfig

Issue management configuration dataclass.

```python
@dataclass
class IssuesConfig:
    base_dir: str = ".issues"
    categories: dict[str, CategoryConfig]
    completed_dir: str = "completed"  # DEPRECATED: use IssueInfo.status instead
    deferred_dir: str = "deferred"  # DEPRECATED: use IssueInfo.status instead
    priorities: list[str]  # ["P0", "P1", ...]
    templates_dir: str | None = None
    capture_template: str = "full"
    duplicate_detection: DuplicateDetectionConfig  # thresholds for skip/update/create
    next_issue: NextIssueConfig  # selection strategy for ll-issues next-issue / next-issues
    auto_commit: bool = False
    auto_commit_prefix: str = "chore(issues)"
```

### DuplicateDetectionConfig

Thresholds controlling duplicate issue detection behavior.

```python
@dataclass
class DuplicateDetectionConfig:
    exact_threshold: float = 0.8   # score >= this → skip (duplicate)
    similar_threshold: float = 0.5  # score >= this → update existing issue
```

### NextIssueConfig

Selection behavior for `ll-issues next-issue` / `next-issues` commands. Named strategies map to preset sort orderings; an explicit `sort_keys` list overrides the preset.

```python
@dataclass
class NextIssueConfig:
    strategy: str = "confidence_first"   # "confidence_first" | "priority_first"
    sort_keys: list[NextIssueSortKey] | None = None  # custom sort, overrides strategy

@dataclass
class NextIssueSortKey:
    key: str         # "priority" | "outcome_confidence" | "confidence_score" |
                     # "effort" | "impact" | "score_complexity" |
                     # "score_test_coverage" | "score_ambiguity" | "score_change_surface"
    direction: str = "asc"  # "asc" | "desc"
```

Strategy presets:
- `confidence_first` (default): `(-outcome_confidence, -confidence_score, priority_int)` — byte-identical to the legacy hardcoded ordering.
- `priority_first`: `(priority_int, -outcome_confidence, -confidence_score)`.

None-handling (per-field sentinel): `direction="desc"` → component is `-value` when set, `1` when `None` (sorts after negatives); `direction="asc"` → component is `value` when set, `9999` when `None` (sorts last).

`NextIssueConfig.from_dict` validates `strategy` and each `sort_keys[*].key` against the allowed enum, raising `ValueError` on unknown values.

### CategoryConfig

Configuration for an issue category.

```python
@dataclass
class CategoryConfig:
    prefix: str      # e.g., "BUG"
    dir: str         # e.g., "bugs"
    action: str      # e.g., "fix"
```

### AutomationConfig

Sequential automation configuration.

```python
@dataclass
class AutomationConfig:
    timeout_seconds: int = 7200
    idle_timeout_seconds: int = 0  # Kill if no output for N seconds (0 to disable)
    post_stream_close_grace_seconds: int = 300  # Grace before force-kill after streams close
    timeout_kill_grace_seconds: float = 30  # SIGTERM grace before SIGKILL on timeout (ENH-3130)
    state_file: str = ".auto-manage-state.json"
    worktree_base: str = ".worktrees"
    max_workers: int = 2
    stream_output: bool = True
    max_continuations: int = 3  # Max session restarts on context handoff
```

### ParallelAutomationConfig

Parallel automation configuration stored in BRConfig using composition.

Uses `AutomationConfig` for shared settings (max_workers, worktree_base, state_file, timeout_seconds, stream_output) plus parallel-specific fields.

```python
@dataclass
class ParallelAutomationConfig:
    base: AutomationConfig  # Shared automation settings
    p0_sequential: bool = True
    max_merge_retries: int = 2
    command_prefix: str = "/ll:"
    ready_command: str = "ready-issue {{issue_id}}"
    manage_command: str = "manage-issue {{issue_type}} {{action}} {{issue_id}}"
    decide_command: str = "decide-issue {{issue_id}}"
    worktree_copy_files: list[str] = field(default_factory=lambda: [".claude/settings.local.json", ".env", ".ll/ll.local.md"])
    require_code_changes: bool = True
    use_feature_branches: bool = False
    push_feature_branches: bool = False
    open_pr_for_feature_branches: bool = False
    base_branch: str = "main"
    remote_name: str = "origin"
```

**Fields:**
- `decide_command` - Command template for automated decision resolution
- `worktree_copy_files` - Files copied from main repo to each worktree. See [WORKTREES.md](WORKTREES.md) for the full copy contract (directory recursion, `.claude/` handling, `history.db` sharing).
- `require_code_changes` - Fail issues that don't produce code changes
- `use_feature_branches` - Create `feature/<id>-<slug>` branches instead of auto-merged worktree branches; skips auto-merge, leaving branches as PR-ready
- `push_feature_branches` - Push feature branches to remote after creation
- `open_pr_for_feature_branches` - Open a PR automatically for each feature branch
- `base_branch` - Base branch for rebase/merge operations (default: `None` — auto-detected at runtime as `origin/HEAD` → current branch → `main`)
- `remote_name` - Git remote name for fetch/pull operations (default: `"origin"`)

**Note:** Shared fields from `AutomationConfig` are accessed via `base.*`:
- `base.max_workers` - Maximum parallel workers (default: 2)
- `base.worktree_base` - Base directory for worktrees (default: ".worktrees")
- `base.state_file` - State file path (default: ".parallel-manage-state.json")
- `base.timeout_seconds` - Per-issue timeout in seconds (default: 3600)
- `base.stream_output` - Stream subprocess output (default: False for parallel)

### SprintsConfig

Sprint management configuration.

```python
@dataclass
class SprintsConfig:
    sprints_dir: str = ".sprints"                 # Directory for sprint YAML files
    default_timeout: int = 3600                   # Default per-issue timeout in seconds
    default_max_workers: int = 2                  # Default worker count for wave execution
    max_issue_wall_clock_time: int = 2700         # Max wall-clock seconds per issue before forced handoff
```

### LoopsConfig

FSM loop configuration.

```python
@dataclass
class LoopsConfig:
    loops_dir: str = ".loops"                    # Directory for loop YAML definitions
    queue_wait_timeout_seconds: int = 86400      # Max seconds to wait for a queue item
    glyphs: LoopsGlyphsConfig                    # Unicode badge overrides for FSM box diagrams
    run_defaults: LoopRunDefaults                # Persistent CLI defaults for ll-loop run
```

### LoopRunDefaults

Persistent CLI defaults for `ll-loop run`. Values are backfilled when the corresponding flag is absent; explicit CLI flags always take precedence.

```python
@dataclass
class LoopRunDefaults:
    clear: bool = False           # If True, inject --clear into every ll-loop run invocation
    show_diagrams: str | None = None  # Inject --show-diagrams <value>; 'default' = bare flag; None = disabled
    mode: str | None = None       # Reserved for a future --mode flag
    include: str = ""             # Default loop allowlist injected into fsm.context; empty = all loops visible
    delay: float | None = None    # Inject --delay <seconds> inter-iteration pause; None = disabled
```

`include` accepts comma-separated selectors: `loop-name`, `builtin:*`, `project:*`, `category:<label>`. Set in `ll-config.json` as `loops.run_defaults.include`; override per-invocation with `--context include=VALUE`.

`delay` injects `--delay <seconds>` (a non-negative inter-iteration pause) when `--delay` is absent on the CLI; an explicit `--delay` always wins, and `null` disables injection.

### GitHubSyncConfig

GitHub-specific sync configuration.

```python
@dataclass
class GitHubSyncConfig:
    repo: str | None = None                    # GitHub repo slug (owner/repo); auto-detected if None
    label_mapping: dict[str, str] = {          # Issue type → GitHub label
        "BUG": "bug",
        "FEAT": "enhancement",
        "ENH": "enhancement",
        "EPIC": "epic",
    }
    priority_labels: bool = True               # Sync priority as GitHub labels
    sync_completed: bool = False               # Include completed issues in sync
    state_file: str = ".ll/ll-sync-state.json"  # Sync state file path
    pull_template: str = "minimal"             # Template for pulled issues ("minimal" | "full")
    pull_limit: int = 500                      # Max issues to fetch from GitHub per pull (ENH-825)
```

> **Note**: When `pull_issues()` returns exactly `pull_limit` results, a warning is logged indicating the results may be truncated. Increase `sync.github.pull_limit` in `ll-config.json` if you have more issues than the default limit.

### SyncConfig

Issue sync configuration.

```python
@dataclass
class SyncConfig:
    enabled: bool = False
    provider: str = "github"
    github: GitHubSyncConfig = GitHubSyncConfig()
```

### ScoringWeightsConfig

Scoring weights for semantic conflict analysis. Used by `DependencyMappingConfig`.

```python
@dataclass
class ScoringWeightsConfig:
    semantic: float = 0.5    # Weight for semantic target overlap (component/function names)
    section: float = 0.3     # Weight for section mention overlap (UI regions)
    type: float = 0.2        # Weight for modification type match
```

Weights should sum to 1.0 for normalized scoring.

### DependencyMappingConfig

Dependency mapping threshold configuration. Controls overlap detection sensitivity and conflict scoring.

```python
@dataclass
class DependencyMappingConfig:
    overlap_min_files: int = 2                 # Minimum overlapping files to trigger overlap
    overlap_min_ratio: float = 0.25            # Minimum ratio of overlapping to smaller file set
    min_directory_depth: int = 2               # Minimum path segments for directory overlap
    conflict_threshold: float = 0.4            # Below = parallel-safe, above = dependency proposed
    high_conflict_threshold: float = 0.7       # Above = HIGH conflict label
    confidence_modifier: float = 0.5           # Applied when dependency direction is ambiguous
    scoring_weights: ScoringWeightsConfig      # Weights for semantic/section/type signals
    exclude_common_files: list[str]            # Infrastructure files excluded from overlap detection
```

**Overlap detection AND semantics**: An issue pair is considered overlapping only when **both** `overlap_min_files` and `overlap_min_ratio` thresholds are met simultaneously. This prevents false serialization for pairs that share many small files (high file count, low ratio) or few files from a large set (low file count, high ratio). Lower either threshold to serialize more aggressively; raise both to parallelize more.

### RefineStatusConfig

Configuration for the `ll-issues refine-status` display.

```python
@dataclass
class RefineStatusConfig:
    columns: list[str] = []       # Column names to include (empty = all default columns)
    elide_order: list[str] = []   # Column drop sequence for narrow terminals (empty = default order)
```

---

## little_loops.issue_parser

Issue file parsing utilities.

### IssueInfo

Parsed information from an issue file.

```python
@dataclass
class IssueInfo:
    path: Path                              # Path to the issue file
    issue_type: str                         # e.g., "bugs"
    priority: str                           # e.g., "P1"
    issue_id: str                           # e.g., "BUG-123"
    title: str                              # Issue title
    blocked_by: list[str] = []             # Issue IDs that block this issue (hard dependency — wave-gated)
    blocks: list[str] = []                 # Issue IDs that this issue blocks (computed inverse of blocked_by)
    parent: str | None = None              # Parent issue ID this was decomposed from (e.g., "ENH-179")
    depends_on: list[str] = []            # Soft ordering prerequisites (wave-gated: scheduled after; non-fatal if absent)
    relates_to: list[str] = []            # Thematically related issue IDs (no ordering constraint)
    duplicate_of: str | None = None        # Issue ID this duplicates; set when closing a duplicate
    supersedes: list[str] = []            # Issue IDs this issue replaces; `superseded_by()` derives the reverse edge
    discovered_by: str | None = None       # Source command/workflow that created this issue
    epic: str | None = None                # Epic issue ID this child belongs to (e.g., "EPIC-001")
    base_branch: str | None = None         # For EPIC issues, the fork base for the integration branch; from frontmatter `base_branch:` or alias `target_branch:`; None means fall back to `parallel.base_branch` (FEAT-2652)
    product_impact: ProductImpact | None = None  # Product impact assessment
    effort: int | None = None              # Effort estimate (1=low, 2=medium, 3=high)
    impact: int | None = None              # Impact estimate (1=low, 2=medium, 3=high)
    confidence_score: int | None = None    # Readiness score (0-100) from /ll:confidence-check
    outcome_confidence: int | None = None  # Outcome confidence (0-100) from /ll:confidence-check
    score_complexity: int | None = None    # Outcome criterion A – Complexity (0-25; Breadth 0-12 + Depth 0-13) from /ll:confidence-check
    score_test_coverage: int | None = None # Outcome criterion B – Test Coverage (0-25) from /ll:confidence-check
    score_ambiguity: int | None = None     # Outcome criterion C – Ambiguity (0-25) from /ll:confidence-check
    score_change_surface: int | None = None # Outcome criterion D – Change Surface / Fanout Verifiability (0-25; Pattern A blast-radius or Pattern B enumerated mechanical fanout) from /ll:confidence-check
    size: str | None = None               # Issue size from /ll:issue-size-review (Small, Medium, Large, Very Large)
    testable: bool | None = None           # False = skip TDD phase; None = treat as testable
    decision_needed: bool | None = None    # Set to true by /ll:refine-issue (2+ options) or /ll:confidence-check (unresolved decision); cleared by /ll:decide-issue
    unproven_mechanism: bool | None = None # Set to true by /ll:refine-issue when a deposited finding has no confirming precedent; caps /ll:confidence-check's outcome_confidence and drives set-flags' spike_needed trigger; cleared by /ll:spike (spike_completed) or /ll:reconcile-issue (ENH-3350)
    missing_artifacts: bool | None = None  # Set to true by `ll-issues set-flags` (FLAG_RULES) when absent pre-condition files detected; suppressed for co-deliverable files in Files to Create
    implementation_order_risk: bool | None = None  # Set to true by `ll-issues set-flags` (FLAG_RULES) when ordering advice detected (e.g., "implement tests first"), or when missing_artifacts' co-deliverable suppression fired; not a wiring gap
    learning_tests_required: list[str] | None = None  # Declared assumptions about external systems; /ll:ready-issue and /ll:confidence-check (Phase 1.5) each check via ll-learning-tests check
    session_commands: list[str] = []       # Distinct /ll:* commands in ## Session Log
    session_command_counts: dict[str, int] = {}  # Per-command occurrence counts
    labels: list[str] = []                 # Labels from `labels:` frontmatter field
    milestone: str | None = None           # Sprint or milestone name; None if unassigned
    status: str = "open"                   # Lifecycle status from frontmatter: open | in_progress | blocked | deferred | done | cancelled
```

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `priority_int` | `int` | Priority as integer (0=P0, 1=P1, etc.) |

#### Methods

```python
def to_dict(self) -> dict[str, Any]
```
Convert to dictionary for JSON serialization.

```python
@classmethod
def from_dict(cls, data: dict[str, Any]) -> IssueInfo
```
Create from dictionary.

#### Confidence-Check Score Rubrics (Outcome Criteria A & D)

The `score_complexity` and `score_change_surface` fields are composite scores produced by `/ll:confidence-check`. They were refactored in ENH-1413 and ENH-1412 respectively into sub-axis structures:

**Criterion A — Complexity (0–25 = Breadth 0–12 + Depth 0–13)** _(ENH-1413)_

- **Breadth** scores how many files/components the change touches (detected by enumeration in the issue's integration map).
- **Depth** scores how complex the change is per-site (detected from change-description language: "rewrite", "refactor", "new abstraction" → high; "rename", "add flag", "extend table" → low).
- Risk factors phrase concerns by the dominant axis ("wide-shallow" vs "narrow-deep").

**Criterion D — Change Surface / Fanout Verifiability (0–25)** _(ENH-1412)_

Dual-pattern rubric — the issue is scored under whichever pattern fits:

- **Pattern A — Code blast radius** (count-based): Score by how many files/symbols the change ripples to. Used for novel changes whose effects cannot be enumerated up-front.
- **Pattern B — Enumerated mechanical fanout** (verifiability-based): Score by completeness of the verification chain (issue enumerates all sites + greppable invariant + automated test that asserts coverage). A complete chain earns a full score even with a large file count, because the change is mechanically verifiable.
- Phase 4.8 suppresses large-file-surface risk phrases when Pattern B's verification chain is complete.

See `skills/confidence-check/rubric.md` for the full rubric tables and output templates, and `skills/confidence-check/SKILL.md` for the phase definitions and flow.

### ProductImpact

Product impact assessment dataclass, stored as `IssueInfo.product_impact`.

```python
@dataclass
class ProductImpact:
    goal_alignment: str | None = None    # Strategic priority ID this supports
    persona_impact: str | None = None    # ID of affected persona
    business_value: str | None = None    # "high" | "medium" | "low"
    user_benefit: str | None = None      # Description of user benefit
```

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `to_dict()` | `dict` | Convert to dictionary for JSON serialization |
| `from_dict(data)` | `ProductImpact \| None` | Create from dictionary; returns `None` if data is `None`/empty |

### IssueParser

Parses issue files based on project configuration.

```python
from little_loops.issue_parser import IssueParser
from little_loops.config import BRConfig
from pathlib import Path

config = BRConfig(Path.cwd())
parser = IssueParser(config)
info = parser.parse_file(Path(".issues/bugs/P1-BUG-001-example.md"))

print(info.issue_id)  # "BUG-001"
print(info.priority)  # "P1"
print(info.title)     # "Example bug title"
```

#### Constructor

```python
IssueParser(config: BRConfig)
```

**Parameters:**
- `config` - Project configuration

#### Methods

##### parse_file

```python
def parse_file(self, issue_path: Path) -> IssueInfo
```

Parse an issue file to extract metadata.

**Parameters:**
- `issue_path` - Path to the issue markdown file

**Returns:** Parsed `IssueInfo`

### Helper Functions

#### is_normalized

```python
def is_normalized(filename: str) -> bool
```

Check whether an issue filename conforms to naming conventions.

**Parameters:**
- `filename` - The basename of the issue file (e.g. `"P2-BUG-010-my-issue.md"`)

**Returns:** `True` if filename matches `^P[0-5]-(BUG|FEAT|ENH|EPIC)-[0-9]{3,}-[a-z0-9-]+\.md$`

#### parse_issue_filename

```python
def parse_issue_filename(filename: str) -> FilenameId | None
```

Parse the canonical `P?-TYPE-NNN-` anchor at the start of an issue filename into a frozen `FilenameId` dataclass (`priority: str | None`, `type_prefix: str`, `number: str`).

The numeric ID is the true unique identifier (globally unique across types); the type prefix is human-readable shorthand. Resolvers must key on this anchored parse — never on substring matching over the whole filename, which a title slug embedding another issue's ID can accidentally satisfy (e.g. `P3-ENH-3144-correct-epic-3127-...md` contains `epic-3127` in its slug but is issue 3144).

**Parameters:**
- `filename` - Issue file basename (e.g. `"P2-BUG-010-my-issue.md"`)

**Returns:** `FilenameId`, or `None` when the filename has no canonical anchor (legacy/unnormalized names)

#### is_formatted

```python
def is_formatted(issue_path: Path, templates_dir: Path | None = None) -> bool
```

Check whether an issue file has been formatted to the template structure.

An issue is considered formatted if either:
1. Its `## Session Log` section contains a `/ll:format-issue` entry, **or**
2. All required sections for its type template are present as `##` headings. `Labels` is no longer a required body heading post-ENH-1392 (it moved to `labels:` frontmatter); `is_formatted()` derives this from the template, so no `## Labels` body section is needed.

**Parameters:**
- `issue_path` - Path to the issue markdown file
- `templates_dir` - Optional override for the templates directory

**Returns:** `True` if the issue passes either criterion; `False` for files whose type cannot be determined or whose template cannot be loaded

#### check_format_gaps

```python
def check_format_gaps(
    issue_path: Path,
    templates_dir: Path | None = None,
    issue_statuses: dict[str, str] | None = None,
    ref_index: RefIndex | None = None,
    symbol_index: SymbolIndex | None = None,
    cli_index: CliSurfaceIndex | None = None,
) -> FormatGaps
```

Grade an issue's structural format gaps against its type template (ENH-2426). Deterministic (no LLM) — backs the `ll-issues format-check` subcommand and the `ensure_formatted` gate in `rn-remediate.yaml`. Unlike `is_formatted()`, this always runs the structural analysis; it does not honor the `/ll:format-issue` session-log shortcut, since every issue reaching the gate has already run that command.

Reports twenty-six gap classes on the returned `FormatGaps` dataclass (`missing`, `renamed`, `empty`, `boilerplate`, `malformed_id`, `prose_dep_drift`, `stale_prose_dep`, `program_design_nonspecific`, `deprecated_key`, `multi_frontmatter`, `testable`, `stale_file_ref`, `unmarked_superseded_directive`, `duplicate_findings_block`, `ambiguous_file_ref`, `missing_behavior_parity`, `soft_dep_hard_edge`, `malformed_dep_id`, `stale_symbol_ref`, `mislocated_symbol_ref`, `stale_cli_flag`, `duplicate_heading`, `empty_provenance_stub`, `template_placeholders`, `unapplied_decision`, `priority_drift` — each a `list[str]`, plus a derived `has_gaps` property and a `to_dict()` for JSON output; re-derive this count from `dataclasses.fields(FormatGaps)` rather than trusting the number written here):
- **missing** — a required section header is absent from the body.
- **renamed** — a present section header is `deprecated: true` in the template with an extractable canonical replacement in its `deprecation_reason` (e.g. `"Proposed Fix" -> "Proposed Solution"`).
- **empty** — a required section header is present but its body is whitespace-only.
- **boilerplate** — a required section's body still equals its `creation_template` (whole-body match only, to avoid false positives on partially-filled sections).
- **malformed_id** — frontmatter `id` is present but does not match the filename-derived `TYPE-NNN` (BUG-2769), e.g. a bare int (`id: 2756`) or quoted numeric (`id: "1294"`) instead of `id: BUG-2756`.
- **prose_dep_drift** (FEAT-2849) — the body claims a dependency in prose (`extract_prose_deps()`, see below) on an **active** issue absent from `blocked_by`/`depends_on`. Two write paths close this gap and they are layered, not mutually exclusive: `ll-issues format-check --fix --apply` backfills the edge reactively after the drift is detected (ENH-3247), while `/ll:refine-issue`'s Step 5a Dependency Classification rule (ENH-3284) can also write it proactively at deposit time, before this gap class would ever fire — `apply_link`'s idempotent, cycle-safe write makes either order safe.
- **stale_prose_dep** (FEAT-2849) — the body's prose dependency claim names a `done`/`cancelled` issue — the remedy is deleting the stale text, not adding an edge.
- **program_design_nonspecific** (ENH-2852) — the `## Program Design` section is present and non-boilerplate but not *specific*: it carries no signature-shaped line (`name(params) -> ret`, `field: type`), or names no `Call Path` anchor that resolves against the repo. Graded by `little_loops.issues.program_design.grade_program_design()`. **Opt-in per project and grandfathered**: the whole Program Design check — including the `missing`/`empty` entries for that section — is skipped unless the project has armed the gate by writing `.ll/program-design-cutover.json` (`{"sha": "<40-char SHA>", "date": "YYYY-MM-DD"}`), and is skipped per-issue when the issue's design timestamp (latest `/ll:refine-issue` Session Log entry, else `discovered_date`) is *strictly earlier* than the stamped date, or when frontmatter carries `program_design_not_applicable: true`. Only call-path anchors must resolve; new identifiers need only be signature-*shaped*, and a new identifier that happens to resolve never changes the verdict.
- **deprecated_key** (ENH-2876) — frontmatter carries a retired key (e.g. hand-authored `superseded_by`) or a coerced status synonym (e.g. `status: completed`), each paired with a mandatory prose reason from `little_loops.frontmatter.DEPRECATED_FRONTMATTER_KEYS`/`DEPRECATED_STATUS_VALUES`.
- **multi_frontmatter** (BUG-2955) — the issue carries more than one YAML frontmatter block in its header region (`little_loops.frontmatter.has_multiple_frontmatter_blocks()`), e.g. an outer `score_*` block prepended by the confidence-check scoring path followed by the canonical `id:`-bearing block.
- **testable** (ENH-2946, precision-tuned by ENH-2966) — the title + `## Summary` text trips 2+ distinct doc-only keyword signals (`doc`, `readme`, `changelog`, `typo`, etc.), word-boundary matched, while frontmatter has no explicit `testable:` key — an advisory that the issue is documentation-only. Advisory-only: it still renders in every output surface but does not fail `format-check`'s exit code (`FormatGaps.has_blocking_gaps`).
- **stale_file_ref** (ENH-2983; reworded BUG-3194) — a file path reference extracted from the body (`little_loops.text_utils.classify_issue_refs()`) classifies as `stale`: a `/`-qualified path that is not git-tracked. This includes a present-but-gitignored file (it may exist on disk, just not tracked), not only a moved/deleted one — the printed line states the actual predicate rather than implying the file is missing. Reporting only — a moved file can't be safely re-pointed without knowing intent. A slash-joined pair of filenames (`ARCHITECTURE.md/CONTRIBUTING.md`) or a brace-expanded span (`{a,b}/SKILL.md`) is not one path and classifies `unresolvable_form` instead (BUG-3194 Finding 2), never `stale_file_ref`. Only reported when `ref_index` is given.
- **ambiguous_file_ref** (ENH-2999) — a file path reference classifies as `ambiguous`: the unrooted suffix matches more than one tracked file after the host-adapter mirror tie-break, so it cannot be resolved without disambiguation. Distinct from `stale_file_ref` — the file wasn't deleted or moved, the reference just lacks enough path prefix to pick one of several real matches. Each entry names the candidate count and up to three candidate paths (elided with `…` beyond that). Only reported when `ref_index` is given.
- **unmarked_superseded_directive** (ENH-2995) — an issue's `### Codebase Research Findings` block contains a correction phrase from a closed detection list while none of `## Implementation Steps`/`### Files to Modify`/`## Acceptance Criteria` carries a `⚠ Superseded` marker.
- **duplicate_findings_block** (ENH-2993) — an H2 section carries more than one `### Codebase Research Findings` block; entries are `"<H2> (N)"`.
- **missing_behavior_parity** (ENH-3045) — a file ref in `## Summary`, `## Proposed Solution`, or `### Files to Modify` resolves (`classify_file_ref()`) and shares a line with a replacement keyword (`delete`, `remove`, `replace`, `rewrite`, `supersede`, `delegate`, and their inflections — same line only, no multi-line proximity window), while no `### Behavior Parity` subsection exists under `## Integration Map` (`_heading_bodies()`). Suppressed unconditionally by `behavior_parity_not_applicable: true` in frontmatter — a human decision mirroring `program_design_not_applicable`; `/ll:refine-issue` and `/ll:wire-issue` must never set it themselves. Only reported when `ref_index` is given.
- **soft_dep_hard_edge** (ENH-3046) — an ID in `blocked_by`/`depends_on` that the body describes with soft-dependency language (`soft dep`, `optional`, `nice to have`, `has not landed`) in the same blank-line-delimited paragraph as the ID. The hard structured edge contradicts the soft prose; remedy is moving the ID to `relates_to`, not deleting the prose (the soft language is usually the accurate statement). No suppression escape hatch. Only reported when `issue_statuses` is given.
- **malformed_dep_id** (BUG-3059) — an entry in `blocked_by`, `depends_on`, `blocks`, `relates_to`, or `supersedes` that is not a well-formed `TYPE-NNN` ID, most often a bare number (`depends_on: [3038]` instead of `[FEAT-3038]`). Distinct from `malformed_id`, which only checks the `id:` key against the filename. Not cosmetic: `DependencyGraph` matches IDs by exact string, so the edge is silently dropped from the graph. The optional `P<n>-` filename prefix is accepted and normalized.
- **stale_symbol_ref** (FEAT-3048/BUG-3063) — a backticked symbol claim (`little_loops.issues.symbol_claims.extract_symbol_claims()`) attributed to a cited file that itself resolves via `ref_index`, where the symbol does not resolve as a def-site (function/class) or module-level constant in that file (`symbol_exists_in_file()`) **and** does not resolve as a def-site in any other tracked file either (`symbol_resolves_elsewhere()`). Claims are extracted only from a current-state section allowlist (`## Summary`, `## Current Behavior`, `## Root Cause`, `## Context`, matched by H2 span via `_section_body()` — BUG-3063 A1, fence-aware since BUG-3202 so a quoted `##`-shaped line inside a code fence neither hijacks nor truncates the span) so a symbol named in a forward-looking section (`## Program Design`, `### Files to Modify`, `## Implementation Steps`, …) is never read as an existence assertion. Only reported when both `ref_index` and `symbol_index` are given; fails open for a cited file whose language is outside the resolver's supported set.
- **mislocated_symbol_ref** (BUG-3063) — the resolves-elsewhere sibling of `stale_symbol_ref`, subject to the same section allowlist: a symbol claim that doesn't resolve in the cited file but does resolve somewhere else in the repo (`symbol_resolves_elsewhere()`), backed by a repo-wide symbol -> files reverse index built eagerly in `build_symbol_index()`. A mis-attribution, not a stale claim — reported separately rather than folded into `stale_symbol_ref`. **Claim-drop noise filters (BUG-3194)**: a claim is dropped before it reaches either gap class — never rerouted to `stale_symbol_ref` — when its symbol fails the bare-form floor (`extract_symbol_claims()`: under 3 characters, or all-lowercase with no underscore, no internal capital, and no `()` suffix — `_passes_bare_form_floor()`, applied to both the bare and dotted-attr claim shapes) or when the symbol resolves in more than 8 tracked files other than the cited one (`claim_breadth_exceeds_cap()`, checked at the `check_format_gaps()` call site since it needs the reverse index).
- **stale_cli_flag** (FEAT-3048) — a backticked `` `ll-<tool> <subcommand> [--flag ...]` `` claim (`little_loops.issues.cli_claims.extract_cli_flag_claims()`) naming a subcommand or long flag the tool's argparse parser does not accept, per a `--help`-scraped surface index (`little_loops.issues.cli_surface.build_cli_surface_index()`). Only reported when `cli_index` is given; fails open for an unscrapable tool. Short flags are ignored (ambiguous in prose).
- **duplicate_heading** (ENH-3247) — the same `###` heading text appears more than once under one `##` parent, e.g. two `### Files to Modify` under `## Integration Map` after a retry pass. Excludes `### Codebase Research Findings`, already owned by `duplicate_findings_block`. Fence-masked.
- **empty_provenance_stub** (ENH-3247) — an `` _Added by `/ll:refine-issue` — DATE — based on codebase analysis:_ `` provenance line with no bullet or other content before the next heading or the next stub. Fence-masked like `duplicate_heading`.
- **template_placeholders** (ENH-3244) — a literal unfilled template placeholder (e.g. `TBD - requires codebase analysis`, `[Major phase 1]`) still present in the section whose `creation_template` emits it. Section-scoped, fence- and inline-backtick-masked, and excludes `## Program Design`. Detection only — no `--fix` handler is registered.
- **unapplied_decision** (ENH-3256) — an issue's `> **Selected:**` callout in `## Proposed Solution` names a winning option while a backticked identifier unique to a *rejected* option (`REJ - SEL`, the discriminating identifier set) still appears, unmarked, in `## Proposed Solution`, `## Program Design`, `## Implementation Steps`, `### Files to Modify`, or `## Acceptance Criteria`. A recorded decision is not proof the decision was *applied*. Options are enumerated from `## Proposed Solution` only, the selected block is identified by matching the callout's option title against each option heading (not by presence-only markers, which cannot distinguish selected from rejected), and a mention is exempt when `⚠ Superseded` appears in the same paragraph. Report-only; caps `/ll:confidence-check` Criterion C, never a hard override.
- **priority_drift** (BUG-3286) — the filename's `P<n>-` prefix and the frontmatter `priority:` key are both present and disagree. Scoped to the file's own name and frontmatter — no cross-file comparison — and silent when either source is absent (an absent frontmatter `priority:` is the normal state for most of a corpus, not drift). The filename prefix is authoritative (`resolve_priority()`); the remedy is `ll-issues prioritize --apply`, which reconciles both sources in one operation.

**Parameters:**
- `issue_path` - Path to the issue markdown file
- `templates_dir` - Optional override for the templates directory
- `issue_statuses` - Optional `issue_id -> status` mapping used to distinguish `prose_dep_drift` from `stale_prose_dep`. When `None` (default), both prose-dependency gap classes fail open (report no gaps) — matching this module's existing convention.
- `ref_index` - Optional `little_loops.text_utils.RefIndex` (built once per invocation via `build_ref_index()`) used to resolve file path references cited in the body. When `None` (default), no `stale_file_ref`/`ambiguous_file_ref`/`missing_behavior_parity` gaps are reported.
- `symbol_index` - Optional `little_loops.issues.symbol_claims.SymbolIndex` (built once per invocation via `build_symbol_index()`, which also eagerly builds the BUG-3063 C reverse index) used to resolve symbol claims. When `None` (default), no `stale_symbol_ref`/`mislocated_symbol_ref` gaps are reported.
- `cli_index` - Optional `little_loops.issues.cli_surface.CliSurfaceIndex` (built once per invocation via `build_cli_surface_index()`) used to resolve CLI-flag claims. When `None` (default), no `stale_cli_flag` gaps are reported.

**Returns:** A `FormatGaps` instance. Fails open (no gaps reported) when the file is unreadable, its type cannot be determined, or its template cannot be loaded — mirroring `is_formatted()`'s fail-open behavior.

#### extract_prose_deps

```python
def extract_prose_deps(body: str) -> set[str]
```

Extracts issue IDs claimed as dependencies in prose (FEAT-2849,
`little_loops/issues/prose_deps.py`). Matches canonical phrasings only —
"Depends on `<ID>`", "Blocked by `<ID>`", "Requires `<ID>`", their unambiguous
synonyms ("blocked on", "gated on", "waiting on", "contingent on", "predicated
on", "depends upon"), and IDs listed
in the body of a `## Blocked By` section — normalizing `P\d-TYPE-NNN` /
`TYPE-NNN` forms to `TYPE-NNN` and stripping case. Ignores IDs inside fenced
code blocks. Deliberately conservative: recall matters less than not crying
wolf — temporal/narrative phrasings ("after `<ID>`", "once `<ID>`", "pending
`<ID>`", "needs `<ID>`") are **not** matched, since in real issue bodies they
overwhelmingly describe history rather than a live edge, and a wrong
`blocked_by` silently hides an issue from `ll-issues next-issue`/`next-issues`.
Callers pass the
issue *body only* (post `strip_frontmatter()`) — this
function does not parse frontmatter itself.

**Parameters:**
- `body` - Issue markdown body (frontmatter already stripped)

**Returns:** Set of normalized issue IDs, e.g. `{"FEAT-109"}`.

#### superseded_marker_count

```python
def superseded_marker_count(issue_path: Path) -> int
```

Count `⚠ Superseded` markers (ENH-2995's in-place annotation convention)
present inside the three directive sections `/ll:reconcile-issue` rewrites:
`## Implementation Steps`, `### Files to Modify`, `## Acceptance Criteria`.

The public marker-*presence* surface (ENH-2992), and the inverse of
`check_format_gaps`'s `unmarked_superseded_directive` gap class — that one
reports correction language with no marker (a refine-did-not-mark defect),
while this reports a standing contradiction awaiting reconcile. Reuses the
same private `_SUPERSEDED_MARKER_PREFIX` / `_SUPERSEDED_DIRECTIVE_SECTIONS` /
`_heading_bodies()` primitives so the two can never disagree about what counts
as a marker (the `count_open_questions_in_sections()` private-helper/
public-wrapper pairing).

Surfaced as the `superseded_marker_count` key on `ll-issues format-check
<ID> --format json`, which `autodev.yaml`'s `check_reconcile_needed` reads as
its contradiction predicate. Returns `0` for a missing or unreadable file —
the FSM predicate must never fail the loop on a vanished issue.

**Parameters:**
- `issue_path` - Path to the issue markdown file

**Returns:** Marker count across the three directive sections (0 when none).

#### locate_enumerable_options

```python
def locate_enumerable_options(content: str) -> LocatedOptions
```

Deterministic (no LLM) re-implementation of `skills/decide-issue/SKILL.md` Phase 3's
option-extraction patterns (ENH-2443), widened to return spans rather than just a count
(ENH-2950). Backs both `ll-issues check-decidable` (boolean gate, the FSM-facing
companion to `/ll:decide-issue --validate-only`) and `ll-issues locate-options --json`
(the full data frontend `/ll:decide-issue` Phase 3/3b reads instead of re-implementing
this precedence chain in prose) — one code path, two CLI frontends, mirroring how
`check_format_gaps` backs `ll-issues format-check`.

Tries, in precedence order: the first `_OPTION_PATTERNS` tier (`### Option X` headers →
`section_header`, `**Option X**` bold labels → `bold_label`, numbered `N. **Option`/
`...approach` items → `numbered`, `- (x)`/`- Option X` bullets → `bullet`) with any match
in `## Proposed Solution`; widening to `## Codebase Research Findings` / `##
Implementation Status` when that yields 0; then a whole-document H2 scan (ENH-2821); then
the `decision_rules_numbered` structural heuristic (`_locate_decision_rules_numbered`,
BUG-3293) — 2+ bold-numbered items (`N. **label**`) under `## Program Design → ###
Decision Rules` specifically, not the whole-document fallback's unscoped `_OPTION_PATTERNS`
tiers, because a naive corpus-wide widening of the `numbered` tier's bold alternative was
measured to false-positive on 77% of the files it newly matched (ordinary bold-led step
lists are this repo's dominant list convention); scoping to just this one subsection and
requiring 2+ matches shrinks that to 2 false positives out of 3 gains corpus-wide — accepted
deliberately, since this probe is a cheap pre-check whose false positives cost one harmless
`/ll:refine-issue` detour, not a wrong final decision; then, as a final fallback tier when
nothing else has matched anywhere in the document, the Pattern E "un-preferenced decision
directive" heuristic (`_locate_directive_alternatives`, ENH-2936, reported as
`pattern="provisional_e"`) — an imperative decide-marker ("decide before implementation", "do
not leave unaddressed", "must be decided", "pick one", "must be made before implementation")
co-occurring within 3 lines of a 2+-alternative "X or Y"/"X versus Y" shape, with no stated
preference, scanned over `## Scope Boundaries` / `## Proposed Change` / `## Proposed Solution` /
`## Open Questions` / `## Program Design` (BUG-3293 added the last of these, plus the "must be
made before implementation" and "versus" alternatives — measured to add exactly one
corpus-wide match, zero spurious). A Pattern E match always reports `count=2` with a single
`LocatedOption` spanning the matched window — it only proves a decision exists, not how many
alternatives, so individual alternatives are not split out.

BUG-3287: the Pattern E directive probe additionally runs **alongside** the tier scan and the
whole-document H2 scan, not only as the terminal fallback — a document holding both an
enumerated option set and a separate prose decision directive reports both. When a tier or the
H2 scan wins, a co-located directive is attached as `residual_directive` rather than replacing
the winning result — `count`/`pattern`/`heading` stay byte-identical to the tier-only result
(the directive would otherwise silently preempt and hide a second, distinct decision point). A
`decision_rules_numbered` win explicitly sets `residual_directive = None` — that stage is
out of scope for the directive probe (measured 0/0 corpus impact; see BUG-3287).

**Parameters:**
- `content` - Full issue file text

**Returns:** A `LocatedOptions` dataclass:
- `count: int` - Number of options found (0 when there is nothing to decide)
- `pattern: str | None` - Which tier fired (`section_header` | `bold_label` | `numbered` | `bullet` | `decision_rules_numbered` | `provisional_e`), or `None` when `count == 0`
- `heading: str | None` - The section the options were found under, or `None` when `count == 0`
- `options: list[LocatedOption]` - Per-option spans; each `LocatedOption` has `label: str`, `text: str`, `start_line: int`, `end_line: int` (1-indexed), and a `to_dict()` for JSON serialization. `LocatedOptions.to_dict()` nests the full option list.
- `residual_directive: LocatedOptions | None` - A co-located Pattern E directive preempted by a tier/H2-scan win (BUG-3287), or `None`. Always `None` on the nested object itself (no recursion).

#### count_enumerable_options

```python
def count_enumerable_options(content: str) -> int
```

Thin wrapper: `return locate_enumerable_options(content).count`. Kept for callers that
only need the count, not the spans — see `locate_enumerable_options` above for the
underlying pattern precedence.

**Parameters:**
- `content` - Full issue file text

**Returns:** Count of enumerable options found (0 when there is nothing to decide).

#### count_unresolved_options

```python
def count_unresolved_options(content: str) -> int
```

Coverage-aware sibling of `count_enumerable_options` (ENH-2446). Counts only the
`### Option X` / `**Option X: ...**` blocks in `## Proposed Solution` (with the same
fallback widening to `## Codebase Research Findings` / `## Implementation Status`) that
LACK a resolution marker — i.e. neither `> **Selected:**` callout nor `### Decision Rationale`
subsection within the block's boundary. An issue with resolved options PLUS unresolved
free-form questions is the coverage gap this probe catches (the count-based
`count_enumerable_options` returns 2 in that case; this returns 0). Backs the
`ll-issues check-open-questions` subcommand alongside `count_open_questions_in_sections`.

**Parameters:**
- `content` - Full issue file text

**Returns:** Count of unresolved (unmarked) option blocks. 0 means every enumerable
option in the issue has a `> **Selected:**` or `### Decision Rationale` marker.

#### locate_unresolved_decisions

```python
def locate_unresolved_decisions(
    content: str, *, include_approximate_tiers: bool = False
) -> list[DecisionGroup]
```

BUG-3278: the decision-*group*-aware sibling of `locate_unresolved_options`, and **not
interchangeable with it**. `locate_unresolved_options` resolves per option *block* — Phase 7a of
`/ll:decide-issue` marks only the winning option, so every losing option in a correctly-decided
group reads as unresolved (a 3-option group with one winner reports 2, not 0). This function
resolves per decision *group* — a maximal contiguous run of same-tier option blocks, or one
Pattern E directive window — via `DecisionGroup`/`_iter_decision_groups`/`is_group_resolved`. A
group is resolved when any member option's own span carries a `> **Selected:**` callout, or the
group's enclosing section carries a `### Decision Rationale` subsection AND holds exactly one
group (the single-group restriction — an unrestricted section-level check would let deciding one
group in a multi-group section silently resolve every sibling group by side effect). Backs `ll-issues
check-unresolved-decisions`, the gate `/ll:decide-issue` Phase 7b and Phase 3b step 4 run before
clearing `decision_needed`.

Under the default `include_approximate_tiers=False`, only the `section_header`/`bold_label` tiers
are recognized — reproducing today's group set over Patterns 1-2 only, so the ENH-2446
conservatism `check-open-questions`/`check_open_question_progress` depend on is undisturbed.
`include_approximate_tiers=True` additionally recognizes the `numbered`/`bullet` tiers and probes
for a co-located Pattern E directive (sourced from `LocatedOptions.residual_directive`, not a
second `_locate_directive_alternatives` call). At most one `provisional_e` group is detectable per
document — a hard limit of the shared directive probe, which returns on its first matching window.
Never emits a `decision_rules_numbered` group (BUG-3293's Program Design → Decision Rules block):
those are the issue's own settled design rulings, not mutually exclusive alternatives.

**Parameters:**
- `content` - Full issue file text
- `include_approximate_tiers` - Widen to `numbered`/`bullet` tiers plus the Pattern E directive probe (default `False`)

**Returns:** `DecisionGroup` list — `heading: str | None`, `tier: str`, `options: list[LocatedOption]`,
`start_line: int`, `end_line: int` — for every group that fails `is_group_resolved`. Empty when no
unresolved decision point remains.

#### count_open_questions_in_sections

```python
def count_open_questions_in_sections(content: str) -> int
```

Counts unresolved open questions in `## Edge Cases`, `## Confidence Check Notes`, and
`## Open Questions` sections (ENH-2446). An item is an "open question" if it is a
bullet or numbered list line carrying an open-question signal (`Q:` prefix, ends with
`?`, or contains `open question`, `needs decision`, `decision needed`, `open decision`,
`unresolved decision`, or `decision point`) AND lacks a resolved-question marker
(`✅ RESOLVED`, `✔ RESOLVED`, `**RESOLVED**`, or `> **RESOLVED**`). Mirrors the resolved-
question vocabulary already defined in `skills/decide-issue/SKILL.md:197` so both the
deterministic probe and the LLM skill read the same markers.

**Parameters:**
- `content` - Full issue file text

**Returns:** Count of unresolved open questions across the three target sections. 0 means
every bullet/numbered item is either resolved or not an open question.

#### QuestionGaps

```python
@dataclass
class QuestionGaps:
    unresolved_options: list[str]
    open_questions: list[str]
```

Typed return-value mirroring the two-field-per-category `FormatGaps` convention
(ENH-2446) — note `FormatGaps` itself has since grown to seven categories
(FEAT-2849) that `QuestionGaps` does not mirror; only the dataclass shape
(`list[str]` fields + derived `has_gaps` + `to_dict()`) is shared, not the gap
count. Each list carries the respective markers/headings; `has_gaps` is
derived; `to_dict()` serializes for `--format json`. Companion to `FormatGaps`
for the coverage-aware decidability probe.

#### find_issues

```python
def find_issues(
    config: BRConfig,
    category: str | None = None,
    skip_ids: set[str] | None = None,
    only_ids: list[str] | set[str] | None = None,
    type_prefixes: set[str] | None = None,
    status_filter: set[str] | None = None,
    *,
    skip_blocked: bool = False,
) -> list[IssueInfo]
```

Find all issues matching criteria, sorted by priority.

**Parameters:**
- `config` - Project configuration
- `category` - Optional category to filter (e.g., `"bugs"`)
- `skip_ids` - Issue IDs to skip
- `only_ids` - If provided, only include these issue IDs. When a list, results are returned in list order; when a set, results are sorted by priority.
- `type_prefixes` - If provided, only include issues whose ID starts with one of these prefixes (e.g., `{"BUG", "ENH"}`)
- `status_filter` - If provided, only include issues whose status is in this set. When `None` (default), skips `done`/`cancelled`/`deferred` issues, preserving all existing caller behaviour.
- `skip_blocked` - Keyword-only. When `True` (ENH-2436), exclude issues whose `Blocked By` references a non-terminal (`done`/`cancelled`) issue. Default `False` is byte-identical to prior behaviour — no existing caller is affected.

**Returns:** List of `IssueInfo` sorted by priority

**Example:**
```python
from little_loops.issue_parser import find_issues

issues = find_issues(config, category="bugs")
for issue in issues:
    print(f"{issue.priority} {issue.issue_id}: {issue.title}")

# Skip blocked issues (ENH-2436)
ready = find_issues(config, skip_blocked=True)
```

#### find_issues_for_graph

```python
def find_issues_for_graph(
    config: BRConfig,
    category: str | None = None,
) -> list[IssueInfo]
```

Build the non-terminal superset needed for correct `DependencyGraph`
construction (BUG-2897). `find_issues()`'s default status filter hides
`deferred` issues — correct for work-selection callers, but wrong for graph
building: a `blocked_by`/`depends_on` edge pointing at a `deferred` issue
must not be silently dropped just because the blocker is absent from the
graph. Only terminal statuses (`done`, `cancelled`) should resolve a
dependency edge. Callers should build the graph from this superset, then
apply their own display-narrowing filter (e.g. `status in _OPEN_STATUSES`)
to the ordered/display list afterward — the same "build wide, filter narrow"
shape `find_issues(skip_blocked=True)` already uses internally.

**Example:**
```python
from little_loops.dependency_graph import DependencyGraph
from little_loops.issue_parser import find_issues_for_graph

graph_issues = find_issues_for_graph(config)
graph = DependencyGraph.from_issues(graph_issues)
```

#### find_highest_priority_issue

```python
def find_highest_priority_issue(
    config: BRConfig,
    category: str | None = None,
    skip_ids: set[str] | None = None,
    only_ids: set[str] | None = None,
    type_prefixes: set[str] | None = None,
) -> IssueInfo | None
```

Find the highest priority issue.

**Parameters:**
- `config` - Project configuration
- `category` - Optional category to filter
- `skip_ids` - Issue IDs to skip
- `only_ids` - If provided, only include these issue IDs
- `type_prefixes` - If provided, only include issues with these type prefixes

**Returns:** Highest priority `IssueInfo` or `None` if no issues found

#### get_next_issue_number

```python
def get_next_issue_number(config: BRConfig, category: str | None = None) -> int
```

Determine the next globally unique issue number across all issue types.

Scans ALL issue directories (active and any legacy completed/deferred) to find the highest existing number across ALL issue types (BUG, FEAT, ENH, EPIC). Issue numbers are globally unique regardless of type.

**Parameters:**
- `config` - Project configuration
- `category` - Unused; kept for backwards compatibility

**Returns:** Next available issue number (globally unique across all types)

#### slugify

```python
def slugify(text: str) -> str
```

Convert text to slug format for filenames.

**Parameters:**
- `text` - Text to convert

**Returns:** Lowercase slug with hyphens

---

## little_loops.issue_template

Issue template assembly using per-type section definition files.

### resolve_templates_dir

Return the templates directory using 4-tier precedence lookup.

```python
def resolve_templates_dir(config: BRConfig) -> Path
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `config` | `BRConfig` | Project configuration |

**Returns:** `Path` — resolved templates directory

**Precedence (highest to lowest):**

1. `config.issues.templates_dir` — explicit config override
2. `<project_root>/.ll/templates/` — project-deployed copy (written by `ll-init --deploy-templates`)
3. Bundled in-package `templates/` (always available)

Skills and commands that need template JSON should invoke `ll-issues sections <type>` (which calls this internally) rather than reading the template path directly. This ensures project-local overrides propagate correctly.

**Example:**

```python
from little_loops.issue_template import resolve_templates_dir
from little_loops.config import load_config

config = load_config()
templates_dir = resolve_templates_dir(config)
# Returns .ll/templates/ if deployed, otherwise bundled templates/
```

### load_issue_sections

Load per-type sections JSON from the resolved templates directory.

```python
def load_issue_sections(issue_type: str, templates_dir: Path | None = None) -> dict[str, Any]
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `issue_type` | `str` | Issue type prefix (`BUG`, `FEAT`, `ENH`, `EPIC`) |
| `templates_dir` | `Path \| None` | Optional override path; defaults to bundled `templates/` |

**Returns:** `dict[str, Any]` — parsed JSON template data

**Raises:** `FileNotFoundError` if the per-type sections file does not exist.

---

## little_loops.cli.issues.create

Atomic single-issue creation (`ll-issues create`) — allocates a globally unique ID and writes the file under a lock, exclusive-create only.

```python
@dataclass
class IssueSpec:
    type: str
    title: str
    priority: str = "P2"
    body: str | None = None
    parent: str | None = None
    labels: list[str] = field(default_factory=list)
    stage: bool = False
    variant: str = "minimal"
```

```python
@dataclass
class CreatedIssue:
    id: str
    path: Path

    def to_dict(self) -> dict[str, str]: ...
```

### create_issue

```python
def create_issue(config: BRConfig, spec: IssueSpec, now: datetime | None = None) -> CreatedIssue
```

Allocates the next globally unique issue number under a single `acquire_lock` hold (retrying on filesystem collision), slugs the title, selects the type directory from `spec.type`, and writes frontmatter + template body via exclusive-create (`open(path, "x")`) so a racer that bypasses the lock fails loudly instead of clobbering an existing file. If `spec.parent` is set, the child's frontmatter always gets `parent:`, and a bullet is appended to the parent's `## Children` section if one exists (silently skipped for non-EPIC parents).

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `config` | `BRConfig` | Project configuration |
| `spec` | `IssueSpec` | Issue fields to create from |
| `now` | `datetime \| None` | Injectable current time; defaults to `datetime.now(UTC)` |

**Returns:** `CreatedIssue` — the new issue's ID and path

**Raises:** `ValueError` if `spec.type` has no configured category; `FileExistsError` if 5 collision retries are exhausted.

---

## little_loops.cli.issues.scaffold_epic

Creates an EPIC and its pre-wired child stubs atomically (`ll-issues scaffold-epic`).

```python
@dataclass
class ChildSpec:
    type: str
    title: str
    priority: str
    summary: str = ""
```

### scaffold_epic

```python
def scaffold_epic(
    config: BRConfig,
    title: str,
    children: list[ChildSpec],
    priority: str = "P2",
    stage: bool = False,
    now: datetime | None = None,
) -> tuple[CreatedIssue, list[CreatedIssue]]
```

Assembles every child and EPIC file's content in memory first, then writes them all. Each child is wired with `parent: EPIC-N` and a bullet in the EPIC's `## Children` section; children inherit `priority` unless overridden per-child. If `stage` is `True`, every created file is `git add`ed in one call on success. On any failure, every path this call created is unlinked and the exception re-raised — since every touched file was just created, `Path.unlink()` is a complete undo.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `config` | `BRConfig` | Project configuration |
| `title` | `str` | EPIC title |
| `children` | `list[ChildSpec]` | Child issues to scaffold under the EPIC |
| `priority` | `str` | Applied to the EPIC; inherited by children unless overridden |
| `stage` | `bool` | If `True`, stage every created file with `git add` |
| `now` | `datetime \| None` | Injectable current time |

**Returns:** `tuple[CreatedIssue, list[CreatedIssue]]` — the created EPIC and its created children, in the order given

**Raises:** `ValueError` if any child's type has no configured category.

---

## little_loops.cli.issues.link_epics

Proposal-only orphan-to-EPIC assignment and orphan clustering (`ll-issues link-epics --mode assign|synthesize`). An "orphan" is an open BUG/FEAT/ENH issue with both `parent:` and `epic:` unset.

```python
@dataclass
class EpicProposal:
    orphan_id: str
    epic_id: str
    score: float
    tier: str

    def to_dict(self) -> dict: ...  # rounds score to 3 decimals
```

```python
@dataclass
class ClusterProposal:
    member_ids: list[str]
    placeholder_title: str
    modal_priority: str
    pairwise_min_score: float

    def to_dict(self) -> dict: ...  # sorts member_ids, rounds pairwise_min_score to 3 decimals
```

### propose_assignments

```python
def propose_assignments(
    orphans: list[IssueInfo], epics: list[IssueInfo], threshold: float
) -> list[EpicProposal]
```

Scores every orphan × EPIC pair via title word-overlap (`little_loops.text_utils.calculate_word_overlap`/`extract_words`), filtered by `threshold`.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `orphans` | `list[IssueInfo]` | Candidate orphan issues |
| `epics` | `list[IssueInfo]` | Candidate open EPIC issues |
| `threshold` | `float` | Minimum score for a proposal to be included |

**Returns:** `list[EpicProposal]` sorted by score descending, then `orphan_id`, then `epic_id` (deterministic tiebreak for equal-score pairs).

### synthesize_clusters

```python
def synthesize_clusters(orphans: list[IssueInfo], min_score: float) -> list[ClusterProposal]
```

Union-find clusters orphans on pairwise title word-overlap ≥ `min_score`.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `orphans` | `list[IssueInfo]` | Candidate orphan issues |
| `min_score` | `float` | Minimum pairwise score for an edge to union two orphans |

**Returns:** `list[ClusterProposal]` for clusters with 2+ members (singletons not proposed), sorted by member count descending then first `member_id`.

### apply_assignment

```python
def apply_assignment(proposal: EpicProposal, *, orphan_path: Path, epic_path: Path) -> None
```

Writes the orphan-side frontmatter (both `parent:` and `epic:` — the corpus convention is both fields, not `parent:` alone) and appends to the EPIC-side `## Children` section. Idempotent: re-running with the same proposal is a no-op on the EPIC body if the child is already listed. `--apply` is unsupported for `synthesize` mode — EPIC creation belongs to `scaffold_epic`, not this subcommand.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `proposal` | `EpicProposal` | Accepted assignment |
| `orphan_path` | `Path` | Path to the orphan issue file |
| `epic_path` | `Path` | Path to the EPIC issue file |

---

## little_loops.dependency_graph

Dependency graph construction for issue scheduling based on `Blocked By` relationships.

### DependencyGraph

Represents a directed acyclic graph (DAG) of issue dependencies.

```python
from little_loops.dependency_graph import DependencyGraph
from little_loops.issue_parser import find_issues
from little_loops.config import BRConfig
from pathlib import Path

config = BRConfig(Path.cwd())
issues = find_issues(config)
graph = DependencyGraph.from_issues(issues)

# Get issues ready to process (no active blockers)
ready = graph.get_ready_issues()

# Get execution waves for parallel processing
waves = graph.get_execution_waves()
for i, wave in enumerate(waves, 1):
    print(f"Wave {i}: {[issue.issue_id for issue in wave]}")
```

#### Construction

```python
@classmethod
def from_issues(
    cls,
    issues: list[IssueInfo],
    completed_ids: set[str] | None = None,
    all_known_ids: set[str] | None = None,
) -> DependencyGraph
```

Build graph from list of issues.

**Parameters:**
- `issues` - List of `IssueInfo` objects; both `blocked_by` and `blocks` fields are consumed to build edges
- `completed_ids` - Set of completed issue IDs (treated as resolved)
- `all_known_ids` - Set of all issue IDs that exist on disk; references to these are silently skipped (not warned) even if not in the graph

**Returns:** Constructed `DependencyGraph`

A blocker is only treated as satisfied if it has a terminal status (`done`/
`cancelled`), either via `completed_ids` or by being absent from `issues`
because the caller's own list excluded terminal statuses. A blocker that is
absent from `issues` for any *other* reason — most commonly a `deferred`
issue omitted by a narrow status filter — is **not** satisfied; the edge is
silently dropped instead (BUG-2897). Build `issues` from
`issue_parser.find_issues_for_graph()` rather than `find_issues()`'s default
filter when constructing a graph.

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `issues` | `dict[str, IssueInfo]` | Mapping of issue ID to `IssueInfo` |
| `blocked_by` | `dict[str, set[str]]` | Mapping of issue ID to blocker IDs |
| `blocks` | `dict[str, set[str]]` | Reverse mapping (what each issue blocks) |
| `depends_on_edges` | `dict[str, set[str]]` | Mapping of issue ID to soft-prerequisite issue IDs |

#### Methods

##### get_ready_issues

```python
def get_ready_issues(self, completed: set[str] | None = None) -> list[IssueInfo]
```

Return issues whose blockers are all completed.

**Parameters:**
- `completed` - Set of completed issue IDs

**Returns:** List of `IssueInfo` for ready issues, sorted by priority

##### get_execution_waves

```python
def get_execution_waves(self, completed: set[str] | None = None) -> list[list[IssueInfo]]
```

Return issues grouped into parallel execution waves.

Wave 1: All issues with no blockers (or blockers already completed)
Wave 2: Issues whose blockers are all in wave 1
Wave N: Issues whose blockers are all in waves 1..N-1

**Parameters:**
- `completed` - Set of already-completed issue IDs

**Returns:** List of waves, each wave is a list of issues that can run in parallel

**Raises:** `ValueError` if graph contains cycles

**Example:**
```python
graph = DependencyGraph.from_issues(issues)
waves = graph.get_execution_waves()

# Wave 1: [FEAT-001, BUG-001]  - no blockers
# Wave 2: [FEAT-002, FEAT-003] - blocked by FEAT-001
# Wave 3: [FEAT-004]           - blocked by FEAT-002, FEAT-003
```

##### topological_sort

```python
def topological_sort(self) -> list[IssueInfo]
```

Return issues in dependency order (Kahn's algorithm). Both `blocked_by`
(hard) and `depends_on` (soft) edges constrain ordering — an issue is
scheduled only after every prerequisite named by either field, not
`blocked_by` alone (BUG-2848).

**Returns:** List of `IssueInfo` in topological order

**Raises:** `ValueError` if graph contains cycles

##### has_cycles

```python
def has_cycles(self) -> bool
```

Check if the graph contains cycles.

**Returns:** `True` if cycles exist

##### detect_cycles

```python
def detect_cycles(self) -> list[list[str]]
```

Find all cycles in the graph using DFS.

**Returns:** List of cycles, each cycle is a list of issue IDs

### WaveContentionNote

Annotation returned when `refine_waves_for_contention()` splits a wave due to file overlap between issues.

```python
@dataclass
class WaveContentionNote:
    contended_paths: list[str]   # Files that caused the split
    sub_wave_index: int          # 0-based index of this sub-wave within the parent wave
    total_sub_waves: int         # Total sub-waves the parent wave was split into
    parent_wave_index: int = 0   # 0-based index of the original unsplit wave
```

### refine_waves_for_contention

```python
def refine_waves_for_contention(
    waves: list[list[IssueInfo]],
    *,
    config: DependencyMappingConfig | None = None,
) -> tuple[list[list[IssueInfo]], list[WaveContentionNote | None]]
```

Refine execution waves by splitting issues that would edit the same files. Uses greedy graph coloring so no two issues in the same sub-wave modify the same files. Called automatically by `ll-sprint` before each wave is dispatched to parallel workers.

**Parameters:**
- `waves` — Execution waves from `DependencyGraph.get_execution_waves()`
- `config` — Optional `DependencyMappingConfig` for file-hint extraction tuning

**Returns:** `(refined_waves, contention_notes)` — parallel lists of equal length. `contention_notes[i]` is `None` for waves that were not split, and a `WaveContentionNote` for sub-waves that were.

**Example:**
```python
from little_loops.dependency_graph import DependencyGraph, refine_waves_for_contention

graph = DependencyGraph.from_issues(issues)
waves = graph.get_execution_waves()
refined, notes = refine_waves_for_contention(waves)

for i, (wave, note) in enumerate(zip(refined, notes)):
    if note:
        print(f"Wave {i}: sub-wave {note.sub_wave_index+1}/{note.total_sub_waves} "
              f"(split on: {note.contended_paths})")
```

---

## little_loops.dependency_mapper

Cross-issue dependency discovery and mapping. Analyzes active issues to discover potential dependencies based on file overlap and validates existing dependency references for integrity.

This is a sub-package split into focused modules:
- `dependency_mapper.models` — data models (`DependencyProposal`, `ParallelSafePair`, `ValidationResult`, `DependencyReport`, `FixResult`)
- `dependency_mapper.analysis` — conflict scoring and dependency analysis
- `dependency_mapper.formatting` — report and graph formatting
- `dependency_mapper.operations` — file mutation operations (apply/fix)

All names are re-exported from `little_loops.dependency_mapper` for backwards compatibility.

Complements `dependency_graph`:
- `dependency_graph` = execution ordering from existing `Blocked By` data
- `dependency_mapper` = discovery and proposal of new relationships

### DependencyProposal

A proposed dependency relationship between two issues.

```python
@dataclass
class DependencyProposal:
    """A proposed dependency relationship between two issues."""
    source_id: str              # Issue that would be blocked
    target_id: str              # Issue that would block (the blocker)
    reason: str                 # Category of discovery method
    confidence: float           # Score from 0.0 to 1.0
    rationale: str              # Human-readable explanation
    overlapping_files: list[str]  # Files referenced by both issues
    conflict_score: float       # Semantic conflict score from 0.0 to 1.0
```

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `source_id` | `str` | Issue that would be blocked |
| `target_id` | `str` | Issue that would block (the blocker) |
| `reason` | `str` | Category of discovery method (e.g., "file_overlap") |
| `confidence` | `float` | Score from 0.0 to 1.0 |
| `rationale` | `str` | Human-readable explanation |
| `overlapping_files` | `list[str]` | Files referenced by both issues |
| `conflict_score` | `float` | Semantic conflict score (0.0 = parallel-safe, 1.0 = definite conflict). Default: 0.5 |

### ParallelSafePair

A pair of issues that share files but can safely run in parallel (conflict score below threshold).

```python
@dataclass
class ParallelSafePair:
    """A pair of issues that share files but can safely run in parallel."""
    issue_a: str                # First issue ID
    issue_b: str                # Second issue ID
    shared_files: list[str]     # Files referenced by both issues
    conflict_score: float       # Semantic conflict score (< 0.4)
    reason: str                 # Why these are parallel-safe
```

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `issue_a` | `str` | First issue ID |
| `issue_b` | `str` | Second issue ID |
| `shared_files` | `list[str]` | Files referenced by both issues |
| `conflict_score` | `float` | Semantic conflict score (always < 0.4) |
| `reason` | `str` | Explanation of why the pair is parallel-safe (e.g., "Different sections (body vs header)") |

### ValidationResult

Result of validating existing dependency references.

```python
@dataclass
class ValidationResult:
    """Result of validating existing dependency references."""
    broken_refs: list[tuple[str, str]]             # (issue_id, missing_ref_id) for blocked_by refs
    missing_backlinks: list[tuple[str, str]]       # (issue_id, should_have_backlink_from)
    cycles: list[list[str]]                        # Cycle paths
    stale_completed_refs: list[tuple[str, str]]    # (issue_id, completed_ref_id)
    broken_depends_on_refs: list[tuple[str, str]]  # (issue_id, missing_ref_id) for depends_on refs
    broken_relates_to_refs: list[tuple[str, str]]  # (issue_id, missing_ref_id) for relates_to refs

    @property
    def has_issues(self) -> bool
```

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `broken_refs` | `list[tuple[str, str]]` | References to nonexistent issues in `blocked_by` or `duplicate_of` |
| `missing_backlinks` | `list[tuple[str, str]]` | Asymmetric `Blocked By`/`Blocks` pairs |
| `cycles` | `list[list[str]]` | Circular dependency chains |
| `stale_completed_refs` | `list[tuple[str, str]]` | References to completed issues |
| `broken_depends_on_refs` | `list[tuple[str, str]]` | References to nonexistent issues in `depends_on` |
| `broken_relates_to_refs` | `list[tuple[str, str]]` | References to nonexistent issues in `relates_to` |

**Properties:**
- `has_issues` - Returns `True` if any validation problems were found

### DependencyReport

Complete dependency analysis report combining proposals, parallel-safe pairs, and validation.

```python
@dataclass
class DependencyReport:
    """Complete dependency analysis report."""
    proposals: list[DependencyProposal]
    parallel_safe: list[ParallelSafePair]
    validation: ValidationResult
    issue_count: int
    existing_dep_count: int
```

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `proposals` | `list[DependencyProposal]` | Proposed new dependency relationships (conflict score >= 0.4) |
| `parallel_safe` | `list[ParallelSafePair]` | File-overlapping pairs safe to run in parallel (conflict score < 0.4) |
| `validation` | `ValidationResult` | Validation results for existing dependencies |
| `issue_count` | `int` | Total issues analyzed |
| `existing_dep_count` | `int` | Number of existing dependency edges |

### FixResult

Result of `operations.fix_dependencies()` — auto-repairing broken/stale refs
and missing backlinks, plus reporting (and optionally cutting) cycles.

```python
@dataclass
class FixResult:
    """Result of auto-fixing dependency validation issues."""
    changes: list[str]         # Human-readable descriptions of each fix applied
    modified_files: set[str]   # File paths that were modified
    skipped_cycles: int        # Cycles left unbroken (no --break-cycles, or dry_run)
    cycles: list[list[str]]    # Cycles detected this run, each a closed walk of issue IDs
```

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `changes` | `list[str]` | Human-readable descriptions of each fix applied (or, for cycles without `--break-cycles`, each cycle's edges plus its suggested cut) |
| `modified_files` | `set[str]` | File paths that were modified |
| `skipped_cycles` | `int` | Number of cycles left unbroken — all of them when `break_cycles=False`, or when `dry_run=True` |
| `cycles` | `list[list[str]]` | Cycles detected this run, each a closed walk of issue IDs (e.g. `["A", "B", "A"]`), for programmatic access beyond `changes` |

### Functions

#### extract_file_paths

```python
def extract_file_paths(content: str) -> set[str]
```

Extract file paths from issue content.

Searches for file paths in backtick-quoted paths, location section bold paths, and standalone paths with recognized extensions. Code fence blocks are stripped before extraction.

**Parameters:**
- `content` - Issue file content

**Returns:** Set of file paths found in the content

#### compute_conflict_score

```python
def compute_conflict_score(
    content_a: str,
    content_b: str,
) -> float
```

Compute semantic conflict score between two issues.

Combines three weighted signals to determine how likely two file-overlapping issues are to conflict:

| Signal | Weight | Description |
|--------|--------|-------------|
| Semantic target overlap | 0.5 | Jaccard similarity of component/function names (PascalCase, function refs, explicit scopes) |
| Section mention overlap | 0.3 | Whether issues reference the same UI regions (header, body, sidebar, etc.) |
| Modification type match | 0.2 | Whether both issues have the same modification type (structural, infrastructure, enhancement) |

When a signal cannot be determined (e.g., no component names found), it defaults to 0.5 (moderate).

**Parameters:**
- `content_a` - First issue's file content
- `content_b` - Second issue's file content

**Returns:** Conflict score from 0.0 (parallel-safe) to 1.0 (definite conflict)

**Score interpretation:**

| Score | Level | Meaning |
|-------|-------|---------|
| >= 0.7 | HIGH | Same component, same section, same type — definite conflict |
| 0.4–0.7 | MEDIUM | Possible conflict, unclear if same section |
| < 0.4 | LOW | Different sections/components — likely safe to parallelize |

#### find_file_overlaps

```python
def find_file_overlaps(
    issues: list[IssueInfo],
    issue_contents: dict[str, str],
) -> tuple[list[DependencyProposal], list[ParallelSafePair]]
```

Find issues that reference overlapping files and propose dependencies.

For each pair of issues where both reference the same file(s), computes a semantic conflict score. High-conflict pairs (score >= 0.4) get dependency proposals; low-conflict pairs (score < 0.4) are reported as parallel-safe.

**Dependency direction logic:**
1. **Different priorities**: Higher priority (lower P-number) blocks lower priority
2. **Same priority, different modification types**: Structural blocks infrastructure blocks enhancement
3. **Same priority, same type**: Falls back to ID ordering with reduced confidence (0.5x multiplier)

Pairs that already have a dependency relationship are skipped.

**Parameters:**
- `issues` - List of parsed issue objects
- `issue_contents` - Mapping from issue_id to file content

**Returns:** Tuple of (proposed dependencies, parallel-safe pairs)

#### validate_dependencies

```python
def validate_dependencies(
    issues: list[IssueInfo],
    completed_ids: set[str] | None = None,
) -> ValidationResult
```

Validate existing dependency references for integrity.

Checks for broken references to nonexistent issues, missing backlinks where A blocks B but B doesn't list A in `blocked_by`, circular dependency chains, and stale references to completed issues.

**Parameters:**
- `issues` - List of parsed issue objects
- `completed_ids` - Set of completed issue IDs

**Returns:** `ValidationResult` with all detected problems

Also checks broken refs in `depends_on`, `relates_to`, and `duplicate_of` fields.

#### validate_frontmatter_fields

```python
def validate_frontmatter_fields(issues: list[IssueInfo]) -> None
```

Warn about deprecated relationship frontmatter keys found in issue files on disk.

Reads the raw file content for each issue and emits a `logger.warning()` for any deprecated key (e.g., `parent_issue:`, `related:`) left over from pre-ENH-1434 migration.

**Parameters:**
- `issues` - List of parsed issue objects (must have a valid `.path` attribute)

#### analyze_dependencies

```python
def analyze_dependencies(
    issues: list[IssueInfo],
    issue_contents: dict[str, str],
    completed_ids: set[str] | None = None,
) -> DependencyReport
```

Run full dependency analysis: discovery and validation.

Combines file overlap discovery with dependency validation to produce a comprehensive report.

**Parameters:**
- `issues` - List of parsed issue objects
- `issue_contents` - Mapping from issue_id to file content
- `completed_ids` - Set of completed issue IDs

**Returns:** Comprehensive `DependencyReport`

#### format_report

```python
def format_report(report: DependencyReport) -> str
```

Format a dependency report as human-readable markdown.

Output includes:
- Summary statistics (issues analyzed, existing deps, proposed deps, parallel-safe pairs, validation issues)
- **Proposed Dependencies** table with Conflict level column (HIGH/MEDIUM/LOW)
- **Parallel Execution Safe** table listing file-overlapping pairs that can run concurrently
- **Validation Issues** sections (broken refs, missing backlinks, cycles, stale refs)

**Parameters:**
- `report` - The analysis report to format

**Returns:** Markdown-formatted report string

#### format_text_graph

```python
def format_text_graph(
    issues: list[IssueInfo],
    proposals: list[DependencyProposal] | None = None,
) -> str
```

Generate an ASCII dependency graph diagram.

Shows existing dependencies as solid arrows (`──→`) and proposed dependencies as dashed arrows (`-.→`).

**Parameters:**
- `issues` - List of parsed issue objects
- `proposals` - Optional proposed dependencies to include

**Returns:** Text graph string readable in the terminal

#### format_epic_tree

```python
def format_epic_tree(
    root_id: str,
    root_info: IssueInfo,
    child_map: dict[str, IssueInfo],
    graph: DependencyGraph,
    use_color: bool = True,
) -> str
```

Render an EPIC's child hierarchy as a Unicode box-drawing tree string.

Children are ordered via topological sort. Status badges (`[done]`, `[blocked]`) appear inline; `[open]` is suppressed. Blocking edges are annotated as `⮡ blocks ISSUE-NNN` under the blocker's tree line.

**Parameters:**
- `root_id` - The EPIC issue ID (e.g. `"EPIC-001"`)
- `root_info` - IssueInfo for the root EPIC
- `child_map` - Mapping from child issue ID to IssueInfo
- `graph` - DependencyGraph scoped to the EPIC's children
- `use_color` - Whether to emit ANSI color codes (default `True`)

**Returns:** Unicode box-drawing tree string, or `"EPIC-001: (no children)"` when `child_map` is empty

#### apply_proposals

```python
def apply_proposals(
    proposals: list[DependencyProposal],
    issue_files: dict[str, Path],
) -> list[str]
```

Write approved dependency proposals to issue files.

For each proposal, adds the target to the source's `## Blocked By` section and the source to the target's `## Blocks` section.

**Parameters:**
- `proposals` - Approved proposals to apply
- `issue_files` - Mapping from issue_id to file path

**Returns:** List of modified file paths

**Usage Example:**
```python
from little_loops.dependency_mapper import analyze_dependencies, apply_proposals
from little_loops.issue_parser import find_issues
from little_loops.config import BRConfig
from pathlib import Path

config = BRConfig(Path.cwd())
issues = find_issues(config)

# Load issue contents
contents = {issue.issue_id: issue.path.read_text() for issue in issues}

# Run analysis
report = analyze_dependencies(issues, contents)

# Review proposals (conflict score >= 0.4)
for proposal in report.proposals:
    print(f"{proposal.source_id} -> {proposal.target_id} "
          f"(conflict: {proposal.conflict_score:.0%}): {proposal.rationale}")

# Review parallel-safe pairs (conflict score < 0.4)
for pair in report.parallel_safe:
    print(f"{pair.issue_a} || {pair.issue_b}: {pair.reason}")

# Apply approved proposals
if report.proposals:
    issue_files = {issue.issue_id: issue.path for issue in issues}
    modified = apply_proposals(report.proposals, issue_files)
    print(f"Modified: {modified}")
```

---

## little_loops.goals_parser

Parser for `ll-goals.md` product goals document. Provides structured access to product goals including persona and priorities.

### Persona

Primary user persona.

```python
@dataclass
class Persona:
    """Primary user persona."""
    id: str
    name: str
    role: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Persona: ...
```

### Priority

Strategic priority.

```python
@dataclass
class Priority:
    """Strategic priority."""
    id: str
    name: str

    @classmethod
    def from_dict(cls, data: dict[str, Any], index: int = 0) -> Priority: ...
```

### ProductGoals

Parsed product goals from `ll-goals.md`.

```python
@dataclass
class ProductGoals:
    """Parsed product goals from ll-goals.md."""
    version: str
    persona: Persona | None
    priorities: list[Priority] = field(default_factory=list)
    raw_content: str = ""

    @classmethod
    def from_file(cls, path: Path) -> ProductGoals | None: ...

    @classmethod
    def from_content(cls, content: str) -> ProductGoals | None: ...

    def is_valid(self) -> bool: ...
```

**`from_file(path)`** — Parse goals from an `ll-goals.md` file. Returns `None` if the file doesn't exist or is invalid.

**`from_content(content)`** — Parse goals from raw string content. Returns `None` if the content is invalid or missing a YAML frontmatter block.

**`is_valid()`** — Returns `True` if both `persona` and at least one `priority` are defined.

### validate_goals

```python
def validate_goals(goals: ProductGoals) -> list[str]
```

Validate product goals and return warnings.

**Parameters:**
- `goals` - ProductGoals instance to validate

**Returns:** List of validation warning messages (empty if valid)

**Example:**
```python
from pathlib import Path
from little_loops.goals_parser import ProductGoals, validate_goals

goals = ProductGoals.from_file(Path(".ll/ll-goals.md"))
if goals is None:
    print("Goals file not found or invalid")
else:
    warnings = validate_goals(goals)
    for warning in warnings:
        print(f"Warning: {warning}")

    if goals.persona:
        print(f"Persona: {goals.persona.name} ({goals.persona.role})")

    for priority in goals.priorities:
        print(f"Priority: {priority.id} - {priority.name}")
```

---

## little_loops.issue_discovery

Issue discovery, duplicate detection, and regression analysis. Implemented as a
package (`issue_discovery/`) with three sub-modules: `matching`, `extraction`,
and `search`.

### Public Functions (6)

| Function | Purpose |
|----------|---------|
| `search_issues_by_content()` | Search issues by content with relevance scoring |
| `search_issues_by_file_path()` | Search for issues mentioning a specific file path |
| `detect_regression_or_duplicate()` | Classify a completed issue match |
| `find_existing_issue()` | Multi-pass search for an existing issue matching a finding |
| `reopen_issue()` | Move a completed issue back to active with Reopened section |
| `update_existing_issue()` | Add new findings to an existing active issue |

### Classes

#### MatchClassification

Enum classifying how a finding relates to an existing issue.

```python
class MatchClassification(Enum):
    NEW_ISSUE = "new_issue"    # No existing issue matches
    DUPLICATE = "duplicate"    # Active issue exists
    REGRESSION = "regression"  # Completed, fix broken by later changes
    INVALID_FIX = "invalid_fix"  # Completed, fix never worked
    UNVERIFIED = "unverified"  # Completed, no fix commit tracked
```

#### RegressionEvidence

Evidence gathered when classifying a completed-issue match.

```python
@dataclass
class RegressionEvidence:
    fix_commit_sha: str | None = None
    fix_commit_exists: bool = True
    files_modified_since_fix: list[str] = field(default_factory=list)
    days_since_fix: int = 0
    related_commits: list[str] = field(default_factory=list)
```

#### FindingMatch

Result of matching a finding to an existing issue.

```python
@dataclass
class FindingMatch:
    issue_path: Path | None
    match_type: str  # "exact", "similar", "content", "none"
    match_score: float  # 0.0–1.0
    is_completed: bool = False
    matched_terms: list[str] = field(default_factory=list)
    classification: MatchClassification = MatchClassification.NEW_ISSUE
    regression_evidence: RegressionEvidence | None = None
```

Key properties: `should_skip` (score ≥ 0.8), `should_update` (0.5–0.8),
`should_create` (< 0.5), `should_reopen`, `should_reopen_as_regression`,
`should_reopen_as_invalid_fix`, `is_unverified`.

### Example

```python
from little_loops.issue_discovery import (
    find_existing_issue,
    reopen_issue,
    MatchClassification,
)
from little_loops.config import BRConfig
from pathlib import Path

config = BRConfig(Path.cwd())

# Search for an existing issue matching a new finding
match = find_existing_issue(
    config,
    finding_type="BUG",
    file_path="scripts/little_loops/config.py",
    finding_title="Config fails to load on missing key",
    finding_content="KeyError raised when optional key absent",
)

if match.should_skip:
    print(f"Duplicate of {match.issue_path}")
elif match.should_reopen_as_regression:
    print(f"Regression: {match.issue_path} — {match.regression_evidence}")
elif match.should_create:
    print("New issue — no match found")
```

---

## little_loops.issue_history

Analysis of completed issues for project health insights.

### Public Functions (28)

#### Parsing & Scanning

| Function | Purpose |
|----------|---------|
| `parse_completed_issue(file_path, *, batch_dates=None)` | Parse a single completed issue file |
| `scan_completed_issues(issues_dir, category_dirs=None)` | Scan `.issues/` for completed issues (takes the parent `.issues/` directory, not the completed subdir) |
| `scan_active_issues(base_dir, categories)` | Scan active issue directories |
| `detect_recurring_feedback(corrections)` | Detect recurring correction patterns |
| `detect_skill_bypass(history)` | Detect skill bypass events |
| `scan_completed_issues_from_db(db_path)` | Scan completed issues from history.db |

#### parse_completed_issue

```python
def parse_completed_issue(
    file_path: Path,
    *,
    batch_dates: dict[str, date] | None = None,
) -> CompletedIssue | None
```

Parse a single completed issue file.

**Parameters:**
- `file_path` — Path to the completed issue `.md` file
- `batch_dates` — Optional pre-fetched filename→date mapping from `_batch_completion_dates()`. When provided, the completion date is resolved via an O(1) dict lookup instead of a per-file `git log` subprocess call. Pass this when calling from inside a loop over many issue files.

**Returns:** `CompletedIssue` dataclass, or `None` if the file cannot be parsed.

**Performance note**: Without `batch_dates`, each call runs one `git log` subprocess to determine when the file was added to the repo. For scanning an entire directory, prefer `scan_completed_issues()` — it pre-fetches all completion dates in a single `git log` call and passes the resulting map to each `parse_completed_issue()` call automatically (ENH-970).

#### Analysis

| Function | Purpose |
|----------|---------|
| `calculate_summary(issues, *, source="files", since=None, until=None, loop_runs_started=None, loop_runs_ended=None)` | Calculate summary statistics; `source`/window/loop-run fields are recorded on the result (ENH-3237) |
| `calculate_analysis(completed_dir, ...)` | Calculate full history analysis |
| `analyze_hotspots(issues, ...)` | Detect file/directory hotspots |
| `analyze_coupling(issues, ...)` | Analyze file coupling patterns |
| `analyze_regression_clustering(issues)` | Cluster regression bug chains |
| `analyze_test_gaps(issues, ...)` | Detect test coverage gaps |
| `analyze_rejection_rates(issues)` | Analyze rejection and closure patterns |
| `detect_manual_patterns(issues)` | Detect recurring manual activities |
| `detect_config_gaps(manual_analysis, ...)` | Detect configuration automation gaps |
| `analyze_agent_effectiveness(issues)` | Analyze agent effectiveness by type |
| `analyze_complexity_proxy(issues)` | Analyze complexity via issue duration |
| `detect_cross_cutting_smells(issues)` | Detect cross-cutting concern patterns |

#### Formatting

| Function | Purpose |
|----------|---------|
| `format_summary_text(summary)` | Format summary as plain text |
| `format_summary_json(summary)` | Format summary as JSON |
| `format_analysis_text(analysis)` | Format full analysis as plain text |
| `format_analysis_json(analysis)` | Format full analysis as JSON |
| `format_analysis_markdown(analysis)` | Format full analysis as Markdown |
| `format_analysis_yaml(analysis)` | Format full analysis as YAML |

#### Documentation Synthesis

| Function | Purpose |
|----------|---------|
| `synthesize_docs(issues, topic, ...)` | Synthesize documentation from issue history |
| `score_relevance(issue, topic)` | Score issue relevance to a topic |
| `build_narrative_doc(issues, topic)` | Build narrative-style documentation |
| `build_structured_doc(issues, topic)` | Build structured documentation |

### Data Classes (26)

#### CompletedIssue

Parsed information from a completed issue file.

```python
@dataclass
class CompletedIssue:
    """Parsed information from a completed issue file."""
    path: Path
    issue_type: str          # BUG, ENH, FEAT, EPIC
    priority: str            # P0-P5
    issue_id: str            # e.g., BUG-001
    discovered_by: str | None = None
    discovered_date: date | None = None
    completed_date: date | None = None
    captured_at: datetime | None = None   # sub-day precision from `captured_at` frontmatter
    completed_at: datetime | None = None  # sub-day precision from `completed_at` frontmatter
```

#### HistorySummary

Summary statistics for completed issues.

```python
@dataclass
class HistorySummary:
    """Summary statistics for completed issues."""
    total_count: int
    type_counts: dict[str, int] = field(default_factory=dict)
    priority_counts: dict[str, int] = field(default_factory=dict)
    discovery_counts: dict[str, int] = field(default_factory=dict)
    earliest_date: date | None = None
    latest_date: date | None = None
    source: str = "files"           # "issue_events" or "files" — which store answered (ENH-3237)
    since: date | None = None       # requested --since window bound, if any
    until: date | None = None       # requested --until window bound, if any
    loop_runs_started: int | None = None  # None (not 0) when the session DB can't answer
    loop_runs_ended: int | None = None
    # Properties: date_range_days, velocity
    # date_range_days uses the requested (since, until) span when both are
    # set; otherwise it falls back to the span actually observed between
    # earliest_date/latest_date (status quo).
```

#### Hotspot

A file or directory that appears in multiple issues.

```python
@dataclass
class Hotspot:
    """A file or directory that appears in multiple issues."""
    path: str
    issue_count: int = 0
    issue_ids: list[str] = field(default_factory=list)
    issue_types: dict[str, int] = field(default_factory=dict)  # {"BUG": 5, "ENH": 3, "EPIC": 2}
    bug_ratio: float = 0.0
    churn_indicator: str = "low"  # "high", "medium", "low"
```

#### CouplingPair

A pair of files that frequently appear together in issues.

```python
@dataclass
class CouplingPair:
    """A pair of files that frequently appear together in issues."""
    file_a: str
    file_b: str
    co_occurrence_count: int = 0
    coupling_strength: float = 0.0  # 0-1, Jaccard similarity
    issue_ids: list[str] = field(default_factory=list)
```

#### Other Data Classes

| Class | Purpose |
|-------|---------|
| `PeriodMetrics` | Metrics for a specific time period (quarter, month, week) |
| `SubsystemHealth` | Health metrics for a subsystem directory |
| `HotspotAnalysis` | Container for file/directory hotspot analysis results |
| `CouplingAnalysis` | Container for file coupling analysis results |
| `RegressionCluster` | A cluster of bugs where fixes caused new bugs |
| `RegressionAnalysis` | Container for regression clustering results |
| `Gap` | A source file with bugs but missing/weak test coverage |
| `GapAnalysis` | Container for test gap analysis results |
| `RejectionMetrics` | Metrics for rejection and invalid closure tracking |
| `RejectionAnalysis` | Container for rejection pattern analysis |
| `ManualPattern` | A recurring manual activity detected across issues |
| `ManualPatternAnalysis` | Container for manual pattern analysis results |
| `ConfigGap` | A configuration gap that could automate manual work |
| `ConfigGapsAnalysis` | Container for configuration gap analysis |
| `AgentOutcome` | Metrics for a single agent processing a specific issue type |
| `AgentEffectivenessAnalysis` | Container for agent effectiveness analysis |
| `TechnicalDebtMetrics` | Technical debt health indicators |
| `ComplexityProxy` | Duration-based complexity proxy for a file/directory |
| `ComplexityProxyAnalysis` | Container for complexity proxy analysis |
| `CrossCuttingSmell` | A detected cross-cutting concern scattered across the codebase |
| `CrossCuttingAnalysis` | Container for cross-cutting concern analysis |
| `HistoryAnalysis` | Complete history analysis report (all analysis results) |

### Example

```python
from little_loops.issue_history import (
    scan_completed_issues,
    calculate_summary,
    analyze_hotspots,
    format_summary_text,
)
from pathlib import Path

# Load and analyze
issues_dir = Path(".issues")
issues = scan_completed_issues(issues_dir)
summary = calculate_summary(issues)

print(f"Completed: {summary.total_count}")
print(f"Velocity: {summary.velocity:.2f} issues/day")

# Find problematic files
hotspot_analysis = analyze_hotspots(issues)
for hotspot in hotspot_analysis.file_hotspots[:5]:
    print(f"{hotspot.path}: {hotspot.issue_count} issues")

# Generate text report
report = format_summary_text(summary)
print(report)
```

---

## little_loops.git_operations

Git utility functions for status checking and .gitignore management.

### Porcelain parsing and dirty-tree preservation (BUG-2963)

```python
def porcelain_paths(raw: str) -> list[str]
def snapshot_dirty_paths(repo_path: Path) -> frozenset[str]
def abandoned_ref_name(identifier: str) -> str
def preserve_dirty_tree(repo_path: Path, ref_name: str, logger: Logger | None = None) -> str | None
def has_non_noise_dirty_paths(repo_path: Path) -> tuple[bool, list[str]]
def filter_ll_noise(paths: list[str]) -> list[str]
```

- **`porcelain_paths`** — parse `git status --porcelain -z` (NUL-delimited) output into paths. The `-z` form is used deliberately: the newline format's `old -> new` rename arrow is ambiguous when a filename contains ` -> `, and its quoted paths are only quote-stripped, not octal-unescaped, so non-ASCII names arrive corrupted. Returns the *new* path for renames/copies.
- **`snapshot_dirty_paths`** — capture the `pre_run_dirty` set for the completion pre-flight. **Must be called before the work runs**; a snapshot taken afterwards already contains the deliverable, which would classify the whole implementation as pre-existing WIP. Returns an empty set on any git failure — the direction that preserves more, never less.
- **`abandoned_ref_name`** — build `refs/ll/abandoned/<identifier>-<timestamp>`.
- **`preserve_dirty_tree`** — non-destructively snapshot a dirty tree to a durable ref via a throwaway `GIT_INDEX_FILE` (`add -A` → `write-tree` → `commit-tree` → `update-ref`), leaving the working tree and real index byte-identical. Returns the snapshot commit SHA, or `None` on a clean tree or error. **Never implemented with `git stash`** — stash removes the changes it is supposed to preserve. Because worktrees share the object database and ref store with the main repo, a ref written from inside a worktree survives `git worktree remove --force`; recover with `git show <ref>:<path>`. Nothing prunes these refs automatically.
- **`has_non_noise_dirty_paths` / `filter_ll_noise`** — the noise filter (`.issues/`, `thoughts/`, `.ll/`) shared by the pre-flight and the worktree-teardown backstop. `EXCLUDED_DIRECTORIES` is intentionally left unmodified; the `.ll/` set is adjacent, so `verify_work_was_done()` still counts a `.ll/`-only change as real work.

### GitignorePattern

Represents a suggested .gitignore pattern with metadata.

```python
@dataclass
class GitignorePattern:
    pattern: str           # The .gitignore pattern (e.g., "*.log", ".env")
    category: str          # Category of file (e.g., "coverage", "environment")
    description: str       # Human-readable description
    files_matched: list[str]  # Untracked files matching this pattern
    priority: int          # Suggestion priority (1=highest, 5=lowest)
```

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `is_wildcard` | `bool` | True if pattern contains wildcards (`*`, `?`) |
| `is_directory` | `bool` | True if pattern targets a directory (ends with `/`) |

### GitignoreSuggestion

Container for gitignore suggestions with user interaction helpers.

```python
@dataclass
class GitignoreSuggestion:
    patterns: list[GitignorePattern]  # Suggested patterns
    existing_gitignore: Path | None   # Path to .gitignore file
    already_ignored: list[str]        # Files already covered by .gitignore
    total_files: int                  # Total untracked files examined
```

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `has_suggestions` | `bool` | True if there are patterns to suggest |
| `files_to_ignore` | `list[str]` | All files that would be ignored by suggested patterns |
| `summary` | `str` | Human-readable summary of suggestions |

### suggest_gitignore_patterns

```python
def suggest_gitignore_patterns(
    untracked_files: list[str] | None = None,
    repo_root: Path | str = ".",
    logger: Logger | None = None,
) -> GitignoreSuggestion
```

Analyze untracked files and suggest .gitignore patterns.

Examines untracked files against a curated list of common patterns (coverage reports, environment files, logs, Python/Node.js artifacts, etc.). Respects existing .gitignore patterns and won't suggest patterns for already-ignored files.

**Parameters:**
- `untracked_files` - Optional list of untracked files. If None, detects via git status
- `repo_root` - Path to repository root (default: current directory)
- `logger` - Optional logger for debug output

**Returns:** `GitignoreSuggestion` with suggested patterns and metadata

**Example:**
```python
from little_loops.git_operations import suggest_gitignore_patterns
from little_loops.logger import Logger

logger = Logger()
result = suggest_gitignore_patterns(logger=logger)

if result.has_suggestions:
    for pattern in result.patterns:
        print(f"{pattern.pattern}: {pattern.description}")
        print(f"  Matches: {', '.join(pattern.files_matched)}")
```

### add_patterns_to_gitignore

```python
def add_patterns_to_gitignore(
    patterns: list[str],
    repo_root: Path | str = ".",
    logger: Logger | None = None,
    backup: bool = True,
) -> bool
```

Add patterns to .gitignore file.

Skips duplicate patterns and optionally creates a backup before modifying.

**Parameters:**
- `patterns` - List of patterns to add
- `repo_root` - Path to repository root
- `logger` - Optional logger for output
- `backup` - If True, creates `.gitignore.backup` before modifying

**Returns:** `True` if patterns were added successfully

**Example:**
```python
from little_loops.git_operations import add_patterns_to_gitignore
from little_loops.logger import Logger

logger = Logger()
success = add_patterns_to_gitignore(
    patterns=["*.log", ".env", "coverage.json"],
    logger=logger
)
```

### get_untracked_files

```python
def get_untracked_files(repo_root: Path | str = ".") -> list[str]
```

Get list of untracked files from git status.

Uses `git status --porcelain` to detect untracked files.

**Parameters:**
- `repo_root` - Path to repository root (default: current directory)

**Returns:** List of untracked file paths (relative to repo root)

### check_git_status

```python
def check_git_status(logger: Logger) -> bool
```

Check for uncommitted changes.

**Parameters:**
- `logger` - Logger for output

**Returns:** `True` if there are uncommitted changes

---

## little_loops.work_verification

Shared work verification utilities used by `issue_manager` (ll-auto) and `worker_pool` (ll-parallel).

```python
from little_loops.work_verification import verify_work_was_done, filter_excluded_files
```

### Constants

```python
EXCLUDED_DIRECTORIES = (
    ".issues/",
    "issues/",
    ".speckit/",
    "thoughts/",
    ".worktrees/",
    ".auto-manage",
)
```

Directories excluded from work verification. Changes to files in these directories do not count as meaningful implementation work.

### filter_excluded_files

```python
def filter_excluded_files(files: list[str]) -> list[str]
```

Filter out files in excluded directories.

**Parameters:**
- `files` - List of file paths to filter

**Returns:** List of files not in `EXCLUDED_DIRECTORIES`

### verify_work_was_done

```python
def verify_work_was_done(
    logger: Logger,
    changed_files: list[str] | None = None,
    baseline_sha: str | None = None,
    config: BRConfig | None = None,
    repo_root: Path | None = None,
    pre_step_snapshot: TamperSnapshot | None = None,
    issue_id: str | None = None,
    git_lock: GitLock | None = None,
) -> bool
```

Verify that actual work was done (not just issue file moves).

Prevents marking issues as "completed" when no actual fix was implemented. Returns `True` if there are file changes outside of excluded directories and the tamper guard did not fail them.

Detection runs in three modes (first match wins):
1. **Pre-computed list** (`changed_files` provided) — used by `ll-parallel` via `worker_pool.py`
2. **Uncommitted/staged** — `git diff --name-only` + `git diff --cached --name-only`
3. **Commit-range** (`baseline_sha` provided and HEAD has moved) — `git diff --name-only <baseline_sha>..HEAD` — covers the common case where the agent commits mid-phase and exits with a clean working tree

When meaningful changes are found and `config` is supplied, the tamper guard (ENH-2933,
`little_loops.test_tamper_guard.run_tamper_guard`) also runs against the changed-file set
(ENH-2935) — the non-FSM counterpart to the FSM's `tamper_guard:` state key (ENH-2934). It runs
in up to two windows, ANDing the verdicts:

1. **Implement window** (unconditional). "before" is reconstructed from git history
   (`snapshot_test_paths_at_ref`) using *baseline_sha* (or `HEAD` when unset) as the reference
   point. Because that window spans the whole implement phase (not just a dedicated verify
   step), findings are filtered to edits that actually weaken the test suite
   (assertions/test functions removed, skip/skipif/xfail markers added, file deleted) rather
   than any byte change (BUG-2954). The strength metric is a per-file aggregate count, so it
   still does not detect a same-count substitution (real assertions gutted and backfilled with
   `assert True`) and still reads assertions extracted into a shared helper as a weakening — see
   ENH-2964. A test function moved to another file is no longer a false positive: the filter
   nets a file's strength deficit against a same-named test function newly present elsewhere in
   the same finding set (ENH-2964).
2. **Post-implement window** (ENH-2958, only when `pre_step_snapshot` is given). Both
   `issue_manager.py` (`ll-auto`) and `worker_pool.py` (`ll-parallel`/`ll-sprint`) capture a
   live `snapshot_test_paths(...)` right after the implement call returns and thread it
   through as `pre_step_snapshot`; this window is compared byte-strictly (no weakening
   filter), mirroring the FSM adapter's snapshot-on-entry bracket, and catches a mutation
   occurring strictly after implement returned (e.g. a worker's committed-leak recovery).

The guard is skipped entirely when `config` is omitted, preserving pre-ENH-2935 behavior for
callers with no project config in scope.

When the tamper guard passes and both `config` and `issue_id` are supplied, the non-FSM
pre-patch check adapter (ENH-2998) runs next — the `ll-auto`/`ll-parallel` counterpart to
the FSM executor's guarded-state hook (ENH-2997). It resolves `(base_sha, base_dirty)` for
`issue_id` from `.ll/history.db` via `little_loops.history_reader.read_base_sha`/
`read_base_dirty`, forks a pre-patch worktree under `config.get_worktree_base()`, reruns
candidate tests with `little_loops.prepatch_check.run_prepatch_check()`, tears the fork down
in a `finally` (mirroring `fsm/executor.py`'s teardown contract), and persists the resulting
`PrePatchEvidence` to `.ll/history.db` via `little_loops.session_store.record_prepatch_evidence()`
— the same row `ll-harness --issue-id` reads. `config.prepatch_check.enabled` (default `False`)
is this check's only off-switch, reused rather than duplicated; when disabled, or when `issue_id`
is omitted, this step is skipped entirely. A `flagged` verdict fails verification the same way
an unresolved tamper-guard finding does.

**Parameters:**
- `logger` - Logger for output
- `changed_files` - Optional pre-computed file list. If `None`, detects via `git diff` and `git diff --cached`
- `baseline_sha` - Optional git SHA captured before Phase 2 began. When provided and HEAD has advanced beyond this SHA, checks for non-excluded files committed in the range; enables detection of mid-phase commits in `ll-auto`. Also used as the tamper guard's "before" git reference when `config` is supplied.
- `config` - Optional `BRConfig` used to resolve the tamper guard's default policy (`tamper_guard.policy`, default `"fail"`) and test-file patterns. Both `ll-auto` (`issue_manager.py`) and `ll-parallel`/`ll-sprint` (`worker_pool.py`) always have one in scope and pass it through.
- `repo_root` - Optional repo root the tamper guard runs against; defaults to `config.project_root` when `config` is given.
- `issue_id` - Optional issue ID (ENH-2998) that gates and scopes the non-FSM pre-patch check described above. `None` (the default) skips it, preserving pre-ENH-2998 behavior unchanged.
- `git_lock` - Optional caller-owned `GitLock` (ENH-2998) the pre-patch check's worktree fork uses. `worker_pool.py` threads its own `self._git_lock`; `issue_manager.py` has none in scope, so the adapter constructs one locally when omitted. Unused when the pre-patch check does not run.

**Returns:** `True` if meaningful file changes were detected and neither the tamper guard nor the pre-patch check failed them

**Example:**

```python
from little_loops.work_verification import verify_work_was_done
from little_loops.logger import Logger

logger = Logger()
if not verify_work_was_done(logger):
    logger.warning("No implementation changes detected")
```

---

## little_loops.context_window

Single source of truth for model → context-window size mapping. Used by `issue_manager`, `subprocess_utils`, and `worker_pool` to resolve the correct token denominator for handoff/guillotine decisions.

### context_window_for

```python
def context_window_for(model: str | None, override: int | None = None) -> int:
    """Resolve context-window size for a model id.

    Precedence (highest to lowest):
    1. Explicit ``override`` argument (non-zero)
    2. ``LL_CONTEXT_LIMIT`` environment variable (non-zero integer)
    3. ``[1m]`` suffix on model id → 1_000_000
    4. Exact model-id lookup in MODEL_CONTEXT_WINDOW
    5. 200_000 conservative floor
    """
```

**Parameters**:
- `model` — Model identifier string (e.g. `"claude-opus-4-8[1m]"`), or `None` to use env-var / floor.
- `override` — Explicit token count; takes top precedence when non-zero.

**Returns**: Context window size in tokens (always a positive `int`).

**Examples**:
```python
from little_loops.context_window import context_window_for

context_window_for("claude-opus-4-8[1m]")          # → 1_000_000
context_window_for("claude-opus-4-8")               # → 200_000
context_window_for(None)                             # → 200_000 (conservative floor)
context_window_for("claude-opus-4-8", override=500_000)  # → 500_000
```

**Note**: The bash layer (`hooks/scripts/context-monitor.sh:get_context_limit()`) implements the same logic; both are kept in sync via a `# keep in sync with` comment. The env-var precedence means that `LL_CONTEXT_LIMIT` set by any CLI (`ll-auto`, `ll-parallel`, `ll-sprint`, `ll-loop`) flows through `context_window_for()` into every Python continuation path.

---

## little_loops.issue_manager

Process all backlog issues sequentially in priority order.

### AutoManager

Automated issue manager for sequential processing.

```python
from little_loops.issue_manager import AutoManager
from little_loops.config import BRConfig
from pathlib import Path

config = BRConfig(Path.cwd())
manager = AutoManager(
    config=config,
    dry_run=False,
    max_issues=5,
    resume=False,
    category="bugs"
)
exit_code = manager.run()
```

#### Constructor

```python
AutoManager(
    config: BRConfig,
    dry_run: bool = False,
    max_issues: int = 0,
    resume: bool = False,
    category: str | None = None,
    only_ids: list[str] | set[str] | None = None,
    skip_ids: set[str] | None = None,
    type_prefixes: set[str] | None = None,
    priority_filter: set[str] | None = None,
    label_filter: set[str] | None = None,
    verbose: bool = True,
    preview_full: bool = False,
    db_path: Path | None = None,
)
```

**Parameters:**
- `config` - Project configuration
- `dry_run` - Preview mode (no actual changes)
- `max_issues` - Maximum issues to process (0 = unlimited)
- `resume` - Resume from previous state
- `category` - Filter to specific category
- `only_ids` - If provided, only process these issue IDs
- `skip_ids` - Issue IDs to skip (in addition to attempted issues)
- `type_prefixes` - If provided, only process issues with these type prefixes
- `priority_filter` - If provided, only process issues with these priority levels (e.g., `{"P0", "P1"}`)
- `label_filter` - If provided, only process issues carrying one of these labels
- `verbose` - Whether to output progress messages
- `preview_full` - Show full issue body in dry-run preview (default: summary only)
- `db_path` - Override path for the SQLite session store (default: `.ll/history.db`, resolved via `resolve_history_db()` — anchored at the resolved project root, ENH-2927, not the bare cwd)

**Behavior:** On construction, `AutoManager` creates an internal `EventBus` and wires a `SQLiteTransport(db_path or DEFAULT_DB_PATH)` to it automatically. `SQLiteTransport.__init__` resolves its path via `resolve_history_db()`, so the default anchors at the resolved project root rather than the working directory. Issue lifecycle events (`issue.completed`, `issue.deferred`, `issue.skipped`, `issue.started`, etc.) are recorded live during `run()` without any additional configuration.

#### Methods

##### run

```python
def run(self) -> int
```

Run the automation loop.

**Returns:** Exit code (0 = success)

### Helper Functions

#### run_claude_command

```python
def run_claude_command(
    command: str,
    logger: Logger,
    timeout: int = 3600,
    stream_output: bool = True,
    on_model_detected: Callable[[str], None] | None = None,
    on_usage: Callable[[int, int], None] | None = None,
    on_usage_detailed: Callable[[TokenUsage], None] | None = None,
    preview_full: bool = False,
    resume_session: bool = False,
    *,
    automation: AutomationContext | None = None,
    timeout_kill_grace_seconds: float = 0.0,
) -> subprocess.CompletedProcess[str]
```

Preview and invoke a Claude CLI command with output streaming. This is the `issue_manager`-local wrapper that logs and truncates the command before delegating to `subprocess_utils.run_claude_command`.

> **Breaking change (ENH-3261):** the `automation_profile`/`disable_background_tasks`/`idle_timeout` legacy kwargs were removed from this signature. Callers must pass `automation=AutomationContext(profile=..., disable_background_tasks=..., idle_timeout=...)` instead. `automation` and every parameter after it are now keyword-only.

**Parameters:**
- `command` - Command to pass to Claude CLI
- `logger` - Logger for output
- `timeout` - Timeout in seconds
- `stream_output` - Whether to stream output to console
- `on_model_detected` - Optional callback invoked with the model name from the stream-json system/init event. This is the **requested alias** (e.g. `"sonnet"`), not the resolved model the CLI actually ran.
- `on_usage` - Optional callback invoked with `(input_tokens, output_tokens)` from the stream-json result event
- `on_usage_detailed` - Optional callback invoked with a `TokenUsage` dataclass from the stream-json result event. `TokenUsage.model` carries the **resolved** model ID (e.g. `"claude-sonnet-5"`), unlike `on_model_detected` (BUG-2757).
- `preview_full` - If `True`, display the full command without truncation (for `--verbose`)
- `resume_session` - If `True`, passes `--continue` to the Claude CLI to continue the most recent conversation
- `automation` (ENH-3097) - Collapsed automation signal (`profile`, `disable_background_tasks`, `idle_timeout`), forwarded as-is to `subprocess_utils.run_claude_command`. `None` disables automation entirely.
- `timeout_kill_grace_seconds` (ENH-3130) - Grace period (seconds) given to the process group after a wall-clock or idle timeout fires before escalating from `SIGTERM` to `SIGKILL`. `0` (default) preserves the historical immediate-`SIGKILL` behavior.

**Returns:** `CompletedProcess` with stdout/stderr captured. When a `result` event with `is_error=True` is present in the stream-json output, `CompletedProcess.stderr` will include a `[result] <error>` line containing the error text from the result event's `error` field (falling back to the `result` field).

**Turn-end detection**: The reader breaks on the stream-json `result` event rather than waiting for pipe EOF. This is necessary because background `Workflow`/`Task` child processes spawned by the headless `claude -p` session inherit the stdout/stderr write-ends; a pipe only reports EOF when the *last* writer closes it, so EOF may never arrive even after the turn completes, causing the reader to hang until the wall-clock timeout fires. Stopping on `result` bounds read latency to the actual turn duration regardless of whether background children are still running.

**Process-group cleanup**: On timeout or idle-timeout, cleanup sends `SIGTERM` to the entire process group via `os.killpg(os.getpgid(pid), SIGTERM)` first, waits up to `timeout_kill_grace_seconds` for the group to exit on its own, and only then escalates to `SIGKILL` if it is still alive (ENH-3130) — `timeout_kill_grace_seconds=0` (the function default) skips straight to `SIGKILL`, preserving the pre-ENH-3130 behavior. The subprocess is started with `start_new_session=True` so it leads its own isolated process group, so both signals reach background `Workflow`/`Task` children spawned during the session, not just the direct child PID; otherwise they would linger as orphans holding pipe write-ends open. Falls back to `process.terminate()`/`process.kill()` on platforms where `os.killpg` is absent (Windows). (ENH-1999, ENH-3130)

#### verify_issue_completed

```python
def verify_issue_completed(
    info: IssueInfo,
    config: BRConfig,
    logger: Logger
) -> bool
```

Verify that an issue was marked as completed via frontmatter status check.

Reads the issue file's `status:` frontmatter field; `done` or `cancelled` means the close lifecycle ran successfully. Issues are updated in-place rather than moved, so this is a pure frontmatter check.

**Parameters:**
- `info` - Issue info
- `config` - Project configuration (unused; kept for signature stability)
- `logger` - Logger for output

**Returns:** `True` if issue's frontmatter `status` is `done` or `cancelled`

#### close_issue

```python
def close_issue(
    info: IssueInfo,
    config: BRConfig,
    logger: Logger,
    close_reason: str | None,
    close_status: str | None,
    fix_commit: str | None = None,
    files_changed: list[str] | None = None,
    event_bus: EventBus | None = None,
    interceptors: list[Any] | None = None,
    pre_run_dirty: frozenset[str] | None = None,
    repo_path: Path | None = None,
) -> bool
```

Close an issue by moving to completed with closure status.

**Parameters:**
- `info` - Issue info
- `config` - Project configuration
- `logger` - Logger for output
- `close_reason` - Reason code (e.g., `"already_fixed"`)
- `close_status` - Status text (e.g., `"Closed - Already Fixed"`)
- `fix_commit` - SHA of the commit that fixed the issue (for regression tracking)
- `files_changed` - List of files modified by the fix (for regression tracking)
- `event_bus` - Optional `EventBus` for emitting lifecycle events during closure
- `interceptors` - Optional list of interceptor objects; each may implement `before_issue_close(info) -> bool | None`. Returning `False` vetoes the close and causes this function to return `False` immediately without moving the issue file.
- `pre_run_dirty` - Snapshot of `git status --porcelain` paths taken **before** this run started, from `git_operations.snapshot_dirty_paths()` (BUG-2963). Paths absent from it are this run's deliverable and are committed alongside the issue file; paths present in it are pre-existing WIP and are left untouched. `None` — the conservative default for external API callers — means the two sets cannot be separated, so any non-noise dirty path refuses the close.
- `repo_path` - Working tree to operate in. Defaults to the process cwd.

**Returns:** `True` if the issue is closed **and** its closure is in a commit. `False` if vetoed by an interceptor, if an error occurs, or if the close was **refused** because the deliverable could not be committed.

**Refusal contract (BUG-2963):** on refusal the working tree is first preserved non-destructively to a durable `refs/ll/abandoned/<ID>-<timestamp>` ref (never `git stash`, which would remove the very changes it claims to preserve), the issue file is left unmutated — no `status: done`, no `## Resolution` section, no `completed_at` — and `uncommitted_paths` / `abandoned_ref` / `abandoned_sha` are stamped into its frontmatter as a best-effort convenience. Callers must treat a `False` return as "still open" and requeue. A pre-commit hook rejection is a legitimate refusal and is never bypassed with `--no-verify`.

#### complete_issue_lifecycle

```python
def complete_issue_lifecycle(
    info: IssueInfo,
    config: BRConfig,
    logger: Logger,
    event_bus: EventBus | None = None,
    pre_run_dirty: frozenset[str] | None = None,
    repo_path: Path | None = None,
) -> bool
```

Fallback: Complete issue lifecycle when command exited early. This is the path BUG-2963 was filed against — it fires after an abnormal subloop exit, exactly when the deliverable is most likely to still be uncommitted.

**Parameters:**
- `info` - Issue info
- `config` - Project configuration
- `logger` - Logger for output
- `event_bus` - Optional `EventBus` for emitting lifecycle events on completion
- `pre_run_dirty` - As for `close_issue` above.
- `repo_path` - Working tree to operate in. Defaults to the process cwd.

**Returns:** `True` if the issue is `done` **and** that state is in a commit. `False` if the completion was refused.

**Refusal contract (BUG-2963):** same as `close_issue`, except the issue is left `in_progress` rather than at its prior status, so it is requeued rather than silently dropped. Never a hollow `done`.

> **Scope carve-out:** `defer_issue()` / `undefer_issue()` deliberately do **not** carry this contract. A deferral is not a claim that work was delivered, and mapping a failed commit onto `in_progress` there would silently un-defer an issue and fight autodev's `deferred_by` / `deferred_reason` policy.

---

## little_loops.issue_lifecycle

Issue lifecycle operations: completing, closing, deferring, and undeferring issues.

```python
from little_loops.issue_lifecycle import defer_issue, undefer_issue
```

### defer_issue

```python
def defer_issue(
    info: IssueInfo,
    config: BRConfig,
    logger: Logger,
    reason: str | None = None,
    event_bus: EventBus | None = None,
) -> bool
```

Defer an issue by writing `status: deferred` to its frontmatter.

The file remains in its type directory; only the `status:` field changes. Appends a `## Deferred` section with the reason and date, then commits the update.

**Parameters:**
- `info` - Parsed issue info
- `config` - Project configuration
- `logger` - Logger for output
- `reason` - Reason for deferring (default: `"Intentionally set aside for later consideration"`)
- `event_bus` - Optional `EventBus` for emitting `issue.deferred` lifecycle event

**Returns:** `True` if successful, `False` otherwise

### undefer_issue

```python
def undefer_issue(
    config: BRConfig,
    deferred_issue_path: Path,
    logger: Logger,
    reason: str | None = None,
    event_bus: EventBus | None = None,
) -> Path | None
```

Update a deferred issue in-place: sets status to `open` and emits `issue.started`.

**Parameters:**
- `config` - Project configuration
- `deferred_issue_path` - Path to the issue file (in its type directory, e.g. `.issues/features/`)
- `logger` - Logger for output
- `reason` - Reason for undeferring (optional)
- `event_bus` - Optional `EventBus` for emitting `issue.started` lifecycle event

**Returns:** Same path as `deferred_issue_path` — the issue is updated in-place (status set to `open`), no file is moved; returns `None` if failed

**Example:**

```python
from little_loops.issue_lifecycle import defer_issue, undefer_issue
from little_loops.issue_parser import IssueParser
from little_loops.config import BRConfig
from little_loops.logger import Logger
from pathlib import Path

config = BRConfig(Path.cwd())
logger = Logger()
parser = IssueParser(config)
info = parser.parse_file(Path(".issues/features/P3-FEAT-042-example.md"))

# Defer
defer_issue(info, config, logger, reason="Blocked pending design review")

# Undefer later
new_path = undefer_issue(config, Path(".issues/features/P3-FEAT-042-example.md"), logger)
```

### FailureType / classify_failure

```python
class FailureType(Enum):
    TRANSIENT = "transient"          # temporary error, don't create a bug issue
    NON_RECOVERABLE = "non_recoverable"  # auth/credential failure — retry won't help
    REAL = "real"                    # actual bug/error, create an issue
    INFRA_RETRY = "infra_retry"      # host-CLI teardown after output was already produced

def classify_failure(
    error_output: str, returncode: int, result_seen: bool = False
) -> tuple[FailureType, str]
```

Classifies a command failure by scanning `error_output` for known transient
patterns (API quota/rate-limit text, network errors, timeouts) and credential
failures, falling back to `REAL` when nothing matches. `FSMExecutor` uses this
to decide whether a failed state should retry, defer, or route to `on_error`
without ever creating a spurious bug issue for a transient blip.

`INFRA_RETRY` (BUG-2731) is checked first, ahead of any text pattern: when
`returncode == 143` (SIGTERM) and `result_seen=True`, the failure is classified
as infra teardown rather than a real error. This covers the headless host CLI
reaping a still-running subagent process group when the top-level turn ends —
a clean kill with no distinguishing error text, but one that occurred *after*
a stream-json `"result"` event was already observed, so discarding the
in-flight work as a genuine failure would be wrong. `result_seen` is threaded
through from `ActionResult.result_seen`, populated only for host-CLI actions.
The executor retries `INFRA_RETRY` failures via `_handle_infra_retry()`
(`_DEFAULT_INFRA_RETRY_RETRIES` attempts, `_DEFAULT_INFRA_RETRY_BACKOFF`
seconds apart — mirroring `_handle_api_error()`'s shape but with a short flat
backoff since it's re-running an already-completed action, not waiting on an
external service), emitting `InfraRetryVariant`/`InfraRetryExhaustedVariant`
DES events. `ll-logs scan-failures` and `ll-loop test`'s simulated-failure path
also treat `INFRA_RETRY` as a non-bug-worthy classification alongside
`TRANSIENT`/`NON_RECOVERABLE`.

---

## little_loops.state

State persistence for automation resume capability.

### ProcessingState

Persistent state for automated issue processing.

```python
@dataclass
class ProcessingState:
    current_issue: str = ""
    phase: str = "idle"
    timestamp: str = ""
    completed_issues: list[str] = field(default_factory=list)
    failed_issues: dict[str, str] = field(default_factory=dict)
    attempted_issues: set[str] = field(default_factory=set)
    timing: dict[str, dict[str, float]] = field(default_factory=dict)
    corrections: dict[str, list[str]] = field(default_factory=dict)
```

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `current_issue` | `str` | Path to currently processing issue file |
| `phase` | `str` | Current processing phase |
| `timestamp` | `str` | Last update timestamp |
| `completed_issues` | `list[str]` | List of completed issue IDs |
| `failed_issues` | `dict[str, str]` | Mapping of issue ID to failure reason |
| `attempted_issues` | `set[str]` | Set of issues already attempted |
| `timing` | `dict` | Per-issue timing breakdown |
| `corrections` | `dict[str, list[str]]` | Mapping of issue ID to list of auto-corrections made |

#### Methods

```python
def to_dict(self) -> dict[str, Any]
@classmethod
def from_dict(cls, data: dict[str, Any]) -> ProcessingState
```

### StateManager

Manages persistence of processing state.

```python
from little_loops.state import StateManager
from little_loops.logger import Logger
from pathlib import Path

manager = StateManager(Path(".auto-manage-state.json"), Logger())
state = manager.load()
manager.mark_completed("BUG-001", {"total": 120.5})
manager.save()
```

#### Constructor

```python
StateManager(state_file: Path, logger: Logger, event_bus: EventBus | None = None)
```

**Parameters:**
- `state_file` - Path to the state file
- `logger` - Logger instance for output
- `event_bus` - Optional `EventBus` for emitting state transition events

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `state` | `ProcessingState` | Get current state, creating new if needed |

#### Methods

| Method | Description |
|--------|-------------|
| `load() -> ProcessingState \| None` | Load state from file |
| `save()` | Save current state to file |
| `cleanup()` | Remove state file |
| `update_current(issue_path: str, phase: str)` | Update current issue and phase |
| `mark_attempted(issue_id, *, save=True)` | Mark issue as attempted |
| `mark_completed(issue_id, timing=None)` | Mark issue as completed |
| `mark_failed(issue_id, reason)` | Mark issue as failed |
| `is_attempted(issue_id) -> bool` | Check if issue was attempted |
| `record_corrections(issue_id, corrections)` | Record auto-corrections made to an issue |

---

## little_loops.logger

Logging utilities with colorized output.

### Logger

Simple logger with timestamps and colors.

```python
from little_loops.logger import Logger

logger = Logger(verbose=True, use_color=True)
logger.info("Processing...")
logger.success("Done!")
logger.warning("Check this")
logger.error("Failed!")
logger.timing("Took 5.2 seconds")
logger.header("SUMMARY")
```

#### Constructor

```python
Logger(verbose: bool = True, use_color: bool | None = None, colors: CliColorsConfig | None = None)
```

**Parameters:**
- `verbose` - Whether to output messages (False silences all output)
- `use_color` - Whether to use ANSI color codes. Defaults to `True` unless the `NO_COLOR` environment variable is set or stdout is not a TTY.
- `colors` - Optional `CliColorsConfig` to override default ANSI color codes per log level.

#### Methods

| Method | Color | Description |
|--------|-------|-------------|
| `info(msg)` | Cyan | General information |
| `debug(msg)` | Gray | Debug messages |
| `success(msg)` | Green | Success messages |
| `warning(msg)` | Yellow | Warnings |
| `error(msg)` | Orange | Errors (to stderr) |
| `timing(msg)` | Magenta | Timing information |
| `header(msg, char="=", width=60)` | - | Header with separators |

### format_duration

```python
def format_duration(seconds: float) -> str
```

Format duration in human-readable form.

**Parameters:**
- `seconds` - Duration in seconds

**Returns:** Human-readable string

**Example:**
```python
from little_loops.logger import format_duration

format_duration(65.5)  # "1.1 minutes"
format_duration(45.2)  # "45.2 seconds"
```

---

## little_loops.user_messages

Extract and analyze user messages from Claude Code session logs.

### UserMessage

Extracted user message with metadata.

```python
@dataclass
class UserMessage:
    content: str                                       # The text content of the message
    timestamp: datetime                                # When the message was sent
    session_id: str                                    # Claude Code session identifier
    uuid: str                                          # Unique message identifier
    cwd: str | None = None                             # Working directory when sent
    git_branch: str | None = None                      # Git branch active when sent
    is_sidechain: bool = False                         # Whether this was a sidechain message
    response_metadata: ResponseMetadata | None = None  # Metadata extracted from the assistant response
```

#### Methods

```python
def to_dict(self) -> dict
```
Convert to dictionary for JSON serialization.

### ExampleRecord

Training example pair extracted from a skill invocation session, suitable for APO/prompt-optimization pipelines.

```python
@dataclass
class ExampleRecord:
    skill: str         # Skill name (e.g., "capture-issue")
    input: str         # Concatenated preceding user messages as context
    output: str        # JSON-serialized ResponseMetadata (tools_used, files_modified, completion_status)
    session_id: str    # Claude Code session identifier
    timestamp: datetime
    context_window: int  # Number of preceding messages used
```

#### Methods

```python
def to_dict(self) -> dict
```
Convert to dictionary for JSON serialization. Output includes `type: "example"`.

### build_examples

```python
def build_examples(
    messages: list[UserMessage],
    skill: str,
    context_window: int = 3,
) -> list[ExampleRecord]
```

Build training example pairs from skill invocation sessions.

Groups messages by session, identifies skill trigger records (user-side records containing
`<command-name>/ll:SKILL_NAME</command-name>`), and pairs each with the N preceding messages
as input context.

**Parameters:**
- `messages` - UserMessage list (typically pre-filtered to skill-matching sessions)
- `skill` - Skill name to build examples for (e.g. `"capture-issue"`)
- `context_window` - Number of preceding messages to include as input context (default: 3)

**Returns:** List of `ExampleRecord` objects, one per skill trigger found.

**Example:**
```python
from little_loops.user_messages import extract_user_messages, build_examples, get_project_folder

project_folder = get_project_folder()
messages = extract_user_messages(project_folder, include_response_context=True)
examples = build_examples(messages, "capture-issue", context_window=3)
for ex in examples:
    print(ex.to_dict())
```

### get_project_folder

```python
def get_project_folder(
    cwd: Path | None = None, *, host: str | None = None
) -> Path | None
```

Map a directory to the host's session-log project folder. Dispatches to host-specific
helpers for Claude Code, Codex, OpenCode, and Pi.

**Parameters:**
- `cwd` - Working directory to map (default: current directory)
- `host` - Host identifier: ``"claude-code"``, ``"codex"``, ``"opencode"``, or ``"pi"``.
  If ``None``, auto-detects from the ``LL_HOOK_HOST`` env var (default ``"claude-code"``).

**Returns:** Path to the host's project session folder, or ``None`` if it doesn't exist.

**Example:**
```python
from little_loops.user_messages import get_project_folder
from pathlib import Path

# Map current directory (auto-detect host from LL_HOOK_HOST)
project_folder = get_project_folder()

# Map specific directory for Claude Code
project_folder = get_project_folder(Path("/Users/me/my-project"), host="claude-code")
# Returns: ~/.claude/projects/-Users-me-my-project

# Map for Codex
project_folder = get_project_folder(host="codex")
# Returns: ~/.codex/projects/-Users-me-my-project
```

**Internal helpers:**

- ``_get_claude_project_folder(encoded_path: str) -> Path | None`` — probes ``~/.claude/projects/<encoded_path>``
- ``_get_codex_project_folder(encoded_path: str) -> Path | None`` — probes ``~/.codex/projects/<encoded_path>``
- ``_get_opencode_project_folder(encoded_path: str) -> Path | None`` — probes ``~/.opencode/projects/<encoded_path>``
- ``_get_pi_project_folder(encoded_path: str) -> Path | None`` — probes ``~/.pi/projects/<encoded_path>`` (stub; Pi adapter deferred per FEAT-992)

Each helper returns the ``Path`` if the directory exists, or ``None`` otherwise.

**Encoding rule:** ``encode_project_path(path_str: str) -> str`` (also exported from
``little_loops.user_messages``) maps every non-alphanumeric character — slashes, dots,
underscores, hyphens — 1:1 to a single ``-``. Consecutive special characters are **not**
collapsed: a cwd segment like ``/.worktrees/`` (slash followed by dot) encodes to
``--worktrees`` (two dashes), matching Claude Code's on-disk project-folder naming. This
matters for git worktree checkouts (``ll-parallel`` / ``ll-sprint`` / subloop epics),
whose paths always contain a dotted ``.worktrees/`` segment.

### get_sessions_folder

```python
def get_sessions_folder(
    cwd: Path | None = None, *, host: str | None = None
) -> Path | None
```

Resolve the folder holding the host's top-level session JSONL transcripts (ENH-3165).
Wraps ``get_project_folder()`` and joins ``subagent_layout_for(host).sessions_subdir``:
for qwen, ``get_project_folder(host="qwen")`` returns the project **root** (so both
``chats/`` and ``subagents/`` are reachable), while session JSONL lives one level
deeper under ``chats/`` — this helper performs that join. For Claude-shaped hosts
``sessions_subdir`` is ``""`` and the result equals ``get_project_folder()`` exactly.

Use this instead of ``get_project_folder()`` whenever you glob ``*.jsonl``
non-recursively or index a transcript by ``<session-id>.jsonl`` (the
``get_current_session_jsonl``, ``fsm.continuity``, and ``ll-ctx-stats`` cache-rate
call sites all resolve through it).

**Parameters:**
- `cwd` - Working directory to map (default: current directory)
- `host` - Host identifier, same vocabulary as ``get_project_folder``. If ``None``,
  auto-detects from the ``LL_HOOK_HOST`` env var (default ``"claude-code"``).

**Returns:** Path to the session-JSONL folder, or ``None`` when the host has no
recorded sessions for *cwd*.

**Example:**
```python
from little_loops.user_messages import get_sessions_folder

sessions_dir = get_sessions_folder()  # host auto-detected from LL_HOOK_HOST
# qwen host: the project root's "chats" child
# claude-code host: the project folder itself (sessions_subdir is "")
```

### discover_all_projects

```python
def discover_all_projects(
    logger: Logger, *, host: str | None = None
) -> list[Path]
```

Discover all projects with ll activity for the given host. Iterates the host's session
directory (e.g. ``~/.claude/projects/`` for Claude Code, ``~/.codex/projects/`` for
Codex), resolves each directory name back to an absolute path, checks for ll-relevant
JSONL records, and returns a sorted list of paths that exist on disk.

**Parameters:**
- ``logger`` - Logger instance for warnings.
- ``host`` - Host identifier: ``"claude-code"``, ``"codex"``, ``"opencode"``, or ``"pi"``.
  If ``None``, auto-detects from the ``LL_HOOK_HOST`` env var (default ``"claude-code"``).

**Returns:** Sorted list of decoded absolute paths for projects with ll activity.

**Example:**
```python
from little_loops.cli.logs import discover_all_projects
from little_loops.logger import Logger

logger = Logger.get()
projects = discover_all_projects(logger)
# ['/Users/me/my-project', '/Users/me/other-project']

# Discover Codex projects
projects = discover_all_projects(logger, host="codex")
```

**Implementation:** Uses the same four-way host dispatch as ``get_project_folder()``.
Decodes project directory names back to absolute paths by preferring the ``cwd`` field
from JSONL records first, then falling back to string-replacing ``-`` with ``/``. The
fallback decode is inherently lossy — the encode side (``encode_project_path()``) maps
dots, underscores, and hyphens all onto the same ``-``, so a bare reverse-replace can't
reconstruct the original path exactly. This is why the ``cwd``-from-JSONL preference
exists: it is the only exact source of the original path, and the round trip only holds
because that field is checked first.
Filters to directories that contain ll-relevant JSONL records via ``_has_ll_activity()``.
Returns an empty list for unknown host identifiers.

### extract_user_messages

```python
def extract_user_messages(
    project_folder: Path,
    limit: int | None = None,
    since: datetime | None = None,
    include_agent_sessions: bool = True,
    include_response_context: bool = False,
) -> list[UserMessage]
```

Extract user messages from all JSONL session files in a project folder.

**Parameters:**
- `project_folder` - Path to Claude project folder
- `limit` - Maximum number of messages to return
- `since` - Only include messages after this datetime
- `include_agent_sessions` - Whether to include agent-*.jsonl files
- `include_response_context` - Whether to include the assistant response immediately following each user message

**Returns:** Messages sorted by timestamp, most recent first.

**Filters:**
- Only messages with `type == "user"`
- Excludes tool results (array content with `tool_result` type)

**Example:**
```python
from datetime import datetime
from little_loops.user_messages import extract_user_messages, get_project_folder

project_folder = get_project_folder()
if project_folder:
    # Get last 50 messages
    messages = extract_user_messages(project_folder, limit=50)

    # Get messages since a date
    since = datetime(2026, 1, 1)
    recent = extract_user_messages(project_folder, since=since)

    for msg in messages:
        print(f"[{msg.timestamp}] {msg.content[:50]}...")
```

### save_messages

```python
def save_messages(
    messages: list[UserMessage],
    output_path: Path | None = None,
) -> Path
```

Save messages to a JSONL file.

**Parameters:**
- `messages` - List of UserMessage objects to save
- `output_path` - Output file path. If None, uses `.ll/user-messages-{timestamp}.jsonl`

**Returns:** Path to the saved file.

### print_messages_to_stdout

```python
def print_messages_to_stdout(messages: list[UserMessage]) -> None
```

Print messages to stdout in JSONL format.

**Parameters:**
- `messages` - List of UserMessage objects to print

---

## little_loops.parallel

Parallel processing subpackage with git worktree isolation.

### ParallelOrchestrator

Main controller for parallel issue processing.

```python
from little_loops.config import BRConfig
from little_loops.parallel import ParallelOrchestrator
from pathlib import Path

br_config = BRConfig(Path.cwd())
parallel_config = br_config.create_parallel_config(max_workers=3)

orchestrator = ParallelOrchestrator(
    parallel_config=parallel_config,
    br_config=br_config,
    repo_path=Path.cwd(),
    verbose=True
)
exit_code = orchestrator.run()
```

#### Constructor

```python
ParallelOrchestrator(
    parallel_config: ParallelConfig,
    br_config: BRConfig,
    repo_path: Path | None = None,
    verbose: bool = True,
    wave_label: str | None = None,
    event_bus: EventBus | None = None,
)
```

**Parameters:**
- `parallel_config` - Parallel processing configuration
- `br_config` - Project configuration
- `repo_path` - Path to the git repository (default: current directory)
- `verbose` - Whether to output progress messages
- `wave_label` - Optional label for wave-based execution (e.g., `"Wave 1"`)
- `event_bus` - Optional `EventBus` for emitting worker completion events

#### Methods

| Method | Description |
|--------|-------------|
| `run() -> int` | Run parallel issue processor, returns exit code |

### WorkerPool

Thread pool for processing issues in isolated git worktrees.

```python
from little_loops.parallel import WorkerPool

pool = WorkerPool(parallel_config, br_config, logger, repo_path)
pool.start()
future = pool.submit(issue_info, on_complete_callback)
result = future.result()  # WorkerResult
pool.shutdown()
pool.cleanup_all_worktrees()
```

#### Constructor

```python
WorkerPool(
    parallel_config: ParallelConfig,
    br_config: BRConfig,
    logger: Logger,
    repo_path: Path | None = None,
)
```

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `active_count` | `int` | Number of active workers |

#### Methods

| Method | Description |
|--------|-------------|
| `start()` | Start the worker pool |
| `submit(issue: IssueInfo, on_complete: Callable[[WorkerResult], None] \| None = None) -> Future` | Submit issue for processing |
| `shutdown(wait=True)` | Shutdown the worker pool |
| `cleanup_all_worktrees()` | Remove all worktree directories |

### Output Parsing

Utilities for parsing Claude's output from `/ll:ready-issue` commands. Located at `little_loops.output_parsing`.

#### parse_ready_issue_output

```python
def parse_ready_issue_output(output: str) -> dict[str, Any]
```

Parse the output from a `/ll:ready-issue` command to extract verdict and metadata.

**Parameters:**
- `output` - Raw stdout from Claude CLI

**Returns:** Dictionary with parsed results:

```python
{
    "verdict": str,              # READY, CORRECTED, NOT_READY, NEEDS_REVIEW, CLOSE, or UNKNOWN
    "concerns": list[str],       # List of concerns from ## CONCERNS section
    "is_ready": bool,            # True if verdict is READY or CORRECTED
    "was_corrected": bool,       # True if verdict is CORRECTED
    "should_close": bool,        # True if verdict is CLOSE
    "close_reason": str | None,  # Reason code (e.g., "already_fixed", "invalid_ref")
    "close_status": str | None,  # Status text (e.g., "Closed - Already Fixed")
    "corrections": list[str],    # List of corrections made
    "validated_file_path": str | None,  # File path from validation
    "sections": dict,            # Raw parsed sections
    "validation": dict           # Validation details
}
```

**Example:**
```python
from little_loops.output_parsing import parse_ready_issue_output

result = subprocess.run(["claude", "-p", "/ll:ready-issue BUG-001"], capture_output=True, text=True)
parsed = parse_ready_issue_output(result.stdout)

if parsed["is_ready"]:
    print(f"Issue ready! Was corrected: {parsed['was_corrected']}")
elif parsed["should_close"]:
    print(f"Issue should be closed: {parsed['close_reason']}")
else:
    print(f"Not ready: {len(parsed['concerns'])} concern(s)")
```

#### Valid Verdicts

| Verdict | Description | `is_ready` | `should_close` |
|---------|-------------|------------|----------------|
| `READY` | Issue is prepared for implementation | `True` | `False` |
| `CORRECTED` | Issue had problems that were auto-fixed | `True` | `False` |
| `NOT_READY` | Issue has concerns preventing implementation | `False` | `False` |
| `NEEDS_REVIEW` | Requires manual review | `False` | `False` |
| `CLOSE` | Issue should be closed (already fixed, invalid, etc.) | `False` | `True` |
| `UNKNOWN` | Verdict could not be parsed (error state) | `False` | `False` |

#### Parsing Strategy

The parser uses a 6-step fallback strategy to extract verdicts:

1. **New format**: Look for `## VERDICT` section header
2. **Old format**: Match `VERDICT: <keyword>` pattern via regex
3. **Keyword scan**: Search lines containing "verdict" for keywords
4. **Full scan**: Search entire output for verdict keywords
5. **Clean retry**: Remove markdown formatting and retry extraction
6. **Infer from READY_FOR**: If still unknown, check `## READY_FOR` section for "Implementation: Yes"

This multi-step approach handles variations in Claude's output formatting (bold, backticks, headers) and different response styles.

#### Tool-Specific Verdict Handling

Both `ll-auto` and `ll-parallel` use `parse_ready_issue_output()` but handle results differently:

| Aspect | ll-auto | ll-parallel |
|--------|---------|-------------|
| **UNKNOWN verdict** | Logs and proceeds | Returns error with output snippet for debugging |
| **CLOSE handling** | Validates "invalid_ref" reason, checks file path | Generic handling via WorkerResult flags |
| **File validation** | Validates path with fallback retry | None (relies on worktree isolation) |

### JSON Output Helpers

Stop-sequence / prefill recipes for bounding the *output* tokens an LLM spends
emitting structured data (FEAT-2470, EPIC-2456 Tier 0). Located at
`little_loops.output.parse`. Both return a `(value, error)` tuple — the same
convention as `output_parsing.extract_tagged_json` (BUG-2383); neither swallows,
so callers must surface `error` when `value is None`.

#### extract_between_tags

```python
def extract_between_tags(start_tag: str, end_tag: str, raw: str) -> tuple[str | None, str | None]
```

Extract the text between `start_tag` and `end_tag`. Pairs with the **stop-sequence**
recipe: set `end_tag` as the model's stop sequence so generation halts the instant
the payload is complete. Tolerates a missing `end_tag` (returns the remainder after
`start_tag`). Returns `(None, error)` only when `start_tag` is absent.

#### parse_prefilled_json

```python
def parse_prefilled_json(raw: str) -> tuple[Any | None, str | None]
```

Parse a JSON object from prefilled output. Pairs with the **prefill** recipe
(seed the assistant turn with `{`). Tries a verbatim parse first, then falls back
to the `rfind('{')` recipe — scanning from the last `{` to its matching `}` via a
string-aware bracket-depth walk — so leading fragments or trailing prose don't
break it.

```python
from little_loops.output.parse import extract_between_tags, parse_prefilled_json

payload, err = extract_between_tags("<json>", "</json>", raw_output)
verdict, err = parse_prefilled_json(raw_output)  # raw begins with "{"
```

### Output Cleaner

Anti-event + duplicate-window pre-filter (FEAT-2470, EPIC-2456 technique [25])
that trims avoidable token cost from tool/log output before it enters the model's
context. Located at `little_loops.output_cleaner`.

#### filter_output

```python
def filter_output(raw: str, *, dup_threshold: int = 1) -> str
```

Strips ANSI, drops **anti-event** lines (tqdm/ascii progress bars, spinner frames,
pytest-xdist worker chatter), and collapses **duplicate windows** — runs of
consecutive identical lines become a single line plus a `… (repeated N×)` marker
once the run exceeds `dup_threshold`. Consecutive blank lines collapse to one.
Trailing-newline presence is preserved.

```python
from little_loops.output_cleaner import filter_output

trimmed = filter_output(noisy_pytest_stdout)
```

### MergeCoordinator

Sequential merge queue with sophisticated conflict handling, error recovery, and adaptive strategies.

**See [MERGE-COORDINATOR.md](../development/MERGE-COORDINATOR.md) for comprehensive documentation.**

```python
from little_loops.parallel import MergeCoordinator

coordinator = MergeCoordinator(config, logger, repo_path)
coordinator.start()
coordinator.queue_merge(worker_result)
coordinator.wait_for_completion(timeout=120)
coordinator.shutdown()
```

#### Constructor

```python
MergeCoordinator(
    config: ParallelConfig,
    logger: Logger,
    repo_path: Path | None = None,
)
```

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `merged_ids` | `list[str]` | Successfully merged issue IDs |
| `failed_merges` | `dict[str, str]` | Failed merges with errors |
| `stash_pop_failures` | `dict[str, str]` | Issues where merge succeeded but stash restore failed |
| `pending_count` | `int` | Pending merge requests |

#### Methods

| Method | Description |
|--------|-------------|
| `start()` | Start the merge coordinator background thread |
| `queue_merge(result)` | Queue a worker result for merging |
| `wait_for_completion(timeout)` | Wait for all pending merges |
| `shutdown(wait=True, timeout=30.0)` | Shutdown the coordinator |

### ParallelConfig

Configuration dataclass for parallel processing.

```python
@dataclass
class ParallelConfig:
    max_workers: int = 2
    p0_sequential: bool = True
    merge_interval: float = 30.0
    worktree_base: Path = field(default_factory=lambda: Path(".worktrees"))
    state_file: Path = field(default_factory=lambda: Path(".parallel-manage-state.json"))
    max_merge_retries: int = 2
    priority_filter: list[str] = field(default_factory=lambda: ["P0", "P1", "P2", "P3", "P4", "P5"])
    max_issues: int = 0
    dry_run: bool = False
    timeout_per_issue: int = 3600
    idle_timeout_per_issue: int = 0
    orchestrator_timeout: int = 0
    stream_subprocess_output: bool = False
    show_model: bool = False
    command_prefix: str = "/ll:"
    ready_command: str = "ready-issue {{issue_id}}"
    manage_command: str = "manage-issue {{issue_type}} {{action}} {{issue_id}}"
    decide_command: str = "decide-issue {{issue_id}}"
    only_ids: set[str] | None = None
    skip_ids: set[str] | None = None
    type_prefixes: set[str] | None = None
    label_filter: set[str] | None = None
    require_code_changes: bool = True
    use_feature_branches: bool = False
    push_feature_branches: bool = False
    open_pr_for_feature_branches: bool = False
    worktree_copy_files: list[str] = field(default_factory=lambda: [".claude/settings.local.json", ".env", ".ll/ll.local.md"])
    merge_pending: bool = False
    clean_start: bool = False
    ignore_pending: bool = False
    overlap_detection: bool = False
    serialize_overlapping: bool = True
    skip_learning_gate: bool = False
    base_branch: str | None = None
    remote_name: str = "origin"
    epic_branches: EpicBranchesConfig = field(default_factory=EpicBranchesConfig)
```

#### Methods

##### get_ready_command

```python
def get_ready_command(self, issue_id: str) -> str
```

Build the ready-issue command string.

**Parameters:**
- `issue_id` - Issue identifier

**Returns:** Complete command string (e.g., `"/ll:ready-issue BUG-001"`)

##### get_manage_command

```python
def get_manage_command(self, issue_type: str, action: str, issue_id: str) -> str
```

Build the manage-issue command string.

**Parameters:**
- `issue_type` - Type of issue (bug, feature, enhancement)
- `action` - Action to perform (fix, implement, improve)
- `issue_id` - Issue identifier

**Returns:** Complete command string

### EpicBranchesConfig

Per-EPIC integration branch configuration (FEAT-2339). Declared twice with
identical fields — a runtime dataclass at `little_loops.parallel.types` (held by
`ParallelConfig.epic_branches`) and an automation-side dataclass at
`little_loops.config.automation` (held by `parallel.epic_branches` in config).
`BRConfig.create_parallel_config` converts the automation form to the runtime
form via `_build_parallel_epic_branches`.

```python
@dataclass
class EpicBranchesConfig:
    enabled: bool = False              # master switch; False preserves per-worker behavior
    prefix: str = "epic/"              # branch = f"{prefix}{epic_id.lower()}-{slug}"
    merge_to_base_on_complete: bool = True  # merge EPIC branch to base after last child
    open_pr: bool = False              # open a PR for the EPIC branch via gh on completion
    verify_before_merge: bool = False  # run test_cmd/lint_cmd against the branch tip before merge/PR-open (ENH-2603)
    refresh_on_reuse: str = "merge"    # warn|merge|off — staleness guard on a reused branch (ENH-3302)
```

When `enabled`, `WorkerPool` routes every child of a shared `parent:` EPIC onto
one `epic/<EPIC-ID>-<slug>` branch (fork point and merge target), recorded on
`WorkerResult.epic_branch`. See [Configuration reference](CONFIGURATION.md#parallel).

BUG-2614: the merge/verify/PR logic is implemented as three stateless free functions
in `little_loops.worktree_utils` — `verify_epic_branch_before_merge`,
`merge_epic_branch_to_base`, `open_pr_for_epic_branch` — extracted from what were
previously `ParallelOrchestrator` instance methods, so both `ll-parallel`'s
`WorkerPool` completion path and the `auto-refine-and-implement` FSM loop's
`merge_epic_branch` state can share one implementation instead of the FSM loop
reimplementing it inline. `ParallelOrchestrator._verify_epic_branch_before_merge`/
`_merge_epic_branch_to_base`/`_open_pr_for_epic_branch` remain as thin wrappers that
adapt the free functions to this instance's config/state (`self._git_lock`,
`self.repo_path`, `self._merged_epic_branches` idempotency set,
`self._epic_branch_verify_failures` reporting dict — none of which the free functions
take directly, since they're specific to `WorkerPool`'s concurrency model).

When `verify_before_merge` is `True`, `verify_epic_branch_before_merge` checks out the
EPIC branch tip in a scratch worktree (via `worktree_utils.setup_worktree(...,
checkout_existing=True)`), runs `test_cmd`/`lint_cmd` against it, and always tears the
worktree down, returning `(ok, message, returncode)` (ENH-2631: `returncode` is the
failing process exit code — `None` on success or a worktree-setup failure — so callers
can tell a pytest collection/usage error, exit 2, from a real test failure, exit 1,
without re-running the suite). When the optional `src_dir` kwarg is truthy
(callers forward `project.src_dir`, e.g. `"scripts"`), the verify subprocess prepends
the worktree's `<worktree>/<src_dir>` onto `PYTHONPATH` so branch-only modules resolve
to the worktree — defeating editable-install `.pth` shadowing that would otherwise
resolve `import little_loops.<new_module>` to the main checkout and false-fail
collection (BUG-2629). When `src_dir` is falsy (default `None`), no injection occurs,
preserving prior behavior for non-editable / non-Python setups. Independent of
`src_dir`, the verify subprocess always carries `LL_VERIFY_GATE="1"` in its
environment (BUG-2649, mirroring the `LL_NON_INTERACTIVE` marker idiom): tests
that are non-deterministic under the gate's non-standard invocation (injected
`PYTHONPATH` + parallel-xdist worktree) detect it via
`os.environ.get("LL_VERIFY_GATE") == "1"` and quarantine themselves
(`pytest.mark.skipif`) rather than false-negative a genuinely mergeable branch —
the assertions still run under the standard `python -m pytest scripts/tests/`
invocation off the gate. On the `ll-parallel` path, a failure blocks
the merge/PR-open (the branch is NOT added to `_merged_epic_branches`, so it is retried
on the next completion event), and the message is recorded in
`ParallelOrchestrator.epic_branch_verify_failures` (EPIC ID → message), which
`_report_results()` surfaces in the run summary (ENH-2603). On the FSM loop path, the
`merge_epic_branch` state writes the outcome to a `$RUN_DIR/epic-merge-verdict.txt`
artifact instead — the loop runs `merge_epic_branch` exactly once per execution, so no
idempotency set or failure dict is needed; a branch that no longer exists (already
merged) is the sole idempotency signal. ENH-2630: on the FSM loop path the
`verify` state runs `verify_epic_branch_before_merge` first (unconditionally) and
records both its verdict (`$RUN_DIR/verify-verdict.txt`) and the epic tip SHA
(`$RUN_DIR/verify-sha.txt`). `merge_epic_branch` then **reuses** that verdict —
skipping its own `verify_epic_branch_before_merge` call — when the verdict is
`passed` and the recorded SHA still matches the current epic tip (the two states
run back-to-back, so it normally does), avoiding a redundant second full-suite
run. It falls back to invoking the gate only when the verdict is missing,
non-`passed`, or the SHA is stale, so the binding gate still cannot merge a
failing tip.

ENH-2643: `merge_epic_branch_to_base` accepts an optional keyword-only
`run_dir: Path | None = None`. On the FSM loop path the `merge_epic_branch` state
threads `run_dir=$RUN_DIR` through, so a merge *failure* — before `git merge
--abort` discards the conflict state — persists three flat-text diagnostic
artifacts under the run dir, mirroring the verify gate's `verify-detail.txt`
pair: `merge-returncode.txt` (the failing `git merge` exit code),
`merge-detail.txt` (the bounded `stderr + stdout` tail via `format_verify_detail`),
and `merge-conflicts.txt` (the conflicted-path list from `git diff --name-only
--diff-filter=U`). A clean merge writes none of them. The `ll-parallel`
orchestrator wrapper has no per-run `run_dir` and omits the kwarg (defaults to
`None` → nothing persisted), so its behavior is unchanged.

### WorkerResult

Result from a worker processing an issue.

```python
@dataclass
class WorkerResult:
    issue_id: str
    success: bool
    branch_name: str
    worktree_path: Path
    changed_files: list[str] = field(default_factory=list)
    leaked_files: list[str] = field(default_factory=list)
    duration: float = 0.0
    error: str | None = None
    stdout: str = ""
    stderr: str = ""
    was_corrected: bool = False  # populated on every return path from
                                  # WorkerPool._process_issue, not only success
                                  # (BUG-3254): defaults to False/[] on returns
                                  # before the ready-issue parse, and carries the
                                  # real value on every return after it
    corrections: list[str] = field(default_factory=list)
    should_close: bool = False
    close_reason: str | None = None
    close_status: str | None = None
    was_blocked: bool = False  # ready-issue verdict BLOCKED (open dependency)
    interrupted: bool = False
    epic_branch: str | None = None  # EPIC integration branch this worker forked
                                    # from / merges into (FEAT-2452); None for
                                    # standalone issues or when epic_branches is
                                    # disabled
```

### IssuePriorityQueue

Priority queue for issue processing. Located at `little_loops.parallel.priority_queue`.

```python
from little_loops.parallel.priority_queue import IssuePriorityQueue

queue = IssuePriorityQueue()
added = queue.add_many(issues)
queued_issue = queue.get(block=False)
queue.mark_completed(issue_id)
queue.mark_failed(issue_id)
queue.mark_skipped(issue_id)
```

#### Methods

| Method | Description |
|--------|-------------|
| `add(issue_info) -> bool` | Add a single issue |
| `add_many(issues) -> int` | Add multiple issues, return count added |
| `get(block=True, timeout=None)` | Get next issue from queue |
| `mark_completed(issue_id)` | Mark issue as completed |
| `mark_failed(issue_id)` | Mark issue as failed |
| `mark_skipped(issue_id)` | Mark issue as skipped, e.g. BLOCKED on an open dependency (BUG-3254) |
| `requeue(issue_info, demote_priority=False)` | Requeue an issue; clears it from the in-progress, failed, and skipped buckets |
| `qsize() -> int` | Count of issues currently in queue |
| `in_progress_count() -> int` | Count of issues currently being processed |
| `completed_count() -> int` | Count of completed issues |
| `failed_count() -> int` | Count of failed issues |
| `skipped_count() -> int` | Count of skipped issues |
| `completed_ids() -> list[str]` | IDs of completed issues |
| `failed_ids() -> list[str]` | IDs of failed issues |
| `skipped_ids() -> list[str]` | IDs of skipped issues |
| `load_completed(ids)` | Restore previously completed IDs (resume) |
| `load_failed(ids)` | Restore previously failed IDs (resume); also blocks re-`add()` of those IDs |

**No `load_skipped()`, and `add()` does not reject a previously-skipped id.**
This asymmetry with `load_completed`/`load_failed` is deliberate (BUG-3254 D1):
the skip bucket is a within-run counter, not resume-suppression state, so a
BLOCKED issue is eligible for re-attempt on the very next run.

### Additional Types

Located at `little_loops.parallel.types`:

#### SprintWorkerContext

Sprint worker identity injected into guillotine continuation prompts (BUG-2141).
Tells a fresh Option J session which single issue it must complete and that it
must exit immediately after — preventing deadlock where a fresh session processes
multiple visible issues and blocks on "What next?".

```python
@dataclass
class SprintWorkerContext:
    issue_id: str   # e.g. "FEAT-025"
    branch: str     # Git branch for this worker (main or worktree branch)

    def to_dict(self) -> dict[str, Any]: ...
```

#### QueuedIssue

```python
@dataclass
class QueuedIssue:
    priority: int
    issue_info: IssueInfo
    timestamp: float
```

#### MergeStatus

```python
class MergeStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    CONFLICT = "conflict"
    FAILED = "failed"
    RETRYING = "retrying"
```

#### MergeRequest

```python
@dataclass
class MergeRequest:
    worker_result: WorkerResult
    status: MergeStatus = MergeStatus.PENDING
    retry_count: int = 0
    error: str | None = None
    queued_at: float
```

#### OrchestratorState

```python
@dataclass
class OrchestratorState:
    in_progress_issues: list[str]
    completed_issues: list[str]
    failed_issues: dict[str, str]
    pending_merges: list[str]
    timing: dict[str, dict[str, float]]
    corrections: dict[str, list[str]]   # Issue ID → corrections made (for pattern analysis)
    started_at: str
    last_checkpoint: str
```

#### WorkerStage

```python
class WorkerStage(Enum):
    SETUP = "setup"                # Creating git worktree and copying .claude/
    VALIDATING = "validating"      # Running ready-issue command
    PROVING = "proving"            # Running proof-first-task assumption-firewall gate
    IMPLEMENTING = "implementing"  # Running manage-issue command
    VERIFYING = "verifying"        # Checking work was done and updating branch base
    MERGING = "merging"            # Awaiting merge coordination
    COMPLETED = "completed"        # Successfully finished
    FAILED = "failed"              # Failed at some stage
    INTERRUPTED = "interrupted"    # Interrupted during shutdown
```

Located at `little_loops.parallel.types`.

#### PendingWorktreeInfo

```python
@dataclass
class PendingWorktreeInfo:
    worktree_path: Path             # Path to the worktree directory
    branch_name: str | None         # Git branch from rev-parse, or None if unavailable
    issue_id: str                   # Extracted issue ID (e.g., "BUG-045")
    commits_ahead: int              # Commits ahead of main
    has_uncommitted_changes: bool   # Whether there are uncommitted changes
    changed_files: list[str]        # Files with uncommitted changes
```

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `has_pending_work` | `bool` | `True` if `commits_ahead > 0` or `has_uncommitted_changes` |

Located at `little_loops.parallel.types`.

#### OverlapResult

```python
@dataclass
class OverlapResult:
    has_overlap: bool = False
    overlapping_issues: list[str] = []    # Issue IDs that overlap
    overlapping_files: set[str] = set()   # Specific files/paths that overlap
```

`bool(result)` returns `result.has_overlap`. Located at `little_loops.parallel.overlap_detector`.

#### OverlapDetector

Thread-safe tracker for detecting file modification conflicts between parallel issues. Located at `little_loops.parallel.overlap_detector`.

```python
class OverlapDetector:
    def __init__(self, config: DependencyMappingConfig | None = None) -> None
```

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `register_issue(issue)` | `FileHints` | Register an issue as actively being processed |
| `unregister_issue(issue_id)` | `None` | Unregister a completed issue |
| `check_overlap(issue)` | `OverlapResult` | Check for conflicts without registering |
| `get_active_issues()` | `list[str]` | List currently active issue IDs |
| `get_hints(issue_id)` | `FileHints \| None` | Get hints for a registered issue |
| `clear()` | `None` | Clear all tracked issues |

**Usage pattern:**
```python
from little_loops.parallel.overlap_detector import OverlapDetector

detector = OverlapDetector()
result = detector.check_overlap(new_issue)
if not result:
    detector.register_issue(new_issue)
    # ... process issue ...
    detector.unregister_issue(new_issue.issue_id)
```

---

## little_loops.cli

CLI entry points for the package.

### main_action

```python
def main_action() -> int
```

Entry point for `ll-action` command. Thin CLI wrapper for invoking ll skills as one-shot commands with JSON-structured output.

**Returns:** Exit code

**Subcommands:**
- `invoke <skill> [--args ARG ...] [--timeout SECONDS] [--output stream-json|json]` — invoke a skill and stream NDJSON events or collect JSON
- `capabilities` — emit `CapabilityReport` as JSON
- `list` — list all skills with names, descriptions, and argument hints

**`list` output shape:**

```json
[
  {"name": "refine-issue", "description": "...", "args": "ISSUE_ID [--auto] [--dry-run]"},
  {"name": "old-skill", "description": "...", "args": null}
]
```

The `args` field is sourced from the `args:` frontmatter field in `skills/<name>/SKILL.md`. If `args:` is absent but `argument-hint:` is present, `argument-hint:` is used as a fallback. The field is `null` when neither is set.

---

### main_auto

```python
def main_auto() -> int
```

Entry point for `ll-auto` command. Process all backlog issues sequentially in priority order.

Supports `--skip-learning-gate` to bypass the per-issue learning-test gate (equivalent to `ll-sprint`'s `--skip-learning-gate` flag). The gate runs `proof-first-task` between the ready and implement phases for each issue whose resolved targets are non-empty.

**Returns:** Exit code

### main_loop

```python
def main_loop() -> int
```

Entry point for `ll-loop` command. FSM-based automation loop execution.

**Returns:** Exit code

**Signal handling (`ll-loop run`):**

When `ll-loop run` is executing a loop in the foreground, the process
registers POSIX signal handlers for `SIGINT` (Ctrl-C) and `SIGTERM`
(`scripts/little_loops/cli/loop/_helpers.py:157-173`). The contract is:

| Signal | Behavior |
|--------|----------|
| `SIGINT` (1st) / `SIGTERM` | Graceful shutdown: the executor completes its current state, then `PersistentExecutor.run` calls `archive_run()`. The audit trail (`events.jsonl`, `state.json`, `.history/<run_id>-<loop_name>/` archive) is complete. Exit code: `0`. |
| `SIGINT` (2nd) | Force-exit: the signal handler calls `archive_run_only(terminated_by="interrupted_force")` *before* `sys.exit(1)` (ENH-2516, `scripts/little_loops/cli/loop/_helpers.py:103-107`). The `.history/<run_id>-<loop_name>/` archive still lands. Exit code: `1`. |
| `SIGKILL` (`kill -9`) | **Cannot be trapped.** Data already written via `_append_jsonl` (ENH-2515, `scripts/little_loops/fsm/persistence.py:129-145`) is durable, but the `.history/<run_id>-<loop_name>/` archive and the final `state.json` snapshot may not land. To prevent silent data loss, run `ll-loop run` under a supervisor (`systemd`, `supervisord`), a terminal multiplexer (`tmux`, `screen`), or `nohup` so the loop receives `SIGTERM` (which is trap-able) on shutdown rather than `SIGKILL`. |

The end-to-end SIGINT contract is locked by
`scripts/tests/test_fsm_signal_integration.py`.

### little_loops.cli.loop.scaffold_eval / scaffold_verify

`ll-loop scaffold-eval`/`ll-loop scaffold-verify` (FEAT-2948) generate FSM loop
YAML in Python instead of `/ll:create-eval-from-issues`/`/ll:verify-issue-loop`
hand-assembling it in prose. Both build `FSMLoop`/`StateConfig` objects
(`little_loops.fsm.schema`) directly and validate them in-process via
`fsm.validation.validate_fsm()` before returning.

```python
def scaffold_eval(issue_ids: list[str], dsl: bool) -> ScaffoldResult
def scaffold_verify(issue_id: str, adversarial: bool) -> ScaffoldResult
```

- `scaffold_eval` (`little_loops/cli/loop/scaffold_eval.py`): Variant A (1 issue,
  `initial: execute`) or Variant B (2+ issues, `initial: discover`/`advance`),
  including Proof-First Gate `check_proof_<slug>` chaining/splicing when
  `learning_tests.enabled` and an issue's `learning_tests_required` is non-empty.
  Emits `<EXECUTE_PROMPT>`/`<EVALUATION_CRITERIA_PROMPT>` placeholder slots — the
  prompt/criteria text genuinely requires LLM synthesis. `dsl=True` is rejected
  with a pointer back to `/ll:create-eval-from-issues --dsl` (a separate,
  already-prose-only DSL task generator, out of scope here).
- `scaffold_verify` (`little_loops/cli/loop/scaffold_verify.py`): criteria mode
  (default) builds one `verify-criterion-N` state per `CriterionSlot` extracted
  via `IssueParser.extract_criteria()`; `adversarial=True` emits the fixed
  3-probe template (`probe-boundary`/`probe-malformed-hostile`/
  `probe-failure-mode` → non-LLM `count_probes` gate) verbatim. Timeout selection
  is code: 1800s criteria / 2700s adversarial. Output has no placeholder slots.
- `ScaffoldResult` (`little_loops/cli/loop/_scaffold_core.py`, shared by both):
  `yaml_path: Path | None`, `yaml_text: str`, `placeholders: list[str]`,
  `validated: bool`, `errors: list[str]`.
- `IssueParser.extract_criteria(issue_path) -> list[CriterionSlot]`
  (`little_loops/issue_parser.py`): generalizes `_parse_section_items()`'s
  section-location logic to extract top-level bullet text (checkboxes, plain
  bullets, numbered lists; indented sub-bullets skipped) from `## Acceptance
  Criteria`, falling back to `## Expected Behavior` when empty.

### main_issues

```python
def main_issues() -> int
```

Entry point for `ll-issues` command. Issue management and visualization utilities.

**Returns:** Exit code

**Sub-commands:**

| Sub-command | Description |
|-------------|-------------|
| `next-id` | Print next globally unique issue number; `--count N` / `-n N` emits N consecutive IDs from a single scan |
| `list` | List active issues with optional type/priority filters |
| `search` | Search issues with text query, filters, sorting, and multiple output formats |
| `count` | Count active issues with optional filters (`--type`, `--priority`, `--json`) |
| `show` | Show summary card for a single issue |
| `sequence` | Suggest dependency-ordered implementation sequence |
| `impact-effort` | Display impact vs effort matrix for active issues |
| `refine-status` | Refinement depth table sorted by commands touched (`--type`, `--format json`) |
| `next-action` | Next refinement action needed across all active issues (for FSM loop use) |
| `next-issue` | Single highest-confidence issue ID (alias: `nx`) |
| `next-issues` | All active issues in ranked order (alias: `nxs`); optional count argument |
| `append-log` | Append a session log entry to an issue file |
| `clusters` | Visualize issue dependency clusters as box diagrams (`--include-orphans`, `--min-connections N`, `--json`, `--edges SET`, `--status SET`) |
| `anchor-sweep` | Rewrite bare `file:line` references in active issue files to enclosing anchor form (`--dry-run`, `--issues-dir DIR`) |
| `fingerprint` | Extract structured fingerprint (id, files_to_modify, key_terms) from an issue file as JSON; used by `audit-issue-conflicts` Phase 2b (`--cross-theme`) |
| `find-similar` | Score title word-overlap similarity (Jaccard, `text_utils.py`) between text and the issue corpus, or pairwise via `--batch` (alias: `fs`); `--against open\|all`, `--threshold T`, `--limit N` (ENH-2941) |
| `check-flag` | Exit 0 if a named boolean frontmatter field equals `true`; takes `issue_id` and `field` positional args |
| `check-decidable` | Exit 0 if an issue has >=1 enumerable option to decide between (deterministic companion to `/ll:decide-issue --validate-only`, ENH-2443) |
| `check-readiness` | Exit 0 if `confidence_score` and `outcome_confidence` meet thresholds; reads from `ll-config.json` or `--readiness`/`--outcome` flags |
| `check-design` | Exit 0 if the Program Design gate passes for an issue; single owner of `design_gate_failed()` (ENH-2967) |
| `epic-consistency` | Detect and reconcile EPIC body/parent drift (`--all`, `--fix`, `--format text\|json`); exits non-zero when drift found in report-only mode |
| `deferred-triage` | List `deferred_by: automation` issues awaiting human triage, with reason + age (alias: `dt`) |

#### deferred-triage

```
ll-issues deferred-triage [--format text|json|markdown]
ll-issues dt [--format text|json|markdown]
```

Lists `status: deferred` issues with `deferred_by: automation` — the discriminator stamped by
`ll-issues set-status <ID> deferred --by automation --reason <code>` (see `mark_deferred` in
`loops/rn-implement.yaml`, and the equivalent not-ready exits in `loops/autodev.yaml` —
`mark_gate_blocked`, `record_decision_unresolved`, `recheck_after_size_review`,
`regate_after_atomic_remediation` (BUG-2734) — added by ENH-2666 to align autodev's not-ready
handling to the same model) — showing `deferred_reason` and age-since-`deferred_date`.
`recheck_after_size_review` writes `decision_unresolved` itself (ENH-2936, not just
`design_gate_failed`/`readiness_stagnated`/`low_readiness`) when its own re-check of
`decision_needed` on the score-failing path finds the flag still armed — a fourth
`decision_unresolved` source alongside `assert_decision_cleared` and
`check_decision_after_decide_error`.
`deferred_by: human` (or absent) issues are excluded.
`remediation_stalled` entries rank above `blocked_by_unmet`, above `gate_blocked`, above
`decision_unresolved`, above `oversized_atomic` (BUG-2734: readiness passed but a Very Large,
atomic issue's outcome risk failed even after Pattern-B rescoring), above `readiness_stagnated`
(FEAT-2751: every repair remedy including reconcile was attempted and Readiness never moved),
above `design_gate_failed` (ENH-2870: the deterministic `## Program Design` gate failed even
after the one-shot `refine_for_design` remedy — BUG-3002: retargeted from reconcile, whose
contract excludes that section), above `blocked_by_gate` (ENH-3148: caught by autodev's
pre-dequeue `check_gate_at_dequeue` state before the remediation ladder ever runs), above
`low_readiness`; ties break oldest-first. This
closes the cross-run resurfacing gap FEAT-2665 targets: `re_enqueue_unblocked` only
re-surfaces within a single run.

#### next-issue

```
ll-issues next-issue [--json] [--path] [--skip ISSUE_IDS] [--include-blocked]
ll-issues nx [--json] [--path] [--skip ISSUE_IDS] [--include-blocked]
```

Print the single highest-confidence active issue ID. Uses the same sort key as `next-issues`.

By default (ENH-2436), issues whose `Blocked By` references a non-terminal
(`done`/`cancelled`) issue are filtered out of the candidate set, so the
returned ID is always actionable. Pass `--include-blocked` to revert to the
legacy behavior (return any active issue, blocked or not).

EPIC-type ids are never returned (BUG-2638), in any output mode — EPICs are
umbrella containers meant to be decomposed via scope resolution, not implemented
as leaves.

**Output flags:**
- `--json` - Output as a JSON object with fields: `id`, `path`, `outcome_confidence`, `confidence_score`, `priority`. When `--include-blocked` is also set, the row additionally carries `blocked` (bool), `blocked_by` (sorted list of issue IDs), and `pending_prerequisites` (sorted list of still-open soft `depends_on` targets, ENH-2635). `blocked` reflects hard `blocked_by` edges only; combined with `pending_prerequisites` this distinguishes three states — **hard-blocked** (`blocked: true`), **soft-deferred** (`blocked: false` with a non-empty `pending_prerequisites`), and **ready** (`blocked: false`, `pending_prerequisites: []`). The default (no-flag) path already filters both hard and soft edges via `get_ready_issues()`, so it never returns a soft-deferred pick; this field only matters in the `--include-blocked` reporting mode.
- `--path` - Output only the file path instead of the issue ID

**Filter flags:**
- `--skip ISSUE_IDS` - Comma-separated list of issue IDs to exclude (e.g., `BUG-003,FEAT-004`). Useful in FSM loops to skip issues already attempted in the current session.
- `--include-blocked` (ENH-2436) - Re-include issues with unresolved blockers in the ranked output. Each JSON row carries `blocked` (bool), `blocked_by` (sorted list), and `pending_prerequisites` (sorted list of open soft `depends_on` targets, ENH-2635) fields when this flag is set.

**Exit codes:** 0 when an issue is found; 1 when no active issues exist or when every active issue is currently blocked (the latter surfaces `Error: No ready issues (N blocked, 0 ready)` on stderr).

**Strategy**: Config-driven via `issues.next_issue.strategy` (default `confidence_first`). See [`NextIssueConfig`](#nextissueconfig) for available presets and custom sort keys.

**Sort key (default, `confidence_first`)**: `-(outcome_confidence or -1)`, `-(confidence_score or -1)`, `priority_int` — byte-identical to the legacy hardcoded tuple.

**Configuration**: Switch strategies via `.ll/ll-config.json`:
```json
{
  "issues": {
    "next_issue": { "strategy": "priority_first" }
  }
}
```

**Examples:**
```bash
ll-issues next-issue                            # print top unblocked issue ID
ll-issues nx --json                             # top unblocked issue as JSON object
ll-issues nx --path                             # top unblocked issue file path
ll-issues nx --skip BUG-003,FEAT-004            # skip specific issues
ll-issues nx --include-blocked                  # include blocked issues (legacy behavior)
ll-issues nx --include-blocked --json           # JSON with blocked / blocked_by / pending_prerequisites
```

**FSM loop use**: Use `--skip` to avoid re-selecting issues already processed in the current loop run. Pair with `next-issues` when you need the full ranked list. Loops that need the legacy behavior (i.e. pick any active issue even if blocked) should pass `--include-blocked` to opt back in.

#### next-issues

```
ll-issues next-issues [COUNT] [--json] [--path] [--include-blocked]
ll-issues nxs [COUNT] [--json] [--path] [--include-blocked]
```

Print all active issues sorted by outcome confidence, readiness score, and priority. Returns one issue ID per line by default.

By default (ENH-2436), issues whose `Blocked By` references a non-terminal
(`done`/`cancelled`) issue are filtered out of the ranked list. Pass
`--include-blocked` to revert to the legacy behavior (return every active
issue, blocked or not).

EPIC-type ids are never included in the ranked list (BUG-2638), in any output
mode — EPICs are decomposed via scope resolution, not ranked as implementable
leaves. This also prevents an EPIC and its own children from being
double-dispatched into the same backlog wave.

**Arguments:**
- `COUNT` - Optional integer; limit output to top N issues

**Output flags:**
- `--json` - Output as a JSON array with fields: `id`, `path`, `outcome_confidence`, `confidence_score`, `priority`. When `--include-blocked` is also set, each row additionally carries `blocked` (bool), `blocked_by` (sorted list), and `pending_prerequisites` (sorted list of still-open soft `depends_on` targets, ENH-2635). As with `next-issue`, `blocked` reflects hard `blocked_by` edges only, so a row's state is **hard-blocked**, **soft-deferred** (non-empty `pending_prerequisites`), or **ready** (both empty).
- `--path` - Output one file path per line instead of IDs

**Filter flags:**
- `--include-blocked` (ENH-2436) - Re-include issues with unresolved blockers in the ranked list. Each JSON row carries `blocked`, `blocked_by`, and `pending_prerequisites` (open soft `depends_on` targets, ENH-2635) fields when set.

**Exit codes:** 0 when at least one unblocked issue is found; 1 when no active issues exist or when every active issue is currently blocked (the latter surfaces `Error: No ready issues (N blocked, 0 ready)` on stderr).

**Strategy**: Config-driven via `issues.next_issue.strategy` (default `confidence_first`). See [`NextIssueConfig`](#nextissueconfig) for available presets and custom sort keys.

**Sort key (default, `confidence_first`)**: `-(outcome_confidence or -1)`, `-(confidence_score or -1)`, `priority_int` — byte-identical to the legacy hardcoded tuple.

**Configuration**: Switch strategies via `.ll/ll-config.json`:
```json
{
  "issues": {
    "next_issue": { "strategy": "priority_first" }
  }
}
```

**Examples:**
```bash
ll-issues next-issues                       # all unblocked issues ranked
ll-issues next-issues 5                     # top 5 unblocked
ll-issues nxs --json                        # unblocked list as JSON array
ll-issues nxs --path                        # unblocked list as file paths
ll-issues nxs --include-blocked --json      # JSON with blocked / blocked_by / pending_prerequisites
```

**FSM loop use**: Pair with `ll-issues next-issue` (singular) when you need only the top item; use `next-issues` when you want to seed a loop queue or inspect the full ranked backlog. Loops that need the legacy behavior (i.e. include blocked issues in the queue) should pass `--include-blocked`.

#### search

```
ll-issues search [QUERY] [OPTIONS]
```

Search across issues with rich filtering, sorting, and output options.

**Arguments:**
- `QUERY` - Optional text to match against title and body (case-insensitive substring)

**Filters:**
- `--type {BUG,FEAT,ENH,EPIC}` - Filter by issue type (repeatable)
- `--priority P` - Filter by priority P0–P5 or range e.g. `P0-P2` (repeatable)
- `--status {open,in_progress,blocked,deferred,done,cancelled,all}` - Filter by status (default: `open`)
- `--include-completed` - Include issues of all statuses (alias for `--status all`)
- `--label LABEL` - Filter by label tag in the `## Labels` section (repeatable)
- `--since DATE` - Only issues discovered on or after DATE (`YYYY-MM-DD`)
- `--until DATE` - Only issues discovered on or before DATE (`YYYY-MM-DD`)
- `--date-field {discovered,updated}` - Date field to filter on (default: `discovered`)

**Sorting:**
- `--sort {priority,id,date,type,title}` - Sort field (default: `priority`)
- `--asc` / `--desc` - Sort direction (default: asc except date which defaults to desc)

**Output:**
- `--json` - Output as JSON array with fields: `id`, `priority`, `type`, `title`, `path`, `status`, `discovered_date`
- `--format {table,list,ids}` - Output format (default: `table`)
- `--limit N` - Cap results at N

**Examples:**
```bash
ll-issues search                           # list all open issues
ll-issues search "caching" --status all
ll-issues search --type BUG --priority P0-P2
ll-issues search --since 2026-01-01 --sort date
ll-issues search --label api --json
ll-issues search --type BUG --format ids
```

#### show

```
ll-issues show <issue_id>
```

Display a formatted summary card for a single issue. Accepts three input formats:
- Numeric ID: `ll-issues show 518`
- Type + ID: `ll-issues show FEAT-518`
- Priority + Type + ID: `ll-issues show P3-FEAT-518`

Searches all type directories regardless of status. Displays a box-drawing character card with:
- **Metadata**: priority, status, effort, risk level
- **Scores**: confidence score, outcome confidence (when present in frontmatter)
- **Details**: summary text (word-wrapped to fit card width), source (`discovered_by` alias), norm (✓/✗ filename convention check), fmt (✓/✗ required sections check), integration file count, labels, session log history with command counts
- **Path**: relative path from project root

**`--json` output fields**: `issue_id`, `title`, `priority`, `status`, `effort`, `confidence`, `outcome`, `score_complexity`, `score_test_coverage`, `score_ambiguity`, `score_change_surface`, `summary`, `integration_files`, `risk`, `labels`, `history`, `path`, `source`, `norm`, `fmt`. ENH-2535 added the following additive keys (all `str | None`; absent when the source issue lacks the field): `raw_status`, `decision_ref`, `closing_note`, `closed_reason`, `cancelled_reason`, `deferred_reason`, `closed_by`, `closed_at`, `deferred_date`, `closure_text`, `discovered_date`, `discovered_commit`, `discovered_branch`, `discovered_source`, `discovered_external_repo`, `parent`, `parent_display`, `relates_to`, `depends_on`, `blocked_by`, `blocks`, `supersedes`, `superseded_by`, `decomposed_into`, `affects`, `focus_area`, `testable`.

### main_history

```python
def main_history() -> int
```

Entry point for `ll-history` command. Display summary statistics, analysis, and synthesized documentation for completed issues.

**Returns:** Exit code

**Sub-commands:**

| Sub-command | Description |
|-------------|-------------|
| `summary` | Show issue statistics (count, velocity, type/priority breakdown). `--since`/`-S` and `--until` (`YYYY-MM-DD`) restrict the window and add loop-run counts (ENH-3237); `--json` output includes `source` (`"issue_events"` or `"files"`) naming which store answered |
| `analyze` | Full analysis with trends, subsystems, and debt metrics |
| `export` | Export topic-filtered excerpts from completed issue history |
| `rework` | Reopen/follow-up/touch-back/revert rates and quality-adjusted throughput (FEAT-2867) |

**Global options (all sub-commands):**
- `--intent QUERY` - Intent query for output filtering (no-op until FTS5 ranking lands; ENH-1114)
- `--intent-limit N` - Max lines for intent-filtered output (default: `50`)

#### export

```
ll-history export <topic> [options]
```

Exports a markdown document from completed issues matching a topic.

**Arguments:**
- `topic` - Topic, area, or system to generate documentation for

**Options:**
- `--output PATH` - Write output to file instead of stdout
- `-f, --format {narrative,structured}` - Output format (default: `narrative`)
- `-d, --directory PATH` - Path to issues directory (default: `.issues`)
- `--since DATE` - Only include issues completed after DATE (YYYY-MM-DD)
- `--min-relevance FLOAT` - Minimum relevance score threshold (default: `0.5`)
- `--type {BUG,FEAT,ENH,EPIC}` - Filter by issue type
- `--scoring {intersection,bm25,hybrid}` - Relevance scoring method (default: `intersection`)

**Scoring modes:**
- `intersection` (default): fraction of topic words appearing in the issue — best recall, no corpus needed
- `hybrid`: `intersection * 0.5 + normalized_bm25 * 0.5` — blends recall and ranking precision
- `bm25`: normalized BM25 score only — ranks by term frequency and IDF weighting

**Example:**
```bash
# Default intersection scoring
ll-history export "session logging" --output docs/arch/session.md

# Hybrid scoring for better ranking among many results
ll-history export "sprint CLI" --scoring hybrid --min-relevance 0.3

# BM25-only for precision-focused ranking
ll-history export "dependency resolution" --scoring bm25 --format structured
```

### main_messages

```python
def main_messages() -> int
```

Entry point for `ll-messages` command. Extract user messages from Claude Code logs.

**Returns:** Exit code

**CLI Arguments:**
- `-n, --limit` - Maximum messages to extract (default: 100)
- `--since` - Only messages after date (YYYY-MM-DD or ISO format)
- `-o, --output` - Output file path
- `--cwd` - Working directory to use
- `--exclude-agents` - Exclude agent session files
- `--stdout` - Print to stdout instead of file
- `-v, --verbose` - Verbose progress output
- `--skill` - Filter to sessions where this skill was invoked
- `--examples-format` - Output (input, output) training pairs (requires `--skill`); mutually exclusive with `--sft-format`
- `--sft-format` - Output conversation turns in SFT training format (`chatml`/`alpaca`/`sharegpt`); mutually exclusive with `--examples-format`
- `--context-window` - Number of context turn-pairs per window in `--examples-format` or `--sft-format` (default: 3)

### main_sprint

```python
def main_sprint() -> int
```

Entry point for `ll-sprint` command. Define and execute curated issue sets with dependency-aware wave ordering.

**Returns:** Exit code

**Sub-commands:** `create`, `edit`, `list`, `show`, `delete`, `run`, `resume`, `status`

### main_parallel

```python
def main_parallel() -> int
```

Entry point for `ll-parallel` command. Process issues concurrently using isolated git worktrees.

**Returns:** Exit code

**CLI Arguments:**
- `--workers` - Number of parallel workers (short: `-w`)
- `--timeout` - Per-issue timeout in seconds
- `--only` - Comma-separated issue IDs to process exclusively

### main_sync

```python
def main_sync() -> int
```

Entry point for `ll-sync` command. Sync local issues with GitHub Issues (bidirectional push/pull).

**Returns:** Exit code

**Sub-commands:** `push`, `pull`, `status`, `reset`

### main_deps

```python
def main_deps() -> int
```

Entry point for `ll-deps` command. Cross-issue dependency analysis and validation.

**Returns:** Exit code

**Global options:**
- `--intent QUERY` - Intent query for output filtering (no-op until FTS5 ranking lands; ENH-1114)
- `--intent-limit N` - Max lines for intent-filtered output (default: `50`)

**Sub-commands:** `analyze`, `validate`, `fix`, `apply`, `tree`

### main_verify_docs

```python
def main_verify_docs() -> int
```

Entry point for `ll-verify-docs` command. Verify that documented counts match actual file counts in the project.

### main_verify_des_audit

```python
def main_verify_des_audit() -> int
```

Entry point for `ll-verify-des-audit` command (ENH-2475). Walk the source tree, classify every event-emit site against the canonical `DES_VARIANTS` registry, and exit 0 iff every currently-emitted event has a registered variant — the F5 adoption gate (EPIC-2456 § Tier 1).

**Returns:** Exit code

### main_check_links

```python
def main_check_links() -> int
```

Entry point for `ll-check-links` command. Check markdown documentation for broken links, classifying failures as broken (host answered, said no) or unreachable (network timeout/DNS/connection - broken-only gates the exit code by default; `--strict-network` restores the old behavior).

**Returns:** Exit code

---

### main_logs

```python
def main_logs() -> int
```

Entry point for `ll-logs` command. Discover, extract, sequence, and tail Claude Code session logs for ll-loop and ll-commands.

**Returns:** 0 on success, 1 when no subcommand given or on error

`--project DIR`/`--all` (via `cli_args.add_corpus_target_args()`) and the window flags `--window-days D`/`--since DATE`/`--until DATE` (via `cli_args.add_window_args()`) are shared across `sequences`/`stats`/`scan-failures`/`dead-skills`/`loop-fleet`, resolved by `cli/logs.py`'s `_resolve_window()` into a single UTC-aware `(cutoff, until)` pair. `--since` is mutually exclusive with `--window-days` (both express a lower bound); `--until` composes with either for a closed date range. `--since` later than `--until` exits non-zero.

**Subcommands:**
- `discover` — List all Claude projects with ll activity (no flags)
- `extract` — Extract ll-relevant JSONL records to `logs/<slug>/<session-id>.jsonl`; requires `--project DIR` or `--all`; optional `--cmd TOOL` to filter by CLI tool
- `sequences` — Extract tool-chain n-grams of ll invocations from JSONL logs; requires `--project DIR` or `--all`; options: `--min-len N` (default 2), `--min-count M` (default 1), `--top N`, `--window-days D`/`--since DATE`/`--until DATE`, `--json`; JSON schema: `[{chain: [str], count: int, edges: [{from, to, freq, pmi?, lift?}], pmi?: float, lift?: float}]`; `pmi` and `lift` are additive optional fields (present when the corpus has sufficient unigram data); `lift < 1.0` means the pair co-occurs at or below the frequency-prior baseline (frequency-prior-equivalent)
- `stats` — Aggregate per-skill invocation frequency and correction rate from `skill_events` in `.ll/history.db`; requires `--project DIR` or `--all`; options: `--window-days D`/`--since DATE`/`--until DATE`, `--sort {freq,corrections}` (default freq), `--json`; JSON schema: `[{skill: str, invocations: int, corrections: int, correction_rate: float}]`
- `dead-skills` — Cross-reference skill catalog against log corpus to flag never/rarely-invoked skills; requires `--project DIR` or `--all`; options: `--window-days D`/`--since DATE`/`--until DATE`, `--threshold N` (default 3), `--sort {tier,name}` (default tier: never before rarely, then invocation count), `--json`; JSON schema: `[{skill: str, invocations: int, tier: "never"|"rarely"}]`; excludes bridge skills and `disable-model-invocation: true` entries
- `scan-failures` — Mine failed `ll-*` Bash calls from interactive session JSONL logs; requires `--project DIR` or `--all`; options: `--window-days D`/`--since DATE`/`--until DATE`, `--limit N` (top N clusters by count, 0 = unlimited default), `--skill NAME` (limit to clusters attributed to skill NAME; `ll:` prefix optional), `--json`, `--capture`; clusters failures by `(tool, normalized-error-signature)`, suppresses transient errors and `ll-verify-*` expected-nonzero gates; JSON schema: `[{tool: str, count: int, normalized_sig: str, sample_error: str, session_ids: [str], skills: [str]}]`; `skills` is the sorted list of skills attributed to the cluster (unattributed excluded, `[]` when none); under `--skill NAME`, `count`/`session_ids` are re-projected to that skill's subset of the cluster. Skill attribution is heuristic, tracked via a stream-tracking pass over `<command-name>` markers and `Skill` tool_use blocks — it identifies `ll-*` CLI failures that occurred *while* a skill was the enclosing context, not failures of that skill's own `Read`/`Edit`/`Grep` calls. `--capture` creates a BUG issue file per cluster via `create_issue_from_failure()` (unaffected by `--skill`'s count re-projection, since capture reads only `tool_name`/`sample_error`/`cwd_path`)
- `loop-fleet` — Aggregate cross-project loop-run outcomes from `.loops/.history/*/events.jsonl` for built-in loop improvement; requires `--project DIR` or `--all`; options: `--loop NAME` (filter to one loop), `--window-days D`/`--since DATE`/`--until DATE`, `--existing-only` (skip dead worktrees; meaningful with `--all`), `--sort {success,name}` (default success: ascending/worst-first), `--limit N` (caps `--json` per-run rows only, not the aggregated table; 0 = unlimited default), `--json`; reads the `loop_complete` terminal event from each archived run dir, derives outcome (`converged`/`failed`/`max-steps`/`stalled`/`interrupted`/`error`), and attributes each loop as `builtin` (name matches a shipped `little_loops/loops/**/*.yaml`) or `custom`; default output: per-loop table (Loop, Type, Runs, Success%, Med-Iter, Top Outcome, Projects); JSON schema (one record per run, sorted newest-first): `[{loop_name: str, project: str, run_folder: str, final_state: str, iterations: int, outcome: str, ts: str, attribution: "builtin"|"custom"}]`; complements `scan-failures` (session-layer) with FSM-run-layer diagnostics; use `-j` output as input to `ll-loop validate`/`diagnose-evaluators`/`loop-specialist`
- `diff` — Compare two sessions' ll-invocation behavior; positional args: `SESSION_A SESSION_B` (session ID or JSONL path); option: `--json`; reports added/removed skills, invocation count deltas, and unified sequence diff; JSON schema: `{session_a: str, session_b: str, skills_added: [str], skills_removed: [str], count_deltas: {skill: {a: int, b: int, delta: int}}, sequence_diff: [str]}`; resolves session IDs via `sessions` table in `.ll/history.db`
- `eval-export` — Reconstruct `ll-harness` eval fixtures (EvalFixture v1) from session logs; optional `--project DIR` (default: cwd), `--skill NAME`, `--issue ID`, `--limit N` (0 = unlimited), `--out PATH` (default: stdout), `--json` (default: YAML). Walks the project's JSONL via the ENH-1919 invocation extractor, sources an **execution** outcome (`accepted`/`corrected`/`failed`; `unknown` records are skipped with a logged count) from `history_reader.lookup_session_metadata()`, and best-effort-redacts `input_context` (PII + absolute paths, flagged by `pii_detected`). ll-harness has **no fixture loader** — a fixture replays by serializing its fields into `ll-harness <runner> <target> [runner_args...] [--exit-code N] [--semantic TEXT] [--timeout S]`. Fixture fields: `runner` (skill|cmd), `target`, `session_id`, `timestamp`, `outcome`, `runner_args`, `exit_code`, `semantic`, `timeout`, `input_context`, `issue_id`, `skill_name`, `pii_detected`. Schema + outcome taxonomy fixed by decision ARCHITECTURE-017 in `.ll/decisions.yaml` (FEAT-1968). Example record:
  ```yaml
  - runner: skill
    target: refine-issue
    session_id: 9c1f-...
    timestamp: '2026-06-06T00:00:00Z'
    outcome: accepted
    runner_args: []
    exit_code: null
    semantic: null
    timeout: 120
    input_context: refine FEAT-1971 in the backlog
    issue_id: FEAT-1971
    skill_name: refine-issue
    pii_detected: false
  ```
- `tail` — Stream live events from an active loop session; requires `--loop NAME`; optional `--project DIR`

---

### main_session

```python
def main_session() -> int
```

Entry point for `ll-session` command. Query the unified session store (SQLite + FTS5) — the per-project `.ll/history.db`.

**Returns:** 0 on success, 1 when no subcommand given or on error

**Global flags:**
- `--db PATH` — Path to the session database (default: `.ll/history.db`)

**Subcommands:**
- `search` — FTS5 full-text query with BM25-ranked results; requires `--fts QUERY`, optional `--kind` (choices come from `VALID_KINDS`: `tool,file,issue,loop,correction,message,skill,cli,snapshot,commit,test_run,usage,orchestration_run,loop_run,learning_test,session_lifecycle`), `--limit N` (default 20), `--json`
- `recent` — Most recent rows for an event kind; requires `--kind` (same `VALID_KINDS` choices as `search`, or `--issue ID` to list sessions for an issue); optional `--limit N` (default 20), `--json`
- `backfill` — Ingest on-disk sources; issue/loop-state/commit data is written directly, session JSONL lines go into `raw_events` only (ENH-2581). `--rebuild` also materializes the JSONL-derived cache tables in the same call (equivalent to a following `rebuild`). `--since DATE` (ISO 8601 or YYYY-MM-DD) uses incremental JSONL-only mode via `backfill_incremental()` (ENH-1830). `--host {claude-code,codex,opencode,pi,kimi-code,qwen}` selects the host for session log discovery (default: auto-detect from ``LL_HOOK_HOST`` env var); full backfill (no ``--since``) also uses ``--host`` for JSONL file discovery (ENH-1945). For `qwen`, session JSONL is discovered under the project folder's `chats/` subdirectory and subagent transcripts under `subagents/<session-id>/` are backfilled into `subagent_runs` with `agent_id`/`agent_type`/timestamps/`status` sourced from each transcript's `.meta.json` sidecar (ENH-3165). Ingested rows are stamped with the `--host` value in `raw_events.host` (not the ambient host), and qwen records are normalized into Claude shape at rebuild time — `parts[]`→`content[]`, `functionCall`/`functionResponse`→`tool_use`/`tool_result`, tool names canonicalized (`run_shell_command`→`Bash`, …), only `provenance: real_user` user records without a subtype reach `message_events`, and `ui_telemetry` records are skipped at ingest (ENH-3166). `--extract-decisions` runs decision mining after backfill (ENH-2152). `--snapshots` hydrates the `issue_snapshots` table from existing `.issues/` files (ENH-2151)
- `rebuild` — Wipe+re-derive the JSONL-derived cache tables (and their `search_index` rows) from `raw_events`; optional `--config PATH`, `--json` (ENH-2581)
- `compact` — Sweep `raw_events` rows past the retention cutoff into per-session `kind='retention'` summary nodes, marking them `compacted=1`; optional `--and-prune` (also runs `prune` afterward), `--config PATH`, `--json` (ENH-2581)
- `related` — Issue events for a given issue ID; requires `ISSUE_ID` positional arg, optional `--limit N` and `--json`
- `path` — Resolve and print the JSONL file path for a session ID; exits non-zero if unknown
- `grep` — Regex search over `message_events` with optional summary-node context; requires `PATTERN`, optional `--summary-id ID`, `--limit N` (default 50), `--json`
- `expand` — Return `message_events` covered by a summary node; requires `SUMMARY_ID`, optional `--json`
- `describe` — Show metadata for a summary node; requires `NODE_ID`, optional `--json`
- `prune` — Delete `raw_events` rows already marked `compacted=1` past the configured max-age, then VACUUM the database; optional `--dry-run`, `--json` (ENH-2581 — previously deleted directly from `tool_events`/`cli_events`/`file_events`/`message_events`)

---

### main_queue

```python
def main_queue() -> int
```

Entry point for `ll-queue` command (FEAT-2682). Persisted work-item queue backed by `.ll/queue.db` (`little_loops.queue_store`) — distinct from `ll-loop queue`'s PID-liveness marker mechanism.

**Returns:** 0 on success, 1 on not-found/ambiguous id, 2 on a malformed `--arg`

**Subcommands:**
- `add TARGET` — Classify and persist a new entry. Without `--runner`, `TARGET` is classified in order: an FSM loop name (resolves via `resolve_loop_path`), a skill/command name (resolves via `skills/<name>/SKILL.md` / `commands/<name>.md`), else a raw CLI invocation. Optional `--priority {P0..P5}` (default `P3`), `--runner {skill,cmd,mcp,prompt,loop}` (skip classification), `--arg KEY=VALUE` (repeatable), `--timeout N` (default 120), `--json`
- `list` — List all entries ordered by priority tier then FIFO within tier; optional `--json`, `--wide` (untruncated args/timeout/elapsed summary, ENH-2931)
- `status ID` — Show one entry by full id or 8+-char prefix; optional `--json`
- `remove ID` — Delete a `pending` entry by full id or 8+-char prefix; `--force` removes a non-pending entry too; optional `--json`
- `run` — Serially dequeue and dispatch `pending` entries in priority/FIFO order (FEAT-2683). Optional `--json` (single array; NDJSON under `--watch`). `--watch` (FEAT-2930) turns this into a long-lived drainer: after draining, sleep-polls (`--poll-interval`, default 3s) for new entries instead of exiting. Shutdown is two-stage — a first `SIGINT`/`SIGTERM` finishes the in-flight entry and exits 0 without claiming more; a second forwards `SIGTERM` to an in-flight `LOOP` child's process group, marks that entry `failed` with `error: "interrupted by operator"`, and exits 0. Also runs `_reclaim_stale` on startup and each idle poll, returning `running` entries with a dead `owner_pid` to `pending`
- `requeue ID [--force]` — Return a stranded `running` entry to `pending` (FEAT-2930). Without `--force`, refuses if the owner still looks alive (same psutil identity check `_reclaim_stale` uses); `--force` overrides for the "owner alive but wedged" case. Optional `--json`

---

### main_history_context

```python
def main_history_context() -> int
```

Entry point for `ll-history-context` command. Query `.ll/history.db` for user corrections and FTS5 matches related to an issue ID and render a `## Historical Context` markdown block.

**Returns:** 0 on success (including empty output when no matches or DB absent), 1 on argument error

**Flags:**
- `ISSUE_ID` — Issue ID to query (required positional argument)
- `--file PATH` — Also include recent file events for this path (optional)
- `--db PATH` — Path to the session database (default: `.ll/history.db`)
- `--effort` — Output a `## Effort Context` block with per-issue session count and cycle time (ENH-1905)
- `--for-skill NAME` — Exit 0 with no output if NAME is not in `history.planning_skills` (ENH-1909)

**Behavior:**
- Calls `find_user_corrections(topic=issue_id)` and `search(query=issue_id, kind="correction")` with deduplication
- Post-filters `search()` results by staleness (no built-in stale filter in `search()`)
- Optionally calls `recent_file_events(path=file)` when `--file` is given
- Caps output at 5 rows
- Returns empty output when DB is missing, no matches, or all rows stale

---

### main_learning_tests

```python
def main_learning_tests() -> int
```

Entry point for `ll-learning-tests` command. Query and manage the learning test registry.

**Returns:** 0 on success, 1 when target not found

**Subcommands:**
- `check <target>` — Print record JSON to stdout; exit 1 if not found
- `list` — Print all records as a JSON array
- `mark-stale <target>` — Set status=stale on a record; exit 1 if not found

---

### main_ctx_stats

```python
def main_ctx_stats() -> int
```

Entry point for `ll-ctx-stats` command. Show context-window analytics for the current project (FEAT-1160). Reads per-tool byte metrics that the `post_tool_use` hook persists into `.ll/history.db` (FEAT-1623) and renders a compact summary of how much data was processed by tools vs. how much actually entered the conversation context. Also aggregates skill-health signals (per-skill invocation frequency and correction rate) via `_aggregate_skill_stats()` from the same `.ll/history.db` (ENH-1921); when skill events are present a "Skill health" section is appended to the human-readable report and a `skill_health` array is included in `--json` output. When `usage_events` rows join to `loop_runs` on `run_id`, also renders a "Waste" section via `_aggregate_waste()` → `history_reader.waste_attribution()` (ENH-2722). Falls back to `.ll/ll-context-state.json` (token estimates) when the SQLite store is absent. When `--db` is not passed, the DB path resolves via `resolve_history_db()` (env `LL_HISTORY_DB` → `history.db_path` config → default), not a bare local constant (ENH-2722 fixed a prior bypass).

**Returns:** 0 when a report was rendered (data present or fallback used), 1 when no data found in either the SQLite store or the fallback file.

**Flags:**
- `--db PATH` — Use a non-default session database (default `.ll/history.db`; resolves `LL_HISTORY_DB` / `history.db_path` config when omitted)
- `--json` — Emit the report as JSON instead of the human-readable summary; includes `skill_health: [{skill, invocations, corrections, correction_rate}]` or `null`, and `waste: [{loop_name, tokens_total, tokens_wasted, waste_pct, runs_total, runs_wasted}]` or `null`

Enable per-tool byte tracking by setting `"analytics": {"enabled": true}` in `.ll/ll-config.json`. The `post_tool_use` hook reads this gate and no-ops when disabled or absent. Use `analytics.capture` for per-category control (e.g. `analytics.capture.file_events: false` disables file-event recording while keeping tool-event metrics active). See [CONFIGURATION.md § analytics.capture](CONFIGURATION.md#analyticscapture) for the full key reference.

---

### main_config

```python
def main_config() -> int
```

Entry point for `ll-config` command. Resolve and print a single dot-path configuration value via `BRConfig.resolve_variable()`. This is the CLI a markdown skill shells out to when it needs a resolved config value at runtime — the `{{config.path.to.value}}` template token syntax only expands under `ll-auto`'s `skill_expander.py` pre-expansion pass, so interactive/slash-command skill runs never see it substituted (ENH-2678).

**Returns:** 0 always — mirrors `resolve_variable()`'s never-raise, config-or-default contract.

**Subcommands:**
- `get <key>` — Print the resolved value for a dot-separated config path (e.g. `history.go_no_go.correction_penalty`); prints nothing for unknown keys.

---

## little_loops.workflow_sequence

Step 2 of a 3-step workflow analysis pipeline. Analyzes user message patterns to identify multi-step workflows, link related sessions, and detect workflow boundaries.

> **Note**: Previously exposed as `little_loops.workflow_sequence_analyzer` (monolithic module). Refactored in ENH-840 into a sub-package at `little_loops/workflow_sequence/`. The public API is unchanged — import from `little_loops.workflow_sequence`.

### Quick Example

```python
from pathlib import Path
from little_loops.workflow_sequence import analyze_workflows

# Analyze messages from Step 1 output
result = analyze_workflows(
    messages_file=Path(".ll/user-messages.jsonl"),
    patterns_file=Path(".ll/workflow-analysis/step1-patterns.yaml"),
    output_file=Path(".ll/workflow-analysis/step2-workflows.yaml"),
)

print(f"Found {len(result.workflows)} workflows")
print(f"Linked {len(result.session_links)} sessions")
```

### SessionLink

Represents a link between related sessions.

```python
@dataclass
class SessionLink:
    link_id: str                    # Unique identifier for the link
    sessions: list[dict[str, Any]]  # Session data with positions
    unified_workflow: dict[str, Any]  # Combined workflow metadata
    confidence: float               # Link confidence score (0.0-1.0)
```

#### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `to_dict()` | `dict` | Convert for YAML serialization |

### EntityCluster

Represents a group of messages sharing common entities.

```python
@dataclass
class EntityCluster:
    cluster_id: str                 # Unique identifier for the cluster
    primary_entities: list[str]     # Top 3 most common entities
    all_entities: set[str]          # All entities in the cluster
    messages: list[str]             # Message UUIDs in this cluster
    span: dict[str, str]            # Time span (first, last timestamps)
    inferred_workflow: str          # Inferred workflow type
    cohesion_score: float           # Cluster cohesion (0.0-1.0)
```

#### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `to_dict()` | `dict` | Convert for YAML serialization |

### WorkflowBoundary

Represents a potential boundary between workflows.

```python
@dataclass
class WorkflowBoundary:
    msg_a: str                      # UUID of first message
    msg_b: str                      # UUID of second message
    time_gap_seconds: float         # Time between messages
    time_gap_weight: float          # Boundary weight from time gap (0.0-1.0)
    entity_overlap: float           # Jaccard similarity of entities (0.0-1.0)
    final_boundary_score: float     # Combined boundary score
    is_boundary: bool               # True if score >= threshold
```

#### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `to_dict()` | `dict` | Convert for YAML serialization |

### Workflow

Represents a detected multi-step workflow.

```python
@dataclass
class Workflow:
    workflow_id: str                # Unique identifier
    name: str                       # Human-readable name
    pattern: str                    # Template pattern matched
    pattern_confidence: float       # Match confidence (0.0-1.0)
    messages: list[str]             # Message UUIDs in workflow
    session_span: dict[str, str]    # Time span (first, last)
    entity_cluster: str | None      # Related entity cluster ID
    semantic_cluster: str | None    # Related semantic cluster ID
    duration_minutes: float         # Workflow duration
    handoff_points: list[str]       # Detected handoff message UUIDs
```

#### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `to_dict()` | `dict` | Convert for YAML serialization |

### WorkflowAnalysis

Complete output container for all analysis results.

```python
@dataclass
class WorkflowAnalysis:
    metadata: dict[str, Any]                # Analysis metadata
    session_links: list[SessionLink]        # Linked sessions
    entity_clusters: list[EntityCluster]    # Entity-based clusters
    workflow_boundaries: list[WorkflowBoundary]  # Detected boundaries
    workflows: list[Workflow]               # Detected workflows
    handoff_analysis: dict[str, Any]        # Handoff statistics
```

#### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `to_dict()` | `dict` | Convert for YAML serialization |

### analyze_workflows

```python
def analyze_workflows(
    messages_file: Path,
    patterns_file: Path,
    output_file: Path | None = None,
) -> WorkflowAnalysis
```

Main entry point for workflow sequence analysis (Step 2 of pipeline).

**Parameters:**
- `messages_file` - Path to JSONL file with user messages
- `patterns_file` - Path to YAML file from Step 1 (pattern analysis)
- `output_file` - Optional output path for YAML results

**Returns:** `WorkflowAnalysis` with all analysis results

**Example:**
```python
from pathlib import Path
from little_loops.workflow_sequence import analyze_workflows

result = analyze_workflows(
    messages_file=Path(".ll/user-messages.jsonl"),
    patterns_file=Path(".ll/workflow-analysis/step1-patterns.yaml"),
)

for workflow in result.workflows:
    print(f"{workflow.name}: {len(workflow.messages)} messages")
    print(f"  Pattern: {workflow.pattern}")
    print(f"  Duration: {workflow.duration_minutes:.1f} min")
```

### Helper Functions

#### extract_entities

```python
def extract_entities(content: str) -> set[str]
```

Extract entities from message content using regex patterns.

**Parameters:**
- `content` - Message text to analyze

**Returns:** Set of extracted entities (file paths, issue IDs, commands, etc.)

**Example:**
```python
from little_loops.workflow_sequence import extract_entities

entities = extract_entities("Fix BUG-123 in src/utils.py using /ll:manage-issue")
# Returns: {"BUG-123", "src/utils.py", "/ll:manage-issue"}
```

#### calculate_boundary_weight

```python
def calculate_boundary_weight(gap_seconds: int) -> float
```

Map time gaps to boundary weights using tiered thresholds.

**Parameters:**
- `time_gap_seconds` - Time gap between messages in seconds

**Returns:** Weight from 0.0 (same task) to 0.95 (likely different workflow)

**Thresholds:**
- < 30s → 0.0 (same task)
- 30s-2min → 0.1
- 2-5min → 0.3
- 5-15min → 0.5
- 15-30min → 0.7
- 30min-2h → 0.85
- > 2h → 0.95 (likely different workflow)

#### entity_overlap

```python
def entity_overlap(entities_a: set[str], entities_b: set[str]) -> float
```

Calculate Jaccard similarity between two entity sets.

**Parameters:**
- `entities_a` - First entity set
- `entities_b` - Second entity set

**Returns:** Jaccard coefficient (0.0-1.0), or 0.0 if either set is empty

#### get_verb_class

```python
def get_verb_class(content: str) -> str | None
```

Extract verb class from message content.

**Parameters:**
- `content` - Message text to analyze

**Returns:** Verb class name or `None` if no match

**Classes:** `deletion`, `modification`, `creation`, `search`, `verification`, `execution`

#### semantic_similarity

```python
def semantic_similarity(
    msg_a: dict[str, Any],
    msg_b: dict[str, Any],
    patterns: dict[str, Any],
) -> float
```

Calculate weighted similarity between two messages.

**Parameters:**
- `msg_a` - First message dict
- `msg_b` - Second message dict
- `patterns` - Step 1 patterns data for category lookup

**Returns:** Similarity score (0.0-1.0)

**Weights:**
- Keyword overlap: 0.3
- Verb class match: 0.3
- Entity overlap: 0.3
- Category match: 0.1

### Constants

#### VERB_CLASSES

```python
VERB_CLASSES: dict[str, set[str]]
```

Mapping of verb class names to sets of related verbs:
- `deletion` - delete, remove, drop, etc.
- `modification` - update, modify, change, etc.
- `creation` - create, add, new, etc.
- `search` - find, search, look, etc.
- `verification` - test, verify, check, etc.
- `execution` - run, execute, build, etc.

#### WORKFLOW_TEMPLATES

```python
WORKFLOW_TEMPLATES: dict[str, list[str]]
```

Mapping of workflow pattern names to category sequences:
- `explore -> modify -> verify`
- `create -> refine -> finalize`
- `search -> analyze -> implement`

---

## Import Shortcuts

```python
# Main package imports
from little_loops.config import BRConfig
from little_loops.issue_parser import IssueParser, IssueInfo, find_issues
from little_loops.issue_manager import AutoManager
from little_loops.git_operations import (
    GitignorePattern,
    GitignoreSuggestion,
    suggest_gitignore_patterns,
    add_patterns_to_gitignore,
    get_untracked_files,
    check_git_status,
)
from little_loops.work_verification import verify_work_was_done, filter_excluded_files
from little_loops.state import StateManager, ProcessingState
from little_loops.logger import Logger, format_duration
from little_loops.user_messages import (
    UserMessage,
    get_project_folder,
    extract_user_messages,
    save_messages,
)

# Workflow analysis
from little_loops.workflow_sequence import (
    analyze_workflows,
    SessionLink,
    EntityCluster,
    WorkflowBoundary,
    Workflow,
    WorkflowAnalysis,
    extract_entities,
    calculate_boundary_weight,
    entity_overlap,
    get_verb_class,
    semantic_similarity,
)

# Parallel subpackage
from little_loops.parallel import (
    ParallelOrchestrator,
    WorkerPool,
    MergeCoordinator,
    ParallelConfig,
    WorkerResult,
)
from little_loops.parallel.priority_queue import IssuePriorityQueue
from little_loops.parallel.types import QueuedIssue, MergeRequest, MergeStatus
from little_loops.output_parsing import parse_ready_issue_output
```

---

## Usage Examples

### Basic Configuration Loading

```python
from pathlib import Path
from little_loops.config import BRConfig

# Load config from current directory
config = BRConfig(Path.cwd())

# Access settings
print(f"Project: {config.project.name}")
print(f"Source dir: {config.project.src_dir}")
print(f"Test command: {config.project.test_cmd}")

# Get issue directories
bugs_dir = config.get_issue_dir("bugs")
```

### Finding and Parsing Issues

```python
from pathlib import Path
from little_loops.config import BRConfig
from little_loops.issue_parser import find_issues, find_highest_priority_issue

config = BRConfig(Path.cwd())

# Find all issues
all_issues = find_issues(config)
print(f"Found {len(all_issues)} issues")

# Find only bugs
bugs = find_issues(config, category="bugs")

# Find highest priority issue
next_issue = find_highest_priority_issue(config)
if next_issue:
    print(f"Next: {next_issue.issue_id} ({next_issue.priority})")
```

### Running Sequential Automation

```python
from pathlib import Path
from little_loops.config import BRConfig
from little_loops.issue_manager import AutoManager

config = BRConfig(Path.cwd())
manager = AutoManager(
    config=config,
    max_issues=3,
    dry_run=True,  # Preview only
)
exit_code = manager.run()
```

### Running Parallel Automation

```python
from pathlib import Path
from little_loops.config import BRConfig
from little_loops.parallel import ParallelOrchestrator

br_config = BRConfig(Path.cwd())
parallel_config = br_config.create_parallel_config(
    max_workers=2,
    max_issues=5,
)

orchestrator = ParallelOrchestrator(
    parallel_config=parallel_config,
    br_config=br_config,
)
exit_code = orchestrator.run()
```

---

## little_loops.observability

DES (discriminated-union) variant registry for every event shape currently emitted to `.ll/history.db` (ENH-2475). The registry enumerates the full event surface so F5 (`observability/tracing.py`, EPIC-2456 § Tier 1) can adopt a canonical emit schema without runtime shape-coercion.

### little_loops.observability.schema

```python
from little_loops.observability.schema import DESVariant, DES_VARIANTS, DES_VARIANT_TYPES
```

Frozen dataclasses (per `little_loops.host_runner` value-object convention) keyed by a `type: Literal[...]` discriminator. Every variant matches a wire-format event type currently emitted from `scripts/little_loops/`:

| Export | Description |
|--------|-------------|
| `DESVariant` | Base frozen dataclass for every registered variant |
| `DES_VARIANTS` | `Final[Tuple[Type[DESVariant], ...]]` — every registered variant class |
| `DES_VARIANT_TYPES` | `Final[frozenset[str]]` — every discriminator string (the audit walker's allow-list) |

Each concrete variant subclasses `DESVariant` and declares its discriminator via `type: Literal["exact_string"] = "exact_string"`. Example:

```python
@dataclass(frozen=True)
class LoopStartVariant(DESVariant):
    """FSMExecutor._emit('loop_start') — FSM loop begins execution."""
    type: Literal["loop_start"] = "loop_start"
    loop: str = ""
```

### little_loops.observability.audit

```python
from little_loops.observability.audit import audit_tree, AuditResult
```

Static walker that classifies every emit site in a source tree against `DES_VARIANT_TYPES`. Two-phase detection (regex for positional string literals, AST for `event=...` keyword args) covers both `_emit("type", {...})` and `event_bus.emit({..., "event": "type", ...})` patterns.

```python
result = audit_tree(Path("scripts/little_loops"))
if not result.passed:
    for etype in result.uncovered_event_types:
        print(f"Uncovered event type: {etype}")
```

### little_loops.observability.tracing

```python
from little_loops.observability import (
    OTelAttributes, StampUsageEvent, StreamingParityChecker, vendor_for_runner,
)
```

OTel `gen_ai.*` attribute shaping + streaming-parity primitives (FEAT-2478). Emits
OpenTelemetry-semantic-convention-shaped attributes from internal token-usage rows
**without** an OTel SDK in-process. See
[docs/observability/otel-mapping.md](../observability/otel-mapping.md) for the full
internal-name ↔ OTel-canonical map.

- `OTelAttributes.from_usage(usage, vendor=None, invocation_id=None) -> dict` —
  shape a `TokenUsage` (or flat dict) into the canonical **dotted** `gen_ai.usage.*`
  attribute dict (`gen_ai.usage.cache_read.input_tokens`, not the underscore form).
- `StampUsageEvent.usage_event(row, vendor=None, invocation_id=None) -> dict` —
  non-destructively augment a flat usage row with `gen_ai.*` keys.
- `StreamingParityChecker(threshold=0.001).diff(blocking, streaming)` /
  `.within_threshold(...)` — gate the ENH-2479 0.1% cache-token parity threshold
  across all four token fields.
- `vendor_for_runner(name) -> str` — map a `HostRunner.name` to the
  `gen_ai.provider.vendor` addendum (`anthropic` / `openai` / `google` / `other`).

```python
attrs = OTelAttributes.from_usage(usage, vendor="anthropic", invocation_id=str(uuid4()))
# {"gen_ai.usage.input_tokens": ..., "gen_ai.usage.cache_read.input_tokens": ..., ...}
```

---

## little_loops.fsm

FSM (Finite State Machine) loop system for automation workflows. This subpackage provides the schema, compilation, evaluation, and execution engine for declarative automation loops.

### Submodule Overview

| Module | Purpose |
|--------|---------|
| `little_loops.fsm.schema` | FSM state machine schema definitions |
| `little_loops.fsm.evaluators` | Verdict evaluators (exit_code, llm_structured, etc.) |
| `little_loops.fsm.executor` | FSM execution engine. Optional `inbound` queue + `_drain_inbound()` (ENH-3351) let an external actor (e.g. `ll-loop run --serve`'s SSE bridge) re-enter the running executor as `artifact_interaction` events. |
| `little_loops.fsm.runners` | Action runner protocol and default/simulation implementations |
| `little_loops.fsm.types` | Core result types (`ExecutionResult`, `ActionResult`) |
| `little_loops.fsm.interpolation` | Variable substitution (`${context.*}`, etc.) |
| `little_loops.fsm.validation` | Schema validation utilities |
| `little_loops.fsm.persistence` | Loop state persistence |
| `little_loops.fsm.handoff_handler` | Context handoff signal handling |
| `little_loops.fsm.concurrency` | Scope-based lock management for concurrent loops |
| `little_loops.fsm.rate_limit_circuit` | Shared circuit-breaker state file for cross-worktree 429 coordination |
| `little_loops.fsm.signal_detector` | Pattern-based signal detection in action output |
| `little_loops.fsm.host_guard` | Adaptive host memory-pressure guard: `HostGuardConfig`, `HostGuard`, `RssSampler`, memory probes (ENH-2452/ENH-2453) |
| `little_loops.fsm.stall_detector` | `StallDetector` and `Stall` dataclass for circuit-breaker stall detection |
| `little_loops.fsm.fragments` | Fragment composition: `resolve_fragments()`, `resolve_inheritance()`, `resolve_flow()` |
| `little_loops.fsm.policy_rules` | Shared policy-rule grammar for decision-table routing: `parse_rules()`, `serialize_rules()`, `evaluate_rules()`, `Rule`, `Predicate` dataclasses. Single source of truth used by both `lib/policy-router.yaml` and `edit-routes` compound mode (ENH-2164) |
| `little_loops.fsm.route_table` | Route-table extraction, rendering, parsing, and application for `ll-loop edit-routes`. Includes standard matrix classes (`RouteTableExtractor`, `RouteTableRenderer`, `RouteTableParser`, `RouteTableApplier`) and compound decision-table classes added in ENH-2233 (`PolicyRuleExtractor`, `CompoundGridRenderer`, `CompoundGridParser`, `PolicyRuleApplier`) |

### Quick Import

```python
from little_loops.fsm import (
    # Schema
    FSMLoop, StateConfig, EvaluateConfig, RouteConfig, LLMConfig,
    TargetFileSpec, TargetStateSpec,
    # Validation
    ValidationError, validate_fsm, load_and_validate,
    # Interpolation
    InterpolationContext, InterpolationError, interpolate, interpolate_dict,
    # Evaluation
    EvaluationResult, evaluate, evaluate_exit_code, evaluate_output_numeric,
    evaluate_output_json, evaluate_output_contains, evaluate_convergence,
    evaluate_llm_structured,
    # Execution
    FSMExecutor, ExecutionResult, ActionResult, ActionRunner,
    # Persistence
    LoopState, StatePersistence, PersistentExecutor,
    list_running_loops, get_loop_history,
    # Rate Limiting
    RateLimitCircuit,
)
```

---

### little_loops.fsm.schema

Schema dataclasses for FSM loop definitions.

#### FSMLoop

Complete FSM loop definition.

```python
@dataclass
class FSMLoop:
    name: str                          # Unique loop identifier
    initial: str                       # Starting state name
    states: dict[str, StateConfig]     # State configurations
    description: str | None = None     # Free-text summary surfaced by `ll-loop list` and `--explain`
    context: dict[str, Any] = {}       # User-defined shared variables
    parameters: dict[str, ParameterSpec] = {}  # Declared loop inputs (validated at --from-yaml / --input)
    scope: list[str] = []              # Paths for concurrency control
    max_steps: int = 50                # Step cap (individual state executions)
    on_max_steps: str | None = None    # State to run once when step cap fires (ENH-1631)
    max_iterations: int | None = None  # Full-pass cap (maintain-mode restarts); None = no cap
    on_max_iterations: str | None = None  # State to run once when full-pass cap fires
    max_edge_revisits: int = 100       # Per-edge cycle detection limit (see below)
    backoff: float | None = None       # Seconds between iterations
    timeout: int | None = None         # Max runtime in seconds
    default_timeout: int | None = None # Per-action default when state.timeout is unset
    maintain: bool = False             # If True, restart after completion
    singleton: bool = False            # BUG-2526: serialize loop-name conflicts regardless of scope
    llm: LLMConfig = LLMConfig()       # LLM evaluation settings
    on_handoff: Literal["pause", "spawn", "terminate"] = "pause"  # ContextLimitHandoff handler
    input_key: str = "input"           # Context var that contains the initial input
    config: LoopConfigOverrides | None = None  # Per-loop ll-config.json overrides
    category: str = ""                 # Topical grouping for `ll-loop list` filtering (orthogonal to visibility)
    labels: list[str] = []             # Free-form tags surfaced by `ll-loop list --labels k=v`
    visibility: str = "public"         # Audience tier: "public" (user-facing), "internal" (sub-loop only), or "example" (template)
    required_inputs: list[str] = []    # Names of context vars that must be populated before invocation
    commands: list[CommandEntry] = []  # Optional Commands section override for ll-loop show
    targets: list[TargetFileSpec] = []  # Per-FSM-state targeting spec for harness-optimize APO (ENH-1552)
    circuit: CircuitConfig | None = None  # Top-level safety knobs; currently the stall detector (FEAT-1637)
    host_guard: HostGuardConfig = HostGuardConfig()  # ENH-2452 (memory pressure) + ENH-2453 (subprocess RSS budget)
    prompt_size_guard: PromptSizeGuardConfig = PromptSizeGuardConfig()  # ENH-2486 interpolated-prompt size guard (WARN-only)
    meta_self_eval_ok: bool = False       # Suppress MR-1/MR-2 meta-loop lint rules (ENH-1665)
    shared_state_ok: bool = False         # Suppress MR-3 artifact-isolation lint rule
    partial_route_ok: bool = False        # Suppress MR-4 partial-route dead-end lint rule (ENH-1917)
    artifact_versioning: bool = False     # Declare that this loop versions artifacts per-iteration (satisfies MR-5)
    artifact_versioning_ok: bool = False  # Suppress MR-5 artifact-versioning lint rule (ENH-1957)
    artifact_output: ArtifactOutput | None = None  # Loop->artifact handoff: promote run_dir deliverable to a durable path on terminal (FEAT-3309)
    artifact_mode: Literal["file", "template"] = "file"  # "template" promotes a .llat/ template directory (default templates_dir, not promotion_dir); verified by a runtime gate (FEAT-3318)
    generator_fix_ok: bool = False        # Suppress MR-6 generator-fix discipline lint rule (ENH-2079)
    bash_default_ok: bool = False         # Suppress MR-7 bash-default interpolation lint rule (ENH-2348)
    evidence_contract_ok: bool = False    # Suppress MR-8 evidence-contract lint rule (ENH-2342)
    shell_pid_ok: bool = False            # Suppress MR-9 over-escaped shell $$ PID-corruption lint rule (BUG-2368)
    parse_swallow_ok: bool = False        # Suppress MR-10 inline-Python parse-swallow lint rule
    unsafe_context_interpolation_ok: bool = False  # Suppress MR-11 unsafe raw context interpolation lint rule (BUG-2622)
    policy_dims_scored_ok: bool = False   # Suppress policy-table inactive-rubric-dim lint rule
    terminal_action_ok: bool = False      # Suppress terminal-action-ok (BUG-2813: dead action on terminal: true) lint rule
    abandonment_verdict_ok: bool = False  # Suppress MR-13 abandonment-verdict lint rule (ENH-2860)
    evaluate_unknown_keys_ok: bool = False  # Suppress MR-14 unknown-evaluate-key lint rule (ENH-2896)
    imports: list[str] = []               # Raw `import:` list from YAML (fragment metadata, not serialized by to_dict)
```

**Nested config dataclasses (FEAT-1637):**

```python
@dataclass
class RepeatedFailureConfig:
    window: int = 3                        # Consecutive identical triples required to fire
    on_repeated_failure: str = "abort"     # "abort" or name of a declared recovery state
    progress_paths: list[str] = field(default_factory=list)  # BUG-1674: opt-in fingerprint paths
    exclude_paths: list[str] = field(default_factory=list)   # BUG-1767: paths to exclude from fingerprint
    recurrent_window: int | None = None    # ENH-2245: total occurrences threshold (non-consecutive); None = disabled

@dataclass
class CircuitConfig:
    repeated_failure: RepeatedFailureConfig | None = None
```

The stall detector records `(state_name, exit_code, eval_verdict)` after every transition and fires when the last `window` triples are identical. When `on_repeated_failure == "abort"` the run terminates with `terminated_by="stall_detected"` (exit code 1); otherwise the executor routes to the named state. Each firing also emits a `stall_detected` event with `state`, `exit_code`, `verdict`, `consecutive`, and `action` fields.

**`progress_paths` — fingerprint-based reset (BUG-1674):** Loops with a check↔work ping-pong where the work state uses `next:` (no `evaluate:`) are invisible to the detector — only the eval-bearing state records triples, so three identical `check` verdicts fire the stall even when `work` made real file-level progress. Set `progress_paths` to a list of paths (supports `${env.PWD}` interpolation) to watch: if any path's `(mtime, size)` changes between two consecutive records for the same eval-bearing state, the rolling window resets. Empty by default — existing loops without this field retain current semantics.

**`exclude_paths` — bookkeeping file exclusion (BUG-1767):** When a loop's own internal tracking files (plan, DoD, scratchpad) are listed in `progress_paths`, every append to those files resets the stall window, silently disabling stall detection. Add such files to `exclude_paths` so the executor filters them out before computing the fingerprint. Paths support `${env.PWD}` interpolation. `ll-loop validate` emits a WARNING when a state action references a `progress_paths` file that is not also in `exclude_paths`.

**`recurrent_window` — non-consecutive stall detection (ENH-2245):** The consecutive detector only fires when the same triple appears N times *in a row*. Loops that cycle through intermediate states between each failure (e.g., `run_final_tests → continue_work → select_step → run_final_tests → ...`) never produce consecutive triples, so the consecutive guard never fires regardless of how many times the failure occurs. Set `recurrent_window: N` to also fire the circuit breaker when the same `(state, exit_code, verdict)` triple has been seen N times *total* across the run (non-consecutive). The same `on_repeated_failure` target and `stall_detected` event are reused; the event payload uses `recurrent` (total count) instead of `consecutive`. `null` (default) disables this check — existing loops are unaffected. Minimum value: 2.

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `to_dict()` | `dict` | Convert to dictionary for serialization |
| `from_dict(data)` | `FSMLoop` | Create from dictionary |
| `get_all_state_names()` | `set[str]` | All defined state names |
| `get_terminal_states()` | `set[str]` | States with `terminal=True` |
| `get_failure_states()` | `set[str]` | States with `failure=True` — the single source of truth for whether a run failed (ENH-2814) |
| `get_all_referenced_states()` | `set[str]` | All states referenced by transitions |

When any single state→state edge (e.g., `evaluate → fix`) is traversed more than `max_edge_revisits` times, the loop terminates immediately with `terminated_by="cycle_detected"` (exit code 1) rather than continuing until `max_steps` is reached. This prevents tight infinite loops where two states bounce between each other indefinitely without making progress. Edge counts are persisted in `LoopState` so they survive a `--resume`. The default value of `100` covers all practical loops; lower it on short single-purpose loops to catch regressions faster.

```yaml
# Example: tighten cycle guard on a short loop
name: quick-check
max_steps: 10
max_edge_revisits: 5   # terminate if any edge fires more than 5 times
```

**Example:**
```python
from little_loops.fsm import FSMLoop, StateConfig

fsm = FSMLoop(
    name="check-fix-loop",
    initial="check",
    states={
        "check": StateConfig(
            action="pytest",
            on_yes="done",
            on_no="fix",
        ),
        "fix": StateConfig(
            action="/ll:manage-issue bug fix",
            next="check",
        ),
        "done": StateConfig(terminal=True),
    },
    max_steps=20,
)
```

**Sub-loop composition example** — a parent loop that sequences two child loops:
```python
from little_loops.fsm import FSMLoop, StateConfig

# Parent loop: run quality gate, then commit changes
fsm = FSMLoop(
    name="quality-then-commit",
    initial="run_quality",
    states={
        "run_quality": StateConfig(
            loop="fix-quality-and-tests",   # Invokes .loops/fix-quality-and-tests.yaml
            context_passthrough=True,       # Share parent context; merge child captures back
            on_success="run_git",           # Alias for on_yes
            on_failure="done",              # Alias for on_no
        ),
        "run_git": StateConfig(
            loop="issue-refinement-git",
            on_success="done",
            on_failure="done",
        ),
        "done": StateConfig(terminal=True),
    },
    max_steps=5,
)
```

#### StateConfig

Configuration for a single FSM state.

```python
@dataclass
class StateConfig:
    action: str | None = None          # Command to execute
    action_type: str | None = None     # How to run action: "prompt", "slash_command", "shell", "mcp_tool"
    params: dict[str, Any] = field(default_factory=dict)  # MCP tool arguments (mcp_tool only)
    evaluate: EvaluateConfig | None = None  # Evaluator configuration
    route: RouteConfig | None = None   # Full routing table
    on_yes: str | None = None          # Shorthand routing
    on_no: str | None = None           # Shorthand routing
    on_error: str | None = None        # Shorthand routing
    on_partial: str | None = None      # Shorthand routing for partial verdict
    on_blocked: str | None = None      # Shorthand routing for blocked verdict
    next: str | None = None            # Unconditional transition
    terminal: bool = False             # End state marker
    failure: bool = False              # Terminal means the run FAILED (ENH-2814); defaults true for states named failed/error/aborted/finalize_aborted
    capture: str | None = None         # Variable name to store output
    append_to_messages: str | None = None  # Append captured value to message history
    timeout: int | None = None         # Action timeout in seconds
    on_maintain: str | None = None     # State for maintain mode restart
    max_retries: int | None = None     # Max consecutive re-entries before on_retry_exhausted
    on_retry_exhausted: str | None = None  # State when max_retries exceeded
    retryable_exit_codes: list[int] | None = None  # Exit codes that trigger retry (for shell states)
    loop: str | None = None            # Sub-loop to invoke (name from .loops/<name>.yaml)
    context_passthrough: bool = False  # Pass parent context vars to child; merge child captures back
    with_: dict[str, Any] = field(default_factory=dict)  # Explicit parameter bindings for sub-loop calls
    worktree: str | None = None        # Branch-name template; child runs in a scratch worktree on that branch (sub-loop states only, ENH-2609)
    fragment_name: str | None = None   # Original fragment name (populated by resolve_fragments)
    fragment_bindings: dict[str, Any] = field(default_factory=dict)  # Parameter bindings for fragment references
    fragment_parameters: dict[str, Any] = field(default_factory=dict)  # Parsed ParameterSpec declarations
    agent: str | None = None           # Subprocess agent name; passes --agent <name> to Claude CLI (prompt states only)
    tools: list[str] | None = None     # Subprocess tool scope; passes --tools <csv> to Claude CLI (prompt states only)
    model: str | None = None           # Model override for this state's LLM action
    effort: str | None = None          # Reasoning-effort override (low/medium/high/xhigh/max); config-resolved fallback via state.effort or self.run_effort or self.fsm.llm.effort (ENH-2869); action_complete payload prefers the host CLI's actually-applied effort observed from the session JSONL when available (ENH-2885)
    extra_routes: dict[str, str] = field(default_factory=dict)  # Additional on_<verdict> → state mappings
    type: str | None = None            # State type marker (e.g., "learning")
    max_rate_limit_retries: int | None = None        # Short-burst tier budget; requires on_rate_limit_exhausted
    on_rate_limit_exhausted: str | None = None       # Target state when total wall-clock budget spent
    rate_limit_backoff_base_seconds: int | None = None  # Short-tier backoff base (default 30); delay = base * 2^n + jitter
    rate_limit_max_wait_seconds: int | None = None   # Total wall-clock budget across both tiers (default 21600 / 6h)
    rate_limit_long_wait_ladder: list[int] | None = None  # Long-wait ladder (default [300, 900, 1800, 3600]); index caps at last entry
    throttle: ThrottleConfig | None = None           # Per-state progressive tool-call throttling
    on_throttle_hard: str | None = None              # Target state when hard_max is reached (or hard-stop if unset)
    learning: LearningConfig | None = None           # FEAT-1283: type=learning state targets + retry budget
    cost_ceiling: CostCeilingConfig | None = None    # Per-state USD limit for LLM actions; routes on cost ceiling trip
```

#### ThrottleConfig

`from little_loops.fsm.schema import ThrottleConfig`

Per-state progressive throttling configuration. Counts tool calls within a single state visit and escalates restrictions before provider limits are hit.

```python
@dataclass
class ThrottleConfig:
    normal_max: int | None = None   # Calls 1..normal_max pass through (default 3)
    warn_max: int | None = None     # At warn_max, emits throttle_warn event (default 8)
    hard_max: int | None = None     # At hard_max, routes to on_throttle_hard (default 12)
```

**Throttle event constants** (emitted to the EventBus):

| Constant | Value | Description |
|----------|-------|-------------|
| `THROTTLE_WARN_EVENT` | `"throttle_warn"` | Emitted when tool-call count reaches `warn_max` |
| `THROTTLE_HARD_EVENT` | `"throttle_hard"` | Emitted when tool-call count reaches `hard_max` |
| `THROTTLE_STOP_EVENT` | `"throttle_stop"` | Emitted when count exceeds `hard_max` with no `on_throttle_hard` (hard stop) |

#### PromptSizeGuardConfig

`from little_loops.fsm.schema import PromptSizeGuardConfig`

ENH-2486: per-loop guard that WARNs when a fully-interpolated action grows large. The executor measures `len(action)` (chars) at the single interpolation choke point in `FSMExecutor._run_action` and emits `prompt_size_warn` when it reaches `warn_chars`. WARN-only (it does not route) — it turns a silently ballooning prompt (e.g. a state that re-embeds a monotonically growing captured output each iteration) into an observable signal in `<run>.events.jsonl`. Disable per-run with `--no-prompt-size-guard`; the size unit is chars because the codebase has no tokenizer (the event also reports `est_tokens = size // 4`).

```python
@dataclass
class PromptSizeGuardConfig:
    enabled: bool = True       # Master switch (disable with --no-prompt-size-guard)
    warn_chars: int = 50_000   # Chars at/above which prompt_size_warn fires; 0 disables
```

**Prompt-size event constant** (emitted to the EventBus):

| Constant | Value | Description |
|----------|-------|-------------|
| `PROMPT_SIZE_WARN_EVENT` | `"prompt_size_warn"` | Emitted when an interpolated action's size reaches `warn_chars` |

#### LearningConfig

`from little_loops.fsm.schema import LearningConfig`

FEAT-1283: per-state configuration for `type: learning` dispatch. The handler resolves the target list at runtime — if `targets_csv` is set it is interpolated and CSV-split; otherwise `targets` is used directly. The retry limit is resolved similarly: `max_retries_expr` (if set) is interpolated and `int()`-cast; otherwise `max_retries` (default 2) is used. Each target is then consulted in the learning-tests registry (ENH-1282); the state invokes `/ll:explore-api <target>` on a missing or stale record and advances via `on_yes` only after every target reaches status `proven`; refuted records and exhausted retries route to `on_blocked` (preferred) or `on_no`.

```python
@dataclass
class LearningConfig:
    targets: list[str] = field(default_factory=list)  # Ordered targets (slugified internally for registry lookups)
    targets_csv: str | None = None      # Runtime-interpolated CSV alternative to targets (ENH-1741)
    max_retries: int = 2                # Max /ll:explore-api invocations per target before routing to on_blocked
    max_retries_expr: str | None = None # Runtime-interpolated retry limit; takes precedence over max_retries (ENH-1741)
```

**Learning event types** (see `docs/reference/EVENT-SCHEMA.md` for full payloads):

| Event | Description |
|-------|-------------|
| `learning_target_proven` | A target's registry record is current with status=`proven` |
| `learning_target_stale` | A target's record is missing or stale; explore-api is about to fire |
| `learning_explore_invoked` | The state is calling `/ll:explore-api <target>` (paired with `action_start`) |
| `learning_target_refuted` | A target's record has status=`refuted`; state routes to blocked |
| `learning_complete` | Every target proven; state advances via `on_yes` |
| `learning_blocked` | State cannot advance (reason: `refuted` or `retries_exhausted`) |

> **Rate-limit handling (two-tier):** When a state's action returns an HTTP 429, the executor runs a two-tier retry ladder. **Short-burst tier** (up to `max_rate_limit_retries` attempts) uses `rate_limit_backoff_base_seconds * 2^n` + jitter. Once the short tier is spent, the executor enters the **long-wait tier** and walks `rate_limit_long_wait_ladder` (advancing index on each 429, capped at the last entry). The FSM routes to `on_rate_limit_exhausted` only once `total_wait_seconds >= rate_limit_max_wait_seconds`. The jitter is important under `ll-parallel` to avoid thundering-herd re-requests after a shared 429.

> **Alias note:** `on_success` and `on_failure` are accepted as aliases for `on_yes` and `on_no` in all states (including sub-loop states).

#### TargetStateSpec

`from little_loops.fsm import TargetStateSpec`

ENH-1552: per-state optimization spec for `harness-optimize` APO. Names a single FSM state within a target loop file and associates it with the examples file and eval fragment used during that state's optimization pass.

```python
@dataclass
class TargetStateSpec:
    name: str             # State name within the target loop
    examples_file: str    # Path to the examples YAML file for this state
    eval_fragment: str    # Eval fragment identifier (serialized as "eval:" in YAML)
```

#### TargetFileSpec

`from little_loops.fsm import TargetFileSpec`

ENH-1552: per-file targeting spec for `harness-optimize` APO. Associates a loop YAML file (or glob pattern) with the list of states to optimize.

```python
@dataclass
class TargetFileSpec:
    file: str | None = None            # Explicit path to a loop YAML file
    glob: str | None = None            # Glob pattern matching loop YAML files
    states: list[TargetStateSpec] = [] # States within the matched file(s) to optimize
```

#### EvaluateConfig

Evaluator configuration for action result interpretation.

```python
@dataclass
class EvaluateConfig:
    type: Literal[
        "exit_code",        # Map exit codes to verdicts
        "output_numeric",   # Compare numeric output
        "output_json",      # Extract and compare JSON path
        "output_contains",  # Pattern matching
        "convergence",      # Progress toward target
        "diff_stall",       # Detect stalled iterations via git diff
        "score_stall",      # Detect scored-output plateau via per-round score history
        "action_stall",     # Detect repeated action/output for N consecutive iterations
        "llm_structured",   # LLM with structured output
        "mcp_result",       # Parse MCP tool call response envelope
        "harbor_scorer",    # Harbor-format benchmark scorer (exit code + float stdout)
        "comparator",       # Blind A/B comparison against stored baseline via LLM judge
        "contract",         # Validate producer/consumer pairs
        "classify",         # Classify a single line of output
        "advisor_consult",  # Consult the advisor and route on its verdict
    ]
    operator: str | None = None        # Comparison: eq, ne, lt, le, gt, ge
    target: int | float | str | None = None  # Target value
    tolerance: float | str | None = None     # For convergence
    pattern: str | None = None         # For output_contains
    negate: bool = False               # Invert match result
    path: str | None = None            # JSON path for output_json
    prompt: str | None = None          # For llm_structured
    schema: dict | None = None         # For llm_structured
    min_confidence: float = 0.5        # For llm_structured
    uncertain_suffix: bool = False     # Append _uncertain to low-confidence
    source: str | None = None          # Override default source
    previous: str | None = None        # Previous value reference
    direction: Literal["minimize", "maximize"] = "minimize"
    scope: list[str] | None = None     # For diff_stall: limit git diff to these paths
    max_stall: int = 1                 # For diff_stall/score_stall: consecutive no-progress rounds before failure
    history_file: str | None = None    # For score_stall: per-round score-history file (default: ${context.run_dir}/.score_history)
    epsilon: float = 0.5               # For score_stall: minimum score improvement counted as progress
    track: list[str] | None = None    # For action_stall: context keys to track (default: ["action"])
    max_repeat: int = 2               # For action_stall: consecutive identical iterations before failure
    baseline_path: str | None = None   # For comparator: path to .loops/baselines/<loop>/ dir
    auto_promote: bool = False         # For comparator: write output to baseline on yes verdict
    min_pairs: int = 1                 # For comparator: number of blind A/B comparison pairs
    pairs: list[dict] | None = None    # For contract: list of producer/consumer pair dicts
    line: str | int | None = None      # For classify: which line to read (last/first/<int index>)
    error_patterns: list[str] | None = None  # For output_contains: patterns that yield verdict="error"
    key: str | None = None            # For output_numeric: extract value from a `<key>=<number>` field
    question: str | None = None        # For advisor_consult: the consult prompt
    verdict_map: dict[str, str] | None = None  # For advisor_consult: decision -> FSM verdict
    signal: str | None = None          # For advisor_consult: overrides the fixed "loop_stall" trigger
    timeout: int | None = None         # For advisor_consult: per-state override of advisor.timeout_seconds
    context_from: list[str] | None = None  # For advisor_consult: interpolation paths assembled into consult context
```

#### RouteConfig

Routing table configuration for verdict-to-state mapping.

```python
@dataclass
class RouteConfig:
    routes: dict[str, str] = {}  # Verdict -> next state
    default: str | None = None   # Default for unmatched verdicts ("_")
    error: str | None = None     # State for errors ("_error")
```

**Example:**
```python
from little_loops.fsm import StateConfig, EvaluateConfig, RouteConfig

state = StateConfig(
    action="check_status",
    evaluate=EvaluateConfig(
        type="output_json",
        path=".status",
        operator="eq",
        target="ready",
    ),
    route=RouteConfig(
        routes={"yes": "proceed", "no": "wait"},
        default="error_state",
    ),
)
```

#### LLMConfig

LLM evaluation configuration.

```python
@dataclass
class LLMConfig:
    enabled: bool = True
    model: str = DEFAULT_LLM_MODEL  # Default from schema.py
    max_tokens: int = 256
    timeout: int = 30
    effort: str | None = None       # Loop-default reasoning-effort tier; state.effort/--effort override it (ENH-2869)
```

---

### little_loops.fsm.evaluators

Evaluators interpret action output and produce verdicts for state transitions.

#### EvaluationResult

```python
@dataclass
class EvaluationResult:
    verdict: str                  # Routing key for transitions
    details: dict[str, Any]       # Evaluator-specific metadata
```

For `llm_structured` evaluations (ENH-2342), `details` always includes:
- `evidence: str` — verbatim quote from action output supporting the verdict; empty string means no evidence was found
- `evidence_coerced: bool` — `True` when evidence was absent and the verdict was downgraded to `"no"` (only fires for default schema; custom schemas bypass coercion)

#### Tier 1 Evaluators (Deterministic)

```python
def evaluate_exit_code(exit_code: int, abstain_on_exit_3: bool = False) -> EvaluationResult
```
Map Unix exit code to verdict: 0→success, 1→failure, 2+→error. When
`abstain_on_exit_3=True`, exit code 3 maps to `cannot_judge` instead of
`error` (ENH-3224) — an opt-in per-state flag (`EvaluateConfig.abstain_on_exit_3`),
**not** a global remap, since exit code 3 is not OS-reserved: only invocations
known to follow a tool's ABSTAIN exit-code contract (e.g. `ll-harness`, whose
own exit-code mapping is `0`=pass, `1`=fail, `3`=abstained — see
`cli/harness.py`) should set it. Pair the flag with a declared
`on_cannot_judge` route; a state that sets the flag with no such route holds
up to `_ABSTENTION_HOLD_CAP` (2), re-running the command, before falling to
`on_error` anyway — strictly worse than not opting in. The `loops/lib/common.yaml`
`harness_exit` fragment is the worked example: `fragment: harness_exit` plus
`on_yes`/`on_no`/`on_cannot_judge`.

Note the two built-in CLIs already disagree on exit code `2`: `ll-loop run`
treats it as a failure terminal (`fsm/types.py`), while `ll-harness` treats it
as an infra error (`cli/harness.py`). There is no single global exit-code
vocabulary across tools — read each tool's own contract.

```python
def evaluate_output_numeric(
    output: str,
    operator: str,
    target: float,
    key: str | None = None,
) -> EvaluationResult
```
Parse stdout as number and compare to target. If `key` is set, extract the value from a
`<key>=<number>` field in output (last match wins on multiple occurrences) instead of parsing
the whole output; a missing key yields `verdict="error"` naming the key.

```python
def evaluate_output_json(
    output: str,
    path: str,
    operator: str,
    target: Any,
) -> EvaluationResult
```
Parse JSON and extract value at jq-style path, then compare.

```python
def evaluate_output_contains(
    output: str,
    pattern: str,
    negate: bool = False,
    error_patterns: list[str] | None = None,
) -> EvaluationResult
```
Check if pattern (regex or substring) exists in output. When `error_patterns` is set and the
main pattern is not found, any matching error_pattern yields `verdict="error"` instead of `"no"`,
enabling `on_error` routing for auth/error output even when the action exits with code 0.

```python
def evaluate_convergence(
    current: float,
    previous: float | None,
    target: float,
    tolerance: float = 0,
    direction: str = "minimize",
) -> EvaluationResult
```
Compare current value to target and previous. Returns: target, progress, or stall.

#### Tier 2 Evaluators (LLM-based)

```python
def evaluate_llm_structured(
    output: str,
    prompt: str | None = None,
    schema: dict | None = None,
    min_confidence: float = 0.5,
    uncertain_suffix: bool = False,
    model: str = DEFAULT_LLM_MODEL,  # Default from schema.py
    max_tokens: int = 256,
    timeout: int = 30,
) -> EvaluationResult
```
Evaluate action output using an LLM with structured output. Dispatches through `host_runner.resolve_host().build_blocking_json()` and calls the resolved CLI as a subprocess (no Anthropic Python SDK dependency); requires a supported host CLI on PATH (e.g. `claude`).

#### Dispatcher

```python
def evaluate(
    config: EvaluateConfig,
    output: str,
    exit_code: int,
    context: InterpolationContext,
) -> EvaluationResult
```
Dispatch to appropriate evaluator based on config type.

**Action-level timeouts**: When `exit_code == 124` (action killed at its `timeout:`), the dispatcher short-circuits to `EvaluationResult(verdict="error", details={"exit_code": 124, "error": "action timed out"})` for all types except `mcp_result` (which has its own `timeout` verdict). This ensures `on_error:` is the canonical branch for action timeouts regardless of evaluator type.

**Example:**
```python
from little_loops.fsm import evaluate_exit_code, evaluate_output_contains

# Exit code evaluation
result = evaluate_exit_code(0)
print(result.verdict)  # "yes"

# Pattern matching
result = evaluate_output_contains("All tests passed", "passed")
print(result.verdict)  # "yes"

result = evaluate_output_contains("Error occurred", "Error", negate=True)
print(result.verdict)  # "no"
```

---

### little_loops.fsm.executor

Runtime engine for FSM loop execution.

#### FSMExecutor

```python
class FSMExecutor:
    def __init__(
        self,
        fsm: FSMLoop,
        event_callback: EventCallback | None = None,
        action_runner: ActionRunner | None = None,
        signal_detector: SignalDetector | None = None,
        handoff_handler: HandoffHandler | None = None,
        loops_dir: Path | None = None,
        circuit: RateLimitCircuit | None = None,
        inbound: queue.Queue[dict[str, Any]] | None = None,  # ENH-3351
    )
```

Execute an FSM loop until terminal state, max iterations, timeout, or signal.

`inbound` (ENH-3351) is an optional queue drained non-blockingly at the top of
each `run()` iteration by `_drain_inbound()`: each drained dict is re-emitted
as an `artifact_interaction` event (via `self._emit`, reaching persistence and
any registered transport, including a `--serve` SSE bridge) and appended to the
bounded `self.inbound_events: collections.deque[dict[str, Any]]` (`maxlen=100`)
so future issues can build routing/guard semantics on top. `None` (the
default) is a no-op — behavior is unchanged when `inbound` is omitted.
`PersistentExecutor(..., inbound=q)` forwards it through unmodified
(`**executor_kwargs`); `_execute_sub_loop`'s child executor construction
forwards the parent's `inbound` so interactions keep arriving inside a `loop:`
sub-state. Wired by `ll-loop run --serve` (`LocalBridgeTransport`), not by any
other production call site.

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `run()` | `ExecutionResult` | Execute FSM to completion |
| `request_shutdown()` | `None` | Request graceful shutdown |
| `_drain_inbound()` | `None` | Non-blocking full-drain of `self.inbound`; re-emits each item as `artifact_interaction` and records it in `inbound_events` (ENH-3351) |

**Example:**
```python
from little_loops.fsm import FSMLoop, StateConfig, FSMExecutor

fsm = FSMLoop(
    name="test",
    initial="check",
    states={
        "check": StateConfig(action="pytest", on_yes="done", on_no="check"),
        "done": StateConfig(terminal=True),
    },
)

events = []
executor = FSMExecutor(fsm, event_callback=events.append)
result = executor.run()

print(result.final_state)     # "done"
print(result.iterations)      # Number of iterations
print(result.terminated_by)   # "terminal", "max_steps", "max_iterations_reached", "timeout", "interrupted", "cycle_detected", "stall_detected", or "error"
```

#### ExecutionResult

```python
@dataclass
class ExecutionResult:
    final_state: str                      # State when execution stopped
    iterations: int                       # Total iterations
    terminated_by: str                    # "terminal" | "max_steps" | "max_iterations_reached" | "timeout" | "interrupted" | "cycle_detected" | "stall_detected" | "error"
    duration_ms: int                      # Total execution time
    captured: dict[str, dict[str, Any]]   # Captured variable values
    failure_terminal: bool = False        # Stopped on a `failure: true` terminal (ENH-2814)
    error: str | None = None              # Error message if failed
```

`terminated_by == "terminal"` does **not** imply success — read
`failure_terminal` for that. It drives `ll-loop run`'s exit code (`2`), the
persisted `final_status` (`"failed"` rather than `"completed"`), and sub-loop
`on_no` routing.

#### ActionResult

```python
@dataclass
class ActionResult:
    output: str       # stdout
    stderr: str       # stderr
    exit_code: int    # Exit code
    duration_ms: int  # Execution time (elapsed, not the budget — FEAT-3033)
    usage_events: list[TokenUsage] = field(default_factory=list)  # Host-CLI token usage (ENH-2453)
    peak_rss_mb: float | None = None  # Peak subprocess RSS in MB (ENH-2453)
    result_seen: bool = False  # Stream-json "result" event observed before exit (BUG-2731)
    session_id: str | None = None  # Host CLI session ID from stream-json system/init event (FEAT-2711)
    timeout_kind: str | None = None  # "idle" | "wall" | None — discriminates an idle kill from
                                      # a wall-clock kill on exit_code=124 (FEAT-3033)
```

#### ActionRunner Protocol

```python
class ActionRunner(Protocol):
    def run(
        self,
        action: str,
        timeout: int,
        is_slash_command: bool,
        on_output_line: Callable[[str], None] | None = None,
        agent: str | None = None,
        tools: list[str] | None = None,
        on_usage: UsageCallback | None = None,
        on_usage_detailed: DetailedUsageCallback | None = None,
        model: str | None = None,
        working_dir: Path | None = None,
        automation: AutomationContext | None = None,  # ENH-3096 collapsed automation signal
        automation_profile: str | None = None,  # Deprecated — prefer automation=
        disable_background_tasks: bool = False,  # Hard-disable tool-level background tasks (FEAT-3078); deprecated — prefer automation=
        idle_timeout: int = 0,  # Kill if no output for this many seconds; 0 disables (FEAT-3033); deprecated — prefer automation=
        timeout_kill_grace_seconds: float = 0.0,  # Grace period before escalating SIGTERM to SIGKILL (ENH-3130)
    ) -> ActionResult: ...
```

Implement this protocol to customize action execution (useful for testing). In the extension system, `ActionRunner` is also the contributed-actions runtime dispatch interface — extension plugins register runners against custom `action_type` strings via `ActionProviderExtension.provided_actions()`, and `FSMExecutor` dispatches to them through the `_contributed_actions` registry at runtime.

`automation` (ENH-3096) collapses `automation_profile`/`disable_background_tasks`/`idle_timeout` into a single `AutomationContext`, mirroring `HostRunner.build_streaming()` (ENH-3095). `fsm/executor.py`'s `extra_kwargs` assembly builds one `AutomationContext` and passes it as `automation=` when any of the three knobs resolves non-default; the three legacy kwargs remain as deprecated pass-throughs on the Protocol and both implementations, resolved internally via `resolve_automation()` (`host_runner.py`) — the same shim `build_streaming()` uses, with a `caller="ActionRunner.run()"` override so its `DeprecationWarning` names the right function. Explicit `automation=` wins over any legacy kwarg supplied alongside it (warns); bare legacy-kwarg use stays silent. `DefaultActionRunner` forwards the resolved context straight through as `automation=automation` to `run_claude_command()` (ENH-3097), which now accepts `automation=` directly — no more decompose-then-forward round trip.

`idle_timeout` is kwarg-gated at every executor call site (like `working_dir`/`automation_profile`): it's only passed when resolved to a non-zero value, so `ActionRunner` implementations predating FEAT-3033 keep working unchanged as long as idle detection isn't configured for the states they run. Note: when an explicit `automation=` is supplied alongside a legacy `idle_timeout=`, the legacy value is discarded (not merged) — `resolve_automation()`'s "explicit wins" rule is uniform across all three legacy fields.

`disable_background_tasks` (FEAT-3078) is likewise kwarg-gated: it's only passed (as `True`) when `orchestration.disable_background_tasks` is enabled in config (opt-in; default `false`), so `ActionRunner` implementations predating this change keep working unless they read `**kwargs`. Only meaningful in prompt mode (host CLI invocations); `SimulationActionRunner` accepts and ignores it.

**Idle vs. wall-clock timeout.** `stateConfig.idle_timeout` / loop-level `default_idle_timeout` add a silence sensor alongside the existing wall-clock `timeout` / `default_timeout`, resolved with the same precedence (`state.idle_timeout or fsm.default_idle_timeout or 0`). `0` disables idle detection (the default) — a healthy long-running state that keeps producing output is never killed by it, however long it runs; only sustained silence trips it. On any timeout kill (`exit_code=124`), `ActionResult.timeout_kind` is `"idle"` or `"wall"`; the exit code stays `124` for both so BUG-1640/BUG-1815 error-routing is unaffected. The value flows into the interpolation context as `${prev.timeout_kind}` / `${captured.<name>.timeout_kind}` — read with `:default=` since checkpoints written before this field existed lack the key — so a downstream `shell_exit`-style classifier state can route a wedged process differently from a wall-clock kill. Shell and mcp states enforce idle via `last_output_at` tracking in their selector loops; prompt and baseline (sdk/batch) states pass through to `run_claude_command`'s existing `idle_timeout` implementation. Known boundary: `readline()`-based reads in the shell/mcp selector loops block until a newline or EOF, so a child that writes a partial line and then truly wedges mid-line is not caught by either sensor until it completes the line or exits — pre-existing behavior for the wall-clock sensor too, not introduced by idle detection. `_dispatch_live` (sdk/batch request paths with no subprocess) has no idle sensor and isn't in scope.

---

### little_loops.fsm.interpolation

Variable interpolation using `${namespace.path}` syntax.

#### InterpolationContext

```python
@dataclass
class InterpolationContext:
    context: dict[str, Any] = {}           # User-defined variables
    captured: dict[str, dict] = {}         # Stored action results
    prev: dict[str, Any] | None = None     # Previous state result
    result: dict[str, Any] | None = None   # Current evaluation result
    state_name: str = ""                   # Current state
    iteration: int = 1                     # Current iteration
    loop_name: str = ""                    # FSM loop name
    started_at: str = ""                   # ISO timestamp
    elapsed_ms: int = 0                    # Milliseconds since start
    messages: list[str] = []               # Captured host messages for this run
    messages_summary: str = ""             # Condensed summary of `messages`
    param: dict[str, Any] = {}             # Sub-loop / fragment parameters
```

**Supported namespaces:**
- `context` - User-defined variables from FSM context block
- `captured` - Values stored via `capture:` in states
- `prev` - Previous state's result (output, exit_code, state)
- `result` - Current evaluation result (verdict, details)
- `state` - Current state metadata (name, iteration)
- `loop` - Loop metadata (name, started_at, elapsed_ms, elapsed)
- `env` - Environment variables
- `messages` - Shared append-only message log (`${messages}`, `${messages.last(N)}`, `${messages.summary}`)
- `param` - Per-state parameter bindings for fragment references (resolved from `fragment_bindings`)

**Methods:**

```python
def resolve(self, namespace: str, path: str) -> Any
```
Resolve a namespace.path reference to its value.

#### interpolate

```python
def interpolate(template: str, ctx: InterpolationContext) -> str
```

Replace `${namespace.path}` variables in template string.

**Example:**
```python
from little_loops.fsm import InterpolationContext, interpolate

ctx = InterpolationContext(
    context={"target_dir": "src/", "threshold": 10},
    captured={"check": {"output": "5", "exit_code": 0}},
)

result = interpolate("mypy ${context.target_dir}", ctx)
# Returns: "mypy src/"

result = interpolate("Errors: ${captured.check.output}", ctx)
# Returns: "Errors: 5"

# Escape with $$ — passes through as literal ${...}
result = interpolate("Use $${context.var} syntax", ctx)
# Returns: "Use ${context.var} syntax"

# Bash parameter expansion operators inside $${ } pass through unchanged
result = interpolate("printf '$${DEPTH:-0}'", ctx)
# Returns: "printf '${DEPTH:-0}'"  (bash evaluates ${DEPTH:-0} at runtime)

# Safe interpolation — :default= returns fallback on missing path
result = interpolate("${captured.missing:default=fallback}", ctx)
# Returns: "fallback"

# Safe interpolation — ? returns empty string on missing path
result = interpolate("${captured.missing?}", ctx)
# Returns: ""

# :shell suffix — shlex.quote()s the value for safe use in a bash token
# position (BUG-2622); used WITHOUT surrounding quotes
result = interpolate('VAL=${context.target_dir:shell}', ctx)
# Returns: "VAL=src/"

# ENH-3337: :shell composes with :default=/? in any ordering — the fallback
# is shlex-quoted too, so both orderings below are equivalent
result = interpolate("VAL=${captured.missing:shell:default=fall back}", ctx)
result = interpolate("VAL=${captured.missing:default=fall back:shell}", ctx)
# Both return: "VAL='fall back'"

# Unsuffixed references still raise InterpolationError on missing paths
# interpolate("${captured.missing}", ctx)  → InterpolationError
```

#### interpolate_dict

```python
def interpolate_dict(obj: dict[str, Any], ctx: InterpolationContext) -> dict[str, Any]
```

Recursively interpolate all string values in a dict.

---

### little_loops.fsm.interp_sweep

Static sweep classifying `${context.*}` / `${captured.*}` / `${prev.*}`
interpolation sites found inside embedded Python bodies (heredocs and
`python3 -c` strings) within loop-YAML shell actions (ENH-3338). A quoted
heredoc or `-c` string protects a substituted value from *bash* expansion,
but once the text lands inside a Python source string, an unescaped
quote/backslash is a Python syntax break or injection — a distinct hazard
from the bash-position risk MR-11 (`little_loops.fsm.validation`) checks.

#### classify_site

```python
def classify_site(namespace: str, key: str) -> str
```

Classify one interpolation token by namespace and first path segment.
Returns `"A"` (untrusted `context.*` key), `"B"` (always-untrusted
`captured.*` or `prev.output`/`prev.stderr`), or `"C"` (trusted/runner-owned
— e.g. `context.run_dir`, `prev.exit_code`). This is the single
implementation of the classification rule; ENH-3342 imports it to widen
MR-11 rather than duplicating it.

#### InterpSite

```python
@dataclass(frozen=True)
class InterpSite:
    file: str
    state: str
    var: str
    cls: str
    host_shape: str            # "heredoc" | "c-string" — informational
    misapplied_remedy: bool    # ":shell" found inside a Python body — informational
    line: int                  # informational
    count: int = 1             # informational
```

Equality and hash are restricted to `(file, state, var, cls)` so a ratcheting
baseline can be diffed by set equality without churning on line-number drift.

#### scan_action

```python
def scan_action(action: str, *, state: str, file: str) -> list[InterpSite]
```

Scans one shell action string, tracking both host shapes (a heredoc between
its mid-line opener and column-0 terminator, and a `python3 -c "..."` /
`-c '...'` body), and returns one `InterpSite` per interpolation token found
inside a Python body. Tokens at a plain bash position — including a
`:shell`-suffixed binding on the invocation line — are not reported here.

#### scan_corpus

```python
def scan_corpus(root: Path) -> list[InterpSite]
```

Globs `root` recursively for `*.yaml`, walks both the `states:` and
`fragments:` top-level keys of each loop (so `lib/*.yaml` fragment-only
files are covered), skips non-shell (`action_type: prompt`, etc.) and
slash-command actions, and returns all classified sites sorted
deterministically by `(file, state, var, cls)`.

`scripts/tests/test_builtin_loops.py`'s `TestInterpSweepBaseline` asserts
`scan_corpus(BUILTIN_LOOPS_DIR)`'s result equals the checked-in
`scripts/tests/data/loop_interpolation_baseline.json` — a ratchet that fails
in both directions (new unbaselined site, or a stale entry that no longer
scans), forcing each conversion commit (BUG-3339/3340/3341) to update the
baseline in step with the corpus.

---

### little_loops.fsm.validation

FSM validation and loading utilities.

#### ValidationError

```python
@dataclass
class ValidationError:
    message: str                           # Human-readable description
    path: str | None = None                # Path to problematic element
    severity: ValidationSeverity = ERROR   # ERROR or WARNING
```

#### validate_fsm

```python
def validate_fsm(fsm: FSMLoop, orchestration_request_path: str | None = None) -> list[ValidationError]
```

Validate FSM structure and return list of errors.

**Checks performed:**
- Initial state exists in states dict
- All referenced states exist
- At least one terminal state defined
- Evaluator configs have required fields
- No conflicting routing definitions
- Warns about unreachable states
- Warns when no top-level `description:` field is set
- Warns (WARNING) when a failure terminal state — one carrying `failure: true`, whether declared or defaulted from the `failed`/`error`/`aborted`/`finalize_aborted` name convention (ENH-2814) — has no predecessor state with a diagnostic action (an `action`, a sub-`loop`, or a `learning` block)
- **MR-1 (ERROR)**: meta-loop (writes harness artifacts or imports `lib/benchmark.yaml`) must have at least one non-LLM evaluator; suppress with `meta_self_eval_ok: true` (ENH-1665)
- **MR-2 (WARNING)**: meta-loop should reference a captured baseline value in a later evaluator (measure→propose→apply→re-measure spine); suppress with `meta_self_eval_ok: true` (ENH-1665)
- **MR-3 (WARNING)**: loop writes intermediate artifacts to shared `.loops/tmp/` instead of `${context.run_dir}/`; suppress with `shared_state_ok: true`
- **MR-4 (WARNING)**: LLM-judged state maps `on_yes` but has no route for `no`/`partial` verdicts with no `next:` or `route:` table — dead-ends the loop; suppress with `partial_route_ok: true` (ENH-1917)
- **MR-5 (WARNING)**: harness-category loop writes artifact files to a flat path in an iterative generate→evaluate→generate cycle — only the final iteration's output survives; add per-iteration snapshots and declare `artifact_versioning: true`, or set `artifact_versioning_ok: true` to suppress when intentional overwrite is desired (ENH-1957)
- **MR-6 (WARNING)**: meta-loop has a `shell`-type state that writes to the same file path as an LLM-generator state — hand-patching creates fragile output that diverges from the generator on the next run; fix the generator action so every run produces correct output automatically, or set `generator_fix_ok: true` for intentional post-processing (ENH-2079)
- **MR-7 (ERROR)**: any FSM action string contains an unescaped `${namespace.path:-default}` (bash `:-` default syntax) — the interpolation engine crashes at runtime; use `${ns.path:default=value}` (engine-native) or `$${VAR:-value}` (shell-escaped), or set `bash_default_ok: true` to suppress (ENH-2348)
- **MR-8 (WARNING)**: a `check_semantic`/`llm_structured` state's `evaluate.prompt` omits evidence-contract keywords (`verbatim`, `quote`, `evidence`) — verdicts without verbatim citation requirements default to optimism (SHOR Table 1: 33–55% accuracy); states with `evaluate.prompt: null` inherit `DEFAULT_LLM_PROMPT` which includes the contract automatically; set `evidence_contract_ok: true` to suppress (ENH-2342)
- **MR-9 (ERROR)**: a shell action string contains `$$(` or `$$VAR` — over-escaped bash; the FSM interpolator only rewrites the brace form `$${...}` → `${...}`, so bare `$(...)` / `$VAR` doubled with `$$` expand to the runner's PID at runtime, silently corrupting every downstream `${captured.*}` reference; use single `$` for command substitution and variables, reserve `$$` exclusively for the `$${VAR}` brace escape that collides with `${ns.path}` interpolation; set `shell_pid_ok: true` to suppress (BUG-2368)
- **MR-10 (WARNING)**: a `shell`-type state's inline Python calls `json.loads`/`json.load`, catches `JSONDecodeError`/`ValueError`/bare `Exception`, and explicitly exits 0 — without an `on_error:` route — silently discarding parse failures as an empty success; add `on_error:` to route parse failures explicitly, or set `parse_swallow_ok: true` to suppress when an empty result is intentional (BUG-2383)
- **MR-11 (WARNING)**: a `shell`-type state pastes a user-controlled `${context.input|goal|description|task|prompt|query|topic}` value raw into the action body outside a safe position (single-quoted string, quoted heredoc `<<'EOF'`, or the `:shell` suffix) — `interpolate()` substitutes with a bare `str(value)` and no shell escaping, so a value containing `"`, `$`, `` ` ``, `\`, or `!` breaks bash tokenizing or injects commands; wrap the placeholder in single quotes, write it through a quoted heredoc, or use `${context.input:shell}` to shlex-quote it, or set `unsafe_context_interpolation_ok: true` to suppress (BUG-2622)
- **terminal-action-ok (WARNING)**: a non-empty `action` on a `terminal: true` state — the executor finishes the run the instant a terminal is entered, before its `action` would run, so it's dead code; move the action into a new penultimate non-terminal state with `next: <terminal>` and an `on_error:` route, leaving the terminal bare (the `rn-implement::report` shape); exempts a terminal doubling as the loop's `on_max_steps`/`on_max_iterations` handler (BUG-158); set `terminal_action_ok: true` to suppress (BUG-2813)
- **MR-13 (WARNING)**: a loop has an abandonment mechanism (checkbox rewrite to `[!]`, or `[x]`+"abandoned" annotation, or a `max_step_attempts`-style attempt cap) but no state's action emits an `"abandoned"` key into a summary JSON printf/write; or a shell action hardcodes a literal `"verdict":"success"`/`verdict=success` with no conditional branch on an abandonment/failure counter and no `"abandoned"` key emitted in that same state — abandoned work is silently laundered into a clean success verdict (the pre-ENH-2857 `general-task.yaml` defect); set `abandonment_verdict_ok: true` to suppress (ENH-2860)
- **MR-14 (WARNING)**: a state's raw `evaluate:` mapping has a key outside `EvaluateConfig`'s dataclass fields — `EvaluateConfig.from_dict` silently drops unrecognized keys with no diagnostic, the root cause that let BUG-2893/BUG-2894 ship; the rule derives its known-field set from `dataclasses.fields(EvaluateConfig)` and suggests the nearest known field via `difflib.get_close_matches`; WARN-now/ERROR-later relative to `fsm-loop-schema.json`'s `additionalProperties: false` stance on `evaluateConfig`; set `evaluate_unknown_keys_ok: true` to suppress (ENH-2896)

**Example:**
```python
from little_loops.fsm import FSMLoop, StateConfig, validate_fsm, ValidationSeverity

fsm = FSMLoop(
    name="test",
    initial="start",
    states={
        "start": StateConfig(action="echo", on_yes="done", on_no="done"),
        "done": StateConfig(terminal=True),
    },
)

errors = validate_fsm(fsm)
error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
print(f"Found {len(error_list)} errors")
```

#### load_and_validate

```python
def load_and_validate(
    path: Path,
    raise_on_error: bool = True,
    orchestration_request_path: Path | None = None,
) -> tuple[FSMLoop, list[ValidationError]]
```

Load YAML file and validate FSM structure.

**Parameters:**
- `path` - Path to YAML file
- `raise_on_error` - When `True` (default) and there are no ERROR-severity findings, every
  WARNING-severity `ValidationError` is also logged via `logger.warning(str(warning))` as a
  load-time side effect, independent of what the caller does with the returned list. When
  `False`, nothing is logged and both errors and warnings are returned for the caller to
  handle (used by `--json` output paths and by recursive child-loop loads, e.g.
  `_validate_with_bindings`, so a child's warnings don't leak to stderr through a parent's
  validation — see BUG-3239).
- `orchestration_request_path` - Optional path passed through to request-path-sensitive
  validation rules (e.g. MR-12 Check 3)

**Returns:** `(fsm, violations)` — the parsed `FSMLoop` and a list of `ValidationError`. When
`raise_on_error=True`, ERROR-severity findings raise `ValueError` instead of being returned, so
the returned list contains only warnings.

**Raises:**
- `FileNotFoundError` - If file doesn't exist
- `yaml.YAMLError` - If invalid YAML
- `ValueError` - If validation fails with ERROR-severity findings and `raise_on_error=True`

**Example:**
```python
from pathlib import Path
from little_loops.fsm import load_and_validate

try:
    fsm, warnings = load_and_validate(Path(".loops/my-loop.yaml"))
    print(f"Loaded loop: {fsm.name}")
except ValueError as e:
    print(f"Validation error: {e}")
```

---

### little_loops.fsm.persistence

State persistence and event streaming for FSM loops.

#### LoopState

```python
@dataclass
class LoopState:
    loop_name: str                        # Name of the loop
    current_state: str                    # Current FSM state
    iteration: int                        # Current iteration
    captured: dict[str, dict[str, Any]]   # Captured outputs
    prev_result: dict[str, Any] | None    # Previous state result
    last_result: dict[str, Any] | None    # Last evaluation result
    started_at: str                       # ISO timestamp
    updated_at: str                       # Last update timestamp
    status: str                           # running, completed, failed, interrupted
    continuation_prompt: str | None       # Handoff context (awaiting_continuation)
    accumulated_ms: int                   # Total elapsed ms across segments (resume offset)
    retry_counts: dict[str, int]          # Per-state retry tracking
    messages: list[str]                   # Emitted loop messages
    context: dict[str, Any]               # Full FSM context (input, program.md, --context);
                                          # persisted for resume (BUG-2485). Kept out of the
                                          # CLI status/list --json contract: to_dict() emits it
                                          # only when include_context=True (the on-disk path).
```

#### StatePersistence

```python
class StatePersistence:
    def __init__(self, loop_name: str, loops_dir: Path | None = None, instance_id: str | None = None)
```

Manage loop state persistence and event streaming.

**Methods:**

| Method | Description |
|--------|-------------|
| `initialize()` | Create running directory |
| `save_state(state)` | Save state to JSON file |
| `load_state()` | Load state, or None if not exists |
| `clear_state()` | Remove state file |
| `append_event(event)` | Append event to JSONL file |
| `read_events()` | Read all events from file |
| `clear_events()` | Remove events file |
| `clear_all()` | Archive current run to history, then clear state, events, and meta-eval |
| `archive_run(run_dir=None)` | Copy state, events, meta-eval (meta-loops), and summary.json (when present in `run_dir`) to `.loops/.history/<run_id>-<name>/` |

**File structure:**
```
.loops/
├── my-loop.yaml           # Loop definition
└── .running/              # Runtime state
    ├── my-loop-20260503T122306.state.json
    ├── my-loop-20260503T122306.events.jsonl
    └── my-loop-20260503T122306.meta-eval.jsonl  # meta-loops only
```

#### PersistentExecutor

```python
class PersistentExecutor:
    def __init__(
        self,
        fsm: FSMLoop,
        persistence: StatePersistence | None = None,
        loops_dir: Path | None = None,
        **executor_kwargs,
    )
```

FSM Executor with state persistence and event streaming.

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `run(clear_previous=True)` | `ExecutionResult` | Run with persistence |
| `resume()` | `ExecutionResult \| None` | Resume from saved state |
| `request_shutdown()` | `None` | Request graceful shutdown |

**Example:**
```python
from pathlib import Path
from little_loops.fsm import FSMLoop, StateConfig, PersistentExecutor

fsm = FSMLoop(
    name="my-loop",
    initial="check",
    states={
        "check": StateConfig(action="pytest", on_yes="done", on_no="check"),
        "done": StateConfig(terminal=True),
    },
)

executor = PersistentExecutor(fsm, loops_dir=Path(".loops"))
result = executor.run()

# Later, check saved state
state = executor.persistence.load_state()
print(f"Status: {state.status}")
```

#### Utility Functions

```python
def list_running_loops(loops_dir: Path | None = None) -> list[LoopState]
```
List all loops with saved state, including loops in the `starting` status (not yet executing their first state).

```python
def get_loop_history(loop_name: str, loops_dir: Path | None = None) -> list[dict]
```
Get event history for a loop.

---

### little_loops.fsm.handoff_handler

Handles context handoff signals during FSM loop execution, with configurable behavior (pause, spawn, or terminate).

#### HandoffBehavior

```python
class HandoffBehavior(Enum):
    TERMINATE = "terminate"   # Stop loop execution immediately, no state preservation
    PAUSE = "pause"           # Save state with continuation prompt and exit (default)
    SPAWN = "spawn"           # Save state and spawn a new Claude session to continue
```

#### HandoffResult

```python
@dataclass
class HandoffResult:
    behavior: HandoffBehavior               # The behavior that was applied
    continuation_prompt: str | None         # Continuation prompt from the signal
    spawned_process: subprocess.Popen | None = None  # Set if SPAWN behavior used
```

#### HandoffHandler

```python
class HandoffHandler:
    def __init__(self, behavior: HandoffBehavior = HandoffBehavior.PAUSE) -> None
```

Handle context handoff signals with configurable behavior.

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `handle(loop_name, continuation)` | `HandoffResult` | Handle a detected handoff signal; save state responsibility falls on the caller |

**Example:**

```python
from little_loops.fsm.handoff_handler import HandoffHandler, HandoffBehavior

handler = HandoffHandler(HandoffBehavior.PAUSE)
result = handler.handle("fix-types", "Continue from iteration 5")
# result.behavior == HandoffBehavior.PAUSE
```

---

### little_loops.fsm.concurrency

Scope-based concurrency control for FSM loops. Prevents concurrent loops from conflicting on the same files via file-based locking under `.loops/.running/`.

#### ScopeLock

```python
@dataclass
class ScopeLock:
    loop_name: str      # Name of the loop holding the lock
    scope: list[str]    # List of paths this loop operates on
    pid: int            # Process ID of the lock holder
    started_at: str     # ISO timestamp when lock was acquired
    singleton: bool = False  # BUG-2526: True = block other instances with same loop_name
                             # regardless of scope overlap. False (default) preserves
                             # ENH-1354 / FEAT-1789 disjoint-scope concurrency.
```

**Methods:** `to_dict()`, `from_dict(data)`

`ScopeLock.from_dict()` reads the `singleton` key with a default of `False` so legacy lock files written before BUG-2526 (no `singleton` key) parse cleanly. New writers emit `singleton: true` only when the field is set.

#### LockManager

```python
class LockManager:
    def __init__(self, loops_dir: Path | None = None) -> None
```

Manage scope-based locks for concurrent loop execution. Lock files are stored in `.loops/.running/<instance_id>.lock`.

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `acquire(loop_name, scope, instance_id=None, *, singleton=False)` | `bool` | Acquire lock; returns `False` if conflict exists. When `singleton=True`, any other instance with the same `loop_name` is a conflict regardless of scope overlap (BUG-2526). |
| `release(loop_name, instance_id=None)` | `None` | Release lock for a loop instance |
| `find_conflict(scope, *, caller_loop_name=None, caller_singleton=False)` | `ScopeLock \| None` | Find conflicting running loop; cleans stale locks. Returns `None` if the only conflict is an ancestor process of the caller (prevents self-blocking when a parent loop spawns a child that shares the same scope). When `caller_singleton=True` and `caller_loop_name` matches a candidate with `singleton=True`, also returns that candidate as a singleton conflict. |
| `list_locks()` | `list[ScopeLock]` | List all active locks; cleans stale locks |
| `wait_for_scope(scope, timeout=300, *, loop_name=None, singleton=False)` | `bool` | Wait until scope is available; `False` on timeout. Pass `loop_name` + `singleton=True` so the singleton predicate fires inside the polling loop. |

#### resolve_scope

```python
def resolve_scope(scope: list[str], context: dict[str, Any]) -> list[str]
```

Resolve `${context.<var>}` template expressions in scope paths. Each template referencing a context variable is replaced with the variable's value. Unresolved templates are preserved as literal strings. Static paths (no templates) pass through unchanged.

---

### little_loops.fsm.rate_limit_circuit

Shared circuit-breaker state file for cross-worktree 429 coordination.

#### RateLimitCircuit

```python
class RateLimitCircuit:
    def __init__(self, path: Path) -> None
```

File-backed circuit-breaker for shared 429 backoff coordination. The `path` argument is the absolute path to the shared JSON state file (internally coerced via `Path(path)`); a sidecar `.lock` file is derived from it for `fcntl.flock`-guarded writes.

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `record_rate_limit(backoff_seconds)` | `None` | Record a 429 event; increments `attempts` and advances `estimated_recovery_at` monotonically so concurrent observers cannot shrink an in-flight backoff window |
| `get_estimated_recovery()` | `float \| None` | Epoch-seconds timestamp of estimated recovery, or `None` if the entry is stale or the file is absent |
| `is_stale()` | `bool` | `True` when `last_seen` is older than `STALE_THRESHOLD_SECONDS` (3600s); `False` if the file is absent |
| `clear()` | `None` | Remove the state file; no-op if already absent |

---

### little_loops.fsm.host_guard

Adaptive host memory-pressure guard (ENH-2452) and cumulative subprocess RSS budget (ENH-2453) for the FSM executor. Probes use `vm_stat` (macOS) and `/proc/meminfo` (Linux) — no psutil dependency.

#### HostGuardConfig

```python
@dataclass
class HostGuardConfig:
    enabled: bool = True                  # master switch (--no-host-guard overrides)
    cooldown_ms: int = 500                # extra sleep at warn_pct (added to --delay floor)
    warn_pct: float = 75.0                # used-memory % for extra cooldown
    critical_pct: float = 85.0            # used-memory % for on_pressure
    on_pressure: str = "cool_down"        # cool_down | route | abort
    pressure_state: str | None = None     # required when on_pressure="route"
    on_abort_route: str | None = None     # optional final state on abort
    max_cumulative_subproc_mb: int = 0    # RSS budget in MB; 0 = disabled
    on_budget_exceeded: str = "route"     # route | abort
    budget_state: str | None = None       # required when routing with an enabled budget
```

Mirrors the loop YAML `host_guard:` block; exposed as `FSMLoop.host_guard` (always present, default-enabled). Supports `to_dict()` / `from_dict()` with skip-if-default serialization.

#### HostGuard

```python
class HostGuard:
    def __init__(self, config: HostGuardConfig,
                 probe: Callable[[], float | None] = read_memory_pressure) -> None
```

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `pre_state()` | `GuardDecision` | Sample host memory and decide: `ok`, `cooldown`, `route`, or `abort`. Probe failures yield `ok` with `used_pct=None` |
| `record_subproc_rss(label, peak_rss_mb)` | `bool` | Accumulate one subprocess's peak RSS; returns `True` exactly once when the sum first crosses `max_cumulative_subproc_mb` |
| `budget_enabled` (property) | `bool` | `True` when `max_cumulative_subproc_mb > 0` |

#### Probes and sampling

| Function/Class | Description |
|----------------|-------------|
| `read_memory_pressure()` | Host used-memory percentage via `vm_stat` (macOS) or `/proc/meminfo` (Linux); `None` on failure |
| `parse_vm_stat(output)` / `parse_meminfo(text)` | Pure parsers for the probe outputs |
| `sample_rss_mb(pid)` | Live process RSS in MB (`VmHWM` peak on Linux, `ps -o rss=` elsewhere) |
| `RssSampler(pid, interval=1.0)` | Background thread tracking a subprocess's peak RSS (`start()` / `stop() -> float \| None`) |

#### Events

Emitted through the executor's event stream:

| Event | When |
|-------|------|
| `host_cooldown` | Used memory >= `warn_pct`; payload includes `used_pct`, `cooldown_seconds` |
| `host_pressure` | Used memory >= `critical_pct`; payload `action` is `route:<state>` or `abort` |
| `host_pressure_relieved` | Pressure dropped back below `warn_pct` after a critical crossing |
| `host_pressure_abort` | `on_pressure="abort"` fired; run finishes with `terminated_by="host_pressure_abort"` |
| `host_subproc_rss` | Per sampled subprocess; payload includes `peak_rss_mb`, `cumulative_mb`, `budget_mb` |
| `host_budget_exceeded` | Cumulative RSS sum first crossed the budget; run routes to `budget_state` or finishes with `terminated_by="host_budget_exceeded"` |

---

### little_loops.fsm.signal_detector

Pattern-based signal detection for interpreting special markers in action output (e.g. `CONTEXT_HANDOFF:`, `FATAL_ERROR:`, `LOOP_STOP:`).

#### DetectedSignal

```python
@dataclass
class DetectedSignal:
    signal_type: str        # Type of signal (e.g., "handoff", "error", "stop")
    payload: str | None     # Captured content after the signal marker
    raw_match: str          # The full matched string
```

#### SignalPattern

```python
class SignalPattern:
    def __init__(self, name: str, pattern: str) -> None
```

Configurable signal pattern using regex. A capture group extracts the payload.

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `search(output)` | `DetectedSignal \| None` | Search for pattern in output |

**Built-in patterns:**

| Name | Marker | Signal type |
|------|--------|-------------|
| `HANDOFF_SIGNAL` | `CONTEXT_HANDOFF: <payload>` | `"handoff"` |
| `ERROR_SIGNAL` | `FATAL_ERROR: <payload>` | `"error"` |
| `STOP_SIGNAL` | `LOOP_STOP: <payload>` | `"stop"` |

#### SignalDetector

```python
class SignalDetector:
    def __init__(self, patterns: list[SignalPattern] | None = None) -> None
```

Detect signals in command output. Defaults to the three built-in patterns.

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `detect(output)` | `list[DetectedSignal]` | Detect all signals in output |
| `detect_first(output)` | `DetectedSignal \| None` | Detect first matching signal (highest priority wins) |

**Example:**

```python
from little_loops.fsm.signal_detector import SignalDetector

detector = SignalDetector()
signal = detector.detect_first("Some output\nCONTEXT_HANDOFF: Ready for fresh session")
if signal and signal.signal_type == "handoff":
    print(signal.payload)  # "Ready for fresh session"
```

---

## little_loops.sprint

Sprint planning and execution for batch issue processing.

### SprintOptions

```python
@dataclass
class SprintOptions:
    max_iterations: int = 100   # Max Claude iterations per issue
    timeout: int = 3600         # Per-issue timeout in seconds
    max_workers: int = 2        # Worker count for parallel execution within waves
```

Sprint execution uses dependency-aware wave-based scheduling. Issues are grouped into waves where each wave contains issues whose blockers have all completed, and each wave is executed in parallel.

### Sprint

```python
@dataclass
class Sprint:
    name: str                           # Sprint identifier
    description: str                    # Human-readable purpose
    issues: list[str]                   # Issue IDs (e.g., BUG-001, FEAT-010)
    created: str                        # ISO 8601 timestamp
    options: SprintOptions | None       # Execution options
```

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `to_dict()` | `dict` | Convert for YAML serialization |
| `from_dict(data)` | `Sprint` | Create from dictionary |
| `save(sprints_dir)` | `Path` | Save to YAML file |
| `load(sprints_dir, name)` | `Sprint \| None` | Load from file |

### SprintState

Persistent state for sprint execution. Enables resume capability after interruption.

```python
@dataclass
class SprintState:
    sprint_name: str = ""                           # Name of the sprint being executed
    current_wave: int = 0                           # Wave number currently being processed (1-indexed)
    completed_issues: list[str] = []                # Completed issue IDs
    failed_issues: dict[str, str] = {}              # Issue ID → failure reason
    skipped_blocked_issues: dict[str, str] = {}     # Issue ID → block reason
    timing: dict[str, dict[str, float]] = {}        # Per-issue timing breakdown
    started_at: str = ""                            # ISO 8601 start timestamp
    last_checkpoint: str = ""                       # ISO 8601 last save timestamp
```

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `to_dict()` | `dict` | Convert for JSON serialization |
| `from_dict(data)` | `SprintState` | Create from dictionary |

### SprintManager

```python
class SprintManager:
    def __init__(
        self,
        sprints_dir: Path | None = None,
        config: BRConfig | None = None,
    )
```

Manager for sprint CRUD operations.

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `create(name, issues, description, options)` | `Sprint` | Create new sprint |
| `load(name)` | `Sprint \| None` | Load sprint by name |
| `load_or_resolve(arg)` | `Sprint \| None` | Load sprint by name **or** resolve an EPIC ID (`EPIC-NNN`) to an ephemeral Sprint via forward (`relates_to:`) + backward **transitive** (`parent:`-chain walk, cycle-guarded — grandchildren under sub-EPICs/intermediates included, ENH-2615) lookup, filtered to active statuses |
| `list_all()` | `list[Sprint]` | List all sprints |
| `delete(name)` | `bool` | Delete sprint |
| `validate_issues(issues)` | `dict[str, Path]` | Validate issue IDs exist |
| `load_issue_infos(issues)` | `list[IssueInfo]` | Load full IssueInfo objects for dependency analysis |

**Example:**
```python
from pathlib import Path
from little_loops.sprint import SprintManager, SprintOptions
from little_loops.config import BRConfig

config = BRConfig(Path.cwd())
manager = SprintManager(config=config)

# Create a sprint
sprint = manager.create(
    name="week-1",
    issues=["BUG-001", "BUG-002", "FEAT-010"],
    description="First week bug fixes and feature",
    options=SprintOptions(max_workers=2),
)

# Validate issues exist
valid = manager.validate_issues(sprint.issues)
print(f"Found {len(valid)} valid issues")

# List all sprints
for s in manager.list_all():
    print(f"{s.name}: {len(s.issues)} issues")
```

---

## little_loops.frontmatter

Shared YAML-subset frontmatter read/write utilities used by issue_parser, sync, and issue_history modules.

### Public Functions

| Function | Purpose |
|----------|---------|
| `parse_frontmatter` | Extract YAML frontmatter from file content |
| `parse_skill_frontmatter` | Extract flat key/value pairs from SKILL.md frontmatter, resolving block scalars |
| `strip_frontmatter` | Remove YAML frontmatter block, returning the body |
| `update_frontmatter` | Merge updates into (or create) the YAML frontmatter block |
| `remove_frontmatter_keys` | Delete keys from every frontmatter block, leaving the body untouched |

### parse_frontmatter

```python
def parse_frontmatter(
    content: str, *, coerce_types: bool = False
) -> dict[str, Any]
```

Extract YAML frontmatter from content between opening and closing `---` markers. Parses it with `yaml.load` (`BaseLoader`), so any valid YAML is supported — including PyYAML's own serialized output (block sequences whose long items wrap across physical lines, block scalars, flow lists, and `\uXXXX` escapes). `BaseLoader` resolves every scalar to a string, preserving the `coerce_types=False` contract (values stay strings rather than being coerced to int/bool/datetime). Empty values (`key:`, `null`, `~`) normalize to `None`; `status` synonyms are canonicalized. Malformed YAML falls back to a permissive line-based scan that warns on orphaned `- item` lines.

**Parameters:**
- `content` - File content to parse
- `coerce_types` - If `True`, coerce digit strings to `int`

**Returns:** Dictionary of frontmatter fields, or empty dict if no frontmatter found.

**Example:**
```python
from little_loops.frontmatter import parse_frontmatter

content = "---\npriority: P1\ngithub_issue: 42\n---\n# Title"
meta = parse_frontmatter(content, coerce_types=True)
print(meta)  # {"priority": "P1", "github_issue": 42}
```

### parse_skill_frontmatter

```python
def parse_skill_frontmatter(text: str) -> dict[str, str]
```

Extract flat `key: value` pairs from SKILL.md frontmatter. Uses `yaml.safe_load` so YAML block scalars (e.g. `description: |`) are resolved to their string content instead of the indicator literal `"|"`. Non-string scalar values are stringified; nested structures are dropped. Falls back to a permissive line-based scan if the frontmatter is not valid YAML (e.g. unquoted colons in values).

Prefer this over `parse_frontmatter` for SKILL.md files: it stringifies scalar values (bools/ints) and returns a flat `dict[str, str]`, the shape SKILL.md consumers expect. (`parse_frontmatter` now resolves block scalars natively via YAML, but returns a richer `dict[str, Any]`.)

**Parameters:**
- `text` - Full SKILL.md file content (including the `---` delimited frontmatter block).

**Returns:** Dictionary mapping frontmatter keys to stringified values, or empty dict if no frontmatter found.

**Example:**
```python
from little_loops.frontmatter import parse_skill_frontmatter

content = "---\ndescription: |\n  Use when user does X.\n  Trigger keywords: foo\n---\n# Body"
fm = parse_skill_frontmatter(content)
print(fm["description"])  # "Use when user does X.\nTrigger keywords: foo\n"
```

### update_frontmatter

```python
def update_frontmatter(
    content: str, updates: dict[str, str | int]
) -> str
```

Merge `updates` into an existing `---` delimited YAML frontmatter block, preserving other fields and their order. If no frontmatter block exists, a new one is prepended. Existing keys are overwritten with the new values. Uses `yaml.dump` with `default_flow_style=False, sort_keys=False` so URLs and other colon-containing values round-trip correctly.

**Parameters:**
- `content` - Full file content, possibly with existing frontmatter
- `updates` - Fields to add or overwrite in frontmatter

**Returns:** Content with the updated frontmatter block.

**Example:**
```python
from little_loops.frontmatter import update_frontmatter

content = "---\npriority: P1\n---\n\n# Title\n"
result = update_frontmatter(content, {"completed_at": "2026-04-18T12:00:00Z"})
```

### remove_frontmatter_keys

```python
def remove_frontmatter_keys(
    content: str, keys: Iterable[str]
) -> str
```

The deletion counterpart to `update_frontmatter`. Removes each key from *every*
frontmatter block, including the key's continuation lines (block scalars, list
items) so nothing is orphaned into invalid YAML. Absent keys are ignored.

Operates only within the spans of real frontmatter blocks, so a body line that
happens to start with `<key>:` — a prose mention, a table cell, a fenced YAML
example — is never rewritten. Unlike `update_frontmatter` it does not round-trip
the block through YAML, so the formatting of every surviving key is preserved
byte-for-byte.

**Parameters:**
- `content` - Full file content, possibly with existing frontmatter
- `keys` - Frontmatter keys to remove

**Returns:** Content with the keys removed from all frontmatter blocks.

**Example:**
```python
from little_loops.frontmatter import remove_frontmatter_keys

content = "---\nid: BUG-1\nparent_issue: EPIC-9\n---\n\n# Title\n"
result = remove_frontmatter_keys(content, ["parent_issue"])
```

Used by `ll-migrate-relationships` to drop a deprecated relationship key after
`update_frontmatter` has written its canonical replacement.

---

## little_loops.learning_tests

Registry for learning test records — structured knowledge about external APIs and libraries, persisted as YAML-frontmatter Markdown files under `.ll/learning-tests/<slug>.md`.

### Data Classes

#### Assertion

```python
@dataclass
class Assertion:
    claim: str
    result: Literal["pass", "fail", "untested"]
```

A single tested claim about an API or library behavior.

#### LearnTestRecord

```python
@dataclass
class LearnTestRecord:
    target: str                    # API or library name (e.g., "Anthropic SDK streaming")
    date: str                      # ISO date string (e.g., "2026-04-25")
    status: Literal["proven", "refuted", "stale"]
    assertions: list[Assertion]
    raw_output_path: str | None    # Path to raw test output, if captured
    proven_package: str | None = None   # Resolved distribution the proof ran against
    proven_version: str | None = None   # Its installed version at prove time
```

A record capturing what is known about a target API or library. Records are stored at `.ll/learning-tests/<slugified-target>.md`.

`proven_package`/`proven_version` (ENH-3125) drive version-drift staleness: a record whose distribution has moved is stale immediately, one whose version still matches is only stale past `stale_after_days * version_match_backstop_multiplier`. Both are stamped deterministically in Python by `ll-learning-tests prove` (and retroactively by `ll-learning-tests backfill-versions`) — never by the skill that authors the record. They stay `None` for stdlib and free-text targets, which keep pure age-based staleness.

**File format** (`.ll/learning-tests/<slug>.md`):

```yaml
---
target: "Anthropic SDK streaming"
date: "2026-04-25"
status: proven
assertions:
  - claim: "streaming events are dicts with a `type` key"
    result: pass
raw_output_path: ".ll/learning-tests/raw/anthropic-sdk-streaming.txt"
proven_package: anthropic
proven_version: "0.42.1"
---
```

### Public Functions

| Function | Purpose |
|----------|---------|
| `write_record` | Write a `LearnTestRecord` to `.ll/learning-tests/<slug>.md` |
| `read_record` | Read a record by slug; returns `None` if not found |
| `list_records` | Return all records in the registry directory |
| `mark_stale` | Set `status: stale` on an existing record, preserving other fields |
| `check_learning_test` | Look up a record by target name (slugified); returns `None` if not found |
| `gate.resolve_target_version` | Resolve a target to `(distribution, installed_version)`, or `None` for stdlib/unresolvable targets; never raises — ENH-3125 |
| `gate.is_record_stale` | `version_drift OR age > threshold` staleness predicate — ENH-3125 |
| `gate.describe_staleness` | Short reason a record is stale (version transition or age), or `None` if fresh — ENH-3125 |
| `resolve_learning_targets` | Return targets for an issue (field-first, JIT extraction fallback) — ENH-2319 |
| `run_learning_gate_for_issue` | Determine the learning-gate verdict for an issue and return `"passed"`, `"blocked"`, `"impl_failed"`, or `"skipped"` — ENH-2319, BUG-2833, ENH-2834 |

### write_record

```python
def write_record(
    record: LearnTestRecord, *, base_dir: Path | None = None
) -> Path
```

Write `record` to `.ll/learning-tests/<slug>.md`, overwriting any existing file for the same target slug. Returns the path of the written file.

**Example:**
```python
from little_loops.learning_tests import Assertion, LearnTestRecord, write_record

record = LearnTestRecord(
    target="Anthropic SDK streaming",
    date="2026-04-25",
    status="proven",
    assertions=[Assertion(claim="events have a 'type' key", result="pass")],
    raw_output_path=None,
)
path = write_record(record)
```

### read_record

```python
def read_record(
    target_slug: str, *, base_dir: Path | None = None
) -> LearnTestRecord | None
```

Read a record by its slug (the slugified form of `target`). Returns `None` if the file does not exist or has no parseable frontmatter.

### list_records

```python
def list_records(*, base_dir: Path | None = None) -> list[LearnTestRecord]
```

Return all `LearnTestRecord` objects in the registry directory, sorted by filename. Returns an empty list if the directory does not exist.

### mark_stale

```python
def mark_stale(target_slug: str, *, base_dir: Path | None = None) -> None
```

Set `status: stale` on the record identified by `target_slug`, preserving all other frontmatter fields. No-op if the record does not exist.

### check_learning_test

```python
def check_learning_test(
    target: str, *, base_dir: Path | None = None
) -> LearnTestRecord | None
```

Convenience wrapper: slugifies `target` and calls `read_record`. Returns `None` if not found.

**Example:**
```python
from little_loops.learning_tests import check_learning_test

rec = check_learning_test("Anthropic SDK streaming")
if rec and rec.status == "proven":
    # assertions are trusted
    pass
```

### resolve_learning_targets

```python
def resolve_learning_targets(
    issue: IssueInfo,
    *,
    llm_call: Callable[[str], str] | None = None,
) -> list[str]
```

Return learning-test targets for an issue (ENH-2319). Returns `issue.learning_tests_required` when the field is non-`None` (field-first, no LLM call). Falls back to JIT extraction via `extract_learning_targets` when the field is `None`. Returns `[]` on `OSError`.

The `is not None` sentinel is intentional: `[]` means "proven empty — no external deps" and must NOT trigger JIT extraction; `None` means "field not yet populated" and triggers it.

### run_learning_gate_for_issue

```python
def run_learning_gate_for_issue(
    issue_path: Path,
    *,
    skip: bool = False,
    cwd: Path | None = None,
    targets: list[str] | None = None,
) -> Literal["passed", "blocked", "impl_failed", "infra_failed", "skipped"]
```

Determine the learning-gate verdict for an issue and return it (ENH-2319). `skip=True` short-circuits to `"skipped"` without running any loop (honours `--skip-learning-gate`).

Two distinct paths, selected by whether `targets` is non-empty (ENH-2834):

- **`targets` non-empty** — the caller has already resolved the `learning_tests_required` registry (ENH-2209), so this invokes `ready-to-implement-gate` directly (`--context targets=<csv> --queue --queue-timeout N`) instead of chaining through `proof-first-task`'s redundant impl-loop delegation (any impl work there was thrown away — `issue_manager.py` implements the issue itself afterwards). `ready-to-implement-gate` has exactly two terminals (`done`/`blocked`), so the subprocess exit code alone is sufficient: `0` → `"passed"`, `FAILURE_TERMINAL_EXIT_CODE` → `"blocked"`. Any other non-zero exit, a backstop `TimeoutExpired`, or a missing `ll-loop` binary (`FileNotFoundError`) means the loop never ran to a terminal at all, and yields `"infra_failed"` (ENH-3084) — distinct from both a genuine refuted-target `"blocked"` and BUG-2833's delegated-impl `"impl_failed"`, so callers can retry/skip instead of consuming a remediation cycle. Mirrors the proven `_run_learning_gate_preflight()` pattern in `little_loops.cli.sprint.run`. **Queue-wait budget (BUG-3085):** the child's `--queue` wait for a conflicting scope lock (ENH-3073) is bounded by `loops.queue_wait_timeout_seconds` (default 86400s), read from config and passed down explicitly as `--queue-timeout` so the caller's own `subprocess.run` timeout (that budget plus a 60s backstop slack) never preempts it. A `subprocess.TimeoutExpired` on that backstop (a genuinely wedged child) yields `"infra_failed"`.
- **`targets` empty/`None`** — the JIT-extraction fallback (`assumption-firewall` path) is still needed, so this falls back to `proof-first-task` (`--context issue_file=<path>`). `proof-first-task` has two distinct failure terminals — `blocked` (registry gate refuted/failed) and `impl_failed` (the delegated impl loop failed after the gate passed) — that share the same non-zero exit code, so a failing exit consults the archived `LoopState.current_state` for the just-completed run via `list_run_history("proof-first-task", ...)` to discriminate them: only the `blocked` terminal yields `"blocked"`; any other terminal (or unreadable/missing history) yields `"impl_failed"` (BUG-2833).

---

## little_loops.doc_counts

Automated verification that documented counts (commands, agents, skills, loops) match actual file counts in the codebase.

### Data Classes

#### CountResult

```python
@dataclass
class CountResult:
    category: str              # e.g., "commands", "agents", "skills", "loops"
    actual: int                # Actual file count
    documented: int | None     # Documented count (if found)
    file: str | None           # Documentation file path
    line: int | None           # Line number in doc file
    matches: bool              # Whether counts match
    action_severity: Literal["auto", "mention", "route"] = "auto"  # ENH-2886
    route_owner: str | None = None  # Owning command, set only when action_severity is "route"
```

`action_severity` is a closed vocabulary mirroring `cli/doctor.py`'s `CheckResult.severity` shape: `auto` is safe for `fix_counts()` to rewrite silently, `mention` needs a human to confirm before any rewrite, `route` means another command owns the repair (named in `route_owner`). `verify_documentation()` emits `auto` for every mismatch it finds today; `mention`/`route` exist for callers that construct `CountResult` with a different provenance.

`ll-doctor`'s own exit code is not a simple any-check-failed OR: `_exit_code_for()` in `cli/doctor.py` returns non-zero only when a **`severity="error"`** result also has `status="unsupported"` — an `informational`-severity unsupported result (e.g. a host capability that is honestly absent, not broken) never fails the run. Each default and `--full`-only check independently sets its own `severity`/`status` pair rather than sharing one aggregation rule, so `--full`'s exit code is the OR of every registered check's error-tier failures, not just the default checks (FEAT-2793/FEAT-2795).

#### VerificationResult

```python
@dataclass
class VerificationResult:
    total_checked: int                   # Number of counts checked
    mismatches: list[CountResult]        # List of mismatches
    all_match: bool                      # True if all counts match
```

##### Methods

| Method | Description |
|--------|-------------|
| `add_result(result)` | Add a `CountResult` and track mismatches |

#### FixResult

```python
@dataclass
class FixResult:
    fixed_count: int              # Number of counts fixed
    files_modified: list[str]     # Files that were modified
```

### Public Functions

| Function | Purpose |
|----------|---------|
| `count_files` | Count files matching a glob pattern in a directory |
| `extract_count_from_line` | Extract a count number from a documentation line |
| `verify_documentation` | Verify all documented counts against actual file counts |
| `fix_counts` | Auto-fix count mismatches in documentation files (`auto`-severity only, ENH-2886) |
| `format_result_text` | Format verification result as plain text |
| `format_result_json` | Format verification result as JSON |
| `format_result_markdown` | Format verification result as Markdown |

### verify_documentation

```python
def verify_documentation(
    base_dir: Path | None = None,
) -> VerificationResult
```

Verify all documented counts against actual file counts.

**Parameters:**
- `base_dir` - Base directory path (defaults to current working directory)

**Returns:** `VerificationResult` with all results.

**Example:**
```python
from pathlib import Path
from little_loops.doc_counts import verify_documentation

result = verify_documentation(Path.cwd())
if result.all_match:
    print("All counts match!")
else:
    for m in result.mismatches:
        print(f"{m.category}: documented={m.documented}, actual={m.actual}")
```

---

## little_loops.link_checker

Automated verification that links in markdown files are valid. Supports HTTP/HTTPS URL checking and internal file reference validation.

### Data Classes

#### LinkResult

```python
@dataclass
class LinkResult:
    url: str                    # The URL that was checked
    file: str                   # File containing the link
    line: int                   # Line number where link appears
    status: str                 # "valid", "broken", "timeout", "ignored", "internal"
    error: str | None           # Error message if broken
    link_text: str | None       # The link text from markdown [text](url)
    action_severity: Literal["auto", "mention", "route"] = "auto"  # ENH-2886
    route_owner: str | None = None  # Owning command, set only when action_severity is "route"
```

`action_severity` mirrors `doc_counts.CountResult.action_severity`'s vocabulary. `check_markdown_links()` assigns `auto` to `valid`/`internal`/`ignored` results (no action needed) and `mention` to `broken`/`unreachable` results (a human should review — `ll-check-links` has no `--fix` path, so `mention` findings are surfaced but never rewritten). `route` is supported for callers that construct `LinkResult` directly with a different provenance.

#### LinkCheckResult

```python
@dataclass
class LinkCheckResult:
    total_links: int            # Total number of links found
    valid_links: int            # Number of valid links
    broken_links: int           # Number of broken links
    ignored_links: int          # Number of ignored links
    internal_links: int         # Number of internal file references
    results: list[LinkResult]   # Individual link results
```

##### Properties

| Property | Type | Description |
|----------|------|-------------|
| `has_errors` | `bool` | `True` if any broken links were found |

### Public Functions

| Function | Purpose |
|----------|---------|
| `extract_links_from_markdown` | Extract all links from markdown content |
| `is_internal_reference` | Check if a URL is an internal file reference |
| `should_ignore_url` | Check if a URL matches ignore patterns |
| `check_url` | Check if a single URL is reachable |
| `check_markdown_links` | Check all markdown files for broken links |
| `load_ignore_patterns` | Load ignore patterns from `.mlc.config.json` |
| `format_result_text` | Format link check result as plain text |
| `format_result_json` | Format link check result as JSON |
| `format_result_markdown` | Format link check result as Markdown |

### check_markdown_links

```python
def check_markdown_links(
    base_dir: Path,
    ignore_patterns: list[str] | None = None,
    timeout: int = 10,
    verbose: bool = False,
) -> LinkCheckResult
```

Check all markdown files for broken links.

**Parameters:**
- `base_dir` - Base directory to search
- `ignore_patterns` - List of regex patterns to ignore (defaults to localhost patterns)
- `timeout` - Request timeout in seconds
- `verbose` - Whether to show progress

**Returns:** `LinkCheckResult` with all findings.

**Example:**
```python
from pathlib import Path
from little_loops.link_checker import check_markdown_links

result = check_markdown_links(Path.cwd())
if result.has_errors:
    for r in result.results:
        if r.status == "broken":
            print(f"Broken: {r.url} at {r.file}:{r.line}")
else:
    print(f"All {result.total_links} links valid!")
```

---

## little_loops.session_log

Session log linking for issue files. Links Claude Code JSONL session files to issue files by appending timestamped log entries.

```python
from little_loops.session_log import (
    parse_session_log,
    count_session_commands,
    last_command_timestamp,
    get_current_session_jsonl,
    append_session_log_entry,
)
```

### parse_session_log

```python
def parse_session_log(content: str) -> list[str]
```

Extract distinct `/ll:*` command names from the `## Session Log` section, in first-seen order (deduplicated).

**Parameters:**
- `content` - Full text of an issue markdown file

**Returns:** List of distinct command names (e.g. `["/ll:refine-issue", "/ll:ready-issue"]`)

### count_session_commands

```python
def count_session_commands(content: str) -> dict[str, int]
```

Count occurrences of each `/ll:*` command in the `## Session Log` section. Unlike `parse_session_log()`, this does NOT deduplicate — each entry is counted.

**Parameters:**
- `content` - Full text of an issue markdown file

**Returns:** Mapping of command name to occurrence count (e.g. `{"/ll:refine-issue": 3}`)

### last_command_timestamp

```python
def last_command_timestamp(content: str, command: str) -> datetime | None
```

Return the most recent `## Session Log` timestamp for `command` — the read side of `append_session_log_entry()` (ENH-2971). Accepts both the full `- `/ll:refine-issue` - 2026-08-01T12:34:56 - `session.jsonl`` form and the older date-only form (read as midnight).

Returns a **UTC-aware** datetime, deliberately unlike `issue_history.parsing._parse_iso_datetime()`'s naive-local convention: `append_session_log_entry()` writes `datetime.now(UTC)` without a `Z` suffix, so reading those stamps as local time would skew every comparison by the local UTC offset.

**Parameters:**
- `content` - Full text of an issue markdown file
- `command` - Command name to match, e.g. `"/ll:refine-issue"`

**Returns:** The newest matching timestamp, or `None` when the command has no dated entry (or no Session Log section exists)

### get_current_session_jsonl

```python
def get_current_session_jsonl(cwd: Path | None = None) -> Path | None
```

Resolve the active Claude Code session's JSONL file path. Finds the most recently modified `.jsonl` file in the project's Claude Code session directory, excluding agent session files.

**Parameters:**
- `cwd` - Working directory to map. If `None`, uses current directory

**Returns:** `Path` to the most recent JSONL file, or `None` if not found

### append_session_log_entry

```python
def append_session_log_entry(
    issue_path: Path,
    command: str,
    session_jsonl: Path | None = None,
) -> bool
```

Append a session log entry to an issue file. Creates or appends to the `## Session Log` section with command name, ISO timestamp, and session JSONL path.

**Parameters:**
- `issue_path` - Path to the issue markdown file
- `command` - Command name (e.g. `"/ll:manage-issue"`)
- `session_jsonl` - Path to session JSONL file. If `None`, auto-detected via `get_current_session_jsonl()`

**Returns:** `True` if entry was appended, `False` if session could not be resolved

**Example:**

```python
from pathlib import Path
from little_loops.session_log import append_session_log_entry

success = append_session_log_entry(
    Path(".issues/bugs/P1-BUG-001-example.md"),
    "/ll:manage-issue",
)
```

---

## little_loops.text_utils

Text extraction utilities for issue content. Provides shared functions for extracting file paths from markdown issue text, used by `dependency_mapper`, `issue_history`, and other modules that need to identify file references.

### Public Constants

| Constant | Type | Description |
|----------|------|-------------|
| `SOURCE_EXTENSIONS` | `frozenset[str]` | Recognized source file extensions for path filtering |

### Public Functions

| Function | Purpose |
|----------|---------|
| `extract_file_paths` | Extract file paths from issue content |
| `strip_code_fences` | Remove fenced code blocks — the public form of the fence handling `extract_file_paths` applies, so callers scanning the same text for something else use identical semantics (ENH-2971) |
| `build_ref_index` | Index tracked files by basename via a single `git ls-files` call (ENH-2983) |
| `classify_file_ref` | Classify one extracted file path reference: `resolved`/`stale`/`unresolvable_form`/`planned_new`/`ambiguous` (ENH-2983, ENH-2999) |
| `suffix_match_candidates` | Candidate tracked paths a reference's suffix matches, after the mirror tie-break — 0 = absent, 1 = resolves, >1 = ambiguous; shared body behind both `resolve_ref_path` and `classify_file_ref` (ENH-2999) |
| `resolve_ref_path` | Return the tracked repo-relative path a reference resolves to, or `None` — steps 3-4 of `classify_file_ref`'s resolution order, for callers needing the *target* rather than the verdict (ENH-2971) |
| `classify_issue_refs` | Classify every file path reference extracted from one issue body (ENH-2983) |
| `extract_words` | Tokenize text into a set of significant words (3+ chars, stop words removed) |
| `calculate_word_overlap` | Jaccard similarity between two word sets |
| `score_bm25` | BM25 relevance score for a document against a query |

### SOURCE_EXTENSIONS

```python
SOURCE_EXTENSIONS: frozenset[str]
```

A `frozenset` of 24 file extension strings (each with leading dot) considered real source file paths. Used to filter false-positive path matches during extraction.

Includes: `.py`, `.ts`, `.js`, `.tsx`, `.jsx`, `.md`, `.json`, `.yaml`, `.yml`, `.toml`, `.cfg`, `.ini`, `.html`, `.css`, `.scss`, `.sh`, `.bash`, `.sql`, `.go`, `.rs`, `.java`, `.kt`, `.rb`, `.php`

### extract_file_paths

```python
def extract_file_paths(content: str) -> set[str]
```

Extract file paths from issue content. Searches for paths in backtick-quoted references, bold `**File**:` labels, and standalone paths with recognized extensions. Code fence blocks are stripped before extraction to avoid matching example code.

**Parameters:**
- `content` - Issue file content (markdown text)

**Returns:** `set[str]` of file paths found in the content.

**Example:**
```python
from little_loops.text_utils import extract_file_paths

content = """
## Location

**File**: `scripts/little_loops/config.py`

See also `docs/reference/API.md` and scripts/little_loops/state.py:42.
"""

paths = extract_file_paths(content)
print(paths)
# {'scripts/little_loops/config.py', 'docs/reference/API.md', 'scripts/little_loops/state.py'}
```

### RefStatus / RefIndex

```python
RefStatus = Literal["resolved", "stale", "unresolvable_form", "planned_new", "ambiguous"]

@dataclass(frozen=True)
class RefIndex:
    by_basename: dict[str, list[str]]  # basename -> tracked repo-relative paths
```

`RefIndex` is the tracked-file index used by `classify_file_ref()`/`classify_issue_refs()` (ENH-2983). Built once per invocation and threaded through, never rebuilt per reference.

### build_ref_index

```python
def build_ref_index(root: Path) -> RefIndex
```

Index tracked files by basename via a single `git ls-files -z` call. Fails open (empty index, never raises) when git is unavailable or exits non-zero, matching the convention of the other `git ls-files` call sites in this codebase (`cli/verify_private_refs.py`, `codequery/fallback.py`).

**Parameters:**
- `root` - Repository root to run `git ls-files` from.

**Returns:** A `RefIndex` mapping each tracked file's basename to the list of repo-relative paths sharing that basename.

### classify_file_ref

```python
def classify_file_ref(ref: str, index: RefIndex, *, line: str = "") -> RefStatus
```

Classify one path reference extracted from issue prose. Resolution order (not commutative): form checks first (glob, `<placeholder>`, bare basename with no `/` — all `unresolvable_form`, checked before any suffix matching so a bare basename like `SKILL.md` cannot spuriously suffix-match dozens of tracked files); then `planned_new` from line context (a `(new)` marker); then an exact tracked-path match; then a suffix match against the basename-keyed index via `suffix_match_candidates()` — zero candidates is `stale`, exactly one is `resolved`, more than one is `ambiguous` (ENH-2999). A ref whose only match is a generated host-adapter mirror still resolves; a ref whose matches are 2+ non-mirror paths declines with `ambiguous` rather than picking one silently.

**Parameters:**
- `ref` - The path reference as extracted from issue prose.
- `index` - A `RefIndex` built once per invocation.
- `line` - The source line the reference was found on, used only for `planned_new` detection.

**Returns:** One of `"resolved"`, `"stale"`, `"unresolvable_form"`, `"planned_new"`, or `"ambiguous"`.

### suffix_match_candidates

```python
def suffix_match_candidates(ref: str, index: RefIndex) -> list[str]
```

Candidate tracked paths for *ref* after the existing resolution order (ENH-2999): exact-match short-circuit, then suffix match against the basename index, then the host-adapter mirror tie-break applied only when the raw suffix match is not already unique. `0 = absent, 1 = resolves, >1 = ambiguous`. Holds the shared body behind both `resolve_ref_path()` (which needs only the resolved target) and `classify_file_ref()` (which needs to distinguish "no match" from "many matches"). If every suffix match is a mirror, the mirror filter yields an empty list — reported the same as zero matches (`stale`), not `ambiguous`.

**Parameters:**
- `ref` - The path reference as extracted from issue prose.
- `index` - A `RefIndex` built once per invocation.

**Returns:** `list[str]` of tracked repo-relative paths *ref*'s suffix matches, after the mirror tie-break.

### classify_issue_refs

```python
def classify_issue_refs(content: str, index: RefIndex) -> dict[str, RefStatus]
```

Classify every file path reference extracted from one issue body — pairs each reference from `extract_file_paths()` with the first source line it appears on, then classifies it with `classify_file_ref()`.

**Parameters:**
- `content` - Full issue file content (frontmatter + body).
- `index` - A `RefIndex` built once per invocation.

**Returns:** A mapping of reference string to its `RefStatus`.

### extract_words

```python
def extract_words(text: str) -> set[str]
```

Extract significant words from text. Returns lowercase alphabetic words of 3+ characters, excluding common stop words (`the`, `and`, `file`, `code`, `issue`, etc.).

**Parameters:**
- `text` - Input text

**Returns:** `set[str]` of significant words.

### calculate_word_overlap

```python
def calculate_word_overlap(words1: set[str], words2: set[str]) -> float
```

Calculate Jaccard similarity between two word sets: `|intersection| / |union|`.

**Returns:** Float in `[0.0, 1.0]`.

### score_bm25

```python
def score_bm25(
    query_words: set[str],
    doc_words: set[str],
    doc_freq: dict[str, int],
    avg_doc_len: float,
    total_docs: int,
    k1: float = 1.5,
    b: float = 0.75,
) -> float
```

BM25 relevance score for a document against a query. Uses Robertson BM25 with IDF smoothing. Since `doc_words` comes from `extract_words()` (a set), term frequency within the document is always 1 for matching terms.

**Parameters:**
- `query_words` - Set of query terms
- `doc_words` - Set of document terms (unique words, from `extract_words`)
- `doc_freq` - Document frequency per term (number of docs containing each term)
- `avg_doc_len` - Average document length in unique words across corpus
- `total_docs` - Total number of documents in corpus
- `k1` - Term frequency saturation parameter (default: `1.5`)
- `b` - Length normalization parameter (default: `0.75`)

**Returns:** Non-negative float. Normalize to `[0, 1)` via `score / (score + 1)` before combining with intersection scores.

**Example:**
```python
from little_loops.text_utils import extract_words, score_bm25

docs = ["session logging added to history CLI", "sprint dependency ordering fixed"]
doc_words_list = [extract_words(d) for d in docs]

# Build corpus stats
doc_freq: dict[str, int] = {}
for words in doc_words_list:
    for word in words:
        doc_freq[word] = doc_freq.get(word, 0) + 1
avg_doc_len = sum(len(w) for w in doc_words_list) / len(doc_words_list)

query = extract_words("session logging")
raw = score_bm25(query, doc_words_list[0], doc_freq=doc_freq, avg_doc_len=avg_doc_len, total_docs=2)
normalized = raw / (raw + 1)  # map to [0, 1)
print(f"BM25 normalized: {normalized:.3f}")
```

---

## little_loops.pii

Regex-based PII detection and redaction utilities for SFT corpus filtering.

```python
from little_loops.pii import detect_pii, redact_pii, apply_pii_action
```

### PII_PATTERNS

```python
PII_PATTERNS: dict[str, re.Pattern[str]]
```

Module-level dict mapping PII type names to their compiled regex patterns.

| Key | Pattern covers |
|-----|---------------|
| `"email"` | Standard email addresses |
| `"phone"` | US phone numbers (with/without country code, parens, dashes, dots) |
| `"ssn"` | Social Security Numbers (``NNN-NN-NNNN`` format) |

### detect_pii

```python
def detect_pii(text: str) -> list[str]
```

Return list of PII type names found in *text*.

**Parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `text` | `str` | Input text to scan |

**Returns**: List of PII type name strings (e.g. `["email", "phone"]`); empty list if none found.

### redact_pii

```python
def redact_pii(text: str) -> str
```

Replace all PII spans in *text* with ``[TYPE]`` placeholders.

**Parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `text` | `str` | Input text to redact |

**Returns**: Text with PII replaced by ``[EMAIL]``, ``[PHONE]``, or ``[SSN]`` placeholders.

### apply_pii_action

```python
def apply_pii_action(example: dict, action: str) -> dict | None
```

Apply ``flag``/``redact``/``discard`` to a formatted SFT example dict.

**Parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `example` | `dict` | SFT example dict (Alpaca, ShareGPT, etc.) |
| `action` | `str` | One of ``"flag"``, ``"redact"``, ``"discard"`` |

**Returns**: Modified example dict, or ``None`` for ``"discard"`` when PII is detected.

**Raises**: `ValueError` if *action* is not one of the three supported values.

**Example**

```python
from little_loops.pii import detect_pii, redact_pii, apply_pii_action

text = "Contact john@example.com or call 555-867-5309"
detect_pii(text)    # -> ["email", "phone"]
redact_pii(text)    # -> "Contact [EMAIL] or call [PHONE]"

example = {"instruction": "Email john@example.com", "output": "OK"}
apply_pii_action(example, "flag")     # -> {... "pii_detected": True}
apply_pii_action(example, "redact")   # -> {"instruction": "Email [EMAIL]", ...}
apply_pii_action(example, "discard")  # -> None
```

---

## little_loops.events

Structured event system and EventBus dispatcher for the extension architecture.

> **Event catalog:** For a complete reference of all event types, payload fields, and subsystem namespaces, see [EVENT-SCHEMA.md](EVENT-SCHEMA.md).

```python
from pathlib import Path

from little_loops.events import EventBus, LLEvent
from little_loops.transport import JsonlTransport

bus = EventBus()
bus.register(lambda evt: print(f"Event: {evt['event']}"))
bus.add_transport(JsonlTransport(Path(".ll/events.jsonl")))
bus.emit(LLEvent(type="issue.completed", timestamp="2026-04-02T12:00:00Z", payload={"id": "BUG-001"}).to_dict())
```

### EventCallback

Type alias for event observer callables.

```python
EventCallback = Callable[[dict[str, Any]], None]
```

A callable that accepts a single `dict[str, Any]` argument (the serialized event) and returns `None`. Used as the type for observers registered with `EventBus.register()`.

### LLEvent

Structured event dataclass for the extension system.

```python
@dataclass
class LLEvent:
    type: str                              # Event type identifier (e.g., "issue.completed")
    timestamp: str                         # ISO 8601 timestamp string
    payload: dict[str, Any] = field(default_factory=dict)  # Additional event data
```

#### Methods

```python
def to_dict(self) -> dict[str, Any]
```
Serialize to a flat dictionary. Field names are remapped: `type` becomes `"event"`, `timestamp` becomes `"ts"`, and `payload` keys are spread into the root.

**Returns:** `{"event": self.type, "ts": self.timestamp, **self.payload}`

```python
@classmethod
def from_dict(cls, data: dict[str, Any]) -> LLEvent
```
Deserialize from a flat dictionary. Pops `"event"` (fallback: `"type"`, `"unknown"`) for the type field and `"ts"` (fallback: `"timestamp"`, `""`) for timestamp. Remaining keys become the payload. Operates on a copy of `data`.

```python
@classmethod
def from_raw_event(cls, raw: dict[str, Any]) -> LLEvent
```
Convenience wrapper over `from_dict`. Copies the input dict before parsing so the original is not mutated.

### EventBus

Central dispatcher that fans out events to registered observers and transports.

```python
from little_loops.events import EventBus, LLEvent
from little_loops.transport import JsonlTransport
from pathlib import Path

bus = EventBus()
bus.register(lambda evt: print(evt))
bus.add_transport(JsonlTransport(Path(".ll/events.jsonl")))
bus.emit({"event": "test", "ts": "2026-04-02T00:00:00Z"})
```

#### Constructor

```python
EventBus()
```

Initializes empty observer and transport lists. No parameters.

#### Methods

| Method | Description |
|--------|-------------|
| `register(callback: EventCallback, filter: str \| list[str] \| None = None) -> None` | Append an observer callback with an optional glob filter. `None` (default) receives all events. |
| `unregister(callback: EventCallback) -> None` | Remove an observer by identity. Silently ignores if not found. |
| `add_transport(transport: Transport) -> None` | Register a `Transport` to receive every emitted event. |
| `close_transports() -> None` | Call `close()` on every registered transport, isolating exceptions. |
| `emit(event: dict[str, Any]) -> None` | Fan out event to matching observers, then deliver to every transport via `send()`. Per-observer and per-transport exceptions are caught and logged. |
| `read_events(path: Path) -> list[LLEvent]` | *(static)* Read a JSONL event log file. Returns `[]` if file does not exist. Skips invalid JSON lines. |

#### Filter parameter

The `filter` argument to `register()` accepts a glob pattern string or list of patterns matched against the event's `"event"` key using `fnmatch`:

```python
# Subscribe to issue namespace only
bus.register(my_callback, filter="issue.*")

# Subscribe to multiple namespaces
bus.register(my_callback, filter=["issue.*", "parallel.*"])

# Subscribe to bare FSM event names
bus.register(my_callback, filter=["state_enter", "loop_*"])

# Subscribe to everything (default)
bus.register(my_callback)
```

**Event namespace conventions:**
- `issue.*` — issue lifecycle events (`issue.closed`, `issue.completed`, etc.)
- `state.*` — state manager events (`state.issue_completed`, `state.issue_failed`)
- `parallel.*` — parallel orchestrator events (`parallel.worker_completed`, `parallel.epic_branch_stale`)
- Bare names — FSM executor events (`state_enter`, `loop_start`, `action_start`, etc.)

---

## little_loops.history_reader

Typed read-only query module for `.ll/history.db` (ENH-1752). Provides the common queries that ll skills and agents need to consume the session database without importing ad-hoc SQL into every caller. All functions degrade gracefully: missing/empty/corrupt databases return empty lists, never raise.

> **Session store:** For the write-side schema, `SQLiteTransport`, and backfill functions, see [`little_loops.session_store`](#little_loopssession_store).

```python
from little_loops.history_reader import (
    find_user_corrections,
    recent_file_events,
    search,
    related_issue_events,
    sessions_for_issue,
    lookup_session_metadata,
    conversation_turns,
    recent_skill_events,     # ENH-2460
    summarize_skills,        # ENH-2460
    recent_commit_events,    # ENH-2458
    recent_test_runs,        # ENH-2459
    OrchestrationRun,        # ENH-2492
    recent_orchestration_runs,    # ENH-2492
    aggregate_orchestration_runs, # ENH-2492
    find_session_for_issue_transition,  # ENH-2462
    agent_usage,             # ENH-2497
    recent_tool_events,      # ENH-2497
    LearningTestEvent,       # ENH-2466
    recent_learning_tests,   # ENH-2466
    find_learning_test,      # ENH-2466
    LifecycleEvent,          # ENH-2495
    recent_lifecycle_events, # ENH-2495
    handoff_frequency,       # ENH-2495
    SubagentRun,             # ENH-2505
    subagent_tree,           # ENH-2505
    subagent_retries,        # ENH-2505
    subagent_budget,         # ENH-2505
    HookEvent,               # ENH-2506
    recent_hook_events,      # ENH-2506
    hook_failure_rate,       # ENH-2506
    hook_latency_p95,        # ENH-2506
    HarnessEvent,            # ENH-2741
    recent_harness_events,   # ENH-2741
    harness_eval_pass_rate,  # ENH-2741
    PromptOptEvent,          # ENH-2498
    recent_prompt_opt_events, # ENH-2498
    prompt_opt_offer_rate,   # ENH-2498
    VerdictEvent,            # ENH-2504
    recent_verdict_events,   # ENH-2504
    verdict_pass_rate,       # ENH-2504
    ReviewEvent,             # ENH-2512
    recent_review_events,    # ENH-2512
    review_velocity,         # ENH-2512
)
```

### PromptOptEvent

Dataclass for `prompt_opt_events` rows — one prompt-optimization offer/outcome (ENH-2498). `offered`/`bypass_reason`/`mode`/`raw_len` are written live at hook-fire time; `optimized_len`/`optimized_text`/`accepted` start `NULL` and are filled in by `_backfill_prompt_opt()` when the transcript's next assistant turn contains a parseable `ENHANCED:` block.

```python
@dataclass
class PromptOptEvent:
    ts: str
    session_id: str | None
    mode: str | None
    offered: int | None
    bypass_reason: str | None
    raw_len: int | None
    optimized_len: int | None
    optimized_text: str | None
    accepted: int | None
```

### recent_prompt_opt_events / prompt_opt_offer_rate

```python
def recent_prompt_opt_events(
    *, mode: str | None = None, since: str | None = None, limit: int = 50, db: Path | str = DEFAULT_DB_PATH,
) -> list[PromptOptEvent]

def prompt_opt_offer_rate(*, since: str | None = None, db: Path | str = DEFAULT_DB_PATH) -> float | None
```

`recent_prompt_opt_events()` returns rows newest first, optionally filtered by exact `mode` and/or a `since` lower bound on `ts`. `prompt_opt_offer_rate()` returns the fraction of rows with `offered = 1`, or `None` when there are zero rows.

### SubagentRun

Dataclass for `subagent_runs` rows — one Task/Agent spawn (ENH-2505). `agent_id` is spawn-local (scoped to `parent_session_id`, not a `sessions.session_id`); a subagent's transcript is a nested file, not a joinable top-level session row.

```python
@dataclass
class SubagentRun:
    ts: str
    parent_session_id: str | None
    agent_id: str | None
    agent_type: str | None
    agent_transcript_path: str | None
    started_at: str | None
    ended_at: str | None
    status: str | None
```

```python
def subagent_tree(session_id: str, *, db: Path | str = DEFAULT_DB_PATH) -> list[SubagentRun]
def subagent_retries(agent_type: str, *, since: str | None = None, db: Path | str = DEFAULT_DB_PATH) -> list[dict]
def subagent_budget(session_id: str, *, db: Path | str = DEFAULT_DB_PATH) -> dict | None
```

`subagent_tree()` returns the direct `agent_id` spawns for a parent session (no grandchild recursion — that requires re-parsing each `agent_transcript_path`, not a SQL join). `subagent_retries()` returns per-parent re-spawn counts for a given `agent_type`, restricted to parents that spawned it more than once (the "oscillation" signal). `subagent_budget()` returns `{"spawn_count", "total_duration_s"}` for a parent session (the "burn budget" signal), or `None` when no rows exist.

### UserCorrection

Dataclass for user correction rows from the `user_corrections` table.

```python
@dataclass
class UserCorrection:
    ts: str
    session_id: str | None
    content: str
    source: str | None
```

### FileEvent

Dataclass for file event rows from the `file_events` table.

```python
@dataclass
class FileEvent:
    ts: str
    session_id: str | None
    path: str | None
    op: str | None
    issue_id: str | None
    git_sha: str | None
```

### SearchResult

Dataclass for FTS5 search results from the `search_index` virtual table.

```python
@dataclass
class SearchResult:
    content: str
    kind: str
    ref: str
    anchor: str
    ts: str
    score: float
```

### IssueEvent

Dataclass for issue event rows from the `issue_events` table.

```python
@dataclass
class IssueEvent:
    ts: str
    issue_id: str | None
    transition: str | None
    discovered_by: str | None
    issue_type: str | None
    priority: str | None
```

### SessionRef

Dataclass for `issue_sessions` view rows (ENH-1711). A session that co-occurred with an issue's active period.

```python
@dataclass
class SessionRef:
    issue_id: str | None
    session_id: str | None
    jsonl_path: str | None
    first_message_ts: str | None
    last_message_ts: str | None
```

### find_user_corrections

```python
def find_user_corrections(
    topic: str,
    *,
    limit: int = 10,
    include_stale: bool = False,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[UserCorrection]
```

Return user corrections whose content matches *topic* (LIKE search).

**Parameters:**
- `topic` — substring to match against the `content` column (LIKE `%topic%`)
- `limit` — maximum number of rows to return (default: 10)
- `include_stale` — if `False` (default), excludes rows older than 30 days
- `db` — path to the SQLite database (default: `.ll/history.db`)

**Returns:** List of `UserCorrection` instances ordered by `ts DESC`. Returns `[]` if the database is unavailable.

### recent_file_events

```python
def recent_file_events(
    path: str,
    *,
    limit: int = 10,
    include_stale: bool = False,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[FileEvent]
```

Return recent file events for *path* (LIKE pattern match).

**Parameters:**
- `path` — substring to match against the `path` column (LIKE `%path%`)
- `limit` — maximum number of rows to return (default: 10)
- `include_stale` — if `False` (default), excludes rows older than 30 days
- `db` — path to the SQLite database (default: `.ll/history.db`)

**Returns:** List of `FileEvent` instances ordered by `ts DESC`. Returns `[]` if the database is unavailable.

### search

```python
def search(
    query: str,
    *,
    kind: str | None = None,
    limit: int = 10,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[SearchResult]
```

FTS5 full-text search with optional *kind* filter.

**Parameters:**
- `query` — search string, matched as a literal FTS5 phrase (BM25-ranked results). The query is quoted via `fts_phrase()`, so hyphenated issue IDs (e.g. `BUG-490`) and other FTS5 operator characters match literally instead of being parsed as expressions (BUG-2651).
- `kind` — optional filter: `tool`, `file`, `issue`, `loop`, `correction`, `message`
- `limit` — maximum number of rows to return (default: 10)
- `db` — path to the SQLite database (default: `.ll/history.db`)

**Returns:** List of `SearchResult` instances ordered by BM25 score. Returns `[]` if the database is unavailable or the FTS5 query syntax is invalid.

### related_issue_events

```python
def related_issue_events(
    issue_id: str,
    *,
    session_id: str | None = None,
    limit: int = 20,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[IssueEvent]
```

Return issue events for *issue_id*, ordered by most recent first. When `session_id` is given, only events recorded with that exact authoritative session ID are returned (ENH-2462).

**Parameters:**
- `issue_id` — the issue identifier (e.g., `"ENH-1752"`)
- `session_id` — optional exact `issue_events.session_id` filter (ENH-2462)
- `limit` — maximum number of rows to return (default: 20)
- `db` — path to the SQLite database (default: `.ll/history.db`)

**Returns:** List of `IssueEvent` instances ordered by `ts DESC` (each carries `session_id`, `None` for legacy rows). Returns `[]` if the database is unavailable.

### find_session_for_issue_transition

```python
def find_session_for_issue_transition(
    issue_id: str,
    transition: str,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> str | None
```

Return the authoritative `session_id` recorded for an exact issue transition (ENH-2462), or `None` for legacy pre-v16 rows, transitions emitted outside a session-known context, or unknown transitions.

### recent_skill_events

```python
def recent_skill_events(
    skill_name: str | None = None,
    *,
    limit: int = 20,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[SkillEvent]
```

Return recent `skill_events` rows, newest first, including the v15 completion columns (`exit_code`, `success`, `duration_ms` — `None` for dispatch-only rows) (ENH-2460).

### summarize_skills

```python
def summarize_skills(
    since: str | None = None,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]
```

Per-skill rollup powering `ll-session skill-stats` (ENH-2460): returns dicts with `skill_name`, `invocations`, `completions`, `successes`, `success_rate` (over completion-carrying rows only; `None` when no completions), and `avg_duration_ms`, sorted by invocation count descending.

### agent_usage

```python
def agent_usage(
    since: str | None = None,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]
```

Per-agent rollup of `Task`-tool subagent spawn counts (ENH-2497): returns dicts with `agent_type` and `invocations`, filtered to `tool_name='Task'` rows with a non-NULL `agent_type` (the v24 `tool_events` column), sorted by invocation count descending. Returns `[]` on a missing/unreadable DB.

### recent_tool_events

```python
def recent_tool_events(
    agent_type: str | None = None,
    mcp_server: str | None = None,
    mcp_tool: str | None = None,
    mcp_outcome: str | None = None,
    *,
    limit: int = 20,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]
```

Return recent `tool_events` rows, newest first, optionally filtered to a single `agent_type` (ENH-2497) and/or `mcp_server`/`mcp_tool`/`mcp_outcome` (ENH-2511, the v25 `tool_events` columns). Returns `[]` on a missing/unreadable DB.

### mcp_server_usage

```python
def mcp_server_usage(
    server: str | None = None,
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]
```

Per-MCP-server rollup of invocations/completions/success rate/average latency (ENH-2511), sourced from `tool_events.mcp_server`/`mcp_outcome`/`latency_ms`. Returns `[]` on a missing/unreadable DB.

### mcp_failure_rate

```python
def mcp_failure_rate(
    server: str | None = None,
    tool: str | None = None,
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]
```

Per-server/tool MCP failure-rate rollup (ENH-2511): counts of invocations and `mcp_outcome='error'` rows, grouped by `(mcp_server, mcp_tool)`. Returns `[]` on a missing/unreadable DB.

### cost_attribution

```python
def cost_attribution(
    group_by: str = "gen_ai.invocation.id",
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]
```

Per-`group_by` token/cost rollup over `usage_events` (FEAT-2478). `group_by` is an
OTel attribute name (`gen_ai.invocation.id` / `gen_ai.provider.vendor`) or a raw
column (`session_id` / `model` / `state` / `invocation_id` / `provider_vendor`); any
other value raises `ValueError` (the `GROUP BY` clause is whitelisted). Each returned
dict carries the group key plus the summed token counts under the canonical dotted
OTel names (`gen_ai.usage.input_tokens`, `gen_ai.usage.cache_read.input_tokens`, …),
`cost_usd`, and `invocations`, so a `GROUP BY gen_ai.invocation.id` rollup matches raw
`result`-event `usage` totals row-for-row.

### waste_attribution

```python
def waste_attribution(
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]
```

Per-`loop_name` rollup of token spend vs. spend wasted on runs that produced no
accepted artifact (ENH-2722). Joins `usage_events.run_id = loop_runs.run_id`
(an exact equi-join, no time-range join — depends on ENH-2721/2723/2724's
`run_id` column and live writer). A run is "wasted" when `terminated_by` is an
infra/step-cap exit (`error` / `max_steps` / `max_iterations_reached` /
`timeout` / `system_signal` / `interrupted`), or a normal FSM completion
(`terminated_by == "terminal"`) that stopped on a failure terminal — a
`"terminal"` finish alone does not imply success. Since ENH-2814 failure-ness
is read from the persisted `loop_runs.failure_terminal` flag rather than
re-derived in SQL from `final_state != 'done'`; rows written before ENH-2814
have `NULL` there and fall back to that legacy name check. Operator-initiated
exits (`user_stopped` / `handoff`) are not counted as waste, and per-iteration
`diff_stall` / `score_stall` discard tracking is out of scope (an explicit
follow-on). Each returned dict carries `loop_name`, `tokens_total`,
`tokens_wasted`, `waste_pct` (`tokens_wasted / tokens_total`, or `None` when
`tokens_total` is 0), `runs_total`, and `runs_wasted`. `usage_events` rows with
no matching `loop_runs` row are excluded by the inner join. Returns `[]` on a
missing/unreadable DB.

### recent_commit_events

```python
def recent_commit_events(
    *,
    branch: str | None = None,
    issue_id: str | None = None,
    limit: int = 20,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[CommitEvent]
```

Return recent `commit_events` rows, newest first, optionally filtered by exact `branch` and/or `issue_id` (ENH-2458). `CommitEvent` carries `ts`, `commit_sha`, `parent_sha`, `message`, `author`, `branch`, `issue_id`, and `files_json` (JSON array of touched paths).

### recent_test_runs

```python
def recent_test_runs(
    *,
    branch: str | None = None,
    head_sha: str | None = None,
    limit: int = 50,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[RunEvent]
```

Return recent `test_run_events` rows, newest first, optionally filtered (ENH-2459). `RunEvent` exposes a derived `pass_rate` property (`passed / total`, `None` when `total` is 0/unknown).

### OrchestrationRun / recent_orchestration_runs / aggregate_orchestration_runs

```python
@dataclass
class OrchestrationRun:
    run_id: str
    driver: str
    issue_id: str
    status: str
    failure_reason: str | None
    duration_s: float | None
    wave: str | None
    pr_url: str | None
    started_at: str | None
    ended_at: str | None
    head_sha: str | None
    branch: str | None


def recent_orchestration_runs(
    driver: str | None = None,
    issue_id: str | None = None,
    *,
    since: str | None = None,
    limit: int = 50,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[OrchestrationRun]


def aggregate_orchestration_runs(
    group_by: Literal["driver", "issue_id", "status"] = "driver",
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]
```

Read per-issue outcomes written by `ll-auto`, `ll-parallel`, and `ll-sprint` (ENH-2492). The recent reader filters by exact driver/issue and optional completion-time lower bound. The aggregate reader returns run count, completed count, success rate, and average duration for a fixed, SQL-safe grouping dimension. Both return `[]` on unavailable or pre-v22 databases.

### LoopRun / recent_loop_runs / find_loop_run / aggregate_loop_runs

```python
@dataclass
class LoopRun:
    run_id: str
    loop_name: str
    started_at: str | None
    ended_at: str | None
    final_state: str | None
    iterations: int | None
    terminated_by: str | None
    error: str | None
    evaluator_score: float | None
    diagnostics_path: str | None
    head_sha: str | None
    branch: str | None


def recent_loop_runs(
    *,
    loop_name: str | None = None,
    since: str | None = None,
    limit: int = 50,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[LoopRun]


def find_loop_run(run_id: str, *, db: Path | str = DEFAULT_DB_PATH) -> LoopRun | None


def aggregate_loop_runs(
    group_by: Literal["loop_name", "terminated_by"] = "loop_name",
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]
```

Read per-run summaries written by `FSMExecutor._finish()` (ENH-2463). `recent_loop_runs()` filters by exact `loop_name` and optional completion-time lower bound; `find_loop_run()` looks up a single row by its archive-time `run_id`; `aggregate_loop_runs()` returns run count and mean iteration count for a fixed grouping dimension. All three return `[]`/`None` on unavailable or pre-v23 databases. Known v1 coverage gap: runs that exit via handoff or forced archive (never reaching `_finish()`) have no row.

### LearningTestEvent / recent_learning_tests / find_learning_test

```python
@dataclass
class LearningTestEvent:
    ts: str
    record_id: str
    target: str | None
    status: str | None
    assertions_json: str | None
    date: str | None
    raw_output_path: str | None


def recent_learning_tests(
    *,
    status: str | None = None,
    limit: int = 20,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[LearningTestEvent]


def find_learning_test(target: str, *, db: Path | str = DEFAULT_DB_PATH) -> LearningTestEvent | None
```

Read the `learning_test_events` mirror of the Learning Test Registry (`.ll/learning-tests/*.md`, ENH-2466). `LearningTestEvent` is the DB-side mirror row — not to be confused with `little_loops.learning_tests.LearnTestRecord`, the registry-file dataclass it mirrors. `recent_learning_tests()` filters by exact `status`; `find_learning_test()` looks up a single row by `target` (slugified to `record_id` internally). Both return `[]`/`None` on unavailable or pre-v26 databases.

### LifecycleEvent / recent_lifecycle_events / handoff_frequency

```python
@dataclass
class LifecycleEvent:
    id: int
    ts: str
    session_id: str | None
    event: str
    detail: dict | None
    head_sha: str | None
    branch: str | None


def recent_lifecycle_events(
    *,
    event: str | None = None,
    since: str | None = None,
    limit: int = 50,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[LifecycleEvent]


def handoff_frequency(*, since: str | None = None, db: Path | str = DEFAULT_DB_PATH) -> int
```

Read the `session_lifecycle_events` table — session-lifecycle/handoff transitions written by `record_session_lifecycle_event()` (ENH-2495). `LifecycleEvent.detail` is parsed from the stored JSON `TEXT` column into a `dict` (unlike `CommitEvent.files_json`/`LearningTestEvent.assertions_json`, which stay raw strings). `recent_lifecycle_events()` filters by exact `event` discriminator and/or `ts >= since`. `handoff_frequency()` counts `handoff_needed` rows, optionally since a timestamp — the metric for "how often does this project hit the context-handoff threshold?". Both return `[]`/`0` on unavailable databases.

### sessions_for_issue

```python
def sessions_for_issue(
    issue_id: str,
    *,
    limit: int = 20,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[SessionRef]
```

Return sessions that co-occurred with *issue_id*'s active period.

**Parameters:**
- `issue_id` — the issue identifier (e.g., `"ENH-1752"`)
- `limit` — maximum number of rows to return (default: 20)
- `db` — path to the SQLite database (default: `.ll/history.db`)

**Returns:** List of `SessionRef` instances ordered by `first_message_ts DESC`. Queries the `issue_sessions` VIEW (v5 schema migration, ENH-1711). Returns `[]` when the view is absent (pre-v5 schema), the issue has no recorded sessions, or the database is unavailable.

### lookup_session_metadata

```python
def lookup_session_metadata(
    session_id: str,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> dict
```

Return session-quality metadata for a session ID (ENH-1943).

**Parameters:**
- `session_id` — the session UUID to query
- `db` — path to the SQLite database (default: `.ll/history.db`)

**Returns:** `dict` with keys `has_corrections` (bool), `issue_outcome` (str|None), `tool_count` (int), `files_modified` (int), and `loop_outcome` (None). `issue_outcome` is the transition value when an issue was closed in this session; `None` if no issue was closed. `loop_outcome` is always `None` — `loop_events` has no `session_id` column, so loop outcomes cannot be joined to sessions without a schema change. Returns empty `{}` when the DB is missing, empty, lacks relevant tables, or any query raises a SQL error. All computed fields default to their zero values when the session ID has no matching rows.

**Used by:** `sft-corpus` loop (enrich state) to batch-join session-quality signals for SFT corpus filtering.

### conversation_turns

```python
def conversation_turns(
    db_path: Path | str,
    since: datetime | None = None,
    context_window: int = 3,
) -> list[list[tuple[str, str]]]
```

Return conversation turn-pair windows from `history.db` (ENH-1942).

Queries `message_events` and `assistant_messages` (requires schema ≥ v11), pairs user messages with their assistant responses via temporal adjacency, and groups them into sliding windows of `context_window` turn-pairs each.

**Parameters:**
- `db_path` — path to `history.db`
- `since` — only include turns where the user message timestamp is >= this value (optional)
- `context_window` — number of (user, assistant) turn-pairs per output window (default: 3)

**Returns:** List of conversation windows; each window is a `list[tuple[str, str]]` alternating between `("user", text)` and `("assistant", text)`. Returns `[]` when the database is missing, empty, predates schema v11 (no `assistant_messages` table), no turn-pairs match the `since` filter, or any query raises a SQL error.

**Temporal adjacency pairing:** Each assistant message (from `assistant_messages`) is paired with the immediately preceding user message in the same session. Assistant messages that fall between user message A and user message B are assigned to user message A. Multiple assistant messages following a single user message are joined with `"\n\n"`.

**Sliding windows:** N turn-pairs produce `max(1, N - context_window + 1)` output windows. A single turn-pair session still produces 1 window (of 1 pair). Windows are emitted in chronological order, each covering `context_window` consecutive turn-pairs; adjacent windows overlap by `context_window - 1` pairs.

**Relationship to `extract_conversation_turns()`:** This function is the DB query path; `extract_conversation_turns()` in `user_messages.py` calls this function first (DB-first, `reader="auto"` mode) and falls back to `_extract_turn_pairs()` (JSONL parsing) when the DB is unavailable or returns no results. The temporal adjacency algorithm is identical in both paths; only the data source differs (SQLite vs. JSONL log files).

**Used by:** `extract_conversation_turns()` in `user_messages.py`, which is called by `ll-messages --sft-format` to extract training examples from either the session DB or raw JSONL logs.

### condensed_nodes_for_issue

```python
def condensed_nodes_for_issue(
    issue_id: str,
    *,
    limit: int = 3,
    node_char_cap: int = 500,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[SummaryNode]
```

Return level-0 condensed `summary_nodes` for an issue's sessions (ENH-2231).

Joins the `issue_sessions` VIEW to `summary_nodes` filtering for `kind='condensed'` and `level=0` (per-session condensed nodes, one per session). Returns nodes newest-first, limited to `limit`. Each node's `content` is truncated to `node_char_cap` characters before returning.

**Parameters:**
- `issue_id` — the issue identifier (e.g., `"ENH-2231"`)
- `limit` — maximum number of condensed nodes to return (default: 3)
- `node_char_cap` — maximum characters per node's `content` field (default: 500)
- `db` — path to the SQLite database (default: `.ll/history.db`)

**Returns:** List of `SummaryNode` objects (newest first). Returns `[]` when the DB is absent, the issue has no recorded sessions, no condensed nodes have been generated (requires `history.compaction.enabled: true`), or any query raises a SQL error.

**Integration:** Called by `ll-history-context <issue_id>` when `history.compaction.enabled` is `true` to inject a `## Prior Work (condensed)` section. Output is byte-identical when compaction is disabled or no level-0 nodes exist for the issue's sessions. See ENH-2231 and `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` for the DAG architecture.

**FEAT-2598 note:** for sessions that cross the 7,500-token soft threshold, `session_store._maybe_soft_threshold_summary()` may rewrite this same row's `content` into the 6-section cookbook schema (User Intent / Completed Work / Errors & Corrections / Active Work / Pending Tasks / Key References) — the row's `kind`/`level`/identity are unchanged, so this function's query and truncation behavior are unaffected.

### HarnessEvent / recent_harness_events / harness_eval_pass_rate

```python
@dataclass
class HarnessEvent:
    ts: str
    runner: str | None
    target: str | None
    exit_code: int | None
    semantic_verdict: str | None
    semantic_passed: int | None
    timed_out: int | None
    duration_ms: int | None
    head_sha: str | None
    branch: str | None
    parent_id: int | None
    semantic_prompt: str | None
    semantic_confidence: float | None
    semantic_reason: str | None
    semantic_evidence: str | None
    semantic_model: str | None
```

```python
def recent_harness_events(
    *,
    runner: str | None = None,
    target: str | None = None,
    since: str | None = None,
    limit: int = 50,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[HarnessEvent]

def harness_eval_pass_rate(
    target: str,
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> float | None
```

Read-side API for `harness_events` rows (ENH-2739's schema, written by `record_harness_event()`) — one row per `ll-harness` / eval run outcome. `recent_harness_events()` returns rows newest first, optionally filtered by exact `runner`/`target` and/or a `since` lower bound on `ts`; returns `[]` on a missing/unreadable DB. `harness_eval_pass_rate()` rolls up the `semantic_passed` tri-state column into a pass fraction for *target*, ignoring `semantic_passed IS NULL` rows (abstentions); `ll-harness` sets `semantic_passed` on every non-abstained run regardless of whether `--semantic` was supplied, so the denominator is *all non-abstained runs* for *target*, not only the `check_semantic`-judged ones. Returns `None` when there are zero scored rows. Named `harness_eval_pass_rate` (not `harness_pass_rate`) to avoid colliding with the unrelated `ab_writer.ABResults.harness_pass_rate` (an in-memory A/B-comparator field). `harness_eval_abstention_rate()` is its sibling (ENH-3185): same `target`/`since`/`db` signature, returns `{"abstentions": int, "scored": int, "abstention_rate": float} | None`, where `scored` here counts every semantically-judged row (pass+fail+abstain) — a deliberately different, and generally smaller, population than `harness_eval_pass_rate()`'s `scored`.

**CLI:** `ll-session recent --kind harness` and `ll-session search --fts "<target>" --kind harness` work automatically via the generic `VALID_KINDS`/`_KIND_TABLE` dispatch (ENH-2739) — no CLI code change was needed for this read API. `ll-harness` itself is a consumer of both rollups (ENH-3223): `_evaluate_and_report()` folds the run's target's historical pass/abstention rate (target-scoped, 30-day window, suppressed below 3 scored runs) into its `--output json` payload and text report — see [CLI Reference → `ll-harness`](CLI.md#ll-harness).

### VerdictEvent / recent_verdict_events / verdict_pass_rate

```python
@dataclass
class VerdictEvent:
    ts: str
    session_id: str | None
    verdict_kind: str
    target_kind: str | None
    target_id: str | None
    verdict: str
    severity_counts: str | None
    findings_count: int | None
    confidence: int | None
    head_sha: str | None
    branch: str | None
```

```python
def recent_verdict_events(
    *,
    verdict_kind: str | None = None,
    target_id: str | None = None,
    since: str | None = None,
    limit: int = 50,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[VerdictEvent]

def verdict_pass_rate(
    *,
    verdict_kind: str | None = None,
    target_id: str | None = None,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]
```

Read-side API for `verdict_events` rows (ENH-2504's schema, written by `record_verdict_event()`) — one row per invocation of the nine `ll-action`-bridged verifiers (`ready-issue`, `confidence-check`, `go-no-go`, `tradeoff-review-issues`, `refine-issue`, `format-issue`, `verify-issues`, `prioritize-issues`, `align-issues`). `recent_verdict_events()` returns rows newest first, optionally filtered by exact `verdict_kind`/`target_id` and/or a `since` lower bound on `ts`; returns `[]` on a missing/unreadable DB. `verdict_pass_rate()` groups by `verdict_kind` and returns `{verdict_kind, invocations, successes, cannot_judge_count, success_rate}` dicts (mirroring `summarize_skills()`'s `success_rate` field shape) — `successes` counts `verdict IN ('pass', 'implement')`, and `cannot_judge_count` (ENH-230) reports abstention volume separately so it is not read as a failure. `success_rate` keeps its existing denominator (`invocations`). `check_high_confidence_abstention()` returns `cannot_judge` rows whose `confidence` crosses a threshold (default 90) and logs a warning per row — a producer that is confident enough to score high should have been able to render a verdict.

**CLI:** `ll-session recent --kind verdict` and `ll-session search --fts "<target_id>" --kind verdict` work automatically via the generic `VALID_KINDS`/`_KIND_TABLE` dispatch — no CLI code change was needed for this read API.

### ReviewEvent / recent_review_events / review_velocity

```python
@dataclass
class ReviewEvent:
    ts: str
    session_id: str | None
    reviewer_skill: str
    target_kind: str | None
    target_id: str | None
    severity_counts: str | None
    findings_count: int | None
    findings_json_summary: str | None
    verdict: str | None
    head_sha: str | None
    branch: str | None
```

```python
def recent_review_events(
    *,
    reviewer_skill: str | None = None,
    target_id: str | None = None,
    since: str | None = None,
    limit: int = 50,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[ReviewEvent]

def review_velocity(
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]
```

Read-side API for `review_events` rows (ENH-2512's schema, written by `record_review_event()`) — one row per invocation of the seven `ll-action`-bridged audits/reviews (`review-epic`, `review-loop`, `audit-architecture`, `audit-claude-config`, `audit-docs`, `audit-loop-run`, `review-sprint`). `recent_review_events()` returns rows newest first, optionally filtered by exact `reviewer_skill`/`target_id` and/or a `since` lower bound on `ts`; returns `[]` on a missing/unreadable DB. `review_velocity()` buckets rows by ISO week and sums each `severity_counts` bucket (`p0`/`p1`/`p2`/`info`), returning `{week, reviews, p0, p1, p2, info}` dicts sorted by week ascending — the velocity-tracking rollup ("how many P0 findings this week").

### AdvisorConsultRow / query_advisor_consults / ConsultStats / consult_stats

```python
@dataclass
class AdvisorConsultRow:
    ts: str
    session_id: str | None
    task_key: str | None
    signal: str | None
    advisor_host: str | None
    advisor_model: str | None
    main_model: str | None
    floor_status: str | None
    outcome: str
    latency_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    confidence: float | None
    verdict_body: str | None
```

```python
def query_advisor_consults(
    db_path: Path | str = DEFAULT_DB_PATH,
    *,
    since: str | None = None,
    limit: int = 500,
) -> list[AdvisorConsultRow]

@dataclass
class ConsultStats:
    by_signal: dict[str, int]
    total: int
    total_tokens: int
    skipped: int

def consult_stats(
    db_path: Path | str = DEFAULT_DB_PATH,
    *,
    days: int = 30,
) -> ConsultStats
```

Read-side API for `advisor_consults` rows (FEAT-3300's schema, written by `write_advisor_consult()`) — one row per `consult_for_trigger()` invocation (`advisor.py`), covering issued consults and every `skipped_reason` (`disabled`, `trigger_not_allowed`, `budget_exhausted`, `not_configured`, `floor_violation`, `failed`, `timeout`). `query_advisor_consults()` returns rows newest first, optionally filtered by a `since` lower bound on `ts`; returns `[]` on a missing/unreadable DB. `consult_stats()` aggregates counts by `signal` and sums token usage over the trailing *days* window, returning an all-zero `ConsultStats` on a missing/unreadable DB or empty table. Token columns stay `NULL` until a host surfaces usage; `verdict_body` is `NULL` unless `advisor.store_verdict_body` was set at write time. This is the standalone, independently-testable persistence half of FEAT-3040 — no `ll-ctx-stats` report section ships with it, matching the `harness_events`/`verdict_events`/`review_events` precedent.

**CLI:** `ll-session recent --kind advisor_consult` and `ll-session search --fts "<task_key>" --kind advisor_consult` work automatically via the generic `VALID_KINDS`/`_KIND_TABLE` dispatch — no CLI code change was needed for this read API.

**CLI:** `ll-session recent --kind review` and `ll-session search --fts "<target_id>" --kind review` work automatically via the generic `VALID_KINDS`/`_KIND_TABLE` dispatch — no CLI code change was needed for this read API.

### ContextPressureEvent / context_pressure_curve / pressure_crossings / pressure_summary

```python
@dataclass
class ContextPressureEvent:
    ts: str
    session_id: str | None
    used_pct: float | None
    used_tokens_est: int | None
    threshold_crossed: int | None
    crossed_level: str | None
    head_sha: str | None
    branch: str | None
```

```python
def context_pressure_curve(
    session_id: str,
    *,
    limit: int = 500,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[ContextPressureEvent]

def pressure_crossings(
    session_id: str,
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[ContextPressureEvent]

def pressure_summary(
    session_id: str,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> dict | None
```

Read-side API for `context_pressure_events` rows (ENH-2507's schema, written by `record_context_pressure_event()`) — one row per sampled `PostToolUse` context-window pressure measurement. `context_pressure_curve()` returns a session's samples oldest first (for charting); `pressure_crossings()` filters to rows where `threshold_crossed=1`, optionally since a timestamp; `pressure_summary()` returns `{session_id, samples, peak_pct, avg_pct, peak_tokens_est}` or `None` when the session has no rows. All three return `[]`/`None` on a missing/unreadable database.

**CLI:** `ll-session recent --kind context_pressure` and `ll-session search --fts "<session_id>" --kind context_pressure` work automatically via the generic `VALID_KINDS`/`_KIND_TABLE` dispatch. `ll-ctx-stats` additionally renders an aggregate "Context pressure curve" block (peak/avg pct and level-crossing counts across all sessions) via `cli/ctx_stats.py::_aggregate_context_pressure()`.

## little_loops.prepatch_check

Pre-patch check core (ENH-3142): identifies candidate tests from a step diff, runs them against the pre-patch worktree ENH-3141's `setup_prepatch_worktree()` produces, and returns a `PrePatchEvidence` bundle. Deterministic only — no LLM calls, no FSM/CLI-orchestrator knowledge, no database access; `base_sha`/`base_dirty` arrive as caller-supplied arguments (see `history_reader.read_base_sha()` / `read_base_dirty()` above).

```python
def run_prepatch_check(
    *,
    step_diff: str,
    repo_root: Path,
    worktree_base: str | Path,
    base_sha: str | None,
    base_dirty: bool | None,
    base_branch: str,
    logger: Logger,
    git_lock: GitLock,
    config: BRConfig | None = None,
) -> PrePatchEvidence

def collect_candidates(
    step_diff: str,
    repo_root: Path,
    base_ref: str,
    config: BRConfig | None = None,
) -> list[PrePatchCandidate]
```

`run_prepatch_check()` resolves the base ref itself — the dequeue-time SHA when `base_sha` is given, else a `git merge-base` with `base_branch` — then, when `config.prepatch_check.enabled` is true and at least one candidate is identified, materializes the post-patch (working-tree) content of every touched test file (including a touched `conftest.py`, for fixture-added-in-conftest coverage) into the pre-patch worktree, runs the candidate node IDs under `pytest --junit-xml=...` with `<worktree>/<src_dir>` prepended to `PYTHONPATH` (so an editable install can't resolve `little_loops` back to the post-patch main tree), retries only the node IDs that passed, and assigns each outcome a `flag`.

`collect_candidates()` attributes hunks to top-level `test*` functions via `test_tamper_guard.extract_test_functions()` (post-patch) and `read_paths_at_ref()` (pre-patch), splitting `set(after) - set(before)` into added vs. modified. When a touched line falls outside every top-level test function's range (class-based tests, module-level edits), attribution is ambiguous and the whole file becomes one file-fallback candidate — the file path itself, never an enumerated node-ID set and never the full suite.

Flag policy: a newly added test that passes pre-patch is `hard`-flagged; a modified test that passes is `soft` by default (escalates to `hard` when `config.prepatch_check.modified_hard` is true); a pass not confirmed on retry is `flaky` + `soft`; any `hard` flag is downgraded to `soft` when `base_dirty` is true (the worktree is missing the caller's uncommitted work, so a pre-patch failure there is not trustworthy evidence). `PrePatchEvidence.verdict` is `flagged` when any outcome is `hard`, `skipped` when the check is disabled or zero candidates were found, else `clean`.

### PrePatchCandidate / PrePatchTestOutcome / PrePatchEvidence

Plain `@dataclass`es (no instance state, no methods beyond `to_dict()`), following the `Gap`/`GapAnalysis` convention. `PrePatchCandidate` — `nodeid`, `file`, `added`, `attribution` (`"function"` | `"file-fallback"`). `PrePatchTestOutcome` — `nodeid`, `file`, `added`, `category` (`pass | fail | error | timeout | flaky`), `error_kind` (`"collection" | "infrastructure" | None`), `flag` (`hard | soft | none`), `flag_reason`. `PrePatchEvidence` — `base_ref`, `base_source` (`"dequeue-stamp" | "merge-base"`), `base_dirty`, `outcomes: list[PrePatchTestOutcome]`, `verdict` (`clean | flagged | skipped`), `skipped_reason`.

## little_loops.compaction

Session-memory compaction: StreamingLLM eviction + 6-section schema (FEAT-2598). Extends the LCM compaction surface in `session_store` with two complementary passes: instant structural eviction (no LLM cost, always-on) and 6-section semantic summarization (gated on `history.compaction.enabled`, fires in a background thread at the soft token threshold).

### evict_sink_and_window

```python
def evict_sink_and_window(
    messages: list[dict],
    sink_n: int = 4,
    window_n: int = 20,
) -> list[dict]
```

StreamingLLM-style eviction: keeps the first `sink_n` + last `window_n` messages, dropping the middle. Operates at message granularity (not token/KV-cache granularity). `system`-role messages (system prompt / CLAUDE.md blocks) are preserved unconditionally and excluded from the sink/window accounting. Returns the original list unchanged when there is nothing to prune.

### is_valid_cutoff / compute_goal_tokens / select_sliding_window

```python
def is_valid_cutoff(messages: list[dict], index: int) -> bool
def compute_goal_tokens(model: str | None = None, sliding_window_percentage: float = 0.3, override: int | None = None) -> int
def select_sliding_window(messages: list[dict], model: str | None = None, sliding_window_percentage: float = 0.3, override: int | None = None) -> list[dict]
```

Letta-style sliding-window selection. `compute_goal_tokens` implements `goal_tokens = (1 - sliding_window_percentage) * context_window` using `context_window.context_window_for()`. `select_sliding_window` selects the most recent messages fitting within that budget (inflated by `APPROX_TOKEN_SAFETY_MARGIN = 1.3`, the project's byte/4 token-estimate heuristic), snapped to a valid cutoff via `is_valid_cutoff` (a user-turn boundary, avoiding a split mid assistant/tool-call sequence).

### summarize_6_section

```python
def summarize_6_section(
    messages: list[str] | list[dict],
    *,
    model: str | None = None,
    timeout: int = 60,
) -> str
```

Produces a 6-section cookbook-style summary (User Intent / Completed Work / Errors & Corrections / Active Work / Pending Tasks / Key References) via `session_store._call_llm_for_summary` (same sanctioned host-CLI abstraction `_summarize_block` uses). Falls back to a deterministic empty-section skeleton if the LLM call fails, so a well-shaped summary is always produced.

### CompactResult / compact_result_for_session

```python
@dataclass
class CompactResult:
    summary_message: str | None
    compacted_messages: list[int] = field(default_factory=list)
    summary_text: str | None = None
    context_token_estimate: int = 0

def compact_result_for_session(session_id: str, db: Path | str) -> CompactResult | None
```

`CompactResult` is a thin dataclass wrapper over existing `summary_nodes`/`summary_spans` rows — no schema change. `compact_result_for_session` returns `None` when the session has no per-session condensed node (`kind='condensed'`, `level=0`) yet.

**CLI:** `ll-compact-session SESSION_ID [--db PATH] [--json]` manually triggers `session_store.compact_session()` for one session and prints the resulting `CompactResult`. Distinct from `ll-session compact`, which sweeps the separate *retention* axis (`kind='retention'` `raw_events` summarization, ENH-1906/ENH-2581).

### issue_effort

```python
def issue_effort(
    issue_id: str,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> dict | None
```

Return per-issue effort: session count and cycle time (ENH-1905).

**Parameters:**
- `issue_id` — the issue identifier (e.g., `"ENH-1905"`)
- `db` — path to the SQLite database (default: `.ll/history.db`)

**Returns:** `{"session_count": int, "cycle_time_days": float | None}` or `None` when the DB is absent or the issue has no recorded sessions. Uses a direct aggregate query over `issue_sessions` (no LIMIT cap) for accurate `cycle_time_days` across many sessions.

### recent_issue_velocity

```python
def recent_issue_velocity(
    limit: int = 10,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]
```

Return effort data for recently completed issues (ENH-1905).

**Parameters:**
- `limit` — maximum number of recently completed issues to include (default: 10, configurable via `history.velocity_window`)
- `db` — path to the SQLite database (default: `.ll/history.db`)

**Returns:** List of `{"issue_id": str, "session_count": int, "cycle_time_days": float | None}` dicts ordered by `completed_at DESC`. Returns `[]` when the DB is absent or no completed issues exist.

### SectionProvider

Config-addressable digest section with query and render logic (ENH-1907). The three v1 providers (`touched_files`, `completed_issues`, `recurring_corrections`) are registered in `SECTION_PROVIDERS`.

```python
@dataclass(frozen=True)
class SectionProvider:
    name: str           # config-addressable key (e.g. "touched_files")
    query: Callable     # (conn, *, cutoff: str, cap: int) -> list
    default_cap: int    # max rows returned by this provider
    render: Callable    # (rows: list) -> list[str]  markdown lines
```

### ProjectDigest

Aggregated project-context snapshot from `history.db` (ENH-1907).

```python
@dataclass
class ProjectDigest:
    sections: list[tuple[str, list[str]]]  # [(name, markdown_lines), ...]
    days: int = 7

    @property
    def empty(self) -> bool: ...
```

### SECTION_PROVIDERS

Registry of v1 section providers. Keys: `"touched_files"`, `"completed_issues"`, `"recurring_corrections"`. Future providers (effort/velocity, evolution triggers) register here without requiring a formatter rewrite.

```python
SECTION_PROVIDERS: dict[str, SectionProvider]
```

### project_digest

```python
def project_digest(
    db_path: Path,
    *,
    days: int = 7,
    sections: list[str] | None = None,
) -> ProjectDigest
```

Aggregate a project-wide context snapshot from `history.db`. Returns a `ProjectDigest` with `.empty == True` on missing/empty/stale DB. `sections=None` or `sections=[]` renders all registered providers in registry order; a non-empty list restricts and orders the output. Degrades gracefully — never raises.

### render_project_context

```python
def render_project_context(
    digest: ProjectDigest,
    *,
    char_cap: int = 1200,
    days: int | None = None,
) -> str
```

Render a `<project_context>` block from *digest*, capped at *char_cap* chars. Returns `""` when the digest is empty. Truncates with a `+N more` tail when content would exceed *char_cap*.

---

## little_loops.compression

In-house, zero-dependency heuristic prompt compressor (FEAT-2675, EPIC-2456 Tier 3). Three extractive passes over a `list[dict]` (`role`/`content`) message list plus a `compress()` entry point gated on a window-relative trigger, and a `compress_action_text()` string adapter used by `FSMExecutor._run_action()`. Token estimates use the project's `len(text) // 4` convention (no BPE tokenizer). The LLMLingua-gated benchmark comparator is FEAT-2676.

### drop_stale_tool_results / dedupe_stable_system_blocks / tail_truncate_assistant_turns

```python
def drop_stale_tool_results(messages: list[dict], max_age_turns: int = 5) -> list[dict]
def dedupe_stable_system_blocks(messages: list[dict]) -> tuple[list[dict], list[int]]
def tail_truncate_assistant_turns(messages: list[dict], max_n: int = 8) -> list[dict]
```

The three passes. `drop_stale_tool_results` drops `role=="tool"` messages older than `max_age_turns` user turns (measured from the last user turn), preserving `system` rows unconditionally. `dedupe_stable_system_blocks` keeps the first occurrence of each unique `system` block and returns `(deduped, cache_control_candidates)` where the second element lists output-list indices of surviving repeated blocks — flagged for the future F1 `cache_control` child; no marking happens here. `tail_truncate_assistant_turns` keeps only the most recent `max_n` `assistant` messages, leaving other roles untouched.

### compress / CompressedResult

```python
@dataclass
class CompressedResult:
    messages: list[dict]
    original_tokens: int
    compressed_tokens: int
    cache_control_candidates: list[int] = field(default_factory=list)
    triggered: bool = False
    @property
    def reduction_ratio(self) -> float: ...

def compress(
    messages: list[dict],
    context_window: int | None = None,
    trigger_pct: float = 0.4,
    trigger_tokens: int | None = None,
    max_tool_result_age_turns: int = 5,
    max_assistant_tail_turns: int = 8,
) -> CompressedResult
```

Runs the three passes in order behind an effective trigger: the lower of `trigger_pct * context_window` (when the window is known) and `trigger_tokens` (when set). Below the trigger, returns the messages unchanged with `triggered=False`. When neither trigger applies (both `None`), the passes always run — the mode the locked-trace reduction measurement relies on.

### compress_action_text

```python
def compress_action_text(text: str, *, model: str | None = None, context_window: int | None = None,
                         trigger_pct: float = 0.4, trigger_tokens: int | None = None,
                         max_tool_result_age_turns: int = 5, max_assistant_tail_turns: int = 8) -> str
```

Executor string adapter. Resolves the context window from `model` via `context_window.context_window_for()` when not given. Below the trigger, or when `text` is not a JSON message list, returns `text` **byte-identical**; above the trigger it compresses the parsed message list and re-serializes. This keeps arbitrary prose prompts unmodified while compressing the motivating case — loops re-embedding captured message-list JSON.

---

## little_loops.cache_marking_oracle

Cache-marking cost oracle (FEAT-2673, EPIC-2456 F1 — Goal #3). Decides which stable prompt blocks (system / tool / stable-skill) are safe to mark with `cache_control: {"type": "ephemeral", ...}` without risking the unamortized 1.25x write premium (Anthropic prompt caching: writes cost 1.25x, reads cost 0.1x — marking a block that's never reused is a pure 1.25x loss). Two independent gates must both pass: (1) a per-model **cacheable-prefix minimum** (1024 tokens for Sonnet, 4096 for Opus; unknown models fall back to the conservative Opus floor), and (2) a **reuse-stability signal** from `little_loops.prompts.fragment_store.FragmentStore` (FEAT-2671) — a block is only marked once its content-hash key has already been observed at least once, so the oracle never pays the write premium on a fragment that's never reused. `require_repeat=False` disables gate 2 for callers with a stronger external stability signal.

```python
from little_loops.cache_marking_oracle import (
    CacheMarkingDecision,       # frozen dataclass: should_mark: bool, reason: str
    CACHEABLE_PREFIX_MINIMUMS,  # {"sonnet": 1024, "opus": 4096}
    decide_cache_marking,
)

def decide_cache_marking(
    *,
    block_text: str,
    fragment_key: str,
    fragment_store: FragmentStore,
    model: str = "sonnet",
    require_repeat: bool = True,
) -> CacheMarkingDecision: ...
```

`fragment_store` is consulted read-only via `.get()` — it does not record an observation; callers own the `put()` lifecycle. Token estimation uses the project-wide `len(text) // 4` convention (no BPE tokenizer in the codebase). Never raises.

---

## little_loops.prompts

Content-hash fragment store (FEAT-2671, EPIC-2456 F1-prereq a). Computes a stable SHA-256 key over the three stable prompt fragments — skill body, system prompt, and tool definitions — and tracks whether each observed key repeats a prior invocation. Wired read-only into `FSMExecutor._run_action()` (prompt-mode actions only, measured on the pre-interpolation `action_template` plus `state.agent`/`state.tools`), so it never changes the emitted action. Gives the F1 cache-marking oracle (FEAT-2673) a cheap, deterministic stability signal: a hit means the fragment triple was byte-identical to an earlier call, so marking it `cache_control: ephemeral` would amortize real reads instead of paying an unamortized 1.25x write premium.

```python
from little_loops.prompts import FragmentStore, fragment_key

def fragment_key(skill_body: str, system_prompt: str | None, tool_definitions: list[str] | None) -> str

class FragmentStore:
    hits: int
    misses: int
    def get(self, key: str) -> bool: ...     # True if key was observed before
    def put(self, key: str) -> bool: ...     # records the observation; returns True on a repeat (hit)
    @property
    def hit_rate_pct(self) -> float: ...
```

`fragment_key()` hashes `json.dumps({"skill_body": ..., "system_prompt": ..., "tool_definitions": ...}, sort_keys=True, default=str)` via SHA-256, returning the full 64-char hex digest (unlike `session_store._hash_args()`'s `[:16]` truncation — this is a stability/equality signal, not a storage key needing brevity). `FragmentStore` is a small in-memory `get`/`put` store with a hit counter; `put()` is a miss the first time a key is seen and a hit on every repeat.

---

## little_loops.session_store

Unified SQLite session store for `.ll/history.db`. Current schema version: **45**. All write-side helpers degrade gracefully and are safe to call on every session start via `ensure_db()`. The DB path resolves through a single precedence chain (ENH-2623): the `LL_HISTORY_DB` env var, then the `history.db_path` config key, then the default `.ll/history.db` — applied to default-shaped paths only; a deliberate explicit path is honored verbatim.

```python
from little_loops.session_store import (
    SCHEMA_VERSION,        # 45
    VALID_KINDS,           # tuple of valid recent()/search --kind values — single source (ENH-2581)
    ensure_db,             # create/migrate the DB
    connect,               # open a write-capable connection
    record_correction,     # write a user_corrections row
    record_skill_event,    # write a skill_events row (dispatch-time; completion columns NULL)
    skill_event_context,   # ctx manager: INSERT on enter, UPDATE exit_code/success/duration_ms on exit (ENH-2460)
    record_commit_event,   # write a commit_events row; issue_id inferred from message/branch (ENH-2458)
    record_test_run_event, # write a test_run_events row (ENH-2459)
    record_orchestration_run, # UPSERT one per-issue batch outcome (ENH-2492)
    record_loop_run_summary, # write a loop_runs row (ENH-2463)
    update_loop_run_diagnostics, # link a diagnostics artifact to its loop_runs row (ENH-2463)
    record_learning_test_event, # UPSERT one learning_test_events row (ENH-2466)
    record_issue_event,    # write an issue_events row; direct-call sibling of record_issue_snapshot, used by `ll-issues set-status` (BUG-2770); logs a warning instead of silently discarding on a cross-issue `(issue_num, transition)` dedup collision (BUG-3006)
    record_session_lifecycle_event, # write a session_lifecycle_events row (ENH-2495)
    record_subagent_run_start, # write a running subagent_runs row from SubagentStart (ENH-2505)
    record_subagent_run_stop, # UPDATE ended_at/status/agent_transcript_path from SubagentStop (ENH-2505)
    record_hook_event,     # write a hook_events row (ENH-2506)
    hook_event_context,    # ctx manager: measures duration, records exit_code/stderr_preview on exit (ENH-2506)
    record_harness_event,  # write a harness_events row (ENH-2739)
    record_prompt_opt_event, # write a prompt_opt_events row (ENH-2498)
    record_verdict_event,  # write a verdict_events row (ENH-2504)
    record_context_pressure_event, # write a context_pressure_events row (ENH-2507)
    record_review_event,   # write a review_events row (ENH-2512)
    write_advisor_consult, # write an advisor_consults row (FEAT-3300)
    record_retirement,     # mark a correction cluster as addressed (ENH-2046)
    list_retirements,      # return all correction_retirements rows (ENH-2046)
    backfill_raw_events,   # ingest JSONL lines into raw_events only (ENH-2581)
    rebuild,               # wipe+re-derive the JSONL-derived cache tables from raw_events (ENH-2581)
    compact,               # sweep old raw_events into retention summary_nodes (ENH-2581)
    prune,                 # delete compacted raw_events rows and VACUUM (ENH-2581)
)
```

### raw_events / rebuild / compact (ENH-2581)

`raw_events` is the source of truth for the JSONL-derived cache tables (`tool_events`, `message_events`, `assistant_messages`, `skill_events`, `sessions`): one row per JSONL line, storing both the verbatim `raw_line` and its parsed fields (`ts`, `session_id`, `host`, `source_path`, `line_no`, `event_type`). `backfill()`/`backfill_incremental()` now ingest into `raw_events` only — pass `also_rebuild=True` to also materialize the cache tables in the same call.

```python
def _iter_events(source: list[Path] | sqlite3.Cursor) -> Generator[tuple[str, str], None, None]
```

Dispatch helper letting the JSONL-derived `_backfill_*` functions (`_backfill_sessions`, `_backfill_tool_events`, `_backfill_usage_events`, `_backfill_messages`, `_backfill_assistant_messages`, `_backfill_skill_events`) accept either a legacy `list[Path]` (re-reads files line-by-line) or a `raw_events` cursor selecting `(raw_line, source_path)` — the mechanism `rebuild()` uses to replay previously-ingested lines without touching the filesystem.

```python
def rebuild(
    db: Path | str = DEFAULT_DB_PATH,
    *,
    config: dict | None = None,
    max_sessions: int | None = None,
) -> dict[str, int]
```

Wipes `tool_events`, `message_events`, `assistant_messages`, `skill_events`, `sessions`, `user_corrections`, `summary_nodes`, `summary_spans`, and the `search_index` rows for `kind in ('tool', 'message', 'skill', 'correction')`, then re-derives them by replaying every `raw_events` row through `_iter_events()`. Idempotent. Updates the `last_rebuild_version` meta key to `SCHEMA_VERSION`. Issue/loop/commit/cli/file/test_run/orchestration tables are outside `raw_events`'s scope and are left untouched — no re-derivation path exists for them.

```python
def compact(
    db: Path | str = DEFAULT_DB_PATH,
    *,
    config: dict | None = None,
    and_prune: bool = False,
) -> dict[str, int]
```

Sweeps `raw_events` rows older than `analytics.retention.raw_event_max_age_days` (default 90) that aren't yet `compacted`, groups them by `session_id`, and inserts one `kind='retention'` `summary_nodes` row per session — a deterministic one-liner (no host-CLI call), distinct from the LLM-backed `history.compaction` feature's `kind='condensed'` nodes so the two features' dedup indexes never collide. Marks the swept rows `compacted=1` with `summary_node_id` set. `and_prune=True` also calls `prune()` afterward.

`prune()` now deletes only `raw_events` rows already marked `compacted=1` past the cutoff (previously it deleted directly from `tool_events`/`cli_events`/`file_events`/`message_events` and never touched `search_index`, leaving stale FTS rows behind a since-deleted event — the "FTS5 leak"). Because `rebuild()` always wipes+re-populates `search_index` from current cache-table state, running `rebuild()` after a `prune()` brings FTS row counts back in sync.

### skill_event_context

```python
@contextmanager
def skill_event_context(
    db_path: Path | str = DEFAULT_DB_PATH,
    session_id: str | None = None,
    skill_name: str = "",
    args: str = "",
    config: dict | None = None,
) -> Generator[SkillEventCompletion, None, None]
```

Skill-host analogue of `cli_event_context()` (ENH-2460): inserts a `skill_events` row on enter and updates `exit_code`, `success`, and `duration_ms` on exit. Yields a mutable `SkillEventCompletion` handle — hosts that observe a concrete process exit code (e.g. `ll-action invoke`) set `completion.exit_code` before the block exits; otherwise a clean exit records `exit_code=0, success=1` and a raise records `exit_code=1, success=0`. Best-effort per the EPIC-1707 contract: a missing/locked database never blocks the wrapped skill body.

### hook_event_context

```python
@contextmanager
def hook_event_context(
    db_path: Path | str = DEFAULT_DB_PATH,
    session_id: str | None = None,
    event_name: str = "",
    matcher: str | None = None,
    script: str | None = None,
    config: dict | None = None,
) -> Generator[HookEventCompletion, None, None]
```

Hook-fire analogue of `skill_event_context()` (ENH-2506): measures elapsed time with `time.monotonic()` and writes one `hook_events` row on exit via `record_hook_event()` — `exit_code`, `duration_ms`, `stderr_preview`. Yields a mutable `HookEventCompletion` handle; a clean exit records `exit_code=0`, a raise records `exit_code=1` (and re-raises — this wrap never alters the wrapped hook's exit code or exception propagation), and a caller that observes the paired handler's own `LLHookResult.exit_code` (e.g. `main_hooks()`) sets `completion.exit_code` explicitly before the block exits. Best-effort per the EPIC-1707 contract. `main_hooks()` (`hooks/__init__.py`) wraps every Python-dispatched intent with this single context manager around the `handler(event)` call, gated on `analytics.enabled` + `analytics.capture.hooks`; `Stop`/`SessionEnd` (bash-only, never routed through `main_hooks()`) are instead covered by the `hooks/scripts/record-hook-event.sh` shim, which calls `ll-session record-hook-event` directly.

### record_hook_event

```python
def record_hook_event(
    db_path: Path | str,
    *,
    ts: str | None = None,
    session_id: str | None,
    event_name: str,
    matcher: str | None,
    script: str | None,
    exit_code: int | None,
    duration_ms: int | None,
    stderr_preview: str | None = None,
    head_sha: str | None = None,
    branch: str | None = None,
) -> None
```

Write one `hook_events` row and index it in `search_index` with `kind="hook_event"` (ENH-2506). `stderr_preview` is truncated to 512 bytes. Best-effort: a missing/locked database logs and returns rather than raising. Live-write-only — no `_backfill_hook_events` exists, since the Claude Code host does not emit hook execution results into the transcript JSONL.

### record_harness_event

```python
def record_harness_event(
    db_path: Path | str,
    *,
    ts: str,
    runner: str | None = None,
    target: str | None = None,
    exit_code: int | None = None,
    semantic_verdict: str | None = None,
    semantic_passed: bool | None = None,
    timed_out: bool | None = None,
    duration_ms: int | None = None,
    head_sha: str | None = None,
    branch: str | None = None,
    parent_id: int | None = None,
    semantic_prompt: str | None = None,
    semantic_confidence: float | None = None,
    semantic_reason: str | None = None,
    semantic_evidence: str | None = None,
    semantic_model: str | None = None,
) -> None
```

Write one `harness_events` row and index it in `search_index` with `kind="harness"` (ENH-2739). `parent_id` links DSL per-task rows to their parent harness run (ENH-2740). Mirrors `record_test_run_event()`'s contract, not `record_hook_event()`'s: raises on failure — callers are responsible for `contextlib.suppress(Exception)` if a failed write should not abort the run. Live-write-only — nothing calls this yet (ENH-2740 wires the `ll-harness` producer); no `_backfill_harness_events` exists.

### record_prompt_opt_event

```python
def record_prompt_opt_event(
    db_path: Path | str,
    *,
    session_id: str | None,
    offered: bool,
    mode: str | None = None,
    bypass_reason: str | None = None,
    raw_len: int | None = None,
    ts: str | None = None,
) -> None
```

Write one `prompt_opt_events` row and index it in `search_index` with `kind="prompt_opt"` (ENH-2498). Called from `user_prompt_submit.py::handle()` at every return point once config is loaded (gated on `analytics.enabled`), one row per prompt: `offered=True` when the optimization template rendered, `offered=False` with the matching `bypass_reason` (`disabled`, `prefix`, `slash`, `hash`, `question`, `short`, `no_template`, `template_error`) otherwise. The empty-prompt and no-config early returns write no row — analytics can't be gated before config loads. Mirrors `record_correction()`'s contract: raises on failure; the caller wraps the call in `contextlib.suppress(Exception)` so a DB failure never changes the hook's stdout/exit. `optimized_len`/`optimized_text`/`accepted` start `NULL` and are filled in later, in place, by `_backfill_prompt_opt()`.

### record_verdict_event

```python
def record_verdict_event(
    db_path: Path | str,
    *,
    ts: str,
    session_id: str | None,
    verdict_kind: str,
    target_kind: str | None = None,
    target_id: str | None = None,
    verdict: str,
    severity_counts: dict | None = None,
    findings_count: int | None = None,
    confidence: int | None = None,
    abstention_reason: str | None = None,
    head_sha: str | None = None,
    branch: str | None = None,
) -> None
```

Write one `verdict_events` row and index it in `search_index` with `kind="verdict"` (ENH-2504). Called from `cli/action.py::cmd_invoke()` for the nine skill-bridged verifiers, wrapped in `contextlib.suppress(Exception)` so a DB failure never changes a verifier's exit code. `severity_counts` is JSON-serialized on write (`json.dumps`), parsed back on read. `abstention_reason` (ENH-230) is the closed four-tag enum (`missing_artifacts`, `unparseable_criteria`, `evaluation_context_unavailable`, `circular_dependencies`) and MUST be supplied when `verdict` is `cannot_judge` and omitted otherwise — the v44 schema CHECK enforces the pairing, so a mismatch raises `sqlite3.IntegrityError` from the INSERT. Mirrors `record_harness_event()`'s contract: raises on failure — the call site, not the producer, enforces best-effort.

### record_context_pressure_event

```python
def record_context_pressure_event(
    db_path: Path | str,
    *,
    session_id: str | None,
    used_pct: float | None,
    used_tokens_est: int | None,
    threshold_crossed: bool = False,
    crossed_level: str | None = None,
    head_sha: str | None = None,
    branch: str | None = None,
    ts: str | None = None,
) -> bool
```

Write one `context_pressure_events` row and index it in `search_index` with `kind="context_pressure"` (ENH-2507). Called from `context-monitor.sh`'s `record_context_pressure()` shell-out after every sampled `PostToolUse` (at most once per second per session, except a new 50/75/80/90/100 crossing always persists). Mirrors `record_session_lifecycle_event()`'s contract: catches `sqlite3.Error` internally and returns `False` (never raises) so the shell hook's `|| true` guard is a backstop, not the only safety net.

### record_review_event

```python
def record_review_event(
    db_path: Path | str,
    *,
    ts: str,
    session_id: str | None,
    reviewer_skill: str,
    target_kind: str | None = None,
    target_id: str | None = None,
    severity_counts: dict | None = None,
    findings_count: int | None = None,
    findings_json_summary: dict | list | None = None,
    verdict: str | None = None,
    head_sha: str | None = None,
    branch: str | None = None,
) -> None
```

Write one `review_events` row and index it in `search_index` with `kind="review"` (ENH-2512). Called from `cli/action.py::cmd_invoke()` for the seven skill-bridged audits/reviews via a `_REVIEWER_SKILLS` frozenset gate, wrapped in `contextlib.suppress(Exception)` so a DB failure never changes an audit's exit code. `severity_counts`/`findings_json_summary` are JSON-serialized on write (`json.dumps`), parsed back on read. Mirrors `record_verdict_event()`'s contract: raises on failure — the call site, not the producer, enforces best-effort.



```python
def record_commit_event(
    db_path: Path | str,
    commit_sha: str,
    message: str,
    *,
    author: str | None = None,
    branch: str | None = None,
    issue_id: str | None = None,
    files: Sequence[str] | None = None,
    parent_sha: str | None = None,
    ts: str | None = None,
    config: dict | None = None,
) -> bool
```

Write one `commit_events` row and index it in `search_index` with `kind="commit"` (ENH-2458). `issue_id` is inferred from the message (`Closes/Fixes/Resolves/Issue:` references, bare `TYPE-NNN` tokens) and branch naming (`feat/ENH-2458-*`) when not given. Idempotent via `INSERT OR IGNORE` on the `commit_sha` UNIQUE constraint; returns `True` when a new row was inserted. Producers: the `hooks/scripts/record-commit-post-commit` git hook (via `little_loops.hooks.post_commit.record_head_commit()`) and `ll-session backfill`, which walks `git log --all`.

### record_test_run_event

```python
def record_test_run_event(
    db_path: Path | str,
    *,
    ts: str,
    ended_at: str | None = None,
    total: int = 0,
    passed: int = 0,
    failed: int = 0,
    errored: int = 0,
    skipped: int = 0,
    duration_s: float | None = None,
    failing_names: Sequence[str] | None = None,
    env_label: str | None = None,
    head_sha: str | None = None,
    branch: str | None = None,
    command: str | None = None,
    config: dict | None = None,
) -> None
```

Write one `test_run_events` row and index it in `search_index` with `kind="test_run"` (ENH-2459). `failing_names` (pytest node IDs) are stored as a JSON array and fed into FTS so failing-test fragments are searchable. The primary producer is the `little_loops.pytest_history_plugin` pytest11 plugin (auto-registered via entry point; opt out with `PYTEST_DISABLE_PLUGIN_LL_HISTORY=1`); it only activates when the invocation directory contains `.ll/` or `LL_HISTORY_DB` is set, records from the xdist controller only, and swallows all write errors.

### record_orchestration_run

```python
def record_orchestration_run(
    db_path: Path | str,
    *,
    run_id: str,
    driver: str,
    issue_id: str,
    status: str,
    failure_reason: str | None = None,
    duration_s: float | None = None,
    wave: str | None = None,
    pr_url: str | None = None,
    started_at: str | None = None,
    ended_at: str | None = None,
    head_sha: str | None = None,
    branch: str | None = None,
    base_sha: str | None = None,
    base_dirty: bool | None = None,
    config: dict | None = None,
) -> bool
```

UPSERT one `orchestration_runs` row per `(run_id, issue_id)` and replace its matching FTS row (ENH-2492). A top-level `ll-auto`, `ll-parallel`, or `ll-sprint` invocation reuses one opaque UUID for all of its issues and retries; the final retry therefore replaces the initial failure rather than adding a duplicate. Producers guard calls with `contextlib.suppress(Exception)` so history failures never alter orchestration behavior.

`base_sha`/`base_dirty` are the dequeue-time base-state stamp (ENH-2866): the commit SHA the work item started from, and whether the tree had *tracked* modifications (`git status --porcelain --untracked-files=no`) at that moment. Orchestrators call this function **twice** per issue — once at dequeue with `status="running"` plus the stamp, so the base state is readable while the issue is still in flight, and once at end-of-issue with the outcome. Three columns are therefore write-once rather than last-write-wins: `base_sha`, `base_dirty`, and `started_at` are `COALESCE`d in the `DO UPDATE` clause, so a terminal upsert that passes none of them cannot null the dequeue-time values. An in-flight row leaves `ended_at` NULL (the `_now()` default applies only to a terminal status), so an abandoned run does not read as `ended_at == started_at`. A falsy `base_sha` is normalized to NULL — NULL means unstamped, never `""`.

Consequence: a crashed or interrupted run now leaves a permanent `status='running'` row where previously no row existed, which slightly lowers `aggregate_orchestration_runs`' reported success rate. This is intentional — a crashed run *is* a non-completion.

### read_base_sha

```python
def read_base_sha(
    issue_id: str,
    *,
    run_id: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> str | None
```

Resolve the dequeue-time base commit SHA stamped for `issue_id` (ENH-2866). The single reader every consumer uses, so the merge-base fallback is implemented once rather than per-orchestrator; all stamped drivers (`ll-parallel`, `ll-auto`, `ll-sprint`) write the same column on the same table, so there is no table dispatch.

`run_id` is optional and that is load-bearing: it is a process-local `uuid4().hex` never exported to env, run-dir, or subprocess argv, so an out-of-process consumer cannot supply one. When omitted, the most recent *stamped* row for the issue wins (`WHERE issue_id = ? AND base_sha IS NOT NULL ORDER BY id DESC LIMIT 1`) — the NOT NULL filter keeps a later unstamped row from shadowing an earlier stamped one.

Never raises. Returns `None` when the database is missing or unreadable, no matching row exists, or `base_sha` is NULL; the stamp is advisory, and a consumer that gets `None` should fall back to merge-base and say which base it used.

### read_base_dirty

```python
def read_base_dirty(
    issue_id: str,
    *,
    run_id: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> bool | None
```

Additive sibling of `read_base_sha()` (ENH-3142), mirroring its query dispatch exactly but against the `base_dirty` column. Converts the stored `int | None` to `bool | None` at the return boundary. Never raises. Returns `None` when the database is missing or unreadable, no matching row exists, or the row's `base_dirty` is NULL.

### record_loop_run_summary / update_loop_run_diagnostics

```python
def record_loop_run_summary(
    db_path: Path | str,
    *,
    run_id: str,
    loop_name: str,
    started_at: str | None = None,
    ended_at: str | None = None,
    final_state: str | None = None,
    iterations: int | None = None,
    terminated_by: str | None = None,
    error: str | None = None,
    evaluator_score: float | None = None,
    diagnostics_path: str | None = None,
    head_sha: str | None = None,
    branch: str | None = None,
    config: dict | None = None,
) -> bool


def update_loop_run_diagnostics(db_path: Path | str, run_id: str, diagnostics_path: str) -> bool
```

Write one `loop_runs` row and index it in `search_index` with `kind="loop_run"` (ENH-2463). `run_id` is the archive-time identifier (`started_at` mangled the same way as `fsm/persistence.py::archive_run`, joined with `-<loop_name>`) so the row JOINs to the on-disk `.loops/.history/` archive. Idempotent via `INSERT OR IGNORE` on the `run_id` UNIQUE constraint — a resumed-then-completed run contributes exactly one row. The sole v1 producer is `FSMExecutor._finish()`, called best-effort (wrapped in `try/except`) immediately after it emits `loop_complete`. `update_loop_run_diagnostics()` is a single `UPDATE ... WHERE run_id = ?` linking a `loop-specialist`-written diagnostics artifact back to its row; exposed as a public API but not yet wired into any caller (the artifact filename does not encode the archive `run_id`, so an upstream caller must supply it — a known v1 gap).

### record_learning_test_event / _backfill_learning_test_events

```python
def record_learning_test_event(
    db_path: Path | str,
    target: str,
    file_path: str,
    config: dict | None = None,
) -> bool


def _backfill_learning_test_events(conn: sqlite3.Connection, registry_dir: Path) -> int
```

UPSERT one `learning_test_events` row mirroring a Learning Test Registry record and refresh its FTS row (ENH-2466). `record_learning_test_event()` reads the `.md` file at `file_path`, keys the row on `record_id` (the slugified `target`), and is called best-effort from `ll-learning-tests prove`/`mark-stale`/`orphans --mark-stale` — a re-prove overwrites `status`/`assertions_json`/`date` rather than inserting a duplicate. `_backfill_learning_test_events()` is the reconcile companion: it walks `registry_dir` (`.ll/learning-tests/*.md`) with `INSERT OR IGNORE` on `record_id` so out-of-band file edits still land, without overwriting a live-written row's newer status. Wired into `backfill(db, ..., registry_dir=...)`, defaulting to `.ll/learning-tests` when not given.

### record_session_lifecycle_event

```python
def record_session_lifecycle_event(
    db_path: Path | str,
    *,
    session_id: str | None,
    event: str,
    detail: dict | None = None,
    head_sha: str | None = None,
    branch: str | None = None,
    ts: str | None = None,
) -> bool
```

Write one `session_lifecycle_events` row and index it in `search_index` with `kind="session_lifecycle"` (ENH-2495). `event` is an open TEXT discriminator (no CHECK constraint) — `handoff_needed`, `compaction`, `stale_ref_sweep` are the v1 producers; ENH-2509 shares the table with `worktree_*` values. Best-effort: catches `sqlite3.Error` internally and returns `False` (never raises), so a hook's primary job is never blocked by a missing/locked database. One authoritative producer per discriminator — `context-monitor.sh`'s first 80%-threshold crossing per pressure episode (`handoff_needed`), `pre_compact.handle()` after state persistence (`compaction`), `sweep_stale_refs.handle()` once per invocation including zero findings (`stale_ref_sweep`).

### record_retirement

```python
def record_retirement(
    db: Path | str = DEFAULT_DB_PATH,
    topic_fingerprint: str = "",
    rule_id: str = "",
    session_id: str = "",
) -> None
```

Mark a recurring-correction cluster as addressed. Uses `INSERT OR REPLACE` so calling it a second time for the same fingerprint updates the record. `rule_id` should be the `decisions.yaml` entry ID (e.g. `BEHAVIOR-001`) or `"claude-md"` when the rule was written directly into CLAUDE.md.

**Parameters:**
- `db` — path to the SQLite database (default: `.ll/history.db`)
- `topic_fingerprint` — 16-char hex fingerprint from `_fingerprint(content)` in `evolution.py`
- `rule_id` — the persisted rule ID (for audit trail); optional
- `session_id` — the session that accepted the rule; optional

### list_retirements

```python
def list_retirements(
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]
```

Return all `correction_retirements` rows as `dict` objects, ordered by `addressed_at DESC`. Returns `[]` when the DB does not exist.

**Dict keys:** `topic_fingerprint`, `rule_id`, `addressed_at`, `session_id`.

### correction_retirements table (v13, ENH-2046)

| Column | Type | Notes |
|--------|------|-------|
| `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | |
| `topic_fingerprint` | `TEXT NOT NULL` | `sha256(content[:512])[:16]`; unique index |
| `rule_id` | `TEXT` | `decisions.yaml` entry ID or `"claude-md"` |
| `addressed_at` | `TEXT NOT NULL` | UTC ISO 8601 timestamp |
| `session_id` | `TEXT` | session that accepted the rule |

`detect_recurring_feedback()` in `evolution.py` queries this table read-only via the existing `_open_db()` path; clusters whose fingerprint appears here are excluded from `RecurringFeedbackAnalysis.feedbacks` and counted in `retired_count`.

---

## little_loops.hooks

Host-agnostic hook intent dispatcher. Adapters under `hooks/adapters/<host>/` translate each host's native hook payload into an `LLHookEvent`, pipe it to `python -m little_loops.hooks <intent>`, and translate the returned `LLHookResult` back to the host's response contract.

```python
from little_loops.hooks import LLHookEvent, LLHookResult, main_hooks
```

Public surface — `__all__ = ["LLHookEvent", "LLHookResult", "main_hooks"]`.

### LLHookEvent

The host-agnostic request payload delivered to a hook intent handler. Defined in `scripts/little_loops/hooks/types.py`.

```python
@dataclass
class LLHookEvent:
    host: str
    intent: str = ""
    timestamp: str = ""        # wire key: "ts"
    payload: dict[str, Any] = field(default_factory=dict)
    session_id: str | None = None
    cwd: str | None = None
```

**Fields:**

| Field | Type | Default | Wire key | Description |
|---|---|---|---|---|
| `host` | `str` | *(required)* | `host` | Host agent identifier (`"claude-code"`, `"opencode"`, `"codex"`, …). Adapters set this; the CLI reads `LL_HOOK_HOST` (default `"claude-code"`). |
| `intent` | `str` | `""` | `intent` | Hook intent name matching the handler module (`pre_compact`, `session_start`, …). |
| `timestamp` | `str` | `""` | `ts` | ISO 8601 UTC. **Field name and wire key differ** — stored as `timestamp`, serialized as `ts`. |
| `payload` | `dict[str, Any]` | `{}` | `payload` | Host-supplied event data. Schema is intent-specific. |
| `session_id` | `str \| None` | `None` | `session_id` | Host session identifier. Omitted from the wire dict when `None`. |
| `cwd` | `str \| None` | `None` | `cwd` | Working directory the host was operating in. Omitted from the wire dict when `None`. |

**Behavior:**
- `to_dict()` emits the timestamp under the key `ts`; `from_dict()` accepts either `ts` or `timestamp` via `data.get("ts", data.get("timestamp", ""))`. A dict from `to_dict()` round-trips cleanly through `from_dict()`.
- `session_id` and `cwd` are omitted from the wire dict when `None`, so a `from_dict(to_dict(e)) == e` round-trip preserves the `None` sentinel.

```python
from little_loops.hooks import LLHookEvent

event = LLHookEvent(
    host="claude-code",
    intent="pre_compact",
    payload={"transcript_path": "/tmp/session.jsonl"},
    cwd="/Users/me/project",
)
event.to_dict()
# {"host": "claude-code", "intent": "pre_compact", "ts": "", "payload": {...}, "cwd": "..."}
```

### LLHookResult

The host-agnostic response returned by a hook intent handler. Defined in `scripts/little_loops/hooks/types.py`.

```python
@dataclass
class LLHookResult:
    exit_code: int = 0
    feedback: str | None = None
    decision: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    stdout: str | None = None
```

**Fields:**

| Field | Type | Default | Wire key | Description |
|---|---|---|---|---|
| `exit_code` | `int` | `0` | `exit_code` | Always emitted. `0` = pass; `2` = block and surface `feedback` to the model. Non-Claude hosts map this to their own permit/deny semantics. |
| `feedback` | `str \| None` | `None` | `feedback` | Human-readable message. Claude Code writes this to stderr when `exit_code == 2`. Omitted from the wire dict when `None`. |
| `decision` | `str \| None` | `None` | `decision` | Permission decision for permission-checking intents (`allow` / `deny` / `ask`). Omitted from the wire dict when `None`. |
| `data` | `dict[str, Any]` | `{}` | `data` | Additional structured data returned to the host. Omitted from the wire dict when empty. |
| `stdout` | `str \| None` | `None` | `stdout` | Raw payload written to the host's stdout (e.g. `session_start`'s merged config JSON). Omitted from the wire dict when `None`. |

**Behavior:**
- `main_hooks` writes `result.stdout` to stdout verbatim if non-`None`, prints `result.feedback` to stderr if truthy, and raises `SystemExit(result.exit_code)`.
- Handlers should **not** `print()` directly — return bytes on `LLHookResult.stdout` instead so adapters can route them to the host's stdout contract.

```python
from little_loops.hooks import LLHookResult

LLHookResult(exit_code=2, feedback="context budget exceeded; consider /compact")
```

### main_hooks

CLI entry point. Invoked as `python -m little_loops.hooks <intent>`.

```python
def main_hooks() -> int: ...
```

**Behavior:**
1. Reads stdin as JSON (skips when stdin is a TTY).
2. Builds `LLHookEvent(host=os.environ.get("LL_HOOK_HOST", "claude-code"), intent=sys.argv[1], payload=<parsed>, cwd=os.getcwd(), session_id=payload.get("session_id"))`. Note: `timestamp` stays at its dataclass default — the CLI does not populate it.
3. Looks up the handler via `_dispatch_table()` — extension-contributed intents merged with built-ins, with built-ins shadowing extensions on collision.
4. Calls the handler; writes `result.stdout` to stdout if non-`None`, prints `result.feedback` to stderr if truthy, and returns `result.exit_code` (the `__main__` shim raises `SystemExit(...)`).

**Adapter integration:**
- Claude Code adapters (`hooks/adapters/claude-code/precompact.sh`, `precompact-handoff.sh`, `post-tool-use.sh`, `session-start.sh`, `session-end.sh`, `drift-check.sh`, `stop.sh`) invoke `python -m little_loops.hooks <intent>` directly — `LL_HOOK_HOST` defaults to `"claude-code"`.
- The OpenCode adapter (`hooks/adapters/opencode/index.ts`) sets `LL_HOOK_HOST=opencode` before invoking the same CLI.
- The Codex CLI adapter (`scripts/little_loops/hooks/adapters/codex/session-start.sh`, `pre-compact.sh`, `drift-check.sh`) sets `LL_HOOK_HOST=codex` before invoking the same CLI. The `hooks.json` template restricts `SessionStart` to `"matcher": "startup"` per FEAT-957's policy (avoids re-emitting identifiers on `resume`/`clear` and minimizes trust-hash churn); the `drift_check` intent (ENH-2888) reuses this same convention.

**`drift_check` throttle (`hooks/drift_check.py`, ENH-2888):** surfaces throttled `mention`/`route`-severity doc-drift findings at session start, but only once per `hooks.doc_drift_throttle_days` (config key, default in `_DEFAULT_THROTTLE_DAYS`) — a per-project throttle-state file records the last-checked timestamp, and the hook is a no-op until that window elapses. Set `LL_DOC_DRIFT_DISABLE` to disable the check entirely regardless of throttle state.

---

## little_loops.host_runner

Host-agnostic CLI invocation layer. Every shell-out to a host CLI (`claude`, `codex`, `opencode`, `pi`, `gemini`, `omp`) is built through a `HostRunner` implementation, so the orchestration layer (`ll-auto`, `ll-parallel`, `ll-action`, `ll-loop`, FSM evaluators, FSM handoff) never hard-codes host-specific argv.

```python
from little_loops.host_runner import (
    CapabilityEntry,
    CapabilityNotSupported,
    CapabilityReport,
    HostCapabilities,
    HostInvocation,
    HostNotConfigured,
    HostRunner,
    apply_host_cli_from_config,
    resolve_host,
)
```

Public surface — `__all__ = ["BlockingJsonError", "CapabilityEntry", "CapabilityNotSupported", "CapabilityReport", "ClaudeCodeRunner", "CodexRunner", "GeminiRunner", "HostCapabilities", "HostInvocation", "HostNotConfigured", "HostRunner", "KimiRunner", "OmpRunner", "OpenCodeRunner", "PiRunner", "apply_host_cli_from_config", "build_anthropic_request", "build_batch_request", "dispatch_anthropic_request", "dispatch_batch_request", "poll_batch_result", "resolve_host", "resolve_host_named", "resolve_model_alias", "run_blocking_json"]`.

### HostInvocation

Immutable value object describing how to invoke a host CLI. Returned by every `build_*` factory on `HostRunner`. Call sites pass `binary` + `args` to `subprocess.Popen`/`run` and merge `env` into the child process environment.

```python
@dataclass(frozen=True)
class HostInvocation:
    binary: str
    args: list[str]
    env: dict[str, str] = field(default_factory=dict)
    capabilities: HostCapabilities = field(default_factory=HostCapabilities)
    cleanup_paths: tuple[Path, ...] = field(default_factory=tuple)
```

**Fields:**

| Field | Type | Default | Description |
|---|---|---|---|
| `binary` | `str` | *(required)* | Name of the host binary (e.g., `"claude"`, `"codex"`, `"opencode"`, `"pi"`). |
| `args` | `list[str]` | *(required)* | Positional + flag arguments to append after `binary`. Host-specific argv shape lives here. |
| `env` | `dict[str, str]` | `{}` | Environment variables to merge into the child process. Notably includes `GIT_DIR` / `GIT_WORK_TREE` when working inside a worktree, and host-specific knobs like `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR`. |
| `capabilities` | `HostCapabilities` | `HostCapabilities()` | Snapshot of the runner's capability flags, so callers can branch on what was actually wired without re-querying the runner. |
| `cleanup_paths` | `tuple[Path, ...]` | `()` | Temp files created during invocation building that the caller must unlink after the subprocess completes. Currently populated by `CodexRunner.build_blocking_json` when `json_schema` is supplied — the schema dict is written to a temp file and `--output-schema <path>` is appended to `args`. Call `p.unlink(missing_ok=True)` for each path in this tuple after `subprocess.run`. |

**Behavior:**
- `frozen=True` — mutating an invocation in flight would silently corrupt argv across the runner/caller boundary. This establishes the `frozen=True` convention for new value objects in `scripts/little_loops/`.

### HostCapabilities

Capability flags describing what a host runner supports. Each flag corresponds to a feature that may or may not be available on a given host; call sites that require a capability should check the relevant flag and either fall back gracefully or emit `CapabilityNotSupported`.

```python
@dataclass(frozen=True)
class HostCapabilities:
    streaming: bool = False
    permission_skip: bool = False
    agent_select: bool = False
    tool_allowlist: bool = False
    structured_output: bool = False
```

**Fields:**

| Field | Type | Default | Description |
|---|---|---|---|
| `streaming` | `bool` | `False` | Host can produce turn-by-turn structured (JSON / NDJSON) events for long-running orchestration paths. |
| `permission_skip` | `bool` | `False` | Host supports skipping interactive permission prompts (Claude `--dangerously-skip-permissions`, Codex `--dangerously-bypass-approvals-and-sandbox`). Required for headless automation. |
| `agent_select` | `bool` | `False` | Host accepts a per-invocation agent / persona selector. |
| `tool_allowlist` | `bool` | `False` | Host accepts an explicit tool allowlist on invocation. |
| `structured_output` | `bool` | `False` | Host's CLI honors the inline `--json-schema` flag the FSM evaluators append (Anthropic `claude` CLI). When `False`, evaluators skip the flag and rely on prompt-and-parse (BUG-2626 tag fallback). Gated at the evaluator call sites (ENH-2627). |

### HostRunner

Protocol every host runner satisfies. `@runtime_checkable`, so `isinstance(obj, HostRunner)` works for registry validation. Protocols are matched structurally — any class with the methods below satisfies `HostRunner` whether or not it subclasses the Protocol explicitly.

```python
@runtime_checkable
class HostRunner(Protocol):
    name: str

    def detect(self) -> bool: ...
    def build_streaming(self, *, prompt: str, working_dir: Path | None = None,
                        resume: bool = False, agent: str | None = None,
                        tools: list[str] | None = None,
                        model: str | None = None,
                        automation: AutomationContext | None = None,
                        automation_profile: str | None = None,
                        disable_background_tasks: bool = False,
                        workspace_root: Path | None = None) -> HostInvocation: ...
    def build_blocking_json(self, *, prompt: str, model: str | None = None,
                            json_schema: dict | None = None) -> HostInvocation: ...
    def build_version_check(self) -> HostInvocation: ...
    def build_detached(self, *, prompt: str) -> HostInvocation: ...
    def describe_capabilities(self) -> CapabilityReport: ...
```

`sandbox_mode` is **not** part of the Protocol — it is a `CodexRunner`-only extension parameter on that class's `build_streaming` / `build_blocking_json` / `build_detached`. Code written against `HostRunner` must not pass it. `CodexRunner` likewise accepts `workspace_root` for signature compatibility but warns and ignores it.

`automation` (ENH-3095) collapses the per-call automation signal into a single `AutomationContext(profile, idle_timeout, disable_background_tasks)`. `automation.disable_background_tasks` (FEAT-3078) is Claude-Code-only: when `True` and `automation.profile` is set, `ClaudeCodeRunner.build_streaming()` injects `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`, covering both `Bash run_in_background: true` and Agent/Task-tool spawns left to their background-by-default behavior (BUG-3209); when `automation.profile` is `None` (or `automation` is `None`), the variable is explicitly neutralized to `""` (same leak-prevention pattern as `LL_AUTOMATION`, see `_apply_automation_env`). The other seven runners accept and silently ignore the field — see `docs/reference/HOST_COMPATIBILITY.md`. The legacy `automation_profile`/`disable_background_tasks` keywords remain as deprecated pass-throughs, folded into an `AutomationContext` internally via `_resolve_automation()`; supplying either alongside an explicit `automation` emits a `DeprecationWarning` and the explicit context wins.

**Methods:**
- `detect()` — return `True` if this host is available in the current environment (typically `shutil.which("<binary>") is not None`).
- `build_streaming()` — argv that streams structured turn-by-turn events. Used by the long-running orchestration paths (`ll-auto`, `ll-parallel`, FSM runners).
- `build_blocking_json()` — argv for a one-shot invocation returning a single JSON blob. Used by FSM structured evaluators.
- `build_version_check()` — argv that prints the host's version and exits. Used by capability probes.
- `build_detached()` — argv for fire-and-forget detached execution. Used by FSM handoff.
- `describe_capabilities()` — probe the host and return a `CapabilityReport` describing which features are supported. Used by `ll-doctor` and `ll-action`.

**Concrete runners:**

| Runner | Host | Status | Notes |
|---|---|---|---|
| `ClaudeCodeRunner` | `claude` CLI | ✓ production | Argv mirrors `subprocess_utils.run_claude_command`; snapshot test in `tests/test_host_runner.py::test_claude_runner_matches_legacy_args`. |
| `CodexRunner` | `codex` CLI | ✓ production | Translates the Claude-shaped Protocol surface to Codex `exec` headless mode. Auto-detected when `codex` is on PATH (probe order: `claude → codex → pi → gemini → omp`). For `agent`, `build_streaming` reads `.codex/agents/<name>.toml` and prepends `developer_instructions` as a `[Persona: <name>]` block (ENH-1533); when the TOML is absent, falls back to emitting `CapabilityNotSupported` plus a stderr notice. `tools` always emits `CapabilityNotSupported` and is dropped; use `sandbox_mode=` (ENH-1529) for constrained execution. `describe_capabilities()` reports `agent_select.status == "partial"` and `tool_allowlist.status == "partial"` (via sandbox_mode). |
| `GeminiRunner` | `gemini` CLI | ✓ production | Gemini CLI (npm `@google/gemini-cli`). Flags are near-identical to Claude Code: `-p <prompt>`, `--output-format stream-json` / `json`, `--approval-mode yolo` for permission skip, `--resume latest` for resume, `--model <id>`. `agent` and `tools` parameters emit `CapabilityNotSupported` and are dropped (no `--agent` flag — skills activate implicitly; tool policy is a TOML-file Policy Engine, not a flag). `json_schema` is silently dropped, unlike `ClaudeCodeRunner` — which honors the inline `--json-schema` flag (BUG-2759). See `thoughts/research/gemini-cli-surface.md` (ENH-2184/ENH-2185). |
| `OmpRunner` | `omp` CLI | ✓ production | oh-my-pi (Bun `@oh-my-pi/pi-coding-agent`). `-p <prompt>` print mode; `--mode json` emits a JSONL event stream (no single-blob mode — `build_blocking_json` uses `--mode json --no-session` and callers consume the final event, same contract as Codex). `--continue` for resume, `--model <pattern>`, native `--tools <comma-list>` allowlist. `agent` emits `CapabilityNotSupported` (subagents spawn in-session). Permission skip is implicit — print mode never prompts. See `thoughts/research/omp-headless-flags.md` (FEAT-1850). |
| `OpenCodeRunner` | `opencode` CLI | stub | Registered so `LL_HOST_CLI=opencode` resolves to a useful error rather than the generic "unknown host". All `build_*` methods raise `HostNotConfigured`. See FEAT-1472. |
| `PiRunner` | `pi` CLI | frozen stub | Present in `_PROBE_ORDER`, so hosts with `pi` on PATH resolve to this stub. All `build_*` methods raise `HostNotConfigured`. Vanilla Pi support is cancelled (ARCHITECTURE-050); superseded by `OmpRunner` (EPIC-2258). |

### CapabilityEntry

Immutable value object describing the support status of a single host capability.

```python
@dataclass(frozen=True)
class CapabilityEntry:
    name: str
    status: Literal["full", "partial", "unsupported"]
    note: str = ""
```

**Fields:**

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | *(required)* | Capability identifier (e.g., `"streaming"`, `"permission_skip"`). |
| `status` | `Literal["full", "partial", "unsupported"]` | *(required)* | Support level on the active host. |
| `note` | `str` | `""` | Optional human-readable clarification (e.g., `"flag accepted but not validated"`). |

### CapabilityReport

Aggregated result of `describe_capabilities()`. Produced by every `HostRunner` implementation and consumed by `ll-doctor` and `ll-action capabilities`.

```python
@dataclass(frozen=True)
class CapabilityReport:
    host: str
    binary: str
    version: str
    capabilities: list[CapabilityEntry]
```

**Fields:**

| Field | Type | Description |
|---|---|---|
| `host` | `str` | Runner name (e.g., `"claude"`, `"codex"`). |
| `binary` | `str` | Resolved binary path (e.g., `"/usr/local/bin/claude"`). |
| `version` | `str` | Version string reported by the host, or `"unknown"` if detection fails. |
| `capabilities` | `list[CapabilityEntry]` | One entry per capability probe. |

### describe_capabilities

Protocol method implemented by every `HostRunner`. Returns a `CapabilityReport` without invoking the host for a real task — capability probes are fast, read-only checks.

```python
def describe_capabilities(self) -> CapabilityReport: ...
```

Used by `ll-doctor` (and `ll-doctor --json`) to generate human-readable and JSON diagnostic output. Each runner reports only the capabilities it can probe; stubs (`OpenCodeRunner`, `PiRunner`) return `"unsupported"` for all entries.

`ll-doctor --json`'s payload is not a 1:1 serialization of this dataclass — it's a superset. Alongside `host`/`binary`/`version`/`capabilities`, it adds `analytics_capture` and `issues` keys sourced from `BRConfig` (`cfg.analytics_capture`, `cfg.issues`), the same config state the text output prints under the "Analytics Capture" and "Issues" sections (ENH-2762). It also adds install-surface keys covering little-loops' own project state (FEAT-2793/FEAT-2794): `entry_points` (list of `{name, status, note}`), `skills_commands` (`{status, note, total}`), `decisions_store` (`{status, note}`), `history_db` (`{status, note}`), `loop_validity` (`{status, note, total, invalid}`), `schema_drift` (`{status, note}`, ENH-3242), and `advisor` (list of `{name, status, note, severity, floor_status}`, one row for `advisor_host` reachability and one for `advisor_floor` capability, `floor_status` the raw `FloorResult.status` on the floor row and `null` on the host row; FEAT-3122). When `--full` is passed, a `full` key (dict keyed by verifier name → `{status, note}`) aggregates the `ll-verify-*` / `ll-check-links` checker family (FEAT-2795).

### apply_host_cli_from_config

Apply the `orchestration.host_cli` config key (or `LL_HOST_CLI` env var) to the runner selection before the binary probe runs. Typically called once at startup by orchestration entry points.

```python
def apply_host_cli_from_config(config: object) -> None: ...
```

### resolve_host

Discovery entry point. Returns a `HostRunner` instance ready to build invocations.

```python
def resolve_host(env: dict[str, str] | None = None) -> HostRunner: ...
```

**Behavior:**

Detection order (first match wins):
1. `LL_HOST_CLI` environment variable — explicit override.
2. `LL_HOOK_HOST` environment variable — falls back to the hooks-layer host identifier so users with an existing hook config don't need a second knob.
3. Binary probe: `claude` → `codex` → `pi` → `gemini` → `omp` (see `_PROBE_ORDER`).
4. Raise `HostNotConfigured` with a remediation hint.

```python
from little_loops.host_runner import resolve_host

runner = resolve_host()
invocation = runner.build_streaming(prompt="Hello, world")
# subprocess.run([invocation.binary, *invocation.args], env={**os.environ, **invocation.env})
```

### project_child_env

Single chokepoint every task-path `subprocess.*` call routes through to build its `env=` mapping (ENH-3184).

```python
def project_child_env(
    invocation: HostInvocation | None = None,
    *,
    extra: dict[str, str] | None = None,
) -> dict[str, str]: ...
```

**Behavior:**

Default behavior is byte-identical to the pre-ENH-3184 status quo: full inheritance of the parent's `os.environ`, with `invocation.env` (when *invocation* is given) merged over it, then *extra* (for one-off keys a call site adds beyond what the `HostInvocation` carries, e.g. `LL_HOST_CLI` at `cli/loop/_helpers.py`) merged over that. Absence of a key at any layer means "inherit the parent's value" — this helper provides no way to clear or deny an inherited variable; that's deliberately out of scope (see ENH-3203).

`invocation` is optional because two `bash -c` task-path spawns (`fsm/runners.py`'s `DefaultActionRunner` shell branch, `runner_spec.py::_run_cmd()`) never construct a `HostInvocation` at all — `project_child_env()` with no arguments is exactly today's implicit inheritance, made explicit and interceptable at this one seam.

An AST-based guard test (`test_enh3184_spawn_site_guard.py`) enumerates every `subprocess.(run|Popen|check_output|call)` site across the task-path modules and fails if a new spawn bypasses this helper; sites intentionally exempt (git plumbing, `gh` auth/PR calls, detection/maintenance probes, pip introspection) carry an inline `# ll-no-project: <reason>` marker.

### resolve_host_named

FEAT-3042: resolve a specific registered host, ignoring ambient `LL_HOST_CLI`. Unlike `resolve_host`, never falls back to a PATH probe — an unregistered name raises `HostNotConfigured` immediately.

```python
def resolve_host_named(name: str) -> HostRunner: ...
```

```python
from little_loops.host_runner import resolve_host_named

runner = resolve_host_named("codex")  # ignores ambient LL_HOST_CLI, no env mutation
```

### run_blocking_json

FEAT-3042: execute a blocking invocation and return the parsed structured verdict. Handles all three structured-output paths (claude-code inline `--json-schema`, codex `--output-schema` temp file, prompt-and-parse tag fallback), the empty-stdout-with-exit-0 guard, the JSON envelope extraction chain (whole-string parse → last-non-blank-line JSONL fallback → tag fallback), and unlinks every `invocation.cleanup_paths` entry — including on failure/timeout.

```python
def run_blocking_json(
    invocation: HostInvocation,
    *,
    schema: dict[str, Any] | None = None,
    timeout: int = 180,
) -> dict[str, Any] | None: ...
```

Raises `BlockingJsonError` (a `RuntimeError` carrying a `details` dict with the same `timeout`/`missing_dependency`/`api_error`/`empty_output`/`raw_preview` flags `evaluate_llm_structured` has always surfaced) on any failure; in practice never returns `None`. `fsm.evaluators.evaluate_llm_structured` is the first migrated caller — build the invocation with `json_schema=schema` so hosts that need a schema file (codex) get it wired at build time, then pass the same `schema` to `run_blocking_json` so hosts with `HostCapabilities.structured_output` (claude-code) get the inline flag appended.

### build_anthropic_request / build_batch_request / dispatch_anthropic_request / dispatch_batch_request / poll_batch_result

`orchestration.request_path` opt-in dispatch (FEAT-2673, FEAT-2710, FEAT-2716,
EPIC-2456 F1) — a request path structurally distinct from the `HostRunner`
Protocol above: it calls the `anthropic` SDK's `messages.create()` /
`messages.batches.*` directly rather than shelling out to a host CLI
subprocess.

```python
def build_anthropic_request(*, skill_body, system_prompt, tools, messages, model,
                             fragment_store, require_repeat=True,
                             defer_loading_threshold=None,
                             search_tool_variant="bm25") -> dict[str, Any]: ...

def build_batch_request(*, custom_id, skill_body, system_prompt, tools, messages,
                         model, fragment_store, require_repeat=True,
                         defer_loading_threshold=None,
                         search_tool_variant="bm25") -> dict[str, Any]: ...

def dispatch_anthropic_request(*, action, system_prompt=None, tools=None, model,
                                fragment_store, require_repeat=True,
                                defer_loading_threshold=None,
                                search_tool_variant="bm25") -> ActionResult: ...

def dispatch_batch_request(*, custom_id, action, system_prompt=None, tools=None,
                            model, fragment_store, require_repeat=True,
                            defer_loading_threshold=None,
                            search_tool_variant="bm25") -> str: ...

def poll_batch_result(*, batch_id, custom_id, poll_interval_seconds=5.0,
                       max_wait_seconds=3600.0, backoff_factor=1.5,
                       max_poll_interval_seconds=60.0) -> ActionResult: ...
```

**Behavior:**
- `build_anthropic_request()` / `build_batch_request()` only assemble request
  kwargs (system/tools/messages, plus F1 cache-marking `cache_control` blocks
  and F1 deferred-tool-loading search-tool injection) — no network call. This
  keeps the `anthropic` package import lazy for callers that stay on the
  default `"cli"` path.
- `dispatch_anthropic_request()` builds via `build_anthropic_request()`, then
  calls `anthropic.Anthropic().messages.create(**request)` and normalizes the
  response into an `ActionResult` (same contract `action_runner.run()`
  returns for the CLI subprocess path). `anthropic.APIError` is caught and
  returned as a nonzero-exit-code result rather than raised.
- **Subscription OAuth fallback** (BUG-2830): the client is built via
  `host_runner._anthropic_client()`, not a bare `anthropic.Anthropic()`. When
  `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` are unset but
  `CLAUDE_CODE_OAUTH_TOKEN` (the var `claude setup-token` tells subscription
  users to set) is present, it's passed as `auth_token` with the
  `anthropic-beta: oauth-2025-04-20` header attached — the Messages API only
  honors a subscription OAuth token when the request also presents as Claude
  Code (beta header **and** a system prompt whose first block is the Claude
  Code identity line, which `build_anthropic_request()` supplies). A bare
  Bearer request with a subscription token is otherwise rejected with a
  header-less generic `429 rate_limit_error`, not an honest `401`/`403` —
  which autodev's failure classifier previously misread as transient infra
  instead of an auth problem.
- `dispatch_batch_request()` builds via `build_batch_request()`, submits via
  `anthropic.Anthropic().messages.batches.create(**kwargs)`, and returns the
  new batch's id. Persisting that id so a resumed run doesn't double-submit
  is the caller's responsibility — see `fsm/batch_tracker.py`'s
  `BatchTracker`.
- `poll_batch_result()` polls `messages.batches.retrieve()` with exponential
  backoff (capped at `max_poll_interval_seconds`) until
  `processing_status == "ended"` or `max_wait_seconds` elapses, then fetches
  `messages.batches.results()` and returns the entry matching `custom_id` as
  an `ActionResult`. Raises `BatchPollTimeout` on deadline — callers should
  leave the batch tracker file in place on that error so a resumed run
  retries against the same `batch_id`.
- `FSMExecutor._resolve_request_path()` / `_dispatch_live()`
  (`fsm/executor.py`) are the sole production call sites, gated on
  `state.request_path or orchestration_config.request_path` resolving to
  `"sdk"`/`"batch"` for `action_mode == "prompt"` states. Default (`"cli"`)
  behavior is unaffected. `_resolve_request_path()` additionally probes
  `anthropic` importability and credential resolvability — `ANTHROPIC_API_KEY`
  or `ANTHROPIC_AUTH_TOKEN` env statics, else the SDK's own
  `default_credentials()` chain (explicit profile, workload identity
  federation, active on-disk OAuth profile) — before returning
  `"sdk"`/`"batch"`; if either probe fails it downgrades the resolved value to
  `"cli"` with a one-shot `request_path_downgrade` event + stderr warning, so
  a missing package/credential never hard-fails the run (ENH-2737).

### HostNotConfigured

Raised when no host runner can be resolved from env or binary probe. The error message includes a remediation hint pointing at the `LL_HOST_CLI` and `LL_HOOK_HOST` env vars and the `orchestration.host_cli` config key so users have a clear path to fix the failure.

```python
class HostNotConfigured(RuntimeError): ...
```

Also raised by stub runners (`OpenCodeRunner`, `PiRunner`) on any `build_*` call, so callers that explicitly select a non-wired host get a useful error rather than malformed argv.

### CapabilityNotSupported

Warning emitted when a caller requests a capability the active host lacks (e.g., requesting `tools=` against `CodexRunner`; or requesting `agent=` against `CodexRunner` when `.codex/agents/<name>.toml` is absent — ENH-1533 prompt injection succeeds silently when the TOML exists).

```python
class CapabilityNotSupported(UserWarning): ...
```

Subclasses `UserWarning` (not `Warning`) so test code can capture it via `pytest.warns` and production code can route it through `warnings.simplefilter("error", CapabilityNotSupported)` for strict contexts. Mirrors the precedent set by `config.core` which emits `DeprecationWarning` via `warnings.warn(..., stacklevel=2)`.

---

## little_loops.runner_spec

Shared runner abstraction extracted from `ll-harness`/`ll-action`'s previously duplicated dispatch if/elifs (ENH-2668). `ll-harness` and `ll-action` build an `ActionSpec` and call `run_action()` instead of each owning its own runner-kind dispatch.

```python
from little_loops.runner_spec import ActionSpec, RunnerResult, RunnerType, run_action
```

### RunnerType

`Enum` covering the runner kinds `ll-harness` exposes (`SKILL`, `CMD`, `MCP`, `PROMPT`, `DSL`) plus `LOOP` for FSM loop execution.

### ActionSpec

```python
@dataclass(frozen=True)
class ActionSpec:
    name: str
    runner: RunnerType
    target: str
    args: dict[str, Any] = field(default_factory=dict)
    timeout: int = 120
```

Frozen, following the same crosses-the-runner/caller-boundary convention as `host_runner.HostInvocation`.

### RunnerResult

Unchanged in shape from its pre-extraction definition in `cli/harness.py`; that module re-exports it (`from little_loops.cli.harness import RunnerResult` still resolves) so existing importers are unaffected.

### run_action

`run_action(spec: ActionSpec) -> RunnerResult` dispatches to the runner named by `spec.runner`. Covers `SKILL`/`CMD`/`MCP`/`PROMPT`. `RunnerType.DSL` is a batch driver over `PROMPT` (callers loop and call `run_action` once per task, as `ll-harness`'s `cmd_dsl` does via `cmd_prompt`) rather than an independent execution path. `RunnerType.LOOP` is **not** dispatched by `run_action` — raises `ValueError` if attempted — because FSM loop execution (`PersistentExecutor`/`run_foreground()`) is a stateful, resumable, multi-state engine with per-state persistence, an event bus, and scope locking spanning the entire run, not a single blocking call. `cli/loop/run.py`'s `cmd_run()` builds a `RunnerType.LOOP` `ActionSpec` for structural/observability parity only and continues to call `PersistentExecutor` directly for execution.

---

## little_loops.queue_store

Persisted queue-entry store for `ll-queue` (FEAT-2682), backing a dedicated `.ll/queue.db` — distinct from `ll-loop queue`'s PID-liveness marker mechanism (`cli/loop/queue.py`), which FEAT-2684 preserves unchanged as a compat shim rather than migrating. Modeled directly on `session_store`'s migration/`connect`/`ensure_db` shape (own `_MIGRATIONS`/`SCHEMA_VERSION`, copied rather than shared). `ensure_db()`'s default-shaped `DEFAULT_DB_PATH` argument resolves via `resolve_ll_dir()` (ENH-2927), anchoring at the resolved project root rather than the bare working directory; an explicit non-default `db_path` is always honored verbatim.

```python
from little_loops.queue_store import (
    DEFAULT_DB_PATH,     # Path(".ll/queue.db")
    PRIORITY_TIERS,      # ("P0", "P1", "P2", "P3", "P4", "P5")
    QueueEntry,           # id, action: ActionSpec, enqueued_at, priority, status, result, claimed_at, owner_pid
    AmbiguousEntryIdError,
    ensure_db,
    connect,
    add_entry,            # (action: ActionSpec, priority: str = "P3", *, db_path=...) -> QueueEntry
    list_entries,          # ordered by priority tier, then FIFO within tier
    get_entry,              # exact id lookup
    resolve_entry,          # exact id or 8+-char prefix; raises AmbiguousEntryIdError on a multi-match prefix
    remove_entry,
    update_entry_result,   # for the FEAT-2683 worker loop to record status/result; also nulls claimed_at/owner_pid
    claim_entry,          # atomic pending->running acquisition write (BUG-2929); stamps claimed_at/owner_pid (FEAT-2930)
    reset_to_pending,      # running->pending; shared by _reclaim_stale and `ll-queue requeue` (FEAT-2930)
)
```

Schema: `queue_entries(id, action, enqueued_at, priority, status, result, claimed_at, owner_pid)`. `action` is a JSON-serialized `ActionSpec` (`little_loops.runner_spec`); `priority` is stored as the 0(P0)-5(P5) numeric rank so `ORDER BY priority ASC, enqueued_at ASC` reproduces `QueuedIssue.__lt__`'s tiered-then-FIFO ordering without importing that class (it's typed concretely against `IssueInfo`). Acquisition and completion are distinct writes: `claim_entry()` performs the `pending` -> `running` transition inside a `BEGIN IMMEDIATE` transaction so concurrent drainers cannot both win the same entry, stamping `claimed_at`/`owner_pid` (default `os.getpid()`) in the same transaction (FEAT-2930); `update_entry_result()` performs the completion write once the caller already owns the entry (`result` is `NULL` until then) and nulls both ownership columns. `reset_to_pending()` (FEAT-2930) is the inverse — `running` -> `pending`, clearing ownership — shared by `cli/queue.py`'s `_reclaim_stale` sweep (a `--watch` drainer's dead-owner cleanup) and the `ll-queue requeue` manual escape hatch.

---

## little_loops.tool_catalog

Catalog-assembly for little-loops' own Anthropic Messages API tool set (FEAT-2680). Walks `skills/*/SKILL.md`, `commands/*.md`, and `agents/*.md` frontmatter and produces a full `tools` array — the single, stable data source FEAT-2672 (deferred tool loading) and FEAT-2673 (`build_anthropic_request()`) consume instead of each reimplementing frontmatter enumeration.

```python
from little_loops.tool_catalog import ToolDefinition, assemble_tool_catalog, to_anthropic_tools
```

### ToolDefinition

```python
@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    cache_control: dict[str, str] | None = None
```

Frozen, following the same crosses-a-boundary convention as `host_runner.CapabilityEntry`. `cache_control` is always `None` coming out of `assemble_tool_catalog` — no code today populates it (see FEAT-2681); callers may set it before serializing.

**Fields:**

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | *(required)* | Skill directory name / command file stem / agent file stem. |
| `description` | `str` | *(required)* | Frontmatter `description`, quote-stripped. |
| `input_schema` | `dict[str, Any]` | *(required)* | Envelope-free Anthropic `input_schema` body — see below. |
| `cache_control` | `dict[str, str] \| None` | `None` | Unset by `assemble_tool_catalog`; present in serialized output only when set. |

### assemble_tool_catalog

```python
def assemble_tool_catalog(project_root: Path) -> list[ToolDefinition]: ...
```

Walks `project_root / "skills"` (`*/SKILL.md`), `project_root / "commands"` (`*.md`), and `project_root / "agents"` (`*.md`), each via `sorted(glob(...))` for deterministic order. Missing directories contribute no entries and never raise, matching the `cli/action.py:_load_skills()` / `cli/artifact/policy_builder.py:_load_skill_catalog()` precedent. All three walks parse frontmatter with the same `frontmatter.parse_skill_frontmatter()` — standardized on the flat parser rather than `adapters/core.py:_read_frontmatter()`'s nested-preserving variant, since `input_schema` bodies are hand-authored per entry *kind*, not derived from an agent's `tools:`/`model:` structure.

`input_schema` generation has no mechanical derivation path (skills/commands' `args`/`argument-hint` frontmatter is free-text display hints with no type information; agents carry no args-equivalent field at all):
- Skill/command **with** an `args`/`argument-hint` hint: `{"type": "object", "properties": {"args": {"type": "string", "description": <hint>}}, "required": []}`.
- Skill/command **without** a hint: `{"type": "object", "properties": {}, "required": []}`.
- Agent (always): fixed `{"type": "object", "properties": {"description": {...}, "prompt": {...}}, "required": ["description", "prompt"]}`, mirroring the real Agent-tool invocation contract.

### to_anthropic_tools

```python
def to_anthropic_tools(
    entries: list[ToolDefinition], *, defer_loading_threshold: int | None = None
) -> list[dict[str, Any]]: ...
```

Serializes catalog entries into the literal Anthropic Messages API `tools` array shape. `cache_control` is omitted from the dict entirely when `None` — the Anthropic API rejects a literal `null` cache_control value, so `None` must never become a JSON key.

`defer_loading_threshold` (FEAT-2672, EPIC-2456 F1): when set, entries at or past this catalog index get `defer_loading: True`, withholding their full definition from the assembled system prompt unless the model searches for them via a server-side search tool. `None` (default) leaves every entry unflagged — unchanged behavior. Setting `defer_loading: True` has no effect unless the request's `tools` array also carries a `tool_search_tool_bm25_20251119` / `tool_search_tool_regex_20251119` entry — see `host_runner.build_anthropic_request()`, which injects that entry automatically.

---

## little_loops.adapters

> `CodexEmitter`, `GeminiEmitter`, `OmpEmitter`, `KimiEmitter`, and `ClaudeCodeEmitter` are all registered (FEAT-2391/2392/3104/3105/3139). Use `ll-adapt --host <host> --apply` to emit artifacts for a given host.

Host-parameterised adapter layer that converts ll skill/command/agent metadata into each target host's discovery format. Parallel to `little_loops.host_runner` (which handles *invoking* the host CLI); this module handles *emitting* ll artifacts *to* a host.

```python
from little_loops.adapters import HostEmitter, resolve_emitter, AdapterError
```

### HostEmitter

`@runtime_checkable` structural Protocol. Any class exposing `name: str` and the four `emit_*` methods satisfies it without explicit subclassing; `isinstance(obj, HostEmitter)` works at runtime.

```python
class HostEmitter(Protocol):
    name: str
    def emit_skill(self, skill_meta: dict) -> str: ...
    def emit_command(self, cmd_meta: dict) -> str: ...
    def emit_agent(self, agent_meta: dict) -> str: ...
    def emit_mcp_config(self, meta: dict) -> str: ...
```

`emit_mcp_config` (FEAT-3138/FEAT-3139) wires an `ll-mcp` server entry into the host's MCP config format. Only `ClaudeCodeEmitter` and `CodexEmitter` write a real file; the other three emitters implement it as a stub returning `"skipped"` (no native MCP config surface yet for that host).

### resolve_emitter

Registry-backed factory. Returns a `HostEmitter` instance for the given host name.

```python
emitter = resolve_emitter("codex")
output = emitter.emit_skill({"name": "my-skill", ...})
```

**Args:** `host` — one of `"codex"`, `"gemini"`, `"omp"`, `"kimi-code"`, `"claude-code"`.  
**Raises:** `AdapterError` if the host is not registered.

### AdapterError

Raised when a host emitter cannot fulfil the request (unknown host, or stub emitter called before implementation is wired up).

```python
class AdapterError(Exception): ...
```

### Built-in emitters

| Class | Host key | Status |
|-------|----------|--------|
| `CodexEmitter` | `"codex"` | Implemented (FEAT-2391) — emits `.codex/` skill/command/agent files; `emit_mcp_config` ignores `output_dir` and merges an `[mcp_servers.ll-mcp]` table (`command = "ll-mcp"`) into Codex's global `~/.codex/config.toml` (or `$CODEX_HOME/config.toml`) — corrected under BUG-3178, since Codex has no project-local MCP config read path |
| `GeminiEmitter` | `"gemini"` | Implemented (FEAT-2392) — emits `.gemini/` skill/command/agent files; `emit_mcp_config` is a stub (no native MCP config yet) |
| `OmpEmitter` | `"omp"` | Implemented (FEAT-3104/FEAT-3105) — emits `.omp/skills/`, flat `.omp/commands/`, and `.omp/agents/` files; `emit_mcp_config` is a stub |
| `KimiEmitter` | `"kimi-code"` | Implemented (EPIC-2910) — emits skill/command/agent files for Kimi Code; `emit_mcp_config` is a stub. Host key is `"kimi-code"`, not `"kimi"`, to match its `host_runner` registry key. |
| `ClaudeCodeEmitter` | `"claude-code"` | Implemented (FEAT-3139) — `emit_skill`/`emit_command`/`emit_agent` are stubs (Claude Code's plugin marketplace serves these natively); `emit_mcp_config` merges `{"mcpServers": {"ll-mcp": {"command": "ll-mcp"}}}` into `.mcp.json` at the project root |

To add a host: create `scripts/little_loops/adapters/<host>.py` implementing `HostEmitter`, then register the class in `_EMITTER_MAP` in `core.py`.

---

## little_loops.codequery

Structural code-query provider protocol and registry (FEAT-2576). Mirrors the `adapters/`
shape above: a `@runtime_checkable` Protocol, a lazy-import registry, and a `resolve_*`
factory. Answers "who calls/imports/defines/references X" and "what is impacted if these
files change" without requiring any index to be built.

```python
from little_loops.codequery import CodeQueryProvider, CodeRef, ProviderStatus, resolve_provider
```

### CodeQueryProvider

```python
class CodeQueryProvider(Protocol):
    name: str
    def capabilities(self) -> set[str]: ...
    def status(self) -> ProviderStatus: ...
    def callers_of(self, symbol: str) -> list[CodeRef]: ...
    def callees_of(self, symbol: str) -> list[CodeRef]: ...
    def importers_of(self, module: str) -> list[CodeRef]: ...
    def defines(self, path: str) -> list[CodeRef]: ...
    def references(self, symbol: str) -> list[CodeRef]: ...
    def impact_of(self, paths: list[str], depth: int = 2) -> list[CodeRef]: ...
```

### resolve_provider

```python
provider = resolve_provider("auto")  # or "fallback"
refs = provider.callers_of("little_loops.issue_manager.IssueManager.load")
```

**Args:** `name` — a registered provider name, or `"auto"` (default) to pick the first
registered provider (registration order) whose `status()` reports `available`.
**Raises:** `CodeQueryError` if `name` is not registered, or `"auto"` finds none available.

### Built-in providers

| Class | Provider key | Status |
|-------|--------------|--------|
| `CodegraphProvider` | `"codegraph"` | Implemented (ENH-2613) — read-only reader over a `.codegraph/codegraph.db` SQLite index; `exact` confidence, staleness-checked against `git HEAD` and the working tree per `code_query.staleness`. The working-tree dirty-file check is scoped to `scan.focus_dirs`/`exclude_patterns` (ENH-2736) — untracked/modified files outside the scan scope (e.g. `.ll/`, `.issues/`, `thoughts/`) don't flip freshness to `stale` |
| `FallbackProvider` | `"fallback"` | Implemented (FEAT-2576) — grep/AST over the working tree; always available, always `freshness: fresh` |

To add a provider: create `codequery/<provider>.py` implementing `CodeQueryProvider`, then
register in `_PROVIDER_MAP` in `core.py`.

---

## little_loops.transport

Transport abstraction for the EventBus. A `Transport` is an additive sink that receives every event emitted on the bus. The Protocol is intentionally minimal — `send(event)` for delivery and `close()` for cleanup — so new sinks can be added without modifying `EventBus` itself.

```python
from pathlib import Path

from little_loops.events import EventBus
from little_loops.transport import JsonlTransport, Transport

bus = EventBus()
bus.add_transport(JsonlTransport(Path(".ll/events.jsonl")))
bus.emit({"event": "demo", "ts": "2026-05-02T00:00:00Z"})
bus.close_transports()
```

### Transport Protocol

```python
@runtime_checkable
class Transport(Protocol):
    def send(self, event: dict[str, Any]) -> None: ...
    def close(self) -> None: ...
```

Implement this protocol to register a custom event sink. The `@runtime_checkable` decorator enables `isinstance(obj, Transport)` checks at runtime. Transports do not filter events — every event emitted on the bus is delivered to every registered transport. Implementations must tolerate arbitrary `dict[str, Any]` shapes (the bus does not validate event contents). Per-transport `send()` and `close()` exceptions are caught and logged by `EventBus`, so a faulty transport never blocks delivery to other observers or transports.

### JsonlTransport

Reference implementation that appends each event as a single JSON line to a file. Replaces the previous `EventBus._file_sinks` mechanism.

```python
from little_loops.transport import JsonlTransport
from pathlib import Path

transport = JsonlTransport(Path(".ll/events.jsonl"))
transport.send({"event": "demo", "ts": "2026-05-02T00:00:00Z"})
```

#### Constructor

```python
JsonlTransport(path: Path)
```

**Parameters:**
- `path` - Path to the JSONL log file. The parent directory is created at construction time so per-event writes do not have to check it.

#### Methods

| Method | Description |
|--------|-------------|
| `send(event: dict[str, Any]) -> None` | Append `json.dumps(event)` as a line to the configured path. Each call opens and closes the file. |
| `close() -> None` | No-op. Each `send()` already closes its file handle. |

### UnixSocketTransport

Streams newline-delimited JSON events over an `AF_UNIX` socket so local consumers (TUIs, log tailers, dev dashboards) get sub-second latency without polling. Stdlib-only (no external dependencies).

```python
from little_loops.transport import UnixSocketTransport
from pathlib import Path

transport = UnixSocketTransport(Path(".ll/events.sock"), max_clients=8)
transport.send({"event": "demo", "ts": "2026-05-02T00:00:00Z"})
transport.close()
```

#### Constructor

```python
UnixSocketTransport(path: Path, max_clients: int = 32, on_connect: Callable[[_SocketClient], None] | None = None)
```

**Parameters:**
- `path` - Preferred path for the AF_UNIX socket. Before binding, the constructor probes `path` (BUG-3324): a genuinely stale occupant (regular file, or a bound-but-dead socket) is unlinked and `path` is bound as before; a *live* listener already on `path` causes this instance to bind a `{stem}-{pid}{suffix}` sibling path instead, leaving the live listener and its consumers untouched. The bound path (not necessarily `path`) is available as `self._path` after construction and is `chmod 0600` immediately after `bind()`.
- `max_clients` - Maximum simultaneous client connections. Used as both the `listen()` backlog and the live-clients cap; further connections are accepted-and-closed.
- `on_connect` - Optional callback invoked by `_accept_loop` immediately after a new client is registered. Receives the new `_SocketClient`; used internally by `wire_transports` to seed current loop state. Defaults to `None` (no-op). Also fires for the accept-and-close connection made by another instance's construction-time probe against this listener — self-healing, and does not affect delivery to already-attached consumers.

**Wire format:** Each `send(event)` serializes the event with `json.dumps(event)` and appends a `\n`, so consumers can parse one line at a time:

```bash
nc -U .ll/events.sock | jq
```

#### Methods

| Method | Description |
|--------|-------------|
| `send(event: dict[str, Any]) -> None` | Enqueue the serialized event into every connected client's outbound queue. Non-blocking — if a client's queue is full, the newest event is dropped (preserving causal order) and a rate-limited warning is logged. |
| `close() -> None` | Set the shutdown event, join the accept thread (≤2s) and each client thread (≤1s, 10s ceiling overall), close the server socket, and unlink the socket file — but only if it is still the same inode this instance bound (BUG-3324): if another producer reclaimed the path during the drain window, that producer's socket is left alone. |

**Platform support:** Requires `AF_UNIX` (POSIX). On Windows, [`wire_transports`](#wire_transports) raises `RuntimeError` rather than registering the transport.

### OTelTransport

Maps ll loop executions to OpenTelemetry traces and spans, exporting via OTLP to any OTel-compatible backend (Grafana, Jaeger, Datadog, etc.). Requires `pip install 'little-loops[otel]'`.

**Span hierarchy:** loop run = trace root (`loop_start`/`loop_complete`), state = child span (`state_enter`), action = grandchild span (`action_start`/`action_complete`). Span events are emitted for `evaluate`, `route`, `retry_exhausted`, `handoff_detected`, `handoff_spawned`, and `action_output`.

```python
from little_loops.transport import OTelTransport

transport = OTelTransport(
    endpoint="http://localhost:4317",
    service_name="little-loops",
)
transport.send({"event": "loop_start", "loop_name": "my-loop"})
transport.send({"event": "loop_complete", "outcome": "success"})
transport.close()
```

#### Constructor

```python
OTelTransport(
    endpoint: str = "http://localhost:4317",
    service_name: str = "little-loops",
)
```

**Parameters:**
- `endpoint` - OTLP gRPC endpoint for the collector. Passed directly to `OTLPSpanExporter`.
- `service_name` - Value for the `service.name` OTel resource attribute applied to all spans.

**Raises `RuntimeError`** at construction time if `opentelemetry-sdk` or `opentelemetry-exporter-otlp-grpc` are not installed.

#### Methods

| Method | Description |
|--------|-------------|
| `send(event: dict[str, Any]) -> None` | Route the event through the span state machine. Sub-loop events (`depth > 0`) are no-ops with a single warning per session. |
| `close() -> None` | Call `force_flush()` then `shutdown()` on the tracer provider, flushing all buffered spans before exit. |

#### Event → span mapping

| Event | Span action |
|-------|-------------|
| `loop_start` | Open root span (new trace). Name = `event["loop_name"]`. |
| `loop_resume` | Close all open spans; open a new root span (new trace). |
| `state_enter` | Close prior state span + action span; open child of loop span. Name = `event["state"]`. |
| `action_start` | Open grandchild of state span. Name = `event["action"]`. |
| `action_complete` | Close action span. |
| `loop_complete` | Close state + action spans; set loop span status (OK or ERROR); close loop span. |
| `evaluate`, `route`, `retry_exhausted`, `handoff_detected`, `handoff_spawned`, `action_output` | Add span event on innermost open span. |

### WebhookTransport

POSTs batched FSM events to an HTTP endpoint for remote dashboards, Slack bots, and CI systems. Requires `pip install 'little-loops[webhooks]'`.

**Batching:** `send()` enqueues events non-blocking; a daemon thread flushes the queue every `batch_ms` milliseconds. All accumulated events are POSTed as a single JSON array.

**Retry:** Failed POSTs (5xx or connection error) are retried up to `max_retries` times with exponential backoff (0.5s → … → 8s). After exhaustion the batch is dropped with a `WARNING` — exceptions never propagate to the caller.

```python
from little_loops.transport import WebhookTransport

transport = WebhookTransport(
    url="https://hooks.example.com/ll-events",
    batch_ms=1000,
    headers={"Authorization": "Bearer token"},
    max_retries=3,
)
transport.send({"event": "loop_start", "loop_name": "my-loop"})
transport.close()
```

#### Constructor

```python
WebhookTransport(
    url: str,
    batch_ms: int = 1000,
    headers: dict[str, str] | None = None,
    max_retries: int = 3,
)
```

**Parameters:**
- `url` - HTTP endpoint to POST batched events to.
- `batch_ms` - Flush interval in milliseconds (default: 1000).
- `headers` - Optional dict of extra HTTP headers (e.g. `{"Authorization": "Bearer tok"}`).
- `max_retries` - Number of retries on 5xx/connection error before giving up (default: 3).

**Raises `RuntimeError`** at construction time if `httpx` is not installed.

#### Methods

| Method | Description |
|--------|-------------|
| `send(event: dict[str, Any]) -> None` | Enqueue the event for the next batch flush. Non-blocking. No-op after `close()` is called. |
| `close() -> None` | Signal shutdown, drain the queue with one final flush, and join the daemon thread (10s timeout). |

### LocalBridgeTransport

Loopback-only HTTP + SSE bridge — Level 3 (host-owned) per
[ARTIFACT_CONTROL_LEVELS.md](ARTIFACT_CONTROL_LEVELS.md) — backing `ll-loop run
--serve` (ENH-3351). Bidirectional: outbound events stream to connected browser
clients as SSE frames; a `POST /{token}/interaction` handler enqueues the JSON
body onto an `inbound` queue the FSM executor drains
(`FSMExecutor._drain_inbound`). Stdlib-only (`http.server.ThreadingHTTPServer`),
no new dependency. Constructed directly by `cli/loop/run.py` under `--serve` —
not registered through `wire_transports`/`_TRANSPORT_REGISTRY`.

```python
import queue

from little_loops.transport import LocalBridgeTransport

inbound: queue.Queue[dict] = queue.Queue()
bridge = LocalBridgeTransport(port=0, inbound=inbound, render_fragment=None)
print(bridge.url)  # http://127.0.0.1:<bound-port>/<token>/
bridge.send({"event": "state_enter", "state": "running"})
bridge.close()
```

#### Constructor

```python
LocalBridgeTransport(
    port: int = 0,
    inbound: queue.Queue[dict[str, Any]] | None = None,
    render_fragment: Callable[[dict[str, Any]], str | None] | None = None,
    page_html: str | None = None,
)
```

**Parameters:**
- `port` - TCP port on `127.0.0.1` to bind. `0` (default) picks an ephemeral port; the actual bound port is read back via `url`. Binds `127.0.0.1` only — there is no host-override parameter.
- `inbound` - Optional `queue.Queue` that `POST /{token}/interaction` bodies are enqueued onto unchanged (`put_nowait`, dropped with a rate-limited warning if full or the body isn't valid JSON). `None` means inbound POSTs are accepted and dropped.
- `render_fragment` - Optional callable converting an event dict to an HTML fragment string (or `None` to skip that event). When omitted, `send()` forwards raw JSON `data:` frames — the form `test_transport.py`'s unit tests mostly exercise. `cli/artifact/dashboard.py`'s `render_live_fragment` is the real caller supplied here, keeping Jinja out of `transport.py`.
- `page_html` - HTML served at `GET /{token}/`. `None` serves a minimal placeholder; the loop process supplies the full dashboard page built via `build_dashboard_html(..., serve_context=...)`.

Every request is checked against the per-run token (`secrets.token_urlsafe(16)`, generated at construction) and the `Host` header (`403` unless it is exactly `127.0.0.1:<port>` or `localhost:<port>`, guarding against DNS rebinding); a missing/wrong token is `404`.

#### Methods

| Method | Description |
|--------|-------------|
| `send(event: dict[str, Any]) -> None` | Fan out to every connected SSE client's per-client queue as an SSE frame (via `render_fragment`, or raw JSON when unset). Non-blocking — a full client queue drops the newest event. |
| `close() -> None` | Push a final `run_complete`-derived frame (plus a shutdown sentinel) into every connected client's queue so each SSE handler exits cleanly, then `shutdown()`/`server_close()` the HTTP server and join handler threads within a bounded budget. Delivers the final frame and leaves no handler threads behind — asserted in tests, not just intended. |
| `set_page_html(page_html: str) -> None` | Replace the HTML served at `GET /{token}/` after construction — the served page typically embeds this transport's own `url` (for its SSE/interaction endpoints), which is only known once the server is bound, so callers construct first, build the page from `url`, then call this instead of passing `page_html` to `__init__`. |
| `url` (property) | `http://127.0.0.1:<bound-port>/<token>/` — the page URL. Derive the events/interaction endpoints by appending `events` / `interaction`. |

### wire_transports

Register the transports listed in an `EventsConfig` on an `EventBus`. Called by CLI entry points (ll-loop, ll-parallel, ll-sprint) at startup.

```python
from little_loops.events import EventBus
from little_loops.transport import wire_transports
from pathlib import Path

bus = EventBus()
wire_transports(bus, config.events, log_dir=Path(".ll"))
```

**Signature:**
```python
def wire_transports(
    bus: EventBus,
    config: EventsConfig,
    log_dir: Path | None = None,
) -> None
```

**Parameters:**
- `bus` - The `EventBus` instance to register transports on.
- `config` - `EventsConfig` whose `transports` field lists the transport names to wire up.
- `log_dir` - Directory under which built-in transports place their log files. Defaults to `Path(".ll")` under the current working directory.

**Behavior:**
- Each name in `config.transports` is resolved against an internal registry of built-in transport names. Five transports are currently shipped: `"jsonl"` (registers a `JsonlTransport` writing to `<log_dir>/events.jsonl`), `"socket"` (registers a [`UnixSocketTransport`](#unixsockettransport) bound at `config.socket.path` with `config.socket.max_clients`), `"otel"` (registers an [`OTelTransport`](#oteltransport) using `config.otel.endpoint` and `config.otel.service_name`), `"webhook"` (registers a [`WebhookTransport`](#webhooktransport) using `config.webhook.url`, `batch_ms`, and `headers`; skipped with a warning if `url` is `None`), and `"sqlite"` (registers a `SQLiteTransport` — defined in `little_loops.session_store`, not `transport.py` — writing events into the per-project `.ll/history.db` unified session store).
- Unknown names log a `WARNING` and are skipped — a typo in user config never prevents the loop from starting.
- The `"socket"` transport raises `RuntimeError` on platforms without `AF_UNIX` (e.g. Windows). This is the deliberate exception to the warn-and-skip rule: silently dropping `"socket"` on Windows would be a more confusing failure mode.

---

## little_loops.extension

Extension protocol, loader, and reference implementation for the plugin extension system.

```python
from little_loops.extension import ExtensionLoader, LLExtension

extensions = ExtensionLoader.load_all(config_paths=["my_package:MyExtension"])
for ext in extensions:
    ext.on_event(LLEvent(type="issue.completed", timestamp="2026-04-02T12:00:00Z"))
```

### ENTRY_POINT_GROUP

```python
ENTRY_POINT_GROUP = "little_loops.extensions"
```

Module-level constant defining the Python entry point group name used by `ExtensionLoader.from_entry_points()` and by external packages registering extensions in `pyproject.toml`.

### LLExtension Protocol

```python
@runtime_checkable
class LLExtension(Protocol):
    event_filter: str | list[str] | None  # optional; defaults to None
    def on_event(self, event: LLEvent) -> None: ...
```

Implement this protocol to create an extension that receives structured events from the EventBus. The `@runtime_checkable` decorator enables `isinstance(obj, LLExtension)` checks at runtime.

Optionally declare `event_filter` as a class attribute to subscribe only to specific event namespaces. `wire_extensions()` reads this attribute and passes it to `bus.register()`. If the attribute is absent, the extension receives all events:

```python
class MyFSMExtension:
    event_filter = ["state_enter", "loop_*"]  # bare FSM event names

    def on_event(self, event: LLEvent) -> None:
        print(f"FSM event: {event.type}")

class MyIssueExtension:
    event_filter = "issue.*"  # dotted namespace

    def on_event(self, event: LLEvent) -> None:
        print(f"Issue event: {event.type}")
```

### NoopLoggerExtension

Reference implementation of `LLExtension` that appends events to a JSONL log file.

```python
from little_loops.extension import NoopLoggerExtension
from pathlib import Path

ext = NoopLoggerExtension(log_path=Path(".ll/my-events.jsonl"))
ext.on_event(event)  # appends event.to_dict() as JSON line
```

#### Constructor

```python
NoopLoggerExtension(log_path: Path | None = None)
```

**Parameters:**
- `log_path` - Path to the JSONL log file. Defaults to `Path(".ll/extension-events.jsonl")`. Parent directories are created on construction.

#### Methods

| Method | Description |
|--------|-------------|
| `on_event(event: LLEvent) -> None` | Append `json.dumps(event.to_dict())` as a line to the log file. |

### ExtensionLoader

Discovers and instantiates extensions from config paths and Python entry points. All methods are static.

#### Methods

```python
@staticmethod
def from_config(extension_paths: list[str]) -> list[LLExtension]
```
Load extensions from `"module.path:ClassName"` strings. Each string is split on the last `":"`, the module is imported, and the class is instantiated with no arguments. Failures are caught and logged individually.

```python
@staticmethod
def from_entry_points() -> list[LLExtension]
```
Discover extensions registered under the `"little_loops.extensions"` entry point group via `importlib.metadata.entry_points()`. Each discovered class is instantiated with no arguments. Includes Python 3.11 compatibility fallback.

```python
@staticmethod
def load_all(config_paths: list[str] | None = None) -> list[LLExtension]
```
Combined loader. When `config_paths` is provided, loads from config first, then always loads from entry points. Returns the merged list.

**Parameters:**
- `config_paths` - Optional list of `"module:Class"` strings from the `extensions` config key. Defaults to `None`.

**Returns:** List of instantiated extensions from both sources.

### wire_extensions

Convenience helper that loads all extensions from config and registers them on an `EventBus`. This is the function called by CLI entry points (ll-loop, ll-parallel, ll-sprint) to activate extension callbacks at run time.

```python
from little_loops.extension import wire_extensions
from little_loops.events import EventBus

bus = EventBus()
extensions = wire_extensions(bus, config.extensions)
```

**Signature:**
```python
def wire_extensions(
    bus: EventBus,
    config_paths: list[str] | None = None,
    executor: FSMExecutor | None = None,
) -> list[LLExtension]
```

**Parameters:**
- `bus` - The `EventBus` instance to register extensions on.
- `config_paths` - Optional list of `"module.path:ClassName"` strings (from `BRConfig.extensions`). Pass `None` or omit to skip config-path loading (entry-point discovery still runs).
- `executor` - Optional `FSMExecutor` to populate with contributed actions, evaluators, and interceptors from loaded extensions.

**Returns:** List of all successfully loaded extension instances (from both config paths and entry points).

**Behavior:**
- Calls `ExtensionLoader.load_all(config_paths)` to discover extensions from both config paths and Python entry points.
- For each loaded extension, wraps `ext.on_event` to convert the raw event dict into an `LLEvent` (using `LLEvent.from_raw_event()`, which copies the dict to prevent mutation), then calls `bus.register(callback, filter=getattr(ext, "event_filter", None))` — forwarding any `event_filter` declared on the extension class.
- The forwarded `event_filter` is matched against the event's `type` field using `fnmatch` glob patterns. `None` (the default) means the extension receives every event.
- When `executor` is provided, a second pass populates `executor._contributed_actions`, `executor._contributed_evaluators`, and `executor._interceptors` from each extension that implements the corresponding protocols (`ActionProviderExtension`, `EvaluatorProviderExtension`, `InterceptorExtension`).
- The same second pass also merges any `LLHookIntentExtension.provided_hook_intents()` mappings into the module-level `_HOOK_INTENT_REGISTRY` in `little_loops.hooks` (detected via `hasattr()`), making the contributed `name → Callable[[LLHookEvent], LLHookResult]` handlers available to `little_loops.hooks.main_hooks()` for dispatch by the host adapters under `hooks/adapters/<host>/`.

**Error handling:**
- **Load failures** — both `ExtensionLoader.from_config()` and `from_entry_points()` catch all exceptions per extension, log a `WARNING` with the full traceback, and continue. A single bad extension never prevents others from loading; `wire_extensions` returns a partial list of the extensions that did succeed.
- **Runtime failures** — if an extension's `on_event` raises during `EventBus.emit()`, the exception is caught and logged at `WARNING` level. Other registered observers still receive the event.
- **Duplicate key conflicts** — if two extensions provide the same action or evaluator key, `wire_extensions` raises `ValueError: "Extension conflict: action/evaluator '<key>' already registered by another extension"`.

### LLHookIntentExtension

Optional mixin Protocol that extensions implement to contribute hook intent handlers. Detected by `wire_extensions()` via `hasattr(ext, "provided_hook_intents")` (same duck-typing pattern as `ActionProviderExtension`, `EvaluatorProviderExtension`, and `InterceptorExtension`).

```python
@runtime_checkable
class LLHookIntentExtension(Protocol):
    def provided_hook_intents(self) -> dict[str, Callable[[LLHookEvent], LLHookResult]]: ...
```

**Methods:**

| Method | Description |
|--------|-------------|
| `provided_hook_intents() -> dict[str, Callable[[LLHookEvent], LLHookResult]]` | Return a mapping of intent name → handler. Handler signature must match `(LLHookEvent) -> LLHookResult`. Called once at wire time. |

**Behavior:**
- `wire_extensions()` calls `_register_hook_intents(ext.provided_hook_intents())` for each extension that implements the Protocol, merging the result into the module-level `_HOOK_INTENT_REGISTRY` in `little_loops.hooks`.
- Duplicate intent names **across extensions** raise `ValueError` at wire time — first-loaded wins is not the policy; collisions are an error.
- Built-in intents (`pre_compact`, `pre_compact_handoff`, `session_start`, `session_end`, `user_prompt_submit`, `post_tool_use`, `pre_tool_use`) shadow extension-registered intents on collision: `_dispatch_table()` returns `{**_HOOK_INTENT_REGISTRY, **built_ins}`, so a built-in always wins.
- The same `little_loops.extensions` entry-point group used for `LLExtension` also discovers `LLHookIntentExtension` providers (per FEAT-1116 Decision 2 — single shared group; FEAT-1117 group-split is deferred). See [Configuration → `extensions`](CONFIGURATION.md#extensions).

**Usage:**

```python
from little_loops.hooks import LLHookEvent, LLHookResult

class MyHookIntents:
    """Extension contributing a custom 'license_check' hook intent."""

    def provided_hook_intents(self):
        return {"license_check": self._license_check}

    def _license_check(self, event: LLHookEvent) -> LLHookResult:
        if event.payload.get("license") == "GPL":
            return LLHookResult(exit_code=2, feedback="GPL files not allowed.")
        return LLHookResult(exit_code=0)
```

Register via the same `extensions` config key or entry-point group as any other `LLExtension`:

```toml
[project.entry-points."little_loops.extensions"]
my_hook_intents = "my_package:MyHookIntents"
```

After installation, `python -m little_loops.hooks license_check` dispatches to `MyHookIntents._license_check`.

### Configuration

Extensions are configured in `.ll/ll-config.json` via the `extensions` key:

```json
{
  "extensions": [
    "my_package.ext:MyExtension",
    "another_package:AnotherExtension"
  ]
}
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `extensions` | `array` of `string` | `[]` | Extension module paths to load. Format: `"module.path:ClassName"`. Extensions receive structured events from the EventBus. |

External packages can also register extensions for automatic discovery via Python entry points in `pyproject.toml`:

```toml
[project.entry-points."little_loops.extensions"]
my_ext = "my_package:MyExtension"
```

### Creating a Custom Extension

```python
from little_loops.events import LLEvent

class MyExtension:
    """Custom extension that handles issue completion events."""

    def on_event(self, event: LLEvent) -> None:
        if event.type == "issue.completed":
            print(f"Issue completed: {event.payload.get('id', 'unknown')}")
```

Register via config (`"my_package:MyExtension"`) or entry point. The class must implement `on_event(self, event: LLEvent) -> None` to satisfy the `LLExtension` protocol.

### LLTestBus

```python
from little_loops.testing import LLTestBus
```

Offline replay engine for testing `LLExtension` implementations without a running `ll-loop` or live `EventBus`. Load a JSONL events file recorded during a real run, register your extension, and call `replay()` to drive `on_event` with the recorded events. Unlike the live `EventBus`, exceptions from extensions propagate immediately so tests see raw failures.

```python
bus = LLTestBus.from_jsonl("path/to/recorded.events.jsonl")
ext = MyExtension()
bus.register(ext)
bus.replay()
assert len(bus.delivered_events) == 15
```

**Constructor:**

```python
LLTestBus(events: list[LLEvent])
```

Create from a pre-parsed list of `LLEvent` objects. Initializes `delivered_events` to an empty list.

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `delivered_events` | `list[LLEvent]` | Events delivered to at least one registered extension during the last `replay()` call. Reset at the start of each `replay()` — not accumulated across calls. |

**Class methods:**

```python
@classmethod
def from_jsonl(cls, path: str | Path) -> LLTestBus
```

Load events from a JSONL file (one JSON object per line). Returns an empty `LLTestBus` if the file does not exist. Malformed lines are silently skipped.

Each line must be a JSON object with at minimum an `"event"` key (the event type string) and a `"ts"` key (ISO 8601 timestamp). All other keys become payload attributes:

```json
{"event": "loop_start", "ts": "2025-01-01T00:00:00", "loop": "test-loop"}
{"event": "issue.closed", "ts": "2025-01-01T00:00:01", "issue": "BUG-001"}
```

**Methods:**

```python
def register(self, ext: LLExtension) -> None
```

Register an extension to receive events during `replay()`. Accepts any object implementing the `LLExtension` protocol. May be called multiple times to register multiple extensions. Extensions can optionally declare an `event_filter` class attribute (see below).

```python
def replay(self) -> None
```

Reset `delivered_events` to `[]`, then deliver all loaded events to every registered extension in order. For each event, each extension's `event_filter` attribute is checked (via `fnmatch` glob matching against the event type). If the filter matches — or if the extension has no filter — `on_event(event)` is called. An event is added to `delivered_events` if at least one extension received it. Exceptions from extensions are **not** caught and propagate immediately.

**Event filtering:**

Extensions can opt in to a subset of events by declaring `event_filter` as a class attribute:

```python
class MyExtension:
    event_filter = "issue.*"          # single glob pattern
    # event_filter = ["loop_*", "issue.*"]  # or a list of patterns
    # event_filter = None             # or absent — receives all events

    def on_event(self, event: LLEvent) -> None: ...
```

Patterns use `fnmatch` glob syntax matched against `event.type`. `None` or a missing attribute means the extension receives every event.

**Example:**

```python
from pathlib import Path
from little_loops.testing import LLTestBus

class CountingExtension:
    event_filter = "issue.*"  # only issue.* events

    def __init__(self):
        self.count = 0

    def on_event(self, event):
        self.count += 1

ext = CountingExtension()
bus = LLTestBus.from_jsonl(Path("tests/fixtures/recorded.jsonl"))
bus.register(ext)
bus.replay()
assert ext.count == 3
assert len(bus.delivered_events) == 3  # only issue.* events delivered
```

> **Tip:** The scaffold generated by `ll-create-extension` includes a starter test using `LLTestBus` in `tests/test_extension.py`.

---

## little_loops.skill_expander

Pre-expands skill and command Markdown files into self-contained prompt strings for subprocess invocation. Used by `ll-auto` to eliminate the `ToolSearch → Skill` deferred-tool round-trip when spawning Claude subprocesses.

### expand_skill

```python
def expand_skill(name: str, args: list[str], config: BRConfig) -> str | None
```

Reads the Markdown source for *name*, strips frontmatter, substitutes `{{config.xxx}}` placeholders, converts relative `(file.md)` link targets to absolute paths, replaces the `$ARGUMENTS` token with the joined *args*, and — when *args* is non-empty — appends an imperative execution directive (`IMPERATIVE_TAIL`, canonically defined here and re-exported by `little_loops.ready_issue`) stating explicitly that the expanded body is a request to act, not reference material. Without this, a long expanded skill body reads as documentation and a model can decline to act on it (see `little_loops.ready_issue` for the observed failure this was extracted from).

**Parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Skill or command name (e.g. `"manage-issue"`, `"ready-issue"`) |
| `args` | `list[str]` | Arguments that would normally follow the slash command |
| `config` | `BRConfig` | Project configuration used for `{{config.xxx}}` placeholder substitution |

**Returns**: Fully-expanded prompt string, or `None` on any failure (file not found, substitution error, etc.). Callers should fall back to the original slash command when `None` is returned.

**Resolution order**: `skills/{name}/SKILL.md` → `commands/{name}.md`

**Plugin root**: Reads `CLAUDE_PLUGIN_ROOT` env var first; falls back to the directory three levels above `skill_expander.py`.

**Example**

```python
from little_loops.config import BRConfig
from little_loops.skill_expander import expand_skill

config = BRConfig(Path.cwd())
prompt = expand_skill("ready-issue", ["FEAT-123"], config)
if prompt is None:
    prompt = "/ll:ready-issue FEAT-123"  # fallback
```

## little_loops.ready_issue

Runs `/ll:ready-issue` with containment for non-compliant model turns. Shared by `issue_manager.process_issue_inplace` (ll-auto) and `parallel.worker_pool` (ll-parallel / ll-sprint).

`parse_ready_issue_output` returns `UNKNOWN` only after five progressively looser extraction strategies fail, so `UNKNOWN` means the model did not answer the question at all — a distinct failure from a real `NOT_READY`. Collapsing the two used to discard whole runs: one observed autodev run lost 14m17s of successful refine/wire/confidence work because a single ready-issue turn replied with prose, exited 0, and parsed to `UNKNOWN`.

### run_ready_issue_with_retry

```python
def run_ready_issue_with_retry(
    *,
    target: str,
    initial_command: str,
    run: Callable[[str], subprocess.CompletedProcess[str]],
    config: BRConfig,
    retries: int = 1,
    log: Callable[[str], None] | None = None,
) -> tuple[dict[str, Any], subprocess.CompletedProcess[str]]
```

**Parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `target` | `str` | Issue ID or path — what `$ARGUMENTS` resolves to |
| `initial_command` | `str` | First-attempt command, already built by the caller |
| `run` | `Callable` | Executes a command, returns a `CompletedProcess` |
| `config` | `BRConfig` | Used to build the retry prompt |
| `retries` | `int` | Attempts allowed after an `UNKNOWN` verdict; `0` disables |
| `log` | `Callable \| None` | Optional sink for retry notices |

**Returns**: `(parsed, result)` from the final attempt, so downstream handling (path validation, corrections, CLOSE/BLOCKED/NOT_READY) runs unchanged against whichever attempt won.

**Retry contract**: retries only when `returncode == 0` **and** the verdict is `UNKNOWN`. A non-zero return code is never retried — that is a different failure mode both callers already handle. A genuine `NOT_READY` is never retried.

Configured by `automation.ready_issue_unknown_retries` (default `1`) in `.ll/ll-config.json`.

### build_retry_command

```python
def build_retry_command(target: str, config: BRConfig) -> str
```

Builds the *differentiated* retry prompt. `expand_skill` now appends the `IMPERATIVE_TAIL` directive itself whenever args are non-empty, so this is a passthrough to the pre-expanded form — always the expanded form regardless of what the first attempt used, so an ll-parallel worker that opened with the slash form still gets the hardened prompt.

Falls back to a plain `/ll:ready-issue <target>` re-roll when `expand_skill` returns `None`.

## little_loops.init.install_check

Installation detection and version-comparison helpers used by `ll-init` to detect package drift and auto-upgrade. All network calls are offline-safe: every function returns `None` on timeout, missing binary, or parse failure.

### InstallStatus

```python
class InstallStatus(Enum):
    UpToDate     = "up_to_date"
    OutOfDate    = "out_of_date"
    NotInstalled = "not_installed"
    Unknown      = "unknown"
```

### detect_installation

```python
def detect_installation(project_root: Path) -> tuple[str | None, str | None, str | None]
```

Detects the active little-loops installation. Checks pip metadata first; falls back to `<host> plugin list --json` for global/project plugin installs. The plugin-check binary is resolved via `resolve_host()` rather than a hardcoded `claude` literal (CLAUDE.md host-abstraction rule), so the check is skipped cleanly when no host CLI is configured.

**Returns**: `(install_source, installed_version, install_path)` where `install_source` is one of `"local-editable"`, `"pypi"`, `"global-claude-code"`, `"project-claude-code"`, or `None` (not found). `installed_version` is the version string for pip-based and claude-code plugin installs (populated via `--json` flag; `None` if the CLI is too old to support it). `install_path` is the `installPath` from the plugin JSON for claude-code plugin installs; `None` otherwise.

| `install_source` value | Meaning |
|------------------------|---------|
| `"local-editable"` | Installed via `pip install -e` (dev / contributor path) |
| `"pypi"` | Installed via `pip install little-loops` (end-user path) |
| `"global-claude-code"` | Installed as a user-scoped Claude Code plugin (`scope: "user"`) |
| `"project-claude-code"` | Installed as a project-scoped Claude Code plugin (`scope: "project"`) |
| `None` | Not found |

### installed_package_version

```python
def installed_package_version() -> str | None
```

Returns the installed `little-loops` package version via `importlib.metadata.version`, or `None` when the package is not installed. Single source of truth for the codex adapter gen-version stamp (written by `install_codex_adapter`) and the warn-only staleness comparison in `ll-init`.

### fetch_latest_pypi

```python
def fetch_latest_pypi(timeout: float = 10.0) -> str | None
```

Fetches the latest little-loops release version from PyPI using `pip index versions`. Parses the `LATEST:` line. Returns `None` on any failure (offline, timeout, pip not available).

### fetch_latest_plugin

```python
def fetch_latest_plugin(timeout: float = 10.0) -> str | None
```

Fetches the latest `ll@little-loops` plugin version from the Claude Code marketplace. Uses `resolve_host()` — never hardcodes the `claude` binary. Returns `None` when the host CLI is not configured or the call fails. Only meaningful when the `claude-code` host is active.

### check_version

```python
def check_version(installed: str, latest: str) -> InstallStatus
```

Compares an installed version string against the latest available version using semver-aware tuple comparison. Returns `InstallStatus.UpToDate` when `installed >= latest` (including when the local build is newer than PyPI), `InstallStatus.OutOfDate` when `installed < latest`. Does not perform network I/O; call `fetch_latest_pypi` / `fetch_latest_plugin` first.

## little_loops.advisor

Capability-rank comparison used to gate an advisor consult on model strength (FEAT-3108), plus the `consult()`/`AdvisorVerdict` accountable consult path (FEAT-3120).

### FloorResult

```python
@dataclass(frozen=True)
class FloorResult:
    status: Literal["ok", "violation", "advisory", "unknown"]
    detail: str
```

Outcome of comparing an advisor model's rank against the main model's. `"ok"` — advisor ranks at or above main, same host. `"violation"` — same host, advisor ranks below main. `"advisory"` — cross-host; capability ranks aren't comparable across hosts, so this is returned before either model's rank is even looked up. `"unknown"` — same host, but either model is unrankable; never a silent pass.

### MODEL_RANKS

```python
MODEL_RANKS: dict[str, dict[str, int]]
```

Per-host capability rank, keyed on the concrete model ID that `resolve_model_alias()` normalizes aliases to. Only `claude-code` is populated today (`claude-haiku-4-5` < `claude-sonnet-5` < `claude-opus-5` < `claude-fable-5`); every other canonical host (`codex`, `opencode`, `pi`, `gemini`, `omp`, `kimi-code`) carries an empty table until a follow-up issue supplies real capability data.

### rank_model

```python
def rank_model(host: str, model: str) -> int | None
```

Capability rank of `model` within `host`; `None` when unrankable. Normalizes `model` through `resolve_model_alias()` before lookup, so an alias (`"opus"`) and its concrete ID (`"claude-opus-5"`) rank the same.

### check_floor

```python
def check_floor(
    advisor_host: str, advisor_model: str, main_host: str, main_model: str
) -> FloorResult
```

Classifies an advisor/main model pairing against the capability floor. The cross-host check runs before rank lookup, so a host mismatch always returns `"advisory"` regardless of whether either model is individually rankable. `check_floor("claude-code", "haiku", "claude-code", "opus")` returns `"violation"`.

### AdvisorVerdict

```python
@dataclass(frozen=True)
class AdvisorVerdict:
    recommendation: str
    risks: list[str]
    confidence: float
    dissent: str
    signal: str
    host: str
    model: str
```

A structured, signal-cited consult response from the advisor host. `signal`/`host`/`model` are stamped locally by `consult()` from its own arguments and the resolved host — they are not requested from the model.

### consult

```python
def consult(
    *,
    question: str,
    signal: str,
    context: str = "",
    config: BRConfig | None = None,
    main_host: str | None = None,
    main_model: str | None = None,
) -> AdvisorVerdict
```

Issues one blocking, signal-cited consult to the configured advisor host (`config.advisor.host`/`config.advisor.model`), independent of the ambient `orchestration.host_cli` / `LL_HOST_CLI`. Gates the advisor/main pairing through `check_floor` before the transport call: a same-host `"violation"` raises `CapabilityFloorViolation` (no consult); a cross-host `"advisory"` or unrankable `"unknown"` proceeds with a warning on stderr. `context` is caller-authored — never an auto-slurp of the working tree. `main_host` defaults to the ambient `resolve_host().name`; `main_model` defaults to `fsm.schema.DEFAULT_LLM_MODEL`.

Uses the subprocess transport exclusively (`resolve_host_named` -> `HostRunner.build_blocking_json(json_schema=...)` -> `run_blocking_json`), so it structurally never touches `derive_input_hash` or `dispatch_anthropic_request` — advisor consults are excluded from FSM resume/replay input hashing and are never cache-marked, by construction. Never calls `apply_host_cli_from_config()`.

Raises `AdvisorNotConfigured` when no `advisor.host` resolves, `CapabilityFloorViolation` on a same-host floor violation, `HostNotConfigured` when the advisor host isn't registered or isn't on PATH, and `BlockingJsonError` on transport timeout/missing binary/non-zero exit/unparseable output — including a `shape_mismatch` detail flag when a host's tag-fallback parse succeeds but doesn't carry the `AdvisorVerdict` keys (never a silently defaulted verdict).

### TaskKey / ConsultBudget / ConsultOutcome (FEAT-3116)

```python
@dataclass(frozen=True)
class TaskKey:
    kind: Literal["issue", "loop_run", "session"]
    value: str

@dataclass(frozen=True)
class ConsultBudget:
    max_per_task: int
    spent: int
    task_key: TaskKey

@dataclass(frozen=True)
class ConsultOutcome:
    task_key: TaskKey
    verdict: AdvisorVerdict | None = None
    skipped_reason: Literal[
        "disabled", "trigger_not_allowed", "budget_exhausted",
        "not_configured", "floor_violation", "failed", "timeout",
    ] | None = None
    error: str | None = None
```

`TaskKey` is the stable identity a consult budget is scoped to. `ConsultOutcome` is `consult_for_trigger()`'s return type — exactly one of `verdict`/`skipped_reason` is set, never a bare `None`; `skipped_reason`'s vocabulary maps 1:1 onto FEAT-3300's `AdvisorConsultRow.outcome` enum.

### Task-identity env contract

`resolve_task_key()` reads three environment variables, in precedence order:

- `LL_ISSUE_ID` — exported by ll-auto, ll-sprint, and ll-parallel into every spawned host session for the issue being processed.
- `LL_LOOP_RUN_ID` — exported by ll-loop, set to the loop run's `instance_id`.
- `CLAUDE_SESSION_ID` — read from the injected env, falling back to `session_log.get_current_session_id()` (best-effort, the most recently modified session JSONL).

### resolve_task_key

```python
def resolve_task_key(env: dict[str, str] | None = None) -> TaskKey
```

Pure env lookup — mirrors `host_runner.resolve_host()`'s precedence-resolver shape. `env` defaults to `dict(os.environ)`. Never reads orchestrator state directly; the task-identity env contract above is the only channel.

### record_consult

```python
def record_consult(task_key: TaskKey) -> int
```

Persists and increments the consult counter for `task_key`; returns the new count. One JSON file per key at `.ll/advisor-budget/<kind>-<value>.json`, read-modify-write under `file_utils.acquire_lock()` + `atomic_write_json()` — safe across a subprocess boundary a consult from a child runner crosses.

### should_consult

```python
def should_consult(
    trigger: str, config: BRConfig, *, task_key: TaskKey | None = None, manual: bool = False,
) -> bool
```

Gate predicate: `False` when `config.advisor.enabled` is `False`, when `trigger` is not in `config.advisor.triggers`, or when the task's spent count has reached `config.advisor.max_consults_per_task`. `manual=True` (the `ll-advise` path) bypasses the `enabled` and `triggers` checks — an explicit user-requested consult is not an auto-consult — but the budget check always applies. Fail-soft: any config-read failure is caught and treated as "do not consult."

### consult_for_trigger

```python
def consult_for_trigger(
    trigger: str, *, question: str, context: str = "", config: BRConfig | None = None,
    main_host: str | None = None, main_model: str | None = None, manual: bool = False,
) -> ConsultOutcome
```

The single caller of `consult()` — no other code path may call it. Resolves the task key once, spends budget via `record_consult()` *before* the host call (reserve-before-consult: a timed-out or failed consult still spends budget, bounding retries of a hung advisor), then calls `consult()`. Never raises: `AdvisorNotConfigured`, `CapabilityFloorViolation`, `HostNotConfigured`, and `BlockingJsonError` each map to a `skipped_reason` with `error=str(exc)`, logged at warning level.

---

## little_loops.pricing

Model pricing constants (USD per million tokens) for token cost estimation across the model registry. `INTRO_PRICING` overrides `MODEL_PRICING` for a model while a time-bounded introductory rate is active (e.g. Sonnet 5's $2/$10 rate through 2026-08-31 inclusive, ENH-2835); `estimate_cost_usd()` checks `date.today()` against each entry's `expires` date and falls back to standard `MODEL_PRICING` once it lapses.

```python
from little_loops.pricing import MODEL_PRICING, INTRO_PRICING, BATCH_DISCOUNT, estimate_cost_usd
```

### MODEL_PRICING

```python
MODEL_PRICING: dict[str, dict[str, float]]
```

Per-model pricing table: `{model_id: {"input": ..., "output": ..., "cache_read": ..., "cache_creation": ...}}`, all in USD per million tokens. Covers the current Claude 5.x / 4.x model registry plus legacy 3.x models that may still appear in historical logs.

### INTRO_PRICING

```python
INTRO_PRICING: dict[str, dict[str, float | str]]
```

Time-bounded introductory rates that override `MODEL_PRICING` while active: `{model_id: {"expires": iso_date, "input": ..., "output": ..., "cache_read": ..., "cache_creation": ...}}`. Currently holds only `claude-sonnet-5`, expiring `2026-08-31`.

### BATCH_DISCOUNT

```python
BATCH_DISCOUNT = 0.5
```

Flat discount applied to all four token types under the Anthropic Message Batches API (FEAT-2710, EPIC-2456). Stacks with prompt caching since the batch discount is a flat 50% off the synchronous per-token rate, cache-adjusted rates included.

### estimate_cost_usd

```python
def estimate_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
    is_batch: bool = False,
) -> float | None
```

Estimates cost in USD for a token usage event. Returns `None` if `model` is not in `MODEL_PRICING`. Checks `INTRO_PRICING` first and uses it while unexpired, otherwise falls back to `MODEL_PRICING`. `is_batch=True` applies `BATCH_DISCOUNT` to the computed total. `is_batch` is appended at the end of the signature (not inserted) so existing positional callers (`fsm/cost_graph.py`, `session_store.py`) are unaffected.

**Parameters:**

- `model` — model ID to look up in the pricing tables.
- `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens` — token counts by type.
- `is_batch` — apply the Message Batches API flat discount.

**Returns:** estimated cost in USD, or `None` if the model is unrecognized.

---

---

## little_loops.stats

Statistical utilities for loop evaluation reporting. Provides Wilson 95% binomial confidence intervals for honest uncertainty reporting at small sample sizes, where naive ±√(p(1-p)/n) estimates are unreliable near 0 or 1.

```python
from little_loops.stats import wilson_ci
```

### wilson_ci

```python
def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]
```

Computes the Wilson binomial confidence interval: `(p + z²/2n ± z√(p(1-p)/n + z²/4n²)) / (1 + z²/n)`.

**Parameters:**

- `k` — number of successes (`0 <= k <= n`).
- `n` — total trials (`n > 0`).
- `z` — z-score for the confidence level (default `1.96` for 95% CI).

**Returns:** `(lower, upper)` bounds as floats, clamped to `[0, 1]`.

**Raises:** `ValueError` if `n <= 0`, `k < 0`, or `k > n`.

---

---

## little_loops.sft_formatter

SFT (supervised fine-tuning) data format converters used by `ll-messages --sft-format`. All three functions take the same input shape — a list of `(role, content)` turn pairs — and convert it to a different training-data wire format.

```python
from little_loops.sft_formatter import to_chatml, to_alpaca, to_sharegpt
```

### to_chatml

```python
def to_chatml(turns: list[tuple[str, str]]) -> dict
```

Converts conversation turns to ChatML format: `{"messages": [{"role": ..., "content": ...}, ...]}`.

### to_alpaca

```python
def to_alpaca(turns: list[tuple[str, str]]) -> dict
```

Converts conversation turns to Alpaca format. Maps the first user turn to `instruction`, all subsequent user turns joined with `\n\n` to `input`, and the last assistant turn to `output`.

### to_sharegpt

```python
def to_sharegpt(turns: list[tuple[str, str]]) -> dict
```

Converts conversation turns to ShareGPT format: `{"conversations": [{"from": ..., "value": ...}, ...]}`, mapping `"user"` → `"human"` and `"assistant"` → `"gpt"`.

**Parameters (all three):**

- `turns` — list of `(role, content)` pairs where `role` is `"user"` or `"assistant"`.

---

---

## little_loops.file_utils

Shared file I/O utilities: atomic writes (tempfile + `os.replace`, so readers never observe a partial file), an atomic-JSON-write helper, an issue-tree mutation lock path resolver, and an `fcntl`-based advisory file lock context manager.

```python
from little_loops.file_utils import atomic_write, atomic_write_json, issue_lock_path, acquire_lock
```

### atomic_write

```python
def atomic_write(path: Path, content: str, encoding: str = "utf-8") -> None
```

Writes `content` to `path` atomically: writes to a sibling temp file in the same directory (same filesystem), then `os.replace`s it over the target. On any exception, best-effort deletes the temp file before re-raising.

### atomic_write_json

```python
def atomic_write_json(path: Path, data: Any) -> None
```

Atomically writes `data` as JSON to `path` (Python port of `hooks/scripts/lib/common.sh:atomic_write_json`). Creates the parent directory if missing, serializes with `allow_nan=False` (rejecting NaN/Infinity like `jq empty`), round-trips through `json.loads` as a defensive check, then delegates to `atomic_write`.

**Raises:** `ValueError` if the serialized payload fails round-trip validation.

### issue_lock_path

```python
def issue_lock_path(issue_path: Path, base_dir: str = ".issues") -> Path
```

Resolves the path of the issue-tree mutation lock guarding `issue_path` (BUG-3150). Issue files live at `<base_dir>/<type>/<file>.md`, so the lock belongs on the nearest ancestor named `base_dir` — one lock for the whole tree, shared by every mutator (`set-status`, `link`, `session_log`) so they provably serialize against each other. Falls back to `issue_path`'s own resolved parent directory when no `base_dir` ancestor exists (e.g. a bare path in a scratch directory, as several tests use). Deliberately distinct from `cli/issues/create.py`'s `.id-alloc.lock` — ID allocation and issue mutation do not need to serialize against each other.

### acquire_lock

```python
@contextmanager
def acquire_lock(path: Path, timeout: float = 10.0) -> Generator[None, None, None]
```

Acquires an exclusive advisory lock on `path`, polled every 0.05s up to `timeout` seconds. Python port of `hooks/scripts/lib/common.sh:acquire_lock`. Uses `fcntl.flock(LOCK_EX | LOCK_NB)`; the lock releases automatically when the file descriptor closes on context-manager exit — no explicit release call needed. The precompact bash adapter calls this with `timeout=3.0` and falls back to a best-effort unlocked write on `TimeoutError` to preserve its existing semantics.

**Raises:** `TimeoutError` if the lock cannot be acquired within `timeout` seconds.

---

---

## little_loops.decisions_sync

Syncs the decisions log's active required rules to the `## Active Rules` section of `.ll/ll.local.md`, so local project guidance stays in sync with `.ll/decisions.yaml` / `.ll/decisions.d/` without hand-editing.

```python
from little_loops.decisions_sync import sync_to_local_md
```

### sync_to_local_md

```python
def sync_to_local_md(path: Path | None = None) -> None
```

Writes active required rules to `## Active Rules` in `ll.local.md`. `path` is the decisions YAML path (e.g. `.ll/decisions.yaml`); when omitted, resolves via `little_loops.paths.resolve_ll_dir()` (falling back to a cwd-anchored default if no project root resolves). `ll.local.md` is resolved as `path.parent / "ll.local.md"`.

Filters `list_entries(decisions_path, type="rule")` down to entries with `enforcement == "required"`, then `resolve_active()` to drop superseded/inactive ones, and renders each surviving `RuleEntry.rule` as a `- ` bullet. If `## Active Rules` already exists in the file, replaces that section in place (up to the next `##` heading or end of file); otherwise appends a new section. Writes via `little_loops.file_utils.atomic_write`.

---

---

## little_loops.output_cleaner

Anti-event + duplicate-window pre-filter for tool/log output (FEAT-2470). A LogCleaner-style pre-filter (EPIC-2456 technique [25]) that trims two kinds of avoidable token cost from tool/log output *before* it enters the model's context window:

- **Anti-events** — lines that carry no signal (tqdm/ascii progress bars, spinner frames, pytest-xdist worker chatter, bare carriage-return redraws) are dropped outright.
- **Duplicate windows** — runs of consecutive identical lines (a stack trace or warning repeated N times) collapse to a single line plus a `… (repeated N×)` marker.

Follows the module-level compiled-`re.Pattern` constant style of `little_loops.text_utils` and the single-regex ANSI-strip precedent in `little_loops.cli.output.strip_ansi`.

```python
from little_loops.output_cleaner import filter_output
```

### filter_output

```python
def filter_output(raw: str, *, dup_threshold: int = 1) -> str
```

Strips anti-event noise and collapses duplicate windows from `raw`. ANSI CSI escape sequences are stripped before matching so a colorized anti-event line still matches. Blank lines collapse to a single blank and always break a duplicate run (they never carry a `repeated N×` marker).

**Parameters:**

- `raw` — raw tool/log output.
- `dup_threshold` — emit a `… (repeated N×)` marker once a line has repeated more than this many times consecutively. The default of `1` collapses any run of ≥2 identical lines to one line + marker.

**Returns:** the cleaned text. Trailing newline presence is preserved from `raw`.

---

---

## little_loops.testing

Offline test harness for little-loops extensions. Provides `LLTestBus` — a standalone replay engine that loads a recorded `.events.jsonl` file and dispatches events through registered `little_loops.extension.LLExtension` instances without running a live loop.

```python
from little_loops.testing import LLTestBus

bus = LLTestBus.from_jsonl("path/to/recorded.events.jsonl")
bus.register(MyExtension())
bus.replay()
assert len(bus.delivered_events) == 15
assert bus.delivered_events[0].type == "loop_start"
```

### LLTestBus

```python
class LLTestBus:
    def __init__(self, events: list[LLEvent]) -> None
```

Offline event replay harness for testing `LLExtension` handlers.

**Fields:**

- `delivered_events: list[LLEvent]` — events actually delivered to at least one registered extension (i.e. events that passed the `event_filter` of any registered extension). Populated by `replay()`.

**Methods:**

- `from_jsonl(cls, path: str | Path) -> LLTestBus` (classmethod) — creates an `LLTestBus` from a JSONL events file via `EventBus.read_events`. If the file does not exist, returns an empty bus (no events, no error).
- `register(self, ext: LLExtension) -> None` — registers an extension to receive events during `replay()`. `ext` must implement the `LLExtension` protocol (`on_event`, optionally `event_filter`).
- `replay(self) -> None` — replays all loaded events through registered extensions in order. For each event, applies each extension's `event_filter` (if set) using glob matching (`fnmatch`) against `event.type`, then calls `ext.on_event(event)` for matches. `event_filter` semantics mirror `little_loops.events.EventBus`: `None`/absent delivers every event; a `str` is a single glob pattern; a `list[str]` delivers on any match. Resets and repopulates `delivered_events`.

---

---

## little_loops.ab_writer

A/B baseline results aggregation and `ab.json` writer (FEAT-1790). Provides the `ABResults` dataclass, summary-statistics calculation from per-item blind comparison records, JSON (de)serialization, and draft-07 JSON Schema generation.

```python
from little_loops.ab_writer import (
    ABResults,
    calculate_ab_summary,
    ab_results_to_dict,
    write_ab_json,
    read_ab_json,
    get_ab_schema,
)
```

### ABResults

```python
@dataclass
class ABResults:
    harness_pass_rate: float
    baseline_pass_rate: float
    delta: float
    median_tokens_harness: int
    median_tokens_baseline: int
    median_duration_harness: float
    median_duration_baseline: float
    per_item: list[dict[str, Any]] = field(default_factory=list)
```

Aggregated A/B comparison results.

**Fields:**

- `harness_pass_rate`, `baseline_pass_rate` — fraction of items where the arm passed (0-1).
- `delta` — pass-rate difference (`harness - baseline`).
- `median_tokens_harness`, `median_tokens_baseline` — median token count per arm.
- `median_duration_harness`, `median_duration_baseline` — median duration (ms) per arm.
- `per_item` — list of per-item comparison records.

### calculate_ab_summary

```python
def calculate_ab_summary(per_item_results: list[dict[str, Any]]) -> ABResults
```

Aggregates per-item verdicts into summary statistics. Each item dict is expected to carry `harness_pass`, `baseline_pass`, `harness_tokens`, `baseline_tokens`, `harness_duration_ms`, `baseline_duration_ms`. An empty `per_item_results` returns an all-zero `ABResults`. Token/duration aggregates use `statistics.median`.

### ab_results_to_dict

```python
def ab_results_to_dict(results: ABResults) -> dict[str, Any]
```

Serializes `ABResults` to the `ab.json` wire format: `{"summary": {...}, "items": results.per_item}`.

### write_ab_json

```python
def write_ab_json(results: ABResults, run_dir: str) -> None
```

Writes `ab.json` to `run_dir` (created if missing) via `ab_results_to_dict`.

### read_ab_json

```python
def read_ab_json(run_dir: str) -> ABResults | None
```

Reads `ab.json` from `run_dir`. Returns `None` if the file is missing or fails to parse (`json.JSONDecodeError`/`OSError`), or on any of the object shapes missing individual summary keys `read_ab_json` still returns a value — each summary field falls back to `0.0`/`0` via `dict.get`.

### get_ab_schema

```python
def get_ab_schema() -> dict[str, Any]
```

Returns the `ab.json` JSON Schema (draft-07): a `summary` object with required pass-rate/token/duration keys and an `items` array of per-item records (`index`, `harness_pass`, `baseline_pass`, token/duration counts per arm, plus optional `confidence`/`reason`).

---

---

## little_loops.output_parsing

Output parsing utilities for little-loops. Parses the standardized `## SECTION_NAME` markdown output format that `/ll:ready-issue` and `/ll:manage-issue` slash commands emit, used by both `issue_manager` (`ll-auto`) and `parallel` (`ll-parallel`) to extract structured verdicts and metadata from raw Claude CLI stdout.

```python
from little_loops.output_parsing import (
    extract_tagged_json,
    parse_sections,
    parse_validation_table,
    parse_status_lines,
    parse_ready_issue_output,
    parse_manage_issue_output,
    VALID_VERDICTS,
)
```

### VALID_VERDICTS

```python
VALID_VERDICTS = ("READY", "CORRECTED", "NOT_READY", "NEEDS_REVIEW", "CLOSE", "BLOCKED")
```

The verdict vocabulary recognized by `parse_ready_issue_output`.

### extract_tagged_json

```python
def extract_tagged_json(raw: str, tag: str) -> tuple[list | dict | None, str | None]
```

Extracts and parses a tagged JSON line from LLM output. Scans for the last line starting with `<tag>:` and parses the JSON after it. On a clean-parse failure, attempts bounded structural repair by balancing trailing unmatched `]`/`}` (inner-to-outer order).

**Returns:** `(data, None)` on clean parse, `(data, warning)` on successful repair, `(None, error_msg)` on unrecoverable failure. Never swallows — callers must surface the error when `data is None`.

### parse_sections

```python
def parse_sections(output: str) -> dict[str, str]
```

Parses `output` into sections delimited by `#`/`##`/`###` uppercase-with-underscores headers (flexible spacing, optional `**bold**` wrapping). Content before the first header is keyed under `"PREAMBLE"`.

### parse_validation_table

```python
def parse_validation_table(section_content: str) -> dict[str, dict[str, str]]
```

Parses a `| Check | Status | Details |` markdown table from `section_content` (typically the `VALIDATION` section) into `{check_name: {"status": ..., "details": ...}}`. Skips header/separator rows.

### parse_status_lines

```python
def parse_status_lines(section_content: str) -> dict[str, str]
```

Parses `- item: STATUS` lines from `section_content` into `{item: STATUS}` (status uppercased).

### parse_ready_issue_output

```python
def parse_ready_issue_output(output: str) -> dict[str, Any]
```

Extracts verdict and concerns from `/ll:ready-issue` output. Tries the new standardized `## VERDICT` section format first, then falls back through five additional strategies (an old `VERDICT: READY` inline format, lines mentioning "verdict", whole-output keyword scanning, artifact-cleaned whole-output scanning, and inference from a `READY_FOR` section's `Implementation: Yes` line) before giving up and returning `"UNKNOWN"`.

**Returns:** a dict with `verdict` (one of `VALID_VERDICTS` or `"UNKNOWN"`), `concerns: list[str]`, `is_ready: bool`, `was_corrected: bool`, `should_close: bool`, `is_blocked: bool`, `close_reason: str | None`, `close_status: str | None`, `corrections: list[str]`, `validated_file_path: str | None`, `sections: dict[str, str]` (raw parsed sections), and `validation: dict` (parsed `VALIDATION` table, if present).

### parse_manage_issue_output

```python
def parse_manage_issue_output(output: str) -> dict[str, Any]
```

Extracts structured data from `/ll:manage-issue` output: parses `RESULT` for a `Status: <word>` line, `FILES_CHANGED`/`FILES_CREATED`/`COMMITS` as `- ` bullet lists, `VERIFICATION` via `parse_status_lines`, and `OODA_IMPACT` as `- key: VALUE` pairs.

**Returns:** a dict with `status` (`"COMPLETED"`, `"FAILED"`, `"BLOCKED"`, or `"UNKNOWN"`), `files_changed: list[str]`, `files_created: list[str]`, `commits: list[str]`, `verification: dict[str, str]`, `ooda_impact: dict[str, str]`, and `sections: dict[str, str]` (all parsed sections).

---

## little_loops.decisions

Decisions and rules log data layer. Provides typed dataclasses and CRUD operations for managing architectural decisions, team-enforced rules, exceptions, and file-coupling rules stored in `.ll/decisions.yaml` plus its append-only `.ll/decisions.d/*.json` fragment directory.

### DecisionOutcome

```python
@dataclass
class DecisionOutcome:
    result: str
    measured_at: str
    notes: str | None = None
```

Recorded outcome for a `DecisionEntry`.

**Fields:**
- `result` — Outcome result string (e.g. pass/fail label).
- `measured_at` — Timestamp the outcome was measured.
- `notes` — Optional free-text notes; omitted from `to_dict()` output when `None`.

Also defines `from_dict(data: dict[str, Any]) -> DecisionOutcome` and `to_dict(self) -> dict[str, Any]`.

### RuleEntry

```python
@dataclass
class RuleEntry:
    id: str
    type: str = "rule"
    timestamp: str = ""
    category: str = ""
    labels: list[str] = field(default_factory=list)
    rationale: str = ""
    rule: str = ""
    enforcement: str = "advisory"
    supersedes: str | None = None
    issue: str | None = None
    source_session_id: str | None = None
    source_issue_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
```

An enforced rule in the decisions log.

**Fields:**
- `id` — Unique entry identifier.
- `type` — Always `"rule"` for this dataclass.
- `enforcement` — Enforcement level (e.g. `"advisory"`).
- `supersedes` — ID of an earlier entry this one replaces, if any; consumed by `resolve_active()`.
- `extra` — Any unrecognized keys from the source dict, round-tripped through `to_dict()`.

Also defines `from_dict(data: dict[str, Any]) -> RuleEntry` and `to_dict(self) -> dict[str, Any]`.

### DecisionEntry

```python
@dataclass
class DecisionEntry:
    id: str
    type: str = "decision"
    timestamp: str = ""
    category: str = ""
    labels: list[str] = field(default_factory=list)
    rationale: str = ""
    rule: str = ""
    alternatives_rejected: str | None = None
    issue: str | None = None
    scope: str = "issue"
    outcome: DecisionOutcome | None = None
    source_session_id: str | None = None
    source_issue_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
```

A recorded architectural or process decision.

**Fields:**
- `scope` — Decision scope, e.g. `"issue"` (the default) for a decision tied to a single issue.
- `outcome` — Optional `DecisionOutcome`, set later via `set_outcome()`.
- `issue` — Linked issue ID; `generate_from_completed()` uses this to detect issues that already have a `DecisionEntry`.

Also defines `from_dict(data: dict[str, Any]) -> DecisionEntry` and `to_dict(self) -> dict[str, Any]`.

### ExceptionEntry

```python
@dataclass
class ExceptionEntry:
    id: str
    type: str = "exception"
    timestamp: str = ""
    category: str = ""
    labels: list[str] = field(default_factory=list)
    rationale: str = ""
    rule_ref: str = ""
    issue: str = ""
    alternatives_rejected: str | None = None
    source_session_id: str | None = None
    source_issue_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
```

A one-time exception to an existing rule.

**Fields:**
- `rule_ref` — ID of the `RuleEntry` this exception applies against.
- `issue` — Issue justifying the exception (required, not optional, unlike other entry types).

Also defines `from_dict(data: dict[str, Any]) -> ExceptionEntry` and `to_dict(self) -> dict[str, Any]`.

### CouplingEntry

```python
@dataclass
class CouplingEntry:
    id: str
    type: str = "coupling"
    timestamp: str = ""
    category: str = ""
    labels: list[str] = field(default_factory=list)
    rationale: str = ""
    if_changed: str = ""
    then_check: list[str] = field(default_factory=list)
    tier: str = "soft"  # hard | soft | fyi
    archetype: str | None = None
    enforcement: str = "advisory"
    supersedes: str | None = None
    issue: str | None = None
    source_session_id: str | None = None
    source_issue_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
```

A coupling rule linking changed files to required audit targets, consumed by wire-issue.

**Fields:**
- `if_changed` — Glob pattern matched against changed files (via `fnmatch`).
- `then_check` — List of things to check/audit when `if_changed` matches.
- `tier` — One of `"hard"`, `"soft"`, or `"fyi"`.
- `archetype` — Optional archetype filter, matched by `load_coupling_entries()`.

Also defines `from_dict(data: dict[str, Any]) -> CouplingEntry` and `to_dict(self) -> dict[str, Any]`.

### load_decisions

```python
def load_decisions(path: Path | None = None) -> list[AnyEntry]
```

Loads all decision log entries as one logical log (flat file ∪ fragments). Presents the legacy flat `entries:` list (or bare top-level list) *plus* every `.ll/decisions.d/*.json` fragment as a single merged list. The flat file is still parsed strictly (malformed YAML / missing `id` / unknown `type` raise, preserving ENH-2589 corruption gating); malformed *fragments* are skipped (BUG-2644). Returns an empty list when neither source exists.

**Parameters:**
- `path` — Explicit path to the flat `decisions.yaml`; when `None`, resolved via `resolve_ll_dir()` (project root), falling back to a cwd-anchored `_DEFAULT_LOG_PATH` (`.ll/decisions.yaml`) if no project root is found.

**Returns:** Merged list of `AnyEntry` (`RuleEntry | DecisionEntry | ExceptionEntry | CouplingEntry`), flat-file entries followed by fragment entries sorted by `(timestamp, filename)`.

### save_decisions

```python
def save_decisions(entries: list[AnyEntry], path: Path | None = None) -> None
```

Atomically persists entries to the flat YAML file and compacts fragments. Rewrites the whole flat file (the pre-BUG-2644 behavior). Because `entries` is normally the *union* view (flat ∪ fragments) obtained from `load_decisions()`, any fragments are now folded into the flat file, so the fragment directory is cleared afterward to keep a subsequent load from double-counting. This makes `save_decisions()` the compaction point; ordinary appends go through `add_entry()` and never rewrite the flat file.

**Parameters:**
- `entries` — Full entry list to persist (typically the result of `load_decisions()`).
- `path` — Flat-file path; resolved the same way as `load_decisions()` when `None`.

**Returns:** `None`. Deletes all `*.json` fragments under the sibling `.d` directory after writing.

### add_entry

```python
def add_entry(entry: AnyEntry, path: Path | None = None) -> None
```

Appends a new entry as its own fragment file (append-only, no rewrite). Writes one `.ll/decisions.d/<uuid>.json` fragment rather than rewriting the whole flat file, so concurrent appends from divergent branches never touch the same file region and merge cleanly (BUG-2642 / BUG-2644).

**Parameters:**
- `entry` — One `AnyEntry` to append.
- `path` — Flat-file path used to derive the sibling fragment directory (`.d` suffix).

**Returns:** `None`.

### update_entry

```python
def update_entry(
    entry_id: str,
    mutate: Callable[[AnyEntry], AnyEntry],
    path: Path | None = None,
) -> None
```

Updates a single decision entry in place, preserving fragment isolation. Locates the entry whose `id` matches `entry_id` (fragments searched first, in filename order, then the flat file), applies `mutate` to it, and persists only the one file backing it — never rewrites the whole log or clears the fragment directory.

**Parameters:**
- `entry_id` — ID of the entry to update.
- `mutate` — Callable that receives the current entry and returns the updated entry.
- `path` — Flat-file path; resolved the same way as `load_decisions()` when `None`.

**Returns:** `None`. Raises `KeyError` if no entry with `entry_id` exists in either source. Any exception raised by `mutate` propagates before any write occurs.

### list_entries

```python
def list_entries(
    path: Path | None = None,
    *,
    type: str | None = None,
    category: str | None = None,
    label: str | None = None,
) -> list[AnyEntry]
```

Returns entries, optionally filtered by type, category, or label.

**Parameters:**
- `path` — Flat-file path passed through to `load_decisions()`.
- `type` — Filter to entries whose `type` matches exactly (e.g. `"rule"`, `"decision"`).
- `category` — Filter to entries whose `category` matches exactly.
- `label` — Filter to entries whose `labels` list contains this value.

**Returns:** Filtered list of `AnyEntry`.

### resolve_active

```python
def resolve_active(entries: list[AnyEntry]) -> list[AnyEntry]
```

Returns entries excluding those superseded by a newer entry. An entry is inactive if another entry's `supersedes` field references its ID.

**Parameters:**
- `entries` — Entry list to filter (typically from `load_decisions()`).

**Returns:** Entries whose `id` is not referenced by any other entry's `supersedes` field.

### set_outcome

```python
def set_outcome(
    entry_id: str,
    result: str,
    measured_at: str,
    notes: str | None = None,
    path: Path | None = None,
    *,
    force: bool = False,
) -> None
```

Sets the outcome on a decision entry; refuses to overwrite without `force=True`. Mutates only the single fragment (or flat-file entry) backing `entry_id` via `update_entry()` — sibling fragments are untouched, so a concurrent append on another branch never collides (BUG-2645).

**Parameters:**
- `entry_id` — ID of the `DecisionEntry` to set an outcome on.
- `result` — Outcome result string.
- `measured_at` — Timestamp the outcome was measured.
- `notes` — Optional free-text notes.
- `path` — Flat-file path, forwarded to `update_entry()`.
- `force` — When `False` (default), raises `ValueError` if the entry already has an outcome.

**Returns:** `None`. Raises `TypeError` if the resolved entry is not a `DecisionEntry`.

### load_coupling_entries

```python
def load_coupling_entries(
    path: Path | None = None,
    *,
    changed_globs: list[str] | None = None,
    archetype: str | None = None,
) -> list[CouplingEntry]
```

Returns coupling entries, optionally filtered by glob match against changed files and archetype. Returns an empty list when `decisions.yaml` is absent (graceful degradation).

**Parameters:**
- `path` — Flat-file path, forwarded to `load_decisions()`.
- `changed_globs` — When given, keeps only entries whose `if_changed` glob matches at least one of these file paths (via `fnmatch`).
- `archetype` — When given, keeps only entries whose `archetype` matches exactly.

**Returns:** Filtered list of `CouplingEntry`.

### generate_from_completed

```python
def generate_from_completed(config: BRConfig) -> int
```

Generates `DecisionEntry` records from completed issues and persists them to the log. Prefers the SQLite history DB when present; falls back to filesystem scanning. Skips issues that already have an entry in the log. When `config.decisions.auto_generate` is non-empty, only issues whose type prefix appears in the list are processed (e.g. `["FEAT", "ENH"]` skips BUG entries).

**Parameters:**
- `config` — `BRConfig` instance; uses `config.project_root`, `config.decisions.log_path`, `config.decisions.auto_generate`, and `config.issues.base_dir`.

**Returns:** Number of `DecisionEntry` records added. Reads completed issues from `<project_root>/.ll/history.db` (via `scan_completed_issues_from_db()`) when present, otherwise scans the issues directory (via `scan_completed_issues()`). Each generated entry has `id` set to `f"DEC-{issue.issue_id}"`, `category` set to the lowercased issue type, and `labels` set to `[priority, issue_type.lower()]`; new entries are persisted via `add_entry()` (fragment-append, not a flat-file rewrite).

---

## little_loops.subprocess_utils

Subprocess utilities for Claude CLI invocation. Provides shared functionality for running Claude CLI commands with real-time output streaming, timeout handling, and context handoff detection.

### TokenUsage

Token usage from a single host-CLI invocation. Passed to `DetailedUsageCallback` / `on_usage_detailed`.

```python
@dataclass
class TokenUsage:
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    model: str
    is_batch: bool = False
```

**Fields:**

| Field | Type | Default | Description |
|---|---|---|---|
| `input_tokens` | `int` | *(required)* | Input tokens from the stream-json `result` event's `usage` block. |
| `output_tokens` | `int` | *(required)* | Output tokens from the same `usage` block. |
| `cache_read_tokens` | `int` | *(required)* | `cache_read_input_tokens` from `usage`. |
| `cache_creation_tokens` | `int` | *(required)* | `cache_creation_input_tokens` from `usage`. |
| `model` | `str` | *(required)* | Model ID reported by the `result` event, falling back to the model detected from the earlier `system`/`init` event. |
| `is_batch` | `bool` | `False` | True when this usage came from the Message Batches API (FEAT-2716), eligible for the flat 50% batch discount in `little_loops.pricing.estimate_cost_usd`. Defaults to `False` so every existing construction site is unaffected. |

### ToolCall

A single ordered tool-call captured live from a stream-json run. Mirrors `scripts/tests/spike/eval_trace_capture/trace_capture.py`'s `ToolCall` shape, proven in the FEAT-2878 spike.

```python
@dataclass(frozen=True)
class ToolCall:
    index: int
    name: str
    input: dict[str, object]
```

**Fields:**

| Field | Type | Description |
|---|---|---|
| `index` | `int` | The call's 0-based position in the ordered trace for this invocation. |
| `name` | `str` | Tool name from the `tool_use` block. |
| `input` | `dict[str, object]` | Tool input payload from the `tool_use` block. |

**Behavior:** Passed to `ToolCallCallback` / `on_tool_call`, invoked live, once per ordered `tool_use` block parsed out of an `assistant` stream-json event, so a caller can build/assert an ordered tool-call trace during a run instead of only reconstructing it post-hoc from on-disk JSONL logs.

### detect_context_handoff

```python
def detect_context_handoff(output: str) -> bool
```

**Parameters:**
- `output` — Command output to check.

**Returns:** `True` if `output` matches `CONTEXT_HANDOFF_PATTERN` (`CONTEXT_HANDOFF:\s*Ready for fresh session`).

### read_continuation_prompt

```python
def read_continuation_prompt(repo_path: Path | None = None) -> str | None
```

**Parameters:**
- `repo_path` — Optional repository root path; defaults to `Path.cwd()`.

**Returns:** Contents of `<repo_path>/.ll/ll-continue-prompt.md` (`CONTINUATION_PROMPT_PATH`), or `None` if the file does not exist.

### read_sentinel

```python
def read_sentinel(repo_path: Path | None = None) -> dict | None
```

Reads and consumes the context-handoff sentinel file if it exists. The sentinel is written by `context-handoff-sentinel.sh` (Stop hook) or the Python layer in `run_with_continuation` when a session ends with high context usage but no `CONTEXT_HANDOFF` signal.

**Parameters:**
- `repo_path` — Optional repository root path; defaults to `Path.cwd()`.

**Returns:** Parsed JSON dict from `<repo_path>/.ll/ll-context-handoff-needed` (`SENTINEL_PATH`), or `None` if the file is absent.

**Behavior:** Consumes the sentinel — the file is unlinked (`missing_ok=True`) whether the read succeeds or the JSON fails to parse. On a parse/read exception, still unlinks the file and returns `{}` rather than `None`, so callers can distinguish "sentinel present but unreadable" from "no sentinel at all."

### write_sentinel

```python
def write_sentinel(
    repo_path: Path | None = None,
    token_count: int = 0,
    context_limit: int | None = None,
) -> None
```

**Parameters:**
- `repo_path` — Optional repository root path; defaults to `Path.cwd()`.
- `token_count` — Total tokens used in the session. Default `0`.
- `context_limit` — Context window size; when `None`, resolved via `context_window_for(None)`.

**Behavior:** Writes a JSON payload (`written_at`, `token_count`, `context_limit`, `usage_percent`) to `SENTINEL_PATH`, creating parent directories as needed. `usage_percent` is `int(token_count * 100 / context_limit)` (0 if `context_limit <= 0`). Swallows all exceptions silently — a failed sentinel write must not crash the caller.

### assemble_guillotine_prompt

```python
def assemble_guillotine_prompt(
    original_command: str,
    captured_stdout: str,
    token_stats: dict,
    sprint_context: SprintWorkerContext | None = None,
    issue_id: str | None = None,
) -> str
```

Assembles a fresh-session continuation prompt for Option J (parent-side guillotine). Called when context > 90% or "Prompt is too long" is detected with no handoff. The resulting prompt is passed to a brand-new `claude -p` session (not `--resume`), so it starts with 0 tokens.

**Parameters:**
- `original_command` — The original task command / skill invocation. Truncated to the first `_GUILLOTINE_MAX_TASK_LINES` (20) lines, with a truncation note appended if longer.
- `captured_stdout` — All Claude text output captured so far. Only the trailing `_GUILLOTINE_TAIL_CHARS` (12,000) characters are included; empty capture renders as `"(no output captured before interruption)"`.
- `token_stats` — Dict with keys `input_tokens`, `output_tokens`, `context_limit` (falls back to `context_window_for(None)` if falsy), and optional `trigger_reason` (defaults to `"context > 90%"`).
- `sprint_context` — Optional `SprintWorkerContext`; when present, prepends a "Sprint Worker Context" framing block scoping the fresh session to exactly `sprint_context.issue_id` on `sprint_context.branch`.
- `issue_id` — Optional issue ID; when `sprint_context` is `None` and this is set, prepends a "Scope Constraint" framing block scoping the fresh session to exactly that one issue. Ignored if `sprint_context` is provided.

**Returns:** Assembled continuation prompt string, including a scratch-pad file listing (`.loops/tmp/scratch/`) and numbered instructions for the fresh session to continue from the interruption point rather than restarting.

### run_claude_command

```python
def run_claude_command(
    command: str,
    timeout: int = 3600,
    working_dir: Path | None = None,
    stream_callback: OutputCallback | None = None,
    on_process_start: ProcessCallback | None = None,
    on_process_end: ProcessCallback | None = None,
    *,
    on_model_detected: ModelCallback | None = None,
    on_usage: UsageCallback | None = None,
    on_usage_detailed: DetailedUsageCallback | None = None,
    agent: str | None = None,
    tools: list[str] | None = None,
    resume_session: bool = False,
    model: str | None = None,
    automation: AutomationContext | None = None,
    post_stream_close_grace_seconds: int = 300,
    timeout_kill_grace_seconds: float = 0.0,
    on_result_seen: ResultSeenCallback | None = None,
    on_session_id_detected: SessionIdCallback | None = None,
    on_tool_call: ToolCallCallback | None = None,
    workspace_root: Path | None = None,
) -> subprocess.CompletedProcess[str]
```

Invokes the Claude CLI command with real-time output streaming.

> **Breaking change (ENH-3261):** the `automation_profile`/`disable_background_tasks`/`idle_timeout` legacy kwargs were removed from this signature. Callers must pass `automation=AutomationContext(profile=..., disable_background_tasks=..., idle_timeout=...)` instead. Every parameter from `on_model_detected` onward is now keyword-only.

**Parameters:**
- `command` — Command to pass to the Claude CLI.
- `timeout` — Wall-clock timeout in seconds (`0` for no timeout). Default `3600`.
- `working_dir` — Optional working directory for the subprocess.
- `stream_callback` — Called with `(line, is_stderr)` for each line of output.
- `on_process_start` — Invoked after the process starts, receiving the `Popen` object.
- `on_process_end` — Invoked after the process completes (in a `finally` block), receiving the `Popen` object.
- `on_model_detected` — Invoked at most once with the model name from the stream-json `system`/`init` event.
- `on_usage` — Invoked with `(input_tokens, output_tokens)` from the stream-json `result` event; `input_tokens` includes `cache_read_input_tokens`. Kept for back-compat with `issue_manager.py` and `worker_pool.py` callers.
- `on_usage_detailed` — Invoked with a `TokenUsage` carrying all four token fields plus the model ID from the `result` event.
- `agent` — Optional agent/persona selector forwarded to `build_streaming()`.
- `tools` — Optional tool allowlist forwarded to `build_streaming()`.
- `resume_session` — If `True`, passes `--continue` (via `build_streaming(resume=...)`) to continue the most recent conversation. Used for the Option E explicit-handoff path.
- `model` — Optional model override forwarded to `build_streaming()`.
- `automation` (ENH-3097) — Collapsed automation signal (`profile`, `disable_background_tasks`, `idle_timeout`), forwarded as `automation=` alone into `build_streaming()`. `None` disables automation entirely.
- `post_stream_close_grace_seconds` — Grace period (seconds) to wait for the process to exit on its own after stdout/stderr streams close before force-killing the process group. Must accommodate synchronous parallel Agent tool calls (`run_in_background: false`) that can still be running when the parent's own streams close (BUG-2718). Default `300`.
- `timeout_kill_grace_seconds` — Grace period (seconds) given to the process group after a wall-clock or idle timeout fires: SIGTERM is sent first, and SIGKILL only follows if the group is still alive after this many seconds. `0` (default) preserves the historical immediate-SIGKILL behavior (ENH-3130).
- `on_result_seen` — Invoked once, right before return, with whether a stream-json `result` event was observed (BUG-2731). Lets callers distinguish an exit-143-after-result infra teardown (re-runnable) from a genuine mid-turn crash, without widening this function's `CompletedProcess` return type.
- `on_session_id_detected` — Invoked with the host CLI's `session_id` from the stream-json `system`/`init` event (FEAT-2711). Called at most once per invocation, alongside `on_model_detected`.
- `on_tool_call` — Invoked live, once per ordered `tool_use` block parsed out of an `assistant` stream-json event (FEAT-2878). Lets a caller build/assert an ordered tool-call trace (name, order, input) during the run, instead of only reconstructing it post-hoc from on-disk JSONL logs.
- `workspace_root` — Optional path forwarded to `build_streaming()` to request that tool access be confined to that directory (FEAT-2878). Only honored by hosts advertising `HostCapabilities.workspace_sandboxed` — see that flag's docstring for the current support matrix.

**Returns:** `subprocess.CompletedProcess[str]` with joined `stdout`/`stderr` captured from the parsed stream-json events (or raw text for non-JSON lines).

**Raises:**
- `subprocess.TimeoutExpired` — if the command exceeds `timeout` or `idle_timeout`. When triggered by idle timeout, the `output` field is set to `"idle_timeout"`.

**Behavior:**
- Resolves a `HostRunner` via `resolve_host()` and builds the invocation with `runner.build_streaming(...)`, then spawns it with `subprocess.Popen(..., start_new_session=True)` so `_kill_process_group()` can `os.killpg` the whole process group (including inherited background Task/Workflow children) on timeout or teardown.
- Reads stdout/stderr non-blockingly via `selectors.DefaultSelector`, parsing each stdout line as a stream-json event:
  - `system`/`init` — captures the detected model (`on_model_detected`) and session id (`on_session_id_detected`); not added to `stdout_lines`.
  - `assistant` — extracts `text` blocks into `stdout_lines`/`stream_callback`, and emits a `ToolCall` per `tool_use` block via `on_tool_call`.
  - `result` — the canonical end-of-turn signal (`result_seen = True`); reports usage via `on_usage`/`on_usage_detailed`, appends an `[result] ...` line to `stderr_lines` if `is_error` is set, then the read loop drains the current ready batch and breaks — it does **not** wait for pipe EOF, because inherited background-task file descriptors can keep the pipe open indefinitely even after the turn finished.
  - Non-JSON lines pass through as raw text to `stdout_lines`/`stderr_lines`.
- On process spawn failure, returns a `CompletedProcess` with `returncode=1` and the exception message in `stderr` rather than raising.
- After the read loop exits, waits up to `post_stream_close_grace_seconds` for natural process exit, then force-kills via `_kill_process_group()` if still alive.
- `on_process_end` and `on_result_seen` always fire (the former in a `finally` block) even on timeout paths.

---

## little_loops.worktree_utils

Shared git worktree setup and cleanup utilities. Used by `ll-parallel`, `ll-sprint`, and `ll-loop` to create and remove isolated git worktrees with consistent file-copy behavior, by the FSM executor's pre-patch check hook (ENH-2997), and by `work_verification`'s non-FSM pre-patch check adapter (ENH-2998). The file-copy contract these functions implement is documented in [WORKTREES.md](WORKTREES.md).

### detect_default_branch

```python
def detect_default_branch(repo_path: Path, git_lock: GitLock | None = None) -> str
```

Resolves the repository's default/integration branch (BUG-2323). Resolution order: (1) `origin/HEAD` symbolic ref, stripped of its `origin/` prefix; (2) the current branch via `git rev-parse --abbrev-ref HEAD`, only when it is a real branch name (not the literal `HEAD` from a detached HEAD); (3) `"main"` as a last resort.

**Parameters:**
- `repo_path` — Path to the repository to inspect.
- `git_lock` — Optional thread-safe git lock. Pass the orchestrator's lock when calling mid-run (serializes with concurrent checkout/pull); leave as `None` at CLI startup, before the orchestrator exists.

**Returns:** The detected branch name. Never returns the literal `"HEAD"`.

### resolve_epic_base

```python
def resolve_epic_base(
    epic_id: str,
    base_branch: str,
    repo_path: Path | None = None,
    config: object | None = None,
) -> str
```

Returns the fork base for an EPIC integration branch (ENH-2656, FEAT-2652). Single source of truth for the EPIC fork point. When the EPIC declares a per-EPIC `base_branch:` (alias `target_branch:`) in its frontmatter, that ref is preferred; otherwise the caller's default `base_branch` is returned verbatim. The per-EPIC lookup is gated on `repo_path`: when it is `None`, the function short-circuits to `base_branch` without touching disk, preserving the original two-arg contract for callers (and unit tests) that cannot or need not scan `.issues/`.

**Parameters:**
- `epic_id` — The EPIC issue id (e.g. `"EPIC-2451"`).
- `base_branch` — The default fork base the caller resolved.
- `repo_path` — Repository root to scan for the EPIC's issue file. When `None`, no lookup is performed.
- `config` — An optional `BRConfig` for the `IssueParser`. Built from `repo_path` when omitted.

**Returns:** The branch to fork the EPIC integration branch from — the EPIC's declared `base_branch` when present, else the passed `base_branch`.

### resolve_epic_branch_name

```python
def resolve_epic_branch_name(epic_id: str, prefix: str, slug: str) -> str
```

Returns the EPIC integration branch name (ENH-2656). Single source of truth for the `<prefix><epic-id-lower>-<slug>` format, deduplicating a pattern previously hand-written at three call sites (`worker_pool._resolve_branch_targets`, `orchestrator._inspect_worktree`, and the `checkout_epic_branch` FSM heredoc).

**Parameters:**
- `epic_id` — The EPIC issue id (e.g. `"EPIC-2451"`); lower-cased into the name.
- `prefix` — The `epic_branches.prefix` config value (e.g. `"epic/"`).
- `slug` — The EPIC title slug (or the EPIC id lower-cased as a fallback).

**Returns:** The integration branch name, e.g. `"epic/epic-2451-my-title"`.

### setup_worktree

```python
def setup_worktree(
    repo_path: Path,
    worktree_path: Path,
    branch_name: str,
    copy_files: list[str],
    logger: Logger,
    git_lock: GitLock,
    base_branch: str | None = None,
    checkout_existing: bool = False,
) -> None
```

Creates a git worktree and copies essential files. Copies the `.claude/` directory (so Claude Code can detect the project root, BUG-007) and any additional files listed in `copy_files`, then writes a `.ll-session-<pid>` marker so orphan-cleanup routines can identify this process's worktrees. If `worktree_path` already exists, it is torn down via `cleanup_worktree` first.

**Parameters:**
- `repo_path` — Path to the main repository.
- `worktree_path` — Destination path for the new worktree.
- `branch_name` — Name of the branch. By default a *new* branch created via `git worktree add -b`. When `checkout_existing` is `True`, it names an *already-existing* branch checked out in place instead (no new branch is created, and no branch is deleted when this worktree is later torn down for it).
- `copy_files` — File paths (relative to `repo_path`) to copy into the worktree.
- `logger` — Logger instance.
- `git_lock` — Thread-safe git lock for serializing repo operations.
- `base_branch` — Optional commit-ish to fork the new branch from. When `None`, forks from the current HEAD of `repo_path`. When provided, validated via `git rev-parse --verify` before use. Mutually exclusive with `checkout_existing`.
- `checkout_existing` — When `True`, check out `branch_name` (which must already exist) instead of creating a new branch.

**Raises:**
- `ValueError` — If both `base_branch` and `checkout_existing` are given.
- `RuntimeError` — If git worktree creation fails, or `base_branch` does not resolve.

**Behavior:**
- BUG-3112: resolves the main repo's history DB while `cwd` is still the main repo and exports it as `LL_HISTORY_DB` (via `os.environ.setdefault`) so every descendant process — host-CLI sessions, FSM shell actions, hooks, pytest runs — resolves the shared DB instead of creating a throwaway `<worktree>/.ll/history.db` that teardown deletes.
- Copies `user.email`/`user.name` git config from `repo_path` into the new worktree so commits made there have the right author.

### cleanup_worktree

```python
def cleanup_worktree(
    worktree_path: Path,
    repo_path: Path,
    logger: Logger,
    git_lock: GitLock,
    delete_branch: bool = True,
) -> None
```

Removes a git worktree and optionally its associated branch. No-op if `worktree_path` does not exist. Before removal, calls `preserve_before_teardown()` (from `little_loops.git_operations`) to snapshot any non-noise uncommitted work to a durable ref — `git worktree remove --force` discards uncommitted changes unconditionally, but the snapshot ref survives because worktrees share the main repo's object database and ref store (BUG-2963 #8). Runs `git worktree unlock` then `git worktree remove --force`, falling back to `shutil.rmtree` if the directory still exists afterward.

**Parameters:**
- `worktree_path` — Path to the worktree to remove.
- `repo_path` — Path to the main repository.
- `logger` — Logger instance.
- `git_lock` — Thread-safe git lock for serializing repo operations.
- `delete_branch` — If `True`, detect (via `git rev-parse --abbrev-ref HEAD` in the worktree, before removal) and delete the worktree's branch after removal.

### setup_prepatch_worktree

```python
def setup_prepatch_worktree(
    repo_path: Path,
    worktree_base: str | Path,
    base_ref: str,
    test_files: dict[str, str],
    logger: Logger,
    git_lock: GitLock,
    src_dir: str | None = None,
) -> Path
```

Forks a worktree at `base_ref` and writes pre-patch test content into it (ENH-3141). Additive sibling of `setup_worktree()` for ENH-2991's pre-patch check core: forks a worktree at an arbitrary base ref via `setup_worktree()`'s existing `base_branch` param, then materializes caller-supplied test-file content directly into the fork via `Path.write_text()` — there is no patch-parsing, 3-way-merge, or reject-hunk handling; `test_files` is the literal content written at each path. The forked branch is named `prepatch-<YYYYMMDD>-<HHMMSS>-<microseconds>`.

**Parameters:**
- `repo_path` — Path to the main repository.
- `worktree_base` — Directory (relative to `repo_path`) to create the scratch worktree under. Should be gitignored (e.g. `".worktrees"`) so the fork sits outside `tamper_guard_changed_files()`'s repo-root scan scope.
- `base_ref` — Commit-ish to fork the pre-patch worktree from.
- `test_files` — Repo-relative path → content, written directly into the fork after creation. Same shape as `read_paths_at_ref()`'s return value.
- `logger` — Logger instance.
- `git_lock` — Thread-safe git lock for serializing repo operations.
- `src_dir` — When provided, validated to exist in the forked worktree so callers can safely prepend `<worktree_path>/<src_dir>` onto `PYTHONPATH` (mirroring `verify_epic_branch_before_merge()`'s `src_dir` injection, BUG-2629) before running tests — that subprocess/env construction is caller-side; this function only forks and materializes content.

**Returns:** Path to the created pre-patch worktree.

**Raises:**
- `RuntimeError` — If worktree creation fails, `base_ref` does not resolve, or `src_dir` is given but absent from the forked tree. On error, the worktree (if created) is torn down via `cleanup_worktree` before the error propagates; the main repository's working tree is never touched.

### format_verify_detail

```python
def format_verify_detail(
    stdout: str | None,
    stderr: str | None,
    *,
    max_lines: int = 40,
    max_chars: int = 2000,
) -> str
```

Captures the diagnostic *tail* of a failed verify command (ENH-2641). Combines both streams in `stderr + stdout` order (matching the `merge_coordinator.py` idiom) so stdout — which carries pytest's `=== short test summary info ===` / `FAILED …` lines — lands at the tail rather than being dropped, then keeps the last `max_lines` lines bounded to `max_chars` (mirrors the scrollback cap in `cli/loop/_helpers.py`). Fixes BUG-2640, where the prior first-500-char prefix of `stderr or stdout` preferred stderr (pytest-benchmark/xdist warning banners) and clipped its head, losing the real failure summary.

**Returns:** The bounded diagnostic tail string.

### verify_epic_branch_before_merge

```python
def verify_epic_branch_before_merge(
    epic_id: str,
    epic_branch: str,
    *,
    verify_before_merge: bool,
    repo_path: Path,
    worktree_base: str | Path,
    test_cmd: str | None,
    lint_cmd: str | None,
    logger: Logger,
    git_lock: GitLock,
    src_dir: str | None = None,
) -> tuple[bool, str | None, int | None]
```

Runs `test_cmd`/`lint_cmd` against an EPIC branch tip before merge/PR (ENH-2603, BUG-2614). Stateless free-function extraction of `ParallelOrchestrator`'s `_verify_epic_branch_before_merge`, shared by `WorkerPool`-based runs and the FSM `auto-refine-and-implement` loop. Checks out `epic_branch` in a scratch worktree under `worktree_base` (via `setup_worktree(..., checkout_existing=True)`), runs `test_cmd` and (if set) `lint_cmd` against it, and always tears the worktree down in a `finally` block regardless of outcome (`cleanup_worktree(..., delete_branch=False)`).

**Parameters:**
- `epic_id` — The EPIC issue ID, used for logging and the scratch worktree name.
- `epic_branch` — Name of the EPIC integration branch to verify.
- `verify_before_merge` — When `False`, returns `(True, None, None)` immediately without doing any work.
- `repo_path` — Path to the main repository.
- `worktree_base` — Directory (relative to `repo_path`) to create the scratch worktree in.
- `test_cmd` — Shell command to run as the test gate, or `None` to skip.
- `lint_cmd` — Shell command to run as the lint gate, or `None` to skip.
- `logger` — Logger instance.
- `git_lock` — Thread-safe git lock for serializing repo operations.
- `src_dir` — When truthy, the source directory (relative to the branch worktree, e.g. `"scripts"`) whose absolute path is prepended to `PYTHONPATH` for the test/lint subprocess. Defeats editable-install `.pth` shadowing (BUG-2629): the editable `_editable_impl_*.pth` hardcodes the main checkout's source dir at interpreter startup regardless of `cwd`, so `import little_loops.<branch_only_module>` would otherwise resolve to the main tree and fail collection. `.pth` entries land on `sys.path` after `PYTHONPATH`, so the prepend wins.

**Behavior:**
- The test/lint subprocess always runs with `LL_VERIFY_GATE="1"` in its environment (BUG-2649), independent of `src_dir`, so tests non-deterministic under the gate's non-standard invocation (injected `PYTHONPATH` + parallel-xdist worktree) can detect and quarantine themselves.
- Also sets `PYTEST_XDIST_AUTO_NUM_WORKERS` (default `max(2, cpu_count // 4)`, via `setdefault`) to cap nested pytest-xdist worker counts across concurrent verify gates, and `LL_FUZZ=full` (via `setdefault`) so the enforced gate always fuzzes at full depth.

**Returns:** `(ok, message, returncode)`. `(True, None, None)` if the gate passed or was disabled. `(False, message, returncode)` if worktree setup or a configured command failed — `message` describes the failure and `returncode` is the failing process's exit code (`None` for a worktree-setup failure, which never ran a command). ENH-2631: the exit code lets callers distinguish a pytest collection/usage error (exit 2, a harness/env problem — BUG-2629) from a real test failure (exit 1) without re-running the suite.

### merge_epic_branch_to_base

```python
def merge_epic_branch_to_base(
    epic_id: str,
    epic_branch: str,
    *,
    base_branch: str,
    repo_path: Path,
    logger: Logger,
    git_lock: GitLock,
    run_dir: Path | None = None,
) -> bool
```

Merges `epic_branch` into `base_branch` (via `git merge --no-ff`) then deletes it (FEAT-2449, BUG-2614). Stateless free-function extraction of `ParallelOrchestrator`'s `_merge_epic_branch_to_base`. Assumes `repo_path`'s working tree is already checked out on (or fast-forwardable to) `base_branch` — no checkout is performed here. Never raises; unexpected errors are caught and logged.

**Parameters:**
- `epic_id` — The EPIC issue ID, used in the merge commit message and logs.
- `epic_branch` — Name of the EPIC integration branch to merge and delete.
- `base_branch` — Branch to merge into.
- `repo_path` — Path to the repository, checked out on `base_branch`.
- `logger` — Logger instance.
- `git_lock` — Thread-safe git lock for serializing repo operations.
- `run_dir` — When non-`None`, the per-run directory to persist a merge-failure diagnostic into (ENH-2643). On failure, before `git merge --abort` discards the conflict state, three flat-text artifacts are written: `merge-returncode.txt` (the failing `git merge` exit code), `merge-detail.txt` (the bounded `stderr + stdout` tail via `format_verify_detail`), and `merge-conflicts.txt` (the conflicted-path list from `git diff --name-only --diff-filter=U`). When `None` (the parallel-orchestrator caller, which has no per-run `run_dir`), nothing is persisted.

**Returns:** `True` if the merge succeeded (and the branch was deleted), `False` on merge failure or an unexpected error.

### ensure_epic_branch

```python
def ensure_epic_branch(
    branch: str,
    base: str,
    *,
    repo_path: Path,
    git_lock: GitLock,
    logger: Logger,
    remote_name: str,
    refresh_on_reuse: str,
    run_dir: Path | None = None,
) -> EpicBranchStatus
```

Lazily creates `branch` off `base`, guarding a **local-hit reuse** against staleness relative to `base` (ENH-3302). Shared helper for `WorkerPool._ensure_epic_branch` and the `checkout_epic_branch` FSM state — the single implementation of the exists-check (local → remote → create) previously duplicated at both call sites.

**Exists-check sequence:** local `git rev-parse --verify <branch>` → remote `git ls-remote --heads <remote_name> <branch>` → `git branch <branch> <base>`. Staleness (`git rev-list --count <branch>..<base>`) is measured **only on the local-hit path** — the remote-hit path cannot be measured/merged without a prior `git fetch`, and stays unmeasured (left unchanged).

**Parameters:**
- `branch` — The EPIC integration branch name.
- `base` — The resolved fork base (`resolve_epic_base()`'s return value).
- `repo_path` — Path to the main repository.
- `git_lock` — Thread-safe git lock for serializing repo operations.
- `logger` — Logger instance.
- `remote_name` — Remote to check for a remote-hosted branch.
- `refresh_on_reuse` — `"warn"` | `"merge"` | `"off"`. `"off"`: no measurement/event/artifact. `"warn"`: measure and log only, no git state change. `"merge"` (default): additionally merge `base` into `branch` via a scratch worktree (`setup_worktree(..., checkout_existing=True)`, `git merge --no-ff --no-edit -m "Merge <base> into <branch> (ENH-3302 refresh)" <base>`, `cleanup_worktree(..., delete_branch=False)`); a conflict aborts the merge (branch SHA unchanged, clean tree) and degrades to `"merge_conflict"` without raising.
- `run_dir` — When non-`None` (the YAML call site), a merge conflict persists the ENH-2643 diagnostic artifacts (`merge-conflicts.txt` / `merge-detail.txt` / `merge-returncode.txt`) under it. `WorkerPool` has no per-run `run_dir` and passes `None`, relying on the returned status / an emitted `parallel.epic_branch_stale` event instead.

**Returns:** `EpicBranchStatus` — `branch`, `base`, `created: bool`, `commits_behind: int`, `action: Literal["created", "fresh", "warned", "merged", "merge_conflict", "off"]`, `detail: str | None` (conflict detail on `merge_conflict`).

### open_pr_for_epic_branch

```python
def open_pr_for_epic_branch(
    epic_id: str,
    epic_branch: str,
    *,
    base_branch: str,
    repo_path: Path,
    logger: Logger,
) -> None
```

Opens one PR for a completed EPIC integration branch via `gh` (FEAT-2449, BUG-2614). Stateless free-function extraction of `ParallelOrchestrator`'s `_open_pr_for_epic_branch`. The branch is **not** deleted — the PR needs it. `--head` is `epic_branch`, `--base` is `base_branch`.

**Parameters:**
- `epic_id` — The EPIC issue ID, used in the PR title/body and logs.
- `epic_branch` — Name of the EPIC integration branch to open a PR for.
- `base_branch` — PR base branch.
- `repo_path` — Path to the repository.
- `logger` — Logger instance.

**Behavior:**
- Checks `gh auth status` first; if not authenticated, logs a warning and returns without attempting PR creation.
- If the `gh` binary is missing (`FileNotFoundError`) or `gh pr create` times out (`subprocess.TimeoutExpired`), logs a warning and returns rather than raising.

---

## little_loops.sync

GitHub Issues bidirectional sync. Provides push/pull/status/diff/close/reopen operations between local `.issues/` markdown files and GitHub Issues via the `gh` CLI, plus PR-merge reconciliation for feature-branch issues.

```python
from little_loops.sync import GitHubSyncManager, SyncedIssue, SyncResult, SyncStatus
```

### SyncedIssue

```python
@dataclass
class SyncedIssue:
    local_path: Path | None = None
    issue_id: str = ""
    github_number: int | None = None
    github_url: str = ""
    last_synced: str = ""
    local_changed: bool = False
    github_changed: bool = False
```

Represents an issue's sync state. Defined for future use as a per-issue state record — not currently constructed anywhere in this module (all operations below build and return `SyncResult`/`SyncStatus` instead).

### SyncResult

```python
@dataclass
class SyncResult:
    action: str  # push, pull, status
    success: bool
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)  # (issue_id, reason)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]: ...
```

Result of a single sync operation, returned by every `GitHubSyncManager` method except `get_status`. `created`/`updated`/`skipped` are human-readable summary strings (e.g. `"BUG-123 → #45"`); `failed` pairs an issue ID with a failure reason. `GitHubSyncManager.diff_issue` repurposes `created` to carry raw unified-diff lines rather than summary strings — see that method.

**Fields:**

| Field | Type | Description |
|---|---|---|
| `action` | `str` | Operation name: `"push"`, `"pull"`, `"status"`, `"diff"`, `"close"`, `"reopen"`. |
| `success` | `bool` | `False` if the operation hit an unrecoverable error or any item failed. |
| `created` | `list[str]` | Summary lines for newly created issues (push→GitHub or pull→local). Overloaded by `diff_issue` to hold diff text. |
| `updated` | `list[str]` | Summary lines for updated/closed/reopened issues. |
| `skipped` | `list[str]` | Summary lines for issues skipped (already tracked, not synced, in sync, etc.). |
| `failed` | `list[tuple[str, str]]` | `(issue_id, reason)` pairs for per-issue failures. |
| `errors` | `list[str]` | Operation-level errors (e.g. auth failure) that abort before per-issue processing. |

**Methods:**
- `to_dict() -> dict[str, Any]` — serialize all fields for JSON output.

### SyncStatus

```python
@dataclass
class SyncStatus:
    provider: str
    repo: str
    local_total: int = 0
    local_synced: int = 0
    local_unsynced: int = 0
    github_total: int = 0
    github_only: int = 0
    github_error: str | None = None

    def to_dict(self) -> dict[str, Any]: ...
```

Sync status overview returned by `GitHubSyncManager.get_status()`.

**Fields:**

| Field | Type | Description |
|---|---|---|
| `provider` | `str` | Sync provider name from config (e.g. `"github"`). |
| `repo` | `str` | Resolved `owner/repo`, or `"unknown"` if it could not be determined. |
| `local_total` | `int` | Count of local issue files considered for sync (respects `sync.github.sync_completed`). |
| `local_synced` | `int` | Count of local issues with a `github_issue` frontmatter field. |
| `local_unsynced` | `int` | `local_total - local_synced`. |
| `github_total` | `int` | Count of open issues on GitHub (requires `gh auth`). |
| `github_only` | `int` | GitHub issue numbers not tracked by any local issue. |
| `github_error` | `str \| None` | Set if the GitHub query failed (e.g. not authenticated); other GitHub-derived fields stay at their defaults in that case. |

**Methods:**
- `to_dict() -> dict[str, Any]` — serialize all fields for JSON output.

### GitHubSyncManager

```python
class GitHubSyncManager:
    def __init__(
        self,
        config: BRConfig,
        logger: Logger,
        dry_run: bool = False,
    ) -> None: ...
```

Manages bidirectional sync between local `.issues/` files and GitHub Issues, shelling out to the `gh` CLI (via an internal `_run_gh_command` helper) for every remote operation. All mutating methods honor `dry_run`: they report what *would* happen (prefixed `"would create"`/`"would update"`/etc. in `SyncResult.created`/`updated`) without calling `gh` or writing files. Every method first checks `gh auth status`; on failure it returns a `SyncResult`/`SyncStatus` with `success=False` (or a populated `github_error`) and the message `"GitHub CLI not authenticated. Run: gh auth login"`.

**Parameters (`__init__`):**
- `config` — Project `BRConfig`; `config.sync` supplies GitHub repo/label/limit settings, `config.issues.base_dir` + `config.issue_categories` locate local issue files.
- `logger` — `Logger` used for all `gh` command tracing and per-issue success/failure messages.
- `dry_run` — When `True`, mutating operations (push, pull, close, reopen) report intended actions without calling `gh` or writing to disk.

**Methods:**

- `push_issues(issue_ids: list[str] | None = None) -> SyncResult` — Push local issues to GitHub. Iterates all local issue files (or just `issue_ids` if given), creating a new GitHub issue (`gh issue create`) when the file has no `github_issue` frontmatter, or updating the existing one (`gh issue edit`) when it does. On create, writes `github_issue`, `github_url`, and `last_synced` back into the local file's frontmatter. Also posts a `"Duplicate of ..."` comment when the issue has a `duplicate_of` frontmatter field. Labels are derived from the issue's type/priority/`blocked_by`/`labels:` frontmatter via an internal `_get_labels_for_issue` helper.

- `pull_issues(labels: list[str] | None = None) -> SyncResult` — Pull GitHub Issues into new local files via `gh issue list` (bounded by `sync.github.pull_limit`, with a warning if the result count hits that limit — results may be truncated). Skips issues that are closed (unless `sync.github.sync_completed`), already tracked locally (matched by `github_issue` number), or carry no label recognized by `sync.github.label_mapping` (used to infer local issue type). Newly created local files get the next global issue number (`get_next_issue_number`), a filename slug derived from the GitHub title, and are assembled via `assemble_issue_markdown` using the project's per-type section template; GitHub labels are copied into frontmatter `labels:` after stripping ll-managed type/priority/`blocked-by` labels.

- `get_status() -> SyncStatus` — Return a `SyncStatus` with local counts (from local issue files) and, if `gh auth` succeeds, GitHub-side counts (`gh issue list --json number --limit 500`). Does not error out if GitHub is unreachable — sets `github_error` and leaves GitHub counts at their defaults instead.

- `diff_issue(issue_id: str) -> SyncResult` — Show a unified diff (`difflib.unified_diff`) between one local issue's body and its GitHub counterpart's body (`gh issue view --json body`). Requires the local issue to already carry a `github_issue` frontmatter number, else returns `success=False`. On a difference, the diff lines (not summary strings) are stored in `result.created`; if bodies match, a `"... in sync"` note goes to `result.skipped`.

- `diff_all() -> SyncResult` — Summarize (not full diffs — just differs/in-sync) local-vs-GitHub body differences across all synced local issues, using a single batch `gh issue list --json number,body --limit 500 --state all` call rather than one `gh issue view` per issue.

- `close_issues(issue_ids: list[str] | None = None, all_completed: bool = False) -> SyncResult` — Close the GitHub issues (`gh issue close`, with a comment) for local issues that are done. Either pass explicit `issue_ids`, or set `all_completed=True` to close every local issue whose frontmatter `status` is `done`/`cancelled`. Exactly one of the two must be provided; otherwise returns `success=False` with an error asking for `--all-completed` or issue IDs. Issues with no `github_issue` frontmatter are skipped, not failed.

- `reopen_issues(issue_ids: list[str] | None = None, all_reopened: bool = False) -> SyncResult` — Reopen the GitHub issues (`gh issue reopen`, with a comment) for locally-active issues. With `all_reopened=True`, iterates all active-directory local issues and, for each, first queries GitHub state (`gh issue view --json state`) and skips any not currently `CLOSED`; with explicit `issue_ids`, reopens unconditionally. On success also writes local frontmatter `status: open` via `update_frontmatter`. Exactly one of `issue_ids`/`all_reopened` must be provided.

- `reconcile_pr_merges() -> int` — Promote `in_progress` local issues to `status: done` (with `completed_at`) when their associated PR has been merged. For every local issue with `status: in_progress` and a `pr_url` or `branch` frontmatter field, calls `is_pr_merged` (from `little_loops.parallel.github_utils`) and, if merged, updates the local frontmatter (or just logs the intended change under `dry_run`). Returns the count of issues promoted. Unlike the other methods, this does not check `gh auth` up front or return a `SyncResult` — it returns a plain `int` count and logs (rather than raises) per-issue errors.

---

## Agents

Specialized sub-agents live in `agents/*.md` and are registered in `.claude-plugin/plugin.json`. Each agent is spawned via the `Task` / `Agent` tool with `subagent_type` set to the agent name. Codex-CLI mirrors are generated into `.codex/agents/*.toml` by `ll-adapt --host codex --apply`.

| Agent | Model | Tools | Purpose |
|-------|-------|-------|---------|
| [`codebase-analyzer`](../../agents/codebase-analyzer.md) | sonnet | Read, Glob, Grep, WebFetch, WebSearch | Trace HOW code works — implementation details, data flows, integration points, anchor-based references. |
| [`codebase-locator`](../../agents/codebase-locator.md) | sonnet | Read, Glob, Grep, WebFetch, WebSearch | Find WHERE code lives — file paths grouped by purpose, each citing its Grep match; no reading for analysis. |
| [`codebase-pattern-finder`](../../agents/codebase-pattern-finder.md) | sonnet | Read, Glob, Grep, WebFetch, WebSearch | Extract concrete code examples of patterns and conventions to model new work after. |
| [`consistency-checker`](../../agents/consistency-checker.md) | sonnet | Read, Glob, Grep, WebFetch, WebSearch | Validate cross-component references between CLAUDE.md, agents, skills, commands, hooks, and MCP config. |
| [`loop-specialist`](../../agents/loop-specialist.md) | sonnet | Bash, Read, Edit, Write | Monitor, diagnose, refine, and verify FSM loops; classifies failures against the seven-mode taxonomy (including `evaluator-trivial`) and writes diagnosis artifacts to `.loops/diagnostics/`. |
| [`plugin-config-auditor`](../../agents/plugin-config-auditor.md) | sonnet | Read, Glob, Grep, WebFetch, WebSearch | Audit individual agent/skill/command/hook definitions for quality, completeness, and best practices. |
| [`prompt-optimizer`](../../agents/prompt-optimizer.md) | sonnet | Read, Glob, Grep, WebFetch, WebSearch, Write | Gather codebase context so vague user prompts can be rewritten with specific references and conventions. |
| [`web-search-researcher`](../../agents/web-search-researcher.md) | sonnet | Read, Glob, Grep, WebFetch, WebSearch, Bash | Fetch current external documentation, release notes, and best-practice references beyond the training cutoff. |
| [`workflow-pattern-analyzer`](../../agents/workflow-pattern-analyzer.md) | sonnet | Read, Glob, Grep, WebFetch, WebSearch, Write | Categorize extracted user messages and emit `step1-patterns.yaml` for the three-step workflow-analysis pipeline. |

## Loops

Built-in loops live in `scripts/little_loops/loops/`. Full documentation and a decision guide are in [LOOPS_GUIDE.md](../guides/LOOPS_GUIDE.md).

### `rn-build` — Spec-to-Project Capstone Orchestrator

**Category**: orchestration  
**File**: `scripts/little_loops/loops/rn-build.yaml`  
**Required input**: `spec` (path to spec Markdown file)

End-to-end spec-to-project pipeline. Accepts a spec Markdown file and drives: spec validation → tech research → design artifacts → commit → scope EPIC + feature stubs → issue refinement → eval harness → `goal-cluster` (batched `rn-implement`, `value_ranked` scheduling) → eval gate with bounded re-entry → integration/acceptance gate → structured JSON result.

Uses value-ranked scheduling via `rn-implement` + `goal-cluster` rather than an `eval-driven-development` sub-loop.

**CLI invocation:**

```bash
ll-loop run rn-build --context spec=specs/sample.md

# Multiple spec files (comma-separated)
ll-loop run rn-build --context spec=specs/backend.md,specs/frontend.md
```

**Key phases:**

| Phase | States | Description |
|-------|--------|-------------|
| 0 — Resume (optional) | `resume`, `resume_read_harness` | Skip front half; re-enter `cluster_execute` for an already-scoped EPIC. Entered when `resume_epic` is set |
| 1 — Spec validation | `init` | Reads and validates the spec file(s); halts with clear error if required sections are missing |
| 2 — Research & design | `tech_research`, `design_artifacts`, `commit_design` | LLM tech research → generates architecture and design artifacts → commits them to the working tree |
| 3 — Scope | `scope_project`, `write_epic_id`, `enumerate_epic_children`, `refine_seed` | Runs `/ll:scope-epic` to create EPIC + feature stubs, captures EPIC ID, enumerates child issues, refines them via `recursive-refine` (depth-first, handles size-review decomposition) |
| 4 — Eval harness | `eval_harness`, `read_harness_name` | Installs an eval harness loop keyed to the spec's acceptance criteria |
| 5 — Execution | `cluster_execute` | Delegates to `goal-cluster` which batches issues and dispatches each batch to `rn-implement` with `schedule_mode=value_ranked` |
| 6 — Eval gate | `check_harness_name`, `eval_gate`, `check_eval_retry_budget`, `capture_eval_failures` | Runs eval harness; on failure, captures failing scenarios as new issues and re-enters `cluster_execute` (bounded by `max_eval_retries`) |
| 6.5 — Harness missing/skipped (ENH-2415) | `harness_missing`, `finalize_harness_missing`, `finalize_eval_skipped` | Reached when no harness resolves, the harness crashes, or retries are exhausted. Terminates `build_failed` (loud, resumable) unless `skip_eval=true` was explicitly set, which still terminates non-`done` with `eval_skipped: true` |
| 6.75 — Integration/acceptance gate (FEAT-2414) | `derive_acceptance_checks`, `run_acceptance`, `score_acceptance`, `check_acceptance_retry_budget`, `capture_acceptance_failures` | Turns the spec's `## Acceptance Criteria` into an executable contract. An LLM derives one runnable check per criterion into `${run_dir}/acceptance/checks.json`; `run_acceptance` stands up the assembled project and **executes** each check, writing a per-criterion breakdown to `acceptance/results.json`; `score_acceptance` scores `passed / executed` through a non-LLM `output_numeric` gate against `min_acceptance_pass_rate`. Failures re-enter `cluster_execute` as captured issues (bounded by `max_acceptance_retries`) |
| 6.8 — Acceptance failed (FEAT-2414) | `finalize_acceptance_failed`, `acceptance_failed` | Reached when integration cannot be verified after the retry budget is spent. Emits the per-criterion breakdown plus a `resume_command` and terminates at the `failure: true` terminal `acceptance_failed` — every feature passing in isolation is not a passing build |
| 7 — Result | `synthesize_result`, `done` | Emits a structured JSON summary of the build outcome, including per-criterion `acceptance` results read from `acceptance/results.json`; includes `resume_command` when `eval_passed: false`. Only reached when both the eval gate **and** the acceptance gate actually passed |

**Context knobs:**

| Variable | Default | Description |
|----------|---------|-------------|
| `spec` | `""` | **Required.** Path(s) to spec Markdown file(s), comma-separated. |
| `max_eval_retries` | `"2"` | Maximum `eval_gate` retry cycles before accepting a partial result. |
| `harness_name` | `""` | Auto-populated: name of the installed eval harness loop. Do not set manually. |
| `epic_id` | `""` | Auto-populated: EPIC ID from `scope_project`. Do not set manually. |
| `resume_epic` | `""` | **Resume only.** EPIC ID from a prior run. When set, `init` skips spec validation and routes to `resume`, which re-enters `cluster_execute`. |
| `resume_harness` | `""` | **Resume only.** Harness loop name from a prior run. Passed to `eval_gate` via `resume_read_harness`. |
| `skip_eval` | `"false"` | **Deliberate bypass only** (ENH-2415). The only way to skip the eval gate; still terminates `build_failed` (not `done`) with `eval_skipped: true` in the JSON output. |
| `max_acceptance_retries` | `"1"` | FEAT-2414. Remediation cycles for *integration* failures, budgeted separately from `max_eval_retries` (own counter: `${run_dir}/acceptance-retry-count.txt`). |
| `min_acceptance_pass_rate` | `"1.0"` | FEAT-2414. Fraction of **executed** acceptance checks that must pass. Defaults to a full pass — a partially-satisfied spec is not a `done` build. A criterion the derivation marks unrunnable (`skip_reason`) is excluded from the denominator, but an all-skipped `results.json` scores `0.0` so the gate cannot be cleared by declining to write checks. |

**Internal dispatch flags** (fixed; set automatically, not user-facing):

| Flag | Value | Effect |
|------|-------|--------|
| `schedule_mode` | `value_ranked` | Passed to each `rn-implement` batch via `goal-cluster`; issues are implemented in value-ranked order |
| `propagate_context` | `true` | Cluster propagates context across batches so later batches can incorporate earlier-batch results |

**Loop settings**: `max_steps: 40`, `timeout: 86400s` (24h), `on_handoff: spawn` (auto-resumes across session boundaries).
