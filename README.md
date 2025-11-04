# DruidQ

Simple Druid CLI to query Apache Druid using SQLAlchemy with caching support and Python evaluation capabilities.

## Features

- Query Druid using SQL strings or files
- Smart caching system (queries cached in `/tmp/druidq/`)
- Python evaluation context with direct DataFrame access
- Parameter templating with `-- @param key value` annotations
- Environment variable templating in queries
- Inline and file-based Python evaluation
- Verbose and quiet modes for different use cases
- Export results to JSON, CSV, or Parquet formats
- Dry-run mode to preview queries before execution
- Query execution timing
- Desktop notifications when queries complete

## Table of Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [SQL Annotations](#sql-annotations)
  - [@param - Query Parameters](#param---query-parameters)
  - [@eval - Inline Python Evaluation](#eval---inline-python-evaluation)
  - [@eval-file - External Python Script](#eval-file---external-python-script)
  - [Combining Annotations](#combining-annotations)
  - [Priority Rules](#priority-rules)
- [Environment Variables](#environment-variables)
- [Examples](#examples)
- [Programmatic Usage](#programmatic-usage)
- [Caching](#caching)
- [Command Line Reference](#command-line-reference)
- [Development](#development)

## Requirements

- Python 3.8+
- Apache Druid instance accessible via network

## Installation

### Using uv (Recommended)

```bash
uv tool install git+https://github.com/mmngreco/druidq
```

### With plotting support (includes plotly-express)

```bash
uv tool install --with plotly-express git+https://github.com/mmngreco/druidq
```

### Alternative: Install from source

```bash
git clone https://github.com/mmngreco/druidq
cd druidq
uv pip install -e .
```

### Optional: Desktop notifications

To enable desktop notifications with the `--noti` flag, install [noti](https://github.com/variadico/noti):

```bash
# macOS
brew install noti

# Linux (download from releases)
# https://github.com/variadico/noti/releases
```

> [!Note]
> If you are on MacOS and encounter issues, consider creating a new virtual environment.

## Usage

```bash
# Query string (shows only output by default)
druidq "select 1"

# Query from file (requires -f flag)
druidq -f ./query.sql
druidq -f query.sql

# Verbose mode (show input and output)
druidq "select 1" -v

# Quiet mode (no output except explicit prints in eval)
druidq "select 1" -q

# Eval Python code inline (df variable available)
druidq "select 1" --eval "print(df)"
druidq "select 1" -q --eval "print(df.head())"

# Eval Python code from file
druidq "select 1" --eval-file script.py

# No cache (force fresh query)
druidq "select 1" --no-cache

# Custom Druid URL
DRUIDQ_URL='druid://localhost:8887/' druidq -f ./query.sql
DRUIDQ_URL='druid://localhost:8082/druid/v2/sql/' druidq -f ./query.sql

# Dry-run to see rendered query without executing
druidq -f ./query.sql --dry-run

# Show execution time
druidq -f ./query.sql --timing

# Export to different formats
druidq -f ./query.sql --output json
druidq -f ./query.sql --output csv
druidq -f ./query.sql --output parquet

# Send desktop notification when query completes (requires noti)
druidq -f ./query.sql --noti
druidq -f ./query.sql --timing --noti  # Includes timing in notification
```

## SQL Annotations

DruidQ supports special SQL comments (annotations) that allow you to embed configuration directly in your SQL files. All annotations must be placed at the beginning of the file as SQL comments starting with `-- @`.

### Available Annotations

#### `@param` - Query Parameters

Define parameters that can be used throughout your SQL query and eval code using `{{variable}}` syntax:

```sql
-- @param token ABC123
-- @param days 7
-- @param table_name events

SELECT * FROM {{table_name}}
WHERE publisher_token = '{{token}}'
  AND __time >= CURRENT_TIMESTAMP - INTERVAL '{{days}}' DAY
```

**Features:**
- Multiple parameters supported (one per line)
- Format: `-- @param key value` (value is everything after the key)
- Parameters override environment variables with the same name
- Available in: SQL queries, `@eval` code, and `@eval-file` scripts
- Use `{{variable}}` syntax (double braces) to reference parameters

#### `@eval` - Inline Python Evaluation

Execute Python code after the query runs. The DataFrame is available as `df`:

```sql
-- @eval print(f'Total rows: {len(df)}'); print(df.describe())

SELECT * FROM datasource
WHERE __time >= CURRENT_TIMESTAMP - INTERVAL '7' DAY
```

**Features:**
- Direct access to query results via `df` variable (pandas DataFrame)
- Can use parameters with `{{variable}}` syntax
- Supports multiple statements separated by semicolons
- CLI `--eval` flag takes priority over `@eval` annotation

#### `@eval-file` - External Python Script

Reference an external Python file for more complex data processing:

```sql
-- @eval-file analysis.py

SELECT * FROM datasource
WHERE __time >= CURRENT_TIMESTAMP - INTERVAL '7' DAY
```

```python
# analysis.py
import matplotlib.pyplot as plt

print(f'Processing {len(df)} records')
print(df.describe())

# Parameters are available via {{variable}} syntax
print('Table name: {{table_name}}')

# Create visualization
df['value'].hist(bins=50)
plt.savefig('output.png')
```

**Features:**
- Python file relative to working directory or absolute path
- Full access to `df` variable and all pandas/Python features
- Can use parameters with `{{variable}}` syntax
- CLI `--eval-file` flag takes priority over `@eval-file` annotation

### Combining Annotations

All annotations can be combined in a single SQL file:

```sql
-- @param publisher_id ABC123
-- @param days 30
-- @param min_revenue 1000
-- @eval print(f'Analyzing publisher: {{publisher_id}}'); print(f'Total revenue: ${df["total_revenue"].sum():,.2f}')

SELECT 
    publisher_token,
    COUNT(*) as impressions,
    SUM(revenue) as total_revenue
FROM ad_events
WHERE publisher_token = '{{publisher_id}}'
  AND __time >= CURRENT_TIMESTAMP - INTERVAL '{{days}}' DAY
GROUP BY publisher_token
HAVING SUM(revenue) > {{min_revenue}}
```

Run with:
```bash
druidq -f query.sql              # Uses all annotations
druidq -f query.sql -v           # Verbose output
druidq -f query.sql --dry-run    # Preview rendered query
```

### Priority Rules

When the same configuration is specified in multiple places, DruidQ follows this priority order:

**For evaluation code:**
1. `--eval` CLI flag (highest priority)
2. `--eval-file` CLI flag
3. `-- @eval` annotation in SQL file
4. `-- @eval-file` annotation in SQL file (lowest priority)

**For parameters:**
1. `-- @param` annotations in SQL file (highest priority)
2. Environment variables (lowest priority)

### Benefits of Annotations

- **Self-contained files:** Query and processing logic stored together
- **Portable:** Share SQL files with embedded configuration
- **Version control friendly:** Track parameters and eval code with queries
- **No external files needed:** Everything in one place
- **Flexible:** CLI flags can still override annotations when needed

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
druidq -f ./query.sql

# With Python evaluation
druidq -f ./query.sql -e "print(df.shape)"
```

### Using Python Scripts

```bash
# Use Python scripts for evaluation
echo "print(df.shape)" > script.py
echo "print(df.T)" >> script.py
druidq -f ./query.sql --eval-file script.py

# Quiet mode with eval
druidq -f ./query.sql -q --eval "print(df.describe())"
```

### Using Environment Variables

You can use environment variables for templating in your queries:

```sql
-- query.sql
SELECT * FROM datasource 
WHERE __time >= '{{START_DATE}}' 
  AND __time < '{{END_DATE}}'
```

```bash
export START_DATE="2025-01-01"
export END_DATE="2025-01-31"
druidq -f ./query.sql
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

## Advanced Examples

> **Note:** These examples use [SQL Annotations](#sql-annotations) (`@param`, `@eval`, `@eval-file`). See the [SQL Annotations section](#sql-annotations) for detailed documentation.

### Complete Example: Parameters + Eval

Create a self-contained SQL file with parameters and processing logic:

```sql
-- query_with_params.sql
-- @param publisher ABC123
-- @param days 7
-- @eval print(f'Total records: {len(df)}'); print(df.describe())

SELECT 
    publisher_token,
    COUNT(*) as impressions,
    SUM(revenue) as total_revenue
FROM ad_events
WHERE publisher_token = '{{publisher}}'
  AND __time >= CURRENT_TIMESTAMP - INTERVAL '{{days}}' DAY
GROUP BY publisher_token
```

```bash
# Run with all features enabled
druidq -f query_with_params.sql -v
```

### Complex Eval Processing

```sql
-- analysis.sql
-- @param threshold 1000
-- @eval-file analyze.py

SELECT * FROM metrics
WHERE value > {{threshold}}
```

```python
# analyze.py
import matplotlib.pyplot as plt

print(f'Processing {len(df)} records above threshold: {{threshold}}')
print(df.describe())

# Create visualization
df['value'].hist(bins=50)
plt.savefig('metrics_distribution.png')
print('Saved plot to metrics_distribution.png')
```

### Debugging and Optimization

```bash
# Preview rendered query before execution
druidq -f query.sql --dry-run

# Measure query performance
druidq -f query.sql --timing

# Export results for further processing
druidq -f query.sql --output json > results.json
druidq -f query.sql --output csv | head -10
```

### Pipeline Integration

```bash
# Export to CSV and pipe to other tools
druidq "SELECT * FROM events LIMIT 100" --output csv | \
  awk -F',' '{print $1}' | \
  sort | uniq -c

# Save query results as parquet for later analysis
druidq -f large_query.sql --output parquet --timing
# Output: Execution time: 2.347s
#         Exported to output.parquet
```

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

## Command Line Reference

```
druidq [-h] [-f] [--eval EVAL] [--eval-file EVAL_FILE] 
       [-n] [-v] [-q] [--dry-run] [-t] [-o FORMAT] [--pdb] query

Arguments:
  query                 SQL query string (use -f to read from file)

Options:
  -h, --help            Show help message
  -f, --file            Read query from file (required for file input)
  --eval EVAL           Evaluate 'df' using inline code (overrides @eval annotation)
  --eval-file FILE      Evaluate 'df' using code from file (overrides @eval-file annotation)
  -n, --no-cache        Do not use cache
  -v, --verbose         Show input and output (query and result)
  -q, --quiet           Suppress all output except explicit prints in eval
  --dry-run             Show rendered query without executing it
  -t, --timing          Show query execution time
  -o, --output FORMAT   Export format: json, csv, or parquet
  --pdb                 Run pdb on start
```

### SQL File Annotations

When using `-f` flag, you can embed configuration in SQL files using comment annotations:

```sql
-- @param key value          Define parameter (available as {{key}})
-- @eval python_code         Execute Python code after query
-- @eval-file script.py      Run Python script after query
```

See [SQL Annotations](#sql-annotations) for complete documentation.
