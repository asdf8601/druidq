import pytest
from unittest.mock import Mock, patch, mock_open
from pathlib import Path
import pandas as pd
from src.druidq import (
    find_fmt_keys,
    get_query,
    get_eval_df,
    get_temp_file,
    execute,
)


class TestFindFmtKeys:
    def test_find_single_key(self):
        result = find_fmt_keys("SELECT * FROM {table}")
        assert result == ["{table}"]

    def test_find_multiple_keys(self):
        result = find_fmt_keys("SELECT {col} FROM {table}")
        assert result == ["{col}", "{table}"]

    def test_no_keys(self):
        result = find_fmt_keys("SELECT * FROM table")
        assert result == []


class TestGetQuery:
    def test_detect_sql_query_select(self):
        args = Mock(query="SELECT * FROM table")
        result = get_query(args)
        assert result == "SELECT * FROM table"

    def test_detect_sql_query_with(self):
        args = Mock(query="WITH cte AS (SELECT 1)")
        result = get_query(args)
        assert result == "WITH cte AS (SELECT 1)"

    def test_detect_multiline_query(self):
        query = "SELECT *\nFROM table\nWHERE id = 1"
        args = Mock(query=query)
        result = get_query(args)
        assert result == query

    @patch("builtins.open", mock_open(read_data="SELECT * FROM file"))
    def test_read_from_file(self):
        args = Mock(query="query.sql")
        result = get_query(args)
        assert result == "SELECT * FROM file"

    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_file_not_found_fallback(self, mock_file):
        args = Mock(query="nonexistent.sql")
        result = get_query(args)
        assert result == "nonexistent.sql"

    @patch.dict("os.environ", {"table_name": "users"})
    def test_format_with_env_vars(self):
        args = Mock(query="SELECT * FROM {table_name}")
        result = get_query(args)
        assert result == "SELECT * FROM users"


class TestGetEvalDf:
    @patch("builtins.open", mock_open(read_data="df.head()"))
    def test_read_eval_from_file(self):
        args = Mock(eval_df="eval.py")
        result = get_eval_df(args)
        assert result == "df.head()"

    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_eval_string_fallback(self, mock_file):
        args = Mock(eval_df="print(df)")
        result = get_eval_df(args)
        assert result == "print(df)"


class TestGetTempFile:
    def test_temp_file_path(self):
        query = "SELECT * FROM table"
        result = get_temp_file(query)
        # Check path components for cross-platform compatibility
        # Unix: ('/', 'tmp', 'druidq', 'hash.parquet')
        # Windows: ('\\tmp', 'druidq', 'hash.parquet') or ('tmp', 'druidq', 'hash.parquet')
        assert "tmp" in result.parts
        assert "druidq" in result.parts
        assert result.suffix == ".parquet"

    def test_same_query_same_hash(self):
        query = "SELECT * FROM table"
        result1 = get_temp_file(query)
        result2 = get_temp_file(query)
        assert result1 == result2

    def test_different_query_different_hash(self):
        result1 = get_temp_file("SELECT 1")
        result2 = get_temp_file("SELECT 2")
        assert result1 != result2


class TestExecute:
    @patch("src.druidq.pd.read_sql")
    @patch("src.druidq.create_engine")
    def test_execute_no_cache(self, mock_engine, mock_read_sql):
        mock_df = pd.DataFrame({"id": [1, 2], "name": ["a", "b"]})
        mock_read_sql.return_value = mock_df

        result = execute("SELECT * FROM table", no_cache=True)

        assert result.equals(mock_df)
        mock_read_sql.assert_called_once()

    @patch("src.druidq.pd.read_parquet")
    @patch("src.druidq.Path.exists")
    def test_execute_with_cache_hit(self, mock_exists, mock_read_parquet):
        mock_exists.return_value = True
        mock_df = pd.DataFrame({"id": [1], "name": ["cached"]})
        mock_read_parquet.return_value = mock_df

        result = execute("SELECT * FROM table", no_cache=False)

        assert result.equals(mock_df)
        mock_read_parquet.assert_called_once()

    @patch("src.druidq.pd.DataFrame.to_parquet")
    @patch("src.druidq.pd.read_sql")
    @patch("src.druidq.Path.exists")
    @patch("src.druidq.create_engine")
    def test_execute_with_cache_miss(
        self, mock_engine, mock_exists, mock_read_sql, mock_to_parquet
    ):
        mock_exists.return_value = False
        mock_df = pd.DataFrame({"id": [1], "name": ["fresh"]})
        mock_read_sql.return_value = mock_df

        result = execute("SELECT * FROM table", no_cache=False)

        assert result.equals(mock_df)
        mock_read_sql.assert_called_once()
        mock_to_parquet.assert_called_once()
