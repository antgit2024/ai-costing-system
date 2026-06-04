# Frontend 闭环任务单：结构标准管理（字典页）MVP

> 角色：@Frontend Agent  
> 背景：目前结构标准 code 已能写入标准版本 `metadata_json.structure_standard_code`，并用于工艺模块候选过滤；但仍靠手填 code，容易产生漂移（同义不同码/大小写/下划线差异），后续推荐与校验会失效。  
> 目标：做一个“像分类一样”的**结构标准主数据管理页**，用于统一维护结构 code/name/slots，并给模型/工艺模块引用提供稳定字典。

## 1) 本轮范围（必须很小）

只做一个闭环：
- 新增一个页面：结构标准管理（列表 + 抽屉）
- 支持结构标准的最小 CRUD（新增/编辑/启用停用）
- UI 先跑通“字典维护”，不做推荐算法/复杂校验

不做：
- 不做“结构地图 slot→模块绑定”（下一轮再做）
- 不做“自动生成/强制校验模型必须选结构标准”（先可空）

## 2) 数据模型（前端口径，MVP）

> 后端可先用 taxonomy 或临时表实现；前端只依赖以下字段口径。

结构标准对象（StructureStandard）：
- `id: string`
- `code: string`（稳定唯一键，建议小写+下划线，如 `pillowcase_v1`）
- `name: string`
- `slots: string[]`（例如：`["front_panel","back_panel","zipper","edging","decoration"]`）
- `status: "active" | "inactive"`（或 `is_active: boolean`，以后端实现为准）
- `updated_at?: string`

## 3) UI 设计（MVP）

### 3.1 页面入口

- 新增菜单：成本核算 → **结构标准**
- 路由建议：`/costing/structure-standards`

### 3.2 列表

列：
- code
- 名称
- slots（展示前 3 个 + “…+N”）
- 状态（active/inactive Tag）
- 操作：编辑 / 启用/停用

筛选：
- 搜索（code/name）
- 状态（全部/启用/停用）

### 3.3 抽屉（新增/编辑）

字段：
- code（新增可编辑；编辑时可锁定或允许但需二次确认）
- name
- slots：Tags 输入（回车新增、可删除）
- 状态：开关（或按钮）

校验（前端最小）：
- code 必填、trim、长度限制（如 3~64）
- slots 去重、trim

## 4) 依赖契约（后端接口，MVP 约定）

> 若后端暂未实现，Frontend 先按此契约对接；Hub/Backend 再补接口闭环。

- `GET /api/planner/structure-standards?search=&status=&page=&page_size=`
- `POST /api/planner/structure-standards`
- `PATCH /api/planner/structure-standards/{id}`
- `POST /api/planner/structure-standards/{id}/activate`
- `POST /api/planner/structure-standards/{id}/deactivate`

## 5) 代码范围（必须很小）

仅限以下文件（若要扩展，先由 Hub/Planner 更新 `DOC/agents/workset.md`）：
- `frontend/src/App.tsx`（加路由）
- `frontend/src/components/layout/AppLayout.tsx`（加菜单项）
- `frontend/src/pages/costing/StructureStandardsPage.tsx`（新页面）
- `frontend/src/services/planner.ts`（新增接口封装）
- `frontend/src/types/planner.ts`（新增类型）

## 6) 验收命令（只给 1 条）

`npm -C frontend run build`

---

【每轮必须自维护 + 必须提交（强制）】  
你本轮工作完成/暂停前，必须做 3 件事，否则视为未交付：  
1) 更新恢复包（必须）：同步更新 `DOC/agents/state.md`（写清本轮产物+下一步+验收命令+北京时间日期）、必要时更新 `DOC/agents/known_issues.md` / `DOC/agents/commands.md` / `DOC/agents/workset.md`。  
2) 硬验收（必须）：前端跑 `npm -C frontend run build` 并贴出输出。  
3) Git 落地（必须）：把你改动的代码 + 对应 `DOC/agents/*` 一起 `git add`，并提交一次小步 commit（一个主题一个 commit）。


