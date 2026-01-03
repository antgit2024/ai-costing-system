# Frontend 闭环任务单：结构标准/slot 下拉收口（防呆）MVP

> 角色：@Frontend Agent  
> 背景：当前结构标准与 slot 允许自由输入，容易把 slot 当结构、把结构当 slot，且 code 漂移（大小写/下划线差异）会导致筛选与推荐失效。  
> 目标：把“结构标准选择”和“slot 选择”改成**下拉选择**（来源于结构标准字典页数据），实现 ERP 风格防呆收口。

## 1) 本轮范围（必须很小）

只做一个闭环：
- 工艺模块抽屉：结构标准 code 改为下拉；slot/slots 改为依赖结构标准的下拉（禁止自由新增）
- 标准模型版本：结构标准 code 改为下拉（同一数据源）
- 增加最小 UI 拦截：未选择结构标准时，不允许选择 slot（slot_internal/assembly）

不做：
- 不做后端新接口（MVP 继续复用 taxonomy(domain=`structure_standard`) 或现有结构标准页的数据源）
- 不做结构地图（slot→模块绑定）
- 不做发布校验

## 2) 数据源（MVP 约定）

结构标准列表来自：taxonomy
- `GET /api/planner/taxonomy/items?domain=structure_standard&include_inactive=true/false`
- 约定映射：
  - `code` = `item.name`（唯一键）
  - `display_name` = `item.metadata.display_name`（可选）
  - `slots[]` = `item.metadata.slots`（数组）
  - `is_active` = `item.is_active`

## 3) UI 行为（必须写死）

### 3.1 工艺模块抽屉（ProcessModulesPage）

- 结构标准：Select 下拉（展示 `code + display_name`）
- 适用类型：
  - `slot_internal`：slot 用 Select（单选），选项=当前结构标准的 slots[]
  - `assembly`：slots 用 Select（多选），选项=当前结构标准的 slots[]，至少 2 个（MVP 可只提示不强拦）
  - `global`：隐藏 slots
- 防呆：
  - 未选结构标准时：slot/slots 控件 disabled，并提示“请先选择结构标准”
- 结构标签预览与保存逻辑不变（仍由现有 computeStructureTags 生成）

### 3.2 标准模型版本（ProductModelEditorDrawer）

- “结构标准 code”输入改为 Select 下拉（同一数据源）
- 保存仍调用现有 `PATCH /api/planner/product-model-versions/{version_id}`，只是不再允许自由手填

## 4) 代码范围（必须很小）

仅限：
- `frontend/src/pages/costing/ProcessModulesPage.tsx`
- `frontend/src/components/costing/ProductModelEditorDrawer.tsx`
- `frontend/src/services/planner.ts`（如需新增 fetchStructureStandards：复用 fetchTaxonomyItems）
- `frontend/src/types/planner.ts`（如需补类型）

## 5) 验收命令（只给 1 条）

`npm -C frontend run build`

---

【每轮必须自维护 + 必须提交（强制）】  
你本轮工作完成/暂停前，必须做 3 件事，否则视为未交付：  
1) 更新恢复包（必须）：同步更新 `DOC/agents/state.md`（写清本轮产物+下一步+验收命令+北京时间日期）、必要时更新 `DOC/agents/known_issues.md` / `DOC/agents/commands.md` / `DOC/agents/workset.md`。  
2) 硬验收（必须）：前端跑 `npm -C frontend run build` 并贴出输出。  
3) Git 落地（必须）：把你改动的代码 + 对应 `DOC/agents/*` 一起 `git add`，并提交一次小步 commit（一个主题一个 commit）。


