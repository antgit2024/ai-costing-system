## 成本核算系统 - UI“新建指南”文档（单一真相）

> 目标：把各页面上的 **“新建指南”** 收口到仓库 `DOC/` 下，作为**唯一真相**；
> 前端通过 `?raw` 直接读取这些 Markdown 并展示，避免出现“前端一份、DOC 一份”导致的口径漂移。

---

### 维护原则（强约束）

- **只改这里**：页面上的“新建指南”内容以本目录文件为准。
- **允许推翻**：当新想法推翻旧内容时，不要删历史段落：
  - 在文档中标注“已废弃/被替代”，并写清 **替代方案** 与 **生效时间**。
  - 同时在 `DOC/agents/task_log.md` 记录变更决议与影响范围。
- **上线纪律**：
  - 因为指南被前端静态打包，修改后需要 **重新构建并发布前端静态资源**（见 `DOC/agents/commands.md` 的发布命令）。

---

### 文件清单（按页面）

- `process_create_guide.md`：新建工序指南（三步法）
- `process_modules_guide.md`：新建工艺模块指南（规范/口径）
- `materials_guide.md`：真实物料（物料主数据）新建/维护指南
- `virtual_materials_guide.md`：虚拟物料新建/维护指南
- `product_model_guide.md`：产品模型新建/维护指南
- `derive_standard_per_sqm_tablecloth_example.md`：推导标准每平米（示例）
- `table_list_style_two_line_cells.md`：两行列表风格规范（研发参考）
- `sample_lines_guide.md`：打样指南（清单编辑 Tab）
- `standard_lines_guide.md`：模型指南（清单编辑 Tab）
- `structure_standards_guide.md`：新增结构标准指南
- `access_control_quick_guard.md`：临时访问控制（无用户体系阶段）- IP 白名单
- `team_rate_guide.md`：工价指南（班组默认单价：元/分）
- `price_calculation_guide.md`：价格计算说明（物料费/人工费/制造费）
- `usage_calculation_guide.md`：计算说明（计量方式/本品用量/调参）

