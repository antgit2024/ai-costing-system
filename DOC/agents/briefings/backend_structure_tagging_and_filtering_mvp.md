# Backend 闭环任务单：模型结构化落点（结构标准/工艺模块标签）+ 列表筛选 MVP

> 角色：@Backend Agent  
> 背景：我们要推进“模型结构化/精测工艺模块”，但目前结构信息只停留在文档/口头约定，无法在 UI 中做筛选/推荐/校验。  
> 目标：用**最小成本**把结构化“落点”打通：  
> - 产品模型版本落 `structure_standard_code`（表示该版本属于哪个结构标准）  
> - 工艺模块落 `structure_tags[]`（表示该模块适用于哪些结构/slot）  
> 并在列表接口支持按这些字段筛选（让前端能做“按结构找模块/按结构找版本”）。

## 1) 本轮范围（必须很小）

只做一个闭环：
- 通过 `metadata_json` 承载两个结构化字段（不新增表/不加新列）
- 为两个现有列表 API 增加筛选参数：
  - `GET /api/planner/process-modules` 支持按 `structure_tag` / `structure_code` 筛选
  - `GET /api/planner/product-model-versions` 支持按 `structure_standard_code` 筛选
- 返回结构保持兼容（不破坏现有字段）

不做：
- 不做“结构标准字典管理 UI/CRUD”（先用字符串约定，下一轮再做 taxonomy 字典）
- 不做“推荐算法/slot 自动填充”（前端先筛选+运营手填标签即可）
- 不做跨表深度引用校验（只保证字段可写可查）

## 2) 字段口径（必须写死）

### 2.1 产品模型版本结构标准

- 位置：`product_model_versions.metadata_json.structure_standard_code`
- 类型：`str`
- 示例：
  - `"pillowcase_v1"`
  - `"decoration_combo_painting_v1"`

### 2.2 工艺模块结构标签

- 位置：`process_modules.metadata_json.structure_tags`
- 类型：`List[str]`（默认空数组）
- 推荐格式（先统一一个最简单的、可运营的约定）：
  - `"<structure_standard_code>"`（表示通用适配该结构）
  - `"<structure_standard_code>:<slot>"`（表示适配某个 slot，例如 `pillowcase_v1:zipper`）

> 备注：不强制解析 slot，只当字符串筛选；slot 的枚举由结构标准文档/运营表后续收敛。

## 3) 接口改动（新增筛选参数，尽量不破坏）

### 3.1 Process Modules 列表筛选

- 现有：`GET /api/planner/process-modules?search=&category=&status=&page=&page_size=`
- 新增 query（可选）：
  - `structure_tag: str | null`（精确匹配标签；例如 `pillowcase_v1:zipper`）
  - `structure_code: str | null`（匹配结构标准；例如 `pillowcase_v1`，应同时命中 `pillowcase_v1` 与 `pillowcase_v1:*`）

### 3.2 Product Model Versions 列表筛选

- 现有：`GET /api/planner/product-model-versions?search=&version_kind=&version_status=&page=&page_size=`
- 新增 query（可选）：
  - `structure_standard_code: str | null`

## 4) 实现要点（数据库兼容）

- Postgres：优先用 JSON 查询（如 contains / jsonb_path_query），避免全量拉取后 Python 过滤
- SQLite（若测试环境使用）：允许 fallback 为 Python 过滤（page_size 小时可接受），但要保证行为一致
- 统一保证：
  - 未设置字段时不影响现有列表（等价于不筛选）
  - `metadata_json` 默认空对象/空数组，不抛异常

## 5) 单测（必须最小覆盖）

建议新增：
- `backend/tests/planner/test_structure_tag_filters_mvp.py`

至少覆盖：
- 创建/更新 process_module metadata 写入 `structure_tags` 后，列表按 `structure_tag` 能筛到
- 创建 product_model_version metadata 写入 `structure_standard_code` 后，列表按该字段能筛到

## 6) 验收命令（只给 1 条）

`python -m pytest backend/tests/planner/test_structure_tag_filters_mvp.py -q`

---

【每轮必须自维护 + 必须提交（强制）】  
你本轮工作完成/暂停前，必须做 3 件事，否则视为未交付：  
1) 更新恢复包（必须）：同步更新 `DOC/agents/state.md`（写清本轮产物+下一步+验收命令+北京时间日期）、必要时更新 `DOC/agents/known_issues.md` / `DOC/agents/commands.md` / `DOC/agents/workset.md`。  
2) 硬验收（必须）：按本单验收命令跑通并贴出输出。  
3) Git 落地（必须）：把你改动的代码 + 对应 `DOC/agents/*` 一起 `git add`，并提交一次小步 commit（一个主题一个 commit）。


