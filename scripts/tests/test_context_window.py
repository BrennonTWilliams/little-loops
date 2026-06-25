"""Tests for context_window module."""
from little_loops.context_window import context_window_for


class TestContextWindowFor:
    def test_1m_suffix_returns_1_million(self):
        assert context_window_for("claude-opus-4-8[1m]") == 1_000_000

    def test_sonnet_1m_suffix_returns_1_million(self):
        assert context_window_for("claude-sonnet-4-6[1m]") == 1_000_000

    def test_known_opus_returns_200k(self):
        assert context_window_for("claude-opus-4-8") == 200_000

    def test_known_sonnet_returns_200k(self):
        assert context_window_for("claude-sonnet-4-6") == 200_000

    def test_known_haiku_returns_200k(self):
        assert context_window_for("claude-haiku-4-5-20251001") == 200_000

    def test_none_returns_200k_floor(self):
        assert context_window_for(None) == 200_000

    def test_unknown_model_returns_200k_floor(self):
        assert context_window_for("unknown-model-xyz") == 200_000

    def test_override_arg_wins_over_model_lookup(self):
        assert context_window_for("claude-opus-4-8[1m]", override=500_000) == 500_000

    def test_override_arg_wins_over_env_var(self, monkeypatch):
        monkeypatch.setenv("LL_CONTEXT_LIMIT", "1000000")
        assert context_window_for("claude-opus-4-8", override=300_000) == 300_000

    def test_env_var_wins_over_model_lookup(self, monkeypatch):
        monkeypatch.setenv("LL_CONTEXT_LIMIT", "500000")
        assert context_window_for("claude-opus-4-8") == 500_000

    def test_env_var_1m_wins_over_model_lookup(self, monkeypatch):
        monkeypatch.setenv("LL_CONTEXT_LIMIT", "1000000")
        assert context_window_for("claude-opus-4-8") == 1_000_000

    def test_env_var_invalid_falls_through_to_lookup(self, monkeypatch):
        monkeypatch.setenv("LL_CONTEXT_LIMIT", "notanumber")
        assert context_window_for("claude-opus-4-8[1m]") == 1_000_000

    def test_env_var_zero_falls_through_to_lookup(self, monkeypatch):
        monkeypatch.setenv("LL_CONTEXT_LIMIT", "0")
        assert context_window_for("claude-opus-4-8[1m]") == 1_000_000

    def test_returns_int(self):
        result = context_window_for("claude-opus-4-8")
        assert isinstance(result, int)

    def test_override_zero_falls_through_to_lookup(self):
        # override=0 is treated as "not set" — falls through to model lookup
        assert context_window_for("claude-opus-4-8[1m]", override=0) == 1_000_000
