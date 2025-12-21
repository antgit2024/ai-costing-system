## 一键复现命令（前端迁移编辑器）

> 目标：任何新 Agent 拿到仓库后，无需读历史对话即可复现、验证、交付。

- 最近校对（北京时间 GMT+8）：2025-12-21（接力入口：`DOC/agents/handoff_planner.md` / `DOC/agents/handoff_frontend.md`）

### 1) 前端（必做）

- 安装依赖：
  - `cd frontend && npm ci`
- 构建（验收门槛）：
  - `npm -C frontend run build`

### 4) 文档验收（可选）

- 行级变体运营规范文档存在性：
  - `grep -nF "## 标准模型：行级变体（Overlay）运营/实施规范（v0.1）" DOC/costing/manuals/standard_model_variants_ops_rules.md`

### 2) 本地联调（可选，但强烈建议）

- 访问页面：
  - 打样模型：`/costing/sample-models`
  - 标准模型：`/costing/standard-models`

### 3) 后端接口 smoke（可选）

> 注意：生产环境通常走 nginx 同源 `/api/planner`；不要在浏览器里直连 `:8800` 以免跨域。

- 标准版本分页（给标准模型列表用）：
  - `curl -sS "http://127.0.0.1:8800/api/planner/product-model-versions?version_kind=standard&page=1&page_size=20" | python -m json.tool`



