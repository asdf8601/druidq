# ignore warnings from sqlalchemy and pandas

from __future__ import annotations

import argparse
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
    pattern = r"{[^}]+}"
    matches = re.findall(pattern, s)
    return matches


def extract_eval_from_query(query: str) -> str | None:
    """Extract eval file from -- eval: comment in SQL query"""
    for line in query.split("\n"):
        line = line.strip()
        # Handle variations: "-- eval:", "--eval:", "-- eval :"
        if line.startswith("--") and "eval:" in line:
            # Extract everything after "eval:"
            eval_part = line.split("eval:", 1)[1].strip()
            if eval_part:
                return eval_part
    return None


def get_query(args):
    query_in = args.query

    # Detect if it's a SQL query
    is_query = (
        query_in.strip()
        .upper()
        .startswith(("SELECT", "WITH", "INSERT", "UPDATE", "DELETE"))
        or "\n" in query_in.strip()
    )

    sql_file_path = None
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

    # format {{{
    fmt_keys = find_fmt_keys(out)
    if fmt_keys:
        fmt_values = {}
        for key in fmt_keys:
            k = key[1:-1]
            fmt_values[k] = os.environ[k]
        out = out.format(**fmt_values)
    # }}}

    # Extract eval file from comment
    eval_file = extract_eval_from_query(out)

    # Resolve relative eval paths relative to SQL file location
    if eval_file and sql_file_path and not os.path.isabs(eval_file):
        sql_dir = os.path.dirname(os.path.abspath(sql_file_path))
        eval_file = os.path.join(sql_dir, eval_file)

    return out, eval_file


def get_args():
    parser = argparse.ArgumentParser(description="Druid Query")
    parser.add_argument("query", help="Druid query or filename")
    parser.add_argument(
        "-e",
        "--eval-df",
        help="Evaluate 'df' using string or filename",
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


def get_eval_df_from_file(eval_file: str) -> str:
    """Read eval code from file or return as-is if it's code"""
    try:
        with open(eval_file, "r") as f:
            out = f.read()
    except FileNotFoundError:
        out = eval_file
    return out


def get_eval_df(args):
    eval_df_in = args.eval_df
    return get_eval_df_from_file(eval_df_in)


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

    query, auto_eval_file = get_query(args)

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

    # Priority: explicit --eval-df > auto-detected from SQL
    eval_file_to_use = args.eval_df if args.eval_df else auto_eval_file

    if eval_file_to_use:
        eval_df = (
            get_eval_df(args)
            if args.eval_df
            else get_eval_df_from_file(eval_file_to_use)
        )
        if show_eval_input:
            print(f"\nIn[eval]:\n{eval_df}")

        exec(eval_df, globals(), locals())


if __name__ == "__main__":
    app()
