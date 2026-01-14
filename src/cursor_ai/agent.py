from __future__ import annotations

from dataclasses import dataclass

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
    ) -> str:
        """
        Runs a tool-calling chat loop until the model returns a final message.
        """
        tools = self.tools.as_openai_tools()
        for _ in range(max_steps):
            result = self.provider.chat(messages=messages, tools=tools)
            tool_calls = result.tool_calls or []
            assistant_msg = {"role": "assistant", "content": result.content}
            if tool_calls:
                assistant_msg["tool_calls"] = [_tool_call_to_dict(c) for c in tool_calls]
            messages.append(assistant_msg)

            if not tool_calls:
                return (result.content or "").strip()

            for call in tool_calls:
                fn = call.function
                output = self.tools.run(name=fn.name, arguments_json=fn.arguments)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": output,
                    }
                )

        raise RuntimeError("Agent exceeded max_steps without returning a final answer.")

