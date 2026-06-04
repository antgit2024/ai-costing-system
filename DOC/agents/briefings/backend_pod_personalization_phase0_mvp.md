# Backend 闭环任务单：POD 个性化定制 Phase0（先印布）— POD 领域最小对象 + Job + 生产包下载（MVP）

> 备注（重要）：该任务单当前为**备用草案**（用于避免文档验收 grep 断链），不代表已进入实施主线。  
> 启动前置：按 `DOC/agents/handoff_pod.md` 补齐工厂参数（RIP 接入方式/裁切线格式/定位标规范/分组规则）。

---

## 目标（Phase0 最小闭环）

用户/运营完成确稿后，后端能够：
- 记录素材（hash/元数据/存储 key）
- 生成“效果图/印刷稿”异步 job（至少印刷稿）
- 生成并快照化 ProductionPack（含印刷稿文件列表 + 追溯字段）
- 提供受控下载（工厂下载生产包）
- 预留 ERP 回传接口（或先写回调表，后续接真实ERP）

---

## 建议数据落点（可先用新表，也可先用 metadata_json）

- `artwork_assets`
- `print_templates`（按 `product_model_version_id + structure_slot`）
- `artwork_jobs`（mockup_render/print_export）
- `production_packs`

---

## 建议接口（最小）

- `POST /api/planner/pod/assets`：注册素材（或上传回传 storage_key）
- `POST /api/planner/pod/jobs/print-export`：创建印刷稿 job
- `GET /api/planner/pod/jobs/{job_id}`：查询 job 状态
- `POST /api/planner/pod/production-packs`：确稿创建生产包（触发 print job）
- `GET /api/planner/pod/production-packs/{id}`：生产包详情
- `GET /api/planner/pod/production-packs/{id}/download`：受控下载（签名URL或鉴权流式）
- `POST /api/planner/pod/erp/writeback`：回传ERP（占位，后续对齐字段）

---

## 验收口径（建议）

给定 1 个模型版本 + 1 张图片 + 1 个确稿请求：
- 能生成一个 production_pack（ready）
- 能生成一个 print_export job（completed）
- 工厂下载接口可用（返回签名链接或文件流）

# Backend 闭环任务单：POD 个性化定制 Phase0（先印布）— POD 领域最小对象 + Job + 生产包下载（MVP）

> 范围：仅后端 POD 领域的最小可跑通闭环；**不做 AI**、不做工厂 RIP 深对接。  
> 背景与口径：见 `DOC/costing/blueprints/pod_personalization_print_pipeline_phase0.md` 与 `DOC/agents/handoff_pod.md`。

---

## 任务名

Backend-POD-Phase0-MVP：确稿→生成印刷稿（mock）→生产包可下载→回传 ERP（mock）

---

## 范围（必须很小）

- 仅新增/修改：
  - `backend/src/planner/routers/`（新增 pod 路由文件并在 router 聚合）
  - `backend/src/planner/schemas.py`（补 POD DTO）
  - `backend/src/planner/models.py`（补 POD ORM）
  - `backend/src/planner/services/`（新增 pod_service / pod_storage）
  - `backend/tests/planner/`（新增 1 个最小 pytest）
- **不做**：
  - 不接入真实 RIP/切割机；不做热文件夹下发
  - 不接入真实 AI；mockup/print 文件可以先用“复制输入图 + 叠加简单水印/裁切线占位”的方式生成
  - 不扩展前端页面（本任务只做后端契约与最小可跑通链路）

---

## 完成标准（可验收）

- 能创建 1 个 POD 素材（ArtworkAsset），并以 `sha256` 去重（同 hash 重复注册不产生新记录，返回既有 id）。
- 能创建 1 个 POD 生产包（ProductionPack）：
  - 绑定 **published standard** 的 `product_model_version_id`
  - 绑定 `print_template_id`
  - 记录“确稿参数快照”（transform/crop/rotation/placement 等）与 input_hash
- 能触发并查询 2 类 job（mock）：
  - mockup_render（效果图）
  - print_export（印刷稿）
- 能下载生产包文件（受控下载）：
  - 下载 URL 需带一次性或短期 token（最小可用：HMAC 签名 query + 过期时间）
  - 下载行为写审计（至少记录 pack_id、文件名、下载时间、ip/actor）
- 能模拟“ERP 回传”（mock）：
  - `POST /api/planner/erp/writeback/production-pack` 接收 pack_id + url + trace_id 并落库到 `production_packs.erp_writeback_status`

---

## API 契约（建议最小）

> 统一前缀：`/api/planner/pod`

### 1) 注册素材（推荐：先走对象存储，再登记）

`POST /api/planner/pod/artwork-assets`

Request（JSON）：
- `storage_key: string`（对象存储 key；Phase0 可先用本地文件路径模拟）
- `filename: string`
- `content_type: string`
- `bytes: int`
- `sha256: string`
- `width_px?: int`
- `height_px?: int`
- `uploaded_by: string`

Response：
- `id: string`
- `sha256: string`
- `status: "active"`

幂等：
- 以 `sha256` 作为唯一键（同 hash 返回已有记录）

### 2) 创建/更新印刷模板（最小：可写死一个默认模板，也要可落库）

`POST /api/planner/pod/print-templates`

Request（JSON）：
- `name: string`
- `product_model_version_id: string`（published standard）
- `structure_slot: string`（如 `body_front`；Phase0 可先用字符串）
- `dpi: int`（默认 150）
- `bleed_mm: number`
- `safe_margin_mm: number`
- `cut_line: { enabled: boolean }`
- `registration_marks: { enabled: boolean }`
- `mirror_mode: "none" | "horizontal" | "vertical"`
- `icc_profile?: string`（Phase0 可选）
- `metadata_json?: object`

Response：
- `id: string`
- `version: int`

### 3) 确稿：创建生产包 + 触发印刷稿 job

`POST /api/planner/pod/production-packs`

Request（JSON）：
- `order_ref?: { channel?: string, order_no?: string, order_line_no?: string }`（Phase0 可空）
- `product_model_version_id: string`（published standard）
- `print_template_id: string`
- `artwork_asset_id: string`
- `artwork_transform: object`（裁剪框/缩放/旋转/对齐；直接原样快照）
- `requested_by: string`

Response：
- `production_pack_id: string`
- `print_export_job_id: string`
- `status: "created"`

规则：
- 创建 pack 后立即 enqueue `print_export` job（Phase0 可直接同步生成并标记 completed，但仍保留 job 记录）

### 4) 查询生产包

`GET /api/planner/pod/production-packs/{production_pack_id}`

Response（JSON）：
- `id`
- `status: "created" | "ready" | "failed"`
- `product_model_version_id`
- `print_template_id`
- `artwork_asset_id`
- `files: Array<{ kind: "mockup"|"print_pdf", filename: string, bytes?: int, sha256?: string }>`
- `download: { url: string, expires_at: string }`（ready 时给）
- `trace_id?: string`
- `created_at`

### 5) 触发/查询 Job

`POST /api/planner/pod/jobs`

Request：
- `job_type: "mockup_render" | "print_export"`
- `production_pack_id: string`
- `requested_by: string`

`GET /api/planner/pod/jobs/{job_id}`

Response：
- `id`
- `job_type`
- `status: "queued"|"running"|"completed"|"failed"`
- `progress?: number`
- `error?: string`
- `result_files?: [...]`

### 6) ERP 回传（mock）

`POST /api/planner/erp/writeback/production-pack`

Request：
- `production_pack_id: string`
- `download_url: string`
- `trace_id?: string`
- `operator_id: string`

Response：
- `{ "status": "ok" }`

---

## 数据模型（最小建议，字段可先全放 metadata_json，但必须快照化）

- `pod_artwork_assets`
  - `id, sha256(unique), storage_key, filename, content_type, bytes, width_px, height_px, status, created_at`
- `pod_print_templates`
  - `id, product_model_version_id, structure_slot, dpi, bleed_mm, safe_margin_mm, mirror_mode, icc_profile, version(int), metadata_json, created_at`
- `pod_jobs`
  - `id, job_type, status, production_pack_id, payload_json, result_json, error, created_at, updated_at`
- `pod_production_packs`
  - `id, product_model_version_id, print_template_id, artwork_asset_id`
  - `input_hash`（由 `template + asset.sha256 + transform_json + version_id` 组合 sha256）
  - `files_json`（mockup/print_pdf 的存储 key/filename/sha256/bytes）
  - `download_token_hash/expire_at`（或签名策略所需字段）
  - `erp_writeback_status`（pending/sent/failed）
  - `trace_id`
  - `created_at, updated_at`

---

## 验收命令（只给 1 条）

```bash
./backend/venv/bin/python -m pytest backend/tests/planner/test_pod_phase0_mvp.py -q
```

---

## 回填要求（执行者必须做）

- `DOC/agents/state.md`：更新“本轮产物/下一步/验收命令/北京时间日期”
- `DOC/agents/task_log.md`：追加一行记录

