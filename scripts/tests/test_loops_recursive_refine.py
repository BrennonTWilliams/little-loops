"""Tests for recursive-refine depth-cap behavior (ENH-1347).

Tests the depth-tracking bash logic for parse_input, dequeue_next, check_depth,
enqueue_children / enqueue_or_skip, and done states by executing shell snippets
directly against a tmp_path environment.
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


class TestDoneSummary:
    """Skipped (depth-cap N) line in done state summary."""

    _DONE_SCRIPT = r"""
    PASSED_IDS=$(cat .loops/tmp/recursive-refine-passed.txt 2>/dev/null \
      | grep -v '^[[:space:]]*$' | sort -u || true)
    SKIPPED_IDS=$(cat .loops/tmp/recursive-refine-skipped.txt 2>/dev/null \
      | grep -v '^[[:space:]]*$' | sort -u || true)
    DEPTH_SKIPPED_IDS=$(cat .loops/tmp/recursive-refine-skipped-depth.txt 2>/dev/null \
      | grep -v '^[[:space:]]*$' | sort -u || true)

    PASSED_COUNT=$(echo "$PASSED_IDS" | grep -c '[^[:space:]]' || echo 0)
    SKIPPED_COUNT=$(echo "$SKIPPED_IDS" | grep -c '[^[:space:]]' || echo 0)
    DEPTH_COUNT=$(echo "$DEPTH_SKIPPED_IDS" | grep -c '[^[:space:]]' || echo 0)

    PASSED_LIST=$(echo "$PASSED_IDS" | tr '\n' ',' | sed 's/,$//')
    SKIPPED_LIST=$(echo "$SKIPPED_IDS" | tr '\n' ',' | sed 's/,$//')
    DEPTH_LIST=$(echo "$DEPTH_SKIPPED_IDS" | tr '\n' ',' | sed 's/,$//')

    printf '\n=== Recursive Refine Summary ===\n\n'
    printf 'Passed  (%d): %s\n' "$PASSED_COUNT" "${PASSED_LIST:-none}"
    printf 'Skipped (%d): %s\n' "$SKIPPED_COUNT" "${SKIPPED_LIST:-none}"
    printf 'Skipped (depth-cap %d): %s\n' "$DEPTH_COUNT" "${DEPTH_LIST:-none}"
    printf '\n'
    """

    def test_depth_cap_line_shows_capped_ids(self, tmp_path: Path) -> None:
        """done includes 'Skipped (depth-cap N): IDs' when depth-capped issues exist."""
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True)
        (loops_tmp / "recursive-refine-passed.txt").write_text("ENH-001\n")
        (loops_tmp / "recursive-refine-skipped.txt").write_text("ENH-002\nENH-003\n")
        (loops_tmp / "recursive-refine-skipped-depth.txt").write_text("ENH-003\n")

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

        result = _bash(self._DONE_SCRIPT, tmp_path)

        assert result.returncode == 0
        assert "Skipped (depth-cap 0): none" in result.stdout
