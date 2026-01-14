from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class CursorConfig:
    """
    Configuration for a Cursor/OpenAI-compatible chat endpoint.

    Environment variables:
    - CURSOR_API_KEY
    - CURSOR_BASE_URL (optional)
    - CURSOR_MODEL (optional)
    """

    api_key: str
    base_url: str | None = None
    model: str = "gpt-4o-mini"

    @staticmethod
    def from_env() -> CursorConfig:
        api_key = os.getenv("CURSOR_API_KEY")
        if not api_key:
            raise RuntimeError("Missing CURSOR_API_KEY in environment.")
        base_url = os.getenv("CURSOR_BASE_URL")
        model = os.getenv("CURSOR_MODEL") or "gpt-4o-mini"
        return CursorConfig(api_key=api_key, base_url=base_url, model=model)
