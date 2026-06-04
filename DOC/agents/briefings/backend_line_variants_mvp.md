# Backend 闭环任务单：行级变体（overlay）+ 规格解析（tokens）MVP

> 角色：@Backend Agent  
> 目标：让前端“物料行变体面板（overlay）”有真实数据可接，并能用 `spec_text` 预演出“最终BOM（含 trace）”。  
> 关键口径：**基准标准清单不被直接修改**；变体是 version-scoped overlay；ADD 类变体建议挂在**锚点行**，插入位置固定为“锚点行之后”。

## 1) 本轮范围（必须很小）

仅实现以下能力（不做 UI，不做智能推荐，不做对外系统对接）：

1. `spec/parse`：把非结构化 `spec_text` 解析为 tokens + 尺寸派生量（面积/周长）
2. 行级变体 CRUD（version-scoped）：
   - 规则表：`product_model_line_variants`
   - 变体物料清单：`product_model_line_variant_items`
3. `bom/generate`（MVP）：加载 standard 版本基准清单 → 应用行级变体 overlay → 输出最终物料行 + trace（命中回放）

## 2) 完成标准

- 能创建/查询/更新/删除某个 `version_id` 下、某个 `base_line_id` 的变体规则
- 能为某条变体规则维护多行 `variant_items`（新增/删除/排序/替换物料）
- `POST /api/planner/spec/parse` 返回：
  - `tokens[]`
  - `width_cm/height_cm/diameter_cm`（能解析则给）
  - `area_m2/perimeter_m`
  - `explanations[]`（可选但推荐：每个 token 的来源片段）
- `POST /api/planner/bom/generate`：
  - 对命中规则的 base_line 做 `replace_bundle/remove_self/add_siblings`
  - **ADD 插入位置**：默认插在锚点行之后（锚点行由前端/模型配置预置，MVP 仅按 line_id 插入即可）
  - 返回 `trace`：命中哪些规则、应用顺序、最终插入/替换的行

## 3) 依赖契约（API 草案）

### 3.1 spec/parse

- `POST /api/planner/spec/parse`
- Request：
  - `{ "spec_text": string, "sku_code"?: string }`
- Response（示例字段）：
  - `tokens: string[]`
  - `width_cm?: number, height_cm?: number, diameter_cm?: number`
  - `area_m2?: number, perimeter_m?: number`
  - `explanations?: Array<{ token: string; source: string; rule: string }>`

### 3.2 line variants CRUD

- `GET /api/planner/product-model-versions/{version_id}/line-variants?base_line_id=...`
- `POST /api/planner/product-model-versions/{version_id}/line-variants`
- `PATCH /api/planner/line-variants/{variant_id}`
- `DELETE /api/planner/line-variants/{variant_id}`

### 3.3 variant items CRUD（可合并进变体 PATCH）

- `GET /api/planner/line-variants/{variant_id}/items`
- `PUT /api/planner/line-variants/{variant_id}/items`（整单替换：最省事）

### 3.4 bom/generate（MVP）

- `POST /api/planner/bom/generate`
- Request：
  - `{ "sku_code"?: string, "spec_text": string, "model_version_id": string, "quantity"?: number }`
- Response：
  - `final_material_lines: [...]`
  - `trace: { parsed: ..., matched_variants: ..., applied_actions: ... }`

## 4) 数据结构（建议）

### 4.1 product_model_line_variants

- `id`
- `version_id`（FK → product_model_versions）
- `base_line_id`（FK → product_model_version_lines）
- `priority`（int, default 100）
- `enabled`（bool）
- `conditions_json`（JSON：MVP 先支持 `spec_contains_any` / `spec_contains_all`）
- `action`（enum：`replace_bundle` / `remove_self` / `add_siblings`）
- `stop_on_hit`（bool, default true）
- `created_at/updated_at`

### 4.2 product_model_line_variant_items

- `id`
- `variant_id`（FK）
- `sequence_order`
- `material_ref_id`
- `material_kind`（real/virtual_non_placeholder，MVP 可先用 string）
- `calculation_method`（area/perimeter/count/width/height）
- `base_quantity/fixed_quantity/coverage_ratio`
- `metadata_json`
- `created_at/updated_at`

## 5) 验收命令（只给 1 条）

按现有惯例先用 pytest 验证（新增一个最小测试即可）：

`pytest backend/tests/planner/test_line_variants_mvp.py -q`

（测试建议：构造一个 standard version + 画框基准行 + 锚点行 + 两条变体规则；spec_text 命中后，断言最终行序与 trace）


