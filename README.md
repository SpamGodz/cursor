# cursor

Minimal Python scaffold for an "AI project" with a clean `src/` layout, tests, lint/format, and CI.

## Quickstart

Create a virtual environment, then install:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

Run the CLI:

```bash
python -m cursor_ai --help
python -m cursor_ai hello
```

## Development

Format + lint:

```bash
python -m ruff format .
python -m ruff check .
```

Run tests:

```bash
python -m pytest -q
```
