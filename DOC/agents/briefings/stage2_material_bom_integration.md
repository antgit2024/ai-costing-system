# Stage 2 物料字段接入 BOM + KB8 反推诊断 — 全栈大任务单（2026-05-10）

> 派单类型：全栈大任务（后端核心算法 + 前端 UI + 反推诊断脚本）
> 预估工作量：1~1.5 人天（AI Agent 4~6 小时）
> 承接 Agent 角色：`@Fullstack Agent`（完整自主权 + ai-costing-system 仓库内部）
> 唯一硬约束：**不准动 finance 集成 / Hub MVP / Insights / 已 commit 的契约文档**

---

## 0. 30 秒摘要

commit `e6dcf969` 已经给 materials 表加了 6 个 Stage 2 字段（purchase_entity_id / tax_rate / tax_included_flag / effective_from / effective_to / price_source），但**核心 BOM 计算 service 完全没读这些字段** — 加了等于没加。

本任务把 6 个字段真正接入 BOM 计算，让物料成本能按"生效期取价 + 含税还原不含税 + 区分采购主体"准确算出来。同时跑 KB8 反推诊断，输出"系统算的成本 vs 用 Stage 2 重算的成本"差异报告，让用户直观判断算法准确度。

---

## 1. 必读 3 步（开工前必读）

```
[ ] 1. 完整读 commit e6dcf969 的 diff（理解 6 字段含义）：
       cd /home/admin/ai-costing-system && git show e6dcf969 --stat | head -30
       关键文件：backend/src/planner/models.py (Material ORM ~line 301)
                 backend/migrations/versions/0039_materials_stage2_fields.py
                 frontend/src/pages/costing/MaterialMasterPage.tsx (Drawer Stage 2 卡片)

[ ] 2. 找到现有 BOM 计算的"物料价格读取"位置：
       backend/src/planner/services/bom_generation_service.py
       搜 "_resolve_material_price" 或 "Material.price" 或 "material.price"
       理解现有取价逻辑（很可能直接 material.price 取最新值）

[ ] 3. 看 1 个真实 KB8 发货行的 cost_breakdown 元数据格式：
       backend/migrations/versions/0027_shipment_costing_results_no_snapshot.py
       理解 cost_material_total / cost_breakdown JSONB 结构
```

---

## 2. 任务范围

### 2.1 后端：物料价格读取改造（核心）

**目标文件**：`backend/src/planner/services/bom_generation_service.py`

**改造点**（在 `_resolve_material_price` 或类似函数内）：

```python
def _resolve_material_price(
    self, 
    material: Material, 
    as_of_date: date | None = None,        # 默认今天，发货行回溯时传发货日
    purchase_entity_id: str | None = None, # 可选过滤特定采购主体
) -> dict:
    """
    返回: {
        "price_inclusive": Decimal,           # 含税价（原始）
        "price_exclusive": Decimal,           # 不含税价（成本核算用，法定要求）
        "tax_rate": Decimal,
        "tax_included_flag": bool,
        "purchase_entity_id": str,
        "price_source": str,                  # contract / invoice / purchase_order / estimate
        "effective_from": date,
        "effective_to": date | None,
        "_data_quality": "green/yellow/red"   # green=有完整元数据, yellow=部分缺失, red=fallback
    }
    
    取价逻辑（优先级）：
    1. 如果 material 是 versioned (有 effective_from/to)：
       - 找 as_of_date 落在 [effective_from, effective_to] 内的版本
       - 多个版本时优先 price_source 高质量的（contract > invoice > purchase_order > estimate）
    2. 如果 material 没有 effective_from（老数据）：
       - 直接用当前 material 字段，data_quality = yellow
    3. 都拿不到：raise MaterialPriceNotFound + log warning，data_quality = red
    
    含税还原：
    - 如果 tax_included_flag=True 且 tax_rate 非 NULL：
      price_exclusive = price_inclusive / (1 + tax_rate)
    - 如果 tax_included_flag=False：
      price_exclusive = price_inclusive  (price 字段就是不含税价)
    - 如果 tax_rate=NULL：默认 13% (一般纳税人) 或 3% (小规模) — 看 purchase_entity_id（v1 用 13% 兜底+ data_quality=yellow）
    
    成本核算法定用 price_exclusive（不含税价）。
    """
```

**调用方修改**：
- 凡是当前用 `material.price` 直接读的地方，改为调 `_resolve_material_price(material, as_of_date=shipment_date)`
- 把返回的元数据写进 `cost_breakdown` JSONB（每行物料含 price_source / effective_from 等）

### 2.2 后端：KB8 反推诊断脚本

**新建脚本**：`backend/scripts/kb8_stage2_reverse_diagnosis.py`

**功能**：
1. 找 4 月（或最近 1 个月）KB8 真实发货行（至少 5~10 条）
2. 对每条发货行：
   - 拿 `shipment_costing_results.cost_material_total`（**系统当前算的旧值**）
   - 用新 `_resolve_material_price` 重算物料成本（**新算法值**）
   - 算差异：`diff = new_value - old_value` / `diff_pct = diff / old_value`
3. 输出 Markdown 报告到：`DOC/costing/handovers/stage2_kb8_reverse_diagnosis_YYYYMMDD.md`

**报告结构**：

```markdown
# KB8 Stage 2 物料接入反推诊断报告 (YYYYMMDD)

## 摘要
- 抽样发货行数: N 条
- 平均偏差: X%
- 最大正偏差（旧算高了）: Y% on shipment_id
- 最大负偏差（旧算低了）: Z% on shipment_id

## 偏差源分类
| 偏差源 | 影响行数 | 平均偏差 |
|---|---|---|
| 含税口径错（旧用含税价当成本）| ... | ... |
| 取价时间错（旧取最新价非发货时价）| ... | ... |
| price_source 缺失 fallback 估算偏差 | ... | ... |

## 详细行明细
| shipment_id | sku_code | 旧物料成本 | 新物料成本 | 偏差 | 偏差源 |
|---|---|---|---|---|---|
| ... | ... | ... | ... | ... | ... |

## 给老板的结论
- 1~3 句话告诉老板"用了 Stage 2 字段后 KB8 物料成本算得多准"
```

### 2.3 前端：UI 元数据展示

**目标文件 1**：`frontend/src/pages/costing/RealtimePricingPage.tsx`（实时核价）
- 物料明细表格加 1 列「价格来源」
- 显示 price_source（中文化：合同 / 发票 / 采购单 / 估算）
- Tooltip hover 显示：「采购主体: XXX / 含税: 是/否 / 税率: 13% / 生效期: 2026-04-01~now / 数据质量: 🟢」

**目标文件 2**：`frontend/src/pages/costing/ShipmentLedgerPage.tsx`（发货台账"成本拆分" Tab）
- 同上加列 + tooltip

**目标文件 3**（如有）：`frontend/src/components/costing/MaterialPriceQualityBadge.tsx`（新建小组件，复用）
- 与 `CostQualityBadge`（已有）保持视觉风格一致：🟢 绿 / 🟡 黄 / 🔴 红

### 2.4 不在 scope 内（不要做）

- ❌ 不动 finance C1 集成代码（finance_c1_client.py 等）
- ❌ 不动 Hub MVP 相关（cost_rate_master / long_tail_strategy_service）
- ❌ 不动 4 个 Insights 看板（U7-A 已完成）
- ❌ 不动契约文档（DOC/costing/blueprints/finance_to_costing_*）
- ❌ 不动 cost_center 相关（U2 后续任务）
- ❌ 不写 cost_center_master 主表
- ❌ 不实施 Stage 3 人工成本（v1.5 后续）

---

## 3. 关键技术决策

### 3.1 versioned 物料的"老数据兼容"

老 material 行 effective_from = NULL → 默认行为=当前价格永久生效。新创建的物料如果填了 effective_from 走新逻辑。**兼容老数据 0 break change**。

### 3.2 含税口径默认值

如果 material 老数据 tax_included_flag = NULL：
- 默认按 **True**（中国采购大部分含税开票）+ data_quality = yellow + log warning
- 强制 ops 后续在 UI 补值

### 3.3 KB8 反推诊断的 sample 选择

- 优先选 4 月（最近月）发货
- 至少 5 条，最多 20 条（避免报告过长）
- 多样化：选不同物料数量的 SKU，不要全是同一种

### 3.4 cost_breakdown 元数据格式扩展

老 cost_breakdown JSONB 结构不变，**只在物料行追加** `price_metadata` 子对象：

```json
{
  "materials": [
    {
      "material_id": "...",
      "material_code": "...",
      "qty": 0.5,
      "price": 26.93,                    // 老字段，保持兼容（=不含税价）
      "subtotal": 13.47,
      "price_metadata": {                // 新增（向后兼容）
        "price_inclusive": 30.43,
        "price_exclusive": 26.93,
        "tax_rate": 0.13,
        "tax_included_flag": true,
        "purchase_entity_id": "...",
        "price_source": "contract",
        "effective_from": "2026-01-01",
        "effective_to": null,
        "_data_quality": "green"
      }
    }
  ]
}
```

老前端 / 老 endpoint 不读 `price_metadata` 不会崩。

---

## 4. 完成标准

```
[ ] B1 _resolve_material_price 函数实现完毕（含 4 种取价场景 + 3 种含税还原 + 数据质量分级）
[ ] B2 调用方全部改完（grep "material.price" 验证无遗漏）
[ ] B3 cost_breakdown.price_metadata 在新 BOM 计算结果里都有
[ ] B4 老数据 effective_from = NULL 不崩，data_quality 自动 = yellow
[ ] B5 backend/tests/planner/test_material_price_resolver.py 至少 8 条测试全过
[ ] B6 KB8 反推诊断脚本能跑通：python -m backend.scripts.kb8_stage2_reverse_diagnosis
[ ] B7 反推报告 markdown 输出到 DOC/costing/handovers/，含摘要 + 偏差源分类 + 详细明细 + 老板结论
[ ] F1 RealtimePricingPage.tsx 物料表格加「价格来源」列
[ ] F2 ShipmentLedgerPage.tsx 成本拆分 Tab 加「价格来源」列
[ ] F3 MaterialPriceQualityBadge 视觉风格与 CostQualityBadge 一致
[ ] F4 Tooltip hover 显示完整元数据
[ ] F5 frontend/ npm run build 无错误
```

---

## 5. 验收命令（自主选 1~3 条）

```bash
# 选项 A：单元测试
cd /home/admin/ai-costing-system
pytest backend/tests/planner/test_material_price_resolver.py -v

# 选项 B：反推诊断脚本
PYTHONPATH=backend python -m backend.scripts.kb8_stage2_reverse_diagnosis --period=2026-04 --sku-prefix=KB8

# 选项 C：前端构建
cd frontend && npm run build
```

---

## 6. 收工归集 3 件

1. **commit 1 次**（标题 `feat(stage2): 物料 6 字段接入 BOM 计算 + KB8 反推诊断`）
2. **更新 task_log.md** 加 1 行
3. **更新 system_capability_inventory.md §13.3 已完成事项审计** 加 1 行

push 自决（这是 ai-costing-system 仓库自己 push 没问题）。

---

## 7. 唯一回 Hub 的 3 种情况

1. **scope 不够**：发现 KB8 真实发货行 0 条（数据库空），无法做反推诊断
2. **架构冲突**：现有 BOM 计算逻辑非常复杂，改 _resolve_material_price 会触发大面积级联修改（>10 个调用点）
3. **完全卡死**：超过 60 分钟无进展

其他全部自主决策（用 Decimal 还是 float、tooltip 用 antd Popover 还是 Tooltip、报告 markdown 风格、老 cost_breakdown 数据怎么 migrate 等）。

---

## 8. 风险规避

1. ⚠️ **不动 cost_breakdown 老字段**：只追加 price_metadata 子对象，老字段 price/subtotal 保持兼容
2. ⚠️ **老 material 数据 effective_from = NULL 别报错**：必须 graceful fallback，data_quality=yellow + warning
3. ⚠️ **含税口径错算成本会被老板发现**：测试至少 1 条"含税价当不含税价"的反例
4. ⚠️ **不要重新计算历史 shipment_costing_results**：本任务只改"未来新算的逻辑"，历史数据保持原样（在 task_log 注明）
5. ⚠️ **不要碰 finance C1 / Hub / Insights**：独立 scope，don't touch

---

## 9. 元信息

| 项 | 值 |
|---|---|
| 创建日期 | 2026-05-10 13:58 北京时间 |
| 创建人 | Hub Agent |
| 触发原因 | 用户 13:55 同意推荐方案；commit e6dcf969 加字段不接入 = 浪费 |
| 关联 commit | e6dcf969 (Stage 2 字段加进 ORM/migration/UI Drawer) |
| 期望承接 | Fullstack Agent (能写 Python + React + 跑 SQL + 写 Markdown) |
| 期望完工 | 4~6 小时后台 |
| 验收人 | Hub Agent + 用户看反推报告 |
