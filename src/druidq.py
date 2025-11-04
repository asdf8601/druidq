# ignore warnings from sqlalchemy and pandas

from __future__ import annotations

import argparse
import json
import os
import re
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

    # Check if explicit file flag is set
    if hasattr(args, "file") and args.file:
        # Explicit file mode - always read from file
        with open(query_in, "r") as f:
            out = f.read()
            sql_file_path = query_in
    else:
        # Auto-detect mode (backward compatible)
        # Detect if it's a SQL query
        is_query = (
            query_in.strip()
            .upper()
            .startswith(("SELECT", "WITH", "INSERT", "UPDATE", "DELETE"))
            or "\n" in query_in.strip()
        )

        if is_query:
            out = query_in
        else:
            # Try to read as file
            try:
                with open(query_in, "r") as f:
                    out = f.read()
                    sql_file_path = query_in
            except (FileNotFoundError, IOError):
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
            # Remove {{ and }} from key
            k = key[2:-2]
            # Priority: params from comment > environment variables
            if params and k in params:
                fmt_values[k] = params[k]
            else:
                fmt_values[k] = os.environ[k]

        # Simple string replacement instead of format()
        # to avoid issues with { } in SQL
        formatted_out = out
        for key in fmt_keys:
            k = key[2:-2]
            formatted_out = formatted_out.replace(
                f"{{{{{k}}}}}", fmt_values[k]
            )

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

    return out, eval_inline, eval_file, params


def get_args():
    parser = argparse.ArgumentParser(description="Druid Query")
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


def get_temp_file(query):
    qhash = sha1(query.encode()).hexdigest()
    temp_file = Path(f"/tmp/druidq/{qhash}.parquet")
    if not temp_file.parent.exists():
        temp_file.parent.mkdir(parents=True, exist_ok=True)

    return temp_file


def execute(query, engine=None, no_cache=False, quiet=True):
    if engine is None:
        engine = create_engine(DRUIDQ_URL)

    if no_cache:
        return pd.read_sql(query, engine.raw_connection())

    # cache {{
    temp_file = get_temp_file(query)
    if temp_file.exists():
        printer(f"Loading cache: {temp_file}", quiet=quiet)
        return pd.read_parquet(temp_file)
    # }}

    df = pd.read_sql(query, engine.raw_connection())

    # cache {{
    printer(f"Saving cache: {temp_file}", quiet=quiet)
    try:
        df.to_parquet(temp_file)
    except Exception as e:
        printer(f"Error saving cache: {e}", quiet=quiet)
    # }}

    return df


def app():
    args = get_args()

    query, auto_eval_inline, auto_eval_file, params = get_query(args)

    if args.pdb:
        breakpoint()

    # Default: only output
    # -v: input + output
    # -q: nothing (except explicit prints in eval)
    show_query = args.verbose
    show_output = not args.quiet
    show_eval_input = args.verbose
    cache_quiet = not args.verbose

    if show_query:
        print(f"In[query]:\n{query}")

    df = execute(query=query, no_cache=args.no_cache, quiet=cache_quiet)

    if show_output:
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


if __name__ == "__main__":
    app()
