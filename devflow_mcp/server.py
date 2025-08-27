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

if __name__ == "__main__":
    # 以 stdio 方式启动 MCP（FastMCP 会处理协议细节）
    app.run()
