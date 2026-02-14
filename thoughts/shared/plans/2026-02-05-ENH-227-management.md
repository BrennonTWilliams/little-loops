# ENH-227: Add GitHub Sync Setup to Init Wizard - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-227-add-github-sync-setup-to-init-wizard.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: implement

## Current State Analysis

### Key Discoveries
- The sync configuration schema is **fully defined** in `config-schema.json:593-647` with `sync.enabled`, `sync.provider`, `sync.github.*` properties
- The Python dataclasses (`SyncConfig`, `GitHubSyncConfig`) are **fully implemented** in `scripts/little_loops/config.py:305-346`
- The `/ll:sync-issues` command (`commands/sync_issues.md`) and skill (`skills/sync-issues/SKILL.md`) are **fully operational**
- The `/ll:init` wizard (`commands/init.md`) has **no sync question** - it has Rounds 1-9 covering project, issues, features, product, advanced, documents, extended config
- The `/ll:configure` command (`commands/configure.md`) is **missing the `sync` area** from its area mapping table (lines 41-52) and has no sync interactive configuration section

### Patterns to Follow
- **Init Features Round pattern** (`init.md:333-347`): Round 3 multi-select for parallel processing and context monitoring
- **Init Product Analysis pattern** (`init.md:351-487`): Yes/No opt-in with conditional sub-rounds
- **Configure Area pattern** (`configure.md:728-780`): Current values display → Round 1 questions → config update
- **Configure Area Mapping** (`configure.md:41-52`): Simple table mapping argument → config section → description

## Desired End State

1. `/ll:init` wizard includes a GitHub sync question in the Features Selection round (Round 3)
2. If enabled, conditional follow-up questions in Dynamic Round 5 for sync-specific settings
3. `sync` section written to `ll-config.json` with sensible defaults when enabled
4. `/ll:configure` supports `sync` area for interactive editing
5. Summary output includes `[SYNC]` section when enabled

### How to Verify
- Read `commands/init.md` and confirm sync question exists in Round 3
- Read `commands/init.md` and confirm conditional sync settings in Round 5
- Read `commands/init.md` and confirm sync in summary output and config writing
- Read `commands/configure.md` and confirm sync in area mapping table
- Read `commands/configure.md` and confirm sync `--show` output
- Read `commands/configure.md` and confirm sync interactive configuration section
- Read `commands/configure.md` and confirm sync in area selection menus

## What We're NOT Doing

- Not modifying Python code (config.py, sync.py, cli.py) - already complete
- Not modifying the sync command or skill - already functional
- Not modifying templates/*.json - sync is opt-in and disabled by default
- Not adding tests - these are command definition files (markdown), not executable code
- Not auditing all issue commands for sync.enabled checks - the sync feature works independently

## Solution Approach

Add sync to the init wizard as a Feature Selection option (following the parallel/context monitoring pattern) with conditional follow-up questions. Add sync as a new configuration area in the configure command following existing area patterns.

## Implementation Phases

### Phase 1: Update Init Wizard - Features Selection (Round 3)

#### Overview
Add "GitHub sync" as an option in the Features multi-select question.

#### Changes Required

**File**: `commands/init.md`
**Changes**: Add "GitHub sync" option to the Features Selection multi-select in Step 5c (Round 3)

At line ~341, add a third option to the features multi-select:

```yaml
- label: "GitHub sync"
  description: "Sync issues with GitHub Issues via /ll:sync-issues"
```

#### Success Criteria

**Automated Verification**:
- [ ] `grep -c "GitHub sync" commands/init.md` returns at least 1

---

### Phase 2: Update Init Wizard - Conditional Sync Settings (Round 5)

#### Overview
Add conditional sync configuration questions to the Dynamic Round 5, triggered when user selects "GitHub sync" in Round 3.

#### Changes Required

**File**: `commands/init.md`

1. **Update Round 5 conditions** (around line 492-498): Add condition for GitHub sync selection
2. **Add sync questions** to Step 5e Dynamic Round 5 (around line 500): Add conditional questions for sync settings (sync_completed, priority_labels)
3. **Add configuration mapping** after Round 5 questions: Map responses to sync config section

Add these conditional questions:

```yaml
# ONLY include if user selected "GitHub sync" in Round 3:
- header: "Priority Labels"
  question: "Add priority levels (P0-P5) as GitHub labels when syncing?"
  options:
    - label: "Yes (Recommended)"
      description: "Map P0-P5 to GitHub labels for filtering"
    - label: "No"
      description: "Don't add priority labels to GitHub Issues"
  multiSelect: false

# ONLY include if user selected "GitHub sync" in Round 3:
- header: "Sync Completed"
  question: "Sync completed issues to GitHub (close them)?"
  options:
    - label: "No (Recommended)"
      description: "Only sync active issues"
    - label: "Yes"
      description: "Also close completed issues on GitHub"
  multiSelect: false
```

And the configuration mapping:

```json
{
  "sync": {
    "enabled": true,
    "github": {
      "priority_labels": true,
      "sync_completed": false
    }
  }
}
```

Only include non-default values (priority_labels defaults to true, sync_completed defaults to false).

#### Success Criteria

**Automated Verification**:
- [ ] `grep -c "GitHub sync" commands/init.md` returns at least 3 (feature option + 2 conditionals)
- [ ] `grep -c "sync_completed" commands/init.md` returns at least 1

---

### Phase 3: Update Init Wizard - Summary & Config Writing

#### Overview
Add sync section to the summary display and config writing rules.

#### Changes Required

**File**: `commands/init.md`

1. **Summary section** (around line 928-954): Add `[SYNC]` block after `[CONTEXT MONITOR]`

```
  [SYNC]                                # Only show if enabled
  sync.enabled: true
  sync.github.priority_labels: [true/false]
  sync.github.sync_completed: [true/false]
```

2. **Interactive Mode Summary table** (around line 871): Update Round 3 description and Round 5 conditions

3. **Config writing rules** (around line 994-1001): Add sync omission rule

```
- Omit `sync` section entirely if user did not select "GitHub sync" (disabled is the default)
- Only include `sync.github.priority_labels` if false (true is default)
- Only include `sync.github.sync_completed` if true (false is default)
```

4. **Completion message** (around line 1039): Add sync next step

```
  6. Sync with GitHub: /ll:sync-issues push   # Only show if sync enabled
```

#### Success Criteria

**Automated Verification**:
- [ ] `grep -c "\[SYNC\]" commands/init.md` returns at least 1
- [ ] `grep -c "sync_issues" commands/init.md` returns at least 1

---

### Phase 4: Update Configure Command - Area Mapping & Show

#### Overview
Add `sync` to the configure command's area mapping table and `--show` output.

#### Changes Required

**File**: `commands/configure.md`

1. **Area Mapping Table** (line 52): Add sync row after workflow

```markdown
| `sync` | `sync` | GitHub Issues sync: enabled, label mapping, priorities |
```

2. **Description argument** (line 5): Update argument description to include sync

3. **--show output** (after line 244, before "Stop here"): Add sync show section

```markdown
#### sync --show

```
Sync Configuration
------------------
  enabled:          {{config.sync.enabled}}                       (default: false)
  provider:         {{config.sync.provider}}                      (default: github)
  GitHub:
    repo:           {{config.sync.github.repo}}                   (default: auto-detect)
    label_mapping:  {{config.sync.github.label_mapping}}          (default: BUG→bug, FEAT→enhancement, ENH→enhancement)
    priority_labels: {{config.sync.github.priority_labels}}       (default: true)
    sync_completed: {{config.sync.github.sync_completed}}         (default: false)

Edit: /ll:configure sync
```
```

3. **--list output** (around line 76): Add sync to the list

```
  sync          [DEFAULT]     GitHub Issues sync: enabled, label mapping, priorities
```

#### Success Criteria

**Automated Verification**:
- [ ] `grep -c "sync" commands/configure.md` returns at least 10

---

### Phase 5: Update Configure Command - Interactive Flow & Area Selection

#### Overview
Add the sync interactive configuration section and update area selection menus.

#### Changes Required

**File**: `commands/configure.md`

1. **Area selection menus** (lines 280-330): Add `sync` to the "More areas..." chain. Move it to the second page alongside parallel, automation, documents.

2. **Interactive configuration section** (after workflow area, before Step 3): Add full sync area section:

```markdown
## Area: sync

### Current Values

```
Current Sync Configuration
--------------------------
  enabled:          {{config.sync.enabled}}
  provider:         {{config.sync.provider}}
  repo:             {{config.sync.github.repo}}
  label_mapping:    {{config.sync.github.label_mapping}}
  priority_labels:  {{config.sync.github.priority_labels}}
  sync_completed:   {{config.sync.github.sync_completed}}
```

### Round 1 (4 questions)

```yaml
questions:
  - header: "Enable"
    question: "Enable GitHub Issues synchronization?"
    options:
      - label: "{{current enabled}} (keep)"
        description: "Keep current setting"
      - label: "true"
        description: "Yes, sync with GitHub"
      - label: "false"
        description: "No, disable (default)"
    multiSelect: false

  - header: "Repository"
    question: "GitHub repository (owner/repo format)?"
    options:
      - label: "{{current repo}} (keep)"
        description: "Keep current setting"
      - label: "Auto-detect"
        description: "Detect from git remote (default)"
    multiSelect: false

  - header: "Priority Labels"
    question: "Add priority as GitHub labels (P0-P5)?"
    options:
      - label: "{{current priority_labels}} (keep)"
        description: "Keep current setting"
      - label: "true"
        description: "Yes, add priority labels (default)"
      - label: "false"
        description: "No, omit priority labels"
    multiSelect: false

  - header: "Sync Completed"
    question: "Sync completed issues to GitHub (close them)?"
    options:
      - label: "{{current sync_completed}} (keep)"
        description: "Keep current setting"
      - label: "false"
        description: "No, active only (default)"
      - label: "true"
        description: "Yes, also close completed"
    multiSelect: false
```
```

#### Success Criteria

**Automated Verification**:
- [ ] `grep -c "Area: sync" commands/configure.md` returns 1
- [ ] `grep -c "sync_completed" commands/configure.md` returns at least 2

---

## Testing Strategy

### Manual Verification
- Run `/ll:init --interactive` and verify the GitHub sync question appears in Round 3
- Run `/ll:configure sync --show` and verify sync configuration display
- Run `/ll:configure --list` and verify sync appears in the list
- Run `/ll:configure sync` and verify interactive questions work

## References

- Issue: `.issues/enhancements/P3-ENH-227-add-github-sync-setup-to-init-wizard.md`
- Init wizard: `commands/init.md`
- Configure command: `commands/configure.md`
- Config schema sync section: `config-schema.json:593-647`
- Existing sync command: `commands/sync_issues.md`
- Existing sync skill: `skills/sync-issues/SKILL.md`
