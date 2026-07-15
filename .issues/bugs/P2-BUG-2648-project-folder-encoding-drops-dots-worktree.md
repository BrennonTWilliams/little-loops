---
id: BUG-2648
type: bug
status: open
priority: P2
captured_at: '2026-07-15T18:22:18Z'
discovered_date: 2026-07-15
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 79
score_complexity: 19
score_test_coverage: 22
score_ambiguity: 18
score_change_surface: 20
---

# BUG-2648: get_project_folder encoding drops dots, breaks session resolution in worktrees

## Summary

`get_project_folder()` maps the cwd to the host's session-log directory using a
naive `path_str.replace("/", "-")` encoding (`scripts/little_loops/user_messages.py:382`).
Claude Code's actual project-folder encoding replaces **all** non-alphanumeric
characters (including `.`) with `-`, not just slashes. Any cwd containing a
dotted path segment therefore resolves to a folder that does not exist, so
`get_project_folder()` returns `None` and every session-JSONL lookup silently
fails.

This surfaces most often under git **worktrees**, whose paths contain
`.worktrees/` — exactly how `ll-parallel` / `ll-sprint` waves / subloop epics
lay out isolated checkouts. An autodev FSM subloop running in
`ll-labs/cards/.worktrees/…` reported:

> The ll-issues append-log failed to resolve a session JSONL

## Root Cause

**File**: `scripts/little_loops/user_messages.py`
**Function**: `get_project_folder` → `_get_claude_project_folder`

```python
# user_messages.py:382
encoded_path = path_str.replace("/", "-")   # only handles "/"
```

Concrete divergence for a worktree cwd
`/Users/brennon/AIProjects/ai-workspaces/ll-labs/cards/.worktrees/20260715-125040-subloop-epic-epic-495-…`:

| source | encoded folder |
|---|---|
| little-loops produces | `…cards-.worktrees-20260715-…` (dot kept) |
| Claude Code created on disk | `…cards--worktrees-20260715-…` (`/.` → `--`) |

`_get_claude_project_folder` does `project_folder.exists()` → `False` →
`get_project_folder` returns `None` →
`session_log.get_current_session_jsonl()` returns `None` →
`append_session_log_entry()` returns `False` →
`ll-issues append-log` prints "could not resolve session JSONL; entry not written."
(`scripts/little_loops/cli/issues/append_log.py:29`).

## Impact

The base project path (no dots) resolves fine, so this only manifests in dotted
cwds — but that includes every `.worktrees/`-based run. Beyond `append-log`, the
same broken resolver feeds:

- `get_current_session_id()` — issue-event `session_id` stamping (ENH-2462)
- the FSM prompt-mode payload builder
- `complete_issue_lifecycle` session linking

All silently degrade under worktrees (no session id recorded, empty session
links), so worktree-run history/analytics lose session provenance.

## Integration Map

### Files to Modify
- `scripts/little_loops/user_messages.py:382` — the single production encoder
  (`path_str.replace("/", "-")`). This is the **only** place encoding happens;
  all four `_get_*_project_folder` helpers (lines 395–416) consume the one shared
  `encoded_path`, so fixing this line fixes every host and every caller at once.

### Dependent Files (Callers — all route through `get_project_folder`, so all inherit the fix)
- `scripts/little_loops/session_log.py` — `get_current_session_jsonl()`,
  `get_current_session_id()`, `append_session_log_entry()` (primary internal chain)
- `scripts/little_loops/cli/issues/append_log.py:29` — `cmd_append_log()` (the
  `ll-issues append-log` surface that reported the symptom)
- `scripts/little_loops/cli/session.py:504,534` — `get_project_folder(host=...)`
- `scripts/little_loops/cli/messages.py:173`
- `scripts/little_loops/cli/logs.py:561,570,670,679,1038,1047,1647`
- `scripts/little_loops/cli/ctx_stats.py:282` (cache-hit-rate stats)
- `scripts/little_loops/fsm/executor.py:1554` — `get_current_session_jsonl()`
  (FSM prompt-mode payload builder)
- `scripts/little_loops/hooks/session_start.py:146`
- `scripts/little_loops/parallel/orchestrator.py:1677` — `append_session_log_entry()`
  for worktree wave runs (`ll-parallel` / `ll-sprint`); this is the **highest-value
  site** — worktree cwds are exactly where the bug bites, so this call currently
  fails on every dotted `.worktrees/` checkout.
- `scripts/little_loops/issue_lifecycle.py:36,734` — `get_current_session_id()` +
  `append_session_log_entry()` (`complete_issue_lifecycle` session linking)

### Round-Trip Consumer (must stay consistent with the new scheme)
- `scripts/little_loops/cli/logs.py:137` — `discover_all_projects()` re-encodes
  the real cwd (preferred from JSONL `cwd` field via `_extract_cwd_from_project`)
  back through `get_project_folder(decoded_path)` (line 570). The fix must produce
  folder names matching Claude Code's on-disk scheme for this round-trip to hold.
  Its fallback lossy decode `project_dir.name.replace("-", "/")` (line 188)
  already documents the current scheme's ambiguity — no change required, but note
  the reverse decode remains inherently lossy (dots/slashes/hyphens all collapse
  to `-`, so a decode can't be exact; the `cwd`-from-JSONL preference is what
  keeps it correct).

### Tests
- `scripts/tests/test_user_messages.py` — `TestGetProjectFolder` (lines 79–226):
  the class the new AC#3 regression test belongs in. Model after
  `test_host_claude_code_probes_claude_projects` (line 101) and the format-only
  `test_path_conversion_format` (line 88).
- `scripts/tests/test_ll_logs.py:1420` — `TestExtract._make_project_dir()`:
  reusable fixture builder that explicitly comments its encoding "must track
  `get_project_folder`" — its `.replace("/", "-")` line must be updated in lockstep.
- `scripts/tests/test_session_log.py:316`, `scripts/tests/test_cli.py:2979` —
  additional fixtures duplicating the encoding.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_logs.py` — the fixture duplication is **wider than
  line 1420**: the `.replace("/", "-")` encoding is independently copy-pasted at
  lines 93, 367, 407, 448, 818, 1387, 1724, 2356, 3296, 3533 (in addition to the
  known ~1447). Each must be updated in lockstep — includes
  `TestSequences._make_project_dir()` (~818), `TestScanFailures._make_project_dir()`
  (~2356), `TestEvalExport._setup_project_folder()` (~3296, comments it mirrors
  `TestExtract`), and `TestEvalExportRoundTrip._make_project_dir()` (~3533), plus
  inline fixtures in `test_discover_json_output` / `test_discover_json_short_flag`
  / `test_extract_skips_agent_jsonl`. [Agent 3 finding]
- `scripts/tests/test_session_log.py:348` — a **second** encoding duplication in
  `TestSessionLogHostAware` beyond the known line 316; update in lockstep. [Agent 3 finding]
- `scripts/tests/test_user_messages.py:88` — `test_path_conversion_format` is the
  one test whose **assertion itself** hardcodes the old encoding
  (`expected_encoded = "-Users-test-my-project"`); its expected value (not just
  fixture code) must change to the new regex scheme. [Agent 3 finding]
- All dotless fixtures above **pass unchanged** either way (dotless strings encode
  identically under slash-only vs. full-non-alphanumeric rules) — these are
  update-for-consistency, not break-and-fix. The real coverage gap is that **no
  existing test uses a dotted / `.worktrees/`-style subpath**. New tests needed:
  (a) a dotted-path case in `TestGetProjectFolder` modeled on
  `test_host_claude_code_probes_claude_projects` asserting a `.worktrees/` cwd
  resolves to the dash-collapsed folder (AC#3); (b) a `_make_project_dir`-style
  round-trip integration test in `test_ll_logs.py` (`TestExtract`/`TestSequences`)
  with a dotted `subpath`, proving `discover`/`extract` still finds the project.
  [Agent 3 finding]
- Insulated from the change (mock `get_project_folder` at return-value level, no
  edits needed): `test_hook_session_start.py`, `test_cli_ctx_stats.py`,
  `test_cli_messages.py`, `test_ll_session.py`, `test_orchestrator.py:3505`. [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `### get_project_folder` section (~lines 2774–2820):
  authoritative external description of the encoding contract; its example
  (`my-project`, dotless) stays correct, but the section does **not** state the
  dot-handling rule at all — add it so the contract is documented. [Agent 2 finding]
- `docs/reference/API.md` — `### discover_all_projects` section: documents the
  **decode** side in prose ("falling back to string-replacing `-` with `/`") — the
  inverse operation whose correctness depends on the encode side. Reconcile this
  wording with the paired `cli/logs.py:137` decode fix; it is the only place the
  round-trip contract is stated in English. [Agent 2 finding]
- No `commands/*.md`, `skills/*/SKILL.md`, config schema, or asserted
  error-message string is coupled to the encoding scheme — confirmed no changes
  needed there. The `.ll/decisions.yaml` `ARCHITECTURE-004` (ENH-1945) entry
  concerns `get_project_folder`'s host-**parameter** shape, not its internal
  encoding, so it is not invalidated — but it sets the "internal-only change, zero
  call-site breakage" precedent this fix should honor. [Agent 2 finding]

## Implementation Steps

1. In `_get_claude_project_folder` (and, host-scheme permitting, the codex /
   opencode / pi variants), encode with the full non-alphanumeric rule instead
   of slash-only: `re.sub(r"[^a-zA-Z0-9]+", "-", path_str)`. Move the encoding
   into each `_get_*_project_folder` so per-host schemes can diverge, rather than
   encoding once before the host branch at line 382.
2. Confirm Claude Code's exact sanitization (single vs collapsed dashes for
   consecutive specials) against on-disk folders before finalizing the regex —
   the observed `--` shows consecutive specials each map to a dash.
3. Keep the `.exists()` guard; if no encoding matches, still return `None`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. Update `docs/reference/API.md` — state the dot-handling rule in the
   `### get_project_folder` section, and reconcile the `### discover_all_projects`
   decode-algorithm prose with the paired `cli/logs.py:137` fix (the only
   English-language statement of the round-trip contract).
5. Update **all** `test_ll_logs.py` fixture duplications in lockstep (lines 93,
   367, 407, 448, 818, 1387, ~1447, 1724, 2356, 3296, 3533), plus
   `test_session_log.py:348` (second occurrence beyond 316) and
   `test_user_messages.py:88` (`test_path_conversion_format` — change the
   asserted `expected_encoded`, not just the fixture builder).
6. Add the dotted-path regression test in `TestGetProjectFolder` (AC#3) and a
   `_make_project_dir`-based round-trip integration test in `test_ll_logs.py`
   with a dotted `subpath` — no existing test exercises a `.worktrees/` segment.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Single production encoder, 22 test-fixture duplications.** Grep for
  `.replace("/", "-")` returns 23 hits: exactly 1 in production
  (`user_messages.py:382`) and 22 across `test_user_messages.py`,
  `test_session_log.py`, `test_ll_logs.py`, and `test_cli.py`. Every test that
  builds a fake `~/.claude/projects/<encoded>` layout re-derives the encoding
  inline rather than importing a shared helper — so those fixtures will keep
  passing on dotless `tmp_path` but do **not** exercise the dotted-path bug. The
  new regression test must construct its expected folder name with the *fixed*
  encoding (not `.replace("/", "-")`), or it silently won't test the fix.
- **`CLAUDE_SESSION_ID` masks the bug in some contexts.**
  `get_current_session_id()` (`session_log.py:109`) returns the
  `CLAUDE_SESSION_ID` env var when a host sets one, bypassing the folder-encoding
  path entirely. So the `session_id`-stamping degradation (ENH-2462) only
  manifests when that env var is unset — reproduction must clear it.
- **`re.sub` sanitizer precedent already exists** (no shared helper to reuse,
  each is a local one-liner): `fsm/executor.py:842`
  (`re.sub(r"[^a-zA-Z0-9-]", "-", worktree_branch)`), `cli/loop/run.py:427`,
  `sync.py:679`. The proposed `re.sub(r"[^a-zA-Z0-9]+", "-", path_str)` follows
  the same convention; note these branch-name variants keep `-` in the allowed
  set — the project-folder rule must *not* (a literal `-` in the source path must
  still map to `-`, which `[^a-zA-Z0-9]+` handles, and consecutive specials
  collapse via `+`, matching the observed on-disk `--`).
- **Failure is silent end-to-end** except at the CLI edge. `None`/`False`
  threads through `get_project_folder → get_current_session_jsonl →
  get_current_session_id / append_session_log_entry`; only `cmd_append_log()`
  prints a warning and exits `1`. Worth an AC that the resolver's failure mode
  stays a clean `None` (not an exception) for genuinely-missing folders.

## Acceptance Criteria

- [ ] A cwd containing `.worktrees/` resolves to the correct
      `~/.claude/projects/…` folder.
- [ ] `ll-issues append-log` succeeds (writes the entry) when run from a worktree
      checkout that has a live session JSONL.
- [ ] Regression test asserts `get_project_folder` maps a dotted path
      (e.g. `.worktrees/…`) to the dash-collapsed folder name, using a tmp fake
      `~/.claude/projects` layout.
- [ ] Non-worktree (dotless) paths continue to resolve as before.

## Session Log
- `/ll:confidence-check` - 2026-07-15T19:06:52 - `1e72aa60-fb3f-42de-95f2-db5e48012c1d.jsonl`
- `/ll:wire-issue` - 2026-07-15T19:02:44 - `379b1176-e84b-4b88-9179-893332f09ceb.jsonl`
- `/ll:refine-issue` - 2026-07-15T18:56:08 - `3990f0fc-673f-4cb1-8647-3039d1efb245.jsonl`
- `/ll:capture-issue` - 2026-07-15T18:22:18Z - `689f0076-ace7-401e-be3c-6a6b5718157a.jsonl`

---

## Status

open
