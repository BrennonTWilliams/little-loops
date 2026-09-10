# Spike Plan: ENH-3430 — per-host `list_workspaces` union + cwd-dedupe for `--all`

## Context

ENH-3430's own Proposed Solution → Codebase Research Findings flags one
mechanism explicitly:

> **No existing precedent for step 2's per-host `list_workspaces` union**:
> `list_workspaces` has zero production callers anywhere in the codebase
> today... No shared "dedupe a list of `Path`s across hosts" utility exists
> in the codebase either... This step's mechanism is genuinely new code with
> no confirming precedent anywhere.
> ⚠ Unproven mechanism — no precedent for multi-host list_workspaces
> union/dedupe

Concrete failures this spike must rule out: **(a)** the mechanism has zero
precedent — no code anywhere iterates `_REGISTERED_HOSTS`, calls
`list_workspaces(host)` per host, and merges the results into one deduped
list; **(b)** no existing test exercises this because no production caller
exists yet, so the union/dedupe/filter algorithm the issue's step 2 prose
describes (`for h in hosts: for ws in list_workspaces(h, ...):
detect_sessions(ws, h, ...)`, dedupe on resolved cwd, re-apply the
ll-activity filter per workspace) has never run against real data.

The issue also calls out two specific hazards for this same mechanism that a
naive implementation could get wrong:
- calling `detect_sessions(ws, None)` per workspace instead of
  `detect_sessions(ws, h)` per host — silently multiplies the host-probe
  cost and breaks the union-dedupe contract (Impact → Risk);
- the same cwd can be recorded under two hosts with different **spellings**
  (a resolved vs. as-recorded path, e.g. macOS `/var/...` vs.
  `/private/var/...`) — must still collapse to one entry, not two (step 6).

## Approach

Build one library function, `union_workspaces(hosts, *, home)`, that
implements exactly the algorithm the issue's step 2 prescribes, calling the
**real** `little_loops.session_store.sessions.list_workspaces`,
`detect_sessions`, and `iter_events` — nothing about the seam itself is
faked. What's synthetic is the **fixture data**: a temp `home` directory
with hand-written Claude-Code-shaped and Codex-shaped project folders (both
formats the real parsers already read), so the spike drives the real
discovery/parsing code end-to-end without touching the developer's actual
`~/.claude`/`~/.codex`. The ll-activity filter re-applied per workspace is
the real `_is_ll_relevant` predicate from `little_loops.cli.logs`, called
against real parsed event payloads — not reimplemented, since for
`claude-code`/`opencode`/`pi` hosts `SessionEvent.payload` **is** the whole
Claude-shaped record (`_parse_claude_shaped`), the exact shape
`_is_ll_relevant` already expects.

## Critical files

Read-only references (production, not modified by this skill):

- `scripts/little_loops/session_store/sessions.py` — `list_workspaces`
  (483-531), `detect_sessions` (309-347, esp. the `host=None` union-and-sort
  branch at 333-340 — the exact anti-pattern step 2 says NOT to use per
  workspace), `iter_events` (852-857), `SessionHandle` (58+), `_REGISTERED_HOSTS`
  (286-295), `_cwd_spellings` (`user_messages.py:407-416`, imported into this
  module).
- `scripts/little_loops/cli/logs.py` — `_is_ll_relevant` (52-99, the filter
  to re-apply per workspace), `discover_all_projects` (171-231, the real
  integration point this spike proves the algorithm for, untouched here).

New spike paths:

- `scripts/tests/spike/enh3430_workspace_union/__init__.py`
- `scripts/tests/spike/enh3430_workspace_union/union.py`
- `scripts/tests/spike/enh3430_workspace_union/fixtures.py`
- `scripts/tests/spike/enh3430_workspace_union/test_union.py`

## Implementation

```
scripts/tests/spike/enh3430_workspace_union/
├── __init__.py
├── union.py            # union_workspaces(hosts, *, home) — the mechanism under test
├── fixtures.py          # write_claude_project()/write_codex_project() synthetic-home builders
└── test_union.py        # the AC test class
```

API sketch:

```python
# union.py
def union_workspaces(
    hosts: Sequence[str],
    *,
    home: Path,
    detect_sessions_calls: list[tuple[Path, str | None]] | None = None,
) -> list[Path]:
    """Per-host list_workspaces union, deduped on resolved cwd, ll-activity filtered.

    Mirrors ENH-3430 Proposed Solution step 2 exactly: iterate hosts (never
    detect_sessions(ws, None) per workspace), collect each host's
    list_workspaces(host, home=home), resolve+dedupe, then drop any
    workspace with no ll-relevant event (early-exit iter_events walk).
    If detect_sessions_calls is given, every (cwd, host) pair passed to
    detect_sessions is appended to it — the regression-guard test's spy.
    """
```

`fixtures.py` writes minimal real JSONL files under `home/.claude/projects/<encoded>/`
and `home/.codex/sessions/<date>/<uuid>.jsonl` (or wherever `_list_codex_workspaces`
reads from) so `list_workspaces`/`detect_sessions`/`iter_events` all run against
real files, not mocks.

## Acceptance Criteria → Test Table

| Test | Retires (AC / risk) | Kind |
|------|---------------------|------|
| `test_same_cwd_under_two_hosts_collapses_to_one_entry` | Risk (a): proves the core union/dedupe mechanism — a workspace recorded under both `claude-code` and `codex` appears once in the final list | behavior |
| `test_distinct_cwds_across_hosts_both_survive` | Risk (a): proves the dedupe does not over-collapse — two genuinely different workspaces (one per host) both appear | behavior |
| `test_resolved_vs_as_recorded_spelling_still_dedupes` | Step 6 hazard: two hosts record the *same* directory but with different string spellings (via a symlinked path, resolved vs. as-recorded) — still collapses to one entry | behavior |
| `test_ll_activity_filter_excludes_non_ll_workspace` | Risk (b): a real workspace with sessions but zero ll-relevant records is dropped from the union, matching `_has_ll_activity`'s existing exclusion behavior | behavior |
| `test_never_calls_detect_sessions_with_host_none_per_workspace` | Impact → Risk hazard: spies on every `detect_sessions` call made during the union and asserts `host` is always a concrete string, never `None` — guards against the documented cost-multiplication bug | regression-guard |
| `test_spike_does_not_import_cli_logs_discover_all_projects` | isolation guard: AST-sniffs `union.py` to confirm it never imports `discover_all_projects` itself (proves the mechanism, not a copy of the integration point) | regression-guard |

## Verification

```bash
python -m pytest scripts/tests/spike/enh3430_workspace_union/ -v
python -m pytest scripts/tests/test_session_discovery.py -v
python -m pytest scripts/tests/test_ll_logs.py -v -k TestDiscover
```

## Out of Scope

- Wiring `union_workspaces` (or its logic) into `discover_all_projects` /
  `cli/logs.py` itself — that is the real implementation, done separately.
- The other 11 `get_project_folder` call-site rewrites and the
  `_extract_ll_event_streams` handles-based signature (issue steps 1, 3, 4,
  5, 7, 8) — unrelated mechanisms, none flagged as unprecedented.
- `list_workspaces("omp")`'s always-`[]` lossy-encoding gap — documented,
  not fixed, in the issue itself; not this spike's concern.
- qwen/gemini/kimi-code/opencode/pi fixture coverage — two hosts
  (claude-code, codex) are sufficient to prove the union/dedupe/filter
  algorithm generalizes (it never branches on which two hosts collided).

## Promotion

On acceptance, promote `union.py`'s proven algorithm into
`discover_all_projects`'s `--all`/union-default path in
`scripts/little_loops/cli/logs.py` (issue step 2) in a separate PR — not a
literal move of `union.py` itself, since the real integration calls
`_is_ll_relevant` and `iter_events` inline rather than through a standalone
function. Update ENH-3430's Proposed Solution to note the proven shape:
per-host iteration first, dedupe on `str(Path.resolve())`, ll-activity
filter applied after dedupe (cheaper — skips the filter walk for
already-deduped duplicates).
