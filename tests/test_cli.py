from __future__ import annotations

from cursor_ai.cli import main


def test_hello(capsys) -> None:
    code = main(["hello"])
    assert code == 0
    out = capsys.readouterr().out.strip()
    assert out == "hello"
