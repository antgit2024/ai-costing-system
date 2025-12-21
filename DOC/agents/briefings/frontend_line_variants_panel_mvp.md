# Frontend 闭环任务单：物料行“变体”按钮 + Overlay Drawer（接后端 line-variants/spec/parse/bom）

> 角色：@Frontend Agent  
> 目标：在标准模型“清单编辑”里实现物料行级变体管理 UI：点“变体”图标弹出独立 Drawer 管理变体清单（overlay，不改基准清单），并能用 spec_text 预演生成最终 BOM。  
> 后端已就绪：line-variants/spec/parse/bom MVP（由 @Backend Agent 提交 `a7ee7ac`）。

## 1) 本轮范围（必须很小）

仅做以下 UI/交互（不重构现有编辑器，不做全局搜索/推荐，不做复杂权限）：

1. 在 **标准入口**（`entryContext="standard"`）的“清单编辑”Tab：每条**物料行**增加一个“变体”按钮/图标
2. 点击后打开 **独立 Drawer**（Overlay 面板）：
   - 管理该 `base_line_id` 的变体规则列表（创建/启用/禁用/删除/排序（可选））
   - 编辑某条规则的“变体物料清单 items”（整单替换：最省事）
   - 提供一个 `spec_text` 输入框，点击“预演”：
     - 调用 `POST /spec/parse`（展示 tokens）
     - 调用 `POST /bom/generate`（展示最终出料物料列表 + trace 摘要）
3. **锚点行约定**（只需 UI 约束，不必自动创建）：
   - ADD 类变体建议挂在“锚点行”（产品经理/实施在基准清单里预置）
   - 本轮 UI 只提示/标记锚点行（例如 tag：锚点），不强制实现自动插入

## 2) 完成标准

- 标准模型抽屉打开任意 standard 版本后：
  - 物料行右侧出现“变体”图标
  - 点击能打开 Drawer
- Drawer 内：
  - 能创建 1 条变体规则（最小字段：enabled/priority/action/conditions）
  - 能编辑并保存该规则的 items（多行）
  - 输入 `spec_text` 后能预演：展示解析 tokens + 最终 BOM 行（至少 material_code/material_name/qty）
- 不修改基准清单（保存变体只写到 line-variants 相关 API）
- `npm -C frontend run build` 通过

## 3) 依赖契约（API 约定，按后端实现对接）

> 注意：生产环境走同源 `/api/planner`；不要在浏览器里直连 `:8800`（避免 CORS），见 `DOC/agents/known_issues.md`。

- `POST /api/planner/spec/parse`
  - `{ spec_text, sku_code? }` → `{ tokens, width_cm?, height_cm?, area_m2?, ... }`

- line variants（version-scoped）
  - `GET /api/planner/product-model-versions/{version_id}/line-variants?base_line_id=...`
  - `POST /api/planner/product-model-versions/{version_id}/line-variants`
  - `PATCH /api/planner/line-variants/{variant_id}`
  - `DELETE /api/planner/line-variants/{variant_id}`
  - items（整单替换）：
    - `PUT /api/planner/line-variants/{variant_id}/items`

- `POST /api/planner/bom/generate`
  - `{ model_version_id, spec_text, sku_code?, quantity? }`
  - 返回：`final_material_lines` + `trace`

## 4) 文件范围（尽量只改这几个）

- `frontend/src/components/costing/ProductModelEditorDrawer.tsx`（加“变体”按钮入口、传参 base_line_id/version_id）
- **新增**：`frontend/src/components/costing/LineVariantDrawer.tsx`（Overlay Drawer 主体）
- `frontend/src/services/planner.ts`（补齐 line-variants/spec/bom 的请求封装；如已存在就复用）
- `frontend/src/types/planner.ts`（补齐必要类型）

## 5) 验收命令（只给 1 条）

`npm -C frontend run build`


