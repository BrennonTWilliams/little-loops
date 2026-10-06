---
name: ll-verify-issues
description: Verify issue files for accuracy, relevance, and completeness by testing claims against actual code
argument-hint: "[issue-id]"
allowed-tools:
  - Read
  - Glob
  - Grep
  - Edit
  - Bash(git:*)
  - Bash(ll-code:*)
  - Bash(ll-verify-evidence:*)
  - Bash(ll-issues:*)
arguments:
  - name: issue_id
    description: Optional specific issue ID to verify
    required: false
  - name: flags
    description: "Optional flags: --auto (non-interactive, apply all non-destructive changes without prompting), --check (check-only mode, implies --auto), --from-evidence (BUG-3637: non-check mode only — re-check and correct only the claims listed in the issue's verify_evidence frontmatter field, skip the full 2A-2E sweep, no-op if verify_evidence is absent)"
    required: false
---

# Verify Issues

You are tasked with verifying that issue files accurately describe the current state of the codebase.

## Configuration

This command uses project configuration from `.ll/ll-config.json`:
- **Issues base**: `{{config.issues.base_dir}}`
- **Source directory**: `{{config.project.src_dir}}`

## Process

### 0. Parse Flags

```bash
ISSUE_ID="${issue_id:-}"
FLAGS="${flags:-}"
AUTO_MODE=false
CHECK_MODE=false

# Auto-enable auto mode in automation contexts
if [[ "$FLAGS" == *"--dangerously-skip-permissions"* ]] || [[ -n "${LL_NON_INTERACTIVE:-}" ]] || [[ -n "${DANGEROUSLY_SKIP_PERMISSIONS:-}" ]]; then
    AUTO_MODE=true
fi

if [[ "$FLAGS" == *"--auto"* ]]; then AUTO_MODE=true; fi
if [[ "$FLAGS" == *"--check"* ]]; then CHECK_MODE=true; AUTO_MODE=true; fi

# BUG-3637: --from-evidence is a non-check-mode-only targeted correction pass.
# Parsed here so downstream section 3/4 logic can branch on it, but it has no
# effect when CHECK_MODE is true (--check always runs the full 2A-2E sweep;
# it is the producer of verify_evidence, never a consumer of it).
# Check B8 (format-check citations) is skipped under --from-evidence; the post-write
# format-check in section 4 ("must not re-introduce the finding") still applies.
FROM_EVIDENCE=false
if [[ "$FLAGS" == *"--from-evidence"* ]]; then FROM_EVIDENCE=true; fi
```

### 1. Find Issues to Verify

```bash
if [ -n "$ISSUE_ID" ]; then
    # ENH-3031: honor a provided issue_id — verify only that issue, not the
    # whole active backlog. Without this filter, every caller that passes an
    # explicit ID (e.g. a per-issue FSM gate) silently falls through to a
    # whole-backlog pass, and with Edit in allowed-tools that pass can mutate
    # issues the caller never asked to touch.
    ll-issues path "$ISSUE_ID"
else
    # List only active issues (open, in_progress, blocked) — skips deferred, done, cancelled
    ll-issues list --json --status all | \
      python3 -c "import json,sys; [print(i['path']) for i in json.load(sys.stdin) if i.get('status') in {'open','in_progress','blocked'}]" | \
      sort -u
fi
```

### 2. For Each Issue

#### A. Parse Issue Content
- Extract file paths and line numbers mentioned
- Identify code snippets quoted
- Note expected vs. actual behavior claims

#### B.0 Graph-assisted checks (ENH-3126)

Active only when the issue names concrete symbols/files and `ll-code --json status`
reports `available: true`. **Read
[`docs/guides/GRAPH_DISCOVERY_GUIDE.md`](../docs/guides/GRAPH_DISCOVERY_GUIDE.md) and
follow its procedure, contract, and three safety rules** — this section states only
what is specific to verify-issues, not the shared contract.

Permitted query surface (verify-issues only):

```bash
ll-code --json status
ll-code --json defines <file>            # anchor relocation
ll-code --json callers-of <symbol>       # negative-claim corroboration
ll-code --json references <symbol>       # negative-claim corroboration
# NOT permitted: callees-of, importers-of, impact-of
```

`impact-of` is excluded — regression detection (2D) already has a deterministic
signal in git history (fix commit → files changed since), and a transitive-closure
guess on top only widens the blast radius of a wrong `REGRESSION` verdict.

**Verdict-origination prohibition (stricter than the other two consumers):** A
graph result may corroborate or correct a verdict. It may never originate one. In
particular, `callers-of` (or `references`) exiting `1` ("no callers") must never by
itself produce `RESOLVED` or `INVALID`; the exploratory Grep pass in 2B still runs
and decides. A result showing callers/references, by contrast, safely **refutes** a
"never called"/"dead" claim on its own — presence is easy to prove, absence is not.

Provider absent, `status.available: false`, or a query exiting `2` → silent
fallback to today's flow, zero behavior change. If `status.freshness` is `stale`,
demote every graph result to a lead only — confirm each positive hit with one
targeted Grep at its `path:line` before it informs a verdict.

Wire the results into the checks below:
- **Anchor relocation**: on a `path:line` mismatch in check 2B.2, one `ll-code
  defines <file>` call locates the named symbol's current line; the verdict becomes
  `OUTDATED` with the corrected line written back, instead of an unresolved "not
  found at line N".
- **Negative claims**: for issue text asserting "X is never called"/"no caller
  handles this"/"this path is dead", run `ll-code callers-of`/`references` on the
  named symbol before falling back to Grep-only reasoning. A hit refutes the claim
  outright; a miss is a lead that the normal exploratory pass must still confirm.

Record the provider and freshness that served each graph-assisted check (`ll-code
--json status` → `provider`, `freshness`) on the Section 5 output report — a later
reader cannot otherwise tell an index-accelerated verification from a grep-fallback
one, and the two are not equally trustworthy. Do **not** put this in the Session Log
entry (Section 4.5): that line's format is parsed by `issue_design_timestamp()`
(`little_loops.issues.program_design:issue_design_timestamp`) and extra text breaks the
Program Design gate's arming.

#### B. Verify Against Codebase
1. **Check files exist**: Do referenced files still exist? (B8 governs examined
   occurrences — see check 8.)
2. **Verify line numbers**: Has the code moved or changed? (B8 governs examined
   occurrences — see check 8.)
3. **Validate code snippets**: Does quoted code match current code?
4. **Test claims**: Is the described behavior accurate?
5. **Check decisions rules**: Gate on the decisions log, then run the query without
   `|| true` so a command failure surfaces instead of masquerading as "no rules"
   (BUG-2423) — do **not** blackhole stderr:

   The decisions log is hybrid storage — a legacy `.ll/decisions.yaml` flat file
   and/or `.ll/decisions.d/*.json` fragments — so gate on either (a fresh,
   never-compacted install has only the fragment dir):

   ```bash
   if [ -f .ll/decisions.yaml ] || [ -d .ll/decisions.d ]; then
       required_rules=$(ll-issues decisions list --type rule --enforcement required --active-only)
       if [ $? -ne 0 ]; then
           echo "⚠ [DECISIONS] required-rule query failed — decisions check did NOT run" >&2
       elif [ -n "$required_rules" ]; then
           : # for each required rule, check whether the issue's proposed solution conflicts
       fi
   fi
   ```

   If the query **fails**, note the check did not run (do not treat as a clean pass).
   If output is non-empty, check whether the issue's proposed solution conflicts with
   any active required rule. Suppress violations where a matching exception entry
   (`rule_ref` = rule ID) exists. Assign verdict `DECISIONS_VIOLATION` if a
   non-suppressed violation is found. An absent decisions log (no `.ll/decisions.yaml`
**and** no `.ll/decisions.d/`) is a graceful skip.
6. **Proposal-vs-code consequence check (ENH-3250)** — a separate sub-check from
   checks 1-4 above. Those are retrospective: they test whether the issue's claims
   about the *current* state of the code are true. This check is prospective: it
   asks what happens if the `## Proposed Solution` is implemented *as written*,
   read against the code it names.

   **Precondition — skip entirely if `## Proposed Solution` is absent, `TBD`, or
   still template boilerplate.** Do not run this check on issues with nothing
   prescriptive to evaluate; this keeps the added cost off batch `/ll:verify-issues`
   runs over issues that never proposed anything.

   When the precondition is met, trace the proposal against the code it touches for:
   - **Exception-handler compatibility**: does the proposed change raise, or route
     through, an exception type not covered by an `except` clause it now passes
     through (e.g. adding `timeout=` to a call whose handler does not catch the
     resulting timeout exception's actual type/MRO)?
   - **Test-fixture invalidation**: does the proposal add a call, branch, or code
     path that an existing test's mock/fixture does not account for (e.g. a second
     call landing on a single-`return_value` mock intended for the first)?
   - **AC coverage of identified integration points (BUG-3695)**: walk **every
     actual Integration Map entry** once and classify it `covered`, `uncovered`
     or `not applicable` (with the applicable directive and a one-line reason).
     Decide by the entry's **role in the selected mechanism**, not its subsection
     name:

     | Entry's role in the selected mechanism | Required coverage |
     |---|---|
     | Observable behavior, public API or compatibility contract change | An Acceptance Criterion stating the expected outcome and how it is verified |
     | Required test/mock/fixture update or fixture invalidation | A concrete Implementation Step — do not invent an AC for the fixture itself |
     | Context-only existing caller, unchanged helper, Similar Pattern, or Tests/Documentation inventory | `not applicable` with a reason — listing a file alone creates no requirement |

     Several entries may share one criterion or step; coverage is not one AC per
     filename. An entry that describes a real behavior/contract consequence stays
     applicable even when filed under Tests or Documentation. An AC that merely
     says a surface "is covered" is not coverage. Collect **all** uncovered
     applicable points in this one pass — do not stop at the first, and do not
     narrow scope after a failed replay — because the repair loop gets one
     reconcile attempt per run. An applicable gap whose fix would change the
     chosen mechanism is `PROPOSAL_UNSOUND`, not directive drift.

   This is judgment over consequences, not a claim to corroborate — read the
   Proposed Solution's diff-shape against the current code the same way an
   implementer would before writing it, not the way checks 1-4 read the issue's
   prose against the code.

   **Verdict** (BUG-3574): classify each finding by **which section must change to
   fix it**, not by sub-check. If the fix is confined to Implementation Steps /
   Acceptance Criteria / Integration Map and the selected mechanism stands (e.g. an
   AC gap, a fixture-invalidation step) → `DIRECTIVE_DRIFT` (§C). If the selected
   option / Proposed Solution itself must change (the chosen mechanism is refuted)
   → `PROPOSAL_UNSOUND` (§C). When both kinds of finding exist,
   `PROPOSAL_UNSOUND` wins (a refuted proposal makes directive drift moot). If checks 1-4 *also*
   find a claim about current state to be false, the claim-verdict wins
   (`OUTDATED`/`INVALID`/`NEEDS_UPDATE`/etc.) — its remedy repairs the research
   the proposal check itself depends on, so it must run first: `correct_claims`
   for an in-scope `CLAIMS_OUTDATED` finding (BUG-3637), `refine_followup` for
   any other claim defect. Only assign `PROPOSAL_UNSOUND` / `DIRECTIVE_DRIFT` when every claim about current state
   holds and the defect is purely in the proposal's consequences.
7. **Evidence-quote existence check (BUG-3282)** — deterministic, run via the CLI
   rather than LLM judgment. A quote attributed to a named artifact (another
   `.issues/` file, or a file path) can be code-accurate everywhere else and still
   be fabricated evidence: a snippet that never appeared in the artifact it is
   attributed to, at HEAD, in the working tree, or in any git revision. This is
   the strongest-looking, least-checked part of an issue — downstream passes treat
   an evidence quote as settled ground.

   Run:
   ```bash
   ll-verify-evidence "$ISSUE_FILE" --json
   ```
   A non-clean (`"ok": false`) result names the unverifiable span(s) and the
   artifact each was attributed to. `ll-verify-evidence` unavailable (non-zero on
   invocation itself, not a findings result) → silent fallback, zero behavior
   change, matching §B.0's `ll-code` convention.

   **Verdict**: any finding → `EVIDENCE_UNVERIFIED` (§C), and it **outranks**
   `PROPOSAL_UNSOUND` when an issue qualifies for both (Decision Rules → Verdict
   precedence in BUG-3282's Program Design): a fabricated premise very often also
   yields an unsound proposal built on top of it, and the premise must be named
   first or the proposal-repair path re-derives the fiction. The verdict is
   currently **advisory** — reported and persisted, but not routed; see §C.

8. **Citation findings via format-check (BUG-3708)** — `ll-issues format-check`
   owns path / line-range / symbol-location resolution; defer to it instead of
   re-deriving it, and do not restate its algorithms here. **B8 governs examined
   occurrences**: where `examined_refs` has an entry for the occurrence and
   property, B8 decides the mechanical question; your ad-hoc read stands only for
   unexamined occurrences and for content/premise judgments (what a line says,
   whether the premise holds), which a range or location check cannot decide.
   Gap keys, blocking-vs-advisory split and entry schema: `docs/reference/CLI.md`
   (format-check).

   Call once, **after** your reads, with the current per-issue ID (in batch, the
   issue being verified; never `$ISSUE_FILE`), and share that result with §E step 3.
   Re-run only after a §4 edit; never reuse a prior pass's output:
   ```bash
   ll-issues format-check "$ID" --format json
   ```
   **Consumable = stdout parses to a JSON object whose `examined_refs` is a list** —
   not the exit code (0 and 1 are both valid; exit 1 also covers non-JSON "not
   found" errors). Otherwise, an empty list, unknown property/result values, or
   conflicting entries for one occurrence/property → silent fallback to model
   judgment, matching B7. Skipped under `--from-evidence`; runs read-only under
   `--check`; it never repairs citations.

   Two sources. **Blocking** findings come from the top-level blocking gap lists
   (no occurrence key — a plain path mention has no `examined_refs` entry, so match
   a model finding by ref string). **`examined_refs`** entries are used for
   demotion and advisory coverage: match the exact occurrence
   (`issue_line`, `issue_column`, `ref`) and `property` against the full issue text;
   never a canonical path alone. If a model finding cannot be located
   unambiguously, keep model judgment. Count a blocking symbol result found in
   both sources once.

   | Coverage for the exact occurrence/property | Treatment |
   |---|---|
   | `ok` | Demote a conflicting mechanical model finding **of the same property** to an advisory note; no verdict effect |
   | Blocking gap key | Surface it even if you missed it; deduplicate; a check-1/check-4 `NEEDS_UPDATE` finding under §2C's correctable-scope rule |
   | Advisory gap key | Report it, and any equivalent model finding, as advisory; neither changes the verdict |
   | Absent, unsupported, malformed or contradictory | Current model judgment for that occurrence/property |

   **Property-exact demotion.** A pass is evidence only for its own property.
   `path_resolves: ok` is tracked-index resolution only: demote a "file doesn't
   exist" objection only if the file also exists on disk. `line_in_range: ok`
   demotes only a "line is past end of file" objection, never a claim about what
   the line contains. `symbol_resolves_in: ok` is import-inclusive and never demotes
   "not defined here" (that needs `symbol_defined_in: ok`). A pass in one
   occurrence never overrides another; a missing entry means "not examined", not
   "passed". Report `stale_file_ref` as **untracked**, not "missing".

**Causal / identity claims (method for check 4, unconditional — runs regardless of
`ll-code` availability or index freshness; not part of §2B.0):** for issue text
attributing observed state to a named cause, origin, or version — "is the vN
definition", "caused by", "because", "the result of", "introduced by", "this is the
pre-X form" — where that attribution is load-bearing for the fix (the issue's stated
root cause, an artifact-identity assertion, or a version/origin attribution that
determines what gets changed), probe the claimed cause directly rather than a
consequence merely consistent with it: read the artifact in its own terms (e.g.
stored DDL via `SELECT sql FROM sqlite_master WHERE name=...`) over an inferred
signal (e.g. `PRAGMA table_info(...)`), the actual file/commit content over a
symptom that is merely consistent with it. Incidental causal prose ("we filed this
because the reader was empty") does not trigger this rule. Observing a consequence
consistent with the stated cause is necessary but not sufficient to confirm it — it
only fails to refute it. If the cause can be read directly and the direct read
confirms it, `VALID` is available as before. If the cause cannot be read directly,
assign `NEEDS_UPDATE` rather than `VALID`, and name the unverified claim in the
verification output.

#### C. Determine Verdict

| Verdict | Meaning |
|---------|---------|
| VALID | Issue accurately describes current state |
| OUTDATED | Referenced code has changed |
| RESOLVED | Issue appears to be fixed |
| INVALID | Issue description is incorrect |
| NEEDS_UPDATE | Valid but needs clarification |
| REGRESSION_LIKELY | Matches completed issue, files modified since fix |
| POSSIBLE_REGRESSION | Matches completed issue, but can't confirm regression |
| DEP_ISSUES | Dependency references have problems (broken refs, missing backlinks, cycles) |
| DECISIONS_VIOLATION | Issue violates an active required rule in the decisions log |
| PROPOSAL_UNSOUND | The Proposed Solution, implemented as written, contradicts the code it names (check B6) and the selected option must change — a claim-verification defect, not a claim, so it is not remedied by `refine_followup` or `reconcile-issue` |
| DIRECTIVE_DRIFT | Check B6 finding whose fix is confined to Implementation Steps / Acceptance Criteria / Integration Map; the selected mechanism stands (BUG-3574) — remedied by `reconcile-issue --from-verify-evidence` (BUG-3695), which reads the persisted `verify_evidence` and may add the entailed AC/Step |
| EVIDENCE_UNVERIFIED | A quoted evidence span attributed to a named artifact (check B7) exists in no revision of that artifact — outranks `PROPOSAL_UNSOUND` when both apply |
| CLAIMS_OUTDATED | An `OUTDATED`/`NEEDS_UPDATE` finding (checks 1-4) whose fix is a **factual metadata correction** only (BUG-3637; see correctable-scope rule below) — remedied by `correct_claims`, not `refine_followup` |

**Correctable scope for `CLAIMS_OUTDATED` (BUG-3637).** Classify an `OUTDATED`/
`NEEDS_UPDATE` finding by **which section its fix touches**, the same
principle §B6 already applies to split `PROPOSAL_UNSOUND` from
`DIRECTIVE_DRIFT`. A finding is `CLAIMS_OUTDATED` only when its fix is
confined to Codebase Research Findings, Confidence Check Notes, Verification
Notes, Integration Map citations, Similar Patterns/Tests citations, or
frontmatter references, and is one of: another issue's status, a file path, a
line number/range, a count (line/state/test counts), or a citation
anchor/symbol location. `OUTDATED` also covers a *premise* change (bug
partially fixed, targeted code refactored) — auto-rewriting a premise in
place is unsafe because an independent `--check` re-pass cannot catch it (the
rewritten issue would be internally consistent), so any finding whose fix
requires changing Summary, Current Behavior, Expected Behavior, Root Cause,
Motivation, Steps to Reproduce, or Proposed Solution stays `NON_VALID`, never
`CLAIMS_OUTDATED`, regardless of how narrow the actual text change looks.
`## Context` is in neither list above: a finding whose fix touches it (e.g. a
blocking citation key surfaced by check B8) is an `OUTDATED`/`NEEDS_UPDATE` finding
outside the correctable scope, so it stays `NON_VALID`.
`INVALID`, `RESOLVED`, `DECISIONS_VIOLATION`, `REGRESSION_LIKELY`,
`POSSIBLE_REGRESSION`, and `DEP_ISSUES` are never `CLAIMS_OUTDATED` — they
always persist as `NON_VALID` (never-auto-correct set). When an issue has
findings in both scopes, `NON_VALID` wins (see verdict precedence in §2.5).

#### E. Validate Dependency References

For each issue, check dependency integrity. Resolve target status from
**frontmatter**, not directory location — `done`/`cancelled` issues stay in
their type directories, so "in completed" is not a status signal (BUG-3637):

1. **Blocked By / Depends On references**: Read the issue's frontmatter
   `blocked_by` and `depends_on` lists (fall back to the body `## Blocked By`
   section only if frontmatter is absent). For each referenced ID:
   - Verify the referenced issue exists. If missing entirely: flag as
     BROKEN_REF.
   - Resolve its status via `ll-issues show <REF> --json` and lowercase the
     value (the field is display-cased, e.g. `"Completed"` for `done`). An
     edge whose target status is `done`/`completed`/`cancelled` is
     **satisfied** — note it informationally, never as an error, and it never
     contributes to a non-VALID verdict on its own. `deferred` is
     non-terminal (stays an open blocker, like `open`/`in_progress`/`blocked`).
   - **Skip the backlink check below for satisfied edges** — a satisfied edge
     whose target lacks a `## Blocks` backlink is not a defect; requiring one
     would route a satisfied dependency into `DEP_ISSUES` → `NON_VALID`, which
     the correctable-claims rule (§2C) can never auto-correct.

2. **Blocks backlinks**: For each *unsatisfied* ID from step 1:
   - Check that the referenced issue has this issue in its `## Blocks` section
   - If missing: flag as MISSING_BACKLINK

3. **Prose dependency claims**: Consume the `ll-issues format-check <ID> --format
   json` result already fetched once by check B8 (call it yourself only if B8 was
   skipped) — its `stale_prose_dep` / `prose_dep_drift` output (already computed from
   issue statuses and already run by `normalize_structure` before every verify
   in `refine-to-ready-issue.yaml`) instead of re-deriving the same judgment by
   reading prose. Prose asserting that a dependency is resolved, satisfied, or
   no longer present is **consistent** with a satisfied edge from step 1, not a
   contradiction — only prose asserting a satisfied target is still
   *open/active* is a claim finding (route through §2C's claim-verdict checks).

4. **Cycle check**: After processing all issues, build a dependency graph and check for cycles

#### D. Regression Detection (for matches to completed issues)

When an issue matches a completed issue, perform regression analysis:

1. **Extract fix metadata** from the completed issue's Resolution section:
   - `Fix Commit`: SHA of the commit that fixed the issue
   - `Files Changed`: List of files modified by the fix

2. **Analyze git history** to classify the match:
   | Scenario | Classification | Meaning |
   |----------|----------------|---------|
   | No fix commit tracked | UNVERIFIED | Can't determine - original fix not recorded |
   | Fix commit not in history | INVALID_FIX | Fix was never merged/deployed |
   | Files modified AFTER fix | REGRESSION | Fix worked, later changes broke it |
   | Files NOT modified after fix | INVALID_FIX | Fix was applied but never actually worked |

3. **Present evidence** including:
   - Original fix commit SHA
   - Files modified since fix
   - Related commits that touched the fixed files
   - Days since original fix

### 2.5. Check Mode Behavior (--check)

**When `CHECK_MODE` is true**: Run all verification logic (sections 2A-2E) without writing changes (other than the verdict persistence below). For each issue with a non-VALID verdict, print `[ID] verify: [verdict]`. After all issues checked, if any were non-VALID: print `N issues not verified`, then `exit 1`. If all VALID: print `All issues verified`, then `exit 0`. This integrates with FSM `evaluate: type: exit_code` routing (0=success, 1=failure, 2+=error).

**Persist the verdict to frontmatter (ENH-3031).** A slash command's internal
exit code never reaches the host CLI's process exit code — `action_type:
slash_command` runs through the host session, not a shell whose exit status an
FSM `fragment: shell_exit` gate can read. Callers that need a deterministic
gate on this command's verdict (e.g. `refine-to-ready-issue.yaml`'s
`verify_issue` → `route_pre_score_obligation` pair) read a persisted artifact
instead. For **each** issue checked in this mode, use the `Edit` tool to write
or update a `verify_verdict:` line in that issue's YAML frontmatter block:

- `VALID` verdict → `verify_verdict: VALID`
- `EVIDENCE_UNVERIFIED` verdict (BUG-3282, check B7) → `verify_verdict:
  EVIDENCE_UNVERIFIED` — persisted as its own value, **not** collapsed into
  `NON_VALID`, so the `route_pre_score_obligation` dispatch in
  `refine-to-ready-issue.yaml` (its `VERIFY:EVIDENCE_UNVERIFIED` token) can read it. **Outranks `PROPOSAL_UNSOUND`**: an
  issue can satisfy both, and the fabricated premise must be named before the
  proposal built on top of it is rewritten, or the rewrite re-derives the
  fiction. It still counts as a non-VALID, `exit 1` outcome in `--check` mode
  below — the split is in the persisted value, not the exit-code contract.

  **Advisory, not routing (fallback F3, decided 2026-08-21).** The verdict is
  detected, persisted, and reported, but the `VERIFY:EVIDENCE_UNVERIFIED` route does *not*
  divert the loop to `reconcile_issue` — it falls through to
  `check_gate_refine_limit`, like any other non-VALID verdict. The detector measured ~0.13–0.20 precision on a
  hand-labelled 30-finding sample against a 0.30 blocking bar; the residual is
  the *paraphrase* class (spans quoting real code inexactly), which no
  attribution or span-kind rule reaches. Below 0.30 a false verdict sends a
  **correct** issue into a rewrite, so routing is net-negative even when the
  gate is right. Re-arm — route `VERIFY:EVIDENCE_UNVERIFIED` to `check_reconcile_limit` — only once
  precision is measured ≥ 0.30 with recall still 1.00 on labelled true
  fabrications.
- `PROPOSAL_UNSOUND` verdict (ENH-3250, check B6) → `verify_verdict:
  PROPOSAL_UNSOUND` — persisted as its own value, **not** collapsed into
  `NON_VALID`, so the `VERIFY:PROPOSAL_UNSOUND` route of `route_pre_score_obligation` in
  `refine-to-ready-issue.yaml` can
  route it to a bounded design revision (BUG-3574) instead of `reconcile_issue`,
  which cannot edit `## Proposed Solution`. It still counts as a non-VALID,
  `exit 1` outcome in `--check` mode below — the split is in the persisted
  value, not the exit-code contract. Only assigned when the issue does not also
  qualify for `EVIDENCE_UNVERIFIED` above. Also write a one-line
  `verify_evidence:` field holding the B6 finding as a **double-quoted YAML
  scalar** on a single line (no newlines) with `"` and `\` escaped, e.g.
  `verify_evidence: "handler at x.py:40 swallows it"` — a bare value holding
  `: `, a leading backtick, `#` or quotes breaks the frontmatter and the gate
  then reads the verdict as absent. Frontmatter only; `--check` makes no body
  edits, and never invents alternatives.
- `DIRECTIVE_DRIFT` verdict (BUG-3574, check B6) → `verify_verdict:
  DIRECTIVE_DRIFT` — persisted as its own value so the `VERIFY:DIRECTIVE_DRIFT` route can
  route it to `reconcile_issue`. Non-VALID, `exit 1` in `--check` mode. Ranks
  below `EVIDENCE_UNVERIFIED` and `PROPOSAL_UNSOUND`. In the **same frontmatter
  update** (BUG-3695) also write the **complete current** `verify_evidence:`
  field — replace any prior value, never append — as a **double-quoted YAML
  scalar** on a single line (no newlines, `"` and `\` escaped), one item per
  applicable uncovered point or fixture/compatibility drift found in this pass,
  `; `-separated, each shaped `<section>: '<specific drift>' -> <entailed
  correction>`, e.g. `verify_evidence: "Acceptance Criteria: 'no AC covers the
  ll-doctor rebuild-pending surface' -> add an AC stating the expected
  notice and how it is verified"`. Do not truncate the list or drop findings.
  `reconcile-issue --from-verify-evidence` consumes it; `clear_verify_verdict`
  removes it (value-agnostic) before the next verify. Frontmatter only under
  `--check`.
- `CLAIMS_OUTDATED` verdict (BUG-3637): when every `OUTDATED`/`NEEDS_UPDATE`
  finding is in the correctable scope defined in §2C (and no finding from the
  never-auto-correct set below applies) → `verify_verdict: CLAIMS_OUTDATED` —
  persisted as its own value, **not** collapsed into `NON_VALID`, so the
  `VERIFY:CLAIMS_OUTDATED` route of `route_pre_score_obligation` in
  `refine-to-ready-issue.yaml` can route it to `correct_claims` instead of
  `refine_followup`, which cannot delete or rewrite a stale fact (additive
  only, `commands/refine-issue.md` §5c). Non-VALID, `exit 1` in `--check` mode
  — the split is in the persisted value, not the exit-code contract. Also
  write a one-line `verify_evidence:` field as a **double-quoted YAML
  scalar** on a single line (no newlines, `"` and `\` escaped), one item per
  stale claim, `; `-separated, each item shaped `<section>: '<stale text>' ->
  <current truth>` (single quotes inside an item avoid `"` escaping), e.g.
  `verify_evidence: "Confidence Check Notes: 'BUG-3628 is open' -> BUG-3628 is
  done; Integration Map: 'prepare-issue.yaml (91 lines)' -> 90 lines"`. Naming
  the section lets `correct_claims` apply the fix without re-locating the
  claim. `clear_verify_verdict` already removes `verify_evidence` by key name
  (value-agnostic), so no new cleanup is needed.
- Any other verdict — `OUTDATED`/`NEEDS_UPDATE` with at least one finding
  outside the correctable scope, `RESOLVED`, `INVALID`,
  `REGRESSION_LIKELY`, `POSSIBLE_REGRESSION`, `DEP_ISSUES`, or
  `DECISIONS_VIOLATION` (the never-auto-correct set) → `verify_verdict:
  NON_VALID`. These are never assigned `CLAIMS_OUTDATED`, even when only one
  finding drives the verdict.

**Full verdict precedence (one persisted value per issue, highest wins):**
`NON_VALID` > `EVIDENCE_UNVERIFIED` > `CLAIMS_OUTDATED` > `PROPOSAL_UNSOUND` >
`DIRECTIVE_DRIFT` > `VALID`. `EVIDENCE_UNVERIFIED` outranks `CLAIMS_OUTDATED`
because a fabricated quote is not a stale fact and must not be "corrected"
into the file as if it were true. `CLAIMS_OUTDATED` outranks
`PROPOSAL_UNSOUND`/`DIRECTIVE_DRIFT` per §B6's existing "claim-verdict wins"
rule — a proposal built on an outdated premise must have that premise
corrected first, or the proposal-repair path re-derives the same fiction.

If the field already exists in the frontmatter, replace its value in place;
otherwise insert it alongside the issue's other single-line frontmatter
fields (e.g. after `confidence_score` if present). This write happens even
though `CHECK_MODE` otherwise skips section 4's content edits — it is the
one artifact this mode is responsible for producing.

### 3. Request User Approval

**Skip this section if `AUTO_MODE` is true.** In auto mode, proceed directly to Phase 4, applying all non-destructive changes (verification notes, line number updates). Skip updating resolved issue status in auto mode (destructive action requires explicit approval).

Before making any changes, present the verification results to the user:

1. Show the summary table with all verdicts
2. List specific changes that will be made:
   - Issues to update with verification notes
   - Issues to close (set `status: done` in frontmatter)
3. Ask: "Proceed with these changes? (y/n)"
4. Wait for user confirmation before modifying any files

### 4. Update Issue Files

For issues needing updates:
- Add a `## Verification Notes` section (see 4.1 for how to phrase the opening
  line when this pass also applied fixes)
- Document what changed or needs correction
- Update file paths and line numbers if moved

For resolved issues:
- Add resolution note
- Consider setting `status: done` in frontmatter

**In-place claim correction (BUG-3637).** A Verification Notes entry alone
does not count as a correction of a stale claim — it must also be rewritten
**in place** in whichever section holds it (including a stale frontmatter
status/line-count reference), bounded by §2C's correctable-scope rule (never
rewrite Summary / Current Behavior / Expected Behavior / Root Cause /
Motivation / Steps to Reproduce / Proposed Solution here; those verdicts stay
`NON_VALID` and read-only). This applies:
- **Under `--from-evidence`** (non-check mode): read the issue's
  `verify_evidence` frontmatter field. If absent or empty, make no edits and
  exit — the following `--check` re-pass then decides. Otherwise, re-check
  **only** the listed claims against the codebase and rewrite each confirmed
  stale claim in place; do not run the full 2A-2E sweep and do not apply
  fixes beyond the `verify_evidence` work list.
- **In a normal (non-`--from-evidence`) non-check run**, for any in-scope
  `OUTDATED`/`NEEDS_UPDATE` finding the 2A-2E sweep itself surfaces: rewrite it
  in place the same way, in addition to the full sweep's other work. A plain
  `/ll:verify-issues <ID>` run (no `--from-evidence`) keeps its normal
  full-sweep behavior regardless of any `verify_evidence` a prior run left
  behind — the flag is explicit, never inferred from the field's presence.

**Verification Notes must not re-introduce the finding.** A note describing a
stale claim must **paraphrase** any path, symbol, flag or line citation it is about,
never quote it verbatim: a quoted stale path in `## Verification Notes` is itself
scanned by `ll-issues format-check` and re-triggers the same `stale_file_ref` /
`CLAIMS_OUTDATED` finding on the next `--check`. Describe it instead (e.g. "a
slash-joined shorthand for the skill, rubric and reference text"). After writing the
note, run `ll-issues format-check <ID>`; if it reports a `stale_file_ref` (or other
citation finding) that your own edit introduced, reword the note and re-run until
clean. This post-write check applies under `--from-evidence` too, even though
check B8 is skipped there.

### 4.1 Verdict Phrasing When Fixes Are Applied in the Same Pass

**Applies whenever this run is not `CHECK_MODE`** (i.e. `--auto` or interactive) **and**
section 4 edited the same content the Verification Notes section describes. `--check`
mode never reaches this rule — it exits before any content edit, so its bare verdict
label always describes the file's true current state (see 2.5).

**Label source**: use the verdict value from the `#### C. Determine Verdict` table in
2C (`VALID`, `NEEDS_UPDATE`, `OUTDATED`, etc.) — the verdict as it stood *at detection
time*, before this pass's fixes were applied. Do not use the collapsed
`VALID`/`NON_VALID` frontmatter enum from 2.5; that enum is for the frontmatter field
only, never for Verification Notes prose.

**Never write a bare `Verdict: X` label** in a fix-applying pass — by the time the
note is written the fix has already landed, so a bare label describes a state that no
longer exists and reads as an outstanding action item. Use one of these two forms
instead:

- **Fully resolved** — every finding from this pass was corrected in the same edit:
  > Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same
  > pass, so the issue as it now reads is up to date — this section is a record of
  > what was wrong and fixed, not an outstanding action item)
- **Partially resolved** — one or more findings were not corrected (e.g. a decision
  needing human input, or a destructive change auto mode cannot make): use the same
  lead line, then add an explicit `Remaining:` line naming each uncorrected finding.

**Frontmatter sync**: if `verify_verdict:` already exists in the issue's frontmatter,
rewrite it in place to reflect the post-fix state — `VALID` if this pass resolved
everything, otherwise the 2.5 mapping applied to the residual (unfixed) verdict
(including `CLAIMS_OUTDATED` when the residual findings are still all in the
correctable scope). Do not insert the field if it is absent; inserting it remains
`--check` mode's responsibility (2.5).

### 4.5 Append Session Log Entries

After updating each issue file, use the Bash tool to append a session log entry:

```bash
ll-issues append-log <path-to-issue-file> /ll:verify-issues
```

If `ll-issues` is not available, fall back to manually appending with **exactly** this format (backticks required):

```
- `/ll:verify-issues` - YYYY-MM-DDTHH:MM:SS - `<absolute path to session JSONL>`
```

Append it under the existing `## Session Log` heading if one exists; create the
heading only when none does, immediately above the `---`/`## Status` footer (or at
end of file if no footer exists). Never add a second `## Session Log` heading —
doing so orphans every entry recorded under the earlier one (BUG-3424).

### 5. Output Report

```markdown
# Issue Verification Report

## Summary
- **Graph**: provider=`<provider>` freshness=`<freshness>` (omit this line entirely if the provider was unavailable and §2B.0 fell back silently)
- **Citations (B8)**: examined N / demoted N / surfaced N / advisory N (omit this line entirely if B8 fell back silently)
- **Issues checked**: X
- **Valid**: N
- **Outdated**: N
- **Resolved**: N
- **Invalid**: N
- **Needs Update**: N

## Results by Issue

### Valid Issues
| Issue ID | Title | Notes |
|----------|-------|-------|
| BUG-001 | Title | Verified accurate |

### Outdated Issues
| Issue ID | Title | What Changed |
|----------|-------|--------------|
| ENH-002 | Title | File moved to new location |

### Resolved Issues
| Issue ID | Title | Resolution |
|----------|-------|------------|
| BUG-003 | Title | Fixed in commit abc123 |

### Invalid Issues
| Issue ID | Title | Problem |
|----------|-------|---------|
| FEAT-004 | Title | Described behavior is incorrect |

### Needs Update
| Issue ID | Title | Action Needed |
|----------|-------|---------------|
| ENH-005 | Title | Update line numbers |

### Potential Regressions
| Issue ID | Matched Completed | Classification | Evidence |
|----------|-------------------|----------------|----------|
| BUG-006 | BUG-003 | REGRESSION | Files modified after fix: `src/module.py` |
| ENH-007 | ENH-002 | INVALID_FIX | Files unchanged since fix - fix never worked |
| BUG-008 | BUG-001 | UNVERIFIED | No fix commit tracked |

### Dependency Issues
| Issue ID | Problem | Details |
|----------|---------|---------|
| [ID] | BROKEN_REF | References nonexistent [REF-ID] |
| [ID] | MISSING_BACKLINK | Blocked by [REF-ID], but [REF-ID] has no Blocks entry for [ID] |
| [IDs] | CYCLE | Circular dependency detected |

## Recommended Actions
1. Close resolved issues by setting `status: done` in frontmatter
2. Update outdated issues with current info
3. Remove or archive invalid issues
4. Re-prioritize if needed
5. Review potential regressions - reopen completed issues with proper classification
6. Fix dependency issues - remove broken refs, add missing backlinks, resolve cycles
```

---

## Arguments

$ARGUMENTS

- **issue_id** (optional): Specific issue ID to verify
  - If provided, verifies only that specific issue
  - If omitted, verifies all active issues (open, in_progress, blocked); deferred, done, and cancelled issues are skipped

- **flags** (optional): Command behavior flags
  - `--auto` - Non-interactive mode: apply all non-destructive changes (verification notes, line number updates) without prompting. Skips setting resolved issue status (requires explicit approval).
  - `--check` — Check-only mode for FSM loop evaluators. Run verification without applying changes, print `[ID] verify: [verdict]` per non-VALID issue, exit 1 if any non-VALID, exit 0 if all valid. Implies `--auto`.
  - `--from-evidence` (BUG-3637) — Non-check mode only. Read the target issue's `verify_evidence` frontmatter field and re-check/correct only the claims it lists, skipping the full 2A-2E sweep; no-op (no edits) when `verify_evidence` is absent or empty. Used by `refine-to-ready-issue.yaml`'s `correct_claims` state to repair a `CLAIMS_OUTDATED` verdict without a second full verify session.

---

## Examples

```bash
# Verify all active issues (open, in_progress, blocked) — deferred, done, cancelled are skipped
/ll:verify-issues

# Verify a specific issue
/ll:verify-issues BUG-042

# Non-interactive mode (for FSM loop actions)
/ll:verify-issues --auto

# Verify a specific issue non-interactively
/ll:verify-issues BUG-042 --auto

# Check-only mode for FSM loop evaluators (exit 0 if all pass, exit 1 if any fail)
/ll:verify-issues --check
/ll:verify-issues BUG-042 --check

# Targeted correction of a CLAIMS_OUTDATED verdict's flagged claims only
/ll:verify-issues BUG-042 --auto --from-evidence

# After verification, process resolved issues
/ll:manage-issue bug fix RESOLVED-ISSUE-ID

# Update issues that need correction
# Then commit: /ll:commit
```

---

## Integration

Works well with:
- `/ll:scan-codebase` - Find new issues after verification
- `/ll:prioritize-issues` - Re-prioritize after verification
- `/ll:manage-issue` - Process verified issues
