from __future__ import annotations

import argparse
from dataclasses import dataclass


@dataclass(frozen=True)
class Args:
    command: str


def parse_args(argv: list[str] | None = None) -> Args:
    parser = argparse.ArgumentParser(prog="cursor_ai")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("hello", help="Print a greeting.")
    ns = parser.parse_args(argv)
    return Args(command=ns.command)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "hello":
        print("hello")
        return 0
    raise AssertionError(f"Unhandled command: {args.command}")
