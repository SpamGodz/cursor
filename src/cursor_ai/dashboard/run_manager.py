from __future__ import annotations

import asyncio
import json
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from cursor_ai.agent import Agent
from cursor_ai.config import CursorConfig
from cursor_ai.dashboard import db
from cursor_ai.providers.openai_compat import OpenAICompatProvider
from cursor_ai.tools.base import ToolRegistry
from cursor_ai.tools.fs import ListFilesTool, ReadFileTool, WriteFileTool


@dataclass
class LiveRun:
    run_id: str
    stop_event: threading.Event
    queue: asyncio.Queue[str]
    started_at: datetime
    task: asyncio.Task[None]


def _build_agent(
    *,
    workspace: Path,
    api_key: str | None,
    base_url: str | None,
    model: str | None,
    enable_write: bool,
) -> Agent:
    cfg = CursorConfig.from_env()
    if api_key is not None:
        cfg = CursorConfig(api_key=api_key, base_url=cfg.base_url, model=cfg.model)
    if base_url is not None:
        cfg = CursorConfig(api_key=cfg.api_key, base_url=base_url, model=cfg.model)
    if model is not None:
        cfg = CursorConfig(api_key=cfg.api_key, base_url=cfg.base_url, model=model)

    tools_list = [
        ListFilesTool(workspace=workspace),
        ReadFileTool(workspace=workspace),
    ]
    if enable_write:
        tools_list.append(WriteFileTool(workspace=workspace))
    tools = ToolRegistry(tools=tools_list)
    provider = OpenAICompatProvider(cfg)
    return Agent(provider=provider, tools=tools)


class RunManager:
    def __init__(self, *, db_path: Path):
        self._conn = db.connect(db_path)
        db.init(self._conn)
        self._lock = threading.Lock()
        self._live: dict[str, LiveRun] = {}

    # -------- Preferences / Studio ----------
    def get_preferences(self) -> dict[str, Any]:
        prefs = db.list_preferences(self._conn)
        # Defaults (so UI is usable on first load)
        prefs.setdefault(
            "system_prompt",
            (
                "You are an agentic assistant. Use tools when helpful. "
                "When you are done, respond with a final answer."
            ),
        )
        prefs.setdefault("max_steps", 24)
        prefs.setdefault("enable_write", True)
        prefs.setdefault("model", None)
        prefs.setdefault("base_url", None)
        return prefs

    def set_preferences(self, prefs: dict[str, Any]) -> dict[str, Any]:
        # Save only known keys
        allowed = {"system_prompt", "max_steps", "enable_write", "model", "base_url"}
        for k, v in prefs.items():
            if k in allowed:
                db.set_preference(self._conn, key=k, value=v)
        return self.get_preferences()

    def list_features(self) -> list[dict[str, Any]]:
        return db.list_features(self._conn, limit=200)

    def add_feature(self, *, title: str, description: str) -> dict[str, Any]:
        fid = uuid.uuid4().hex
        now = db.utcnow()
        db.insert_feature(
            self._conn,
            feature_id=fid,
            title=title,
            description=description,
            status="backlog",
            now=now,
        )
        return {"id": fid}

    def move_feature(self, *, feature_id: str, status: str) -> None:
        db.update_feature_status(self._conn, feature_id=feature_id, status=status, now=db.utcnow())

    def start_chat(self) -> str:
        cid = uuid.uuid4().hex
        db.insert_chat(self._conn, chat_id=cid, now=db.utcnow())
        return cid

    def list_chat_messages(self, chat_id: str) -> list[dict[str, Any]]:
        return db.list_chat_messages(self._conn, chat_id=chat_id, limit=500)

    def chat_send(self, *, chat_id: str, message: str, workspace: Path) -> dict[str, Any]:
        prefs = self.get_preferences()
        system_prompt = str(prefs.get("system_prompt") or "")
        max_steps = int(prefs.get("max_steps") or 24)
        enable_write = bool(prefs.get("enable_write"))
        model = prefs.get("model")
        base_url = prefs.get("base_url")

        agent = _build_agent(
            workspace=workspace,
            api_key=None,
            base_url=str(base_url) if base_url else None,
            model=str(model) if model else None,
            enable_write=enable_write,
        )

        db.insert_chat_message(
            self._conn, chat_id=chat_id, ts=db.utcnow(), role="user", content=message
        )

        history = db.list_chat_messages(self._conn, chat_id=chat_id, limit=500)
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        for m in history:
            messages.append({"role": m["role"], "content": m["content"]})

        out = agent.run(messages=messages, max_steps=max_steps)
        db.insert_chat_message(
            self._conn, chat_id=chat_id, ts=db.utcnow(), role="assistant", content=out
        )
        return {"assistant": out}

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        return [r.as_dict() for r in db.list_runs(self._conn, limit=limit)]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        r = db.get_run(self._conn, run_id)
        return r.as_dict() if r else None

    def get_events(self, run_id: str, limit: int = 500) -> list[dict[str, Any]]:
        return db.list_events(self._conn, run_id, limit=limit)

    def get_stats(self) -> dict[str, Any]:
        runs = db.list_runs(self._conn, limit=500)
        total = len(runs)
        successes = sum(1 for r in runs if r.status == "succeeded")
        failed = sum(1 for r in runs if r.status == "failed")
        cancelled = sum(1 for r in runs if r.status == "cancelled")
        durations = [r.duration_s for r in runs if r.duration_s is not None]
        avg_dur = (sum(durations) / len(durations)) if durations else None

        # "Training/improvement" proxy metrics: compare last 10 vs previous 10.
        def avg(xs: list[float]) -> float | None:
            return (sum(xs) / len(xs)) if xs else None

        last10 = [r for r in runs[:10] if r.duration_s is not None]
        prev10 = [r for r in runs[10:20] if r.duration_s is not None]
        last_avg = avg([float(r.duration_s) for r in last10 if r.duration_s is not None])
        prev_avg = avg([float(r.duration_s) for r in prev10 if r.duration_s is not None])
        trend = None
        if last_avg is not None and prev_avg is not None and prev_avg != 0:
            trend = (last_avg - prev_avg) / prev_avg

        tokens = [r.total_tokens for r in runs if r.total_tokens is not None]
        avg_tokens = (sum(tokens) / len(tokens)) if tokens else None

        return {
            "runs_total": total,
            "runs_succeeded": successes,
            "runs_failed": failed,
            "runs_cancelled": cancelled,
            "avg_duration_s": avg_dur,
            "avg_total_tokens": avg_tokens,
            "duration_trend_last10_vs_prev10": trend,
        }

    async def start_run(
        self,
        *,
        goal: str,
        workspace: Path,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        max_steps: int | None = None,
        enable_write: bool | None = None,
    ) -> str:
        run_id = uuid.uuid4().hex
        started_at = db.utcnow()
        stop_event = threading.Event()
        queue: asyncio.Queue[str] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        # Persist run
        # Model/base_url may be None if inherited from env; store overrides for visibility.
        db.insert_run(
            self._conn,
            run_id=run_id,
            goal=goal,
            status="running",
            model=model or CursorConfig.from_env().model,
            base_url=base_url or CursorConfig.from_env().base_url,
            started_at=started_at,
        )

        def emit(kind: str, content: Any) -> None:
            payload = {"ts": db.to_iso(db.utcnow()), "kind": kind, "content": content}
            msg = json.dumps(payload, ensure_ascii=False)
            db.insert_event(
                self._conn, run_id=run_id, ts=db.utcnow(), kind=kind, content=str(content)
            )
            loop.call_soon_threadsafe(queue.put_nowait, msg)

        async def runner() -> None:
            tool_calls = 0
            messages_count = 0
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0

            try:
                prefs = self.get_preferences()
                sp = system_prompt or str(prefs.get("system_prompt") or "")
                ms = int(max_steps or prefs.get("max_steps") or 24)
                ew = bool(enable_write if enable_write is not None else prefs.get("enable_write"))
                effective_model = model or (prefs.get("model") if prefs.get("model") else None)
                effective_base_url = base_url or (
                    prefs.get("base_url") if prefs.get("base_url") else None
                )
                agent = _build_agent(
                    workspace=workspace,
                    api_key=api_key,
                    base_url=effective_base_url,
                    model=effective_model,
                    enable_write=ew,
                )
                messages: list[dict] = [
                    {
                        "role": "system",
                        "content": sp,
                    },
                    {"role": "user", "content": goal},
                ]

                def on_event(evt: dict[str, Any]) -> None:
                    nonlocal \
                        tool_calls, \
                        messages_count, \
                        prompt_tokens, \
                        completion_tokens, \
                        total_tokens
                    kind = evt.get("type", "event")
                    if kind == "assistant":
                        messages_count += 1
                        emit("assistant", evt.get("content") or "")
                        usage = evt.get("usage") or {}
                        prompt_tokens += int(usage.get("prompt_tokens") or 0)
                        completion_tokens += int(usage.get("completion_tokens") or 0)
                        total_tokens += int(usage.get("total_tokens") or 0)
                    elif kind == "tool":
                        tool_calls += 1
                        emit("tool", {"name": evt.get("name"), "output": evt.get("output")})
                    else:
                        emit("event", evt)

                def run_in_thread() -> str:
                    return agent.run(
                        messages=messages, max_steps=ms, stop_event=stop_event, on_event=on_event
                    )

                result = await asyncio.to_thread(run_in_thread)
                emit("final", result)
                ended = db.utcnow()
                dur = (ended - started_at).total_seconds()
                db.update_run(
                    self._conn,
                    run_id=run_id,
                    status="succeeded",
                    ended_at=ended,
                    duration_s=dur,
                    tool_calls=tool_calls,
                    messages=messages_count,
                    prompt_tokens=prompt_tokens or None,
                    completion_tokens=completion_tokens or None,
                    total_tokens=total_tokens or None,
                )
            except RuntimeError as e:
                ended = db.utcnow()
                dur = (ended - started_at).total_seconds()
                status = "cancelled" if "stop" in str(e).lower() else "failed"
                emit("error", str(e))
                db.update_run(
                    self._conn,
                    run_id=run_id,
                    status=status,
                    ended_at=ended,
                    duration_s=dur,
                    error=str(e),
                )
            except Exception as e:  # noqa: BLE001
                ended = db.utcnow()
                dur = (ended - started_at).total_seconds()
                emit("error", repr(e))
                db.update_run(
                    self._conn,
                    run_id=run_id,
                    status="failed",
                    ended_at=ended,
                    duration_s=dur,
                    error=repr(e),
                )
            finally:
                with self._lock:
                    self._live.pop(run_id, None)
                loop.call_soon_threadsafe(queue.put_nowait, json.dumps({"kind": "eof"}))

        task = asyncio.create_task(runner())
        with self._lock:
            self._live[run_id] = LiveRun(
                run_id=run_id, stop_event=stop_event, queue=queue, started_at=started_at, task=task
            )
        emit("status", {"status": "running", "run_id": run_id})
        return run_id

    def stop_run(self, run_id: str) -> bool:
        with self._lock:
            live = self._live.get(run_id)
        if not live:
            return False
        live.stop_event.set()
        db.insert_event(
            self._conn, run_id=run_id, ts=db.utcnow(), kind="status", content="stop_requested"
        )
        return True

    def get_live_queue(self, run_id: str) -> asyncio.Queue[str] | None:
        with self._lock:
            live = self._live.get(run_id)
        return live.queue if live else None
