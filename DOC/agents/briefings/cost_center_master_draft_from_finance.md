# ❌ 已废弃 — 班组 + 固开摊法 v3 草案 — 财务侧出初稿任务单（2026-05-10）

> **❌ 废弃原因（2026-05-10 12:08）**：用户指出"让财务出建议又让老板 review = 财务变业务大脑 = 我没自己出主意"。正确分工：**costing 一次性出全部规则告诉财务 → 财务按规则提供数据 → costing 直接消费 → 老板只看结果**，财务不出建议。
>
> **替代方案**：本派单已被以下 2 件事取代：
> 1. C1 契约 v1.1 增量需求（在 `finance_to_costing_c1_contract_v1.md` 加 §3.6 班组聚合接口 + §3.7 摊法计算接口，含 costing 定义的全部公式）
> 2. costing 内部 cost_center_master 管理 UI（老板登录系统点品类标签，不需要填模板）
>
> **本文档保留**作为：v3 → v3.5（"财务出建议"路径）→ 终极方案（"costing 出规则、财务执行"）的决策演进留档。
>
> **以下原内容仅供历史参考，不要按此执行**。
>
> ---

派单类型：跨仓库专业出稿任务（基于 finance-analyzer 真实数据出 6 班组 + 11 项摊法草案）
预估工作量：4~6 小时（AI Agent）
承接 Agent 角色：`@Finance Analyst Agent`（完整自主权 + 跨仓库强约束）
唯一硬约束：**不准 push 到 origin、不准动任何代码、只输出 1 份 Markdown 草案**

---

## 0. 30 秒摘要

ai-costing-system 这边的老板要填一张「6 班组 + 11 项固开摊法」的表（`cost_center_master_填报模板_v2.md`），但**这些数据的原材料全在你 finance-analyzer 这边**（员工花名册 / 工资单 / 固开台账）。请你基于真实数据出一份 v3 初稿草案，让老板只需要 review + 加业务标签即可，不需要从零手填。

**输出位置**：`/home/admin/ai-costing-system/DOC/基础表单/cost_center_master_填报模板_v3_财务初稿.md`（创建新文件，不覆盖 v2）

---

## 1. 必读 3 步（开工前必读）

```
[ ] 1. 读 ai-costing-system 这边的现状文档（约 200 行）：
       /home/admin/ai-costing-system/DOC/基础表单/cost_center_master_填报模板_v2.md
       重点看：表 1 的列结构、表 2 的固开 11 项标准枚举、«填完后我会做什么»

[ ] 2. 读契约（约 460 行）：
       /home/admin/ai-costing-system/DOC/costing/blueprints/finance_to_costing_c1_contract_v1.md
       重点看：§3.3 employees / §3.4 fixed-costs / §3.5 payroll 的 schema

[ ] 3. cd /home/admin/projects/finance-analyzer && 摸清 employees / payroll / fixed_monthly_cost 真实数据分布
       (参考：backend/app/models/employee.py / payroll*.py / fixed_monthly_cost.py)
```

---

## 2. 任务范围（只输出 1 份 Markdown，不写代码）

### 2.1 输出文件

新建：`/home/admin/ai-costing-system/DOC/基础表单/cost_center_master_填报模板_v3_财务初稿.md`

文件结构与 v2 完全保持一致（保证老板不用重学），但每个空格已填好「财务建议值」+ 加 1 列「数据来源」+ 加 1 节「财务给老板的 review 提示」。

### 2.2 表 1 班组初稿生成规则

**输入数据**：finance-analyzer 数据库的 `employees` 表 + `payroll_record` 表（或工资聚合表）+ `master_companies` 表

**生成规则**：

1. 从 `employees` 取 `is_active=true` 且 `departure_date is null`（在职员工），按 `department` 字段 group by
2. 取员工数 ≥ 3 的 department，按人数倒序，**取前 6~10 个**作为候选班组
   - 如果不足 6 个：全部取出，标注「实际班组数 < 6，请老板确认是否合并/拆分」
   - 如果超过 10 个：只取前 10 个，标注「还有 X 个小班组未列出，老板可补充」
3. 每个班组填以下字段（**不知道的字段就标 ❓ 留给老板填**）：

| 字段 | 数据来源 | 算法 |
|---|---|---|
| 班组名称（中文）| `employees.department` 字段值 | 直接取，原样 |
| 班组 code（英文短码）| 财务自己起 | department 拼音首字母大写 + 数字（如 SEW01）|
| 班长 | `employees` where `position` LIKE '%班长%' OR '%组长%' | 同 department 里筛 |
| 人数 | count(employees) | 在职在该 department |
| 主要工序 | ❓ 留空（业务决策）| 财务不填，老板补 |
| 主要服务品类（家居饰品/布艺/通用）| ❓ 留空（业务决策）| 财务不填，老板补 |
| 归属工厂主体 | `employees.contract_company_id` 占比最大的那个 → 查 `master_companies.legal_name` | 取众数；若并列写"多主体" |
| 默认工时单价（元/分钟）| 最近 3 个月 payroll 聚合 | sum(total_labor_cost) / (sum(headcount × workdays) × 8 × 60) |
| 备注 | 自动填「财务建议：基于 YYYY-MM 工资数据，工时单价 = X 元/分钟，可信度 🟢」| |

### 2.3 表 2 固开 11 项摊法专业建议

**输入数据**：finance-analyzer 数据库的 `fixed_monthly_cost` 表 + 你自己的会计专业知识

**生成规则**：每一项固开按下表给出「会计专业默认摊法 + 理由」，老板只需 review 改/不改：

| 固开类别（与契约 §3.4.1 一致）| 推荐摊给谁 | 推荐分摊驱动因子 | 财务理由（必填）|
|---|---|---|---|
| rent (房租 - 生产区域) | 6 班组 | 占地面积 | 会计准则 ASBE 4 — 与生产相关的固定资产折旧/租赁费按受益空间分摊 |
| rent (房租 - 办公区域) | 4 店铺 + 班组按 50/50 | 占地面积 | 办公空间无法严格划分，建议两边均摊 |
| utility (水电) | 6 班组 | 占地面积 + 设备工时 | 生产用电为主，可按面积近似 |
| ... | ... | ... | ... |

**11 项全部要给，不要漏**。如果某项 finance 现有数据库没有这个 cost_category 历史记录，仍要给推荐摊法（标注「历史无记录，预设规则」）。

### 2.4 加 1 节「review 提示给老板」

在 v3 文档末尾加 1 节，内容如：

```markdown
## 给老板的 review 重点（5 分钟看完）

财务这边已经基于真实数据填好了 6 个班组 + 11 项摊法，**你只需要 confirm 3 件事**：

1. **每个班组的「主要服务品类」**（财务不知道，必须你填）— 5 个 ☐ 框打勾
2. **班组的合并/拆分意见**（如果你觉得某 2 个班组应该合并 / 某 1 个班组应该拆开为 2 个）
3. **摊法是否同意**（11 项里你觉得不合理的改一下，否则保持财务建议）

review 完告诉 Hub Agent「v3 草案 OK，可落地」即可。
```

### 2.5 不在 scope 内（不要做）

- ❌ 不写代码（不动 ai-costing-system / finance-analyzer 任何代码）
- ❌ 不动 finance-analyzer 数据库 / migration / schema
- ❌ 不实施 cost_center_master 主表（那是后续 Hub Agent 的活）
- ❌ 不在 finance-analyzer 仓库 commit 任何东西
- ❌ 不填「主要服务品类」「主要工序」（业务决策留给老板）
- ❌ 不动 v2 文件（保留作为决策对比留档）

---

## 3. 跨仓库 Git 安全协议

```
[ ] G1 全程只读 finance-analyzer 数据库 / 代码 / 文档 — 不写不改不 commit
[ ] G2 ai-costing-system 这边只新建 1 个文件（v3 草案），不动任何其他文件
[ ] G3 不要碰 git config / 不 push / 不 commit（让 Hub Agent 后续统一归集 commit）
[ ] G4 finance-analyzer dirty 文件 hands-off — 完全不碰
```

---

## 4. 完成标准

```
[ ] D1 v3 草案文件已建（路径准确）
[ ] D2 表 1 含 6~10 个班组，每个班组都有：班组名 / 班组 code / 班长（or ❓）/ 人数 / 归属工厂主体 / 工时单价 / 备注
[ ] D3 表 1「主要工序」「主要服务品类」全部留 ❓（不要乱填）
[ ] D4 表 2 11 项固开全部有：摊给谁 + 驱动因子 + 财务理由（每项 ≥ 1 句话）
[ ] D5 文档末尾有「给老板的 review 重点」5 分钟章节
[ ] D6 文档头部明确标注「数据来源时间窗：YYYY-MM 至 YYYY-MM」「数据 snapshot 日期：YYYY-MM-DD」「下次重算建议：每季度 1 次」
[ ] D7 老板 review 5~10 分钟即可定稿（凭经验判断）
```

---

## 5. 数据缺失时的应对

| 情况 | 处理方式 |
|---|---|
| `employees.department` 字段值不规范（如「缝纫组」「缝纫一组」「sewing01」混用）| 在 v3 草案里**保留你的归一化版本** + 在备注列标注「财务做了归一化：原值 X/Y/Z → 统一为 'XXX'，老板请确认」 |
| `payroll` 数据近 3 个月不全 | 用近 6 个月或近 1 年；标注「数据时间窗：YYYY-MM」 |
| 某个 department 的 `contract_company_id` 分散在 5 个公司 | 标注「该班组员工分散在 5 个法人主体，建议老板决策合并到 1 个主体」 |
| `fixed_monthly_cost` 完全无数据 | 11 项摊法仍按会计准则给推荐 + 标注「历史无台账，建议老板补录后重算」 |

---

## 6. 工作量预估

| 子任务 | 工时 |
|---|---|
| 读 v2 模板 + 契约 + finance 数据 schema | 30~60 分钟 |
| SQL 跑数据 + 班组聚合 + 工时单价计算 | 1~2 小时 |
| 写 11 项摊法专业建议（每项 ≥ 1 句理由） | 1 小时 |
| 写 v3 Markdown 文档 + review 提示章节 | 1~1.5 小时 |
| 自检 D1~D7 | 30 分钟 |
| **总计** | **4~6 小时** |

---

## 7. 唯一回 Hub 的 3 种情况

1. **scope 不够**：finance 数据库连 `employees.department` 字段都没有，无法分组（极不可能）
2. **架构冲突**：finance 数据完全不可读取（DB 挂了 / 表结构与契约 §3.3 严重偏差）
3. **完全卡死**：超过 60 分钟无进展

其他全部自主决策（班组取 6 还是 10 个？工时单价用 3 个月还是 6 个月？归一化怎么做？— 你专业判断）。

---

## 8. 元信息

| 项 | 值 |
|---|---|
| 创建日期 | 2026-05-10 12:05 北京时间 |
| 创建人 | Hub Agent (ai-costing-system) |
| 触发原因 | 老板指出"班组+摊法的原材料在财务，应该让财务出初稿，不应让老板手填" |
| 关联文档 | `cost_center_master_填报模板_v2.md`（v2 → v3 升级的数据来源说明）|
| 输出位置 | `/home/admin/ai-costing-system/DOC/基础表单/cost_center_master_填报模板_v3_财务初稿.md` |
| 期望承接 | Finance Analyst Agent (能跑 SQL + 懂会计准则 + 能写 Markdown) |
| 期望完工时间 | 后台跑 4~6 小时 |
| 完工后 Hub 动作 | 自动归集 commit + 通知老板 review 5~10 分钟 |
