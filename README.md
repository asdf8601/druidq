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

### Auto-detect Eval from SQL Comments

You can specify the evaluation code or script directly in your SQL file using comments. This allows you to store the query and its processing logic together:

#### Inline evaluation code

```sql
-- @eval print(df.head())
SELECT * FROM datasource 
WHERE __time >= CURRENT_TIMESTAMP - INTERVAL '7' DAY
```

#### External evaluation file

```sql
-- @eval-file script.py
SELECT * FROM datasource 
WHERE __time >= CURRENT_TIMESTAMP - INTERVAL '7' DAY
```

```bash
# The eval code/file is automatically detected from the SQL comment
druidq -f ./query.sql

# Explicit flags take priority over comments
druidq -f ./query.sql --eval "print(df.shape)"
druidq -f ./query.sql --eval-file other_script.py
```

**Priority order:**
1. `--eval` flag (inline code)
2. `--eval-file` flag (file)
3. `-- @eval` comment (inline code)
4. `-- @eval-file` comment (file)

**Benefits:**
- No need to remember which eval script goes with which query
- Query files are self-contained and portable
- Explicit flags still work and take priority

### Template Queries with Parameters

You can define parameters directly in your SQL file and use them in both queries and eval code:

```sql
-- @param token 7739-9592-01
-- @param table my_table
-- @eval print('Processing token: {{token}}')

SELECT * FROM {{table}}
WHERE publisher_token = '{{token}}'
  AND __time >= CURRENT_TIMESTAMP - INTERVAL '7' DAY
```

Parameters use `{{variable}}` syntax (double braces) and work in:
- SQL queries
- Inline eval code (`-- @eval`)
- External eval files (`-- @eval-file`)
- CLI eval flags (`--eval` and `--eval-file`)

**Priority:** Parameters defined with `-- @param` take precedence over environment variables.

### Template Queries with Environment Variables

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
       [-n] [-v] [-q] [--pdb] query

Arguments:
  query                 SQL query string (use -f to read from file)

Options:
  -h, --help            Show help message
  -f, --file            Read query from file (required for file input)
  --eval EVAL           Evaluate 'df' using inline code
  --eval-file FILE      Evaluate 'df' using code from file
  -n, --no-cache        Do not use cache
  -v, --verbose         Show input and output (query and result)
  -q, --quiet           Suppress all output except explicit prints in eval
  --dry-run             Show rendered query without executing it
  -t, --timing          Show query execution time
  -o, --output FORMAT   Export format: json, csv, or parquet
  --pdb                 Run pdb on start
```
