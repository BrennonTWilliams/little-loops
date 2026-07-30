---
id: ENH-2920
type: enhancement
priority: P2
status: done
created: 2026-07-29
labels:
- tooling
- doctor
- link-checker
confidence_score: 100
outcome_confidence: 73
score_complexity: 15
score_test_coverage: 22
score_ambiguity: 18
score_change_surface: 18
completed_at: '2026-07-30T20:55:40Z'
---

# ll-check-links: restore intended doc scope and classify non-authoritative HTTP statuses as non-fatal

## Status

open

## Summary

`ll-check-links` walks the entire repository tree instead of the documentation
surface it declares, and treats every HTTP error status as a broken link. Together
these produce a permanently-red `ll-doctor --full` gate reporting 600–800 "broken"
links, of which only a small residue are genuinely broken. Fix the scope regression
(`DEFAULT_DOC_FILES` is dead code) and add status-code tiering so the gate fires only
on statuses that actually assert a link is dead.

## Current Behavior

`ll-doctor --full` fails on `check_links` with 600–800 broken links. The count is not
reproducible between runs (616 in one `ll-doctor --full` run, 806 in a direct
`ll-check-links` run minutes later) — itself the tell that most failures are
rate-limiting artifacts rather than broken links.

Measured breakdown of one 806-link run:

| Error | Count | Reality |
|---|---:|---|
| HTTP 429 | 497 | Rate limiting — 10 concurrent workers hammering github.com |
| HTTP 403 | 120 | Auth-walled (SharePoint, Vertex grounding redirects) |
| HTTP 401 | 110 | Auth-walled (outlook.office365.com) |
| HTTP 404 | 72 | The only genuine broken-link candidates |
| 5xx / 400 | 7 | Transient server-side |

Scanned-file distribution shows the walk ranges far outside the documentation
surface: `docs/` 449, `thoughts/` 149, `.loops/` 144, `.issues/` 43 — including
`hooks/adapters/opencode/node_modules/zod/README.md` (vendored dependency) and
`.pytest_cache/README.md` (tool cache).

Of the 72 genuine 404s: ~33 are in `docs/research/dreaming-research-synthesis.md`
(bibliography link rot), 3 in vendored zod, 6 in `thoughts/`, 5 in `.issues/`. The
residue in maintained documentation is small.

## Root Cause

Two independent defects in `scripts/little_loops/link_checker.py`:

**1. Declared scope is dead code.** `DEFAULT_DOC_FILES` (line 40–44) declares the
intended surface:

```python
DEFAULT_DOC_FILES = [
    "README.md",
    "CONTRIBUTING.md",
    "docs/**/*.md",
]
```

`grep -rn DEFAULT_DOC_FILES scripts/ --include='*.py'` returns **only its own
definition** — it is referenced nowhere. `check_markdown_links()` (line 259, the
function behind the `main_check_links` CLI entry in `cli/docs.py:313`) instead does:

```python
md_files = list(base_dir.rglob("*.md"))    # line 284
```

walking the entire tree: `node_modules/`, `.pytest_cache/`, `.loops/` run artifacts,
`thoughts/` scratch, `.issues/`. The intended scope was written and never wired up.

**2. Every HTTP error status is classified BROKEN.** `_check_url_once` (line 210–211):

```python
except urllib.error.HTTPError as e:
    return LinkOutcome.BROKEN, f"HTTP {e.code}"
```

There is a **second classification site**: line 208 returns
`LinkOutcome.BROKEN, f"HTTP {response.status}"` for non-2xx statuses that come back
through the success path (no exception raised). Both sites need the same tiering.

No discrimination by status code. The `LinkOutcome.BROKEN` docstring (line 50) reads
"the host answered and said no" — but a 429 means "you asked too fast" and a 401/403
means "you are not authenticated," neither of which asserts the link is dead. Only
`BROKEN` gates the exit code (`has_errors`, line 118); `UNREACHABLE` is already
correctly non-fatal per ENH-2836.

## Expected Behavior

`ll-check-links` with no arguments checks only the documentation surface, and exits
non-zero only when a host authoritatively reports a link gone (404/410). Statuses
that reflect checker aggressiveness or missing credentials are reported for
visibility but do not gate, matching the ENH-2836 precedent for unreachable links.

## Proposed Solution

**Scope** — wire `DEFAULT_DOC_FILES` into `check_markdown_links()` as the default
file set, replacing the bare `rglob`. Keep a positional path override (already shown
in `--help` examples as `ll-check-links docs/`). Additionally apply a hard directory
denylist — `node_modules/`, `.pytest_cache/`, `.venv/`, `.git/`, `.loops/`, `.ll/` —
so an explicit wider path still cannot drag in vendored or generated markdown
(stray/quarantined `.ll/` contents included).

**Status classification** — add a third outcome tier via a single shared
status-code classifier applied at **both** sites (the non-2xx success path at line
208 and the `HTTPError` handler at line 210–211):

- `404`, `410` → `BROKEN` (fatal; the host asserts it is gone)
- `429`, `401`, `403`, `5xx` → new `INDETERMINATE` outcome — reported in output, does
  not gate exit code
- `--strict-network` gates `INDETERMINATE` as well as `UNREACHABLE`, consistent with
  existing behavior

The tier must be threaded through the result model and every consumer:
`LinkResult.status`, `LinkCheckResult` counters, `has_errors`, the JSON formatter
(`"has_errors"` key, line 527), and the `ll-doctor --full` adapter
(`cli/doctor.py:774` `_full_check_links_data()`), which currently gates on
`result.broken_links > 0` and string-filters `r.status == "broken"` /
`"unreachable"`. The adapter should surface `INDETERMINATE` as an informational
finding, the way it already handles unreachable.

**Rate-limit hygiene** — honor `Retry-After` on 429 with backoff in the existing
retry path, capping the honored delay (e.g. ≤30s) and the total per-run retry
budget so a large or adversarial `Retry-After` cannot stall the run; and lower the
default `--workers` from 10. A 429 is evidence the checker was too aggressive, not
evidence about the link.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Retry config already declared but dead**: `.mlc.config.json` (repo root)
  already declares `"retryOn429": true`, `"retryCount": 3`,
  `"fallbackRetryDelay": "5s"` alongside `ignorePatterns`. `load_ignore_patterns()`
  (`scripts/little_loops/link_checker.py:415-451`) only reads the `ignorePatterns`
  key (line 435: `config.get("ignorePatterns", [])`) — `retryOn429`/`retryCount`/
  `fallbackRetryDelay` are never consumed anywhere in the module. The Rate-limit
  hygiene work should wire these existing config keys into the new 429 backoff
  path (reading `Retry-After` when present, falling back to
  `fallbackRetryDelay`/`retryCount` otherwise) rather than inventing new config
  surface, so the already-authored `.mlc.config.json` values take effect for the
  first time.
- **Existing retry precedent is UNREACHABLE-only**: `check_url_outcome()`
  (`link_checker.py:242-256`) already retries once, but only when the first
  outcome is `LinkOutcome.UNREACHABLE`, using flat constant
  `_RETRY_BACKOFF_SECONDS = 0.2` (line 23) — no `Retry-After` header parsing
  exists in the codebase (confirmed via repo-wide grep). A `BROKEN` outcome
  (which is what 429 currently maps to) is never retried today. The new
  `INDETERMINATE` tier should extend this same retry gate (`if outcome is
  LinkOutcome.INDETERMINATE and status == 429: ...`) rather than adding a
  parallel retry mechanism.
- **No in-repo `Retry-After` precedent to reuse directly**: the closest existing
  backoff machinery — `scripts/little_loops/fsm/rate_limit_circuit.py`
  (`RateLimitCircuit.record_rate_limit()`) and `config/automation.py`'s
  `rate_limits.long_wait_ladder` — are config-driven backoff schedules for the
  FSM executor, not HTTP-header-driven, and operate on a different subsystem
  (loop rate-limit detection, not link checking). They're not directly reusable
  but confirm the codebase convention of capping/bounding retry delays via a
  fixed ladder rather than trusting a raw header value.

## Program Design

### Types

- `LinkOutcome.INDETERMINATE` — new enum member alongside `VALID`/`BROKEN`/`UNREACHABLE` in `scripts/little_loops/link_checker.py`; carried through `LinkResult.status` as the string `"indeterminate"` and counted on `LinkCheckResult` as `indeterminate_links: int`.

### Signatures

- `_classify_http_status(code: int) -> LinkOutcome`

  New shared status→tier classifier: `404`/`410` → `BROKEN`; `429`/`401`/`403`/`5xx` → `INDETERMINATE`.

- `check_markdown_links(base_dir: Path, ignore_patterns: list[str], files: list[Path] | None = None) -> LinkCheckResult`

  Default file set from `DEFAULT_DOC_FILES` globs plus a hard directory denylist, replacing `base_dir.rglob("*.md")` (existing keyword args unchanged; `files` is additive).

- `_check_url_once(url: str, timeout: int) -> tuple[LinkOutcome, str | None]`

  Both classification sites (non-2xx success path and `HTTPError` handler) route through `_classify_http_status`.

### Call Path

`main_check_links` (`scripts/little_loops/cli/docs.py`) → `check_markdown_links` → `_check_url_once` → `_classify_http_status`; and `_full_check_links_data` (`scripts/little_loops/cli/doctor.py`) → `check_markdown_links`, with `_full_check_links_data` growing an informational branch on `indeterminate_links` mirroring its existing `unreachable_links` branch. `has_errors` on `LinkCheckResult` continues to gate only on `BROKEN`; `--strict-network` extends to `INDETERMINATE`.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/link_checker.py` — `DEFAULT_DOC_FILES`, `check_markdown_links()`, `_check_url_once()`, `LinkOutcome`, `LinkResult`, `LinkCheckResult`, `load_ignore_patterns()`
- `scripts/little_loops/cli/doctor.py` — `_full_check_links_data()` (lines 774-815), `_full_check_links_check()` (lines 818-829)

### Dependent Files (Callers)
- `scripts/little_loops/cli/docs.py:423` — `main_check_links()` calls `check_markdown_links(base_dir, ignore_patterns, ...)`; no positional path argument is actually wired despite the `%(prog)s docs/` usage example in the epilog (line 340) — only `-C/--directory` exists (lines 367-373).
- `scripts/little_loops/cli/doctor.py:780` — `_full_check_links_data()` calls `check_markdown_links(base_dir, ignore_patterns, ...)`.
- `scripts/little_loops/cli/__init__.py` — re-exports `main_check_links`.
- `scripts/pyproject.toml:75` — entry point `ll-check-links = "little_loops.cli:main_check_links"`.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/lib/cli.yaml:70-84` — `ll_check_links` reusable FSM fragment shells out to `ll-check-links`; its description text repeats the current "gated on genuinely broken links only ... unless --strict-network" semantics and needs updating once `INDETERMINATE` exists.
- `scripts/little_loops/loops/docs-sync.yaml:36-49` — `check_links` state (`fragment: ll_check_links`) routes on the shelled-out exit code; a code comment at line 49 explicitly references "link_checker.py's action_severity assignment" as the basis for its own `on_yes`/`on_no`/`on_error` routing — review whether `indeterminate` should route like `mention` (current `unreachable`/`broken` treatment) or differently.
- `scripts/little_loops/init/writers.py:37` — `_LL_PERMISSIONS` canonical allowlist includes `"Bash(ll-check-links:*)"`; unaffected by this issue's changes but confirms `ll-check-links` is a tracked CLI surface (cross-check with `ll-verify-cli-allowlist` after any entry-point rename, none planned here).

### Similar Patterns
- Directory-denylist precedent: `_EXCLUDE_DIRS` set tested against `Path.relative_to(project_root).parts` in `scripts/little_loops/init/detect.py:78-92` (`detect_documents()`), and the glob-pattern variant (`**/node_modules/**`, etc.) in `scripts/little_loops/config/features.py:296,307` — link_checker.py's file discovery currently has no denylist at all.
- ENH-2836's `UNREACHABLE` tier is the exact five-part shape to replicate for `INDETERMINATE`: enum member → classifier branch → counter field on `LinkCheckResult` → `has_errors` stays excluded → formatter section (text/json/markdown) mirroring the existing unreachable section.

### Tests
- `scripts/tests/test_link_checker.py` — `TestCheckUrlOutcome` (HTTPError/URLError status mocking via `@patch("urllib.request.urlopen")`) and `TestCheckMarkdownLinks` (mocks `little_loops.link_checker.check_url_outcome` directly, e.g. `test_check_with_unreachable_link`) are the direct templates for new `INDETERMINATE`-tier tests.
- `scripts/tests/test_cli_docs.py` — `main_check_links()` exit-code and `--strict-network` tests.
- `scripts/tests/test_cli_doctor_full.py` — `_full_check_links_data()` adapter tests (broken/unreachable aggregation, action-severity propagation).

### Tests (wiring pass)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_fragments.py:895-986` — exercises the `ll_check_links` FSM fragment library entry; add/verify a case asserting the fragment's action-severity routing comment still matches `link_checker.py` once `INDETERMINATE` lands.
- **Breakage risk in `test_link_checker.py`'s `TestCheckMarkdownLinks`**: several existing tests write arbitrarily-named files directly under `tmp_path` (e.g. `test_check_multiple_files` at lines 401-412 creating `tmp_path/test1.md`, `tmp_path/test2.md`; `test_check_with_no_markdown_files`) that rely on the current unscoped `base_dir.rglob("*.md")` walk. Once `DEFAULT_DOC_FILES` (`README.md`, `CONTRIBUTING.md`, `docs/**/*.md`) is wired in as the default, these fixtures stop matching and the tests will fail unless updated to either (a) name fixture files to match the default globs (e.g. `tmp_path/README.md`), or (b) pass an explicit `files=` override exercising the new additive parameter. `test_check_recursive_subdirectories` (writes to `tmp_path/docs/api.md`) already matches `docs/**/*.md` and is expected to keep passing unchanged.
- No test in `test_cli_doctor_full.py` currently exercises multiple non-zero `LinkCheckResult` counters simultaneously (e.g. `broken_links>0` and `unreachable_links>0` together); add a combined-severity case alongside the new `indeterminate_links`-only case per the ENH-2836 five-layer shape (enum member → classifier branch → counter field → `has_errors` exclusion → formatter section), since `INDETERMINATE` and `BROKEN` can co-occur in one real run.
- Directory-denylist test template: `scripts/tests/test_init_core.py`'s `test_excludes_node_modules`/`test_excludes_dot_git` (creates a noise file under an excluded dir, asserts `detect_documents()` doesn't pick it up) — mirror this shape for `check_markdown_links()`, e.g. `test_check_markdown_links_excludes_node_modules(tmp_path)` creating `tmp_path/node_modules/pkg/README.md` with a broken link and asserting `total_links == 0` even though the filename matches `DEFAULT_DOC_FILES`.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `## little_loops.link_checker` section (~line 6599) documents `LinkResult`/`LinkCheckResult` dataclass fields verbatim; the `status` field comment (line 6613) already omits `"unreachable"` (pre-existing drift) and will need both that gap and the new `"indeterminate"` value added in the same pass. Also the `main_check_links` entry (lines 4225-4231) describing broken vs. unreachable classification.
- `docs/reference/CLI.md` — `### ll-check-links` section (lines 3207-3238): flag table, exit-code description (line 3226), and the `action_severity` paragraph (line 3224) describing `broken`/`unreachable` → `mention`.
- `.claude/CLAUDE.md` — top-level CLI tool list one-line summary for `ll-check-links` (line ~249, cites ENH-2836) needs updating once scope/status semantics change enough to affect the summary.
- `CHANGELOG.md` — expected new entry per repo convention (prior ENH-2836 entry is the template).
- `commands/help.md:283`, `.gemini/commands/help.toml`, `.kimi-code/skills/ll-help/SKILL.md` — host-adapted mirrors of the `/ll:help` one-line `ll-check-links` description; regenerate via `ll-adapt` if the CLAUDE.md summary line changes.
- `docs/guides/LOOPS_REFERENCE.md` — references the `ll_check_links` FSM fragment; update if its description text changes in `cli.yaml`.

### Configuration
- `.mlc.config.json` (repo root) — already declares `retryOn429`/`retryCount`/`fallbackRetryDelay` keys that `load_ignore_patterns()` never reads (see Proposed Solution → Codebase Research Findings for detail).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Before wiring `DEFAULT_DOC_FILES` into `check_markdown_links()`, update `test_link_checker.py`'s `TestCheckMarkdownLinks` fixtures that write arbitrarily-named files under `tmp_path` (e.g. `test_check_multiple_files`) so they match the new default glob scope, or pass an explicit `files=` override — otherwise this change breaks passing tests.
2. Add an `indeterminate_links`-only test and a combined broken+indeterminate test to `test_cli_doctor_full.py`, mirroring the existing `unreachable_links`-only case.
3. Add a directory-denylist test to `test_link_checker.py` following `test_init_core.py`'s `test_excludes_node_modules` shape.
4. Review `scripts/little_loops/loops/docs-sync.yaml`'s `check_links` state routing comment (line 49, which references `link_checker.py`'s `action_severity` assignment) and `scripts/little_loops/loops/lib/cli.yaml`'s `ll_check_links` fragment description text for accuracy once `INDETERMINATE` exists.
5. Update `docs/reference/API.md` and `docs/reference/CLI.md` to document the `INDETERMINATE`/`"indeterminate"` tier (and fix the pre-existing `"unreachable"` omission in API.md's status-field comment while touching that line).
6. Update `.claude/CLAUDE.md`'s one-line `ll-check-links` summary if scope/status semantics changed enough to affect it, and regenerate host-adapted help mirrors (`commands/help.md`, `.gemini/commands/help.toml`, `.kimi-code/skills/ll-help/SKILL.md`) via `ll-adapt` if so.

## Impact

The `ll-doctor --full` link gate is currently unactionable and permanently red, which
trains maintainers to ignore the entire `--full` exit code — eroding the value of
every other check it aggregates (`des_audit`, `design_tokens`, `host_map`,
`package_data`, and the rest). Fixing it restores a gate that can be trusted and
acted on, and removes pointless outbound HTTP traffic to auth-walled corporate URLs
captured in loop run artifacts.

## Acceptance Criteria

- [x] `DEFAULT_DOC_FILES` is referenced by `check_markdown_links()`; no dead
      constant remains.
- [x] `ll-check-links` with no arguments does not visit `node_modules/`,
      `.pytest_cache/`, `.loops/`, `thoughts/`, or `.issues/`.
- [x] An explicit path argument still cannot pull in `node_modules/` or
      `.pytest_cache/` (denylist applies regardless of scope).
- [x] HTTP 429/401/403/5xx are reported but do not set exit code 1; 404/410 still
      do. Both classification sites (line 208 success path and the `HTTPError`
      handler) route through the same shared classifier.
- [x] `--strict-network` gates on `INDETERMINATE` as well as `UNREACHABLE`.
- [x] `ll-doctor --full`'s `_full_check_links_data()` adapter handles the
      `INDETERMINATE` tier (reported as informational, not error) and does not
      break on the new `LinkResult.status` value.
- [x] 429 responses honor `Retry-After` before retrying, with the delay capped
      (≤30s) and a bounded total retry budget per run.
- [x] Unit tests cover each status-code tier's outcome classification and the scope
      denylist, using a stubbed fetch layer (no live network in the suite).
- [x] `ll-doctor --full` `check_links` reports only genuine 404/410s. A residual
      red count from `docs/research/dreaming-research-synthesis.md` (~33 rotted
      bibliography URLs) is expected until the follow-up content-triage issue
      lands — this issue does not make the gate green, it makes the red count
      honest and actionable.

## Scope Boundaries

**In scope:** `scripts/little_loops/link_checker.py` scope resolution and HTTP status
classification; corresponding tests in `scripts/tests/`.

**Out of scope:** fixing the ~33 rotted bibliography URLs in
`docs/research/dreaming-research-synthesis.md`. That is content triage, not a tooling
defect — file separately once this lands and the real 404 list is legible. Note the
consequence: because `DEFAULT_DOC_FILES` includes `docs/**/*.md`, the `ll-doctor
--full` gate stays red (with a small honest count) until that follow-up lands. Consider
annotating that file as a citation list rather than chasing dead academic URLs.

Also out of scope: the `claude_md_suppression` and `auto_commit` ✗ marks in
`ll-doctor --full` output. Those are capability/config reporting, not failures.

## Notes

- Per project CI policy there is no hosted CI; tests live in `scripts/tests/` under
  `python -m pytest scripts/tests/` and must stub the fetch layer so the suite makes
  no live network calls.
- Related: ENH-2836 established the report-but-don't-gate stance for
  unreachable/timeout links. This extends the same reasoning to HTTP statuses that
  are not authoritative about link liveness.


## Session Log
- `/ll:manage-issue` - 2026-07-30T20:55:03 - `bb2e38ab-1ec5-4aff-b350-56f1d97a5912.jsonl`
- `/ll:ready-issue` - 2026-07-30T20:42:25 - `4b9c7f3c-2afc-4e9c-9590-ce32ef8e56b5.jsonl`
- `/ll:wire-issue` - 2026-07-30T20:39:19 - `8472a67c-562a-4560-bb95-8fe9714d9309.jsonl`
- `/ll:refine-issue` - 2026-07-30T20:34:24 - `ca840b60-f6b0-4f4e-9626-7c0dd40b4a87.jsonl`
