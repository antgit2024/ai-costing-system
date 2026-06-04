## 接力包：新 Planner（成本系统 / ai-costing-system）

> **禁止靠聊天上下文推进**。新 Agent 只需阅读：`DOC/agents/workset.md` → 本文件 → `DOC/agents/state.md` → `DOC/agents/commands.md` → `DOC/agents/known_issues.md`。

### 当前关键结论（必须先记住）

- **防慢/防崩唯一解**：不全仓扫、不直读大文件、不做大 diff；按 `workset.md` 只读；每轮一个闭环；每次变更后维护恢复包（`state/commands/known_issues/workset`）。
- **产品模型入口已拆分（强约束）**：
  - **打样模型**：`/costing/sample-models`（sample 语境）
  - **标准模型**：`/costing/standard-models`（standard 语境，支持 `initialVersionId` 定位）
- **编辑器迁移的唯一承载组件**：`frontend/src/components/costing/ProductModelEditorDrawer.tsx`

### 推荐架构（最稳、成本最低：Hub Agent + 执行 Agent）

> 目标：把“推进”从聊天迁移到仓库可恢复包；降低上下文/大 diff 风险；让任意新 Agent 10 分钟内能接续。

- **Hub Agent（= 新 Planner）职责边界（只做协调/接力/规则执行，不直接写业务代码）**：
  - 维护**可恢复包**：`DOC/agents/workset.md` / `state.md` / `commands.md` / `known_issues.md`
  - 维护**快照目录**：`DOC/index/extracted/`（只存提炼件/已确认正确快照，禁止放入大导出全文）
  - 产出每个域的**下一步闭环任务单**：包含“完成标准 + 1 条验收命令 + 依赖契约（API/类型/字段口径）”
  - 负责**跨域互联**：
    - Backend 接口变化 → 同步到前端索引（`frontend/src/services/planner.ts`、`frontend/src/types/planner.ts`、相关 UI 规格引用）
    - Docs 口径变化 → 同步到 UI 指南/规格（`DOC/costing/ui_specs/*.md`）并提示前端调整
  - 负责**收口范围**：确保每轮只交付一个闭环产物，避免跨文件风暴/大 diff

- **执行 Agent（Frontend / Backend / Docs）职责边界（只改自己域内文件）**：
  - 每轮只做一个闭环：一个页面/组件/接口/文档（不并行开新坑）
  - 必须跑本域验收命令并回填：`DOC/agents/state.md` + `DOC/agents/task_log.md`
  - 不跨域“顺手修”：发现依赖变更需求 → 交给 Hub Agent 产出任务单与契约同步

### 闭环任务单模板（Hub Agent 输出给执行 Agent）

- **任务名**：<域>-<模块>-<一句话目标>
- **范围（必须很小）**：仅限 <文件/目录清单>（若要扩展，先改 `workset.md`）
- **完成标准**：<可观察/可验收的 2-5 条>
- **验收命令（只给 1 条）**：<例如 `npm -C frontend run build` / `pytest tests/... -q`>
- **依赖契约**：
  - API：<method + path + request/response 关键字段>
  - 类型/枚举：<前端 types 或后端 schema 的字段名口径>
  - 文档口径：<UI spec/requirements 引用路径>
- **回填要求**：
  - `state.md`：更新“当前主任务/下一步/验收命令/北京时间校对时间”
  - `task_log.md`：追加一行（日期/模块/角色/任务/结论/待办）
  - 如产出快照/提炼件：写入 `DOC/index/extracted/` 并在 `state.md` 记录路径

### 派单统一尾注（每次派活必贴，执行 Agent 看这一段就知道自己是谁）

> 用法：Hub Agent 派单时，**消息开头第一行**写清楚执行者身份：  
> `你是 @Frontend Agent` / `你是 @Backend Agent` / `你是 @Docs Agent`（只选一个）。  
> 然后贴“闭环任务单”，最后把下面尾注原样粘贴。

【每轮必须自维护 + 必须提交（强制）】  
你本轮工作完成/暂停前，必须做 3 件事，否则视为未交付：  
1) 更新恢复包（必须）：同步更新 `DOC/agents/state.md`（写清本轮产物+下一步+验收命令+北京时间日期）、必要时更新 `DOC/agents/known_issues.md` / `DOC/agents/commands.md` / `DOC/agents/workset.md`。  
2) 硬验收（必须）：前端跑 `npm -C frontend run build`；后端/文档按 `DOC/agents/commands.md` 的命令验收。  
3) Git 落地（必须）：把你改动的代码 + 对应 `DOC/agents/*` 一起 `git add`，并提交一次小步 commit（一个主题一个 commit），避免“正确版本只在工作区、崩了就丢”。  
如果你准备开始下一轮任务但没完成以上 3 件，请先补齐再继续。

### Hub Agent（新 Planner）派单 SOP / 自检清单（给我自己用，你也可以每次派活时贴给我）

> 用法：你每次给我发“请派活/请拆任务”时，把下面这段一起贴给我，我会逐条对齐执行。

【Hub Agent 派单自检（强制）】
0) 只读工作集：我只读取 `DOC/agents/workset.md` 列出的文件/目录；若需要扩展，先更新 `workset.md` 再读。
1) 大文件不直读：任何超大导出/日志先提炼到 `DOC/index/extracted/`，并在 `DOC/agents/state.md` 记录提炼件路径。
2) 一轮一个闭环：本轮只交付一个可验收产物（一个页面/组件/接口/文档）；不达标不扩范围。
3) 派单格式固定：
   - 首行声明身份：`你是 @Frontend Agent` / `你是 @Backend Agent` / `你是 @Docs Agent`（只选一个）
   - 给“闭环任务单”（任务名/范围/完成标准/唯一验收命令/依赖契约/回填要求）
   - 末尾粘贴“派单统一尾注（三件事强制）”
4) 跨域互联：若 Backend/Docs 变化影响前端索引或 UI 口径，我负责同步到：
   - 前端索引：`frontend/src/services/planner.ts`、`frontend/src/types/planner.ts`
   - 文档口径：`DOC/costing/ui_specs/*.md`
5) 可恢复包必须维护：我每次变更后同步更新 `DOC/agents/state.md`（本轮产物+下一步+验收命令+北京时间日期），必要时更新 `known_issues/commands/workset`。
6) 验收命令必须可执行：优先用系统默认可用工具（例如 `grep -n`），避免依赖未安装（如 `rg`）。

### 唯一真相文件（Single Source of Truth）

> 任何口径冲突，以这里为准；不要靠“记忆/聊天摘要”判断。

- **前端接口**：`frontend/src/services/planner.ts`（API_BASE 回退与所有请求封装）
- **前端类型**：`frontend/src/types/planner.ts`
- **编辑器实现**：`frontend/src/components/costing/ProductModelEditorDrawer.tsx`
- **入口页（路由/语境）**：
  - `frontend/src/pages/costing/SampleModelsPage.tsx`
  - `frontend/src/pages/costing/StandardModelsPage.tsx`
  - `frontend/src/App.tsx`
- **后端接口契约（只读校对用）**：
  - `backend/src/planner/routers/product_models.py`
  - `backend/src/planner/routers/product_model_versions.py`
  - `backend/src/planner/schemas.py`
- **规格口径**：`DOC/costing/ui_specs/product_model.md`

### 已确认正确的编辑器快照（禁止覆盖 / 用于恢复）

- **目录**：`DOC/index/extracted/`
- **已确认正确快照（北京时间口径，文件名中为时间戳）**：
  - `DOC/index/extracted/ProductModelEditorDrawer_confirmed_20251221T042643Z.tsx`
  - `DOC/index/extracted/ProductModelEditorDrawer_confirmed_20251221T042643Z.sha256`

### 必须维护的恢复文件清单（每次变更后都要更新）

- `DOC/agents/state.md`
- `DOC/agents/commands.md`
- `DOC/agents/known_issues.md`
- `DOC/agents/workset.md`

### 本轮最小闭环（完成标准 + 1 条验证命令）

- **完成标准**：
  - 打样/标准两个列表页打开抽屉后能正常加载版本与清单，并可保存版本清单（PUT version lines）
  - 无额外扩范围（不并行改无关模块）
- **验证命令（前端门槛）**：`npm -C frontend run build`


