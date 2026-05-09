# PnL 模块决策日志

> **目的**：每个重大设计决策一行（**事实 + 理由 + 状态**），方便后人理解"为什么是这样而不是那样"，避免重复讨论。
> **维护规则**：决策发生时立即写入；废弃决策不删除，状态改为 `废弃` 并附理由。

---

## 决策表

| # | 日期 | 决策 | 替代方案（被否的） | 理由 | 状态 | 决策人 | 关联文档 |
|---|---|---|---|---|---|---|---|
| 1 | 2026-05-08 | 制造费率从写死 0.3 改为月度从 finance 反推 | 继续用 0.3 / 按手工配置 | 同行卖 26 元，我们算 44.55，运营拿不下手 | ✅ 生效 | 老板 + 集团财务 | price_calculation_guide.md §3 |
| 2 | 2026-05-08 | 班组单价从拍脑袋改为 finance 反推（含社保福利全口径） | 维持 v1 月工资 / (26×8×60×0.85) | v1 不含社保福利，效率系数过高 | ✅ 生效 | 工厂总账 + finance | price_calculation_guide.md §2.2 |
| 3 | 2026-05-08 | 物料用量按"原料幅宽切割"算 | 继续按"产品面积 × 损耗率" | 解决 70cm vs 90cm 不公平问题 | ✅ 生效 | 工厂总账 + 采购 | price_calculation_guide.md §1.2 |
| 4 | 2026-05-08 | 引入"内部转移价"机制（三层价格） | 工厂全成本直接给运营 | 解决"运营拿不到合理价格"的根本矛盾 | ✅ 生效 | 老板 + 集团财务 | transfer_pricing_handbook.md |
| 5 | 2026-05-08 | SKU 引入 5 类角色（引流/利润/形象/清仓/新品） | 不分角色统一管理 | 不能把引流款与利润款一刀切 | ✅ 生效 | 运营 + 老板 | sku_portfolio_management_v1.md |
| 6 | 2026-05-08 | Phase 0 文档 5 份核心 + 1 份评审清单 | 单一长文档 / 多 N 份小文档 | 受众不同，分文档便于针对性评审 | ✅ 生效 | 本 Agent | DOC/costing/blueprints/ + handovers/ |
| 7 | 2026-05-09 | 多主体三层模型（法人 → BU → 店铺/班组/品类）+ 6 张表 | finance 单方面做调节 / 完全按法人主体硬分 | 法人税务账 ≠ 经营管理账，调节放 ai-costing 端最灵活 | ✅ 生效 | 集团财务 + 老板（待签） | finance_analyzer_integration_v1.md §7.5 |
| 8 | 2026-05-09 | 品类制造费率必须 Phase 1 就分 | "Phase 1 统一一个工厂费率，Phase 2 再分品类" | 布艺 4-5 人 vs 饰品 4-50 人，工艺差距 10 倍，统一费率必失真 | ✅ 生效（覆盖原 v2 规划） | 工厂总账 + 老板 | finance §7.5.6 + price §3 |
| 9 | 2026-05-09 | BU 方案采用 C+：每法人 1 BU，BU 下挂多店铺 | A：1 工厂 BU + 1 运营 BU；B：按一般纳税人/小规模拆 | 用户业务诉求"每个法人能独立核算 + 一个法人多店铺" | ✅ 生效 | 老板 | finance §7.5.2 |
| 10 | 2026-05-09 | 已采纳 Manus 第一轮外部评审，Phase 1 严格收敛为"订单利润作战室 MVP" | 维持原 Phase 1 大而全 | 避免一年才能上线，先把"算清楚每单赚亏"做透 | ✅ 生效 | 本 Agent + 用户 | pnl_analytics_module_design.md v1.1 头部 |
| 11 | 2026-05-09 | `shipment_pnl_lines` 从 Phase 2 提到 Phase 1 | 维持 Phase 2 | Manus 评审：它是所有分析的底座 | ✅ 生效 | 本 Agent + 用户 | pnl §2 |
| 12 | 2026-05-09 | 三层利润显式化：贡献毛利一 GM1 / 经营毛利二 GM2 / 全成本利润三 NP3 | 只有"变动成本"和"全成本"两层 | 缺中间层 GM2（含广告 + 退款）会让"运营动作问题"看不出来 | ✅ 生效 | 本 Agent + 用户 | price §0.1 + pnl §3.3 |
| 13 | 2026-05-09 | 砍 SKU 决策**优先看 GM1**（贡献毛利一），不看 NP3 | 看综合净利润 | 砍 fullcost_loss SKU 后固定费用不会消失，反而摊给剩下 SKU | ✅ 生效 | 老板 + 运营 | sku §1.4 |
| 14 | 2026-05-09 | 5 类亏损分类（true / op / fullcost / traffic / data_anomaly / profit）| 单一"亏损"标签 | 不同亏损来源决策动作完全不同；data_anomaly 不进决策流 | ✅ 生效 | 老板 + 运营 | sku §1.4 + pnl §3.5 |
| 15 | 2026-05-09 | 每条发货必须锁 `cost_snapshot_id` + 6 个版本字段 | 仅记 cost_calculation_version | 防止历史利润被今天改价污染 | ✅ 生效 | 本 Agent | pnl §3.4 |
| 16 | 2026-05-09 | 月度差异分摊 `monthly_cost_variance`（5 类差异 + 异常拦截）| 仅做总账对账不分摊到 SKU | 让"半实际成本"真正闭环到 SKU 维度 | ✅ 生效（Phase 2） | 集团财务 | finance §7.6 |
| 17 | 2026-05-09 | 转移价 4 线约束（成本 / 市场 / 税务 / 战略）+ 高于市场 1.05 倍报警 | 仅"全成本 × (1 + 利润率)" | 工厂效率不达标时机械加价让运营卖不出去 | ✅ 生效 | 老板 + 采购 | transfer §二·补 |
| 18 | 2026-05-09 | 战略补贴单独入账 `strategic_subsidy_log` | 工厂账面承担补贴 | 不污染品类毛利分析 | ✅ 生效 | 集团财务 | transfer §二·补.3 |
| 19 | 2026-05-09 | 幅宽公式措辞：从"实际消耗面积"改为"标准下料占用面积" | 维持原措辞 | 不是真实排版裁切，命名要诚实，避免误导 | ✅ 生效 | 本 Agent | price §1.2 |
| 20 | 2026-05-09 | 已采纳 Manus 第二轮外部评审 4 项补充 | 不采纳 | 见决策 21-24 | ✅ 生效 | 本 Agent + 用户 | DOC/基础表单/多主体核算与品类制造费率补充评审报告.md |
| 21 | 2026-05-09 | 制造费拆三类：变动 / 固定 / 异常 | 维持 1 个综合费率 | 旺淡季波动 + 小规格被压死 + 异常污染常规成本 | ✅ 生效 | 集团财务 + 老板（待签） | price §3.0 |
| 22 | 2026-05-09 | 4 个固定费用池（工厂固定 / 运营固定 / 集团管理 / 异常战略） | 只有"间接费"一个口径 | 不同池有不同分摊路径与决策用途，混在一起会污染 | ✅ 生效 | 集团财务 + 老板（待签） | finance §7.5.4·b |
| 23 | 2026-05-09 | `shipment_pnl_lines` 加 `cost_center_id / work_team_id / factory_legal_entity` | 维持只到 BU + category | 精细成本归集需要看到成本中心和班组 | ✅ 生效 | 工厂总账（待签） | pnl §3.3 |
| 24 | 2026-05-09 | 三视图（经营 CO / 法人 FI / 集团合并 Group）用 SQL 视图实现，无需新表 | Manus 建议在 finance 端建 `management_accounting_adjustment` 表 | 数据已在 `shipment_pnl_lines`，无需复制 | ✅ 生效 | 本 Agent + 用户 | finance §7.5.11 |
| 25 | 2026-05-09 | finance 端**不新建调整表**；用 finance 现有 3 领域 + ai-costing 现有 6 表覆盖 | Manus 建议新建 `management_accounting_adjustment` | finance 已有按主体三表雏形，重复建设 | ✅ 生效 | 本 Agent + 用户 | finance §7.5.11 + pnl_module_handover.md §8 |
| 26 | 2026-05-09 | "硬卡 finance 三表测试通过"方案废弃，改为 3 个具体契约（C1 主体别名 + C2 接口 pytest + C3 双向 SLA）| 硬卡 finance 测试通过才启动 Phase 1 | finance 反向调用 ai-costing 已是双向耦合，硬卡 = 卡死自己 | ✅ 生效 | 本 Agent + 用户 | finance §9 + phase0 决策 6.c |
| 27 | 2026-05-09 | **不立即拆独立项目**，在 ai-costing 内强划模块边界（`backend/src/pnl/` 等） | 现在就拆独立项目 ai-costing-pnl | finance ↔ ai-costing 已双向耦合，再加新项目变三向；Phase 3 末再评估 | ✅ 生效 | 本 Agent + 用户 | pnl_module_handover.md §4 |
| 28 | 2026-05-09 | 建立 5 份接力 / 运维文档体系（本系列）| 维持仅设计文档（蓝图）| 多 AI Agent 接力 + 1 年长周期，必须有"活文档" | ✅ 生效 | 本 Agent + 用户 | pnl_module_handover.md §2 |
| 29 | 2026-05-09 | **关键转向：现状审计后发现 4 个 Insights 看板 + shipment_costing_results 已生产；不需要新建，改为"增量改造"** | 按原 Phase 1 新建 shipment_pnl_lines + 新建 PnL 看板 | 后端 `shipment_costing_results` 表（migration 0027，2026-01-26 上线）已落 cost_material/process/overhead 三段；前端 4 个 Insights 页面已生产（4170 行代码）；Phase 1 实际编码 5-6 周 → 3 周 | ✅ 生效 | 本 Agent + 用户 | finance §7.5（待修订）+ pnl_module_handover.md §4（待修订） |
| 30 | 2026-05-09 | **关键转向：Phase 1 顺序倒过来——「数据可信度治理」优先，「决策语言（GM1/GM2/NP3、5 类亏损）」后置** | 原 Phase 1 顺序：先加决策语言，最后试跑 | 用户判断"数据不可信 = 一切归零"。当前 KB8 三段成本预期偏差：物料 ±10-30%，人工 40%（巧合下"看起来对"实际全错），制造费 30-100%。在数据治理完成前，加再多决策列也是放大错误 | ✅ 生效 | 本 Agent + 用户 | 待回写 pnl_phase_status.md + 新增 data_trust_governance.md |
| 31 | 2026-05-09 | **新方法论：每个数字旁加可信度徽章（🟢真实 / 🟡估算 / 🔴默认）** + 综合可信度 < 80% 时禁用"砍 SKU/调价"决策按钮 | 不分级直接展示数字 | 强制让"数据治理"成为可见的过程，避免"以为做完了实际没做"；强制让数据可信度成为决策门槛 | ✅ 生效 | 本 Agent + 用户 | 待回写蓝图文档 |
| 32 | 2026-05-09 | **数据治理 4 个口径修复优先级（按差距大小）**：① 制造费率（默认值 → finance 反推）② 班组单价（v1 公式 → finance 全口径反推）③ 物料单价（BOM 写死 → 月度加权）④ BOM 用量（经验损耗 → 真实台账） | 按技术难度 / 按"先易后难" | 数据治理资源稀缺，必须按"修了能立刻见效"排序，不按工程难度 | ✅ 生效 | 本 Agent + 用户 | 待写 data_trust_governance.md |
| 33 | 2026-05-09 | **诊断方法：单 SKU 反向核算法**——选 KB8 一个模型 → 财务/工厂出 5 张真实数据表 → Excel 对账 → 确定 4 个口径的真实偏差 → 按偏差排序修复 | 不诊断直接修 / 抽样统计学方法 | 单 SKU 反向核算 1-2 天可完成，对老板/财务可解释；统计学方法工程量大且数据噪声大 | ✅ 生效 | 本 Agent + 用户 | 待写 kb8_reverse_audit_template.md |
| 34 | 2026-05-09 | **采纳 Cost Rate Hub 方案 + 三阶段路线**：Stage 1 Hub 骨架（2.5 周）→ Stage 2 物料做实（1 周）→ Stage 3 专业能力按需扩展（无限期）| 直接接 finance API 自动反推 / 维持原 v1.1 算法升级路线 | 用户洞察：人工和固定本质是"调节值"，需要几个月才能调真。先做"控制面板/HUB"做平台，把治理动作集中。把"算法依赖"降级为"治理依赖"，财务主动参与，弱依赖 finance 团队 | ✅ 生效 | 本 Agent + 用户 | cost_rate_hub_design_v1.md |
| 35 | 2026-05-09 | **专业能力（sku_role / volume_tier / 学习曲线 / 单位时间毛利 / 多主体费率）通过 Hub 接口扩展，算法层永远不动**：4 个扩展点（scope_type enum / derivation_strategy / metadata_json / API 版本化）| 每个专业能力都改算法 / v1 一上来就堆全 | 用户问"是不是加接口就行"——是的。Hub 设计的核心不在 v1 实现什么，而在 v1 把"扩展点"留好 | ✅ 生效 | 本 Agent + 用户 | cost_rate_hub_design_v1.md §4 |
| 36 | 2026-05-09 | **物料成本不进 Hub，直接从 BOM × 实时物料价 × 真实用量算**，可信度天然 🟢 真实 | 物料价也走 Hub 治理 | 用户洞察："物料成本是实在的，直接从物料里读取"。物料数据有客观依据（采购单/出库台账），不需要"治理"，只需要"做实"（更新单价、补全辅料、修损耗率）| ✅ 生效 | 本 Agent + 用户 | cost_rate_hub_design_v1.md §0.3 + Stage 2 |
| 37 | 2026-05-09 | **Hub v1 实施顺序：先 Hub 骨架 → 再物料做实 → 后专业能力扩展**（不并行）| 三件事并行 / 先物料后 Hub | Hub 是"地基中央"，立起来后所有费率有地方放、可信度有地方挂；物料做实有"对照系"；专业能力扩展有"接入位"。顺序错了会返工 | ✅ 生效 | 本 Agent + 用户 | cost_rate_hub_design_v1.md §11 |
| 38 | 2026-05-09 | **Hub v1 必须做 `cost_snapshot` 锁版本**（不再延后） | 维持原 Phase 1 才做 | 用户改费率时如果不锁 → 历史 SKU 成本会跟着跳变 → 老板对账失败 → "数据不准"问题被替换为"数据漂移"问题（更糟）| ✅ 生效 | 本 Agent | cost_rate_hub_design_v1.md §9 R1 |
| 39 | 2026-05-09 | **Hub v1 范围严格收敛**：只做 Tab 1+2，scope 只 global+model，不做审批流，不做财务月度录入 Tab，不做影响分析 Tab | 一次做完整 4 Tab + 审批流 | 防止 v1 膨胀；Tab 3/4 + 审批流 + 多 scope 全部通过 Stage 3 接口扩展加 | ✅ 生效 | 本 Agent + 用户 | cost_rate_hub_design_v1.md §0 |
| 40 | 2026-05-09 | **采纳 Manus 第三轮外部评审 11 项建议**：8 面板架构 / 4 概念正交 / rate_type 扩展为 3 种 / cost_pool + allocation_basis / 已结账月不可改硬规则 / 留 8 层 scope_type enum / cost_quality 三色徽章 / 凭证上传 / 撤销窗口 / API 版本化 / 治理健康度 | 不采纳 | 全部建议方向正确，与项目现状契合；只有"factory 维度"建议在第四轮被用户校正（见 #41） | ✅ 生效 | 本 Agent + 用户 | DOC/基础表单/成本参数Hub与月度调节面板：评审与设计建议.md / cost_rate_hub_design_v1.md v1.2 §0 §7 |
| 41 | 2026-05-09 | **关键事实校准（覆盖 Manus 第三轮的 factory 部分）**：3 法人物理一体在一栋楼，**整个工厂是 1 个生产体系，不会出现"同商品两个工厂做"**；Hub 不分 factory；后续 production_unit 也只 1 个默认值 | 按 Manus 第三轮"factory 是必需"的建议执行 | 用户明确：3 法人是名义分开的（用于税筹/采购），实际共用一栋楼 + 一支生产队伍。如果按法人维度分费率，会造成虚假分裂 | ✅ 生效 | 老板 + 本 Agent | DOC/基础表单/对用户解答的二次评审：factory 维度修正版结论.md / cost_rate_hub_design_v1.md v1.2 §0.1 |
| 42 | 2026-05-09 | **采纳 Manus 第四轮校正：4 个组织概念正交拆分**——用 `production_unit_id` / `purchase_entity_id` / `cost_center_id` / `legal_entity_id` 替代单一 `factory` 字段 | 维持单一 factory / 不分 4 维 | 4 件事正交：在哪生产 ≠ 谁采购 ≠ 费用归谁 ≠ 谁报税。强行用一个字段会让 v2/Phase2 全面返工 | ✅ 生效 | 本 Agent + 用户 | DOC/基础表单/对用户解答的二次评审：factory 维度修正版结论.md / cost_rate_hub_design_v1.md v1.2 §0.2 |
| 43 | 2026-05-09 | **现状审计校准（v1.2）：复用现有 `processes` + `process_modules` + `materials` + `virtual_materials`（8456 行 UI / 5 张后端表），不新建 cost_rate_master 主表** | 按 v1.0 设计新建 cost_rate_master 统管所有费率 | 现状审计发现：现有 `processes` 已有 `charging_mode`(rate_type) + `standard_rate` + `team_name` + `category`，覆盖人工费率 80% 能力；现有 `materials` 覆盖物料 60% 能力。重新建主表会造成双轨数据不一致 | ✅ 生效 | 本 Agent + 用户 | cost_rate_hub_design_v1.md v1.2 §0.3 §4 |
| 44 | 2026-05-09 | **Hub v1 优先级链 4 层：model > category > cost_center > global**；schema 留 8 层枚举（+production_unit/purchase_entity/legal_entity/sku_role/volume_tier） | v1.0 的 2 层（global+model） | Manus 第三轮建议 8 层 + 第四轮校正后保留 4 层为 v1 实做：cost_center 是 v1 必须解决的"班组费率治理"痛点；其余 4 层 Stage 3 按需开启 | ✅ 生效 | 本 Agent + 用户 | cost_rate_hub_design_v1.md v1.2 §1 §5 |
| 45 | 2026-05-09 | **Stage 2 物料端 4 字段先确定 schema，v1 上线后 +1 周实施**：`materials` 加 `purchase_entity_id` / `tax_included_flag` / `tax_rate` / `price_source` / `effective_from` | 物料端不动 / Phase 2 才加 | 用户业务：1 一般纳税人 + 2 小规模采购法人，物料价含税/不含税混用，必须显式建模才能让物料成本"可信"。Stage 2 实施成本 1 周，与 Hub v1 解耦 | ✅ 生效 | 本 Agent + 用户 | cost_rate_hub_design_v1.md v1.2 §0.2 §4.5 §13 |
| 46 | 2026-05-09 | **新建 `cost_center` 表（5-7 行数据），与现有 `processes.team_name` 共存**：processes 加 `cost_center_id` FK 字段，迁移脚本一次性映射，team_name 字段保留兼容前端 | 直接重命名 team_name 为 cost_center / 强制下线 team_name | 现有 ProcessesPage 1027 行 UI 重度使用 team_name；强制重构会造成 UI 大改风险 | ✅ 生效 | 本 Agent + 用户 | cost_rate_hub_design_v1.md v1.2 §4.1 §4.2 §11 R6 |
| 47 | 2026-05-09 | **Hub 控制台保留 8 个面板槽位，v1 仅实做 Tab 1（总览）+ Tab 2（编辑）；Tab 3-8 在 Stage 2/3 按需加** | 一次做满 8 Tab / 永远只做 2 Tab | Manus 第三轮建议的 8 面板（财务月度录入 / 影响分析 / 学习曲线 / SKU 角色 / 量价档位 / 治理健康度）确实有用，但 v1 验证假设阶段不应膨胀；留好"位置"避免 UI 重构 | ✅ 生效 | 本 Agent + 用户 | cost_rate_hub_design_v1.md v1.2 §7 |

## 待决策（评审会现场拍板）

| # | 日期 | 议题 | 选项 | 谁拍板 |
|---|---|---|---|---|
| P1 | TBD | 7 法人的业务别名 + UUID + 规范全称对照表（C1 契约） | finance 提供初稿，会议现场确认 | 集团财务 + finance |
| P2 | TBD | 跨法人共享开支的分摊基准（5 类首批：房租 / 水电 / 客服工资 / 集团管理 / 引流补贴） | 矩阵列在 finance §7.5.5·b | 集团财务 + 老板 |
| P3 | TBD | 4 个固定费用池的归集口径 | finance §7.5.4·b 的默认值 / 或自定义 | 集团财务 + 老板 |
| P4 | TBD | 评审会的实施负责人任命 | TBD | 老板 |
| **H1** | TBD | **Hub 全局默认 2 个费率初始值** | 维持 0.30 制造费 + 0.45 元/分钟人工 / 或先按某月反推值 | 老板 + 财务 |
| **H2** | TBD | **谁有 Hub 编辑权** | 仅财务 + 老板 / 加 ai-costing 实施负责人 | 老板 |
| **H3** | TBD | **"撤销最近 1 次变更"按钮的可用窗口** | 24 小时 / 7 天 / 永久 | 老板 + 财务 |
| **H4** | TBD | **cost_center 初稿清单（v1.2 新增）** | 6 个默认（饰品/布艺/印花/裁剪包边/包装发货/管理）/ 老板按真实班组校对 | **老板 + 工厂厂长** |

---

## 决策追溯流程

1. **谁能新增决策行**：当前实施负责人 + 任何参与评审会的人
2. **决策行写法**：必须有日期、决策内容、被否方案、理由、状态、决策人、关联文档 7 个字段
3. **决策反悔**：状态改为 `废弃`，新增一条决策行说明替代方案
4. **不要删除老决策**：留作历史教训

---

*文档版本：v1.2*
*创建日期：2026-05-09*
*v1.2 更新：加决策 #40-#47（Manus 第三+第四轮采纳 + 现状审计校准 + cost_center 拆分 + Stage 2 物料端 4 字段 + 8 面板架构 + H4 评审决策点）*
