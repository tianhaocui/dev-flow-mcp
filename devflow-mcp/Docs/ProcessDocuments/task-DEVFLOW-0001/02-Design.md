---
status: DRAFT
updatedAt: 2025-08-14T00:00:00Z
---

# 总体设计
- 文档目录结构与 Front Matter 统一；状态受控。
- 工具通过 MCP 对外暴露，返回待执行计划与文档路径。
- 与 Jira/MySQL MCP 以“执行提示 + 计划载荷”对接。

# 状态机门禁
- 仅 APPROVED 后可生成 curl / MySQL 计划 / 对接文档 / Jira 计划。

# 外部 MCP 路径
- Jira MCP：`/Volumes/外置/MCP/Jira-MCP-Server`
- MySQL MCP：`/Volumes/外置/MCP/mysql_mcp_server`

