# 虚拟物料模块详细设计（Draft v0.1）

> 目标：打造一个与现实库存盘点/消耗统计对齐的“虚拟物料”层，允许业务定义抽象耗材（如“墨水”）并映射到多个真实物料（青/品/黄/黑）。虚拟层只计数、不直接进 BOM，重点解决“总瓶数/总米数准确但各颜色配比难以精确”的场景。

---

## 1. 业务背景
- 运营常以“虚拟集合”来衡量消耗（墨水、包装辅料套装等），而真实物料往往拆分为多 SKU（颜色、规格）。
- 订单核价阶段我们需要统一用 BOM 物料；盘点/统计阶段则要回溯到真实物料。
- 现状痛点：某个虚拟集合的耗用量无法直接回写到各真实物料，只能凭经验拆账，导致库存对账困难。
- 参考 ERP 实践（SAP Phantom BOM、Oracle EBS Substitutable Components）：通常会提供“父级虚拟物料 + 子项真实物料 + 配比”模型，并在真实物料上维持引用关系，便于盘点/成本回溯。本设计即比照这些做法落地在 AI Costing 系统。

## 2. 核心要求
1. **可自定义虚拟物料**：`virtual_code` 唯一、可设置名称/描述/计量单位/标签。
2. **三种虚拟物料类型（关键）**：`virtual_kind` 由虚拟物料头决定，绑定行不允许混用规则。
   - **配方型（recipe / 按比例）**
     - **要求**：所有子物料单位必须一致（或可换算成同一单位；当前系统先按“单位字符串一致”强校验）。
     - **虚拟物料单位**：与子物料单位一致（例如 `ML/㎡`）。
     - **绑定字段**：`quantity_ratio` 表示每 1 个虚拟单位中各子物料的比例（且**合计=1**），`loss_rate` 为损耗率。
   - **套件型（kit / 按数量）**
     - **要求**：子物料单位可以不同，但每个子物料必须有明确的固定数量。
     - **虚拟物料单位**：固定为 `套`（仅用于展示/录入一致性）。
     - **绑定字段**：`quantity_ratio` 表示“每 1 套需要的数量”（可小数），`loss_rate` 为损耗率。
   - **占位型（placeholder / 模板化占位）**
     - **用途**：用于工艺模块模板化占位，**不参与计价**（BOM 单价视为 0）。
     - **要求**：不允许绑定子物料（bindings 允许空数组；非空会被拒绝）。
     - **单位**：必须选择（后续产品模型替换映射依赖口径），不固定为“套”。
     - **命名规范（强制落库）**：数据库字段 `name` 固定存为 `#{...}`（例如 `#{通用PS线条}`），便于在任何引用场景一眼识别为占位；同时 `metadata_json` 同步写入：
       - `virtual_kind=placeholder`
       - `placeholder_name=通用PS线条`（去符号）
       - `placeholder_symbol=#{通用PS线条}`
       - `constraint_category`（必填，限定“该占位符可被哪些真实物料替换”，枚举与工艺模块分类一致）
       - `replacement_hint`（可选，文字提示：如“请替换为 SKU 对应的外饰条”）
       - `replacement_required=true`（系统默认 true，供产品模型启用校验使用）
3. **绑定约束**：
   - 仅允许引用 `is_active = true`、未归档的真实物料，BOM/非 BOM 皆可。
   - 同一个真实物料可被多个虚拟物料引用；系统会在真实物料侧写入 `metadata_json.virtual_links` 供盘点追溯。
4. **盘点统计**：虚拟物料本身不定义默认计算方式；盘点或模型引用时必须在请求中显式传入 `calculation_method`（count/perimeter/area/quantity/custom）或 `usage_context`，系统根据用户提供的口径进行折算。
5. **审计追踪**：记录谁创建/编辑了虚拟物料及绑定，便于仓储人员追踪调整历史。
6. **盘点上下文**：盘点接口 `POST /api/planner/base-config/virtual-materials/{id}/inventory-breakdown` 必须携带 `calculation_method` 或 `usage_context` 至少一个字段，响应会原样回显，供调用方在报表中说明“本次折算的计量口径/使用场景”；若均为空，API 返回 400。

## 3. 数据模型复用
| 表 | 关键字段 | 备注 |
| --- | --- | --- |
| `virtual_materials` | `virtual_code`、`name`、`unit`、`status`、`tags`、`metadata_json` | 已在数据库中创建，可直接启用 |
| `virtual_material_bindings` | `virtual_material_id`、`material_id`、`quantity_ratio`、`loss_rate`、`metadata_json` | `material_id` 指向 `materials.id` |
| `materials` | `metadata_json.virtual_links`（新增约定） | 每次绑定更新 `{virtual_id, virtual_code, ratio}` 列表 |

> 备注：如果未来要允许模型引用虚拟物料，可在 `model_materials.material_type` 中使用 `virtual` 并指向 `virtual_materials.id`。

## 4. API 设计
| Method | 路径 | 描述 |
| --- | --- | --- |
| `GET` | `/api/planner/base-config/virtual-materials` | 列表，支持搜索 `code/name`、状态、标签 |
| `POST` | `/api/planner/base-config/virtual-materials` | 创建虚拟物料 |
| `PATCH` | `/api/planner/base-config/virtual-materials/{id}` | 更新基础信息（不含绑定） |
| `PUT` | `/api/planner/base-config/virtual-materials/{id}/bindings` | 批量覆盖绑定（前端提交完整列表） |
| `GET` | `/api/planner/base-config/virtual-materials/{id}` | 详情，含绑定数组 |
| `GET` | `/api/planner/base-config/materials/{id}/virtual-links` | 查询真实物料被哪些虚拟物料引用 |
| `POST` | `/api/planner/base-config/virtual-materials/{id}/deactivate` | 停用虚拟物料（软删除） |

### 请求/响应要点
- `quantity_ratio`、`loss_rate` 以小数表示，校验 >0 且 loss 可为 0–1。
- 绑定保存时需校验：真实物料存在、未归档、`is_active = true`。
- 返回结构中额外附带 `referenced_materials_count` 供列表展示。

## 5. 前端交互稿
### 5.1 列表页
- 路径：`/costing/virtual-materials`
- 功能区：
  1. 搜索框 + 状态筛选（启用、停用、全部）。
  2. 标签筛选（多选）。
  3. 操作按钮：`新建虚拟物料`、`导出绑定`（预留）。
- 表格列：虚拟编码、名称、引用数量、最近更新时间、状态、操作（编辑/停用）。

### 5.2 详情抽屉/编辑页
1. 基础信息表单（编码、名称、描述、分类、状态）
   - **占位型专属字段**：当类型=placeholder 时，在基础信息区展示以下表单项并写入 `metadata_json`：
     - `占位符名称`（仅输入纯文本；保存时自动包裹 `#{}`）
     - `约束分类 constraint_category`（必填，多选自工艺模块分类，如：面板/骨架/包材）
     - `替换提示 replacement_hint`（可选，用于产品模型编辑提示）
   - **类型/单位不在基础信息里人工维护**：避免“单位/数量含义混乱”。（类型切换放在绑定区，与“保存绑定”同一条保存链路）
2. **绑定编辑器**（重点）：
   - 顶部右侧提供 **类型切换按钮**（与工序库“计时/计件”同款按钮样式）
     - 选择 **配方型**：绑定强制为 ratio（按比例），并自动校验子物料单位一致
     - 选择 **套件型**：绑定强制为 quantity（按数量），单位固定“套”
     - 选择 **占位型**：绑定编辑器隐藏/禁用（不绑定子物料），BOM 单价固定显示 0 并提示“占位型不计价，仅用于模板化”
   - `Table Form` 或 `List` 形式，每行字段：`物料缩略图`、`物料编码`（可搜索选择）、`物料名称`（自动带出）、`单位`（只读）、`配比/数量（quantity_ratio）`、`损耗率（loss_rate %）`。
   - 行尾操作：复制、删除。
   - 顶部说明：
     - 配方型：子物料单位必须一致；配比合计必须为 100%
     - 套件型：子物料单位可不同；数量为“每套用量”
     - 占位型：不绑定真实物料；请在产品模型中为 `#{占位符}` 配置替换映射
   - **虚拟 BOM 单价**：显示为 `¥xxx / <单位>`，其中：
     - 套件型：单位永远为 `套`
     - 配方型：单位从“子物料单位一致性校验通过后”的单位自动推导（无需人工输入）
3. “引用关系”区块：
   - 配方/套件型：展示当前虚拟物料绑定的真实物料列表，可点击跳转到对应真实物料详情。
   - 占位型：展示“引用该占位符的工艺模块”列表，供运营快速定位需要配置替换映射的模块。

## 6. 盘点 & 报表
- 使用 `POST /api/planner/base-config/virtual-materials/{id}/inventory-breakdown` 计算折算结果，Body 结构：
  ```json
  {
    "quantity": 120,
    "calculation_method": "count",        // 可选
    "usage_context": "SKUX-户外软膜"      // 可选，calculation_method 与 usage_context 至少提供一个
  }
  ```
- 响应中会回显 `calculation_method` 与 `usage_context`，并列出每个真实物料的 `required_quantity`。前端详情页的“盘点计算器”小组件需支持“数量 + 计算方式（可选） + 使用场景（可选）”输入，并在结果区展示这两个字段，方便导出/截图时说明“本次折算依据”。

## 7. 标签写回策略
- 每次保存绑定时：
  1. 对所有涉及的真实物料写入 `metadata_json.virtual_links`，并记录 `{virtual_id, virtual_code, ratio}`。
  2. 对取消绑定的真实物料剔除对应条目。
- 前端真实物料详情（Material Drawer）增加“虚拟引用”只读区域，列出所有虚拟物料名称+比例，便于核查。

## 8. 权限与审计（对齐 ERP 控管流程）
- **权限分层**：
  - 成本/计划团队：可创建、编辑、停用虚拟物料；维护配比规则。
  - 仓储团队：只读访问，可使用盘点计算器查询折算结果。
  - 审批（可选）：若绑定关系影响财务核算，可通过工作流在变更前触发审批。
- **审计记录**：所有 create/update/bindings 操作写入 `audit_logs`（`target_type=virtual_material`），记录旧/新绑定列表、操作者、trace_id，满足 SOX/内控要求。
- **标签对帐**：真实物料被引用时在 metadata 留下“虚拟链接 + 时间戳 + 操作者”，方便事后追溯是谁建立关联。

## 9. 开发拆解
1. Backend：
   - REST 路由 + service + schema +单测（覆盖绑定校验、标签写回）。
   - 定义 `VirtualMaterialService`，支持 `list/create/update/bindings/bulk_export`.
2. Frontend：
   - 新增页面、路由、服务调用；绑定编辑器组件封装。
   - 真实物料详情中读取 `metadata.virtual_links`。
3. Docs：
   - 扩充 `planner_user_guide` “虚拟物料”章节；更新 runbook/ERD。

## 10. 后续展望
- 允许产品模型引用虚拟物料，并在 BOM 计算时自动展开。
- 结合 `VirtualMaterialBinding` 与库存系统对接，实现实时扣减。
- 引入版本控制（虚拟物料的绑定变更需要审批/发布）。

---

> 若本设计无异议，下一步由 Backend 先实现 API + 单测，Frontend 同步页面，Docs 更新用户手册与 runbook。欢迎补充更多场景（如虚拟工序、批次管理）。 ✍️

---

## 11. 兼容说明（线上后端未升级时）
- 若某些部署环境的 API 暂未返回/保留 `virtual_kind` 字段，前端可通过以下方式保持“类型回显”稳定：
  - `unit != 套` ⇒ 推断为配方型
  - 或根据 `bindings[].binding_type`（ratio/quantity）推断
- 占位型兼容：若后端尚未支持 `virtual_kind=placeholder`，前端会优先根据 `metadata_json.placeholder_symbol` 推断为占位型；待后端升级后以 API 字段为准。
- 建议最终仍以 API 字段 `virtual_kind` 为准；待后端升级后可移除推断逻辑。

## 12. 与工艺模块 / 产品模型的协作规则

1. **工艺模块引用**：
   - 配方/套件型：工艺模块保存时校验物料引用是否启用、是否满足配比/数量规则。
   - 占位型：工艺模块仅检查虚拟物料状态=启用，不做真实物料校验，允许模块模板先行发布。
2. **产品模型替换映射**：
   - 当模型引用的工艺模块中存在 `virtual_kind=placeholder` 的物料行，模型编辑器必须提供“占位符 → 真实物料”映射列表，且映射需指定 `material_id` 与（如需要）虚拟到真实的数量换算。
   - **启用校验**：模型从 draft/review 切换到 published/active 前，系统会检查所有占位符是否拥有替换映射；若缺失则阻止启用并提示 `#{symbol}` 及其 `constraint_category`。
   - 映射结果会在导出/盘点时用于展开真实物料，并写入 `audit_logs` 便于追溯。
3. **截图/验收提示**：
   - 虚拟物料页面新增“占位型”表单与约束字段，需要在上线回执中附 UI 截图（创建占位型 + 工艺模块引用占位符）。
   - 产品模型启用前的校验弹窗也需截图，确认缺少替换映射时 UI 正确阻止启用并列出缺失列表。

## 13. 价格治理（ERP 口径：实时价 + 显式取价/快照）

> 目标：避免“物料主数据价格变了，但工艺模块/产品模型仍用旧价”导致核价偏差。

### 13.1 实时价（用于预览/模拟）
- **来源**：真实物料主数据的 `metadata_json.bom_unit_price`（以及单位）。
- **虚拟物料单价**：
  - recipe/kit：由绑定真实物料的 BOM 单价按规则汇总派生（含绑定损耗）。
  - placeholder：固定 0，不计价。
- **适用场景**：用户在产品模型中点击“刷新汇总/预览”时，按最新主数据实时计算。

### 13.2 显式取价/快照（用于展示与锁定口径）
- **产品模型层**提供“同步物料价格”按钮：
  - 仅刷新模型清单行的 `metadata_json.bom_unit_price / bom_unit` 快照
  - **不修改**用量/工时等调参数据
  - 用于主数据价格变更后，用户显式确认“本模型以最新单价重新核价”

> 注意：订单/报价层若需要“历史可追溯不随主数据改价波动”，应在订单生成时落成本快照（后续迭代）。

