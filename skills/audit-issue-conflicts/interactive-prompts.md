# Interactive Mode — AskUserQuestion Templates

Companion reference for `SKILL.md` Phase 4 "Interactive Mode (default)". For each
conflict, present an `AskUserQuestion` prompt with options shaped by the
recommendation type.

**merge / deprecate** conflicts:

```yaml
questions:
  - question: "[SEVERITY] conflict: [ISSUE-A] vs [ISSUE-B] — [description]. Apply recommendation?"
    header: "[ISSUE-A] vs [ISSUE-B]"
    multiSelect: false
    options:
      - label: "Yes, apply — [proposed_change summary]"
        description: "[specific action, e.g., merge scope into ISSUE-A, close ISSUE-B]"
      - label: "No, keep both as-is"
        description: "Leave both issues unchanged"
      - label: "Add dependency instead"
        description: "Add blocked_by frontmatter to link them without closing either"
```

**add_dependency** conflicts:

```yaml
questions:
  - question: "Add dependency link: [ISSUE-A] should depend on [ISSUE-B]. Which field?"
    header: "[ISSUE-A]"
    multiSelect: false
    options:
      - label: "blocked_by (hard stop)"
        description: "Appends blocked_by: [ISSUE-B] to [ISSUE-A] frontmatter — ISSUE-B must complete before ISSUE-A can start (wave-gated)"
      - label: "depends_on (soft ordering)"
        description: "Appends depends_on: [ISSUE-B] to [ISSUE-A] frontmatter — wave-gated ordering (ISSUE-A scheduled after ISSUE-B) but non-fatal if ISSUE-B is absent"
      - label: "No, skip"
        description: "Leave both issues unchanged"
```

**split / update_scope** conflicts:

```yaml
questions:
  - question: "Scope overlap: [ISSUE-A] vs [ISSUE-B] — [description]. Add scope note?"
    header: "[ISSUE-A] vs [ISSUE-B]"
    multiSelect: false
    options:
      - label: "Yes, append scope clarification note"
        description: "Adds a ## Scope Boundary note to each issue clarifying their split"
      - label: "No, keep as-is"
        description: "Leave both issues unchanged"
```
