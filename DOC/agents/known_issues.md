## 已知坑（新 Agent 必读）

> 最近校对（北京时间 GMT+8）：2026-05-12（接力入口：`DOC/agents/handoff_planner.md` / `DOC/agents/handoff_frontend.md`）

### 0.0k) 吉客云售后 API 上线 + 两条 client 隐藏 bug（2026-05-12 上线）

- **背景**：上线 `omsapi-business.refund.listrefund` 同步，把 ERP 售后单合并到
  `after_sales_lines` 表，发现 `JackyunClient` 在 OMS-API namespace 下有两条
  WMS namespace 没碰到的 bug，需要 client 层修。
- **bug #1：业务子码 200 被误判为失败**
  - WMS namespace 用 `subCode="0000000000"` 表示成功，OMS-API namespace 用
    `subCode="200"`。`_BUSINESS_OK_SUB_CODES` 原来只覆盖前者，导致整批 OMS 请求
    被 `parse_response` 全报失败。
  - 修复：`_BUSINESS_OK_SUB_CODES` 加 `"200"`。
- **bug #2：result.data 是 JSON 字符串而非对象**
  - WMS namespace `result.data` 直接是 `dict/list`；OMS-API namespace 是
    **JSON-encoded string**（要 `json.loads` 一次才能看到内层 `{count, tradeAfterOnlineDtoArr}`）。
  - 修复：`parse_response` 检测到 `data` 是 `str` 且首字符 `{`/`[` 时自动二次解析，
    所有下游 mapper 看到的形状统一。
- **upstream 强约束（实测 2026-05-12）**——以下错一点都返回「未知错误」：
  - `pageInfo` 必须是 `{pageIndex,pageSize}` **嵌套对象**（不能是平铺 key）。
  - `pageIndex` **从 1 开始**（传 0 返回空数组）。
  - `memberName="jackyun"` （吉客号）**必填**，缺了会报「创建起止时间或更新起止时间不能全为空」（误导性错误）。
  - 4 组时间区间任选其一：`gmtModifiedBegin/End` / `gmtCreateBegin/End` /
    `createTimeBegin/End` / `modifiedTimeBegin/End` —— 我们用 `gmtModified*` 做水位线。
  - `isQueryCount=true` 返回 `count` 但 `tradeAfterOnlineDtoArr=[]`；
    `isQueryCount=false`（默认）返回数据但 `count=0`。**翻页停止条件靠"短页"**，不能依赖 `count`。
- **mapper 关键设计**：
  1. `external_line_key_hash = sha1("jackyun|{tradeAfterOnlineId}|{afterSubTradeId}")`
     全局唯一 → 重跑/二次 sync **幂等**（已实测 1898 行第二次跑全部走 update 分支）。
  2. 同售后单号 (`after_sales_no`) 同时存在 Excel + 吉客云数据时：
     **不删除** Excel 行，打 `tag="superseded_by_jackyun"` + metadata 指针指向新 jackyun 行。
     审计可逆，分析可按 tag 过滤。
  3. `erp_order_no` best-effort：用 `platOrderNo` 反查 `shipment_lines.platform_order_no`，
     找到唯一匹配才填，多匹配 / 0 匹配都留 null。**因此 refund timer 编排在 shipment timer 之后 30min**
     （02:30 → 03:00），让发货行先落库再回填。
  4. PII 脱敏：`customerName/name/mobile/address` 在上游就是 `~xxx~/tb/~N~~` 包裹；
     `_strip_redaction` 只剥外壳（保 `王**` 之类内层）→ 进 metadata，不进任何分析聚合字段。
- **入口**：
  - 手动：`/costing/integrations` 「吉客云 · 售后退款同步」卡片
  - API：`POST /api/planner/integrations/jackyun/sync/refunds`
  - CLI：`python -m scripts.cron_sync_jackyun --task=refund [--start ...] [--end ...]`
  - 自动：`jackyun-refund-sync.timer` 每晚 03:00 (Asia/Shanghai)
- **首跑数据**：7 天窗口拉到 1898 行 / 1668 单售后；erp_order_no 命中率 36% (683/1898)，
  剩余 64% 是发货还没同步过来 / 历史发货已 archive。

---

### 0.0j) SPU 属性冲突检测必须只看真实订单，不能算 Excel 历史（2026-05-09 上线）

- **背景**：上线 SPU 属性冲突检测（同一 `erp_sku_barcode` 历史发货跨多个不相关品类）后，
  首次回填扫到 91 个"冲突 SKU"。运营反馈像 `5970014255535` 这种典型例子并没有真冲突——
  看 ERP 实际订单只是单一品类，那些"跨品类"的发货行全是测试期间手工灌的 Excel 历史数据。
- **诊断**：`5970014255535` 的 77 条发货里 74 条无 `erp_order_no` / `platform_order_no`
  （Excel 灌的回测/老映射），仅 3 条来自吉客云同步的真实订单——这 3 条都是同一类枕套，
  不存在冲突。其它被误标的 SKU 也是同样模式。
- **修复**：`backend/src/planner/services/data_quality_service.py` 的 `recompute_all` /
  `detect_for_one_sku` 默认 `only_with_real_order=True`，SQL 端
  `WHERE (erp_order_no IS NOT NULL AND erp_order_no <> '') OR (platform_order_no IS NOT NULL AND platform_order_no <> '')`
  过滤掉 Excel/无单号历史。
  - `backfill_data_quality_status.py` 加 `--include-excel`（默认关，仅排查用）和
    `--clear-stale`（一次性回填打开，把"被标过但本次扫不到的"残留旧标也清掉）。
  - 一次性回填后真实冲突从 91 → 2（`10000001` 测试条码 + `5970014255534`
    都有真实跨品类订单，正确识别），运营视角立刻干净。
  - **nightly 任务 `ai-costing-data-quality.timer` 不要传 `--clear-stale`**——
    沉默 SKU 维持现状即可，否则会把"短期没新发货的标记 SKU"清掉，下次有冲突订单进来再标显得反复。
- **关键不变量**：任何"基于全库历史发货"的数据质量/冲突检测**都必须有 only_real_order
  开关并默认开启**，否则一旦运营再灌 Excel 测试数据就会大量误报。
- **mark_only 原则**：检测出 SPU 属性冲突的 SKU 仅在 SkuMaster 抽屉 + SkuMaster 列表 +
  发货管理已完成 Tab 显示灰/红色 Tag，**不会自动解绑、不会绕开成本计算**——绑定问题
  走现有的"重新绑定 / 忽略提示"路径由运营手动处理。

---

### 0.0i) 在 sku-master 绑定后 OLD pending 行不出快照（2026-05-07 修复）

- **现象**：用户在 `/costing/sku-master` 给 SKU `6232909415870` 绑定到 `KB8 通用包边垫类`，但 `/costing/biz/shipments?tab=pending` 仍显示该 SKU 的 4-19 / 4-21 两条 ShipmentLine 为「🟥 无对应模型 (人工)」。`sku-master` 里"已关联"，发货管理却看不出来。
- **根因**：双重断层
  1. `sweep_bound_lines_missing_snapshot` 默认 `lookback_days=14`，4-19 / 4-21 距今 16~18 天 → **超出窗口被永久跳过**
  2. `bind_sku_to_version` 完成绑定后**没有任何**反向 hook 触发该 SKU pending 行立即出快照 → 用户必须等定时 sweep，而 sweep 又被时间窗口排除 → 死锁
- **修复**：
  1. **绑定即触发**（核心修复）：`product_model_service.bind_sku_to_version` 末尾新加 best-effort hook `_trigger_pending_snapshots_for_sku`，扫该 SKU **所有时间** pending 行（最多 500 条）逐条调 `compute_snapshot_for_shipment_line`。失败 swallow + log，不影响 binding 主事务。
  2. **sweep 窗口保持 14d**（一度放宽到 60d, 同日按用户反馈回退）：bind hook 已覆盖 99% 场景，sweep 只需要兜底 hook 失败的少数行，扩大窗口反而每 5 分钟扫更多无谓行。改为「14d 后台 sweep + 手动「🔁 回写快照」按钮」组合：
     - **后台**：每 5 分钟 14 天窗口，零成本兜底
     - **手动**：PendingTab 顶部按钮 → POST `/shipments/lines/regenerate-snapshots?lookback_days=90` → 复用 `sweep_bound_lines_missing_snapshot`，月底盘点时点一下即可
  3. **execute() 统计修正**：`auto_resolve_pending_shipment_lines_execute` 内 step 3 改成 walk 「pre-bind 时的 pending line ids」而非 「post-bind 仍 pending」（hook 已搞完，post-bind 全空）。同时新增「pre-bind open exception line ids」snapshot，让 hook 帮忙 resolved 的异常也算到 execute 头上 — 否则 UI 会误显示「绑定 N 个 / 出快照 0 / 解决异常 0」。
  4. **执行历史回填**：批量跑 `sweep_bound_lines_missing_snapshot(lookback_days=60, limit=2000)` 一次性出 **155 条** 历史卡住快照（用户当时用户看到的 16 条全部消化）。剩 356 条是 `SPEC_EMPTY`（spec_text 上游就是空的，需走 Exception Queue 人工处理，不归本次修复）。
- **测试**：新增 `test_bind_sku_to_version_triggers_snapshot_for_old_pending_lines` 锁住 90 天前的 pending line 在 bind 之后必须立即出 snapshot。同时所有原 `auto_resolve_*` 测试因 hook 行为更新了断言，**19/19 全部通过**（含 jackyun sprint1 套件）。
- **影响**：
  - 用户新绑定一个 SKU 时（无论 sku-master 还是 ⚡ 一键自动绑定）— 该 SKU 所有历史 pending 行**立即**出快照，发货管理"待处理"Tab 立刻减少
  - 防止"已绑定 / 缺快照"长期堆积：60d sweep + bind hook 双层覆盖，理论上一行最多 5 分钟内被处理
- **已知 follow-up**：sweep 失败 356 条 SPEC_EMPTY 已独立列入异常队列，由 `/costing/exceptions` 流程处理，不阻塞本闭环。

---

### 0.0h) Jackyun 同步失败被 latest_runs 滚动覆盖、前端看不见（2026-05-07 修复）

- **现象**：审计 pipeline 时发现最近 24h 有 3 条 jackyun shipment_pull `status='failed'`，但 PendingTab 顶部状态条只看 `latest_runs[0]`，那 3 条失败因为后面跑了几次成功，已经被滚出 `latest_runs[0:3]` 列表，**操作员完全看不见有失败发生**。
- **根因**：`get_recent_shipment_line_stats` 只返回最近 N 条 `latest_runs`（按 `finished_at desc`），没有任何"窗口内失败次数 / 最近一次失败"的聚合字段。前端没数据可显示。
- **修复**：
  1. 后端 `shipment_import_service.get_recent_shipment_line_stats`：新增 2 个字段
     - `recent_failed_runs_count: int` — `started_at >= cutoff_at AND status='failed'` 的总条数
     - `latest_failed_run: SyncRunItem | None` — 窗口内最近一次失败的完整明细（id / 开始时间 / 错误信息 / 触发者）
     - 用 `started_at` 作锚点而不是 `finished_at`，因为崩溃失败的 run 可能根本没 `finished_at`
  2. `schemas.py` + `frontend/types/planner.ts` 同步加 2 个可选字段
  3. `PendingTab.tsx`：在原同步状态条**上方**新增红色 `Alert type="error"`，仅当 `recent_failed_runs_count > 0` 时显示，包含失败次数 + 最近一次起始时间 + 触发者 + 错误信息（截断+tooltip 全文）+ "→ 同步管理排错" 按钮跳 `/costing/integrations`
  4. 加 2 个 regression test：`test_recent_stats_surfaces_failed_runs_count_for_pending_tab`（含窗口内/外混合用例 + 验证 latest_failed_run 取最新一条），`test_recent_stats_returns_zero_failed_when_window_clean`（防止 banner 误报）
- **影响**：
  - 当前 PendingTab 已经能看到红 banner 提示 3 条 jackyun 失败（错误信息：`[0050030002] 创建时间/完成时间/修改时间必传其一!`）
  - 未来再有 sync 失败，操作员第一时间能看见，不会被掩盖
- **相关上下文**：与 Issue 0.0g 的 batch.status 字面值修复一起，组成"sync 失败的两层可观测性"：DB 层批次状态正确（0.0g）+ UI 层窗口内聚合显示（0.0h）。

---

### 0.0g) Jackyun 同步批次 `batch.status='succeeded'` 不被前端识别（2026-05-07 修复）

- **现象**：审计 pipeline 时发现 `shipment_import_batches` 状态字面值不一致——8 条 `'succeeded'`，9 条 `'success'`。前端 `BatchWorkbench.tsx:40` 的状态映射只识别 `'success'`，导致 8 条 jackyun 同步批次在工作台显示为"未知"。
- **根因**：`backend/src/integrations/jackyun/sync_jobs.py:298` 写 `batch.status = "succeeded"`，孤立于项目其它 5 处批次写入（xlsx 导入、worker、售后导入、shipments router 全部用 `"success"`）。
- **修复**：
  1. 把 `sync_jobs.py:298` 改成 `batch.status = "success"`，加注释说明契约。
  2. 一次性 `UPDATE shipment_import_batches SET status='success' WHERE status='succeeded'`（影响 8 条历史脏数据）。
  3. 前端 `BatchWorkbench.tsx:40` 防御性同时识别 `'success' || 'succeeded'`，未来类似事故不会再让操作员看到"未知"。
  4. 加 `test_jackyun_sync_jobs_writes_canonical_batch_status_literal` regression test（`tests/integrations/test_jackyun_sprint1_pipeline.py`），源码层面锁住 `sync_jobs.py` 不能再写 `'succeeded'`。
- **影响**：所有历史 jackyun 同步批次现在能在 BatchWorkbench 正确显示成功，未来同步也写规范字面值。
- **未做（不是 bug）**：`sku_master.metadata_json.governance_status` 字段缺失 162k 行——审计初看以为是 bug，实际后端 `sku_master_service.py:4376` 用 `coalesce(metadata->>'governance_status', 'unmanaged')` 兜底，缺失等价于 `unmanaged`，行为正确。`pending_model / auto_bound / do_not_model` 都是 0 单纯是因为还没人用治理流程标过，不是数据丢失。

---

### 0.0f) `list_shipment_lines` 已完成 Tab 30~180 天暴慢 — Nested Loop 1.8 亿次 join filter（2026-05-07 修复）

- **现象**：`/costing/shipments` 和 `/costing/biz/shipments?tab=done` 列表卡顿。实测 4 种最常见查询：
  | 场景 | 修复前 | 修复后 | 倍数 |
  |---|---:|---:|---:|
  | 已完成 7 天（DoneTab 默认） | 6.7s | **195ms** | 34× |
  | 已完成 30 天 | 31s | **288ms** | **107×** |
  | 全部 30 天（台账默认） | 1.8s | 128ms | 14× |
  | 待处理 30 天 | 1.8s | 315ms | 6× |
  | 已完成 90 天 | **157s** | 687ms | **228×** |
  | 已完成 180 天 | (timeout) | 847ms | — |
- **根因（多层）**：
  1. **`shipment_exception_queue` 12.7w 行无 `shipment_line_id` 索引**。两个 correlated scalar_subquery（unresolved_reason / unresolved_message）每行做 Seq Scan 12ms × 50 = 1.2s，但 prod 冷缓存能放大到 30s。
  2. **`binding_sq` 子查询触发 Nested Loop 灾难**。原代码用 `LEFT JOIN (binding_sq with row_number() OVER PARTITION BY sku_code) ON sku_code AND rn=1` 想优化 scalar_subquery，但 PostgreSQL 选了 NL Left Join：
     ```
     Nested Loop Left Join: Rows Removed by Join Filter: 180,135,956
     →  Index Scan on shipment_lines (rows=2156)
     →  Materialize binding_sq (rows=83552, loops=2156)
     ```
     **1.8 亿次** join 比较，单这一步就 38s。binding_sq 作为 inline view 没有索引，planner 选了 NL+Materialize 而不是 Hash Join。
- **修复**（两件事）：
  1. **Migration 0037**：在 `shipment_exception_queue` 加 partial index `(shipment_line_id, created_at DESC) WHERE resolved_at IS NULL`。SubPlan 7/8 从 12ms × 50 → 0.001ms × 50（4000× 提升）。
  2. **干掉 `binding_sq`**（`shipment_import_service.py::list_shipment_lines`）。改成直接 `LEFT JOIN sku_model_version_mapping m + LEFT JOIN product_model_versions v + LEFT JOIN product_models pm`。原 `row_number() OVER PARTITION BY sku_code` 完全多余 — 表已经有 `ux_sku_model_version_mapping_sku_code_active` partial unique index 保证每个活跃 SKU 唯一，planner 直接走 unique-index lookup。
- **关键边界**：把 `bound_model_version_id` 从 `m.model_version_id` 改成 `v.id`。如果 ProductModelVersion 后期 archived，LEFT JOIN 会让 v/pm 整组 NULL；用 `v.id` 保证"无可用 binding"是单一一致状态（全 NULL），匹配 v2 binding_sq INNER JOIN 的语义。
- **验证**：
  - 6 个常用查询全部 sub-second
  - `total` 数字与修复前完全一致（行为零变更）
  - 249/249 planner+integrations 测试通过（含 governance / bulk_resolve / auto_resolve_pending / mapper 全套）
  - 跑 systemctl restart 重启 + 验证两次连续请求时间稳定
- **位置**：
  - 迁移：`backend/migrations/versions/0037_shipment_exception_queue_line_idx.py`
  - 服务：`backend/src/planner/services/shipment_import_service.py::list_shipment_lines`（约 2175-2360 行；改前 v2 是 binding_sq + row_number()，改后 v3 是 3 段 LEFT JOIN）
- **审计指南**：未来如果有人想加"按多版本展示一行 SKU 的所有 binding 历史"功能，**不能**重用 list_shipment_lines 的 join 链。partial unique index `ux_sku_model_version_mapping_sku_code_active` 限制了 active 行只有一条 — 多版本必须走独立的 history 接口。

### 0.0e) Jackyun v2 全量字段一次性补齐（migration 0036，2026-05-07）

- **背景**：用户反馈"你能加上的都加上吧，后面加又麻烦，你现在数量小"。审计 mapper vs Jackyun v2 API 文档（https://open.jackyun.com/developer/apidocinfo.html?id=wms.order.query-info.page.v2）发现还有 20 个有业务价值的字段只存在 `raw_row_json` 里，没作为列暴露：
  - **头部 13 列**：`order_status_name`、`logistic_type_name`、`logistic_code`、`wave_no`、`customer_name`、`picker / packer / checker`、`check_started_at`、`paid_at`、`ordered_at`、`trade_type`、`trade_type_msg`
  - **明细 7 列**：`unit_price`、`unit_of_measure`、`category_name`、`goods_name`、`goods_no`、`is_gift`、`actual_qty`
- **价值点**：
  - `order_status_name`：区分"已完成 / 待配货 / 待出库 / 已签收"，财务报表能筛"真发货" vs "待发货"
  - `logistic_name + logistic_code + logistic_type_name`：算运费（按快递公司价签）和配送方式分析
  - `unit_price`：单价×数量 vs 实际入账可识别折扣/优惠券（实测数据：SKU 5826491336939 单价 ¥55.9 vs 入账 ¥47.5 = 折扣 ¥8.4）
  - `unit_of_measure`：防"件 vs 瓶 vs 箱"歧义，BOM 计算更稳
  - `category_name`：Jackyun 自分类，可喂给长尾策略表单做关键词补充（注意：实测有些商家把 `cateName` 当渠道名，需结合 channel 看）
  - `picker / packer / checker / wave_no`：仓库内部责任追溯
  - `is_gift`：财务能区分赠品（不计入 GMV）vs 正常品
- **实现**：
  1. Migration `0036_shipment_line_jackyun_full_fields`：在 `shipment_lines` 表加 20 列，全 nullable，关键列加索引（`order_status_name / logistic_type_name / logistic_code / wave_no / paid_at / ordered_at / trade_type / category_name / goods_no`）
  2. `backend/src/integrations/jackyun/mappers/shipment.py::upsert_shipment_from_payload`：抽取所有 20 个字段
     - **坑点**：Jackyun v2 spec 把 `LogisticCode` 写成 upper-camel（其他全是 lowerCamel），mapper 同时尝试 `LogisticCode` 和 `logisticCode` 两种写法，避免 sandbox 不一致
     - **坑点**：`isGift` upstream 是 0/1（有时是 "0"/"1"），用 `bool(int(...))` 解析；缺失值留 NULL（而不是 False），区分"明确不是赠品" vs "老数据未知"
  3. `backend/src/planner/schemas.py::ShipmentLineListItem` 加 28 个 optional 字段（含已有的 erp/sent_at/logistic_no 等也补齐对外暴露）
  4. `backend/src/planner/services/shipment_import_service.py::list_shipment_lines` 末尾 `getattr` 透传新字段（不影响现有行）
  5. **一次性回填**：`backend/scripts/backfill_shipment_line_jackyun_fields.py`（幂等，可重跑）从 `raw_row_json` 反查回填 1716 行 jackyun ShipmentLine，无 raw_row 的 Excel 行自动跳过
  6. **前端展示**：`ShipmentLedgerPage.tsx` 详情抽屉加"上游 ERP 字段"卡，3 列 Descriptions bordered，包含一个"单价×数量 vs 总金额"自动比对 Tag（差额 ≥ 0.01 显示折扣/溢价金额）
- **测试**：3 个新 mapper 测试 + 0 regression（pre-existing 的 4 个失败跟我无关，stash 验证一致）
  - `test_sync_shipments_promotes_jackyun_v2_full_fields_into_columns`
  - `test_lower_camel_logistic_code_is_also_accepted`
  - `test_is_gift_zero_resolves_to_false_not_none`
- **位置**：
  - 迁移：`backend/migrations/versions/0036_shipment_line_jackyun_full_fields.py`
  - mapper：`backend/src/integrations/jackyun/mappers/shipment.py`
  - model：`backend/src/planner/models.py::ShipmentLine`（行 ~1190 附近）
  - 回填脚本：`backend/scripts/backfill_shipment_line_jackyun_fields.py`
  - schema：`backend/src/planner/schemas.py::ShipmentLineListItem`
  - 前端 types：`frontend/src/types/planner.ts::ShipmentLineListItem`
  - 前端展示：`frontend/src/pages/costing/ShipmentLedgerPage.tsx`（详情抽屉"上游 ERP 字段"卡）
- **后续可做（暂不动）**：
  - 待处理 Tab 列表加"快递"列、"状态"列做面分类筛选
  - "退货库存"功能：用 `order_status_name LIKE '%退%'` + `goods_no` 反查可二次销售的 SKU
  - 长尾策略表单加"按 jackyun cateName 匹配"模式

### 0.0d) Jackyun mapper 主时间字段对齐为 `sendTime`（发货时间）+ 列名重命名（2026-05-07）

- **背景**：用户反馈"我们完成时间改成发货时间较好，方便跟 ERP 核对"。Jackyun v2 API 文档中（https://open.jackyun.com/developer/apidocinfo.html?id=wms.order.query-info.page.v2）的"业务返回参数"明确规定：
  - `sendTime` (Date) - **发货时间** ⬅ 主字段
  - `gmtCreate` - 创建时间
  - 文档**没有** `finishTime` 字段（之前我们错把它当主字段，文档里根本不存在）
- **修复**：
  1. `backend/src/integrations/jackyun/mappers/shipment.py::upsert_shipment_from_payload` 主字段链改为：
     `sendTime → payTime → orderTime → gmtCreate → 同步时间`
     （去掉了不存在的 `finishTime`）
  2. 前端列名「完成时间」改「发货时间」：
     - `frontend/src/pages/costing/biz/components/PendingTab.tsx`
     - `frontend/src/pages/costing/biz/components/DoneTab.tsx`
     - `SalesInsightsPage.tsx` 时间口径文案同步调整
  3. 一次性脚本：1716 条 jackyun 行用新链路重算 `completed_at + sent_at`，分布：
     - `upstream_send`: 670 条（真实已发货，跟 ERP 一字不差）
     - `upstream_pay`: 1046 条（订单状态"待配货"，没真发货，用付款时间兜底）
- **验证**：
  - 抽样真发货行：上游 `sendTime=2026-05-07 07:40:20` → DB UTC `2026-05-06 23:40:20` → 前端北京 `2026-05-07 07:40:20`，三者一致。
  - SKU `5826491336939`（待配货状态）：sendTime 为空 → fallback `payTime=2026-05-06 13:42:55` → 前端显示北京 `2026-05-06 13:42:55`，业务合理。
  - 7/7 mapper 测试 + 23 项扩展测试全过。
- **位置**：
  - mapper：`backend/src/integrations/jackyun/mappers/shipment.py`
  - 前端：`PendingTab.tsx`、`DoneTab.tsx`、`SalesInsightsPage.tsx`

### 0.0c) Jackyun 时间字符串被错当 UTC 存储 → 前端显示偏 +8 小时（2026-05-07 修复）

- **现象**：`/costing/biz/shipments` 列表「完成时间」显示 `05-07 15:40` 而当前实际是 `12:13`，差几个小时；本质上**所有 jackyun 同步进来的 `completed_at / sent_at` 都被偏移了 +8 小时**。之前没人察觉是因为偏移后看起来"还是同一天"，财务对账数据未爆雷。
- **根因**：`backend/src/integrations/jackyun/mappers/shipment.py::_parse_dt` 写法是
  ```python
  dt = datetime.strptime(s, fmt)
  return dt.replace(tzinfo=timezone.utc)
  ```
  jackyun upstream 给的字符串其实是 **Asia/Shanghai 北京时间**（无 tz suffix），错误地打了 `tzinfo=UTC` → DB 里存的"UTC" 实际是北京时间字面值。前端 `formatBeijingTime` 再 `+8` 显示，最终展示成"实际北京时间 +8h"。
- **修复**：
  1. `_parse_dt` 改为按 Beijing 时区解析后转 UTC：
     ```python
     dt = datetime.strptime(s, fmt)
     return dt.replace(tzinfo=_BEIJING_TZ).astimezone(timezone.utc)
     ```
  2. mapper 同时升级 fallback 链：`finishTime → sendTime → payTime → orderTime → gmtCreate → 同步时间`，避免对"待出库"订单（`orderStatus=1`）显示同步时间这种业务上无意义的值。
  3. 一次性脚本：对**全部 1716 条** jackyun ShipmentLine 行用新 `_parse_dt` + 新 fallback 链重新解析 `raw_row_json`，更新 `completed_at / sent_at / metadata_json.completed_at_source`。
- **验证**：
  - SKU `5826491336939` 上游 `payTime=2026-05-06 13:42:55 北京` → DB 存 `05-06 05:42:55 UTC` → 前端显示 `05-06 13:42:55 北京`，三者一致。
  - 23/23 测试通过（含新加 `test_parse_dt_treats_upstream_string_as_beijing_local` 锁住时区行为）。
- **审计指南**：
  - 重新解析过的行：`metadata_json.completed_at_re_parsed_at = '2026-05-07T12:18+08:00'`。
  - `completed_at_source` 取值：`upstream_finish / upstream_send / upstream_pay / upstream_order / upstream_gmt_create / fallback_sync_time`。财务报表想剔除非 finish 的兜底数据，按字段过滤即可。
- **未覆盖的场景（待办）**：5673 条老 Excel 导入路径（`source_system IS NULL`）的行也有 `completed_at` 偏差，但它们没有 `raw_row_json` 上游字段可重算；当前用的是 `created_at` 兜底（标记 `fallback_sync_time_backfill`）。如果业务上需要更准，需要重新拉 Excel 文件回放。
- **位置**：
  - mapper：`backend/src/integrations/jackyun/mappers/shipment.py::_parse_dt`、`upsert_shipment_from_payload`
  - 测试：`backend/tests/integrations/test_jackyun_shipment_mapper.py::test_parse_dt_treats_upstream_string_as_beijing_local`、`test_completed_at_falls_back_through_payload_levels`
  - 一次性脚本：手工 Python 脚本（已执行，幂等）

### 0.0b) Jackyun 行 `completed_at = NULL` 让发货管理列表/搜索找不到（2026-05-07 修复）

- **现象**：吉客云上游 `finishTime / sendTime` 为空时，mapper 落 `completed_at = NULL`。`list_shipment_lines` 主查询要求 `completed_at IS NOT NULL`（且按它过滤 `start/end` + 排序），导致这些行在「发货管理 > 待处理」**搜不到、也排不出来**。同样的问题让 `sweep_bound_lines_missing_snapshot`（快照重试 worker）每次只能扫到 54 行，134 个该出快照的行被跳过。
- **根因**：`completed_at` 是系统的"交易完成时间锚点"（销售利润看板、BomSnapshot/ExceptionQueue/CostingResult 都复制一份按月归账）。下游有 6+ 处依赖。如果挨个改下游过滤会牵动财务/分析路径，风险大。
- **修复策略（B 方案：mapper 兜底 + 一次性回填）**：
  1. `backend/src/integrations/jackyun/mappers/shipment.py::upsert_shipment_from_payload`：当 `finishTime/sendTime` 都为空时，`completed_at` 兜底为同步时刻 `_utcnow()`，并在 `ShipmentLine.metadata_json.completed_at_source` 打 `"upstream"` 或 `"fallback_sync_time"` 标记。
  2. 一次性回填：用 Python 脚本把库里现存 `completed_at IS NULL` 的 6719 行（1046 jackyun + 5673 老 Excel 路径）补成 `created_at`，并打 `completed_at_source = "fallback_sync_time_backfill"` 标记。
- **验证**：
  - `5826491336939`：发货管理按 SKU 搜索 `total=1`，状态 pending，已绑定 F6A 皮革桌垫；重启后 sweep 立刻扫了 195 行（之前 54 行）、新建 134 个快照；这条的 BomSnapshot `059ed831` 也出来了。
  - `pytest tests/integrations/test_jackyun_shipment_mapper.py + tests/planner/test_shipment_auto_resolve_pending.py + test_snapshot_retry_sweep.py + test_shipment_line_resolve.py + test_shipment_line_bulk_resolve.py` → 41/41 全过。
- **审计指南**：财务/分析报表如要剔除"非真实完成时间"的行，过滤条件：
  ```sql
  -- 仅保留上游真实回填的 completed_at
  WHERE metadata_json->>'completed_at_source' IS NULL
     OR metadata_json->>'completed_at_source' = 'upstream'
  ```
  反之要审计有多少行用了兜底：
  ```sql
  WHERE metadata_json->>'completed_at_source' LIKE 'fallback%'
  ```
- **架构选型笔记（A vs B）**：之前 0.0 已经在运维链路改了 `created_at` 锚点（A 方案），但 B 方案让所有不该关心 NULL 的下游零改动，最稳。两者并存的好处：
  - 运维链路（自动绑定/快照重试）按 `created_at` 更准（关心"行什么时候进系统"）；
  - 财务/列表/排序按 `completed_at` 不变，靠 mapper 兜底保证非 NULL；
  - metadata 标记让两套口径可审计。
- **位置**：
  - mapper：`backend/src/integrations/jackyun/mappers/shipment.py::upsert_shipment_from_payload`
  - 一次性回填：手工 Python 脚本（DB 改动幂等，已执行）

### 0.0) 「⚡ 自动绑定」候选大量漏识别 — 时间窗口锚点错误（2026-05-07 修复）

- **现象**：用户在 `/costing/biz/shipments → 待处理 → ⚡ 自动绑定` 看到候选清单只有 1 条，但实际上 SKU 主档里至少 8 条规格里明显含 `皮革桌垫 / 丝圈地垫` 关键字、按理应被 `model_keyword` 识别为 `F6A / OZU` 模型；老 `/costing/sku-master → 候选预览` 同样的 8 个 SKU 全部能匹配出来。
- **根因**：`shipment_import_service._list_pending_shipment_line_sku_codes` 之前用 `completed_at` 做时间窗口过滤：
  ```python
  models.ShipmentLine.completed_at.isnot(None),
  models.ShipmentLine.completed_at >= cutoff_at,
  ```
  这把两类常见的"待处理"行直接过滤掉了：
  1. **Jackyun 同步刚进来的新行**：吉客云的 `finishTime / sendTime` 经常没填（订单可能还没真正"完成发货"流程），mapper 会落 `completed_at = NULL` → 被 `isnot(None)` 排除；这恰恰是最新最该自动绑定的一批。
  2. **Excel 老订单回溯导入**：发货行 `completed_at` 是 1～4 月的旧时间，但 `created_at` 是今天才入库；`completed_at >= cutoff_at(30天)` 把它们排除，但业务上"刚进系统的就该自动绑"。
- **修复**：改为按 `ShipmentLine.created_at >= cutoff_at` 过滤，去掉 `completed_at IS NOT NULL` 限制。语义上更准确："最近 N 天落库到我们系统、还没出快照、SKU 未绑定 → 进入自动绑定候选池"。
- **验证**：真数据复跑 `auto_resolve_pending_shipment_lines_preview(days=30)` → 8/8 目标 SKU 全部识别（之前是 0/8）；`unique_unbound_skus` 5837 → 7680（窗口扩大正常）；`candidates_count` 1 → 44（多识别 43 个之前被漏的）。`pytest tests/planner/test_shipment_auto_resolve_pending.py` 9/9 全过（含新加 `test_auto_resolve_preview_includes_lines_with_null_or_old_completed_at` 回归用例）。
- **位置**：
  - 后端 service：`backend/src/planner/services/shipment_import_service.py::_list_pending_shipment_line_sku_codes`
  - 测试：`backend/tests/planner/test_shipment_auto_resolve_pending.py::test_auto_resolve_preview_includes_lines_with_null_or_old_completed_at`
- **类似可疑位置**：以后所有"近期 N 天 + 待处理"类查询，要先想清楚锚点应该是 `created_at`（系统视角，行什么时候落库）还是 `completed_at`（业务视角，订单什么时候完成）。**自动绑定/异常工作流应该一律用 `created_at`**；财务台账类（按发货月份/付款月份做 GMV 统计）才该用 `completed_at`。

### 0.1) 前端所有业务时间统一按北京时间展示（2026-05-07）

- **规则**：前端展示层一律使用 `frontend/src/utils/beijingTime.ts`，即 `Asia/Shanghai`。不要直接 `dayjs(value).format(...)` 或 `new Date(value).toLocaleString()`，否则服务器/浏览器时区不同会让发货管理、同步历史、审计日志显示偏差。
- **工具函数**：
  - `formatBeijingTime(value, pattern='YYYY-MM-DD HH:mm:ss')`
  - `formatBeijingRelativeTime(value)`
  - `beijingTime(value)` / `nowBeijing()`
- **已覆盖**：发货管理 Pending/Done、外部同步页、发货作业中心、SKU 主档/规格解析、长尾策略、物料/工序/虚拟物料、模型编辑器、场景/审计相关页面等。`rg "dayjs\\([^\\n]+\\)\\.format|new Date\\([^\\n]+\\)\\.toLocaleString"` 当前只应命中 `utils/beijingTime.ts` 自身。

### 1) API_BASE 与跨域

- 前端 `frontend/src/services/planner.ts` 内置了“同 host 不同端口”回退逻辑：浏览器若检测到 `VITE_PLANNER_API_BASE` 设成 `http(s)://同域:8800/...` 会回退到 `/api/planner`，避免 CORS。
- 结论：**生产联调尽量走 nginx 同源 `/api/planner`**；不要强制把浏览器 API_BASE 指向 `:8800`。

### 4) 统一 Markdown 指南（实际以纯文本展示）

- `frontend/src/guides/*.md` 通过 `?raw` 导入为字符串，在 `frontend/src/components/common/GuideDrawer.tsx` 里以 `<pre>` 纯文本展示并支持“一键复制”。
- 结论：指南内容以“可读/可复制”为第一目标；不要依赖 markdown 渲染效果（避免引入额外依赖/构建风险）。

### 2) @/* alias（构建稳定性）

- 需要同时满足：
  - `frontend/tsconfig.app.json` 有 `baseUrl="."` + `paths: { "@/*": ["src/*"] }`
  - `frontend/vite.config.ts` 有 `resolve.alias` 指向 `src`
- 若 build 报 `TS2307 Cannot find module '@/...'`，先检查以上两处。

### 3) 迁移范围控制（避免“跨文件风暴”）

- 本轮只交付一个闭环产物：**把旧编辑器迁到 `ProductModelEditorDrawer.tsx` 并接通两入口页**。
- 不要顺手重构 unrelated 组件；避免一次改动牵扯几十个文件导致 diff 巨大、交互层卡顿。

### 3.1) `/costing/shipments` 预览/上传 413（Request Entity Too Large）

- **现象**：
  - 在 `/costing/shipments` 上传发货单（xlsx）点击“预览”时提示：`Request failed with status code 413`。
- **根因**：
  - 通常是网关/Nginx 对请求体大小的限制触发（`client_max_body_size`，常见默认 1MB）。
  - 前端走 `multipart/form-data` 上传，无法在浏览器端“绕过”该限制。
- **处理**：
  - 业务侧先行：拆分 Excel（按日期/店铺/导出批次拆分），降低单文件体积。
  - 运维侧根治：放开网关/Nginx 上传限制（例如 `client_max_body_size 20m;`），并确保对以下接口路径生效：
    - `/api/planner/shipments/import/preview`
    - `/api/planner/shipments/import`

### 5) 行级变体需要 base_line_id（未保存清单无法配置）

- “变体（Overlay）”是 **version-scoped + base_line_id-scoped**：只有当版本清单行已落库（物料行有 `id`）才能创建/绑定变体规则。
- 现象：刚新增的物料行（尚未“保存清单”）点击“变体”会提示缺少 base_line_id。
- 处理：先点一次“保存清单”（PUT version lines）再配置变体。

### 6) 目标机 SSH 场景下 systemctl --user 需要 XDG_RUNTIME_DIR

- 现象：在 SSH/非交互环境执行 `systemctl --user restart planner-costing.service` 报错（无法连接 user bus / 找不到 runtime dir），导致服务无法重启。
- 处理：先执行 `export XDG_RUNTIME_DIR=/run/user/$(id -u)`，再运行 `systemctl --user ...`。

### 7) `SKU_NOT_BOUND` 的业务含义（对外文案必须解释清楚）

- **含义口径**：导入发货行时，`sku_code` 无法解析到一个“可用且已发布的标准版本（published standard version）”。
- **常见根因**：
  - 未建立 SKU→标准版本绑定
  - 绑定存在但版本未发布/被禁用（不可用于生产计算）
  - 绑定到草稿/打样版本（口径错误）
- **UI 建议**：异常队列主表按 Excel 列展示；系统字段（`bound_version_id/spec_hash/parser_version/trace`）进抽屉；`SKU_NOT_BOUND` 提示“去绑定/重试异常”。

### 8) “幂等”和“重跑”的语义容易被误解（必须提前写死）

- **误区**：做了幂等后，运营补齐绑定/升级规则，仍然“导入同文件=不再生成结果”，业务误以为系统坏了。
- **口径**：
  - 幂等只保证“不重复写同一份结果”
  - 重跑/重算必须显式触发，并产出**新快照**（不回写历史快照）
- **建议**：统一采用 3 种动作语义（见 `DOC/costing/reviews/erp_guardrails_addendum_20251222.md`）：
  - Retry Exceptions / Rerun Batch / Rebuild Snapshot（单行）

### 16) 数据洞察不要默认“全量计算”（会卡、且数据会逐步补齐）

- **结论**：数据洞察页面必须“按用户选择的时间范围查询/汇总”，默认不要全量拉取 2025 全年/全库。
- **原因**：
  - 2025 属于“边搭建边算”，导入数据可能只有部分 SKU 已绑定模型；全量计算会产生大量无意义查询与异常噪音。
  - 浏览器端全量渲染也会造成卡顿（尤其是表格/图表）。
- **实现口径（已落地）**：
  - 前端 `AfterSalesInsightsPage` 仅在用户点击“查询”后请求 `/api/planner/analytics/returns-rate/sku`，并且必须携带 `start/end/group_by` 参数。
  - 前端 `ProfitInsightsPage` 仅在用户点击“查询”后请求 `/api/planner/analytics/profit/sku` 或 `/api/planner/analytics/profit/model`，并且必须携带 `start/end/group_by` 参数。

### 18) 三张洞察页都是空（最常见原因：未导入数据）

- **现象**：打开“售后分析/模型分析/店铺数据”，选择范围后查询仍然返回空数组。
- **最常见根因**：库里还没有发货/售后数据（当前阶段先靠 xlsx 上传导入，后续才会接 ERP API）。
- **处理**：
  - 发货单：到 `/costing/shipments` 上传发货单（预览→执行）
  - 售后退货单：到 `/costing/insights/after-sales` 上传售后退货单（xlsx 导入）
  - 再回到洞察页选范围点“查询”

### 17) pytest（SQLite）报 “no such table …”（测试库建表不完整）

- **现象**：
  - 运行某些单测（例如 `backend/tests/planner/test_after_sales_import_mvp.py`）报：
    - `sqlite3.OperationalError: no such table: shipment_import_batches`
- **根因**：
  - `Base.metadata.create_all()` 只会创建“已被 import 过、已注册到 Base”的表。
  - 若测试初始化（`backend/tests/planner/conftest.py`）在 `create_all()` 之前没有 import `src.planner.models`，则发货/售后/分析等表不会被建出来。
- **修复口径**（已落地）：
  - 在 `backend/tests/planner/conftest.py` 中提前 `import src.planner.models`（仅用于注册表到 `Base.metadata`），再执行 `Base.metadata.create_all()`。

### 14) 方案文档“方向互补”容易被误读（别拿错主线）

- **现象**：有人把 `DOC/基础表单/BOM系统优化完整方案_最终版.md` 当成“当前发货导入/对账主线”的实施依据，导致讨论跑偏（该文档重点在 30% 复杂套装：编码抽取、模型套模型、自动编码与运营流程）。
- **口径**：
  - “发货时再解析（导入 xlsx → spec_hash 缓存解析 → BOM 快照 → 异常队列）”主线以 `DOC/costing/blueprints/sku_binding_bom_shipment_plan.md` 为准，并以快照不回写/可重跑为硬约束。
  - 《BOM系统优化完整方案》作为 **复杂产品扩展路线**（与主线互补），用于后续迭代“非规则型套装/编码治理/运营流程”。

### 15) 售后/发货导出字段未开启会影响“模型退货率/净利润”归因（必须开启强关联键）

- **现象**：如果 ERP 导出时没有开启“网店订单号/原始单号 + 商品链接ID + 货品条码”，售后行只能做弱匹配，模型归因会不可靠。
- **影响**：
  - “退货率（货品维度）”可以直接按 `货品编号 + 渠道 + 规格` 与发货行做弱关联或直接用 `货品编号` 聚合统计。
  - “退货率（模型维度）/退货导致的成本归因”必须能关联到某条发货行或某个 BOM 快照；否则只能落入“待关联异常队列”，无法严谨归因到模型/版本。
- **专业做法**：
  - 必须开启导出字段：
    - 发货：`原始单号` + `商品链接ID` + `货品条码` + `交易规格` + `完成时间` + `数量` + `金额` + `销售渠道`
    - 售后：`网店订单号` + `商品链接Id` + `货品条码` + `申请时间` + `退货数量` + `退货金额` + `退换原因` + `销售渠道`
  - 在强键齐全时：优先用 `order_no + product_link_id + sku_code` 做强匹配；缺失时才回退到弱匹配，并记录 `match_method/confidence/explanation` 供人工确认。
- **附带提醒**：售后表自带 `货品成本/毛利/毛利率` 多为上游计算列，建议仅留痕；本系统 2025 分析口径以“BOM 快照 + 当前价估算 + 可配置 Run 参数集”为准。

### 11) 店铺对接（集成）别一上来就做“深 API 对接”

- **推荐最低成本路径（Phase0）**：先做“店铺数据导出 → 转换为系统发货导入 xlsx → 上传到 `/costing/shipments`”，用最小数据量验证：
  - SKU 主档是否能覆盖（是否大量 `SKU_NOT_BOUND`）
  - `spec_text` 是否能解析出尺寸/tokens
  - BOM/扣库清单是否符合业务口径
- **原因**：单店深对接成本高（你们反馈 18 万/店），而当前系统已具备 xlsx 导入 + 快照/异常闭环，适合先做可验收的 PoC。
- **参考简报**：`DOC/agents/briefings/integration_shop_connector_onboarding_mvp.md`

### 12) 小程序接入：本地服务器“直接用”通常不可行

- **结论**：小程序端请求必须走“合法域名 + 公网 HTTPS”。纯内网/局域网 IP 的“本地服务器”无法直接被小程序访问。
- **可行路径**：
  - 用 Nginx/网关把后端 API 与文件下载 **通过公网域名暴露**（同源 `/api/...` 优先），并配置鉴权/限流
  - 图片上传优先直传对象存储（OSS/S3），后端只拿 `storage_key` 拉取生成效果图/印刷稿（避免网关带宽瓶颈）
- **参考蓝图**：`DOC/costing/blueprints/pod_personalization_print_pipeline_phase0.md`

### 9) 前端报错：Failed to load module script（MIME type: text/html）

- **现象（Chrome 控制台）**：
  - `Failed to load module script: Expected a JavaScript-or-Wasm module script but the server responded with a MIME type of "text/html".`
  - `Failed to fetch dynamically imported module: http(s)://<host>/assets/<chunk>.js`
- **本质**：浏览器在加载 `/assets/*.js`（hash chunk），但 Nginx 返回了 `index.html` 或 404 页面（`Content-Type: text/html`）。
- **常见根因**：
  - **非原子部署**：发布过程中 `index.html` 先更新，但 `/assets` 还没同步完，导致旧入口去拉新/旧 chunk 失败。
  - **Nginx 错误回退**：对 `/assets/*` 也做了 SPA 回退（`try_files ... /index.html`），把 404 的 chunk 回退成 HTML，触发严格 MIME 校验失败。
  - **缓存策略错误**：`index.html` 被缓存（或中间缓存/CDN 缓存），导致客户端拿到旧入口，但服务器已换了新 assets。
- **彻底修复（必须同时满足）**：
  - 发布侧：静态发布必须**原子切换**（先写临时目录，再一次性切换目录）。脚本：`frontend/scripts/deploy_static.sh`
  - Nginx：
    - `index.html`：`Cache-Control: no-cache`（永远拿最新入口）
    - `/assets/*`：`Cache-Control: public, max-age=31536000, immutable`
    - `/assets/*`：不要回退到 `index.html`，应 `try_files $uri =404`

### 19) BrowserRouter 深链接 404（直接打开 `/costing/...` 显示 Not Found）

- **现象**：
  - 直接访问例如 `https://work.znma.com/costing/insights/models` 返回 `Not Found`（但从首页点菜单进入通常正常）。
- **根因**：
  - 前端使用 `BrowserRouter`（history 模式）。当你直接打开一个“深路径”，服务器需要把该路径回退到同一个 `index.html`，否则会按“静态文件不存在”返回 404。
- **根治（推荐，Nginx 配置）**：
  - 对 SPA 路由前缀开启 history fallback（示例）：
    - `try_files $uri $uri/ /index.html;`
  - 注意：对 `/assets/*` **不要**回退到 `index.html`（否则会触发 §9 的 MIME=text/html chunk 加载失败）。
- **代码侧兜底（已落地，减少对 Nginx 的依赖）**：
  - `npm -C frontend run deploy:static` 在 `vite build` 后会执行 `frontend/scripts/generate_spa_fallbacks.mjs`：
    - 自动把 `dist/index.html` 复制到 `dist/<route>/index.html`（例如 `dist/costing/insights/models/index.html`）
    - 这样即便 Nginx 只支持“目录 index.html”，也能更容易命中并加载 SPA
- **快速自检**：
  - 构建后：`test -f frontend/dist/costing/insights/models/index.html`
  - 发布后（目标机）：`test -f /var/www/html/ai-costing/dist/costing/insights/models/index.html`
  - 若你确认生成了但线上仍 403：检查 `frontend/scripts/deploy_static.sh` 是否误排除了子目录 `index.html`（旧版本 `--exclude "index.html"` 会误伤；应为 `--exclude "/index.html"`）。

### 10) 后端 500：Postgres 要求加密连接（no encryption）

- **现象**：
  - 前端轮询任务角标：`GET /api/planner/task-center/recent` 报 500
  - 后端日志出现：`pg_hba.conf rejects connection ... no encryption`
- **根因**：数据库实例/链路对 SSL 的要求不一致，需要用 `sslmode` 明确策略。
- **额外说明**：如果 Postgres **未续费/不可达**，也会表现为全站 DB 接口 500（processes/taxonomy 等），此时需要先恢复数据库服务本身。
- **修复**：
  - 代码在 `backend/src/database.py` 默认设置 `sslmode=prefer`（尽量兼容：能 SSL 就 SSL，不能就退回明文）
  - 如遇 `pg_hba.conf rejects ... no encryption`（服务端强制加密）：设置环境变量 **`PLANNER_PG_SSLMODE=require`**
  - 如遇 `server does not support SSL, but SSL was required`（链路/代理不支持 SSL 协商）：设置环境变量 **`PLANNER_PG_SSLMODE=disable`**

### 20) 洞察类接口 500：MySQL/MariaDB 下时间分组函数不兼容（strftime/julianday）

- **现象**：
  - 打开洞察页（例如售后仪表盘 `/costing/insights/after-sales`）提示：`Request failed with status code 500`。
  - 后端对应接口（例如 `/api/planner/analytics/after-sales/dashboard`）在 MySQL/MariaDB 环境执行时报 SQL 函数错误。
- **根因**：
  - 后端 `analytics_service` 的 “sqlite/mysql fallback” 若误用 sqlite 专用函数（如 `strftime/julianday/date(...,'weekday')`），在 MySQL/MariaDB 会直接报错。
- **修复**：
  - 升级到包含以下改动的版本（本仓库已落地）：
    - `backend/src/planner/services/analytics_service.py`：为 `mysql/mariadb` 方言使用 `DATE_FORMAT/CONCAT/DATEDIFF` 实现 day/month/week 分组与 lag 计算。

### 13) 全站列表/记录都空或 500：DNS 被 Tailscale/NetworkManager 接管导致公网域名解析失败

- **典型现象**：
  - 页面能打开（静态资源正常、`/api/planner/health` 仍可能返回 200）
  - 但所有依赖 DB 的接口（materials/processes/taxonomy/virtual materials…）全 500 或“列表无记录”
  - 同时“同步宜搭/钉钉”也会失败（钉钉域名解析不到）
- **后端日志关键字**：
  - `could not translate host name "<pgm-xxx>.pg.rds.aliyuncs.com" to address: Name or service not known`
- **快速确认**（返回空/报错即为 DNS 问题）：
  - `getent hosts pgm-xxx.pg.rds.aliyuncs.com`
  - `getent hosts oapi.dingtalk.com`
  - `cat /etc/resolv.conf`
    - 若看到 `nameserver 100.100.*`（Tailscale DNS）或仅 tailnet search，通常就是被接管且上游不可用
- **修复口径（推荐：不影响 Tailscale 通道，但停止接管全机 DNS）**：
  - 关闭 Tailscale 接管 DNS：`sudo tailscale set --accept-dns=false`
  - 若 `/etc/resolv.conf` 仍被 NetworkManager 写成 `100.100.*`，把主网卡连接改为忽略自动 DNS 并指定可用 DNS：
    - `nmcli -t -f NAME,DEVICE,TYPE connection show --active`
    - `nmcli connection modify "<NAME>" ipv4.ignore-auto-dns yes ipv4.dns "223.5.5.5 114.114.114.114"`
    - `nmcli connection up "<NAME>"`
  - DNS 恢复后建议重启后端服务以重建连接池：`systemctl --user restart planner-costing.service`（注意 SSH 场景要设置 `XDG_RUNTIME_DIR`）

### 22) 吉客云（Jackyun）开放平台对接的若干「文档骗你」陷阱

- **现象**：照官方/旧 SDK 文档对接 Jackyun 时，DNS、参数名、签名、成功判定都很容易写错，且报错信息会指引到错误方向（比如说「参数缺失」其实是网关选错了）。
- **快速定位真相**：
  - 真正的开放平台网关是 `https://open.jackyun.com/open/openapi/do`（**不是** `openapi.jackyun.com`，**不是** `/wms/service`）
  - 公参全部一个词、小写：`appkey` / `version` / `contenttype` / `bizcontent`（**不是** `app_key` / `v` / `format` / `biz_content`）
  - 签名最后一步要 `.toLowerCase()` 再 MD5（Java SDK 里有，Python 容易漏）
  - 成功判定看 `code == 0`（**不是** 200），且 `subCode` 为空/全零
  - 单次 `startModifyTime~endModifyTime` 窗口硬性 ≤ 24 小时（已在 sync_jobs 自动按天切片）
  - 接口 `wms.order.query-info.page.v2` 是「**未完成**发货单」子集；全量同步要用 `wms.order.query-info.page`
  - 该接口的 `pageInfo.total` 不可信（经常返回 0），分页只能靠「短页」判终止
- **完整契约 + 排错路径 + 历史踩坑**：见 `DOC/costing/runbooks/jackyun_integration.md`
- **测试守门**：`backend/tests/integrations/test_jackyun_*.py`（client_contract / window_splitter / watermark_policy / shipment_mapper / routes），57 个用例，改 client/sync_jobs 前后必须跑一遍

### 23) SKU 治理与按需建模（4 态 + 长尾兜底成本）

- **背景 / 设计哲学**：100 万级 Jackyun SKU 不可能预导入或预建模，所以采用「发货时按需建档 + 4 态人工审核 + 长尾兜底成本」的治理模型。详细方案：`DOC/costing/runbooks/jackyun_integration.md` §SKU 治理。
- **4 态语义**（落在 `SkuMaster.metadata_json.governance_status`，无 Alembic 迁移）：

  | 状态 | 含义 | worker 行为 | UI 出现位置 |
  |---|---|---|---|
  | `unmanaged` | 默认；运营还没看过 | 入异常队列 `SKU_NOT_BOUND` | BatchWorkbench → 异常队列 |
  | `auto_bound` | 已绑定 published 模型版本 | 正常解析 + BOM snapshot | BatchWorkbench → 已就绪/快照 |
  | `pending_model` | 决定要建模，模型还没发布 | 入异常队列 `MODEL_PENDING`(新 reason) | ShipmentOpsPage → 建模 Backlog Tab |
  | `do_not_model` | 长尾，一月一单不值得建 | **静默跳过**异常 + 写「长尾兜底快照」 | ShipmentOpsPage → 长尾 SKU Tab |

- **关键 API**（`/api/planner/sku-master/governance`）：
  - `POST /sku-master/governance` — body `{sku_codes, status, decided_by, note}`，批量设置（带 audit history）
  - `GET /sku-master/governance?status=...` — 列表（带最近 N 天发货统计供运营按销售额排序）
  - `POST /sku-master/governance/promote-from-model` — 模型发布完成后批量 `pending → auto_bound`
- **长尾兜底成本**（Sprint 3-2）：
  - `do_not_model` SKU 的 cogs 估算 = `revenue × settings.long_tail_cogs_rate`（默认 0.55，财务一年校准一次）
  - 写入 `BomSnapshot.trace_json.kind='long_tail_fallback'` + `ShipmentCostingResult.metadata_json.kind='long_tail_fallback'`，报表可以原样累加无需特判
  - 关闭：`LONG_TAIL_COGS_FALLBACK_ENABLED=False`（cogs=0；会导致利润虚高）
- **常见踩坑**：
  - 看到异常队列里同一个 SKU 反复出现 → 说明运营没做 4 态决策，建议加入 backlog 或标记长尾
  - 模型已建但 `pending_model` 状态没自动转 `auto_bound` → 模型发布流程要 hook `auto_promote_pending_model(sku_codes=[...])`
  - 长尾兜底快照不出现在「批量计价」列表 → 它有 `model_version_id IS NULL`，确认计价 query 没把它过滤掉
- **测试守门**：
  - `backend/tests/planner/test_sku_governance.py`（14 用例，状态机 / 审计 / 排序）
  - `backend/tests/planner/test_sku_governance_routes.py`（HTTP 合约 5 用例）
  - `backend/tests/planner/test_shipment_import_governance_gating.py`（worker 分支 4 用例）
  - `backend/tests/integrations/test_jackyun_sprint1_pipeline.py`（端到端 6 用例：mapper → worker → 异常队列）

### 25) 前端改了代码 + npm run build 完，线上仍然看不到变化（部署目录两套）

- **现象**：本地 `frontend/dist` 已重新构建（时间戳更新），浏览器强刷后顶部 Tab / 新按钮仍未出现。
- **根因**：nginx 配置里 `root /var/www/html/ai-costing/dist;`（见 `/etc/nginx/conf.d/work-https.conf`），**不是**仓库内的 `~/ai-costing-system/frontend/dist`。两个 dist 目录是物理拷贝关系，不是 symlink。`npm run build` 只更新仓库内 dist，**不会自动同步到 nginx 目录**。
- **2026-05-06 实际遭遇**：Sprint 1-3 前端改完跑 `npm run build`，浏览器看不到「建模 Backlog」「长尾 SKU」Tab；查 `stat /var/www/html/ai-costing/dist/index.html` 发现仍是当天上午 12:05 的旧产物。
- **修复 / 标准部署命令**：
  ```bash
  cd ~/ai-costing-system/frontend
  npm run build
  rsync -av --delete dist/ /var/www/html/ai-costing/dist/
  # nginx 不需要 reload (root 是目录,不是配置变化)
  # index.html 已配 Cache-Control: no-cache,普通 F5 即可生效
  ```
- **建议**：把这两步合并到 `package.json` 的一个 script，例如 `npm run deploy`，避免再忘。
- **如何快速判断是不是这个问题**：`stat -c '%y' /var/www/html/ai-costing/dist/index.html` 跟 `stat -c '%y' ~/ai-costing-system/frontend/dist/index.html` 对比，时间不一致就是没同步。

### 24) 4 个 pre-existing 测试失败（与 SKU 治理 / Jackyun 集成无关，独立问题）

- **背景**：2026-05-06 验收 Sprint 1-3「SKU 治理与按需建模」时跑全套 `pytest`，4 个失败用例**均不在本次改动域内**（Sprint 1-3 改动域：`sku_master_service` / `shipment_import_service` / `shipment_import_worker` / `Jackyun mappers` / `routers/sku_master` / 前端 `BatchWorkbench` & `GovernanceBacklogTab`）。先记录避免下次 agent 误以为是新引入。
- **失败清单**：

  | 测试 | 根因 | 修复方向 |
  |---|---|---|
  | `tests/planner/test_migrations.py::test_alembic_upgrade_creates_tables` | `backend/migrations/versions/0031_expand_tag_columns_to_text.py` 用 `op.alter_column(..., type_=sa.Text())` 修改列类型；SQLite 不支持 `ALTER TABLE ... ALTER COLUMN ... TYPE TEXT`，CI/本地 SQLite 跑迁移就会炸 | 改用 `with op.batch_alter_table('shipment_lines') as batch: batch.alter_column(...)`，对 PG 透明，对 SQLite 走 copy-and-rename。同 patch 修 0031 的 `after_sales_lines` 段 |
  | `tests/planner/test_bom_generate_by_spec_bundle_selector.py::test_generate_by_spec_bundle_selector_A_forces_first_phrase_preset` | bundle phrase_preset 「mode=force + selector=A」期望强制取首条 preset 的 components_list，实测拿到的是别的分支 | 看 `bom_generation_service.generate_bom` 里 selector A 的优先级判断；可能是某次 preset 排序/匹配规则改动后没回归到这个用例 |
  | `tests/planner/test_bom_generate_by_spec_bundle_selector.py::test_generate_by_spec_bundle_selector_prefers_preset_components_list` | preset 自带 components_list 应优先于模型默认 components；实测取了模型默认 | 同上，`bom_generation_service` preset 注入逻辑回归 |
  | `tests/planner/test_spec_parser_code_tokens.py::test_parse_spec_extracts_bundle_code_tokens` | `spec_text="组合装BUNDLE:K8F3J2 40X50"` 期望 tokens 里出现 `B:K8F3J2`、`BUNDLE:K8F3J2`，实测只有 `K8F3J2 40X50`（连 `BUNDLE:` 前缀都没分出来） | `spec_parser_service.parse_spec` tokenizer 缺 `BUNDLE:` 前缀的特化规则；要补一条正则 `r'BUNDLE:([A-Z0-9]+)'` → emit 双 token (`BUNDLE:CODE` + `B:CODE`) |

- **影响范围**：
  - 0031 迁移问题：**线上 PostgreSQL 不受影响**（PG 支持原生 `ALTER COLUMN TYPE`）；只影响开发者本地 / CI 用 SQLite 跑全套迁移测试。
  - bundle selector 2 个用例：可能影响**某些套装模板的 BOM 生成结果**；建议先在 SkuMaster 报表里抽样核对几个 bundle SKU 的 BOM 是否符合预期，再决定优先级。
  - bundle code token：影响**通过 `BUNDLE:CODE` 前缀做匹配的 spec 规则**（如果项目内有规则用了这个前缀就会失效）。
- **建议修复优先级**：低（除非真的在用 BUNDLE: 前缀规则）；3 个 bundle 相关失败可以等下一次 BOM/bundle 系统迭代时一起带上。**0031 迁移问题**是最简单的，5 分钟就能 batch_alter_table 包一下。
- **跑测试时的稳定基线**：`pytest --ignore=tests/planner/test_migrations.py --ignore=tests/planner/test_bom_generate_by_spec_bundle_selector.py --ignore=tests/planner/test_spec_parser_code_tokens.py` → 175 passed。

### 26) 「📦 业务管理 → 🚚 发货管理 → 🔴 待处理」存在 2 个并行的"自动绑定"入口（防误用 + 后续可合并）

- **背景**：2026-05-07 重构「业务管理」三级菜单时，新增了「📦 业务管理」一级菜单（区别于老的"系统运维 / SKU 主档"），目标是让"上架员"用更简单的视图处理日常发货。但**老的全自动绑定能力**（`/costing/sku-master > 自动识别` Tab 的"候选预览/执行绑定/一键跑完"三按钮，覆盖率 ~50% / 8.3 万 SKU）一开始**没有**接进新页面，导致新页面上线时新员工拿到的是"100% 手动逐条选模型"的退化体验。
- **现状（已修复）**：在「待处理」Tab 顶部加了**条件性横幅**「⚡ 系统能自动识别 N 个 SKU」+「⚡ 一键自动绑定全部」+「🔍 查看候选清单 + 选择性绑定」按钮，调用新加的后端接口：
  - `POST /api/planner/shipments/lines/auto-resolve/preview` —— 找最近 N 天**仍是 pending 的发货行**对应的未绑定 SKU，跑同样的 keyword/code-hint 识别算法，返回候选清单
  - `POST /api/planner/shipments/lines/auto-resolve/execute` —— 绑定 + **立刻为相关行出 BomSnapshot + 解决 SKU_NOT_BOUND 异常队列**（不用等 worker 异步重跑）
- **2 个入口的差异**：

  | 维度 | 老入口 `/costing/sku-master > 自动识别` | 新入口 `/costing/biz/shipments > 待处理 banner` |
  |---|---|---|
  | 候选范围 | **全部** ~7.8 万未绑定 SkuMaster | 只有最近 N 天 pending 的 ShipmentLine 涉及的 SKU |
  | 一次能识别的量 | 大（万级） | 小（几十~几百，仅活跃发货） |
  | 后续动作 | 仅绑定 → 等 worker 下次扫到该 SKU 出快照 | 绑定 + **立刻**出快照 + **立刻**关闭异常 |
  | 适用场景 | 大批量历史 SKU 治理（管理员） | 日常发货上架员"跟进今天卡住的订单" |
  | UX | 工程师视角（候选预览 / 命中视图 / 一键跑完） | 业务视角（一行字 + 一个按钮） |

- **算法是同一套**：底层都调 `sku_master_service.auto_bind_preview`（新加了 `restrict_to_sku_codes` 参数让新入口能限定范围），所以"识别准不准"两边一致；区别只在**圈定哪些 SKU 进入识别器**。
- **2 个入口为什么先并存**：
  - 不能直接把老入口废弃 — 历史治理场景（管理员一次绑几万 SKU）新入口的"跟着发货走"模式覆盖不到。
  - 不能直接把新入口的横幅删掉 — 上架员的日常工作要的就是"今天有多少能立刻自动处理"。
  - 后续如果发现两边覆盖率高度重合（90%+），可以考虑合并；但现阶段并存。
- **未来 backlog（不在本次范围）**：
  - **Issue 27 — 自动按 spec 推荐模型（置信度匹配引擎）**：当前算法只对"已发布模型有 `recognition_keywords` 关键字 / spec_text 含模型代码提示"的 SKU 自动绑定；规格描述模糊的（占长尾大头）依然要人工。下一步可加"按品类关键字打分 → 推荐 top-N + 置信度"，把「待处理」表格的"系统提示"列从"无对应模型"升级成"系统建议: 画框-024（置信度 0.78）"。
  - **Issue 28 — 长尾 COGS 按品类策略表 ✅ 已完成（2026-05-07, v1.0 minimal 版）**：
    - **现状**：之前 `settings.long_tail_cogs_rate=0.55` 对所有长尾 SKU 一刀切。画框毛利率 ~60% / 抱枕 ~40% / 地毯 ~50% 差异很大，单一比率会让品类利润互相掩盖。
    - **新增表**：`long_tail_cogs_rate_strategies`（migration 0035）字段 `category` (unique) / `rate` (Decimal 0–1) / `keywords` (JSON 数组) / `priority` (int) / `enabled` (bool) / `note` / `metadata.history`（最近 20 次改动审计）。
    - **匹配优先级**（`long_tail_strategy_service.resolve_rate_for_sku`）：① `SkuMaster.metadata.long_tail_category` 人工指定 → ② keyword 命中 spec_text+product_name+product_code+barcode（priority 高优先，case-insensitive substring）→ ③ category='default' 兜底策略 → ④ 全局 `settings.long_tail_cogs_rate` 兼容回落。
    - **审计设计**：每次改 rate 仅写入 `metadata.history`，**不**回写历史 BomSnapshot/ShipmentCostingResult — 它们的 `trace_json` 已经记录了当时使用的 rate + source + strategy_id，财务报表保持稳定。
    - **接口位置**：
      - 后端 service：`backend/src/planner/services/long_tail_strategy_service.py`（CRUD + resolve）
      - 后端 router：`backend/src/planner/routers/long_tail_strategies.py`
        - `GET /api/planner/long-tail-strategies` — 列出 + global_fallback_rate
        - `POST /api/planner/long-tail-strategies` — 新建（category 唯一、rate ∈ [0,1]）
        - `PATCH /api/planner/long-tail-strategies/{id}` — 部分更新
        - `DELETE /api/planner/long-tail-strategies/{id}?actor=...` — 软删（is_archived=true）
        - `POST /api/planner/long-tail-strategies/resolve-preview` — 试算工具
      - 后端集成：`shipment_import_service._generate_long_tail_fallback_snapshot` 已切换为调 `resolve_rate_for_sku`，trace_json 多记 `rate_source` / `strategy_id` / `strategy_category` / `matched_keyword`。
      - 前端 service：`frontend/src/services/longTailStrategy.ts`
      - 前端页面：`frontend/src/pages/costing/admin/LongTailCogsRatePage.tsx`，路由 `/costing/admin/long-tail-cogs-rate`，菜单挂在「⚙ 系统运维 → 💰 长尾成本策略」。
    - **测试守门**：`backend/tests/planner/test_long_tail_strategy.py` 16/16（CRUD 5 + resolve 优先级 6 + integration 2 + HTTP 3）；regression `test_shipment_import_governance_gating` / `test_sku_governance` / `test_shipment_auto_resolve_pending` / `test_jackyun_sprint1_pipeline` 共 36 个测试全过。
    - **回归 Bug 修复（顺手）**：`ShipmentLinesAutoResolveExecuteResponse` 之前误删了 `snapshot_errors` / `items` 字段（recent-stats schema 修复时被一并删掉），本次补回；`test_auto_resolve_execute_binds_and_creates_snapshot` 重新通过。
    - **未做（minimal 版意识地砍掉）**：① 反向回填给历史 SKU 自动打 long_tail_category（已经被下面"最后一公里"覆盖了）；② rate 改前后利润对比报表。
    - **2026-05-07 最后一公里 — 长尾池可手动标 long_tail_category**：策略表上线后发现"人工指定"分支没出口（只能走关键字 / 默认），运营无法在 SKU 端覆盖品类。
      - **后端**：`sku_master_service.set_sku_long_tail_category(sku_codes, category, actor, note)` — 校验 category 必须存在于 enabled 策略表（or 空字符串清除）+ 写 `metadata.long_tail_category_history`（最近 20 条 audit）。
      - **后端**：`POST /api/planner/sku-master/long-tail-category` body `{sku_codes, category, actor?, note?}` → `{updated, unchanged, missing, cleared}`。
      - **后端**：`list_governance_backlog` 的 item 顺手携带 `long_tail_category` / `long_tail_category_decided_at` / `long_tail_category_decided_by`，前端长尾 Tab 直接渲染。
      - **前端**：`GovernanceBacklogTab`（do_not_model 分支）新增「当前品类」列 + 行操作「📂 标品类 / 改品类」按钮 + rowSelection 批量「📂 批量标品类」（顶部 Alert 工具栏）；弹窗下拉来自策略表 enabled 项，「清除标注」按钮一键撤销。
      - **关键 bug 修复（顺手）**：`create_strategy` 之前对同名 archived 策略会 400（unique 约束阻止 INSERT）。改为：检测到同名 archived 行 → **复活**（覆盖字段 + 写 `change_note='revived'`），active 同名仍 400。新增测试 `test_create_revives_archived_same_category` + `test_create_active_duplicate_still_400`。
      - **测试守门**：`backend/tests/planner/test_sku_long_tail_category.py` 9 个用例（set/clear/audit/校验/批量/cross-feature with snapshot resolver/HTTP）；regression 含 long_tail_strategy + governance + auto_resolve 共 58 个测试全过。
      - **位置**：service `sku_master_service.set_sku_long_tail_category`；router `sku_master.set_sku_long_tail_category`（路由路径 `/long-tail-category`，必须放在 `/{sku_id}` 之前，否则被吃成 404）；前端 service `setSkuLongTailCategory`；前端组件 `GovernanceBacklogTab.tsx`（do_not_model 专属代码段）。
    - **2026-05-07 最后一公里 v2 — ⚡ 一键自动标长尾品类**：手动标完之后用户立刻问"能不能自动？"。把策略表的 keyword 匹配从"出快照时才用"提前到"事先批量打标"。
      - **后端**：`long_tail_strategy_service.match_keyword_strategy(enabled, haystack_lower)` 抽出纯函数（resolve_rate_for_sku 也复用），避免重复实现。
      - **后端**：`sku_master_service.auto_suggest_long_tail_category(sku_codes?, include_already_labeled=False, limit=5000)` 扫描 + 推荐；`auto_apply_long_tail_category` 一键应用（按品类分组调 `set_sku_long_tail_category`，actor='auto-suggest'，note='auto-applied via keyword match'）。
      - **关键设计 - 不覆盖人工**：`include_already_labeled=False`（默认）跳过已经手动标过的 SKU，避免覆盖人工决策。要重打必须显式传 True。
      - **路由**：`POST /sku-master/long-tail-category/auto-suggest/preview`（dry-run, 返回候选清单）+ `/execute`（一键写入）。preview 60s timeout, execute 120s timeout（前端 service 默认值）。
      - **前端**：`GovernanceBacklogTab.tsx` 长尾 Tab 顶部新增「⚡ 一键自动标品类」按钮 → 点击 preview → 候选清单抽屉（统计卡 / 全选 / 单条勾选 / 一键应用 N 条 with Popconfirm）。抽屉里展示 sku_code / 当前品类 / 推荐品类 / 命中关键字 / rate / 规格商品名。
      - **测试守门**：`backend/tests/planner/test_long_tail_auto_suggest.py` 9 个用例（无策略 reason / scope=all do_not_model / scope=显式 sku_codes / 跳过已标 / include 已标 / priority 决胜 / no_match 计数 / auto_apply 按品类分组写入 + audit / HTTP preview+execute+幂等 re-preview）；regression 67/67 全过。
      - **smoke 测试**（生产数据上）：长尾池只 1 条 SKU 已标 → preview 返回 scanned=1 skipped=1 suggested=0；execute applied=0（防覆盖兼容）；`include_already_labeled=true` 时返回 1 条候选并命中"砂岩"策略；不存在 sku_codes 走显式分支返回 scanned=0。
      - **位置**：service `sku_master_service.auto_suggest_long_tail_category` / `auto_apply_long_tail_category`；router `sku_master.auto_suggest_long_tail_category_{preview,execute}`；前端 service `autoSuggestLongTailCategory{Preview,Execute}`；前端 UI `GovernanceBacklogTab.tsx`（autoDrawerOpen / autoPreview / autoSelectedKeys + Drawer 块）。
  - **Issue 29 — 合并 bind+spec+snapshot 为一个 `/resolve` 接口 ✅ 已完成（2026-05-07）**：把 `frontend/src/services/planner.ts::resolveShipmentLine` 的前端 4 步串行替换为单次后端调用。
    - **Endpoint**：`POST /api/planner/shipments/lines/{shipment_line_id}/resolve`
      - body：`{"action": "adopt"|"mark_long_tail"|"defer_modeling", "model_id"?, "operator_id"?, "note"?}`
      - response：`{ok, action, shipment_line_id, snapshot_id?, snapshot_action?, error?, steps[]}` — 保留 step audit 兼容前端错误展示。
    - **后端逻辑**（`shipment_import_service.resolve_shipment_line`）：
      - `mark_long_tail` / `defer_modeling`：只调 `set_sku_governance` 一步（snapshot 不强制；长尾走 worker 下次扫到时按策略 rate 自动出快照；pending_model 没绑模型不能出快照）。
      - `adopt`：4 步在**单事务**内 — `lookup_sku_master` → `bind_sku_master_by_model(allow_rebind=True)` → `set_sku_governance(auto_bound)` → `compute_snapshot_for_shipment_line(overwrite=True)`。任何一步抛异常 → `db.rollback()` + 返回 `ok=false` + `steps[]` 完整 audit。
      - **关键设计 - 软失败 vs 硬失败**：找不到 line / unknown action 抛 `ValueError` → router 翻 400；line 没 sku_code / adopt 没 model_id / 找不到 SkuMaster / snapshot=failed 都返回 200 + `ok=False` + 详细 `steps[]`，让 UI 能告诉用户"哪一步出问题"。
    - **前端**：`frontend/src/services/planner.ts::resolveShipmentLine` 内部从"4 次串行 axios"改成单次 POST。**函数签名 / 返回类型 0 改动**，所有调用方（`PendingTab` / `BatchWorkbench` 等）零修改。BomSnapshot 完整对象不在响应里（只有 snapshot_id），调用方目前只用 `result.snapshot ? '已出快照' : ''` 判断 → 用 `{id: snapshot_id}` 占位对象保持类型契约。
    - **测试守门**：`backend/tests/planner/test_shipment_line_resolve.py` 12 个用例（unknown action 抛 ValueError / missing line 抛 ValueError / 缺 sku_code 软失败 / mark_long_tail 写治理 / defer_modeling 写治理 / adopt 缺 model_id 软失败 / adopt 缺 SkuMaster 软失败带 step audit / adopt 完整路径 bind+governance+snapshot / adopt 幂等重跑无重复快照 / 3 个 HTTP 端到端）；168 个 planner 测试中 168 全过（4 个失败是预先存在的，跟 Issue 29 无关 - migrations / spec_parser / bom_generate_by_spec_bundle_selector）。
    - **smoke 测试**（生产数据）：`defer_modeling` 单步 4ms（vs 过去前端 4 次串 ~1.5-2s）；unknown line → 400 中文 detail；adopt 无 model_id → 200 + ok=false + error。
    - **位置**：service `shipment_import_service.resolve_shipment_line`；router `routers/shipments.py::resolve_shipment_line`（路径 `/lines/{shipment_line_id}/resolve`）；schema `ShipmentLineResolveRequest/Response/Step`；前端 service `frontend/src/services/planner.ts::resolveShipmentLine`（实现重写，签名不变）。
### 32) ⏳ "等出快照(系统处理中)" 不再是空头支票（2026-05-07，snap-retry-sweep）
- **问题**：发货管理待处理 Tab 的 `⏳ 等出快照(系统处理中)` tooltip 写"系统 worker 5-10 分钟内自动出快照"，但**没有**真正的自动 worker — 主 `shipment_import_worker` 只处理 `batch.status='queued'/'processing'`，一旦 batch=success 就不回头。结果是：用户给某 SKU 手工绑了模型后，这条 line 永远卡在 ⏳。生产里有 92 条这种 bound-no-snapshot 的孤儿 line。
- **根因**：worker 的 scope 是 batch 级别的 finalize；line 级别的"先排队 → 后绑定"路径没有 catch-up 机制。
- **修复**：`shipment_import_service.sweep_bound_lines_missing_snapshot(lookback_days=14, limit=200)` — 找 pending 且 SKU 已绑模型的 line，逐条调 `compute_snapshot_for_shipment_line(overwrite=False)` 出快照。挂在 `shipment_import_worker._loop` 上，每 5 分钟触发一次（`PLANNER_SHIPMENT_SNAPSHOT_RETRY_INTERVAL_SECONDS`），与主 batch 处理共享 advisory lock。
- **关键设计**：
  - SQL 用 `EXISTS` 子查询查 binding，避免 N+1（教训：Issue 26 / 31）
  - lookback 14 天 + limit 200 → 单次扫描 ~3.7s（生产实测）
  - `compute_snapshot_for_shipment_line(overwrite=False)` 自身是幂等的，二次扫描不会重做
  - 失败行不影响其他行，只在日志里采样前 5 条 detail
  - 失败时 `_last_snapshot_sweep_at` 倒退 30 秒，避免错误时疯狂重试
- **配置**（`backend/src/config.py`）：
  - `PLANNER_SHIPMENT_SNAPSHOT_RETRY_ENABLED=True`
  - `PLANNER_SHIPMENT_SNAPSHOT_RETRY_INTERVAL_SECONDS=300`
  - `PLANNER_SHIPMENT_SNAPSHOT_RETRY_LOOKBACK_DAYS=14`
  - `PLANNER_SHIPMENT_SNAPSHOT_RETRY_MAX_LINES_PER_PASS=200`
- **测试守门**：`backend/tests/planner/test_snapshot_retry_sweep.py` 7 个用例（empty / 跳过未绑定 / 创建快照 / 跳过 lookback 外的 / 幂等重跑 / 处理人工 cleared 的 / 尊重 limit）。Regression 89/89 全过。
- **生产首跑结果**（worker 重启后立刻触发）：scanned=92 created=38 failed=54 duration=3.7s。54 条 failed 主要是 SPEC_EMPTY 等业务数据问题（不是 worker bug，那些行本来 manual 触发也会失败）。原本卡在 PendingTab 的 3 条 OZU line **全部消失**（出了快照转 processed）。
- **前端配套**：`PendingTab.tsx` tooltip 由"5-10 分钟内自动出快照"改为更准确的"系统每 5 分钟扫一次, 自动补出快照, 一般 5-10 分钟内消失。不需要人工处理 — 急用可点右侧「重算」立刻触发。" tag 文案 `⏳ 等出快照 (5 分钟内自动)`。
- **位置**：service `shipment_import_service.sweep_bound_lines_missing_snapshot`；worker `shipment_import_worker._maybe_run_snapshot_sweep` + 在 `_loop` 内挂钩；config 4 个 `PLANNER_SHIPMENT_SNAPSHOT_RETRY_*` 字段；前端 `PendingTab.tsx` 改 tooltip。

### 33) Jackyun 同步定时调度上线（2026-05-07，auto-sync-backlog）
- **背景**：从 Jackyun 接入后，运营每天要手动到「外部数据同步」页点"立即同步" — 漏一天就漏一天的发货数据。原计划 backlog A 走 systemd timer，2026-05-07 上线。
- **CLI script**：`backend/scripts/cron_sync_jackyun.py` — 包装 `jackyun_sync_jobs.sync_shipments(use_watermark=True, triggered_by="cron-nightly")`，输出单行 `[cron-jackyun-sync] {status} run_id={...} total= inserted= updated= skipped= errors= cursor_end= elapsed=` 让 `journalctl -u` 可见。`status='partial'` 也算 exit 0（dead letter 在 UI 看），只有 hard failure 才 exit 1。
- **systemd user units**：`~/.config/systemd/user/jackyun-shipment-sync.{service,timer}` — `OnCalendar=*-*-* 02:30:00`（Asia/Shanghai），`Persistent=true`（关机重启后补跑），`RandomizedDelaySec=120`（避开多 timer 同时点火），`TimeoutStartSec=1800`（30 分钟硬上限）。`Type=oneshot`。
- **enable**：`systemctl --user daemon-reload && systemctl --user enable --now jackyun-shipment-sync.timer`。下次跑：明早 02:30 CST。
- **smoke test（立刻 start service）**：`run_id=226bdf05-…` `succeeded total=35 inserted=27 updated=8 skipped=0 errors=0 cursor_end=2026-05-07 11:18:56 elapsed=1s` — 增量同步抓了上次水位线之后的真实 35 条新数据。
- **运维 hint**：`journalctl --user -u jackyun-shipment-sync.service` 看历史；要立刻补一次跑用 UI 「立即同步」按钮，不要直接调脚本（避免抢占 watermark 锁）。
- **位置**：CLI `backend/scripts/cron_sync_jackyun.py`；systemd `~/.config/systemd/user/jackyun-shipment-sync.{service,timer}`。

---

    - **后续优化 ✅ 已完成（2026-05-07，p1-new-4）**：上文"前端 `Promise.all + 并发 8`"已替换为 `POST /api/planner/shipments/lines/bulk-resolve`。
      - **Endpoint**：body `{items: [{shipment_line_id, action, model_id?}], operator_id?, note?, stop_on_first_error?}`；response `{total, succeeded, failed, skipped_after_error, total_duration_ms, results: [{shipment_line_id, ok, action, snapshot_id?, snapshot_action?, error?, duration_ms}]}`。
      - **后端逻辑**（`shipment_import_service.bulk_resolve_shipment_lines`）：按 item 顺序循环调 `resolve_shipment_line`（每条**独立 commit/rollback**）。**故意不**用一个大事务包整批 — 否则 row 99 失败会回滚 row 1..98 的绑定/治理写入，业务上很 nasty。`stop_on_first_error=False`（默认）= best effort；`True` 时遇到第一个失败之后剩余 items 标 `error="skipped after earlier failure (stop_on_first_error=true)"`。
      - **健壮性**：非 dict items / unknown action（schema 层 422）/ 找不到 line / adopt 缺 model_id 全部转成单行失败，不会让整批 500。
      - **前端**：`bulkResolveShipmentLines(payload)` service + PendingTab `runBulk` 重写为单次 POST，删掉 `runWithConcurrency` helper。message 显示 `total_duration_ms` 让运营看见后端速度。
      - **测试守门**：`backend/tests/planner/test_shipment_line_bulk_resolve.py` 8 个用例（empty / 非 list 抛 / 全成功 / best-effort 失败一条剩余继续 / stop_on_first_error 跳余下 / garbage 元素转单行失败 / HTTP 汇总 / HTTP Literal 校验 422）；regression 78/78 全过。
      - **smoke 测试**（生产）：3 真实 + 1 fake uuid 的 4 行批量 = 后端 **16ms** 全完（3 succeeded, 1 failed 中文错误"发货行不存在或已归档"），best-effort 验证 ✅；`stop_on_first_error=true` 时 fake 在前 → 1 failed + 2 skipped ✅。烟测后用 `POST /sku-master/governance` 把 3 条回滚为 `unmanaged`（避免污染业务）。
      - **位置**：service `shipment_import_service.bulk_resolve_shipment_lines`；router `routers/shipments.py::bulk_resolve_shipment_lines`（路径 `/lines/bulk-resolve`）；schema `ShipmentLineBulkResolve{Item,Request,ResultItem,Response}`；前端 service `bulkResolveShipmentLines`；前端 UI `PendingTab.tsx::runBulk`。
- **位置**：
  - 后端：`backend/src/planner/services/shipment_import_service.py::auto_resolve_pending_shipment_lines_{preview,execute}` + `_list_pending_shipment_line_sku_codes`
  - 后端：`backend/src/planner/services/sku_master_service.py::auto_bind_preview`（新增 `restrict_to_sku_codes` 参数）
  - 后端路由：`backend/src/planner/routers/shipments.py::auto_resolve_pending_shipment_lines_{preview,execute}`
  - 前端：`frontend/src/pages/costing/biz/components/PendingTab.tsx`（顶部横幅 + 候选清单抽屉）
  - 前端 service：`frontend/src/services/planner.ts::autoResolvePendingShipmentLines{Preview,Execute}`
  - 测试：`backend/tests/planner/test_shipment_auto_resolve_pending.py`（7 个测试覆盖 preview / execute / 关键字匹配 / 已绑定跳过 / sku_codes 过滤 / 幂等）

- **2026-05-07 PendingTab v0.3 重构（必读：自动绑定的入口形态演变）**：v0.2 上线后业务反馈两点关键问题——
  1. **被动扫描**：进 Tab 自动跑 `auto-resolve preview`，10 个上架员 × 每天 50 次 = 500 次/天。当前 1.25s 还能忍，未来 SKU 涨到 10 万时会变 30s，全是浪费 CPU。
  2. **状态消失**：banner 处理完就隐藏 → 上架员**新建完模型**后回来想再点一次，按钮没了，必须刷新整个页面。这是把"主动操作"做成了"被动展示"，方向错了。
  
  **v0.3 改动**：
  - 自动识别 banner 撤掉，改成**筛选行右侧常驻按钮「⚡ 一键自动绑定」**
  - 用户主动点才触发 `preview` 扫描 → 弹出抽屉 → 用户选择性执行
  - 新增**顶部同步状态条**（`fetchShipmentLinesRecentStats`）：上次同步时间 + 24h 新进 N 条 + 跳 `/costing/integrations`，让上架员"跟着同步节奏走"而不是"看见 13k 积压懵掉"
  - 表格加 `rowSelection` + 浮出**批量工具栏**（批量待建模 / 批量标长尾），前端并发 8 调用 `resolveShipmentLine`
  - 操作列 `align: 'right' + fixed: 'right'`
  - **教训**：业务工具的"自动化能力" UI 应该是**永远在那的工具**（像"导入 Excel"），不是"出现一下又消失的横幅"。任何"处理完就隐藏"的入口必须警惕——它会让工作流不连贯。

- **后续优化（backlog）**：批量操作目前是前端 `Promise.all + 并发 8`，100 条 ≈ 12 秒，期间不能关页面，单条失败要逐个重试。下个 Sprint 改后端 `POST /shipments/lines/bulk-resolve` 一次调用搞定（跟 Issue 29 「合并 bind+spec+snapshot」一起做）。

- **2026-05-07 性能事故修复（必读）**：上线后业务侧反馈"banner 一直转圈"，curl 直测 preview 接口耗时 **90.45 秒**（不是前端 retry 问题，是真的慢）。
  - **根因**：`_list_pending_shipment_line_sku_codes` 末尾对每个未绑定 SKU 单独调用 `product_model_service.get_active_sku_binding(db, sku)`。生产数据 ≈ 5,779 个未绑定 SKU → **5,779 次串行 DB 往返**。
  - **修复**：改成一次 `IN (...)` 批量查询（chunk=1000，PG/MySQL 安全上限内），把 5,779 次查询压成 6 次。修复后冷起 **1.25s** / 热 **0.46s**（前端真实参数 `days=14, limit=1000`）。**提速 ~75 倍**。
  - **教训 / 防再犯**：
    - 任何返回"批量 SKU/订单"的预览接口在 service 层有循环时，必须先 grep 循环体内是否有 `db.query(...)` / `db.get(...)`。如果有，就是 N+1，必须批量化。
    - 不能信赖 SQLAlchemy identity map 顶住串行查询——`get_active_sku_binding` 每次都是 `.filter(...).first()`，identity map 不会缓存这种条件查询结果。
    - 前端给"非交互响应必需"的接口都应配 `retry: 0` + `staleTime: 60s` + 显式 error UI，避免后端慢退化成"无尽 loading"——但**前端兜底不能掩盖后端真慢**，发现 banner 长时间不出来必须立刻 curl 直测真实耗时。
  - **类似可疑位置（待巡检）**：`backend/src/planner/services/sku_master_service.py::auto_bind_preview` 内部 `for r in rows:` 循环里也有 `product_model_service.get_latest_published_standard_version_for_model_code(db, hint)` 和 `db.get(models.ProductModel, version.model_id)`，目前只对"有 hint"的 SKU 触发，量小没暴雷；如果未来 hint 命中率上升或 SkuMaster 全表扫描调用此函数，需要同样批量化。

### 31) `list_shipment_lines(status='processed')` 路径在 30 天窗口下慢 ~25 秒

- **现象（2026-05-07 测）**：
  - `GET /api/planner/shipments/lines?status=processed&start=<-30d>&end=<now>&page=1&page_size=20` 耗时 **25.3 秒**（生产真实数据，total=1916）
  - 同接口 `status=pending` 同窗口耗时 **1.0 秒**（total=13117）
  - 时间窗收到 7 天 → 1.86 秒（total=75），收到 3 天 → 0.12 秒（total=0）
  - **耗时与命中条数线性相关**，不是 count 慢
- **根因（待严格确认）**：
  - `backend/src/planner/services/shipment_import_service.py::list_shipment_lines` 主查询带 6 个 correlated `scalar_subquery`：`latest_snapshot_id_sq` / `latest_snapshot_model_version_id_sq` / `unresolved_reason_sq` / `unresolved_message_sq` / `cost_mode_sq` / `cost_total_sq`
  - status=pending 时 ORDER BY + LIMIT 20 让 PG 用索引前缀就能终止扫描；status=processed 时 `processed_pred = EXISTS(BomSnapshot or ShipmentCostingResult)` 命中条数多，每行都触发 6 个 scalar_subquery。
  - 老的 `/costing/shipments`（ShipmentLedgerPage）也慢，但财务派习惯了"等出报表"的节奏所以从未抱怨；新「发货管理 → ✅ 已完成」给上架员日常用，必须解决。
- **当前缓解（已上线）**：
  - `frontend/src/pages/costing/biz/components/DoneTab.tsx` 默认时间窗 30 天 → **7 天**
  - 用户主动扩大到 >14 天时显示黄色 banner，告知"加载较慢，建议去发货台账"
- **彻底修复（backlog，下次后端性能 Sprint）**：
  1. 把 6 个 `scalar_subquery` 重写成 LEFT JOIN + `ROW_NUMBER() OVER (PARTITION BY shipment_line_id ORDER BY created_at DESC) = 1`（已经在同函数里给 binding_sq 这么做过，参考第 2147-2175 行）
  2. 验证 `bom_snapshots(shipment_line_id, created_at DESC)` / `shipment_exception_queue(shipment_line_id, resolved_at, created_at DESC)` 索引存在；如缺则补
  3. 跑 EXPLAIN ANALYZE 确认 worst-row latency < 5ms
- **位置**：
  - 后端：`backend/src/planner/services/shipment_import_service.py::list_shipment_lines`（行 2017+）
  - 前端缓解：`frontend/src/pages/costing/biz/components/DoneTab.tsx`（默认 7 天 + 黄色 banner）

### 30) 4 个"发货相关页面"的角色矩阵（防混淆 / 防误删 / 防误改）

- **背景**：2026-05-07 上架员视角的「📦 业务管理 → 🚚 发货管理」(`/costing/biz/shipments`) 上线后，与已有的几个发货相关页面**容易被误认为是替代关系**。实际是**5 个页面 = 5 个角色**，并存而非互斥。任何后续 Agent 在动这些页面之前必须先读懂矩阵，避免把"运营查账页"当成"上架员处理页"删掉。

- **5 个页面的真实角色**：

  | URL | 中文名 | 角色 | 主要功能 | 写操作 | 不能删/不能合并的理由 |
  |---|---|---|---|---|---|
  | `/costing/sku-master` | SKU 主档 | 商品维护员 | 100w SKU 全量预绑定、自动识别（候选预览/执行/一键跑完三按钮） | ✅ 写 | 历史治理场景：管理员一次绑几万 SKU，新页面"跟着发货走"模式覆盖不到 |
  | `/costing/spec-matching` | 规格匹配 | 规格员 | 单独跑规格解析、调试模型识别规则 | ✅ 写 | 调试 / 规则编辑视角，发货页都是"运行时" |
  | `/costing/shipments/ops` | 发货作业中心 | 上架员（**技术派**） | 模型解析 + 规格解析 + 快照生成 + 批量重算 + 异常队列处理（写操作核心，所有发货行的最终落库都在这里） | ✅✅ 写 | **真正的写操作总入口**——`/costing/shipments` 的"批量计价快照"和 `/costing/biz/shipments` 的"出快照"底层都依赖这里的 service |
  | `/costing/shipments` | **发货台账** | **运营 / 财务查账** | 看每行的：发货金额、成本、利润、毛利率、BOM 物料、成本拆分、毛利为负 / 疑似绑错 / 尺寸异常软提示 | ❌ **只读为主**（"批量计价快照"按钮也是组装参数 → 跳 `/costing/shipments/ops?tab=bulk`，**写操作物理上不在台账页**） | 服务的是"事后查账"角色（按月/周拉数据看利润分布），跟"事中处理"完全不同 |
  | `/costing/biz/shipments`（**新**，2026-05-07 上线） | 发货管理 | 上架员（**业务派**） | 一站式视图：⚡ 一键自动绑定 + 4 阶段生命周期 Tab（待处理/处理中/已完成/长尾池）+ 业务友好提示 | ✅ 写 | 上架员日常视角："今天有多少行没绑定/卡在哪/要不要一键消化掉"，需要简化到一句话 + 一个按钮 |

- **物理位置 = 路径前缀**：
  - `/costing/shipments` 系列（无 `/biz/` 前缀） = **老系统**
  - `/costing/biz/` 系列 = **新业务管理一级菜单**（包含发货/售后/POD 三子页面）
  - 任何后续 Agent 在改"发货页"之前必须先 `grep` 路径，确认改的是哪个角色的页面。

- **为什么不能强行合并 `/costing/shipments`（台账）和 `/costing/biz/shipments`（发货管理）**：
  - 角色不同：财务/运营 vs 上架员
  - 时间维度不同：事后（按月按周拉历史） vs 事中（今天卡住了什么）
  - UI 密度不同：台账要 20+ 列利润/成本/异常软提示；发货管理只展示推进生命周期所必需的几列
  - 软提示不同：台账要"毛利为负 / 尺寸疑似异常"等核算视角的标签；发货管理要"系统建议: 画框-024（置信度 0.78）"等业务推荐
  - 强行合并 = 给业务派塞工程师视角的 30 列表格，给财务派塞业务的"自动绑定"按钮 → 双方都用不爽

- **共享后端 service**：虽然 5 个页面 UI 不同，但底层 service 高度复用：
  - 自动绑定算法 `sku_master_service.auto_bind_preview` —— 老 SKU 主档 + 新发货管理 共用（详见 Issue 26）
  - 快照生成 `_generate_bom_snapshot` —— 老作业中心 + 新发货管理执行按钮 共用
  - 异常队列 `ShipmentExceptionQueue` —— 所有页面读同一份数据
  - **改 service 时同时影响多个页面，改前必须 grep 所有调用方**

- **修订历史**：
  - 2026-05-07：补充本矩阵，触发原因——新发货管理上线后，user 明确指出"`/costing/shipments` 是计价格及落库的页面，跟新建的是两个完全不同的功能"。

### 21) BOM 系统优化方案被误认为“已经上线自动编码/子模型等能力”

- **现象**：一线或新同事看到《DOC/基础表单/BOM系统优化完整方案_最终版.md》后，以为其中提到的“子模型表/组合型产品模型表/编码提取日志表/产品模型编码 \`#S3V1F1\` 嵌入电商字段”等已经在系统中落地，并据此向业务承诺能力或设计下游流程。
- **口径**：
  - 截止 2026-02-10，仓库中只落地了“发货时再解析 + SKU→已发布标准版本绑定 + spec_hash 缓存解析 + BOM 快照 + 发货异常队列”等主线能力；自动编码/子模型/组合型产品模型/编码提取日志目前均处于**方案设计阶段**，尚未有任何 Alembic 迁移或 API/前端实现。
  - 复杂产品（30% 多幅套装/非规则型）的落地路线以《BOM系统优化完整方案》为蓝图，但必须在 Hub/Planner 拆分出 Backend/Frontend/Docs 闭环任务单、完成实现与验收后，才允许对外宣传“已支持自动编码/组合型产品模型”。
  - 对外沟通与培训时，应明确区分：**当前已上线的是什么（主线）**、**设计中/规划中的是什么（扩展方案）**，避免因误读方案文档导致超卖能力或错误依赖。

