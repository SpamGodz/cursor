from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from cursor_ai.providers.openai_compat import OpenAICompatProvider
from cursor_ai.tools.base import ToolRegistry


def _tool_call_to_dict(call: object) -> dict:
    # Compatible with OpenAI tool call objects (chat.completions).
    fn = call.function
    return {
        "id": call.id,
        "type": "function",
        "function": {"name": fn.name, "arguments": fn.arguments},
    }


@dataclass
class Agent:
    provider: OpenAICompatProvider
    tools: ToolRegistry

    def run(
        self,
        *,
        messages: list[dict],
        max_steps: int = 12,
        stop_event: threading.Event | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> str:
        """
        Runs a tool-calling chat loop until the model returns a final message.
        """
        tools = self.tools.as_openai_tools()
        for _ in range(max_steps):
            if stop_event is not None and stop_event.is_set():
                raise RuntimeError("Stopped by user request.")
            result = self.provider.chat(messages=messages, tools=tools)
            tool_calls = result.tool_calls or []
            assistant_msg = {"role": "assistant", "content": result.content}
            if tool_calls:
                assistant_msg["tool_calls"] = [_tool_call_to_dict(c) for c in tool_calls]
            messages.append(assistant_msg)
            if on_event is not None:
                on_event(
                    {
                        "type": "assistant",
                        "content": result.content,
                        "tool_calls": assistant_msg.get("tool_calls"),
                        "usage": result.usage,
                    }
                )

            if not tool_calls:
                return (result.content or "").strip()

            for call in tool_calls:
                if stop_event is not None and stop_event.is_set():
                    raise RuntimeError("Stopped by user request.")
                fn = call.function
                output = self.tools.run(name=fn.name, arguments_json=fn.arguments)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": output,
                    }
                )
                if on_event is not None:
                    on_event({"type": "tool", "name": fn.name, "output": output})

        raise RuntimeError("Agent exceeded max_steps without returning a final answer.")
