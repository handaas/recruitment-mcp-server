# 招聘大数据服务

[该 MCP 服务提供企业关键词搜索、职位检索、雇主招聘画像、人才需求、职位薪酬和招聘趋势分析能力，帮助用户开展人才市场研究、雇主分析和招聘决策。](https://www.handaas.com/)

## 主要功能

- 🏢 企业简称与关键词搜索
- 🔍 企业招聘职位检索
- 🏢 雇主招聘画像分析
- 👥 企业人才需求分析
- 💰 招聘职位薪酬查询
- 📈 企业招聘趋势概览

## 服务设计说明

- 服务按实际业务场景提供 6 个 Tool，不按上游 API 数量平铺工具。
- 用户只提供企业简称时，先用 `recruitment_enterprise_search` 获取企业全称或稳定 ID。
- 招聘明细和招聘统计两个 Product ID 由不同场景 Tool 复用。
- `recruitment_demand_analysis` 通过 `view` 选择明细或统计，单次只访问一个 Product ID。
- 翻页结果的业务外层只包含 `total` 与 `resultList`，`pageSize` 最大为 50。
- 画像和统计中的长列表通过 `listLimit` 限制，默认 50，最大 200。
- `recruitment_trend` 只返回招聘数量、近三月统计、更新频率和平均薪资，避免重复返回画像长列表。

## 环境要求

- Python 3.10+
- 依赖包：python-dotenv、requests、mcp

## 本地快速启动

### 1. 进入项目目录

```bash
cd recruitment-mcp-server
```

### 2. 创建虚拟环境并安装依赖

```bash
python3 -m venv mcp_env
source mcp_env/bin/activate
pip install -r requirements.txt
```

### 3. 配置环境变量

复制环境变量模板：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
INTEGRATOR_ID=your_integrator_id
SECRET_ID=your_secret_id
SECRET_KEY=your_secret_key
HANDAAS_REQUEST_TIMEOUT=30
```

`HANDAAS_REQUEST_TIMEOUT` 为可选配置，单位为秒，默认值为 30。

### 4. 启动 Streamable HTTP 服务

```bash
python server/mcp_server.py streamable-http
```

服务默认地址为 `http://localhost:8000/mcp`。

也可以使用启动脚本：

```bash
./start_mcp_server.sh streamable-http
```

支持 `stdio`、`sse` 和 `streamable-http` 三种启动方式。

### 5. Cursor / Cherry Studio MCP 配置

```json
{
  "mcpServers": {
    "recruitment-mcp-server": {
      "type": "streamableHttp",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

## STDIO 版安装部署

将 `{workdir}` 替换为 `recruitment-mcp-server` 的绝对路径：

```json
{
  "mcpServers": {
    "recruitment-mcp-server": {
      "command": "{workdir}/mcp_env/bin/python",
      "args": [
        "{workdir}/server/mcp_server.py",
        "stdio"
      ]
    }
  }
}
```

`INTEGRATOR_ID`、`SECRET_ID` 和 `SECRET_KEY` 需要登录 [HandaaS](https://www.handaas.com/) 注册并开通对接器后获取。真实凭据只应保存在本地 `.env` 或部署密钥中。

## 可用工具与 Product ID

| MCP Tool | 功能或视图 | Product ID |
|---|---|---|
| `recruitment_enterprise_search` | 企业简称、品牌或产品关键词查询企业 | `675cea1f0e009a9ea37edaa1` |
| `recruitment_job_search` | 企业招聘职位明细 | `66b338e274bf098447db7f09` |
| `recruitment_employer_profile` | 企业招聘画像与统计 | `66b338e274bf098447db7f1b` |
| `recruitment_demand_analysis` | `view=details` 人才需求明细 | `66b338e274bf098447db7f09` |
| `recruitment_demand_analysis` | `view=statistics` 人才需求统计 | `66b338e274bf098447db7f1b` |
| `recruitment_salary` | 职位薪酬范围明细 | `66b338e274bf098447db7f09` |
| `recruitment_trend` | 招聘数量、近三月统计、更新频率和平均薪资 | `66b338e274bf098447db7f1b` |

### 1. recruitment_enterprise_search

**功能**：按企业简称、品牌、产品或其他关键词搜索候选企业。

**主要参数**：`matchKeyword` 必需；`pageIndex` 默认 1；`pageSize` 默认 10、最大 50。

**返回**：候选企业 `total/resultList`。确认候选后，把企业全称、企业 ID 或统一社会信用代码传给招聘 Tool。

### 2. recruitment_job_search

**功能**：查询指定企业的招聘职位明细。

**主要参数**：

- `matchKeyword`（必需）：企业名称、企业 ID、注册号或统一社会信用代码。
- `keywordType`（可选）：企业标识类型，支持 `name`、`nameId`、`regNumber`、`socialCreditCode`。
- `pageIndex`（可选）：页码，从 1 开始。
- `pageSize`（可选）：每页数量，默认 50，最大 50。

**返回**：`total` 和 `resultList`；职位明细可包含职位名称、城市、学历、薪酬、工作年限、发布时间和工作地址等字段。

### 3. recruitment_employer_profile

**功能**：查询企业招聘画像，包括福利、招聘城市、岗位关键词和平均薪资。

**主要参数**：

- `matchKeyword`（必需）：企业名称、企业 ID、注册号或统一社会信用代码。
- `keywordType`（可选）：企业标识类型。
- `listLimit`（可选）：画像列表字段最多返回多少项，默认 50，最大 200。

**返回**：企业招聘统计和画像；发生列表截断时返回 `truncatedFields`。

### 4. recruitment_demand_analysis

**功能**：分析企业人才需求，可选择岗位明细或企业统计视图。

**主要参数**：

- `matchKeyword`（必需）：企业标识。
- `view`（可选）：`details` 岗位明细；`statistics` 企业统计。默认 `statistics`。
- `keywordType`（可选）：企业标识类型。
- `pageIndex`、`pageSize`（可选）：仅 `details` 视图使用，`pageSize` 最大为 50。
- `listLimit`（可选）：仅 `statistics` 视图使用，默认 50，最大 200。

**返回**：明细视图返回 `total` 和 `resultList`；统计视图返回企业招聘画像和统计字段。

### 5. recruitment_salary

**功能**：查询企业招聘职位的薪酬范围，用于岗位和人才市场薪酬比较。

**主要参数**：

- `matchKeyword`（必需）：企业名称、企业 ID、注册号或统一社会信用代码。
- `keywordType`（可选）：企业标识类型。
- `pageIndex`（可选）：页码，从 1 开始。
- `pageSize`（可选）：每页数量，默认 50，最大 50。

**返回**：`total` 和 `resultList`；`workingSalary` 可包含币种、最低薪酬和最高薪酬。

### 6. recruitment_trend

**功能**：查询企业招聘趋势概览，不返回逐月时间序列。

**主要参数**：

- `matchKeyword`（必需）：企业名称、企业 ID、注册号或统一社会信用代码。
- `keywordType`（可选）：企业标识类型。

**返回**：

- `recruitingCurrentCount`：当前招聘人数。
- `recruitingLastThreeMonthCount`：近三月招聘人数。
- `recruitingLastThreeMonthNo`：近三月招聘岗位数。
- `recruitingAvgUpdate`：岗位平均更新频率。
- `recruitingAvgWorkingSalary`：平均招聘薪资。

## 使用场景

1. **企业定位**：通过简称或品牌词确认企业全称与稳定标识。
2. **人才需求研究**：查看目标企业正在招聘的岗位和人才方向。
3. **雇主分析**：了解企业招聘城市、福利、岗位关键词和招聘活跃度。
4. **薪酬比较**：比较不同企业或岗位的薪酬区间。
5. **招聘趋势判断**：分析当前及近三月招聘规模和平均更新频率。
6. **竞争情报**：从招聘需求变化判断企业业务扩张方向。

## 使用注意事项

1. **简称处理**：企业简称无法直接查询时，先调用 `recruitment_enterprise_search`。
2. **企业标识**：确认候选后，建议使用企业 ID 或统一社会信用代码。
3. **分页限制**：`pageIndex` 从 1 开始，`pageSize` 必须在 1 到 50 之间。
4. **列表限制**：`listLimit` 必须在 1 到 200 之间。
5. **视图选择**：需要岗位记录时使用 `view=details`；需要汇总画像时使用 `view=statistics`。
6. **趋势口径**：`recruitment_trend` 是当前和近三月概览，不是逐月时间序列。

## 使用提问示例

### recruitment_enterprise_search（企业关键词搜索）

1. “小米”对应哪家企业？
2. 通过“京东”查找准确企业名称和企业 ID。

### recruitment_job_search（招聘职位检索）

1. 小米科技有限责任公司目前在招哪些职位？
2. 查询北京京东世纪贸易有限公司最近的招聘岗位。

### recruitment_employer_profile（雇主招聘画像）

1. 分析小米科技有限责任公司的招聘城市、福利和岗位画像。
2. 珠海格力电器股份有限公司的平均招聘薪资怎么样？

### recruitment_demand_analysis（招聘需求分析）

1. 汇总某企业的人才需求结构。
2. 列出目标企业的具体岗位需求。

### recruitment_salary（职位薪酬查询）

1. 查看小米科技有限责任公司招聘职位的薪酬区间。
2. 珠海格力电器股份有限公司的岗位薪资水平如何？

### recruitment_trend（招聘趋势概览）

1. 小米科技有限责任公司当前招聘热度和近三月趋势怎样？
2. 查询京东近期招聘人数、岗位数和平均薪资。

## 测试验证

```bash
python -m py_compile server/mcp_server.py
python -m unittest discover -s tests -v
```

单元测试使用 Mock HTTP 响应，不调用真实 HandaaS 招聘接口。
