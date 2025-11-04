from unittest.mock import Mock, mock_open, patch

import pandas as pd

from src.druidq import (
    execute,
    extract_params_from_query,
    find_fmt_keys,
    get_query,
    get_temp_file,
)


class TestFindFmtKeys:
    def test_find_single_key(self):
        result = find_fmt_keys("SELECT * FROM {{table}}")
        assert result == ["{{table}}"]

    def test_find_multiple_keys(self):
        result = find_fmt_keys("SELECT {{col}} FROM {{table}}")
        assert result == ["{{col}}", "{{table}}"]

    def test_no_keys(self):
        result = find_fmt_keys("SELECT * FROM table")
        assert result == []

    def test_single_braces_not_matched(self):
        result = find_fmt_keys("SELECT * FROM {table}")
        assert result == []


class TestGetQuery:
    def test_detect_sql_query_select(self):
        args = Mock(query="SELECT * FROM table", file=False)
        query, eval_inline, eval_file, params = get_query(args)
        assert query == "SELECT * FROM table"
        assert eval_inline is None
        assert eval_file is None
        assert params is None

    def test_detect_sql_query_with(self):
        args = Mock(query="WITH cte AS (SELECT 1)", file=False)
        query, eval_inline, eval_file, params = get_query(args)
        assert query == "WITH cte AS (SELECT 1)"
        assert eval_inline is None
        assert eval_file is None
        assert params is None

    def test_detect_multiline_query(self):
        query_str = "SELECT *\nFROM table\nWHERE id = 1"
        args = Mock(query=query_str, file=False)
        query, eval_inline, eval_file, params = get_query(args)
        assert query == query_str
        assert eval_inline is None
        assert eval_file is None
        assert params is None

    @patch("builtins.open", mock_open(read_data="SELECT * FROM file"))
    def test_read_from_file(self):
        args = Mock(query="query.sql", file=False)
        query, eval_inline, eval_file, params = get_query(args)
        assert query == "SELECT * FROM file"
        assert eval_inline is None
        assert eval_file is None
        assert params is None

    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_file_not_found_fallback(self, mock_file):
        args = Mock(query="nonexistent.sql", file=False)
        query, eval_inline, eval_file, params = get_query(args)
        assert query == "nonexistent.sql"
        assert eval_inline is None
        assert eval_file is None
        assert params is None

    @patch.dict("os.environ", {"table_name": "users"})
    def test_format_with_env_vars(self):
        args = Mock(query="SELECT * FROM {{table_name}}", file=False)
        query, eval_inline, eval_file, params = get_query(args)
        assert query == "SELECT * FROM users"
        assert eval_inline is None
        assert eval_file is None
        assert params is None

    @patch("builtins.open", mock_open(read_data="SELECT * FROM explicit"))
    def test_explicit_file_flag(self):
        args = Mock(query="query.sql", file=True)
        query, eval_inline, eval_file, params = get_query(args)
        assert query == "SELECT * FROM explicit"
        assert eval_inline is None
        assert eval_file is None
        assert params is None

    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_explicit_file_flag_raises_on_missing_file(self, mock_file):
        args = Mock(query="missing.sql", file=True)
        try:
            get_query(args)
            assert False, "Expected FileNotFoundError"
        except FileNotFoundError:
            pass


class TestExtractParamsFromQuery:
    def test_extract_params_with_spaces(self):
        query = '-- params = {"token": "7739-9592-01"}\nSELECT * FROM table'
        result = extract_params_from_query(query)
        assert result == {"token": "7739-9592-01"}

    def test_extract_params_without_spaces(self):
        query = '--params={"key":"value"}\nSELECT * FROM table'
        result = extract_params_from_query(query)
        assert result == {"key": "value"}

    def test_extract_params_single_line_with_comment(self):
        query = """-- Some comment
-- params = {"a": "1", "b": "2"}
SELECT * FROM table"""
        result = extract_params_from_query(query)
        assert result == {"a": "1", "b": "2"}

    def test_extract_params_multiline(self):
        query = """-- params = {
--   "token": "7739-9592-01",
--   "table": "my_table",
--   "threshold": "1000"
-- }
SELECT * FROM table"""
        result = extract_params_from_query(query)
        assert result == {
            "token": "7739-9592-01",
            "table": "my_table",
            "threshold": "1000",
        }

    def test_extract_params_multiline_compact(self):
        query = """-- params = {
-- "a": "1",
-- "b": "2"
-- }
SELECT * FROM table"""
        result = extract_params_from_query(query)
        assert result == {"a": "1", "b": "2"}

    def test_no_params_returns_none(self):
        query = "SELECT * FROM table"
        result = extract_params_from_query(query)
        assert result is None

    def test_invalid_json_returns_none(self):
        query = "-- params = {invalid json}\nSELECT * FROM table"
        result = extract_params_from_query(query)
        assert result is None


class TestParamsInQuery:
    def test_params_in_query(self):
        query_str = '-- params = {"token": "7739-9592-01"}\nSELECT * FROM table WHERE publisher_token = \'{{token}}\''
        args = Mock(query=query_str, file=False)
        query, eval_inline, eval_file, params = get_query(args)
        assert "7739-9592-01" in query
        assert "{{token}}" not in query
        assert params == {"token": "7739-9592-01"}

    def test_params_priority_over_env(self):
        query_str = '-- params = {"key": "from_params"}\nSELECT * FROM {{key}}'
        args = Mock(query=query_str, file=False)
        with patch.dict("os.environ", {"key": "from_env"}):
            query, eval_inline, eval_file, params = get_query(args)
            assert "from_params" in query
            assert "from_env" not in query

    def test_params_in_eval_inline(self):
        query_str = '-- params = {"token": "abc123"}\n-- eval = print(\'{{token}}\')\nSELECT 1'
        args = Mock(query=query_str, file=False)
        query, eval_inline, eval_file, params = get_query(args)
        assert eval_inline == "print('abc123')"
        assert params == {"token": "abc123"}


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
