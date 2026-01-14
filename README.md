# Data Processing Framework

A lightweight, configurable framework for ingesting, processing, and storing data.

## Project Structure

- `src/`: Source code for the framework.
  - `ingestion/`: Data ingestion modules (e.g., CSV reader).
  - `processing/`: Data processing engine and transformations.
  - `database/`: Database connectors (e.g., SQLite).
  - `egress/`: Data egress modules (e.g., CSV writer).
  - `config.py`: Configuration management.
- `tests/`: Unit tests for the framework.
- `config/`: Configuration files.
- `data/`: Sample data input and output.
- `docs/`: Documentation.
- `examples/`: Example usage scripts.

## Usage

1.  Configure the `config/config.ini` file.
2.  Run the example script:

```bash
python3 examples/main.py
```

## Running Tests

To run the unit tests:

```bash
python3 -m unittest discover tests
```
