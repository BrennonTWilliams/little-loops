# ENH-457: Reconcile templates/*.json with presets.md as Single Source of Truth

**Created**: 2026-02-23
**Issue**: P3-ENH-457-reconcile-templates-json-with-presets-md.md
**Status**: Planning

## Research Findings

### Current State
- **SKILL.md Step 3** (lines 57-73): Manual 7-row detection table mapping indicator files to project types (Python, Node.js, Go, Rust, Java, .NET, General)
- **SKILL.md Step 4** (line 77): Single line referencing `presets.md` for configuration presets
- **presets.md** (lines 5-123): 7 preset JSON blocks with only `project` and `scan` sections
- **presets.md** (lines 125-157): Interactive mode option alternatives per language (test commands, lint commands, format commands, build/run/test dir options)
- **interactive.md** (line 86): References `presets.md` for populating wizard option lists
- **templates/*.json** (9 project-type files): Rich JSON with `_meta.detect`, `project`, `scan`, `issues`, `product` sections
- **docs/ARCHITECTURE.md** (line 136): Lists `presets.md` in the directory tree

### Key Differences Between Templates and Presets
1. **TypeScript**: Templates have a distinct `typescript.json`; presets.md has no TypeScript (falls to Node.js)
2. **Java split**: Templates split into `java-maven.json` and `java-gradle.json`; presets.md has single "Java"
3. **JS/TS disambiguation**: `javascript.json` has `detect_exclude: ["tsconfig.json"]`; no equivalent in SKILL.md
4. **Missing fields**: presets.md omits `build_cmd`, `run_cmd` for most types; templates always include them
5. **Value drift**: e.g., Rust clippy has `-D warnings` in template but not presets; Java `lint_cmd` is `null` in presets but `mvn checkstyle:check` in template
6. **Additional sections**: Templates include `issues` and `product` sections; presets.md has neither

### Interactive Alternatives Challenge
`presets.md` lines 125-157 contain interactive mode alternative options (e.g., "Python: pytest, pytest -v, python -m pytest"). These are consumed by `interactive.md` at line 86. The template JSON files have no equivalent. **Decision**: Move these alternative lists into `interactive.md` directly since it's the only consumer.

## Implementation Plan

### Phase 1: Update SKILL.md Step 3 — Template-Driven Detection

**File**: `skills/init/SKILL.md` (lines 57-73)

Replace the manual detection table with instructions to read template files and use `_meta.detect` patterns:

```markdown
### 3. Detect Project Type

Read all project-type template JSON files from `templates/` (relative to the little-loops plugin directory), excluding `issue-sections.json` and `ll-goals-template.md`. For each template, check `_meta.detect` patterns against files in the project root:

1. For each template file, read its `_meta.detect` array
2. Check if ANY listed indicator file exists in the project root
3. If `_meta.detect_exclude` is present, skip this template if any excluded file also exists
4. If `_meta.detect` is empty (e.g., `generic.json`), this is the fallback template
5. If multiple templates match, prefer the one without `priority: -1`

**Template files** (9 project-type templates):
- `python-generic.json` — detect: `pyproject.toml`, `setup.py`, `requirements.txt`
- `typescript.json` — detect: `tsconfig.json`
- `javascript.json` — detect: `package.json` (exclude: `tsconfig.json`)
- `go.json` — detect: `go.mod`
- `rust.json` — detect: `Cargo.toml`
- `java-maven.json` — detect: `pom.xml`
- `java-gradle.json` — detect: `build.gradle`, `build.gradle.kts`
- `dotnet.json` — detect: `*.csproj`, `*.sln`, `*.fsproj`
- `generic.json` — fallback (empty detect, priority: -1)

Also detect:
- **Project name**: Use the directory name
- **Source directory**: Look for `src/`, `lib/`, or `app/` directories
```

- [x] Preserves the "Also detect" project name/source dir logic
- [x] Documents the 9 templates inline for quick reference
- [x] Handles `detect_exclude` and `priority` fields

### Phase 2: Update SKILL.md Step 4 — Use Template Directly

**File**: `skills/init/SKILL.md` (lines 75-77)

Replace the reference to `presets.md` with instructions to use the matched template JSON file:

```markdown
### 4. Generate Configuration

Read the matched template JSON file from Step 3. Extract the `project` and `scan` sections as the initial configuration presets. Also apply the `issues` section as the default issue tracking configuration.

Strip the `_meta`, `$schema`, and `product` sections (product is configured separately in interactive mode).
```

### Phase 3: Update SKILL.md Additional Resources

**File**: `skills/init/SKILL.md` (lines 259-262)

Replace:
```
- For project type configuration presets, see [presets.md](presets.md)
```
With:
```
- For project type configuration presets, see `templates/*.json` (relative to the little-loops plugin directory)
```

### Phase 4: Move Interactive Alternatives to interactive.md

**File**: `skills/init/interactive.md` (line 86)

Replace the reference:
```
Populate options based on detected project type - see [presets.md](presets.md) for options by language.
```

With the actual alternative options inline (migrated from presets.md lines 125-157):

```markdown
Populate options based on detected project type. Use these alternatives by language:

**Test commands:**
- Python: pytest, pytest -v, python -m pytest
- TypeScript: npm test, jest, vitest
- Node.js: npm test, yarn test, jest
- Go: go test ./..., go test -v ./...
- Rust: cargo test, cargo test --verbose
- Java (Maven): mvn test
- Java (Gradle): gradle test, ./gradlew test
- .NET: dotnet test

**Lint commands:**
- Python: ruff check ., flake8, pylint
- TypeScript: npm run lint, eslint .
- Node.js: npm run lint, eslint .
- Go: golangci-lint run, go vet ./...
- Rust: cargo clippy -- -D warnings, cargo check
- Java (Maven): mvn checkstyle:check
- Java (Gradle): ./gradlew checkstyleMain
- .NET: dotnet format --verify-no-changes

**Format commands:**
- Python: ruff format ., black ., autopep8
- TypeScript: npm run format, prettier --write .
- Node.js: npm run format, prettier --write ., eslint --fix
- Go: gofmt -w ., go fmt ./...
- Rust: cargo fmt
- Java: (none common)
- .NET: dotnet format

**Build/Run/Test dir options:**
- Python: tests/, test/, Same as src | Skip, python -m build, make build | Skip, python app.py, python -m flask run
- TypeScript: tests/, test/, __tests__ | npm run build, yarn build, Skip | npm start, node server.js, Skip
- Node.js: tests/, test/, __tests__/ | npm run build, yarn build, Skip | npm start, node server.js, Skip
- Go: *_test.go files in same dir | go build, make build, Skip | go run ., go run cmd/main.go, Skip
- Rust: tests/ | cargo build, cargo build --release, Skip | cargo run, Skip
- Java (Maven): src/test/java/ | mvn package, Skip | mvn exec:java, Skip
- Java (Gradle): src/test/java/ | gradle build, ./gradlew build, Skip | gradle run, Skip
- .NET: tests/ | dotnet build, dotnet publish, Skip | dotnet run, Skip
```

Key changes from the original:
- Added TypeScript as a distinct entry (matches the new template set)
- Split Java into Maven and Gradle variants
- Updated Rust lint to include `-D warnings` flag (matching the template)
- Updated Java lint to `mvn checkstyle:check` / `./gradlew checkstyleMain` (matching templates)

### Phase 5: Delete presets.md

**File**: `skills/init/presets.md`

Delete the file entirely. All data has been migrated:
- JSON preset blocks → now sourced from `templates/*.json` directly
- Interactive alternatives → moved to `interactive.md`

### Phase 6: Update ARCHITECTURE.md

**File**: `docs/ARCHITECTURE.md` (line 136)

Remove `presets.md` from the directory tree listing. The line `│   │   └── presets.md` should be removed.

## Success Criteria

- [ ] SKILL.md Step 3 uses `_meta.detect` from templates for project type detection
- [ ] SKILL.md Step 4 reads matched template JSON file instead of presets.md
- [ ] SKILL.md Additional Resources section updated
- [ ] interactive.md has inline alternatives (no presets.md reference)
- [ ] presets.md is deleted
- [ ] ARCHITECTURE.md updated to remove presets.md from tree
- [ ] TypeScript and Java Maven/Gradle are properly handled as distinct types
- [ ] `detect_exclude` logic is documented for JS/TS disambiguation
- [ ] No other files reference presets.md (checked: format-issue, capture-issue, scan-codebase, ready-issue — none reference it)

## Risks

- **Low**: Detection behavior changes slightly — TypeScript now detected separately from Node.js, Java split into Maven/Gradle. This is an improvement per the template design.
- **Low**: Interactive alternatives updated to match template values (e.g., Rust clippy flags). This aligns preset data with the authoritative templates.
