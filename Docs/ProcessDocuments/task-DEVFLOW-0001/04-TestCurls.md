---
status: DRAFT
updatedAt: 2025-08-14T00:00:00Z
---

# 运行前
- 环境变量：`API_BASE`, `API_TOKEN`

# 示例
```bash
curl -sS -H "Authorization: Bearer $API_TOKEN" "$API_BASE/api/health"
```

# 断言建议
- HTTP 200
- JSON 中包含 `status: ok`

