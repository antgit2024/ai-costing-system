# 对用户解答的二次评审：factory 维度修正版结论

作者：**Manus AI**  
日期：2026-05-09

## 一、核心修正结论

根据你刚才补充的真实情况，我需要明确修正前一版评审中的一个重要判断：**不能把你们的“三个工厂”理解为三个真实独立、互相可替代、都可能生产同一品类或同一商品的生产工厂。** 你们实际是同一栋楼内的一套生产体系，只是名义上存在一般纳税人和两个小规模主体，部分材料采购、人员归集、费用归属和品类管理会有所区分。

因此，前面“KB8 在不同工厂做的成本完全不同，所以 factory 必须提到 v1”的说法不准确，应当撤回。更准确的判断是：**v1 需要保留组织归集能力，但不应把 factory 作为核心成本优先级维度。系统应该将产品成本主线放在 product_model/category，将材料差异放在 purchase_entity，将人工和固定费用放在 cost_center，将财务税务口径放在 legal_entity。**

> 修正后的总原则是：**你们不是多物理工厂并行生产同品类的成本模型，而是一个实际生产体系下的多主体、多采购口径、多费用归集口径模型。**

| 项目 | 原判断 | 修正后判断 |
|---|---|---|
| 工厂性质 | 多个真实工厂可能生产同一商品 | 同一实际生产体系，名义主体分开 |
| factory 作用 | v1 核心优先级维度 | v1 字段预留，不作为核心优先级 |
| 成本差异来源 | 不同工厂效率、费用、设备差异 | 采购主体、税务口径、人员归集、费用中心差异 |
| v1 主链路 | model + factory / category + factory | model / category / cost_center / global |
| 物料差异 | 可能按 factory 区分 | 应按 purchase_entity、材料价格、税务口径区分 |
| 人工固定费用 | 按 factory 配费率 | 按 cost_center 配费率和费用池 |

## 二、组织维度应拆成四个概念

上一版把很多含义都压在 `factory` 一个字段里，这会导致系统误判。更适合你们业务的方式，是把“名义工厂/主体/采购/费用归集”拆成四个概念。

| 概念 | 建议字段 | 中文含义 | 应承接的业务问题 |
|---|---|---|---|
| 实际生产单元 | `production_unit_id` | 实际干活的生产组织或车间体系 | 你们 v1 多数情况下只有一个默认生产体系。 |
| 采购主体 | `purchase_entity_id` | 一般纳税人或小规模主体的采购归属 | 解决材料由谁采购、材料价和税务口径不同的问题。 |
| 费用中心 | `cost_center_id` | 人工、制造费、公共费用的归集对象 | 解决人员和固定费用如何分摊的问题。 |
| 法律/税务主体 | `legal_entity_id` | 公司主体、开票主体、纳税主体 | 解决财务、税务、内部结算和月度调节问题。 |

这四个概念的关系应当是：`production_unit_id` 描述实际生产在哪里发生；`purchase_entity_id` 描述材料采购成本从哪里来；`cost_center_id` 描述人工和固定费用归到哪里；`legal_entity_id` 描述账务、税务和内部结算归到哪里。它们可以有关联，但不能混成一个字段。

## 三、v1 优先级链应从 factory 改为 cost_center

上一版建议的 8 层链路偏向传统多工厂 ERP，适用于“多个真实工厂都能生产同一产品”的企业。按你们实际情况，v1 不需要把 `model + factory` 做成最重要的精细维度。更合适的是以产品模型和品类为主，以费用中心作为人工和制造费的归集维度。

| 优先级 | 修正版规则 | 是否建议 v1 开放 | 说明 |
|---:|---|---:|---|
| 1 | `order_override` | 是，但需审批 | 特殊订单临时覆盖，必须留痕。 |
| 2 | `model + cost_center` | 可预留，谨慎开放 | 只有当某模型确实由某费用中心专门承担时使用。 |
| 3 | `model` | 是 | 产品模型级标准人工/制造费，是 v1 核心。 |
| 4 | `category + cost_center` | 可预留 | 某类产品归某费用中心时使用。 |
| 5 | `category` | 是 | 品类级默认参数，是模型缺失时的主要回退。 |
| 6 | `cost_center` | 是 | 某费用中心的默认人工/制造费。 |
| 7 | `production_unit` | 暂不强调 | 你们目前实际是一套生产体系，先默认一个即可。 |
| 8 | `global` | 是 | 全局兜底参数。 |

为了控制第一期工程量，v1 前端可以先做四层：**model、category、cost_center、global**。`production_unit` 只作为字段保留，`team` 先不做，`legal_entity` 不进入人工和制造费的主优先级链。

## 四、物料成本应优先接 purchase_entity

你强调“有些材料采购分为一般纳税人和小规模”，这说明物料成本的差异来源主要在采购主体和采购价格口径，而不是生产工厂。Stage 2 做物料成本时，应重点补 `purchase_entity_id`、含税口径和价格来源。

| 字段 | 建议进入 Stage 2 | 说明 |
|---|---:|---|
| `material_id` | 是 | 材料主数据。 |
| `purchase_entity_id` | 是 | 区分一般纳税人、小规模等采购归属。 |
| `supplier_id` | 建议 | 同一材料不同供应商可能价格不同。 |
| `tax_included_flag` | 是 | 标识材料价是否含税。 |
| `tax_rate` | 是 | 用于还原可比成本口径。 |
| `effective_price` | 是 | 成本计算使用的有效材料价。 |
| `price_source` | 是 | ERP、宜搭、Excel 导入或手工修正。 |
| `effective_from/effective_to` | 是 | 价格生效期间。 |

这样设计以后，系统不会错误地问“这个 KB8 是哪个工厂生产的”，而是会正确地问：“这个 KB8 用到的材料由哪个采购主体采购？材料价按什么税务口径进入成本？人工和制造费归哪个费用中心？”

## 五、人工和固定费用应按 cost_center 管理

你说人员也有所不同、会简单分一下类，这个信息对应的是 `cost_center`，不是传统意义上的 `factory`。例如同一栋楼里可以有地毯生产、打印输出、包装发货、公共管理等费用中心。每个费用中心可以设置不同的人工费率、制造费用率和分摊基准。

| 费用中心示例 | 主要成本 | 分摊基准 |
|---|---|---|
| 地毯生产费用中心 | 地毯相关人工、设备、低耗、水电 | 按面积、按件、按标准工时。 |
| 打印输出费用中心 | 打印人员、机器折旧、墨水相关成本 | 按面积、按分钟、按打印量。 |
| 包装发货费用中心 | 包装人工、包装耗材、发货处理 | 按件、按订单。 |
| 公共管理费用中心 | 管理人员、办公、公共水电 | 按订单数、收入、面积或标准工时分摊。 |

所以，人工和固定成本 Hub 的核心字段建议从 `factory_id` 改成 `cost_center_id`。如果以后真的出现物理上独立、成本体系独立的生产场地，再启用 `production_unit_id` 作为更高一层维度。

## 六、对前面 9 条评审的修正结果

你对上一版评审的解答中，大部分结论仍然有效，但第 1 条和第 2 条需要按新事实修正。

| 编号 | 原结论 | 修正后结论 |
|---:|---|---|
| 1 | factory 必须加到 v1 核心维度 | 改为：组织字段必须预留，但 v1 核心应是 `model/category/cost_center/global`。 |
| 2 | 8 层优先级链采用 model × factory × team | 改为：优先级链应从 factory 转向 cost_center，team 暂缓。 |
| 3 | 人工费率支持按件、按面积、按分钟 | 保留，仍然正确。 |
| 4 | 制造费不能只用百分比，要支持分摊基准 | 保留，仍然正确。 |
| 5 | 已结账月份不能直接改 | 保留，必须作为硬规则。 |
| 6 | cost_model_master 不新建，复用 product_model | 保留，仍然正确。 |
| 7 | 8 个面板概念采纳，v1 只做核心面板 | 保留，但面板里的 factory 字段应改为 cost_center/purchase_entity。 |
| 8 | 成本口径和利润层次归入 Phase 2 | 保留，仍然正确。 |
| 9 | 不采用人工语义版本号 | 保留，但建议系统自动生成只读展示名。 |

## 七、最终开发口径建议

修正后的 Cost Rate Hub v1.2 不应描述为“多工厂成本参数 Hub”，而应描述为“成本参数与费用归集 Hub”。这更符合你们一套生产体系、多主体采购、多费用归集的实际情况。

> **Cost Rate Hub v1.2 的正式口径建议：以 product_model/category 管产品标准成本，以 purchase_entity 管材料采购价差异，以 cost_center 管人工与制造费用归集，以 legal_entity 管财务税务与月度调节。production_unit 字段保留但默认单一生产体系，不作为 v1 核心配置维度。**

| 成本模块 | v1 主维度 | 辅助维度 | 阶段安排 |
|---|---|---|---|
| 产品模型成本 | `product_model_id`、`category_id` | `production_unit_id` 默认值 | v1 做。 |
| 人工成本 | `cost_center_id`、`basis_type` | `worker_group`、`process_type` | v1 做。 |
| 制造费用 | `cost_center_id`、`allocation_basis` | `pool_type` | v1 留接口，Phase 2 接费用池。 |
| 物料成本 | `material_id`、`purchase_entity_id` | `tax_mode`、`supplier_id` | Stage 2 做。 |
| 财务调节 | `legal_entity_id`、`period` | `cost_center_id`、`category_id` | Phase 2 做。 |
| 利润事实 | `shipment_id`、`snapshot_version` | `cost_source_trace` | Phase 2 做。 |

## 八、需要写入开发文档的明确改动清单

| 文档位置 | 原写法 | 改动 |
|---|---|---|
| Cost Rate Hub 范围说明 | factory 是 v1 核心维度 | 改为 cost_center 是人工/制造费核心维度，purchase_entity 是物料核心维度。 |
| 优先级链 | model + factory、category + factory | 改为 model + cost_center、category + cost_center，并且 v1 可先不开复杂组合。 |
| 物料成本字段 | 可能按 factory 区分 | 改为必须支持 purchase_entity、tax_mode、price_source。 |
| 人工费率字段 | `factory_id` | 改为 `cost_center_id`，`production_unit_id` 只保留。 |
| 制造费字段 | `factory_id + overhead_rate` | 改为 `cost_center_id + allocation_basis + pool_type`。 |
| 财务调节 | factory/主体混用 | 拆为 legal_entity、purchase_entity、cost_center 三个口径。 |

## 九、最终判断

你这次纠正后，方案反而更清晰了。我们不需要把第一版做成复杂的多工厂 ERP，也不需要维护大量 `model + factory` 参数。真正应该做的是：**产品模型和品类负责标准成本，采购主体负责材料价，费用中心负责人工与制造费，法律主体负责财务税务归集。**

这比“factory 进 v1 核心优先级”更贴近你的实际业务，也能显著降低开发和维护复杂度。我建议后续正式文档都按这个修正版口径推进。
