# DruidQ

Simple druid cli to query druid using sqlalchemy.


## Installation


```bash
pipx install git+https://github.com/mmngreco/druidq
```

> [!Note]
> I you are on MacOS I recommend creating a new venv and avoid using `pipx`


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


### Examples

```bash
mkdir /tmp/druidq/
cd /tmp/druidq/
echo "select 1" > query.sql
export DRUIDQ_URL='druid://localhost:8887/'

# Read query from file
druidq ./query.sql

# With Python evaluation
druidq ./query.sql -e "print(df.shape)"

# Use Python scripts
echo "print(df.shape)" > script.py
echo "print(df.T)" >> script.py
druidq ./query.sql -e ./script.py

# Quiet mode with eval
druidq ./query.sql -q -e "print(df.describe())"
```

### Programmatic Usage

```python
from druidq import execute

df = execute("select 1")
```
