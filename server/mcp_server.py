"""HandaaS 招聘大数据 MCP 服务。"""

import json
import os
import sys
from hashlib import md5
from typing import Any, Literal
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations


load_dotenv()

mcp = FastMCP(
    "企业用人需求洞察",
    instructions=(
        "面向企业简称解析、职位检索、雇主招聘画像、人才需求、薪酬和招聘趋势分析。"
        "同一 Product ID 可由不同场景工具复用，但单次调用只访问一个上游接口。"
    ),
    dependencies=["python-dotenv", "requests"],
)

GATEWAY_BASE_URL = "https://console.handaas.com/api/v1/integrator/call_api"
DEFAULT_TIMEOUT_SECONDS = 30.0

PRODUCT_IDS = {
    "enterprise_search": "675cea1f0e009a9ea37edaa1",
    "recruitment_details": "66b338e274bf098447db7f09",
    "recruitment_statistics": "66b338e274bf098447db7f1b",
}

KeywordType = Literal["name", "nameId", "regNumber", "socialCreditCode"]
READ_ONLY_TOOL = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)
SENSITIVE_RECRUITMENT_SOURCE_FIELDS = frozenset(
    {
        "recruitingSource",
        "recruitingSources",
        "recruitmentSource",
        "recruitmentSources",
    }
)


def _request_timeout() -> float:
    """读取请求超时配置，非法值回退为默认值。"""
    raw_value = os.environ.get("HANDAAS_REQUEST_TIMEOUT", "")
    try:
        value = float(raw_value) if raw_value else DEFAULT_TIMEOUT_SECONDS
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_TIMEOUT_SECONDS


def _credential(name: str) -> str | None:
    """读取并清理认证配置。"""
    value = os.environ.get(name, "").strip()
    if not value or value.startswith("your_"):
        return None
    return value


def _build_signature(call_params: dict[str, str], secret_key: str) -> str:
    """按 HandaaS Integrator Gateway 规则生成 MD5 签名。"""
    plain_text = "".join(str(call_params[key]) for key in sorted(call_params))
    return md5(f"{plain_text}{secret_key}".encode("utf-8")).hexdigest()


def _compact_params(params: dict[str, Any]) -> dict[str, Any]:
    """移除未提供的可选参数。"""
    return {key: value for key, value in params.items() if value is not None}


def _pagination_error(page_index: int, page_size: int) -> dict[str, Any] | None:
    """校验 HandaaS 分页公共约束。"""
    if page_index < 1:
        return {"error": "pageIndex 必须大于等于 1", "parameter": "pageIndex"}
    if page_size < 1 or page_size > 50:
        return {
            "error": "pageSize 必须在 1 到 50 之间",
            "parameter": "pageSize",
        }
    return None


def _list_limit_error(list_limit: int) -> dict[str, Any] | None:
    """校验画像类列表字段的返回上限。"""
    if list_limit < 1 or list_limit > 200:
        return {
            "error": "listLimit 必须在 1 到 200 之间",
            "parameter": "listLimit",
        }
    return None


def _limit_list_fields(result: Any, list_limit: int) -> Any:
    """限制超长画像列表，并显式记录被截断字段。"""
    if not isinstance(result, dict) or "error" in result:
        return result
    normalized = dict(result)
    truncated_fields: dict[str, dict[str, int]] = {}
    for key, value in result.items():
        if isinstance(value, list) and len(value) > list_limit:
            normalized[key] = value[:list_limit]
            truncated_fields[key] = {
                "total": len(value),
                "returned": list_limit,
            }
    if truncated_fields:
        normalized["truncatedFields"] = truncated_fields
    return normalized


def _remove_sensitive_recruitment_source_fields(value: Any) -> Any:
    """递归移除不应由 MCP 暴露的敏感字段。"""
    if isinstance(value, dict):
        return {
            key: _remove_sensitive_recruitment_source_fields(child)
            for key, child in value.items()
            if key not in SENSITIVE_RECRUITMENT_SOURCE_FIELDS
        }
    if isinstance(value, list):
        return [
            _remove_sensitive_recruitment_source_fields(child)
            for child in value
        ]
    return value


def call_api(product_id: str, params: dict[str, Any]) -> Any:
    """
    调用 HandaaS Integrator Gateway，并返回响应中的 data。

    不向调用方泄露密钥、签名、网关响应正文或底层网络异常详情。
    """
    integrator_id = _credential("INTEGRATOR_ID")
    secret_id = _credential("SECRET_ID")
    secret_key = _credential("SECRET_KEY")

    if not integrator_id:
        return {"error": "INTEGRATOR_ID 未配置"}
    if not secret_id:
        return {"error": "SECRET_ID 未配置"}
    if not secret_key:
        return {"error": "SECRET_KEY 未配置"}
    if not product_id:
        return {"error": "Product ID 不能为空"}

    call_params = {
        "product_id": product_id,
        "secret_id": secret_id,
        "params": json.dumps(
            _compact_params(params),
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }
    call_params["signature"] = _build_signature(call_params, secret_key)
    url = f"{GATEWAY_BASE_URL}/{quote(integrator_id, safe='')}"

    try:
        response = requests.post(
            url,
            data=call_params,
            timeout=_request_timeout(),
        )
    except requests.RequestException:
        return {"error": "HandaaS 网关请求失败，请稍后重试"}

    if response.status_code != 200:
        return {
            "error": "HandaaS 网关返回非成功状态",
            "statusCode": response.status_code,
        }

    try:
        payload = response.json()
    except (ValueError, requests.exceptions.JSONDecodeError):
        return {"error": "HandaaS 网关返回了无法解析的响应"}

    if not isinstance(payload, dict):
        return {"error": "HandaaS 网关返回格式异常"}
    if "data" in payload:
        return payload["data"]

    message = payload.get("msgCN") or payload.get("message") or "HandaaS 网关未返回 data"
    error = {"error": message}
    if payload.get("code") is not None:
        error["code"] = payload["code"]
    return error


def _recruitment_details(
    match_keyword: str,
    keyword_type: KeywordType,
    page_index: int,
    page_size: int,
) -> Any:
    """复用招聘明细 API。"""
    if error := _pagination_error(page_index, page_size):
        return error
    return _remove_sensitive_recruitment_source_fields(
        call_api(
            PRODUCT_IDS["recruitment_details"],
            {
                "matchKeyword": match_keyword,
                "keywordType": keyword_type,
                "pageIndex": page_index,
                "pageSize": page_size,
            },
        )
    )


def _recruitment_statistics(
    match_keyword: str,
    keyword_type: KeywordType,
) -> Any:
    """复用招聘统计 API。"""
    return _remove_sensitive_recruitment_source_fields(
        call_api(
            PRODUCT_IDS["recruitment_statistics"],
            {"matchKeyword": match_keyword, "keywordType": keyword_type},
        )
    )


@mcp.tool(title="关键词查询企业", annotations=READ_ONLY_TOOL)
def recruitment_enterprise_search(
    matchKeyword: str,
    pageIndex: int = 1,
    pageSize: int = 10,
) -> dict[str, Any]:
    """
    按企业简称、品牌、产品或其他关键词查询候选企业。

    用户只提供简称时先调用本工具，再将候选企业的全称、企业 ID
    或统一社会信用代码传给招聘职位、画像、薪酬或趋势 Tool。

    返回:
    - total: 候选企业总数。
    - resultList: 企业名称、企业 ID、统一社会信用代码及基础信息。
    """
    if error := _pagination_error(pageIndex, pageSize):
        return error
    return call_api(
        PRODUCT_IDS["enterprise_search"],
        {
            "matchKeyword": matchKeyword,
            "pageIndex": pageIndex,
            "pageSize": pageSize,
        },
    )


@mcp.tool(title="招聘职位检索", annotations=READ_ONLY_TOOL)
def recruitment_job_search(
    matchKeyword: str,
    keywordType: KeywordType = "name",
    pageIndex: int = 1,
    pageSize: int = 50,
) -> dict[str, Any]:
    """
    查询指定企业的招聘职位明细。

    参数:
    - matchKeyword: 企业名称、企业 ID、注册号或统一社会信用代码。
    - keywordType: matchKeyword 的主体类型。
    - pageIndex: 页码，从 1 开始。
    - pageSize: 每页数量，最大 50。

    返回:
    - total: 招聘总数。
    - resultList: 职位名称、城市、学历、薪酬、工作年限、渠道等职位明细。
    """
    return _recruitment_details(matchKeyword, keywordType, pageIndex, pageSize)


@mcp.tool(title="雇主招聘画像", annotations=READ_ONLY_TOOL)
def recruitment_employer_profile(
    matchKeyword: str,
    keywordType: KeywordType = "name",
    listLimit: int = 50,
) -> dict[str, Any]:
    """
    查询企业招聘画像，包括福利、招聘城市、岗位关键词和平均薪资。

    参数:
    - matchKeyword: 企业名称、企业 ID、注册号或统一社会信用代码。
    - keywordType: matchKeyword 的主体类型。
    - listLimit: 城市、业务标签等列表字段最多返回多少项，默认 50，最大 200。
    """
    if error := _list_limit_error(listLimit):
        return error
    return _limit_list_fields(
        _recruitment_statistics(matchKeyword, keywordType),
        listLimit,
    )


@mcp.tool(title="招聘需求分析", annotations=READ_ONLY_TOOL)
def recruitment_demand_analysis(
    matchKeyword: str,
    view: Literal["details", "statistics"] = "statistics",
    keywordType: KeywordType = "name",
    pageIndex: int = 1,
    pageSize: int = 50,
    listLimit: int = 50,
) -> dict[str, Any]:
    """
    分析企业人才需求，可选择职位明细或招聘统计视图。

    参数:
    - matchKeyword: 企业标识。
    - view: details=岗位级需求；statistics=企业汇总需求。
    - keywordType: matchKeyword 的主体类型。
    - pageIndex/pageSize: details 视图的分页参数。
    - listLimit: statistics 视图列表字段返回上限，默认 50，最大 200。

    说明:
    - 单次调用只访问所选视图对应的一个 Product ID，避免隐式双倍调用。
    """
    if view == "details":
        return _recruitment_details(matchKeyword, keywordType, pageIndex, pageSize)
    if error := _list_limit_error(listLimit):
        return error
    return _limit_list_fields(
        _recruitment_statistics(matchKeyword, keywordType),
        listLimit,
    )


@mcp.tool(title="职位薪酬查询", annotations=READ_ONLY_TOOL)
def recruitment_salary(
    matchKeyword: str,
    keywordType: KeywordType = "name",
    pageIndex: int = 1,
    pageSize: int = 50,
) -> dict[str, Any]:
    """
    查询企业职位薪酬明细，用于岗位和人才市场薪酬比较。

    返回翻页结果 total 与 resultList；resultList 中的 workingSalary
    包含币种、最低薪酬和最高薪酬。
    """
    return _recruitment_details(matchKeyword, keywordType, pageIndex, pageSize)


@mcp.tool(title="招聘趋势概览", annotations=READ_ONLY_TOOL)
def recruitment_trend(
    matchKeyword: str,
    keywordType: KeywordType = "name",
) -> dict[str, Any]:
    """
    查询企业招聘趋势概览，而非逐月时间序列。

    仅返回当前招聘人数、近三月招聘人数与岗位数、岗位平均更新频率
    和平均薪资，避免重复返回画像类长列表。
    """
    result = _recruitment_statistics(matchKeyword, keywordType)
    if not isinstance(result, dict) or "error" in result:
        return result
    fields = (
        "recruitingCurrentCount",
        "recruitingLastThreeMonthCount",
        "recruitingLastThreeMonthNo",
        "recruitingAvgUpdate",
        "recruitingAvgWorkingSalary",
    )
    return {field: result.get(field) for field in fields}


def main(argv: list[str] | None = None) -> int:
    """启动 MCP 服务。"""
    arguments = sys.argv[1:] if argv is None else argv
    transport = arguments[0] if arguments else "stdio"
    if transport not in {"stdio", "sse", "streamable-http"}:
        print(
            "启动方式必须是 stdio、sse 或 streamable-http",
            file=sys.stderr,
        )
        return 2
    mcp.run(transport=transport)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
