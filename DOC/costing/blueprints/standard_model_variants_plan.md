# 标准模型：变体 / 动态 BOM 功能方案（v0.1）

> 输入来源：`DOC/基础表单/BOM动态生成引擎业务需求说明.md`  
> 目标：把“SKU 绑定 + 规格解析 + 物料组变体（REPLACE/ADD/REMOVE）”落到当前成本系统的 **标准版本（standard）** 体系里，形成可实施的 MVP 路线。

## 1. 范围与非范围

- **范围（本方案覆盖）**：
  - 标准模型（standard 版本）作为“基准 BOM/工艺路线模板”
  - SKU→标准版本绑定（长期有效，可追溯历史）
  - “规格”文本解析为结构化属性（尺寸/面积/周长/关键词 tokens）
  - 基于“物料组”的变体规则：**整组替换/整组增加/整组删除**
  - 输出“最终 BOM”用于：库存扣减、成本核算、生产指引

- **非范围（本轮不做，但会预留接口/数据结构）**：
  - 完整的智能推荐模型（先规则/词典/相似度 MVP）
  - 跨系统（电商/ERP/WMS）实时对接与异步队列（先用 API/任务脚本）
  - 复杂审批准入/权限体系（先最小权限+审计日志）

## 2. 当前系统资产如何复用（对齐现状）

结合现有实现（见 `DOC/costing/ui_specs/product_model.md`）：

- **标准版本（standard）**：已版本化，可发布，可 SKU 绑定；标准口径固定 1㎡（`1000×1000×1`）。
- **SKU→version 绑定**：已有接口 `POST/GET /api/planner/sku-model-version-mapping`，并支持按 SKU 预览 `POST /api/planner/sku-preview`。
- **虚拟物料**：已存在 `recipe/kit/placeholder` 三类能力（placeholder 用于模板层，占位符映射用于落库前替换）。

本方案的关键设计（经业务复核后的推荐）是：**不强依赖“通用虚拟物料（kit）”承载物料组**，而是在“标准版本清单”的每一条物料行上，提供“变体配置”（变体图标）：

- 变体规则**绑定到具体标准版本的具体行**（version-scoped），避免通用实体被多个产品复用导致关系爆炸。
- 规则可以做到“更自由”：对单行进行替换/删除/追加（追加时可增加多行配套物料），并保留可追溯/可回放的命中链路。

## 3. 目标用户流程（端到端）

对应你文档中的端到端示例（规格 `"...;约50*140;024画框+向左推拉"`）：

1. **SKU 绑定（一次性）**
   - 新 SKU 进入 → 标记“待绑定” → 系统按关键词推荐标准模型 → 人工确认绑定到某个 **已发布 standard 版本**。

2. **订单解析（每单）**
   - 解析规格文本 → 输出：尺寸（宽/高/直径）、派生量（面积/周长）、关键词 tokens（如 `024画框`、`推拉`）。

3. **加载基准 BOM（每单）**
   - 通过 SKU→version 绑定获取基准 standard 版本 → 读出其“标准版本清单”（物料行/工序行）。

4. **应用变体规则（每单）**
   - 命中 `024` → 在“画框主料行”的变体中触发：**REPLACE+追加配套行**（画框本体替换，挂扣/螺丝等配套物料随变体清单一起变化）
   - 命中 `推拉` → 在某个“锚点行/功能行”的变体中触发：**ADD**（追加推拉组件的多行物料）

5. **输出最终 BOM（每单）**
   - 将“行级变体”应用到基准清单，得到最终物料行集合 → 按口径（面积/周长/数量）计算数量 → 输出给库存/成本/生产。

## 4. 核心设计（MVP）

### 4.1 规格解析（Spec Parser）

**输入**：订单 `sku_code` + 原始 `spec_text`（非结构化）  
**输出**：结构化 `SpecParseResult`

- **尺寸提取**（MVP）：
  - `50*140` / `50×140` / `约50*140` → width_cm=50,height_cm=140
  - `直径50` / `φ50` → diameter_cm=50
  - 派生：area_m2、perimeter_m

- **关键词 tokens 提取**（MVP）：
  - 分隔符：`; , ， + / |` 等统一切分
  - 词典：画框型号（024/149/...）、功能词（推拉/无框/...）、材质词（宣绒布/...）
  - 输出 tokens：`["024","画框","推拉", ...]`（保留原始片段用于回放/调试）

> 建议：解析器需要“可回放/可解释”，即每个 token 给出来源片段与命中规则，便于运营校对与迭代词典。

### 4.2 行级变体（Line-level Variants）：用“变体清单表”替代通用 kit

#### 4.2.1 你提出的交互（前端）

- 标准版本清单（物料组表）每一行提供一个 **“变体”图标**：
  - 点开后进入该行的“变体配置面板”
  - 可配置多条“候选变体”，每条变体包含：
    - **触发条件**（基于规格解析 tokens / 尺寸派生量）
    - **变体动作**（替换/删除/追加）
    - **变体物料清单**（多行：主料 + 配套料，可自由增减替换）

#### 4.2.2 数据模型（建议：version-scoped，避免通用实体耦合）

以“标准版本的物料行”为锚点：

- `product_model_version_lines`（已存在）：作为基准清单
- 新增（建议）：
  - `product_model_line_variants`：一条“变体规则”记录
    - `id`
    - `version_id`（标准版本）
    - `base_line_id`（指向基准物料行）
    - `priority`（越大越先执行）
    - `enabled`
    - `conditions_json`（规则条件 DSL）
    - `action`（`replace_self` / `remove_self` / `add_siblings` / `replace_bundle`）
    - `notes`（业务解释）
  - `product_model_line_variant_items`：变体输出的“物料清单”
    - `variant_id`
    - `sequence_order`
    - `material_kind`（real/virtual_non_placeholder 等）
    - `material_ref_id`
    - `calculation_method`（area/perimeter/count/width/height）
    - `base_quantity` / `fixed_quantity` / `coverage_ratio`
    - `metadata_json`（可放损耗、备注、来源标记等）

> 这样每个版本自带变体规则与变体清单，不影响其他产品模型；复制版本时规则天然随版本复制，符合 ERP “变更即版本”。

#### 4.2.3 业务逻辑影响与预推（关键场景）

**场景 A：画框组合整组替换（REPLACE）**

- 基准：标准版本里有一行 “画框主料（149）”
- 需求：规格命中 `024` 时，需要把画框本体换成 024，并且挂扣/螺丝等配套也要换
- 行级变体表达：
  - 在“画框主料行”配置变体：条件 `spec_contains_any=["024"]`
  - 动作用 `replace_bundle`（推荐）：输出清单包含多行（024画框、对应挂扣、螺丝…）
  - 引擎执行时：移除原 base_line，并插入 variant_items（多行）到原位置附近（按 `sequence_order`）

**业务影响**：完全覆盖你文档的“物料组替换”，但把“组”内组件收敛为该版本内部配置，不会污染通用实体。

**场景 B：推拉功能组件新增（ADD）**

- 基准：标准版本里没有推拉组件
- 需求：规格命中 “推拉” 时，额外增加一组物料（轨道/滑轮/定位器…）
- 行级变体表达的两种方式：
  - 方式 1（推荐，显式锚点行）：在基准清单里预放一行“功能扩展锚点（虚拟占位行/纯说明行）”，默认不出料；对这行配置 `add_siblings` 变体，命中则追加多行物料。
  - 方式 2（在任意主料行挂载）：在某个主料行配置 `add_siblings`，命中后追加推拉组件多行。

**业务影响**：ADD 场景可实现，但需要明确“追加的插入位置”规则（建议用方式1：锚点行可控、可读性高、运营不易误配）。

**场景 C：无框（REMOVE）**

- 需求：规格命中“无框”时，移除画框相关物料
- 行级变体表达：
  - 在画框主料行配置 `remove_self` 或 `replace_bundle`（输出为空）
  - 如果还有其他依赖画框的配套行（非通过 bundle 输出产生），建议也挂在同一变体 bundle 里统一管理

**业务影响**：比“全局组删除”更可控，但要求模型设计时把“相关物料尽量集中在同一 bundle 管理”，避免漏删。

#### 4.2.4 冲突与执行顺序（MVP）

为避免“多个变体都命中导致重复出料/互相覆盖”，建议：

- 每个 `base_line_id` 的变体规则按 `priority desc` 执行
- 对同一 base_line：**默认 first-match wins**（命中第一条后停止），除非显式 `continue=true`
- ADD 规则建议挂在“锚点行”上，并允许多条命中（多功能可叠加）

### 4.3 变体规则（Variant Rules）

### 4.3 变体规则（Variant Rules）

规则作用对象：**版本内的某个基准物料行（base_line_id）**，并允许输出一个“变体物料清单”（多行）。

#### 规则结构（建议）
- **scope**：作用域（model_code / model_id / version_id / category）
- **priority**：优先级（数字越大越先执行）
- **conditions**（满足即触发）：
  - `spec_contains_any`: ["024","推拉"]
  - `spec_contains_all`: ["无框","地垫"]
  - `area_between`: [0.5, 1.0]
  - `perimeter_between`: [...]
  - `size_between`: width/height 约束
- **actions**（触发后执行）：
  - `REPLACE_GROUP`: { from_group: "149画框组合", to_group: "024画框组合" }
  - `ADD_GROUP`: { group: "推拉功能组件" }
  - `REMOVE_GROUP`: { group: "画框组合" }
- **stop_on_hit**（可选）：命中后是否阻断同类规则继续执行（用于互斥画框型号）

#### 冲突处理（MVP 规则）
- 同一“组位”只允许存在一个（例如画框组）：用 `group_slot="frame"` 表达；REPLACE 只能在同 slot 内替换。
- ADD 允许多个（功能组件可多选），但可通过 `exclusive=true` 或 slot 控制互斥。
- REMOVE 优先级最高（先删除再替换，或替换后再删除需明确）。

### 4.4 动态 BOM 生成流程（计算顺序）

1) 解析规格 → 得到 `SpecParseResult`  
2) 取基准 standard 版本 → 得到 `BasePlan`（组层清单）  
3) 选取规则集合（按 scope 命中）并按 `priority desc` 执行  
4) 对组层清单做 REPLACE/ADD/REMOVE → 得到 `VariantPlan`  
5) 展开 kit → 得到真实物料行 `MaterialLines`  
6) 按口径计算数量：
   - 对需要面积/周长驱动的行：使用 `calculation_method`（area/perimeter/count）
   - 用标准口径（1㎡）做基数，再乘订单面积（或按解析出来的面积/周长/数量）
7) 输出最终 BOM（含来源追溯：命中哪些规则/替换链路/展开链路）

## 5. API / 数据（建议新增项，先给契约）

> 说明：本轮仅出方案，不强制立刻落库；但建议先把契约定下来，避免前后端各写各的。

### 5.1 SKU 绑定（补齐“待绑定”流程）

- **新增**：`GET /api/planner/sku-bindings/pending`  
  - 返回：新 SKU 列表（sku_code/spec_text/first_seen_at/recommendations）
- **新增**：`POST /api/planner/sku-bindings/recommend`  
  - 入参：sku_code/spec_text  
  - 返回：候选 model/version（按关键词/词典规则/相似度）

（已存在）`POST /api/planner/sku-model-version-mapping`：确认绑定到已发布 standard 版本。

### 5.2 规格解析

- **新增**：`POST /api/planner/spec/parse`
  - 入参：`{ sku_code?, spec_text }`
  - 返回：`SpecParseResult`（含 tokens、尺寸、area/perimeter、命中解释）

### 5.3 变体规则 CRUD

- **新增**：`/api/planner/variant-rules`
  - `GET`（分页/按 model/version/category 过滤）
  - `POST/PATCH/DELETE`（带审计日志）

### 5.4 动态 BOM 生成（订单级）

- **新增**：`POST /api/planner/bom/generate`
  - 入参：`{ sku_code, spec_text, quantity?, order_id? }`
  - 输出：最终 BOM + 工艺路线 + trace（规则命中/替换/展开）

## 6. UI 方案（MVP 页面）

### 6.1 SKU 待绑定工作台

- 列表：待绑定 SKU（规格字段预览、解析摘要、推荐模型）
- 操作：确认绑定 / 手工选择模型 / 查看解析详情

### 6.2 标准模型管理（standard 版本）扩展

在“标准版本”相关区域增加：
- 当前版本状态：published 只读提示
- “复制为草稿并编辑”（ERP 风格：改必须走新版本）
- “变体规则”入口（仅管理规则，不直接在清单里写 if/else）

### 6.3 清单行级变体面板（新增）

- 入口：标准版本“清单编辑”Tab 的物料行末尾“变体”图标
- 形态：点击后弹出**独立面板**（Modal/Drawer 均可，建议 Drawer 便于编辑长清单）
- 核心原则：**基准标准模型清单不被直接修改**。变体面板管理的是“覆盖层（overlay）”，用于动态生成/预览/订单出料；只有当用户显式选择“固化为新版本”时才会把结果写回基准清单（可选增强，MVP 不做）。
- 面板内容：
  - 规则列表（按优先级）：条件摘要、动作类型、启用开关、删除
  - 规则编辑：条件构建器（tokens/尺寸区间）、动作选择（replace/remove/add/replace_bundle）
  - 变体物料清单编辑：可新增/删除/替换物料行，并配置数量/口径
  - 调试：给一个 `spec_text` 预演命中结果（展示命中哪条规则、最终会出哪些物料行）

- 插入位置（ADD/replace_bundle 输出多行时必须可预测）：
  - 推荐：用“锚点行”（基准清单中预置一行“可选功能锚点/扩展组件”）作为 `add_siblings` 的唯一挂载点，追加物料默认插入在锚点行之后
  - 对 `replace_bundle`：默认替换发生在 base_line 原位置（同一组输出按 `sequence_order` 排序插入）

> 说明：虚拟物料（recipe/kit/placeholder）仍保留其“通用能力”，但**不再作为物料组变体的主承载**；必要时可在某些型号中复用（例如通用包装件），但不强依赖。

## 7. 验收用例（来自业务场景）

1) 规格：`"...;约50*140;024画框+向左推拉"`  
   - 命中：REPLACE(frame:149→024) + ADD(push_pull)  
   - 输出：BOM 包含 024画框组合的组件 + 推拉功能组件的组件

2) 规格：`"...;无框"`  
   - 命中：REMOVE(frame)  
   - 输出：不含任何画框组合组件

3) 规格格式变化：`;`/`,`/`+` 混用  
   - 解析 tokens 仍稳定命中规则

## 8. 分期建议（最稳最低成本）

- **Phase 0（1-2 天）**：落“行级变体”的数据结构与最小 CRUD（只支持 tokens 条件 + replace_bundle/remove_self/add_siblings），并打通 `spec/parse` 的最小返回（tokens+面积/周长）。
- **Phase 1（2-4 天）**：实现 `bom/generate` MVP：加载 standard 版本清单 → 应用行级变体 → 输出最终 BOM（含 trace/回放信息）。
- **Phase 2（1 周+）**：加入“待绑定 SKU 工作台”+ 推荐（词典/相似度）+ 规则调试回放。
- **Phase 3（后续）**：审批/权限/审计增强；规则表达扩展（尺寸区间、互斥、组合优先级）；对接 WMS/ERP。

## 9. 下一步闭环任务单（供 Hub 派单）

- **Backend Agent**：实现 `spec/parse` + `variant-rules`（只做接口与最小落库），并提供 `bom/generate` demo（可先仅输出“组层计划+展开结果”）。
- **Frontend Agent**：虚拟物料 kit 的“物料组”口径收口（文案/约束）；标准模型管理页增加“复制为草稿并编辑”与“变体规则”入口占位。
- **Docs Agent**：把本方案关键口径同步到 `DOC/costing/ui_specs/product_model.md` 与用户手册（SKU待绑定、变体规则解释、审计/发布治理）。


