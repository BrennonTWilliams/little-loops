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
arguments:
  - name: issue_id
    description: Optional specific issue ID to verify
    required: false
  - name: flags
    description: "Optional flags: --auto (non-interactive, apply all non-destructive changes without prompting)"
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
(`scripts/little_loops/issues/program_design.py:406-427`) and extra text breaks the
Program Design gate's arming.

#### B. Verify Against Codebase
1. **Check files exist**: Do referenced files still exist?
2. **Verify line numbers**: Has the code moved or changed?
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
   - **AC coverage of identified integration points**: do the issue's Acceptance
     Criteria cover every integration point already listed in its Integration Map
     (including points `wire_issue` found)? A point with no corresponding AC is a
     gap this check must surface.

   This is judgment over consequences, not a claim to corroborate — read the
   Proposed Solution's diff-shape against the current code the same way an
   implementer would before writing it, not the way checks 1-4 read the issue's
   prose against the code.

   **Verdict**: any finding above → `PROPOSAL_UNSOUND` (§C). If checks 1-4 *also*
   find a claim about current state to be false, the claim-verdict wins
   (`OUTDATED`/`INVALID`/`NEEDS_UPDATE`/etc.) — the existing `refine_followup`
   remedy repairs the research the proposal check itself depends on, so it must
   run first. Only assign `PROPOSAL_UNSOUND` when every claim about current state
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
| PROPOSAL_UNSOUND | The Proposed Solution, implemented as written, contradicts the code it names (check B6) — a claim-verification defect, not a claim, so it is not remedied by `refine_followup` |
| EVIDENCE_UNVERIFIED | A quoted evidence span attributed to a named artifact (check B7) exists in no revision of that artifact — outranks `PROPOSAL_UNSOUND` when both apply |

#### E. Validate Dependency References

For each issue, check dependency integrity:

1. **Blocked By references**: For each ID in `## Blocked By`:
   - Verify the referenced issue exists (in active issues or completed)
   - If in completed: note as "satisfied" (informational, not an error)
   - If missing entirely: flag as BROKEN_REF

2. **Blocks backlinks**: For each ID in `## Blocked By`:
   - Check that the referenced issue has this issue in its `## Blocks` section
   - If missing: flag as MISSING_BACKLINK

3. **Cycle check**: After processing all issues, build a dependency graph and check for cycles

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
`verify_issue` → `check_verify_verdict` pair) read a persisted artifact
instead. For **each** issue checked in this mode, use the `Edit` tool to write
or update a `verify_verdict:` line in that issue's YAML frontmatter block:

- `VALID` verdict → `verify_verdict: VALID`
- `EVIDENCE_UNVERIFIED` verdict (BUG-3282, check B7) → `verify_verdict:
  EVIDENCE_UNVERIFIED` — persisted as its own value, **not** collapsed into
  `NON_VALID`, so the `check_evidence_unverified` gate in
  `refine-to-ready-issue.yaml` can read it. **Outranks `PROPOSAL_UNSOUND`**: an
  issue can satisfy both, and the fabricated premise must be named before the
  proposal built on top of it is rewritten, or the rewrite re-derives the
  fiction. It still counts as a non-VALID, `exit 1` outcome in `--check` mode
  below — the split is in the persisted value, not the exit-code contract.

  **Advisory, not routing (fallback F3, decided 2026-08-21).** The verdict is
  detected, persisted, and reported, but `check_evidence_unverified` does *not*
  divert the loop to `reconcile_issue` — every edge falls through to
  `check_proposal_unsound`. The detector measured ~0.13–0.20 precision on a
  hand-labelled 30-finding sample against a 0.30 blocking bar; the residual is
  the *paraphrase* class (spans quoting real code inexactly), which no
  attribution or span-kind rule reaches. Below 0.30 a false verdict sends a
  **correct** issue into a rewrite, so routing is net-negative even when the
  gate is right. Re-arm — restore `on_yes: check_reconcile_limit` — only once
  precision is measured ≥ 0.30 with recall still 1.00 on labelled true
  fabrications.
- `PROPOSAL_UNSOUND` verdict (ENH-3250, check B6) → `verify_verdict:
  PROPOSAL_UNSOUND` — persisted as its own value, **not** collapsed into
  `NON_VALID`, so `check_proposal_unsound` in `refine-to-ready-issue.yaml` can
  route it to `reconcile_issue` instead of `refine_followup`. It still counts
  as a non-VALID, `exit 1` outcome in `--check` mode below — the split is in
  the persisted value, not the exit-code contract. Only assigned when the
  issue does not also qualify for `EVIDENCE_UNVERIFIED` above.
- Any other verdict (`OUTDATED`, `RESOLVED`, `INVALID`, `NEEDS_UPDATE`,
  `REGRESSION_LIKELY`, `POSSIBLE_REGRESSION`, `DEP_ISSUES`,
  `DECISIONS_VIOLATION`) → `verify_verdict: NON_VALID`

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
- Add a `## Verification Notes` section
- Document what changed or needs correction
- Update file paths and line numbers if moved

For resolved issues:
- Add resolution note
- Consider setting `status: done` in frontmatter

### 4.5 Append Session Log Entries

After updating each issue file, use the Bash tool to append a session log entry:

```bash
ll-issues append-log <path-to-issue-file> /ll:verify-issues
```

If `ll-issues` is not available, fall back to manually appending with **exactly** this format (backticks required):

```
- `/ll:verify-issues` - YYYY-MM-DDTHH:MM:SS - `<absolute path to session JSONL>`
```

### 5. Output Report

```markdown
# Issue Verification Report

## Summary
- **Graph**: provider=`<provider>` freshness=`<freshness>` (omit this line entirely if the provider was unavailable and §2B.0 fell back silently)
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
