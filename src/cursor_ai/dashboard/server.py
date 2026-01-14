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

    @app.post("/api/runs/start", response_class=JSONResponse)
    async def run_start(body: StartBody) -> JSONResponse:
        ws = Path(body.workspace).expanduser().resolve() if body.workspace else workspace
        run_id = await manager.start_run(
            goal=body.goal,
            workspace=ws,
            api_key=body.api_key,
            base_url=body.base_url,
            model=body.model,
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

    return app
