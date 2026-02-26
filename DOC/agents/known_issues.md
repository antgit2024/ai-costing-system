## 已知坑（新 Agent 必读）

> 最近校对（北京时间 GMT+8）：2025-12-22（接力入口：`DOC/agents/handoff_planner.md` / `DOC/agents/handoff_frontend.md`）

### 1) API_BASE 与跨域

- 前端 `frontend/src/services/planner.ts` 内置了“同 host 不同端口”回退逻辑：浏览器若检测到 `VITE_PLANNER_API_BASE` 设成 `http(s)://同域:8800/...` 会回退到 `/api/planner`，避免 CORS。
- 结论：**生产联调尽量走 nginx 同源 `/api/planner`**；不要强制把浏览器 API_BASE 指向 `:8800`。

### 4) 统一 Markdown 指南（实际以纯文本展示）

- `frontend/src/guides/*.md` 通过 `?raw` 导入为字符串，在 `frontend/src/components/common/GuideDrawer.tsx` 里以 `<pre>` 纯文本展示并支持“一键复制”。
- 结论：指南内容以“可读/可复制”为第一目标；不要依赖 markdown 渲染效果（避免引入额外依赖/构建风险）。

### 2) @/* alias（构建稳定性）

- 需要同时满足：
  - `frontend/tsconfig.app.json` 有 `baseUrl="."` + `paths: { "@/*": ["src/*"] }`
  - `frontend/vite.config.ts` 有 `resolve.alias` 指向 `src`
- 若 build 报 `TS2307 Cannot find module '@/...'`，先检查以上两处。

### 3) 迁移范围控制（避免“跨文件风暴”）

- 本轮只交付一个闭环产物：**把旧编辑器迁到 `ProductModelEditorDrawer.tsx` 并接通两入口页**。
- 不要顺手重构 unrelated 组件；避免一次改动牵扯几十个文件导致 diff 巨大、交互层卡顿。

### 3.1) `/costing/shipments` 预览/上传 413（Request Entity Too Large）

- **现象**：
  - 在 `/costing/shipments` 上传发货单（xlsx）点击“预览”时提示：`Request failed with status code 413`。
- **根因**：
  - 通常是网关/Nginx 对请求体大小的限制触发（`client_max_body_size`，常见默认 1MB）。
  - 前端走 `multipart/form-data` 上传，无法在浏览器端“绕过”该限制。
- **处理**：
  - 业务侧先行：拆分 Excel（按日期/店铺/导出批次拆分），降低单文件体积。
  - 运维侧根治：放开网关/Nginx 上传限制（例如 `client_max_body_size 20m;`），并确保对以下接口路径生效：
    - `/api/planner/shipments/import/preview`
    - `/api/planner/shipments/import`

### 5) 行级变体需要 base_line_id（未保存清单无法配置）

- “变体（Overlay）”是 **version-scoped + base_line_id-scoped**：只有当版本清单行已落库（物料行有 `id`）才能创建/绑定变体规则。
- 现象：刚新增的物料行（尚未“保存清单”）点击“变体”会提示缺少 base_line_id。
- 处理：先点一次“保存清单”（PUT version lines）再配置变体。

### 6) 目标机 SSH 场景下 systemctl --user 需要 XDG_RUNTIME_DIR

- 现象：在 SSH/非交互环境执行 `systemctl --user restart planner-costing.service` 报错（无法连接 user bus / 找不到 runtime dir），导致服务无法重启。
- 处理：先执行 `export XDG_RUNTIME_DIR=/run/user/$(id -u)`，再运行 `systemctl --user ...`。

### 7) `SKU_NOT_BOUND` 的业务含义（对外文案必须解释清楚）

- **含义口径**：导入发货行时，`sku_code` 无法解析到一个“可用且已发布的标准版本（published standard version）”。
- **常见根因**：
  - 未建立 SKU→标准版本绑定
  - 绑定存在但版本未发布/被禁用（不可用于生产计算）
  - 绑定到草稿/打样版本（口径错误）
- **UI 建议**：异常队列主表按 Excel 列展示；系统字段（`bound_version_id/spec_hash/parser_version/trace`）进抽屉；`SKU_NOT_BOUND` 提示“去绑定/重试异常”。

### 8) “幂等”和“重跑”的语义容易被误解（必须提前写死）

- **误区**：做了幂等后，运营补齐绑定/升级规则，仍然“导入同文件=不再生成结果”，业务误以为系统坏了。
- **口径**：
  - 幂等只保证“不重复写同一份结果”
  - 重跑/重算必须显式触发，并产出**新快照**（不回写历史快照）
- **建议**：统一采用 3 种动作语义（见 `DOC/costing/reviews/erp_guardrails_addendum_20251222.md`）：
  - Retry Exceptions / Rerun Batch / Rebuild Snapshot（单行）

### 16) 数据洞察不要默认“全量计算”（会卡、且数据会逐步补齐）

- **结论**：数据洞察页面必须“按用户选择的时间范围查询/汇总”，默认不要全量拉取 2025 全年/全库。
- **原因**：
  - 2025 属于“边搭建边算”，导入数据可能只有部分 SKU 已绑定模型；全量计算会产生大量无意义查询与异常噪音。
  - 浏览器端全量渲染也会造成卡顿（尤其是表格/图表）。
- **实现口径（已落地）**：
  - 前端 `AfterSalesInsightsPage` 仅在用户点击“查询”后请求 `/api/planner/analytics/returns-rate/sku`，并且必须携带 `start/end/group_by` 参数。
  - 前端 `ProfitInsightsPage` 仅在用户点击“查询”后请求 `/api/planner/analytics/profit/sku` 或 `/api/planner/analytics/profit/model`，并且必须携带 `start/end/group_by` 参数。

### 18) 三张洞察页都是空（最常见原因：未导入数据）

- **现象**：打开“售后分析/模型分析/店铺数据”，选择范围后查询仍然返回空数组。
- **最常见根因**：库里还没有发货/售后数据（当前阶段先靠 xlsx 上传导入，后续才会接 ERP API）。
- **处理**：
  - 发货单：到 `/costing/shipments` 上传发货单（预览→执行）
  - 售后退货单：到 `/costing/insights/after-sales` 上传售后退货单（xlsx 导入）
  - 再回到洞察页选范围点“查询”

### 17) pytest（SQLite）报 “no such table …”（测试库建表不完整）

- **现象**：
  - 运行某些单测（例如 `backend/tests/planner/test_after_sales_import_mvp.py`）报：
    - `sqlite3.OperationalError: no such table: shipment_import_batches`
- **根因**：
  - `Base.metadata.create_all()` 只会创建“已被 import 过、已注册到 Base”的表。
  - 若测试初始化（`backend/tests/planner/conftest.py`）在 `create_all()` 之前没有 import `src.planner.models`，则发货/售后/分析等表不会被建出来。
- **修复口径**（已落地）：
  - 在 `backend/tests/planner/conftest.py` 中提前 `import src.planner.models`（仅用于注册表到 `Base.metadata`），再执行 `Base.metadata.create_all()`。

### 14) 方案文档“方向互补”容易被误读（别拿错主线）

- **现象**：有人把 `DOC/基础表单/BOM系统优化完整方案_最终版.md` 当成“当前发货导入/对账主线”的实施依据，导致讨论跑偏（该文档重点在 30% 复杂套装：编码抽取、模型套模型、自动编码与运营流程）。
- **口径**：
  - “发货时再解析（导入 xlsx → spec_hash 缓存解析 → BOM 快照 → 异常队列）”主线以 `DOC/costing/blueprints/sku_binding_bom_shipment_plan.md` 为准，并以快照不回写/可重跑为硬约束。
  - 《BOM系统优化完整方案》作为 **复杂产品扩展路线**（与主线互补），用于后续迭代“非规则型套装/编码治理/运营流程”。

### 15) 售后/发货导出字段未开启会影响“模型退货率/净利润”归因（必须开启强关联键）

- **现象**：如果 ERP 导出时没有开启“网店订单号/原始单号 + 商品链接ID + 货品条码”，售后行只能做弱匹配，模型归因会不可靠。
- **影响**：
  - “退货率（货品维度）”可以直接按 `货品编号 + 渠道 + 规格` 与发货行做弱关联或直接用 `货品编号` 聚合统计。
  - “退货率（模型维度）/退货导致的成本归因”必须能关联到某条发货行或某个 BOM 快照；否则只能落入“待关联异常队列”，无法严谨归因到模型/版本。
- **专业做法**：
  - 必须开启导出字段：
    - 发货：`原始单号` + `商品链接ID` + `货品条码` + `交易规格` + `完成时间` + `数量` + `金额` + `销售渠道`
    - 售后：`网店订单号` + `商品链接Id` + `货品条码` + `申请时间` + `退货数量` + `退货金额` + `退换原因` + `销售渠道`
  - 在强键齐全时：优先用 `order_no + product_link_id + sku_code` 做强匹配；缺失时才回退到弱匹配，并记录 `match_method/confidence/explanation` 供人工确认。
- **附带提醒**：售后表自带 `货品成本/毛利/毛利率` 多为上游计算列，建议仅留痕；本系统 2025 分析口径以“BOM 快照 + 当前价估算 + 可配置 Run 参数集”为准。

### 11) 店铺对接（集成）别一上来就做“深 API 对接”

- **推荐最低成本路径（Phase0）**：先做“店铺数据导出 → 转换为系统发货导入 xlsx → 上传到 `/costing/shipments`”，用最小数据量验证：
  - SKU 主档是否能覆盖（是否大量 `SKU_NOT_BOUND`）
  - `spec_text` 是否能解析出尺寸/tokens
  - BOM/扣库清单是否符合业务口径
- **原因**：单店深对接成本高（你们反馈 18 万/店），而当前系统已具备 xlsx 导入 + 快照/异常闭环，适合先做可验收的 PoC。
- **参考简报**：`DOC/agents/briefings/integration_shop_connector_onboarding_mvp.md`

### 12) 小程序接入：本地服务器“直接用”通常不可行

- **结论**：小程序端请求必须走“合法域名 + 公网 HTTPS”。纯内网/局域网 IP 的“本地服务器”无法直接被小程序访问。
- **可行路径**：
  - 用 Nginx/网关把后端 API 与文件下载 **通过公网域名暴露**（同源 `/api/...` 优先），并配置鉴权/限流
  - 图片上传优先直传对象存储（OSS/S3），后端只拿 `storage_key` 拉取生成效果图/印刷稿（避免网关带宽瓶颈）
- **参考蓝图**：`DOC/costing/blueprints/pod_personalization_print_pipeline_phase0.md`

### 9) 前端报错：Failed to load module script（MIME type: text/html）

- **现象（Chrome 控制台）**：
  - `Failed to load module script: Expected a JavaScript-or-Wasm module script but the server responded with a MIME type of "text/html".`
  - `Failed to fetch dynamically imported module: http(s)://<host>/assets/<chunk>.js`
- **本质**：浏览器在加载 `/assets/*.js`（hash chunk），但 Nginx 返回了 `index.html` 或 404 页面（`Content-Type: text/html`）。
- **常见根因**：
  - **非原子部署**：发布过程中 `index.html` 先更新，但 `/assets` 还没同步完，导致旧入口去拉新/旧 chunk 失败。
  - **Nginx 错误回退**：对 `/assets/*` 也做了 SPA 回退（`try_files ... /index.html`），把 404 的 chunk 回退成 HTML，触发严格 MIME 校验失败。
  - **缓存策略错误**：`index.html` 被缓存（或中间缓存/CDN 缓存），导致客户端拿到旧入口，但服务器已换了新 assets。
- **彻底修复（必须同时满足）**：
  - 发布侧：静态发布必须**原子切换**（先写临时目录，再一次性切换目录）。脚本：`frontend/scripts/deploy_static.sh`
  - Nginx：
    - `index.html`：`Cache-Control: no-cache`（永远拿最新入口）
    - `/assets/*`：`Cache-Control: public, max-age=31536000, immutable`
    - `/assets/*`：不要回退到 `index.html`，应 `try_files $uri =404`

### 19) BrowserRouter 深链接 404（直接打开 `/costing/...` 显示 Not Found）

- **现象**：
  - 直接访问例如 `https://work.znma.com/costing/insights/models` 返回 `Not Found`（但从首页点菜单进入通常正常）。
- **根因**：
  - 前端使用 `BrowserRouter`（history 模式）。当你直接打开一个“深路径”，服务器需要把该路径回退到同一个 `index.html`，否则会按“静态文件不存在”返回 404。
- **根治（推荐，Nginx 配置）**：
  - 对 SPA 路由前缀开启 history fallback（示例）：
    - `try_files $uri $uri/ /index.html;`
  - 注意：对 `/assets/*` **不要**回退到 `index.html`（否则会触发 §9 的 MIME=text/html chunk 加载失败）。
- **代码侧兜底（已落地，减少对 Nginx 的依赖）**：
  - `npm -C frontend run deploy:static` 在 `vite build` 后会执行 `frontend/scripts/generate_spa_fallbacks.mjs`：
    - 自动把 `dist/index.html` 复制到 `dist/<route>/index.html`（例如 `dist/costing/insights/models/index.html`）
    - 这样即便 Nginx 只支持“目录 index.html”，也能更容易命中并加载 SPA
- **快速自检**：
  - 构建后：`test -f frontend/dist/costing/insights/models/index.html`
  - 发布后（目标机）：`test -f /var/www/html/ai-costing/dist/costing/insights/models/index.html`
  - 若你确认生成了但线上仍 403：检查 `frontend/scripts/deploy_static.sh` 是否误排除了子目录 `index.html`（旧版本 `--exclude "index.html"` 会误伤；应为 `--exclude "/index.html"`）。

### 10) 后端 500：Postgres 要求加密连接（no encryption）

- **现象**：
  - 前端轮询任务角标：`GET /api/planner/task-center/recent` 报 500
  - 后端日志出现：`pg_hba.conf rejects connection ... no encryption`
- **根因**：数据库实例/链路对 SSL 的要求不一致，需要用 `sslmode` 明确策略。
- **额外说明**：如果 Postgres **未续费/不可达**，也会表现为全站 DB 接口 500（processes/taxonomy 等），此时需要先恢复数据库服务本身。
- **修复**：
  - 代码在 `backend/src/database.py` 默认设置 `sslmode=prefer`（尽量兼容：能 SSL 就 SSL，不能就退回明文）
  - 如遇 `pg_hba.conf rejects ... no encryption`（服务端强制加密）：设置环境变量 **`PLANNER_PG_SSLMODE=require`**
  - 如遇 `server does not support SSL, but SSL was required`（链路/代理不支持 SSL 协商）：设置环境变量 **`PLANNER_PG_SSLMODE=disable`**

### 20) 洞察类接口 500：MySQL/MariaDB 下时间分组函数不兼容（strftime/julianday）

- **现象**：
  - 打开洞察页（例如售后仪表盘 `/costing/insights/after-sales`）提示：`Request failed with status code 500`。
  - 后端对应接口（例如 `/api/planner/analytics/after-sales/dashboard`）在 MySQL/MariaDB 环境执行时报 SQL 函数错误。
- **根因**：
  - 后端 `analytics_service` 的 “sqlite/mysql fallback” 若误用 sqlite 专用函数（如 `strftime/julianday/date(...,'weekday')`），在 MySQL/MariaDB 会直接报错。
- **修复**：
  - 升级到包含以下改动的版本（本仓库已落地）：
    - `backend/src/planner/services/analytics_service.py`：为 `mysql/mariadb` 方言使用 `DATE_FORMAT/CONCAT/DATEDIFF` 实现 day/month/week 分组与 lag 计算。

### 13) 全站列表/记录都空或 500：DNS 被 Tailscale/NetworkManager 接管导致公网域名解析失败

- **典型现象**：
  - 页面能打开（静态资源正常、`/api/planner/health` 仍可能返回 200）
  - 但所有依赖 DB 的接口（materials/processes/taxonomy/virtual materials…）全 500 或“列表无记录”
  - 同时“同步宜搭/钉钉”也会失败（钉钉域名解析不到）
- **后端日志关键字**：
  - `could not translate host name "<pgm-xxx>.pg.rds.aliyuncs.com" to address: Name or service not known`
- **快速确认**（返回空/报错即为 DNS 问题）：
  - `getent hosts pgm-xxx.pg.rds.aliyuncs.com`
  - `getent hosts oapi.dingtalk.com`
  - `cat /etc/resolv.conf`
    - 若看到 `nameserver 100.100.*`（Tailscale DNS）或仅 tailnet search，通常就是被接管且上游不可用
- **修复口径（推荐：不影响 Tailscale 通道，但停止接管全机 DNS）**：
  - 关闭 Tailscale 接管 DNS：`sudo tailscale set --accept-dns=false`
  - 若 `/etc/resolv.conf` 仍被 NetworkManager 写成 `100.100.*`，把主网卡连接改为忽略自动 DNS 并指定可用 DNS：
    - `nmcli -t -f NAME,DEVICE,TYPE connection show --active`
    - `nmcli connection modify "<NAME>" ipv4.ignore-auto-dns yes ipv4.dns "223.5.5.5 114.114.114.114"`
    - `nmcli connection up "<NAME>"`
  - DNS 恢复后建议重启后端服务以重建连接池：`systemctl --user restart planner-costing.service`（注意 SSH 场景要设置 `XDG_RUNTIME_DIR`）

### 21) BOM 系统优化方案被误认为“已经上线自动编码/子模型等能力”

- **现象**：一线或新同事看到《DOC/基础表单/BOM系统优化完整方案_最终版.md》后，以为其中提到的“子模型表/组合型产品模型表/编码提取日志表/产品模型编码 \`#S3V1F1\` 嵌入电商字段”等已经在系统中落地，并据此向业务承诺能力或设计下游流程。
- **口径**：
  - 截止 2026-02-10，仓库中只落地了“发货时再解析 + SKU→已发布标准版本绑定 + spec_hash 缓存解析 + BOM 快照 + 发货异常队列”等主线能力；自动编码/子模型/组合型产品模型/编码提取日志目前均处于**方案设计阶段**，尚未有任何 Alembic 迁移或 API/前端实现。
  - 复杂产品（30% 多幅套装/非规则型）的落地路线以《BOM系统优化完整方案》为蓝图，但必须在 Hub/Planner 拆分出 Backend/Frontend/Docs 闭环任务单、完成实现与验收后，才允许对外宣传“已支持自动编码/组合型产品模型”。
  - 对外沟通与培训时，应明确区分：**当前已上线的是什么（主线）**、**设计中/规划中的是什么（扩展方案）**，避免因误读方案文档导致超卖能力或错误依赖。

