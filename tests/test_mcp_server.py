"""招聘大数据 MCP 服务离线测试。"""

import asyncio
import importlib.util
import os
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch


SERVER_PATH = Path(__file__).parents[1] / "server" / "mcp_server.py"
SPEC = importlib.util.spec_from_file_location("recruitment_mcp_server", SERVER_PATH)
assert SPEC and SPEC.loader
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


class GatewayTests(TestCase):
    def test_missing_credentials_prevents_http_request(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(server.requests, "post") as post,
        ):
            result = server.call_api("product", {})
        self.assertEqual(result, {"error": "INTEGRATOR_ID 未配置"})
        post.assert_not_called()

    def test_gateway_extracts_data(self) -> None:
        response = Mock(status_code=200)
        response.json.return_value = {"data": {"total": 0, "resultList": []}}
        credentials = {
            "INTEGRATOR_ID": "integrator",
            "SECRET_ID": "secret-id",
            "SECRET_KEY": "secret-key",
        }
        with (
            patch.dict(os.environ, credentials, clear=True),
            patch.object(server.requests, "post", return_value=response) as post,
        ):
            result = server.call_api("product", {"pageIndex": 1})
        self.assertEqual(result, {"total": 0, "resultList": []})
        self.assertEqual(post.call_count, 1)


class ToolTests(TestCase):
    def test_registered_tool_names(self) -> None:
        tools = asyncio.run(server.mcp.list_tools())
        self.assertEqual(
            {tool.name for tool in tools},
            {
                "recruitment_enterprise_search",
                "recruitment_job_search",
                "recruitment_employer_profile",
                "recruitment_demand_analysis",
                "recruitment_salary",
                "recruitment_trend",
            },
        )
        for tool in tools:
            self.assertEqual(tool.outputSchema.get("type"), "object")
            self.assertTrue(tool.annotations.readOnlyHint)
            self.assertFalse(tool.annotations.destructiveHint)

    def test_enterprise_search_resolves_abbreviated_company_names(self) -> None:
        with patch.object(
            server,
            "call_api",
            return_value={"total": 1, "resultList": [{"name": "企业A全称"}]},
        ) as call:
            result = server.recruitment_enterprise_search("企业A", pageSize=5)
        self.assertEqual(result["total"], 1)
        call.assert_called_once_with(
            server.PRODUCT_IDS["enterprise_search"],
            {"matchKeyword": "企业A", "pageIndex": 1, "pageSize": 5},
        )

        with patch.object(server, "call_api") as call:
            invalid = server.recruitment_enterprise_search("企业A", pageSize=51)
        self.assertEqual(invalid["parameter"], "pageSize")
        call.assert_not_called()

    def test_job_search_and_salary_reuse_details(self) -> None:
        expected_params = {
            "matchKeyword": "企业A",
            "keywordType": "name",
            "pageIndex": 1,
            "pageSize": 50,
        }
        for function in (
            server.recruitment_job_search,
            server.recruitment_salary,
        ):
            with self.subTest(function=function.__name__):
                with patch.object(server, "call_api", return_value={}) as call:
                    function("企业A")
                call.assert_called_once_with(
                    server.PRODUCT_IDS["recruitment_details"],
                    expected_params,
                )

    def test_sensitive_recruitment_source_fields_are_removed(self) -> None:
        upstream = {
            "total": 1,
            "recruitingSources": ["sensitive-summary-source"],
            "resultList": [
                {
                    "recruitingName": "测试岗位",
                    "recruitingSource": "sensitive-detail-source",
                    "nested": {
                        "recruitmentSource": "sensitive-nested-source",
                    },
                }
            ],
        }
        with patch.object(server, "call_api", return_value=upstream):
            result = server.recruitment_job_search("企业A")

        self.assertEqual(
            result,
            {
                "total": 1,
                "resultList": [
                    {
                        "recruitingName": "测试岗位",
                        "nested": {},
                    }
                ],
            },
        )

    def test_profile_and_trend_reuse_statistics(self) -> None:
        statistics = {
            "benefitList": ["福利1", "福利2", "福利3"],
            "recruitingCities": ["城市1", "城市2", "城市3"],
            "recruitingCurrentCount": 10,
            "recruitingLastThreeMonthCount": 30,
            "recruitingLastThreeMonthNo": 5,
            "recruitingAvgUpdate": 7,
            "recruitingAvgWorkingSalary": 12000,
        }
        with patch.object(
            server,
            "call_api",
            return_value=statistics,
        ) as call:
            profile = server.recruitment_employer_profile(
                "企业A",
                listLimit=2,
            )
        self.assertEqual(profile["benefitList"], ["福利1", "福利2"])
        self.assertEqual(profile["recruitingCities"], ["城市1", "城市2"])
        self.assertEqual(
            profile["truncatedFields"]["recruitingCities"],
            {"total": 3, "returned": 2},
        )
        call.assert_called_once_with(
            server.PRODUCT_IDS["recruitment_statistics"],
            {"matchKeyword": "企业A", "keywordType": "name"},
        )

        with patch.object(
            server,
            "call_api",
            return_value=statistics,
        ) as call:
            trend = server.recruitment_trend("企业A")
        self.assertEqual(
            trend,
            {
                "recruitingCurrentCount": 10,
                "recruitingLastThreeMonthCount": 30,
                "recruitingLastThreeMonthNo": 5,
                "recruitingAvgUpdate": 7,
                "recruitingAvgWorkingSalary": 12000,
            },
        )
        call.assert_called_once_with(
            server.PRODUCT_IDS["recruitment_statistics"],
            {"matchKeyword": "企业A", "keywordType": "name"},
        )

    def test_demand_analysis_selects_one_view(self) -> None:
        with patch.object(server, "call_api", return_value={}) as call:
            server.recruitment_demand_analysis("企业A")
        call.assert_called_once_with(
            server.PRODUCT_IDS["recruitment_statistics"],
            {"matchKeyword": "企业A", "keywordType": "name"},
        )

        with patch.object(server, "call_api", return_value={}) as call:
            server.recruitment_demand_analysis("企业A", view="details")
        call.assert_called_once_with(
            server.PRODUCT_IDS["recruitment_details"],
            {
                "matchKeyword": "企业A",
                "keywordType": "name",
                "pageIndex": 1,
                "pageSize": 50,
            },
        )

    def test_pagination_validation(self) -> None:
        with patch.object(server, "call_api") as call:
            result = server.recruitment_job_search("企业A", pageIndex=0)
        self.assertEqual(result["parameter"], "pageIndex")
        call.assert_not_called()

    def test_list_limit_validation(self) -> None:
        for function in (
            server.recruitment_employer_profile,
            server.recruitment_demand_analysis,
        ):
            with self.subTest(function=function.__name__):
                with patch.object(server, "call_api") as call:
                    result = function("企业A", listLimit=201)
                self.assertEqual(result["parameter"], "listLimit")
                call.assert_not_called()


class DocumentationTests(TestCase):
    def test_readme_documents_enterprise_search_first(self) -> None:
        readme = (SERVER_PATH.parents[1] / "README.md").read_text(encoding="utf-8")
        self.assertIn("`recruitment_enterprise_search`", readme)
        self.assertIn("`675cea1f0e009a9ea37edaa1`", readme)
        self.assertIn("企业简称无法直接查询时", readme)

    def test_public_tool_docs_do_not_describe_recruitment_sources(self) -> None:
        readme = (SERVER_PATH.parents[1] / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("招聘来源", readme)
        self.assertNotIn("招聘渠道", readme)

        tools = asyncio.run(server.mcp.list_tools())
        public_descriptions = "\n".join(tool.description or "" for tool in tools)
        self.assertNotIn("招聘来源", public_descriptions)
        self.assertNotIn("招聘渠道", public_descriptions)
