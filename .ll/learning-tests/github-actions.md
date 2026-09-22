---
target: GitHub Actions
date: '2026-09-22'
status: proven
assertions:
- claim: a workflow run's conclusion field is null while status != "completed",
    and non-null once status == "completed"
  result: pass
- claim: runs triggered by a push to main report event == "push" in the API response
  result: pass
- claim: when a newer run supersedes an in-progress run on the same concurrency
    group, the older run's conclusion becomes "cancelled"
  result: pass
- claim: within a single run, the conformance job's started_at is >= the unit-tests
    job's completed_at (needs serialization is enforced at the job level, not just
    declared in YAML)
  result: pass
- claim: artifacts uploaded via actions/upload-artifact@v4 are visible via GET /repos/{owner}/{repo}/actions/artifacts
    with a non-null expires_at reflecting the configured retention-days
  result: pass
raw_output_path: .ll/learning-tests/raw/github-actions.txt
---
