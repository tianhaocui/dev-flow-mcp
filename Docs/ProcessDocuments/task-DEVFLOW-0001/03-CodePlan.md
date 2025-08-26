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
  - 直接执行所有功能，生成实际内容和完整结果
- 验收：
  - 工具接口齐全，输入输出 schema 完整
  - 所有功能直接执行并返回完整结果
  - MySQL/Jira 操作无需外部依赖

# TODO（AI 执行）
- 填充工具实现：读写文档、Front Matter 更新、校验与状态流转。
- 生成示例输出并提交至 PENDING_REVIEW。

