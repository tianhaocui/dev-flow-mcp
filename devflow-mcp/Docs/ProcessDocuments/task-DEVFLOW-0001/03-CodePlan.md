---
status: DRAFT
updatedAt: 2025-08-14T00:00:00Z
---

# 代码生成指南（面向 AI）
- 语言：Python
- 模块：`devflow_mcp`
- 约束：
  - 严格路径：`Docs/.tasks` 与 `Docs/ProcessDocuments`
  - 保留 Front Matter 与用户修改
  - 只生成“计划”和“文档”，外部执行交给对应 MCP
- 验收：
  - 工具接口齐全，输入输出 schema 完整
  - 计划能指导外部 MCP 执行

# TODO（AI 执行）
- 填充工具实现：读写文档、Front Matter 更新、校验与状态流转。
- 生成示例输出并提交至 PENDING_REVIEW。

