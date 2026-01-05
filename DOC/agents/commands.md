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



