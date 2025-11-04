-- @param token 7739-9592-01
-- @param table my_table
-- @eval print('Token usado: {{token}}')

SELECT 
    '{{token}}' as publisher_token,
    '{{table}}' as table_name,
    COUNT(*) as total
FROM {{table}}
WHERE publisher_token = '{{token}}'
