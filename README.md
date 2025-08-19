# DevFlow MCP Server (Python)

面向 AI 的开发流程管控 MCP 服务。核心目标：引导 AI 严格按流程执行，从任务文档 → 人审 → 代码生成 → curl 测试 → MySQL MCP 验证 → 对接文档 → Jira 提交，统一沉淀于 Docs 目录。

- 主文档：`Docs/.tasks`
- 过程文档：`Docs/ProcessDocuments`
- 集成：
  - Jira MCP 
  - MySQL MCP 位置

本仓库当前仅提供工具骨架与接口契约，尚未实现具体逻辑。

## 快速开始

- Python >= 3.10
- 建议使用虚拟环境

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m devflow_mcp.server
```

## Cursor 内配置（示例）
```json
{
  "devflow-mcp": {
    "command": "/Users/wulingren/Desktop/coding/devflow-mcp/.venv/bin/python",
    "args": ["-m", "devflow_mcp.server"],
    "cwd": "/Users/wulingren/Desktop/coding/devflow-mcp",
    "env": {
      "MYSQL_HOST": "127.0.0.1",
      "MYSQL_PORT": "3306",
      "MYSQL_USER": "root",
      "MYSQL_PASSWORD": "pass",
      "MYSQL_DB": "demo",
      "JIRA_BASE_URL": "https://jira.example.com",
      "JIRA_CONTEXT_PATH": "/jira",      
      "JIRA_API_VERSION": "2",           
      "JIRA_USER": "you@example.com",
      "JIRA_USER_PASSWORD": "yourPassword"
      // 也可使用 JIRA_BEARER_TOKEN 或 JIRA_API_TOKEN（兼容旧配置）
    }
  }
}
```

## 工具列表（骨架）
- task.prepare_docs
- task.request_code_generation
- test.generate_curl_calls
- verify.plan_with_mysql_mcp
- docs.generate_integration
- jira.publish_integration_doc
- review.set_status
- review.validate_checklist

## 目录结构
```
DevFlow MCP
├── Docs/
│   ├── .tasks/
│   └── ProcessDocuments/
├── devflow_mcp/
│   ├── __init__.py
│   ├── server.py
│   └── tools/
│       ├── __init__.py
│       ├── task_tools.py
│       ├── test_tools.py
│       ├── verify_tools.py
│       ├── docs_tools.py
│       ├── jira_tools.py
│       └── review_tools.py
├── requirements.txt
└── README.md
```

## 注意
- 本项目会尊重工作区已有“分支生成 md 文档”的机制，不会重复创建，而是做增强（状态机、校验、骨架补全）。
- 生成的计划会提示使用外部 Jira/MySQL MCP 执行，不直接连接。


### 核心流程工具

- task.prepare_docs（RPC：mcp_task_prepare_docs）: 准备 Docs/.tasks 与 Docs/ProcessDocuments 的任务骨架

- task.request_code_generation（RPC：mcp_task_request_code_generation）: 生成面向 AI 的代码编写计划

- review.set_status（RPC：mcp_review_set_status）: 切换任务文档 Front Matter 状态，记录审核日志（PENDING_REVIEW / APPROVED / CHANGES_REQUESTED / PUBLISHED）

- review.validate_checklist（RPC：mcp_review_validate_checklist）: 执行一致性校验（文档存在性、状态门禁、配置完整性等）

- test.generate_curl_calls（RPC：mcp_test_generate_curl_calls）: 生成可执行的 curl 测试片段与用例集（前置：状态需 ≥ APPROVED）

- verify.plan_with_mysql_mcp（RPC：mcp_verify_plan_with_mysql_mcp）: 生成 MySQL 验证计划（前置/断言/清理）（前置：状态需 ≥ APPROVED）

- docs.generate_integration（RPC：mcp_docs_generate_integration）: 生成对接文档框架（概览/鉴权/接口/Schema/错误码/样例）（前置：状态需 ≥ APPROVED）

- jira.publish_integration_doc（RPC：mcp_jira_publish_integration_doc）: 生成 Jira 提交计划（payload 与附件清单）（前置：状态需 ≥ APPROVED，且文档已生成）

### 辅助/外联工具

- jira.create_issue（RPC：mcp_jira_create_issue）: 在 Jira 中创建工单（REST v3，支持自定义字段）

- jira.attach_files（RPC：mcp_jira_attach_files）: 向指定工单上传附件（支持多文件批量）

- jira.link_issues（RPC：mcp_jira_link_issues）: 关联两个工单（Relates/Blocks/Duplicate 等）

- mysql.execute_statements（RPC：mcp_mysql_execute_statements）: 执行一组 SQL（需配置 MYSQL_HOST/USER/PASSWORD/DB 等环境变量）