# Frontend 闭环任务单：标准模型版本结构标准选择 + 按结构过滤模块候选（MVP）

> 角色：@Frontend Agent  
> 背景：后端已支持：  
> - 工艺模块列表筛选：`GET /api/planner/process-modules?structure_code=&structure_tag=`  
> - 标准版本列表筛选：`GET /api/planner/product-model-versions?structure_standard_code=`  
> 且前端工艺模块页已支持结构筛选与结构标签维护。  
> 目标：把“结构标准”真正落到**模型版本**，并在模型侧“选模块/同步模块”时默认按结构过滤候选，提升精测工艺模块效率并降低误选。

## 1) 本轮范围（必须很小）

只做一个闭环：
- 在**标准模型编辑**场景，让用户为“当前标准版本”选择 `结构标准 code`
- 当用户在模型侧进行“从工艺模块同步/选择模块”时，候选模块请求自动带上 `structure_code=<该版本结构标准>`

不做：
- 不做“结构标准字典管理页面”（下一轮再做）
- 不做“结构地图 slot→模块绑定”（下一轮再做）
- 不做“发布校验/强制必填”（先可空，MVP 不拦截）

## 2) 依赖契约（后端已具备）

- `GET /api/planner/process-modules?structure_code=...`：匹配 `"<code>"` 或 `"<code>:<slot>"` 的结构标签前缀
- 标准版本元数据承载：`product_model_versions.metadata_json.structure_standard_code`

## 3) UI 设计（MVP）

### 3.1 入口位置

- 页面：`/costing/standard-models` → 打开模型抽屉 → 标准版本相关区域

### 3.2 结构标准字段

- 字段名：**结构标准 code**
- 组件：可搜索输入框（MVP 允许自由输入）
- 绑定位置：保存到该版本 `metadata_json.structure_standard_code`

> 注意：此处先不做字典下拉；下一轮再接“结构标准管理”页面与字典接口。

### 3.3 候选模块过滤

- 当用户打开“选择工艺模块/从模块同步”弹窗（或抽屉）时：
  - 若当前版本存在 `structure_standard_code`：
    - 请求候选模块时自动加 query：`structure_code=<structure_standard_code>`
  - 若为空：不加筛选（兼容历史模型）

## 4) 代码范围（必须很小）

仅限以下文件（若发现实际实现不在此处，先由 Hub/Planner 更新 `DOC/agents/workset.md` 再扩范围）：
- `frontend/src/components/costing/ProductModelEditorDrawer.tsx`
- `frontend/src/services/planner.ts`
- `frontend/src/types/planner.ts`
- （如标准入口页需要传参）`frontend/src/pages/costing/StandardModelsPage.tsx`

## 5) 完成标准（可验收）

- 标准模型抽屉里能录入并保存“结构标准 code”（刷新/切换版本后能回显）
- 选择/同步工艺模块时，能看到请求已按结构过滤（可通过 Network 观察 querystring 包含 `structure_code=`）
- 不影响其它入口（打样模型不要求加此字段）

## 6) 验收命令（只给 1 条）

`npm -C frontend run build`

---

【每轮必须自维护 + 必须提交（强制）】  
你本轮工作完成/暂停前，必须做 3 件事，否则视为未交付：  
1) 更新恢复包（必须）：同步更新 `DOC/agents/state.md`（写清本轮产物+下一步+验收命令+北京时间日期）、必要时更新 `DOC/agents/known_issues.md` / `DOC/agents/commands.md` / `DOC/agents/workset.md`。  
2) 硬验收（必须）：前端跑 `npm -C frontend run build` 并贴出输出。  
3) Git 落地（必须）：把你改动的代码 + 对应 `DOC/agents/*` 一起 `git add`，并提交一次小步 commit（一个主题一个 commit）。


