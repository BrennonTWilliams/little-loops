#!/usr/bin/env bash
#
# verify_learning_citations.sh
# Verify that every # Verified: .ll/learning-tests/<slug>.md citation in a
# scaffold directory resolves to an existing record with status: proven.
#
# Usage: bash scripts/verify_learning_citations.sh <scaffold_dir>
#
# Exit 0 if all citations are valid (proven records).
# Exit 1 if any citation is missing, refuted, stale, or malformed.
# Exit 1 if no # Verified: citations are found (scaffold was not annotated).

set -euo pipefail

SCAFFOLD_DIR="${1:-}"

if [[ -z "$SCAFFOLD_DIR" ]]; then
    echo "ERROR: scaffold_dir argument required" >&2
    echo "Usage: bash scripts/verify_learning_citations.sh <scaffold_dir>" >&2
    exit 1
fi

if [[ ! -d "$SCAFFOLD_DIR" ]]; then
    echo "ERROR: scaffold directory does not exist: ${SCAFFOLD_DIR}" >&2
    exit 1
fi

# Patterns to match verified citations in source files:
#   Python:     # Verified: .ll/learning-tests/<slug>.md
#   TypeScript: // Verified: .ll/learning-tests/<slug>.md
CITATION_PATTERN='Verified: \.ll/learning-tests/[a-zA-Z0-9_-]+\.md'

# Collect all citation lines from source files (null-terminated for safety)
citations_found=0
failures=0

while IFS= read -r -d '' src_file; do
    # Skip non-source files
    case "$src_file" in
        *.py|*.ts|*.js|*.jsx|*.tsx|*.rb|*.go|*.java|*.rs|*.kt) ;;
        *) continue ;;
    esac

    # Extract citation paths from this file
    while IFS= read -r citation_line; do
        citations_found=$((citations_found + 1))

        # Extract the path part: .ll/learning-tests/<slug>.md
        lt_path=$(echo "$citation_line" | grep -oE '\.ll/learning-tests/[a-zA-Z0-9_-]+\.md' || true)

        if [[ -z "$lt_path" ]]; then
            echo "FAIL: malformed citation in ${src_file}: ${citation_line}" >&2
            failures=$((failures + 1))
            continue
        fi

        # Check the record file exists
        if [[ ! -f "$lt_path" ]]; then
            echo "FAIL: cited record does not exist: ${lt_path} (referenced in ${src_file})" >&2
            failures=$((failures + 1))
            continue
        fi

        # Extract status from YAML frontmatter (first occurrence of 'status:' line)
        record_status=$(grep -m 1 '^status:' "$lt_path" | sed 's/^status:[[:space:]]*//' | tr -d "'" | tr -d '"' | tr -d ' ' || true)

        if [[ "$record_status" != "proven" ]]; then
            echo "FAIL: cited record has status '${record_status}' (expected 'proven'): ${lt_path} (referenced in ${src_file})" >&2
            failures=$((failures + 1))
        else
            echo "OK: ${lt_path} (status: proven)"
        fi
    done < <(grep -oE "$CITATION_PATTERN" "$src_file" 2>/dev/null || true)

done < <(find "$SCAFFOLD_DIR" -type f -print0 2>/dev/null)

if [[ $citations_found -eq 0 ]]; then
    echo "FAIL: no # Verified: citations found in ${SCAFFOLD_DIR}" >&2
    echo "Every API call site in scaffolded integration code must include a" >&2
    echo "  # Verified: .ll/learning-tests/<slug>.md" >&2
    echo "comment citing the Learning Test record that proves that surface." >&2
    exit 1
fi

if [[ $failures -gt 0 ]]; then
    echo "FAIL: ${failures} citation(s) invalid out of ${citations_found} total" >&2
    exit 1
fi

echo "PASS: all ${citations_found} citation(s) verified (status: proven)"
exit 0
