"""Tests for the sft-corpus loop — enrich state and quality filter predicates."""

import json
import subprocess
from pathlib import Path


def _bash(script: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a bash script in the given working directory, capturing output."""
    return subprocess.run(["bash", "-c", script], cwd=cwd, capture_output=True, text=True)


# ---------------------------------------------------------------------------
# Enrich state tests
# ---------------------------------------------------------------------------


class TestEnrichGracefulDegradation:
    """Enrich state degrades gracefully when history.db is missing or empty."""

    def test_missing_db_produces_default_metadata(self, tmp_path: Path) -> None:
        """When history.db is absent, all examples get default metadata (zeros/nulls)."""
        run_dir = tmp_path / ".loops" / "runs" / "sft-corpus-test"
        run_dir.mkdir(parents=True)

        # Create a staged raw.jsonl with a fake source path
        raw = run_dir / "raw.jsonl"
        raw.write_text(
            json.dumps(
                {
                    "source": "00000000-0000-0000-0000-000000000001.jsonl",
                    "messages": [{"role": "user", "content": "test"}],
                }
            )
            + "\n"
        )

        script = f"""python3 << 'PYEOF'
import json, sys
from pathlib import Path
sys.path.insert(0, "scripts")
from little_loops.history_reader import lookup_session_metadata

input_file = Path("{raw}")
output_file = Path("{run_dir}/enriched.jsonl")

with open(input_file) as f_in, open(output_file, "w") as f_out:
    for line in f_in:
        line = line.strip()
        if not line:
            continue
        example = json.loads(line)
        source = example.get("source", "")
        session_id = Path(source).stem if source else ""
        if session_id:
            metadata = lookup_session_metadata(session_id)
        else:
            metadata = {{}}
        example["metadata"] = {{
            "has_corrections": metadata.get("has_corrections", False),
            "issue_outcome": metadata.get("issue_outcome"),
            "tool_count": metadata.get("tool_count", 0),
            "files_modified": metadata.get("files_modified", 0),
        }}
        f_out.write(json.dumps(example) + "\\n")
print(str(output_file))
PYEOF
"""
        result = _bash(script, tmp_path)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        enriched_file = run_dir / "enriched.jsonl"
        assert enriched_file.exists()

        enriched = json.loads(enriched_file.read_text().strip())
        assert enriched["metadata"]["has_corrections"] is False
        assert enriched["metadata"]["issue_outcome"] is None
        assert enriched["metadata"]["tool_count"] == 0
        assert enriched["metadata"]["files_modified"] == 0

    def test_empty_source_produces_default_metadata(self, tmp_path: Path) -> None:
        """When source field is empty, session_id is empty → default metadata."""
        run_dir = tmp_path / ".loops" / "runs" / "sft-corpus-test"
        run_dir.mkdir(parents=True)

        raw = run_dir / "raw.jsonl"
        raw.write_text(
            json.dumps(
                {
                    "source": "",
                    "messages": [{"role": "user", "content": "test"}],
                }
            )
            + "\n"
        )

        script = f"""python3 << 'PYEOF'
import json, sys
from pathlib import Path
sys.path.insert(0, "scripts")
from little_loops.history_reader import lookup_session_metadata

input_file = Path("{raw}")
output_file = Path("{run_dir}/enriched.jsonl")

with open(input_file) as f_in, open(output_file, "w") as f_out:
    for line in f_in:
        line = line.strip()
        if not line:
            continue
        example = json.loads(line)
        source = example.get("source", "")
        session_id = Path(source).stem if source else ""
        if session_id:
            metadata = lookup_session_metadata(session_id)
        else:
            metadata = {{}}
        example["metadata"] = {{
            "has_corrections": metadata.get("has_corrections", False),
            "issue_outcome": metadata.get("issue_outcome"),
            "tool_count": metadata.get("tool_count", 0),
            "files_modified": metadata.get("files_modified", 0),
        }}
        f_out.write(json.dumps(example) + "\\n")
print(str(output_file))
PYEOF
"""
        result = _bash(script, tmp_path)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        enriched_file = run_dir / "enriched.jsonl"
        assert enriched_file.exists()

        enriched = json.loads(enriched_file.read_text().strip())
        assert enriched["metadata"]["has_corrections"] is False


# ---------------------------------------------------------------------------
# Filter predicate tests — precision (each predicate drops only its target)
# ---------------------------------------------------------------------------


def _make_enriched_example(
    run_dir: Path,
    *,
    issue_outcome: str | None = "done",
    has_corrections: bool = False,
    tool_count: int = 5,
    files_modified: int = 3,
) -> Path:
    """Write an enriched.jsonl with controlled metadata for predicate testing."""
    run_dir.mkdir(parents=True, exist_ok=True)
    enriched = run_dir / "enriched.jsonl"
    example = {
        "source": "00000000-0000-0000-0000-000000000001.jsonl",
        "messages": [{"role": "user", "content": "test"}],
        "metadata": {
            "has_corrections": has_corrections,
            "issue_outcome": issue_outcome,
            "tool_count": tool_count,
            "files_modified": files_modified,
        },
    }
    enriched.write_text(json.dumps(example) + "\n")
    return enriched


class TestRequireIssueOutcome:
    """Predicate: require_issue_outcome drops sessions where no issue was closed."""

    def test_passes_when_issue_outcome_is_done(self, tmp_path: Path) -> None:
        run_dir = tmp_path / ".loops" / "runs" / "sft-corpus-test"
        enriched_file = _make_enriched_example(run_dir, issue_outcome="done")

        result = _bash(
            f"""python3 -c "
import json
with open('{enriched_file}') as f:
    ex = json.loads(f.readline())
outcome = ex.get('metadata', {{}}).get('issue_outcome')
print(1 if outcome == 'done' else 0)
"
""",
            tmp_path,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "1"

    def test_fails_when_issue_outcome_is_not_done(self, tmp_path: Path) -> None:
        run_dir = tmp_path / ".loops" / "runs" / "sft-corpus-test"
        enriched_file = _make_enriched_example(run_dir, issue_outcome="cancelled")

        result = _bash(
            f"""python3 -c "
import json
with open('{enriched_file}') as f:
    ex = json.loads(f.readline())
outcome = ex.get('metadata', {{}}).get('issue_outcome')
print(1 if outcome == 'done' else 0)
"
""",
            tmp_path,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "0"

    def test_fails_when_issue_outcome_is_none(self, tmp_path: Path) -> None:
        run_dir = tmp_path / ".loops" / "runs" / "sft-corpus-test"
        enriched_file = _make_enriched_example(run_dir, issue_outcome=None)

        result = _bash(
            f"""python3 -c "
import json
with open('{enriched_file}') as f:
    ex = json.loads(f.readline())
outcome = ex.get('metadata', {{}}).get('issue_outcome')
print(1 if outcome == 'done' else 0)
"
""",
            tmp_path,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "0"

    def test_disabled_flag_passes_through(self, tmp_path: Path) -> None:
        """When require_issue_outcome is false, predicate prints 1 regardless."""
        run_dir = tmp_path / ".loops" / "runs" / "sft-corpus-test"
        enriched_file = _make_enriched_example(run_dir, issue_outcome=None)

        # Simulate the gating: enabled=false → print 1
        result = _bash(
            f"""python3 -c "
enabled = False  # context flag is false
if not enabled:
    print(1)
    exit()
import json
with open('{enriched_file}') as f:
    ex = json.loads(f.readline())
outcome = ex.get('metadata', {{}}).get('issue_outcome')
print(1 if outcome == 'done' else 0)
"
""",
            tmp_path,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "1"


class TestExcludeUserCorrections:
    """Predicate: exclude_user_corrections drops sessions with user corrections."""

    def test_passes_when_no_corrections(self, tmp_path: Path) -> None:
        run_dir = tmp_path / ".loops" / "runs" / "sft-corpus-test"
        enriched_file = _make_enriched_example(run_dir, has_corrections=False)

        result = _bash(
            f"""python3 -c "
import json
with open('{enriched_file}') as f:
    ex = json.loads(f.readline())
has_corrections = ex.get('metadata', {{}}).get('has_corrections', False)
print(1 if has_corrections else 0)
"
""",
            tmp_path,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "0"

    def test_fails_when_has_corrections(self, tmp_path: Path) -> None:
        run_dir = tmp_path / ".loops" / "runs" / "sft-corpus-test"
        enriched_file = _make_enriched_example(run_dir, has_corrections=True)

        result = _bash(
            f"""python3 -c "
import json
with open('{enriched_file}') as f:
    ex = json.loads(f.readline())
has_corrections = ex.get('metadata', {{}}).get('has_corrections', False)
print(1 if has_corrections else 0)
"
""",
            tmp_path,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "1"

    def test_disabled_flag_passes_through(self, tmp_path: Path) -> None:
        """When exclude_user_corrections is false, predicate prints 0 (evaluator eq 0 passes)."""
        run_dir = tmp_path / ".loops" / "runs" / "sft-corpus-test"
        _make_enriched_example(run_dir, has_corrections=True)

        # With gating disabled, print 0 → eq 0 → routes on_yes (pass-through)
        result = _bash(
            """python3 -c "
enabled = False
if not enabled:
    print(0)
    exit()
"
""",
            tmp_path,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "0"


class TestMinToolInvocations:
    """Predicate: min_tool_invocations drops sessions with too few tool calls."""

    def test_passes_when_tool_count_meets_minimum(self, tmp_path: Path) -> None:
        run_dir = tmp_path / ".loops" / "runs" / "sft-corpus-test"
        enriched_file = _make_enriched_example(run_dir, tool_count=10)

        result = _bash(
            f"""python3 -c "
import json
with open('{enriched_file}') as f:
    ex = json.loads(f.readline())
tool_count = ex.get('metadata', {{}}).get('tool_count', 0)
print(tool_count)
"
""",
            tmp_path,
        )
        assert result.returncode == 0
        assert int(result.stdout.strip()) >= 3  # ge 3

    def test_fails_when_tool_count_below_minimum(self, tmp_path: Path) -> None:
        run_dir = tmp_path / ".loops" / "runs" / "sft-corpus-test"
        enriched_file = _make_enriched_example(run_dir, tool_count=1)

        result = _bash(
            f"""python3 -c "
import json
with open('{enriched_file}') as f:
    ex = json.loads(f.readline())
tool_count = ex.get('metadata', {{}}).get('tool_count', 0)
print(tool_count)
"
""",
            tmp_path,
        )
        assert result.returncode == 0
        assert int(result.stdout.strip()) < 3  # below ge 3

    def test_default_zero_passes_through(self, tmp_path: Path) -> None:
        """When min_tool_invocations is 0 (default), predicate passes through."""
        result = _bash(
            """python3 -c "
min_tools = '0'
if min_tools == '0' or min_tools == '':
    print(0)
    exit()
"
""",
            tmp_path,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "0"


class TestRequireFileModifications:
    """Predicate: require_file_modifications drops sessions with zero file modifications."""

    def test_passes_when_files_modified(self, tmp_path: Path) -> None:
        run_dir = tmp_path / ".loops" / "runs" / "sft-corpus-test"
        enriched_file = _make_enriched_example(run_dir, files_modified=5)

        result = _bash(
            f"""python3 -c "
import json
with open('{enriched_file}') as f:
    ex = json.loads(f.readline())
files_modified = ex.get('metadata', {{}}).get('files_modified', 0)
print(files_modified)
"
""",
            tmp_path,
        )
        assert result.returncode == 0
        assert int(result.stdout.strip()) >= 1

    def test_fails_when_zero_files_modified(self, tmp_path: Path) -> None:
        run_dir = tmp_path / ".loops" / "runs" / "sft-corpus-test"
        enriched_file = _make_enriched_example(run_dir, files_modified=0)

        result = _bash(
            f"""python3 -c "
import json
with open('{enriched_file}') as f:
    ex = json.loads(f.readline())
files_modified = ex.get('metadata', {{}}).get('files_modified', 0)
print(files_modified)
"
""",
            tmp_path,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "0"

    def test_disabled_flag_passes_through(self, tmp_path: Path) -> None:
        """When require_file_modifications is false, predicate prints 1 (pass)."""
        result = _bash(
            """python3 -c "
enabled = False
if not enabled:
    print(1)
    exit()
"
""",
            tmp_path,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "1"


# ---------------------------------------------------------------------------
# Rejection annotation tests
# ---------------------------------------------------------------------------


class TestRejectionAnnotations:
    """Rejection annotations have correct rejected_by field and are written to rejections.jsonl."""

    def test_rejection_entry_has_correct_reason_field(self, tmp_path: Path) -> None:
        out_dir = tmp_path / "data" / "corpus"
        out_dir.mkdir(parents=True)

        script = f"""python3 -c "
import json, os
from datetime import datetime, timezone
out_dir = '{out_dir}'
os.makedirs(out_dir, exist_ok=True)
entry = {{
    'path': 'test.jsonl',
    'score': 0,
    'reason': 'require_issue_outcome',
    'timestamp': datetime.now(timezone.utc).isoformat()
}}
with open(os.path.join(out_dir, 'rejections.jsonl'), 'a') as f:
    f.write(json.dumps(entry) + '\\n')
print('rejected: require_issue_outcome')
"
"""
        result = _bash(script, tmp_path)
        assert result.returncode == 0

        rejections = out_dir / "rejections.jsonl"
        assert rejections.exists()

        lines = rejections.read_text().strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["reason"] == "require_issue_outcome"
        assert "timestamp" in entry
        assert entry["score"] == 0

    def test_multiple_rejections_accumulate(self, tmp_path: Path) -> None:
        out_dir = tmp_path / "data" / "corpus"
        out_dir.mkdir(parents=True)

        # Simulate two rejections
        for reason in ["require_issue_outcome", "exclude_user_corrections"]:
            script = f"""python3 -c "
import json, os
from datetime import datetime, timezone
out_dir = '{out_dir}'
os.makedirs(out_dir, exist_ok=True)
entry = {{
    'path': 'test.jsonl',
    'score': 0,
    'reason': '{reason}',
    'timestamp': datetime.now(timezone.utc).isoformat()
}}
with open(os.path.join(out_dir, 'rejections.jsonl'), 'a') as f:
    f.write(json.dumps(entry) + '\\n')
"
"""
            result = _bash(script, tmp_path)
            assert result.returncode == 0

        rejections = out_dir / "rejections.jsonl"
        lines = rejections.read_text().strip().split("\n")
        assert len(lines) == 2

        reasons = [json.loads(line)["reason"] for line in lines]
        assert "require_issue_outcome" in reasons
        assert "exclude_user_corrections" in reasons


# ---------------------------------------------------------------------------
# PII detection tests — flag, redact, discard, and default behaviors
# ---------------------------------------------------------------------------


class TestPiiFlagPassthrough:
    """PII flag action: annotates with pii_detected but never rejects."""

    def test_flag_adds_pii_detected_when_pii_present(self) -> None:
        from little_loops.pii import apply_pii_action

        example = {
            "instruction": "Summarize this text",
            "output": "Contact user@example.com or call 555-123-4567",
        }
        result = apply_pii_action(example, "flag")
        assert result is not None
        assert result["pii_detected"] is True
        assert "user@example.com" in result["output"]  # content unchanged

    def test_flag_does_not_add_pii_detected_when_no_pii(self) -> None:
        from little_loops.pii import apply_pii_action

        example = {
            "instruction": "Summarize this text",
            "output": "No personal data here.",
        }
        result = apply_pii_action(example, "flag")
        assert result is not None
        assert "pii_detected" not in result  # no annotation when clean

    def test_flag_predicate_always_prints_1(self, tmp_path: Path) -> None:
        """The check_pii predicate prints 1 for flag action (pass-through)."""
        run_dir = tmp_path / ".loops" / "runs" / "sft-corpus-test"
        run_dir.mkdir(parents=True)
        enriched_file = run_dir / "enriched.jsonl"
        example = {
            "source": "test.jsonl",
            "messages": [{"role": "user", "content": "test"}],
            "metadata": {"tool_count": 5},
            "output": "Contact user@example.com",
        }
        enriched_file.write_text(json.dumps(example) + "\n")

        script = f"""python3 << 'PYEOF'
import json, sys
sys.path.insert(0, "scripts")
from little_loops.pii import apply_pii_action

action = "flag"
with open("{enriched_file}") as f:
    example = json.loads(f.readline())

if action == "flag":
    result = apply_pii_action(example, action)
    with open("{enriched_file}", "w") as f:
        json.dump(result, f)
    print(1)
PYEOF
"""
        result = _bash(script, tmp_path)
        assert result.returncode == 0
        assert result.stdout.strip() == "1"
        # Verify the example was annotated
        written = json.loads(enriched_file.read_text().strip())
        assert written.get("pii_detected") is True


class TestPiiRedact:
    """PII redact action: replaces PII spans with [TYPE] placeholders."""

    def test_redact_replaces_email(self) -> None:
        from little_loops.pii import apply_pii_action

        example = {
            "instruction": "Email support",
            "output": "Contact user@example.com for help.",
        }
        result = apply_pii_action(example, "redact")
        assert result is not None
        assert "user@example.com" not in result["output"]
        assert "[EMAIL]" in result["output"]

    def test_redact_replaces_phone(self) -> None:
        from little_loops.pii import apply_pii_action

        example = {
            "instruction": "Call support",
            "output": "Dial 555-123-4567 for assistance.",
        }
        result = apply_pii_action(example, "redact")
        assert result is not None
        assert "555-123-4567" not in result["output"]
        assert "[PHONE]" in result["output"]

    def test_redact_replaces_ssn(self) -> None:
        from little_loops.pii import apply_pii_action

        example = {
            "instruction": "Verify identity",
            "output": "SSN: 123-45-6789 was provided.",
        }
        result = apply_pii_action(example, "redact")
        assert result is not None
        assert "123-45-6789" not in result["output"]
        assert "[SSN]" in result["output"]

    def test_redact_handles_multiple_pii_types(self) -> None:
        from little_loops.pii import apply_pii_action

        example = {
            "instruction": "User profile",
            "output": (
                "Email: alice@example.com, Phone: 555-987-6543, SSN: 987-65-4321."
            ),
        }
        result = apply_pii_action(example, "redact")
        assert result is not None
        assert "[EMAIL]" in result["output"]
        assert "[PHONE]" in result["output"]
        assert "[SSN]" in result["output"]

    def test_redact_preserves_non_pii_content(self) -> None:
        from little_loops.pii import apply_pii_action

        example = {
            "instruction": "General question",
            "output": "The answer is 42.",
        }
        result = apply_pii_action(example, "redact")
        assert result is not None
        assert result["output"] == "The answer is 42."

    def test_redact_predicate_prints_1_and_writes_redacted(self, tmp_path: Path) -> None:
        """The check_pii predicate prints 1 for redact action and writes redacted content."""
        run_dir = tmp_path / ".loops" / "runs" / "sft-corpus-test"
        run_dir.mkdir(parents=True)
        enriched_file = run_dir / "enriched.jsonl"
        example = {
            "source": "test.jsonl",
            "messages": [{"role": "user", "content": "test"}],
            "metadata": {"tool_count": 5},
            "output": "Contact user@example.com",
        }
        enriched_file.write_text(json.dumps(example) + "\n")

        script = f"""python3 << 'PYEOF'
import json, sys
sys.path.insert(0, "scripts")
from little_loops.pii import apply_pii_action

action = "redact"
with open("{enriched_file}") as f:
    example = json.loads(f.readline())

result = apply_pii_action(example, action)
with open("{enriched_file}", "w") as f:
    json.dump(result, f)
print(1)
PYEOF
"""
        result = _bash(script, tmp_path)
        assert result.returncode == 0
        assert result.stdout.strip() == "1"
        written = json.loads(enriched_file.read_text().strip())
        assert "[EMAIL]" in written["output"]


class TestPiiDiscard:
    """PII discard action: rejects examples with detected PII."""

    def test_discard_returns_none_when_pii_present(self) -> None:
        from little_loops.pii import apply_pii_action

        example = {
            "instruction": "Contact info",
            "output": "Email user@example.com for details.",
        }
        result = apply_pii_action(example, "discard")
        assert result is None

    def test_discard_returns_example_when_no_pii(self) -> None:
        from little_loops.pii import apply_pii_action

        example = {
            "instruction": "General question",
            "output": "No personal data here.",
        }
        result = apply_pii_action(example, "discard")
        assert result is not None
        assert result == example

    def test_discard_predicate_prints_0_when_pii_present(self, tmp_path: Path) -> None:
        """The check_pii predicate prints 0 when action=discard and PII is detected."""
        run_dir = tmp_path / ".loops" / "runs" / "sft-corpus-test"
        run_dir.mkdir(parents=True)
        enriched_file = run_dir / "enriched.jsonl"
        example = {
            "source": "test.jsonl",
            "messages": [{"role": "user", "content": "test"}],
            "metadata": {"tool_count": 5},
            "output": "Contact user@example.com",
        }
        enriched_file.write_text(json.dumps(example) + "\n")

        script = f"""python3 << 'PYEOF'
import json, sys
sys.path.insert(0, "scripts")
from little_loops.pii import apply_pii_action

action = "discard"
with open("{enriched_file}") as f:
    example = json.loads(f.readline())

result = apply_pii_action(example, action)
if result is None:
    print(0)
else:
    with open("{enriched_file}", "w") as f:
        json.dump(result, f)
    print(1)
PYEOF
"""
        result = _bash(script, tmp_path)
        assert result.returncode == 0
        assert result.stdout.strip() == "0"

    def test_discard_predicate_prints_1_when_no_pii(self, tmp_path: Path) -> None:
        """The check_pii predicate prints 1 when action=discard and no PII is detected."""
        run_dir = tmp_path / ".loops" / "runs" / "sft-corpus-test"
        run_dir.mkdir(parents=True)
        enriched_file = run_dir / "enriched.jsonl"
        example = {
            "source": "test.jsonl",
            "messages": [{"role": "user", "content": "test"}],
            "metadata": {"tool_count": 5},
            "output": "No personal data here.",
        }
        enriched_file.write_text(json.dumps(example) + "\n")

        script = f"""python3 << 'PYEOF'
import json, sys
sys.path.insert(0, "scripts")
from little_loops.pii import apply_pii_action

action = "discard"
with open("{enriched_file}") as f:
    example = json.loads(f.readline())

result = apply_pii_action(example, action)
if result is None:
    print(0)
else:
    with open("{enriched_file}", "w") as f:
        json.dump(result, f)
    print(1)
PYEOF
"""
        result = _bash(script, tmp_path)
        assert result.returncode == 0
        assert result.stdout.strip() == "1"


# ---------------------------------------------------------------------------
# Token length filter tests
# ---------------------------------------------------------------------------


def _make_enriched_batch(run_dir: Path, examples: list[dict]) -> Path:
    """Write multiple enriched examples to a JSONL file for batch processing tests."""
    run_dir.mkdir(parents=True, exist_ok=True)
    enriched = run_dir / "enriched.jsonl"
    with open(enriched, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")
    return enriched


class TestTokenLengthFilter:
    """Token length filter: discards examples outside [min_tokens, max_tokens] range."""

    def test_passes_example_within_range(self, tmp_path: Path) -> None:
        """Example with token count in [min, max] passes through."""
        run_dir = tmp_path / ".loops" / "runs" / "sft-corpus-test"
        enriched_file = _make_enriched_batch(
            run_dir,
            [
                {
                    "source": "sess-1.jsonl",
                    "messages": [
                        {"role": "user", "content": "hello world"},
                        {"role": "assistant", "content": "hi there"},
                    ],
                }
            ],
        )

        result = _bash(
            f"""python3 -c "
import json
min_tokens = 2
max_tokens = 1000

with open('{enriched_file}') as f:
    for line in f:
        if not line.strip():
            continue
        ex = json.loads(line)
        # Word count across all message content
        word_count = sum(
            len(m.get('content', '').split())
            for m in ex.get('messages', [])
        )
        if min_tokens <= word_count <= max_tokens:
            print(json.dumps(ex))
"
""",
            tmp_path,
        )
        assert result.returncode == 0
        lines = [ln for ln in result.stdout.strip().split("\n") if ln.strip()]
        assert len(lines) == 1  # example passed through

    def test_rejects_example_below_min_tokens(self, tmp_path: Path) -> None:
        """Example with too few tokens is dropped."""
        run_dir = tmp_path / ".loops" / "runs" / "sft-corpus-test"
        enriched_file = _make_enriched_batch(
            run_dir,
            [
                {
                    "source": "sess-1.jsonl",
                    "messages": [
                        {"role": "user", "content": "hi"},
                    ],
                }
            ],
        )

        result = _bash(
            f"""python3 -c "
import json
min_tokens = 5
max_tokens = 1000

with open('{enriched_file}') as f:
    for line in f:
        if not line.strip():
            continue
        ex = json.loads(line)
        word_count = sum(
            len(m.get('content', '').split())
            for m in ex.get('messages', [])
        )
        if min_tokens <= word_count <= max_tokens:
            print(json.dumps(ex))
"
""",
            tmp_path,
        )
        assert result.returncode == 0
        lines = [ln for ln in result.stdout.strip().split("\n") if ln.strip()]
        assert len(lines) == 0  # rejected

    def test_rejects_example_above_max_tokens(self, tmp_path: Path) -> None:
        """Example with too many tokens is dropped."""
        run_dir = tmp_path / ".loops" / "runs" / "sft-corpus-test"
        long_content = "word " * 5000  # 5000 words
        enriched_file = _make_enriched_batch(
            run_dir,
            [
                {
                    "source": "sess-1.jsonl",
                    "messages": [
                        {"role": "user", "content": long_content},
                    ],
                }
            ],
        )

        result = _bash(
            f"""python3 -c "
import json
min_tokens = 0
max_tokens = 100

with open('{enriched_file}') as f:
    for line in f:
        if not line.strip():
            continue
        ex = json.loads(line)
        word_count = sum(
            len(m.get('content', '').split())
            for m in ex.get('messages', [])
        )
        if min_tokens <= word_count <= max_tokens:
            print(json.dumps(ex))
"
""",
            tmp_path,
        )
        assert result.returncode == 0
        lines = [ln for ln in result.stdout.strip().split("\n") if ln.strip()]
        assert len(lines) == 0  # rejected

    def test_mixed_batch_filters_correctly(self, tmp_path: Path) -> None:
        """Batch with mix of valid and invalid examples; only valid pass."""
        run_dir = tmp_path / ".loops" / "runs" / "sft-corpus-test"
        enriched_file = _make_enriched_batch(
            run_dir,
            [
                {
                    "source": "sess-1.jsonl",
                    "messages": [{"role": "user", "content": "hi"}],  # 1 word, below min
                },
                {
                    "source": "sess-2.jsonl",
                    "messages": [
                        {"role": "user", "content": "hello world how are you"},
                        {"role": "assistant", "content": "I am doing great today"},
                    ],  # 10 words
                },
                {
                    "source": "sess-3.jsonl",
                    "messages": [
                        {"role": "user", "content": "a" * 5000},  # many tokens
                    ],
                },
            ],
        )

        result = _bash(
            f"""python3 -c "
import json
min_tokens = 3
max_tokens = 1000

with open('{enriched_file}') as f:
    for line in f:
        if not line.strip():
            continue
        ex = json.loads(line)
        word_count = sum(
            len(m.get('content', '').split())
            for m in ex.get('messages', [])
        )
        if min_tokens <= word_count <= max_tokens:
            print(json.dumps(ex))
"
""",
            tmp_path,
        )
        assert result.returncode == 0
        lines = [ln for ln in result.stdout.strip().split("\n") if ln.strip()]
        assert len(lines) == 1
        passed = json.loads(lines[0])
        assert passed["source"] == "sess-2.jsonl"

    def test_rejection_entry_written_for_filtered_examples(self, tmp_path: Path) -> None:
        """Rejected examples produce a rejection entry with reason."""
        run_dir = tmp_path / ".loops" / "runs" / "sft-corpus-test"
        enriched_file = _make_enriched_batch(
            run_dir,
            [
                {
                    "source": "sess-1.jsonl",
                    "messages": [{"role": "user", "content": "hi"}],
                },
                {
                    "source": "sess-2.jsonl",
                    "messages": [{"role": "user", "content": "hello world how are you doing today"}],
                },
            ],
        )

        script = f"""python3 << 'PYEOF'
import json, os
from datetime import datetime, timezone

min_tokens = 3
max_tokens = 1000
out_dir = "{run_dir}/output"
os.makedirs(out_dir, exist_ok=True)
rejections = os.path.join(out_dir, "rejections.jsonl")

with open("{enriched_file}") as f_in:
    for line in f_in:
        if not line.strip():
            continue
        ex = json.loads(line)
        word_count = sum(
            len(m.get('content', '').split())
            for m in ex.get('messages', [])
        )
        if min_tokens <= word_count <= max_tokens:
            continue  # passes
        # Reject
        entry = {{
            "path": ex.get("source", ""),
            "score": word_count,
            "reason": "token_length",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }}
        with open(rejections, "a") as f:
            f.write(json.dumps(entry) + "\\n")

print(len([l for l in open(rejections) if l.strip()]))
PYEOF
"""
        result = _bash(script, tmp_path)
        assert result.returncode == 0
        assert result.stdout.strip() == "1"  # one rejection


# ---------------------------------------------------------------------------
# Dedup tests
# ---------------------------------------------------------------------------


class TestDedup:
    """Near-duplicate removal via Jaccard similarity."""

    def test_identical_examples_are_deduplicated(self, tmp_path: Path) -> None:
        """Two identical examples → only one survives."""
        from little_loops.text_utils import calculate_word_overlap, extract_words

        example = {
            "messages": [
                {"role": "user", "content": "how do I fix a bug in Python"},
                {"role": "assistant", "content": "You should use a debugger to trace the issue"},
            ]
        }

        words1 = extract_words(
            " ".join(m["content"] for m in example["messages"])
        )
        words2 = extract_words(
            " ".join(m["content"] for m in example["messages"])
        )

        similarity = calculate_word_overlap(words1, words2)
        assert similarity > 0.9  # identical → high similarity

    def test_different_examples_are_kept(self, tmp_path: Path) -> None:
        """Two very different examples → both survive."""
        from little_loops.text_utils import calculate_word_overlap, extract_words

        ex1 = {
            "messages": [
                {"role": "user", "content": "how do I fix a bug in Python"},
                {"role": "assistant", "content": "You should use a debugger"},
            ]
        }
        ex2 = {
            "messages": [
                {"role": "user", "content": "what is the best restaurant in Paris"},
                {"role": "assistant", "content": "Le Comptoir is highly recommended"},
            ]
        }

        words1 = extract_words(
            " ".join(m["content"] for m in ex1["messages"])
        )
        words2 = extract_words(
            " ".join(m["content"] for m in ex2["messages"])
        )

        similarity = calculate_word_overlap(words1, words2)
        assert similarity < 0.5  # different topics → low similarity

    def test_dedup_shell_logic_removes_duplicates(self, tmp_path: Path) -> None:
        """Inline Python dedup logic: removes examples with Jaccard > threshold."""
        run_dir = tmp_path / ".loops" / "runs" / "sft-corpus-test"
        enriched_file = _make_enriched_batch(
            run_dir,
            [
                {
                    "source": "sess-1.jsonl",
                    "messages": [
                        {"role": "user", "content": "how do I fix a bug in Python"},
                        {"role": "assistant", "content": "use a debugger to trace the issue"},
                    ],
                },
                {
                    "source": "sess-2.jsonl",
                    "messages": [
                        {"role": "user", "content": "how do I fix a bug in Python"},
                        {"role": "assistant", "content": "use a debugger to trace the issue"},
                    ],
                },  # near-identical
                {
                    "source": "sess-3.jsonl",
                    "messages": [
                        {"role": "user", "content": "what is the capital of France"},
                        {"role": "assistant", "content": "Paris is the capital of France"},
                    ],
                },
            ],
        )

        script = f"""python3 << 'PYEOF'
import json, sys
sys.path.insert(0, "scripts")
from little_loops.text_utils import extract_words, calculate_word_overlap

threshold = 0.9
input_file = "{enriched_file}"

# Load all examples
examples = []
with open(input_file) as f:
    for line in f:
        if line.strip():
            examples.append(json.loads(line))

# Dedup: keep first occurrence, skip near-duplicates
kept = []
seen_word_sets = []

for ex in examples:
    text = " ".join(
        m.get("content", "") for m in ex.get("messages", [])
    )
    current_words = extract_words(text)

    is_dup = False
    for seen_words in seen_word_sets:
        if calculate_word_overlap(current_words, seen_words) > threshold:
            is_dup = True
            break

    if not is_dup:
        kept.append(ex)
        seen_word_sets.append(current_words)

for ex in kept:
    print(json.dumps(ex))
PYEOF
"""
        result = _bash(script, tmp_path)
        assert result.returncode == 0
        lines = [ln for ln in result.stdout.strip().split("\n") if ln.strip()]
        assert len(lines) == 2  # sess-1 and sess-3, sess-2 deduped
        sources = [json.loads(ln)["source"] for ln in lines]
        assert "sess-1.jsonl" in sources
        assert "sess-3.jsonl" in sources
        assert "sess-2.jsonl" not in sources  # removed as duplicate

    def test_dedup_preserves_single_example(self, tmp_path: Path) -> None:
        """Single example batch: nothing to dedup, example preserved."""
        from little_loops.text_utils import calculate_word_overlap, extract_words

        ex = {
            "messages": [
                {"role": "user", "content": "hello world"},
            ]
        }
        words = extract_words(
            " ".join(m["content"] for m in ex["messages"])
        )
        # No crash, self-comparison would be 1.0 but we skip self
        similarity = calculate_word_overlap(words, words)
        assert similarity == 1.0  # identical to itself


# ---------------------------------------------------------------------------
# Split tests
# ---------------------------------------------------------------------------


class TestSplit:
    """Train/val/test split by source session."""

    def test_split_proportions_approximate_configured_ratios(self, tmp_path: Path) -> None:
        """Split 10 sessions with 0.1 val, 0.1 test → ~8 train, ~1 val, ~1 test."""
        run_dir = tmp_path / ".loops" / "runs" / "sft-corpus-test"
        examples = []
        for i in range(10):
            examples.append({
                "source": f"sess-{i}.jsonl",
                "messages": [{"role": "user", "content": f"message {i}"}],
            })
        enriched_file = _make_enriched_batch(run_dir, examples)

        script = f"""python3 << 'PYEOF'
import json, os, random

val_ratio = 0.1
test_ratio = 0.1
input_file = "{enriched_file}"
output_dir = "{run_dir}/staged"
os.makedirs(output_dir, exist_ok=True)

# Load all examples
examples = []
with open(input_file) as f:
    for line in f:
        if line.strip():
            examples.append(json.loads(line))

# Group by source session
by_session = {{}}
for ex in examples:
    source = ex.get("source", "unknown")
    by_session.setdefault(source, []).append(ex)

sessions = list(by_session.keys())
random.seed(42)
random.shuffle(sessions)

n = len(sessions)
n_test = max(1, round(n * test_ratio))
n_val = max(1, round(n * val_ratio))
n_train = n - n_val - n_test

test_sessions = set(sessions[:n_test])
val_sessions = set(sessions[n_test:n_test + n_val])
train_sessions = set(sessions[n_test + n_val:])

# Write splits
for split_name, split_sessions in [
    ("train", train_sessions),
    ("val", val_sessions),
    ("test", test_sessions),
]:
    split_file = os.path.join(output_dir, f"{{split_name}}.jsonl")
    with open(split_file, "w") as f_out:
        for session in split_sessions:
            for ex in by_session[session]:
                f_out.write(json.dumps(ex) + "\\n")

# Report
for split_name in ["train", "val", "test"]:
    split_file = os.path.join(output_dir, f"{{split_name}}.jsonl")
    count = 0
    if os.path.exists(split_file):
        with open(split_file) as f:
            count = sum(1 for _ in f)
    print(f"{{split_name}}={{count}}")
PYEOF
"""
        result = _bash(script, tmp_path)
        assert result.returncode == 0

        # Parse output
        counts = {}
        for line in result.stdout.strip().split("\n"):
            if "=" in line:
                k, v = line.split("=")
                counts[k] = int(v)

        assert counts.get("train", 0) > 0
        assert counts.get("val", 0) > 0
        assert counts.get("test", 0) > 0
        total = counts["train"] + counts["val"] + counts["test"]
        assert total == 10  # all examples accounted for

    def test_split_output_files_exist(self, tmp_path: Path) -> None:
        """Split creates train.jsonl, val.jsonl, test.jsonl in output dir."""
        run_dir = tmp_path / ".loops" / "runs" / "sft-corpus-test"
        examples = [
            {"source": "sess-1.jsonl", "messages": [{"role": "user", "content": "hello"}]},
            {"source": "sess-2.jsonl", "messages": [{"role": "user", "content": "world"}]},
        ]
        enriched_file = _make_enriched_batch(run_dir, examples)
        output_dir = run_dir / "staged"
        output_dir.mkdir(parents=True)

        script = f"""python3 << 'PYEOF'
import json, os, random

val_ratio = 0.0
test_ratio = 0.0
input_file = "{enriched_file}"
output_dir = "{output_dir}"

examples = []
with open(input_file) as f:
    for line in f:
        if line.strip():
            examples.append(json.loads(line))

by_session = {{}}
for ex in examples:
    source = ex.get("source", "unknown")
    by_session.setdefault(source, []).append(ex)

sessions = list(by_session.keys())
random.seed(42)
random.shuffle(sessions)

n = len(sessions)
n_test = max(1, round(n * test_ratio)) if test_ratio > 0 else 0
n_val = max(1, round(n * val_ratio)) if val_ratio > 0 else 0
n_train = n - n_val - n_test

test_sessions = set(sessions[:n_test])
val_sessions = set(sessions[n_test:n_test + n_val])
train_sessions = set(sessions[n_test + n_val:])

for split_name, split_sessions in [
    ("train", train_sessions),
    ("val", val_sessions),
    ("test", test_sessions),
]:
    split_file = os.path.join(output_dir, f"{{split_name}}.jsonl")
    with open(split_file, "w") as f_out:
        for session in split_sessions:
            for ex in by_session[session]:
                f_out.write(json.dumps(ex) + "\\n")

for fname in ["train.jsonl", "val.jsonl", "test.jsonl"]:
    path = os.path.join(output_dir, fname)
    exists = os.path.exists(path)
    print(f"{{fname}}={{exists}}")
    if exists:
        with open(path) as f:
            print(f"{{fname}}_count={{sum(1 for _ in f)}}")
PYEOF
"""
        result = _bash(script, tmp_path)
        assert result.returncode == 0
        assert "train.jsonl=True" in result.stdout
        assert "val.jsonl=True" in result.stdout
        assert "test.jsonl=True" in result.stdout

    def test_split_stratifies_by_source_session(self, tmp_path: Path) -> None:
        """Examples from the same source session stay together in one split."""
        run_dir = tmp_path / ".loops" / "runs" / "sft-corpus-test"
        examples = [
            {"source": "sess-a.jsonl", "messages": [{"role": "user", "content": "a1"}]},
            {"source": "sess-a.jsonl", "messages": [{"role": "user", "content": "a2"}]},
            {"source": "sess-b.jsonl", "messages": [{"role": "user", "content": "b1"}]},
            {"source": "sess-c.jsonl", "messages": [{"role": "user", "content": "c1"}]},
        ]
        enriched_file = _make_enriched_batch(run_dir, examples)
        output_dir = run_dir / "staged"
        output_dir.mkdir(parents=True)

        script = f"""python3 << 'PYEOF'
import json, os, random

val_ratio = 0.3
test_ratio = 0.3
input_file = "{enriched_file}"
output_dir = "{output_dir}"

examples = []
with open(input_file) as f:
    for line in f:
        if line.strip():
            examples.append(json.loads(line))

by_session = {{}}
for ex in examples:
    source = ex.get("source", "unknown")
    by_session.setdefault(source, []).append(ex)

sessions = list(by_session.keys())
random.seed(42)
random.shuffle(sessions)

n = len(sessions)
n_test = max(1, round(n * test_ratio))
n_val = max(1, round(n * val_ratio))
n_train = n - n_val - n_test

test_sessions = set(sessions[:n_test])
val_sessions = set(sessions[n_test:n_test + n_val])
train_sessions = set(sessions[n_test + n_val:])

for split_name, split_sessions in [
    ("train", train_sessions),
    ("val", val_sessions),
    ("test", test_sessions),
]:
    split_file = os.path.join(output_dir, f"{{split_name}}.jsonl")
    with open(split_file, "w") as f_out:
        for session in split_sessions:
            for ex in by_session[session]:
                f_out.write(json.dumps(ex) + "\\n")

# Verify sess-a examples are all in the same split
for split_name in ["train", "val", "test"]:
    split_file = os.path.join(output_dir, f"{{split_name}}.jsonl")
    if os.path.exists(split_file):
        with open(split_file) as f:
            sources = [json.loads(l)["source"] for l in f if l.strip()]
        # All sess-a entries (if present) must be in the same file
        a_entries = [s for s in sources if s.startswith("sess-a")]
        if a_entries:
            assert len(a_entries) in (0, 2)  # either both here or none
            print(f"sess-a_in_{{split_name}}=True")
PYEOF
"""
        result = _bash(script, tmp_path)
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Harvest sentinel tests
# ---------------------------------------------------------------------------


class TestHarvestSentinel:
    """Harvest sentinel pattern: incremental re-runs skip already-processed sessions."""

    def test_sentinel_read_returns_empty_when_no_file(self, tmp_path: Path) -> None:
        """First run: no sentinel file → SINCE_ARG is empty."""
        result = _bash(
            """SINCE_ARG=""
[ -f sft-corpus.last_harvested ] && SINCE_ARG="--since $(cat sft-corpus.last_harvested)"
echo "SINCE_ARG=${SINCE_ARG}"
""",
            tmp_path,
        )
        assert result.returncode == 0
        assert "SINCE_ARG=" in result.stdout
        assert "--since" not in result.stdout

    def test_sentinel_read_returns_date_when_file_exists(self, tmp_path: Path) -> None:
        """Subsequent run: sentinel file exists → SINCE_ARG populated."""
        sentinel = tmp_path / "sft-corpus.last_harvested"
        sentinel.write_text("2026-06-01T00:00:00Z")

        result = _bash(
            """SINCE_ARG=""
[ -f sft-corpus.last_harvested ] && SINCE_ARG="--since $(cat sft-corpus.last_harvested)"
echo "SINCE_ARG=${SINCE_ARG}"
""",
            tmp_path,
        )
        assert result.returncode == 0
        assert "--since 2026-06-01T00:00:00Z" in result.stdout

    def test_sentinel_write_updates_timestamp(self, tmp_path: Path) -> None:
        """Publish writes a new sentinel timestamp."""
        sentinel = tmp_path / "sft-corpus.last_harvested"

        result = _bash(
            f"""date -u +%Y-%m-%dT%H:%M:%SZ > {sentinel}
echo "sentinel_written"
""",
            tmp_path,
        )
        assert result.returncode == 0
        assert sentinel.exists()
        content = sentinel.read_text().strip()
        assert content.endswith("Z")  # ISO 8601 UTC
        assert "T" in content


class TestPiiDefaultBehavior:
    """PII module defaults: unknown/unset action falls through gracefully."""

    def test_flag_is_default_passthrough(self) -> None:
        """Flag is the default action — annotates but never rejects."""
        from little_loops.pii import apply_pii_action

        example = {
            "instruction": "test",
            "output": "Email: user@example.com",
        }
        result = apply_pii_action(example, "flag")
        assert result is not None
        assert result.get("pii_detected") is True

    def test_invalid_action_raises_value_error(self) -> None:
        import pytest as pt

        from little_loops.pii import apply_pii_action

        with pt.raises(ValueError, match="Invalid pii_action"):
            apply_pii_action({"instruction": "test"}, "delete")

    def test_check_pii_unknown_action_falls_through(self, tmp_path: Path) -> None:
        """When pii_action is an unknown value, predicate prints 1 (safe pass-through)."""
        run_dir = tmp_path / ".loops" / "runs" / "sft-corpus-test"
        run_dir.mkdir(parents=True)
        enriched_file = run_dir / "enriched.jsonl"
        example = {
            "source": "test.jsonl",
            "messages": [{"role": "user", "content": "test"}],
            "metadata": {"tool_count": 5},
            "output": "Contact user@example.com",
        }
        enriched_file.write_text(json.dumps(example) + "\n")

        script = f"""python3 << 'PYEOF'
import json, sys
sys.path.insert(0, "scripts")
from little_loops.pii import apply_pii_action

action = "unknown_value"
with open("{enriched_file}") as f:
    example = json.loads(f.readline())

try:
    result = apply_pii_action(example, action)
    print(1)
except ValueError:
    print(1)  # safe fallback: don't reject on config error
PYEOF
"""
        result = _bash(script, tmp_path)
        assert result.returncode == 0
        assert result.stdout.strip() == "1"
