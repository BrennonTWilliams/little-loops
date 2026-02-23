# ENH-466: Audit MCP configs across all scopes with env variable expansion validation

## Implementation Plan

**Created**: 2026-02-23
**Issue**: `.issues/enhancements/P3-ENH-466-audit-mcp-scope-and-env-expansion.md`
**Action**: implement

---

## Research Summary

### Current State

The audit-claude-config skill uses a three-wave architecture:
- **Wave 1 Task 3** (`codebase-locator`): Validates `.mcp.json` at project scope with 4 checks: server commands exist/executable, no duplicate names, env vars properly referenced, appropriate scope
- **Wave 1 Task 2** (`plugin-config-auditor`): Validates agent `mcpServers` frontmatter (has `command` field)
- **Wave 2 Task 2** (`consistency-checker`): Cross-references CLAUDE.md MCP tool mentions against `.mcp.json` servers
- **Report template**: MCP gets a single row in Config Files table + 5% health score weight

### Gaps to Address (from issue)

1. **Multi-scope MCP discovery**: Only `.mcp.json` checked; `~/.claude.json` user-scope, local-scope, and `managed-mcp.json` not discovered
2. **`${VAR}` expansion validation**: No syntax validation for `${VAR}` or `${VAR:-default}` in MCP config fields
3. **HTTP/SSE transport validation**: Only `stdio` transport checked (`command`/`args`); `http`/`sse` with `url`/`headers` not validated
4. **MCP approval settings cross-referencing**: `enableAllProjectMcpServers`, `enabledMcpjsonServers`, `disabledMcpjsonServers`, `allowedMcpServers`, `deniedMcpServers` not cross-referenced against actual servers
5. **Scope conflict detection**: Same server name at multiple scopes not flagged
6. **Report template**: No MCP scope breakdown section

### Files to Modify

1. `skills/audit-claude-config/SKILL.md` — Extend Wave 1 Task 3 MCP instructions; add Wave 2 MCP cross-references
2. `skills/audit-claude-config/report-template.md` — Add MCP scope breakdown section
3. `agents/plugin-config-auditor.md` — Add agent `mcpServers` HTTP/SSE validation
4. `agents/consistency-checker.md` — Add MCP approval settings cross-references; scope conflict detection

---

## Implementation Phases

### Phase 1: Extend Wave 1 Task 3 — Multi-scope MCP discovery + env var validation

**File**: `skills/audit-claude-config/SKILL.md`

**Changes at lines 238 and 333-337** (Task 3 Config Files Auditor prompt):

1. Expand the MCP config file list from:
   ```
   - .mcp.json or ~/.claude/.mcp.json
   ```
   To:
   ```
   - .mcp.json (project-scope MCP servers)
   - ~/.claude.json → mcpServers field (user-scope MCP servers)
   - ~/.claude.json → projects → <project-path> → mcpServers (local-scope MCP servers per project)
   - managed-mcp.json at managed settings directory (macOS: /Library/Application Support/ClaudeCode/managed-mcp.json, Linux: /etc/claude-code/managed-mcp.json)
   ```

2. Expand MCP-specific validation from 4 checks to comprehensive validation:
   ```
   For MCP config across ALL scopes:
   - Discover MCP configs at all scopes: project (.mcp.json), user (~/.claude.json mcpServers), local (~/.claude.json per-project mcpServers), managed (managed-mcp.json)
   - For stdio transport: server commands exist and are executable
   - For http/sse transport: url is well-formed (valid URL format), headers is object of string key-value pairs
   - No duplicate server names within a single scope
   - ${VAR} and ${VAR:-default} expansion syntax validation:
     - Scan command, args, env, url, headers fields for ${...} patterns
     - Validate syntax: ${VAR_NAME} or ${VAR_NAME:-default_value} (no nested expansions)
     - Warn (INFO) if referenced env var is not currently set in the environment
     - Flag malformed syntax as WARNING (e.g., ${}, ${VAR:-}, unclosed ${)
   - Record per-scope server inventory for Wave 2 (server name, scope, transport type)
   ```

3. Add to the Wave 1 Task 3 return list:
   ```
   - MCP server inventory per scope (server name, scope, transport type) for Wave 2
   - MCP env var expansion issues found for Wave 2
   ```

4. Update `~/.claude.json` entry at line 245 to note MCP extraction:
   ```
   - Global prefs: ~/.claude.json (MCP configs at user/local scope — extract mcpServers for MCP audit; preferences — validate JSON syntax only)
   ```

**Success criteria**:
- [ ] Task 3 prompt lists all 4 MCP scopes (project, user, local, managed)
- [ ] HTTP/SSE transport validation instructions added
- [ ] `${VAR}` expansion syntax validation instructions added
- [ ] Return section includes per-scope MCP inventory

### Phase 2: Extend Wave 2 — MCP approval cross-referencing + scope conflicts

**File**: `skills/audit-claude-config/SKILL.md`

**Changes in Phase 2 reference compilation (lines 391-415)**:

1. Add to compiled reference list:
   ```
   - MCP server inventory per scope (from Wave 1 Task 3)
   - MCP approval settings: enableAllProjectMcpServers, enabledMcpjsonServers, disabledMcpjsonServers, allowedMcpServers, deniedMcpServers (from Wave 1 Task 3 settings audit)
   ```

**Changes in Wave 2 Task 2 External Consistency Checker (lines 489-524)**:

2. Expand check 1 from:
   ```
   1. **CLAUDE.md → MCP**: MCP tools mentioned exist in .mcp.json
   ```
   To:
   ```
   1. **CLAUDE.md → MCP**: MCP tools mentioned exist in any MCP scope (project, user, local, managed)
   ```

3. Add new checks:
   ```
   N. **MCP Scope Conflicts**: Detect same server name defined at multiple scopes; report which scope takes precedence (managed > local > project > user)
   N+1. **MCP Approval → Servers**: Cross-reference enabledMcpjsonServers/disabledMcpjsonServers against actual server names in .mcp.json; flag references to non-existent servers
   N+2. **MCP Managed Policy → Servers**: If allowedMcpServers/deniedMcpServers present, cross-reference against all discovered server names across all scopes; flag servers blocked by managed deny that are configured in project/user scope
   ```

4. Update return list to include:
   ```
   - MCP scope conflict table
   - MCP approval cross-reference results
   ```

**Success criteria**:
- [ ] Phase 2 compilation includes MCP per-scope inventory
- [ ] External checker has scope conflict detection
- [ ] Approval settings cross-referenced against actual servers
- [ ] Managed deny overriding project/user config detected

### Phase 3: Extend consistency-checker agent — MCP scope awareness

**File**: `agents/consistency-checker.md`

**Changes to Cross-Reference Matrix (line 72)**:

1. Update MCP row from:
   ```
   | CLAUDE.md | .mcp.json | MCP tool X mentioned → server provides it |
   ```
   To:
   ```
   | CLAUDE.md | MCP configs (all scopes) | MCP tool X mentioned → server exists in any scope |
   ```

2. Add new rows:
   ```
   | MCP configs (multi-scope) | MCP configs | Same server name at multiple scopes → report precedence |
   | settings files | MCP configs (all scopes) | enabledMcpjsonServers/disabledMcpjsonServers → server names exist in .mcp.json |
   | managed-settings.json | MCP configs (all scopes) | allowedMcpServers/deniedMcpServers → cross-reference all scopes; flag managed deny overriding project/user |
   ```

**Changes to Step 1 collection (line 100)**:

3. Update MCP extraction:
   ```
   - Extract all MCP tool mentions from CLAUDE.md files
   - Extract MCP server inventory per scope (project, user, local, managed) from Wave 1
   - Extract MCP approval settings (enableAllProjectMcpServers, enabledMcpjsonServers, disabledMcpjsonServers, allowedMcpServers, deniedMcpServers) from settings audit
   ```

**Changes to Output Format**:

4. Add new output sections after "Agents → mcpServers (frontmatter)":
   ```
   #### MCP Scope Conflicts
   | Server Name | Scope 1 | Scope 2 | Precedence Winner | Status |
   |-------------|---------|---------|-------------------|--------|
   | server-x | project (.mcp.json) | user (~/.claude.json) | project | INFO |

   #### MCP Approval → Servers
   | Setting | Value | Server Exists | Status |
   |---------|-------|---------------|--------|
   | enabledMcpjsonServers | ["server-x"] | Yes/No | OK/WARNING |

   #### MCP Managed Policy → Servers
   | Policy | Server | Also Configured In | Effective | Status |
   |--------|--------|--------------------|-----------|--------|
   | deniedMcpServers | server-x | project (.mcp.json) | Blocked by managed deny | WARNING |
   ```

5. Update Summary table to include new check types:
   ```
   | MCP Scope Conflicts | X | Y | Z |
   | MCP Approval → Servers | X | Y | Z |
   | MCP Managed Policy | X | Y | Z |
   ```

**Success criteria**:
- [ ] Cross-Reference Matrix includes multi-scope MCP rows
- [ ] Step 1 collects per-scope MCP inventory
- [ ] Output format has MCP Scope Conflicts table
- [ ] Output format has MCP Approval cross-reference table
- [ ] Output format has MCP Managed Policy table
- [ ] Summary table includes new MCP check types

### Phase 4: Extend plugin-config-auditor — HTTP/SSE transport in agent mcpServers

**File**: `agents/plugin-config-auditor.md`

**Changes at line 48** (agent frontmatter validation):

1. Expand from:
   ```
   - `mcpServers`: each entry must have a `command` field with valid structure
   ```
   To:
   ```
   - `mcpServers`: validate per transport type:
     - stdio: must have `command` field (string) with valid structure; optional `args` (array), `env` (object), `cwd` (string)
     - http/sse: must have `url` field (valid URL format); optional `headers` (object of string key-value pairs)
     - Validate ${VAR} expansion syntax in command, args, env, url, headers fields (warn if malformed)
   ```

**Changes at line 100** (audit checklist):

2. Expand from:
   ```
   - [ ] `mcpServers` entries have `command` field (WARNING if malformed)
   ```
   To:
   ```
   - [ ] `mcpServers` entries validated per transport type: stdio has `command`, http/sse has `url` (WARNING if missing required fields)
   - [ ] `mcpServers` ${VAR} expansion syntax valid in all fields (WARNING if malformed)
   ```

**Success criteria**:
- [ ] Agent mcpServers validation covers stdio + http/sse transports
- [ ] ${VAR} expansion validation added to agent mcpServers check

### Phase 5: Update report template — MCP scope breakdown section

**File**: `skills/audit-claude-config/report-template.md`

**Changes after Config Files section (after line 89)**:

1. Add new MCP Scope Breakdown section:
   ```markdown
   ### MCP Configuration (All Scopes)

   #### MCP Server Inventory
   | Server Name | Scope | Transport | Command/URL | Env Vars | Status |
   |-------------|-------|-----------|-------------|----------|--------|
   [Table rows across all scopes: project, user, local, managed]

   #### Environment Variable Expansion
   | Server | Field | Expression | Env Var Set | Status |
   |--------|-------|------------|-------------|--------|
   [Table rows for ${VAR} references found, or "No environment variable expansions found"]

   #### MCP Scope Conflicts
   | Server Name | Scope 1 | Scope 2 | Precedence Winner | Status |
   |-------------|---------|---------|-------------------|--------|
   [Table rows, or "No scope conflicts detected"]

   #### MCP Approval Settings
   | Setting | Scope | Value | Servers Matched | Issues |
   |---------|-------|-------|-----------------|--------|
   | enableAllProjectMcpServers | [scope] | true/false | N/A | — |
   | enabledMcpjsonServers | [scope] | [list] | X of Y exist | OK/WARNING |
   | disabledMcpjsonServers | [scope] | [list] | X of Y exist | OK/WARNING |
   | allowedMcpServers | managed | [list] | X of Y configured | OK/WARNING |
   | deniedMcpServers | managed | [list] | X blocked | WARNING if blocking active servers |
   ```

2. Update MCP config health score row (line 228-229) with expanded note:
   ```
   | MCP config | X/10 | [Multi-scope discovery, env var expansion, transport validation, approval cross-reference] |
   ```

**Success criteria**:
- [ ] MCP Server Inventory table added (all scopes)
- [ ] Environment Variable Expansion table added
- [ ] MCP Scope Conflicts table added
- [ ] MCP Approval Settings table added
- [ ] Health score note updated

---

## Design Decisions

1. **INFO vs WARNING for unset env vars**: Using INFO severity because env vars may be intentionally set only at runtime (CI, deployment). Malformed syntax gets WARNING.
2. **MCP scope precedence**: Following Claude Code documentation: managed > local > project > user.
3. **Transport detection**: If entry has `url` field → http/sse; if entry has `command` field → stdio. Flag entries with neither as ERROR.
4. **No functional testing**: Per issue scope boundaries — we validate config structure, not actual MCP server connectivity.

## Testing Strategy

- Run `/ll:audit-claude-config mcp` after changes to verify MCP-scoped audit works
- Run `/ll:audit-claude-config all` for full audit regression
- Verify report template renders correctly with new sections

## Risk Assessment

- **Risk**: Low — All changes are additive to existing audit instructions
- **Breaking change**: No — New sections appear only when relevant MCP configs are discovered
- **Scope creep guard**: Not validating MCP tool schemas or server functionality per issue scope boundaries
