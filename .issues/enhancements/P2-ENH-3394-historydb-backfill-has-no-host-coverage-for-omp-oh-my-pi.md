---
id: ENH-3394
type: ENH
title: history.db backfill has no host coverage for omp (oh-my-pi)
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-06'
captured_at: '2026-09-06T03:39:22Z'
labels:
- backfill
- session-store
- omp
depends_on:
- ENH-3393
confidence_score: 95
outcome_confidence: 71
score_complexity: 16
score_test_coverage: 22
score_ambiguity: 15
score_change_surface: 18
---

# ENH-3394: history.db backfill has no host coverage for omp (oh-my-pi)

## Summary

`ll-session backfill --host omp` has no code path, mirroring the gap ENH-3393
fixed for `gemini`. omp (oh-my-pi) is a fully wired, production orchestration
host (`OmpRunner` in `host_runner.py`'s `_HOST_RUNNER_REGISTRY`) with a real
hook adapter (`hooks/adapters/omp/`, FEAT-2261 — `session_start` +
`post_tool_use` only), but its transcript-backfill tier has no host support:
`ll-session backfill --host` doesn't accept `"omp"`, `get_project_folder()`
has no omp branch, and `host_layout_for()` has no omp entry.

ENH-3393 (done) added the `HostLayout.normalize_file` contract this issue
reuses (a file-level normalizer hook, needed because — like gemini — omp's
session id lives only in a file header, not on each record) and split omp
out as "Recommended split" in that issue's Impact section, since qwen alone
took two issues (ENH-3165 + ENH-3166) for a friendlier record format, and omp
needs an additional decision gemini didn't (child-session `subagent_runs`
mapping).

## Current Behavior

- `scripts/little_loops/cli/session.py` — `ll-session backfill --host`
  choices do not include `"omp"`.
- `scripts/little_loops/user_messages.py` — `get_project_folder()`'s
  `if`/`elif` host chain has no `omp` branch; falls through to `None`.
- `scripts/little_loops/session_store/writers.py` — `host_layout_for()` has
  no `omp` branch; an `omp` host string degrades to the generic
  Claude-shaped default (`projects_root=None`, no normalizer).
- No `session_store/omp.py` normalizer module exists.

Net effect: `omp` sessions can never be recovered via `ll-session backfill
--host omp`. Their only path into `.ll/history.db` is the partial live-hook
tier (`session_start`/`post_tool_use` only, FEAT-2261) — a dropped/interrupted
live session, or any event type FEAT-2261 didn't wire, has no repair path.

## Expected Behavior

`ll-session backfill --host omp` walks omp's on-disk session-transcript
layout and populates `sessions`/`tool_events`/`raw_events` (and
`subagent_runs`, pending the child-session decision below), matching the
pattern ENH-3393 established for gemini and reusing its `HostLayout.
normalize_file` contract.

## Motivation

`omp` is a production orchestration host today (loops, sprints, and
subagents can run under it via `host_runner.py`, and it has a real hook
adapter per FEAT-2261), but its history is permanently unrecoverable once
the live-hook tier's `session_start`/`post_tool_use`-only coverage misses an
event, or a session predates `ll-init`. Every other wired host got a
dedicated backfill fix when this gap was found (ENH-1945 for codex/pi,
ENH-3165/3166 for qwen, ENH-3393 for gemini); omp was the deliberate
carve-out from ENH-3393 rather than an oversight, but it still needs its own
issue so the coverage matrix doesn't silently drift further from the
orchestration layer's actual host list.

## Proposed Solution

Follow ENH-3393's gemini implementation as the structural template — one
`host_layout_for()` branch, a `session_store/omp.py` file-level normalizer
(`normalize_omp_session(path: Path) -> Iterator[dict]`), a
`_get_omp_project_folder(cwd)` helper plus `get_project_folder()` branch, and
the `--host omp` CLI wire-in — but omp's on-disk shape differs from gemini's
in ways ENH-3393's "Verified Host Layouts" section already documented from
the vendored omp 18.0.11 source
(`scripts/little_loops/hooks/adapters/omp/node_modules/@oh-my-pi/pi-coding-agent/src/session/`);
re-verify against whatever omp version is vendored when this issue is
implemented.

**omp** (`~/.omp/`):
- Sessions root: `~/.omp/agent/sessions/` (`pi-utils/src/dirs.ts:872`,
  `getSessionsDir`); `PI_CONFIG_DIR` overrides `.omp`; `XDG_DATA_HOME`
  flattens to `$XDG_DATA_HOME/omp/sessions`.
- Project folder encoding (`pi-coding-agent/src/session/session-paths.ts:40-90`):
  cwd under `$HOME` → `-<home-relative with /\: → ->` (dots preserved); cwd
  under `os.tmpdir()` → `-tmp-<rel>`; other absolute → legacy `--<abs sans
  leading />--`. A transitional `<scope>-<basename>-<sha256hex>` form from omp
  17.2.5–17.2.8 may also exist; omp migrates old `--<home>-…--` dirs to the
  new form on first access (`migrateHomeSessionDirs`).
- Session files: `<ts with :. → ->_<sessionId>.jsonl`
  (`session-manager.ts:1142`). Child/subagent sessions:
  `<parent stem>/<agentId>.jsonl` — a sibling dir named after the parent file
  minus `.jsonl` (`session-manager.ts:139-151`; also the artifacts dir). This
  matches neither `parent_from="parent_dir"` nor `"child_dir"`; a third mode
  (`"stem_dir"`) or a per-host callable is needed if `subagent_runs` is
  populated for omp.
- Record format (`session-entries.ts:28-80`): header `{type: "session",
  version?, id, title?, timestamp, cwd, additionalDirectories?,
  parentSession?}`; then `{type: "message", id, parentId, timestamp, message:
  {role, content}}` plus `thinking_level_change`, `model_change`,
  `compaction`, `custom` entries. Header key is `id` (not `sessionId`) and
  message entries carry no session id.
- omp has no sessions on disk on the ENH-3393 dev machine (binary not on
  PATH, `~/.omp/agent/sessions` absent) — build fixtures from the vendored
  `session-entries.ts` types, labeled as synthesized (not sanitized real
  captures, unlike gemini's).

Note: the existing `pi` entries (`~/.pi/projects` in both
`_get_pi_project_folder` and `host_layout_for`) are also wrong — real pi
writes `~/.pi/agent/sessions/--<abs>--/` (omp's legacy encoding is pi's
current one). Out of scope here too, but shape `encode_omp_session_dir`/
`_get_omp_project_folder` so a follow-up pi fix is a one-line reuse.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/session.py` — `backfill --host` choices: add
  `"omp"`
- `scripts/little_loops/user_messages.py` — `get_project_folder()`: new
  `elif host == "omp"` branch calling `_get_omp_project_folder(cwd)`
- `scripts/little_loops/session_store/writers.py` — `host_layout_for()`: new
  dedicated `omp` branch
- `scripts/little_loops/session_store/omp.py` (new) — omp file-level
  normalizer
- `scripts/little_loops/session_store/__init__.py` — export
  `normalize_omp_session` mirroring `normalize_gemini_session`
- `docs/reference/HOST_COMPATIBILITY.md` — session-store table, add the
  `omp` column (gemini's column landed in ENH-3393)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/session.py:664,702` — `main_session()` calls
  `get_project_folder(host=args.host)` (both the `--since` and full-backfill
  branches)
- `scripts/little_loops/cli/session.py:672,705` — `main_session()` calls
  `host_layout_for(_backfill_host)` to resolve `sessions_subdir` for the
  JSONL glob
- `scripts/little_loops/user_messages.py:439,444` — `get_sessions_folder()`
  calls both `get_project_folder()` and (lazily imported at `:442`)
  `host_layout_for()`
- `scripts/little_loops/session_store/lifecycle.py:774` (`_backfill_raw_events`),
  `:1110` (`backfill`) — call `host_layout_for(host)` for `normalize_file`/
  `skip_at_ingest`
- `scripts/little_loops/session_store/writers.py:2358`
  (`_backfill_subagent_runs`), `:2946` (`_iter_events`) — call
  `host_layout_for` for `parent_from` and `normalize` respectively

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/logs.py:106,143,195,287,645,649,653,658,667,693,774,783,1344,1355,1360,1369,1556,2034`
  — calls `host_layout_for()`/`get_project_folder()` throughout; in
  particular `discover_all_projects(logger, *, host=None)` (`:195`) resolves
  `layout.projects_root` per host — once `host_layout_for("omp")` registers a
  `projects_root`, `ll-logs` project-discovery commands begin surfacing omp
  projects (today they return `[]` silently, per the "unregistered hosts...
  surface as None" comment at `:192-194`)
- `scripts/little_loops/cli/backfill_worker.py:57,59-60` — the detached
  backfill worker (spawned by `session_start.py`, BUG-1882/ENH-3166) resolves
  `layout = host_layout_for(host if host is not None else "claude-code")`
  then reads `layout.session_glob` — this is the live-hook backfill call
  path FEAT-2261's omp `session_start` hook already invokes today with
  `--host omp`
- `scripts/little_loops/hooks/session_start.py:162,178-179` — calls
  `get_project_folder(cwd)` (no explicit `host` arg — relies on auto-detect)
  to build the synchronous backfill-worker path arg, then passes
  `_backfill_host = event.host or LL_HOOK_HOST` as `--host` to
  `backfill_worker.py` above — confirms omp's live-hook tier already
  exercises this exact code path in production and currently gets no folder
  resolution for omp
- `scripts/little_loops/cli/messages.py:31,173` — `ll-messages` imports and
  calls `get_project_folder(cwd)`

### Similar Patterns
- ENH-3393 — gemini backfill + the `HostLayout.normalize_file` contract this
  issue reuses directly
- ENH-3165 / ENH-3166 — qwen backfill + wire-format normalizer

### Tests
- `scripts/tests/test_user_messages.py` — `get_project_folder` cases for
  `omp` (home-relative, tmp-relative, legacy `--abs--`, and
  `PI_CONFIG_DIR`/`XDG_DATA_HOME` overrides), plus `encode_omp_session_dir`
  unit cases including a `.worktrees` path (dot must survive)
- `scripts/tests/test_enh_omp_normalizer.py` (new), mirroring
  `scripts/tests/test_enh_3393_gemini_normalizer.py`, with synthesized
  fixtures at `scripts/tests/fixtures/omp/` built from the vendored
  `session-entries.ts` types (labeled as synthesized, not real captures)
- `scripts/tests/test_enh_3166_qwen_normalizer.py`'s
  `test_gemini_and_omp_have_no_static_projects_root` — flip the `omp` half
  of this assertion once `host_layout_for("omp")` is registered (currently
  passes because omp falls through to the unregistered-host default)
- `scripts/tests/test_ll_session.py::test_backfill_host_choices_list` — add
  `"omp"` to the accepted-choices list and drop the `SystemExit` case for it
- `scripts/tests/test_enh_2505_subagent_runs.py` — add an `omp`
  `host_layout_for` case if the `<parent stem>/<agentId>.jsonl` child-session
  layout is mapped into `subagent_runs`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh_3393_gemini_normalizer.py:239-306`
  (`TestRebuildGeminiRecords`) — the gemini test file has a fifth class
  beyond the "four-layer structure" this issue's own Codebase Research
  Findings names; a `TestRebuildOmpRecords` sibling (verifying `rebuild()`
  correctly derives `tool_events`/`message_events`/`assistant_messages`/
  `sessions` cache rows from omp `raw_events`) is required since this
  issue's own Call Path already routes through "rebuild extractors" — not
  currently named in this section
- `scripts/tests/test_enh_2505_subagent_runs.py` — a
  `TestOmpSubagentBackfill.test_no_subagents_dir_yields_zero_rows` case
  (mirroring `TestGeminiSubagentBackfill` at `:717-736`) is available and
  should be added regardless of the `parent_from`/child-session decision —
  it exercises the no-match branch of `_backfill_subagent_runs`, which is
  identical no matter which `parent_from` mode omp eventually gets. The
  bullet above ("add an `omp` case **if** ... mapped") incorrectly gates
  this specific no-op case on that decision; it is not gated.

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md` — session-store table (add `omp`
  column, mirroring the `[^geminiwire]` footnote pattern)
- `docs/reference/API.md` — `get_project_folder`/`get_sessions_folder`
  docstrings: add `"omp"` to the host vocabulary list
- `docs/reference/CLI.md` — `backfill --host` flags table: add `omp`
- `docs/guides/HISTORY_SESSION_GUIDE.md` — "Incremental backfill" example
  commands: add an `omp` example

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:3435,3439-3441,3464-3477` — `get_project_folder`'s
  docstring has three separate host-enumeration sites (prose sentence, the
  `host` param's enum list, and the `_get_<host>_project_folder`
  internal-helpers bullet list), not a single "vocabulary list" — add `omp`
  to all three, including a new `_get_omp_project_folder(cwd: Path) -> Path
  | None` bullet matching this issue's own Program Design signature
- `docs/reference/API.md:3526-3543` — `discover_all_projects()`'s docstring
  (function lives in `cli/logs.py`, see Dependent Files above) repeats the
  same host-list, also missing `omp`
- `docs/guides/HISTORY_SESSION_GUIDE.md:232` — a second, prose-only `--host`
  choices enumeration ("valid choices also include `pi`, `kimi-code`,
  `qwen`, and `gemini`") separate from the example code block at `:226-230`
  — "add an `omp` example" above doesn't cover this sentence; append `omp`
  here independently
- `docs/reference/HOST_COMPATIBILITY.md:511-521` — clarify: "add the omp
  column" is a 7-row addition (Config file, Issue tracking, FSM runs,
  Scratch pads, Continuation prompt, Session store, Session logs), not a
  single cell. 6 rows are mechanical `(same path)[^state]` copies — the
  `[^state]` footnote (`:527-538`) already lists omp among the hosts that
  keep these surfaces shared. Only the Session logs row needs new
  omp-specific prose/footnote (e.g. `[^ompwire]`) describing the
  `~/.omp/agent/sessions/` layout from this issue's own Program Design.
- `docs/reference/HOST_COMPATIBILITY.md:523-525` — the placeholder paragraph
  ("`ll-session backfill --host omp` is tracked separately... omp has no
  dedicated row here yet") must be removed once the column lands.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-06 — based on codebase analysis:_

- `host_layout_for()`'s host registry (`scripts/little_loops/session_store/writers.py:2219-2276`) is a flat `if`/`elif` chain; the generic fallback tail — the shape `omp` currently falls into — spans `:2263-2276`, with its `projects_root` dict lookup at `:2263-2268` keyed only on `{claude-code, codex, opencode, pi}` (`omp` isn't a key, so `.get()` resolves to `None`).
- `HostLayout` and its `normalize_file` field are defined at `writers.py:2147-2203` (`normalize_file` at `:2179-2189`); qwen's dedicated branch is `:2237-2249`, gemini's is `:2253-2262` — the direct structural precedent for a new `omp` branch.
- `get_project_folder()`'s host dispatch chain is `scripts/little_loops/user_messages.py:371-415`; the `if`/`elif` ladder is `:401-414`, falling through to `return None` at `:415` for any unmatched host (no explicit error raised).
- `_get_gemini_project_folder()` (`user_messages.py:530-556`) is the `cwd`-based helper template `_get_omp_project_folder` should follow (per this issue's own Program Design), not the `encoded_path`-based helpers — its docstring states why: index/registry-resolved hosts need the raw `cwd`, not a pre-encoded string.
- `ll-session backfill --host`'s `choices=[...]` list is `scripts/little_loops/cli/session.py:213`; `main_session()`'s two `get_project_folder(host=args.host)` call sites are `:664` (`--since` path) and `:702` (full-backfill path), with the paired `host_layout_for(_backfill_host)` calls at `:672`/`:705`.
- `session_store/__init__.py`'s normalizer export convention: gemini's import is at `:65`, its `__all__` entry at `:215`; qwen's import is at `:97`, its `__all__` entries at `:216-217` — `normalize_omp_session` follows the same two-site pattern.
- `test_no_subagents_dir_yields_zero_rows` (`scripts/tests/test_enh_2505_subagent_runs.py:717-736`) confirms an empty subagent glob yields zero rows, not an error — the relevant precedent given omp, like gemini, has no real session captures to test against yet.
- `test_backfill_host_choices_list` (`scripts/tests/test_ll_session.py:41-60`) is the CLI-layer regression lock; it currently asserts `"omp"` raises `SystemExit` and its docstring states "Update this list AND the docs together when adding a host."

_Added by `/ll:refine-issue` — 2026-09-06 — based on codebase analysis:_

- File-level normalizers are registered through one shared shape: each host with a header-only session id gets its own `session_store/<host>.py` module exposing `normalize_<host>_session(path: Path) -> Iterator[dict]`, which opens the file itself, tolerates malformed lines/missing files by skipping rather than raising, and yields fully Claude-shaped dicts with the session id stamped from the header on every record — evidence: `session_store/gemini.py:1-31,40-75` (module docstring + function), mirrored by the record-level sibling contract in `session_store/qwen.py:59` (`normalize_qwen_record`).
- New hosts register in `host_layout_for()` via a dedicated `if host == "<name>":` branch that lazily imports its normalizer inside the branch (not at module top-level) and returns a fully-specified `HostLayout(...)` — evidence: qwen's branch (`writers.py:2237-2249`), gemini's branch (`writers.py:2253-2262`, `normalize_file=normalize_gemini_session` set, `normalize`/`skip_at_ingest` left at their defaults since the two contracts are mutually exclusive per the class docstring at `:2179-2189`).
- The `_get_<host>_project_folder` helper's signature (`encoded_path: str` vs `cwd: Path`) tracks how the host maps cwd to its folder, not a fixed convention: dash-encoding hosts (claude-code/codex/opencode/pi/qwen) take pre-computed `encoded_path`; index/registry-resolved hosts (kimi via `session_index.jsonl`, gemini via `~/.gemini/projects.json`) take raw `cwd` and resolve internally — both kimi's and gemini's own docstrings state this reasoning explicitly (`user_messages.py:511-527`, `:530-556`), and this issue's own Program Design already follows the `cwd`-based shape for `_get_omp_project_folder`, consistent with that split.
- A new normalizer's public function is exported at two sites in `session_store/__init__.py`: a top-level `from little_loops.session_store.<host> import normalize_<host>_session` plus an `__all__` entry — evidence: gemini's import (`:65`) and `__all__` entry (`:215`); qwen's import (`:97`) and `__all__` entries (`:216-217`).
- New-host test modules share one four-layer structure in a single file (`TestNormalize<Host>...` unit tests on the normalizer in isolation; `TestHostLayoutRegistry` asserting `host_layout_for` field values plus negative "other hosts unaffected" tests; `TestBackfillRawEventsNormalizeFile`/integration tests through `backfill_raw_events(...)`; a `TestClaudeParity...` regression class proving Claude-shaped ingestion is unchanged) — evidence: `scripts/tests/test_enh_3393_gemini_normalizer.py` and `scripts/tests/test_enh_3166_qwen_normalizer.py`, both with a per-file `FIXTURES` path constant and a module docstring stating fixture provenance (gemini's are labeled synthesized, qwen's labeled sanitized-real-capture) — the convention this issue's own Tests section already commits to following for omp's synthesized fixtures.

## Program Design

### Signatures

- `_get_omp_project_folder(cwd: Path) -> Path | None` — new branch in
  `get_project_folder()`; returns `<sessions_root>/<omp-encoded cwd>` where
  `sessions_root` is `$XDG_DATA_HOME/omp/sessions` if set else
  `~/<PI_CONFIG_DIR or .omp>/agent/sessions`, probing the current encoding
  first and then the legacy encoding.
- `encode_omp_session_dir(cwd: Path) -> str` — omp's cwd encoding
  (home-relative `-<rel>`, tmp-relative `-tmp-<rel>`, else `--<abs>--`, with
  `/\:` → `-` and dots preserved). Separate from `encode_project_path`
  (Claude's every-non-alnum scheme, which would mangle `.worktrees`).
- `normalize_omp_session(path: Path) -> Iterator[dict]`
  (`session_store/omp.py`) — file-level normalizer (same
  `HostLayout.normalize_file` contract ENH-3393 added): reads the
  `{type:"session", id, cwd, parentSession?}` header, yields Claude-shaped
  records from `{type:"message", message:{role, content}}` entries, drops
  `model_change`/`thinking_level_change`/`compaction` entries (or routes them
  to `skip_at_ingest`).
- `host_layout_for("omp")` — new branch using `normalize_file=
  normalize_omp_session`; decide the `parent_from` mode (new `"stem_dir"` or
  a per-host callable) if child-session `subagent_runs` mapping is in scope.

### Call Path

`ll-session backfill --host omp` -> `get_project_folder` ->
`_get_omp_project_folder` (new, `cwd`-based) -> `host_layout_for` ->
`HostLayout` (with `normalize_file=normalize_omp_session`) -> `backfill` ->
`_backfill_raw_events` (uses `normalize_file` to stamp `session_id`, per the
ENH-3393 contract) -> `rebuild` extractors -> `_backfill_subagent_runs` (if
child-session dirs are mapped)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-06 — based on codebase analysis:_

- `_backfill_raw_events`'s `normalize_file` branch (`scripts/little_loops/session_store/lifecycle.py:747-831`, the `layout.normalize_file is not None` gate at `:777-798`) stores the **normalized** record as both `raw_line` and `parsed_json` — there is no verbatim per-line source once file-level unpacking has happened, per `test_raw_line_and_parsed_json_are_normalized_form`. This applies identically to `normalize_omp_session`: `raw_events.raw_line` for omp rows will hold the re-serialized Claude-shaped record, not the original omp JSONL line.
- `_backfill_subagent_runs`'s `parent_from` branch (`writers.py:2339-2366`, `host_layout_for` call site at `:2358`) recognizes exactly two values today — `"parent_dir"` (default: parent id = `container.parent.name`) and `"child_dir"` (qwen's inverted layout: parent id = `container.name`). No `"stem_dir"` mode exists anywhere in `writers.py`/`lifecycle.py`/any test — confirmed by a repo-wide search — so mapping omp's `<parent stem>/<agentId>.jsonl` layout requires adding a new mode there or a per-host callable, exactly as this issue's Scope Boundaries section already flags as an explicit decision to record.
- `host_layout_for()` never raises for an unregistered host (docstring, `writers.py:2222-2226`): the `--host` `choices=[...]` list at `cli/session.py:213` is what currently prevents an unsupported host from reaching the backfill path at all, not any internal validation in `get_project_folder()` or `host_layout_for()` themselves.

## Implementation Steps

1. Decide the `subagent_runs` child-session question (a new `parent_from:
   "stem_dir"` mode vs. a per-host callable) before writing the normalizer,
   since it shapes whether `session_store/omp.py` needs to expose a
   directory-walk helper alongside `normalize_omp_session`.
2. Add `session_store/omp.py` (file-level normalizer reusing the
   `HostLayout.normalize_file` contract from ENH-3393), `_get_omp_project_folder`
   + `encode_omp_session_dir` in `user_messages.py`, and the `omp`
   `host_layout_for()` branch.
3. Wire `--host omp` through `ll-session backfill` (`cli/session.py` choices)
   and update `test_backfill_host_choices_list`'s expectations.
4. Add synthesized fixtures (from the vendored `session-entries.ts` types,
   labeled as synthesized — omp has no real captures on the ENH-3393 dev
   machine) and tests mirroring `test_enh_3393_gemini_normalizer.py`.
5. Update `docs/reference/HOST_COMPATIBILITY.md` (add the `omp` column),
   `docs/reference/API.md`, `docs/reference/CLI.md`, and
   `docs/guides/HISTORY_SESSION_GUIDE.md`.
6. Run `python -m pytest scripts/tests/` to confirm the Claude/qwen/gemini
   fixtures are unaffected (the `HostLayout.normalize_file` contract is
   additive; this issue must not touch its ENH-3393 regression tests).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Sanity-check `cli/backfill_worker.py:57,59-60` and
  `hooks/session_start.py:162,178-179` once `host_layout_for("omp")` and
  `get_project_folder(..., host="omp")` are wired — no code change is
  expected in either file (both already pass `host` through generically),
  but they are today's silent consumers of this gap: FEAT-2261's omp
  `session_start` hook already invokes the backfill worker with `--host
  omp` in production, so this issue's fix takes effect on the next live omp
  session without further hook changes. Confirm this with a smoke test.
- Update `docs/reference/API.md` — three enumeration sites under
  `get_project_folder` (prose, param docstring, internal-helpers bullet
  list) plus the `discover_all_projects` docstring
- Update `docs/guides/HISTORY_SESSION_GUIDE.md:232` — the prose `--host`
  choices sentence, in addition to the example command block
- Update `docs/reference/HOST_COMPATIBILITY.md`'s "State directory" table
  (add an Omp CLI column across all 7 rows, new `[^ompwire]` footnote for
  the Session logs row) and remove the now-superseded placeholder paragraph
  at `:523-525`
- Add `TestRebuildOmpRecords` to the new omp normalizer test file, mirroring
  `TestRebuildGeminiRecords` (`test_enh_3393_gemini_normalizer.py:239-306`)
- Add `TestOmpSubagentBackfill.test_no_subagents_dir_yields_zero_rows`
  (independent of the `parent_from`/child-session decision)

## Impact

- **Priority**: P2 — observability gap, not data loss; source transcripts
  persist on disk (when they exist) so recovery remains possible once
  implemented.
- **Effort**: Medium — the `HostLayout.normalize_file` contract already
  exists (ENH-3393); this issue is "one more host" plus the child-session
  `subagent_runs` decision gemini didn't need.
- **Risk**: Low — additive host branch; the contract this issue depends on
  is already regression-locked against Claude/qwen fixtures by ENH-3393.
- **Breaking Change**: No.

## Scope Boundaries

**In scope**: `_get_omp_project_folder`/`encode_omp_session_dir` in
`user_messages.py`; the `omp` `host_layout_for()` branch and
`session_store/omp.py` normalizer; wiring `--host omp` into `ll-session
backfill`; fixtures (synthesized from `session-entries.ts`); the
`HOST_COMPATIBILITY.md` session-store table's `omp` column.

**Explicit decision the implementer must record**: whether omp child sessions
(`<parent stem>/<agentId>.jsonl`) map into `subagent_runs` in this issue or a
further follow-up — the `parent_from` mode doesn't exist yet (`"stem_dir"` or
a per-host callable).

**Out of scope**: improving omp's live-hook coverage beyond
`session_start`/`post_tool_use` (separate issue against FEAT-2261's
follow-up); any change to `omp` orchestration in `host_runner.py`; fixing
`pi`'s existing `~/.pi/projects` entries (capture as a follow-up, but shape
this issue's helpers so that fix is a reuse).

## Related

- ENH-3393 (done) — HostLayout.normalize_file contract + gemini backfill;
  this issue builds on it
- ENH-1945 — host-aware session-log discovery (codex, pi)
- ENH-3165 / ENH-3166 — qwen subagent transcript backfill + normalizer
- FEAT-2261 — omp session_start/post_tool_use hook wiring (live-hook tier;
  this issue does not extend that work)
- P4-EPIC-2258 — oh-my-pi (omp) host adapter tracking (done)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-06 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-09-06T04:53:40 - `3b34c35b-9273-4059-80be-11dd20598e17.jsonl`
- `/ll:wire-issue` - 2026-09-06T04:37:09 - `40599667-8ac5-47aa-88f2-6a2e34850427.jsonl`
- `/ll:refine-issue` - 2026-09-06T03:57:16 - `fb75bfe7-573f-4313-a50e-f7fd15a75fa9.jsonl`
