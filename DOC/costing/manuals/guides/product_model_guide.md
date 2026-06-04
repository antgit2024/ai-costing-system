# 产品模型 UI 规格（v0.3）

> 本文档描述 **当前已落地** 的“产品模型（Product Model）”页面结构、字段口径、接口依赖与校验规则，供前后端一致实现与验收。
>
> 参考：`DOC/基础表单/产品模型方案 - 完整版 (for Cursor).md`（业务蓝图）、`DOC/costing/ui_specs/virtual_materials.md`（占位型虚拟物料约束）、后端路由 `backend/src/planner/routers/product_models.py`。
>
> 引擎蓝图（计算顺序、变体规则、快照/版本治理）：`DOC/costing/blueprints/product_model_engine.md`

```guozong
- 产品模型的主线目标：能稳定生成 BOM/成本/扣库清单；发布治理优先（draft 可改，published 受控）。
- 任何“看起来能算”但口径不一致（单位/计量方式/换算/用途）都会导致线上对账困难，宁可先停下问清楚再录入。
```

## 1. 页面入口

- **菜单**：`成本核算 → 模型配置`
- **路由**：`/costing/models`

## 2. 页面结构（列表 + 抽屉 4 Tabs）

### 2.1 列表区

- **筛选**：搜索（模型编码/名称）、状态（draft/active/inactive）
- **表格列（MVP）**：
  - 模型编码 `model_code`
  - 模型名称 `model_name`
  - 状态 `status`
  - 计算模式 `calc_mode`（ratio/fixed/independent）
  - 工艺模块数 `modules.length`
  - 标准尺寸 `standard_width_mm × standard_height_mm`
  - 更新时间 `updated_at`
- **操作（MVP）**：编辑、启用/停用

### 2.2 编辑抽屉（核心：二列工作台 + 明细上下分组）

- **Tab：基础信息**
  - 字段：
    - `model_code`（系统自动生成 3 位短码：A-Z + 1-9，例如 `K7Q`；只读，可点击“生成”重试）
    - `model_name`（必填）
    - `status`
    - `calc_mode`（比例/独立/一口价）
    - `fixed_price`（当 `calc_mode=fixed` 必填；非 fixed 强制清空）
    - `standard_width_mm`、`standard_height_mm`
    - `unit_of_measure`（展示口径；用于对齐尺寸口径/报表口径）
    - `category`、`tags`、`description`
  - 说明：
    - **占位符映射会写入** `metadata_json.placeholder_mappings`，无需用户手工编辑 JSON。

- **Tab：工艺路线编排（主工作台，二列）**
  - **顶部栏（打样尺寸面板）**：宽/高/数量/单位，派生展示 面积/周长，并展示费用汇总（物料/人工/管理费 30%）
  - **左列：工艺模块编排**：添加模块、排序；模块仅作为模板来源
  - **右列（上物料下工序）：模型清单（最终落库，可编辑）**
    - 物料组：每行字段包含 `实际用量（可编辑）/数量/损耗/计量/备注` 等，并支持物料替换与变体入口
    - 工序组：每行字段包含 `班组/实际用时（可编辑）/基础(分)/计量(分)/单价(元/分)/备注`
    - 虚拟物料与普通物料同字段展示（默认不打散子项）
  - **从模块同步**：点击“从模块同步到清单”将模块内容抄入模型清单，并默认保留模型层已调参（可配置 keep_overrides）
  - **保存清单**：将“打样尺寸实际用量/用时 + 标准尺寸单位用量/用时”落库，用于后续 SKU 自动算价与追溯
  - **同步物料价格**：只刷新“模型清单行”的 `BOM单价/单位` 快照（不改用量/工时），用于在物料主数据价格变更后显式重新取价

## 3. 校验规则（MVP）

## 2.3 打样第一原则（口径强约束）

- **打样尺寸必须是实际尺寸**：打样阶段录入的宽/高/数量代表“你真实打样出来的这件货”，用于对齐沟通口径与追溯。
- **本品用量必须手工录入真实用量**：打样阶段每一行的“本品用量/实际用量”以现场量出来/称出来/实测为准；系统不提供“电脑自动计算本品用量”的入口，避免误用导致口径漂移。
- **系统只做推导**：后续“推导标准模型（单位口径/每㎡/每米/每件）”时，才使用打样记录反推参数（如 base_quantity/损耗/按件追加等），用于 SKU 绑定后的稳定出 BOM。

### 3.1 启用校验（后端强校验）

- 当模型引用的工艺模块中存在 `virtual_kind=placeholder` 的虚拟物料行：
  - 必须存在对应 `placeholder_virtual_id` 的映射
  - 映射必须包含 `replacement_kind + replacement_ref_id`
  - 若 `constraint_category` 存在，则目标物料分类必须匹配
  - 若占位符单位存在，则目标单位必须匹配
  - 不允许映射到另一个占位型虚拟物料

### 3.2 计算模式校验（后端强校验）

- `calc_mode=fixed` 时必须提供 `fixed_price`
- `calc_mode!=fixed` 时 `fixed_price` 会被清空

## 4. 接口依赖（已落地）

| 功能 | 接口 |
| --- | --- |
| 列表 | `GET /api/planner/product-models` |
| 详情 | `GET /api/planner/product-models/{id}` |
| 新建 | `POST /api/planner/product-models` |
| 更新 | `PATCH /api/planner/product-models/{id}` |
| 启用/停用 | `POST /api/planner/product-models/{id}/activate` / `POST /api/planner/product-models/{id}/deactivate` |
| 占位符列表 | `GET /api/planner/product-models/{id}/placeholders` |
| 预览计算 | `POST /api/planner/product-models/{id}/preview` |
| 从模块同步到清单 | `POST /api/planner/product-models/{id}/sync-from-modules` |
| 读取/保存模型清单 | `GET /api/planner/product-models/{id}/lines` / `PUT /api/planner/product-models/{id}/lines` |
| 同步物料价格（刷新单价快照） | `POST /api/planner/product-models/{id}/refresh-material-prices` |
| 随机编码生成 | `POST /api/planner/codes/random`（`kind=product_model,length=3`） |
| 工艺模块候选 | `GET /api/planner/process-modules` |
| 物料候选 | `GET /api/planner/base-config/materials` |
| 虚拟物料候选 | `GET /api/planner/base-config/virtual-materials` |

## 5. 验收清单（MVP）

- 能新建/编辑/列表检索产品模型
- 能选择工艺模块并保存顺序（刷新后仍在）
- 若模型引用占位符：未配置映射时点击“启用”会被后端阻止，并提示缺失信息
- 配置完成映射后，模型可成功启用
- 预览计算：输入尺寸/数量后可返回物料/工序明细与汇总；若存在缺失单价/缺失计价参数等，会在 warnings 中提示但不崩溃
- 物料主数据的 BOM 单价变更后：点击“同步物料价格”可刷新模型清单行的 `BOM单价/单位` 展示（不影响你已录入的打样用量/工时）












