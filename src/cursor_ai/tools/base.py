from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol


class Tool(Protocol):
    name: str
    description: str

    def schema(self) -> dict[str, Any]: ...

    def run(self, arguments: dict[str, Any]) -> Any: ...


@dataclass
class ToolRegistry:
    tools: list[Tool]

    def as_openai_tools(self) -> list[dict[str, Any]]:
        return [{"type": "function", "function": t.schema()} for t in self.tools]

    def get(self, name: str) -> Tool:
        for t in self.tools:
            if t.name == name:
                return t
        raise KeyError(f"Unknown tool: {name}")

    def run(self, *, name: str, arguments_json: str) -> str:
        tool = self.get(name)
        args = json.loads(arguments_json or "{}")
        result = tool.run(args)
        return json.dumps(result, ensure_ascii=False)
