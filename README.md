# DruidQ

Simple Druid CLI to query Apache Druid using SQLAlchemy with caching support and Python evaluation capabilities.

## Features

- Query Druid using SQL strings or files
- Smart caching system (queries cached in `/tmp/druidq/`)
- Python evaluation context with direct DataFrame access
- Environment variable templating in queries
- Verbose and quiet modes for different use cases

## Requirements

- Python 3.8+
- Apache Druid instance accessible via network

## Installation

### Using uv (Recommended)

```bash
uv tool install git+https://github.com/mmngreco/druidq
```

### Alternative: Install from source

```bash
git clone https://github.com/mmngreco/druidq
cd druidq
uv pip install -e .
```

> [!Note]
> If you are on MacOS and encounter issues, consider creating a new virtual environment.

## Usage

```bash
# Query string (shows only output by default)
druidq "select 1"

# Query from file (auto-detected)
druidq ./query.sql
druidq query.sql

# Verbose mode (show input and output)
druidq "select 1" -v

# Quiet mode (no output except explicit prints in eval)
druidq "select 1" -q

# Eval Python code (df variable available)
druidq "select 1" -e "print(df)"
druidq "select 1" -q -e "print(df.head())"

# No cache (force fresh query)
druidq "select 1" --no-cache

# Custom Druid URL
DRUIDQ_URL='druid://localhost:8887/' druidq ./query.sql
DRUIDQ_URL='druid://localhost:8082/druid/v2/sql/' druidq ./query.sql
```

## Environment Variables

- `DRUIDQ_URL`: Druid connection URL (default: `druid://localhost:8887/`)

## Examples

### Basic Usage

```bash
mkdir /tmp/druidq/
cd /tmp/druidq/
echo "select 1" > query.sql
export DRUIDQ_URL='druid://localhost:8887/'

# Read query from file
druidq ./query.sql

# With Python evaluation
druidq ./query.sql -e "print(df.shape)"
```

### Using Python Scripts

```bash
# Use Python scripts for evaluation
echo "print(df.shape)" > script.py
echo "print(df.T)" >> script.py
druidq ./query.sql -e ./script.py

# Quiet mode with eval
druidq ./query.sql -q -e "print(df.describe())"
```

### Template Queries with Environment Variables

```sql
-- query.sql
SELECT * FROM datasource 
WHERE __time >= '{START_DATE}' 
  AND __time < '{END_DATE}'
```

```bash
export START_DATE="2025-01-01"
export END_DATE="2025-01-31"
druidq ./query.sql
```

## Programmatic Usage

```python
from druidq import execute

# Simple query
df = execute("select 1")

# With custom engine
from sqlalchemy import create_engine
engine = create_engine("druid://localhost:8887/")
df = execute("select 1", engine=engine)

# Disable cache
df = execute("select 1", no_cache=True)
```

## Caching

Queries are automatically cached in `/tmp/druidq/` using SHA1 hash of the query string as filename. Use `--no-cache` flag to bypass cache and force a fresh query.

## Development

### Setup

```bash
git clone https://github.com/mmngreco/druidq
cd druidq
uv sync --dev
```

### Commands

```bash
# Install in dev mode
make dev

# Run tests
make test

# Lint and type check
make lint

# Format code
make format

# Sync dependencies
make sync

# Clean environment
make clean
```

## Author

Max Greco (mmngreco@gmail.com)
