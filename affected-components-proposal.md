# Affected Components Section - Proposal

## Problem Statement

**Current Gap**: Issues are often implemented in isolation without properly identifying:
- Files that call/import the changed code
- Files with similar patterns that should be updated consistently
- Tests that need updates
- Documentation that needs updates
- Configuration files affected
- Integration points with other systems

**Impact**: Leads to:
- Broken callers/dependents after changes
- Inconsistent patterns across codebase
- Stale tests passing incorrectly
- Outdated documentation
- Missing configuration updates
- Integration failures

## Proposed Solution

Add **"Affected Components"** section to `common_sections` in the template.

### Section Definition

```json
{
  "Affected Components": {
    "required": false,
    "description": "Files, modules, and systems that interact with or depend on the changed code",
    "ai_usage": "HIGH",
    "human_value": "HIGH",
    "quality_guidance": [
      "Identify files that call/import the changed code (use grep/analysis)",
      "List files with similar patterns that should be updated consistently",
      "Enumerate test files that need updates or new tests",
      "Identify documentation files that reference this behavior",
      "Note configuration files, constants, or settings affected",
      "Consider integration points with external systems",
      "Think: what breaks if I change this in isolation?"
    ],
    "creation_template": "TBD - requires codebase analysis"
  }
}
```

### Template Structure

```markdown
## Affected Components

### Primary Changes
- `path/to/main_file.py` - [What changes here]
- `path/to/related_file.py` - [What changes here]

### Dependent Files (Callers/Importers)
- `path/to/caller1.py` - Imports `function_name()`, needs update to handle new behavior
- `path/to/caller2.py` - Calls `ClassName`, verify compatibility with changes
- _Use `grep -r "function_name" .` to find all references_

### Similar Patterns (Consistency)
- `path/to/similar1.py` - Uses same pattern, should be updated for consistency
- `path/to/similar2.py` - Similar logic, consider refactoring together
- _Search for similar code patterns to keep codebase consistent_

### Tests
- `tests/test_main.py` - Update existing tests for new behavior
- `tests/test_integration.py` - Add integration tests for affected callers
- _Ensure test coverage for all affected components_

### Documentation
- `docs/API.md` - Update function signature/behavior documentation
- `README.md` - Update usage examples if public API changed
- `CHANGELOG.md` - Document breaking changes
- _Keep documentation in sync with code changes_

### Configuration
- `config/settings.yaml` - Update default values/options
- `constants.py` - Update related constants
- _Configuration changes often forgotten_

### Integration Points
- External API calls that depend on this behavior
- Database schema if data models change
- Message queues/events if contract changes
- _Consider external dependencies_
```

## Example: BUG Issue with Full Integration Map

```markdown
# BUG-123: Token validation allows expired tokens

## Summary
Authentication middleware accepts expired JWT tokens due to missing expiry check.

## Root Cause
- **File**: `auth/token_validator.py`
- **Anchor**: `in function validate_token()`
- **Cause**: Function checks signature but skips expiry timestamp validation

## Proposed Solution

Fix in `auth/token_validator.py`, function `validate_token()`:

```python
def validate_token(token: str) -> bool:
    payload = jwt.decode(token, SECRET_KEY)

    # Add expiry check (MISSING)
    if datetime.now() > datetime.fromtimestamp(payload['exp']):
        raise TokenExpiredError()

    return True
```

## Affected Components

### Primary Changes
- `auth/token_validator.py` - Add expiry check in `validate_token()`

### Dependent Files (Callers/Importers)
- `api/middleware/auth_middleware.py` - Calls `validate_token()`, needs to handle TokenExpiredError
- `api/routes/admin.py` - Uses token validation, should catch new exception
- `api/routes/user.py` - Uses token validation, should catch new exception
- `services/background_tasks.py` - Validates tokens for async jobs
- _Found via: `grep -r "validate_token" api/ services/`_

### Similar Patterns (Consistency)
- `auth/refresh_token_validator.py` - Has SAME bug, should fix there too
- `auth/api_key_validator.py` - Different pattern but should verify expiry logic
- _Search pattern: `grep -r "jwt.decode" auth/` to find similar validators_

### Tests
- `tests/auth/test_token_validator.py` - Add test for expired tokens
- `tests/api/test_auth_middleware.py` - Update to expect TokenExpiredError
- `tests/integration/test_admin_routes.py` - Test admin endpoints reject expired tokens
- `tests/integration/test_user_routes.py` - Test user endpoints reject expired tokens
- _All 4 dependent files need corresponding test updates_

### Documentation
- `docs/API.md` - Document new TokenExpiredError in authentication section
- `docs/SECURITY.md` - Update security practices to note expiry validation
- `README.md` - No changes needed (internal implementation)

### Configuration
- `config/security.yaml` - Consider adding `token_expiry_buffer_seconds` setting
- `auth/constants.py` - No changes needed

### Integration Points
- Frontend clients - Need to handle 401 with "token_expired" error code
- Mobile apps - Same as frontend, update error handling
- Third-party integrations - Notify partners of stricter token validation
```

## Example: FEAT Issue with Full Integration Map

```markdown
# FEAT-456: Add user profile caching

## Summary
Add Redis caching for user profiles to reduce database load.

## Proposed Solution

Add caching layer in `user_service.py`:

```python
@cache_with_redis(ttl=300)
def get_user_profile(user_id: int) -> UserProfile:
    return db.query(UserProfile).filter_by(id=user_id).first()
```

## Affected Components

### Primary Changes
- `services/user_service.py` - Add `@cache_with_redis` decorator to `get_user_profile()`
- `utils/cache.py` - Create new `cache_with_redis()` decorator (NEW FILE)

### Dependent Files (Callers/Importers)
- `api/routes/user.py` - Calls `get_user_profile()`, no changes needed (transparent)
- `api/routes/admin.py` - Calls `get_user_profile()`, no changes needed
- `services/notification_service.py` - Calls `get_user_profile()`, no changes needed
- _Found via: `grep -r "get_user_profile" .`_

### Cache Invalidation Points
- `services/user_service.py:update_user_profile()` - Must invalidate cache after update
- `services/user_service.py:delete_user()` - Must invalidate cache after delete
- `admin/bulk_operations.py:bulk_update_users()` - Must invalidate cache
- _Critical: Every write operation needs cache invalidation!_

### Similar Patterns (Consistency)
- `services/org_service.py:get_organization()` - Should also add caching (same pattern)
- `services/team_service.py:get_team()` - Should also add caching (same pattern)
- _Opportunity: Apply caching pattern consistently across all read-heavy services_

### Tests
- `tests/services/test_user_service.py` - Add tests for cache hits/misses
- `tests/utils/test_cache.py` - Test cache decorator (NEW FILE)
- `tests/integration/test_user_cache_invalidation.py` - Test invalidation on updates (NEW FILE)
- _Need integration tests to verify cache invalidation works correctly_

### Documentation
- `docs/ARCHITECTURE.md` - Add caching layer to system architecture diagram
- `docs/CACHING.md` - Document caching strategy and invalidation rules (NEW FILE)
- `README.md` - Add Redis to installation/setup instructions

### Configuration
- `config/cache.yaml` - Add Redis connection settings (NEW FILE)
- `config/production.yaml` - Add Redis URL for production
- `docker-compose.yml` - Add Redis service
- `.env.example` - Add `REDIS_URL` example
- _Configuration is critical for new infrastructure dependency_

### Integration Points
- **Redis** - New infrastructure dependency, needs deployment planning
- **Monitoring** - Add Redis metrics to monitoring dashboard
- **Deployment** - Update deployment scripts to ensure Redis is available
- **Rollback plan** - Can disable caching via feature flag if issues arise
```

## Benefits of "Affected Components" Section

### For AI Agents
1. ✅ **Comprehensive change map** - Agent knows exactly what to modify
2. ✅ **Prevents isolated changes** - Forces consideration of callers/dependents
3. ✅ **Ensures consistency** - Identifies similar patterns to update together
4. ✅ **Test coverage** - Explicitly lists test files to update
5. ✅ **Integration awareness** - Considers external dependencies

### For Human Reviewers
1. ✅ **Completeness check** - Easy to verify all components addressed
2. ✅ **Risk assessment** - See scope of changes upfront
3. ✅ **Review focus** - Know which files to review carefully
4. ✅ **Deployment planning** - Identify infrastructure/config changes

## Implementation Approach

### Phase 1: Add Section to Template
1. Add "Affected Components" to `common_sections` in `templates/issue-sections.json`
2. Position after "Proposed Solution" and before "Implementation Steps"
3. Update creation variants to include in "full" template

### Phase 2: Update Commands
1. **capture-issue.md** - Add Affected Components to creation flow
2. **format-issue.md** - Add interactive questions for identifying affected files
3. **scan-codebase.md** - Auto-populate Affected Components using grep/analysis

### Phase 3: Add Tooling Support
1. Create helper function to find callers: `grep -r "function_name" .`
2. Create helper to find similar patterns: `grep -r "pattern" .`
3. Integration with codebase-locator agent to verify file existence

### Phase 4: Update Quality Checks
Add to `quality_checks`:

```json
"common": [
  "Affected Components should list callers/importers (use grep to find references)",
  "Affected Components should identify test files that need updates",
  "Affected Components should note documentation changes needed",
  "If API/Interface changes, Affected Components must list all callers"
]
```

## Quality Checklist for "Affected Components"

When reviewing this section:

- [ ] **Primary changes** - All files to modify listed
- [ ] **Callers found** - Used grep/analysis to find all references
- [ ] **Similar patterns** - Searched for consistent patterns to update together
- [ ] **Tests identified** - Every affected file has corresponding test update
- [ ] **Documentation** - All docs referencing changed behavior identified
- [ ] **Configuration** - Any settings/constants affected listed
- [ ] **Integration points** - External dependencies considered
- [ ] **Nothing says "TBD"** - All sections have specific file paths or "N/A - no changes needed"

## Alternative: Enhance Implementation Steps

Instead of new section, could enhance "Implementation Steps" to require integration enumeration:

```markdown
## Implementation Steps

1. **Primary changes**
   - Fix `auth/token_validator.py` to check token expiry

2. **Update dependent files**
   - `api/middleware/auth_middleware.py` - Handle TokenExpiredError
   - `api/routes/admin.py` - Catch new exception
   - `api/routes/user.py` - Catch new exception
   - `services/background_tasks.py` - Catch new exception

3. **Fix similar patterns**
   - `auth/refresh_token_validator.py` - Apply same fix

4. **Update tests**
   - `tests/auth/test_token_validator.py` - Test expired tokens
   - `tests/api/test_auth_middleware.py` - Test exception handling
   - `tests/integration/test_admin_routes.py` - Integration test
   - `tests/integration/test_user_routes.py` - Integration test

5. **Update documentation**
   - `docs/API.md` - Document TokenExpiredError
   - `docs/SECURITY.md` - Note expiry validation
```

**Pros**:
- Uses existing section
- More actionable (already in step format)

**Cons**:
- Mixes "what" (affected components) with "how" (implementation order)
- Harder to review completeness at a glance
- Implementation Steps should stay high-level per v2.0 design

## Recommendation

**Add "Affected Components" as new section** because:

1. ✅ Separates "what's affected" (analysis) from "how to implement" (execution)
2. ✅ Easier to review for completeness
3. ✅ Can be populated early (during capture/refine) before detailed implementation plan
4. ✅ Agents can use it as input to create detailed Implementation Steps
5. ✅ Clear checklist format for verification

Position in template:
```
1. Summary
2. Current Behavior
3. Expected Behavior
4. Motivation
5. Root Cause (BUG) / Use Case (FEAT)
6. Proposed Solution
7. **Affected Components** ← NEW
8. Implementation Steps
9. Impact
...
```

This ensures developers think about integration BEFORE writing code.
