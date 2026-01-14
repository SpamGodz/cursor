from __future__ import annotations

import asyncio
import json
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
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

    # -------- Evals / Improvements (100% user-verified) ----------
    def list_eval_suites(self) -> list[dict[str, Any]]:
        suites = db.list_eval_suites(self._conn, limit=100)
        if suites:
            return suites
        # Create a tiny default suite so the UI isn't empty.
        sid = uuid.uuid4().hex
        now = db.utcnow()
        db.insert_eval_suite(self._conn, suite_id=sid, name="Default suite", created_at=now)
        db.insert_eval_case(
            self._conn,
            case_id=uuid.uuid4().hex,
            suite_id=sid,
            title="Repo scan & plan",
            goal="Scan the repo and propose a short actionable plan in TODO.md.",
            rubric="Plan should be concrete and actionable.",
            now=now,
        )
        return db.list_eval_suites(self._conn, limit=100)

    def create_eval_suite(self, *, name: str) -> dict[str, Any]:
        sid = uuid.uuid4().hex
        db.insert_eval_suite(self._conn, suite_id=sid, name=name, created_at=db.utcnow())
        return {"id": sid}

    def list_eval_cases(self, suite_id: str) -> list[dict[str, Any]]:
        return db.list_eval_cases(self._conn, suite_id, limit=500)

    def add_eval_case(
        self, *, suite_id: str, title: str, goal: str, rubric: str | None
    ) -> dict[str, Any]:
        cid = uuid.uuid4().hex
        db.insert_eval_case(
            self._conn,
            case_id=cid,
            suite_id=suite_id,
            title=title,
            goal=goal,
            rubric=rubric,
            now=db.utcnow(),
        )
        return {"id": cid}

    def list_eval_runs(self) -> list[dict[str, Any]]:
        return db.list_eval_runs(self._conn, limit=50)

    def get_eval_run(self, eval_run_id: str) -> dict[str, Any] | None:
        return db.get_eval_run(self._conn, eval_run_id)

    def get_eval_results(self, eval_run_id: str) -> list[dict[str, Any]]:
        return db.list_eval_case_results(self._conn, eval_run_id)

    def list_improvements(self) -> list[dict[str, Any]]:
        return db.list_improvements(self._conn, limit=50)

    def get_baseline_snapshot_id(self) -> str | None:
        return db.get_preference(self._conn, key="baseline_snapshot_id")

    def set_baseline_snapshot_id(self, snapshot_id: str) -> None:
        db.set_preference(self._conn, key="baseline_snapshot_id", value=snapshot_id)

    def get_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        return db.get_snapshot(self._conn, snapshot_id)

    def list_snapshots(self) -> list[dict[str, Any]]:
        return db.list_snapshots(self._conn, limit=50)

    async def start_eval(
        self,
        *,
        suite_id: str,
        workspace: Path,
        label: str | None = None,
    ) -> str:
        """
        Runs all cases in a suite and stores outputs + metrics.
        Nothing is automatically "good"—user must approve an eval run as an improvement.
        """
        cases = db.list_eval_cases(self._conn, suite_id, limit=500)
        snapshot_id = uuid.uuid4().hex
        eval_run_id = uuid.uuid4().hex
        now = db.utcnow()
        snapshot = self.get_preferences()
        db.insert_snapshot(
            self._conn,
            snapshot_id=snapshot_id,
            label=label,
            created_at=now,
            data=snapshot,
        )
        db.insert_eval_run(
            self._conn,
            eval_run_id=eval_run_id,
            suite_id=suite_id,
            snapshot_id=snapshot_id,
            status="queued",
            created_at=now,
            cases_total=len(cases),
        )

        async def runner() -> None:
            started = db.utcnow()
            db.update_eval_run(
                self._conn,
                eval_run_id=eval_run_id,
                status="running",
                started_at=started,
            )
            durations: list[float] = []
            tokens: list[int] = []
            tool_calls_total = 0
            done = 0
            try:
                enable_write = bool(snapshot.get("enable_write"))
                model = snapshot.get("model")
                base_url = snapshot.get("base_url")
                system_prompt = str(snapshot.get("system_prompt") or "")
                max_steps = int(snapshot.get("max_steps") or 24)
                agent = _build_agent(
                    workspace=workspace,
                    api_key=None,
                    base_url=str(base_url) if base_url else None,
                    model=str(model) if model else None,
                    enable_write=enable_write,
                )

                for c in cases:
                    started_case = perf_counter()
                    tool_calls = 0
                    prompt_tokens = 0
                    completion_tokens = 0
                    total_tokens = 0

                    def on_event(evt: dict[str, Any]) -> None:
                        nonlocal tool_calls, prompt_tokens, completion_tokens, total_tokens
                        if evt.get("type") == "tool":
                            tool_calls += 1
                        if evt.get("type") == "assistant":
                            usage = evt.get("usage") or {}
                            prompt_tokens += int(usage.get("prompt_tokens") or 0)
                            completion_tokens += int(usage.get("completion_tokens") or 0)
                            total_tokens += int(usage.get("total_tokens") or 0)

                    messages: list[dict[str, Any]] = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": c["goal"]},
                    ]
                    try:
                        out = await asyncio.to_thread(
                            agent.run, messages=messages, max_steps=max_steps, on_event=on_event
                        )
                        dur = perf_counter() - started_case
                        db.upsert_eval_case_result(
                            self._conn,
                            eval_run_id=eval_run_id,
                            case_id=c["id"],
                            status="needs_review",
                            output=out,
                            duration_s=dur,
                            prompt_tokens=prompt_tokens or None,
                            completion_tokens=completion_tokens or None,
                            total_tokens=total_tokens or None,
                            tool_calls=tool_calls,
                            error=None,
                        )
                        durations.append(float(dur))
                        if total_tokens:
                            tokens.append(int(total_tokens))
                        tool_calls_total += int(tool_calls)
                    except Exception as e:  # noqa: BLE001
                        dur = perf_counter() - started_case
                        db.upsert_eval_case_result(
                            self._conn,
                            eval_run_id=eval_run_id,
                            case_id=c["id"],
                            status="error",
                            output=None,
                            duration_s=dur,
                            prompt_tokens=prompt_tokens or None,
                            completion_tokens=completion_tokens or None,
                            total_tokens=total_tokens or None,
                            tool_calls=tool_calls,
                            error=repr(e),
                        )
                        tool_calls_total += int(tool_calls)

                    done += 1
                    db.update_eval_run(
                        self._conn,
                        eval_run_id=eval_run_id,
                        cases_done=done,
                        total_tool_calls=tool_calls_total,
                    )

                ended = db.utcnow()
                avg_dur = (sum(durations) / len(durations)) if durations else None
                avg_tok = (sum(tokens) / len(tokens)) if tokens else None
                db.update_eval_run(
                    self._conn,
                    eval_run_id=eval_run_id,
                    status="completed",
                    ended_at=ended,
                    avg_duration_s=avg_dur,
                    avg_total_tokens=avg_tok,
                    total_tool_calls=tool_calls_total,
                    cases_done=done,
                )
            except Exception as e:  # noqa: BLE001
                ended = db.utcnow()
                db.update_eval_run(
                    self._conn,
                    eval_run_id=eval_run_id,
                    status="failed",
                    ended_at=ended,
                    error=repr(e),
                    cases_done=done,
                    total_tool_calls=tool_calls_total,
                )

        asyncio.create_task(runner())
        return eval_run_id

    def review_eval_case(
        self, *, eval_run_id: str, case_id: str, verdict: str, notes: str | None
    ) -> None:
        db.review_eval_case_result(
            self._conn,
            eval_run_id=eval_run_id,
            case_id=case_id,
            verdict=verdict,
            notes=notes,
            reviewed_at=db.utcnow(),
        )

    def approve_improvement(self, *, eval_run_id: str, notes: str | None) -> dict[str, Any]:
        run = db.get_eval_run(self._conn, eval_run_id)
        if not run:
            raise KeyError("eval_run not found")
        snapshot_id = run["snapshot_id"]
        iid = uuid.uuid4().hex
        db.insert_improvement(
            self._conn,
            improvement_id=iid,
            eval_run_id=eval_run_id,
            snapshot_id=snapshot_id,
            verdict="approved",
            notes=notes,
            verified_at=db.utcnow(),
        )
        # Promote approved snapshot to baseline (your definition of improvement).
        self.set_baseline_snapshot_id(snapshot_id)
        return {"improvement_id": iid, "baseline_snapshot_id": snapshot_id}

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
