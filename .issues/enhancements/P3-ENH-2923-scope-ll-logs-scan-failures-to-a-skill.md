---
id: ENH-2923
type: ENH
priority: P3
status: open
captured_at: '2026-07-30T02:14:15Z'
discovered_date: 2026-07-29
discovered_by: capture-issue
relates_to:
- ENH-2925
parent: EPIC-1918
verify_verdict: VALID
confidence_score: 100
outcome_confidence: 92
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 20
score_change_surface: 25
---

# ENH-2923: Scope `ll-logs scan-failures` to a specific skill

## Summary

`ll-logs scan-failures --project <path>` reports failure clusters keyed by
tool+error signature across the entire project, with no way to filter to a
single skill (e.g. `review-epic`). Getting skill-specific analytics currently
requires running the full scan and manually grepping the output for the
skill name.

**Scope clarification.** `_cmd_scan_failures` mines only assistant `Bash`
tool_use blocks matching `_LL_BASH_RE` (i.e. `ll-*` CLI invocations). So
`--skill review-epic` means "`ll-*` CLI failures that occurred *while*
`review-epic` was the enclosing skill" — not failures of `review-epic`'s own
`Read`/`Edit`/`Grep` calls, which this subcommand never sees. The `--help`
text and docs must say this.

## Current Behavior

`ll-logs scan-failures --project <path>` accepts only `--project`/`--all`,
`--window-days`, `--capture`, `--capture-foreign`, and `-j/--json`. There is
no `--skill NAME` filter, so a user asking "what's failing for skill X"
must run the unfiltered scan and grep the (potentially large) output
themselves.

## Expected Behavior

`scan-failures` should accept an optional `--skill NAME` flag that limits
reported failure clusters to those attributable to the named skill,
mirroring how `ll-history-context --for-skill NAME` already gates on a
skill name for a related CLI.

## Motivation

Skill-scoped failure analytics let a maintainer check the health of one
skill (e.g. after a change to `review-epic`) without wading through
unrelated `ll-issues`/other-tool noise in the full project scan.

## Proposed Solution

Add `--skill NAME` to `scan-failures`. Failure clusters are keyed by
tool+error signature (`_cmd_scan_failures`, `scripts/little_loops/cli/logs.py` —
`raw_clusters` keyed `(cwd_path, tool_name, normalized_sig)`), not skill name,
so a simple string match on the cluster's tool name cannot answer "what's
failing under skill X."

**Attribution mechanism.** Session JSONL records carry no per-tool-call
"enclosing skill" field, so attribution is a stream-tracking pass inside the
existing single-pass file walk in `_cmd_scan_failures`:

1. Maintain `current_skill: str | None` per JSONL file (reset per file, like
   the existing `pending` dict).
2. Update it from two marker sources as records stream by. **The user-record
   branch discriminates on the *type* of `message.content`, which is the
   mechanical form of the reset rule:**
   - **user records whose `message.content` is a `str`** — a real user turn.
     Apply `_COMMAND_NAME_SKILL_RE` (`logs.py:245`): on a match set
     `current_skill = NAME`; **on no match set `current_skill = None`.** The
     reset must trigger on *no regex match*, not on *no marker at all* —
     `/clear` (728 occurrences in this project's logs) and `/model` (476) are
     `<command-name>` markers without an `ll:` prefix, and treating them as
     "no marker, leave unchanged" would leak a skill's attribution across a
     context clear.
   - **user records whose `message.content` is a `list`** — a tool_result
     carrier. These must **never** touch `current_skill`.
   - **assistant `tool_use` blocks with `name == "Skill"`** — set
     `current_skill = input.skill`, stripping a **leading `ll:` if present**.
     The strip must be conditional (`removeprefix("ll:")`), **not**
     `split(":", 1)[1]`: 6% of real `Skill` blocks carry a bare name (see
     Decision Rules for the measured breakdown). The strip is still
     load-bearing — the *same* skill appears under both spellings
     (`ll:explore-api` and `explore-api`), and only normalization collapses
     them into one attribution bucket.
3. When a failing tool_result is folded into a cluster, record the
   `current_skill` in effect when its `tool_use` was *issued* — i.e. extend
   the `pending` map's value tuple to `(tool_name, ts, skill)` so attribution
   survives interleaved records.
4. **Do not add `skill` to the cluster key.** Keep `raw_clusters` keyed
   exactly as today — `(cwd_path, tool_name, normalized_sig)` — and carry
   `skill_counts: dict[str | None, int]` plus per-skill session ids on the
   cluster value. Splitting the key regresses the *unfiltered* path four
   ways: cluster counts inflate, `--limit`'s top-N reorders,
   `.loops/ll-logs-telemetry-digest.yaml:83`'s `FAILURES_FOUND:$COUNT`
   inflates, and `--capture` files one bug issue *per skill per signature*
   (the same failure captured N times via `_capture_failure_clusters`,
   `logs.py:1299`). With the key left alone, all four consumers are untouched
   and default output is unchanged (plain-text byte-identical; `--json` gains
   only the additive `skills` key).
5. `--skill NAME` filters to clusters whose `skill_counts` contain `NAME`
   (accept with or without the `ll:` prefix) **and re-projects each surviving
   cluster's `count` and `session_ids` to that skill's subset** — more
   accurate than key-splitting, since a filtered cluster then reports only the
   failures actually attributable to the named skill. Failures with no
   enclosing skill attribute to `None` and are excluded by any `--skill`
   filter.

   **Order of operations is load-bearing.** Today the code sorts by `count`
   and *then* applies `--limit` (`logs.py:1255-1261`). Because re-projection
   changes `count`, the new pipeline must be:

   `filter by skill` → `re-project count/session_ids` → `re-sort by the
   re-projected count` → `apply --limit`

   Re-sorting **after** re-projection is required. Sorting first would make
   `--skill X --limit 5` return the five clusters with the most *total*
   failures rather than the most `X` failures — ranking results by failures
   that the filter just excluded. The unfiltered path is unaffected (no
   re-projection ⇒ sort order identical to today).
6. `--json` rows gain `skills: list[str]` — the sorted attributed skill names
   for the cluster, `None` excluded, `[]` when nothing was attributed. (A
   scalar `skill` field cannot represent a cluster that legitimately spans
   several skills, which is the normal case once the key is not split.)

**Source coverage is asymmetric — this is a decision, not an oversight.**
Source (a)'s regex is anchored to `/ll:` and can *never* match a non-`ll`
skill (`artifact-design`, `claude-api`, `publish`, `analyze_log`). Source (b)
matches any skill name. So non-`ll` skills are attributable only when invoked
via the `Skill` tool, and `--skill artifact-design` will under-report if that
skill was ever invoked via a slash-command marker. Accepted: the flag's
purpose is triage of `ll-*` CLI failures, which cluster overwhelmingly under
`ll:` skills. Do not "fix" this by loosening `_COMMAND_NAME_SKILL_RE` — it is
shared with `_detect_ll_signal` and widening it would change unrelated
signal detection.

Known limitations to state in `--help`:
- Attribution is heuristic — a tool call made after a skill's turn completes
  but before the next user message may be mis-attributed to that skill.
- The literal string `<command-name>/ll:NAME</command-name>` appears in this
  project's own logs (63 occurrences, from docs and issue text quoting the
  marker) and would attribute to a skill named `NAME`. Scanning only `str`
  content per step 2 makes this largely inert, but it is not impossible.
- `--window-days`/`--since`/`--until` filter at *cluster* granularity on the
  cluster's latest timestamp (`logs.py:1230-1238`), not per-failure. A cluster
  kept inside the window by a recent `skill-B` failure will re-project
  `skill-A`'s count including `skill-A` failures older than the window. This
  coarseness is pre-existing; `--skill` inherits rather than introduces it.

All are acceptable for triage analytics.

Sequencing: the consolidated parser (shared target/window parent parsers,
`--limit`) has already landed on `scan-failures`; this flag lands on top of
that existing surface rather than waiting on it.

## Acceptance Criteria

- [x] `ll-logs scan-failures --skill review-epic` reports only clusters whose
      failures occurred while `review-epic` (via `<command-name>` marker or
      `Skill` tool_use) was the enclosing skill; `ll:review-epic` is accepted
      as an equivalent spelling.
- [x] Unfiltered **clustering is unchanged**: same cluster count, same
      ordering, same `--limit` top-N, same `FAILURES_FOUND` count for
      `.loops/ll-logs-telemetry-digest.yaml`. The cluster key is not extended.
      A regression test pins this. (Unfiltered *plain-text* output is
      byte-identical; unfiltered `--json` output gains exactly one additive
      key, `skills`, and is otherwise unchanged — see the next bullet. The
      digest consumer reads `len(items)` only, so it is unaffected.)
- [x] `--capture` without `--skill` creates exactly the same set of bug issues
      as before the change (no per-skill duplicates).
- [x] `--json` rows include a `skills` array (sorted attributed skill names,
      unattributed excluded, `[]` when none).
- [x] Under `--skill NAME`, each surviving cluster's `count` and `session_ids`
      reflect only that skill's failures, not the cluster total.
- [x] `--skill` composes with `--window-days`/`--since`/`--until` and
      `--limit`. Specifically: under `--skill X --limit N`, the top-N is
      ranked by each cluster's **re-projected** (skill-X) count, not its total
      count. A test pins this with a fixture where the two orderings differ.
- [x] `--help` for `scan-failures` states the scope clarification (`--skill`
      means "`ll-*` CLI failures while NAME was the enclosing skill", not
      failures of NAME's own `Read`/`Edit`/`Grep` calls) and the heuristic
      limitations listed in Proposed Solution.
- [x] Tests cover: marker-based attribution, `Skill` tool_use attribution
      (including `ll:` prefix stripping **and a bare, unprefixed
      `input.skill` such as `analyze_log` — must not raise and must attribute
      under its bare name**), **both spellings of one skill
      (`ll:explore-api` + `explore-api`) collapsing into a single
      attribution bucket**, reset on a plain user message,
      **no reset from an interleaved tool_result user record**, **reset on a
      non-`ll:` marker such as `/clear`**, unattributed failures excluded
      under `--skill`, per-skill count re-projection, and the
      prefix-equivalence acceptance — using synthetic JSONL fixtures (no live
      session logs).
- [x] `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

**In scope:** attribution tracking inside `_cmd_scan_failures`'s existing
stream walk; `--skill` flag; `skill_counts` on `_FailureCluster` and a
`skills` array in JSON output; `--help` text per AC; tests.

**Plain-text output gains nothing — deliberate.** The human-readable branch
(`logs.py:1289-1294`) is left untouched: no skill names in the `[{count}x]
{tool}` lines, filtered or unfiltered. Rationale: it keeps unfiltered
plain-text output byte-identical (AC bullet 2) with no conditional-formatting
branch, and under `--skill NAME` the skill is already known from the
invocation, so printing it back is redundant. Structured consumers use
`--json`. Revisit only if a concrete consumer needs it.

**Out of scope:** `--skill` on `stats`/`dead-skills` (evaluated and dropped
during the shared-flags scope review); attribution via `.ll/history.db` session-store
queries (scan-failures is deliberately JSONL-direct and cross-project — the
history DB is per-project and not guaranteed backfilled); changing clustering
signatures.

**`--capture` interaction:** `--capture` behavior is explicitly *unchanged* —
this is a constraint on the design, not merely an omission. Because the
cluster key is not split by skill (Proposed Solution step 4),
`_capture_failure_clusters` receives the same cluster set as before and files
the same bug issues. Combining `--capture` with `--skill` narrows which
clusters are captured, which is the natural composition; no new dedupe logic
is needed.

**Capture is insulated more strongly than the above argues** (verified
2026-08-19): `_capture_failure_clusters` (`logs.py:1312-1324`) reads only
`c.tool_name`, `c.sample_error`, and `c.cwd_path` — **it never reads
`c.count` or `c.session_ids`**. Count re-projection under `--skill`
therefore cannot affect capture output under any design. The only vector by
which capture could change is the cluster *set*, which step 4 fixes.

## Integration Map

### Codebase Research Findings

### Files to Modify
- `scripts/little_loops/cli/logs.py` — `_cmd_scan_failures` (lines 1112-1296) is the target function; `_FailureCluster` dataclass (lines 1100-1109, currently `tool_name`, `normalized_sig`, `count`, `sample_error`, `session_ids`, `cwd_path` — no skill field); per-file `pending` dict (line 1141, currently `dict[str, tuple[str, str]]` keyed on `tool_use_id`); `raw_clusters` keyed `(cwd_path, tool_name, normalized_sig)` (line 1134); `scan_failures_parser` arg wiring (lines 2157-2180).

  **Blocking implementation detail — the marker scan must be inserted *above* an existing early-`continue`.** The `record_type == "user"` branch opens with `if not isinstance(content, list) or not content: continue` (`logs.py:1184`). Command-name records carry `message.content` as a **plain `str`** — verified shape: `"<command-message>ll:commit</command-message>\n<command-name>/ll:commit</command-name>"` — so *every* marker record is discarded by that guard before any marker logic could see it. Naively appending marker handling inside the existing user branch yields silent zero attribution from source (a). The `str`/`list` split at this guard is also exactly the reset discriminator specified in Proposed Solution step 2.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/logs.py:2336-2337` — `main_logs` dispatches `scan-failures` to `_cmd_scan_failures`.
- `scripts/tests/test_ll_logs.py:16`, `scripts/little_loops/cli/ctx_stats.py:20`, `scripts/little_loops/cli/__init__.py:73` — import `cli/logs.py`.

_Wiring pass added by `/ll:wire-issue`:_
- `.loops/ll-logs-telemetry-digest.yaml:56-96` — `scan_failures` state shells out to `ll-logs scan-failures --project . --json > "$OUT"` and parses the JSON via `len(items)` only (not keyed on specific fields), so a new `skills` field is additive-safe; the `FAILURES_FOUND:$COUNT` signal (:83) and the `triage_failures` dedupe cap (:109) read the cluster *count*. **This consumer is the primary reason the cluster key must not be split by skill** — under the key-split alternative both would silently inflate, changing this loop's triage volume with no code change to the loop itself. Under the chosen design the count is unchanged and this loop needs no edit; confirm with a before/after `FAILURES_FOUND` comparison after implementation [Agent 1 + Agent 2 finding, revised].
- `scripts/little_loops/cli/logs.py:2229-2233` — `eval-export` subcommand's existing `--skill NAME` argparse flag (`metavar="NAME"`, help "Filter by skill name") is the in-repo naming precedent for a free-form filter with no allowlist — the design this issue's `--skill` should match, as opposed to the allowlist-gated `--for-skill` precedent already cited above [Agent 2 finding].

### Conventions in Force
- The `<command-name>/ll:NAME</command-name>` marker extraction this issue proposes (attribution source a) already exists and is reusable as-is: `_COMMAND_NAME_SKILL_RE = re.compile(r"<command-name>/ll:(\S+)")` (`logs.py:245`), used inside `_detect_ll_signal` (`logs.py:350-410`) at `:387`, with trailing-tag stripping at `:390-391`. It is duplicated (not shared) in `session_store/writers.py:3081` (`_BACKFILL_SKILL_RE`) and `user_messages.py:1073` / `cli/messages.py:213` (per-skill exact-match variants) — none of these are currently wired into `_cmd_scan_failures`.
- No "Skill tool_use block" parsing (attribution source b in the issue's Proposed Solution) exists anywhere in the codebase — a grep for a tool_use block named `Skill` (e.g. `block.get("name") == "Skill"`) across `scripts/little_loops/**/*.py` returns no hits. `_detect_ll_signal`'s three recognized signal types are queue-operation, `<command-name>` user text, and Bash tool_use only (`logs.py:350-360`).
- The existing skill-scoped-flag precedent this issue cites (`--for-skill`, `history_context.py:176-182`) gates against an allowlist (`cfg.history.planning_skills`, guard at `:249-255`) — it rejects any name not in that list. This issue's proposed `--skill NAME` has no such allowlist in its Acceptance Criteria; it is a free-form exact-match filter, a materially different validation behavior than the cited precedent.
- The `--json` payload for `scan-failures` currently omits `cwd_path` even though it is a `_FailureCluster` field (`logs.py:1274-1286`) — relevant since this issue's AC requires a `skills` array in `--json` rows alongside the existing ones (and confirms the payload is a deliberate projection of the dataclass, not a dump of it, so `skill_counts` staying internal is consistent).

### Tests
- `scripts/tests/test_ll_logs.py:2687` onward — "Tests for the scan-failures subcommand" class. Fixture helpers: `_make_project_dir` (:2689-2715), `_assistant_bash_record` (:2717-2739), `_user_tool_result_record` (:2741-2764). No existing fixture constructs a `<command-name>` user-message record or a `Skill` tool_use block — both would be new fixture shapes.
- `scripts/tests/test_history_context_cli.py` — covers the `--for-skill` precedent's test pattern (built on a sqlite `history.db` fixture, not JSONL — does not map 1:1 onto this issue's JSONL-stream attribution).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_logs.py:3266-3308` (`test_scan_failures_json_output_schema`) — asserts individual key presence (`"tool" in entry`, etc.), so a new key won't break it, but it should be updated to also assert `"skills" in entry` and that the value is a `list` [Agent 3 finding].
- `scripts/tests/test_ll_logs.py:4194-4206` (`test_detect_ll_signal_command_name_user_record`) and `:4208-4226` (`test_detect_ll_signal_bash_tool_use`) — closest existing fixtures for a `<command-name>` user record and an assistant `tool_use` block; model new `_user_command_name_record`/`_assistant_skill_tool_use_record` helpers in `TestScanFailures` on these shapes (swap `"name": "Bash", "input": {"command": ...}` for `"name": "Skill", "input": {"skill": ...}`) [Agent 3 finding].
- `scripts/tests/test_ll_logs.py:3899-3916,4100-4159` (`TestEvalExportMapping.test_extract_skill_from_command_name`, `test_skill_filter_and_skip_unknown`) — second reference showing an end-to-end `--skill`-style filter test built on synthetic multi-record JSONL fixtures with `main_logs()` in-process invocation [Agent 3 finding].
- `scripts/tests/test_ll_logs.py:3134-3175` (`test_scan_failures_clusters_same_error`) and `:2818-2879` (`test_scan_failures_limit_caps_clusters_by_count`) — assert exact cluster counts on fixtures with no skill markers (all records attribute to `None`). Under the non-key-splitting design these must pass **unmodified**; if either needs its expected counts edited, the implementation has split the cluster key and violated AC bullet 2. Treat them as the canary, and add a fixture *with* mixed skill markers asserting the same unfiltered cluster count [Agent 3 finding, revised].
- `scripts/tests/test_bug_3216_telemetry_digest_invocations.py:44,160-195,265` — asserts the `.loops/ll-logs-telemetry-digest.yaml` invocation shape (`["scan-failures", "--project", ".", "--json"]`) via a `SCAN_FAILURES_FLAG` map; stable as long as `--skill` isn't added to that loop's invocation — verify no regression [Agent 1 + Agent 2 finding].

### Documentation
- `docs/reference/CLI.md:3251` (scan-failures subcommand table row), `:3318` (flags section), `:3736` (`--for-skill NAME` precedent doc row).

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:4747` — `main_logs` docstring documents the `scan-failures --json` schema as `[{tool: str, count: int, normalized_sig: str, sample_error: str, session_ids: [str]}]`; must be updated to add `skills: [str]` [Agent 2 finding].
- `docs/guides/HISTORY_SESSION_GUIDE.md:445-452` — "Mine failed commands for bugs" section shows `ll-logs scan-failures --project .` example invocations with no `--skill` example; add one [Agent 2 finding].
- `docs/reference/API.md:4750` — `eval-export --skill NAME` flag doc entry (different semantics: filters reconstructed fixtures to `runner == "skill" and target == NAME`) — the naming precedent this issue's `--skill` help text should read consistently against, not a file to modify [Agent 2 finding].

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation. No formal `## Implementation Steps` section exists on this issue, so this phase lives under Integration Map:_

- Update `docs/reference/API.md:4747` — extend the documented `scan-failures --json` schema string with `skills: [str]`.
- Update `docs/guides/HISTORY_SESSION_GUIDE.md:445-452` — add a `--skill` example invocation.
- Update `scripts/tests/test_ll_logs.py` `test_scan_failures_json_output_schema` (:3266-3308) — assert `"skills" in entry` and that the value is a `list`. (Plural, per AC bullet 4 — a scalar `skill` cannot represent a cluster spanning several skills, which is the normal case once the key is not split.)
- Add `_user_command_name_record`/`_assistant_skill_tool_use_record` fixture helpers to `TestScanFailures` (model: `_assistant_bash_record` :2717-2739, `test_detect_ll_signal_command_name_user_record` :4194-4206) and author the 5 AC-mandated attribution tests on them.
- Verify `.loops/ll-logs-telemetry-digest.yaml`'s `scan_failures`/`triage_failures` states are **unchanged**: run `ll-logs scan-failures --project . --json` before and after the change and confirm the `FAILURES_FOUND` count is *equal*. Under the chosen design (step 4, key not split) the count cannot inflate — an inflated count means the key was split and AC bullet 2 is violated. The state's parser reads `len(items)` only (`:70-77`, verified 2026-08-19), so the additive `skills` key is safe and this loop needs no edit.

## Program Design

### Codebase Research Findings

### Types
- `_FailureCluster.skill_counts: dict[str | None, int]` — new field holding the per-skill failure breakdown for the cluster (key `None` = unattributed). Existing dataclass at `logs.py:1100-1109` follows a `field(default_factory=...)` pattern for its last field (`cwd_path`), so `skill_counts: dict[str | None, int] = field(default_factory=dict)` fits the same shape.
- A parallel per-skill session-id mapping is needed for the `--skill` count/session re-projection in Proposed Solution step 5 — either a second field (`skill_sessions: dict[str | None, list[str]]`) or by widening `skill_counts`' value to a `(count, session_ids)` pair. Implementer's choice; the former keeps the common unfiltered path cheaper to read.
- Not a scalar `skill: str | None`. With the cluster key unsplit, one cluster can legitimately span several skills, which a scalar cannot represent.

### Signatures
- `_cmd_scan_failures(args, logger) -> int` — existing signature at `logs.py:1112`, unchanged by this issue; the new tracking lives inside the function body, not its interface.

### Call Path
`main_logs` (`logs.py:2337`) -> `_cmd_scan_failures` (`logs.py:1112`) -> per-file loop where the per-file `pending` dict (`logs.py:1141`, currently `tool_use_id -> (tool_name, ts)`) would extend to `(tool_name, ts, skill)` -> `raw_clusters` keyed `(cwd_path, tool_name, normalized_sig)` (`logs.py:1134`), **key left exactly as-is per Proposed Solution step 4** — the attribution rides on the cluster *value* (`skill_counts`), never the key -> `_FailureCluster` construction (`logs.py:1243-1254`) -> `--json` serialization (`logs.py:1274-1286`) or plain-text (`logs.py:1289-1294`).

### Decision Rules
- Gap kind: per-cluster skill attribution, gated by a new `--skill NAME` filter.
- Attribution source (a) — `<command-name>/ll:NAME</command-name>` marker in a user record — is backed by an existing, reusable extraction: `_COMMAND_NAME_SKILL_RE` (`logs.py:245`), extraction logic at `logs.py:387-391`.
- Attribution source (b) — an assistant `Skill` tool_use block with `input.skill` — has **no existing implementation anywhere in this codebase** (see Integration Map → Conventions in Force), but the *record shape is now verified* against real session transcripts (2026-08-19): blocks appear as `{"type": "tool_use", "name": "Skill", "input": {"skill": "ll:capture-issue", "args": "..."}}`.
- **The `ll:` prefix is usually but NOT always present** (measured 2026-08-19 across all non-`agent-*` JSONL for this project: 149 `Skill` blocks, of which **9 (6%) carry a bare name** — `explore-api` ×2, `artifact-design` ×2, `claude-api` ×2, `publish`, `analyze_log`, `reconcile-issue`). Consequences, both load-bearing:
  - The strip must be **conditional** — `skill.removeprefix("ll:")`. A `split(":", 1)[1]` or an unguarded index would raise or emit garbage on the bare 6%.
  - Normalization is still required, because the *same* skill appears under both spellings in the same corpus (`ll:explore-api` ×5 and `explore-api` ×2; `reconcile-issue` bare). Without the strip they would occupy two separate attribution buckets and `--skill explore-api` would under-report.
  - An earlier revision of this issue asserted the prefix was "always present in practice." That claim was wrong and has been corrected here; do not reinstate it.
- Reset rule (verified shapes, 2026-08-19): discriminate on the type of `message.content`. A `str` content is a real user turn → run `_COMMAND_NAME_SKILL_RE` and set `current_skill` to the match or `None` on no match; a `list` content is a tool_result carrier → leave `current_skill` untouched. The reset fires on *regex non-match*, not on *marker absence*: `/clear` and `/model` records carry a `<command-name>` marker with no `ll:` prefix and must reset. No existing function implements stream-tracking reset semantics; `_detect_ll_signal` (`logs.py:350-410`) is a stateless per-record detector and cannot be reused for this responsibility, though its regex can.
- `--skill NAME` matching: exact string match, `ll:` prefix optional on either side (per AC). Unlike the cited `--for-skill` precedent (`history_context.py:176-182`, gated against `cfg.history.planning_skills`), this issue's AC does not require an allowlist — any name is accepted, and a name with no matching clusters simply yields empty output.
- Escape hatch: failures attributed to `None` (no enclosing skill detected) are always excluded when `--skill` is passed, and always counted when it is not (per AC bullet 1). A cluster whose `skill_counts` is entirely `{None: n}` therefore disappears under any `--skill` filter, while a mixed cluster survives with its count re-projected to the named skill's subset.

## Impact

- **Priority**: P3 - convenience/analytics improvement, not blocking any workflow
- **Effort**: Medium - requires wiring skill attribution into cluster data, not just an argparse flag
- **Risk**: Low - additive, optional flag
- **Breaking Change**: No

## Resolution

- **Action**: improve
- **Completed**: 2026-08-20
- **Implementation**: Added `--skill NAME` to `ll-logs scan-failures`. `_FailureCluster` gained
  `skill_counts`/`skill_sessions` fields; a new `_RawCluster` accumulator tracks them during the
  streaming pass without splitting the `(cwd_path, tool_name, normalized_sig)` cluster key.
  Attribution tracks `current_skill` per JSONL file from two sources: `<command-name>` markers on
  `str`-content user records (reset to `None` on no match) and `Skill` tool_use blocks (`ll:`
  prefix stripped via `removeprefix`). `list`-content user records (tool_result carriers) never
  touch `current_skill`. `--skill NAME` filters clusters, re-projects `count`/`session_ids` to the
  named skill's subset, then re-sorts before `--limit` is applied. `--json` gained an additive
  `skills` array. Implementation matched the issue's Program Design exactly — no deviations.

### Files Changed
- `scripts/little_loops/cli/logs.py` — `_FailureCluster`, new `_RawCluster`, `_cmd_scan_failures`
  attribution tracking and `--skill` filter/reprojection, `--skill` argparse flag, `--json` schema
- `scripts/tests/test_ll_logs.py` — 19 new tests covering marker/Skill-tool_use attribution,
  prefix normalization, reset semantics, unattributed exclusion, count re-projection, and
  `--skill`+`--limit` reordering; updated `test_scan_failures_json_output_schema`
- `docs/reference/API.md`, `docs/reference/CLI.md`, `docs/guides/HISTORY_SESSION_GUIDE.md` —
  documented `--skill` and the `skills` JSON field

### Verification Results
- `python -m pytest scripts/tests/` — 19987 passed, 46 skipped
- `ruff check` / `mypy` clean on changed files
- Confirmed unfiltered cluster count is byte-identical before/after against this project's real
  session corpus (452 clusters both runs)

### Commits
- See git log for details

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log
- `/ll:manage-issue` - 2026-08-20T04:43:52 - `2768e842-48b3-4e1e-a794-4ea32e6534b7.jsonl`
- `/ll:ready-issue` - 2026-08-20T04:28:36 - `fd4224d4-6311-4f68-b2b0-63712be1c780.jsonl`
- `/ll:confidence-check` - 2026-08-20T04:15:03 - `bc783ddd-7686-4216-8c7b-f8960149f7f4.jsonl`
- `/ll:confidence-check` - 2026-08-20T04:05:04 - `126a5f56-c9e2-4e46-a250-6fd8dd7c821f.jsonl`
- `/ll:wire-issue` - 2026-08-20T04:01:41 - `aaf0ea2a-841b-4c50-a0ca-6a58028f4f0d.jsonl`
- `/ll:refine-issue` - 2026-08-20T03:52:48 - `790544d7-1b14-4b6c-a7fc-6d3e39e40211.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:04:57 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:capture-issue` - 2026-07-30T02:14:15Z - `b1cb0370-8b55-4a10-a364-649e81045dd0.jsonl`

---

## Status

**Open** | Created: 2026-07-29 | Priority: P3
