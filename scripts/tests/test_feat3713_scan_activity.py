"""Bounded scoped-activity loader: framing, windows, caps, git policy (FEAT-3713 step 2)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from little_loops.next_arena.scan_activity import (
    BUDGET_SECONDS,
    MAX_BYTES,
    MAX_RECORDS,
    LogDecoder,
    child_environment,
    head_command,
    load_scope_activity,
    log_command,
)
from tests.scan_support import (
    AS_OF,
    AS_OF_EPOCH,
    DAY,
    HEAD,
    FakeClock,
    FakePopen,
    FakeProc,
    head_proc,
    load,
    record,
    scope_for,
    sha,
    stream,
)

IN_WINDOW = AS_OF_EPOCH - DAY


def decoder(
    *,
    threshold: int = 20,
    lookback_days: int = 30,
    focus: tuple[str, ...] = ("src",),
    exclude: tuple[str, ...] = (),
    max_records: int = MAX_RECORDS,
) -> LogDecoder:
    from little_loops.next_arena.scan_activity import _epoch_us
    from little_loops.next_arena.scan_state import path_in_scope

    return LogDecoder(
        lambda p: path_in_scope(p, focus, exclude),
        window_start_us=_epoch_us(AS_OF - timedelta(days=lookback_days)),
        window_end_us=_epoch_us(AS_OF),
        threshold=threshold,
        max_records=max_records,
    )


def run(dec: LogDecoder, data: bytes) -> LogDecoder:
    dec.feed(data)
    dec.finish()
    return dec


# ------------------------------------------------------------------------------ framing


def test_counts_each_scoped_in_window_commit_once_across_overlapping_directories() -> None:
    dec = decoder(focus=("src", "src/lib"))
    run(
        dec,
        stream(
            record(
                sha(1), IN_WINDOW, ["src/a.py", "src/lib/b.py"]
            ),  # two matching dirs, one commit
            record(sha(2), IN_WINDOW, ["docs/x.md"]),  # out of scope
            record(sha(3), IN_WINDOW, []),  # empty path list (outside --relative)
            record(sha(4), IN_WINDOW, ["src/lib/c.py"]),
        ),
    )
    assert (dec.records_completed, dec.scoped_count, dec.error) == (4, 2, None)


def test_a_filename_embedding_the_old_record_sentinel_cannot_forge_a_commit() -> None:
    forged = f"src/\x01{sha(99)}\x02{IN_WINDOW}"  # looked like a %x01..%x02 header before
    dec = decoder()
    run(dec, stream(record(sha(1), IN_WINDOW, [forged]), record(sha(2), IN_WINDOW, ["README"])))
    assert dec.records_completed == 2 and dec.scoped_count == 1 and dec.error is None


def test_newline_backslash_and_leading_newline_names_stay_literal() -> None:
    names = ["src/a\\b.py", "src/new\nline.py", "src/\nlead.py"]
    seen: list[str] = []
    dec = LogDecoder(
        lambda p: seen.append(p) or True,
        window_start_us=0,
        window_end_us=10**18,
        threshold=99,
    )
    # a hit short-circuits later paths of the same record, so feed one record per name
    run(dec, stream(*(record(sha(i), 1, [n]) for i, n in enumerate(names))))
    assert seen == names  # exactly one leading "\n" separator stripped, nothing else altered


def test_empty_commit_streams_and_quiet_repository_are_complete() -> None:
    assert run(decoder(), b"").records_completed == 0
    dec = run(decoder(), stream(record(sha(1), IN_WINDOW), record(sha(2), IN_WINDOW)))
    assert (dec.records_completed, dec.scoped_count, dec.error) == (2, 0, None)


def test_split_chunks_decode_like_one_chunk() -> None:
    data = stream(record(sha(1), IN_WINDOW, ["src/a.py", "docs/b"]), record(sha(2), IN_WINDOW, []))
    whole = run(decoder(), data)
    split = decoder()
    for i in range(len(data)):
        split.feed(data[i : i + 1])
    split.finish()
    assert (split.records_completed, split.scoped_count) == (
        whole.records_completed,
        whole.scoped_count,
    )


@pytest.mark.parametrize(
    "bad",
    [b"junk", b"\x00not-a-header\x00", b"\x00" + b"z" * 40 + b" 1\x00"],
)
def test_malformed_streams_are_errors_not_counts(bad: bytes) -> None:
    dec = decoder()
    dec.feed(bad)
    dec.finish()
    assert dec.error is not None and dec.scoped_count == 0


def test_a_truncated_token_at_eof_is_not_evidence() -> None:
    dec = decoder()
    dec.feed(record(sha(1), IN_WINDOW, ["src/a.py"]) + b"\x00" + f"{sha(2)} {IN_WINDOW}".encode())
    assert dec.finish() is False
    # the first record was fully decoded; the dangling second header is never evidence
    assert dec.error and dec.scoped_count == 1 and dec.records_completed == 1


# ------------------------------------------------------------------------------ windows


def test_window_is_the_exact_inclusive_utc_interval() -> None:
    dec = decoder(lookback_days=30)
    lower = AS_OF_EPOCH - 30 * DAY
    run(
        dec,
        stream(
            record(sha(1), lower - 1, ["src/a"]),  # one second too old
            record(sha(2), lower, ["src/a"]),  # inclusive lower bound
            record(sha(3), AS_OF_EPOCH, ["src/a"]),  # inclusive upper bound
            record(sha(4), AS_OF_EPOCH + 1, ["src/a"]),  # future-dated
        ),
    )
    assert dec.scoped_count == 2


def test_fractional_lower_cutoff_does_not_admit_a_just_too_old_commit() -> None:
    # as_of 12:00:00.500: the lower cutoff is 30 days earlier at .5, so the commit stamped at the
    # whole second *below* it is out although git's floored --since-as-filter would pass it
    from little_loops.next_arena.scan_activity import _epoch_us

    as_of = AS_OF + timedelta(microseconds=500_000)
    lower_floor = AS_OF_EPOCH - 30 * DAY
    dec = LogDecoder(
        lambda p: True,
        window_start_us=_epoch_us(as_of - timedelta(days=30)),
        window_end_us=_epoch_us(as_of),
        threshold=99,
    )
    run(
        dec,
        stream(
            record(sha(1), lower_floor, ["src/a"]),  # lower_floor < lower cutoff (.5): excluded
            record(sha(2), lower_floor + 1, ["src/a"]),
            record(sha(3), AS_OF_EPOCH, ["src/a"]),  # floor(as_of) is within [.., as_of]
            record(sha(4), AS_OF_EPOCH + 1, ["src/a"]),  # beyond the fractional upper bound
        ),
    )
    assert dec.scoped_count == 2


def test_backdated_commits_after_newer_ones_are_still_assessed() -> None:
    dec = decoder()
    run(
        dec,
        stream(
            record(sha(1), IN_WINDOW, ["src/a"]),
            record(sha(2), AS_OF_EPOCH - 400 * DAY, ["src/a"]),  # old parent date mid-stream
            record(sha(3), IN_WINDOW - 5, ["src/a"]),  # newer again: no pruning on parent date
        ),
    )
    assert dec.scoped_count == 2 and dec.records_completed == 3


# --------------------------------------------------------------------- saturation and caps


def test_threshold_saturation_stops_with_a_truthful_lower_bound() -> None:
    dec = decoder(threshold=2)
    dec.feed(stream(*(record(sha(i), IN_WINDOW, ["src/a"]) for i in range(10))))
    assert dec.stop_reason == "saturated" and dec.scoped_count == 2 and dec.done


def test_record_cap_stops_only_when_more_output_exists() -> None:
    exact = decoder(max_records=3)
    run(exact, stream(*(record(sha(i), IN_WINDOW, []) for i in range(3))))
    assert exact.stop_reason is None and exact.records_completed == 3  # fully consumed

    more = decoder(max_records=3)
    more.feed(stream(*(record(sha(i), IN_WINDOW, []) for i in range(5))))
    assert more.stop_reason == "record_cap" and more.records_completed == 3


def test_decoder_ignores_input_after_it_is_done() -> None:
    dec = decoder(threshold=1)
    dec.feed(record(sha(1), IN_WINDOW, ["src/a"]) + record(sha(2), IN_WINDOW, ["src/a"]))
    count = dec.scoped_count
    dec.feed(record(sha(3), IN_WINDOW, ["src/a"]))
    assert dec.scoped_count == count


# ------------------------------------------------------------------------------- command


def test_commands_apply_the_arena_git_read_policy() -> None:
    assert head_command() == [
        "git",
        "--no-lazy-fetch",
        "rev-parse",
        "HEAD",
        "--is-shallow-repository",
    ]
    argv = log_command(HEAD, 1234)
    assert argv[:4] == ["git", "--no-lazy-fetch", "log", HEAD]  # global option before subcommand
    for flag in (
        "--format=%x00%H %ct",
        "--root",
        "--no-renames",
        "--diff-merges=first-parent",
        "--name-only",
        "-z",
        "--relative",
        "--since-as-filter=1234",
        "--no-ext-diff",
        "--no-textconv",
        "--no-show-signature",
        "--no-color",
    ):
        assert flag in argv
    assert "--first-parent" not in argv  # merge *diffs* only; ancestry is not pruned
    assert not any(a.startswith("--since=") for a in argv)


def test_child_environment_disables_traces_locks_and_prompts() -> None:
    env = child_environment(
        {
            "PATH": "/usr/bin",
            "GIT_TRACE": "/tmp/x",
            "GIT_TRACE_PACKET": "1",
            "git_trace2_perf": "/tmp/y",
            "GIT_DIR": "/keep",
        }
    )
    assert env["PATH"] == "/usr/bin" and env["GIT_DIR"] == "/keep"
    assert env["GIT_OPTIONAL_LOCKS"] == "0"
    for key in ("GIT_TRACE", "GIT_TRACE2", "GIT_TRACE2_EVENT", "GIT_TRACE2_PERF"):
        assert env[key] == "0"
    assert "GIT_TRACE_PACKET" not in env and "git_trace2_perf" not in env
    assert env["LC_ALL"] == "C" and env["GIT_TERMINAL_PROMPT"] == "0"


# ----------------------------------------------------------------------------- the loader


def test_complete_traversal_gives_an_exact_count_with_two_git_calls(tmp_path: Path) -> None:
    data = stream(
        record(sha(1), IN_WINDOW, ["src/a.py"]),
        record(sha(2), IN_WINDOW, ["docs/x"]),
        record(sha(3), IN_WINDOW - 10, ["src/b.py"]),
    )
    popen = FakePopen(head_proc(), FakeProc(data))
    activity = load(tmp_path, popen)
    assert (activity.available, activity.complete, activity.saturated) == (True, True, False)
    assert activity.scoped_commit_count == 2 and activity.lower_bound is None
    assert activity.records_visited == 3 and activity.git_calls == 2 == popen.procs_started
    assert activity.head == HEAD and activity.shallow is False
    assert activity.truncation_reason is None
    # both calls run from the project root with the controlled environment
    for call in popen.calls:
        assert call["cwd"] == str(tmp_path)
        assert call["env"]["GIT_OPTIONAL_LOCKS"] == "0" and call["env"]["GIT_TRACE2"] == "0"
    assert popen.calls[1]["argv"][3] == HEAD  # the log starts from the captured HEAD
    since = next(a for a in popen.calls[1]["argv"] if a.startswith("--since-as-filter="))
    assert since == f"--since-as-filter={AS_OF_EPOCH - 30 * DAY}"


def test_saturation_passes_with_lower_bound_stops_and_reaps(tmp_path: Path) -> None:
    log = FakeProc(stream(*(record(sha(i), IN_WINDOW, ["src/a"]) for i in range(50))), chunk=100)
    activity = load(tmp_path, FakePopen(head_proc(), log), threshold=3)
    assert activity.saturated and activity.lower_bound == 3 and activity.scoped_commit_count is None
    assert activity.truncation_reason == "saturated" and not activity.complete
    assert log.killed  # stopped rather than draining the rest
    assert activity.records_visited <= 5


def test_saturation_on_the_final_record_is_still_a_lower_bound(tmp_path: Path) -> None:
    log = FakeProc(stream(*(record(sha(i), IN_WINDOW, ["src/a"]) for i in range(3))))
    activity = load(tmp_path, FakePopen(head_proc(), log), threshold=3)
    assert activity.saturated and activity.lower_bound == 3 and activity.scoped_commit_count is None


def test_record_cap_below_threshold_is_partial_not_zero(tmp_path: Path, monkeypatch) -> None:
    import little_loops.next_arena.scan_activity as mod

    real = mod.LogDecoder
    monkeypatch.setattr(mod, "LogDecoder", lambda *a, **k: real(*a, **{**k, "max_records": 4}))
    data = stream(*(record(sha(i), IN_WINDOW, ["docs/x"]) for i in range(10)))
    log = FakeProc(data)
    activity = load(tmp_path, FakePopen(head_proc(), log), threshold=20)
    assert activity.available and not activity.complete and not activity.saturated
    assert activity.truncation_reason == "record_cap"
    assert activity.scoped_commit_count is None and activity.lower_bound == 0
    assert log.killed


def test_byte_budget_below_threshold_is_partial(tmp_path: Path, monkeypatch) -> None:
    import little_loops.next_arena.scan_activity as mod

    monkeypatch.setattr(mod, "MAX_BYTES", 300)
    data = stream(*(record(sha(i), IN_WINDOW, ["docs/x"]) for i in range(40)))
    log = FakeProc(data, chunk=120)
    activity = load(tmp_path, FakePopen(head_proc(), log), threshold=20)
    assert activity.truncation_reason == "byte_cap" and not activity.complete
    assert activity.scoped_commit_count is None and activity.bytes_consumed >= 300 - 60
    assert log.killed


def test_stderr_counts_toward_the_combined_byte_budget(tmp_path: Path, monkeypatch) -> None:
    import little_loops.next_arena.scan_activity as mod

    monkeypatch.setattr(mod, "MAX_BYTES", 500)
    log = FakeProc(
        stream(*(record(sha(i), IN_WINDOW, ["docs/x"]) for i in range(3))),
        stderr=b"w" * 5000,
    )
    activity = load(tmp_path, FakePopen(head_proc(), log), threshold=20)
    assert activity.truncation_reason == "byte_cap" and log.killed


def test_expired_shared_time_budget_is_partial_and_never_a_zero(tmp_path: Path) -> None:
    chunks = [record(sha(i), IN_WINDOW, ["docs/x"]) for i in range(5)]
    clock = FakeClock()
    # each log read advances the shared monotonic clock; the deadline passes on the third
    log = FakeProc(chunks, on_read=lambda: setattr(clock, "now", clock.now + BUDGET_SECONDS / 2.5))
    activity = load(tmp_path, FakePopen(head_proc(), log), threshold=20, clock=clock)
    assert activity.available and not activity.complete
    assert activity.truncation_reason == "deadline" and activity.scoped_commit_count is None
    assert log.killed


def test_unsupported_git_maps_to_git_unsupported_without_retry(tmp_path: Path) -> None:
    popen = FakePopen(
        FakeProc(b"", b"error: unknown option `no-lazy-fetch'\nusage: git ...\n", 129)
    )
    activity = load(tmp_path, popen)
    assert not activity.available and activity.unavailable_reason == "git_unsupported"
    assert "--no-lazy-fetch" in (activity.detail or "") and "2.45.0" in (activity.detail or "")
    assert popen.procs_started == 1  # no retry, no log call
    assert activity.scoped_commit_count is None and activity.lower_bound is None


def test_usage_error_from_the_log_call_is_git_unsupported_too(tmp_path: Path) -> None:
    popen = FakePopen(head_proc(), FakeProc(b"", b"unknown option\n", 129))
    activity = load(tmp_path, popen)
    assert activity.unavailable_reason == "git_unsupported" and popen.procs_started == 2


def test_nonzero_exit_after_partial_output_discards_the_tentative_count(tmp_path: Path) -> None:
    good = stream(*(record(sha(i), IN_WINDOW, ["src/a"]) for i in range(5)))
    log = FakeProc(good, b"fatal: bad object\n", 128)
    activity = load(tmp_path, FakePopen(head_proc(), log), threshold=20)
    assert not activity.available and activity.unavailable_reason == "git_failed"
    assert activity.scoped_commit_count is None and activity.lower_bound is None
    assert not activity.saturated and not activity.complete


def test_not_a_git_repository_is_unavailable_not_zero(tmp_path: Path) -> None:
    popen = FakePopen(FakeProc(b"", b"fatal: not a git repository (or any parent)\n", 128))
    activity = load(tmp_path, popen)
    assert activity.unavailable_reason == "not_a_git_repository" and popen.procs_started == 1


def test_missing_git_binary_is_unavailable(tmp_path: Path) -> None:
    activity = load(tmp_path, FakePopen(FileNotFoundError("git")))
    assert activity.unavailable_reason == "git_missing" and activity.git_calls == 0


def test_malformed_rev_parse_output_is_unavailable(tmp_path: Path) -> None:
    activity = load(tmp_path, FakePopen(FakeProc(b"not-a-sha\nmaybe\n")))
    assert activity.unavailable_reason == "git_failed"


def test_decode_errors_make_activity_unavailable(tmp_path: Path) -> None:
    activity = load(tmp_path, FakePopen(head_proc(), FakeProc(b"\x00garbage\x00")))
    assert activity.unavailable_reason == "decode_error" and activity.scoped_commit_count is None


def test_shallow_status_is_captured_with_head(tmp_path: Path) -> None:
    log = FakeProc(stream(record(sha(1), IN_WINDOW, ["src/a"])))
    activity = load(tmp_path, FakePopen(head_proc(shallow=True), log))
    assert activity.shallow is True and activity.complete and activity.scoped_commit_count == 1


def test_work_is_bounded_by_the_documented_defaults() -> None:
    assert (MAX_RECORDS, MAX_BYTES, BUDGET_SECONDS) == (5000, 16 * 1024 * 1024, 2.0)


def test_unrelated_exclusions_and_scope_apply_to_the_stream(tmp_path: Path) -> None:
    scope = scope_for(tmp_path, ("src",), ("src/vendor/**",))
    log = FakeProc(
        stream(
            record(sha(1), IN_WINDOW, ["src/vendor/x.py"]),
            record(sha(2), IN_WINDOW, ["src/vendor/y.py", "src/real.py"]),
            record(sha(3), IN_WINDOW, ["src-extra/z.py"]),
        )
    )
    activity = load(tmp_path, FakePopen(head_proc(), log), scope=scope)
    assert activity.scoped_commit_count == 1


def test_module_function_signature_is_importable_for_the_cli() -> None:
    assert callable(load_scope_activity)
