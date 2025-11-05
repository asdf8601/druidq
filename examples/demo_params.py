#!/usr/bin/env python
"""Demo script to show params functionality with new @param syntax"""

from unittest.mock import Mock
from druidq import get_query

# Test 1: Params in query with inline eval
print("=" * 60)
print("Test 1: Params in query with inline eval")
print("=" * 60)
query_str = """-- @param token 7739-9592-01
-- @param table my_table
-- @eval print('Token usado: {{token}}')

SELECT 
    '{{token}}' as publisher_token,
    '{{table}}' as table_name
WHERE publisher_token = '{{token}}'
"""

args = Mock(query=query_str, file=False)
query, eval_inline, eval_file, params = get_query(args)

print("\nOriginal query (with @param annotations):")
print(query_str)

print("\nExtracted params:")
print(params)

print("\nProcessed query (params replaced):")
print(query)

print("\nExtracted eval code (params replaced):")
print(eval_inline)

# Test 2: Params from file
print("\n" + "=" * 60)
print("Test 2: Params from file with eval-file")
print("=" * 60)

with open("tests/demo_params_file.sql", "r") as f:
    file_content = f.read()

print("\nFile content:")
print(file_content)

args2 = Mock(query="tests/demo_params_file.sql", file=True)
query2, eval_inline2, eval_file2, params2 = get_query(args2)

print("\nExtracted params:")
print(params2)

print("\nProcessed query:")
print(query2)

print("\nEval file:")
print(eval_file2)

# Test 3: Params override environment variables
print("\n" + "=" * 60)
print("Test 3: Params priority over environment variables")
print("=" * 60)

import os

os.environ["token"] = "from_environment"

query_str3 = """-- @param token from_params
SELECT * FROM table WHERE token = '{{token}}'
"""

args3 = Mock(query=query_str3, file=False)
query3, _, _, params3 = get_query(args3)

print("\nEnvironment variable token =", os.environ.get("token"))
print("Params token =", params3.get("token"))
print("\nProcessed query (should use 'from_params'):")
print(query3)

print("\n" + "=" * 60)
print("All tests completed successfully!")
print("=" * 60)
