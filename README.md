# DevFlow MCP Server (Python)

面向 AI 的开发流程管控 MCP 服务。核心目标：引导 AI 严格按流程执行，从任务文档 → 人审 → 代码生成 → curl 测试 → MySQL 验证 → 对接文档 → Jira 提交，统一沉淀于 Docs 目录。

- 主文档：`Docs/.tasks`
- 过程文档：`Docs/ProcessDocuments`
- 内置功能：
  - 完整的 MySQL 数据库操作
  - 完整的 Jira 工单管理
  - 文档生成与状态管理
  - curl 测试用例生成

本仓库提供完整的开发流程管控功能，内置所有必要的工具实现。

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
- 本项目会尊重工作区已有"分支生成 md 文档"的机制，不会重复创建，而是做增强（状态机、校验、骨架补全）。
- 所有功能均为内置实现，直接执行并返回结果，无需外部依赖。


### 核心流程工具

- task.prepare_docs（RPC：mcp_task_prepare_docs）: 直接创建 Docs/.tasks 与 Docs/ProcessDocuments 的任务文档骨架

- task.request_code_generation（RPC：mcp_task_request_code_generation）: 生成详细的 AI 代码编写计划文档

- review.set_status（RPC：mcp_review_set_status）: 切换任务文档 Front Matter 状态，记录审核日志（PENDING_REVIEW / APPROVED / CHANGES_REQUESTED / PUBLISHED）

- review.validate_checklist（RPC：mcp_review_validate_checklist）: 执行完整的一致性校验（文档存在性、状态门禁、配置完整性等）

- test.generate_curl_calls（RPC：mcp_test_generate_curl_calls）: 生成并保存可执行的 curl 测试文档与用例集（前置：状态需 ≥ APPROVED）

- verify.plan_with_mysql_mcp（RPC：mcp_verify_plan_with_mysql_mcp）: 直接执行 MySQL 验证（前置/断言/清理）并返回结果（前置：状态需 ≥ APPROVED）

- docs.generate_integration（RPC：mcp_docs_generate_integration）: 生成完整的对接文档内容（概览/鉴权/接口/Schema/错误码/样例）（前置：状态需 ≥ APPROVED）

- jira.publish_integration_doc（RPC：mcp_jira_publish_integration_doc）: 直接创建 Jira 工单并上传附件（前置：状态需 ≥ APPROVED，且文档已生成）

### 内置功能工具

- jira.create_issue（RPC：mcp_jira_create_issue）: 内置 Jira 工单创建（REST API，支持自定义字段）

- jira.attach_files（RPC：mcp_jira_attach_files）: 内置文件上传到 Jira 工单（支持多文件批量）

- jira.link_issues（RPC：mcp_jira_link_issues）: 内置 Jira 工单关联（Relates/Blocks/Duplicate 等）

- mysql.execute_statements（RPC：mcp_mysql_execute_statements）: 内置 MySQL 执行器（需配置 MYSQL_HOST/USER/PASSWORD/DB 等环境变量）

### Jira集成与测试分析工具

- jira.fetch_issue_with_analysis（RPC：mcp_jira_fetch_issue_with_analysis）: 拉取Jira工单及子任务信息，批量下载附件，为分析准备数据

- analyze.requirements_vs_tests（RPC：mcp_analyze_requirements_vs_tests）: 智能分析Jira需求与测试用例覆盖度，生成gap分析和推荐

- sync.jira_requirements（RPC：mcp_sync_jira_requirements）: 双向同步Jira需求到DevFlow任务，可选自动生成测试用例

### 状态管理工具

- status.query（RPC：mcp_status_query）: 查询任务状态信息，包括当前状态、允许的转换、历史记录和统计

- status.batch_operation（RPC：mcp_status_batch_operation）: 批量状态转换操作，支持事务性处理和错误恢复

- status.report（RPC：mcp_status_report）: 生成完整的状态报告，包括统计分析、活动摘要和阻塞任务识别

### 状态管理特性

**🔒 状态控制**
- 严格的状态转换路径验证，防止非法跳转
- 关键转换必须提供原因说明（拒绝、发布等）
- 事务性状态更新，确保数据一致性

**📊 状态流程**
```
DRAFT → PENDING_REVIEW → APPROVED → PUBLISHED
          ↓                 ↓
    CHANGES_REQUESTED ←──────┘
          ↓
        DRAFT (可选回退)
```

**📈 审计追踪**
- 完整的状态变更历史记录
- 操作者和变更原因记录
- 状态统计和分析报告
- 阻塞任务识别和预警

### Jira集成分析特性

**🔄 数据获取**
- 完整的工单信息抓取（包括自定义字段）
- 递归获取所有子任务详情
- 批量下载和管理附件
- 可选的变更历史追踪

**🧠 智能分析**
- 自动解析需求条目和验收标准
- 基于关键词的测试用例匹配
- 覆盖度计算和Gap识别  
- 按需求类别智能推荐测试用例

**📊 分析维度**
```
需求来源: 工单描述 + 子任务 + 附件内容
测试匹配: 关键词重叠度算法
覆盖度: 需求点 ↔ 测试用例映射关系
推荐策略: 功能性|性能|安全|界面 差异化推荐
```

**🔗 双向同步**
- Jira → DevFlow任务自动创建
- 需求变更实时同步更新
- 可选的测试用例自动生成
- 完整的同步记录和追溯