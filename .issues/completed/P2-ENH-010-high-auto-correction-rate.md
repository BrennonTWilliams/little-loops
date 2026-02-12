---
discovered_commit: 64342c8
discovered_date: 2026-01-09
discovered_source: ll-parallel-blender-agents-debug.log
discovered_external_repo: <external-repo>
---

# ENH-010: Issue quality: high auto-correction rate indicates scan accuracy issues

## Summary

During parallel processing, 7 out of 17 completed issues (41%) required auto-correction during validation. This high rate suggests that issue scanning and creation is producing inaccurate or incomplete issues that need to be corrected downstream.

## Evidence from Log

**Log File**: `ll-parallel-blender-agents-debug.log`
**Log Type**: ll-parallel
**Target Repo**: `<external-repo>`
**Occurrences**: 7
**Affected External Issues**: BUG-549, ENH-550, BUG-552, BUG-546, ENH-542, BUG-543, ENH-527

**Log File Location** (check in order):
1. Little-loops repo: `ll-parallel-blender-agents-debug.log`
2. Target repo: `<external-repo>/ll-parallel-blender-agents-debug.log`

Note: ll-parallel logs are typically created in the directory where the command is run (usually little-loops), not in the target repository being processed.

### Sample Log Output

```
[15:35:56] BUG-549 was auto-corrected during validation
[15:46:39] ENH-550 was auto-corrected during validation
[16:04:15] BUG-552 was auto-corrected during validation
[16:05:36] BUG-546 was auto-corrected during validation
[16:15:35] ENH-542 was auto-corrected during validation
[16:24:48] BUG-543 was auto-corrected during validation
[16:27:20] ENH-527 was auto-corrected during validation
```

## Current Behavior

- Issues created by scan commands often have inaccuracies
- These are detected and corrected during the validation phase of manage_issue
- Auto-correction adds processing time and may not catch all issues
- 41% auto-correction rate suggests systematic problems

## Expected Behavior

- Issues created by scan should be accurate enough to pass validation without correction
- Target auto-correction rate should be under 10%
- Common correction patterns should be fed back into scan logic

## Potential Causes

1. **Scan prompts** may be asking for information that's difficult to determine accurately
2. **Issue templates** may have fields that are often mis-specified
3. **Validation rules** may be stricter than scan prompts account for
4. **Code analysis** during scan may be insufficient to accurately characterize issues

## Proposed Investigation

1. Analyze what types of corrections are being made (priority, description, files, etc.)
2. Review scan command prompts and templates
3. Compare scan output with validation expectations
4. Consider adding a "confidence score" to scanned issues

## Proposed Improvements

1. Add logging of what specifically was auto-corrected
2. Track auto-correction patterns over time
3. Feed correction patterns back into scan prompts
4. Consider a validation pass during scan before creating issues

## Impact

- **Severity**: Low (P2) - Not blocking, but indicates quality issue
- **Frequency**: 7 occurrences (41% of completed issues)
- **Data Risk**: Low - corrections handle the issue, but add latency

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-09
- **Status**: Completed

### Changes Made

1. **commands/scan_codebase.md**: Added "Reproduction Steps" section to issue template (lines 182-188) to align with ready_issue validation requirements. Also updated bug scanner prompt to request reproduction steps.

2. **scripts/little_loops/state.py**: Extended ProcessingState dataclass with `corrections` field to persist auto-correction data for pattern analysis.

3. **scripts/little_loops/issue_manager.py**: Updated to store corrections in state via `record_corrections()` method, and added correction statistics to processing summary output.

4. **scripts/tests/test_state.py**: Added comprehensive tests for corrections persistence and `record_corrections()` method.

### Verification Results
- Tests: 477 PASS
- Lint: PASS
- Types: PASS

### Root Cause
The primary mismatch was between scan_codebase template (missing "Reproduction Steps") and ready_issue validation (requiring it for bugs). Every bug issue was auto-corrected to add the missing section.

### Impact
- Prevention: Future scanned bugs will include reproduction steps, reducing auto-correction rate
- Tracking: Corrections are now persisted for pattern analysis to enable continuous improvement

---

## Reopened

- **Date**: 2026-01-11
- **By**: /analyze_log
- **Reason**: Issue recurred with higher rate despite previous fix

### New Evidence

**Log File**: `ll-parallel-blender-agents-debug.log`
**External Repo**: `<external-repo>`
**Occurrences**: 5 out of 9 completed issues (56%)
**Affected External Issues**: ENH-617, ENH-618, ENH-620, ENH-629, ENH-630

```
[22:11:33] ENH-617 was auto-corrected during validation
[22:24:24] ENH-618 was auto-corrected during validation
[22:27:14] ENH-620 was auto-corrected during validation
[22:38:53] ENH-629 was auto-corrected during validation
[22:45:08] ENH-630 was auto-corrected during validation
```

### Analysis

The previous fix addressed BUG issues (adding "Reproduction Steps" to scan_codebase template). However, this run processed only ENH (enhancement) issues, and the auto-correction rate increased to 56% (up from 41%).

**Key observations**:
1. All auto-corrected issues are enhancements (ENH), not bugs
2. The previous fix targeted bug-specific fields ("Reproduction Steps")
3. Enhancement issues may have different validation requirements not addressed

**Possible root causes**:
1. Enhancement template may be missing fields that ready_issue expects
2. The corrections tracking was added but no action taken on the patterns
3. Different validation rules for enhancements vs bugs

**Next steps**:
1. Analyze the logged corrections to identify what fields are being corrected for ENH issues
2. Update scan_codebase template for enhancement-specific requirements
3. Review ready_issue validation rules for enhancements

---

## Resolution (Second Fix)

- **Action**: improve
- **Completed**: 2026-01-12
- **Status**: Completed

### Changes Made

1. **commands/scan_codebase.md** (lines 103-110): Updated Enhancement Scanner prompt to request complete information:
   - Added "Current behavior (what the code does now)"
   - Added "Expected behavior (what the code should do after improvement)"
   - Added "Proposed solution (suggested approach to implement the enhancement)"
   - Changed from only requesting "Brief explanation of the improvement"

2. **commands/scan_codebase.md** (lines 194-196): Renamed template section from "Proposed Fix" to "Proposed Solution" to align with ready_issue validation terminology ("Proposed solution/approach").

### Verification Results
- Tests: 486 PASS
- Lint: PASS
- Types: PASS

### Root Cause
The Enhancement Scanner prompt only asked for "Brief explanation of the improvement", but the issue template and ready_issue validation expected detailed Current Behavior, Expected Behavior, and Proposed Solution sections. The mismatch caused ready_issue to auto-correct nearly every enhancement issue.

### Impact
- Prevention: Future scanned enhancements will include all required fields, reducing auto-correction rate
- Consistency: Template section heading now matches ready_issue validation terminology

---

## Status
**Reopened** | Created: 2026-01-09 | Reopened: 2026-01-11, 2026-01-12 | Fixed: 2026-01-12 | Priority: P2

---

## Reopened (Third Time)

- **Date**: 2026-01-12
- **By**: /analyze_log
- **Reason**: Auto-correction rate still at 33% despite second fix

### New Evidence

**Log File**: `ll-parallel-blender-agents-debug.log`
**External Repo**: `<external-repo>`
**Occurrences**: 3 out of 9 completed issues (33%)
**Affected External Issues**: BUG-643, ENH-625, ENH-639

```
[12:38:39] BUG-643 was auto-corrected during validation
[12:38:43] ENH-625 was auto-corrected during validation
[12:53:17] ENH-639 was auto-corrected during validation
```

### Analysis

The second fix added enhancement-specific fields to the scan template. The auto-correction rate has decreased from 56% (previous run) to 33% (this run), showing improvement but not reaching the target of under 10%.

**Key observations**:
1. Both BUG and ENH issues are still being auto-corrected
2. The improvement shows the previous fix had partial effect
3. Additional patterns are still causing corrections

**Possible remaining causes**:
1. Specific field content quality (not just presence)
2. Priority mismatches between scan estimation and validation
3. File location accuracy in scanned issues
4. Other validation rules not yet addressed

### Proposed Investigation

1. Review the corrections tracking data to identify specific fields being corrected
2. Compare the BUG-643, ENH-625, ENH-639 issues before/after correction
3. Identify patterns in what specifically is being auto-corrected
4. Consider adding validation-like checks during scan to catch issues earlier

---

## Resolution (Third Fix)

- **Action**: improve
- **Completed**: 2026-01-12
- **Status**: Completed

### Root Cause Analysis

Investigation of completed issues (BUG-643, ENH-625, ENH-639) revealed corrections were primarily about **code reference accuracy** - file paths, line numbers, and structural clarity. The scan sub-agents were finding issues but not verifying the accuracy of file paths and code references before reporting.

Additionally, **parallel processing was not capturing correction details** to state, making pattern analysis impossible. Sequential processing logged corrections but parallel only logged "was auto-corrected" without specifics.

### Changes Made

**Phase 1: Add corrections tracking to parallel processing**

1. **scripts/little_loops/parallel/types.py**:
   - Added `corrections: list[str]` field to `WorkerResult` dataclass (line 84)
   - Updated `to_dict()` and `from_dict()` to serialize/deserialize corrections (lines 103, 124)
   - Added `corrections: dict[str, list[str]]` field to `OrchestratorState` (line 193)
   - Updated state serialization/deserialization (lines 205, 219)

2. **scripts/little_loops/parallel/worker_pool.py**:
   - Extract corrections list from `ready_parsed` output (line 284)
   - Pass corrections to `WorkerResult` (line 360)

3. **scripts/little_loops/parallel/orchestrator.py**:
   - Log correction details when issue is auto-corrected (lines 488-492)
   - Store corrections in orchestrator state for pattern analysis (lines 489-492)
   - Added correction statistics summary to final report (lines 596-617)

**Phase 2: Add reference verification to scanner prompts**

4. **commands/scan_codebase.md**:
   - Added verification instructions to Bug Scanner (lines 89-93)
   - Added verification instructions to Enhancement Scanner (lines 118-122)
   - Added verification instructions to Feature Scanner (lines 144-148)

   Each scanner now includes:
   ```
   IMPORTANT: Before reporting each finding, VERIFY:
   - File paths exist (use Read tool to confirm)
   - Line numbers are accurate (check the actual file)
   - [Type-specific verifications]
   Only report VERIFIED findings with accurate references.
   ```

**Phase 3: Tests**

5. **scripts/tests/test_worker_pool.py**:
   - Added `test_process_issue_captures_corrections` (lines 1130-1175)

6. **scripts/tests/test_orchestrator.py**:
   - Updated `test_on_worker_complete_corrected` to verify corrections storage (lines 793-816)
   - Added `test_load_state_resumes_corrections` (lines 432-457)

### Verification Results
- Tests: 499 PASS
- Lint: PASS
- Types: PASS

### Impact

1. **Observability**: Parallel processing now captures and logs detailed corrections, enabling pattern analysis
2. **Prevention**: Scanner prompts now instruct sub-agents to verify code references before reporting
3. **Pattern Analysis**: Correction statistics are displayed in summary, with most common correction types shown
4. **Data Persistence**: Corrections are persisted in state file, surviving session restarts

### Expected Outcome

Future scan runs should produce more accurate issues with verified code references, reducing the auto-correction rate. The correction tracking enables continuous improvement by revealing which types of corrections occur most frequently.

---

## Status
**Reopened** | Created: 2026-01-09 | Reopened: 2026-01-11, 2026-01-12 (twice), 2026-01-13 | Priority: P2

---

## Reopened (Fourth Time)

- **Date**: 2026-01-13
- **By**: /analyze_log
- **Reason**: Auto-correction rate spiked to 73% despite third fix

### New Evidence

**Log File**: `ll-parallel-blender-agents-debug.log`
**External Repo**: `<external-repo>`
**Occurrences**: 11 out of 15 completed issues (73%)
**Affected External Issues**: ENH-691, ENH-706, BUG-699, ENH-692, ENH-693, ENH-698, ENH-697, ENH-702, ENH-703, ENH-704, ENH-705

```
[16:29:11] ENH-691 was auto-corrected during validation
[16:42:17] ENH-706 was auto-corrected during validation
[16:54:28] BUG-699 was auto-corrected during validation
  Correction: Updated "Files to Modify" section to clarify that:
  Correction: The issue affects generated specfiles from character workflow templates
  Correction: The specific instance was found at `.blender-agents/585f7626-d9f1-46cd-ac1a-dfdc72e67929/specfile.yaml`
  Correction: The verification expressions with typos are NOT in the template code
  Correction: The typos appear to be introduced during specfile generation or manual editing
[17:03:33] ENH-692 was auto-corrected during validation
  Correction: All 3 prescriptive criteria still exist in CHARACTER_CREATION_TEMPLATE
  Correction: Noted that CHARACTER_CREATION_SCULPT has corrected clothing offset
  Correction: Clarified P1-ENH-701 only fixed metaball template, not main template
  Correction: Changed `character_creation_v1.yaml` to `workflow_templates.py`
  Correction: Updated line numbers: 110→479, 187→673, 55→349
[17:08:02] ENH-693 was auto-corrected during validation
[17:17:21] ENH-698 was auto-corrected during validation
[17:19:49] ENH-697 was auto-corrected during validation
[17:28:57] ENH-702 was auto-corrected during validation
  Correction: Updated related issue references to reflect that P2-BUG-699 and P1-ENH-696 are in completed directory
[17:31:54] ENH-703 was auto-corrected during validation
  Correction: Updated **Verification Notes** section to:
  Correction: Confirm both criteria still exist in the referenced workflow specfile (lines 150, 180)
  Correction: Clarify that ENH-692 addressed **templates**, not individual workflow specfiles
  Correction: Explain this issue provides a **general solution** for quality judgment detection across all workflows
[17:37:05] ENH-704 was auto-corrected during validation
  Correction: Line 206: `name: hair_creation` ✓
  Correction: Line 225: `technique_family: box_modeling` ✓
  Correction: Line 223: `create_sphere` is in operation_preferences ✓
  Correction: Contains: `create_cube`, `create_cylinder`, `add_boolean_modifier`, etc.
  Correction: Does NOT contain: `create_sphere` ✓
[17:41:49] ENH-705 was auto-corrected during validation
  Correction: Changed `src/blender_agents/capabilities/analysis_ops.py` → `src/blender_agents/capabilities/scene/scene_snapshot.py`
  Correction: Changed `tests/unit/capabilities/test_analysis_ops.py` → `tests/unit/capabilities/test_scene_snapshot.py`
  Correction: Noted that `SceneSnapshot.get_total_triangles()` already exists (lines 594-612)
  Correction: Noted that `SceneSnapshot.triangle_count` property already exists (lines 647-649)
  Correction: **P2-ENH-692**: Marked as (COMPLETED)
```

### Analysis

The third fix added reference verification instructions to scanner prompts. However, the auto-correction rate increased dramatically from 33% to 73%, suggesting:

1. **Corrections are now being logged in detail** (Phase 1 of third fix is working)
2. **Reference verification may not be effective** or is creating new patterns
3. **Correction types have shifted** from missing fields to content accuracy

**Correction pattern analysis from this run**:
- File path corrections (e.g., `analysis_ops.py` → `scene/scene_snapshot.py`)
- Line number updates (e.g., `110→479, 187→673`)
- Related issue status updates (marking issues as COMPLETED)
- Clarifications about which code artifacts are affected (templates vs specfiles)

**Key observations**:
1. Most corrections are about **code reference accuracy** and **related issue status**
2. The scanner creates issues that reference lines/files, but the codebase evolves during parallel processing
3. **Cross-issue dependencies**: Issues reference other issues that get completed during the same run

### Proposed Investigation

1. **Temporal drift**: Issues created at scan time may reference code that changes during parallel processing
2. **Related issue staleness**: Scanner snapshots related issue status at scan time, but status changes during run
3. **Line number volatility**: Line numbers drift as files are modified by other workers
4. **Scanner vs runtime mismatch**: Scanner prompts were updated but issues may have been created before the fix

### Proposed Solutions

1. **Lazy reference validation**: Validate code references just before implementation, not at scan time
2. **Relative line references**: Use function/class names instead of line numbers where possible
3. **Dynamic issue status**: Don't include related issue status in scanned issues; let validation resolve it
4. **Scanner version tracking**: Include scanner version in issues to detect pre-fix issues

---

## Resolution (Fourth Fix)

- **Action**: improve
- **Completed**: 2026-01-13
- **Status**: Completed

### Root Cause Analysis

The 73% correction rate analysis revealed that corrections were primarily about:
1. **Line number drift** (high frequency) - Code modified by other workers during parallel processing
2. **File path changes** (medium frequency) - Files renamed/moved during processing
3. **Related issue status stale** (medium frequency) - Issues completed during same run appear as "open"
4. **Content clarifications** (low frequency) - Scanner misunderstood code relationships

The core problem is **temporal drift** - the scanner captures state at scan time (T0) that becomes stale by validation time (T1) during parallel processing.

### Changes Made

**Phase 1: Add Stable Anchors to Scanner Prompts and Template**

1. **commands/scan_codebase.md** - Scanner Prompts (lines 84, 116, 148):
   - Added "Stable anchor (function name, class name, or unique nearby string that won't change)" to each scanner's return fields
   - Bug Scanner, Enhancement Scanner, and Feature Scanner now request stable anchors

2. **commands/scan_codebase.md** - Issue Template (lines 202-203):
   - Updated Location section to include commit hash with line numbers: `**Line(s)**: 42-45 (at scan commit: [COMMIT_HASH_SHORT])`
   - Added `**Anchor**` field for function/class names or unique markers

**Phase 2: Remove Related Issue Status from Scanned Issues**

3. **commands/scan_codebase.md** - Scanner Prompts (lines 90-91, 123-124, 153-154):
   - Added instruction to all scanners: "IMPORTANT: Do NOT include related issue IDs or their status in findings. Related issues will be resolved dynamically during validation."

**Phase 3: Update ready_issue to Use Anchors for Validation**

4. **commands/ready_issue.md** - Code References Section (lines 123-132):
   - Added "Anchor field present and valid" to validation checklist
   - Added "Using Stable Anchors for Validation" guidance for anchor-based line number correction

**Phase 4: Add Correction Classification**

5. **commands/ready_issue.md** - CORRECTIONS_MADE Section (lines 216-228):
   - Updated correction format to include category prefixes: `[line_drift]`, `[file_moved]`, `[content_fix]`, `[issue_status]`
   - Added documentation of correction categories

6. **scripts/little_loops/parallel/orchestrator.py** (lines 606-625):
   - Added category extraction from `[category]` prefix in corrections
   - Added "Corrections by type:" summary to final report showing breakdown by category
   - Preserved existing "Most common corrections:" report

7. **scripts/tests/test_output_parsing.py** (lines 223-245):
   - Added `test_corrected_verdict_with_categories` to verify categorized corrections are parsed correctly

8. **scripts/tests/test_orchestrator.py** (lines 845-872):
   - Added `test_on_worker_complete_categorized_corrections` to verify categorized corrections are stored properly

### Verification Results
- Tests: 736 PASS
- Lint: PASS
- Types: PASS

### Impact

1. **Stable Anchors**: Future scanned issues will include function/class names alongside line numbers, enabling ready_issue to correct line drift using anchor search
2. **No Related Issue Status**: Scanned issues won't include stale related issue status; validation will resolve dynamically
3. **Correction Categories**: Corrections are now categorized (`[line_drift]`, `[file_moved]`, `[content_fix]`, `[issue_status]`) enabling pattern analysis to identify remaining correction causes
4. **Category Statistics**: Parallel processing summary now shows correction breakdown by type for continuous improvement

### Expected Outcome

The categorized corrections will reveal which types of drift are most common, guiding future targeted fixes. The stable anchors provide a fallback for ready_issue to correct line numbers even when they drift during parallel processing.
