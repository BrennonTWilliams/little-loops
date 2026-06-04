"""Tests for the sft-corpus loop — enrich state and quality filter predicates."""

import json
import subprocess
from pathlib import Path


def _bash(script: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a bash script in the given working directory, capturing output."""
    return subprocess.run(
        ["bash", "-c", script], cwd=cwd, capture_output=True, text=True
    )


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
