---
discovered_commit: c5005eb
discovered_branch: main
discovered_date: 2026-02-06T22:30:00Z
discovered_by: audit_docs
doc_file: README.md, ARCHITECTURE.md, CONTRIBUTING.md
---

# ENH-265: Automated Documentation Count Verification

## Summary

Documentation issue found by `/ll:audit_docs`. The project lacks automated verification for counts (commands, agents, skills) leading to potential drift between documented numbers and actual files.

## Location

- **File**: `README.md`, `ARCHITECTURE.md`, `CONTRIBUTING.md`
- **Section**: Overview/Quick Start sections

## Current Content

Documentation manually states counts like:
- "34 slash commands"
- "8 specialized agents"
- "6 skills"

These counts are hard-coded and can become outdated as files are added/removed.

## Problem

No automated way to verify that documented counts match actual files. The recent audit found:
- README.md: Correct (34 commands)
- ARCHITECTURE.md: Was outdated (stated 33, now fixed to 34)

## Expected Content

Add automated count verification that:
1. Counts actual files in `commands/`, `agents/`, `skills/`
2. Validates counts against documentation
3. Fails CI if counts don't match
4. Provides update command to fix discrepancies

## Implementation Suggestion

```bash
# scripts/verify-doc-counts.sh
#!/bin/bash
COMMAND_COUNT=$(find commands -name "*.md" -type f | wc -l)
AGENT_COUNT=$(find agents -name "*.md" -type f 2>/dev/null | wc -l)
SKILL_COUNT=$(find skills -name "SKILL.md" -type f 2>/dev/null | wc -l)

echo "Commands: $COMMAND_COUNT"
echo "Agents: $AGENT_COUNT"
echo "Skills: $SKILL_COUNT"
```

Add to CI:
```yaml
- name: Verify documentation counts
  run: ./scripts/verify-doc-counts.sh
```

## Impact

- **Severity**: Low (informational)
- **Effort**: Small
- **Risk**: Low

## Labels

`enhancement`, `documentation`, `developer-experience`

---

## Status

**Open** | Created: 2026-02-06 | Priority: P4
