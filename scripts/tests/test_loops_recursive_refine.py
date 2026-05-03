"""Tests for recursive-refine depth-cap behavior (ENH-1347) and cycle detection (ENH-1338).

Tests the depth-tracking and cycle-detection bash/python logic for parse_input,
dequeue_next, check_depth, enqueue_children / enqueue_or_skip, and done states by
executing shell snippets directly against a tmp_path environment.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


def _bash(script: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", "-c", script], cwd=cwd, capture_output=True, text=True)


class TestDepthMapInit:
    """parse_input depth-map initialization."""

    def test_root_ids_written_at_depth_zero(self, tmp_path: Path) -> None:
        """parse_input writes all root IDs to depth-map at depth 0."""
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)
        (loops_tmp / "recursive-refine-queue.txt").write_text("ENH-001\nENH-002\n")

        _bash(
            r"""
            while IFS= read -r id; do echo "$id 0"; done \
              < .loops/tmp/recursive-refine-queue.txt \
              > .loops/tmp/recursive-refine-depth-map.txt
            > .loops/tmp/recursive-refine-skipped-depth.txt
            """,
            tmp_path,
        )

        depth_map = (loops_tmp / "recursive-refine-depth-map.txt").read_text()
        assert "ENH-001 0" in depth_map
        assert "ENH-002 0" in depth_map

    def test_skipped_depth_file_is_cleared(self, tmp_path: Path) -> None:
        """parse_input clears any stale recursive-refine-skipped-depth.txt."""
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)
        (loops_tmp / "recursive-refine-queue.txt").write_text("ENH-001\n")
        (loops_tmp / "recursive-refine-skipped-depth.txt").write_text("stale-entry\n")

        _bash(
            r"""
            while IFS= read -r id; do echo "$id 0"; done \
              < .loops/tmp/recursive-refine-queue.txt \
              > .loops/tmp/recursive-refine-depth-map.txt
            > .loops/tmp/recursive-refine-skipped-depth.txt
            """,
            tmp_path,
        )

        assert (loops_tmp / "recursive-refine-skipped-depth.txt").read_text() == ""


class TestParseInputDedup:
    """parse_input deduplication of comma-separated input."""

    def test_duplicate_ids_written_once_to_queue(self, tmp_path: Path) -> None:
        """parse_input deduplicates the comma-split queue via sort -u."""
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)

        _bash(
            r"""
            INPUT="ENH-001,ENH-002,ENH-001,ENH-003,ENH-002"
            mkdir -p .loops/tmp
            printf '' > .loops/tmp/recursive-refine-visited.txt
            echo "$INPUT" | tr ',' '\n' \
              | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' \
              | grep -v '^[[:space:]]*$' \
              | sort -u \
              > .loops/tmp/recursive-refine-queue.txt
            """,
            tmp_path,
        )

        queue = (loops_tmp / "recursive-refine-queue.txt").read_text()
        lines = [ln for ln in queue.splitlines() if ln.strip()]
        assert lines.count("ENH-001") == 1
        assert lines.count("ENH-002") == 1
        assert lines.count("ENH-003") == 1
        assert len(lines) == 3

    def test_visited_file_created_empty_by_parse_input(self, tmp_path: Path) -> None:
        """parse_input creates (or clears) recursive-refine-visited.txt for the new run."""
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)
        (loops_tmp / "recursive-refine-visited.txt").write_text("stale-entry\n")

        _bash(
            r"""
            printf '' > .loops/tmp/recursive-refine-visited.txt
            """,
            tmp_path,
        )

        assert (loops_tmp / "recursive-refine-visited.txt").read_text() == ""


class TestDequeueDepth:
    """dequeue_next depth lookup."""

    def test_writes_depth_from_map_to_current_depth_file(self, tmp_path: Path) -> None:
        """dequeue_next reads depth from depth-map and writes to recursive-refine-current-depth.txt."""
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)
        (loops_tmp / "recursive-refine-queue.txt").write_text("ENH-010\n")
        (loops_tmp / "recursive-refine-depth-map.txt").write_text("ENH-010 1\n")

        result = _bash(
            r"""
            CURRENT=$(head -1 .loops/tmp/recursive-refine-queue.txt)
            tail -n +2 .loops/tmp/recursive-refine-queue.txt \
              > .loops/tmp/recursive-refine-queue.tmp
            mv .loops/tmp/recursive-refine-queue.tmp .loops/tmp/recursive-refine-queue.txt
            DEPTH=$(grep "^$CURRENT " .loops/tmp/recursive-refine-depth-map.txt 2>/dev/null \
              | awk '{print $2}')
            printf '%s' "${DEPTH:-0}" > .loops/tmp/recursive-refine-current-depth.txt
            echo "$CURRENT"
            """,
            tmp_path,
        )

        assert result.stdout.strip() == "ENH-010"
        assert (loops_tmp / "recursive-refine-current-depth.txt").read_text() == "1"

    def test_defaults_to_zero_when_id_absent_from_map(self, tmp_path: Path) -> None:
        """dequeue_next defaults depth to 0 when issue ID is not in depth-map."""
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)
        (loops_tmp / "recursive-refine-queue.txt").write_text("ENH-999\n")
        (loops_tmp / "recursive-refine-depth-map.txt").write_text("")

        _bash(
            r"""
            CURRENT=$(head -1 .loops/tmp/recursive-refine-queue.txt)
            tail -n +2 .loops/tmp/recursive-refine-queue.txt \
              > .loops/tmp/recursive-refine-queue.tmp
            mv .loops/tmp/recursive-refine-queue.tmp .loops/tmp/recursive-refine-queue.txt
            DEPTH=$(grep "^$CURRENT " .loops/tmp/recursive-refine-depth-map.txt 2>/dev/null \
              | awk '{print $2}')
            printf '%s' "${DEPTH:-0}" > .loops/tmp/recursive-refine-current-depth.txt
            echo "$CURRENT"
            """,
            tmp_path,
        )

        assert (loops_tmp / "recursive-refine-current-depth.txt").read_text() == "0"


class TestVisitedSetAppend:
    """dequeue_next appends dequeued ID to recursive-refine-visited.txt."""

    def test_dequeued_id_appears_in_visited_file(self, tmp_path: Path) -> None:
        """dequeue_next appends current ID to visited.txt on each dequeue."""
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)
        (loops_tmp / "recursive-refine-queue.txt").write_text("ENH-042\n")
        (loops_tmp / "recursive-refine-depth-map.txt").write_text("ENH-042 0\n")
        (loops_tmp / "recursive-refine-visited.txt").write_text("")

        result = _bash(
            r"""
            CURRENT=$(head -1 .loops/tmp/recursive-refine-queue.txt)
            tail -n +2 .loops/tmp/recursive-refine-queue.txt \
              > .loops/tmp/recursive-refine-queue.tmp
            mv .loops/tmp/recursive-refine-queue.tmp .loops/tmp/recursive-refine-queue.txt
            echo "$CURRENT" >> .loops/tmp/recursive-refine-visited.txt
            DEPTH=$(grep "^$CURRENT " .loops/tmp/recursive-refine-depth-map.txt 2>/dev/null \
              | awk '{print $2}')
            printf '%s' "${DEPTH:-0}" > .loops/tmp/recursive-refine-current-depth.txt
            echo "$CURRENT"
            """,
            tmp_path,
        )

        assert result.stdout.strip() == "ENH-042"
        assert "ENH-042" in (loops_tmp / "recursive-refine-visited.txt").read_text()

    def test_multiple_dequeues_accumulate_visited(self, tmp_path: Path) -> None:
        """Each dequeue appends to visited.txt; two dequeues produce two entries."""
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)
        (loops_tmp / "recursive-refine-queue.txt").write_text("ENH-001\nENH-002\n")
        (loops_tmp / "recursive-refine-depth-map.txt").write_text("ENH-001 0\nENH-002 0\n")
        (loops_tmp / "recursive-refine-visited.txt").write_text("")

        _bash(
            r"""
            for _ in 1 2; do
              CURRENT=$(head -1 .loops/tmp/recursive-refine-queue.txt)
              tail -n +2 .loops/tmp/recursive-refine-queue.txt \
                > .loops/tmp/recursive-refine-queue.tmp
              mv .loops/tmp/recursive-refine-queue.tmp .loops/tmp/recursive-refine-queue.txt
              echo "$CURRENT" >> .loops/tmp/recursive-refine-visited.txt
            done
            """,
            tmp_path,
        )

        visited = (loops_tmp / "recursive-refine-visited.txt").read_text()
        assert "ENH-001" in visited
        assert "ENH-002" in visited


def _check_depth_script(current_id: str, max_depth: int = 2) -> str:
    return rf"""
    MAX_DEPTH={max_depth}
    CURRENT_DEPTH=$(cat .loops/tmp/recursive-refine-current-depth.txt 2>/dev/null || echo 0)
    if [ "$CURRENT_DEPTH" -ge "$MAX_DEPTH" ]; then
      echo "{current_id}" >> .loops/tmp/recursive-refine-skipped-depth.txt
      echo "{current_id}" >> .loops/tmp/recursive-refine-skipped.txt
      echo 1
    else
      echo 0
    fi
    """


class TestCheckDepth:
    """check_depth gate state."""

    def _setup(self, tmp_path: Path, depth: int) -> Path:
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True, exist_ok=True)
        (loops_tmp / "recursive-refine-current-depth.txt").write_text(str(depth))
        (loops_tmp / "recursive-refine-skipped-depth.txt").write_text("")
        (loops_tmp / "recursive-refine-skipped.txt").write_text("")
        return loops_tmp

    def test_at_max_depth_echoes_1_and_writes_both_skip_files(self, tmp_path: Path) -> None:
        """Depth == max_depth: echoes 1 and writes ID to both skip files."""
        loops_tmp = self._setup(tmp_path, depth=2)

        result = _bash(_check_depth_script("ENH-999", max_depth=2), tmp_path)

        assert result.stdout.strip() == "1"
        assert "ENH-999" in (loops_tmp / "recursive-refine-skipped-depth.txt").read_text()
        assert "ENH-999" in (loops_tmp / "recursive-refine-skipped.txt").read_text()

    def test_above_max_depth_also_echoes_1(self, tmp_path: Path) -> None:
        """Depth > max_depth is also capped."""
        loops_tmp = self._setup(tmp_path, depth=3)

        result = _bash(_check_depth_script("ENH-888", max_depth=2), tmp_path)

        assert result.stdout.strip() == "1"
        assert "ENH-888" in (loops_tmp / "recursive-refine-skipped-depth.txt").read_text()

    def test_below_max_depth_echoes_0_and_no_skip_writes(self, tmp_path: Path) -> None:
        """Depth < max_depth: echoes 0 and does not write to skip files."""
        loops_tmp = self._setup(tmp_path, depth=1)

        result = _bash(_check_depth_script("ENH-100", max_depth=2), tmp_path)

        assert result.stdout.strip() == "0"
        assert "ENH-100" not in (loops_tmp / "recursive-refine-skipped-depth.txt").read_text()
        assert "ENH-100" not in (loops_tmp / "recursive-refine-skipped.txt").read_text()

    def test_four_level_decomposition_grandchildren_capped(self, tmp_path: Path) -> None:
        """Synthetic 4-level tree with max_depth=2: depth>=2 issues are capped.

        Tree: ROOT(0) → CHILD(1) → GRAND(2) → GREAT(3)
        ROOT and CHILD pass; GRAND and GREAT are depth-capped.
        """
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)
        (loops_tmp / "recursive-refine-skipped-depth.txt").write_text("")
        (loops_tmp / "recursive-refine-skipped.txt").write_text("")

        for issue_id, depth, expected_echo in [
            ("ROOT", 0, "0"),
            ("CHILD", 1, "0"),
            ("GRAND", 2, "1"),
            ("GREAT", 3, "1"),
        ]:
            (loops_tmp / "recursive-refine-current-depth.txt").write_text(str(depth))
            result = _bash(_check_depth_script(issue_id, max_depth=2), tmp_path)
            assert result.stdout.strip() == expected_echo, (
                f"{issue_id} at depth {depth} should echo {expected_echo}"
            )

        depth_skipped = (loops_tmp / "recursive-refine-skipped-depth.txt").read_text()
        assert "GRAND" in depth_skipped
        assert "GREAT" in depth_skipped
        assert "ROOT" not in depth_skipped
        assert "CHILD" not in depth_skipped


def _check_attempt_budget_script(issue_id: str, max_count: int = 5) -> str:
    return rf"""
    python3 << 'PYEOF'
import sys
from pathlib import Path
issue_id = '{issue_id}'
cap = {max_count}
attempts_file = '.loops/tmp/recursive-refine-attempts.txt'
try:
    lines = Path(attempts_file).read_text().splitlines()
except FileNotFoundError:
    lines = []
count = sum(1 for ln in lines if ln.strip() == issue_id)
if count >= cap:
    with open('.loops/tmp/recursive-refine-skipped-budget.txt', 'a') as f:
        f.write(issue_id + '\n')
    with open('.loops/tmp/recursive-refine-skipped.txt', 'a') as f:
        f.write(issue_id + '\n')
    sys.exit(1)
with open(attempts_file, 'a') as f:
    f.write(issue_id + '\n')
sys.exit(0)
PYEOF
    """


class TestCheckAttemptBudget:
    """check_attempt_budget gate state."""

    def _setup(self, tmp_path: Path, attempts: int, issue_id: str = "ENH-001") -> Path:
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True, exist_ok=True)
        content = "\n".join([issue_id] * attempts) + ("\n" if attempts else "")
        (loops_tmp / "recursive-refine-attempts.txt").write_text(content)
        (loops_tmp / "recursive-refine-skipped-budget.txt").write_text("")
        (loops_tmp / "recursive-refine-skipped.txt").write_text("")
        return loops_tmp

    def test_below_cap_exits_0_and_appends_to_attempts(self, tmp_path: Path) -> None:
        """Below cap: exits 0 and appends issue_id to attempts file."""
        loops_tmp = self._setup(tmp_path, attempts=2, issue_id="ENH-500")

        result = _bash(_check_attempt_budget_script("ENH-500", max_count=5), tmp_path)

        assert result.returncode == 0
        attempts = (loops_tmp / "recursive-refine-attempts.txt").read_text()
        assert attempts.count("ENH-500") == 3
        assert "ENH-500" not in (loops_tmp / "recursive-refine-skipped-budget.txt").read_text()
        assert "ENH-500" not in (loops_tmp / "recursive-refine-skipped.txt").read_text()

    def test_at_cap_exits_1_and_writes_both_skip_files(self, tmp_path: Path) -> None:
        """At cap: exits 1 and writes ID to both skipped-budget and skipped files."""
        loops_tmp = self._setup(tmp_path, attempts=5, issue_id="ENH-600")

        result = _bash(_check_attempt_budget_script("ENH-600", max_count=5), tmp_path)

        assert result.returncode == 1
        assert "ENH-600" in (loops_tmp / "recursive-refine-skipped-budget.txt").read_text()
        assert "ENH-600" in (loops_tmp / "recursive-refine-skipped.txt").read_text()
        attempts = (loops_tmp / "recursive-refine-attempts.txt").read_text()
        assert attempts.count("ENH-600") == 5

    def test_above_cap_also_exits_1(self, tmp_path: Path) -> None:
        """Above cap (count > cap): also exits 1."""
        loops_tmp = self._setup(tmp_path, attempts=7, issue_id="ENH-700")

        result = _bash(_check_attempt_budget_script("ENH-700", max_count=5), tmp_path)

        assert result.returncode == 1
        assert "ENH-700" in (loops_tmp / "recursive-refine-skipped-budget.txt").read_text()

    def test_exactly_max_refine_count_attempts_then_budget_skip(self, tmp_path: Path) -> None:
        """Synthetic issue that always fails: produces exactly max_refine_count attempts then is budget-skipped."""
        loops_tmp = self._setup(tmp_path, attempts=0, issue_id="ENH-EXHAUST")
        cap = 5

        for i in range(cap):
            result = _bash(_check_attempt_budget_script("ENH-EXHAUST", max_count=cap), tmp_path)
            assert result.returncode == 0, f"Attempt {i + 1} should be allowed"

        result = _bash(_check_attempt_budget_script("ENH-EXHAUST", max_count=cap), tmp_path)
        assert result.returncode == 1, "Attempt beyond cap should be budget-skipped"

        attempts = (loops_tmp / "recursive-refine-attempts.txt").read_text()
        assert attempts.count("ENH-EXHAUST") == cap
        assert "ENH-EXHAUST" in (loops_tmp / "recursive-refine-skipped-budget.txt").read_text()
        assert "ENH-EXHAUST" in (loops_tmp / "recursive-refine-skipped.txt").read_text()


class TestEnqueueChildDepths:
    """Child depth appending in enqueue_children / enqueue_or_skip."""

    def test_children_get_parent_depth_plus_one(self, tmp_path: Path) -> None:
        """Children of a depth-0 parent are appended to depth-map at depth 1."""
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)
        (loops_tmp / "recursive-refine-current-depth.txt").write_text("0")
        (loops_tmp / "recursive-refine-new-children.txt").write_text("ENH-010\nENH-011\n")
        (loops_tmp / "recursive-refine-depth-map.txt").write_text("ENH-001 0\n")

        _bash(
            r"""
            PARENT_DEPTH=$(cat .loops/tmp/recursive-refine-current-depth.txt 2>/dev/null || echo 0)
            while IFS= read -r child; do
              echo "$child $((PARENT_DEPTH + 1))" >> .loops/tmp/recursive-refine-depth-map.txt
            done < .loops/tmp/recursive-refine-new-children.txt
            """,
            tmp_path,
        )

        depth_map = (loops_tmp / "recursive-refine-depth-map.txt").read_text()
        assert "ENH-010 1" in depth_map
        assert "ENH-011 1" in depth_map

    def test_depth_1_parent_produces_depth_2_children(self, tmp_path: Path) -> None:
        """Children of a depth-1 parent are appended at depth 2."""
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)
        (loops_tmp / "recursive-refine-current-depth.txt").write_text("1")
        (loops_tmp / "recursive-refine-new-children.txt").write_text("ENH-021\n")
        (loops_tmp / "recursive-refine-depth-map.txt").write_text("ENH-010 1\n")

        _bash(
            r"""
            PARENT_DEPTH=$(cat .loops/tmp/recursive-refine-current-depth.txt 2>/dev/null || echo 0)
            while IFS= read -r child; do
              echo "$child $((PARENT_DEPTH + 1))" >> .loops/tmp/recursive-refine-depth-map.txt
            done < .loops/tmp/recursive-refine-new-children.txt
            """,
            tmp_path,
        )

        depth_map = (loops_tmp / "recursive-refine-depth-map.txt").read_text()
        assert "ENH-021 2" in depth_map


_VISITED_FILTER_SCRIPT = r"""
python3 << 'PYEOF'
from pathlib import Path
import sys
visited = set()
for f in ['recursive-refine-visited.txt', 'recursive-refine-passed.txt']:
    p = Path(f'.loops/tmp/{f}')
    if p.exists():
        visited.update(ln.strip() for ln in p.read_text().splitlines() if ln.strip())
queue_p = Path('.loops/tmp/recursive-refine-queue.txt')
if queue_p.exists():
    visited.update(ln.strip() for ln in queue_p.read_text().splitlines() if ln.strip())
candidates_p = Path('.loops/tmp/recursive-refine-new-children.txt')
candidates = []
if candidates_p.exists():
    candidates = [ln.strip() for ln in candidates_p.read_text().splitlines() if ln.strip()]
for cid in candidates:
    if cid in visited:
        print(f'WARN: refusing to re-enqueue {cid} (already visited / passed)', file=sys.stderr)
survivors = [cid for cid in candidates if cid not in visited]
candidates_p.write_text(''.join(f'{c}\n' for c in survivors))
PYEOF
"""

_CYCLE_FILTER_SCRIPT = r"""
python3 << 'PYEOF'
from pathlib import Path
import sys
visited = set()
for f in ['recursive-refine-visited.txt', 'recursive-refine-passed.txt']:
    p = Path(f'.loops/tmp/{f}')
    if p.exists():
        visited.update(ln.strip() for ln in p.read_text().splitlines() if ln.strip())
queue_p = Path('.loops/tmp/recursive-refine-queue.txt')
if queue_p.exists():
    visited.update(ln.strip() for ln in queue_p.read_text().splitlines() if ln.strip())
candidates_p = Path('.loops/tmp/recursive-refine-new-children.txt')
candidates = []
if candidates_p.exists():
    candidates = [ln.strip() for ln in candidates_p.read_text().splitlines() if ln.strip()]
for cid in candidates:
    if cid in visited:
        print(f'WARN: refusing to re-enqueue {cid} (already visited / passed)', file=sys.stderr)
survivors = [cid for cid in candidates if cid not in visited]
candidates_p.write_text(''.join(f'{c}\n' for c in survivors))
if len(candidates) > 0 and len(survivors) == 0:
    with open('.loops/tmp/recursive-refine-skipped-cycle.txt', 'a') as cf:
        cf.write('ENH-PARENT\n')
PYEOF
"""


class TestVisitedSetFilter:
    """enqueue_children / enqueue_or_skip filter candidate children against the visited set."""

    def test_visited_id_is_filtered_and_warns(self, tmp_path: Path) -> None:
        """Candidate ID already in visited.txt is dropped and a WARN is printed to stderr."""
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)
        (loops_tmp / "recursive-refine-visited.txt").write_text("ENH-010\n")
        (loops_tmp / "recursive-refine-passed.txt").write_text("")
        (loops_tmp / "recursive-refine-queue.txt").write_text("")
        (loops_tmp / "recursive-refine-new-children.txt").write_text("ENH-010\nENH-020\n")

        result = _bash(_VISITED_FILTER_SCRIPT, tmp_path)

        survivors = (loops_tmp / "recursive-refine-new-children.txt").read_text()
        assert "ENH-010" not in survivors
        assert "ENH-020" in survivors
        assert "WARN: refusing to re-enqueue ENH-010" in result.stderr

    def test_passed_id_is_filtered(self, tmp_path: Path) -> None:
        """Candidate ID already in passed.txt is dropped."""
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)
        (loops_tmp / "recursive-refine-visited.txt").write_text("")
        (loops_tmp / "recursive-refine-passed.txt").write_text("ENH-030\n")
        (loops_tmp / "recursive-refine-queue.txt").write_text("")
        (loops_tmp / "recursive-refine-new-children.txt").write_text("ENH-030\nENH-040\n")

        result = _bash(_VISITED_FILTER_SCRIPT, tmp_path)

        survivors = (loops_tmp / "recursive-refine-new-children.txt").read_text()
        assert "ENH-030" not in survivors
        assert "ENH-040" in survivors
        assert "WARN: refusing to re-enqueue ENH-030" in result.stderr

    def test_queue_id_is_filtered(self, tmp_path: Path) -> None:
        """Candidate ID already in the live queue is dropped."""
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)
        (loops_tmp / "recursive-refine-visited.txt").write_text("")
        (loops_tmp / "recursive-refine-passed.txt").write_text("")
        (loops_tmp / "recursive-refine-queue.txt").write_text("ENH-050\n")
        (loops_tmp / "recursive-refine-new-children.txt").write_text("ENH-050\nENH-060\n")

        result = _bash(_VISITED_FILTER_SCRIPT, tmp_path)

        survivors = (loops_tmp / "recursive-refine-new-children.txt").read_text()
        assert "ENH-050" not in survivors
        assert "ENH-060" in survivors
        assert "WARN: refusing to re-enqueue ENH-050" in result.stderr

    def test_unvisited_id_passes_through(self, tmp_path: Path) -> None:
        """Candidate ID not in any tracking set is written back to new-children.txt."""
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)
        (loops_tmp / "recursive-refine-visited.txt").write_text("ENH-001\n")
        (loops_tmp / "recursive-refine-passed.txt").write_text("")
        (loops_tmp / "recursive-refine-queue.txt").write_text("")
        (loops_tmp / "recursive-refine-new-children.txt").write_text("ENH-099\n")

        result = _bash(_VISITED_FILTER_SCRIPT, tmp_path)

        survivors = (loops_tmp / "recursive-refine-new-children.txt").read_text()
        assert "ENH-099" in survivors
        assert result.stderr == ""


class TestCycleSkipReason:
    """enqueue_or_skip writes parent to skipped-cycle.txt when all children are cycle-filtered."""

    def test_all_filtered_children_writes_to_skipped_cycle(self, tmp_path: Path) -> None:
        """All candidate children already visited → parent is written to skipped-cycle.txt."""
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)
        (loops_tmp / "recursive-refine-visited.txt").write_text("ENH-010\nENH-011\n")
        (loops_tmp / "recursive-refine-passed.txt").write_text("")
        (loops_tmp / "recursive-refine-queue.txt").write_text("")
        (loops_tmp / "recursive-refine-new-children.txt").write_text("ENH-010\nENH-011\n")

        _bash(_CYCLE_FILTER_SCRIPT, tmp_path)

        cycle_file = (loops_tmp / "recursive-refine-skipped-cycle.txt").read_text()
        assert "ENH-PARENT" in cycle_file
        assert (loops_tmp / "recursive-refine-new-children.txt").read_text().strip() == ""

    def test_partial_filter_does_not_write_to_skipped_cycle(self, tmp_path: Path) -> None:
        """Only partially filtered children (some survive) do not trigger cycle-skip."""
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)
        (loops_tmp / "recursive-refine-visited.txt").write_text("ENH-010\n")
        (loops_tmp / "recursive-refine-passed.txt").write_text("")
        (loops_tmp / "recursive-refine-queue.txt").write_text("")
        (loops_tmp / "recursive-refine-new-children.txt").write_text("ENH-010\nENH-099\n")

        _bash(_CYCLE_FILTER_SCRIPT, tmp_path)

        assert not (loops_tmp / "recursive-refine-skipped-cycle.txt").exists()
        survivors = (loops_tmp / "recursive-refine-new-children.txt").read_text()
        assert "ENH-099" in survivors

    def test_no_candidates_does_not_write_to_skipped_cycle(self, tmp_path: Path) -> None:
        """Empty new-children.txt (pre-filter count = 0) does not create skipped-cycle.txt."""
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)
        (loops_tmp / "recursive-refine-visited.txt").write_text("ENH-010\n")
        (loops_tmp / "recursive-refine-passed.txt").write_text("")
        (loops_tmp / "recursive-refine-queue.txt").write_text("")
        (loops_tmp / "recursive-refine-new-children.txt").write_text("")

        _bash(_CYCLE_FILTER_SCRIPT, tmp_path)

        assert not (loops_tmp / "recursive-refine-skipped-cycle.txt").exists()


class TestDoneSummary:
    """Skipped (depth-cap N) and Skipped (cycle N) lines in done state summary."""

    _DONE_SCRIPT = r"""
    PASSED_IDS=$(cat .loops/tmp/recursive-refine-passed.txt 2>/dev/null \
      | grep -v '^[[:space:]]*$' | sort -u || true)
    SKIPPED_IDS=$(cat .loops/tmp/recursive-refine-skipped.txt 2>/dev/null \
      | grep -v '^[[:space:]]*$' | sort -u || true)
    DEPTH_SKIPPED_IDS=$(cat .loops/tmp/recursive-refine-skipped-depth.txt 2>/dev/null \
      | grep -v '^[[:space:]]*$' | sort -u || true)
    CYCLE_SKIPPED_IDS=$(cat .loops/tmp/recursive-refine-skipped-cycle.txt 2>/dev/null \
      | grep -v '^[[:space:]]*$' | sort -u || true)
    BUDGET_SKIPPED_IDS=$(cat .loops/tmp/recursive-refine-skipped-budget.txt 2>/dev/null \
      | grep -v '^[[:space:]]*$' | sort -u || true)

    PASSED_COUNT=$(echo "$PASSED_IDS" | grep -c '[^[:space:]]' || echo 0)
    SKIPPED_COUNT=$(echo "$SKIPPED_IDS" | grep -c '[^[:space:]]' || echo 0)
    DEPTH_COUNT=$(echo "$DEPTH_SKIPPED_IDS" | grep -c '[^[:space:]]' || echo 0)
    CYCLE_COUNT=$(echo "$CYCLE_SKIPPED_IDS" | grep -c '[^[:space:]]' || echo 0)
    BUDGET_COUNT=$(echo "$BUDGET_SKIPPED_IDS" | grep -c '[^[:space:]]' || echo 0)

    PASSED_LIST=$(echo "$PASSED_IDS" | tr '\n' ',' | sed 's/,$//')
    SKIPPED_LIST=$(echo "$SKIPPED_IDS" | tr '\n' ',' | sed 's/,$//')
    DEPTH_LIST=$(echo "$DEPTH_SKIPPED_IDS" | tr '\n' ',' | sed 's/,$//')
    CYCLE_LIST=$(echo "$CYCLE_SKIPPED_IDS" | tr '\n' ',' | sed 's/,$//')
    BUDGET_LIST=$(echo "$BUDGET_SKIPPED_IDS" | tr '\n' ',' | sed 's/,$//')

    printf '\n=== Recursive Refine Summary ===\n\n'
    printf 'Passed  (%d): %s\n' "$PASSED_COUNT" "${PASSED_LIST:-none}"
    printf 'Skipped (%d): %s\n' "$SKIPPED_COUNT" "${SKIPPED_LIST:-none}"
    printf 'Skipped (depth-cap %d): %s\n' "$DEPTH_COUNT" "${DEPTH_LIST:-none}"
    printf 'Skipped (cycle %d): %s\n' "$CYCLE_COUNT" "${CYCLE_LIST:-none}"
    printf 'Skipped (budget %d): %s\n' "$BUDGET_COUNT" "${BUDGET_LIST:-none}"
    printf '\n'
    """

    def test_depth_cap_line_shows_capped_ids(self, tmp_path: Path) -> None:
        """done includes 'Skipped (depth-cap N): IDs' when depth-capped issues exist."""
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)
        (loops_tmp / "recursive-refine-passed.txt").write_text("ENH-001\n")
        (loops_tmp / "recursive-refine-skipped.txt").write_text("ENH-002\nENH-003\n")
        (loops_tmp / "recursive-refine-skipped-depth.txt").write_text("ENH-003\n")
        (loops_tmp / "recursive-refine-skipped-cycle.txt").write_text("")

        result = _bash(self._DONE_SCRIPT, tmp_path)

        assert result.returncode == 0
        assert "Passed  (1):" in result.stdout
        assert "Skipped (2):" in result.stdout
        assert "Skipped (depth-cap 1):" in result.stdout
        assert "ENH-003" in result.stdout

    def test_depth_cap_line_shows_none_when_no_capped_issues(self, tmp_path: Path) -> None:
        """done emits 'Skipped (depth-cap 0): none' when no depth-capped issues."""
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)
        (loops_tmp / "recursive-refine-passed.txt").write_text("ENH-001\n")
        (loops_tmp / "recursive-refine-skipped.txt").write_text("")
        (loops_tmp / "recursive-refine-skipped-depth.txt").write_text("")
        (loops_tmp / "recursive-refine-skipped-cycle.txt").write_text("")

        result = _bash(self._DONE_SCRIPT, tmp_path)

        assert result.returncode == 0
        assert "Skipped (depth-cap 0): none" in result.stdout

    def test_cycle_line_shows_cycle_ids(self, tmp_path: Path) -> None:
        """done includes 'Skipped (cycle N): IDs' when cycle-detected issues exist."""
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)
        (loops_tmp / "recursive-refine-passed.txt").write_text("ENH-001\n")
        (loops_tmp / "recursive-refine-skipped.txt").write_text("ENH-002\n")
        (loops_tmp / "recursive-refine-skipped-depth.txt").write_text("")
        (loops_tmp / "recursive-refine-skipped-cycle.txt").write_text("ENH-002\n")

        result = _bash(self._DONE_SCRIPT, tmp_path)

        assert result.returncode == 0
        assert "Skipped (cycle 1):" in result.stdout
        assert "ENH-002" in result.stdout

    def test_cycle_line_shows_none_when_no_cycle_issues(self, tmp_path: Path) -> None:
        """done emits 'Skipped (cycle 0): none' when no cycle-detected issues."""
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)
        (loops_tmp / "recursive-refine-passed.txt").write_text("ENH-001\n")
        (loops_tmp / "recursive-refine-skipped.txt").write_text("")
        (loops_tmp / "recursive-refine-skipped-depth.txt").write_text("")
        (loops_tmp / "recursive-refine-skipped-cycle.txt").write_text("")

        result = _bash(self._DONE_SCRIPT, tmp_path)

        assert result.returncode == 0
        assert "Skipped (cycle 0): none" in result.stdout

    def test_budget_line_shows_budget_ids(self, tmp_path: Path) -> None:
        """done includes 'Skipped (budget N): IDs' when budget-exceeded issues exist."""
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)
        (loops_tmp / "recursive-refine-passed.txt").write_text("ENH-001\n")
        (loops_tmp / "recursive-refine-skipped.txt").write_text("ENH-002\n")
        (loops_tmp / "recursive-refine-skipped-depth.txt").write_text("")
        (loops_tmp / "recursive-refine-skipped-cycle.txt").write_text("")
        (loops_tmp / "recursive-refine-skipped-budget.txt").write_text("ENH-002\n")

        result = _bash(self._DONE_SCRIPT, tmp_path)

        assert result.returncode == 0
        assert "Skipped (budget 1):" in result.stdout
        assert "ENH-002" in result.stdout

    def test_budget_line_shows_none_when_no_budget_issues(self, tmp_path: Path) -> None:
        """done emits 'Skipped (budget 0): none' when no budget-exceeded issues."""
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)
        (loops_tmp / "recursive-refine-passed.txt").write_text("ENH-001\n")
        (loops_tmp / "recursive-refine-skipped.txt").write_text("")
        (loops_tmp / "recursive-refine-skipped-depth.txt").write_text("")
        (loops_tmp / "recursive-refine-skipped-cycle.txt").write_text("")
        (loops_tmp / "recursive-refine-skipped-budget.txt").write_text("")

        result = _bash(self._DONE_SCRIPT, tmp_path)

        assert result.returncode == 0
        assert "Skipped (budget 0): none" in result.stdout
