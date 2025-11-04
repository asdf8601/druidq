# Tests and Demo Files

This directory contains both unit tests and demo files for DruidQ.

## Unit Tests

- **`test_druidq.py`** - Main test suite with 27 unit tests covering core functionality
  - Run with: `make test` or `pytest tests/test_druidq.py`

## Demo Files

These files demonstrate DruidQ features and can be used for manual testing without requiring a Druid connection.

### Python Demos

- **`demo_params.py`** - Interactive demo showing SQL annotations (`@param`, `@eval`, `@eval-file`)
  - Run with: `python tests/demo_params.py`
  - Demonstrates:
    - Using `@param` annotations to define parameters
    - Inline evaluation with `@eval`
    - External evaluation with `@eval-file`
    - Parameter priority over environment variables

### SQL Demo Files

- **`demo_params.sql`** - Example SQL file with `@param` and `@eval` annotations
  - Shows inline evaluation with parameter substitution
  - Use with: `druidq -f tests/demo_params.sql --dry-run`

- **`demo_params_file.sql`** - Example SQL file with `@param` and `@eval-file` annotations
  - References external Python script for evaluation
  - Use with: `druidq -f tests/demo_params_file.sql --dry-run`

- **`demo_eval.py`** - External evaluation script used by `demo_params_file.sql`
  - Demonstrates accessing `df` DataFrame and parameters
  - Shows template variable syntax `{{variable}}`

## Usage Examples

```bash
# Run unit tests
make test

# Run interactive demo (no Druid needed)
python tests/demo_params.py

# Preview SQL file with annotations (dry-run, no Druid execution)
druidq -f tests/demo_params.sql --dry-run

# See rendered query with verbose output
druidq -f tests/demo_params.sql --dry-run -v
```

## Notes

- Demo SQL files use the `--dry-run` flag to preview queries without executing
- The `demo_params.py` script mocks the execution to demonstrate parameter extraction
- All demo files use the new annotation syntax (`@param`, `@eval`, `@eval-file`)
