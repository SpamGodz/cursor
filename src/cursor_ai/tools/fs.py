from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


class UnsafePathError(ValueError):
    pass


def _safe_join(workspace: Path, rel_path: str) -> Path:
    ws = workspace.resolve()
    p = (ws / rel_path).resolve()
    # Ensure p is inside ws (or equal).
    if p != ws and ws not in p.parents:
        raise UnsafePathError(f"Path escapes workspace: {rel_path}")
    return p


@dataclass(frozen=True)
class ListFilesTool:
    workspace: Path
    name: str = "fs_list"
    description: str = "List files/directories under the workspace."

    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path under workspace."},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        }

    def run(self, arguments: dict[str, Any]) -> Any:
        rel = str(arguments["path"])
        p = _safe_join(self.workspace, rel)
        if not p.exists():
            return {"ok": False, "error": "not_found"}
        if not p.is_dir():
            return {"ok": False, "error": "not_a_directory"}
        items = []
        for child in sorted(p.iterdir(), key=lambda c: c.name):
            items.append({"name": child.name, "type": "dir" if child.is_dir() else "file"})
        return {"ok": True, "items": items}


@dataclass(frozen=True)
class ReadFileTool:
    workspace: Path
    name: str = "fs_read"
    description: str = "Read a UTF-8 text file under the workspace."

    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path under workspace."},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        }

    def run(self, arguments: dict[str, Any]) -> Any:
        rel = str(arguments["path"])
        p = _safe_join(self.workspace, rel)
        if not p.exists():
            return {"ok": False, "error": "not_found"}
        if not p.is_file():
            return {"ok": False, "error": "not_a_file"}
        return {"ok": True, "content": p.read_text(encoding="utf-8")}


@dataclass(frozen=True)
class WriteFileTool:
    workspace: Path
    name: str = "fs_write"
    description: str = "Write a UTF-8 text file under the workspace."

    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path under workspace."},
                    "content": {"type": "string", "description": "Full file contents."},
                    "mkdirs": {"type": "boolean", "description": "Create parent dirs if needed."},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        }

    def run(self, arguments: dict[str, Any]) -> Any:
        rel = str(arguments["path"])
        content = str(arguments["content"])
        mkdirs = bool(arguments.get("mkdirs", True))
        p = _safe_join(self.workspace, rel)
        if mkdirs:
            p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"ok": True}

