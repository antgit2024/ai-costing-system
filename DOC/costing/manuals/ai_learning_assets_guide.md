## AI 数据资产：工序/工艺模板接入说明（基础版）

### 目标
- 把“工序/工艺模板”沉淀为可检索、可复用、可反馈迭代的数据资产
- 后续任意 AI 能直接通过 API 拉取语料并生成建议/模板

---

## 1. 工序（Process）作为 AI 语料

### 1.1 存储位置（不改表结构）
工序的 AI 字段统一写入：`process.metadata_json.ai_spec`

推荐字段（可逐步完善）：
- **intent**：工序意图/目的（可直接写业务口径/规则说明）
- **inputs**：输入/前置条件
- **outputs**：输出/交付物
- **quality_points**：质量要点/QC
- **constraints**：禁忌/边界条件
- **tools**：设备/工具/工装
- **parameter_schema**：参数模板（JSON，用于后续自动生成步骤参数）

另外，工序的“适用标签”写入：`process.metadata_json.process_tags`（数组，如 `["画艺","布艺"]`）。

### 1.2 前端入口
- 工序管理列表“操作”列有 **AI 图标按钮**：点击会打开编辑并自动展开 AI 面板。
- 规则：若 `ai_spec.intent` 为空，会自动用“描述(description)”回填到“工序意图/目的”（保存时固化）。

---

## 2. AI 语料导出接口（给 AI 使用）

### 2.1 工序语料导出
`GET /api/planner/ai/processes/corpus`

参数（可选）：
- `search`：编码/名称模糊检索
- `tag`：按 `process_tags` 过滤（如 画艺/布艺）
- `category`：功能分类过滤
- `status`：draft/active/inactive
- `page` / `page_size`

返回：
- 基础字段 + `tags`（即 process_tags）+ `ai_spec`

---

## 3. 反馈/执行记录（训练闭环）

### 3.1 表：process_feedback
用途：沉淀“实际执行数据 + 上下文 + 结果”，形成可持续学习的数据集。

### 3.2 接口
- `POST /api/planner/processes/{process_id}/feedback`
- `GET /api/planner/processes/{process_id}/feedback`

建议在后续“工艺模板执行/报价预览/生产反馈”环节自动写入。

---

## 4. 工艺模板（Process Module）下一步建议

工艺模板是“可执行版本”的核心，建议同样引入 AI 字段：
- 模块级：`process_modules.metadata_json.ai_spec`（模板意图、适用产品、通用规则）
- 步骤级：`process_module_steps.metadata_json.ai_spec`（步骤口径、输入输出、QC、参数模板）

这样 AI 才能自动“搭建模型/编排工艺路线”，而不是只会推荐工序名。

---

## 5. 推荐落地顺序（最省心）
1) 先把“工序 AI 意图”补齐（从描述迁移/粘贴业务口径即可）
2) 再补“参数模板(JSON)”（先从 3-5 个关键参数开始）
3) 最后开始采集反馈（实际耗时/质量/异常原因）


