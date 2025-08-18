---
status: DRAFT
updatedAt: 2025-08-14T00:00:00Z
---

# 执行提示
- 使用 MySQL MCP 运行：`/Volumes/外置/MCP/mysql_mcp_server`
- 顺序：preconditions → assertions → cleanup

# preconditions
```sql
-- 示例：CREATE TABLE / INSERT ...
```

# assertions
```sql
-- 示例：SELECT * FROM demo WHERE status='OK';
-- 期望：rows >= 1
```

# cleanup
```sql
-- 示例：DROP TABLE demo;
```

