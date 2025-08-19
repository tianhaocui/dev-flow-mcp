---
status: DRAFT
updatedAt: 2025-08-14T00:00:00Z
---

# 执行提示
- 使用 Jira MCP：`/Volumes/外置/MCP/Jira-MCP-Server`
- 附件：`Docs/ProcessDocuments/task-DEVFLOW-0001/06-Integration.md`

# payload（示意）
```json
{
  "fields": {
    "project": {"key": "PROJ"},
    "issuetype": {"name": "Documentation"},
    "summary": "集成文档：DEVFLOW-0001",
    "description": "请参见附件与 Docs 目录",
    "labels": ["integration", "devflow"]
  },
  "attachments": [
    "Docs/ProcessDocuments/task-DEVFLOW-0001/06-Integration.md"
  ],
  "links": []
}
```

