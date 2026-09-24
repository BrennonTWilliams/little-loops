#!/usr/bin/env bash
# Shared utilities library for ll hooks
# Provides file locking, atomic writes, and portable date operations

# File locking with cross-platform fallback
# Usage: acquire_lock "$lockfile" 10
# Returns: 0 on success, 1 on timeout
acquire_lock() {
    local lock_file="$1"
    local timeout="${2:-10}"

    # Try flock first (Linux, macOS with Homebrew coreutils)
    if command -v flock >/dev/null 2>&1; then
        # Open lock file on FD 200
        exec 200>"$lock_file" 2>/dev/null || return 1
        # Wait up to timeout seconds
        flock -w "$timeout" 200 2>/dev/null || return 1
        return 0
    fi

    # Fallback: mkdir-based atomic lock (POSIX)
    local lock_dir="${lock_file}.lock"
    local elapsed=0
    local sleep_interval=0.1
    local max_iterations=$((timeout * 10))  # 0.1s intervals

    while ! mkdir "$lock_dir" 2>/dev/null; do
        sleep "$sleep_interval"
        elapsed=$((elapsed + 1))
        if [ "$elapsed" -ge "$max_iterations" ]; then
            return 1
        fi
    done

    # Set cleanup trap for mkdir-based lock
    trap "rmdir '$lock_dir' 2>/dev/null || true" EXIT INT TERM
    return 0
}

# Release lock (for mkdir-based locks)
# Usage: release_lock "$lockfile"
release_lock() {
    local lock_file="$1"
    local lock_dir="${lock_file}.lock"

    # For flock, closing FD 200 releases lock automatically
    # For mkdir-based, remove directory
    if [ -d "$lock_dir" ]; then
        rmdir "$lock_dir" 2>/dev/null || true
    fi

    # Clear trap
    trap - EXIT INT TERM
}

# Atomic JSON write with validation
# Usage: atomic_write_json "$target" "$json_content"
# Returns: 0 on success, 1 on failure
atomic_write_json() {
    local target="$1"
    local content="$2"
    local tmp="${target}.tmp.$$"

    # Ensure parent directory exists
    mkdir -p "$(dirname "$target")" 2>/dev/null || true

    # Write to temp file
    echo "$content" > "$tmp" 2>/dev/null || return 1

    # Validate JSON structure if jq available
    if command -v jq >/dev/null 2>&1; then
        if ! jq empty "$tmp" 2>/dev/null; then
            rm -f "$tmp"
            return 1
        fi
    fi

    # Atomic rename (works on same filesystem)
    mv -f "$tmp" "$target" 2>/dev/null || {
        rm -f "$tmp"
        return 1
    }

    return 0
}

# Portable date to epoch conversion
# Usage: to_epoch "$iso_date"
# Returns: epoch seconds or 0 on failure
to_epoch() {
    local date="$1"

    # Empty or invalid input
    if [ -z "$date" ]; then
        echo "0"
        return 0
    fi

    # Try macOS date format first
    local epoch
    epoch=$(TZ=UTC date -j -f "%Y-%m-%dT%H:%M:%SZ" "$date" +%s 2>/dev/null)
    if [ $? -eq 0 ] && [ -n "$epoch" ]; then
        echo "$epoch"
        return 0
    fi

    # Try GNU date format (Linux)
    # ll-portability-ok: GNU half of the BSD-first pair above
    epoch=$(date -d "$date" +%s 2>/dev/null)
    if [ $? -eq 0 ] && [ -n "$epoch" ]; then
        echo "$epoch"
        return 0
    fi

    # Fallback: return 0
    echo "0"
    return 0
}

# Safe string substitution without shell expansion
# Usage: safe_substitute "$template" "{{PLACEHOLDER}}" "$user_input"
# Returns: substituted string
safe_substitute() {
    local template="$1"
    local placeholder="$2"
    local value="$3"

    # Use bash parameter expansion (no shell metacharacter expansion)
    echo "${template//$placeholder/$value}"
}

# Get file modification time as epoch
# Usage: get_mtime "$filepath"
# Returns: epoch seconds or 0 on failure
get_mtime() {
    local file="$1"

    if [ ! -f "$file" ]; then
        echo "0"
        return 0
    fi

    # Try macOS stat
    local mtime
    mtime=$(stat -f %m "$file" 2>/dev/null)
    if [ $? -eq 0 ] && [ -n "$mtime" ]; then
        echo "$mtime"
        return 0
    fi

    # Try GNU stat (Linux)
    # ll-portability-ok: GNU half of the BSD-first pair above
    mtime=$(stat -c %Y "$file" 2>/dev/null)
    if [ $? -eq 0 ] && [ -n "$mtime" ]; then
        echo "$mtime"
        return 0
    fi

    # Fallback
    echo "0"
    return 0
}

# Current epoch milliseconds as an integer (pure shell, bash 3.2 safe)
# Usage: now_ms
# Order: $EPOCHREALTIME (bash 5) -> date +%s%N if all digits -> $(date +%s)000.
# BSD date may print a literal "N" for %N (exit 0), hence the digit check.
# Never spawns python3 (macOS xcode-select stub opens a GUI dialog).
now_ms() {
    if [ -n "${EPOCHREALTIME:-}" ]; then
        local sec="${EPOCHREALTIME%%[.,]*}"
        local frac="${EPOCHREALTIME#*[.,]}000"
        echo "${sec}${frac:0:3}"
        return 0
    fi

    local ns
    # ll-portability-ok: output is digit-checked below (BSD may print literal N)
    ns=$(date +%s%N 2>/dev/null || true)
    case "$ns" in
        ''|*[!0-9]*) ;;
        *)
            if [ "${#ns}" -gt 6 ]; then
                echo "${ns%??????}"
                return 0
            fi
            ;;
    esac

    echo "$(date +%s 2>/dev/null || echo 0)000"
    return 0
}

# Resolve ll-config.json file path
# Usage: ll_resolve_config
# Sets: LL_CONFIG_FILE (empty string if not found)
ll_resolve_config() {
    LL_CONFIG_FILE=""
    mkdir -p .ll 2>/dev/null || true
    if [ -f ".ll/ll-config.json" ]; then
        LL_CONFIG_FILE=".ll/ll-config.json"
    elif [ -f "ll-config.json" ]; then
        LL_CONFIG_FILE="ll-config.json"
    fi
}

# Check if a feature flag is enabled in ll-config.json
# Usage: ll_feature_enabled "section.enabled"
# Returns: 0 if enabled, 1 if disabled/missing/no-jq
# Requires: ll_resolve_config called first, jq available
ll_feature_enabled() {
    local flag_path="$1"

    if [ -z "$LL_CONFIG_FILE" ]; then
        return 1
    fi

    if ! command -v jq &> /dev/null; then
        return 1
    fi

    local enabled
    enabled=$(jq -r ".${flag_path} // false" "$LL_CONFIG_FILE" 2>/dev/null || echo "false")
    [ "$enabled" = "true" ]
}

# Read a config value with a default fallback
# Usage: ll_config_value "path.to.key" "default_value"
# Prints: the config value or default
# Requires: ll_resolve_config called first, jq available
ll_config_value() {
    local key_path="$1"
    local default_value="${2:-}"

    if [ -z "$LL_CONFIG_FILE" ] || ! command -v jq &> /dev/null; then
        echo "$default_value"
        return 0
    fi

    local value
    value=$(jq -r ".${key_path} // empty" "$LL_CONFIG_FILE" 2>/dev/null)
    if [ -z "$value" ]; then
        echo "$default_value"
    else
        echo "$value"
    fi
}
