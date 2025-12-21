# Hub Agent 派单体系：跨项目标准说明（可复用）

> 适用：任何多 Agent / 多角色协作的代码仓库  
> 目标：把“上下文”从聊天搬到仓库，避免全仓扫描/大文件直读/大 diff 导致变慢与崩溃；让新项目、新 Agent 能 10 分钟内恢复工作。

## 0. 角色与边界（必须遵守）

### 0.1 Hub Agent（= 新 Planner）

**只做：协调/接力/规则执行/派单/跨域同步**，原则上不直接写业务代码（允许写文档、写任务单、维护恢复包）。

Hub Agent 负责：
- 维护恢复包与只读工作集（见第 1 节）
- 将需求拆成“**一轮一个闭环**”的任务单（见第 3 节模板）
- 负责跨域互联：
  - Backend 接口变化 → 同步到前端索引（`services/types`）与文档口径
  - Docs 口径变化 → 同步到 UI 规格/指南，并提醒前端调整
- 严格控制范围：禁止一次改太多、禁止跨文件风暴、禁止全仓扫描

### 0.2 执行 Agent（Frontend / Backend / Docs / Ops）

**只改自己域内文件**，每轮只交付一个闭环产物。

执行 Agent 负责：
- 按任务单实现并跑验收命令
- 回填恢复包（`state/task_log/...`）
- 小步提交（一个主题一个 commit）

> 说明：如果项目需要，可增加 `@Ops Agent`（部署/迁移/重启/网关）。仍由 Hub Agent 派单，Ops Agent 按闭环交付。

---

## 1. 必备文件与目录（新项目必须先建立）

> 这些文件是“唯一上下文载体”。没有它们，任何协作都会退化成聊天堆上下文。

### 1.1 恢复包（必须维护，短小稳定）

放在 `DOC/agents/`：
- `workset.md`：**只读工作集**白名单（允许读取的文件/目录列表）
- `state.md`：当前状态（分支/本轮产物/下一步/验收命令/北京时间）
- `commands.md`：可执行命令清单（build/test/curl/部署）
- `known_issues.md`：已知坑与绕过方式
- `task_log.md`：变更记录（表格，一行一事）

### 1.2 任务单目录（强制）

放在 `DOC/agents/briefings/`：
- 每个闭环任务一份文件，例如：
  - `backend_xxx_mvp.md`
  - `frontend_xxx_mvp.md`
  - `docs_xxx_update.md`

### 1.3 大文件提炼目录（强制）

放在 `DOC/index/extracted/`：
- 任何超大导出/日志/长文禁止直读
- 必须先提炼出 Top-N 片段到该目录，并在 `state.md` 记录提炼件路径

---

## 2. 统一强制规则（新项目必须照抄）

1) **只读工作集**：只允许读取 `DOC/agents/workset.md` 列出的文件/目录；需要扩展阅读先改 `workset.md` 再读。  
2) **大文件不直读**：超大导出/日志必须先提炼到 `DOC/index/extracted/`，并在 `state.md` 记录提炼件路径。  
3) **一轮一个闭环**：每轮只交付一个可验收产物（一个页面/组件/接口/文档），写清“完成标准 + 1 条验证命令”。  
4) **可恢复包必须维护**：每次变更后同步更新 `state/commands/known_issues/workset`（按需），保证崩了也能继续。  
5) **北京时间口径**：所有时间以北京时间（GMT+8）为准。  
6) **验收门槛**：前端每次提交前必须跑 `npm -C frontend run build`；后端/文档按 `commands.md` 执行。  

---

## 3. Hub Agent 派单模板（固定格式）

> 每次派单必须首行声明身份（只选一个）：  
> `你是 @Frontend Agent` / `你是 @Backend Agent` / `你是 @Docs Agent` / `你是 @Ops Agent`

### 3.1 闭环任务单模板（写入 `DOC/agents/briefings/*.md`）

- **任务名**：<域>-<模块>-<一句话目标>
- **范围（必须很小）**：仅限 <文件/目录清单>（若要扩展，先改 `workset.md`）
- **完成标准**：<可观察/可验收的 2-5 条>
- **验收命令（只给 1 条）**：<例如 `npm -C frontend run build` / `pytest ... -q` / `grep -nF ...`>
- **依赖契约**：
  - API：<method + path + request/response 关键字段>
  - 类型/枚举：<字段名口径、可选值>
  - 文档口径：<UI spec/requirements 引用路径>
- **回填要求**：
  - `DOC/agents/state.md`：更新本轮产物/下一步/验收命令/北京时间日期
  - `DOC/agents/task_log.md`：追加一行（日期/模块/角色/任务/结论/待办）
  - 如产出快照/提炼件：写入 `DOC/index/extracted/` 并在 `state.md` 记录路径

### 3.2 派单统一尾注（三件事强制，执行 Agent 必贴）

【每轮必须自维护 + 必须提交（强制）】  
你本轮工作完成/暂停前，必须做 3 件事，否则视为未交付：  
1) 更新恢复包（必须）：同步更新 `DOC/agents/state.md`（写清本轮产物+下一步+验收命令+北京时间日期）、必要时更新 `DOC/agents/known_issues.md` / `DOC/agents/commands.md` / `DOC/agents/workset.md`。  
2) 硬验收（必须）：前端跑 `npm -C frontend run build`；后端/文档按 `DOC/agents/commands.md` 的命令验收。  
3) Git 落地（必须）：把你改动的代码 + 对应 `DOC/agents/*` 一起 `git add`，并提交一次小步 commit（一个主题一个 commit），避免“正确版本只在工作区、崩了就丢”。  
如果你准备开始下一轮任务但没完成以上 3 件，请先补齐再继续。

---

## 4. 新项目落地步骤（最小可用）

1) 在仓库建立上述目录与文件：`DOC/agents/*`、`DOC/agents/briefings/`、`DOC/index/extracted/`  
2) 在 `workset.md` 写入本轮允许读取的最小文件集合（5–20 个）  
3) 在 `commands.md` 写入前端/后端的“唯一验收命令”  
4) Hub Agent 产出第一份任务单（briefing），并严格按模板派单  
5) 执行 Agent 完成后回填 `state/task_log` 并提交小步 commit  

---

## 5. 验收（本标准说明自身的验收方式）

建议在 `state.md` 里给出以下验收命令之一（择一即可）：
- `grep -nF "# Hub Agent 派单体系：跨项目标准说明（可复用）" DOC/agents/task_distribution_standard.md`


