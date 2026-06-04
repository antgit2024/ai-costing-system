# Frontend 闭环任务单：行级变体“替换物料”不再手输ID（选择器 + 自动回填 + 同单位校验）

> 角色：@Frontend Agent  
> 背景：行级变体已收口为 `replace_self + 同单位 1→1` 且可用，但“替换物料”目前需要手输 `material_ref_id`，易错、难用。  
> 目标：把“手输ID”升级为“可搜索选择 + 自动回填显示”，并补齐关键 UX 校验。

## 1) 本轮范围（必须很小）

仅做以下 UI 细化（不改后端，不扩展到 1→N / bundle）：

1. `LineVariantDrawer` 中“替换物料”字段改为：
   - 支持打开选择器（Modal/Drawer 任一，建议 Modal）
   - 列表可搜索（关键词：物料编码/名称）
   - 选择后回填 `material_ref_id`（作为提交值）
2. 在规则表格/详情处显示：
   - 目标物料的 `material_code/material_name/unit_of_measure`（若已知）
3. 同单位校验 UX：
   - 若基准行单位与目标单位不一致：明确红色提示，且禁止启用
   - 若基准行单位缺失：提示“先保存清单/补齐主数据”
4. 预演与启用门槛逻辑保持不变（仍需预演成功）

## 2) 完成标准

- 不再出现“要求用户手输 material_ref_id”的主路径
- 选择器能在 3 步内完成替换物料选择：打开 → 搜索 → 选择
- 选择后页面可读：能看到目标物料编码/名称/单位
- `npm -C frontend run build` 通过

## 3) 依赖契约（只用现有接口）

- 物料候选：
  - `GET /api/planner/base-config/materials?search=&page=&page_size=`（前端已有封装则复用）
- 行级变体保存：
  - `PUT /api/planner/line-variants/{variant_id}/items`（仍按 1→1 写入）

> 注意：后端会在保存 items 时自动回填 `material_code/material_name/unit_of_measure/calculation_method`（如果你们当前返回体已包含，可直接展示；否则可在选择器侧展示）。

## 4) 文件范围（尽量只改这几个）

- `frontend/src/components/costing/LineVariantDrawer.tsx`
- （可选）新增：`frontend/src/components/costing/MaterialSelectModal.tsx`（仅本功能复用）
- `frontend/src/services/planner.ts`（若缺少 materials 搜索封装则补齐）
- `frontend/src/types/planner.ts`（若缺少 Material 列表类型则补齐）

## 5) 验收命令（只给 1 条）

`npm -C frontend run build`


