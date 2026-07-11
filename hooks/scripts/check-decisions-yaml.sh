#!/usr/bin/env bash
#
# check-decisions-yaml.sh — Claude Code PreToolUse hook for .ll/decisions.yaml
# (ENH-2592).
#
# Validates the candidate content of a Write/Edit operation against
# ll-verify-decisions (ENH-2589) BEFORE Claude mutates disk. Catches
# agent-induced corruption at the host layer, complementing the pre-commit
# hook (ENH-2590) and pytest CI gate (ENH-2591).
#
# Exit semantics (Claude Code PreToolUse contract — see
# hooks/adapters/claude-code/pre-tool-use.sh:7-13):
#   0 = allow (irrelevant tool/path, missing tools, or clean candidate)
#   2 = block (validator reported YAML corruption; ERROR bubbled to stderr)
#
# Reads tool input from stdin (Claude Code native transport) or
# $CLAUDE_TOOL_INPUT as a fallback, then stages Write content or Edit
# reconstruction in a temporary config root and runs the validator against
# the staged copy. This validates the candidate, not the current file —
# catches corruption that the git + pytest belt would miss when the current
# on-disk file is still valid.

set -euo pipefail

# ---------------------------------------------------------------------------
# Read tool input (stdin, with $CLAUDE_TOOL_INPUT fallback)
# ---------------------------------------------------------------------------

INPUT="${CLAUDE_TOOL_INPUT:-}"
if [[ -z "$INPUT" ]]; then
    INPUT=$(cat)
fi

if [[ -z "$INPUT" ]]; then
    exit 0
fi

# Python is required for JSON parsing — the project already assumes Python
# is available for Claude hook adapters (see
# hooks/adapters/claude-code/pre-tool-use.sh:11-13). Fail-open when Python
# is missing so contributors without it aren't hard-blocked.
if ! command -v python3 >/dev/null 2>&1; then
    echo "[little-loops] check-decisions-yaml: python3 not on PATH; skipping host-side gate" >&2
    exit 0
fi

# ---------------------------------------------------------------------------
# Stage candidate content in a temporary config root
# ---------------------------------------------------------------------------
#
# Python handles the JSON parsing, candidate reconstruction (Edit), and
# staging in one pass. Outputs a single status line to stdout:
#   "ok"        → staged candidate ready at $WORK_DIR/.ll/decisions.yaml
#   "skip:msg"  → irrelevant tool/path, allow silently
#   "error:msg" → malformed input, allow silently with a one-line stderr note
WORK_DIR=$(mktemp -d -t check-decisions-yaml-XXXXXX 2>/dev/null || mktemp -d)
trap 'rm -rf "$WORK_DIR" 2>/dev/null || true' EXIT INT TERM

STATUS="$(INPUT="$INPUT" WORK_DIR="$WORK_DIR" python3 <<'PY' 2>/dev/null || true
import json
import os
import sys

try:
    payload = json.loads(os.environ['INPUT'])
except Exception as exc:
    print(f"error:malformed-json ({exc})")
    sys.exit(0)

tool_name = payload.get('tool_name') or ''
tool_input = payload.get('tool_input') or {}
file_path = tool_input.get('file_path') or ''

if tool_name not in ('Write', 'Edit'):
    print('skip:not-write-or-edit')
    sys.exit(0)

# Accept absolute paths ending in /.ll/decisions.yaml and the bare relative
# form. Reject anything else (including paths inside repo subtrees that
# merely contain a .ll/ segment — those are not the log file).
if not (file_path.endswith('/.ll/decisions.yaml') or file_path == '.ll/decisions.yaml'):
    print('skip:not-decisions-yaml')
    sys.exit(0)

work_dir = os.environ['WORK_DIR']
ll_dir = os.path.join(work_dir, '.ll')
os.makedirs(ll_dir, exist_ok=True)
candidate_path = os.path.join(ll_dir, 'decisions.yaml')

if tool_name == 'Write':
    content = tool_input.get('content') or ''
    with open(candidate_path, 'w', encoding='utf-8') as fh:
        fh.write(content)
    print('ok')
    sys.exit(0)

# tool_name == 'Edit' — reconstruct the post-Edit result from the current file
if not os.path.isfile(file_path):
    print('skip:edit-target-missing')
    sys.exit(0)

with open(file_path, 'rb') as fh:
    current = fh.read()

old_string = tool_input.get('old_string') or ''
new_string = tool_input.get('new_string')
if new_string is None:
    new_string = ''
replace_all = bool(tool_input.get('replace_all', False))

if not old_string:
    # No old_string → can't reconstruct; fall back to current-file validation
    with open(candidate_path, 'wb') as fh:
        fh.write(current)
    print('ok')
    sys.exit(0)

old_bytes = old_string.encode('utf-8')
new_bytes = new_string.encode('utf-8')
occurrences = current.count(old_bytes)

if occurrences == 0:
    # old_string not found in current file → fall back to current-file validation
    with open(candidate_path, 'wb') as fh:
        fh.write(current)
    print('ok')
    sys.exit(0)

if replace_all:
    staged = current.replace(old_bytes, new_bytes)
else:
    staged = current.replace(old_bytes, new_bytes, 1)

with open(candidate_path, 'wb') as fh:
    fh.write(staged)
print('ok')
PY
)"

case "$STATUS" in
    skip:*)
        echo "[little-loops] check-decisions-yaml: ${STATUS#skip:}" >&2
        exit 0
        ;;
    error:*)
        echo "[little-loops] check-decisions-yaml: ${STATUS#error:}" >&2
        exit 0
        ;;
    ok)
        : # proceed to validation
        ;;
    *)
        echo "[little-loops] check-decisions-yaml: unexpected status '$STATUS'" >&2
        exit 0
        ;;
esac

# ---------------------------------------------------------------------------
# Run the validator against the staged candidate
# ---------------------------------------------------------------------------

if ! command -v ll-verify-decisions >/dev/null 2>&1; then
    echo "[little-loops] check-decisions-yaml: ll-verify-decisions not on PATH; skipping host-side gate (pre-commit ENH-2590 and pytest CI ENH-2591 still enforce)" >&2
    exit 0
fi

# Run validator; capture exit code separately to avoid set -e killing the
# script on a validator failure (which is the host-level "block" signal).
set +e
VALIDATION_OUTPUT="$(ll-verify-decisions --config-root "$WORK_DIR" 2>&1)"
RC=$?
set -e

if [[ $RC -ne 0 ]]; then
    # Surface the validator's single-line ERROR on stderr for the host to
    # inject as the block reason. Don't echo on stdout (Claude Code uses
    # stdout for permissionDecision JSON; stderr is the feedback channel).
    while IFS= read -r line; do
        echo "[little-loops] decisions gate: ${line}" >&2
    done <<<"$VALIDATION_OUTPUT"
    exit 2
fi

exit 0
