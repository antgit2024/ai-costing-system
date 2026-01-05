## 当前状态（崩了也能继续）

- **最近校对（北京时间 GMT+8）**：2026-01-05（Planner：接力清理崩溃遗留的跨域未提交改动，恢复干净工作区；已硬验收 `npm -C frontend run build` 通过）
- **最近校对（北京时间 GMT+8）**：2026-01-05（Frontend：行级变体“替换物料”选择器新增“同单位置顶 + 仅同单位筛选”，通过 `baseUnit` 透传，减少单位不一致返工；验收 `npm -C frontend run build`）
- **最近校对（北京时间 GMT+8）**：2026-01-05（Backend：spec/parse 增补短语 token（白名单，先覆盖“背面纯色”），使 TOKEN(any) 规则可命中；验收 `./backend/venv/bin/python -m pytest backend/tests/planner/test_spec_parser_code_tokens.py -q`）
- **最近校对（北京时间 GMT+8）**：2026-01-05（Ops-ish：按强制流程重构并原子发布前端静态资源：`cd /home/admin/ai-costing-system/frontend && npm run build` + `PLANNER_STATIC_DIR=/var/www/html/ai-costing/dist ./scripts/deploy_static.sh`）
- **最近校对（北京时间 GMT+8）**：2026-01-05（Frontend：新增“产品上架（测试台）”页：`/costing/product-listing`，支持输入交易规格→spec/parse→bom/generate 只读诊断（解析结果/命中情况/最终BOM）；验收 `npm -C frontend run build`）
- **最近校对（北京时间 GMT+8）**：2026-01-05（Frontend：产品上架（测试台）版本选择支持“显示全部标准版本（含 draft/archived）”，默认仍仅 published，便于未发布版本先测试；验收 `npm -C frontend run build`）
- **最近校对（北京时间 GMT+8）**：2026-01-05（Frontend：产品上架（测试台）在最终BOM下追加“工序明细”与成本汇总：合计=物料+工序+制造费30%，金额保留2位；验收 `npm -C frontend run build`）
- **最近校对（北京时间 GMT+8）**：2026-01-05（Frontend：产品上架（测试台）补齐“扣库清单（真实物料展开）”展示：读取 `trace.inventory.inventory_lines`（用于库存/对账口径）；验收 `npm -C frontend run build`）
- **最近校对（北京时间 GMT+8）**：2026-01-05（Frontend：产品上架（测试台）“命中情况”Tab 增强：展示触发条件表达式 + 基准物料 + 替换物料（通过版本清单 + line-variants 查询拼装），便于运营一眼排错；验收 `npm -C frontend run build`）
- **最近校对（北京时间 GMT+8）**：2026-01-05（Frontend：标准模型管理清单编辑防呆：仅 draft 版本允许“新增/替换物料、工序”；非 draft 直接禁用入口并提示先复制版本，避免误以为“没落库”；验收 `npm -C frontend run build`）
- **最近校对（北京时间 GMT+8）**：2026-01-05（Backend：修复 `GET /api/planner/process-modules?structure_code=...` 500（兼容性：结构筛选改为 Python 过滤，避免 Postgres JSONPath 不兼容）；验证：`curl -sS "http://127.0.0.1:8800/api/planner/process-modules?page=1&page_size=10&structure_code=baozhen"`；验收：`./backend/venv/bin/python -m pytest backend/tests/planner/test_structure_tag_filters_mvp.py -q`）

- **最近校对（北京时间 GMT+8）**：2025-12-30 19:20（接力入口：`DOC/agents/handoff_planner.md` / `DOC/agents/handoff_backend.md`）
- **最近校对（北京时间 GMT+8）**：2025-12-30 20:27（Frontend：关联引用直达编辑 + 列宽收口）
- **最近校对（北京时间 GMT+8）**：2025-12-30 21:03（Backend：关联引用过滤已归档/删除记录）
- **最近校对（北京时间 GMT+8）**：2026-01-03 11:53（Frontend：发货异常重试 + SKU_NOT_BOUND 去绑定 CTA）
- **最近校对（北京时间 GMT+8）**：2026-01-03 11:57（Frontend：Shipments 静态资源原子发布到 47.99.89.206）
- **最近校对（北京时间 GMT+8）**：2026-01-03 12:39（Frontend：工艺模块结构筛选 + 结构标签维护 MVP）
- **最近校对（北京时间 GMT+8）**：2026-01-03 13:10（Frontend：标准版本结构标准 code + 模块候选按结构过滤 MVP）
- **最近校对（北京时间 GMT+8）**：2026-01-03 14:02（Frontend：结构标准字典页 MVP）
- **最近校对（北京时间 GMT+8）**：2026-01-03 14:35（Frontend：工艺模块“适用类型 + 自动结构标签” MVP）
- **最近校对（北京时间 GMT+8）**：2026-01-03 14:56（Frontend：结构标准/slot 下拉防呆收口 MVP）
- **最近校对（北京时间 GMT+8）**：2026-01-03 15:18（Frontend：结构标准字典页支持删除（归档））
- **最近校对（北京时间 GMT+8）**：2026-01-03 15:55（Frontend：结构标准 slots 列表式编辑（中文+自动拼音短码）+ 工艺 slot 下拉中文显示）
- **最近校对（北京时间 GMT+8）**：2026-01-03 16:05（Frontend：工艺模块抽屉补“global/slot/assembly 选择规则”说明）
- **最近校对（北京时间 GMT+8）**：2026-01-03 16:25（Backend：structure_code 过滤自动包含 GLOBAL 通用模块）
- **最近校对（北京时间 GMT+8）**：2026-01-03 16:40（Frontend：选工艺模块候选标注 GLOBAL 通用模块）
- **最近校对（北京时间 GMT+8）**：2026-01-03 16:52（Frontend：工艺模块结构适用范围保存强校验防呆）
- **最近校对（北京时间 GMT+8）**：2026-01-03 17:05（Frontend：global 隐藏结构标准下拉 + 自动清空）
- **最近校对（北京时间 GMT+8）**：2026-01-03 17:30（Frontend：工艺模块删除高难度确认 + AI生成去数值污染；Backend：AI describe 支持结构字段）
- **最近校对（北京时间 GMT+8）**：2026-01-03 17:45（AI生成：描述统一追加“无默认数值”声明）
- **最近校对（北京时间 GMT+8）**：2026-01-03 18:00（Frontend：工艺模块查看模式也可点 AI生成）
- **最近校对（北京时间 GMT+8）**：2026-01-03 18:28（Frontend：结构标准 slots 支持“启用/可选位”（默认启用，取消则不进工艺下拉））
- **最近校对（北京时间 GMT+8）**：2026-01-03 18:45（Frontend：标准模型展示所选结构标准的结构骨架预览）
- **最近校对（北京时间 GMT+8）**：2026-01-04（Frontend：新接力验收通过：`npm -C frontend run build` + Docs grep + Backend curl smoke）
- **最近校对（北京时间 GMT+8）**：2026-01-04（Frontend：工艺模块复制后保存误报“未选择工序行”修复：保存时忽略纯占位空工序行）
- **最近校对（北京时间 GMT+8）**：2026-01-04（Frontend：工艺模块步骤 process_id 兜底修复：保存/校验兼容 step.process.id 与 metadata_json.process_snapshot.id）
- **最近校对（北京时间 GMT+8）**：2026-01-04（Frontend：工艺模块复制后步骤缺失 process_id：保存时按 process_code 自动反查并回填（唯一命中则自动修复，否则提示重选））
- **最近校对（北京时间 GMT+8）**：2026-01-04（Frontend：修复后端步骤快照字段名不一致：process_snapshot.process_id 也视为已选工序，避免复制后保存被拦截）
- **最近校对（北京时间 GMT+8）**：2026-01-04（Frontend：复制工艺模块保存仍误报：在抽屉 hydrate 时将 process_snapshot.process_id 回填到 step.process_id（避免 Form store 丢快照字段）；并修复跳转 state 传 null 导致 /process-modules/null 404）
- **最近校对（北京时间 GMT+8）**：2026-01-04（Frontend：补强护栏：process-modules 详情查询仅允许 UUID，清理非法 openProcessModuleId，彻底阻断 /process-modules/null 404）
- **最近校对（北京时间 GMT+8）**：2026-01-01（Backend：发货异常队列“按批次重试未解决异常（Retry Exceptions）”MVP）

- **最近校对（北京时间 GMT+8）**：2025-12-25 04:30（接力入口：`DOC/agents/handoff_planner.md` / `DOC/agents/handoff_frontend.md`）
- **最近校对（北京时间 GMT+8）**：2025-12-25 06:08（接力入口：`DOC/agents/handoff_planner.md` / `DOC/agents/handoff_frontend.md`）
- **最近校对（北京时间 GMT+8）**：2025-12-25 14:40（接力入口：`DOC/agents/handoff_planner.md` / `DOC/agents/handoff_frontend.md`）
- **最近校对（北京时间 GMT+8）**：2025-12-25 16:40（接力入口：`DOC/agents/handoff_planner.md` / `DOC/agents/handoff_frontend.md`）
- **最近校对（北京时间 GMT+8）**：2025-12-25 17:30（接力入口：`DOC/agents/handoff_planner.md` / `DOC/agents/handoff_frontend.md`）
- **最近校对（北京时间 GMT+8）**：2025-12-26 10:20（接力入口：`DOC/agents/handoff_planner.md` / `DOC/agents/handoff_frontend.md`）
- **最近校对（北京时间 GMT+8）**：2025-12-30 12:30（接力入口：`DOC/agents/handoff_planner.md` / `DOC/agents/handoff_backend.md`）
- **最近校对（北京时间 GMT+8）**：2026-01-01 17:05（Planner：环境文件治理（真实 .env 不进 Git））
- **分支**：`backup/20251214-1535`

- **本轮闭环产物（Frontend / LineVariants - 替换物料选择器验收修复）**：
  - 产物：`LineVariantDrawer` 的“替换物料”选择器链路可用（打开→搜索→选择→回填），并修复缩进错位导致的构建失败；启用时补齐“单位缺失/不一致”红字提示（不改后端口径）。
  - 验收命令（必须）：`npm -C frontend run build`
  - 下一步（建议下一轮再做）：在选择器中支持“同单位优先/筛选”，进一步减少启用时才发现单位不一致的返工。

- **本轮闭环产物（Frontend / ProductModelEditorDrawer - 清单编辑“结构”列（MVP））**：
  - 入口：`清单编辑 → 版本选择` 已支持选择并保存 `结构标准`（sample/standard 均可；仅 draft 可改）。
  - 物料/工序明细表新增列：**结构**（slot）。
    - 模块同步行：默认只读展示（整结构/slots/或行上已有 `metadata_json.structure_slot`）。
    - 通用模块（GLOBAL）或手动新增行：可下拉选择当前结构标准的 slots，保存到 `metadata_json.structure_slot`。
  - 验收命令（必须）：`npm -C frontend run build`
  - 更新（北京时间 GMT+8 2026-01-04）：模块同步行也支持下拉选择结构 slots；同步完成后若模块范围唯一命中 1 个 slot，会自动回填 `metadata_json.structure_slot`（多 slot 保持空让人选）。
  - 更新（北京时间 GMT+8 2026-01-04）：打样模型（sample）也显示“结构标准”下拉并可保存；工艺模块候选也会按结构标准过滤。
  - 更新（北京时间 GMT+8 2026-01-04）：结构列交互收口为“点击编辑”：默认只读展示，不占用列宽；点击单元格才弹出下拉选择，避免把列表挤乱。
  - 更新（北京时间 GMT+8 2026-01-04）：结构 slot 展示口径收口：优先只显示中文名（不显示短码）；缺中文名时兜底显示短码。
  - 更新（北京时间 GMT+8 2026-01-04）：打样管理抽屉加宽 50px；并将左侧“工艺模块”栏固定为 330px，让新增宽度全部让给右侧清单区域（不挤乱模块区）。
  - 更新（北京时间 GMT+8 2026-01-04）：打样版本“生成标准模型”默认不再每次 `create_new` 新建标准草稿；若已存在 `standard draft`，则默认 `overwrite_draft` 覆盖最新草稿（并增加按钮 loading/防连点），避免出现多个标准草稿导致“两个打样版本都到标准模型里”的误解。
  - 下一步（建议下一轮再做）：后端在“从工艺同步”落库时直接回填每行 `structure_slot`（统一口径），并可选支持“模块按 slots 拆行”（若业务确认需要）。

- **本轮闭环产物（Frontend / VirtualMaterials - 添加真实物料卡顿与关闭后仍持续请求修复）**：
  - 现象：虚拟物料抽屉“添加物料（真实物料）”打开很慢；关闭抽屉后仍感觉卡顿持续。
  - 根因：物料查询与“补齐绑定物料信息”的循环请求不可取消（关闭弹窗/抽屉后仍在跑）。
  - 修复：
    - `fetchMaterials` 支持 `AbortSignal`；选择器查询与补齐循环接入 signal，关闭时会 abort in-flight 请求。
    - `VirtualMaterialsPage` 的补齐循环在 cleanup 中停止并 `abort()`，避免拖慢主线程/页面交互。
  - 关键文件：
    - `frontend/src/services/planner.ts`
    - `frontend/src/pages/costing/VirtualMaterialsPage.tsx`
    - `frontend/src/components/costing/MaterialPickerDrawer.tsx`
  - 验收命令（必须）：`npm -C frontend run build`

- **备注（重要口径：打样模型 / 标准模型“删除”互不误伤）**：
  - 两个入口是“管理视图”独立：打样侧与标准侧的版本可分别归档删除，但不会互相连坐。
  - “删除打样”（SampleModelsPage）：仅归档 `sample` 版本（`POST /product-models/{id}/archive-sample`），不影响 `standard` 版本。
  - “删除标准”（StandardModelsPage）：仅归档 `standard` 版本（`POST /product-models/{id}/archive-standard`），不影响 `sample` 版本。
  - 打样列表可见性口径：**只要模型存在 `sample` 版本就应显示**（即便 `entry_context=standard`），避免“删了标准后看起来打样也没了”（实际是列表过滤导致不可见）。
  - 说明：推导标准版本时会在标准版本 `metadata_json.derived_from_version_id` 记录来源打样版本，用于追溯；但删除/归档口径按入口隔离，确保“推导后可独立管理”。

- **更新（北京时间 GMT+8 2026-01-04）：变体规则“跨模型误触发”护栏（后端）**：
  - 背景：物料可跨品类复用（例如同一面料用于抱枕/桌布），若只用 `spec_text` token 匹配，存在跨模型误触发风险。
  - 修复口径：`parse_spec(spec_text)` 仍保持“只从交易规格提取 token”（用于审计/回放）；但在 `bom/generate` 进行变体匹配时注入运行时上下文 token（不要求出现在 spec_text）：
    - `MODEL:<model_code>`（三位码，如 `MODEL:PI5`）
    - `BOUND_VERSION:<version_id>`
    - `SKU:<sku_code>`
  - 备用能力：`spec/parse` 额外支持从交易规格中识别三位模型编码并输出为 `MODEL:<code>`（用于导入/排错/自动绑定候选，不依赖图案码 Qxxxxxx）。
  - 关键文件：
    - `backend/src/planner/services/bom_generation_service.py`
    - `backend/src/planner/services/spec_parser_service.py`
    - `backend/tests/planner/test_bom_runtime_tokens_guardrail.py`
    - `backend/tests/planner/test_spec_parser_code_tokens.py`

- **更新（北京时间 GMT+8 2026-01-04）：模型列表“都能看见”便于回收清理**：
  - 标准模型页/打样模型页：不再按 `entry_context/版本数` 过滤列表（避免“看不见就删不了/以为被删”）。
  - 两页新增开关：**显示已归档**（`GET /product-models?include_archived=true`），用于把历史误删/误归档的模型也拉出来核对。

 - **最近校对（北京时间 GMT+8）**：2026-01-04（Frontend：打样管理允许占位物料保存清单（汇总成本按 0），但推导标准/发布标准前硬拦截：存在占位则不允许推导/发布）
 - **最近校对（北京时间 GMT+8）**：2026-01-04（Backend：版本清单保存占位型虚拟物料校验按 version_kind 拆分：sample 允许临时保存，standard 继续禁止）
 - **最近校对（北京时间 GMT+8）**：2026-01-04（Frontend：保存清单后不再跳回旧版本：versionsQuery 刷新时保留当前 selectedVersionId，仅在首次/当前不存在时自动选版本）
 - **最近校对（北京时间 GMT+8）**：2026-01-04（Frontend：打样清单编辑增强：物料/工序行显示来源工艺模块标识（胶囊+更抗撞色），并新增“汇总视图”（只读合并，用于扫读，不影响编辑与保存））
 - **最近校对（北京时间 GMT+8）**：2026-01-04（Frontend：打样清单编辑字号按 A/B/C 调整：物料/工序表头与正文= A；物料组/工序组标题= B；工艺模块列表表头= A、名称= C）
 - **最近校对（北京时间 GMT+8）**：2026-01-04（Frontend：工艺模块卡片头部布局：将“保留调参”开关移动到“同步”按钮同一行）
 - **最近校对（北京时间 GMT+8）**：2026-01-04（Frontend：工艺模块列表行底色与右侧清单来源底色对齐：左侧模块行也使用同一模块色背景，便于一眼对应）
 - **最近校对（北京时间 GMT+8）**：2026-01-04（Frontend：工艺模块列表底色增强为单元格着色+左侧色条，确保与编码色一致可分辨；含占位型物料时汇总金额强制按0显示并提示）
 - **最近校对（北京时间 GMT+8）**：2026-01-04（Frontend：移除“含占位：合计按0”提示；统一用竖色条标识模块来源：左侧工艺模块列表去胶囊、物料/工序明细行前加竖色条（手动新增为白色））
 - **最近校对（北京时间 GMT+8）**：2026-01-04（Frontend：恢复右侧物料/工序“打散底色”（来源模块浅底、手动新增灰底），同时保留竖色条标识模块来源）
 - **最近校对（北京时间 GMT+8）**：2026-01-04（Frontend：修复“新建虚拟物料保存无响应→连点导致重复创建”的问题：保存按钮增加本地 in-flight 锁，覆盖生成编码阶段并禁用按钮）

- **本轮闭环产物（Planner / 下一轮：模型结构化落点派单）**：
  - 新增派单：`DOC/agents/briefings/backend_structure_tagging_and_filtering_mvp.md`
  - 目标：用 `metadata_json` 落 `structure_standard_code`（版本）与 `structure_tags[]`（工艺模块），并给列表接口加筛选参数，支持“按结构找模块/按结构找版本”
  - 验收命令（文档存在性）：`grep -nF "模型结构化落点（结构标准/工艺模块标签）+ 列表筛选 MVP" DOC/agents/briefings/backend_structure_tagging_and_filtering_mvp.md`

- **本轮闭环产物（Planner / 下一轮：标准版本结构标准选择 + 模块候选过滤派单）**：
  - 新增派单：`DOC/agents/briefings/frontend_standard_version_structure_code_and_module_filter_mvp.md`
  - 目标：标准版本保存 `metadata_json.structure_standard_code`；模型侧选工艺模块候选默认带 `structure_code=<该值>` 过滤
  - 验收命令（文档存在性）：`grep -nF "标准模型版本结构标准选择 + 按结构过滤模块候选（MVP）" DOC/agents/briefings/frontend_standard_version_structure_code_and_module_filter_mvp.md`

- **本轮闭环产物（Planner / 下一轮：结构标准字典页派单）**：
  - 新增派单：`DOC/agents/briefings/frontend_structure_standards_management_mvp.md`
  - 目标：结构标准作为主数据（像分类字典）：维护 `code/name/slots/status`，供模型/工艺模块引用，避免手填 code 漂移
  - 验收命令（文档存在性）：`grep -nF "结构标准管理（字典页）MVP" DOC/agents/briefings/frontend_structure_standards_management_mvp.md`

- **本轮闭环产物（Planner / 下一轮：工艺模块适用类型收口派单）**：
  - 新增派单：`DOC/agents/briefings/frontend_process_modules_applicability_mode_and_auto_tags_mvp.md`
  - 目标：在工艺模块抽屉新增“内用/组合/global”语义与 slot 选择，并自动生成/维护 `metadata_json.structure_tags[]`
  - 验收命令（文档存在性）：`grep -nF "工艺模块“适用类型（内用/组合/global）”+ 结构标签自动生成（MVP）" DOC/agents/briefings/frontend_process_modules_applicability_mode_and_auto_tags_mvp.md`

- **本轮闭环产物（Planner / 下一轮：防呆收口派单（结构标准/slot 下拉））**：
  - 新增派单：`DOC/agents/briefings/frontend_structure_selection_dropdowns_guardrails_mvp.md`
  - 目标：将“结构标准 code/slot(s)”从自由输入收口为下拉选择（来源结构标准字典），避免填错与 code 漂移
  - 验收命令（文档存在性）：`grep -nF "结构标准/slot 下拉收口（防呆）MVP" DOC/agents/briefings/frontend_structure_selection_dropdowns_guardrails_mvp.md`

- **本轮闭环产物（Planner / 下一轮：slot 双语展示派单（拼音短码+中文名））**：
  - 新增派单：`DOC/agents/briefings/frontend_structure_slots_bilingual_display_mvp.md`
  - 目标：slot 存“拼音短码”做稳定键（如 `lalian`），UI 显示中文名（如“拉链位”），结构标签不要求人工读懂
  - 验收命令（文档存在性）：`grep -nF "slot “拼音短码 + 中文名”双语展示（MVP）" DOC/agents/briefings/frontend_structure_slots_bilingual_display_mvp.md`

- **本轮闭环产物（Frontend / 结构标准字典页：删除（归档））**：
  - 位置：`/costing/structure-standards` 列表“操作”列新增“删除（归档）”
  - 防呆：必须先停用再删除；删除前二次确认
  - 底层：复用 taxonomy `DELETE /taxonomy/items/{id}`（需要管理员密钥）
  - 本轮验收命令（必须）：`npm -C frontend run build`

- **本轮闭环产物（Frontend / 结构标准 slots：列表式（中文+拼音短码） + 工艺 slot 下拉中文展示）**：
  - 结构标准编辑抽屉：slots 从 tags 输入改为“中文名 + 自动拼音短码”逐行编辑
  - 落库：`metadata.slots` 存短码数组（如 `["lalian"]`），`metadata.slot_display_names` 存短码→中文名（如 `{ "lalian": "拉链位" }`）
  - 工艺模块“结构适用范围”：slot/slots 下拉优先显示中文名（格式：`中文（短码）`），但结构标签预览/落库仍为短码 tag（如 `PILLOW_V1:lalian`）
  - 本轮验收命令（必须）：`npm -C frontend run build`

- **本轮闭环产物（Backend / 模型结构化落点（结构标准/工艺模块标签）+ 列表筛选 MVP）**：
  - 产品模型版本结构标准（写入/读取）：
    - 位置：`product_model_versions.metadata_json.structure_standard_code`
    - 列表筛选：`GET /api/planner/product-model-versions?structure_standard_code=...`
  - 工艺模块结构标签（写入/读取）：
    - 位置：`process_modules.metadata_json.structure_tags`（List[str]，默认空数组）
    - 支持两种字符串约定：
      - `<structure_standard_code>`
      - `<structure_standard_code>:<slot>`（slot 不解析，仅字符串筛选）
    - 列表筛选：
      - `GET /api/planner/process-modules?structure_tag=...`（精确匹配）
      - `GET /api/planner/process-modules?structure_code=...`（命中 `code` 与 `code:*`）
  - 数据库兼容：
    - Postgres：使用 JSONB 查询（避免全量拉取后 Python 过滤）
    - SQLite：测试环境 fallback 为 Python 过滤（保证口径一致）
  - 最小单测：`backend/tests/planner/test_structure_tag_filters_mvp.py`
  - 本轮验收命令（必须）：`python -m pytest backend/tests/planner/test_structure_tag_filters_mvp.py -q`
  - 最近校对（北京时间 GMT+8）：2026-01-03

- **本轮闭环产物（Planner / 环境文件治理：真实 .env 不进 Git）**：
  - 目的：避免“切分支/拉代码后文件看不见/误提交密钥”，同时保留可复现性
  - 规则：
    - 仓库只保留模板：`.env.sample`、`frontend/env.production.example`
    - 真实环境文件由机器自行提供：`.env`、`frontend/.env.production`（加入 `.gitignore`，从 Git 追踪移除但保留在磁盘）
  - 验收命令：
    - `git status --porcelain`（应无 .env/.env.production 被追踪的变更）

- **本轮闭环产物（Frontend / 接力恢复包 + 强制验收）**：
  - 更新接力包：`DOC/agents/handoff_frontend.md` 刷新“最近校对”时间戳（用于新 Frontend 接力入口）
  - 硬验收（全部 0 退出码）：
    - `cd frontend && npm ci`
    - `npm -C frontend run build`
    - Docs：按 `DOC/agents/commands.md` 的 4 条 `grep -nF ...` 校验文档存在性
    - Backend smoke：`curl -sS "http://127.0.0.1:8800/api/planner/product-model-versions?version_kind=standard&page=1&page_size=20" | python -m json.tool`
  - 下一步（Frontend 建议闭环）：
    - 按 `DOC/agents/state.md` 既有规划，在“停用/删除/改单位/改换算/改单价”等高风险操作前调用 `GET /api/planner/base-config/materials/{material_id}/references` 做影响范围提示与确认/拦截

- **本轮闭环产物（Frontend / Materials - MaterialReferencesPanel（真实物料详情：引用关系区块 MVP））**：
  - UI：`/costing/materials` 物料详情抽屉新增 Tab：**“关联引用”**，展示三类引用（均为 `count + 最近10条`）并提供跳转入口：
    - 虚拟物料绑定引用 → `/costing/virtual-materials`
    - 工艺模块引用 → `/costing/process-modules`
    - 模型版本清单引用 → `/costing/standard-models`
  - 性能收口：
    - 仅在用户切到“关联引用”Tab 时才触发请求（默认不会读库，避免每次进抽屉改价格都查一次）
    - 不在列表页做 N+1 预取
  - 交互收口：Tab 顺序调整为 **基础信息 / 成本参数 / 图片附件 / 关联引用**
  - Fail-open：请求失败或 `errors[]` 非空时，仅在引用区块提示“部分数据不可用”，不阻塞其它功能
  - 关键改动文件：
    - `frontend/src/services/planner.ts`（新增 `fetchMaterialReferences`）
    - `frontend/src/types/planner.ts`（新增 `MaterialReferencesResponse` 等类型）
    - `frontend/src/pages/costing/MaterialMasterPage.tsx`（新增“引用”Tab）
  - 本轮验收命令（必须）：`npm -C frontend run build`（已通过）

- **本轮闭环产物（Frontend / Materials - 列表缩略图卡顿修复（最小））**：
  - 现象：强刷后进入 `/costing/materials` 列表加载很慢，期间点击其它栏目不响应（需等缩略图渲染完）
  - 修复：列表缩略图从 AntD `Image`（带 preview）改为原生 `<img loading="lazy" decoding="async">`，仅用于扫读；大图预览仍在抽屉“图片附件”Tab（`PreviewGroup`）
  - Fail-open：缩略图加载失败不影响页面交互
  - 关键文件：`frontend/src/pages/costing/MaterialMasterPage.tsx`
  - 本轮验收命令（必须）：`npm -C frontend run build`（已通过）

- **本轮闭环产物（Frontend+Backend / SampleModels 缩略图性能：B 方案（后端聚合字段，前端去 N+1））**：
  - 背景：`/costing/sample-models` 列表原实现为每行 `fetchProductModelVersions(modelId)` 获取缩略图 → 50 行即 50 个请求（N+1），强刷后易卡顿/切换不灵
  - 后端：`GET /api/planner/product-models` 响应新增 `latest_sample_version_id`（优先选择有 `metadata_json.version_images` 的最新 sample 版本），供列表直接渲染缩略图
  - 前端：`SampleModelsPage` 移除每行版本请求；缩略图直接用 `latest_sample_version_id` 拼接 `/api/planner/product-model-versions/{id}/images/0`，并使用 `<img loading="lazy" decoding="async">` 降载
  - 文档：补回 `DOC/costing/reviews/erp_guardrails_addendum_20251222.md` 的 **§9 主数据不同频治理策略**，使 `DOC/agents/commands.md` 的 grep 验收命令可执行
  - 本轮验收命令（必须）：`npm -C frontend run build`（已通过）
  - 后端 smoke（示例）：`curl -sS "http://127.0.0.1:8800/api/planner/product-models?page=1&page_size=3" | python -m json.tool`

- **本轮闭环产物（Frontend / Materials - 关联引用：直达编辑 + 列宽收口）**：
  - 关联引用跳转：
    - 虚拟物料：点击“打开”→ 进入 `/costing/virtual-materials` 并直接打开对应虚拟物料抽屉
    - 工艺模块：点击“打开”→ 进入 `/costing/process-modules` 并直接打开对应工艺模块抽屉
    - 模型版本：点击“打开”→ 进入 `/costing/standard-models` 并直接打开对应标准模型版本抽屉
  - 表格列宽/展示收口：
    - 工艺模块引用：ID 列加宽、名称列变窄且字号更小
    - 模型版本清单引用：版本列加宽；模型/状态列变窄
    - 物料主列表：物料编码列加宽约 1/3
  - 本轮验收命令（必须）：`npm -C frontend run build`（已通过）

- **本轮闭环产物（Backend / BaseConfig - MaterialReferences（真实物料引用关系查询 MVP））**：
  - 新增接口：`GET /api/planner/base-config/materials/{material_id}/references`
  - 返回结构要点：
    - `material_id`
    - `virtual_materials.count/items`（最近 10 条，含 `id/virtual_code/name/virtual_kind/status`）
    - `process_modules.count/items`（最近 10 条，含 `id/name`）
    - `product_model_versions.count/items`（最近 10 条，含 `version_id/model_id/model_name/version_label/version_kind/version_status`）
    - `errors[]`：任一引用源查询失败时，接口仍返回 200，但该块返回空并记录错误（用于前端高风险操作前的影响评估）
  - 性能收口：仅返回“计数 + 最近 N 条”（N=10），不返回大 payload
  - 验收命令：
    - `curl -sS "http://127.0.0.1:8800/api/planner/base-config/materials/<material_id>/references" | python -m json.tool`
  - 下一步（前端）：
    - 在“停用/删除/改单位/改换算/改单价”等高风险操作前调用该接口，展示影响范围并做确认/拦截

- **本轮闭环产物（Backend / BaseConfig - MaterialReferences：过滤已归档/删除记录）**：
  - 背景：用户反馈“关联引用”列表会出现已删除（归档）的虚拟物料/工艺模块/模型版本清单项（例如 `version_status=archived` 的版本仍被展示）。
  - 修复：`GET /api/planner/base-config/materials/{material_id}/references` 在三类引用查询中额外过滤：
    - 虚拟物料：`virtual_materials.status != archived`
    - 工艺模块：`process_modules.status != archived`
    - 模型版本：`product_model_versions.version_status != archived`，并同时过滤已归档模型（`product_models.is_archived=false`）
  - 口径：`count` 与 `items` 使用同一过滤口径（避免“计数包含归档，但列表不包含/或相反”）。
  - 本轮验收命令（必须）：`npm -C frontend run build`（已通过）
  - 后端 smoke（可选）：按 `DOC/agents/commands.md` 执行 curl 示例（已通过）

- **本轮闭环产物（Frontend / Shipments - retry exceptions + bind CTA MVP）**：
  - 页面：`/costing/shipments`
  - 异常队列新增按钮：**“重试本批未解决异常”**
    - 调用：`POST /api/planner/shipments/exceptions/retry`
    - 行为：对当前 `batch_id` 的未解决异常逐条重试；成功后自动刷新异常列表，并刷新 BOM 快照缓存
  - 异常行新增 CTA：当 `reason=SKU_NOT_BOUND` 时展示 **“去绑定”**，跳转 `/costing/sku-master?search=<sku_code>`
  - 关键改动文件：
    - `frontend/src/pages/costing/ShipmentMonitorPage.tsx`
    - `frontend/src/services/planner.ts`
    - `frontend/src/types/planner.ts`
  - 本轮验收命令（必须）：`npm -C frontend run build`（已通过）

- **本轮闭环产物（Frontend / Shipments - 原子发布到 47.99.89.206）**：
  - 发布方式：仅发布前端静态资源（不改后端），使用 `frontend/scripts/deploy_static.sh` 原子切换到：
    - `PLANNER_STATIC_DIR=/var/www/html/ai-costing/dist`
  - 发布步骤（执行记录）：
    - `git pull --ff-only`（已 up-to-date，包含 `f35569e`/`feat(shipments): ...`）
    - `cd frontend && npm ci && npm run build`（已通过）
    - `PLANNER_STATIC_DIR=/var/www/html/ai-costing/dist ./scripts/deploy_static.sh`（已完成原子切换）
  - 线上验收命令（只给 1 条）：`curl -sS http://47.99.89.206/ | head -n 5`（已通过，返回 index.html）
  - 点验项（浏览器）：
    - `/costing/shipments` 可见“重试本批未解决异常”按钮
    - `SKU_NOT_BOUND` 行可见“去绑定”按钮，跳转 `/costing/sku-master?search=<sku_code>`
    - 控制台无 `Failed to load module script (MIME text/html)` 报错

- **本轮闭环产物（Frontend / ProcessModules - StructureFiltersAndTags MVP）**：
  - 列表筛选区新增：
    - 结构标准 code → query `structure_code`
    - 结构标签（如 `pillowcase_v1:zipper`）→ query `structure_tag`
  - 列表新增列：**结构标签**（读取 `metadata_json.structure_tags`，展示前 3 个 + `…+N`）
  - 编辑抽屉新增字段：**结构标签（Tags）**
    - 保存到 `metadata_json.structure_tags: string[]`（默认空数组，支持增删）
  - 关键改动文件（严格按 workset）：
    - `frontend/src/pages/costing/ProcessModulesPage.tsx`
    - `frontend/src/types/planner.ts`
    - `frontend/src/services/planner.ts`（仅透传 query params，无额外改动）
  - 本轮验收命令（必须）：`npm -C frontend run build`（已通过）

- **本轮闭环产物（Frontend / StandardModels - VersionStructureCode + ModuleFilter MVP）**：
  - 标准模型编辑抽屉（`ProductModelEditorDrawer`）：
    - 新增字段：**结构标准 code**（可空，自由输入）
    - 保存位置：`product_model_versions.metadata_json.structure_standard_code`
  - 模块候选过滤：
    - 打开“选择工艺模块”弹窗时，若当前标准版本存在 `structure_standard_code`，则候选请求自动带 `structure_code=<该值>`
    - 若为空：不加筛选（兼容历史模型）
  - 后端依赖（本轮补齐最小接口）：
    - 新增 `PATCH /api/planner/product-model-versions/{version_id}`：合并更新版本 `metadata_json`（用于保存结构标准 code）
  - 关键改动文件：
    - `frontend/src/components/costing/ProductModelEditorDrawer.tsx`
    - `frontend/src/services/planner.ts`
    - `frontend/src/types/planner.ts`
    - `backend/src/planner/routers/product_model_versions.py`
    - `backend/src/planner/schemas.py`
  - 本轮验收命令（必须）：`npm -C frontend run build`（已通过）

- **本轮闭环产物（Frontend / StructureStandards - management MVP）**：
  - 新增页面：`/costing/structure-standards`（结构标准：列表 + 抽屉）
  - 新增菜单：成本核算 → 结构标准
  - 列表能力：search(code/name)、状态筛选（全部/启用/停用）、slots 前 3 个 + `…+N`、编辑/启用停用
  - 抽屉能力：新增/编辑（编辑时锁定 code），slots 用 Tags 输入；最小校验（code 3~64，slots 去重）
  - 后端落点（专业折中）：当前后端未提供 `/structure-standards` 接口，MVP 复用 taxonomy：
    - domain=`structure_standard`
    - taxonomy.name 作为 code（唯一键）
    - taxonomy.metadata.display_name 作为 name，metadata.slots 作为 slots[]
  - 关键改动文件：
    - `frontend/src/pages/costing/StructureStandardsPage.tsx`
    - `frontend/src/App.tsx`
    - `frontend/src/components/layout/AppLayout.tsx`
    - `frontend/src/services/planner.ts`
    - `frontend/src/types/planner.ts`
  - 本轮验收命令（必须）：`npm -C frontend run build`（已通过）

- **本轮闭环产物（Frontend / ProcessModules - ApplicabilityMode + AutoTags MVP）**：
  - 编辑抽屉新增区块：**结构适用范围**
    - 结构标准 code（可选，自由输入）
    - 适用类型（三选一）：`slot_internal / assembly / global`
    - slots：`slot_internal` 仅保留 1 个；`assembly` 支持多选；`global` 不展示 slots
  - 自动生成并维护：
    - `metadata_json.structure_tags: string[]`（只读预览，保存时写入）
    - 可选辅助字段：`metadata_json.structure_standard_code / structure_applicability_mode / structure_slots`
  - 生成规则（MVP）：
    - slot_internal：`CODE:slot`
    - assembly：`CODE` + `CODE:slot...`
    - global：固定 `GLOBAL`
  - 关键改动文件：
    - `frontend/src/pages/costing/ProcessModulesPage.tsx`
  - 本轮验收命令（必须）：`npm -C frontend run build`（已通过）

- **本轮闭环产物（Frontend / Guardrails - 结构标准/slot 下拉收口 MVP）**：
  - 工艺模块编辑抽屉：
    - “结构标准 code”由输入框改为下拉选择（数据源：结构标准字典 taxonomy domain=`structure_standard`）
    - `slot_internal`：slot 单选下拉（选项=当前结构标准的 `slots[]`）
    - `assembly`：slots 多选下拉（选项=当前结构标准的 `slots[]`）
    - 未选结构标准时：slot/slots disabled，并提示“请先选择结构标准”
  - 标准模型版本编辑：
    - “结构标准 code”由输入框改为下拉选择（同一数据源），保存链路不变（仍 PATCH version.metadata_json）
  - 关键改动文件（严格按任务单范围）：
    - `frontend/src/pages/costing/ProcessModulesPage.tsx`
    - `frontend/src/components/costing/ProductModelEditorDrawer.tsx`
  - 本轮验收命令（必须）：`npm -C frontend run build`（已通过）

- **本轮闭环产物（Backend / 修复 Task Center 500：Postgres SSL）**：
  - 现象：前端 `GET /api/planner/task-center/recent?limit=5` 轮询报 500
  - 根因：环境链路对 Postgres SSL 协商支持不一致（可能出现 `no encryption` 或 `server does not support SSL`），需要用 `sslmode` 明确策略
  - 修复：
    - `backend/src/database.py`：Postgres URL 默认补齐 `sslmode=prefer`；若设置 `PLANNER_PG_SSLMODE` 则强制覆盖 URL 内 sslmode
    - `backend/src/planner/routers/jobs.py`：task-center 查询失败时 fail-open（避免角标轮询拖垮页面）
  - 当前阻塞（重要）：若 **Postgres 未续费/不可用**（或链路被替换成不支持 SSL 的实例），则依赖 DB 的页面接口仍会 500（例如 `/api/planner/processes`、`/api/planner/taxonomy/items`）；task-center 之所以能 200 是因为做了 fail-open。
  - 验收命令：
    - `curl -sS -D - "http://127.0.0.1:8800/api/planner/task-center/recent?limit=5" -o /tmp/task_center_recent.json && cat /tmp/task_center_recent.json`

- **本轮闭环产物（Planner-Optimization / 方案评审稿）**：
  - `DOC/costing/reviews/shipment_time_parse_review_phase0_phase1_20251222.md`（回答：SKU_NOT_BOUND 根因与治理、spec_hash+解析版本化、幂等与重试/重跑语义、UI按Excel展示）
  - 验收命令：`grep -nF "发货时再解析（spec_hash 缓存）+ SKU→已发布标准版本绑定：优化方案评审稿（Phase0/Phase1）" DOC/costing/reviews/shipment_time_parse_review_phase0_phase1_20251222.md`
  - 路线决策：先跑通“发货导入→SKU绑定→解析→BOM快照/异常→可重试/可重跑”，再扩展“模型套模型+自动编码”解决 30% 复杂产品
  - ERP口径补强清单：`DOC/costing/reviews/erp_guardrails_addendum_20251222.md`（版本为最小核算单元、重跑语义、编码定位、解析版本化、异常工作台、成本口径）
  - 验收命令：`grep -nF "ERP 口径补强清单（Guardrails Addendum）— 发货时再解析主链优先" DOC/costing/reviews/erp_guardrails_addendum_20251222.md`
  - VM策略：已在 ERP Guardrails 增补页 §8 固化（推荐混合模式：VM用于表达/复用，发货/扣库必须展开到真实物料并落快照；绑定变更不回写历史快照）
  - 主数据不同频策略：已在 ERP Guardrails 增补页 §9 固化（宜搭同步物料↔本地模型引用：唯一键/选择器防错/发布校验/健康检查/去重归并）

- **本轮闭环产物（Frontend / 行级变体收口：ERP 最稳第一步）**：
  - 标准入口（`entryContext="standard"`）“清单编辑”Tab：物料行新增 **“变体（Overlay）”** 按钮
  - 点击按钮打开 `LineVariantDrawer`：管理 version-scoped `line-variants`（不修改基准清单）
  - Drawer 内支持 `spec_text` 预演：`POST /api/planner/spec/parse`（tokens） + `POST /api/planner/bom/generate`（最终 BOM + trace）
  - **收口（最稳形态）**：
    - action **固定** `replace_self`（UI 隐藏其它动作）
    - items **限制 1→1**（只允许 1 行目标物料，禁止新增第 2 行）
    - **同单位校验**：目标单位与基准行单位不一致 → 禁止启用并提示（单位缺失提示先补齐主数据/先保存清单）
    - **启用门槛**：启用前必须预演成功，并在 UI 显示最近预演时间/结果摘要（配置变更会标记“预演已过期”）
    - **条件增强（已接入 UI）**：在 token 基础上，额外支持 `width_between/height_between/area_between/perimeter_between`（可选）。若配置了这些条件，启用前要求预演样例能解析出对应数值（避免没测过就启用）。
    - **数量/个数条件（缺口）**：后端 `LineVariantCondition` 暂无 `quantity_between` 等字段；如业务必须支持“个数”，需要下一轮后端补字段或通过 token 离散化临时承载。

- **本轮闭环产物（Frontend / 打样管理：清单编辑 UI 修复）**：
  - 位置：`/costing/sample-models` → 打开抽屉 → `清单编辑`
  - 修复点：
    - 工序组“计量方式”右侧圆感叹号 tooltip：文本改为白色（深色 tooltip 背景可读）
    - 新增物料/新增工序：手动新增的行统一灰底（不再使用彩色模块背景）
    - 工序组列收口：将“替换”列更名为“操作”，并把 `α`（调参面板）按钮移入“操作”列与“替换”合并（宽度与物料组操作列一致）
    - 避免“打开抽屉/切版本”时尺寸联动重算覆盖已保存的本品用量/用时：仅当用户实际修改尺寸输入框时才触发联动重算
  - 关键文件：`frontend/src/components/costing/ProductModelEditorDrawer.tsx`
  - 本轮验收命令：`npm -C frontend run build`（已通过）

- **本轮闭环产物（Standard Models / 标准版本 → 克隆为新标准模型）**：
  - 需求：在“标准模型管理 → 标准版本”中，从某个标准版本生成一个**全新的标准模型**（新编码 + 新版本号），用于大量相似型号的快速复用
  - 前端：
    - 标准版本列表：将“复制”更名为“复制版”，并新增按钮“克隆模型”
    - 点击“克隆模型”：调用后端 `POST /api/planner/product-model-versions/{version_id}/clone-model`，成功后跳转到 `/costing/standard-models` 自动打开新模型抽屉并定位新标准版本
  - 后端：
    - 新接口：`POST /api/planner/product-model-versions/{version_id}/clone-model`
    - 行为：从源 standard version 克隆出新 ProductModel（model_code 自动生成）+ 新 standard draft version（version_label 自动生成）+ 复制版本清单；可选复制 line-variants（overlay）并按行序映射 base_line_id
  - 关键文件：
    - `backend/src/planner/routers/product_model_versions.py`
    - `backend/src/planner/schemas.py`
    - `frontend/src/components/costing/ProductModelEditorDrawer.tsx`
    - `frontend/src/services/planner.ts`
    - `frontend/src/types/planner.ts`
  - 验收命令：
    - Backend：`./backend/venv/bin/python -m pytest backend/tests/planner/test_clone_model_from_standard_version.py -q`
    - Frontend：`npm -C frontend run build`

- **重要修复（Backend / 使 between 条件可落库）**：
  - 修复 `line-variants` 在写入 JSON 列时 `Decimal`/`tuple` 不可序列化导致 500：将 `conditions/metadata` 递归转为 JSON-safe（Decimal→字符串、tuple→list）。
  - 补齐缺失模块以恢复 `planner-costing.service` 可重启（恢复 `codes/processes/process_modules/product_models/product_model_versions` 路由与相关 service/utils）。

- **关键实现文件**：
  - `frontend/src/components/costing/ProductModelEditorDrawer.tsx`
  - `frontend/src/components/costing/LineVariantDrawer.tsx`
  - `frontend/src/services/planner.ts`
  - `frontend/src/types/planner.ts`
  - `frontend/src/pages/costing/ShipmentMonitorPage.tsx`
  - `frontend/src/pages/costing/SkuMasterWorkspacePage.tsx`
  - `frontend/src/pages/costing/ProcessModulesPage.tsx`
  - `backend/src/planner/routers/shipments.py`
  - `backend/src/planner/services/shipment_import_service.py`
  - `backend/src/planner/schemas.py`

- **本轮闭环产物（BOM 成本展示 + 工序明细 + 历史快照回填）**：
  - 动态 BOM 成本口径：
    - `POST /api/planner/bom/generate` 返回每条物料行 `bom_unit_price/line_cost`
    - `trace.costing` 返回 `material_cost_total/process_cost_total/overhead_cost(默认30%)/total_cost/unit_cost`
    - 并补充 `trace.costing.process_lines`（工序明细，含计价参数/行成本/警告）
  - 发货监控页（`/costing/shipments`）抽屉重构：
    - 解析队列 BOM 预览抽屉、BOM 快照详情抽屉统一为 Tabs：汇总 / 物料 / 工序 / Trace
  - 新增“历史快照回填”：
    - 后端：`POST /api/planner/shipments/bom-snapshots/{snapshot_id}/recompute`
    - 前端：BOM 快照列表新增“回填”按钮（回填后刷新并打开详情）

- **盘点/扣库模式确认（待后续实现）**：
  - 当前业务走“发货触发标准回冲（Backflush）按 BOM 标准比例扣真实物料”，月底盘点对真实物料做差异调整；虚拟物料不作为盘点库存对象。

- **本轮补充（扣库清单：虚拟物料→真实物料展开）**：
  - 背景：BOM 快照/预览的“物料”表可能主要是虚拟物料（VM），但库存扣减必须落在真实物料（Material）。
  - 实现：`POST /api/planner/bom/generate` 的 `trace.inventory.inventory_lines` 返回“真实物料扣库清单”（把 virtual 行按 `virtual_material_bindings` 展开并聚合）。
  - 前端：`/costing/shipments` 的 BOM 预览抽屉 / 快照详情抽屉新增 Tab：**扣库清单（真实物料）**，用于对账与后续扣库/盘点闭环。
  - 提示：历史快照若缺失该字段，可用“回填”重算后补齐。

- **下一阶段（真实数据实测 + UI 整理规划）**：
  - 线上直接跑：`47.99.89.206`
  - 首批真实文件：由业务侧上传（平台商品列表 / 发货单）
  - 目标覆盖：约 200 行
  - 成本口径阶段性固定：物料 + 工序 + 制造费 30%
  - 验收清单（可勾选）：`DOC/costing/manuals/real_data_uat_checklist_20251225.md`

- **本轮补充（确定性工艺余量：扎口/封边等固定长度）**：
  - 背景：宽度不固定，但扎口固定（例如两边各 +10cm），属于“确定性尺寸修正”，不应使用损耗%硬凑。
  - 后端：BOM 计算支持物料行 `metadata_json.extra_width_mm/extra_height_mm`（单位mm），计量时使用 `(width_mm+extra_width_mm, height_mm+extra_height_mm)`。
  - 前端：标准模型清单物料行增加列 **工艺余量(mm)**（+宽 / +高），录入后会联动重算本品用量/标准用量。

- **本轮补充（计量方式扩展：长边/短边，单位=米）**：
  - 背景：编织袋/包装类材料存在“宽度不固定，但用料沿长边/短边卷”的口径；仅靠 width/height 无法表达“取最长边/最短边”。
  - 后端：`_measure_qty` 新增 `long_side/short_side`（分别取 `max(width,height)` / `min(width,height)`，并乘以数量）。
  - 前端：
    - 物料详情（`/costing/materials`）“计算方式”支持 **长边/短边**，并校验其 BOM 单位只能为“米”。
    - 模型清单“计量方式”下拉补充 **长边/短边**（仅单位=米时允许选择）。

- **本轮验收命令（必须）**：
  - Frontend：`npm -C frontend run build`
  - Backend（快速 smoke）：`curl -sS "http://127.0.0.1:8800/api/planner/shipments/bom-snapshots?limit=1" | python -m json.tool`
  - Backfill API（示例）：`curl -sS -X POST "http://127.0.0.1:8800/api/planner/shipments/bom-snapshots/<snapshot_id>/recompute" -H "Content-Type: application/json" -d '{"operator_id":"planner_user"}' | python -m json.tool`

- **本轮补充（Frontend / 模型清单：替换物料自动回填口径统一）**：
  - 问题：替换物料后，`unit_of_measure` / `metadata_json.bom_unit` / `calculation_method` / `bom_unit_price` 未同步更新，导致“计量方式与 BOM 单位不配套”、且表现为“所有行看起来都像同一种计量方式”。
  - 修复：
    - `ProductModelEditorDrawer` 在“替换物料”时强制同步回填：`unit_of_measure`、`metadata_json.bom_unit`、`calculation_method`，并尽量从主数据/换算推导 `bom_unit_price`。
    - `ProcessModulesPage` 在替换物料时不再沿用旧 `calculation_method`，改为以新物料主数据为准（避免回归）。
    - **补充（虚拟物料）**：替换虚拟物料时同样回填 `metadata_json.bom_unit_price`（优先用虚拟物料详情的 `bom_unit_price`；为空时按 bindings×真实物料 BOM 单价汇总推导），避免出现“VM00023 → VM00022 但 BOM 单价/单位不更新”。
  - 防回归：在关键函数旁加了“单位口径/计量方式必须匹配 normalizeUnit”的硬备注（禁止改回 `㎡/m` 作为 value）。
  - 本轮验收命令：`npm -C frontend run build`（已通过）

- **本轮补充（Materials / 宜搭同步分模式 + 前端按钮拆分）**：
  - 背景：物料页原“同步宜搭”属于全量 upsert，用户需要更安全/更快的同步方式（只拉新、只更新价格关键字段）。
  - 后端：`POST /api/planner/base-config/materials/sync-yida` 新增 `mode`：
    - `full`：全量同步（默认，raw_form_data 全量覆盖）
    - `new_only`：仅新增新物料（已存在的不更新）
    - `core_fields`：仅更新关键字段（入库单价/单位、采购单价/单位、采购→入库换算、采购规格），并且 raw_form_data 只 merge 对应字段
  - 前端：`/costing/materials` 顶部按钮拆分为 **同步新物料 / 更新原价格 / 全量同步宜搭**（均会打开同步日志抽屉便于跟踪）
  - 新增“推导BOM价格”：
    - 入口：`/costing/materials` 刷新按钮右侧
    - 后端接口：`POST /api/planner/base-config/materials/derive-bom-prices`（后台任务，写入 `metadata_json.bom_unit_price`）
    - 推导口径：\(BOM单价 = 入库单价 \div 入库→BOM换算\)，用于算价/扣库；无法推导时列表以红字提示原因
    - 自动化：三种宜搭同步任务完成后会自动触发一次 BOM 价格推导
  - 本轮验收命令：`npm -C frontend run build`（已通过）；Backend smoke：用 curl 触发 `mode=new_only/core_fields` 与 `derive-bom-prices` 均可成功落库

- **已确认正确版本快照（请勿覆盖）**：
  - `DOC/index/extracted/ProductModelEditorDrawer_confirmed_20251221T042643Z.tsx`
  - 校验和：`DOC/index/extracted/ProductModelEditorDrawer_confirmed_20251221T042643Z.sha256`

- **本轮验收命令（必须）**：`npm -C frontend run build`（已通过）

---

- **本轮闭环产物（Virtual Materials / 虚拟物料列表&抽屉体验 + 分类治理）**：
  - 前端：`/costing/virtual-materials`
    - 列表默认展示“子物料逐行明细”（编码/名称/配比或每套数量/损耗率）
    - 操作列对齐工序管理：图标化按钮（启用/停用/删除归档等，带安全约束与二次确认）
    - 筛选增强：类型（占位/配方/套件）+ 绑定物料搜索（按子物料编码/名称）
    - 分类来源：虚拟物料分类使用 taxonomy `virtual_material_category`
    - “同步数据”增强：同步后提示哪些子物料 BOM 单价缺失/为 0，避免误判“没更新”
  - 后端：
    - `GET /api/planner/base-config/virtual-materials` 新增筛选参数：
      - `virtual_kind`（占位/配方/套件）
      - `binding_search`（按绑定子物料编码/名称过滤）
  - 关键文件：
    - `frontend/src/pages/costing/VirtualMaterialsPage.tsx`
    - `frontend/src/types/planner.ts`
    - `backend/src/planner/routers/base_config.py`
  - 本轮验收命令：
    - `npm -C frontend run build`
    - `python -m compileall backend/src/planner/routers/base_config.py`
  - 最近校对（北京时间 GMT+8）：2025-12-28

---

- **本轮闭环产物（Pickers / 统一“添加物料/添加工序”弹窗体验）**：
  - 目标：统一虚拟物料/工艺模块的“添加物料/选择工序”弹窗交互，减少各页各造一套导致的不一致与学习成本。
  - 前端：
    - `frontend/src/components/costing/MaterialPickerDrawer.tsx`：统一物料选择器 Drawer
      - 顶部 Tabs：真实物料 / 虚拟物料
      - 真实物料筛选区：关键词 + 分类（taxonomy `material_category`）+ **默认勾选“仅 BOM 物料”**
      - 虚拟物料筛选区：关键词 + 分类（taxonomy `virtual_material_category`）
    - `frontend/src/pages/costing/ProcessModulesPage.tsx`：
      - 物料选择入口不再走“二级选择（真实/BOM/虚拟）”，统一打开 `MaterialPickerDrawer`
      - 选择工序弹窗新增“分类”筛选（taxonomy `process_category`）
  - 后端：
    - `GET /api/planner/processes/references` 支持 `category` 过滤（与主列表一致），用于前端工序选择器。
  - 本轮验收命令：
    - `npm -C frontend run build`
    - `python -m compileall backend/src/planner/routers/processes.py`
  - 最近校对（北京时间 GMT+8）：2025-12-28

- **本轮闭环产物（Frontend / 工艺模块列表页：对齐“工序管理”两行风格 + 操作图标化）**：
  - 目标：让“工艺模块”列表可扫读（两行信息密度）并与“工序管理”视觉一致。
  - 变更点：
    - 列表列改造（`ProcessModulesPage`）：
      - “工艺模块”列：第一行名称（加粗）；第二行显示 `分类/版本/引用次数` + 胶囊标签（最多 3 个，超出显示 +N）
      - “描述”列：两行省略（ellipsis rows=2 + tooltip）
      - “操作”列：图标按钮（带边框 + Tooltip）→ 查看/编辑/AI/复制/启用/停用
  - 关键文件：
    - `frontend/src/pages/costing/ProcessModulesPage.tsx`
    - `frontend/src/guides/table_list_style_two_line_cells.md`
  - 本轮验收命令：
    - `npm -C frontend run build`
    - `grep -nF \"title: '描述'\" frontend/src/pages/costing/ProcessModulesPage.tsx`
  - 最近校对（北京时间 GMT+8）：2025-12-27 18:10

- **本轮闭环产物（Frontend / Chrome“页面无响应”卡死：任务角标轮询降载）**：
  - 现象：页面内交互（悬停 Tooltip/点击）都卡住，Chrome 弹“页面无响应”。这通常是前端主线程被长任务占满。
  - 根因假设（高概率）：`AppLayout` 顶部任务角标在后台轮询 `task-center`，返回 payload/result 可能很大；有运行中任务时频率更高，导致频繁 JSON 解析与 React 更新，拖死主线程。
  - 修复（最小）：`frontend/src/components/layout/AppLayout.tsx`
    - 探针请求 `limit` 从 30 降到 5
    - `select` 将缓存数据压缩为 `{statuses, runningCount}`（不保留大 payload）
    - 页面不可见时停止轮询（`document.visibilityState==='hidden'`）
    - 轮询频率降低：运行中 5s / 空闲 15s；并关闭 `refetchOnWindowFocus`
  - 本轮验收命令：
    - `npm -C frontend run build`
    - `grep -nF \"任务角标探针（性能敏感）\" frontend/src/components/layout/AppLayout.tsx`
  - 最近校对（北京时间 GMT+8）：2025-12-27 18:25

- **本轮闭环产物（Ops-ish / 彻底解决：静态资源原子发布，避免 chunk 404→HTML 回退导致白屏/卡死）**：
  - 现象：前端报 `Failed to load module script (MIME text/html)` / `Failed to fetch dynamically imported module`，页面随即白屏或“点不了/无响应”。
  - 根因：静态资源发布非原子 +（或）Nginx 对 `/assets/*` 发生错误回退，导致 chunk 丢失却返回 HTML。
  - 修复：
    - `frontend/scripts/deploy_static.sh` 改为**原子发布**：同步到临时目录 → 一次性 `mv` 切换，避免线上半发布状态。
    - `DOC/agents/known_issues.md` 补充“Failed to load module script（MIME text/html）”的根因与 Nginx 必要配置。
  - 本轮验收命令：
    - `npm -C frontend run build`
    - `bash -n frontend/scripts/deploy_static.sh`
    - `grep -nF \"原子发布\" frontend/scripts/deploy_static.sh`
  - 下一步（需要有权限的人做）：按 `DOC/agents/known_issues.md` 调整 Nginx 的 `/assets` try_files 与缓存头。
  - 最近校对（北京时间 GMT+8）：2025-12-27 18:40

- **本轮闭环产物（Frontend / RESULT_CODE_HUNG：移除 render 内自动纠偏导致的渲染循环）**：
  - 现象：Chrome 报 `RESULT_CODE_HUNG`，页面鼠标悬停/点击都卡住。
  - 根因假设（高概率）：在表格单元格 `render` 过程中触发 `queueMicrotask()+setFieldValue/setState`，导致渲染-微任务-渲染循环，最终主线程被占满。
  - 修复（最小）：
    - `frontend/src/pages/costing/ProcessModulesPage.tsx`：移除 render 内 `queueMicrotask()+form.setFieldValue` 的自动纠偏；改为保存时规范化 `calculation_method/measure_unit`。
    - `frontend/src/components/costing/ProductModelEditorDrawer.tsx`：移除 render 内 `queueMicrotask()+setMaterials` 的自动纠偏；保存清单前统一规范化非法 `calculation_method` 并重算用量。
  - 本轮验收命令：
    - `npm -C frontend run build`
  - 最近校对（北京时间 GMT+8）：2025-12-27 19:05

- **本轮闭环产物（Process Modules / 列表删除（归档））**：
  - 需求：工艺模块列表增加“删除”功能（归档删除），与工序管理一致。
  - 后端：
    - 新增：`DELETE /api/planner/process-modules/{module_id}`（204）
    - 口径：启用中不可删；若仍被模型引用（`model_process_modules`）则阻止删除并提示引用数。
  - 前端：
    - `ProcessModulesPage` 操作列新增“删除”图标按钮（仅非 active 显示，带二次确认）
    - `frontend/src/services/planner.ts` 新增 `deleteProcessModule()`
  - 验收命令：
    - `npm -C frontend run build`
    - `grep -n \"@router.delete\" backend/src/planner/routers/process_modules.py`
  - 最近校对（北京时间 GMT+8）：2025-12-27 19:25

- **本轮闭环产物（Processes / 列表删除按钮可见性增强）**：
  - 反馈：工序管理列表“删除功能看不到”。
  - 说明：后端删除口径要求先停用（active 不允许删除）。
  - 前端改造：`frontend/src/pages/costing/ProcessesPage.tsx`
    - 删除按钮**始终显示**；当工序为 active 时，“删除”按钮置灰并提示“需先停用”。
  - 验收命令：
    - `npm -C frontend run build`
  - 最近校对（北京时间 GMT+8）：2025-12-27 19:45

- **本轮闭环产物（Standard Models / “直接新建标准（高级）”误报失败修复）**：
  - 现象：点击“直接新建标准（高级）”创建成功（模型已生成），但 UI 仍提示“新建标准模型失败”。
  - 根因：创建成功后，后续步骤（取 `current_draft_version_id` / 列表 refetch）任一异常会被 catch，当成创建失败误报。
  - 修复：`frontend/src/pages/costing/StandardModelsPage.tsx`
    - `current_draft_version_id` 读取兼容 `metadata_json` / `metadata`
    - 若未返回 draft id：兜底 `fetchProductModelVersions(model.id)` 自动选取 standard draft
    - 列表 `refetch` 失败不再覆盖“创建成功”反馈（改为忽略）
  - 验收命令：
    - `npm -C frontend run build`
  - 最近校对（北京时间 GMT+8）：2025-12-27 20:05

- **本轮闭环产物（Frontend / 工艺模块 AI 语义抽屉重构：自动汇总为主、步骤级补丁、手工不覆盖）**：
  - 目标：让员工看懂“这个工艺模块怎么做”，并让模块级 AI 字段主要来自工序库 ai_spec 自动汇总，避免重复手填。
  - 变更点：
    - `AI 语义（工艺模块）` 抽屉新增按钮：
      - “从工序自动汇总（只填空）”：按模块已选工序拉取工序库 `metadata_json.ai_spec`，汇总到模块级字段，仅填空。
      - “从工序自动汇总（覆盖）”：覆盖未锁定字段（不会覆盖手工锁定字段）。
    - 新增手工锁定：保存时把人工编辑过的字段写入 `metadata_json.ai_spec._manual_overrides`，后续汇总默认不覆盖。
    - 步骤级区块增加解释文案，并把按钮文案改为“引用工序AI→步骤”（步骤级用于少量差异化补丁）。
  - 关键文件：
    - `frontend/src/components/costing/ProcessModuleAIDrawer.tsx`
    - `frontend/src/pages/costing/ProcessModulesPage.tsx`
  - 本轮验收命令：
    - `npm -C frontend run build`
    - `grep -nF "从工序自动汇总（只填空）" frontend/src/components/costing/ProcessModuleAIDrawer.tsx`
  - 下一步（可选，不在本轮范围）：对“AI生成写入 narrative_long”加“手工锁定字段覆盖确认”提示（尊重 `_manual_overrides.narrative_long`）。
  - 最近校对（北京时间 GMT+8）：2025-12-27 17:30

- **本轮闭环产物（Frontend / 只读：发货批次列表 + 异常队列 + BOM 快照查询）**：
  - 新增页面：`/costing/shipments`（只读）
  - 页面顶部新增：上传发货单（xlsx 导入）→ 调用 `POST /api/planner/shipments/import`，导入成功后自动选中 batch 并刷新列表/异常/快照
  - 页面包含 3 块：
    - 发货批次列表（分页，点击行设置当前 batch_id）
    - 异常队列（支持 batch_id/解决状态/limit 过滤）
    - BOM 快照查询（支持 batch_id/SKU/发货单号/spec_hash/limit 过滤，支持抽屉查看 trace + 最终 BOM 行摘要）
  - 依赖接口（后端已补齐最小查询能力）：
    - `GET /api/planner/shipments/import-batches?page=1&page_size=20`
    - `GET /api/planner/shipments/exceptions?batch_id=...&resolved=...&limit=...`
    - `GET /api/planner/shipments/bom-snapshots?batch_id=...&sku_code=...&shipment_no=...&spec_hash=...&limit=...`
  - 本轮验收命令（补充）：
    - Docs：`grep -nF "## 标准模型：行级变体（Overlay）运营/实施规范（v0.1）" DOC/costing/manuals/standard_model_variants_ops_rules.md`
    - Backend smoke：`curl -sS "http://127.0.0.1:8800/api/planner/product-model-versions?version_kind=standard&page=1&page_size=1" | python -m json.tool`

- **本轮补充（Frontend / 替换物料选择器 MVP）**：
  - 位置：`LineVariantDrawer` 编辑弹窗的“替换物料”列
  - 行为：不再手输 `material_ref_id`；改为 **打开选择器 → 搜索（编码/名称）→ 选择**
  - 选择后回填：`material_ref_id + material_code/material_name/unit_of_measure`（用于可读展示 + 同单位校验）
  - 组件：新增 `frontend/src/components/costing/MaterialSelectModal.tsx`（复用 `/base-config/materials` 搜索接口，默认仅 BOM 物料）
- **本轮补充（Frontend / 变体规则录入体验收口）**：
  - `LineVariantDrawer` 的“编辑”弹窗改为 **多条规则表格**（同一触发类型下批量维护）：列为 启动/条件表达式/替换物料/β/α/覆盖率/损耗% + 新增/删除
  - 启用拦截：未预演成功或预演已过期时，不允许打开“启动”（前端直接提示）
  - 说明：当前版本仍按“同一触发类型”批量维护；若未来要允许每行触发类型不同，需要单独迭代 UI/保存/门槛（本轮暂停）

- **本轮补充（Backend / 缩略图恢复）**：
  - 恢复图片代理接口：`GET /api/planner/base-config/materials/{id}/images/{idx}`
  - 行为：优先读取 `metadata_json.local_images` 的本地文件；若缺失则从钉钉下载并落盘到 `PLANNER_MEDIA_DIR`，并回写 `metadata_json.local_images`
  - 纠偏：钉钉 `temporaryUrls` 在当前环境为 **GET** 且 `appType` 在路径里（非 POST）
  - 本地媒体目录默认：`backend/media`（已加入 `.gitignore`，避免误提交）

- **本轮补充（Backend / 行级变体 replace_self 用量兜底）**：
  - 修复历史规则“替换物料 β=0/计量方式默认 count”导致 `variant_item computed_quantity=0`
  - `bom/generate` 在 `replace_self` 下：若替换行未正确填写，则 **继承基准行的计量方式/β/单位**（避免用户必须重录旧规则）

- **下一步（不在本轮范围）**：
  - 若要允许“每行不同触发类型（token/宽/高/面积/周长混合）”并保持启用门槛正确：需要把触发类型下放到每行，并按行计算维度缺失/单位回填/预演样例覆盖
  - 如需更易用的物料选择（从物料/虚拟物料列表挑选并回填 material_ref_id），再开下一轮单独闭环。

- **下一步闭环任务单（运维/上线）**：`DOC/agents/briefings/ops_deploy_line_variants_to_4799.md`
- **验收命令（派单文件存在）**：`grep -nF "# Ops/Backend Ops 闭环任务单：部署“行级变体（overlay）”到 47.99.89.206" DOC/agents/briefings/ops_deploy_line_variants_to_4799.md`
- **下一步闭环任务单（运维/上线：发货单导入→BOM快照）**：`DOC/agents/briefings/ops_deploy_shipment_import_bom_snapshots_to_4799.md`
- **验收命令（派单文件存在）**：`grep -nF "# Ops/Backend Ops 闭环任务单：部署“发货单导入→spec_cache→BOM快照”到 47.99.89.206（MVP）" DOC/agents/briefings/ops_deploy_shipment_import_bom_snapshots_to_4799.md`
- **下一步闭环任务单（运维/上线：前端发货单上传入口）**：`DOC/agents/briefings/ops_deploy_frontend_shipments_upload_to_4799.md`
- **验收命令（派单文件存在）**：`grep -nF "# Ops 闭环任务单：部署前端“发货单上传导入入口”到 47.99.89.206（/costing/shipments）" DOC/agents/briefings/ops_deploy_frontend_shipments_upload_to_4799.md`
- **最新部署（2025-12-23 10:10 CST）**：
  - `47.99.89.206` 已执行 `git pull --ff-only`、`alembic upgrade heads`（存在 `0016_line_variants_mvp` 与 `0754ad7d6c3f` 双 head，采用 `heads` 选项同步）
  - `systemctl --user restart planner-costing.service`（需要 `export XDG_RUNTIME_DIR=/run/user/$(id -u)`）后，`curl http://127.0.0.1:8800/api/planner/health` 返回 `{"status":"ok"}`
  - OpenAPI 校验：`/api/planner/shipments/import` / `/api/planner/shipments/exceptions` / `/api/planner/shipments/bom-snapshots` → `True`
  - 目标机验收：`pytest backend/tests/planner/test_shipment_import_bom_snapshots_mvp.py -q` → `1 passed`
  - **本轮新增上线（SKU 主档工作台）**：
    - 后端：`alembic upgrade heads` 已运行 `0017 -> 0018_sku_master_import_mvp`，并重启 `planner-costing.service`
    - OpenAPI 校验：`/api/planner/sku-master` 与 `/api/planner/sku-master/import` → `True`
    - API 校验：`GET http://127.0.0.1:8800/api/planner/sku-master?page=1&page_size=10` → 200（`total=0, items=[]`）
    - 前端：静态资源已发布至 `/var/www/html/ai-costing/dist`

- **本轮闭环产物（Docs / 运营规范）**：`DOC/costing/manuals/standard_model_variants_ops_rules.md`（行级变体：token/尺寸边界/预演留痕/变更控制/扣库口径）
- **本轮验收命令（Docs）**：`grep -nF "## 标准模型：行级变体（Overlay）运营/实施规范（v0.1）" DOC/costing/manuals/standard_model_variants_ops_rules.md`

- **接力准备（新 Frontend Agent）**：已刷新 `DOC/agents/handoff_frontend.md`，补齐行级变体 Overlay（`LineVariantDrawer`）与运营规范口径入口。

- **提炼件（禁止直读导出全文）**：`DOC/index/extracted/variants_discussion_extracted_20251221T200250+0800.md`（变体收口：同单位 1→1 平替、规则上限、启用门槛等）
- **本轮验收命令（提炼件）**：`grep -nF "# 提炼：变体收口讨论（从 Cursor 导出记录提炼）" DOC/index/extracted/variants_discussion_extracted_20251221T200250+0800.md`

- **下一步闭环任务单（前端 UX 细化）**：`DOC/agents/briefings/frontend_line_variants_material_picker_mvp.md`（替换物料选择器：替代手输ID）
- **验收命令（派单文件存在）**：`grep -nF "# Frontend 闭环任务单：行级变体“替换物料”不再手输ID（选择器 + 自动回填 + 同单位校验）" DOC/agents/briefings/frontend_line_variants_material_picker_mvp.md`

- **下一步闭环任务单（SKU→库存扣料清单）**：`DOC/agents/briefings/backend_sku_binding_inventory_mvp.md`
- **验收命令（派单文件存在）**：`grep -nF "# Backend 闭环任务单：SKU 绑定 + 规格解析尺寸/条件 + 生成库存扣料清单（BOM 快照）MVP" DOC/agents/briefings/backend_sku_binding_inventory_mvp.md`
- **下一步闭环任务单（发货单导入→BOM快照）**：`DOC/agents/briefings/backend_shipment_import_bom_snapshots_mvp.md`
- **验收命令（派单文件存在）**：`grep -nF "# Backend 闭环任务单：发货单 Excel 导入 → spec_hash 缓存解析 → BOM 快照生成 + 异常队列（MVP）" DOC/agents/briefings/backend_shipment_import_bom_snapshots_mvp.md`
 - **下一步闭环任务单（SKU 主档导入/回写）**：`DOC/agents/briefings/backend_sku_master_import_and_autobind_mvp.md`
 - **验收命令（派单文件存在）**：`grep -nF "# Backend 闭环任务单：SKU 主档导入（ERP 平台商品列表）+ 发货导入自动回写（MVP）" DOC/agents/briefings/backend_sku_master_import_and_autobind_mvp.md`
 - **下一步闭环任务单（前端 SKU 主档工作台）**：`DOC/agents/briefings/frontend_sku_master_workspace_mvp.md`
 - **验收命令（派单文件存在）**：`grep -nF "# Frontend 闭环任务单：SKU 主档工作台（导入/查询/命中率）MVP" DOC/agents/briefings/frontend_sku_master_workspace_mvp.md`

- **补充迭代（已完成）：SKU 主档“预解析缓存 + 规格差异标记”**：
  - 目标：在 SKU 主档中前置沉淀 `spec_hash/解析版本/尺寸/tokens/model_code_hint`，并在发货触发时记录“ERP规格 vs 最近发货规格”差异，避免重复解析、便于前端复核。
  - 前端展示：`/costing/sku-master` 列表显示 **对接状态 + 规格差异**，详情抽屉显示 `model_code_hint / erp_spec_hash / last_shipment_spec_text/hash / erp_dimensions/tokens`。
  - 后端实现：导入/回写时写入 `metadata_json`，并在 `GET /api/planner/sku-master` 列表/详情回传 computed 字段（避免前端 N+1）。
  - 验收命令：`pytest backend/tests/planner/test_sku_master_import_mvp.py -q && npm -C frontend run build`

- **方案产出（ERP回传工艺/生产规格）**：
  - `DOC/costing/blueprints/erp_writeback_process_spec_mvp.md`（把“可生产的工艺/规格 + 追溯ID”回写到ERP的最小口径/字段清单/幂等治理）
- **对外谈判资料（吉客云/ERP API需求表单）**：
  - `DOC/costing/blueprints/jky_api_requirements_form_v1.md`（一页式：读接口+写回接口+限流/幂等/字段字典要求）
  - `DOC/costing/blueprints/jky_after_sales_returns_requirements_form_v1.md`（售后/退货/作废/换货/补发：冲销与对账所需字段/接口/主键要求）

- **本轮闭环产物（Backend / 发货单导入→spec_hash缓存→BOM快照 + 异常队列 MVP）**：
  - 新增落库表：`shipment_import_batches`、`shipment_lines`、`spec_parse_snapshots`、`bom_snapshots`、`shipment_exception_queue`
  - 新增接口：
    - `POST /api/planner/shipments/import`（xlsx 导入→标准化→幂等→生成快照/入异常）
    - `GET /api/planner/shipments/import-batches/{batch_id}`
    - `GET /api/planner/shipments/exceptions?batch_id=...`
    - `GET /api/planner/shipments/bom-snapshots?batch_id=...`
  - 幂等口径：
    - 文件级：`file_hash=sha1(xlsx_bytes)`（同文件重复导入直接返回已成功 batch）
    - 行级：`external_line_key_hash=sha1(shipment_no|sku_code|spec_text|qty|revenue_amount)`（跨批次重复不重复生成 shipment_line/bom_snapshot）
  - 关键输出：`bom_snapshots.trace` 中回填 `bound_version_id + spec_hash + batch_id + shipment_line_id`
  - 本轮验收命令（必须）：`pytest backend/tests/planner/test_shipment_import_bom_snapshots_mvp.py -q`

- **本轮闭环产物（Backend / 发货异常队列：按批次重试未解决异常（Retry Exceptions）MVP）**：
  - 新增接口：`POST /api/planner/shipments/exceptions/retry`
  - 请求字段（JSON）：`batch_id`、`only_unresolved=true`、`limit?`、`operator_id`、`reason`
  - 行为（写死口径，MVP）：
    - 仅选择 `shipment_exception_queue.batch_id==batch_id` 且 `resolved_at is null` 的异常（`only_unresolved` 必须为 true）
    - 对每条异常关联 `shipment_line` 重新执行：SKU 绑定校验 → 规格解析（复用 `spec_hash` 缓存）→ 生成 **新** `bom_snapshots` 记录（不覆盖历史快照）
    - 成功：将原异常标记 resolved（写 `resolved_at`），并在 `payload_json.resolution` 中记录 `action=retry/resolved_by/resolved_bom_snapshot_id/retry_reason`
    - 失败：保持 unresolved，并在 `payload_json.retry` 记录 `count/last_at/last_by/last_reason/last_error`，同时更新 `message`
  - 最小单测：`backend/tests/planner/test_shipment_exception_retry_mvp.py`
  - 本轮验收命令（必须）：`pytest backend/tests/planner/test_shipment_exception_retry_mvp.py -q`
  - 下一步（不在本轮范围）：区分“重跑整批（Rerun Batch）”与父子批次链路；补审计日志落 `audit_logs`（如需要）

- **本轮运维闭环（Backend Ops / 上线 Retry Exceptions 到 47.99.89.206）**：
  - 最近校对（北京时间 GMT+8）：2026-01-01 17:33
  - 结果：**已上线**（`git pull --ff-only` + `alembic upgrade heads` + `systemctl --user restart planner-costing.service`）
  - 最小证据（必须）：
    - OpenAPI 校验输出：`True`
    - pytest 输出：`2 passed`
  - 目标机验收命令（复用口径，留档）：
    - OpenAPI：`curl -sS http://127.0.0.1:8800/openapi.json | python -c 'import json,sys; s=json.load(sys.stdin)[\"paths\"]; print(\"/api/planner/shipments/exceptions/retry\" in s)'`
    - pytest：`cd /home/admin/ai-costing-system/backend && . venv/bin/activate && python -m pytest tests/planner/test_shipment_exception_retry_mvp.py -q`

- **本轮闭环产物（Backend / SKU 主档导入 + 发货导入自动回写 MVP）**：
  - 新增落库表：`sku_master`（以 `erp_sku_barcode=货品条码（系统）` 为唯一键）
  - 新增接口：
    - `POST /api/planner/sku-master/import`（导入 `ERP 理 平台商品列表.xlsx` 过滤字段，按 barcode upsert）
    - `GET /api/planner/sku-master?search=&channel=&match_status=&page=&page_size=`
    - `GET /api/planner/sku-master/{id}`
  - 发货导入增强：`POST /api/planner/shipments/import` 若 barcode 未命中 `sku_master`，则创建最小主档（`metadata.source="shipment_autobackfill"`；不覆盖已存在主档）
  - 本轮验收命令（必须）：`pytest backend/tests/planner/test_sku_master_import_mvp.py -q`

- **本轮闭环产物（Frontend / SKU 主档工作台 MVP）**：
  - 新增页面：`/costing/sku-master`（成本核算菜单下新增入口：SKU 主档 / 商品关联）
  - 功能（MVP）：
    - 上传导入：调用 `POST /api/planner/sku-master/import`（xlsx + requested_by）
    - 列表分页：调用 `GET /api/planner/sku-master`（search/channel/match_status/page/page_size）
    - 详情抽屉：调用 `GET /api/planner/sku-master/{id}`（展示原始字段 + 图片预览 URL + metadata_json）

- **补充迭代（已完成）：SKU 主档绑定工作台（只选模型→唯一在线发布标准版本）**：
  - 手工绑定（不覆盖已有绑定）：
    - 右侧列表勾选 SKU 主档 → 左侧选择“已发布标准模型” → 一键绑定（自动落到该模型唯一 `published standard` 版本）
    - 后端接口：`GET /api/planner/sku-master/published-standard-models`、`POST /api/planner/sku-master/bind-by-model`
  - 自动绑定（确定性规则，带预览/执行）：
    - 仅对 `model_code_hint` 唯一命中“已发布标准模型”的未绑定 SKU 自动绑定
    - 后端接口：`POST /api/planner/sku-master/auto-bind/preview`、`POST /api/planner/sku-master/auto-bind/execute`
  - 验收命令：
    - Backend：`cd backend && . venv/bin/activate && pytest tests/planner/test_sku_master_binding_workbench_mvp.py -q`
    - Frontend：`npm -C frontend run build`

- **补充迭代（已完成）：自动绑定预览→右侧候选列表→默认全选→仅绑定选中**：
  - 预览后：右侧列表自动切换为“命中候选视图”（只显示命中候选并默认全选），新增列展示匹配模型/命中词/命中方式
  - 执行：仅对“命中候选”中被勾选的记录执行绑定；未勾选则不绑定
  - 后端：`POST /api/planner/sku-master/auto-bind/execute` 支持 `sku_master_ids` 入参
  - 验收命令：
    - Backend：`cd backend && . venv/bin/activate && pytest tests/planner/test_sku_master_binding_workbench_mvp.py -q`
    - Frontend：`npm -C frontend run build`

- **补充迭代（已完成）：标准模型“型号识别规则”（用于自动绑定识别）**：
  - 入口：标准模型编辑抽屉（`entryContext="standard"`）新增 Tab：**型号识别规则**
  - 规则：在模型 `metadata_json.recognition_keywords` 维护关键词（如 OZU：`丝圈地垫`、`丝圈`），用于从交易规格 `spec_text` 识别模型
  - 护栏：关键词在“已发布标准模型集合”内 **必须全局唯一**（保存时后端校验，避免歧义）
  - 自动链路：`sku-master auto-bind preview/execute` 优先按关键词命中模型，其次才用 `model_code_hint` 兜底
  - 验收命令：
    - Backend：`cd backend && . venv/bin/activate && pytest tests/planner/test_sku_master_binding_workbench_mvp.py -q`
    - Frontend：`npm -C frontend run build`

- **补充迭代（已完成）：型号识别规则 UI 列表化（新增/删除/校验/保存）**：
  - 交互：新增关键词→列表展示→可删除；提供“校验”按钮（不落库）与“保存”按钮（落库）
  - 后端：新增校验接口 `POST /api/planner/product-models/{id}/recognition/validate`
  - 验收命令：
    - Backend：`cd backend && . venv/bin/activate && pytest tests/planner/test_product_model_recognition_validate.py -q`
    - Frontend：`npm -C frontend run build`
    - 命中率/字段齐全（MVP）：在页面按“当前页”聚合展示
  - 本轮验收命令（必须）：`npm -C frontend run build`（已通过）

- **本轮方案产物（SKU→BOM→发货/扣库/核算对账）**：`DOC/costing/blueprints/sku_binding_bom_shipment_plan.md`
- **本轮提炼件（发货单样例）**：`DOC/index/extracted/shipment_xlsx_extracted_20251222T000000+0800.md`
- **本轮验收命令（提炼件/方案）**：
  - `grep -nF "# 提炼：发货单-理.xlsx（表头/前几行样例，基于xlsx-xml解析）" DOC/index/extracted/shipment_xlsx_extracted_20251222T000000+0800.md`
  - `grep -nF "SKU 绑定 → 规格解析 → 动态 BOM → 发货/扣库/核算对账" DOC/costing/blueprints/sku_binding_bom_shipment_plan.md`
  - `grep -nF "external_line_key" DOC/costing/blueprints/sku_binding_bom_shipment_plan.md`
  - `grep -nF "交易规格（spec_text）变更" DOC/costing/blueprints/sku_binding_bom_shipment_plan.md`
