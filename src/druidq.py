# ignore warnings from sqlalchemy and pandas

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
import warnings
from hashlib import sha1
from pathlib import Path

import pandas as pd
from sqlalchemy.engine import create_engine

warnings.filterwarnings("ignore")


DRUIDQ_URL = os.environ.get("DRUIDQ_URL", "druid://localhost:8887/")


def printer(*args, quiet=False, **kwargs):
    if not quiet:
        print(*args, **kwargs)


def find_fmt_keys(s: str) -> list[str] | None:
    pattern = r"{{[^}]+}}"
    matches = re.findall(pattern, s)
    return matches


def truncate_query(query: str, max_len: int = 50) -> str:
    """Truncate query to max_len chars, replacing newlines with spaces

    Args:
        query: SQL query string
        max_len: Maximum length of truncated query

    Returns:
        Truncated query with ellipsis if needed
    """
    # Replace newlines and multiple spaces with single space
    cleaned = " ".join(query.split())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[:max_len] + "..."


def extract_params_from_query(query: str) -> dict[str, str] | None:
    """Extract params from -- @param key value comments in SQL query

    Format:
    -- @param token 8592-3462-01
    -- @param start_date 2025-10-30
    -- @param publisher_name The New York Times

    Everything after the key name is treated as the value (supports spaces).

    Returns:
        dict[str, str] | None: Dictionary of parameters or None if not found
    """
    params = {}
    pattern = r"--\s*@param\s+(\S+)\s+(.+)"

    for line in query.split("\n"):
        match = re.match(pattern, line.strip())
        if match:
            key = match.group(1)
            value = match.group(2).strip()
            params[key] = value

    return params if params else None


def extract_eval_from_query(query: str) -> tuple[str | None, str | None]:
    """Extract eval code or file from -- @eval or -- @eval-file comments

    Format:
    -- @eval print(df.head())
    -- @eval-file script.py

    Returns:
        tuple[str | None, str | None]: (inline_code, file_path)
    """
    inline_code = None
    file_path = None

    pattern_eval_file = r"--\s*@eval-file\s+(.+)"
    pattern_eval = r"--\s*@eval\s+(.+)"

    for line in query.split("\n"):
        line = line.strip()

        # Handle -- @eval-file path/to/file.py
        match = re.match(pattern_eval_file, line)
        if match:
            file_path = match.group(1).strip().strip('"').strip("'")

        # Handle -- @eval code here
        else:
            match = re.match(pattern_eval, line)
            if match:
                inline_code = match.group(1).strip()

    return inline_code, file_path


def get_query(args):
    query_in = args.query

    sql_file_path = None
    query_source_filename = None  # Track filename if reading from file

    # Check if explicit file flag is set
    if hasattr(args, "file") and args.file:
        # Explicit file mode - always read from file
        with open(query_in, "r") as f:
            out = f.read()
            sql_file_path = query_in
            # Use just the filename (not full path) for notification
            query_source_filename = os.path.basename(query_in)
    else:
        # Without -f flag, treat as SQL string only
        # Check if user accidentally passed a file path
        if os.path.exists(query_in) or query_in.endswith(".sql"):
            raise ValueError(
                f"'{query_in}' looks like a file path. "
                f"Use -f flag to read from file: druidq -f {query_in}"
            )
        out = query_in

    # Extract params from comment first
    params = extract_params_from_query(out)

    # Extract eval code/file from comment first (before formatting)
    eval_inline, eval_file = extract_eval_from_query(out)

    # Remove special comments before formatting to avoid conflicts with {{}}
    lines = []
    for line in out.split("\n"):
        line_stripped = line.strip()
        # Skip @param, @eval, @eval-file comment lines
        if line_stripped.startswith("--") and (
            "@param" in line_stripped
            or "@eval-file" in line_stripped
            or "@eval" in line_stripped
        ):
            continue
        lines.append(line)
    out = "\n".join(lines)

    # format {{{
    fmt_keys = find_fmt_keys(out)
    if fmt_keys:
        fmt_values = {}
        for key in fmt_keys:
            # Remove {{ and }} from key and strip whitespace
            k = key[2:-2].strip()
            # Priority: params from comment > environment variables
            if params and k in params:
                fmt_values[k] = params[k]
            else:
                fmt_values[k] = os.environ[k]

        # Simple string replacement instead of format()
        # to avoid issues with { } in SQL
        formatted_out = out
        for key in fmt_keys:
            # Preserve original spacing in template for replacement
            k = key[2:-2].strip()
            formatted_out = formatted_out.replace(key, fmt_values[k])

        out = formatted_out
    # }}}

    # Apply params to eval code if present
    if params:
        if eval_inline:
            for key, value in params.items():
                eval_inline = eval_inline.replace(f"{{{{{key}}}}}", value)
        # Note: eval_file content will be formatted later when read

    # Resolve relative eval paths relative to SQL file location
    if eval_file and sql_file_path and not os.path.isabs(eval_file):
        sql_dir = os.path.dirname(os.path.abspath(sql_file_path))
        eval_file = os.path.join(sql_dir, eval_file)

    # Generate query_source for notifications
    # For file queries: use filename; for inline: use truncated query
    if query_source_filename:
        query_source = query_source_filename
    else:
        # For inline queries, truncate cleaned query (after comment removal)
        query_source = truncate_query(out)

    return out, eval_inline, eval_file, params, query_source


def get_args():
    parser = argparse.ArgumentParser(
        description="Druid Query CLI with SQL annotations support",
        epilog="""
SQL Annotations (use in query or file):
  -- @param key value       Define parameter (supports spaces in value)
  -- @eval code             Inline Python code (df variable available)
  -- @eval-file script.py   Execute Python script from file

Examples:
  Query with parameters:
    -- @param token 1111-1111-01
    -- @param table my_table
    SELECT * FROM {{table}} WHERE token = '{{token}}'

  Query with inline evaluation:
    -- @eval print(df.describe())
    SELECT * FROM my_table LIMIT 100

  Query with eval from file:
    -- @eval-file analysis.py
    SELECT * FROM my_table

  Retry with exponential backoff:
    druidq --retry 3 --backoff 1.5 -f query.sql
    (Retries up to 3 times with exponential backoff starting at 1.5s)

Priority:
  CLI flags (--eval, --eval-file) override SQL annotations (@eval, @eval-file)
  Parameters from @param override environment variables
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("query", help="Druid query or filename")
    parser.add_argument(
        "-f",
        "--file",
        help="Read query from file (explicit file mode)",
        action="store_true",
    )
    parser.add_argument(
        "-e",
        "--eval",
        help="Evaluate 'df' using inline code",
        default="",
    )
    parser.add_argument(
        "--eval-file",
        help="Evaluate 'df' using code from file",
        default="",
    )
    parser.add_argument(
        "-n",
        "--no-cache",
        help="Do not use cache",
        action="store_true",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        help="Show input and output (query and result)",
        action="store_true",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        help="Suppress all output except explicit prints in eval",
        action="store_true",
    )
    parser.add_argument(
        "--pdb",
        help="Run pdb on start",
        action="store_true",
    )
    parser.add_argument(
        "--dry-run",
        help="Show rendered query without executing it",
        action="store_true",
    )
    parser.add_argument(
        "-t",
        "--timing",
        help="Show query execution time",
        action="store_true",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Export format: json, csv, or parquet (prints to stdout or file)",
        choices=["json", "csv", "parquet"],
        default=None,
    )
    parser.add_argument(
        "--noti",
        help="Send notification when query completes (requires noti)",
        action="store_true",
    )
    parser.add_argument(
        "-c",
        "--compact",
        help="Only print query output (suppress all metadata)",
        action="store_true",
    )
    parser.add_argument(
        "--retry",
        type=int,
        metavar="N",
        help="Number of retry attempts for transient errors (default: 0)",
        default=0,
    )
    parser.add_argument(
        "--backoff",
        type=float,
        metavar="SECONDS",
        help=(
            "Initial backoff time in seconds for exponential backoff "
            "(default: 1.0)"
        ),
        default=1.0,
    )
    return parser.parse_args()


def get_eval_df_from_file(
    eval_file: str, params: dict[str, str] | None = None
) -> str:
    """Read eval code from file and apply params if provided"""
    with open(eval_file, "r") as f:
        code = f.read()

    # Apply params to eval code if present
    if params:
        for key, value in params.items():
            code = code.replace(f"{{{{{key}}}}}", value)

    return code


DRUIDQ_CACHE_DIR = os.environ.get("DRUIDQ_CACHE_DIR", "/tmp/druidq")


def get_temp_file(query):
    qhash = sha1(query.encode()).hexdigest()
    temp_file = Path(DRUIDQ_CACHE_DIR) / f"{qhash}.parquet"
    if not temp_file.parent.exists():
        temp_file.parent.mkdir(parents=True, exist_ok=True)

    return temp_file


def send_notification(
    title: str,
    message: str,
    show_time: bool = False,
    query_id: str | None = None,
):
    """Send desktop notification using noti CLI tool if available

    Args:
        title: Notification title
        message: Notification message
        show_time: Whether to show elapsed time in notification
        query_id: Optional query identifier (filename or truncated query)
    """
    if not shutil.which("noti"):
        printer(
            "Warning: noti command not found. "
            "Install from https://github.com/variadico/noti",
            quiet=False,
        )
        return

    # Prepend query_id to message if provided
    if query_id:
        message = f"{query_id} - {message}"

    cmd = ["noti", "-t", title, "-m", message]
    if show_time:
        cmd.append("-e")

    try:
        subprocess.run(cmd, check=False, capture_output=True)
    except Exception as e:
        printer(f"Warning: Failed to send notification: {e}", quiet=False)


def is_retryable_error(error: Exception) -> bool:
    """Determine if an error is transient and should be retried

    Args:
        error: Exception object

    Returns:
        True if error is retryable, False otherwise
    """
    error_str = str(error)

    # Check the original exception in the chain
    original_error = error
    while original_error.__cause__ is not None:
        original_error = original_error.__cause__
        error_str = str(original_error) + "\n" + error_str

    # Only retry on "missing segments" errors (server availability issues)
    if "Failed to check missing segments" in error_str:
        return True

    return False


def extract_error_message(error: Exception) -> str:
    """Extract clean error message from database exceptions

    Args:
        error: Exception object

    Returns:
        Clean error message string
    """
    error_str = str(error)

    # Check the original exception in the chain
    original_error = error
    while original_error.__cause__ is not None:
        original_error = original_error.__cause__
        error_str = str(original_error) + "\n" + error_str

    # Extract Druid-specific error messages
    # Pattern 1: Object not found
    match = re.search(r"Object '([^']+)' not found", error_str)
    if match:
        return f"Table or column '{match.group(1)}' not found"

    # Pattern 2: Failed to check missing segments
    if "Failed to check missing segments" in error_str:
        return (
            "Failed to check missing segments. "
            "Some Druid servers are not responding. "
            "Check cluster health."
        )

    # Pattern 3: Unknown exception with message
    match = re.search(r"Unknown exception \([^)]+\): (.+?)(?:\n|$)", error_str)
    if match:
        return match.group(1)

    # Pattern 4: Plan validation failed
    match = re.search(r"Plan validation failed[^:]*: (.+?)(?:\n|$)", error_str)
    if match:
        return f"Plan validation failed: {match.group(1)}"

    # Pattern 5: ProgrammingError with description
    match = re.search(r"ProgrammingError: (.+?)(?:\n|$)", error_str)
    if match:
        return match.group(1)

    # Return first line of error message if no specific pattern found
    first_line = str(error).split("\n")[0]
    return first_line


def execute_with_retry(
    query,
    engine=None,
    no_cache=False,
    quiet=True,
    max_retries=0,
    initial_backoff=1.0,
    show_retry_messages=True,
):
    """Execute query with retry logic and exponential backoff

    Args:
        query: SQL query string
        engine: SQLAlchemy engine (optional)
        no_cache: Skip cache if True
        quiet: Suppress cache messages if True
        max_retries: Number of retry attempts (0 = no retry)
        initial_backoff: Initial backoff time in seconds
        show_retry_messages: Show retry progress messages

    Returns:
        DataFrame with query results

    Raises:
        RuntimeError: After all retries exhausted
    """
    attempt = 0
    backoff = initial_backoff

    while True:
        try:
            return execute(
                query=query,
                engine=engine,
                no_cache=no_cache,
                quiet=quiet,
            )
        except RuntimeError as e:
            # Check if error is retryable
            cause = e.__cause__ if e.__cause__ else e
            if not isinstance(cause, Exception) or not is_retryable_error(
                cause
            ):
                # Not a transient error, raise immediately
                raise

            # Check if we have retries left
            if attempt >= max_retries:
                # No more retries, raise the error
                raise

            # Calculate wait time with exponential backoff
            wait_time = backoff * (2**attempt)

            # Show retry message if not in quiet mode
            if show_retry_messages:
                print(
                    f"Retrying ({attempt + 1}/{max_retries}) "
                    f"in {wait_time:.1f}s...",
                    file=sys.stderr,
                )

            # Wait before retry
            time.sleep(wait_time)

            # Increment attempt counter
            attempt += 1


def execute(query, engine=None, no_cache=False, quiet=True):
    if engine is None:
        engine = create_engine(DRUIDQ_URL)

    if no_cache:
        try:
            return pd.read_sql(query, engine.raw_connection())
        except Exception as e:
            raise RuntimeError(extract_error_message(e)) from e

    # cache {{
    temp_file = get_temp_file(query)
    if temp_file.exists():
        printer(f"Loading cache: {temp_file}", quiet=quiet)
        return pd.read_parquet(temp_file)
    # }}

    try:
        df = pd.read_sql(query, engine.raw_connection())
    except Exception as e:
        raise RuntimeError(extract_error_message(e)) from e

    # cache {{
    printer(f"Saving cache: {temp_file}", quiet=quiet)
    try:
        df.to_parquet(temp_file)
    except Exception as e:
        printer(f"Error saving cache: {e}", quiet=quiet)
    # }}

    return df


def app():
    import time

    args = get_args()

    query, auto_eval_inline, auto_eval_file, params, query_source = get_query(
        args
    )

    if args.pdb:
        breakpoint()

    # Handle --dry-run: show query and exit
    if args.dry_run:
        print(f"Rendered query:\n{query}")
        if params:
            print("\nParameters used:")
            for key, value in params.items():
                print(f"  {key}: {value}")
        return

    # Priority: -q > -c > -v > default
    # -q: suppress everything (except explicit prints in eval)
    # -v: show input + output
    # -c: only output (suppress metadata)
    # default: only output

    if args.quiet:
        # -q wins: suppress everything
        show_query = False
        show_output = False
        show_eval_input = False
        cache_quiet = True
        show_timing = False
    elif args.compact:
        # -c: only show output, suppress metadata
        show_query = False
        show_output = True
        show_eval_input = False
        cache_quiet = True
        show_timing = False
    elif args.verbose:
        # -v: show everything
        show_query = True
        show_output = True
        show_eval_input = True
        cache_quiet = False
        show_timing = args.timing
    else:
        # default: only output
        show_query = False
        show_output = True
        show_eval_input = False
        cache_quiet = True
        show_timing = args.timing

    if show_query:
        print(f"In[query]:\n{query}")

    # Determine if retry messages should be shown
    show_retry_messages = not args.compact and not args.quiet

    # Execute query with optional timing and retry
    start_time = time.time() if (args.timing or args.noti) else 0.0
    try:
        df = execute_with_retry(
            query=query,
            no_cache=args.no_cache,
            quiet=cache_quiet,
            max_retries=args.retry,
            initial_backoff=args.backoff,
            show_retry_messages=show_retry_messages,
        )
    except RuntimeError as e:
        # Clean error message from extract_error_message()
        # No traceback for controlled errors
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        # Unexpected/uncontrolled error - always show full traceback
        print(f"Unexpected error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1

    elapsed = 0.0
    if args.timing or args.noti:
        elapsed = time.time() - start_time
    if show_timing:
        print(f"\nExecution time: {elapsed:.3f}s")

    # Handle --output: export to different formats
    if args.output:
        if args.output == "json":
            print(df.to_json(orient="records", indent=2))
        elif args.output == "csv":
            print(df.to_csv(index=False))
        elif args.output == "parquet":
            # For parquet, need to write to file
            output_file = "output.parquet"
            df.to_parquet(output_file)
            print(f"Exported to {output_file}")
    elif show_output:
        print(df)

    # Priority: CLI flags > auto-detected from SQL
    # --eval > --eval-file > -- eval: "code" > -- eval-file: file.py
    eval_code = None

    if args.eval:
        # Inline code from CLI flag
        eval_code = args.eval
        # Apply params if present
        if params:
            for key, value in params.items():
                eval_code = eval_code.replace(f"{{{{{key}}}}}", value)
    elif args.eval_file:
        # File from CLI flag
        eval_code = get_eval_df_from_file(args.eval_file, params)
    elif auto_eval_inline:
        # Inline code from SQL comment (already has params applied)
        eval_code = auto_eval_inline
    elif auto_eval_file:
        # File from SQL comment
        eval_code = get_eval_df_from_file(auto_eval_file, params)

    if eval_code:
        if show_eval_input:
            print(f"\nIn[eval]:\n{eval_code}")

        exec(eval_code, globals(), locals())

    # Send notification if requested
    if args.noti:
        rows = len(df)
        title = "DruidQ - Query Complete"
        message = f"Query returned {rows} row{'s' if rows != 1 else ''}"
        if args.timing:
            message += f" in {elapsed:.3f}s"
        send_notification(
            title, message, show_time=False, query_id=query_source
        )


if __name__ == "__main__":
    app()
