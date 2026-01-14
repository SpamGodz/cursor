from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from cursor_ai.agent import Agent
from cursor_ai.config import CursorConfig
from cursor_ai.providers.openai_compat import OpenAICompatProvider
from cursor_ai.tools.base import ToolRegistry
from cursor_ai.tools.fs import ListFilesTool, ReadFileTool, WriteFileTool


@dataclass(frozen=True)
class Args:
    command: str
    goal: str | None = None
    workspace: Path | None = None
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


def parse_args(argv: list[str] | None = None) -> Args:
    parser = argparse.ArgumentParser(prog="cursor_ai")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("hello", help="Print a greeting.")
    run_p = sub.add_parser("run", help="Run an agent on a goal (tool-calling).")
    run_p.add_argument("goal", type=str, help="Goal or task description.")
    run_p.add_argument("--workspace", type=Path, default=Path.cwd(), help="Workspace root.")
    run_p.add_argument("--api-key", type=str, default=None, help="Override CURSOR_API_KEY.")
    run_p.add_argument("--base-url", type=str, default=None, help="Override CURSOR_BASE_URL.")
    run_p.add_argument("--model", type=str, default=None, help="Override CURSOR_MODEL.")

    chat_p = sub.add_parser("chat", help="Interactive chat (tool-calling).")
    chat_p.add_argument("--workspace", type=Path, default=Path.cwd(), help="Workspace root.")
    chat_p.add_argument("--api-key", type=str, default=None, help="Override CURSOR_API_KEY.")
    chat_p.add_argument("--base-url", type=str, default=None, help="Override CURSOR_BASE_URL.")
    chat_p.add_argument("--model", type=str, default=None, help="Override CURSOR_MODEL.")
    ns = parser.parse_args(argv)
    return Args(
        command=ns.command,
        goal=getattr(ns, "goal", None),
        workspace=getattr(ns, "workspace", None),
        api_key=getattr(ns, "api_key", None),
        base_url=getattr(ns, "base_url", None),
        model=getattr(ns, "model", None),
    )


def _build_agent(args: Args) -> Agent:
    cfg = CursorConfig.from_env()
    if args.api_key:
        cfg = CursorConfig(api_key=args.api_key, base_url=cfg.base_url, model=cfg.model)
    if args.base_url is not None:
        cfg = CursorConfig(api_key=cfg.api_key, base_url=args.base_url, model=cfg.model)
    if args.model is not None:
        cfg = CursorConfig(api_key=cfg.api_key, base_url=cfg.base_url, model=args.model)

    workspace = (args.workspace or Path.cwd()).resolve()
    tools = ToolRegistry(
        tools=[
            ListFilesTool(workspace=workspace),
            ReadFileTool(workspace=workspace),
            WriteFileTool(workspace=workspace),
        ]
    )
    provider = OpenAICompatProvider(cfg)
    return Agent(provider=provider, tools=tools)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "hello":
        print("hello")
        return 0
    if args.command == "run":
        agent = _build_agent(args)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an agentic assistant. Use tools when helpful. "
                    "When you are done, respond with a final answer."
                ),
            },
            {"role": "user", "content": args.goal or ""},
        ]
        out = agent.run(messages=messages)
        print(out)
        return 0
    if args.command == "chat":
        agent = _build_agent(args)
        messages: list[dict] = [
            {
                "role": "system",
                "content": (
                    "You are an agentic assistant. Use tools when helpful. "
                    "When you are done, respond with a final answer."
                ),
            }
        ]
        try:
            while True:
                prompt = input("> ").strip()
                if not prompt:
                    continue
                if prompt in {"/exit", "/quit"}:
                    return 0
                messages.append({"role": "user", "content": prompt})
                out = agent.run(messages=messages)
                print(out)
        except EOFError:
            return 0
    raise AssertionError(f"Unhandled command: {args.command}")
