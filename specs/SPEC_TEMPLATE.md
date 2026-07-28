# [Project Name]

## Overview
<!-- 2-4 sentences: what the project does and why it exists. -->

## Core Features
<!-- Bulleted list of top-level capabilities. Each bullet becomes a candidate
     feature issue after scope-epic runs. Aim for 5-15 features. -->

## Data Model (optional)
<!-- Key entities and relationships if known. rn-build will derive these from
     the Overview + Core Features if omitted. -->

## Non-Goals
<!-- What this project explicitly does NOT do. Prevents scope creep during
     rn-implement. -->

## Tech Constraints (optional)
<!-- Required languages, platforms, or libraries. rn-build picks the stack
     autonomously if omitted. -->

## Acceptance Criteria
<!-- High-level observable outcomes. At least 2-3 concrete scenarios.

     rn-build consumes this section TWICE:
       1. eval_harness  — configures the generated eval harness loop.
       2. derive_acceptance_checks (FEAT-2414) — turns each criterion into a
          RUNNABLE check that is executed against the assembled, running project
          after every feature is built. The results are scored by a non-LLM gate;
          a build whose criteria do not all hold terminates `acceptance_failed`.

     Because criteria are executed, write each one as a single observable,
     mechanically checkable outcome — something a command can decide:

       GOOD: "GET /api/todos returns 200 with a JSON array of todo objects"
       GOOD: "`todo add \"buy milk\"` exits 0 and the item appears in `todo list`"
       POOR: "The API is well designed and easy to use"   (not checkable)
       POOR: "Everything works end to end"                (not a single outcome)

     A criterion that genuinely cannot be mechanized is marked skipped and
     excluded from scoring — but a spec whose criteria are ALL unrunnable
     scores 0 and fails the gate. -->
