# Material Top 50 Stage 2 补全清单生成 — 数据脚本任务（2026-05-10）

> 派单类型：轻量数据脚本（查数据库 + 写 markdown 清单 + 给 ops 用）
> 预估工作量：30~60 分钟（AI Agent）
> 承接 Agent 角色：`@Data Agent`（完整自主权 + ai-costing-system 内部）
> 唯一硬约束：**纯查询 + 写文档，不修改任何代码 / 不动数据库**

---

## 0. 30 秒摘要

按 4 月（2026-04）出货量倒序，找 Top 50 物料，生成一份给 ops 用的 Stage 2 字段补全清单（markdown + Excel CSV 双格式）。ops 拿到后 25~30 分钟填完，KB8 等热门 SKU 的物料成本立刻还原 ~13% 失真。

输出位置：
- 主文件：`DOC/基础表单/material_top50_stage2_补全清单_20260510.md`
- 配套 Excel：`DOC/基础表单/material_top50_stage2_补全清单_20260510.csv`

---

## 1. 必读 2 步

```
[ ] 1. 看反推诊断报告理解上下文（约 70 行）：
       /home/admin/ai-costing-system/DOC/costing/handovers/stage2_kb8_reverse_diagnosis_20260510.md

[ ] 2. 看 6 个 Stage 2 字段含义（commit e6dcf969 diff）：
       cd /home/admin/ai-costing-system && git show e6dcf969 -- backend/src/planner/models.py | head -50
```

---

## 2. 任务范围

### 2.1 SQL 查询逻辑

```sql
-- Top 50 物料按 4 月出货量倒序
WITH april_usage AS (
    SELECT 
        scl.material_id,
        SUM(scl.quantity) AS total_qty
    FROM shipment_costing_lines scl  -- 或对应的物料明细表
    JOIN shipment_costing_results scr ON scl.shipment_id = scr.shipment_id
    WHERE scr.shipment_date >= '2026-04-01' 
      AND scr.shipment_date < '2026-05-01'
    GROUP BY scl.material_id
),
ranked AS (
    SELECT 
        m.id, m.code, m.name, m.unit, m.unit_price,
        m.tax_included_flag, m.tax_rate, m.purchase_entity_id,
        m.effective_from, m.price_source,
        au.total_qty,
        ROW_NUMBER() OVER (ORDER BY au.total_qty DESC) AS rank_no
    FROM materials m
    JOIN april_usage au ON m.id = au.material_id
)
SELECT * FROM ranked WHERE rank_no <= 50;
```

> **如果实际表结构 / cost_breakdown JSONB 解析方式与上面不同，自主调整**。读 `backend/src/planner/services/bom_generation_service.py` 找现有取数模式。
> 
> **如果 4 月数据不足 50 条**，扩到近 3 个月（2026-02 ~ 2026-04），并在报告标注。

### 2.2 输出 markdown 结构

```markdown
# Top 50 物料 Stage 2 字段补全清单（2026-05-10）

> 数据来源：4 月发货物料用量倒序（如 4 月不足扩到 Q1 + 4 月）
> 用途：让 ops 优先补这 50 个物料的 Stage 2 字段，立刻还原 ~13% 物料成本失真

## 操作步骤（5 步）

1. 登录 ai-costing-system → 物料管理 → 在搜索框输入「物料编号」
2. 点击物料行进入编辑 Drawer
3. 在右侧「税务/采购/效期 (Stage 2)」卡片填 5 个字段（**单价不动**）
4. 点保存
5. 重复 50 次

## 默认值建议（让 ops 不用思考）

| 字段 | 默认填什么 | 例外 |
|---|---|---|
| 含税开关 | ☑ Yes | 农副产品/个人采购 = ☐ No |
| 税率 | 13% | 小规模采购 = 3% / 农副 = 0% |
| 采购主体 | 看物料历史最常采购的公司 | 如不确定填「一般纳税人主体」|
| 生效期 | 合同/最新发票的开票日 | 不知道填 2026-01-01 |
| 价格来源 | 合同 > 发票 > 采购单 > 估算 | 按你最新依据 |

## Top 50 清单

| # | 物料编号 | 物料名称 | 单位 | 当前单价 | 4月用量 | 当前 Stage 2 状态 | 建议含税 | 建议税率 | 建议生效期 | 建议价格来源 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | M001 | 棉布 50D 浅灰 | 米 | 30.43 | 1280 | ❌ 全空 | ☑ Yes | 13% | 2026-01-01 | 合同 |
| ... × 50 ... | | | | | | | | | | |

## 完工后效果

- 工作量：30~50 分钟（每物料约 30 秒）
- 立即收益：Top 50 物料覆盖 ~70%+ 出货量，物料成本算法精度 +13%
- 后续：Top 50 完成后再做 Top 100 / Top 200，渐进推进

## 数据快照

- 抽样窗口：YYYY-MM ~ YYYY-MM
- 数据库 snapshot 日期：YYYY-MM-DD
- 当前 Stage 2 启用率：0/1502 (0%)（按反推诊断报告 §1）
```

### 2.3 输出 CSV（让 ops 在 Excel 里也能用）

同样的 50 行数据，CSV 格式 UTF-8 with BOM（Excel 中文不乱码），列顺序与 markdown 表格一致。

### 2.4 不在 scope 内（不要做）

- ❌ 不修改任何代码
- ❌ 不修改数据库（只查询）
- ❌ 不实施"批量补字段 UI"（那是另一个任务）
- ❌ 不写 BOM / Hub / Insights 相关任何代码
- ❌ 不动契约文档

---

## 3. 完成标准

```
[ ] D1 markdown 清单已生成，路径正确
[ ] D2 CSV 配套已生成，UTF-8 with BOM，Excel 打开中文不乱码
[ ] D3 50 行（或近 3 个月可拿到的最大数量）按 4 月用量倒序
[ ] D4 每行含：物料编号 / 名称 / 单位 / 当前单价 / 4 月用量 / 当前 Stage 2 状态 / 建议值 5 列
[ ] D5 头部含「操作步骤 5 步」+「默认值建议表」+「数据快照元信息」
[ ] D6 末尾含「完工后效果」+ 快照日期 + Stage 2 当前启用率
```

---

## 4. 验收命令（自主选 1~2 条）

```bash
# A) wc 看清单完整性
wc -l "DOC/基础表单/material_top50_stage2_补全清单_20260510.md"
wc -l "DOC/基础表单/material_top50_stage2_补全清单_20260510.csv"

# B) head 抽样看格式
head -30 "DOC/基础表单/material_top50_stage2_补全清单_20260510.md"
```

---

## 5. 收工归集 2 件（轻任务，无需 task_log）

1. **commit 1 次**（标题 `docs(基础表单): Top 50 物料 Stage 2 字段补全清单`）
2. push 自决

无需更新 task_log（数据脚本 + 文档输出，非系统能力变更）。

---

## 6. 唯一回 Hub 的 2 种情况

1. **数据完全为空**：4 月 + 近 3 个月物料用量数据都查不到（数据库异常）
2. **完全卡死**：超过 30 分钟无进展

其他全部自主决策（SQL 怎么写、JSON 怎么解、CSV 编码细节、markdown 视觉风格）。

---

## 7. 元信息

| 项 | 值 |
|---|---|
| 创建日期 | 2026-05-10 14:45 北京时间 |
| 触发原因 | 用户 14:38 选 A，要 Top 50 清单立即给 ops |
| 关联诊断报告 | `DOC/costing/handovers/stage2_kb8_reverse_diagnosis_20260510.md` |
| 期望承接 | Data Agent (能跑 SQL + 写 markdown 即可) |
| 期望完工 | 30~60 分钟 |
| 完工后 Hub 动作 | 把清单路径告诉用户，让他直接转给 ops |
