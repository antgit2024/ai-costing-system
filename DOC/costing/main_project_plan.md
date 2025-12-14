# 智能成本核算主项目 – 执行方案（v1.0）

> 参考资料：`DOC/智能成本核算系统 - 讨论要点总结（完整版）.md`、`DOC/智能成本核算系统 - Cursor 终极开发指南.md`  
> 目标：在 Planner 子系统上线的基础上，按阶段交付“公式化成本核算 + 变体规则 + 订单物料统计”主项目，形成可实施的路线、分支、责任与验收要点。

## 1. 总览
| 维度 | 内容 |
| --- | --- |
| 业务范围 | 公式化成本模型（实际尺寸→标准 1×1m → 任意核价）、工艺模块、工序/物料管理、变体规则、SKU 绑定、订单导入与成本计算、物料消耗统计、差异分析报表 |
| 技术栈 | Backend：FastAPI + SQLAlchemy + PostgreSQL（沿用现有栈）；Frontend：React/Ant Design（与 Planner 共用设计体系）；同步服务：定时任务 + 宜搭/ERP API 适配器 |
| 主要产物 | 数据模型与迁移脚本、管理后台 UI、成本计算服务、统计报表、QA 脚本与操作手册 |
| 里程碑 | Phase0 准备 → Phase1 数据与同步 → Phase2 管理后台 → Phase3 计算引擎 → Phase4 统计分析 → Phase5 试运行与切换 |

## 2. Workstream 角色与职责
| Workstream | 负责人 | 主要职责 |
| --- | --- | --- |
| Data & Integration | Backend Agent | 宜搭物料同步、ERP/Excel 订单导入、表结构与迁移 |
| Model & Rule UI | Frontend Agent | 工序、产品模型、SKU 绑定、变体规则的管理界面 |
| Cost Engine | Backend Agent (+ 可选 Calc Specialist) | 公式化计算、规则引擎、成本/物料消耗写入 |
| Analytics & QA | Docs/QA Agent | 物料消耗/成本差异报表、回归脚本、数据样本 |
| Planner Coordination | Planner (当前) | 需求拆解、分支管理、验收对齐、风险跟踪 |

## 3. 阶段规划
### Phase 0 – 基线准备（1 周）
- **目标**：共用代码仓与部署脚手架；划分模块（`backend/costing_core`, `frontend/src/modules/costing`）。
- **任务**：
  - Backend：初始化 Alembic 迁移 `0005_costing_core_base`，创建 materials / process_modules / processes / product_models / model_materials / model_processes / variant_rules / sku_model_mapping 等基础表。
  - Frontend：创建“成本核算”入口与路由占位；引入共享 UI 组件库。
  - Docs：在 `requirements.md` 增补主项目章节。

### Phase 1 – 数据与同步中心（2 周）
- **Backend**：
  - 实现宜搭物料同步 job（定时与手动触发），写入 `materials`。
  - 统一将“采购单位价格 + 换算公式”转换为 BOM 单位单价，保存 `bom_unit_price`，同时保留采购单位/单价与换算公式。
  - 开发 ERP/Excel 订单导入 API：解析 Excel → `sales_orders`、`order_items`。
  - 提供同步状态 API 与审计表。
- **Frontend**：
  - 物料列表、导入/同步日志视图。
  - 订单导入向导（上传、字段映射、结果回执）。
- **QA**：制作物料/订单样本数据集；编写同步流程手册。

#### 1.1 宜搭物料字段映射（待确认）
| 宜搭字段 | 说明 | 第一版映射（必备） | 备注 |
| --- | --- | --- | --- |
| 货品编号 | 唯一标识 | `material_code` | Planner/工序引用主键 |
| 货品名称 | 物料名称 | `material_name` |  |
| 物料类型 | 主料/辅料 | `material_type` |  |
| 分类 / 模型类目 | 业务分类 | `category` / `model_category` | 用于筛选 |
| BOM单位 | 计算单位 | `unit` |  |
| 采购单价 或 固定成本价 | 单价 | `unit_price` | 需确认取值逻辑 |
| 采购单位 & 盘点单位 | 不同单位 | `purchase_unit` / `inventory_unit` | 用于换算 |
| 供应商（编码+名称） | 来源供应商 | `supplier_code` / `supplier_name` |  |
| 物料启用 / 状态 | 启用标记 | `is_active` / `status` |  |
| 创建时间 / 修改时间 | 时间戳 | `source_created_at` / `source_updated_at` |  |
| 使用范围 / 模型类目 | 适用范围 | `usage_scope` / `model_category` |  |
| BOM | 备注/说明 | `bom_notes` | 可选 |

> 其余字段（图片、预警上/下限、换算公式、采购负责人等）先同步至 `metadata` JSON 字段，后续按业务需要逐步开放。

### Phase 2 – 管理后台（3 周）
- **模块**：
  - 工序管理（processes + process_materials + process_labors）
  - 产品模型管理（product_models + model_processes）
  - SKU 绑定与批量导入
  - 变体规则管理（极简版：物料替换/新增）
- **交付**：
  - Backend CRUD + 权限校验（沿用 Planner 鉴权策略）
  - Frontend CRUD UI（支持表格筛选、表单校验、批量操作）
  - Docs 更新操作手册
  - QA 编写 CRUD 回归脚本

#### 2.1 工艺模块（物料 + 工序）数据结构
- **工序配置表**（processes）：
  - `process_code`（如 B010）、`process_name`（如“上拉链”）
  - 人工字段：`fixed_time_minutes`、`hourly_rate`、`piece_rate`, `piece_rate_formula`
  - 元数据：班组、说明、质检要求、状态等
- **工艺模块表**（process_modules）：
  - 由“物料清单（process_materials）+ 工序引用（process_labors）”组成
  - 物料部分使用 BOM 单位及换算后的单价，保留采购单位/单价信息
  - 工序部分可同时配置固定工时（LED 接线等不随尺寸变化）与按周长/面积/数量计价项
  - 引用 PDF 示例（《谌婷婷发起的工艺列表_1765587959158.pdf》）的结构：材料区、工序区、质检区
- **模型引用**：
  - 产品模型表仅保存所选工艺模块 ID 列表（如“超薄翻盖配电箱底座, 内包装辅料, 油画布画芯”），系统自动展开物料/工序。
  - 支持在 UI 上选择多个工艺模块并预览带入的物料/人工，避免重复维护。

> 此结构确保“钉子按颗计价”“LED 固定工时 + 周长额外工时”等场景可复用，工序一处配置，多工艺复用。

#### 2.2 模型录入与核价体验
- **实际尺寸 → 标准尺寸**：创建或打样时先输入实际宽高、数量，系统计算出实际成本，并自动归一化到 1×1m 的标准指标（物料/人工/其它指数）。
- **核价工具**：在模型界面提供“核价”面板，运营可输入任意尺寸即时计算价格，用于报价/验证；结果不改动模型数据，便于试算。
- **Tab 设计**：
  1. 模型概况（基本信息、状态、SKU 绑定、指数、实际 vs 标准尺寸对照）
  2. 物料清单（可编辑表格 + Excel 导入，字段同 PDF/Excel 模板）
  3. 工序/人工清单（可编辑表格，支持固定工时与按周长/面积/数量计价）
  4. 工艺模块 & 变体规则（选模块、查看自动带入的物料/人工，并在物料行下管理规则）
  5. 工艺要求 / 质检 / 附件

### Phase 3 – 成本计算引擎（3 周）
- **核心能力**：
  - 公式化计算（周长/面积/数量三种计量方式）
  - 模型标准尺寸（1×1 米）与变体规则执行
  - 管理费 30% 自动附加
  - `order_costs`、`order_material_consumption` 数据写入
  - 批量计算接口（实时 + 批量）
#### 3.1 变体规则实现
- 规则记录存于 `model_variant_rules`（模型级统一管理），字段包含 `source_material_id`、`trigger_type`（字符/面积/周长）、`trigger_value`、`action`（替换/新增）、`target_material_id`。
- 前端在物料表的每一行下方展示该物料的规则（折叠/展开），用户可就地新增/编辑，减少跳转；同时提供“规则总览”列表方便整体审查。
- 复杂差异（不同材质导致工序大变）仍建议直接创建新模型，而非依赖规则。
- **技术事项**：
  - 支持异步 job，复用 Planner Job Drawer 组件
  - 日志 & Trace：记录每个订单的规则命中、成本构成
  - 单测：规则覆盖、单位/面积计算、异常处理

### Phase 4 – 统计分析与报表（2 周）
- 物料消耗汇总报表（按时间/物料/工序维度）
- 成本差异分析（理论 vs 实际）
- 经营分析驾驶舱（订单利润、多维过滤）
- 导出 Excel/CSV、图表展示（Ant Design Charts / ECharts）
- QA：全量回归 + 数据对账脚本

### Phase 5 – 数据初始化与试运行（2 周）
- 协助业务导入历史物料/模型/订单
- 与现有流程并行试运行，记录差异
- 计划切换节点、回滚策略

## 4. 分支与交付策略
| 阶段 | 主分支 | 子分支命名 | 备注 |
| --- | --- | --- | --- |
| Phase0 | `feature/costing-core-phase0` | `feature/costing-backend-phase0`, `feature/costing-frontend-phase0` | 与 Planner 当前主干隔离 |
| Phase1 | `feature/costing-core-phase1` | 同上 | 完成后合并至主干 |
| Phase2+ | 按阶段递增 | `feature/costing-backend-phaseN`, `feature/costing-frontend-phaseN`, `feature/costing-docs-phaseN`, `feature/costing-qa-phaseN` | 每阶段结束前提供 PR + 测试/文档链接 |

## 5. 依赖与环境
- **数据库**：PostgreSQL 继续使用，新增 schemas/table 由 Alembic 管理。
- **外部系统**：
  - 宜搭 API：需申请只读 Key，限制 IP。
  - ERP/吉客云：拉取已发货/退货订单，考虑每 15 分钟同步 + Excel 导入 fallback。
- **配置管理**：`.env` 新增 `YIDAS_APP_ID/SECRET`、`ERP_API_BASE_URL` 等；`validate_env.py` 增加校验。
- **部署**：沿用现有 systemd + Nginx，静态资源在 `/srv/www/ai-costing-system/costing`.

## 6. 交付与验收清单
| 阶段 | Backend 验收 | Frontend 验收 | Docs/QA 验收 |
| --- | --- | --- | --- |
| Phase0 | Alembic 迁移成功、API 健康检查 | 路由占位可访问 | requirements.md 更新 |
| Phase1 | 同步 job + API 日志、重放能力 | 物料/订单导入 UI 可复盘结果 | 样本数据 & 操作手册 |
| Phase2 | CRUD API + 权限单测 | 管理后台交互流畅、批量操作成功 | CRUD 测试脚本 |
| Phase3 | 计算正确率、规则命中日志、订单/物料写入 | 计算任务 UI、作业抽屉 | 引擎运行指南、测试报告 |
| Phase4 | 报表 API、聚合 SQL 通过 | 报表界面与导出 | 报表说明书、差异分析脚本 |
| Phase5 | 试运行数据验收、回滚脚本 | 运营手册更新 | 切换方案与风险评估 |

## 7. 风险与缓解
1. **数据规模**：订单/物料消耗量大 → 采用分区表、批处理、归档策略。
2. **规则复杂度**：先交付极简版（物料替换/新增），复杂工序差异由新模型承担。
3. **外部 API 不稳定**：宜搭/ERP 拉取失败提供重试 + 手动导入 fallback。
4. **权限/安全**：敏感数据仅在 VPN 内访问；对外接口需 WAF/ACL。
5. **工艺模块与虚拟物料**：
   - 工艺模块需版本化管理（如新增 `version`、冻结/复制机制），避免修改影响既有模型。
   - 工艺物料行需记录 `material_type`（real/virtual）与 `material_ref_id`，以支持虚拟物料绑定真实物料后再拆解领料。
6. **模型/工艺引用校验**：模型发布前需自动校验所选工艺模块、物料/工序有效性，并提供模拟计算按钮验证尺寸输入结果。
7. **SKU 绑定与日志**：SKU ↔ 模型绑定操作需记录日志/审批，提供“自动推荐 + 人工确认”流程。
8. **数据留痕与回滚**：工艺/模型/物料同步等关键操作需写入变更日志，支持恢复点；发布/禁用/批量导入等动作要求附说明。

## 8. 下一步
1. Planner 确认阶段时间与负责人，更新 `DOC/agents/task_log.md`。
2. Backend/Frontend 各建立 Phase0 子分支并初始化模块骨架。
3. Docs/QA 开始准备 Phase0 验收条目与样本数据模板。

