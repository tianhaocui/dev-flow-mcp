from __future__ import annotations
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Any, Optional, Union, Literal
from pathlib import Path
import os
import json
import pymysql
import requests
from requests import Session
import yaml
from datetime import datetime
import frontmatter

# 文档根目录定位：优先使用环境变量 DOCS_PROJECT_ROOT，其次使用进程启动时的工作目录
# 这样可将输出写入“调用方项目”的 Docs 目录，而不是 MCP 自身仓库
PROJECT_ROOT = Path(os.getenv("DOCS_PROJECT_ROOT") or os.getcwd()).resolve()
DOCS_ROOT = PROJECT_ROOT / "Docs"
TASKS_DIR = DOCS_ROOT / ".tasks"
PROCESS_DIR = DOCS_ROOT / "ProcessDocuments"

JIRA_MCP_PATH = Path("/Volumes/外置/MCP/Jira-MCP-Server")
MYSQL_MCP_PATH = Path("/Volumes/外置/MCP/mysql_mcp_server")

app = FastMCP("devflow-mcp")

# ---------- Models (Inputs/Outputs) ----------
class PrepareDocsInput(BaseModel):
    """准备任务主文档与过程文档的输入参数"""
    model_config = ConfigDict(title="PrepareDocsInput", description="准备任务主文档与过程文档的输入参数")
    taskKey: str = Field(..., description="任务唯一标识，例如 PROJ-123")
    title: str = Field(..., description="任务标题")
    owner: str = Field(..., description="责任人")
    reviewers: List[str] = Field(default_factory=list, description="审核人列表")
    force: bool = Field(False, description="若已存在文档，是否强制覆盖骨架（谨慎）")
    projectRoot: Optional[str] = Field(None, description="（可选）项目根目录，默认使用 DOCS_PROJECT_ROOT 或当前工作目录")

class PrepareDocsOutput(BaseModel):
    taskKey: str
    mainDocPath: str
    mainDocPathRelative: Optional[str] = None
    processDir: str
    processDirRelative: Optional[str] = None
    status: str

class CodeGenInput(BaseModel):
    """代码生成计划的输入参数"""
    model_config = ConfigDict(title="CodeGenInput", description="代码生成计划的输入参数")
    taskKey: str = Field(..., description="任务唯一标识")
    requirements: str = Field(..., description="需求/目标的文字说明")
    constraints: List[str] = Field(default_factory=list, description="实现约束（路径/规范/安全等）")
    targetModules: List[str] = Field(default_factory=list, description="目标模块列表，例如 devflow_mcp")
    acceptanceCriteria: List[str] = Field(default_factory=list, description="验收标准列表")
    projectRoot: Optional[str] = Field(None, description="（可选）项目根目录")

class CodeGenOutput(BaseModel):
    codePlanDoc: str
    codePlanDocRelative: Optional[str] = None
    statusHint: str

class CurlGenInput(BaseModel):
    """curl 测试用例生成的输入参数"""
    model_config = ConfigDict(title="CurlGenInput", description="curl 测试用例生成的输入参数")
    taskKey: str = Field(..., description="任务唯一标识")
    baseUrl: Optional[str] = Field(None, description="接口基础地址，例如 https://api.example.com；若从 OpenAPI servers 推断可省略")
    endpoints: List[Dict[str, Any]] = Field(default_factory=list, description="要生成的接口清单（method/path/headers/payload），若留空将尝试从 OpenAPI 推断")
    envVars: Dict[str, str] = Field(default_factory=dict, description="env 变量示例，如 API_TOKEN")
    openapiUrl: Optional[str] = Field(None, description="OpenAPI 文档的 URL（json/yaml）")
    openapiPath: Optional[str] = Field(None, description="OpenAPI 文档的本地路径（json/yaml）")
    maxEndpoints: int = Field(20, description="从 OpenAPI 提取的最大接口数量上限")
    authMode: Literal['none', 'authorization_bearer', 'header_token', 'query_token'] = Field('none', description="鉴权方式：无/Authorization Bearer/自定义请求头/Query 参数")
    tokenEnvVar: str = Field('API_TOKEN', description="用于 curl 的令牌环境变量名，例如 API_TOKEN，将以 $API_TOKEN 引用")
    headerName: str = Field('accessToken', description="当 authMode=header_token 时使用的请求头名称（默认 accessToken）")
    queryParamName: str = Field('accessToken', description="当 authMode=query_token 时使用的查询参数名（默认 accessToken）")
    projectRoot: Optional[str] = Field(None, description="（可选）项目根目录")

class CurlGenOutput(BaseModel):
    curlDoc: str
    curlDocRelative: Optional[str] = None
    snippets: List[str]

class MySQLPlanInput(BaseModel):
    """MySQL 验证计划的输入参数"""
    model_config = ConfigDict(title="MySQLPlanInput", description="MySQL 验证计划的输入参数")
    taskKey: str = Field(..., description="任务唯一标识")
    tables: List[str] = Field(default_factory=list, description="涉及的表（可选）")
    preconditions: List[str] = Field(default_factory=list, description="前置 SQL 语句列表，如建表/准备数据")
    assertions: List[Dict[str, Any]] = Field(default_factory=list, description="断言 SQL 与期望描述")
    cleanup: List[str] = Field(default_factory=list, description="清理 SQL 语句列表")
    projectRoot: Optional[str] = Field(None, description="（可选）项目根目录")

class MySQLPlanOutput(BaseModel):
    verificationPlanDoc: str
    verificationPlanDocRelative: Optional[str] = None
    sqlPlan: Dict[str, Any]
    executionHint: str

class IntegrationDocInput(BaseModel):
    """对接文档生成的输入参数"""
    model_config = ConfigDict(title="IntegrationDocInput", description="对接文档生成的输入参数")
    taskKey: str = Field(..., description="任务唯一标识")
    audience: str = Field(..., description="目标读者：internal|external")
    systems: List[str] = Field(default_factory=list, description="涉及系统列表")
    interfaces: List[Dict[str, Any]] = Field(default_factory=list, description="接口定义列表（name/method/path/schemas）")
    notes: Optional[str] = Field(None, description="补充说明（可选）")
    projectRoot: Optional[str] = Field(None, description="（可选）项目根目录")

class IntegrationDocOutput(BaseModel):
    integrationDoc: str
    integrationDocRelative: Optional[str] = None
    toc: List[str]

class JiraPublishInput(BaseModel):
    """生成 Jira 提交计划的输入参数"""
    model_config = ConfigDict(title="JiraPublishInput", description="生成 Jira 提交计划的输入参数")
    taskKey: str = Field(..., description="任务唯一标识")
    projectKey: str = Field(..., description="Jira 项目 Key")
    issueType: str = Field(..., description="工单类型，如 Task/Story/Documentation")
    summary: str = Field(..., description="工单标题")
    description: str = Field(..., description="工单描述")
    labels: List[str] = Field(default_factory=list, description="标签列表（可选）")
    attachments: List[str] = Field(default_factory=list, description="要上传的附件路径列表（可选）")
    links: List[Dict[str, str]] = Field(default_factory=list, description="要关联的工单列表（可选）")
    projectRoot: Optional[str] = Field(None, description="（可选）项目根目录，用于解析附件相对路径")

class JiraPublishOutput(BaseModel):
    jiraPlanDoc: str
    jiraPlanDocRelative: Optional[str] = None
    jiraPayload: Dict[str, Any]
    executionHint: str

class ReviewStatusInput(BaseModel):
    """文档状态流转的输入参数"""
    model_config = ConfigDict(title="ReviewStatusInput", description="文档状态流转的输入参数")
    taskKey: str = Field(..., description="任务唯一标识")
    newStatus: str = Field(..., description="目标状态：PENDING_REVIEW/APPROVED/CHANGES_REQUESTED/PUBLISHED")
    by: str = Field(..., description="操作者")
    notes: Optional[str] = Field(None, description="备注（可选）")
    projectRoot: Optional[str] = Field(None, description="（可选）项目根目录，默认使用 DOCS_PROJECT_ROOT 或当前工作目录")

class ReviewStatusOutput(BaseModel):
    taskKey: str
    oldStatus: str
    newStatus: str

class ReviewChecklistInput(BaseModel):
    """一致性检查的输入参数"""
    model_config = ConfigDict(title="ReviewChecklistInput", description="一致性检查的输入参数")
    taskKey: str = Field(..., description="任务唯一标识")
    checks: List[str] = Field(..., description="需要执行的检查项标识列表")

class ReviewChecklistOutput(BaseModel):
    passed: bool
    failedItems: List[Dict[str, str]]

# ---------- Utils ----------

def _ensure_dirs_for(project_root: Optional[Path], task_key: Optional[str] = None) -> Dict[str, Path]:
    base = (project_root or PROJECT_ROOT)
    docs_root = base / "Docs"
    tasks_dir = docs_root / ".tasks"
    process_dir = docs_root / "ProcessDocuments"
    if task_key:
        process_dir = process_dir / f"task-{task_key}"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    process_dir.mkdir(parents=True, exist_ok=True)
    return {"docs_root": docs_root, "tasks_dir": tasks_dir, "process_dir": process_dir}


def _timestamp() -> str:
    return datetime.utcnow().isoformat()


def _resolve_project_root(explicit: Optional[str]) -> Path:
    if explicit:
        return Path(explicit).resolve()
    env = os.getenv("DOCS_PROJECT_ROOT")
    if env:
        return Path(env).resolve()
    return Path(os.getcwd()).resolve()


def _relpath(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except Exception:
        return str(path)


def _read_task_status(project_root: Path, task_key: str) -> str:
    main_doc = (project_root / "Docs" / ".tasks" / f"{task_key}.md")
    if not main_doc.exists():
        return "DRAFT"
    try:
        post = frontmatter.load(main_doc)
        status = str(post.metadata.get("status", "DRAFT")).strip().upper()
        return status or "DRAFT"
    except Exception:
        return "DRAFT"


_STATUS_ORDER = {"DRAFT": 1, "PENDING_REVIEW": 2, "CHANGES_REQUESTED": 2, "APPROVED": 3, "PUBLISHED": 4}


def _require_min_status(project_root: Path, task_key: str, min_status: str) -> None:
    current = _read_task_status(project_root, task_key)
    if _STATUS_ORDER.get(current, 0) < _STATUS_ORDER.get(min_status, 0):
        raise ValueError(f"Action not allowed: require >= {min_status}, current={current}")


# ---------- Tool Stubs (no-op implementations) ----------

@app.tool()
def task_prepare_docs(input: PrepareDocsInput) -> PrepareDocsOutput:
    """准备任务主文档与分步骤文档的骨架与标准路径（不落盘实现，返回计划与路径）。"""
    project_root = _resolve_project_root(input.projectRoot)
    dirs = _ensure_dirs_for(project_root, input.taskKey)
    main_doc = dirs["tasks_dir"] / f"{input.taskKey}.md"
    process_dir = dirs["process_dir"]
    return PrepareDocsOutput(
        taskKey=input.taskKey,
        mainDocPath=str(main_doc),
        mainDocPathRelative=_relpath(main_doc, project_root),
        processDir=str(process_dir),
        processDirRelative=_relpath(process_dir, project_root),
        status="DRAFT",
    )


@app.tool()
def task_request_code_generation(input: CodeGenInput) -> CodeGenOutput:
    """生成面向 AI 的代码编写计划文档路径与状态建议，指导后续开发与评审。"""
    project_root = _resolve_project_root(input.projectRoot)
    dirs = _ensure_dirs_for(project_root, input.taskKey)
    code_doc = dirs["process_dir"] / f"{input.taskKey}_03-CodePlan.md"
    return CodeGenOutput(
        codePlanDoc=str(code_doc),
        codePlanDocRelative=_relpath(code_doc, project_root),
        statusHint="PENDING_REVIEW recommended",
    )


@app.tool()
def test_generate_curl_calls(input: CurlGenInput) -> CurlGenOutput:
    """生成可执行的 curl 测试文档路径与片段列表，覆盖正/反用例（返回计划）。
    
    ⚠️ 前置条件：任务状态必须 >= APPROVED。
    👤 AI 提醒：调用前请先确认任务的状态是否已通过人工审核(APPROVED)。
    如当前状态为 DRAFT/PENDING_REVIEW，请先与用户确认是否需要：
    1. 使用 review_set_status 将状态改为 APPROVED，或
    2. 用户手动审核通过后再调用此工具
    
    支持两种来源：
    - 直接传入 endpoints（method/path/...）
    - 通过 openapiUrl/openapiPath 解析 OpenAPI，自动提取 endpoints
    """
    project_root = _resolve_project_root(input.projectRoot)
    dirs = _ensure_dirs_for(project_root, input.taskKey)
    doc_path = dirs["process_dir"] / f"{input.taskKey}_04-TestCurls.md"

    def _load_openapi() -> Optional[Dict[str, Any]]:
        spec_text: Optional[str] = None
        if input.openapiUrl:
            resp = requests.get(input.openapiUrl, timeout=30)
            if resp.status_code >= 400:
                raise ValueError(f"OpenAPI url fetch failed: {resp.status_code}")
            spec_text = resp.text
        elif input.openapiPath:
            p = Path(input.openapiPath)
            if not p.is_absolute():
                p = (PROJECT_ROOT / p).resolve()
            if not p.is_file():
                raise ValueError(f"OpenAPI file not found: {p}")
            spec_text = p.read_text(encoding="utf-8")
        if not spec_text:
            return None
        try:
            return json.loads(spec_text)
        except Exception:
            return yaml.safe_load(spec_text)

    def _extract_endpoints_from_openapi(spec: Dict[str, Any]) -> (List[Dict[str, Any]], Optional[str]):
        endpoints: List[Dict[str, Any]] = []
        derived_base: Optional[str] = None
        # derive baseUrl from servers (OpenAPI v3)
        servers = spec.get("servers")
        if isinstance(servers, list) and servers:
            srv = servers[0]
            if isinstance(srv, dict):
                derived_base = srv.get("url")
        # paths
        paths = spec.get("paths", {})
        for path, ops in paths.items():
            if not isinstance(ops, dict):
                continue
            for method in ["get", "post", "put", "delete", "patch", "head", "options"]:
                if method in ops:
                    op = ops[method]
                    desc = op.get("summary") or op.get("operationId") or ""
                    endpoints.append({
                        "method": method.upper(),
                        "path": path,
                        "description": desc,
                    })
                    if len(endpoints) >= max(1, input.maxEndpoints):
                        return endpoints, derived_base
        return endpoints, derived_base

    # 门禁：只有在 APPROVED 之后才允许生成 curl
    _require_min_status(project_root, input.taskKey, "APPROVED")

    endpoints = list(input.endpoints or [])
    derived_base = None
    if not endpoints:
        spec = _load_openapi()
        if spec:
            endpoints, derived_base = _extract_endpoints_from_openapi(spec)
    if not endpoints:
        raise ValueError("需要提供 endpoints 或 openapiUrl/openapiPath 以生成 curl 用例")

    base_url = input.baseUrl or derived_base or ""
    snippets: List[str] = []
    default_auth_mode = input.authMode or 'none'
    default_header_name = input.headerName or 'accessToken'
    default_query_name = input.queryParamName or 'accessToken'
    token_shell = f"${input.tokenEnvVar}" if input.tokenEnvVar else "$API_TOKEN"
    for ep in endpoints:
        method = (ep.get("method") or "GET").upper()
        path = ep.get("path") or "/"
        headers = ep.get("headers") or {}
        payload = ep.get("samplePayload")
        # 计算鉴权策略（端点可覆盖全局）
        auth_mode = (ep.get("authMode") or default_auth_mode) if isinstance(ep, dict) else default_auth_mode
        header_name = ep.get("headerName") if isinstance(ep, dict) else None
        query_name = ep.get("queryParamName") if isinstance(ep, dict) else None
        eff_header_name = header_name or default_header_name
        eff_query_name = query_name or default_query_name
        parts = ["curl -sS -X", method]
        # 注入鉴权
        if auth_mode == 'authorization_bearer':
            headers = {**headers, "Authorization": f"Bearer {token_shell}"}
        elif auth_mode == 'header_token':
            headers = {**headers, eff_header_name: token_shell}
        # 写入头部
        for k, v in headers.items():
            parts += ["-H", f"\"{k}: {v}\""]
        # 构造 URL 并注入 query token（如需要）
        url = (base_url.rstrip("/") + path) if base_url else path
        if auth_mode == 'query_token':
            sep = '&' if ('?' in url) else '?'
            url = f"{url}{sep}{eff_query_name}={token_shell}"
        if payload is not None:
            parts += ["-H", "\"Content-Type: application/json\"", "--data", json.dumps(payload)]
        parts += [f"\"{url}\""]
        snippets.append(" ".join(parts))

    # 将生成的 curl 用例写入文档文件
    try:
        doc_path.parent.mkdir(parents=True, exist_ok=True)
        lines: List[str] = []
        lines.append("---")
        lines.append("status: DRAFT")
        lines.append(f"generatedAt: {_timestamp()}")
        if base_url:
            lines.append(f"baseUrl: {base_url}")
        lines.append("---\n")
        lines.append("## 运行前")
        lines.append(f"- 导出令牌: export {input.tokenEnvVar or 'API_TOKEN'}=\"<token>\"\n")
        lines.append("## 用例")
        for idx, snip in enumerate(snippets, start=1):
            lines.append(f"\n### 用例 {idx}")
            lines.append("```bash")
            lines.append(snip)
            lines.append("```")
        content = "\n".join(lines) + "\n"
        doc_path.write_text(content, encoding="utf-8")
    except Exception:
        # 写入失败不阻塞返回
        pass

    return CurlGenOutput(curlDoc=str(doc_path), curlDocRelative=_relpath(doc_path, project_root), snippets=snippets)


@app.tool()
def verify_plan_with_mysql_mcp(input: MySQLPlanInput) -> MySQLPlanOutput:
    """生成 MySQL 验证计划（前置/断言/清理），建议由 MySQL MCP 或内置执行工具执行。
    
    ⚠️ 前置条件：任务状态必须 >= APPROVED。
    👤 AI 提醒：调用前请先确认任务的状态是否已通过人工审核(APPROVED)。
    如当前状态不满足，请主动与用户确认是否需要先进行状态流转。
    """
    project_root = _resolve_project_root(input.projectRoot)
    # 门禁：要求 APPROVED
    _require_min_status(project_root, input.taskKey, "APPROVED")
    dirs = _ensure_dirs_for(project_root, input.taskKey)
    doc_path = dirs["process_dir"] / f"{input.taskKey}_05-MySQLVerificationPlan.md"
    plan = {
        "preconditions": input.preconditions,
        "assertions": input.assertions,
        "cleanup": input.cleanup,
        "hints": {
            "mysql_mcp_path": str(MYSQL_MCP_PATH),
            "execution_order": ["preconditions", "assertions", "cleanup"],
        },
    }
    return MySQLPlanOutput(
        verificationPlanDoc=str(doc_path),
        verificationPlanDocRelative=_relpath(doc_path, project_root),
        sqlPlan=plan,
        executionHint="Use MySQL MCP to run the plan sequentially",
    )


@app.tool()
def docs_generate_integration(input: IntegrationDocInput) -> IntegrationDocOutput:
    """生成对接文档框架（概览/鉴权/接口/Schema/错误码/样例）的路径与目录结构。
    
    ⚠️ 前置条件：任务状态必须 >= APPROVED。
    👤 AI 提醒：调用前请先确认任务的状态是否已通过人工审核(APPROVED)。
    如当前状态不满足，请主动与用户确认是否需要先进行状态流转。
    """
    project_root = _resolve_project_root(input.projectRoot)
    # 门禁：要求 APPROVED
    _require_min_status(project_root, input.taskKey, "APPROVED")
    dirs = _ensure_dirs_for(project_root, input.taskKey)
    doc_path = dirs["process_dir"] / f"{input.taskKey}_06-Integration.md"
    toc = ["Overview", "Auth", "Endpoints", "Schemas", "Errors", "Samples"]
    return IntegrationDocOutput(integrationDoc=str(doc_path), integrationDocRelative=_relpath(doc_path, project_root), toc=toc)


@app.tool()
def jira_publish_integration_doc(input: JiraPublishInput) -> JiraPublishOutput:
    """生成 Jira 提交计划（payload 与附件清单），供 Jira MCP 或内置 Jira 工具执行。
    
    ⚠️ 前置条件：任务状态必须 >= APPROVED 且相关文档已生成。
    👤 AI 提醒：调用前请先确认：
    1. 任务的状态是否已通过人工审核(APPROVED)
    2. 对接文档等附件是否已生成完成
    如条件不满足，请主动与用户确认后续步骤。
    """
    project_root = _resolve_project_root(input.projectRoot)
    # 门禁：要求所有检查通过且状态 APPROVED，可按需改为 PUBLISHED 前检查
    _require_min_status(project_root, input.taskKey, "APPROVED")
    dirs = _ensure_dirs_for(project_root, input.taskKey)
    doc_path = dirs["process_dir"] / f"{input.taskKey}_07-JiraPublishPlan.md"
    payload = {
        "fields": {
            "project": {"key": input.projectKey},
            "issuetype": {"name": input.issueType},
            "summary": input.summary,
            "description": input.description,
            "labels": input.labels,
        },
        "attachments": input.attachments,
        "links": input.links,
        "hints": {"jira_mcp_path": str(JIRA_MCP_PATH)},
    }
    return JiraPublishOutput(jiraPlanDoc=str(doc_path), jiraPlanDocRelative=_relpath(doc_path, project_root), jiraPayload=payload, executionHint="Use Jira MCP to create issue and attach docs")


@app.tool()
def review_set_status(input: ReviewStatusInput) -> ReviewStatusOutput:
    """切换主任务文档（Docs/.tasks/{taskKey}.md）的 Front Matter 状态并记录审核日志。
    
    👤 AI 提醒：状态流转通常需要人工审核决策。建议调用前：
    1. 向用户说明当前状态和拟变更的目标状态
    2. 确认变更原因和后续影响
    3. 获得用户明确同意后再执行状态切换
    """
    project_root = _resolve_project_root(input.projectRoot)
    dirs = _ensure_dirs_for(project_root, None)
    main_doc = dirs["tasks_dir"] / f"{input.taskKey}.md"

    old_status = _read_task_status(project_root, input.taskKey)

    # 读取或创建 Front Matter
    if main_doc.exists():
        post = frontmatter.load(main_doc)
    else:
        post = frontmatter.Post("")

    metadata = dict(post.metadata or {})
    metadata["status"] = input.newStatus
    metadata["updatedAt"] = _timestamp()
    reviews = list(metadata.get("reviews", []))
    reviews.append({
        "by": input.by,
        "from": old_status,
        "to": input.newStatus,
        "notes": input.notes or "",
        "time": _timestamp(),
    })
    metadata["reviews"] = reviews
    post.metadata = metadata

    # 落盘（确保以文本写入，避免 bytes/str 混写）
    main_doc.parent.mkdir(parents=True, exist_ok=True)
    content_str = frontmatter.dumps(post)
    main_doc.write_text(content_str, encoding="utf-8")

    return ReviewStatusOutput(taskKey=input.taskKey, oldStatus=old_status, newStatus=input.newStatus)


@app.tool()
def review_validate_checklist(input: ReviewChecklistInput) -> ReviewChecklistOutput:
    """执行一致性校验（文档存在性、状态门禁、配置完整性等），返回通过与失败项。"""
    # 骨架：全部通过，或简单模拟失败项
    failed: List[Dict[str, str]] = []
    return ReviewChecklistOutput(passed=len(failed) == 0, failedItems=failed)


# ---------- External MCP Features (Integrated Implementations) ----------

# MySQL MCP parity: execute SQL statements sequentially
class MySQLExecuteInput(BaseModel):
    """直接执行 SQL 语句的输入参数"""
    model_config = ConfigDict(title="MySQLExecuteInput", description="直接执行 SQL 语句的输入参数")
    taskKey: Optional[str] = Field(None, description="任务唯一标识（可选，用于审计）")
    statements: List[str] = Field(..., description="要顺序执行的 SQL 列表")
    continueOnError: bool = Field(False, description="遇到错误是否继续执行后续语句")


class MySQLStatementResult(BaseModel):
    sql: str
    success: bool
    rowsAffected: Optional[int] = None
    rows: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None


class MySQLExecuteOutput(BaseModel):
    results: List[MySQLStatementResult]
    hint: str


def _get_mysql_connection():
    host = os.getenv("MYSQL_HOST")
    user = os.getenv("MYSQL_USER")
    password = os.getenv("MYSQL_PASSWORD")
    database = os.getenv("MYSQL_DB")
    port = int(os.getenv("MYSQL_PORT", "3306"))
    charset = os.getenv("MYSQL_CHARSET", "utf8mb4")
    if not all([host, user, password, database]):
        missing = [n for n, v in [("MYSQL_HOST", host), ("MYSQL_USER", user), ("MYSQL_PASSWORD", password), ("MYSQL_DB", database)] if not v]
        raise ValueError(f"Missing MySQL env vars: {', '.join(missing)}")
    return pymysql.connect(host=host, port=port, user=user, password=password, database=database, charset=charset, cursorclass=pymysql.cursors.DictCursor, autocommit=True)


@app.tool()
def mysql_execute_statements(input: MySQLExecuteInput) -> MySQLExecuteOutput:
    """执行一组 SQL 语句。
    需要环境变量：MYSQL_HOST, MYSQL_PORT(可选), MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB, MYSQL_CHARSET(可选)
    """
    results: List[MySQLStatementResult] = []
    try:
        connection = _get_mysql_connection()
    except Exception as exc:  # pragma: no cover
        for sql in input.statements:
            results.append(MySQLStatementResult(sql=sql, success=False, error=f"ConnectionError: {exc}"))
        return MySQLExecuteOutput(results=results, hint="Ensure MySQL env vars are set and reachable")

    try:
        with connection.cursor() as cursor:
            for sql in input.statements:
                try:
                    is_select = sql.strip().lower().startswith("select")
                    cursor.execute(sql)
                    if is_select:
                        rows = cursor.fetchall()
                        results.append(MySQLStatementResult(sql=sql, success=True, rows=rows, rowsAffected=None))
                    else:
                        rows_affected = cursor.rowcount
                        results.append(MySQLStatementResult(sql=sql, success=True, rows=None, rowsAffected=rows_affected))
                except Exception as stmt_exc:  # pragma: no cover
                    results.append(MySQLStatementResult(sql=sql, success=False, error=str(stmt_exc)))
                    if not input.continueOnError:
                        break
    finally:
        try:
            connection.close()
        except Exception:
            pass

    return MySQLExecuteOutput(results=results, hint="Executed using direct MySQL connection from devflow-mcp")


# Jira MCP parity: create issue, attach files, link issues
class JiraCreateIssueInput(BaseModel):
    """在 Jira 中创建工单的输入参数"""
    model_config = ConfigDict(title="JiraCreateIssueInput", description="在 Jira 中创建工单的输入参数")
    projectKey: str = Field(..., description="Jira 项目 Key")
    issueType: str = Field(..., description="工单类型，如 Task/Story/Documentation")
    summary: str = Field(..., description="工单标题")
    description: str = Field(..., description="工单描述")
    labels: List[str] = Field(default_factory=list, description="标签列表（可选）")
    fields: Dict[str, Any] = Field(default_factory=dict, description="额外自定义字段（可选）")


class JiraCreateIssueOutput(BaseModel):
    issueKey: Optional[str] = None
    url: Optional[str] = None
    hint: str


def _get_jira_session() -> Session:
    base_url = os.getenv("JIRA_BASE_URL")
    user = os.getenv("JIRA_USER")
    password = os.getenv("JIRA_USER_PASSWORD")
    token = os.getenv("JIRA_API_TOKEN")  # 兼容旧配置
    bearer = os.getenv("JIRA_BEARER_TOKEN")
    if not base_url:
        raise ValueError("Missing env: JIRA_BASE_URL")
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})
    # 优先顺序：用户+密码 > Bearer > 用户+API Token（兼容）
    if user and password:
        session.auth = (user, password)
    elif bearer:
        session.headers.update({"Authorization": f"Bearer {bearer}"})
    elif user and token:
        session.auth = (user, token)
    else:
        raise ValueError("Missing Jira auth: set JIRA_USER + JIRA_USER_PASSWORD (preferred), or JIRA_BEARER_TOKEN, or JIRA_USER + JIRA_API_TOKEN")
    return session


def _jira_api_url(path: str) -> str:
    base_url = os.getenv("JIRA_BASE_URL", "").rstrip("/")
    # 支持 context path，例如 /jira，参考 Jira Server 7.x REST 结构
    context_path = os.getenv("JIRA_CONTEXT_PATH", "").strip()
    if context_path and not context_path.startswith("/"):
        context_path = "/" + context_path
    # Jira Server 7.x 默认使用 REST v2。可通过环境变量覆盖。
    api_version = os.getenv("JIRA_API_VERSION", "2")
    return f"{base_url}{context_path}/rest/api/{api_version}/{path.lstrip('/')}"


@app.tool()
def jira_create_issue(input: JiraCreateIssueInput) -> JiraCreateIssueOutput:
    """在 Jira 中创建工单（REST v3，支持自定义字段）。认证优先 JIRA_USER/JIRA_USER_PASSWORD。"""
    try:
        session = _get_jira_session()
        payload = {"fields": {"project": {"key": input.projectKey}, "issuetype": {"name": input.issueType}, "summary": input.summary, "description": input.description, "labels": input.labels}}
        # 合并自定义字段
        payload["fields"].update(input.fields or {})
        url = _jira_api_url("issue")
        resp = session.post(url, json=payload, timeout=30)
        if resp.status_code >= 400:
            return JiraCreateIssueOutput(issueKey=None, url=None, hint=f"Jira create failed: {resp.status_code} {resp.text}")
        data = resp.json()
        issue_key = data.get("key")
        browse_base = os.getenv("JIRA_BROWSE_BASE", os.getenv("JIRA_BASE_URL", "").rstrip("/"))
        issue_url = f"{browse_base}/browse/{issue_key}" if issue_key else None
        return JiraCreateIssueOutput(issueKey=issue_key, url=issue_url, hint="Created via Jira REST API")
    except Exception as exc:  # pragma: no cover
        return JiraCreateIssueOutput(issueKey=None, url=None, hint=f"Jira error: {exc}")


class JiraAttachFilesInput(BaseModel):
    """Jira 上传附件的输入参数"""
    model_config = ConfigDict(title="JiraAttachFilesInput", description="Jira 上传附件的输入参数")
    issueKey: str = Field(..., description="目标工单 Key")
    filePaths: List[str] = Field(..., description="要上传的文件路径列表")


class JiraAttachFilesOutput(BaseModel):
    attached: List[str]
    failed: List[Dict[str, Any]]
    hint: str


@app.tool()
def jira_attach_files(input: JiraAttachFilesInput) -> JiraAttachFilesOutput:
    """向指定工单上传附件（需 X-Atlassian-Token:no-check）。支持多文件批量上传，并返回失败原因。"""
    try:
        session = _get_jira_session()
        url = _jira_api_url(f"issue/{input.issueKey}/attachments")
        session.headers.update({"X-Atlassian-Token": "no-check"})
        attached: List[str] = []
        failed: List[Dict[str, Any]] = []
        for original_path in input.filePaths:
            p = Path(original_path)
            if not p.is_absolute():
                p = (PROJECT_ROOT / p).resolve()
            if not p.is_file():
                failed.append({"path": str(p), "reason": "file not found"})
                continue
            try:
                with open(p, "rb") as f:
                    files = {"file": (p.name, f)}
                    resp = session.post(url, files=files, timeout=60)
                if resp.status_code < 400:
                    attached.append(str(p))
                else:
                    failed.append({
                        "path": str(p),
                        "status": resp.status_code,
                        "reason": resp.text[:500]
                    })
            except Exception as file_exc:  # pragma: no cover
                failed.append({"path": str(p), "reason": str(file_exc)})
        hint = f"Uploaded {len(attached)} file(s), failed {len(failed)} via Jira REST API"
        return JiraAttachFilesOutput(attached=attached, failed=failed, hint=hint)
    except Exception as exc:  # pragma: no cover
        return JiraAttachFilesOutput(attached=[], failed=[{"error": str(exc)}], hint=f"Jira attach error")


class JiraLinkIssuesInput(BaseModel):
    """Jira 关联工单的输入参数"""
    model_config = ConfigDict(title="JiraLinkIssuesInput", description="Jira 关联工单的输入参数")
    inwardIssue: str = Field(..., description="关联方向的内向工单 Key")
    outwardIssue: str = Field(..., description="关联方向的外向工单 Key")
    linkType: str = Field("relates to", description="关联类型：Relates/Blocks/Duplicate 等")


class JiraLinkIssuesOutput(BaseModel):
    ok: bool
    hint: str


@app.tool()
def jira_link_issues(input: JiraLinkIssuesInput) -> JiraLinkIssuesOutput:
    """关联两个工单（linkType: Relates/Blocks/Duplicate 等）。"""
    try:
        session = _get_jira_session()
        url = _jira_api_url("issueLink")
        payload = {"type": {"name": input.linkType}, "inwardIssue": {"key": input.inwardIssue}, "outwardIssue": {"key": input.outwardIssue}}
        resp = session.post(url, json=payload, timeout=30)
        if resp.status_code >= 400:
            return JiraLinkIssuesOutput(ok=False, hint=f"Jira link failed: {resp.status_code} {resp.text}")
        return JiraLinkIssuesOutput(ok=True, hint="Linked via Jira REST API")
    except Exception as exc:  # pragma: no cover
        return JiraLinkIssuesOutput(ok=False, hint=f"Jira link error: {exc}")

if __name__ == "__main__":
    # 以 stdio 方式启动 MCP（FastMCP 会处理协议细节）
    app.run()
