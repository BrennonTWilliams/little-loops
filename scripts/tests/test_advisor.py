"""Tests for advisor module."""

from little_loops.advisor import MODEL_RANKS, check_floor, rank_model


class TestModelRanks:
    def test_claude_code_covers_haiku_sonnet_opus_fable(self):
        ranks = MODEL_RANKS["claude-code"]
        assert set(ranks) == {
            "claude-haiku-4-5",
            "claude-sonnet-5",
            "claude-opus-5",
            "claude-fable-5",
        }

    def test_claude_code_haiku_ranks_below_opus(self):
        ranks = MODEL_RANKS["claude-code"]
        assert ranks["claude-haiku-4-5"] < ranks["claude-opus-5"]

    def test_covers_canonical_host_name_set(self):
        assert set(MODEL_RANKS) == {
            "claude-code",
            "codex",
            "opencode",
            "pi",
            "gemini",
            "omp",
            "kimi-code",
        }


class TestRankModel:
    def test_alias_and_concrete_id_return_same_rank(self):
        assert rank_model("claude-code", "opus") == rank_model("claude-code", "claude-opus-5")

    def test_haiku_ranks_below_opus(self):
        assert rank_model("claude-code", "haiku") < rank_model("claude-code", "opus")

    def test_unknown_model_returns_none(self):
        assert rank_model("claude-code", "claude-opus-1-ancient") is None

    def test_unrankable_host_returns_none(self):
        assert rank_model("codex", "gpt-5") is None


class TestCheckFloor:
    def test_pinned_same_host_violation(self):
        result = check_floor("claude-code", "haiku", "claude-code", "opus")
        assert result.status == "violation"

    def test_same_mismatch_across_hosts_is_advisory(self):
        result = check_floor("codex", "haiku", "claude-code", "opus")
        assert result.status == "advisory"

    def test_unknown_model_returns_unknown_not_silent_pass(self):
        result = check_floor("claude-code", "claude-opus-1-ancient", "claude-code", "opus")
        assert result.status == "unknown"

    def test_cross_host_is_advisory_even_when_unrankable(self):
        # Pin: the cross-host check runs before rank lookup — two hosts'
        # rank tables are separate ordinal spaces, so a host mismatch is
        # "advisory" regardless of whether either model is rankable.
        result = check_floor("codex", "gpt-5", "claude-code", "opus")
        assert result.status == "advisory"

    def test_equal_rank_same_host_is_ok(self):
        # Pin: equality (advisor rank == main rank, same host) classifies as
        # "ok" — an advisor no weaker than main satisfies the floor. This
        # semantics choice was left open by FEAT-3108; pinned here.
        result = check_floor("claude-code", "opus", "claude-code", "opus")
        assert result.status == "ok"

    def test_advisor_ranked_above_main_same_host_is_ok(self):
        result = check_floor("claude-code", "opus", "claude-code", "haiku")
        assert result.status == "ok"
