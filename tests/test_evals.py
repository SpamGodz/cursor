from __future__ import annotations

from pathlib import Path

from cursor_ai.dashboard import db
from cursor_ai.dashboard.run_manager import RunManager


def test_eval_default_suite_created(tmp_path: Path) -> None:
    mgr = RunManager(db_path=tmp_path / "dash.sqlite")
    suites = mgr.list_eval_suites()
    assert len(suites) >= 1


def test_approve_improvement_sets_baseline(tmp_path: Path) -> None:
    mgr = RunManager(db_path=tmp_path / "dash.sqlite")
    snapshot_id = "s1"
    eval_run_id = "e1"
    now = db.utcnow()
    db.insert_snapshot(mgr._conn, snapshot_id=snapshot_id, label="x", created_at=now, data={"a": 1})
    db.insert_eval_run(
        mgr._conn,
        eval_run_id=eval_run_id,
        suite_id="suite",
        snapshot_id=snapshot_id,
        status="completed",
        created_at=now,
        cases_total=0,
    )
    out = mgr.approve_improvement(eval_run_id=eval_run_id, notes="better")
    assert out["baseline_snapshot_id"] == snapshot_id
    assert mgr.get_baseline_snapshot_id() == snapshot_id
    imps = mgr.list_improvements()
    assert len(imps) == 1
