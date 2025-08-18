# DevFlow MCP Server (Python)

面向 AI 的开发流程管控 MCP 服务。核心目标：引导 AI 严格按流程执行，从任务文档 → 人审 → 代码生成 → curl 测试 → MySQL MCP 验证 → 对接文档 → Jira 提交，统一沉淀于 Docs 目录。

- 主文档：`Docs/.tasks`
- 过程文档：`Docs/ProcessDocuments`
- 集成：
  - Jira MCP 位置：`/Volumes/外置/MCP/Jira-MCP-Server`
  - MySQL MCP 位置：`/Volumes/外置/MCP/mysql_mcp_server`

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
