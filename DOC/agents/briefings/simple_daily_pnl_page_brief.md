# Simple Daily PnL（简易日盈亏）页面 — Costing Fullstack 闭环派单

> 派单时间（北京时间 GMT+8）：2026-05-15
> 派单 Hub Agent：Planner-Optimization
> 执行 Agent：Costing Fullstack Agent（**完整自主权**，单 commit 闭环；按 `task_distribution_standard.md §0.2`）
> 工作量预算：~1.6 人日（实际单 session 闭环即可）

## 1. 背景与价值（一句话）

老板看了「电商税负下低毛利经营应对报告」（`DOC/基础表单/电商税负下低毛利经营应对报告.md`），核心诉求：**昨天发了多少单、哪个赚哪个亏，按单笔税后贡献排个名**。
现有 `/costing/insights/models` 已经按发货完成时间归属期算到了 `revenue / cost / refund_amount / gross_margin`，但**没扣运营成本**（推广/扣点/税/人工/场地快递）。本任务：复刻一份简化版页面 `/costing/insights/daily-pnl`，加 5 个运营参数 + 兜底成本比，让运营在同一规则下看到真税后贡献。
**不重建、不新建表、不动 40 万商品同步流程、不动现有 4 个 Insights 页**。

## 2. 已有资产（一行不改可复用）

| 资产 | 路径 | 给我们什么 |
|---|---|---|
| 模型聚合 API | `GET /api/planner/analytics/model-insights/summary` | `revenue_amount / cost_amount / refund_amount / cost_quality / shipped_qty / returned_qty` 已含真退款 |
| 模型详情 API | `GET /api/planner/analytics/model-insights/detail` | 版本/最终BOM/工序/扣库单 |
| SKU 排名 API | `GET /api/planner/analytics/sales/profit-dashboard?top_n=100` | Top 赚/亏 货品/模型 |
| 行级明细 API | `GET /api/planner/analytics/sales/lines` | 行级 SKU 明细（销售时间/店铺/规格/单价/数量/成本） |
| 现有页面（参考） | `frontend/src/pages/costing/ProfitInsightsPage.tsx` | 复制 80% 代码作为新页骨架 |
| 现有页面（嵌入复用） | `frontend/src/pages/costing/SalesInsightsPage.tsx`（已支持 `embedded` 模式） | 商品明细子组件参考 |
| 全局参数表 | `cost_rate_master scope=global` 或 `taxonomy domain='ops_assumption_scheme'` | 多方案存储，**不新建表** |

## 3. 任务分解（B1~B3 后端 / F1~F4 前端 / 全部一次提交）

### B1 — 后端 ops_assumption 方案 CRUD（taxonomy 复用，不新建表）

**实现**：在 `taxonomy` 表新增 `domain='ops_assumption_scheme'`，每行一个方案，`metadata.json` 存 6 个百分比：
```json
{
  "promotion_pct": 0.17,
  "platform_fee_pct": 0.061,
  "tax_pct": 0.08,
  "labor_pct": 0.20,
  "venue_logistics_pct": 0.10,
  "unmodeled_cost_pct": 0.50,
  "description": "运营当前算账口径",
  "is_default": true
}
```

**端点**（在 `backend/src/planner/routers/base_config.py` 或新增 `routers/ops_assumptions.py`）：
- `GET /api/planner/ops-assumption-schemes` 列出全部方案（含 default 标记）
- `POST /api/planner/ops-assumption-schemes` 新建（请求体含 name + 6 个百分比）
- `PUT /api/planner/ops-assumption-schemes/{id}` 编辑（重命名、改百分比）
- `DELETE /api/planner/ops-assumption-schemes/{id}` 删除（is_default=true 不允许删）
- `POST /api/planner/ops-assumption-schemes/seed` 幂等 seed 4 个预置方案（首次部署时调用）

**Seed 4 个预置方案**（首次部署运维手动调一次或后端启动时检测自动 seed）：

| 方案名 | 推广 | 扣点 | 税 | 人工 | 场地快递 | 兜底 | 用途 |
|---|---|---|---|---|---|---|---|
| 默认标准 | 17% | 6.1% | 8% | 20% | 10% | 50% | 运营当前算账口径（is_default=true） |
| 大促降推广 | 12% | 6.1% | 8% | 20% | 10% | 50% | 大促前预演 |
| 试涨价 | 17% | 6.1% | 8% | 18% | 10% | 50% | 涨价/控人工 |
| 0 推广（最低边界） | 0% | 6.1% | 8% | 20% | 10% | 50% | 看产品基本面 |

### B2 — 单测（最小验收 2 条）

`backend/tests/planner/test_ops_assumption_schemes.py`：
- T1: seed 接口幂等（连调 2 次方案数=4，`is_default` 正好 1 个）
- T2: CRUD 流程（POST 新建 → GET 列表含新行 → PUT 改百分比 → GET 验证 → DELETE → GET 不含；`is_default=true` 删除应 400）

### B3 — schemas

`backend/src/planner/schemas.py` 新增 `OpsAssumptionScheme` Pydantic：name / id / 6 个 Decimal/float / description / is_default / created_at。

---

### F1 — 新页 `SimpleDailyPnlPage.tsx`

**路径**：`/costing/insights/daily-pnl`
**文件**：`frontend/src/pages/costing/SimpleDailyPnlPage.tsx`（复制 `ProfitInsightsPage.tsx` 80% 代码作为骨架）

**顶部参数区（紧凑卡片）**：
- 方案下拉 `Select`（值=方案 id，label=方案名）
- 6 个 `InputNumber`（推广 / 扣点 / 税 / 人工 / 场地快递 / 未建模兜底成本比；单位都是 %，0~100）
- `[保存当前]`（PUT 当前方案）/ `[另存为新方案]`（弹窗输入新名 → POST）/ `[新建空方案]` / `[删除当前]`（is_default 禁用）
- 切换方案 → 立即填值 → 列表实时按新方案重算（前端 JS 算，零延迟）

**左侧 模型日报榜单（按"税后贡献"倒序）**：
列：模型 / 发货量 / 销售额 / 真退款 / 成本(BOM/兜底) / 运营扣减 / 税后贡献 / 税后率 / 颜色
```
KB8  120  5,400  600   840            1,734  2,226  41%  🟢
TC2   50  2,250  150   470              721    909  40%  🟢
KB9   88  3,520  300   1,760(兜底50%) 1,127    333   9%  ⚠️
ZJ1   30  1,000  280   580              320   -180 -18%  🔴
```

**算法（前端 JS 重算，service 不动）**：
```ts
// 来自后端 model-insights/summary 每行
const revenue = Number(row.revenue_amount);     // 销售额
const refund  = Number(row.refund_amount);      // 真退款
const bomCost = Number(row.cost_amount);        // BOM 真成本(已建模); 0/null = 未建模

const isUnmodeled = !bomCost || bomCost === 0 || row.cost_quality?.level === 'red';
const cost = isUnmodeled ? revenue * scheme.unmodeled_cost_pct : bomCost;

const opsDeduct = revenue *
  (scheme.promotion_pct + scheme.platform_fee_pct + scheme.tax_pct +
   scheme.labor_pct + scheme.venue_logistics_pct);

const netProfit = revenue - refund - opsDeduct - cost;
const netMargin = revenue > 0 ? netProfit / revenue : null;

// 颜色
const color =
  isUnmodeled ? 'warning'  // ⚠️
  : netMargin >= 0.02 ? 'success'  // 🟢
  : netMargin >= 0    ? 'info'     // 🟡
                      : 'error';   // 🔴
```

**右侧（点选模型后）父 Tabs**：
- **模型明细**（保留 `ProfitInsightsPage` 原有的 3 个子 Tab：最终BOM / 物料组+工序组 / 扣库单 — 一字未改复用）
- **商品明细**（新加，子 Tabs）：
  - Top 赚钱 SKU（`fetchSalesProfitDashboardSnapshot top_n=100` 取 top_skus_profit，前端按当前方案重算"税后贡献"列、重排）
  - Top 亏损 SKU（同上，取 top_skus_loss）
  - 全量行级明细（`fetchSalesLines` 当前模型相关 SKU + 当前日期范围；列加：销售额/真退款/物料成本/运营扣减/税后贡献/税后率/颜色）

### F2 — 导出 Excel（**新增需求 2026-05-15**）

每个表格右上角加「**导出 Excel**」按钮：
- 左侧"模型日报"导出（单 sheet，列同表格 + 一份 sheet 头注明：使用方案名、6 个百分比值、查询时间范围、店铺）
- 右侧"商品明细 / 全量行"导出（行级，包含 sku_code / 模型 / 规格 / 销售额 / 真退款 / 成本 / 运营扣减 / 税后贡献 / 税后率 / 颜色级别）
- 实现：使用现有 `xlsx`（`SheetJS`）库，前端纯客户端导出（`frontend/package.json` 已有 `xlsx` 依赖；如未有则 `npm i xlsx --save` 加上）
- 文件名格式：`简易日盈亏_<方案名>_<起>_<止>_<导出时间>.xlsx`

### F3 — 路由 + 菜单

- `frontend/src/App.tsx` 加 `<Route path="/costing/insights/daily-pnl" element={<SimpleDailyPnlPage />} />`
- `frontend/src/components/layout/AppLayout.tsx` 在「数据洞察」菜单组加一项「简易日盈亏」（icon 用 DollarOutlined 或 PieChartOutlined）

### F4 — 类型 + service

- `frontend/src/types/planner.ts` 加 `OpsAssumptionScheme` 类型
- `frontend/src/services/planner.ts` 加 5 个 fetcher（list / create / update / delete / seed）

---

## 4. 验收命令（必须全部 0 退出码）

```bash
# 后端
source backend/venv/bin/activate
python -m pytest backend/tests/planner/test_ops_assumption_schemes.py -v
# 期望：T1 + T2 全过

# 前端
npm -C frontend run build
# 期望：✓ built 0 类型错误

# 端到端（部署后）
curl -s "https://work.znma.com/api/planner/ops-assumption-schemes" \
  -H "X-PLANNER-ADMIN-KEY: <key>" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert len(d) >= 4, f'expected >=4 schemes, got {len(d)}'
default_count = sum(1 for s in d if s.get('is_default'))
assert default_count == 1, f'expected 1 default, got {default_count}'
print('OK: schemes seeded =', len(d))
"
```

## 5. 红线（不可越界）

- ❌ 不动 `/costing/insights/models /sales /shops /after-sales` 任何一行代码
- ❌ 不新建表（用 taxonomy domain='ops_assumption_scheme' 复用）
- ❌ 不改 `analytics_service.py` 任何函数（前端 JS 重算即可）
- ❌ 不重算历史 `shipment_costing_results`（参数变更只影响展示口径）
- ❌ 不引入新外部 npm 大依赖（xlsx 已存在或必要时加 1 个）

## 6. 闭环说明（执行 Agent 必须按 `task_distribution_standard.md` 给齐 7 项）

执行完毕在 `task_log.md` 加一行总结，至少包含：
1. **改了什么**：1 后端 router + 1 后端 schema + 1 后端单测 + 1 前端新页 + 1 前端子组件 + 路由 + 菜单 + types + services
2. **影响范围**：仅新增 `/costing/insights/daily-pnl`，不影响现有 4 个 Insights 页与任何后端 service
3. **build**：`npm -C frontend run build` 通过
4. **发布**：`PLANNER_STATIC_DIR=/var/www/html/ai-costing/dist ./scripts/deploy_static.sh` 原子切换
5. **后端重启**：`systemctl --user restart planner-costing.service` Active running
6. **真机验证**：浏览器打开新页 → 切 4 个预置方案数字实时变化 → 选模型→ 父 Tab 模型明细/商品明细都展示 → 导出 Excel 文件名规范且能打开
7. **遗留风险**：未建模 SKU 兜底比是估算值（不写库），运营建模一个 SKU 后下次刷新自动切真值；4 个 seed 方案在首次部署时由 ops 调用 `POST /seed` 一次性写入

## 7. 完整自主权（按 §0.2）

执行 Agent 在不违反 §5 红线的前提下，可以自主决定：
- 后端方案存哪：`taxonomy` 还是 `cost_rate_master`（建议 `taxonomy`，更轻量）
- 前端组件拆分粒度（如 SchemeSelector / ParamsForm / ModelDailyTable / ProductDetailTab 4 个子组件）
- Excel 列名/sheet 名/格式细节
- 方案是否支持复制（[复制为新方案] 按钮，可选）
- 颜色阈值微调（红≤0 / 黄 0~2% / 绿>2% 是建议值）

## 8. 单 commit 信息建议

```
feat(insights): /costing/insights/daily-pnl 简易日盈亏页 + 4 预置运营参数方案 + Excel 导出

- backend: ops_assumption_scheme CRUD via taxonomy domain（不新建表）+ seed 4 默认方案 + 2 单测
- frontend: SimpleDailyPnlPage 复用 ProfitInsights/SalesInsights 现有数据，前端 JS 重算"运营扣减/税后贡献/税后率/颜色"
- 父 Tabs：模型明细（保留原貌）+ 商品明细（Top赚/Top亏/全量行）+ Excel 导出（每表按当前方案 + 查询范围）
- 红线：未动现有 4 个 Insights 页 / 未改 analytics_service / 未重算历史 / 未新建表
```
