---
status: DRAFT
updatedAt: 2025-08-14T00:00:00Z
---

# 执行提示
- 内置 MySQL 功能：直接执行 SQL 并返回结果
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

