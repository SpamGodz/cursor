# cursor

Minimal Python scaffold for an "AI project" with a clean `src/` layout, tests, lint/format, and CI.

## Quickstart

### Configure Cursor / LLM

Set your key (and optionally endpoint + model):

```bash
export CURSOR_API_KEY="...your key..."
# Optional (for OpenAI-compatible endpoints):
export CURSOR_BASE_URL="..."
export CURSOR_MODEL="gpt-4o-mini"
```

Create a virtual environment, then install:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -U pip
python3 -m pip install -e ".[dev]"
```

Run the CLI:

```bash
python3 -m cursor_ai --help
python3 -m cursor_ai hello
python3 -m cursor_ai run "Create a TODO.md with a project plan" --workspace .
python3 -m cursor_ai chat --workspace .
```

## Development

Format + lint:

```bash
python3 -m ruff format .
python3 -m ruff check .
```

Run tests:

```bash
python3 -m pytest -q
```
