## 规则条目目录（Rules）

> 口径：**一条规则一页**，避免在单一大文档里越写越乱；新人入口统一从
> `DOC/costing/manuals/rules_training_handbook_v1.md` 进入。

---

### 1) 文件命名规范（强烈建议）

- **格式**：`R-<主题>-<序号>_<短标题>.md`
- **示例**：
  - `R-SKU-001_sku_not_bound_go_bind.md`
  - `R-SHIP-001_shipment_rerun_semantics.md`

> 主题建议：`SHIP / SKU / SPEC / MODEL / VAR / BUNDLE / INV / POD`

---

### 2) 每条规则模板（复制后填写，一条规则一页）

> 强约束：规则页必须包含 `status`，并具备“可被替代但不丢历史”的字段。

建议在文件头部使用 Front Matter（便于检索/版本化）：

```yaml
---
rule_id: R-INV-001
title: <一句话能说清楚的规则标题>
status: draft|active|deprecated
effective_from: YYYY-MM-DD
superseded_by: <被替代时填写，例如 R-INV-002>   # 仅 deprecated 需要
owner: Rules Agent
updated: YYYY-MM-DD
---
```

正文模板（至少包含）：

- **适用范围**：哪些页面/流程/角色会用到
- **问题背景**：为什么要这条规则（痛点/风险）
- **规则正文（可执行口径）**：一句话能落地（避免含糊词）
- **正例**：至少 1 个
- **反例**：至少 1 个
- **边界与例外**：什么情况下不适用/允许人工介入
- **验收方式（最小闭环）**：1 条可执行命令或明确点验步骤
- **与 UI“新建指南”的关系**：引用对应 guide 文件（如需要）

---

### 3) 状态治理：允许推翻，但不丢历史（必须遵守）

- **状态**：
  - `draft`：探索中（允许频繁修改）
  - `active`：当前唯一有效口径（培训/实施按这个来）
  - `deprecated`：已废弃（保留原因与替代方案，不再执行）
- **推翻旧规则**：
  - 旧规则标为 `deprecated`
  - 写清 `superseded_by / effective_from / reason`
  - 新规则成为唯一 `active`
- **变更记录纪律**：
  - 每次发生 **active 口径变更**（active↔deprecated 或引入新的 active），必须在 `DOC/agents/task_log.md` 追加决议记录（影响范围 + 验收命令 + 上线时间点）

