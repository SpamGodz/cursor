from __future__ import annotations

from dataclasses import dataclass

from openai import OpenAI

from cursor_ai.config import CursorConfig


@dataclass(frozen=True)
class ChatResult:
    content: str | None
    tool_calls: list[object] | None
    raw: object


class OpenAICompatProvider:
    """
    Provider for OpenAI-compatible chat endpoints (Cursor can be wired via base_url + api_key).
    """

    def __init__(self, config: CursorConfig):
        self._config = config
        self._client = OpenAI(api_key=config.api_key, base_url=config.base_url)

    @property
    def model(self) -> str:
        return self._config.model

    def chat(self, *, messages: list[dict], tools: list[dict] | None = None) -> ChatResult:
        resp = self._client.chat.completions.create(
            model=self._config.model,
            messages=messages,
            tools=tools,
        )
        msg = resp.choices[0].message
        return ChatResult(content=msg.content, tool_calls=getattr(msg, "tool_calls", None), raw=resp)

