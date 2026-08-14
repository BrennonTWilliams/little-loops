---
id: ENH-3166
type: ENH
title: 'Qwen wire-format normalizer: chats/ discovery and rebuild extractors are blind
  to qwen message schema'
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-14'
captured_at: '2026-08-14T00:57:49Z'
completed_at: '2026-08-14T20:47:22Z'
testable: true
relates_to:
- ENH-3165
---

# ENH-3166: Qwen wire-format normalizer: chats/ discovery and rebuild extractors are blind to qwen message schema

## Summary

Qwen session JSONL is **Claude-shaped at the envelope level but divergent in the
message body**, and no code path knows the difference. Split out of ENH-3165,
which retains the subagent-transcript backfill; this issue covers session
discovery and the raw_events → cache-table extraction path.

A real record from `~/.qwen/projects/<encoded>/chats/<id>.jsonl` (qwen 0.21.6):

```json
{"uuid":"71805e93-…","parentUuid":null,"sessionId":"61c364ea-…",
 "timestamp":"2026-08-13T01:36:19.752Z","type":"user","provenance":"real_user",
 "cwd":"/private/tmp/ll-qwen-spike","version":"0.21.6",
 "message":{"role":"user","parts":[{"text":"Reply with exactly: BYE"}]}}
```

Consequences of the envelope match — **narrower than ENH-3165 originally
claimed**. `sessionId`, `timestamp`, `type`, and `cwd` are all present with
Claude's names, so `_backfill_raw_events` (`lifecycle.py:747`) and
`_backfill_sessions` (`lifecycle.py:708`) parse qwen files **unmodified** once
files reach them. "No sessions extracted" is not the failure mode.

What actually diverges, and where it bites:

1. **`ll-logs` project discovery has no qwen branch, and the fix is not a
   one-line `elif`.** `cli/logs.py:164–172` maps host → projects root for
   `claude-code`/`codex`/`opencode`/`pi` only; qwen and kimi-code fall through
   to `return []`. But the two helpers the loop calls —
   `_has_ll_activity` (`logs.py:88`) and `_extract_cwd_from_project`
   (`logs.py:111`) — both glob `project_dir/*.jsonl`, while qwen's sessions live
   one level deeper under `chats/`. Worse, `_is_ll_relevant` (`logs.py:38`) /
   `_cmd_matches` (`logs.py:203`) inspect `message.content[]` `tool_use` blocks and match on
   Claude's tool *names* (`"Bash"`) and arg keys (`input.command`), so even with
   the path corrected `_has_ll_activity` returns `False` for every qwen project
   until the body normalizer **and the tool-name map** below exist. Discovery
   **depends on** the normalizer; they cannot be sequenced independently.

   The `chats/` blindness is confined to `cli/logs.py`. The `ll-session
   backfill` path already resolves it via
   `subagent_layout_for(host).sessions_subdir` (`cli/session.py:569,601`,
   landed with ENH-3165).

2. **Message body shape.** Qwen uses `message.parts[]` where Claude uses
   `message.content[]`:

   | Concern | Claude Code | Qwen 0.21.6 |
   |---------|-------------|-------------|
   | Body key | `message.content[]` | `message.parts[]` |
   | Text block | `{"type":"text","text":…}` | `{"text": …}` |
   | Tool call | `{"type":"tool_use","name":…,"input":…}` | `{"functionCall":{"name":…,"args":…}}` |
   | Tool result | `{"type":"tool_result",…}` inside a `user` record | top-level `type:"tool_result"`, `{"functionResponse":{"id":…,"name":…,"response":…}}` **plus** a top-level `toolCallResult` key |
   | Assistant role | `"assistant"` | `"model"` |

   So `rebuild()`'s derived extractors (`_backfill_tool_events`,
   message/assistant/skill events — `lifecycle.py:957–…`) yield zero rows for
   qwen even when `raw_events` and `sessions` are correctly populated.

   Note the two-source tool result: `message.parts[].functionResponse` and a
   sibling top-level `toolCallResult`. Determine which one carries
   status/error before writing the `tool_events` outcome fields. Caveat: the
   current `_backfill_tool_events` derives rows only from assistant `tool_use`
   blocks and consumes no `tool_result` records at all, so the
   `functionResponse` vs `toolCallResult` decision affects only the
   normalizer's unit tests today — it is future-proofing, not an existing
   consumer.

   **Unverified: the envelope `type` of qwen assistant records.** The `role:
   "model"` divergence is observed, but no captured record confirms what the
   *envelope* `type` field says for assistant turns. Every extractor gates on
   `record.get("type") == "assistant"` and `_backfill_raw_events` stores
   `event_type` from the same field — if qwen writes anything other than
   `"assistant"` there, the normalizer must map the envelope type too. Confirm
   against a real captured assistant record before writing the normalizer.

3. **Tool vocabulary diverges, not just tool shape.** Translating
   `functionCall` → `tool_use` is not sufficient: qwen's tool *names* and
   *arg keys* are a disjoint vocabulary. Observed across 10,866 real records
   in `~/.qwen/projects` (0.21.6):

   | Qwen tool | Args | Claude analogue |
   |-----------|------|-----------------|
   | `run_shell_command` | `command`, `description` | `Bash` / `input.command` |
   | `edit` | `file_path`, `old_string`, `new_string` | `Edit` |
   | `read_file` | `file_path` | `Read` |
   | `write_file` | `file_path`, `content` | `Write` |
   | `grep_search` | `path`, `pattern` | `Grep` |
   | `glob` | `path`, `pattern` | `Glob` |
   | `list_directory` | `path` | `LS` |
   | `todo_write` | `todos` | `TodoWrite` |
   | `ask_user_question` | — | `AskUserQuestion` |

   Without a name+arg map, `_cmd_matches`/`_is_ll_relevant` never fire (they
   test `name == "Bash"` and `input.command`), and `tool_events.tool_name`
   fills with a vocabulary that every existing downstream query misses.
   **Decision: canonicalize** — map name and arg keys to the Claude names, and
   hold the map in the host layout descriptor. `functionCall.id` must become
   `tool_use.id` or tool-call ↔ tool-result correlation breaks.

4. **Not every `user`-role record is a user message.** Qwen stamps a
   `provenance` field (`real_user` | `assistant_output` | `tool_result` |
   `system`), and `user` records carry subtypes `notification` and
   `mid_turn_user_message`. Unfiltered, `_backfill_messages` ingests
   notifications and mid-turn injections as genuine user messages and poisons
   corrections mining. `provenance == "real_user"` is the clean discriminator
   for the user-message path.

5. **`host` column is stamped from the ambient host, not the ingested files.**
   `_backfill_raw_events` sets `host = resolve_host().name`. Running
   `ll-session backfill --host qwen` under the default config (`orchestration.host_cli`
   = `claude-code`) writes qwen rows tagged `host="claude-code"`. Today's db has
   911,646 `raw_events` rows, all `claude-code` — any per-host query silently
   folds qwen into Claude. `--host` must plumb through to the column.

   The hook-worker leg is a **protocol change, not just a parameter**:
   `cli/backfill_worker.py` is a bare no-argparse CLI spawned by
   `hooks/session_start.py`, so it needs a `--host` flag (checked ad hoc like
   `--rebuild`) and the hook — which knows its host from the adapter envelope —
   must pass it through the spawn args. The worker also has its own `chats/`
   blindness: when given a directory it globs `path_arg.glob("*.jsonl")`
   (`backfill_worker.py:38–40`), missing qwen's `chats/` subdir. Either resolve
   the dir glob via `layout.session_glob` or document that the hook only ever
   passes a single transcript file and the dir branch is claude-only.

Qwen also carries signal Claude's extractors have no analogue for and that a
normalizer should not discard: `subtype:"ui_telemetry"` carries
`qwen-code.api_response` token usage that maps onto `usage_events` (2,176 such
records in the sample).

**Correction to the original capture:** there is no `slash_command` subtype.
`grep -l slash_command ~/.qwen/projects/*/chats/*.jsonl` returns zero hits
across all four local qwen projects. The `system` subtypes 0.21.6 actually
writes are `ui_telemetry`, `attribution_snapshot`, `file_history_snapshot`, and
`at_command`. Any `skill_events` derivation must therefore be re-scoped onto
`at_command` (unverified) or dropped — it is not a `slash_command` record.

**Volume.** Roughly 47% of qwen records are `ui_telemetry` (2,913
`qwen-code.tool_call` + 2,176 `api_response` of 10,866 total lines, 47 MB on
disk). Ingest into `raw_events` is verbatim and happens *before* normalization,
so these land regardless. Either add an ingest-time skip predicate to the host
layout descriptor or accept the growth explicitly.

## Motivation

Without this, `ll-logs`, `ll-messages`, and every `rebuild()`-derived table are
blind to qwen work — no tool events, no message events, no slash-command
history — and the `host` mislabeling actively corrupts per-host analytics
rather than merely omitting data. ENH-3165's subagent backfill lands
`subagent_runs` rows whose `parent_session_id` points at sessions that only
exist as raw JSON until this issue closes the loop.

## Current Behavior

`discover_all_projects(host="qwen")` returns `[]` — qwen falls through the
host→root chain to the default `return []`.

`ll-session backfill --host qwen` **is** an accepted host value already
(`cli/session.py:175` lists `qwen` and `kimi-code` in `choices`), and it finds
the files (`chats/` resolves via `subagent_layout_for`). What fails is
downstream: the ingested rows are tagged `host="claude-code"` from the ambient
`resolve_host().name`, and `rebuild()` derives zero
`tool_events`/`message_events` rows from them because every extractor reads
`message.content[]` and matches Claude tool names.

## Expected Behavior

`discover_all_projects(host="qwen")` returns qwen project paths by globbing
`chats/*.jsonl` and recognizing qwen-shaped ll activity.
`ll-session backfill --host qwen --also-rebuild` writes `raw_events` rows tagged
`host="qwen"` and materializes `sessions`, `tool_events`, `message_events`, and
`assistant_messages` from them, with `parts[]` normalized to `content[]` at the
raw_events→rebuild boundary. Claude-host output is byte-identical to today's.

## Scope Boundaries

**In scope**: widening the existing host layout descriptor, qwen record
normalization for the four observed record types (`user`, `assistant`,
`tool_result`, `system`) including the tool-name/arg vocabulary map and
`provenance` filtering, `ll-logs` discovery helpers, and the `raw_events.host`
plumbing across both the CLI and hook-worker ingest paths.

**Out of scope**: qwen subagent transcripts and `subagent_runs` (ENH-3165);
kimi-code record extraction (ENH-2918); backfilling the 911,646 existing
`claude-code` rows (they are correctly labeled); `usage_events` derivation from
qwen `ui_telemetry` records — listed under Stretch and droppable;
`skill_events` derivation, which has no qwen record type to derive from (see
Stretch); adding a `host` column to the derived tables (`sessions`,
`tool_events`, `message_events` carry none — only `raw_events` does), so
per-host analytics on derived rows require joining through
`sessions.jsonl_path`/`raw_events` — an explicit non-goal here, not an
oversight.

## Program Design

### Deviations

**2026-08-14 (implementation):** design verified against live code and ~10.9k
real qwen 0.21.6 records before coding; the implemented shape departs from
the design above in these ways:

- The JSONL-derived extractors live in `session_store/writers.py`
  (`_backfill_tool_events`, `_backfill_usage_events`, `_backfill_messages`,
  `_backfill_assistant_messages`, `_backfill_prompt_opt`,
  `_backfill_skill_events`), not `lifecycle.py` as the Integration Map
  states; only `_backfill_sessions`/`_backfill_raw_events`/`rebuild()` are in
  lifecycle.py. The normalization chokepoint (`_iter_events`) is shared by
  all of them regardless.
- The open question is RESOLVED: qwen assistant records carry envelope
  `type: "assistant"` (2,082/2,082 observed); only `message.role` diverges
  (`"model"`). No envelope-type mapping was needed.
- `provenance == "real_user"` alone is NOT a clean user-message
  discriminator: `mid_turn_user_message` records carry `provenance:
  "real_user"` too. Implemented filter is `provenance == "real_user" AND
  subtype is None` (required by the `message_events` AC).
- `subtype: "slash_command"` system records DO exist in 0.21.6 (30 observed
  locally; `systemPayload.rawCommand`), contradicting the "Correction to the
  original capture" paragraph. `skill_events` derivation stays dropped per
  scope; a follow-up issue is the right vehicle.
- `_iter_events` keeps its existing signature; the per-row layout is memoized
  internally instead of a `layouts` keyword parameter, and
  `_normalize_parts` takes no error map — `is_error` is derived per record
  from `toolCallResult.status`.
- The hook passes the project root + `--host` and the worker resolves the
  directory glob via `layout.session_glob`; the ENH-3165 `sessions_subdir`
  join inside `session_start.py` was removed (it would double-nest with
  `session_glob`).
- `tool_arg_keys` is implemented but empty: observed 0.21.6 arg keys already
  match Claude's (`command`/`file_path`/`pattern`/`path`/…).

### Types

**Extend the existing descriptor — do not add a parallel one.**
`SubagentLayout` + `subagent_layout_for()` already exist in
`session_store/writers.py:1946`, already carry `sessions_subdir="chats"` for
qwen, and already have three consumers (`cli/session.py`,
`user_messages.py`, `hooks/session_start.py`). A second host table would drift
from the first. Widen `SubagentLayout` (renaming it `HostLayout` and updating
the three call sites — **no back-compat alias**; an alias of a renamed
descriptor is exactly the drift this section warns against):

```python
@dataclass(frozen=True)
class HostLayout:
    """Per-host description of where session logs live and how to read them."""
    # existing (ENH-3165)
    glob: str                       # subagent-transcript dirs
    parent_from: str                # "parent_dir" | "child_dir"
    sidecar_suffix: str | None
    sessions_subdir: str            # "chats" (qwen) | "" (claude)
    # added here
    name: str                       # "claude-code" | "qwen" | ...
    projects_root: Path | None      # ~/.qwen/projects; None when unknown
    session_glob: str               # "chats/*.jsonl" (qwen) | "*.jsonl" (claude)
    tool_names: dict[str, str]      # {"run_shell_command": "Bash", ...}
    tool_arg_keys: dict[str, dict[str, str]]  # per-tool arg renames
    normalize: Callable[[dict], dict | None] | None
    skip_at_ingest: Callable[[dict], bool] | None  # ui_telemetry volume guard
```

**Unknown-host semantics must stay split.** Today `subagent_layout_for` falls
back to the Claude shape for unknown hosts, and that leniency must survive for
the subagent/`sessions_subdir` fields or existing hosts regress. Only
`projects_root` is strict: resolving it for an unregistered host raises
`KeyError` (or returns `None` and the caller logs), rather than silently
returning `[]`.

### Signatures

- `host_layout_for(host: str) -> HostLayout` — the widened `subagent_layout_for`; lenient defaults for the subagent fields, strict on `projects_root`.
- `normalize_qwen_record(record: dict) -> dict | None` — maps `message.parts[]` to `message.content[]`, `functionCall`/`functionResponse` to `tool_use`/`tool_result` (carrying `functionCall.id` → `tool_use.id`), qwen tool names/arg keys to Claude's, and role `model` to `assistant`; drops non-`real_user` `user` records from the user-message path; returns `None` for records with no Claude-shaped equivalent.
- `_normalize_parts(parts: list[dict]) -> list[dict]` — block-level translation shared by the `assistant` and `tool_result` record paths.
- `discover_all_projects(logger: Logger, *, host: str | None = None, existing_only: bool = False) -> list[Path]` — existing signature, reimplemented over `HostLayout` instead of the inline `if host ==` chain.
- `_backfill_raw_events(conn, jsonl_files, *, host: str | None = None) -> int` — `host` overrides the ambient `resolve_host().name` for the `raw_events.host` column.
- `backfill_raw_events(db, *, jsonl_files, since_ts=None, host: str | None = None) -> int` and `backfill_incremental(db, *, jsonl_files, ..., host: str | None = None)` — **currently take no `host` at all**; without them the SessionStart hook worker path (`cli/backfill_worker.py`) keeps stamping the ambient host.
- `_iter_events(source, *, layouts: ...) -> Generator[tuple[str, str], None, None]` — see below.

### Where normalization actually attaches

"At the raw_events → rebuild boundary" is not directly implementable as
written: `rebuild()`'s `_raw_events_cursor()` selects only
`(raw_line, source_path)` (`lifecycle.py:954`) and `_iter_events`
(`writers.py:2581`) yields 2-tuples of strings — **there is no host in the
stream to dispatch on**.

Concrete approach: add `host` to that SELECT and normalize *inside*
`_iter_events`, which is the single chokepoint all seven `_backfill_*`
functions already share. `_iter_events` tolerates 2-column rows (legacy
`list[Path]` sources and existing tests) by treating a missing host as
"no normalization". This keeps every `_backfill_*` signature unchanged, which
is precisely the "no per-extractor branching" goal.

**This implies a parse → transform → re-serialize round-trip.** `_iter_events`
yields raw *strings* and every `_backfill_*` extractor does its own
`json.loads` on them, so applying `layout.normalize` (dict → dict) inside
`_iter_events` means `json.loads` → normalize → `json.dumps` per line — and
since `rebuild()` opens a fresh cursor for each of the seven extractors, each
qwen line pays that round-trip seven times per rebuild. Acceptable at current
volume (~10k qwen lines), but the round-trip MUST be gated on "this row's host
has a normalizer": rows whose layout has `normalize=None` (all 911,646
existing `claude-code` rows) are yielded untouched. That gate is both the perf
guard and what makes the byte-identical-Claude-output AC hold. Records the
normalizer returns `None` for are skipped (not yielded).

### Call Path

1. `ll-logs` / `ll-messages` — call `discover_all_projects()`
2. `discover_all_projects()` → `host_layout_for()` → `_has_ll_activity()` / `_extract_cwd_from_project()`, both globbing `layout.session_glob`
3. `ll-session backfill --host qwen` → `backfill(host=...)` → `_backfill_raw_events(host="qwen")`
4. SessionStart hook worker — `hooks/session_start.py` reads the host from the
   adapter envelope and spawns `backfill_worker --host <host>` →
   `backfill_incremental(host=...)` → `backfill_raw_events(host=...)` → same column
5. `rebuild()` → `SELECT raw_line, source_path, host` → `_iter_events` applies `layout.normalize` → `_backfill_sessions()` / `_backfill_tool_events()` / … unchanged
6. `resolve_host()` — remains the orchestration-CLI selector; it is *not* the source of the ingested-file host

## Implementation Steps

1. Widen the existing `SubagentLayout` → `HostLayout` and
   `subagent_layout_for` → `host_layout_for` (updating the three existing call
   sites), adding `projects_root`/`session_glob`/`tool_names`/`normalize` for
   the currently-supported hosts. Reimplement `discover_all_projects` over it
   with no behavior change for Claude.
2. Add the qwen entry (`chats/*.jsonl`) and teach `_has_ll_activity` /
   `_is_ll_relevant` / `_cmd_matches` to recognize normalized qwen records —
   i.e. run the normalizer (including the tool-name map) before the predicate,
   so `run_shell_command`/`args.command` reaches the existing `Bash`/
   `input.command` test.
3. Write `normalize_qwen_record` (shape **and** tool vocabulary, `provenance`
   filtering) against fixtures captured from real qwen 0.21.6 output —
   capture a real *assistant* record first and confirm its envelope `type`
   value (unverified; see gap 2) before writing the normalizer. Wire it into
   `_iter_events` with `host` added to the `rebuild()` cursor SELECT, gating
   the loads/normalize/dumps round-trip on `layout.normalize is not None` so
   hosts without a normalizer pass through untouched.
4. Thread `host` through `_backfill_raw_events`, `backfill_raw_events`, and
   `backfill_incremental` so both the CLI and the SessionStart hook worker
   stamp the ingested host. For the worker leg: add `--host` to
   `backfill_worker.py` (ad-hoc check like `--rebuild`), pass it from
   `session_start.py` using the adapter envelope's host, and resolve the
   worker's directory-arg `*.jsonl` glob against `layout.session_glob`.
5. Regression-test the Claude fixture path, add qwen fixtures, and update
   `docs/reference/API.md` + `docs/reference/HOST_COMPATIBILITY.md`.

## Proposed Solution

Grow the **existing** host layout descriptor (`SubagentLayout`, ENH-3165)
rather than adding scattered `if host == "qwen"` branches or a second
descriptor type — one record per host holding:

- `projects_root` (`~/.qwen/projects`)
- `session_glob` (`chats/*.jsonl` for qwen, `*.jsonl` for Claude)
- the subagent fields already there (`glob`, `parent_from`, `sidecar_suffix`,
  `sessions_subdir`) consumed by ENH-3165
- `tool_names` / `tool_arg_keys` — the qwen↔Claude tool vocabulary map
- `normalize(record) -> dict | None` — maps a host record into the
  Claude-shaped internal form the existing `_backfill_*` extractors already
  consume
- `skip_at_ingest(record) -> bool` — optional volume guard for `ui_telemetry`

Normalize once inside `_iter_events` (the shared chokepoint) rather than in
each `_backfill_*` extractor; there are seven of them and the branch count
multiplies per host. `raw_events` keeps the verbatim source line (its stated
contract), so normalization is a read-time transform and re-running `rebuild()`
after a normalizer fix requires no re-ingest.

kimi-code shares gap shapes 1 and 2 (ENH-2918); its extraction stays out of
scope here, but the descriptor must make kimi a table entry rather than a
refactor.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` — host → projects root map (164–172),
  `_has_ll_activity` (88), `_extract_cwd_from_project` (111), `_is_ll_relevant`/
  `_cmd_matches` (203)
- `scripts/little_loops/session_store/lifecycle.py` — `_backfill_raw_events`
  (748, host column + `host` param), `backfill_raw_events` (794) and
  `backfill_incremental` (1084) `host` params, `rebuild()`'s
  `_raw_events_cursor` (953–954: add `host` to the SELECT)
- `scripts/little_loops/session_store/writers.py` — `SubagentLayout` /
  `subagent_layout_for` (1946) widened to `HostLayout` / `host_layout_for`;
  `_iter_events` (2581) gains normalization
- `scripts/little_loops/user_messages.py` — `_get_qwen_project_folder`
  (476–490); drop the "wire-format parsing is a follow-up" deferral note

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/session.py` — `subagent_layout_for` call sites
  (569, 601) and `--host` plumbing (`choices` at 175 already includes `qwen`)
- `scripts/little_loops/hooks/session_start.py` (164–166) — `subagent_layout_for` call site
- `scripts/little_loops/cli/backfill_worker.py` — hook-worker ingest path:
  new `--host` flag (ad-hoc check, matching `--rebuild`), threaded into
  `backfill_incremental(host=...)`; directory-arg glob (`*.jsonl`, lines
  38–40) resolved via `layout.session_glob` or documented as claude-only
- `scripts/little_loops/hooks/session_start.py` — also the spawn site: pass
  `--host` from the adapter envelope when spawning the worker
- Any `ll-logs`/`ll-messages` consumer relying on `discover_all_projects`

### Similar Patterns
- `subagent_layout_for` (`writers.py:1946`) — **the descriptor to extend**, not
  a pattern to copy into a new module
- `_get_kimi_project_folder` (`user_messages.py:437`) — non-Claude layout
  resolution already special-cased
- `hooks/adapters/<host>/` — existing per-host directory convention

### Tests
- `scripts/tests/` — new qwen-fixture coverage for discovery + normalizer;
  fixtures modeled on the real records quoted above

### Documentation
- `docs/reference/API.md` — `ll-session backfill --host {…}` host list
- `docs/reference/HOST_COMPATIBILITY.md` — qwen session-log support row

### Configuration
- N/A

## Acceptance Criteria

- [x] `discover_all_projects(host="qwen")` returns qwen project paths, with
      `_has_ll_activity`/`_extract_cwd_from_project` honoring the `chats/`
      subdirectory rather than `project_dir/*.jsonl`.
- [x] `_has_ll_activity` recognizes ll activity in qwen records — a
      `run_shell_command` `functionCall` whose `args.command` matches `ll-\w+`
      is detected, not just Claude `tool_use`/`input.command` blocks.
- [x] The **existing** `SubagentLayout`/`subagent_layout_for` descriptor is
      widened (not duplicated) to supply projects root, session glob, tool
      vocabulary map, and record normalizer; no second host table exists and no
      new `if host == "qwen"` branches appear inside individual `_backfill_*`
      extractors.
- [x] `rebuild()` derives `tool_events`, `message_events`, and
      `assistant_messages` rows from qwen `raw_events` (`parts[]` →
      `content[]`, `functionCall`/`functionResponse` → `tool_use`/`tool_result`
      with `id` preserved, role `model` → `assistant`).
- [x] `tool_events.tool_name` for qwen rows holds canonical Claude names
      (`run_shell_command` → `Bash`, `edit` → `Edit`, `read_file` → `Read`,
      `grep_search` → `Grep`, `write_file` → `Write`, `glob` → `Glob`,
      `list_directory` → `LS`, `todo_write` → `TodoWrite`), with arg keys
      renamed to match, so existing tool-name-keyed queries see qwen work.
- [x] `message_events` contains only `provenance == "real_user"` qwen user
      records — `notification` and `mid_turn_user_message` subtypes are
      excluded, verified by a fixture containing all three.
- [x] `ll-session backfill --host qwen` writes `raw_events.host = "qwen"`
      regardless of the ambient `orchestration.host_cli` / `LL_HOST_CLI` value.
- [x] The SessionStart hook worker path (`backfill_incremental` →
      `backfill_raw_events` via `cli/backfill_worker.py`) also stamps the
      ingested host rather than the ambient one: the worker accepts `--host`,
      `session_start.py` passes it from the adapter envelope, and the worker's
      directory-arg glob finds qwen sessions under `chats/`.
- [x] Existing Claude-host discovery, ingestion, and rebuild behavior is
      unchanged: the Claude fixture tests pass without modification and
      `rebuild()` row counts on a Claude fixture db are identical pre/post.
- [x] Unit tests use committed qwen fixtures (not `~/.qwen`), so the suite
      passes on a machine with no qwen install. Fixtures are derived from real
      0.21.6 records and include at least one *assistant* record (confirming
      the envelope `type` value the extractors gate on), one `tool_result`
      (with both `functionResponse` and top-level `toolCallResult`), and one
      `system`/`ui_telemetry` record.
- [x] Rows whose host layout has no normalizer bypass the
      loads/normalize/dumps round-trip in `_iter_events` entirely — Claude
      lines are yielded byte-identical to what `raw_events` stores.
- [x] A documented decision on `ui_telemetry` ingest volume: either
      `skip_at_ingest` filters them or the issue records why the ~47% growth is
      accepted.
- [x] Manual check on real data: a qwen session under
      `~/.qwen/projects/-Users-…-little-loops/chats/` yields `sessions`,
      `tool_events`, and `message_events` rows after
      `ll-session backfill --host qwen --also-rebuild`.

## Stretch (defer if it grows the change)

- [ ] `subtype:"ui_telemetry"` / `qwen-code.api_response` records →
      `usage_events` (real signal; 2,176 records in the local sample)
- [ ] ~~`subtype:"slash_command"` system records → `skill_events`~~ —
      **dropped**: no such record type exists in qwen 0.21.6 (zero hits across
      all local projects). If `skill_events` coverage is wanted later, verify
      the `at_command` subtype first and capture it as a separate issue.

## Resolution

- **Action**: improve
- **Completed**: 2026-08-14
- **Status**: Completed

### Changes Made
- `session_store/writers.py` — `SubagentLayout`→`HostLayout`,
  `subagent_layout_for`→`host_layout_for`: widened with `name`,
  `projects_root`, `session_glob`, `tool_names`, `tool_arg_keys`,
  `normalize`, `skip_at_ingest`; lenient Claude-shape fallback for the
  subagent fields, strict `projects_root=None` for unregistered hosts; no
  back-compat alias. `_iter_events` applies `layout.normalize` to cursor
  rows carrying a third `host` column (records normalized to `None` are
  dropped); rows whose layout has no normalizer pass through untouched.
- `session_store/qwen.py` (new) — `normalize_qwen_record`,
  `_normalize_parts`, `qwen_skip_at_ingest`, `QWEN_TOOL_NAMES`,
  `QWEN_TOOL_ARG_KEYS`. Verified against sanitized real 0.21.6 records.
- `session_store/lifecycle.py` — `rebuild()` cursor selects `host`;
  `_backfill_raw_events` / `backfill_raw_events` / `backfill_incremental`
  take `host` (stamps `raw_events.host`, applies `skip_at_ingest`);
  `backfill()` threads its existing `host` into ingest.
- `cli/logs.py` — `discover_all_projects` reimplemented over
  `host_layout_for(host).projects_root` (debug-log + `[]` when None);
  `_has_ll_activity` / `_extract_cwd_from_project` /
  `_extract_ll_event_streams` glob `layout.session_glob` and normalize
  records before the existing Claude predicates; `_cmd_sequences` passes the
  ambient host's layout.
- `cli/session.py` — `--since` incremental path passes `host` to
  `backfill_incremental` (full path already passed it to `backfill`).
- `cli/backfill_worker.py` — ad-hoc `--host` flag (matching `--rebuild`
  style), threaded to `backfill_incremental`; directory args resolve via
  `layout.session_glob` so qwen `chats/` sessions are found.
- `hooks/session_start.py` — passes `--host` from the adapter envelope
  (`event.host`, `LL_HOOK_HOST` fallback) and passes the project root; the
  ENH-3165 `sessions_subdir` join moved into the worker's `session_glob`.
- `user_messages.py` — rename call site; qwen deferral note updated.
- Tests — `scripts/tests/test_enh_3166_qwen_normalizer.py` (31 tests:
  normalizer units, layout registry, discovery, host plumbing, rebuild
  derivation, Claude parity incl. byte-identical `_iter_events` pass-through,
  worker, hook argv) + committed fixtures
  `scripts/tests/fixtures/qwen/{session,noise}.jsonl` derived from real 0.21.6
  records; `test_enh_2505_subagent_runs.py` updated to the renamed API.
- Docs — `docs/reference/API.md` (`ll-session backfill` qwen behavior);
  `docs/reference/HOST_COMPATIBILITY.md` `[^qwenwire]` footnote.

### Verification Results
- Tests: PASS — full suite (19,282 collected) green across chunked runs; two
  load-dependent `TestContextMonitor` subprocess-timeout flakes pass in
  isolation and in a pristine-HEAD worktree (pre-existing, unrelated).
- Lint: PASS (`ruff check scripts/` + `ruff format`).
- Types: PASS (`mypy scripts/little_loops/`; only pre-existing ruamel
  stub noise).
- Manual (real data): `ll-session --db <tmp> backfill --host qwen --since
  2020-01-01 --rebuild` with ambient `LL_HOST_CLI=claude-code` → 3,111
  `raw_events` rows **all `host="qwen"`**, 14 sessions, 1,505 tool_events
  (canonical names: Bash/Edit/Read/Grep/Write/Glob/LS/TodoWrite/
  AskUserQuestion + unmapped qwen-native names passed through), 29
  message_events (real-user only), 630 assistant_messages.

### Decisions
- **ui_telemetry volume**: skipped at ingest via `skip_at_ingest` (~47% of
  qwen record volume, zero rebuild consumers until the deferred
  `usage_events` stretch goal lands). All other record families ingest
  verbatim.
- **Tool-result source of truth**: `toolCallResult` carries status/error
  (`is_error` = `status == "error"`); `functionResponse.response` carries
  content (`{"output": str}` on success, plain string on some failures —
  both handled). `tool_use_id` = `toolCallResult.callId` with
  `functionResponse.id` fallback. No extractor consumes tool_result rows
  today — future-proofing per the issue's note.
- **Unmapped tool names** (e.g. qwen-native `agent`, `send_message`,
  `list_agents`) pass through unchanged so `tool_events` still records them.

## Impact

- **Priority**: P2 — observability gap, not a functional break; no data loss
  (source JSONL persists on disk and can be re-ingested at any time).
- **Effort**: Medium–Large — descriptor widening (with three existing call
  sites to update), a normalizer covering four record types plus the tool
  vocabulary map, and `host` plumbing through two ingest paths, with the Claude
  path held unchanged.
- **Risk**: Medium — touches the shared `_iter_events`/`rebuild()` extractor
  chain that all hosts depend on, and widens a descriptor ENH-3165 already
  ships; mitigated by keeping normalization at the single chokepoint and
  regression-testing the Claude fixtures.
- **Breaking Change**: No.

## Status

**Completed** | Created: 2026-08-14 | Priority: P2 | Completed: 2026-08-14

## Related

- ENH-3165 — qwen subagent-transcript backfill (split from this issue; lands
  `subagent_runs` rows whose parent sessions this issue materializes)
- ENH-2918 — kimi wire-format parsing (same deferred posture, same descriptor)
- FEAT-3158 — qwen hook adapter + `ll-init` wiring (live capture tier)
- FEAT-3155 — qwen path-encoding spike (established `chats/` layout)
- ENH-2581 — `raw_events` + `rebuild()` split this issue extends

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | history.db schema — `raw_events`/rebuild pipeline (ENH-2581) |
| architecture | docs/reference/API.md | `ll-session backfill --host {claude-code,codex,opencode,pi}` — the host list this issue extends |
| reference | docs/reference/HOST_COMPATIBILITY.md | per-host support matrix |


## Session Log
- `/ll:manage-issue` - 2026-08-14T20:46:47 - `fd8937c3-89b1-4fdc-9d4b-c2bb53a7edfb.jsonl`
