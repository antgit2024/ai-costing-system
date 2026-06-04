# Frontend 闭环任务单：工艺模块“适用类型（内用/组合/global）”+ 结构标签自动生成（MVP）

> 角色：@Frontend Agent  
> 背景：目前结构标准字典页已可维护 `code + slots[]`，工艺模块也已支持 `metadata_json.structure_tags[]` 与结构筛选。但用户仍会困惑：**一个工艺模块到底属于哪个 slot？还是跨 slot 装配？还是结构无关（global）？**  
> 目标：把“内用 / 组合 / global”落到工艺模块编辑 UI，并用它**自动生成结构标签**，避免手填漂移。

## 1) 本轮范围（必须很小）

只做一个闭环：
- 在工艺模块编辑抽屉新增“适用类型”三选一：`slot_internal / assembly / global`
- 根据选择自动维护 `metadata_json.structure_tags[]`（或至少给出一键生成按钮）

不做：
- 不做结构地图（slot→模块绑定）
- 不做发布校验/强制必填
- 不做复杂的跨 slot 规则推导（先最小可用）

## 2) UI 设计（MVP）

### 2.1 位置

- 页面：`/costing/process-modules` → 编辑/新建模块抽屉
- 新增区块标题：**结构适用范围**

### 2.2 字段

1) **结构标准 code（可选）**
- 输入框/可搜索下拉（MVP 可先输入框）
- 用于生成 tags 的前缀（例如 `PILLV1`）

2) **适用类型（三选一）**
- `内用（slot）`：表示该模块适用于某一个 slot
- `组合/装配（跨 slot）`：表示该模块连接多个 slot（例如包边把前片后片装配）
- `global（结构无关）`：包装/质检/通用整烫等

3) **slot 选择（按类型显示）**
- 内用（slot）：选择 1 个 slot（来源：结构标准字典页的 slots[]；MVP 若无法联动，允许自由输入）
- 组合/装配：选择 slots 多选（至少 2 个）
- global：不显示 slot

4) **结构标签预览（只读）**
- 展示将写入的 `structure_tags[]`（用户可看懂）

### 2.3 自动生成规则（MVP 写死）

给定结构标准 `CODE`：
- 内用（slot=zipper）：生成 `CODE:zipper`
- 组合/装配（slots=[front_panel, back_panel]）：先生成 `CODE`（表示适用该结构）+ `CODE:front_panel` + `CODE:back_panel`
- global：生成 `GLOBAL`（固定字符串）

> 说明：后端现有筛选逻辑 `structure_code=CODE` 目前只匹配 `CODE` / `CODE:*`，不匹配 `GLOBAL`。  
> 所以：本轮 global 先作为“标签语义”，筛选覆盖放到下一轮（需要后端把 global 也纳入 structure_code 过滤的口径，或统一约定 `CODE` 必打）。

## 3) 数据落点（前端写入）

- `process_module.metadata_json.structure_tags: string[]`
- 可选写入（若你们愿意）：
  - `metadata_json.structure_applicability_mode: "slot_internal" | "assembly" | "global"`
  - `metadata_json.structure_standard_code: string | null`
  - `metadata_json.structure_slots: string[]`

> 这些字段属于前端/运营辅助信息，后端不依赖也不破坏。

## 4) 代码范围（必须很小）

仅限：
- `frontend/src/pages/costing/ProcessModulesPage.tsx`
- `frontend/src/services/planner.ts`（如需补类型/字段）
- `frontend/src/types/planner.ts`

## 5) 验收命令（只给 1 条）

`npm -C frontend run build`

---

【每轮必须自维护 + 必须提交（强制）】  
你本轮工作完成/暂停前，必须做 3 件事，否则视为未交付：  
1) 更新恢复包（必须）：同步更新 `DOC/agents/state.md`（写清本轮产物+下一步+验收命令+北京时间日期）、必要时更新 `DOC/agents/known_issues.md` / `DOC/agents/commands.md` / `DOC/agents/workset.md`。  
2) 硬验收（必须）：前端跑 `npm -C frontend run build` 并贴出输出。  
3) Git 落地（必须）：把你改动的代码 + 对应 `DOC/agents/*` 一起 `git add`，并提交一次小步 commit（一个主题一个 commit）。


