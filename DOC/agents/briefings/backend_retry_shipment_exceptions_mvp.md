# Backend 闭环任务单：发货异常队列“按批次重试未解决异常”（Retry Exceptions）MVP

> 角色：@Backend Agent  
> 背景：当前主链已具备“发货单导入→生成 BOM 快照/写异常队列”，但业务侧最常见困惑是：**同文件幂等后，补齐 SKU 绑定/修复解析规则，重新导入同文件不会再出结果**。  
> 目标：提供一个**显式动作**：对某个 `batch_id` 的未解决异常重新跑（绑定→解析→生成新快照），并把成功项标记为 resolved（但不删除历史异常记录）。

## 1) 本轮范围（必须很小）

只做一个闭环：
- 新增一个 API：**按批次重试未解决异常**（Retry Exceptions）
- 补最小单测覆盖：重试后**生成新 `bom_snapshot`（不回写历史）**，异常置为 resolved

不做：
- 不做“重跑整批（Rerun Batch）”与父子批次链路（留到下一轮）
- 不做“SKU 批量绑定导入/导出”（由 SKU 主档工作台/绑定工作台解决，或单独派单）

## 2) 依赖现状（以仓库为准）

- 现有落库表：`shipment_import_batches / shipment_lines / shipment_exception_queue / bom_snapshots / spec_parse_snapshots`
- 现有 API（只读）：`GET /api/planner/shipments/exceptions?batch_id=&resolved=&limit=`
- 现有“单行重算快照”能力：`POST /api/planner/shipments/bom-snapshots/{snapshot_id}/recompute`（必须保持：**重算产出新快照，不覆盖旧快照**）

## 3) API 设计（新增）

### 3.1 Endpoint

- **`POST /api/planner/shipments/exceptions/retry`**

### 3.2 Request（JSON）

- `batch_id: str`（必填）
- `only_unresolved: bool = true`（必填，MVP 固定为 true 也可）
- `limit: int | null`（可选，防止一次重试太多行）
- `operator_id: str`（必填，用于审计）
- `reason: str`（必填，例如 `binding_completed` / `parser_updated` / `manual_retry`）

### 3.3 Behavior（必须写死口径）

- 仅选择 `shipment_exception_queue` 中满足以下条件的记录：
  - `batch_id` 命中
  - `resolved=false`（若 `only_unresolved=true`）
- 对每条异常，读取其关联的 `shipment_line`（通过 `shipment_line_id` 或可推导键）
- 按主链重新执行：
  1) 查询 SKU→已发布标准版本绑定（无绑定则保持异常 unresolved，并更新 message 可选）
  2) 解析 spec_text（复用 spec_hash 缓存可选）
  3) 生成 BOM 快照（**生成新 `bom_snapshot`，不覆盖旧快照**）
- 成功：将对应异常标记为 `resolved=true`，并在异常记录里写入最小回填：
  - `resolved_at/resolved_by`
  - `resolution_action="retry"`
  - `resolved_bom_snapshot_id=<new_snapshot_id>`（若字段不存在，可写入 `resolution_trace_json`）
- 失败：保持 unresolved，并追加 `retry_count+1` / `last_error`（若无字段则落 `trace_json`）

## 4) 单测（必须最小覆盖）

新增/补充 pytest（建议文件名）：
- `backend/tests/planner/test_shipment_exception_retry_mvp.py`

至少覆盖：
- 给定 batch 内存在 `SKU_NOT_BOUND` 异常：当绑定补齐后，调用 retry → **生成新的 `bom_snapshot`** 且异常变 resolved
- retry 不会覆盖历史快照（可通过比对 snapshot_id 数量或 trace 的 `recomputed_from_snapshot_id`/新建记录来证明）

## 5) 验收命令（只给 1 条）

`python -m pytest backend/tests/planner/test_shipment_exception_retry_mvp.py -q`

---

【每轮必须自维护 + 必须提交（强制）】  
你本轮工作完成/暂停前，必须做 3 件事，否则视为未交付：  
1) 更新恢复包（必须）：同步更新 `DOC/agents/state.md`（写清本轮产物+下一步+验收命令+北京时间日期）、必要时更新 `DOC/agents/known_issues.md` / `DOC/agents/commands.md` / `DOC/agents/workset.md`。  
2) 硬验收（必须）：按本单的验收命令跑通并贴出输出。  
3) Git 落地（必须）：把你改动的代码 + 对应 `DOC/agents/*` 一起 `git add`，并提交一次小步 commit（一个主题一个 commit）。


