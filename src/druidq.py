# ignore warnings from sqlalchemy and pandas

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


def get_query(args):
    query_in = args.query

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
    return out


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


def get_eval_df(args):
    eval_df_in = args.eval_df
    try:
        with open(eval_df_in, "r") as f:
            out = f.read()
    except FileNotFoundError:
        out = eval_df_in
    return out


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

    query = get_query(args)

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

    if args.eval_df:
        eval_df = get_eval_df(args)
        if show_eval_input:
            print(f"\nIn[eval]:\n{eval_df}")

        exec(eval_df, globals(), locals())


if __name__ == "__main__":
    app()
