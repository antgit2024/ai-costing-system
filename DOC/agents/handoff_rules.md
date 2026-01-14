## Rules Agent 接力包（规则/培训专用）

> 目标：把“测试过程中沉淀的规则”统一收口成**可培训、可检索、可版本化**的文档体系，避免口径漂移与新人学习成本爆炸。
>
> 定位：本 Agent 负责**规则沉淀与治理**，不写业务代码；需要时只输出“派单任务单/验收命令/口径决议”供 @Backend/@Frontend/@Ops 执行。

---

### 1) 本 Agent 的职责边界（必须明确）

- **负责**：
  - 把讨论/测试结果写成“规则条目”（含场景、口径、示例、边界、验收方式）
  - 维护新人培训入口（目录/索引/术语表/常见坑）
  - 对“口径冲突”做收口决议，并把变更记录到 `DOC/agents/task_log.md`
- **不负责**：
  - 直接实现功能（由执行 Agent 做）
  - 把规则写进聊天当“唯一真相”（必须落到仓库文档）

---

### 2) 规则文档的落点（统一目录，避免散）

- 新人培训入口（建议唯一入口）：
  - `DOC/costing/manuals/rules_training_handbook_v1.md`
- 规则条目（按主题拆页）：
  - `DOC/costing/manuals/rules/` 目录下逐条新增（推荐：一条规则一页）
  - 模板与命名规范：`DOC/costing/manuals/rules/README.md`
- 变更记录：
  - `DOC/agents/task_log.md`（按日期记录“新增/变更/废弃”）

---

### 3) 规则条目模板（每条规则至少包含）

- **规则编号**：例如 `R-INV-001`
- **适用范围**：发货导入/模型建模/变体/套装/扣库/对账…
- **问题背景**：为什么要这条规则（痛点）
- **规则正文（可执行口径）**：一句话能落地
- **例子**：正例/反例（至少各 1）
- **边界与例外**：什么情况下不适用
- **验收方式**：1 条可执行命令（grep/curl/页面点验）
- **负责人/更新时间**：谁维护、何时更新

---

### 3.1) 专业写法：允许推翻，但不丢历史（强烈建议按状态治理）

> 你担心的“前面写好后面要推翻”是常态。专业做法不是删改到看不出历史，而是：
> **让规则有状态**，让每次推翻都能追溯、可培训、可回滚。

- **规则状态**：
  - `draft`：草稿/探索中（允许频繁修改）
  - `active`：当前唯一有效口径（培训/实施按这个来）
  - `deprecated`：已废弃（保留原因与替代方案，不再执行）
- **推翻/替代的写法**（建议在规则页头部固定字段）：
  - `status: deprecated`
  - `superseded_by: R-XXX-YYY`
  - `effective_from: 2026-01-13`
  - `reason: 为什么推翻（业务变化/发现漏洞/上线反馈）`
- **变更记录纪律（必须）**：
  - 每次把规则从 `active→deprecated` 或引入新的 `active`，都要在 `DOC/agents/task_log.md` 追加一条“决议记录”，包含：
    - 变更摘要、影响范围、关联 PR/commit、验收命令、上线时间点

---

### 4) 本仓已确认的关键口径（从 state/task_log 提取，避免新人乱猜）

- 发货时再解析：spec_hash 缓存 + BOM 快照 + 异常队列 + 重试/重跑语义
- SKU_NOT_BOUND：必须通过“SKU→已发布标准版本绑定”治理
- 结构标准：slot 只做实物区位；工艺实现用工艺模块
- POD（讨论沉淀）：系统侧输出“单裁片 PDF（标准化）”，拼版与最终栅格化优先交给 RIP；150 DPI；长宽比差异允许人工微调

---

### 5) 唯一验收命令（文档存在性）

`grep -nF "## Rules Agent 接力包（规则/培训专用）" DOC/agents/handoff_rules.md`

> 扩展验收（推荐，确保“目录落点”也可用）：`test -d DOC/costing/manuals/rules && grep -nF "## 规则条目目录（Rules）" DOC/costing/manuals/rules/README.md`

---

### 6) 【可复制】接力给新 Rules Agent 的一段话（直接发他/贴给他）

> 你现在接手的是 **Rules Agent（规则/培训治理）**。你的目标不是写业务代码，而是把讨论/测试沉淀成“可培训、可检索、可版本化”的规则体系，并保证 UI 里的“新建指南”能跟着口径变化及时更新。
>
> **单一真相（必须遵守）**：
> - 规则条目（决策/口径层，一条规则一页）：`DOC/costing/manuals/rules/`
> - 新人入口（目录/导航/模板）：`DOC/costing/manuals/rules_training_handbook_v1.md`
> - UI“新建指南”（呈现层，页面按钮展示内容）：`DOC/costing/manuals/guides/`
> - 变更记录（口径决议留痕）：`DOC/agents/task_log.md`
>
> **允许推翻，但不丢历史（专业写法）**：
> - 每条规则要有状态：`draft / active / deprecated`
> - 推翻旧规则：把旧规则标 `deprecated`，写清 `superseded_by / effective_from / reason`；新规则成为唯一 `active`
> - 每次“active 口径变更”都必须在 `task_log.md` 追加决议记录（影响范围 + 验收命令 + 上线时间点）
>
> **上线纪律（你需要推动执行 Agent/或自己执行）**：
> - 规则/指南改动只要会影响 UI 操作，需要重新发布前端静态资源（指南是静态打包的一部分）
> - 前端硬验收门槛：`npm -C frontend run build`（必须 0 退出码）
>
> **验收命令（最小闭环）**：
> - 文档/目录存在性按：`DOC/agents/commands.md`
> - 你提交前至少跑一条综合校验：
>   - `grep -nF "## Rules Agent 接力包（规则/培训专用）" DOC/agents/handoff_rules.md && grep -nF "## 规则与培训手册（v1）— 新人必读入口" DOC/costing/manuals/rules_training_handbook_v1.md && test -d DOC/costing/manuals/rules && test -d DOC/costing/manuals/guides`
>
> **你每天的最小产出**：
> - 把新增/变更的口径写成规则条目（哪怕先是 draft）
> - 同步更新对应 UI 指南（`DOC/costing/manuals/guides/`）
> - 在 `task_log.md` 留一条决议记录（以后新人/回溯全靠这个）

