## 一键复现命令（前端迁移编辑器）

> 目标：任何新 Agent 拿到仓库后，无需读历史对话即可复现、验证、交付。

- 最近校对（北京时间 GMT+8）：2025-12-21（接力入口：`DOC/agents/handoff_planner.md` / `DOC/agents/handoff_frontend.md`）

### 1) 前端（必做）

- 安装依赖：
  - `cd frontend && npm ci`
- 构建（验收门槛）：
  - `npm -C frontend run build`

### 1.2) 前端静态资源发布（服务器同机部署，强制）

> 口径：每次前端/路由/依赖有改动并准备上线时，必须执行“构建 + 原子发布”两步，
> 避免出现 chunk 404 → 回退 HTML 导致 `Failed to load module script (MIME type: text/html)`。

- 构建：
  - `cd /home/admin/ai-costing-system/frontend && npm run build`
- 原子发布到 nginx 静态目录（按机器实际路径调整 `PLANNER_STATIC_DIR`）：
  - `cd /home/admin/ai-costing-system/frontend && PLANNER_STATIC_DIR=/var/www/html/ai-costing/dist ./scripts/deploy_static.sh`

### 1.1) 环境变量文件（强约束：真实 .env 不进 Git）

> 口径：仓库只保留模板文件（例如 `.env.sample`、`frontend/env.production.example`），真实环境文件由部署/个人机器自行提供。

- 后端（根目录）：
  - 首次本地启动前：`cp .env.sample .env`
- 前端（生产构建用）：
  - 首次在服务器/构建机上构建前：`cp frontend/env.production.example frontend/.env.production`

### 4) 文档验收（可选）

- 行级变体运营规范文档存在性：
  - `grep -nF "## 标准模型：行级变体（Overlay）运营/实施规范（v0.1）" DOC/costing/manuals/standard_model_variants_ops_rules.md`
- 发货时再解析（spec_hash 缓存）评审稿存在性：
  - `grep -nF "发货时再解析（spec_hash 缓存）+ SKU→已发布标准版本绑定：优化方案评审稿（Phase0/Phase1）" DOC/costing/reviews/shipment_time_parse_review_phase0_phase1_20251222.md`
- ERP 口径补强清单存在性：
  - `grep -nF "ERP 口径补强清单（Guardrails Addendum）— 发货时再解析主链优先" DOC/costing/reviews/erp_guardrails_addendum_20251222.md`
- 结构标准口径文档存在性（抱枕/桌布）：
  - `grep -nF "结构标准（v1）— 抱枕/靠垫（PILLOW_V1）" DOC/costing/blueprints/structure_standards/pillow_structure_standard_v1.md && grep -nF "结构标准（v1）— 桌布/桌旗/桌垫同构（TABLECLOTH_V1）" DOC/costing/blueprints/structure_standards/tablecloth_structure_standard_v1.md`
- 店铺对接（Integration Agent 入职简报）存在性：
  - `grep -nF "Integration Agent 入职简报：店铺对接（以“商品关联/SKU 主档”为中心）" DOC/agents/briefings/integration_shop_connector_onboarding_mvp.md`
- POD 个性化定制（先印布）蓝图存在性：
  - `grep -nF "POD 个性化定制（先印布）— Phase0 落地蓝图（以抱枕为例）" DOC/costing/blueprints/pod_personalization_print_pipeline_phase0.md`
- POD Agent 接力包存在性：
  - `grep -nF "POD/印刷自动化 Agent 接力包（POD Agent）" DOC/agents/handoff_pod.md`
- Rules Agent 接力包存在性：
  - `grep -nF "## Rules Agent 接力包（规则/培训专用）" DOC/agents/handoff_rules.md`
- 规则与培训手册（v1）存在性：
  - `grep -nF "## 规则与培训手册（v1）— 新人必读入口" DOC/costing/manuals/rules_training_handbook_v1.md`
- 规则条目目录存在性（用于逐条规则拆页）：
  - `test -d DOC/costing/manuals/rules && grep -nF "## 规则条目目录（Rules）" DOC/costing/manuals/rules/README.md`
- UI“新建指南”单一真相（DOC/guides）存在性：
  - `test -d DOC/costing/manuals/guides && grep -nF "UI“新建指南”文档（单一真相）" DOC/costing/manuals/guides/README.md`
- POD Phase0（后端闭环任务单，备用）存在性：
  - `grep -nF "Backend 闭环任务单：POD 个性化定制 Phase0（先印布）— POD 领域最小对象 + Job + 生产包下载（MVP）" DOC/agents/briefings/backend_pod_personalization_phase0_mvp.md`

### 2) 本地联调（可选，但强烈建议）

- 访问页面：
  - 打样模型：`/costing/sample-models`
  - 标准模型：`/costing/standard-models`
  - 发货批次/BOM快照（只读）：`/costing/shipments`
  - SKU 主档工作台：`/costing/sku-master`

### 3) 后端接口 smoke（可选）

> 注意：生产环境通常走 nginx 同源 `/api/planner`；不要在浏览器里直连 `:8800` 以免跨域。

- 标准版本分页（给标准模型列表用）：
  - `curl -sS "http://127.0.0.1:8800/api/planner/product-model-versions?version_kind=standard&page=1&page_size=20" | python -m json.tool`

### 3.1) 后端测试（推荐写法：避免 pytest 命令缺失）

- 统一用：
  - `python -m pytest <test_file> -q`



