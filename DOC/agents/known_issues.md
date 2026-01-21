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



