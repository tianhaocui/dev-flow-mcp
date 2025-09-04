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
import re
import subprocess

# 文档根目录定位：优先使用环境变量 DOCS_PROJECT_ROOT，其次使用进程启动时的工作目录
# 这样可将输出写入“调用方项目”的 Docs 目录，而不是 MCP 自身仓库
PROJECT_ROOT = Path(os.getenv("DOCS_PROJECT_ROOT") or os.getcwd()).resolve()
DOCS_ROOT = PROJECT_ROOT / "Docs"
TASKS_DIR = DOCS_ROOT / ".tasks"
PROCESS_DIR = DOCS_ROOT / "ProcessDocuments"

# 内置实现，无需外部MCP路径

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

class MySQLStatementResult(BaseModel):
    sql: str
    success: bool
    rowsAffected: Optional[int] = None
    rows: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None

class MySQLPlanOutput(BaseModel):
    verificationPlanDoc: str
    verificationPlanDocRelative: Optional[str] = None
    sqlPlan: Dict[str, Any]
    executionResults: Optional[List[MySQLStatementResult]] = None
    executed: bool = False

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
    projectKey: Optional[str] = Field(None, description="Jira 项目 Key（可选，为空时自动从Git分支解析）")
    issueType: str = Field(..., description="工单类型，如 Task/Story/Documentation")
    summary: str = Field(..., description="工单标题")
    description: str = Field(..., description="工单描述")
    labels: List[str] = Field(default_factory=list, description="标签列表（可选）")
    attachments: List[str] = Field(default_factory=list, description="要上传的附件路径列表（可选）")
    links: List[Dict[str, str]] = Field(default_factory=list, description="要关联的工单列表（可选）")
    projectRoot: Optional[str] = Field(None, description="（可选）项目根目录，用于解析附件相对路径")
    autoDetectFromBranch: bool = Field(True, description="是否自动从Git分支检测项目信息（默认启用）")

class JiraCreateIssueOutput(BaseModel):
    issueKey: Optional[str] = None
    url: Optional[str] = None
    hint: str

class JiraAttachFilesOutput(BaseModel):
    attached: List[str]
    failed: List[Dict[str, Any]]
    hint: str

class JiraPublishOutput(BaseModel):
    jiraPlanDoc: str
    jiraPlanDocRelative: Optional[str] = None
    jiraPayload: Dict[str, Any]
    createdIssue: Optional[JiraCreateIssueOutput] = None
    attachmentResults: Optional[JiraAttachFilesOutput] = None
    executed: bool = False

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

# 新增：状态管理相关模型
class StatusQueryInput(BaseModel):
    """查询状态信息的输入参数"""
    model_config = ConfigDict(title="StatusQueryInput", description="查询状态信息的输入参数")
    taskKey: str = Field(..., description="任务唯一标识")
    includeHistory: bool = Field(True, description="是否包含历史记录")
    includeStats: bool = Field(True, description="是否包含统计信息")
    projectRoot: Optional[str] = Field(None, description="（可选）项目根目录")

class StatusQueryOutput(BaseModel):
    taskKey: str
    currentStatus: str
    allowedTransitions: List[str]
    history: Optional[List[Dict[str, Any]]] = None
    stats: Optional[Dict[str, Any]] = None

class StatusBatchInput(BaseModel):
    """批量状态操作的输入参数"""
    model_config = ConfigDict(title="StatusBatchInput", description="批量状态操作的输入参数") 
    operations: List[Dict[str, Any]] = Field(..., description="批量操作列表，每项包含taskKey、newStatus、by、notes等")
    continueOnError: bool = Field(False, description="遇到错误时是否继续执行")
    projectRoot: Optional[str] = Field(None, description="（可选）项目根目录")

class StatusBatchOutput(BaseModel):
    successful: List[Dict[str, Any]]
    failed: List[Dict[str, Any]]
    summary: Dict[str, int]

class StatusReportInput(BaseModel):
    """状态报告的输入参数"""
    model_config = ConfigDict(title="StatusReportInput", description="状态报告的输入参数")
    includeAll: bool = Field(True, description="是否包含所有任务")
    statusFilter: Optional[List[str]] = Field(None, description="状态过滤器")
    userFilter: Optional[str] = Field(None, description="用户过滤器")
    projectRoot: Optional[str] = Field(None, description="（可选）项目根目录")

class StatusReportOutput(BaseModel):
    totalTasks: int
    statusBreakdown: Dict[str, int]
    recentActivity: List[Dict[str, Any]]
    blockedTasks: List[Dict[str, Any]]
    summary: Dict[str, Any]

# ---------- Jira分析与测试对比相关模型 ----------

class JiraFetchInput(BaseModel):
    """Jira工单获取的输入参数"""
    model_config = ConfigDict(title="JiraFetchInput", description="Jira工单获取的输入参数")
    issueKey: str = Field(..., description="Jira工单Key，如 PROJ-123")
    includeSubtasks: bool = Field(True, description="是否包含子任务")
    includeAttachments: bool = Field(True, description="是否下载附件")
    includeHistory: bool = Field(False, description="是否包含变更历史")
    attachmentPath: Optional[str] = Field(None, description="附件下载路径（相对于项目根目录）")
    
class JiraIssueInfo(BaseModel):
    """Jira工单信息"""
    key: str
    summary: str
    description: str
    status: str
    issueType: str
    priority: str
    assignee: Optional[str] = None
    reporter: Optional[str] = None
    created: str
    updated: str
    customFields: Dict[str, Any] = Field(default_factory=dict)
    
class JiraSubtask(BaseModel):
    """Jira子任务信息"""
    key: str
    summary: str
    description: str
    status: str
    assignee: Optional[str] = None
    
class JiraAttachment(BaseModel):
    """Jira附件信息"""
    id: str
    filename: str
    size: int
    mimeType: str
    author: str
    created: str
    downloadUrl: str
    localPath: Optional[str] = None  # 下载后的本地路径
    
class JiraFetchOutput(BaseModel):
    issueInfo: JiraIssueInfo
    subtasks: List[JiraSubtask] = Field(default_factory=list)
    attachments: List[JiraAttachment] = Field(default_factory=list)
    downloadedFiles: List[str] = Field(default_factory=list)
    
class TestAnalysisInput(BaseModel):
    """测试分析的输入参数"""
    model_config = ConfigDict(title="TestAnalysisInput", description="测试分析的输入参数")
    taskKey: str = Field(..., description="DevFlow任务Key")
    jiraIssueKey: str = Field(..., description="关联的Jira工单Key")
    analysisType: str = Field("coverage", description="分析类型：coverage/gap/recommendation")
    includeAttachments: bool = Field(True, description="是否分析附件内容")
    projectRoot: Optional[str] = Field(None, description="项目根目录")
    
class RequirementItem(BaseModel):
    """需求条目"""
    id: str
    title: str
    description: str
    priority: str = "Medium"
    category: str = "功能性"
    source: str  # 来源：description/subtask/attachment
    
class TestCaseMatch(BaseModel):
    """测试用例匹配信息"""
    requirementId: str
    testCases: List[str] = Field(default_factory=list)
    coverage: float  # 0-1之间的覆盖度
    gaps: List[str] = Field(default_factory=list)
    
class TestAnalysisOutput(BaseModel):
    taskKey: str
    jiraIssueKey: str
    requirements: List[RequirementItem]
    testMatches: List[TestCaseMatch] 
    overallCoverage: float
    missingTests: List[str]
    recommendedTests: List[str]
    analysisReport: str  # 详细的分析报告路径
    
class RequirementSyncInput(BaseModel):
    """需求同步的输入参数"""
    model_config = ConfigDict(title="RequirementSyncInput", description="需求同步的输入参数")
    jiraIssueKey: str = Field(..., description="Jira工单Key")
    targetTaskKey: Optional[str] = Field(None, description="目标DevFlow任务Key，为空则自动创建")
    syncMode: str = Field("update", description="同步模式：create/update/merge")
    autoGenerateTests: bool = Field(False, description="是否自动生成测试用例")
    projectRoot: Optional[str] = Field(None, description="项目根目录")
    
class RequirementSyncOutput(BaseModel):
    taskKey: str
    jiraIssueKey: str
    createdFiles: List[str]
    updatedFiles: List[str]
    generatedTests: List[str]
    syncReport: str

# ---------- Git Utils ----------

def _get_recent_git_commits(limit: int = 5) -> List[Dict[str, str]]:
    """获取最近的Git提交记录"""
    try:
        result = subprocess.run(
            ["git", "log", f"--max-count={limit}", "--pretty=format:%h|%s|%an|%ar"],
            capture_output=True,
            text=True,
            check=True
        )
        commits = []
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split('|')
                if len(parts) >= 4:
                    commits.append({
                        "hash": parts[0],
                        "message": parts[1],
                        "author": parts[2],
                        "time": parts[3]
                    })
        return commits
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

def _get_current_git_branch() -> str:
    """获取当前Git分支名称"""
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"], 
            capture_output=True, 
            text=True, 
            check=True
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "main"  # 默认分支

def _extract_ticket_from_branch(branch_name: str) -> Optional[str]:
    """从分支名称中提取ticket号码"""
    if not branch_name:
        return None
        
    # 常见的分支命名模式
    patterns = [
        r'^feature/([A-Z]+-\d+)',     # feature/DTS-7442
        r'^bugfix/([A-Z]+-\d+)',      # bugfix/DTS-7442
        r'^hotfix/([A-Z]+-\d+)',      # hotfix/DTS-7442
        r'^([A-Z]+-\d+)-.*',          # DTS-7442-some-description
        r'^([A-Z]+-\d+)$',            # DTS-7442
        r'([A-Z]+-\d+)',              # 任意位置的 DTS-7442 格式
    ]
    
    for pattern in patterns:
        match = re.search(pattern, branch_name, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    
    return None

def _get_project_key_from_ticket(ticket_key: str) -> Optional[str]:
    """从ticket号码中提取项目key"""
    if not ticket_key:
        return None
    
    # 提取项目前缀，例如 DTS-7442 -> DTS
    match = re.match(r'^([A-Z]+)-\d+', ticket_key)
    if match:
        return match.group(1)
    
    return None

def _auto_detect_jira_context() -> Dict[str, Optional[str]]:
    """自动检测当前上下文的Jira相关信息"""
    branch_name = _get_current_git_branch()
    ticket_key = _extract_ticket_from_branch(branch_name)
    project_key = _get_project_key_from_ticket(ticket_key) if ticket_key else None
    
    return {
        "branch_name": branch_name,
        "ticket_key": ticket_key,
        "project_key": project_key
    }

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


# 状态定义和转换规则
_STATUS_ORDER = {"DRAFT": 1, "PENDING_REVIEW": 2, "CHANGES_REQUESTED": 2, "APPROVED": 3, "PUBLISHED": 4}

# 合法的状态转换路径
_STATUS_TRANSITIONS = {
    "DRAFT": ["PENDING_REVIEW"],
    "PENDING_REVIEW": ["APPROVED", "CHANGES_REQUESTED"],
    "CHANGES_REQUESTED": ["PENDING_REVIEW", "DRAFT"], 
    "APPROVED": ["PUBLISHED", "CHANGES_REQUESTED"],
    "PUBLISHED": []  # 终态，不允许转换
}

def _validate_status_transition(from_status: str, to_status: str) -> bool:
    """验证状态转换是否合法"""
    if from_status not in _STATUS_TRANSITIONS:
        return False
    return to_status in _STATUS_TRANSITIONS[from_status]

def _require_min_status(project_root: Path, task_key: str, min_status: str) -> None:
    current = _read_task_status(project_root, task_key)
    if _STATUS_ORDER.get(current, 0) < _STATUS_ORDER.get(min_status, 0):
        raise ValueError(f"Action not allowed: require >= {min_status}, current={current}")

class StatusValidationError(Exception):
    """状态验证错误"""
    pass

def _get_task_metadata(project_root: Path, task_key: str) -> Dict[str, Any]:
    """获取任务的元数据"""
    main_doc = (project_root / "Docs" / ".tasks" / f"{task_key}.md")
    if not main_doc.exists():
        return {}
    try:
        post = frontmatter.load(main_doc)
        return post.metadata or {}
    except Exception:
        return {}

# ---------- Jira与测试分析辅助函数 ----------

def _download_jira_attachment(session: Session, attachment_info: Dict[str, Any], download_dir: Path) -> Optional[str]:
    """下载Jira附件到指定目录"""
    try:
        download_url = attachment_info.get("content", "")
        filename = attachment_info.get("filename", f"attachment_{attachment_info.get('id', 'unknown')}")
        
        if not download_url:
            return None
            
        response = session.get(download_url, stream=True, timeout=60)
        if response.status_code >= 400:
            return None
            
        download_dir.mkdir(parents=True, exist_ok=True)
        file_path = download_dir / filename
        
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    
        return str(file_path)
        
    except Exception:
        return None

def _parse_requirements_from_text(text: str, source: str = "description") -> List[RequirementItem]:
    """从文本中解析需求条目"""
    requirements = []
    
    if not text or not text.strip():
        return requirements
    
    # 简单的需求识别算法
    lines = text.split('\n')
    current_req = None
    req_id = 1
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # 识别需求标识（如：需求1、Feature、功能等）
        req_patterns = [
            r'^(\d+[\.\)]\s*)',  # 1. 或 1) 开头
            r'^([需求功能特性]\d*[\.\:：]\s*)',  # 需求1. 或 功能:
            r'^(.*应该|.*必须|.*需要)',  # 需求性语言
            r'^(User Story|Feature|需求)[\s\:：]',  # 明确标识
        ]
        
        is_requirement = False
        for pattern in req_patterns:
            if re.search(pattern, line):
                is_requirement = True
                break
        
        if is_requirement or len(line) > 20:  # 长句子可能是需求描述
            # 确定优先级
            priority = "Medium"
            if "重要" in line or "关键" in line or "高优先级" in line:
                priority = "High"
            elif "可选" in line or "低优先级" in line:
                priority = "Low"
            
            # 确定类别
            category = "功能性"
            if "性能" in line or "响应时间" in line:
                category = "性能"
            elif "安全" in line or "权限" in line:
                category = "安全性"
            elif "界面" in line or "UI" in line or "用户体验" in line:
                category = "界面"
            
            requirements.append(RequirementItem(
                id=f"REQ-{source}-{req_id:03d}",
                title=line[:50] + ("..." if len(line) > 50 else ""),
                description=line,
                priority=priority,
                category=category,
                source=source
            ))
            req_id += 1
    
    return requirements

def _extract_test_cases_from_file(file_path: Path) -> List[str]:
    """从测试文件中提取测试用例"""
    test_cases = []
    
    if not file_path.exists():
        return test_cases
        
    try:
        content = file_path.read_text(encoding="utf-8")
        
        # 查找curl命令
        curl_pattern = r'curl\s+.*'
        curl_matches = re.findall(curl_pattern, content, re.MULTILINE)
        test_cases.extend([f"API测试: {match[:80]}..." for match in curl_matches])
        
        # 查找测试描述
        test_patterns = [
            r'###?\s*测试用例\s*\d*[\:\s]+(.*)',
            r'###?\s*Test Case\s*\d*[\:\s]+(.*)',
            r'###?\s*用例\s*\d*[\:\s]+(.*)',
            r'-\s*测试[：:]\s*(.*)',
        ]
        
        for pattern in test_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            test_cases.extend(matches)
    
    except Exception:
        pass
        
    return test_cases

def _calculate_coverage(requirements: List[RequirementItem], test_cases: List[str]) -> List[TestCaseMatch]:
    """计算需求覆盖度"""
    matches = []
    
    for req in requirements:
        matched_tests = []
        coverage = 0.0
        gaps = []
        
        # 简单的关键词匹配算法
        req_keywords = set(re.findall(r'\w+', req.description.lower()))
        
        for test_case in test_cases:
            test_keywords = set(re.findall(r'\w+', test_case.lower()))
            
            # 计算关键词重叠度
            overlap = len(req_keywords.intersection(test_keywords))
            if overlap > 0:
                matched_tests.append(test_case)
                coverage += min(overlap / len(req_keywords), 1.0)
        
        coverage = min(coverage, 1.0)
        
        if coverage < 0.5:
            gaps.append("缺少足够的测试用例覆盖")
        if coverage == 0:
            gaps.append("完全没有相关测试用例")
            
        matches.append(TestCaseMatch(
            requirementId=req.id,
            testCases=matched_tests,
            coverage=coverage,
            gaps=gaps
        ))
    
    return matches

def _generate_task_progress_report(project_root: Path, task_key: str, include_status: bool = True, include_changes: bool = True, include_next_steps: bool = True) -> Dict[str, Any]:
    """生成任务进展报告"""
    report = {
        "taskKey": task_key,
        "timestamp": _timestamp(),
        "status": None,
        "recentChanges": [],
        "nextSteps": [],
        "processDocuments": []
    }
    
    # 1. 获取任务状态信息
    if include_status:
        try:
            task_metadata = _get_task_metadata(project_root, task_key)
            current_status = _read_task_status(project_root, task_key)
            
            report["status"] = {
                "current": current_status,
                "title": task_metadata.get("title", ""),
                "owner": task_metadata.get("owner", ""),
                "reviewers": task_metadata.get("reviewers", []),
                "updatedAt": task_metadata.get("updatedAt", ""),
                "reviews": task_metadata.get("reviews", [])[-3:]  # 最近3次审核记录
            }
        except Exception:
            report["status"] = {"current": "UNKNOWN", "error": "无法读取任务状态"}
    
    # 2. 获取最近的Git改动
    if include_changes:
        report["recentChanges"] = _get_recent_git_commits(5)
    
    # 3. 扫描过程文档状态
    try:
        process_dir = project_root / "Docs" / "ProcessDocuments" / f"task-{task_key}"
        if process_dir.exists():
            docs_info = []
            doc_names = [
                ("01-Context.md", "背景与目标"),
                ("02-Design.md", "设计方案"),
                ("03-CodePlan.md", "代码计划"),
                ("04-TestCurls.md", "测试用例"),
                ("05-MySQLVerificationPlan.md", "MySQL验证"),
                ("06-Integration.md", "集成文档"),
                ("07-JiraPublishPlan.md", "Jira发布")
            ]
            
            for doc_file, doc_title in doc_names:
                doc_path = process_dir / f"{task_key}_{doc_file}"
                if doc_path.exists():
                    try:
                        # 读取文档状态
                        post = frontmatter.load(doc_path)
                        doc_status = post.metadata.get("status", "UNKNOWN")
                        updated_at = post.metadata.get("updatedAt", "")
                        
                        docs_info.append({
                            "name": doc_title,
                            "file": doc_file,
                            "status": doc_status,
                            "updatedAt": updated_at,
                            "exists": True
                        })
                    except Exception:
                        docs_info.append({
                            "name": doc_title,
                            "file": doc_file,
                            "status": "ERROR",
                            "exists": True
                        })
                else:
                    docs_info.append({
                        "name": doc_title,
                        "file": doc_file,
                        "status": "MISSING",
                        "exists": False
                    })
            
            report["processDocuments"] = docs_info
    except Exception:
        report["processDocuments"] = []
    
    # 4. 生成下一步建议
    if include_next_steps:
        next_steps = []
        current_status = report.get("status", {}).get("current", "UNKNOWN")
        
        if current_status == "DRAFT":
            next_steps.append("完善任务文档内容，准备提交审核")
            next_steps.append("确保所有必要的过程文档已创建")
        elif current_status == "PENDING_REVIEW":
            next_steps.append("等待审核人员审核")
            next_steps.append("准备根据审核意见进行修改")
        elif current_status == "APPROVED":
            next_steps.append("开始执行开发任务")
            next_steps.append("生成测试用例和验证计划")
        elif current_status == "CHANGES_REQUESTED":
            next_steps.append("根据审核意见修改文档")
            next_steps.append("重新提交审核")
        elif current_status == "PUBLISHED":
            next_steps.append("任务已完成，进行后续维护")
            next_steps.append("收集使用反馈")
        
        # 基于文档状态添加建议
        for doc in report.get("processDocuments", []):
            if not doc["exists"]:
                next_steps.append(f"创建缺失的文档：{doc['name']}")
            elif doc["status"] == "DRAFT":
                next_steps.append(f"完善文档内容：{doc['name']}")
        
        report["nextSteps"] = next_steps[:5]  # 限制建议数量
    
    return report

def _generate_test_recommendations(requirements: List[RequirementItem], test_matches: List[TestCaseMatch]) -> List[str]:
    """生成测试用例推荐"""
    recommendations = []
    
    for req, match in zip(requirements, test_matches):
        if match.coverage < 0.8:  # 覆盖度低于80%
            # 基于需求类别生成推荐
            if req.category == "功能性":
                recommendations.append(f"为需求 {req.id} 添加功能测试：验证{req.title}")
                recommendations.append(f"为需求 {req.id} 添加边界测试：异常输入处理")
            elif req.category == "性能":
                recommendations.append(f"为需求 {req.id} 添加性能测试：响应时间验证")
                recommendations.append(f"为需求 {req.id} 添加负载测试：并发处理能力")
            elif req.category == "安全性":
                recommendations.append(f"为需求 {req.id} 添加安全测试：权限验证")
                recommendations.append(f"为需求 {req.id} 添加安全测试：输入验证")
            elif req.category == "界面":
                recommendations.append(f"为需求 {req.id} 添加UI测试：界面元素验证")
                recommendations.append(f"为需求 {req.id} 添加UX测试：用户交互流程")
    
    return recommendations[:10]  # 限制推荐数量


# ---------- Tool Stubs (no-op implementations) ----------

@app.tool()
def task_prepare_docs(input: PrepareDocsInput) -> PrepareDocsOutput:
    """准备任务主文档与分步骤文档的骨架，直接生成文档文件。"""
    project_root = _resolve_project_root(input.projectRoot)
    dirs = _ensure_dirs_for(project_root, input.taskKey)
    main_doc = dirs["tasks_dir"] / f"{input.taskKey}.md"
    process_dir = dirs["process_dir"]
    
    # 创建主任务文档
    if not main_doc.exists() or input.force:
        main_content = f"""---
status: DRAFT
taskKey: {input.taskKey}
title: {input.title}
owner: {input.owner}
reviewers: {input.reviewers}
updatedAt: {_timestamp()}
---

# 任务概述
{input.title}

# 责任人
- 负责人：{input.owner}
- 审核人：{", ".join(input.reviewers)}

# 状态机
DRAFT → PENDING_REVIEW → (APPROVED | CHANGES_REQUESTED) → PUBLISHED

# 过程文档
- 上下文：01-Context.md
- 设计：02-Design.md  
- 代码计划：03-CodePlan.md
- 测试用例：04-TestCurls.md
- MySQL验证：05-MySQLVerificationPlan.md
- 集成文档：06-Integration.md
- Jira发布：07-JiraPublishPlan.md
"""
        main_doc.write_text(main_content, encoding="utf-8")
    
    # 创建过程文档骨架
    process_docs = [
        ("01-Context.md", "背景与目标"),
        ("02-Design.md", "设计方案"),
        ("03-CodePlan.md", "代码生成计划"),
        ("04-TestCurls.md", "测试用例"),
        ("05-MySQLVerificationPlan.md", "MySQL验证计划"),
        ("06-Integration.md", "集成文档"),
        ("07-JiraPublishPlan.md", "Jira发布计划")
    ]
    
    for doc_name, doc_title in process_docs:
        doc_path = process_dir / f"{input.taskKey}_{doc_name}"
        if not doc_path.exists() or input.force:
            doc_content = f"""---
status: DRAFT
updatedAt: {_timestamp()}
---

# {doc_title}

待补充内容...
"""
            doc_path.write_text(doc_content, encoding="utf-8")
    
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
    """生成面向 AI 的代码编写计划文档，包含详细的实现指导。"""
    project_root = _resolve_project_root(input.projectRoot)
    dirs = _ensure_dirs_for(project_root, input.taskKey)
    code_doc = dirs["process_dir"] / f"{input.taskKey}_03-CodePlan.md"
    
    # 生成详细的代码计划文档
    code_content = f"""---
status: DRAFT
updatedAt: {_timestamp()}
---

# 代码生成计划（面向 AI）

## 需求描述
{input.requirements}

## 目标模块
{chr(10).join(f"- {module}" for module in input.targetModules)}

## 实现约束
{chr(10).join(f"- {constraint}" for constraint in input.constraints)}

## 验收标准
{chr(10).join(f"- {criteria}" for criteria in input.acceptanceCriteria)}

## 开发指导

### 架构要求
- 语言：Python 3.10+
- 框架：FastMCP
- 模块结构：遵循现有 devflow_mcp 包结构

### 实现步骤
1. **模型定义**：定义输入输出 Pydantic 模型
2. **工具函数**：实现核心业务逻辑
3. **文档生成**：生成实际文档内容，非仅路径
4. **状态管理**：实现状态流转和权限控制
5. **错误处理**：添加完善的异常处理

### 质量要求
- 所有函数必须有完整的文档字符串
- 输入参数必须进行验证
- 错误信息必须用户友好
- 支持相对和绝对路径

## AI 执行清单
- [ ] 补全工具实现逻辑
- [ ] 生成实际文档内容
- [ ] 添加输入验证
- [ ] 完善错误处理
- [ ] 更新状态为 PENDING_REVIEW
"""
    
    code_doc.write_text(code_content, encoding="utf-8")
    
    return CodeGenOutput(
        codePlanDoc=str(code_doc),
        codePlanDocRelative=_relpath(code_doc, project_root),
        statusHint="Document created, ready for PENDING_REVIEW",
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

    def _extract_endpoints_from_openapi(spec: Dict[str, Any]) -> tuple[List[Dict[str, Any]], Optional[str]]:
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
    """生成并执行 MySQL 验证计划（前置/断言/清理），直接返回执行结果。
    
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
        "execution_order": ["preconditions", "assertions", "cleanup"],
    }
    
    # 执行MySQL验证计划
    execution_results = []
    executed = False
    
    try:
        # 按顺序执行：前置条件 -> 断言 -> 清理
        all_statements = []
        
        # 1. 执行前置条件
        if input.preconditions:
            all_statements.extend(input.preconditions)
        
        # 2. 执行断言（转换为SQL查询）
        if input.assertions:
            for assertion in input.assertions:
                if isinstance(assertion, dict) and 'sql' in assertion:
                    all_statements.append(assertion['sql'])
                elif isinstance(assertion, str):
                    all_statements.append(assertion)
        
        # 3. 执行清理语句
        if input.cleanup:
            all_statements.extend(input.cleanup)
        
        if all_statements:
            # 直接使用内置的MySQL执行功能
            mysql_result = mysql_execute_statements(MySQLExecuteInput(
                taskKey=input.taskKey,
                statements=all_statements,
                continueOnError=True
            ))
            execution_results = mysql_result.results
            executed = True
            
    except Exception as e:
        # 如果执行失败，记录错误但继续生成文档
        execution_results = [MySQLStatementResult(
            sql="EXECUTION_ERROR",
            success=False,
            error=str(e)
        )]
    
    # 生成验证计划文档
    doc_content = f"""---
status: {"EXECUTED" if executed else "DRAFT"}
updatedAt: {_timestamp()}
executed: {executed}
---

# MySQL 验证计划

## 验证目标
验证任务 {input.taskKey} 的数据库相关功能

## 涉及表
{chr(10).join(f"- {table}" for table in input.tables)}

## 执行计划

### 1. 前置条件
```sql
{chr(10).join(input.preconditions)}
```

### 2. 断言检查
{chr(10).join(f"- {assertion.get('description', str(assertion)) if isinstance(assertion, dict) else assertion}" for assertion in input.assertions)}

### 3. 清理操作
```sql
{chr(10).join(input.cleanup)}
```

## 执行结果
{'✅ 已执行' if executed else '❌ 未执行'}

{chr(10).join(f"**{i+1}.** {result.sql} - {'✅ 成功' if result.success else '❌ 失败: ' + (result.error or '')}" for i, result in enumerate(execution_results)) if execution_results else '无执行记录'}
"""
    
    doc_path.write_text(doc_content, encoding="utf-8")
    
    return MySQLPlanOutput(
        verificationPlanDoc=str(doc_path),
        verificationPlanDocRelative=_relpath(doc_path, project_root),
        sqlPlan=plan,
        executionResults=execution_results,
        executed=executed
    )


@app.tool()
def docs_generate_integration(input: IntegrationDocInput) -> IntegrationDocOutput:
    """生成完整的集成对接文档，包含概览、鉴权、接口、Schema、错误码和样例。
    
    ⚠️ 前置条件：任务状态必须 >= APPROVED。
    👤 AI 提醒：调用前请先确认任务的状态是否已通过人工审核(APPROVED)。
    如当前状态不满足，请主动与用户确认是否需要先进行状态流转。
    """
    project_root = _resolve_project_root(input.projectRoot)
    # 门禁：要求 APPROVED
    _require_min_status(project_root, input.taskKey, "APPROVED")
    dirs = _ensure_dirs_for(project_root, input.taskKey)
    doc_path = dirs["process_dir"] / f"{input.taskKey}_06-Integration.md"
    
    # 生成完整的集成文档内容
    doc_content = f"""---
status: DRAFT
updatedAt: {_timestamp()}
audience: {input.audience}
---

# 集成对接文档 - {input.taskKey}

## 1. 概览 (Overview)

### 系统简介
任务 {input.taskKey} 的系统集成文档，面向 {input.audience} 用户。

### 涉及系统
{chr(10).join(f"- {system}" for system in input.systems)}

## 2. 鉴权 (Authentication)

### 鉴权方式
- **类型**: Bearer Token / API Key
- **请求头**: `Authorization: Bearer <token>`
- **获取方式**: 联系系统管理员

### 示例
```bash
curl -H "Authorization: Bearer your-api-token" \\
     https://api.example.com/endpoint
```

## 3. 接口 (Endpoints)

{chr(10).join(f'''### {interface.get("name", "Unknown")}
**方法**: {interface.get("method", "GET")}  
**路径**: {interface.get("path", "/")}  
**描述**: {interface.get("description", "暂无描述")}

**请求示例**:
```json
{{"example": "request"}}
```

**响应示例**:
```json
{{"status": "success", "data": {{}}}}
```
''' for interface in input.interfaces)}

## 4. 数据结构 (Schemas)

### 通用响应格式
```json
{{
  "status": "success|error",
  "message": "操作结果描述",
  "data": {{}},
  "timestamp": "2024-01-01T00:00:00Z"
}}
```

### 业务数据结构
```json
{{
  "id": "string",
  "name": "string", 
  "status": "active|inactive",
  "createdAt": "2024-01-01T00:00:00Z",
  "updatedAt": "2024-01-01T00:00:00Z"
}}
```

## 5. 错误码 (Error Codes)

| 错误码 | 描述 | 解决方案 |
|--------|------|----------|
| 400 | 请求参数错误 | 检查请求参数格式和必填字段 |
| 401 | 未授权 | 检查 API Token 是否正确 |
| 403 | 禁止访问 | 检查账号权限 |
| 404 | 资源不存在 | 检查请求的资源ID是否正确 |
| 500 | 服务器内部错误 | 联系技术支持 |

## 6. 集成样例 (Samples)

### Python 示例
```python
import requests

def call_api(endpoint, data=None):
    headers = {{
        'Authorization': 'Bearer your-api-token',
        'Content-Type': 'application/json'
    }}
    
    response = requests.post(
        f'https://api.example.com{{endpoint}}',
        headers=headers,
        json=data
    )
    
    return response.json()

# 使用示例
result = call_api('/api/v1/resource', {{'name': 'test'}})
print(result)
```

### curl 示例
```bash
# GET 请求
curl -H "Authorization: Bearer your-api-token" \\
     https://api.example.com/api/v1/resource

# POST 请求  
curl -X POST \\
     -H "Authorization: Bearer your-api-token" \\
     -H "Content-Type: application/json" \\
     -d '{{"name": "test"}}' \\
     https://api.example.com/api/v1/resource
```

## 7. 技术支持

### 联系方式
- **技术支持**: tech-support@example.com
- **文档问题**: docs@example.com
- **紧急联系**: emergency@example.com

### 更新日志
- {_timestamp()[:10]}: 初始版本创建

## 8. 补充说明
{input.notes or "暂无补充说明"}
"""
    
    doc_path.write_text(doc_content, encoding="utf-8")
    toc = ["Overview", "Authentication", "Endpoints", "Schemas", "Error Codes", "Samples", "Support", "Notes"]
    
    return IntegrationDocOutput(
        integrationDoc=str(doc_path), 
        integrationDocRelative=_relpath(doc_path, project_root), 
        toc=toc
    )


@app.tool()
def jira_publish_integration_doc(input: JiraPublishInput) -> JiraPublishOutput:
    """直接创建 Jira 工单并上传附件，返回完整的执行结果。
    
    ⚠️ 前置条件：任务状态必须 >= APPROVED 且相关文档已生成。
    👤 AI 提醒：调用前请先确认：
    1. 任务的状态是否已通过人工审核(APPROVED)
    2. 对接文档等附件是否已生成完成
    如条件不满足，请主动与用户确认后续步骤。
    
    🔄 自动检测：支持从当前Git分支自动检测项目Key和相关ticket信息
    """
    project_root = _resolve_project_root(input.projectRoot)
    # 门禁：要求所有检查通过且状态 APPROVED
    _require_min_status(project_root, input.taskKey, "APPROVED")
    dirs = _ensure_dirs_for(project_root, input.taskKey)
    doc_path = dirs["process_dir"] / f"{input.taskKey}_07-JiraPublishPlan.md"
    
    # 自动检测Git分支信息
    git_context = _auto_detect_jira_context()
    detected_project_key = input.projectKey
    
    if input.autoDetectFromBranch and not detected_project_key:
        detected_project_key = git_context.get("project_key")
        if not detected_project_key:
            raise ValueError(f"无法从当前分支 '{git_context.get('branch_name', 'unknown')}' 自动检测项目Key，请手动指定 projectKey 参数")
    
    if not detected_project_key:
        raise ValueError("必须指定 projectKey 或启用 autoDetectFromBranch 自动检测")
    
    payload = {
        "fields": {
            "project": {"key": detected_project_key},
            "issuetype": {"name": input.issueType},
            "summary": input.summary,
            "description": input.description,
            "labels": input.labels,
        },
        "attachments": input.attachments,
        "links": input.links,
        "git_context": git_context,  # 记录检测到的Git上下文
    }
    
    # 直接执行Jira工单创建
    created_issue = None
    attachment_results = None
    executed = False
    
    try:
        # 1. 创建Jira工单
        created_issue = jira_create_issue(JiraCreateIssueInput(
            projectKey=detected_project_key,
            issueType=input.issueType,
            summary=input.summary,
            description=input.description,
            labels=input.labels,
            fields={}
        ))
        
        if created_issue and created_issue.issueKey:
            executed = True
            
            # 2. 上传附件（如果有）
            if input.attachments:
                attachment_results = jira_attach_files(JiraAttachFilesInput(
                    issueKey=created_issue.issueKey,
                    filePaths=input.attachments
                ))
            
            # 3. 关联工单（如果有）
            if input.links:
                for link in input.links:
                    if isinstance(link, dict) and 'issueKey' in link and 'linkType' in link:
                        jira_link_issues(JiraLinkIssuesInput(
                            inwardIssue=created_issue.issueKey,
                            outwardIssue=link['issueKey'],
                            linkType=link.get('linkType', 'relates to')
                        ))
                        
    except Exception as e:
        # 如果执行失败，记录错误但继续生成文档
        executed = False
        created_issue = JiraCreateIssueOutput(
            issueKey=None,
            url=None,
            hint=f"Failed to create issue: {str(e)}"
        )
    
    # 生成执行计划文档
    doc_content = f"""---
status: {"PUBLISHED" if executed else "DRAFT"}
updatedAt: {_timestamp()}
executed: {executed}
---

# Jira 发布计划 - {input.taskKey}

## 执行状态
{'✅ 已执行' if executed else '❌ 执行失败'}

## 工单信息
- **项目**: {detected_project_key}
- **类型**: {input.issueType}  
- **标题**: {input.summary}
- **创建结果**: {'成功 - ' + (created_issue.issueKey or 'N/A') if created_issue and created_issue.issueKey else '失败'}
- **工单链接**: {created_issue.url if created_issue and created_issue.url else '无'}

## Git上下文信息
- **当前分支**: {git_context.get('branch_name', 'unknown')}
- **检测到的Ticket**: {git_context.get('ticket_key', '无')}
- **自动检测项目Key**: {git_context.get('project_key', '无')}
- **检测模式**: {'启用' if input.autoDetectFromBranch else '禁用'}

## 附件上传
{f'- 成功: {len(attachment_results.attached if attachment_results else [])} 个文件' if attachment_results else '- 无附件'}
{f'- 失败: {len(attachment_results.failed if attachment_results else [])} 个文件' if attachment_results else ''}

## 原始 Payload
```json
{json.dumps(payload, indent=2, ensure_ascii=False)}
```

## 执行日志
- 工单创建: {'✅' if created_issue and created_issue.issueKey else '❌'}
- 附件上传: {'✅' if attachment_results and not attachment_results.failed else '❌' if attachment_results else 'N/A'}
- 工单关联: {'✅' if input.links else 'N/A'}

## 后续步骤
{f'1. 访问工单: {created_issue.url}' if created_issue and created_issue.url else '1. 工单创建失败，请检查配置'}
2. 通知相关人员
3. 跟踪工单进度
"""
    
    doc_path.write_text(doc_content, encoding="utf-8")
    
    return JiraPublishOutput(
        jiraPlanDoc=str(doc_path),
        jiraPlanDocRelative=_relpath(doc_path, project_root),
        jiraPayload=payload,
        createdIssue=created_issue,
        attachmentResults=attachment_results,
        executed=executed
    )


@app.tool()
def review_set_status(input: ReviewStatusInput) -> ReviewStatusOutput:
    """切换主任务文档状态，包含状态转换路径验证和历史记录。
    
    ⚠️ 状态验证：
    1. 验证状态转换路径是否合法
    2. 记录状态变更历史和原因
    3. 支持事务性状态更新
    
    👤 AI 提醒：状态流转通常需要人工审核决策。建议调用前：
    1. 向用户说明当前状态和拟变更的目标状态
    2. 确认变更原因和后续影响
    3. 获得用户明确同意后再执行状态切换
    """
    project_root = _resolve_project_root(input.projectRoot)
    dirs = _ensure_dirs_for(project_root, None)
    main_doc = dirs["tasks_dir"] / f"{input.taskKey}.md"

    # 获取当前状态
    old_status = _read_task_status(project_root, input.taskKey)
    
    # 1. 验证状态转换是否合法
    if not _validate_status_transition(old_status, input.newStatus):
        valid_transitions = _STATUS_TRANSITIONS.get(old_status, [])
        raise StatusValidationError(
            f"非法状态转换: {old_status} -> {input.newStatus}. "
            f"允许的转换: {valid_transitions}"
        )

    # 2. 验证必需的原因说明（对某些关键转换）
    critical_transitions = [
        ("PENDING_REVIEW", "CHANGES_REQUESTED"),
        ("APPROVED", "CHANGES_REQUESTED"), 
        ("APPROVED", "PUBLISHED")
    ]
    if (old_status, input.newStatus) in critical_transitions and not input.notes:
        raise StatusValidationError(
            f"关键状态转换 {old_status} -> {input.newStatus} 必须提供原因说明"
        )

    # 读取或创建 Front Matter
    if main_doc.exists():
        post = frontmatter.load(main_doc)
    else:
        post = frontmatter.Post("")

    metadata = dict(post.metadata or {})
    
    # 3. 更新状态和时间戳
    metadata["status"] = input.newStatus
    metadata["updatedAt"] = _timestamp()
    
    # 4. 记录状态变更历史
    reviews = list(metadata.get("reviews", []))
    review_entry = {
        "by": input.by,
        "from": old_status,
        "to": input.newStatus,
        "notes": input.notes or "",
        "time": _timestamp(),
        "valid": True  # 标记为经过验证的转换
    }
    reviews.append(review_entry)
    metadata["reviews"] = reviews
    
    # 5. 更新统计信息
    stats = metadata.get("statusStats", {})
    stats[input.newStatus] = stats.get(input.newStatus, 0) + 1
    stats["totalTransitions"] = stats.get("totalTransitions", 0) + 1
    metadata["statusStats"] = stats
    
    post.metadata = metadata

    # 6. 落盘保存（包含事务性检查）
    try:
        main_doc.parent.mkdir(parents=True, exist_ok=True)
        content_str = frontmatter.dumps(post)
        main_doc.write_text(content_str, encoding="utf-8")
        
        # 验证写入成功
        if _read_task_status(project_root, input.taskKey) != input.newStatus:
            raise StatusValidationError("状态更新失败，文件写入异常")
            
    except Exception as e:
        raise StatusValidationError(f"状态更新失败: {str(e)}")

    return ReviewStatusOutput(taskKey=input.taskKey, oldStatus=old_status, newStatus=input.newStatus)


@app.tool()
def review_validate_checklist(input: ReviewChecklistInput) -> ReviewChecklistOutput:
    """执行一致性校验（文档存在性、状态门禁、配置完整性等），返回通过与失败项。"""
    failed: List[Dict[str, str]] = []
    project_root = PROJECT_ROOT
    
    # 可用的检查项
    available_checks = {
        "task_doc_exists": "检查主任务文档是否存在",
        "process_docs_exist": "检查过程文档是否存在", 
        "status_valid": "检查任务状态是否有效",
        "front_matter_valid": "检查 Front Matter 格式",
        "mysql_config": "检查 MySQL 配置",
        "jira_config": "检查 Jira 配置",
        "file_permissions": "检查文件权限",
        "directory_structure": "检查目录结构"
    }
    
    for check_id in input.checks:
        if check_id not in available_checks:
            failed.append({
                "check": check_id,
                "reason": f"未知的检查项: {check_id}"
            })
            continue
            
        try:
            if check_id == "task_doc_exists":
                main_doc = project_root / "Docs" / ".tasks" / f"{input.taskKey}.md"
                if not main_doc.exists():
                    failed.append({
                        "check": check_id,
                        "reason": f"主任务文档不存在: {main_doc}"
                    })
                    
            elif check_id == "process_docs_exist":
                process_dir = project_root / "Docs" / "ProcessDocuments" / f"task-{input.taskKey}"
                if not process_dir.exists():
                    failed.append({
                        "check": check_id,
                        "reason": f"过程文档目录不存在: {process_dir}"
                    })
                else:
                    required_docs = [
                        "01-Context.md", "02-Design.md", "03-CodePlan.md",
                        "04-TestCurls.md", "05-MySQLVerificationPlan.md", 
                        "06-Integration.md", "07-JiraPublishPlan.md"
                    ]
                    for doc in required_docs:
                        doc_path = process_dir / f"{input.taskKey}_{doc}"
                        if not doc_path.exists():
                            failed.append({
                                "check": check_id,
                                "reason": f"缺失过程文档: {doc_path.name}"
                            })
                            
            elif check_id == "status_valid":
                try:
                    current_status = _read_task_status(project_root, input.taskKey)
                    valid_statuses = ["DRAFT", "PENDING_REVIEW", "APPROVED", "CHANGES_REQUESTED", "PUBLISHED"]
                    if current_status not in valid_statuses:
                        failed.append({
                            "check": check_id,
                            "reason": f"无效状态: {current_status}"
                        })
                except Exception as e:
                    failed.append({
                        "check": check_id,
                        "reason": f"无法读取状态: {str(e)}"
                    })
                    
            elif check_id == "front_matter_valid":
                main_doc = project_root / "Docs" / ".tasks" / f"{input.taskKey}.md"
                if main_doc.exists():
                    try:
                        post = frontmatter.load(main_doc)
                        required_fields = ["status", "taskKey", "title", "owner"]
                        for field in required_fields:
                            if field not in post.metadata:
                                failed.append({
                                    "check": check_id,
                                    "reason": f"缺失 Front Matter 字段: {field}"
                                })
                    except Exception as e:
                        failed.append({
                            "check": check_id,
                            "reason": f"Front Matter 格式错误: {str(e)}"
                        })
                        
            elif check_id == "mysql_config":
                required_env = ["MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DB"]
                missing_env = [env for env in required_env if not os.getenv(env)]
                if missing_env:
                    failed.append({
                        "check": check_id,
                        "reason": f"缺失 MySQL 环境变量: {', '.join(missing_env)}"
                    })
                    
            elif check_id == "jira_config":
                base_url = os.getenv("JIRA_BASE_URL")
                user = os.getenv("JIRA_USER")
                password = os.getenv("JIRA_USER_PASSWORD")
                bearer = os.getenv("JIRA_BEARER_TOKEN")
                token = os.getenv("JIRA_API_TOKEN")
                
                if not base_url:
                    failed.append({
                        "check": check_id,
                        "reason": "缺失 JIRA_BASE_URL 环境变量"
                    })
                    
                if not (user and password) and not bearer and not (user and token):
                    failed.append({
                        "check": check_id,
                        "reason": "缺失 Jira 认证配置（需要用户名密码、Bearer Token 或 API Token）"
                    })
                    
            elif check_id == "directory_structure":
                required_dirs = [
                    project_root / "Docs",
                    project_root / "Docs" / ".tasks",
                    project_root / "Docs" / "ProcessDocuments"
                ]
                for dir_path in required_dirs:
                    if not dir_path.exists():
                        failed.append({
                            "check": check_id,
                            "reason": f"目录不存在: {dir_path}"
                        })
                        
            elif check_id == "file_permissions":
                docs_dir = project_root / "Docs"
                if docs_dir.exists() and not os.access(docs_dir, os.W_OK):
                    failed.append({
                        "check": check_id,
                        "reason": f"没有写权限: {docs_dir}"
                    })
                    
        except Exception as e:
            failed.append({
                "check": check_id,
                "reason": f"检查执行异常: {str(e)}"
            })
    
    return ReviewChecklistOutput(passed=len(failed) == 0, failedItems=failed)


# ---------- External MCP Features (Integrated Implementations) ----------

# MySQL MCP parity: execute SQL statements sequentially
class MySQLExecuteInput(BaseModel):
    """直接执行 SQL 语句的输入参数"""
    model_config = ConfigDict(title="MySQLExecuteInput", description="直接执行 SQL 语句的输入参数")
    taskKey: Optional[str] = Field(None, description="任务唯一标识（可选，用于审计）")
    statements: List[str] = Field(..., description="要顺序执行的 SQL 列表")
    continueOnError: bool = Field(False, description="遇到错误是否继续执行后续语句")


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
    projectKey: Optional[str] = Field(None, description="Jira 项目 Key（可选，为空时自动从Git分支解析）")
    issueType: str = Field(..., description="工单类型，如 Task/Story/Documentation")
    summary: str = Field(..., description="工单标题")
    description: str = Field(..., description="工单描述")
    labels: List[str] = Field(default_factory=list, description="标签列表（可选）")
    fields: Dict[str, Any] = Field(default_factory=dict, description="额外自定义字段（可选）")
    autoDetectFromBranch: bool = Field(True, description="是否自动从Git分支检测项目信息（默认启用）")


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
    """在 Jira 中创建工单（REST v3，支持自定义字段）。认证优先 JIRA_USER/JIRA_USER_PASSWORD。支持从Git分支自动检测项目Key。"""
    try:
        # 自动检测Git分支信息
        detected_project_key = input.projectKey
        if input.autoDetectFromBranch and not detected_project_key:
            git_context = _auto_detect_jira_context()
            detected_project_key = git_context.get("project_key")
            if not detected_project_key:
                return JiraCreateIssueOutput(
                    issueKey=None, 
                    url=None, 
                    hint=f"无法从当前分支 '{git_context.get('branch_name', 'unknown')}' 自动检测项目Key，请手动指定 projectKey 参数"
                )
        
        if not detected_project_key:
            return JiraCreateIssueOutput(
                issueKey=None, 
                url=None, 
                hint="必须指定 projectKey 或启用 autoDetectFromBranch 自动检测"
            )
        
        session = _get_jira_session()
        payload = {"fields": {"project": {"key": detected_project_key}, "issuetype": {"name": input.issueType}, "summary": input.summary, "description": input.description, "labels": input.labels}}
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
        return JiraCreateIssueOutput(issueKey=issue_key, url=issue_url, hint=f"Created via Jira REST API (project: {detected_project_key})")
    except Exception as exc:  # pragma: no cover
        return JiraCreateIssueOutput(issueKey=None, url=None, hint=f"Jira error: {exc}")


class JiraAttachFilesInput(BaseModel):
    """Jira 上传附件的输入参数"""
    model_config = ConfigDict(title="JiraAttachFilesInput", description="Jira 上传附件的输入参数")
    issueKey: str = Field(..., description="目标工单 Key")
    filePaths: List[str] = Field(..., description="要上传的文件路径列表")


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


class JiraAddCommentInput(BaseModel):
    """Jira 添加评论的输入参数"""
    model_config = ConfigDict(title="JiraAddCommentInput", description="Jira 添加评论的输入参数")
    issueKey: str = Field(..., description="目标工单 Key")
    comment: str = Field(..., description="评论内容，支持 Jira 标记语法")
    visibility: Optional[str] = Field(None, description="评论可见性：public/internal 或指定用户组")
    mentionUsers: List[str] = Field(default_factory=list, description="要@提及的用户列表（用户名或邮箱）")


class JiraAddCommentOutput(BaseModel):
    commentId: Optional[str] = None
    url: Optional[str] = None
    hint: str


class JiraUpdateStatusInput(BaseModel):
    """Jira 更新状态的输入参数"""
    model_config = ConfigDict(title="JiraUpdateStatusInput", description="Jira 更新状态的输入参数")
    issueKey: str = Field(..., description="目标工单 Key")
    newStatus: str = Field(..., description="新状态名称")
    transitionComment: Optional[str] = Field(None, description="状态转换时添加的评论")
    validateTransition: bool = Field(True, description="是否验证状态转换的合法性")
    fields: Dict[str, Any] = Field(default_factory=dict, description="状态转换时需要更新的字段")


class JiraUpdateStatusOutput(BaseModel):
    success: bool
    oldStatus: Optional[str] = None
    newStatus: Optional[str] = None
    transitionId: Optional[str] = None
    hint: str


class JiraBatchUpdateInput(BaseModel):
    """Jira 批量状态更新的输入参数"""
    model_config = ConfigDict(title="JiraBatchUpdateInput", description="Jira 批量状态更新的输入参数")
    updates: List[Dict[str, Any]] = Field(..., description="批量更新操作列表，每项包含 issueKey, newStatus 等")
    continueOnError: bool = Field(True, description="遇到错误时是否继续执行后续操作")
    addComment: bool = Field(True, description="是否为每个状态转换添加评论")


class JiraBatchUpdateOutput(BaseModel):
    successful: List[Dict[str, Any]]
    failed: List[Dict[str, Any]]
    summary: Dict[str, int]


class JiraMarkProgressInput(BaseModel):
    """Jira 进展标记的输入参数"""
    model_config = ConfigDict(title="JiraMarkProgressInput", description="Jira 进展标记的输入参数")
    taskKey: str = Field(..., description="DevFlow 任务唯一标识")
    jiraIssueKey: Optional[str] = Field(None, description="关联的 Jira 工单 Key，为空时自动从Git分支检测")
    markType: str = Field("progress", description="标记类型：progress/milestone/completion/issue/solution")
    title: str = Field(..., description="进展标记的标题")
    description: Optional[str] = Field(None, description="详细描述（可选）")
    includeTaskStatus: bool = Field(True, description="是否包含当前任务状态信息")
    includeChanges: bool = Field(True, description="是否包含最近的改动信息")
    includeNextSteps: bool = Field(True, description="是否包含下一步计划")
    mentionUsers: List[str] = Field(default_factory=list, description="要@提及的用户列表")
    visibility: Optional[str] = Field("public", description="评论可见性：public/internal")
    autoDetectFromBranch: bool = Field(True, description="是否自动从Git分支检测Jira信息")


class JiraMarkProgressOutput(BaseModel):
    taskKey: str
    jiraIssueKey: Optional[str] = None
    commentId: Optional[str] = None
    commentUrl: Optional[str] = None
    markContent: str
    timestamp: str
    success: bool
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


@app.tool()
def jira_add_comment(input: JiraAddCommentInput) -> JiraAddCommentOutput:
    """向 Jira 工单添加评论，支持富文本、用户提及和可见性控制。"""
    try:
        session = _get_jira_session()
        url = _jira_api_url(f"issue/{input.issueKey}/comment")
        
        # 构建评论内容，处理用户提及
        comment_text = input.comment
        if input.mentionUsers:
            mention_text = " ".join([f"[~{user}]" for user in input.mentionUsers])
            comment_text = f"{mention_text}\n\n{comment_text}"
        
        # 构建请求 payload
        payload = {
            "body": comment_text
        }
        
        # 处理可见性设置
        if input.visibility and input.visibility != "public":
            if input.visibility == "internal":
                # 内部可见性，通常限制给开发团队
                payload["visibility"] = {
                    "type": "role",
                    "value": "Developers"
                }
            else:
                # 指定用户组可见
                payload["visibility"] = {
                    "type": "group", 
                    "value": input.visibility
                }
        
        resp = session.post(url, json=payload, timeout=30)
        if resp.status_code >= 400:
            return JiraAddCommentOutput(
                commentId=None, 
                url=None, 
                hint=f"Failed to add comment: {resp.status_code} {resp.text}"
            )
        
        comment_data = resp.json()
        comment_id = comment_data.get("id")
        
        # 构建评论链接
        base_url = os.getenv("JIRA_BASE_URL", "").rstrip("/")
        comment_url = f"{base_url}/browse/{input.issueKey}?focusedCommentId={comment_id}" if comment_id else None
        
        return JiraAddCommentOutput(
            commentId=comment_id,
            url=comment_url,
            hint=f"Comment added successfully to {input.issueKey}"
        )
        
    except Exception as exc:  # pragma: no cover
        return JiraAddCommentOutput(
            commentId=None, 
            url=None, 
            hint=f"Error adding comment: {exc}"
        )


@app.tool()
def jira_update_status(input: JiraUpdateStatusInput) -> JiraUpdateStatusOutput:
    """更新 Jira 工单状态，支持状态转换验证和评论添加。"""
    try:
        session = _get_jira_session()
        
        # 1. 获取当前工单状态
        issue_url = _jira_api_url(f"issue/{input.issueKey}")
        issue_resp = session.get(issue_url)
        if issue_resp.status_code >= 400:
            return JiraUpdateStatusOutput(
                success=False,
                hint=f"Failed to fetch issue {input.issueKey}: {issue_resp.status_code}"
            )
        
        issue_data = issue_resp.json()
        current_status = issue_data.get("fields", {}).get("status", {}).get("name", "")
        
        # 2. 获取可用的状态转换
        transitions_url = _jira_api_url(f"issue/{input.issueKey}/transitions")
        trans_resp = session.get(transitions_url)
        if trans_resp.status_code >= 400:
            return JiraUpdateStatusOutput(
                success=False,
                oldStatus=current_status,
                hint=f"Failed to get transitions: {trans_resp.status_code}"
            )
        
        transitions_data = trans_resp.json()
        transitions = transitions_data.get("transitions", [])
        
        # 3. 查找目标状态的转换ID
        target_transition = None
        for transition in transitions:
            if transition.get("to", {}).get("name", "").lower() == input.newStatus.lower():
                target_transition = transition
                break
        
        if not target_transition:
            available_statuses = [t.get("to", {}).get("name", "") for t in transitions]
            return JiraUpdateStatusOutput(
                success=False,
                oldStatus=current_status,
                hint=f"Status '{input.newStatus}' not available. Available: {available_statuses}"
            )
        
        # 4. 执行状态转换
        transition_id = target_transition.get("id")
        transition_payload = {
            "transition": {"id": transition_id}
        }
        
        # 添加转换评论
        if input.transitionComment:
            transition_payload["update"] = {
                "comment": [{"add": {"body": input.transitionComment}}]
            }
        
        # 添加需要更新的字段
        if input.fields:
            if "fields" not in transition_payload:
                transition_payload["fields"] = {}
            transition_payload["fields"].update(input.fields)
        
        # 执行转换
        transition_resp = session.post(transitions_url, json=transition_payload, timeout=30)
        if transition_resp.status_code >= 400:
            return JiraUpdateStatusOutput(
                success=False,
                oldStatus=current_status,
                transitionId=transition_id,
                hint=f"Status transition failed: {transition_resp.status_code} {transition_resp.text}"
            )
        
        return JiraUpdateStatusOutput(
            success=True,
            oldStatus=current_status,
            newStatus=input.newStatus,
            transitionId=transition_id,
            hint=f"Status updated from '{current_status}' to '{input.newStatus}'"
        )
        
    except Exception as exc:  # pragma: no cover
        return JiraUpdateStatusOutput(
            success=False,
            hint=f"Error updating status: {exc}"
        )


@app.tool()
def jira_batch_update_status(input: JiraBatchUpdateInput) -> JiraBatchUpdateOutput:
    """批量更新多个 Jira 工单的状态。"""
    successful = []
    failed = []
    
    for i, update_item in enumerate(input.updates):
        try:
            # 验证必要参数
            issue_key = update_item.get("issueKey")
            new_status = update_item.get("newStatus")
            
            if not issue_key or not new_status:
                failed.append({
                    "index": i,
                    "issueKey": issue_key or "unknown",
                    "error": "Missing issueKey or newStatus"
                })
                continue
            
            # 构建状态更新请求
            status_input = JiraUpdateStatusInput(
                issueKey=issue_key,
                newStatus=new_status,
                transitionComment=update_item.get("comment", f"Batch status update to {new_status}" if input.addComment else None),
                validateTransition=update_item.get("validateTransition", True),
                fields=update_item.get("fields", {})
            )
            
            # 执行状态更新
            result = jira_update_status(status_input)
            
            if result.success:
                successful.append({
                    "index": i,
                    "issueKey": issue_key,
                    "oldStatus": result.oldStatus,
                    "newStatus": result.newStatus,
                    "transitionId": result.transitionId
                })
            else:
                failed.append({
                    "index": i,
                    "issueKey": issue_key,
                    "error": result.hint
                })
                
        except Exception as e:
            failed.append({
                "index": i,
                "issueKey": update_item.get("issueKey", "unknown"),
                "error": str(e)
            })
            
            if not input.continueOnError:
                break
    
    summary = {
        "total": len(input.updates),
        "successful": len(successful),
        "failed": len(failed)
    }
    
    return JiraBatchUpdateOutput(
        successful=successful,
        failed=failed,
        summary=summary
    )


@app.tool()
def jira_mark_progress(input: JiraMarkProgressInput) -> JiraMarkProgressOutput:
    """标记任务进展到 Jira，自动生成包含任务状态、改动和下一步计划的评论。
    
    这个功能专门为 AI 设计，用于自动化地将开发进展、状态变更、功能实现等信息
    以结构化的方式记录到 Jira 工单中，提供完整的项目追踪和沟通记录。
    """
    project_root = _resolve_project_root(None)
    timestamp = _timestamp()
    
    try:
        # 1. 自动检测 Jira 工单（如果未指定）
        jira_issue_key = input.jiraIssueKey
        if input.autoDetectFromBranch and not jira_issue_key:
            git_context = _auto_detect_jira_context()
            jira_issue_key = git_context.get("ticket_key")
            
            if not jira_issue_key:
                return JiraMarkProgressOutput(
                    taskKey=input.taskKey,
                    jiraIssueKey=None,
                    commentId=None,
                    commentUrl=None,
                    markContent="",
                    timestamp=timestamp,
                    success=False,
                    hint=f"无法自动检测 Jira 工单，当前分支：{git_context.get('branch_name', 'unknown')}"
                )
        
        if not jira_issue_key:
            return JiraMarkProgressOutput(
                taskKey=input.taskKey,
                jiraIssueKey=None,
                commentId=None,
                commentUrl=None,
                markContent="",
                timestamp=timestamp,
                success=False,
                hint="必须指定 jiraIssueKey 或启用 autoDetectFromBranch"
            )
        
        # 2. 生成任务进展报告
        progress_report = _generate_task_progress_report(
            project_root, 
            input.taskKey, 
            input.includeTaskStatus, 
            input.includeChanges, 
            input.includeNextSteps
        )
        
        # 3. 根据markType构建评论内容
        mark_icons = {
            "progress": "🔄",
            "milestone": "🎯", 
            "completion": "✅",
            "issue": "⚠️",
            "solution": "💡"
        }
        
        icon = mark_icons.get(input.markType, "📝")
        
        # 构建评论内容（使用普通文本格式）
        comment_lines = [
            f"{icon} {input.title}",
            f"标记时间: {timestamp}",
            f"标记类型: {input.markType}",
            ""
        ]
        
        # 添加描述
        if input.description:
            comment_lines.extend([
                "详细说明:",
                input.description,
                ""
            ])
        
        # 添加任务状态信息
        if input.includeTaskStatus and progress_report.get("status"):
            status_info = progress_report["status"]
            comment_lines.extend([
                "📊 任务状态:",
                f"当前状态: {status_info.get('current', 'UNKNOWN')}",
                f"任务标题: {status_info.get('title', 'N/A')}",
                f"负责人: {status_info.get('owner', 'N/A')}",
                f"最后更新: {status_info.get('updatedAt', 'N/A')}",
                ""
            ])
            
            # 添加最近的审核记录
            reviews = status_info.get("reviews", [])
            if reviews:
                comment_lines.append("最近审核记录:")
                for review in reviews[-2:]:  # 最近2次
                    # 安全处理时间字段，可能是datetime对象或字符串
                    review_time = review.get('time', '')
                    if hasattr(review_time, 'strftime'):
                        # 如果是datetime对象，转换为字符串
                        time_str = review_time.strftime('%Y-%m-%d')
                    elif isinstance(review_time, str):
                        # 如果是字符串，取前10个字符
                        time_str = review_time[:10]
                    else:
                        time_str = str(review_time)[:10] if review_time else 'N/A'
                    
                    comment_lines.append(f"  {review.get('from', '')} -> {review.get('to', '')} by {review.get('by', '')} ({time_str})")
                comment_lines.append("")
        
        # 添加过程文档状态
        if input.includeTaskStatus and progress_report.get("processDocuments"):
            comment_lines.extend([
                "📋 文档状态:",
                ""
            ])
            
            for doc in progress_report["processDocuments"]:
                status_emoji = {
                    "DRAFT": "📝",
                    "APPROVED": "✅", 
                    "COMPLETED": "✅",
                    "MISSING": "❌",
                    "ERROR": "⚠️"
                }.get(doc["status"], "❓")
                
                # 安全处理更新时间字段
                updated_at = doc.get("updatedAt", "")
                if hasattr(updated_at, 'strftime'):
                    # 如果是datetime对象，转换为字符串
                    updated_time = updated_at.strftime('%Y-%m-%d')
                elif isinstance(updated_at, str):
                    # 如果是字符串，取前10个字符
                    updated_time = updated_at[:10] if updated_at else "N/A"
                else:
                    updated_time = str(updated_at)[:10] if updated_at else "N/A"
                comment_lines.append(f"  {doc['name']}: {status_emoji} {doc['status']} ({updated_time})")
            
            comment_lines.append("")
        
        # 添加最近改动
        if input.includeChanges and progress_report.get("recentChanges"):
            comment_lines.extend([
                "🔧 最近改动:",
            ])
            
            for commit in progress_report["recentChanges"][:3]:  # 最近3个提交
                comment_lines.append(f"  {commit['hash']} {commit['message']} - {commit['author']} ({commit['time']})")
            
            comment_lines.append("")
        
        # 添加下一步计划
        if input.includeNextSteps and progress_report.get("nextSteps"):
            comment_lines.extend([
                "🎯 下一步计划:",
            ])
            
            for i, step in enumerate(progress_report["nextSteps"], 1):
                comment_lines.append(f"{i}. {step}")
            
            comment_lines.append("")
        
        # 添加时间戳和签名
        comment_lines.extend([
            "---",
            f"自动生成于 {timestamp} by DevFlow MCP"
        ])
        
        comment_content = "\n".join(comment_lines)
        
        # 4. 添加评论到 Jira
        comment_input = JiraAddCommentInput(
            issueKey=jira_issue_key,
            comment=comment_content,
            visibility=input.visibility,
            mentionUsers=input.mentionUsers
        )
        
        comment_result = jira_add_comment(comment_input)
        
        return JiraMarkProgressOutput(
            taskKey=input.taskKey,
            jiraIssueKey=jira_issue_key,
            commentId=comment_result.commentId,
            commentUrl=comment_result.url,
            markContent=comment_content,
            timestamp=timestamp,
            success=comment_result.commentId is not None,
            hint=comment_result.hint
        )
        
    except Exception as e:
        return JiraMarkProgressOutput(
            taskKey=input.taskKey,
            jiraIssueKey=jira_issue_key,
            commentId=None,
            commentUrl=None,
            markContent="",
            timestamp=timestamp,
            success=False,
            hint=f"标记进展失败: {str(e)}"
        )

# ---------- Wiki (Confluence) 集成功能 ----------

def _get_wiki_session() -> Session:
    """获取 Wiki (Confluence) 会话"""
    session = Session()
    
    # 基本认证
    wiki_user = os.getenv("WIKI_USER")
    wiki_password = os.getenv("WIKI_USER_PASSWORD") or os.getenv("WIKI_PASSWORD")
    
    if wiki_user and wiki_password:
        session.auth = (wiki_user, wiki_password)
    
    # 设置请求头
    session.headers.update({
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "DevFlow-MCP/1.0"
    })
    
    return session


def _wiki_api_url(endpoint: str) -> str:
    """构建 Wiki API URL"""
    base_url = os.getenv("WIKI_BASE_URL", "").rstrip("/")
    context_path = os.getenv("WIKI_CONTEXT_PATH", "").strip("/")
    api_version = os.getenv("WIKI_API_VERSION", "latest")
    
    # 根据您的Wiki系统API结构调整
    if context_path:
        if api_version == "1":
            return f"{base_url}/{context_path}/rest/api/{endpoint}"
        elif api_version == "1.0":
            return f"{base_url}/{context_path}/rest/api/1.0/{endpoint}"
        elif api_version == "" or api_version == "latest":
            return f"{base_url}/{context_path}/rest/api/{endpoint}"
        else:
            return f"{base_url}/{context_path}/rest/api/{api_version}/{endpoint}"
    else:
        if api_version == "1":
            return f"{base_url}/rest/api/{endpoint}"
        elif api_version == "1.0":
            return f"{base_url}/rest/api/1.0/{endpoint}"
        elif api_version == "" or api_version == "latest":
            return f"{base_url}/rest/api/{endpoint}"
        else:
            return f"{base_url}/rest/api/{api_version}/{endpoint}"


def _parse_wiki_url(wiki_url: str) -> Dict[str, Optional[str]]:
    """解析Wiki URL，提取空间键和页面标题或ID"""
    try:
        from urllib.parse import urlparse, parse_qs, unquote
        
        parsed = urlparse(wiki_url)
        result = {"spaceKey": None, "pageTitle": None, "pageId": None}
        
        # 处理不同类型的Wiki URL
        path = parsed.path
        query = parse_qs(parsed.query)
        
        # 类型1: /display/SPACE/Page+Title
        if "/display/" in path:
            parts = path.split("/display/")
            if len(parts) > 1:
                remaining = parts[1].split("/", 1)
                if len(remaining) >= 1:
                    result["spaceKey"] = remaining[0]
                if len(remaining) >= 2:
                    # 解码URL编码的标题，并将+替换为空格
                    page_title = unquote(remaining[1]).replace("+", " ")
                    result["pageTitle"] = page_title
        
        # 类型2: /pages/viewpage.action?spaceKey=SPACE&title=Page+Title
        elif "/pages/viewpage.action" in path:
            if "spaceKey" in query:
                result["spaceKey"] = query["spaceKey"][0]
            if "title" in query:
                result["pageTitle"] = unquote(query["title"][0]).replace("+", " ")
            if "pageId" in query:
                result["pageId"] = query["pageId"][0]
        
        # 类型3: /spaces/SPACE/pages/123456/Page+Title
        elif "/spaces/" in path and "/pages/" in path:
            parts = path.split("/")
            try:
                space_idx = parts.index("spaces")
                pages_idx = parts.index("pages")
                if space_idx + 1 < len(parts):
                    result["spaceKey"] = parts[space_idx + 1]
                if pages_idx + 1 < len(parts):
                    # 检查是否是数字ID
                    potential_id = parts[pages_idx + 1]
                    if potential_id.isdigit():
                        result["pageId"] = potential_id
                        # 如果还有后续部分，那可能是标题
                        if pages_idx + 2 < len(parts):
                            result["pageTitle"] = unquote(parts[pages_idx + 2]).replace("+", " ")
            except ValueError:
                pass
        
        return result
        
    except Exception as e:
        print(f"Error parsing Wiki URL: {e}")
        return {"spaceKey": None, "pageTitle": None, "pageId": None}


class WikiCreatePageInput(BaseModel):
    """Wiki 创建页面的输入参数"""
    model_config = ConfigDict(title="WikiCreatePageInput", description="Wiki 创建页面的输入参数")
    spaceKey: str = Field(..., description="空间键值")
    title: str = Field(..., description="页面标题")
    content: str = Field(..., description="页面内容（支持Confluence存储格式或HTML）")
    parentPageId: Optional[str] = Field(None, description="父页面ID（可选）")
    labels: List[str] = Field(default_factory=list, description="页面标签")
    contentFormat: str = Field("storage", description="内容格式：storage/view/html")


class WikiCreatePageOutput(BaseModel):
    pageId: Optional[str] = None
    title: str
    url: Optional[str] = None
    spaceKey: str
    version: int = 1
    hint: str


class WikiUpdatePageInput(BaseModel):
    """Wiki 更新页面的输入参数"""
    model_config = ConfigDict(title="WikiUpdatePageInput", description="Wiki 更新页面的输入参数")
    pageId: str = Field(..., description="页面ID")
    title: Optional[str] = Field(None, description="新标题（可选）")
    content: Optional[str] = Field(None, description="新内容（可选）")
    labels: Optional[List[str]] = Field(None, description="新标签（可选）")
    contentFormat: str = Field("storage", description="内容格式：storage/view/html")
    versionComment: str = Field("Updated by DevFlow MCP", description="版本注释")


class WikiUpdatePageOutput(BaseModel):
    pageId: str
    title: str
    url: Optional[str] = None
    version: int
    hint: str


class WikiSearchInput(BaseModel):
    """Wiki 搜索的输入参数"""
    model_config = ConfigDict(title="WikiSearchInput", description="Wiki 搜索的输入参数")
    query: str = Field(..., description="搜索查询")
    spaceKey: Optional[str] = Field(None, description="限制搜索的空间（可选）")
    searchType: str = Field("content", description="搜索类型：content/title/space")
    limit: int = Field(10, description="返回结果数量限制")
    includeContent: bool = Field(False, description="是否包含页面内容")


class WikiSearchOutput(BaseModel):
    results: List[Dict[str, Any]]
    totalResults: int
    hint: str


class WikiGetPageInput(BaseModel):
    """Wiki 获取页面的输入参数"""
    model_config = ConfigDict(title="WikiGetPageInput", description="Wiki 获取页面的输入参数")
    pageId: Optional[str] = Field(None, description="页面ID")
    spaceKey: Optional[str] = Field(None, description="空间键值")
    title: Optional[str] = Field(None, description="页面标题")
    expand: List[str] = Field(default_factory=lambda: ["body.storage", "version", "space"], description="扩展字段")


class WikiGetPageOutput(BaseModel):
    pageId: str
    title: str
    content: str
    spaceKey: str
    version: int
    url: Optional[str] = None
    labels: List[str] = Field(default_factory=list)
    lastModified: str
    hint: str


class WikiPublishTaskInput(BaseModel):
    """Wiki 发布任务文档的输入参数"""
    model_config = ConfigDict(title="WikiPublishTaskInput", description="Wiki 发布任务文档的输入参数")
    taskKey: str = Field(..., description="任务唯一标识")
    spaceKey: str = Field(..., description="目标Wiki空间")
    parentPageTitle: Optional[str] = Field(None, description="父页面标题（可选）")
    includeProcessDocs: bool = Field(True, description="是否包含过程文档")
    includeIntegrationDoc: bool = Field(True, description="是否包含集成文档")
    templateStyle: str = Field("standard", description="模板样式：standard/compact/detailed")
    autoLink: bool = Field(True, description="是否自动创建页面间链接")
    projectRoot: Optional[str] = Field(None, description="项目根目录")


class WikiPublishTaskOutput(BaseModel):
    taskKey: str
    mainPageId: str
    mainPageUrl: str
    publishedPages: List[Dict[str, str]]
    spaceKey: str
    hint: str


class WikiAddCommentInput(BaseModel):
    """Wiki 添加评论的输入参数"""
    model_config = ConfigDict(title="WikiAddCommentInput", description="Wiki 添加评论的输入参数")
    pageId: str = Field(..., description="页面ID")
    comment: str = Field(..., description="评论内容，支持HTML格式")
    parentCommentId: Optional[str] = Field(None, description="父评论ID，用于回复评论")


class WikiAddCommentOutput(BaseModel):
    commentId: Optional[str] = None
    pageId: str
    commentUrl: Optional[str] = None
    hint: str


class WikiGetCommentsInput(BaseModel):
    """Wiki 获取评论的输入参数"""
    model_config = ConfigDict(title="WikiGetCommentsInput", description="Wiki 获取评论的输入参数")
    pageId: str = Field(..., description="页面ID")
    limit: int = Field(10, description="返回评论数量限制")
    includeReplies: bool = Field(True, description="是否包含回复评论")


class WikiGetCommentsOutput(BaseModel):
    pageId: str
    comments: List[Dict[str, Any]]
    totalComments: int
    hint: str


class WikiUpdateCommentInput(BaseModel):
    """Wiki 更新评论的输入参数"""
    model_config = ConfigDict(title="WikiUpdateCommentInput", description="Wiki 更新评论的输入参数")
    commentId: str = Field(..., description="评论ID")
    comment: str = Field(..., description="新的评论内容")


class WikiUpdateCommentOutput(BaseModel):
    commentId: str
    commentUrl: Optional[str] = None
    hint: str


class WikiDeleteCommentInput(BaseModel):
    """Wiki 删除评论的输入参数"""
    model_config = ConfigDict(title="WikiDeleteCommentInput", description="Wiki 删除评论的输入参数")
    commentId: str = Field(..., description="要删除的评论ID")


class WikiDeleteCommentOutput(BaseModel):
    commentId: str
    success: bool
    hint: str


class WikiReadUrlInput(BaseModel):
    """Wiki 根据URL读取页面的输入参数"""
    model_config = ConfigDict(title="WikiReadUrlInput", description="Wiki 根据URL读取页面的输入参数")
    url: str = Field(..., description="Wiki页面的完整URL")
    includeComments: bool = Field(False, description="是否包含页面评论")
    includeAttachments: bool = Field(False, description="是否包含页面附件信息")


class WikiReadUrlOutput(BaseModel):
    pageId: str
    title: str
    content: str
    spaceKey: str
    spaceName: str
    version: int
    url: str
    labels: List[str] = Field(default_factory=list)
    lastModified: str
    author: str
    comments: List[Dict[str, Any]] = Field(default_factory=list)
    attachments: List[Dict[str, Any]] = Field(default_factory=list)
    breadcrumb: List[Dict[str, str]] = Field(default_factory=list)
    hint: str


class WikiDiagnosticInput(BaseModel):
    pageId: str
    testComment: Optional[str] = "测试评论"


class WikiDiagnosticOutput(BaseModel):
    pageId: str
    apiTests: Dict[str, Any]
    recommendations: List[str]
    hint: str


@app.tool()
def wiki_create_page(input: WikiCreatePageInput) -> WikiCreatePageOutput:
    """在 Wiki (Confluence) 中创建新页面。"""
    try:
        session = _get_wiki_session()
        url = _wiki_api_url("content")
        
        # 构建页面数据
        page_data = {
            "type": "page",
            "title": input.title,
            "space": {"key": input.spaceKey},
            "body": {
                input.contentFormat: {
                    "value": input.content,
                    "representation": input.contentFormat
                }
            }
        }
        
        # 添加父页面
        if input.parentPageId:
            page_data["ancestors"] = [{"id": input.parentPageId}]
        
        # 添加标签
        if input.labels:
            page_data["metadata"] = {
                "labels": [{"name": label} for label in input.labels]
            }
        
        resp = session.post(url, json=page_data, timeout=30)
        
        if resp.status_code >= 400:
            return WikiCreatePageOutput(
                pageId=None,
                title=input.title,
                url=None,
                spaceKey=input.spaceKey,
                version=1,
                hint=f"Failed to create page: {resp.status_code} {resp.text}"
            )
        
        result = resp.json()
        page_id = result.get("id")
        
        # 构建页面URL
        base_url = os.getenv("WIKI_BASE_URL", "").rstrip("/")
        page_url = f"{base_url}/display/{input.spaceKey}/{input.title.replace(' ', '+')}" if page_id else None
        
        return WikiCreatePageOutput(
            pageId=page_id,
            title=result.get("title", input.title),
            url=page_url,
            spaceKey=input.spaceKey,
            version=result.get("version", {}).get("number", 1),
            hint=f"Page created successfully in space {input.spaceKey}"
        )
        
    except Exception as e:
        return WikiCreatePageOutput(
            pageId=None,
            title=input.title,
            url=None,
            spaceKey=input.spaceKey,
            version=1,
            hint=f"Error creating page: {str(e)}"
        )


@app.tool()
def wiki_update_page(input: WikiUpdatePageInput) -> WikiUpdatePageOutput:
    """更新 Wiki (Confluence) 页面内容。"""
    try:
        session = _get_wiki_session()
        
        # 先获取当前页面信息
        get_url = _wiki_api_url(f"content/{input.pageId}?expand=version,space")
        get_resp = session.get(get_url, timeout=30)
        
        if get_resp.status_code >= 400:
            return WikiUpdatePageOutput(
                pageId=input.pageId,
                title="",
                url=None,
                version=1,
                hint=f"Failed to get current page: {get_resp.status_code}"
            )
        
        current_page = get_resp.json()
        current_version = current_page.get("version", {}).get("number", 1)
        current_title = current_page.get("title", "")
        space_key = current_page.get("space", {}).get("key", "")
        
        # 构建更新数据
        update_data = {
            "id": input.pageId,
            "type": "page",
            "title": input.title or current_title,
            "version": {
                "number": current_version + 1,
                "message": input.versionComment
            }
        }
        
        # 更新内容
        if input.content:
            update_data["body"] = {
                input.contentFormat: {
                    "value": input.content,
                    "representation": input.contentFormat
                }
            }
        
        # 更新标签
        if input.labels is not None:
            update_data["metadata"] = {
                "labels": [{"name": label} for label in input.labels]
            }
        
        # 发送更新请求
        update_url = _wiki_api_url(f"content/{input.pageId}")
        resp = session.put(update_url, json=update_data, timeout=30)
        
        if resp.status_code >= 400:
            return WikiUpdatePageOutput(
                pageId=input.pageId,
                title=current_title,
                url=None,
                version=current_version,
                hint=f"Failed to update page: {resp.status_code} {resp.text}"
            )
        
        result = resp.json()
        
        # 构建页面URL
        base_url = os.getenv("WIKI_BASE_URL", "").rstrip("/")
        page_title = result.get("title", current_title)
        page_url = f"{base_url}/display/{space_key}/{page_title.replace(' ', '+')}"
        
        return WikiUpdatePageOutput(
            pageId=input.pageId,
            title=page_title,
            url=page_url,
            version=result.get("version", {}).get("number", current_version + 1),
            hint=f"Page updated successfully (version {current_version + 1})"
        )
        
    except Exception as e:
        return WikiUpdatePageOutput(
            pageId=input.pageId,
            title="",
            url=None,
            version=1,
            hint=f"Error updating page: {str(e)}"
        )


@app.tool()
def wiki_search_pages(input: WikiSearchInput) -> WikiSearchOutput:
    """在 Wiki (Confluence) 中搜索页面。"""
    try:
        session = _get_wiki_session()
        
        # 构建搜索参数
        params = {
            "cql": f"text ~ \"{input.query}\"",
            "limit": input.limit
        }
        
        # 限制搜索空间
        if input.spaceKey:
            params["cql"] += f" and space = {input.spaceKey}"
        
        # 根据搜索类型调整查询
        if input.searchType == "title":
            params["cql"] = f"title ~ \"{input.query}\""
            if input.spaceKey:
                params["cql"] += f" and space = {input.spaceKey}"
        elif input.searchType == "space":
            params["cql"] = f"space = {input.query}"
        
        # 设置扩展字段
        expand_fields = ["version", "space"]
        if input.includeContent:
            expand_fields.append("body.storage")
        params["expand"] = ",".join(expand_fields)
        
        url = _wiki_api_url("content/search")
        resp = session.get(url, params=params, timeout=30)
        
        if resp.status_code >= 400:
            return WikiSearchOutput(
                results=[],
                totalResults=0,
                hint=f"Search failed: {resp.status_code} {resp.text}"
            )
        
        data = resp.json()
        results = data.get("results", [])
        
        # 处理搜索结果
        processed_results = []
        for result in results:
            processed_result = {
                "id": result.get("id"),
                "title": result.get("title"),
                "type": result.get("type"),
                "spaceKey": result.get("space", {}).get("key"),
                "spaceName": result.get("space", {}).get("name"),
                "version": result.get("version", {}).get("number"),
                "lastModified": result.get("version", {}).get("when"),
                "url": result.get("_links", {}).get("webui")
            }
            
            # 添加内容（如果请求）
            if input.includeContent and "body" in result:
                processed_result["content"] = result.get("body", {}).get("storage", {}).get("value", "")
            
            processed_results.append(processed_result)
        
        return WikiSearchOutput(
            results=processed_results,
            totalResults=data.get("size", len(results)),
            hint=f"Found {len(results)} results for query: {input.query}"
        )
        
    except Exception as e:
        return WikiSearchOutput(
            results=[],
            totalResults=0,
            hint=f"Search error: {str(e)}"
        )


@app.tool()
def wiki_get_page(input: WikiGetPageInput) -> WikiGetPageOutput:
    """获取 Wiki (Confluence) 页面详情。"""
    try:
        session = _get_wiki_session()
        
        # 确定页面查询方式
        if input.pageId:
            url = _wiki_api_url(f"content/{input.pageId}")
        elif input.spaceKey and input.title:
            # 通过空间和标题搜索
            search_params = {
                "spaceKey": input.spaceKey,
                "title": input.title,
                "expand": ",".join(input.expand)
            }
            url = _wiki_api_url("content")
        else:
            return WikiGetPageOutput(
                pageId="",
                title="",
                content="",
                spaceKey="",
                version=0,
                url=None,
                lastModified="",
                hint="Must provide either pageId or both spaceKey and title"
            )
        
        # 设置扩展参数
        params = {"expand": ",".join(input.expand)}
        if not input.pageId:
            params.update(search_params)
        
        resp = session.get(url, params=params, timeout=30)
        
        if resp.status_code >= 400:
            return WikiGetPageOutput(
                pageId="",
                title="",
                content="",
                spaceKey="",
                version=0,
                url=None,
                lastModified="",
                hint=f"Failed to get page: {resp.status_code} {resp.text}"
            )
        
        data = resp.json()
        
        # 处理搜索结果（如果是通过标题搜索）
        if not input.pageId and "results" in data:
            if not data["results"]:
                return WikiGetPageOutput(
                    pageId="",
                    title=input.title or "",
                    content="",
                    spaceKey=input.spaceKey or "",
                    version=0,
                    url=None,
                    lastModified="",
                    hint=f"Page not found: {input.title}"
                )
            data = data["results"][0]
        
        # 提取页面信息
        page_id = data.get("id", "")
        title = data.get("title", "")
        space_key = data.get("space", {}).get("key", "")
        version = data.get("version", {}).get("number", 0)
        last_modified = data.get("version", {}).get("when", "")
        
        # 提取内容
        content = ""
        if "body" in data and "storage" in data["body"]:
            content = data["body"]["storage"].get("value", "")
        
        # 提取标签
        labels = []
        if "metadata" in data and "labels" in data["metadata"]:
            labels = [label.get("name", "") for label in data["metadata"]["labels"].get("results", [])]
        
        # 构建页面URL
        base_url = os.getenv("WIKI_BASE_URL", "").rstrip("/")
        page_url = f"{base_url}/display/{space_key}/{title.replace(' ', '+')}" if page_id else None
        
        return WikiGetPageOutput(
            pageId=page_id,
            title=title,
            content=content,
            spaceKey=space_key,
            version=version,
            url=page_url,
            labels=labels,
            lastModified=last_modified,
            hint=f"Page retrieved successfully: {title}"
        )
        
    except Exception as e:
        return WikiGetPageOutput(
            pageId="",
            title="",
            content="",
            spaceKey="",
            version=0,
            url=None,
            lastModified="",
            hint=f"Error getting page: {str(e)}"
        )


@app.tool()
def wiki_read_url(input: WikiReadUrlInput) -> WikiReadUrlOutput:
    """根据Wiki URL直接读取页面内容，支持多种URL格式。"""
    try:
        # 解析URL获取页面信息
        parsed_info = _parse_wiki_url(input.url)
        
        if not parsed_info["spaceKey"] and not parsed_info["pageId"]:
            return WikiReadUrlOutput(
                pageId="",
                title="",
                content="",
                spaceKey="",
                spaceName="",
                version=0,
                url=input.url,
                lastModified="",
                author="",
                hint="无法从URL中解析出有效的空间键或页面ID"
            )
        
        session = _get_wiki_session()
        
        # 根据解析结果获取页面
        if parsed_info["pageId"]:
            # 通过页面ID获取
            page_result = wiki_get_page(WikiGetPageInput(
                pageId=parsed_info["pageId"],
                expand=["body.storage", "version", "space", "metadata.labels", "ancestors"]
            ))
        elif parsed_info["spaceKey"] and parsed_info["pageTitle"]:
            # 通过空间和标题获取
            page_result = wiki_get_page(WikiGetPageInput(
                spaceKey=parsed_info["spaceKey"],
                title=parsed_info["pageTitle"],
                expand=["body.storage", "version", "space", "metadata.labels", "ancestors"]
            ))
        else:
            return WikiReadUrlOutput(
                pageId="",
                title="",
                content="",
                spaceKey="",
                spaceName="",
                version=0,
                url=input.url,
                lastModified="",
                author="",
                hint="URL解析不完整，无法定位页面"
            )
        
        if not page_result.pageId:
            return WikiReadUrlOutput(
                pageId="",
                title="",
                content="",
                spaceKey=parsed_info.get("spaceKey", ""),
                spaceName="",
                version=0,
                url=input.url,
                lastModified="",
                author="",
                hint=f"页面未找到: {page_result.hint}"
            )
        
        # 获取空间信息
        space_name = ""
        try:
            space_url = _wiki_api_url(f"space/{page_result.spaceKey}")
            space_resp = session.get(space_url, timeout=30)
            if space_resp.status_code == 200:
                space_data = space_resp.json()
                space_name = space_data.get("name", "")
        except:
            pass
        
        # 获取作者信息
        author = ""
        try:
            page_url = _wiki_api_url(f"content/{page_result.pageId}?expand=version.by")
            page_resp = session.get(page_url, timeout=30)
            if page_resp.status_code == 200:
                page_data = page_resp.json()
                author = page_data.get("version", {}).get("by", {}).get("displayName", "")
        except:
            pass
        
        # 获取面包屑导航
        breadcrumb = []
        try:
            ancestors_url = _wiki_api_url(f"content/{page_result.pageId}?expand=ancestors")
            ancestors_resp = session.get(ancestors_url, timeout=30)
            if ancestors_resp.status_code == 200:
                ancestors_data = ancestors_resp.json()
                ancestors = ancestors_data.get("ancestors", [])
                for ancestor in ancestors:
                    breadcrumb.append({
                        "id": ancestor.get("id", ""),
                        "title": ancestor.get("title", ""),
                        "type": ancestor.get("type", "")
                    })
        except:
            pass
        
        result = WikiReadUrlOutput(
            pageId=page_result.pageId,
            title=page_result.title,
            content=page_result.content,
            spaceKey=page_result.spaceKey,
            spaceName=space_name,
            version=page_result.version,
            url=input.url,
            labels=page_result.labels,
            lastModified=page_result.lastModified,
            author=author,
            breadcrumb=breadcrumb,
            hint=f"成功读取页面: {page_result.title}"
        )
        
        # 获取评论（如果需要）
        if input.includeComments:
            try:
                comments_result = wiki_get_comments(WikiGetCommentsInput(
                    pageId=page_result.pageId,
                    limit=50,
                    includeReplies=True
                ))
                result.comments = comments_result.comments
            except Exception as e:
                print(f"Failed to get comments: {e}")
        
        # 获取附件信息（如果需要）
        if input.includeAttachments:
            try:
                attachments_url = _wiki_api_url(f"content/{page_result.pageId}/child/attachment")
                attachments_resp = session.get(attachments_url, timeout=30)
                if attachments_resp.status_code == 200:
                    attachments_data = attachments_resp.json()
                    attachments = []
                    for attachment in attachments_data.get("results", []):
                        attachments.append({
                            "id": attachment.get("id"),
                            "title": attachment.get("title"),
                            "mediaType": attachment.get("metadata", {}).get("mediaType", ""),
                            "fileSize": attachment.get("extensions", {}).get("fileSize", 0),
                            "downloadUrl": attachment.get("_links", {}).get("download", ""),
                            "version": attachment.get("version", {}).get("number", 1),
                            "createdDate": attachment.get("version", {}).get("when", "")
                        })
                    result.attachments = attachments
            except Exception as e:
                print(f"Failed to get attachments: {e}")
        
        return result
        
    except Exception as e:
        return WikiReadUrlOutput(
            pageId="",
            title="",
            content="",
            spaceKey="",
            spaceName="",
            version=0,
            url=input.url,
            lastModified="",
            author="",
            hint=f"读取页面时出错: {str(e)}"
        )


@app.tool()
def wiki_add_comment(input: WikiAddCommentInput) -> WikiAddCommentOutput:
    """向 Wiki 页面添加评论。"""
    try:
        session = _get_wiki_session()
        
        # 首先尝试使用TinyMCE API（更现代的方式）
        base_url = os.getenv("WIKI_BASE_URL", "").rstrip("/")
        context_path = os.getenv("WIKI_CONTEXT_PATH", "").strip("/")
        
        # 尝试多种TinyMCE API版本
        tinymce_urls = []
        if context_path:
            tinymce_urls = [
                f"{base_url}/{context_path}/rest/tinymce/1/content/{input.pageId}/comment",
                f"{base_url}/{context_path}/rest/tinymce/1.0/content/{input.pageId}/comment"
            ]
        else:
            tinymce_urls = [
                f"{base_url}/rest/tinymce/1/content/{input.pageId}/comment",
                f"{base_url}/rest/tinymce/1.0/content/{input.pageId}/comment"
            ]
        
        # 构建TinyMCE评论数据
        tinymce_data = {
            "body": input.comment,
            "actions": True
        }
        
        # 如果是回复评论，添加父评论信息
        if input.parentCommentId:
            tinymce_data["parentId"] = input.parentCommentId
        
        # 尝试多个TinyMCE API版本
        tinymce_success = False
        resp = None
        for tinymce_url in tinymce_urls:
            try:
                resp = session.post(tinymce_url, json=tinymce_data, timeout=30)
                if resp.status_code < 400:
                    tinymce_success = True
                    break
            except Exception as e:
                print(f"TinyMCE API {tinymce_url} failed: {e}")
                continue
        
        if tinymce_success and resp and resp.status_code < 400:
            # TinyMCE API成功
            result = resp.json()
            comment_id = result.get("id")
            comment_url = f"{base_url}/pages/viewpage.action?pageId={input.pageId}#comment-{comment_id}" if comment_id else None
            
            return WikiAddCommentOutput(
                commentId=comment_id,
                pageId=input.pageId,
                commentUrl=comment_url,
                hint=f"Comment added successfully via TinyMCE API to page {input.pageId}"
            )
        
        # 如果TinyMCE API失败，回退到标准REST API
        print(f"TinyMCE API failed ({resp.status_code}), falling back to standard REST API")
        
        # 构建标准API评论数据
        comment_data = {
            "type": "comment",
            "container": {"id": input.pageId, "type": "page"},
            "body": {
                "storage": {
                    "value": input.comment,
                    "representation": "storage"
                }
            }
        }
        
        # 如果是回复评论，添加父评论信息
        if input.parentCommentId:
            comment_data["ancestors"] = [{"id": input.parentCommentId}]
        
        url = _wiki_api_url("content")
        resp = session.post(url, json=comment_data, timeout=30)
        
        if resp.status_code >= 400:
            return WikiAddCommentOutput(
                commentId=None,
                pageId=input.pageId,
                commentUrl=None,
                hint=f"Failed to add comment via both APIs. TinyMCE: {tinymce_url}, REST: {url}. Last error: {resp.status_code} {resp.text}"
            )
        
        result = resp.json()
        comment_id = result.get("id")
        
        # 构建评论链接
        comment_url = f"{base_url}/pages/viewpage.action?pageId={input.pageId}#comment-{comment_id}" if comment_id else None
        
        return WikiAddCommentOutput(
            commentId=comment_id,
            pageId=input.pageId,
            commentUrl=comment_url,
            hint=f"Comment added successfully via REST API to page {input.pageId}"
        )
        
    except Exception as e:
        return WikiAddCommentOutput(
            commentId=None,
            pageId=input.pageId,
            commentUrl=None,
            hint=f"Error adding comment: {str(e)}"
        )


@app.tool()
def wiki_get_comments(input: WikiGetCommentsInput) -> WikiGetCommentsOutput:
    """获取 Wiki 页面的评论列表。"""
    try:
        session = _get_wiki_session()
        
        # 尝试多种评论API路径
        base_url = os.getenv("WIKI_BASE_URL", "").rstrip("/")
        context_path = os.getenv("WIKI_CONTEXT_PATH", "").strip("/")
        
        # 构建多个可能的评论API URL
        comment_urls = []
        if context_path:
            comment_urls = [
                f"{base_url}/{context_path}/rest/tinymce/1/content/{input.pageId}/comment",
                f"{base_url}/{context_path}/rest/tinymce/1.0/content/{input.pageId}/comment",
                f"{base_url}/{context_path}/rest/api/content/{input.pageId}/child/comment",
                f"{base_url}/{context_path}/rest/api/1.0/content/{input.pageId}/child/comment",
            ]
        else:
            comment_urls = [
                f"{base_url}/rest/tinymce/1/content/{input.pageId}/comment",
                f"{base_url}/rest/tinymce/1.0/content/{input.pageId}/comment", 
                f"{base_url}/rest/api/content/{input.pageId}/child/comment",
                f"{base_url}/rest/api/1.0/content/{input.pageId}/child/comment",
            ]
        
        # 尝试每个API直到找到可用的
        successful_response = None
        successful_url = None
        
        for comment_url in comment_urls:
            try:
                params = {"limit": input.limit}
                resp = session.get(comment_url, params=params, timeout=30)
                
                if resp.status_code == 200:
                    successful_response = resp
                    successful_url = comment_url
                    break
                elif resp.status_code == 501:
                    print(f"API not implemented: {comment_url}")
                    continue
                else:
                    print(f"API failed with {resp.status_code}: {comment_url}")
                    continue
                    
            except Exception as e:
                print(f"Exception with {comment_url}: {e}")
                continue
        
        if successful_response and successful_response.status_code == 200:
            # API成功
            try:
                data = successful_response.json()
                comments_data = data.get("results", []) if isinstance(data, dict) else data
                
                processed_comments = []
                for comment in comments_data:
                    comment_info = {
                        "id": comment.get("id"),
                        "title": comment.get("title", ""),
                        "content": comment.get("body", comment.get("content", "")),
                        "author": comment.get("author", {}).get("displayName", "Unknown") if isinstance(comment.get("author"), dict) else comment.get("author", "Unknown"),
                        "authorEmail": comment.get("author", {}).get("email", "") if isinstance(comment.get("author"), dict) else "",
                        "createdDate": comment.get("createdDate", comment.get("created", "")),
                        "version": comment.get("version", 1),
                        "isReply": bool(comment.get("parentId") or comment.get("parent"))
                    }
                    
                    # 如果是回复，添加父评论信息
                    if comment_info["isReply"]:
                        comment_info["parentCommentId"] = comment.get("parentId", comment.get("parent", {}).get("id"))
                    
                    processed_comments.append(comment_info)
                
                # 如果不包含回复，过滤掉回复评论
                if not input.includeReplies:
                    processed_comments = [c for c in processed_comments if not c["isReply"]]
                
                return WikiGetCommentsOutput(
                    pageId=input.pageId,
                    comments=processed_comments,
                    totalComments=len(processed_comments),
                    hint=f"Retrieved {len(processed_comments)} comments via {successful_url} for page {input.pageId}"
                )
            except Exception as parse_e:
                print(f"Failed to parse response: {parse_e}")
        
        # 如果所有评论API都失败，返回错误信息
        if not successful_response:
            return WikiGetCommentsOutput(
                pageId=input.pageId,
                comments=[],
                totalComments=0,
                hint=f"All comment APIs failed (501 Not Implemented). Tried: {', '.join(comment_urls)}"
            )
        
        # 构建查询参数
        params = {
            "type": "comment",
            "container": input.pageId,
            "limit": input.limit,
            "expand": "body.storage,version,ancestors"
        }
        
        url = _wiki_api_url("content")
        resp = session.get(url, params=params, timeout=30)
        
        if resp.status_code >= 400:
            return WikiGetCommentsOutput(
                pageId=input.pageId,
                comments=[],
                totalComments=0,
                hint=f"Failed to get comments via all APIs. Tried: {', '.join(comment_urls)}. No successful response."
            )
        
        data = resp.json()
        comments_data = data.get("results", [])
        
        # 处理评论数据
        processed_comments = []
        for comment in comments_data:
            comment_info = {
                "id": comment.get("id"),
                "title": comment.get("title", ""),
                "content": comment.get("body", {}).get("storage", {}).get("value", ""),
                "author": comment.get("version", {}).get("by", {}).get("displayName", "Unknown"),
                "authorEmail": comment.get("version", {}).get("by", {}).get("email", ""),
                "createdDate": comment.get("version", {}).get("when", ""),
                "version": comment.get("version", {}).get("number", 1),
                "isReply": bool(comment.get("ancestors", []))
            }
            
            # 如果是回复，添加父评论信息
            if comment_info["isReply"] and comment.get("ancestors"):
                parent = comment["ancestors"][-1]  # 最后一个ancestor是直接父级
                comment_info["parentCommentId"] = parent.get("id")
            
            processed_comments.append(comment_info)
        
        # 如果不包含回复，过滤掉回复评论
        if not input.includeReplies:
            processed_comments = [c for c in processed_comments if not c["isReply"]]
        
        return WikiGetCommentsOutput(
            pageId=input.pageId,
            comments=processed_comments,
            totalComments=len(processed_comments),
            hint=f"Retrieved {len(processed_comments)} comments via REST API for page {input.pageId}"
        )
        
    except Exception as e:
        return WikiGetCommentsOutput(
            pageId=input.pageId,
            comments=[],
            totalComments=0,
            hint=f"Error getting comments: {str(e)}"
        )


@app.tool()
def wiki_update_comment(input: WikiUpdateCommentInput) -> WikiUpdateCommentOutput:
    """更新 Wiki 评论内容。"""
    try:
        session = _get_wiki_session()
        
        # 先获取当前评论信息
        get_url = _wiki_api_url(f"content/{input.commentId}?expand=version,container")
        get_resp = session.get(get_url, timeout=30)
        
        if get_resp.status_code >= 400:
            return WikiUpdateCommentOutput(
                commentId=input.commentId,
                commentUrl=None,
                hint=f"Failed to get current comment: {get_resp.status_code}"
            )
        
        current_comment = get_resp.json()
        current_version = current_comment.get("version", {}).get("number", 1)
        container_id = current_comment.get("container", {}).get("id")
        
        # 构建更新数据
        update_data = {
            "id": input.commentId,
            "type": "comment",
            "version": {
                "number": current_version + 1
            },
            "body": {
                "storage": {
                    "value": input.comment,
                    "representation": "storage"
                }
            }
        }
        
        # 发送更新请求
        update_url = _wiki_api_url(f"content/{input.commentId}")
        resp = session.put(update_url, json=update_data, timeout=30)
        
        if resp.status_code >= 400:
            return WikiUpdateCommentOutput(
                commentId=input.commentId,
                commentUrl=None,
                hint=f"Failed to update comment: {resp.status_code} {resp.text}"
            )
        
        # 构建评论链接
        base_url = os.getenv("WIKI_BASE_URL", "").rstrip("/")
        comment_url = f"{base_url}/pages/viewpage.action?pageId={container_id}#comment-{input.commentId}" if container_id else None
        
        return WikiUpdateCommentOutput(
            commentId=input.commentId,
            commentUrl=comment_url,
            hint=f"Comment {input.commentId} updated successfully"
        )
        
    except Exception as e:
        return WikiUpdateCommentOutput(
            commentId=input.commentId,
            commentUrl=None,
            hint=f"Error updating comment: {str(e)}"
        )


@app.tool()
def wiki_delete_comment(input: WikiDeleteCommentInput) -> WikiDeleteCommentOutput:
    """删除 Wiki 评论。"""
    try:
        session = _get_wiki_session()
        
        url = _wiki_api_url(f"content/{input.commentId}")
        resp = session.delete(url, timeout=30)
        
        if resp.status_code >= 400:
            return WikiDeleteCommentOutput(
                commentId=input.commentId,
                success=False,
                hint=f"Failed to delete comment: {resp.status_code} {resp.text}"
            )
        
        return WikiDeleteCommentOutput(
            commentId=input.commentId,
            success=True,
            hint=f"Comment {input.commentId} deleted successfully"
        )
        
    except Exception as e:
        return WikiDeleteCommentOutput(
            commentId=input.commentId,
            success=False,
            hint=f"Error deleting comment: {str(e)}"
        )


@app.tool()
def wiki_publish_task(input: WikiPublishTaskInput) -> WikiPublishTaskOutput:
    """将DevFlow任务文档发布到Wiki，创建结构化的文档页面。"""
    try:
        project_root = _resolve_project_root(input.projectRoot)
        published_pages = []
        
        # 1. 获取任务信息
        task_metadata = _get_task_metadata(project_root, input.taskKey)
        task_title = task_metadata.get("title", input.taskKey)
        
        # 2. 创建主页面
        main_page_title = f"{input.taskKey} - {task_title}"
        main_page_content = _generate_wiki_task_overview(
            project_root, input.taskKey, task_metadata, input.templateStyle
        )
        
        # 查找父页面ID（如果指定）
        parent_page_id = None
        if input.parentPageTitle:
            search_result = wiki_search_pages(WikiSearchInput(
                query=input.parentPageTitle,
                spaceKey=input.spaceKey,
                searchType="title",
                limit=1
            ))
            if search_result.results:
                parent_page_id = search_result.results[0]["id"]
        
        # 创建主页面
        main_page_result = wiki_create_page(WikiCreatePageInput(
            spaceKey=input.spaceKey,
            title=main_page_title,
            content=main_page_content,
            parentPageId=parent_page_id,
            labels=[input.taskKey, "DevFlow", "Task"],
            contentFormat="storage"
        ))
        
        if not main_page_result.pageId:
            return WikiPublishTaskOutput(
                taskKey=input.taskKey,
                mainPageId="",
                mainPageUrl="",
                publishedPages=[],
                spaceKey=input.spaceKey,
                hint=f"Failed to create main page: {main_page_result.hint}"
            )
        
        published_pages.append({
            "title": main_page_title,
            "pageId": main_page_result.pageId,
            "url": main_page_result.url or "",
            "type": "overview"
        })
        
        # 3. 发布过程文档（如果启用）
        if input.includeProcessDocs:
            process_dir = project_root / "Docs" / "ProcessDocuments" / f"task-{input.taskKey}"
            if process_dir.exists():
                doc_configs = [
                    ("01-Context.md", "项目背景与目标"),
                    ("02-Design.md", "设计方案"),
                    ("03-CodePlan.md", "代码实现计划"),
                    ("04-TestCurls.md", "测试用例"),
                    ("05-MySQLVerificationPlan.md", "数据库验证计划"),
                    ("06-Integration.md", "集成文档"),
                    ("07-JiraPublishPlan.md", "发布计划")
                ]
                
                for doc_file, doc_title in doc_configs:
                    doc_path = process_dir / f"{input.taskKey}_{doc_file}"
                    if doc_path.exists():
                        try:
                            # 读取文档内容
                            post = frontmatter.load(doc_path)
                            doc_content = post.content
                            
                            # 转换为Wiki格式
                            wiki_content = _convert_markdown_to_confluence(doc_content)
                            
                            # 创建子页面
                            sub_page_title = f"{input.taskKey} - {doc_title}"
                            sub_page_result = wiki_create_page(WikiCreatePageInput(
                                spaceKey=input.spaceKey,
                                title=sub_page_title,
                                content=wiki_content,
                                parentPageId=main_page_result.pageId,
                                labels=[input.taskKey, "DevFlow", "ProcessDoc", doc_file.split('-')[0]],
                                contentFormat="storage"
                            ))
                            
                            if sub_page_result.pageId:
                                published_pages.append({
                                    "title": sub_page_title,
                                    "pageId": sub_page_result.pageId,
                                    "url": sub_page_result.url or "",
                                    "type": "process_doc",
                                    "docFile": doc_file
                                })
                        except Exception as e:
                            print(f"Failed to publish {doc_file}: {str(e)}")
        
        # 4. 发布集成文档（如果启用且存在）
        if input.includeIntegrationDoc:
            integration_doc_path = project_root / "Docs" / "ProcessDocuments" / f"task-{input.taskKey}" / f"{input.taskKey}_06-Integration.md"
            if integration_doc_path.exists():
                try:
                    post = frontmatter.load(integration_doc_path)
                    integration_content = _convert_markdown_to_confluence(post.content)
                    
                    integration_page_result = wiki_create_page(WikiCreatePageInput(
                        spaceKey=input.spaceKey,
                        title=f"{input.taskKey} - API集成文档",
                        content=integration_content,
                        parentPageId=main_page_result.pageId,
                        labels=[input.taskKey, "DevFlow", "Integration", "API"],
                        contentFormat="storage"
                    ))
                    
                    if integration_page_result.pageId:
                        published_pages.append({
                            "title": f"{input.taskKey} - API集成文档",
                            "pageId": integration_page_result.pageId,
                            "url": integration_page_result.url or "",
                            "type": "integration_doc"
                        })
                except Exception as e:
                    print(f"Failed to publish integration doc: {str(e)}")
        
        # 5. 更新主页面，添加子页面链接（如果启用自动链接）
        if input.autoLink and len(published_pages) > 1:
            try:
                updated_main_content = _add_child_page_links(
                    main_page_content, published_pages[1:], input.spaceKey
                )
                
                wiki_update_page(WikiUpdatePageInput(
                    pageId=main_page_result.pageId,
                    content=updated_main_content,
                    versionComment="Added child page links"
                ))
            except Exception as e:
                print(f"Failed to update main page with links: {str(e)}")
        
        return WikiPublishTaskOutput(
            taskKey=input.taskKey,
            mainPageId=main_page_result.pageId,
            mainPageUrl=main_page_result.url or "",
            publishedPages=published_pages,
            spaceKey=input.spaceKey,
            hint=f"Successfully published {len(published_pages)} pages for task {input.taskKey}"
        )
        
    except Exception as e:
        return WikiPublishTaskOutput(
            taskKey=input.taskKey,
            mainPageId="",
            mainPageUrl="",
            publishedPages=[],
            spaceKey=input.spaceKey,
            hint=f"Error publishing task: {str(e)}"
        )


def _generate_wiki_task_overview(project_root: Path, task_key: str, metadata: Dict[str, Any], style: str) -> str:
    """生成Wiki任务概览页面内容"""
    title = metadata.get("title", task_key)
    owner = metadata.get("owner", "未指定")
    reviewers = ", ".join(metadata.get("reviewers", []))
    status = _read_task_status(project_root, task_key)
    created_at = metadata.get("createdAt", "")
    updated_at = metadata.get("updatedAt", "")
    
    if style == "compact":
        content = f"""<h1>{task_key} - {title}</h1>

<table>
<tr><td><strong>任务状态</strong></td><td><ac:structured-macro ac:name="status" ac:schema-version="1"><ac:parameter ac:name="colour">Blue</ac:parameter><ac:parameter ac:name="title">{status}</ac:parameter></ac:structured-macro></td></tr>
<tr><td><strong>负责人</strong></td><td>{owner}</td></tr>
<tr><td><strong>审核人</strong></td><td>{reviewers}</td></tr>
<tr><td><strong>创建时间</strong></td><td>{created_at}</td></tr>
<tr><td><strong>更新时间</strong></td><td>{updated_at}</td></tr>
</table>

<h2>子页面</h2>
<p><em>相关文档页面将在下方列出</em></p>
"""
    elif style == "detailed":
        # 获取任务进展报告
        progress_report = _generate_task_progress_report(project_root, task_key)
        
        content = f"""<h1>{task_key} - {title}</h1>

<ac:structured-macro ac:name="info" ac:schema-version="1">
<ac:parameter ac:name="title">任务概览</ac:parameter>
<ac:rich-text-body>
<p>本页面包含任务 <strong>{task_key}</strong> 的完整文档和进展信息。</p>
</ac:rich-text-body>
</ac:structured-macro>

<h2>基本信息</h2>
<table>
<tr><td><strong>任务编号</strong></td><td>{task_key}</td></tr>
<tr><td><strong>任务标题</strong></td><td>{title}</td></tr>
<tr><td><strong>当前状态</strong></td><td><ac:structured-macro ac:name="status" ac:schema-version="1"><ac:parameter ac:name="colour">Blue</ac:parameter><ac:parameter ac:name="title">{status}</ac:parameter></ac:structured-macro></td></tr>
<tr><td><strong>负责人</strong></td><td>{owner}</td></tr>
<tr><td><strong>审核人</strong></td><td>{reviewers}</td></tr>
<tr><td><strong>创建时间</strong></td><td>{created_at}</td></tr>
<tr><td><strong>最后更新</strong></td><td>{updated_at}</td></tr>
</table>

<h2>文档状态</h2>
<table>
<tr><th>文档类型</th><th>状态</th><th>更新时间</th></tr>
"""
        # 添加文档状态信息
        for doc in progress_report.get("processDocuments", []):
            status_macro = f'<ac:structured-macro ac:name="status" ac:schema-version="1"><ac:parameter ac:name="colour">Green</ac:parameter><ac:parameter ac:name="title">{doc["status"]}</ac:parameter></ac:structured-macro>'
            content += f'<tr><td>{doc["name"]}</td><td>{status_macro}</td><td>{doc.get("updatedAt", "N/A")}</td></tr>\n'
        
        content += """</table>

<h2>相关页面</h2>
<p><em>相关文档页面将在下方列出</em></p>

<h2>最新进展</h2>
<ac:structured-macro ac:name="expand" ac:schema-version="1">
<ac:parameter ac:name="title">查看详细进展</ac:parameter>
<ac:rich-text-body>
<p><em>最新的任务进展信息将通过DevFlow自动更新</em></p>
</ac:rich-text-body>
</ac:structured-macro>
"""
    else:  # standard
        content = f"""<h1>{task_key} - {title}</h1>

<ac:structured-macro ac:name="panel" ac:schema-version="1">
<ac:parameter ac:name="bgColor">#eae6ff</ac:parameter>
<ac:parameter ac:name="title">任务信息</ac:parameter>
<ac:rich-text-body>
<table>
<tr><td><strong>状态</strong></td><td><ac:structured-macro ac:name="status" ac:schema-version="1"><ac:parameter ac:name="colour">Blue</ac:parameter><ac:parameter ac:name="title">{status}</ac:parameter></ac:structured-macro></td></tr>
<tr><td><strong>负责人</strong></td><td>{owner}</td></tr>
<tr><td><strong>审核人</strong></td><td>{reviewers}</td></tr>
<tr><td><strong>创建时间</strong></td><td>{created_at}</td></tr>
<tr><td><strong>更新时间</strong></td><td>{updated_at}</td></tr>
</table>
</ac:rich-text-body>
</ac:structured-macro>

<h2>文档导航</h2>
<p>本任务的相关文档页面：</p>
<p><em>子页面链接将自动生成在此处</em></p>

<h2>快速链接</h2>
<ul>
<li><a href="/display/{metadata.get('spaceKey', 'DEV')}/DevFlow+Tasks">返回任务列表</a></li>
</ul>
"""
    
    return content


def _convert_markdown_to_confluence(markdown_content: str) -> str:
    """将Markdown内容转换为Confluence存储格式"""
    # 这是一个简化的转换器，处理常见的Markdown元素
    content = markdown_content
    
    # 标题转换
    content = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', content, flags=re.MULTILINE)
    content = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', content, flags=re.MULTILINE)
    content = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', content, flags=re.MULTILINE)
    content = re.sub(r'^#### (.*?)$', r'<h4>\1</h4>', content, flags=re.MULTILINE)
    
    # 粗体和斜体
    content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', content)
    content = re.sub(r'\*(.*?)\*', r'<em>\1</em>', content)
    
    # 代码块
    content = re.sub(r'```(\w+)?\n(.*?)\n```', 
                    r'<ac:structured-macro ac:name="code" ac:schema-version="1"><ac:parameter ac:name="language">\1</ac:parameter><ac:plain-text-body><![CDATA[\2]]></ac:plain-text-body></ac:structured-macro>', 
                    content, flags=re.DOTALL)
    
    # 行内代码
    content = re.sub(r'`(.*?)`', r'<code>\1</code>', content)
    
    # 列表转换
    content = re.sub(r'^- (.*?)$', r'<li>\1</li>', content, flags=re.MULTILINE)
    content = re.sub(r'^(\d+)\. (.*?)$', r'<li>\2</li>', content, flags=re.MULTILINE)
    
    # 包装列表项
    content = re.sub(r'(<li>.*?</li>\n?)+', r'<ul>\g<0></ul>', content, flags=re.DOTALL)
    
    # 链接转换
    content = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', content)
    
    # 段落处理
    paragraphs = content.split('\n\n')
    processed_paragraphs = []
    for para in paragraphs:
        para = para.strip()
        if para and not para.startswith('<'):
            para = f'<p>{para}</p>'
        processed_paragraphs.append(para)
    
    return '\n\n'.join(processed_paragraphs)


def _add_child_page_links(main_content: str, child_pages: List[Dict[str, str]], space_key: str) -> str:
    """在主页面中添加子页面链接"""
    links_html = "<h3>相关文档</h3>\n<ul>\n"
    
    for page in child_pages:
        page_title = page["title"]
        page_type = page.get("type", "document")
        
        # 根据类型添加图标
        icon = {
            "process_doc": "📋",
            "integration_doc": "🔗",
            "test_doc": "🧪"
        }.get(page_type, "📄")
        
        links_html += f'<li>{icon} <ac:link><ri:page ri:content-title="{page_title}" ri:space-key="{space_key}"/><ac:plain-text-link-body><![CDATA[{page_title}]]></ac:plain-text-link-body></ac:link></li>\n'
    
    links_html += "</ul>\n"
    
    # 替换占位符文本
    if "子页面链接将自动生成在此处" in main_content:
        return main_content.replace("子页面链接将自动生成在此处", links_html)
    elif "相关文档页面将在下方列出" in main_content:
        return main_content.replace("相关文档页面将在下方列出", links_html)
    else:
        # 在文档导航部分后添加
        return main_content + "\n\n" + links_html


# ---------- Jira分析与测试对比工具函数 ----------

@app.tool()
def jira_fetch_issue_with_analysis(input: JiraFetchInput) -> JiraFetchOutput:
    """拉取Jira工单及子任务信息，下载附件，为后续分析准备数据。
    
    功能特性：
    - 完整的工单信息获取（主要字段和自定义字段）
    - 子任务递归获取
    - 附件批量下载
    - 变更历史追踪（可选）
    """
    try:
        session = _get_jira_session()
        
        # 1. 获取主工单信息
        issue_url = _jira_api_url(f"issue/{input.issueKey}")
        issue_resp = session.get(issue_url, params={"expand": "changelog"} if input.includeHistory else {})
        
        if issue_resp.status_code >= 400:
            raise Exception(f"Failed to fetch issue {input.issueKey}: {issue_resp.status_code}")
            
        issue_data = issue_resp.json()
        fields = issue_data.get("fields", {})
        
        # 构建工单信息
        issue_info = JiraIssueInfo(
            key=issue_data.get("key", input.issueKey),
            summary=fields.get("summary", ""),
            description=fields.get("description", ""),
            status=fields.get("status", {}).get("name", "Unknown"),
            issueType=fields.get("issuetype", {}).get("name", "Unknown"),
            priority=fields.get("priority", {}).get("name", "Medium"),
            assignee=fields.get("assignee", {}).get("displayName") if fields.get("assignee") else None,
            reporter=fields.get("reporter", {}).get("displayName") if fields.get("reporter") else None,
            created=fields.get("created", ""),
            updated=fields.get("updated", ""),
            customFields={k: v for k, v in fields.items() if k.startswith("customfield_")}
        )
        
        subtasks = []
        attachments = []
        downloaded_files = []
        
        # 2. 获取子任务
        if input.includeSubtasks:
            subtask_links = fields.get("subtasks", [])
            for subtask_link in subtask_links:
                try:
                    subtask_key = subtask_link.get("key")
                    if subtask_key:
                        subtask_resp = session.get(_jira_api_url(f"issue/{subtask_key}"))
                        if subtask_resp.status_code < 400:
                            subtask_data = subtask_resp.json()
                            subtask_fields = subtask_data.get("fields", {})
                            
                            subtasks.append(JiraSubtask(
                                key=subtask_data.get("key", subtask_key),
                                summary=subtask_fields.get("summary", ""),
                                description=subtask_fields.get("description", ""),
                                status=subtask_fields.get("status", {}).get("name", "Unknown"),
                                assignee=subtask_fields.get("assignee", {}).get("displayName") if subtask_fields.get("assignee") else None
                            ))
                except Exception:
                    continue  # 跳过获取失败的子任务
        
        # 3. 处理附件
        if input.includeAttachments:
            attachment_list = fields.get("attachment", [])
            
            # 准备下载目录
            project_root = Path(os.getcwd())  # 默认项目根目录
            if input.attachmentPath:
                download_dir = project_root / input.attachmentPath / input.issueKey
            else:
                download_dir = project_root / "downloads" / "jira_attachments" / input.issueKey
            
            for attachment_info in attachment_list:
                try:
                    attachment = JiraAttachment(
                        id=str(attachment_info.get("id", "")),
                        filename=attachment_info.get("filename", ""),
                        size=attachment_info.get("size", 0),
                        mimeType=attachment_info.get("mimeType", ""),
                        author=attachment_info.get("author", {}).get("displayName", "Unknown"),
                        created=attachment_info.get("created", ""),
                        downloadUrl=attachment_info.get("content", "")
                    )
                    
                    # 下载附件
                    local_path = _download_jira_attachment(session, attachment_info, download_dir)
                    if local_path:
                        attachment.localPath = local_path
                        downloaded_files.append(local_path)
                    
                    attachments.append(attachment)
                    
                except Exception:
                    continue  # 跳过下载失败的附件
        
        return JiraFetchOutput(
            issueInfo=issue_info,
            subtasks=subtasks,
            attachments=attachments,
            downloadedFiles=downloaded_files
        )
        
    except Exception as e:
        # 返回基本信息，即使部分获取失败
        return JiraFetchOutput(
            issueInfo=JiraIssueInfo(
                key=input.issueKey,
                summary="Failed to fetch",
                description=f"Error: {str(e)}",
                status="Unknown",
                issueType="Unknown",
                priority="Medium",
                created="",
                updated=""
            ),
            subtasks=[],
            attachments=[],
            downloadedFiles=[]
        )

@app.tool()  
def analyze_requirements_vs_tests(input: TestAnalysisInput) -> TestAnalysisOutput:
    """分析Jira需求与现有测试用例的覆盖度，生成测试gap和推荐。
    
    分析维度：
    - 需求解析：从Jira描述和子任务中提取结构化需求
    - 测试匹配：将需求与现有测试用例进行匹配
    - 覆盖度计算：计算每个需求的测试覆盖程度
    - 缺失识别：识别测试覆盖不足的需求点
    - 智能推荐：基于需求类型推荐合适的测试用例
    """
    project_root = _resolve_project_root(input.projectRoot)
    
    # 1. 首先获取Jira信息
    jira_fetch_input = JiraFetchInput(
        issueKey=input.jiraIssueKey,
        includeSubtasks=True,
        includeAttachments=input.includeAttachments,
        attachmentPath="analysis_temp"
    )
    
    jira_data = jira_fetch_issue_with_analysis(jira_fetch_input)
    
    # 2. 解析需求
    requirements = []
    
    # 从主工单描述解析需求
    main_requirements = _parse_requirements_from_text(jira_data.issueInfo.description, "main_issue")
    requirements.extend(main_requirements)
    
    # 从子任务解析需求
    for i, subtask in enumerate(jira_data.subtasks):
        subtask_requirements = _parse_requirements_from_text(
            f"{subtask.summary}\n{subtask.description}", 
            f"subtask_{i+1}"
        )
        requirements.extend(subtask_requirements)
    
    # 从附件解析需求（如果是文本文件）
    if input.includeAttachments:
        for attachment in jira_data.attachments:
            if attachment.localPath and attachment.mimeType.startswith("text/"):
                try:
                    attachment_path = Path(attachment.localPath)
                    if attachment_path.exists():
                        attachment_content = attachment_path.read_text(encoding="utf-8")
                        attachment_requirements = _parse_requirements_from_text(
                            attachment_content, 
                            f"attachment_{attachment.filename}"
                        )
                        requirements.extend(attachment_requirements)
                except Exception:
                    continue
    
    # 3. 获取现有测试用例
    test_cases = []
    
    # 从DevFlow任务文档中获取测试用例
    process_dir = project_root / "Docs" / "ProcessDocuments" / f"task-{input.taskKey}"
    if process_dir.exists():
        # 查找测试相关文档
        test_files = [
            process_dir / f"{input.taskKey}_04-TestCurls.md",
            process_dir / f"{input.taskKey}_05-MySQLVerificationPlan.md",
            process_dir / f"{input.taskKey}_06-Integration.md",
        ]
        
        for test_file in test_files:
            if test_file.exists():
                file_test_cases = _extract_test_cases_from_file(test_file)
                test_cases.extend(file_test_cases)
    
    # 4. 计算覆盖度
    test_matches = _calculate_coverage(requirements, test_cases)
    
    # 5. 生成推荐
    recommended_tests = _generate_test_recommendations(requirements, test_matches)
    
    # 6. 计算整体覆盖度
    if test_matches:
        overall_coverage = sum(match.coverage for match in test_matches) / len(test_matches)
    else:
        overall_coverage = 0.0
    
    # 7. 识别缺失测试
    missing_tests = []
    for match in test_matches:
        if match.coverage < 0.3:  # 覆盖度低于30%的需求
            req = next((r for r in requirements if r.id == match.requirementId), None)
            if req:
                missing_tests.append(f"{req.id}: {req.title}")
    
    # 8. 生成分析报告
    report_dir = project_root / "Docs" / "ProcessDocuments" / f"task-{input.taskKey}"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{input.taskKey}_TestAnalysisReport.md"
    
    report_content = f"""---
status: DRAFT
generatedAt: {_timestamp()}
jiraIssue: {input.jiraIssueKey}
analysisType: {input.analysisType}
---

# 测试覆盖度分析报告 - {input.taskKey}

## 工单信息
- **Jira工单**: {input.jiraIssueKey}
- **标题**: {jira_data.issueInfo.summary}
- **状态**: {jira_data.issueInfo.status}
- **类型**: {jira_data.issueInfo.issueType}

## 需求分析
**总需求数**: {len(requirements)}

{chr(10).join(f"- **{req.id}** ({req.category}): {req.title}" for req in requirements)}

## 测试覆盖度
**整体覆盖度**: {overall_coverage:.1%}

### 详细覆盖情况
{chr(10).join(f"- **{match.requirementId}**: {match.coverage:.1%} 覆盖 ({len(match.testCases)} 个相关测试)" for match in test_matches)}

## 缺失分析
**缺失测试数**: {len(missing_tests)}

{chr(10).join(f"- {missing}" for missing in missing_tests)}

## 推荐测试用例
{chr(10).join(f"- {rec}" for rec in recommended_tests)}

## 附件信息
{chr(10).join(f"- **{att.filename}** ({att.mimeType}) - {att.size} bytes" for att in jira_data.attachments)}

---
*报告生成时间: {_timestamp()}*
"""
    
    report_path.write_text(report_content, encoding="utf-8")
    
    return TestAnalysisOutput(
        taskKey=input.taskKey,
        jiraIssueKey=input.jiraIssueKey,
        requirements=requirements,
        testMatches=test_matches,
        overallCoverage=overall_coverage,
        missingTests=missing_tests,
        recommendedTests=recommended_tests,
        analysisReport=str(report_path)
    )

@app.tool()
def sync_jira_requirements(input: RequirementSyncInput) -> RequirementSyncOutput:
    """将Jira需求同步到DevFlow任务，可选择自动生成测试用例。
    
    同步功能：
    - 创建或更新DevFlow任务文档
    - 同步需求描述和验收标准
    - 更新子任务状态映射
    - 可选的自动测试用例生成
    - 建立需求追溯链接
    """
    project_root = _resolve_project_root(input.projectRoot)
    
    # 1. 获取Jira数据
    jira_fetch_input = JiraFetchInput(
        issueKey=input.jiraIssueKey,
        includeSubtasks=True,
        includeAttachments=True
    )
    
    jira_data = jira_fetch_issue_with_analysis(jira_fetch_input)
    
    # 2. 确定目标任务Key
    task_key = input.targetTaskKey
    if not task_key:
        # 自动生成任务Key
        task_key = f"JIRA-{input.jiraIssueKey.replace('-', '')}"
    
    created_files = []
    updated_files = []
    generated_tests = []
    
    # 3. 创建或更新主任务文档
    if input.syncMode in ["create", "update", "merge"]:
        task_input = PrepareDocsInput(
            taskKey=task_key,
            title=f"Jira同步: {jira_data.issueInfo.summary}",
            owner="system",
            reviewers=["qa", "dev"],
            force=(input.syncMode == "create")
        )
        
        task_result = task_prepare_docs(task_input)
        if task_result:
            created_files.append(task_result.mainDocPath)
    
    # 4. 更新任务内容
    main_doc_path = project_root / "Docs" / ".tasks" / f"{task_key}.md"
    if main_doc_path.exists():
        try:
            post = frontmatter.load(main_doc_path)
            metadata = dict(post.metadata or {})
            
            # 添加Jira关联信息
            metadata["jiraIssue"] = input.jiraIssueKey
            metadata["jiraStatus"] = jira_data.issueInfo.status
            metadata["syncedAt"] = _timestamp()
            
            # 更新内容
            content_lines = [
                f"# {jira_data.issueInfo.summary}",
                "",
                "## 需求来源",
                f"- **Jira工单**: {input.jiraIssueKey}",
                f"- **状态**: {jira_data.issueInfo.status}",
                f"- **类型**: {jira_data.issueInfo.issueType}",
                f"- **优先级**: {jira_data.issueInfo.priority}",
                "",
                "## 需求描述",
                jira_data.issueInfo.description or "无详细描述",
                "",
                "## 子任务",
            ]
            
            for subtask in jira_data.subtasks:
                content_lines.append(f"- **{subtask.key}**: {subtask.summary} ({subtask.status})")
            
            if jira_data.attachments:
                content_lines.extend([
                    "",
                    "## 附件",
                ])
                for att in jira_data.attachments:
                    content_lines.append(f"- **{att.filename}** ({att.mimeType})")
            
            post.content = "\n".join(content_lines)
            post.metadata = metadata
            
            content_str = frontmatter.dumps(post)
            main_doc_path.write_text(content_str, encoding="utf-8")
            updated_files.append(str(main_doc_path))
            
        except Exception:
            pass
    
    # 5. 自动生成测试用例（如果启用）
    if input.autoGenerateTests:
        analysis_input = TestAnalysisInput(
            taskKey=task_key,
            jiraIssueKey=input.jiraIssueKey,
            analysisType="recommendation",
            includeAttachments=True,
            projectRoot=input.projectRoot
        )
        
        analysis_result = analyze_requirements_vs_tests(analysis_input)
        
        # 生成测试用例文档
        if analysis_result.recommendedTests:
            test_doc_path = project_root / "Docs" / "ProcessDocuments" / f"task-{task_key}" / f"{task_key}_RecommendedTests.md"
            test_doc_path.parent.mkdir(parents=True, exist_ok=True)
            
            test_content = f"""---
status: DRAFT
generatedAt: {_timestamp()}
source: jira_sync
---

# 推荐测试用例 - {task_key}

## 基于需求分析的测试用例推荐

{chr(10).join(f"### 测试用例 {i+1}: {test}" for i, test in enumerate(analysis_result.recommendedTests))}

## 需求覆盖度分析
- **整体覆盖度**: {analysis_result.overallCoverage:.1%}
- **需求总数**: {len(analysis_result.requirements)}
- **缺失测试**: {len(analysis_result.missingTests)}

详细分析报告: [查看报告]({analysis_result.analysisReport})
"""
            
            test_doc_path.write_text(test_content, encoding="utf-8")
            generated_tests.append(str(test_doc_path))
    
    # 6. 生成同步报告
    sync_report_path = project_root / "Docs" / "ProcessDocuments" / f"task-{task_key}" / f"{task_key}_SyncReport.md"
    sync_report_path.parent.mkdir(parents=True, exist_ok=True)
    
    sync_report_content = f"""---
status: COMPLETED
syncedAt: {_timestamp()}
---

# Jira同步报告 - {task_key}

## 同步信息
- **源Jira工单**: {input.jiraIssueKey}
- **目标任务**: {task_key}  
- **同步模式**: {input.syncMode}
- **自动生成测试**: {'是' if input.autoGenerateTests else '否'}

## 同步结果
- **创建文件**: {len(created_files)} 个
- **更新文件**: {len(updated_files)} 个
- **生成测试**: {len(generated_tests)} 个

### 详细文件清单
**创建的文件**:
{chr(10).join(f"- {f}" for f in created_files)}

**更新的文件**:
{chr(10).join(f"- {f}" for f in updated_files)}

**生成的测试**:
{chr(10).join(f"- {f}" for f in generated_tests)}

## Jira工单快照
- **标题**: {jira_data.issueInfo.summary}
- **状态**: {jira_data.issueInfo.status}
- **子任务数**: {len(jira_data.subtasks)}
- **附件数**: {len(jira_data.attachments)}

---
*同步完成时间: {_timestamp()}*
"""
    
    sync_report_path.write_text(sync_report_content, encoding="utf-8")
    
    return RequirementSyncOutput(
        taskKey=task_key,
        jiraIssueKey=input.jiraIssueKey,
        createdFiles=created_files,
        updatedFiles=updated_files,
        generatedTests=generated_tests,
        syncReport=str(sync_report_path)
    )

# ---------- 状态管理工具函数 ----------

@app.tool()
def status_query(input: StatusQueryInput) -> StatusQueryOutput:
    """查询任务的状态信息，包括当前状态、允许的转换、历史记录和统计信息。"""
    project_root = _resolve_project_root(input.projectRoot)
    task_metadata = _get_task_metadata(project_root, input.taskKey)
    current_status = _read_task_status(project_root, input.taskKey)
    
    # 获取允许的状态转换
    allowed_transitions = _STATUS_TRANSITIONS.get(current_status, [])
    
    # 获取历史记录
    history = None
    if input.includeHistory:
        history = task_metadata.get("reviews", [])
        # 按时间倒序排列
        history = sorted(history, key=lambda x: x.get("time", ""), reverse=True)
    
    # 获取统计信息
    stats = None
    if input.includeStats:
        stats = task_metadata.get("statusStats", {})
        # 添加一些派生统计
        if history:
            stats["historyCount"] = len(history)
            stats["averageTimeInStatus"] = {}  # 可以后续计算
    
    return StatusQueryOutput(
        taskKey=input.taskKey,
        currentStatus=current_status,
        allowedTransitions=allowed_transitions,
        history=history,
        stats=stats
    )

@app.tool()
def status_batch_operation(input: StatusBatchInput) -> StatusBatchOutput:
    """批量执行状态转换操作。"""
    project_root = _resolve_project_root(input.projectRoot)
    successful = []
    failed = []
    
    for i, op in enumerate(input.operations):
        try:
            # 验证操作参数
            task_key = op.get("taskKey")
            new_status = op.get("newStatus") 
            by = op.get("by")
            notes = op.get("notes", "")
            
            if not all([task_key, new_status, by]):
                raise ValueError("缺少必要参数: taskKey, newStatus, by")
            
            # 执行状态转换
            status_input = ReviewStatusInput(
                taskKey=task_key,
                newStatus=new_status,
                by=by,
                notes=notes,
                projectRoot=input.projectRoot
            )
            
            result = review_set_status(status_input)
            successful.append({
                "operation": i,
                "taskKey": task_key,
                "from": result.oldStatus,
                "to": result.newStatus,
                "by": by
            })
            
        except Exception as e:
            failed.append({
                "operation": i,
                "taskKey": op.get("taskKey", "unknown"),
                "error": str(e),
                "operation_data": op
            })
            
            if not input.continueOnError:
                break
    
    summary = {
        "total": len(input.operations),
        "successful": len(successful),
        "failed": len(failed)
    }
    
    return StatusBatchOutput(
        successful=successful,
        failed=failed,
        summary=summary
    )

@app.tool()
def status_report(input: StatusReportInput) -> StatusReportOutput:
    """生成状态报告，包括所有任务的状态统计和活动摘要。"""
    project_root = _resolve_project_root(input.projectRoot)
    tasks_dir = project_root / "Docs" / ".tasks"
    
    if not tasks_dir.exists():
        return StatusReportOutput(
            totalTasks=0,
            statusBreakdown={},
            recentActivity=[],
            blockedTasks=[],
            summary={"message": "没有找到任务目录"}
        )
    
    # 扫描所有任务文件
    task_files = list(tasks_dir.glob("*.md"))
    total_tasks = 0
    status_breakdown = {}
    recent_activity = []
    blocked_tasks = []
    
    for task_file in task_files:
        try:
            task_key = task_file.stem
            
            # 读取任务元数据
            post = frontmatter.load(task_file)
            metadata = post.metadata or {}
            current_status = metadata.get("status", "DRAFT")
            
            # 应用过滤器
            if input.statusFilter and current_status not in input.statusFilter:
                continue
                
            if input.userFilter:
                owner = metadata.get("owner", "")
                reviewers = metadata.get("reviewers", [])
                if input.userFilter not in [owner] + list(reviewers):
                    continue
            
            total_tasks += 1
            status_breakdown[current_status] = status_breakdown.get(current_status, 0) + 1
            
            # 收集最近活动
            reviews = metadata.get("reviews", [])
            if reviews:
                latest_review = max(reviews, key=lambda x: x.get("time", ""))
                recent_activity.append({
                    "taskKey": task_key,
                    "action": f"{latest_review.get('from', 'UNKNOWN')} -> {latest_review.get('to', 'UNKNOWN')}",
                    "by": latest_review.get("by", "unknown"),
                    "time": latest_review.get("time", ""),
                    "notes": latest_review.get("notes", "")
                })
            
            # 识别阻塞的任务
            if current_status == "CHANGES_REQUESTED":
                blocked_tasks.append({
                    "taskKey": task_key,
                    "status": current_status,
                    "owner": metadata.get("owner", "unknown"),
                    "lastUpdate": metadata.get("updatedAt", "unknown")
                })
                
        except Exception as e:
            # 跳过无法解析的文件
            continue
    
    # 按时间排序最近活动
    recent_activity.sort(key=lambda x: x.get("time", ""), reverse=True)
    recent_activity = recent_activity[:20]  # 只取最近20条
    
    summary = {
        "totalFiles": len(task_files),
        "validTasks": total_tasks,
        "mostCommonStatus": max(status_breakdown.items(), key=lambda x: x[1])[0] if status_breakdown else "N/A",
        "blockedCount": len(blocked_tasks),
        "recentActivityCount": len(recent_activity)
    }
    
    return StatusReportOutput(
        totalTasks=total_tasks,
        statusBreakdown=status_breakdown,
        recentActivity=recent_activity,
        blockedTasks=blocked_tasks,
        summary=summary
    )


@app.tool()
def wiki_diagnostic(input: WikiDiagnosticInput) -> WikiDiagnosticOutput:
    """诊断Wiki API连接和页面访问问题，测试不同的API路径。"""
    try:
        session = _get_wiki_session()
        base_url = os.getenv("WIKI_BASE_URL", "").rstrip("/")
        context_path = os.getenv("WIKI_CONTEXT_PATH", "").strip("/")
        
        api_tests = {}
        recommendations = []
        
        # 测试不同的API路径，基于您提供的API结构
        test_paths = [
            f"{base_url}/rest/api/content/{input.pageId}",
            f"{base_url}/rest/api/1.0/content/{input.pageId}",
            f"{base_url}/rest/api/2.0/content/{input.pageId}",
            f"{base_url}/rest/tinymce/1/content/{input.pageId}",
            f"{base_url}/rest/tinymce/1.0/content/{input.pageId}",
            f"{base_url}/rest/prototype/1/content/{input.pageId}",
        ]
        
        if context_path:
            test_paths.extend([
                f"{base_url}/{context_path}/rest/api/content/{input.pageId}",
                f"{base_url}/{context_path}/rest/api/1/content/{input.pageId}",
                f"{base_url}/{context_path}/rest/tinymce/1/content/{input.pageId}",
            ])
        
        # 测试每个API路径
        for path in test_paths:
            try:
                params = {"expand": "body.storage,version,space"}
                resp = session.get(path, params=params, timeout=10)
                
                api_tests[path] = {
                    "status_code": resp.status_code,
                    "success": resp.status_code < 400,
                    "response_size": len(resp.text),
                    "content_type": resp.headers.get("content-type", ""),
                    "error": None if resp.status_code < 400 else resp.text[:200]
                }
                
                # 如果成功，记录页面信息
                if resp.status_code < 400:
                    try:
                        data = resp.json()
                        api_tests[path]["page_title"] = data.get("title", "")
                        api_tests[path]["page_type"] = data.get("type", "")
                        api_tests[path]["space_key"] = data.get("space", {}).get("key", "")
                    except:
                        pass
                        
            except Exception as e:
                api_tests[path] = {
                    "status_code": 0,
                    "success": False,
                    "error": str(e)[:200]
                }
        
        # 分析结果并给出建议
        successful_apis = [path for path, result in api_tests.items() if result.get("success")]
        
        if successful_apis:
            recommendations.append(f"✅ 发现可用的API路径: {successful_apis[0]}")
            
            # 确定正确的API版本
            if "/rest/api/content/" in successful_apis[0]:
                recommendations.append("🔧 建议设置 WIKI_API_VERSION=''（空字符串）")
            elif "/rest/api/1/" in successful_apis[0]:
                recommendations.append("🔧 建议设置 WIKI_API_VERSION='1'")
            elif "/rest/tinymce/" in successful_apis[0]:
                recommendations.append("🔧 系统主要使用TinyMCE API，REST API作为备用")
                
        else:
            recommendations.append("❌ 所有API路径都失败了")
            recommendations.append("🔍 请检查:")
            recommendations.append("  - WIKI_BASE_URL是否正确")
            recommendations.append("  - 页面ID是否存在")
            recommendations.append("  - 用户权限是否足够")
            recommendations.append("  - 网络连接是否正常")
        
        # 测试多种评论API
        comment_test_urls = [
            f"{base_url}/rest/tinymce/1/content/{input.pageId}/comment",
            f"{base_url}/rest/tinymce/1.0/content/{input.pageId}/comment", 
            f"{base_url}/rest/api/content/{input.pageId}/child/comment",
            f"{base_url}/rest/api/1.0/content/{input.pageId}/child/comment",
        ]
        
        if context_path:
            comment_test_urls.extend([
                f"{base_url}/{context_path}/rest/tinymce/1/content/{input.pageId}/comment",
                f"{base_url}/{context_path}/rest/tinymce/1.0/content/{input.pageId}/comment",
                f"{base_url}/{context_path}/rest/api/content/{input.pageId}/child/comment",
                f"{base_url}/{context_path}/rest/api/1.0/content/{input.pageId}/child/comment",
            ])
        
        # 测试每个评论API
        working_comment_apis = []
        for comment_url in comment_test_urls:
            try:
                resp = session.get(comment_url, timeout=10)
                api_tests[f"comment_api_{len(api_tests)}"] = {
                    "url": comment_url,
                    "status_code": resp.status_code,
                    "success": resp.status_code < 400,
                    "note": "评论API测试"
                }
                
                if resp.status_code < 400:
                    working_comment_apis.append(comment_url)
                elif resp.status_code == 501:
                    api_tests[f"comment_api_{len(api_tests)-1}"]["note"] += " (501 Not Implemented)"
                    
            except Exception as e:
                api_tests[f"comment_api_{len(api_tests)}"] = {
                    "url": comment_url,
                    "error": str(e)[:200],
                    "success": False,
                    "note": "评论API测试异常"
                }
        
        # 评论API建议
        if working_comment_apis:
            recommendations.append(f"✅ 找到可用的评论API: {working_comment_apis[0]}")
        else:
            recommendations.append("❌ 所有评论API都返回501错误")
            recommendations.append("💡 可能的解决方案:")
            recommendations.append("  - 检查用户是否有评论权限")
            recommendations.append("  - 确认页面是否允许评论")
            recommendations.append("  - 尝试不同的API版本或端点")
            recommendations.append("  - 联系管理员检查服务器配置")
        
        return WikiDiagnosticOutput(
            pageId=input.pageId,
            apiTests=api_tests,
            recommendations=recommendations,
            hint=f"测试了{len(test_paths)}个API路径，找到{len(successful_apis)}个可用路径"
        )
        
    except Exception as e:
        return WikiDiagnosticOutput(
            pageId=input.pageId,
            apiTests={},
            recommendations=[f"诊断过程出错: {str(e)}"],
            hint=f"Wiki诊断失败: {str(e)}"
        )

if __name__ == "__main__":
    # 以 stdio 方式启动 MCP（FastMCP 会处理协议细节）
    app.run()
