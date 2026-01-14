from __future__ import annotations

from pathlib import Path

import pytest

from cursor_ai.tools.fs import ListFilesTool, ReadFileTool, UnsafePathError, WriteFileTool


def test_fs_write_and_read(tmp_path: Path) -> None:
    w = WriteFileTool(workspace=tmp_path)
    r = ReadFileTool(workspace=tmp_path)
    w.run({"path": "a/b.txt", "content": "hi", "mkdirs": True})
    out = r.run({"path": "a/b.txt"})
    assert out["ok"] is True
    assert out["content"] == "hi"


def test_fs_list(tmp_path: Path) -> None:
    (tmp_path / "x").mkdir()
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    t = ListFilesTool(workspace=tmp_path)
    out = t.run({"path": "."})
    assert out["ok"] is True
    names = [i["name"] for i in out["items"]]
    assert "x" in names
    assert "f.txt" in names


def test_fs_rejects_escape(tmp_path: Path) -> None:
    r = ReadFileTool(workspace=tmp_path)
    with pytest.raises(UnsafePathError):
        r.run({"path": "../secrets.txt"})
