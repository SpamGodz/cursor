from __future__ import annotations

import pytest

from cursor_ai.config import CursorConfig


def test_from_env_requires_key(monkeypatch) -> None:
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        CursorConfig.from_env()


def test_from_env_reads_values(monkeypatch) -> None:
    monkeypatch.setenv("CURSOR_API_KEY", "k")
    monkeypatch.setenv("CURSOR_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("CURSOR_MODEL", "m")
    cfg = CursorConfig.from_env()
    assert cfg.api_key == "k"
    assert cfg.base_url == "https://example.invalid"
    assert cfg.model == "m"
