# Issue Template Guide (v2.0)

**Last Updated**: 2026-02-10
**Template Version**: 2.0 (Optimized for AI Implementation)

## Overview

The little-loops issue template has been optimized to maximize value for both AI agents during implementation and human reviewers. Version 2.0 reduces cognitive overhead by **removing 8 low-value sections** and **adding 4 high-impact sections** that appear in best-practice issues.

**Key Changes**:
- 21 sections → 20 sections (-5%)
- Enhanced AI implementation guidance
- Anchor-based code references (no more line number drift)
- Integration Map to identify all affected files/components
- High-level Implementation Steps (agents expand into detailed plans)
- Consolidated redundant sections

## Quick Reference

### Common Sections (All Issue Types)

| Section | Required | AI Usage | Purpose |
|---------|----------|----------|---------|
| **Summary** | ✓ | HIGH | One-sentence what/why |
| **Current Behavior** | ✓ | HIGH | What happens now |
| **Expected Behavior** | ✓ | HIGH | What should happen |
| **Motivation** | | MEDIUM | Why this matters (NEW v2.0) |
| **Proposed Solution** | | HIGH | HOW to fix with code examples |
| **Integration Map** | | HIGH | All affected files/components (NEW v2.0) |
| **Implementation Steps** | | HIGH | High-level outline (NEW v2.0) |
| **Impact** | ✓ | HIGH | Priority/Effort/Risk with justifications |
| **Related Key Documentation** | | LOW | Links to docs |
| **Labels** | ✓ | MEDIUM | Categorization |
| **Status** | ✓ | HIGH | Status footer |

### Type-Specific Sections

**BUG**: Steps to Reproduce, Actual Behavior, Root Cause (NEW), Error Messages, Location
**FEAT**: Use Case (renamed from User Story), Acceptance Criteria, API/Interface (NEW)
**ENH**: Success Metrics, Scope Boundaries

### Deprecated Sections (Still Supported)

Context, Current Pain Point, Environment, Frequency, UI/UX Details, Data/API Impact, Edge Cases, Backwards Compatibility

> **Note**: Deprecated sections are still parsed for backward compatibility but should not be used in new issues.

---

## Section Details

### Summary
**Required for all types | AI Usage: HIGH**

One-sentence description combining WHAT and WHY.

**Good**:
- BUG: "Sprint runner crashes when processing issues with merge conflicts, blocking automated workflows"
- FEAT: "Add user authentication to protect admin endpoints"
- ENH: "Add retry logic to sprint runner to handle transient failures"

**Bad**:
- "Fix the bug" (no context)
- "Implement user authentication using OAuth 2.0 with JWT tokens and refresh token rotation" (too detailed)

---

### Current Behavior
**Required for all types | AI Usage: HIGH**

Describe what currently happens. Be specific and concrete.

**Example (BUG)**:
```markdown
## Current Behavior

When `ll-sprint run` encounters an issue with merge conflicts:
1. The orchestrator processes the issue
2. Merge fails with `MERGE_FAILED` status
3. Issue is marked as failed
4. Sprint continues with remaining issues
5. Failed issue is not retried
```

**Example (FEAT)**:
```markdown
## Current Behavior

Admin endpoints (`/admin/*`) are publicly accessible. Any user can:
- View all user data
- Modify system settings
- Delete content
```

---

### Expected Behavior
**Required for all types | AI Usage: HIGH**

Describe what should happen instead.

**Example (BUG)**:
```markdown
## Expected Behavior

After initial processing completes, failed issues should be:
1. Identified from `orchestrator.queue.failed_ids`
2. Retried sequentially using existing safe processing path
3. Updated in sprint state with retry results
```

---

### Motivation ⭐ NEW
**Optional for all types | AI Usage: MEDIUM | Human Value: HIGH**

Explain WHY this issue matters. Quantify impact where possible.

**Good Examples**:
```markdown
## Motivation

Sprint reliability is currently 60%. This enhancement would:
- Increase reliability to >90% by handling transient failures
- Save ~2 hours/week in manual reprocessing
- Enable unattended overnight sprint runs
```

```markdown
## Motivation

Public admin endpoints represent a critical security vulnerability affecting all users. Current production deployment is at risk until this is addressed.
```

**Bad Example**:
```markdown
## Motivation

This would be better.
```

**Replaces**: "Current Pain Point" (ENH only) → now all issue types can express motivation

---

### Proposed Solution
**Optional for all types | AI Usage: HIGH | Human Value: HIGH**

Suggested approach with **code examples** and **anchor-based references**.

**Key Guidelines**:
- ✅ Use anchor-based references (function/class names)
- ❌ Avoid line numbers (they drift)
- ✅ Include code examples or pseudocode
- ✅ Reference existing utilities to reuse
- ✅ Provide 2-3 approaches if multiple options exist

**Example (with anchors)**:
```markdown
## Proposed Solution

Add retry logic in `sprint_runner.py`:

**Location**: `_cmd_sprint_run()`, after the `orchestrator.run()` block

```python
# After orchestrator completes
failed_ids = set(orchestrator.queue.failed_ids)
if failed_ids:
    for issue in wave:
        if issue.issue_id in failed_ids:
            retry_result = process_issue_inplace(issue, config, logger)
```

**Reuse**: Existing `process_issue_inplace()` from `issue_manager.py` (function anchor: `def process_issue_inplace`)

**Alternative**: Could use `IssueOrchestrator` retry mode, but sequential retry is simpler and reuses tested code path.
```

**Bad Example (line numbers)**:
```markdown
## Proposed Solution

In sprint_runner.py at line 1847, add the retry code.
```
> ❌ Line 1847 will drift as code changes

---

### Integration Map ⭐ NEW
**Optional for all types | AI Usage: HIGH | Human Value: HIGH**

Comprehensive enumeration of all files, components, and systems affected by this change. **Critical for preventing isolated changes that break other parts of the codebase.**

**Purpose**: Answer the question "What else needs to change?" before writing code.

**Structure**:
```markdown
## Integration Map

### Files to Modify
- `path/to/main_file.py` - Primary change location
- `path/to/related_file.py` - Related changes needed

### Dependent Files (Callers/Importers)
- `path/to/caller1.py` - Imports `function_name()`, needs update
- `path/to/caller2.py` - Calls `ClassName`, verify compatibility
- _Use `grep -r "function_name" .` to find all references_

### Similar Patterns
- `path/to/similar1.py` - Uses same pattern, update for consistency
- `path/to/similar2.py` - Similar logic, consider refactoring together
- _Search for similar code to keep codebase consistent_

### Tests
- `tests/test_main.py` - Update existing tests
- `tests/test_integration.py` - Add integration tests for callers
- _Ensure test coverage for all affected components_

### Documentation
- `docs/API.md` - Update function signature documentation
- `README.md` - Update usage examples if public API changed
- _Keep documentation in sync with code changes_

### Configuration
- `config/settings.yaml` - Update defaults/options
- `constants.py` - Update related constants
- N/A - No configuration changes needed
```

**Quality Guidelines**:
- ✅ Use grep/search to find ALL callers/importers (don't guess)
- ✅ Identify similar patterns for consistency
- ✅ List EVERY test file that needs updates
- ✅ Include docs that reference changed behavior
- ✅ Note config files, even if "no change" (shows you considered it)
- ✅ Use "N/A" for categories with no changes (don't leave blank or "TBD")
- ❌ Don't leave as "TBD - requires investigation" in final issue

**Example (BUG)**:
```markdown
## Integration Map

### Files to Modify
- `auth/token_validator.py` - Add expiry check in `validate_token()`

### Dependent Files (Callers/Importers)
- `api/middleware/auth_middleware.py` - Handle new `TokenExpiredError`
- `api/routes/admin.py` - Catch `TokenExpiredError`
- `api/routes/user.py` - Catch `TokenExpiredError`
- `services/background_tasks.py` - Validate tokens for async jobs
- _Found via: `grep -r "validate_token" api/ services/`_

### Similar Patterns
- `auth/refresh_token_validator.py` - Has SAME bug, fix here too
- `auth/api_key_validator.py` - Different pattern, verify expiry logic
- _Pattern: `grep -r "jwt.decode" auth/` found similar validators_

### Tests
- `tests/auth/test_token_validator.py` - Add test for expired tokens
- `tests/api/test_auth_middleware.py` - Test TokenExpiredError handling
- `tests/integration/test_admin_routes.py` - Test admin rejects expired
- `tests/integration/test_user_routes.py` - Test user rejects expired

### Documentation
- `docs/API.md` - Document TokenExpiredError in auth section
- `docs/SECURITY.md` - Update security practices
- `README.md` - N/A (internal change)

### Configuration
- `config/security.yaml` - Consider adding `token_expiry_buffer_seconds`
- N/A - No constant changes needed
```

**Example (FEAT)**:
```markdown
## Integration Map

### Files to Modify
- `services/user_service.py` - Add `@cache_with_redis` decorator
- `utils/cache.py` - Create cache decorator (NEW FILE)

### Dependent Files (Callers/Importers)
- `api/routes/user.py` - No changes (caching transparent)
- `api/routes/admin.py` - No changes (caching transparent)
- `services/notification_service.py` - No changes
- _Found via: `grep -r "get_user_profile" .`_

### Cache Invalidation Points (CRITICAL)
- `services/user_service.py:update_user_profile()` - Invalidate cache
- `services/user_service.py:delete_user()` - Invalidate cache
- `admin/bulk_operations.py:bulk_update_users()` - Invalidate cache
- _Every write operation needs cache invalidation!_

### Similar Patterns
- `services/org_service.py` - Should add caching (same pattern)
- `services/team_service.py` - Should add caching (same pattern)
- _Opportunity: Apply pattern consistently_

### Tests
- `tests/services/test_user_service.py` - Add cache hit/miss tests
- `tests/utils/test_cache.py` - Test cache decorator (NEW)
- `tests/integration/test_cache_invalidation.py` - Critical! (NEW)

### Documentation
- `docs/ARCHITECTURE.md` - Add caching layer to architecture diagram
- `docs/CACHING.md` - Document caching strategy (NEW)
- `README.md` - Add Redis to installation instructions

### Configuration
- `config/cache.yaml` - Redis connection settings (NEW)
- `docker-compose.yml` - Add Redis service
- `.env.example` - Add REDIS_URL example
```

**Why This Section Matters**:

Common failure pattern WITHOUT Integration Map:
```
Fix auth.py → Deploy → Breaks API routes → Breaks background jobs →
Stale tests pass → Docs outdated → Users confused
```

Success pattern WITH Integration Map:
```
Identify all 4 callers → Fix all 4 → Update all 4 tests →
Update docs → Complete change → No breakage
```

**Pro tip**: If you find yourself saying "I'll just fix this one file", you're missing integration points. Use grep to be sure.

---

### Implementation Steps ⭐ NEW
**Optional for all types | AI Usage: HIGH | Human Value: MEDIUM**

High-level outline that guides the implementation agent. Keep it to 3-8 major phases.

**Important**: This is NOT a replacement for the detailed implementation plan that `/ll:manage_issue` creates. Think of it as an outline the agent will expand.

**Good Example (High-Level)**:
```markdown
## Implementation Steps

1. Add retry logic after orchestrator completes
2. Identify failed issues and retry sequentially
3. Update sprint state with retry results
4. Add tests for retry behavior
```

**Bad Example (Too Detailed)**:
```markdown
## Implementation Steps

1. In sprint_runner.py, locate the _cmd_sprint_run() function at line 1847
2. After the orchestrator.run() call, insert a new code block
3. Call orchestrator.queue.failed_ids to get the set of failed IDs
4. Create a for loop that iterates over the wave variable
5. Inside the loop, check if issue.issue_id is in the failed_ids set
6. If true, call process_issue_inplace() with parameters: issue, config, logger
7. Capture the return value in a variable called retry_result
... (12 more steps)
```
> ❌ Too granular - this is what the agent creates during planning

---

### Impact
**Required for all types | AI Usage: HIGH | Human Value: HIGH**

Priority, effort, and risk assessment **with justifications**.

**New Format (v2.0)**:
```markdown
## Impact

- **Priority**: P2 - Blocks sprint reliability; affects daily workflow
- **Effort**: Small-Medium - Reuses existing `process_issue_inplace()`, adds ~15 LOC
- **Risk**: Low - Sequential retry uses existing safe code path, no concurrency concerns
- **Breaking Change**: No
```

**Quality Guidelines**:
- ✅ Justify priority: Why P0? Why P2? What's the urgency?
- ✅ Justify effort: Reuses code? New patterns? Estimated LOC?
- ✅ Justify risk: Breaking change? Well-tested path? Edge cases?

**Bad Example**:
```markdown
## Impact

- **Priority**: P2
- **Effort**: Medium
- **Risk**: Low
```
> ❌ No justifications

---

### Root Cause ⭐ NEW (BUG only)
**Conditional for BUG | AI Usage: HIGH | Human Value: HIGH**

Identify WHERE and WHY the bug occurs using anchor-based references.

**Format**:
```markdown
## Root Cause

- **File**: `scripts/little_loops/sprint_runner.py`
- **Anchor**: `in function _cmd_sprint_run()`, after orchestrator execution
- **Cause**: Orchestrator marks issues as failed but doesn't trigger retry. The function returns after first processing pass without checking for retryable failures.
```

**Quality Guidelines**:
- ✅ Use function/class anchors, not line numbers
- ✅ Explain WHY the bug happens (logic error, missing check, race condition, etc.)
- ✅ Reference specific code patterns or control flow

---

### API/Interface ⭐ NEW (FEAT/ENH)
**Conditional for FEAT/ENH | AI Usage: HIGH | Human Value: MEDIUM**

Document public API contracts, interface changes, or CLI arguments.

**Example (Function Signature)**:
```markdown
## API/Interface

```python
def authenticate_user(username: str, password: str) -> AuthToken:
    """Authenticate user and return session token.

    Args:
        username: User's login name
        password: User's password (will be hashed)

    Returns:
        AuthToken with expiry and permissions

    Raises:
        AuthenticationError: If credentials are invalid
    """
```

**Example (CLI Change)**:
```markdown
## API/Interface

New CLI flag for `ll-sprint`:

```bash
ll-sprint run --retry-failed
```

- **Flag**: `--retry-failed` / `-r`
- **Type**: boolean (default: false)
- **Behavior**: Retry failed issues sequentially after initial processing
- **Breaking Change**: No (opt-in flag)
```

**Consolidates**: "Data/API Impact" (deprecated)

---

### Use Case (FEAT only) - Renamed from "User Story"
**Required for FEAT | AI Usage: HIGH | Human Value: HIGH**

Describe a **concrete scenario** showing who uses this and what they achieve.

**Good Example**:
```markdown
## Use Case

**Who**: DevOps engineer running overnight sprint processing

**Context**: They've configured a sprint with 50 issues and want to run it unattended overnight.

**Goal**: When transient failures occur (network timeouts, temporary merge conflicts), the sprint should automatically retry failed issues instead of requiring manual intervention the next morning.

**Outcome**: Sprint completes with 95%+ success rate, failed issues are logged for review, and engineer has actionable results in the morning.
```

**Bad Example**:
```markdown
## Use Case

As a user, I want the sprint to retry failures so that I don't have to manually reprocess.
```
> ❌ Generic template, no concrete context

---

## Quality Checks

### All Issues
- [ ] Impact includes justifications for priority, effort, and risk
- [ ] Proposed Solution uses anchor-based references (function/class names) not line numbers
- [ ] Implementation Steps (if present) are high-level outline, not detailed plan
- [ ] Summary is one sentence combining WHAT and WHY

### BUG-Specific
- [ ] Steps to Reproduce has numbered concrete steps (not "do the thing")
- [ ] Expected vs Actual describe different specific behaviors (not just "it should work")
- [ ] Error messages include actual error text, not just "there's an error"
- [ ] Root Cause identifies file + function anchor + explanation (not just "investigate")

### FEAT-Specific
- [ ] Use Case describes a concrete scenario with context, not a generic template
- [ ] Acceptance Criteria are individually testable with clear pass/fail
- [ ] API/Interface documents signatures/schemas if introducing public contracts
- [ ] Proposed Solution includes code examples or pseudocode

### ENH-Specific
- [ ] Motivation explains WHY with quantified impact where possible
- [ ] Success Metrics have numeric targets or clear before/after comparison
- [ ] Scope Boundaries list specific exclusions, not just "keep it simple"
- [ ] Proposed Solution references existing utilities/patterns to reuse

---

## Migration Guide

### For New Issues

Use `/ll:capture_issue` or `/ll:refine_issue` - they automatically use the v2.0 template.

### For Existing Issues

Existing issues continue to work without changes. Deprecated sections are still parsed.

To upgrade an existing issue to v2.0:
1. Run `/ll:refine_issue <issue-file>` - it will offer to add new sections
2. Manually migrate:
   - Add "Motivation" if you had "Current Pain Point" (ENH)
   - Add "Implementation Steps" if you want to guide the agent
   - Add "Root Cause" if you know where/why the bug occurs (BUG)
   - Rename "User Story" to "Use Case" and enhance with concrete scenario (FEAT)
   - Replace line numbers in "Proposed Solution" with function/class anchors
   - Add justifications to "Impact" section

---

## Examples

### Complete BUG Issue (v2.0)

```markdown
# BUG: Sprint runner doesn't retry failed issues

## Summary

Sprint runner marks issues as failed but doesn't retry them, requiring manual reprocessing and reducing automation reliability.

## Current Behavior

When `ll-sprint run` encounters an issue with merge conflicts or transient errors:
1. The orchestrator processes the issue
2. Issue fails with `MERGE_FAILED` or error status
3. Issue is marked as failed in sprint state
4. Sprint continues with remaining issues
5. Failed issue is never retried

## Expected Behavior

After initial processing completes:
1. Failed issues are identified from `orchestrator.queue.failed_ids`
2. Each failed issue is retried sequentially
3. Sprint state is updated with retry results
4. Final summary shows original failures vs retry successes

## Motivation

Sprint reliability is currently 60% due to transient merge conflicts. This enhancement would:
- Increase reliability to >90% by handling transient failures
- Save ~2 hours/week in manual reprocessing
- Enable unattended overnight sprint runs

## Root Cause

- **File**: `scripts/little_loops/sprint_runner.py`
- **Anchor**: `in function _cmd_sprint_run()`, after orchestrator execution
- **Cause**: Orchestrator marks issues as failed but doesn't trigger retry. Function returns after first processing pass without checking for retryable failures.

## Proposed Solution

Add retry logic in `sprint_runner.py`:

**Location**: `_cmd_sprint_run()`, after the `orchestrator.run()` block

```python
# After orchestrator completes
failed_ids = set(orchestrator.queue.failed_ids)
if failed_ids:
    logger.info(f"Retrying {len(failed_ids)} failed issues sequentially...")
    for issue in wave:
        if issue.issue_id in failed_ids:
            retry_result = process_issue_inplace(issue, config, logger)
            # Update sprint state with retry result
```

**Reuse**: Existing `process_issue_inplace()` from `issue_manager.py`

## Integration Map

### Files to Modify
- `scripts/little_loops/sprint_runner.py` - Add retry logic in `_cmd_sprint_run()`

### Dependent Files (Callers/Importers)
- N/A - Sprint runner is top-level command, no callers in codebase

### Similar Patterns
- `scripts/little_loops/cli.py` - Consider adding retry to `ll-auto` as well
- _Pattern: Sequential processing of issues appears in multiple commands_

### Tests
- `scripts/tests/test_sprint.py` - Add test for retry behavior after failures
- `scripts/tests/integration/test_sprint_reliability.py` - Integration test (NEW)

### Documentation
- `docs/CLI-TOOLS-AUDIT.md` - Update ll-sprint capabilities
- `README.md` - Update ll-sprint feature list

### Configuration
- N/A - No configuration changes needed

## Implementation Steps

1. Add retry logic after orchestrator completes
2. Identify failed issues and retry sequentially
3. Update sprint state with retry results
4. Add tests for retry behavior

## Steps to Reproduce

1. Create a sprint with an issue that has merge conflicts
2. Run `ll-sprint run sprint-name`
3. Observe orchestrator fails the issue
4. Check sprint state - issue marked as failed, no retry

## Actual Behavior

Issue is marked as failed, sprint continues, no retry occurs.

## Impact

- **Priority**: P2 - Blocks sprint reliability; affects daily workflow
- **Effort**: Small-Medium - Reuses existing function, adds ~15 LOC
- **Risk**: Low - Sequential retry uses existing safe code path
- **Breaking Change**: No

## Labels

`bug`, `sprint`, `reliability`

## Status

**Open** | Created: 2026-02-10 | Priority: P2
```

### Complete FEAT Issue (v2.0)

```markdown
# FEAT: Add user authentication to admin endpoints

## Summary

Add authentication to admin endpoints to prevent unauthorized access to sensitive operations.

## Current Behavior

Admin endpoints (`/admin/*`) are publicly accessible without authentication.

## Expected Behavior

Admin endpoints require valid authentication token. Unauthorized requests return 401.

## Motivation

Public admin endpoints represent a critical security vulnerability. Current production deployment is at risk until this is addressed. Affects all users (potential data breach).

## Use Case

**Who**: System administrator managing user accounts

**Context**: Admin needs to access user management dashboard to ban a spam account. They should authenticate with their admin credentials before accessing sensitive operations.

**Goal**: Securely access admin dashboard, verify identity, perform user management tasks.

**Outcome**: Only authenticated admins can access sensitive endpoints. Audit log records who performed what action.

## Proposed Solution

Add JWT-based authentication:

1. **Auth middleware**: Create `auth_middleware.py` (see `existing_middleware.py` for pattern)
2. **Token validation**: Reuse existing `verify_jwt_token()` from `auth_utils.py`
3. **Protected routes**: Apply `@require_auth` decorator to admin endpoints

```python
from functools import wraps
from auth_utils import verify_jwt_token

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token or not verify_jwt_token(token):
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated

@app.route('/admin/users')
@require_auth
def admin_users():
    # existing logic
```

## Integration Map

### Files to Modify
- `api/middleware/auth_middleware.py` - Create auth middleware (NEW FILE)
- `api/routes/admin.py` - Apply `@require_auth` decorator
- `api/routes/users.py` - Apply decorator to user management routes

### Dependent Files (Callers/Importers)
- All admin route handlers - Need to import and apply decorator
- _Found via: `grep -r "@app.route('/admin" api/`_

### Similar Patterns
- `api/middleware/rate_limit.py` - Similar decorator pattern, reuse structure
- Other protected routes - Consider applying consistent auth pattern

### Tests
- `tests/api/test_auth_middleware.py` - Test middleware functionality (NEW)
- `tests/api/test_admin_routes.py` - Update to include auth token in requests
- `tests/api/test_users_routes.py` - Update to test auth rejection
- `tests/integration/test_admin_security.py` - End-to-end security test (NEW)

### Documentation
- `docs/API.md` - Document authentication requirements
- `docs/SECURITY.md` - Add authentication section
- `README.md` - Update setup instructions for JWT configuration

### Configuration
- `config/auth.yaml` - Add JWT secret and token settings (NEW)
- `.env.example` - Add JWT_SECRET example
- `docker-compose.yml` - No changes needed

## Implementation Steps

1. Create authentication middleware
2. Add JWT token verification
3. Apply @require_auth decorator to admin routes
4. Add authentication tests
5. Update API documentation

## Acceptance Criteria

- [ ] All `/admin/*` endpoints require valid JWT token
- [ ] Requests without token return 401 Unauthorized
- [ ] Requests with invalid token return 401 Unauthorized
- [ ] Requests with valid token proceed normally
- [ ] Audit log records authenticated admin actions

## API/Interface

**Protected Endpoints**:
```
GET  /admin/users     - Requires: Bearer token
POST /admin/users/:id - Requires: Bearer token + admin role
DELETE /admin/content - Requires: Bearer token + admin role
```

**Authentication Header**:
```
Authorization: Bearer <jwt-token>
```

**Error Response**:
```json
{
  "error": "Unauthorized",
  "message": "Valid authentication token required"
}
```

## Impact

- **Priority**: P0 - Critical security vulnerability in production
- **Effort**: Small - Reuses existing JWT utilities, adds decorator pattern (~50 LOC)
- **Risk**: Medium - Changes authentication flow, requires careful testing
- **Breaking Change**: Yes - Clients must include auth token (migration plan needed)

## Labels

`feature`, `security`, `authentication`, `breaking-change`

## Status

**Open** | Created: 2026-02-10 | Priority: P0
```

---

## Template Variants

### Full Template (v2.0)
Includes all non-deprecated sections. Use for important issues.

**Sections**: Summary, Current Behavior, Expected Behavior, Motivation, Proposed Solution, Implementation Steps, Impact, Related Key Documentation, Labels, Status + type-specific sections

### Minimal Template
Core sections only. Use for quick captures that will be refined later.

**Sections**: Summary, Current Behavior, Expected Behavior, Impact, Status

### Legacy Template
Backward compatible with v1.0. Includes deprecated sections.

**Use only if**: You need to maintain exact compatibility with old tooling

---

## Best Practices

### For AI Implementation
1. **Use anchors, not line numbers**: `in function foo()` not `at line 42`
2. **Show code examples**: Agents work better with concrete examples
3. **Reference existing patterns**: Point to code to reuse
4. **High-level steps**: Let the agent create the detailed plan

### For Human Reviewers
1. **Quantify impact**: "affects 100 users" not "affects users"
2. **Concrete scenarios**: Show real use cases, not templates
3. **Justify decisions**: Why P0? Why high effort?
4. **Link docs**: Help reviewers find context quickly

### For Issue Quality
1. **PASS /ll:ready_issue**: Auto-validation catches common issues
2. **Use /ll:refine_issue**: Interactive Q&A improves quality
3. **Include Motivation**: Helps prioritization and buy-in
4. **Write Implementation Steps**: Guides the agent, speeds implementation

---

## FAQ

**Q: Are old issues still valid?**
A: Yes. Deprecated sections are still parsed for backward compatibility.

**Q: Should I migrate all existing issues?**
A: No. Only migrate when actively working on them. `/ll:refine_issue` offers optional migration.

**Q: What happened to "User Story"?**
A: Renamed to "Use Case" to encourage concrete scenarios over generic templates.

**Q: Why remove "Context"?**
A: 0% usage by agents during implementation. Keep it in "Related Key Documentation" if needed.

**Q: Difference between "Implementation Steps" and agent's implementation plan?**
A: Implementation Steps = high-level outline (3-8 phases). Agent's plan = detailed execution (20+ steps with code). Think: outline vs full plan.

**Q: When to use "Root Cause" vs "Location"?**
A: Both! "Location" = where (file/line/code from scan). "Root Cause" = why (explanation of the bug logic).

---

## Related Documentation

- [CONTRIBUTING.md](../CONTRIBUTING.md) - Issue creation workflow
- [API.md](./API.md) - Python module reference for issue parsing
- [ARCHITECTURE.md](./ARCHITECTURE.md) - System design and issue lifecycle
