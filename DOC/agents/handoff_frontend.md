## 接力包：新 Frontend（成本系统 / ai-costing-system）

> **禁止靠聊天上下文推进**。新 Agent 建议阅读顺序：`DOC/agents/workset.md` → 本文件 → `DOC/agents/state.md` → `DOC/agents/commands.md` → `DOC/agents/known_issues.md`。

### 当前关键结论（先读这一段）

- **编辑器共用 + 语境隔离**：打样/标准两入口复用同一编辑器 `ProductModelEditorDrawer`，但必须严格用 `entryContext="sample" | "standard"` 隔离（standard 只操作 standard 版本）。
- **行级变体是 Overlay，不改基准清单**：变体在独立 Drawer 中维护，动态生成最终 BOM；基准清单（version lines）是兜底。
- **运营/实施口径以规范文档为准**：token 字典化、尺寸边界离散化、上线前预演留痕、扣库以最终 BOM 快照为准（见 `DOC/costing/manuals/standard_model_variants_ops_rules.md`）。

- 最近校对（北京时间 GMT+8）：2025-12-30（本轮 Frontend Agent 接力：已按恢复包规范做验收与落地）
- 分支：`backup/20251214-1535`

### 1) P0 目标（产品模型编辑器 + 两入口）

**目标一句话**：把“产品模型编辑器”迁移/固化到 `frontend/src/components/costing/ProductModelEditorDrawer.tsx`，并由两个入口页驱动（打样入口 / 标准入口），严格按语境隔离 sample vs standard。

- **编辑器唯一承载组件**
  - `frontend/src/components/costing/ProductModelEditorDrawer.tsx`
  - 入口参数：
    - `entryContext="sample" | "standard"`：决定 UI 文案、可用动作、校验口径（强约束）
    - `initialVersionId?: string`：标准入口用于定位到指定 standard 版本

- **两入口（必须同时可用）**
  - **打样入口**：`/costing/sample-models` → `frontend/src/pages/costing/SampleModelsPage.tsx`
    - 列表基于模型：`fetchProductModels(...)`
    - 打开抽屉：`<ProductModelEditorDrawer entryContext="sample" modelId=... />`
  - **标准入口**：`/costing/standard-models` → `frontend/src/pages/costing/StandardModelsPage.tsx`
    - 列表基于版本分页：`fetchProductModelVersionsPaged({ version_kind: 'standard', ... })`
    - 打开抽屉：`<ProductModelEditorDrawer entryContext="standard" modelId=... initialVersionId=... />`

### 2) 接口索引（前端/后端契约的单一真相）

> **前端请求封装单一真相**：`frontend/src/services/planner.ts`（不要在页面里散落 axios/fetch）。
>
> **后端路由校对（只读）**：`backend/src/planner/routers/product_models.py`、`backend/src/planner/routers/product_model_versions.py`。

#### 2.1 两入口页直接使用的接口

- **打样入口（模型列表/新建/删除）**
  - `GET /api/planner/product-models` → `fetchProductModels(params)`
  - `POST /api/planner/product-models` → `createProductModel(payload)`
  - `DELETE /api/planner/product-models/{model_id}` → `deleteProductModel(modelId)`

- **标准入口（标准版本分页）**
  - `GET /api/planner/product-model-versions?version_kind=standard&search=&page=&page_size=` → `fetchProductModelVersionsPaged(params)`

#### 2.2 编辑器（抽屉）核心接口（版本化/清单/推导/发布/SKU）

- **版本**
  - `GET /api/planner/product-models/{model_id}/versions` → `fetchProductModelVersions(modelId)`
  - `POST /api/planner/product-models/{model_id}/versions` → `createProductModelVersion(modelId, payload)`
  - `DELETE /api/planner/product-model-versions/{version_id}` → `deleteProductModelVersion(versionId)`（后端限制：仅 sample 可删，且不能已生成 standard）

- **版本清单（本轮闭环必用：GET + PUT）**
  - `GET /api/planner/product-model-versions/{version_id}/lines` → `fetchProductModelVersionLines(versionId)`
  - `PUT /api/planner/product-model-versions/{version_id}/lines` → `updateProductModelVersionLines(versionId, payload)`
  - `POST /api/planner/product-model-versions/{version_id}/sync-from-modules` → `syncProductModelVersionFromModules(versionId, payload)`

- **预览与推导**
  - `POST /api/planner/product-model-versions/{version_id}/preview` → `previewProductModelVersion(versionId, payload)`
  - `POST /api/planner/product-model-versions/{source_version_id}/derive-standard` → `deriveStandardFromSampleVersion(sourceVersionId, payload)`

- **发布与 SKU 绑定**
  - `POST /api/planner/product-model-versions/{version_id}/publish` → `publishProductModelVersion(versionId, payload)`
  - `POST /api/planner/sku-model-version-mapping` → `bindSkuModelVersion(payload)`
  - `GET /api/planner/sku-model-version-mapping?sku_code=...` → `fetchSkuModelVersionMappings(params)`
  - `POST /api/planner/sku-preview` → `previewBySku(payload)`

#### 2.3 “API_BASE / 跨域”关键约定（避免浏览器 CORS 坑）

- 前端在 `frontend/src/services/planner.ts` 内做了保护：若你把 `VITE_PLANNER_API_BASE` 配成 `http(s)://同域:8800/...`（仅端口不同），浏览器会视为跨域，前端会**回退到**同源的 `/api/planner`。
- 结论：**生产/联调尽量走 nginx 同源 `/api/planner`**，不要强行把浏览器 API_BASE 指到 `:8800`。

### 3) 统一 Markdown 指南接入规范（编辑器内嵌）

> 目的：把培训/口径说明沉淀在代码里，避免靠口口相传；同时保证“可复制、可恢复、可更新”。

- **指南文件放置**
  - 目录：`frontend/src/guides/`
  - 命名建议：`snake_case` + 业务主题（例如：`derive_standard_per_sqm_tablecloth_example.md`）

- **导入方式（统一用 raw 字符串）**
  - 在需要展示的组件内使用 Vite raw 导入：
    - `import xxxGuide from '@/guides/xxx.md?raw'`
  - 约束：指南内容以纯文本展示（不依赖 markdown 渲染），避免引入额外依赖。

- **展示组件（统一入口）**
  - 组件：`frontend/src/components/common/GuideDrawer.tsx`
  - 使用方式：传入 `title/content/tip/open/onClose`；`content` 直接传 raw 字符串。

- **示例（已落地）**
  - `ProductModelEditorDrawer.tsx` 内已内嵌“推导标准每平米（桌布示例）”指南，通过 `GuideDrawer` 展示与一键复制。

### 4) 已确认正确的快照位置（恢复用，禁止覆盖）

- `DOC/index/extracted/ProductModelEditorDrawer_confirmed_20251221T042643Z.tsx`
- `DOC/index/extracted/ProductModelEditorDrawer_confirmed_20251221T042643Z.sha256`

> 说明：当编辑器发生“难以回滚/难以解释”的异常时，优先用上述快照对照恢复；不要从大导出/聊天记录回退。

### 5) 验收命令（本轮门槛）

- 安装依赖（首次/环境变更后）：`cd frontend && npm ci`
- **验收门槛（必须通过）**：`npm -C frontend run build`

### 6) 行级变体（Overlay）——新 Agent 必须掌握

#### 6.1 关键文件（前端）

- `frontend/src/components/costing/LineVariantDrawer.tsx`：变体 Drawer（创建/启用/删除规则；保存 items；spec_text 预演 tokens + 最终 BOM + trace）
- `frontend/src/components/costing/ProductModelEditorDrawer.tsx`：在标准入口“清单编辑”Tab 的物料行接入“变体（Overlay）”按钮入口
- `frontend/src/services/planner.ts`：补齐 `spec/parse`、`bom/generate`、`line-variants` 请求封装
- `frontend/src/types/planner.ts`：行级变体相关类型

#### 6.2 关键接口（后端）

- `POST /api/planner/spec/parse`
- `POST /api/planner/bom/generate`
- line-variants：
  - `GET /api/planner/product-model-versions/{version_id}/line-variants?base_line_id=...`
  - `POST /api/planner/product-model-versions/{version_id}/line-variants`
  - `PATCH/DELETE /api/planner/line-variants/{variant_id}`
  - `PUT /api/planner/line-variants/{variant_id}/items`（整单替换）

#### 6.3 常见坑（会导致“又崩/又走不通”）

- **base_line_id 必须存在**：只有当版本清单行已落库（先点过“保存清单”）才有 `base_line_id`；否则变体无法创建（详见 `DOC/agents/known_issues.md`）。
- **先按“最小可控形态”跑通**：推荐运营先只用 `replace_self`（同计量单位平替），避免 1→N items 维护爆炸；进阶的 bundle/add 后续另开迭代（口径见运营规范文档）。

#### 6.4 运营/实施规范（口径唯一真相）

- `DOC/costing/manuals/standard_model_variants_ops_rules.md`（**必须以此为准**）


