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
      "JIRA_USER_PASSWORD": "yourPassword",
      // 也可使用 JIRA_BEARER_TOKEN 或 JIRA_API_TOKEN（兼容旧配置）
      
      // Wiki (Confluence) 配置
      "WIKI_BASE_URL": "https://wiki.logisticsteam.com",
      "WIKI_CONTEXT_PATH": "",           
      "WIKI_API_VERSION": "1.0",        // 基于您的API结构使用1.0版本
      "WIKI_USER": "you@example.com",
      "WIKI_USER_PASSWORD": "yourWikiPassword"
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
  - 🔄 **自动检测**: 支持从当前Git分支自动检测项目Key和相关ticket信息

### 内置功能工具

- jira.create_issue（RPC：mcp_jira_create_issue）: 内置 Jira 工单创建（REST API，支持自定义字段，支持Git分支自动检测）

- jira.attach_files（RPC：mcp_jira_attach_files）: 内置文件上传到 Jira 工单（支持多文件批量）

- jira.link_issues（RPC：mcp_jira_link_issues）: 内置 Jira 工单关联（Relates/Blocks/Duplicate 等）

- jira.add_comment（RPC：mcp_jira_add_comment）: 向 Jira 工单添加评论，支持富文本、用户提及和可见性控制

- jira.update_status（RPC：mcp_jira_update_status）: 更新 Jira 工单状态，支持状态转换验证和评论添加

- jira.batch_update_status（RPC：mcp_jira_batch_update_status）: 批量更新多个 Jira 工单状态

- jira.mark_progress（RPC：mcp_jira_mark_progress）: 智能标记任务进展到 Jira，自动生成包含任务状态、Git改动、文档状态和下一步计划的结构化评论

- mysql.execute_statements（RPC：mcp_mysql_execute_statements）: 内置 MySQL 执行器（需配置 MYSQL_HOST/USER/PASSWORD/DB 等环境变量）

### Wiki (Confluence) 集成工具

- wiki.create_page（RPC：mcp_wiki_create_page）: 在 Wiki 中创建新页面，支持父页面、标签和多种内容格式

- wiki.update_page（RPC：mcp_wiki_update_page）: 更新 Wiki 页面内容，支持版本控制和评论

- wiki.search_pages（RPC：mcp_wiki_search_pages）: 搜索 Wiki 页面，支持全文搜索、标题搜索和空间限制

- wiki.get_page（RPC：mcp_wiki_get_page）: 获取 Wiki 页面详情，支持通过ID或标题查找

- wiki.read_url（RPC：mcp_wiki_read_url）: 根据 Wiki URL 直接读取页面内容，支持多种URL格式，可选包含评论和附件

- wiki.publish_task（RPC：mcp_wiki_publish_task）: 将 DevFlow 任务文档自动发布到 Wiki，创建结构化的文档页面

- wiki.add_comment（RPC：mcp_wiki_add_comment）: 向 Wiki 页面添加评论，支持回复评论

- wiki.get_comments（RPC：mcp_wiki_get_comments）: 获取 Wiki 页面的评论列表，支持过滤回复

- wiki.update_comment（RPC：mcp_wiki_update_comment）: 更新 Wiki 评论内容，自动版本控制

- wiki.delete_comment（RPC：mcp_wiki_delete_comment）: 删除 Wiki 评论

- wiki.diagnostic（RPC：mcp_wiki_diagnostic）: 诊断 Wiki API 连接和权限问题，自动测试多种API路径，解决501等错误

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

**🌿 Git分支集成**
- 自动从分支名提取ticket号码（如：feature/DTS-7442 → DTS-7442）
- 自动推导项目Key（如：DTS-7442 → DTS项目）
- 支持多种分支命名规范：feature/、bugfix/、hotfix/等
- 无需手动指定projectKey，开发更流畅

### Wiki (Confluence) 集成特性

**📖 页面管理**
- 完整的页面CRUD操作（创建、读取、更新、删除）
- 支持父子页面层级结构
- 自动版本控制和变更历史
- 灵活的标签管理系统

**💬 评论系统**
- 添加页面评论，支持HTML格式内容
- 回复评论功能，支持多层级讨论
- 获取评论列表，可选择包含或排除回复
- 更新和删除评论，自动版本控制
- 评论作者信息和时间戳追踪
- 智能API路径检测，自动绕过501错误
- 支持TinyMCE和标准REST API双重备份

**🔗 URL直读功能**
- 支持多种Wiki URL格式自动解析
- 直接通过页面链接获取完整内容
- 可选包含评论和附件信息
- 自动提取面包屑导航和作者信息
- 支持的URL格式：
  - `/display/SPACE/Page+Title`
  - `/pages/viewpage.action?spaceKey=SPACE&title=Page+Title`
  - `/spaces/SPACE/pages/123456/Page+Title`

**🔍 搜索功能**
- 全文内容搜索
- 标题精确匹配
- 空间范围限制
- CQL查询语言支持

**🛠️ 诊断和故障排除**
- 自动测试多种API路径和版本
- 智能检测API兼容性问题
- 提供具体的配置修复建议
- 识别权限和服务器配置问题
- 专门解决501 Not Implemented错误

**📝 内容格式**
- Markdown到Confluence存储格式自动转换
- 支持代码块、表格、链接等富文本元素
- Confluence宏（macro）自动生成
- 多种模板样式（标准、紧凑、详细）

**🔗 DevFlow集成**
```
任务发布流程:
DevFlow任务 → Wiki主页面 + 子页面
├── 任务概览页（状态、负责人、时间线）
├── 过程文档页（背景、设计、代码计划等）
├── 集成文档页（API文档、测试用例）
└── 自动链接和导航
```

**⚙️ 配置说明**
```bash
WIKI_BASE_URL=https://wiki.logisticsteam.com  # Wiki服务器地址
WIKI_CONTEXT_PATH=""                       # 上下文路径（通常为空）
WIKI_API_VERSION=1.0                       # API版本（基于您的API结构使用1.0）
WIKI_USER=you@example.com                 # Wiki用户名
WIKI_USER_PASSWORD=yourPassword            # Wiki密码
```

**🚀 使用场景**
- 将DevFlow任务文档发布到企业Wiki
- 创建结构化的项目文档空间
- 自动维护文档版本和链接关系
- 团队知识库的统一管理
- 页面评论和讨论管理
- 代码审查意见的Wiki记录
- 项目进展的评论跟踪
- 通过URL快速获取和分析Wiki页面内容
- 批量处理Wiki页面信息
- 与外部系统集成时的内容同步