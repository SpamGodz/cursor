from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from cursor_ai.dashboard.run_manager import RunManager


def create_app(*, db_path: Path, workspace: Path) -> FastAPI:
    app = FastAPI(title="Cursor AI Dashboard")
    manager = RunManager(db_path=db_path)

    pkg_dir = Path(__file__).parent
    templates = Jinja2Templates(directory=str(pkg_dir / "templates"))
    app.mount("/static", StaticFiles(directory=str(pkg_dir / "static")), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "workspace": str(workspace),
            },
        )

    @app.get("/studio", response_class=HTMLResponse)
    async def studio(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            "studio.html",
            {
                "request": request,
                "workspace": str(workspace),
            },
        )

    @app.get("/api/stats", response_class=JSONResponse)
    async def stats() -> JSONResponse:
        return JSONResponse(manager.get_stats())

    @app.get("/api/runs", response_class=JSONResponse)
    async def runs() -> JSONResponse:
        return JSONResponse({"runs": manager.list_runs(limit=50)})

    @app.get("/api/runs/{run_id}", response_class=JSONResponse)
    async def run_get(run_id: str) -> JSONResponse:
        r = manager.get_run(run_id)
        if r is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        return JSONResponse(r)

    class StartBody(BaseModel):
        goal: str
        workspace: str | None = None
        api_key: str | None = None
        base_url: str | None = None
        model: str | None = None
        system_prompt: str | None = None
        max_steps: int | None = None
        enable_write: bool | None = None

    @app.post("/api/runs/start", response_class=JSONResponse)
    async def run_start(body: StartBody) -> JSONResponse:
        ws = Path(body.workspace).expanduser().resolve() if body.workspace else workspace
        run_id = await manager.start_run(
            goal=body.goal,
            workspace=ws,
            api_key=body.api_key,
            base_url=body.base_url,
            model=body.model,
            system_prompt=body.system_prompt,
            max_steps=body.max_steps,
            enable_write=body.enable_write,
        )
        return JSONResponse({"run_id": run_id})

    @app.post("/api/runs/{run_id}/stop", response_class=JSONResponse)
    async def run_stop(run_id: str) -> JSONResponse:
        ok = manager.stop_run(run_id)
        return JSONResponse({"ok": ok})

    @app.get("/api/runs/{run_id}/events")
    async def run_events(run_id: str) -> StreamingResponse:
        """
        Server-Sent Events stream for live run logs.
        """
        q = manager.get_live_queue(run_id)

        async def gen() -> Any:
            # First: replay persisted events for context.
            for e in manager.get_events(run_id, limit=500):
                yield f"data: {json.dumps(e, ensure_ascii=False)}\n\n"
            if q is None:
                yield 'data: {"kind":"eof"}\n\n'
                return
            while True:
                msg = await q.get()
                if msg:
                    yield f"data: {msg}\n\n"
                if '"eof"' in msg:
                    return

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.get("/api/preferences", response_class=JSONResponse)
    async def preferences_get() -> JSONResponse:
        return JSONResponse(manager.get_preferences())

    class PreferencesBody(BaseModel):
        system_prompt: str | None = None
        max_steps: int | None = None
        enable_write: bool | None = None
        model: str | None = None
        base_url: str | None = None

    @app.post("/api/preferences", response_class=JSONResponse)
    async def preferences_set(body: PreferencesBody) -> JSONResponse:
        saved = manager.set_preferences(body.model_dump())
        return JSONResponse(saved)

    @app.get("/api/features", response_class=JSONResponse)
    async def features_list() -> JSONResponse:
        return JSONResponse({"features": manager.list_features()})

    class FeatureCreateBody(BaseModel):
        title: str
        description: str = ""

    @app.post("/api/features", response_class=JSONResponse)
    async def feature_create(body: FeatureCreateBody) -> JSONResponse:
        out = manager.add_feature(title=body.title, description=body.description)
        return JSONResponse(out)

    class FeatureMoveBody(BaseModel):
        status: str

    @app.post("/api/features/{feature_id}/move", response_class=JSONResponse)
    async def feature_move(feature_id: str, body: FeatureMoveBody) -> JSONResponse:
        manager.move_feature(feature_id=feature_id, status=body.status)
        return JSONResponse({"ok": True})

    @app.post("/api/chat/start", response_class=JSONResponse)
    async def chat_start() -> JSONResponse:
        return JSONResponse({"chat_id": manager.start_chat()})

    @app.get("/api/chat/{chat_id}", response_class=JSONResponse)
    async def chat_get(chat_id: str) -> JSONResponse:
        return JSONResponse({"messages": manager.list_chat_messages(chat_id)})

    class ChatSendBody(BaseModel):
        message: str
        workspace: str | None = None

    @app.post("/api/chat/{chat_id}/send", response_class=JSONResponse)
    async def chat_send(chat_id: str, body: ChatSendBody) -> JSONResponse:
        ws = Path(body.workspace).expanduser().resolve() if body.workspace else workspace
        out = manager.chat_send(chat_id=chat_id, message=body.message, workspace=ws)
        return JSONResponse(out)

    # -------- Evals / improvements (user verified) ----------
    @app.get("/api/evals/suites", response_class=JSONResponse)
    async def eval_suites() -> JSONResponse:
        return JSONResponse({"suites": manager.list_eval_suites()})

    class EvalSuiteCreateBody(BaseModel):
        name: str

    @app.post("/api/evals/suites", response_class=JSONResponse)
    async def eval_suite_create(body: EvalSuiteCreateBody) -> JSONResponse:
        return JSONResponse(manager.create_eval_suite(name=body.name))

    @app.get("/api/evals/suites/{suite_id}/cases", response_class=JSONResponse)
    async def eval_cases(suite_id: str) -> JSONResponse:
        return JSONResponse({"cases": manager.list_eval_cases(suite_id)})

    class EvalCaseCreateBody(BaseModel):
        title: str
        goal: str
        rubric: str | None = None

    @app.post("/api/evals/suites/{suite_id}/cases", response_class=JSONResponse)
    async def eval_case_create(suite_id: str, body: EvalCaseCreateBody) -> JSONResponse:
        return JSONResponse(
            manager.add_eval_case(
                suite_id=suite_id,
                title=body.title,
                goal=body.goal,
                rubric=body.rubric,
            )
        )

    class EvalRunStartBody(BaseModel):
        suite_id: str
        workspace: str | None = None
        label: str | None = None

    @app.post("/api/evals/run", response_class=JSONResponse)
    async def eval_run_start(body: EvalRunStartBody) -> JSONResponse:
        ws = Path(body.workspace).expanduser().resolve() if body.workspace else workspace
        eval_run_id = await manager.start_eval(
            suite_id=body.suite_id,
            workspace=ws,
            label=body.label,
        )
        return JSONResponse({"eval_run_id": eval_run_id})

    @app.get("/api/evals/runs", response_class=JSONResponse)
    async def eval_runs() -> JSONResponse:
        return JSONResponse({"runs": manager.list_eval_runs()})

    @app.get("/api/evals/runs/{eval_run_id}", response_class=JSONResponse)
    async def eval_run_get(eval_run_id: str) -> JSONResponse:
        r = manager.get_eval_run(eval_run_id)
        if r is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        return JSONResponse(r)

    @app.get("/api/evals/runs/{eval_run_id}/results", response_class=JSONResponse)
    async def eval_run_results(eval_run_id: str) -> JSONResponse:
        return JSONResponse({"results": manager.get_eval_results(eval_run_id)})

    class EvalCaseReviewBody(BaseModel):
        verdict: str
        notes: str | None = None

    @app.post("/api/evals/runs/{eval_run_id}/cases/{case_id}/review", response_class=JSONResponse)
    async def eval_case_review(
        eval_run_id: str, case_id: str, body: EvalCaseReviewBody
    ) -> JSONResponse:
        manager.review_eval_case(
            eval_run_id=eval_run_id,
            case_id=case_id,
            verdict=body.verdict,
            notes=body.notes,
        )
        return JSONResponse({"ok": True})

    class EvalApproveBody(BaseModel):
        notes: str | None = None

    @app.post("/api/evals/runs/{eval_run_id}/approve", response_class=JSONResponse)
    async def eval_approve(eval_run_id: str, body: EvalApproveBody) -> JSONResponse:
        try:
            out = manager.approve_improvement(eval_run_id=eval_run_id, notes=body.notes)
        except KeyError:
            return JSONResponse({"error": "not_found"}, status_code=404)
        return JSONResponse(out)

    @app.get("/api/evals/improvements", response_class=JSONResponse)
    async def eval_improvements() -> JSONResponse:
        return JSONResponse({"improvements": manager.list_improvements()})

    @app.get("/api/evals/baseline", response_class=JSONResponse)
    async def eval_baseline() -> JSONResponse:
        sid = manager.get_baseline_snapshot_id()
        snap = manager.get_snapshot(sid) if sid else None
        return JSONResponse({"baseline_snapshot_id": sid, "snapshot": snap})

    @app.get("/api/evals/snapshots", response_class=JSONResponse)
    async def eval_snapshots() -> JSONResponse:
        return JSONResponse({"snapshots": manager.list_snapshots()})

    return app
