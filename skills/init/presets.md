# Project Type Configuration Presets

Based on detected project type, use these presets for `ll-config.json`:

## Python
```json
{
  "project": {
    "src_dir": "src/",
    "test_cmd": "pytest",
    "lint_cmd": "ruff check .",
    "type_cmd": "mypy",
    "format_cmd": "ruff format ."
  },
  "scan": {
    "focus_dirs": ["src/", "tests/"],
    "exclude_patterns": ["**/__pycache__/**", "**/.venv/**", "**/dist/**"]
  }
}
```

## Node.js
```json
{
  "project": {
    "src_dir": "src/",
    "test_cmd": "npm test",
    "lint_cmd": "npm run lint",
    "type_cmd": null,
    "format_cmd": "npm run format"
  },
  "scan": {
    "focus_dirs": ["src/", "tests/", "lib/"],
    "exclude_patterns": ["**/node_modules/**", "**/dist/**", "**/build/**"]
  }
}
```

## Go
```json
{
  "project": {
    "src_dir": ".",
    "test_cmd": "go test ./...",
    "lint_cmd": "golangci-lint run",
    "type_cmd": null,
    "format_cmd": "gofmt -w ."
  },
  "scan": {
    "focus_dirs": ["cmd/", "pkg/", "internal/"],
    "exclude_patterns": ["**/vendor/**"]
  }
}
```

## Rust
```json
{
  "project": {
    "src_dir": "src/",
    "test_cmd": "cargo test",
    "lint_cmd": "cargo clippy",
    "type_cmd": null,
    "format_cmd": "cargo fmt"
  },
  "scan": {
    "focus_dirs": ["src/"],
    "exclude_patterns": ["**/target/**"]
  }
}
```

## Java
```json
{
  "project": {
    "src_dir": "src/main/java/",
    "test_cmd": "mvn test",
    "lint_cmd": null,
    "type_cmd": null,
    "format_cmd": null,
    "build_cmd": "mvn package"
  },
  "scan": {
    "focus_dirs": ["src/main/java/", "src/test/java/"],
    "exclude_patterns": ["**/target/**", "**/.idea/**"]
  }
}
```

## .NET
```json
{
  "project": {
    "src_dir": "src/",
    "test_cmd": "dotnet test",
    "lint_cmd": "dotnet format --verify-no-changes",
    "type_cmd": null,
    "format_cmd": "dotnet format"
  },
  "scan": {
    "focus_dirs": ["src/"],
    "exclude_patterns": ["**/bin/**", "**/obj/**"]
  }
}
```

## General (fallback)
```json
{
  "project": {
    "src_dir": "src/",
    "test_cmd": null,
    "lint_cmd": null,
    "type_cmd": null,
    "format_cmd": null
  },
  "scan": {
    "focus_dirs": ["src/"],
    "exclude_patterns": ["**/node_modules/**", "**/__pycache__/**", "**/.git/**"]
  }
}
```

## Interactive Mode Options by Project Type

**Test commands:**
- Python: pytest, pytest -v, python -m pytest
- Node.js: npm test, yarn test, jest
- Go: go test ./..., go test -v ./...
- Rust: cargo test, cargo test --verbose
- Java: mvn test, gradle test
- .NET: dotnet test

**Lint commands:**
- Python: ruff check ., flake8, pylint
- Node.js: npm run lint, eslint .
- Go: golangci-lint run, go vet ./...
- Rust: cargo clippy, cargo check
- Java: (no common lint)
- .NET: dotnet format --verify-no-changes

**Format commands:**
- Python: ruff format ., black ., autopep8
- Node.js: npm run format, prettier --write ., eslint --fix
- Go: gofmt -w ., go fmt ./...
- Rust: cargo fmt
- Java: (none common)
- .NET: dotnet format

**Build/Run/Test dir options:**
- Python: tests/, test/, Same as src | Skip, python -m build, make build | Skip, python app.py, python -m flask run
- Node.js: tests/, test/, __tests__/ | npm run build, yarn build, Skip | npm start, node server.js, Skip
- Go: *_test.go files in same dir | go build, make build, Skip | go run ., go run cmd/main.go, Skip
- Rust: tests/ | cargo build, cargo build --release, Skip | cargo run, Skip
- Java: src/test/java/ | mvn package, gradle build, Skip | mvn exec:java, Skip
- .NET: tests/ | dotnet build, dotnet publish, Skip | dotnet run, Skip
