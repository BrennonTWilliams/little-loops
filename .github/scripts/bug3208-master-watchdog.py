#!/usr/bin/env python3
"""BUG-3208 master-side hang watchdog v4 -- heartbeat + snapshot signal generator.

Redesigned for the FULL-VM-FREEZE failure mode (per Cooper / QA, 2026-08-26).
Prior versions targeted a "pytest-stuck-on-syscall" failure mode where the
VM stays alive but pytest blocks. That assumption was wrong: the reaper
(independent sleep+date subshell) dies at the same moment as the snapshotter,
proving the freeze is system-wide. The watchdog itself is in the same VM.

Two contracts:
  1. RED-RUN evidence: heartbeat writes to pytest-master-snapshot.log every
     ~10s (poll_interval). Path E SNAPSHOTTER PATCHes the file content to
     issue #11 at ~30s cadence. The gap between two successful PATCHes
     marks the freeze window.
  2. GREEN-RUN falsification: surviving to close with stable progress events
     AND no snapshot fires = the wedge did not reproduce this run.

Per-heartbeat line carries: alive_at, VmRSS, FD count, last_progress_at, wchan.

Targeted /proc snapshots at T+2min and T+5min of no-progress: same as v3
(stack + status + wchan + fd-listing + smaps_rollup + io).

SIGABRT REMOVED: the watchdog is in the same VM that freezes; SIGABRT to
pytest would only fire if the watchdog is alive, which means the VM is alive
at T+7min -- but if the VM is alive, pytest is probably making progress.

QA-flag: py-spy-silent-fail-on-perf_event_open
"""
import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def proc_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def snapshot(out, pid, label):
    out.write("\n=== SNAPSHOT " + label + " @ " + time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()) + " ===\n")

    out.write("--- /proc/" + str(pid) + "/stack ---\n")
    try:
        with open("/proc/" + str(pid) + "/stack", "r") as f:
            out.write(f.read())
    except OSError as e:
        out.write("(unavailable: " + str(e) + ")\n")

    out.write("--- /proc/" + str(pid) + "/status ---\n")
    try:
        with open("/proc/" + str(pid) + "/status", "r") as f:
            out.write(f.read())
    except OSError as e:
        out.write("(unavailable: " + str(e) + ")\n")

    out.write("--- /proc/" + str(pid) + "/wchan ---\n")
    try:
        with open("/proc/" + str(pid) + "/wchan", "r") as f:
            out.write(f.read().strip() + "\n")
    except OSError as e:
        out.write("(unavailable: " + str(e) + ")\n")

    out.write("--- ls -la /proc/" + str(pid) + "/fd/ ---\n")
    try:
        result = subprocess.run(
            ["ls", "-la", "/proc/" + str(pid) + "/fd/"],
            capture_output=True, text=True, timeout=5,
        )
        out.write(result.stdout)
        if result.stderr:
            out.write("(stderr: " + result.stderr + ")\n")
    except (OSError, subprocess.TimeoutExpired) as e:
        out.write("(unavailable: " + str(e) + ")\n")

    # FD count: single-line, easy to grep + trend across snapshots.
    # identity-at-snap1-and-snap2 = no FD growth (file descriptors not leaking).
    # snap2 > snap1 by N = N files opened during the stall window.
    out.write("--- FD count (ls /proc/" + str(pid) + "/fd | wc -l) ---\n")
    try:
        result = subprocess.run(
            ["bash", "-c", "ls /proc/" + str(pid) + "/fd 2>/dev/null | wc -l"],
            capture_output=True, text=True, timeout=5,
        )
        out.write(result.stdout.strip() + "\n")
        if result.stderr:
            out.write("(stderr: " + result.stderr.strip() + ")\n")
    except (OSError, subprocess.TimeoutExpired) as e:
        out.write("(unavailable: " + str(e) + ")\n")

    # smaps_rollup: heap vs stack vs mmap vs locked vs private.
    # Available since kernel 3.10; 2>/dev/null covers the older-kernel gap.
    # Names the heap-vs-mmap surface directly: cum-load leak in mmap'd
    # objects shows up here as growing `Rss`/`Pss_Anon` deltas across snaps.
    out.write("--- /proc/" + str(pid) + "/smaps_rollup ---\n")
    try:
        with open("/proc/" + str(pid) + "/smaps_rollup", "r") as f:
            out.write(f.read())
    except OSError as e:
        out.write("(unavailable: " + str(e) + ")\n")

    # I/O stats: cumulative read_bytes/write_bytes/syscr/syscw.
    # If the wedge is I/O-bound (pipe wait, blocked syscall), the byte
    # counter at snap1 vs snap2 reveals whether I/O is progressing.
    # Subtracting snap1 from snap2 gives the stall-window I/O delta.
    out.write("--- /proc/" + str(pid) + "/io ---\n")
    try:
        with open("/proc/" + str(pid) + "/io", "r") as f:
            out.write(f.read())
    except OSError as e:
        out.write("(unavailable: " + str(e) + ")\n")


def main():
    ap = argparse.ArgumentParser(description="BUG-3208 master-side hang watchdog")
    ap.add_argument("--pid", type=int, required=True, help="pytest master PID")
    ap.add_argument("--stdout", required=True, help="pytest stdout log path")
    ap.add_argument("--out", required=True, help="snapshot output path")
    ap.add_argument("--snap1-at", type=int, default=120, help="first snapshot at N seconds no-progress")
    ap.add_argument("--snap2-at", type=int, default=300, help="second snapshot at N seconds no-progress")
    ap.add_argument("--poll-interval", type=int, default=10, help="heartbeat interval in seconds (default 10s; Path E PATCHes every ~30s)")
    args = ap.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    out = open(out_path, "w", buffering=1)
    out.write("=== BUG-3208 master-watchdog started at " + time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()) + " ===\n")
    out.write("   pid=" + str(args.pid) + " stdout=" + args.stdout + " snap1=" + str(args.snap1_at) + "s snap2=" + str(args.snap2_at) + "s poll=" + str(args.poll_interval) + "s\n\n")
    out.write("contracts: red-run heartbeat (Path E PATCH) + green-run falsification (no-snapshot-on-close)\n\n")

    last_line_count = 0
    last_progress_monotonic = time.monotonic()
    snap1_done = False
    snap2_done = False
    out.write("[" + time.strftime('%H:%M:%S', time.gmtime()) + "] watchdog alive; watching pid=" + str(args.pid) + "\n")

    last_junit_mtime = 0.0
    last_junit_size = 0
    junit_path = Path("pytest-junit.xml")
    out.write("junit-mtime+size tracking: enabled (path=" + str(junit_path) + ")\n")

    start_epoch = time.time()
    start_monotonic = time.monotonic()

    while proc_alive(args.pid):
        # Progress signal 1: stdout line count growth
        try:
            with open(args.stdout, "r", errors="replace") as f:
                lines = f.readlines()
            line_count = len(lines)
        except OSError:
            line_count = 0

        # Progress signal 2: pytest-junit.xml mtime (when file exists).
        # pytest-junit writes testsuite elements incrementally as tests
        # complete, so mtime advances on test progress even if stdout is
        # quiet (e.g., during xdist loadfile-distribution silences, where
        # master-side stdout may pause while workers churn).
        try:
            if junit_path.exists():
                current_junit_mtime = junit_path.stat().st_mtime
            else:
                current_junit_mtime = 0.0
        except OSError:
            current_junit_mtime = 0.0

        # Progress signal 3: pytest-junit.xml file size.
        # Edge case from QA: pytest-junit buffers per-testcase elements
        # in memory and flushes them at the NEXT test's setup hook. A single
        # test running >2min (rare but real: fixture-build tests, subprocess-
        # spawn clusters, large mock factories) leaves mtime unchanged for
        # the duration of that one test. File size advances incrementally
        # as new testsuite/testcase elements are appended to the buffer,
        # decoupled from filesystem-mtime resolution (1s on most ext4).
        # OR-condition: any of the three signals advancing = progress.
        try:
            if junit_path.exists():
                current_junit_size = junit_path.stat().st_size
            else:
                current_junit_size = 0
        except OSError:
            current_junit_size = 0

        progress_made = False
        progress_reasons = []
        if line_count > last_line_count:
            last_line_count = line_count
            progress_made = True
            progress_reasons.append("lines=" + str(line_count))
        if current_junit_mtime > last_junit_mtime:
            last_junit_mtime = current_junit_mtime
            progress_made = True
            progress_reasons.append("junit_mtime=" + str(int(current_junit_mtime)))
        if current_junit_size > last_junit_size:
            last_junit_size = current_junit_size
            progress_made = True
            progress_reasons.append("junit_size=" + str(current_junit_size))
        if progress_made:
            last_progress_monotonic = time.monotonic()
            out.write("[" + time.strftime('%H:%M:%S', time.gmtime()) + "] progress: " + ",".join(progress_reasons) + "\n")

        now = time.monotonic()
        no_progress = now - last_progress_monotonic

        if not snap1_done and no_progress >= args.snap1_at:
            snapshot(out, args.pid, label="1 (T+2min)")
            snap1_done = True

        if snap1_done and not snap2_done and no_progress >= args.snap2_at:
            snapshot(out, args.pid, label="2 (T+5min)")
            out.write("\n=== STACK DELTA snap1 vs snap2 ===\n")
            out.write("Manual diff required. Identical stacks -> hard deadlock.\n")
            out.write("Different stacks -> slow finalization, not dead.\n")
            snap2_done = True

        # Heartbeat pulse: write a single line to the log every poll interval.
        # Path E SNAPSHOTTER PATCHes this log to issue #11 at ~30s cadence,
        # so each heartbeat becomes an out-of-band evidence point that
        # survives VM freeze (worst case: last heartbeat + ~30s gap).
        try:
            vmrss = ""
            try:
                with open("/proc/" + str(args.pid) + "/status", "r") as sf:
                    for line in sf:
                        if line.startswith("VmRSS:"):
                            vmrss = line.strip()
                            break
            except OSError:
                vmrss = "VmRSS:unavailable"
            fd_count = "?"
            try:
                fd_result = subprocess.run(
                    ["bash", "-c", "ls /proc/" + str(args.pid) + "/fd 2>/dev/null | wc -l"],
                    capture_output=True, text=True, timeout=2,
                )
                fd_count = fd_result.stdout.strip()
            except (OSError, subprocess.TimeoutExpired):
                pass
            wchan_val = "?"
            try:
                with open("/proc/" + str(args.pid) + "/wchan", "r") as wf:
                    wchan_val = wf.read().strip() or "(running)"
            except OSError:
                pass
            last_progress_str = time.strftime('%H:%M:%S', time.gmtime(start_epoch + last_progress_monotonic - start_monotonic))
            out.write("HEARTBEAT T=" + time.strftime('%H:%M:%S', time.gmtime())
                      + " alive=" + ("yes" if proc_alive(args.pid) else "no")
                      + " " + vmrss
                      + " FD=" + fd_count
                      + " last_progress=" + last_progress_str
                      + " no_progress=" + str(int(no_progress)) + "s"
                      + " wchan=" + wchan_val
                      + "\n")
        except Exception as e:
            out.write("HEARTBEAT failed: " + str(e) + "\n")

        time.sleep(args.poll_interval)

    out.write("\n=== pytest exited at " + time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()) + " ===\n")
    out.write("   final no-progress at exit: " + str(int(time.monotonic() - last_progress_monotonic)) + "s\n")
    out.write("   snap1_done=" + str(snap1_done) + " snap2_done=" + str(snap2_done) + "\n")
    out.write("   green-run-falsification: " + ("PASS (no snapshot fired = wedge did NOT reproduce)" if not snap1_done else "FAIL (snapshot fired = wedge reproduced)") + "\n")
    out.close()


if __name__ == "__main__":
    main()
