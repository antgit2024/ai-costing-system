# Frontend 闭环任务单：结构 slot “拼音短码 + 中文名”双语展示（MVP）

> 角色：@Frontend Agent  
> 背景：结构标签用于系统筛选/匹配不应要求人工“读懂”。公司同事英文一般，因此 slot 建议用**拼音短码**作为稳定键（例如 `lalian`），同时在 UI 显示中文名（例如 “拉链位”）。  
> 目标：在不新增后端接口的前提下，让结构标准字典与工艺模块的结构相关 UI **对人友好**，但内部仍使用稳定短码。

## 1) 本轮范围（必须很小）

只交付 1 个闭环：
- 结构标准字典页（`/costing/structure-standards`）：slots 支持维护 **短码 + 中文名**（至少能新增/编辑/删除）
- 工艺模块抽屉与列表：结构相关展示（slot 下拉、结构标签预览/列表列）优先显示中文名；hover/tooltip 显示实际 tag（如 `PILLOW_V1:lalian`）

不做：
- 不改后端 schema / 不新增后端接口
- 不做历史数据自动迁移脚本（MVP 只保证新录入按新口径；旧数据允许“仅显示 raw”）

## 2) 数据落库（MVP 约定，复用 taxonomy metadata）

结构标准仍然是 taxonomy(domain=`structure_standard`)。

新增/使用以下 metadata 字段（都在 item.metadata 下）：
- `slots: string[]`：仍存 **slot_code** 数组（拼音短码），例如 `["lalian","baobian"]`
- `slot_display_names: Record<string,string>`：slot_code → 中文名，例如：
  - `{ "lalian": "拉链位", "baobian": "包边位" }`

说明：
- `slots` 是系统筛选/生成 tag 的来源（稳定键）
- `slot_display_names` 只用于 UI 展示；允许缺失（缺失时回退显示 code）

## 3) UI 行为（必须写死）

### 3.1 结构标准字典页

- slots 编辑从“一个 tags 输入框”升级为“列表式编辑”：
  - 列：slot_code（拼音短码）、slot_name_cn（中文名）、操作（删除）
  - 新增：输入 slot_code + 中文名
  - 编辑：允许修改中文名；slot_code 修改需谨慎（MVP 可禁止修改 slot_code，避免引用漂移）
- 保存时写回：
  - `metadata.slots = [slot_code...]`
  - `metadata.slot_display_names[slot_code] = 中文名`

### 3.2 工艺模块抽屉（结构适用范围区块）

- slot 下拉展示 label：`<中文名>（<slot_code>）`，value 仍为 `slot_code`
- 结构标签预览仍保存 raw tag（如 `PILLOW_V1:lalian`），但 UI 显示：
  - 主显示：`抱枕 / 拉链位`
  - tooltip：`PILLOW_V1:lalian`
- 若缺少字典映射（找不到 slot_display_names）：
  - 显示回退：`PILLOW_V1:lalian`（不阻塞保存）

## 4) 代码范围（尽量小）

仅限（按需）：
- `frontend/src/pages/costing/StructureStandardsPage.tsx`
- `frontend/src/pages/costing/ProcessModulesPage.tsx`
- `frontend/src/components/costing/ProductModelEditorDrawer.tsx`（如要在版本处也展示中文提示可选）
- `frontend/src/services/planner.ts`（复用 taxonomy 拉取即可）
- `frontend/src/types/planner.ts`（如需补充 taxonomy metadata 类型）

## 5) 验收命令（只给 1 条）

`npm -C frontend run build`

---

【每轮必须自维护 + 必须提交（强制）】  
你本轮工作完成/暂停前，必须做 3 件事，否则视为未交付：  
1) 更新恢复包（必须）：同步更新 `DOC/agents/state.md`（写清本轮产物+下一步+验收命令+北京时间日期）、必要时更新 `DOC/agents/known_issues.md` / `DOC/agents/commands.md` / `DOC/agents/workset.md`。  
2) 硬验收（必须）：前端跑 `npm -C frontend run build` 并贴出输出。  
3) Git 落地（必须）：把你改动的代码 + 对应 `DOC/agents/*` 一起 `git add`，并提交一次小步 commit（一个主题一个 commit）。


