# 吉客云（Jackyun）集成运维手册

> 本手册记录 Jackyun 开放平台对接的**契约、操作、排错**全流程，覆盖从「订阅 API → 触发同步 → 数据落库 → 故障定位」每个环节。 
> 写于 2026-05-06 首次端到端打通后；后续如改任何接口名/参数/水位线策略，请同步更新本文档。

---

## 0.2 SKU 匹配工作流：先自动，后手动一键消化（2026-05-07 立 · 用户确认）

> **前提**：模型库不可能一开始就建全。会有一部分发货行因为对应的模型还没建，停在 `SKU_NOT_BOUND` 异常。
>
> **用户已确认接受这个工作流，不做额外的"模型发布反查"自动化。**

### 工作流（背下来）

| 时机 | 谁触发 | 系统行为 | 结果 |
|---|---|---|---|
| 1. **新发货从 Jackyun 同步进来** | 自动（worker 每 2 秒拉 queued batch） | `_finalize_shipment_line` 走识别引擎，命中已发布模型立即自动绑定 + 出快照 | 大部分 SKU 自动消化 |
| 2. 命中不到模型的行 | 自动 | 入 `shipment_exception_queue`，reason=`SKU_NOT_BOUND`；行停在「待处理」Tab | 等人工 |
| 3. **人工建好/发布对应模型** | 你 | （**当前实现不会反向触发**）已有的 SKU_NOT_BOUND 行不会自动重匹 | — |
| 4. **回到 `/costing/biz/shipments?tab=pending` 点 ⚡ 一键自动绑定** | 你 | 跑 `auto_resolve_pending_shipment_lines_execute`：扫所有 pending → 跑识别 → 命中的自动绑定 + 出快照 + 标 SKU_NOT_BOUND 异常为 resolved | 这一批历史 SKU_NOT_BOUND 全消化 |

### 为什么不做"模型发布即反查"

讨论过 3 个方案（A 内联反查 / B 异步反查 / C 定时 sweep），用户判断**当前手动按钮已够用**，不增加复杂度。理由：
- 建模型的频率低（一周几次），手动多点一下按钮成本可控
- 内联反查会让发布 API 慢 1~3 秒，体验有副作用
- 定时 sweep 增加运维面（多一个 systemd timer 要看护）

**未来如果建模频率显著上升，再回头实现方案 A**。改动入口：`product_model_versions.publish` 加 hook → 调 `auto_resolve_pending_shipment_lines_execute(sku_codes=...)`，限制范围到这个 model 的关键词命中范围。

### 给操作员的"半年后还能想起来"的提示

> 建完一个新模型后，**回到「发货管理 → 待处理」Tab 点一次「⚡ 一键自动绑定」**，否则历史的 `SKU_NOT_BOUND` 异常永远停在那里。
> 
> 没建新模型不需要点（除非你怀疑某次自动识别漏了，可以手动点一下兜底）。

---

## 0.1 测试期"自动落库"撤销 SOP（2026-05-07 立 · 用户确认 A 档）

> **前提**：当前模型库还在搭建，担心自动绑定错误。决定走 A 档：**保持系统全自动**，靠"撤销机制"做安全网。
>
> **3 条铁律**：
> 1. 同步 / Worker 自动出快照 / 每 5 分钟 sweep 都**继续运行**（不动 .env）
> 2. 任何错绑都可以**逆向撤销**，不会污染财务报表（清空快照后 SalesInsightsPage 自动忽略）
> 3. 月底前每周抽样审一次"已完成"Tab，发现错绑就用下面 SOP 撤

### 撤销决策树

| 发现的问题 | 用什么操作 | 影响范围 |
|---|---|---|
| 单条发货行绑错了模型 | 详情抽屉点「强制清空快照」+ 在 `/costing/sku-master` 改绑正确模型 | 1 行 |
| 某个 SKU 绑错了，影响很多发货行 | `/costing/sku-master` 找到这个 SKU → 解绑 → 再用「💰 长尾成本策略」标长尾 / 重新绑正确模型 → 5 分钟内 sweep 自动重出快照 | 这个 SKU 的所有历史发货行 |
| 某个**模型版本**全错（应改成另一版） | 现暂无前端入口；找我开发 `/costing/admin/bulk-rebind` 半小时即可 | 全模型版本 |
| 某次同步整批数据有问题 | `/costing/integrations` 运行历史 → 查 `IntegrationSyncRun.id` → 找我用一次性脚本反向 archive 这个 batch | 整批 |

### 安全保障的事实

- **强制清空快照不删数据**：只在 `metadata_json.snapshot_cleared_at` 打时间戳。SalesInsightsPage / 财务报表会自动忽略带这个标记的行，但行本身和 BomSnapshot 都还在 DB，方便事后审计。
- **解绑不删 SkuMaster**：只把 `SkuModelVersionMapping.is_active = False`。SkuMaster 行保留，governance_status 自动回到 `unmanaged`。
- **没有"硬删除"的路径**：所有撤销都是"软删除 + 重建"，原数据可追溯。

### 每周巡检 5 分钟

```sh
# 1. 看待处理 vs 已处理分布
curl -sS http://127.0.0.1:8800/api/planner/shipments/lines/recent-stats \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool

# 2. 进 /costing/biz/shipments?tab=已完成 抽 5-10 行随机检查：
#    - 模型/套装是否合理
#    - 单价 vs 入账金额（详情抽屉那个 Tag）有没有"溢价"出现（通常是绑错才会出溢价）

# 3. 如发现错绑，按上面的撤销决策树处理
```

### 月底升级路径

如果发现"每周巡检-发现-撤销"成本太高（错绑率 > 1%），可以平滑升级到 B 档：

```sh
# 临时停 worker 自动加工，后续手动批量出快照
echo 'PLANNER_SHIPMENT_IMPORT_WORKER_ENABLED=false' >> /home/admin/ai-costing-system/.env
echo 'PLANNER_SHIPMENT_SNAPSHOT_RETRY_ENABLED=false' >> /home/admin/ai-costing-system/.env
systemctl --user restart planner-costing.service
# 同步、Excel 上传都正常，只是不再自动出快照。月底人工审核完去掉两个 false 重启即可。
```

---

## 0. TL;DR — 紧急排错速查

| 现象 | 第一反应 |
|---|---|
| 前端「立即同步」点完报红、或运行历史出现 `failed` | 看 `integration_sync_runs.error_message` 的 `subCode`，对照下文【sub-code 速查表】 |
| `subCode=0130020310 未订阅此API` | 去 [open.jackyun.com](https://open.jackyun.com/) → 应用管理 → API 订阅，给当前 appKey 加上对应方法 |
| `subCode=0050030002 修改时间起止时间差不能超过24小时` | 不应再出现（窗口已自动 24h 切片）；若仍出现说明 sync_jobs 改坏了，回退 `_iter_24h_windows` |
| `subCode=0050030002 创建/完成/修改时间必传其一` | sync_jobs 兜底失效；检查 `effective_start` 是否被正确填成「今天 00:00 上海」 |
| `IntegrationAuthError` 但代码没动 | 90% 是 `appkey/secret` 被改、或时间戳偏移过大。看下 `.env` 和服务器时钟 |
| 重启后端后立即同步还是失败 | `.env` 没被新进程读到。务必用 `set -a && source .env && set +a && uvicorn ...` 重启，**不能** `systemctl restart` 后期望它会重读 |

---

## 1. 契约速记（基于线上文档 2026-05 快照 + 实测）

### 1.1 网关与凭证

```
线上网关:  https://open.jackyun.com/open/openapi/do
appkey:    .env 中 JACKYUN_APP_KEY
appsecret: .env 中 JACKYUN_APP_SECRET    (绝不入库,绝不入 git)
```

### 1.2 公参（form-urlencoded POST 字段名一字不差）

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `method` | str | Y | 接口方法名,见下表 |
| `appkey` | str | Y | 一个词,**不是** `app_key` |
| `version` | str | Y | 当前固定 `1.0`,**不带** `v` 前缀 |
| `contenttype` | str | Y | 一个词,固定 `json`,**不是** `format` |
| `timestamp` | str | Y | `YYYY-MM-DD HH:MM:SS` 上海本地时间(无时区后缀) |
| `bizcontent` | str | Y | 一个词,业务参数 JSON 字符串 |
| `sign` | str | Y | MD5 签名,见 1.4 |
| `contextid` | str | N | 上下文 ID,**不参与签名** |
| `token` | str | N | ISV 授权 token,**不参与签名** |

### 1.3 当前已对接的接口

| method | 中文 | 用途 | 备注 |
|---|---|---|---|
| `wms.order.query-info.page` | 查询发货单(分页) | **同步默认接口** | 必须订阅 |
| `wms.order.query-info.page.v2` | 查询**未完成**发货单(分页) | 备用,只覆盖未完成子集 | 若做"挂单监控"再订阅 |
| `wms.order.query-info` | 查询单条发货单 | 详情接口 | 现未启用 |

### 1.4 签名算法（与上游 Java SDK 完全一致）

```
1. 收集所有公参 + bizcontent,排除 sign / token / contextid 和 None 值
2. 按 key 字典序排序
3. 拼接为 "key1value1key2value2..."（无分隔符）
4. 前后各拼一个 appsecret
5. 整个字符串 .toLowerCase()  ← 这一步极易漏!不做就签名失败
6. MD5 取 32 位 hex 小写
```

实现位置: `backend/src/integrations/jackyun/client.py:_compute_sign`。

### 1.5 响应判定

```
HTTP 200 + body.code in {0, 200} + body.subCode in {None, "0", "0000000000", "00000000"}
   → success = True
否则 → success = False, 走 _classify_error 路径
```

> ⚠️ Jackyun **成功时返回 `code: 0`**(不是 200),subCode 才是真业务错误码。 
> 这跟阿里/淘宝开放平台习惯不同,改 base/client.py 时要小心。

### 1.6 sub-code 速查表（已编码为 client.py 的 `_AUTH_SUB_CODES` / `_RETRYABLE_SUB_CODES`）

| subCode | 含义 | 归类 | 处理 |
|---|---|---|---|
| `0858030801` | 签名错误 | `IntegrationAuthError` | 检查 secret/时钟/签名步骤(尤其 `.lower()`) |
| `0858030802` | appkey 不存在 | `IntegrationAuthError` | 核对 `.env` 与开放平台后台 |
| `0858030803` | token 失效 | `IntegrationAuthError` | 重新授权,或确认 ISV 模式开启 |
| `0130020310` | **未订阅此 API** | `IntegrationAuthError` | 去开放平台后台订阅对应 method |
| `0050030002` | 业务参数缺失/越界 | `IntegrationBusinessError` | 看 msg 定位:24h 窗口 / 时间字段必传 / 状态必传 等 |
| `0859999999` | 上游限流/暂时不可用 | `IntegrationBusinessError` (**可重试**) | 自动重试,无需介入 |
| 其它 | 业务错误 | `IntegrationBusinessError` | 看 msg + 死信表里的 payload 复盘 |

新增 sub-code 时,在 `client.py` 顶部白名单里加,并在 `tests/integrations/test_jackyun_client_contract.py` 加测试。

---

## 2. 数据流与表结构

```
触发同步 (POST /api/planner/integrations/jackyun/sync/shipments)
   │
   ▼
┌─────────────────────────────────────────────────────────────────────┐
│ ① integration_sync_runs       — 每次点击 1 行(运行总账)              │
│    关键字段:                                                          │
│      status / total_rows / inserted_rows / updated_rows /           │
│      error_rows / cursor_start / cursor_end / triggered_by /        │
│      request_params_json (含 start_resolution, window_count)        │
└─────────────────────────────────────────────────────────────────────┘
   │
   ▼  按 24h 窗口分页调上游
┌─────────────────────────────────────────────────────────────────────┐
│ ② integration_api_call_logs   — 每次 HTTP 请求 1 行(审计/排错)       │
│    api_method / http_status / biz_code / biz_sub_code /             │
│    duration_ms / request_json (敏感字段已脱敏) / response_json       │
└─────────────────────────────────────────────────────────────────────┘
   │
   ▼  每个发货单
┌─────────────────────────────────────────────────────────────────────┐
│ ③ integration_api_records     — 原始 payload 不可变档案              │
│    external_id=orderNo / schema_version='jackyun.shipment.v1' /     │
│    payload_json / payload_bytes / payload_hash                      │
│    UNIQUE (source_system, external_id, schema_version) — 多版本共存 │
└─────────────────────────────────────────────────────────────────────┘
   │
   ▼  mapper 拆 SKU 行
┌─────────────────────────────────────────────────────────────────────┐
│ ④ shipment_lines              — 业务表,做账/财务核对就看这个         │
│    shipment_no / erp_order_no / platform_order_no /                 │
│    logistic_no / logistic_name / warehouse_code / warehouse_name /  │
│    sku_code / qty / source_payload_id (反查③) / seller_memo         │
│    UNIQUE (source_system, shipment_no, sku_code) — 幂等的来源       │
└─────────────────────────────────────────────────────────────────────┘
   │
   ▼  任何 mapper 异常
┌─────────────────────────────────────────────────────────────────────┐
│ ⑤ integration_dead_letters    — 死信队列,前端「死信队列」Tab 在看   │
│    stage='mapper' / external_id / error_type / error_message /      │
│    payload_snapshot (出错时的原始 payload, 便于复盘) /               │
│    status='open' → 处理后 'resolved'                                 │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.1 水位线表（增量同步的灵魂）

```
integration_sync_watermarks  — 每个 (source_system, sync_type) 1 行
   source_system='jackyun' / sync_type='shipment_pull'
   watermark_field='modifyTime'
   watermark_value='2026-05-06 13:47:18'   ← 下次从这里续跑
   updated_at / sync_run_id (推进它的那次 run)
```

**水位线推进策略**(2026-05-06 修订,实现在 `sync_jobs._compute_watermark_target`):

```
target = min(
    max(看到的最新 payload 时间, 最后一个窗口的结束时间),
    now − 5 分钟    ← 安全 buffer,避免漏掉上游延迟入库的记录
)
```

> 5 分钟 buffer 由 `_WATERMARK_SAFETY_BUFFER_SECONDS` 常量定义。 
> 改它需要同步更新 `tests/integrations/test_jackyun_watermark_policy.py:test_safety_buffer_is_exactly_five_minutes`。

---

## 3. 触发方式

### 3.1 前端 UI（推荐运营自助）

- 路径: `/costing/integrations` → 选 jackyun → 「立即同步」
- 默认走增量(读 watermark);冷启动从「今天 00:00 上海」拉
- 「高级参数...」可指定 `start_modify_time` / `end_modify_time` / `page_size` / `use_watermark` / `wait`(同步等待)
- 运行历史 Tab + 死信队列 Tab 即时刷新

### 3.2 curl（脚本/调试）

```bash
# 默认增量(走 watermark)
curl -sS -X POST http://127.0.0.1:8800/api/planner/integrations/jackyun/sync/shipments \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"triggered_by":"manual-curl"}'

# 回填 5 月 1 日整天(自动拆 24h 窗口)
curl -sS -X POST http://127.0.0.1:8800/api/planner/integrations/jackyun/sync/shipments \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "start_modify_time":"2026-05-01 00:00:00",
    "end_modify_time":  "2026-05-01 23:59:59",
    "use_watermark": false,
    "wait": true,
    "triggered_by":"backfill-2026-05-01"
  }'
```

### 3.3 Python（cron / 维护脚本）

```bash
cd /home/admin/ai-costing-system/backend
set -a && source /home/admin/ai-costing-system/.env && set +a
.venv/bin/python - <<'PY'
from src.config import settings
from src.database import configure_engine
from src.integrations.jackyun import sync_jobs as jk
from sqlalchemy.orm import sessionmaker
sess = sessionmaker(bind=configure_engine(settings.database_url))()
rid = jk.sync_shipments(sess, page_size=20, use_watermark=True, triggered_by="ops-manual")
sess.commit(); print("run id =", rid)
PY
```

### 3.4 systemd timer（计划任务,**TODO 还未配置**）

如要每 30 分钟自动跑一次,参照 `DOC/costing/runbooks/yida_sync_scheduler.md` 复制
`ops/systemd/yida-material-sync.{service,timer}` → 新建 `jackyun-shipment-sync.{service,timer}`,
把 PAYLOAD 改成 `{"triggered_by":"systemd","use_watermark":true}`,`OnCalendar=*:0/30`。

---

## 4. 常见运维操作

### 4.1 查最近 N 次同步运行

```sql
SELECT id, created_at, triggered_by, status,
       total_rows, inserted_rows, updated_rows, error_rows,
       cursor_start, cursor_end,
       request_params_json->>'start_resolution' AS resolution,
       request_params_json->>'window_count'     AS windows
FROM integration_sync_runs
WHERE source_system='jackyun'
ORDER BY created_at DESC LIMIT 10;
```

### 4.2 看一段时间的发货明细（业务）

```sql
SELECT shipment_no, erp_order_no, logistic_name, logistic_no,
       sku_code, qty, warehouse_name, seller_memo, created_at
FROM shipment_lines
WHERE source_system='jackyun'
  AND created_at >= CURRENT_DATE - INTERVAL '7 days'
ORDER BY shipment_no;
```

### 4.3 反查某个发货单的原始 payload

```sql
SELECT payload_json
FROM integration_api_records
WHERE source_system='jackyun' AND external_id='S202605050120';
```

### 4.4 处理死信（前端「死信队列」Tab → resolve；或 SQL）

```sql
-- 看所有未处理死信
SELECT id, stage, error_type, error_message, external_id, created_at
FROM integration_dead_letters
WHERE source_system='jackyun' AND status='open'
ORDER BY created_at DESC;

-- 修完 mapper 代码后批量重置(如 mapper bug 已 patch,允许下次同步覆盖)
UPDATE integration_dead_letters
SET status='resolved', resolved_at=NOW(),
    resolved_note='mapper bug fixed in commit <sha>, will re-ingest on next sync'
WHERE source_system='jackyun' AND status='open' AND stage='mapper';
```

### 4.5 重置水位线（紧急回填整段时间）

```sql
-- 把水位线推回 4 月 1 日,下次同步会从那天开始按 24h 窗口拉到现在
UPDATE integration_sync_watermarks
SET watermark_value='2026-04-01 00:00:00', updated_at=NOW()
WHERE source_system='jackyun' AND sync_type='shipment_pull';
```

或直接删掉,让下次同步走「冷启动 → 今天 00:00」兜底:

```sql
DELETE FROM integration_sync_watermarks
WHERE source_system='jackyun' AND sync_type='shipment_pull';
```

### 4.6 重启后端（让 .env / 代码改动生效）

```bash
# 找到当前 master pid
pgrep -f "ai-costing-system/backend.*uvicorn"

# kill 后用同一个加载 .env 的命令重启
kill <pid> && sleep 2

cd /home/admin/ai-costing-system/backend && \
  set -a && source /home/admin/ai-costing-system/.env && set +a && \
  nohup .venv/bin/uvicorn src.main:app --host 127.0.0.1 --port 8800 --workers 2 \
  > /tmp/ai-costing-uvicorn.log 2>&1 &
disown

# 健康检查
sleep 3
ss -tlnp | grep :8800
curl -s -o /dev/null -w 'HTTP %{http_code}\n' \
  -X POST http://127.0.0.1:8800/api/planner/integrations/jackyun/sync/shipments \
  -H 'Content-Type: application/json' -d '{}'
# 应返回 401 (need JWT) — 证明路由可达
```

---

## 5. 排错路径（按概率从高到低）

### 5.1 前端报「触发同步失败」

```bash
# A. 后端是否在跑
ss -tlnp | grep :8800

# B. 路由是否注册(返 401 才是正常)
curl -s -o /dev/null -w '%{http_code}\n' \
  -X POST http://127.0.0.1:8800/api/planner/integrations/jackyun/sync/shipments \
  -H 'Content-Type: application/json' -d '{}'

# C. 前端 bundle 是否最新
curl -sS https://work.znma.com/costing/integrations -o /dev/null -w '%{http_code}\n'
ls -la /home/admin/work-znma/static/costing/  # 看构建时间

# D. uvicorn 日志
tail -100 /tmp/ai-costing-uvicorn.log
```

### 5.2 同步 status=failed

1. 前端运行历史点开详情 → 看 `error_message` 的 subCode;对照 §1.6 速查表
2. 或 SQL: `SELECT error_message FROM integration_sync_runs WHERE id='<run-id>'`
3. 死信抽检: `SELECT * FROM integration_dead_letters WHERE sync_run_id='<run-id>'`

### 5.3 同步 succeeded 但业务表没数据

| 可能 | 验证 |
|---|---|
| 窗口内确实没单 | `SELECT request_params_json FROM integration_sync_runs WHERE id=...` 看时间窗 |
| mapper 全失败进死信 | `SELECT count(*) FROM integration_dead_letters WHERE sync_run_id=...` |
| 业务表查询条件错 | 注意 `source_system='jackyun'` 不要漏(其它来源用同表) |

### 5.4 网关连不上

```bash
# DNS
getent hosts open.jackyun.com

# TCP 可达性
curl -sS -o /dev/null -w 'HTTP %{http_code} time=%{time_total}s\n' \
  https://open.jackyun.com/open/openapi/do

# 直接打一发签名请求(不入库)
cd /home/admin/ai-costing-system/backend
set -a && source /home/admin/ai-costing-system/.env && set +a
.venv/bin/python - <<'PY'
from src.integrations.jackyun.client import JackyunClient
from src.config import settings
c = JackyunClient(app_key=settings.jackyun_app_key, app_secret=settings.jackyun_app_secret)
print(c.call("wms.order.query-info.page",
             {"pageIndex":1,"pageSize":1,
              "startModifyTime":"2026-05-06 00:00:00",
              "endModifyTime":  "2026-05-06 23:59:59"}).raw)
PY
```

---

## 6. 文件索引

| 路径 | 用途 |
|---|---|
| `backend/src/integrations/jackyun/client.py` | HTTP 客户端 + 签名 + 错误分类(改这里要改测试) |
| `backend/src/integrations/jackyun/api/shipment.py` | 发货单 API 调用封装 + 分页迭代器 |
| `backend/src/integrations/jackyun/sync_jobs.py` | 顶层同步流程:窗口拆分 + watermark + 死信 |
| `backend/src/integrations/jackyun/mappers/shipment.py` | payload → `shipment_lines` 字段映射 |
| `backend/src/integrations/base/client.py` | 通用基类:重试 / 日志写入 / `_safe_json` |
| `backend/src/integrations/base/sync_runner.py` | `run_sync(...)` 上下文管理器 + archive_record |
| `backend/src/integrations/base/{watermark,dead_letter,errors}.py` | 水位线 / 死信 / 错误层 |
| `backend/src/planner/routers/integrations.py` | FastAPI 路由(触发 / 列表 / 死信处理) |
| `backend/tests/integrations/test_jackyun_client_contract.py` | wire 契约测试(签名/字段名/响应判定) |
| `backend/tests/integrations/test_jackyun_window_splitter.py` | 24h 窗口拆分 + 兜底测试 |
| `backend/tests/integrations/test_jackyun_watermark_policy.py` | 水位线推进策略测试 |
| `backend/tests/integrations/test_jackyun_shipment_mapper.py` | 端到端 mapper 测试(stub HTTP) |
| `backend/tests/integrations/test_jackyun_routes.py` | HTTP 路由测试 |
| `frontend/src/pages/costing/IntegrationsHubPage.tsx` | 控制台页面 |
| `frontend/src/services/integrations.ts` | 前端服务封装 |
| `.env` 中 `JACKYUN_*` | 凭证(不入 git;改完必须重启后端) |

---

## 7. 历史踩坑日志（避免后人重复掉坑）

> 所有这些都已在代码 + 测试里钉死,这里保留作为「为什么这么写」的可追溯记录。

| 日期 | 现象 | 真相 / 修复 |
|---|---|---|
| 2026-05-06 | 网关访问 `openapi.jackyun.com` 报 DNS 不存在 | 该域名根本不存在;真正的网关在 `open.jackyun.com/open/openapi/do` |
| 2026-05-06 | 试 `appkey` 报 `Required parameter 'app_key' not present` | `/wms/service` 那条路是淘宝兼容协议(下划线参数);真网关用一个词的 `appkey` |
| 2026-05-06 | 签名屡次报 `0858030801` | Java SDK 在 MD5 前 `.toLowerCase()`,Python 实现漏了 |
| 2026-05-06 | `code=200` 判定成功失效 | Jackyun 成功是 `code=0` 不是 200;基类 belt-and-suspenders 检查太严 |
| 2026-05-06 | `subCode=0050030002 修改时间不能超过24小时` | 该接口硬性 24h 上限;sync_jobs 加 `_iter_24h_windows` 自动切片 |
| 2026-05-06 | 默认接口选了 `query-info.page.v2` | 它是「未完成发货」子集;全量分页要用 `query-info.page` |
| 2026-05-06 | `pageInfo.total=0` 导致只拉第一页 | 该接口的 `total` 不可信;改为只看返回行数终止 |
| 2026-05-06 | 重复点同步,每次都拉同样 102 行(白工) | 该接口 payload 不带 `modifyTime`;旧逻辑 `max_modify_time = effective_start` 永不被覆盖 → watermark 永远卡在 00:00:00。改为基于 `max(payload_ts, window_end)` capped 到 `now − 5 min` |
| 2026-05-06 | 裸调 `sync_shipments(use_watermark=True)` 在 watermark 空时报 `创建/完成/修改时间必传其一` | sync_jobs 自己缺兜底;现在内部也兜底为「今天 00:00 上海」,并把决策路径写进 `request_params_json.start_resolution` |

---

## 7.5 SKU 治理与按需建模（Sprint 1-3 新增）

### 7.5.1 为什么要做

Jackyun 一拉就是数十万 SKU，预导入或预建模都不现实。三类 SKU 分诊：

- **会重复出现 + 已建模** → 自动绑定 + BOM 快照（auto_bound）
- **重复 + 模型还没建** → 加入建模 backlog（pending_model），异常队列保留可见
- **长尾 / 一月一单** → 标记为 do_not_model，**不再骚扰运营**，cogs 走全局兜底比率

四态全部存在 `sku_master.metadata_json.governance_status`（无 Alembic 迁移），由运营在 `/costing/shipments/ops` 页面交互。

### 7.5.2 新数据流（Sprint 1）

```
Jackyun 同步 → ShipmentImportBatch(status='queued', processor='jackyun_existing_lines')
       ↓
shipment_import_worker._claim_next_queued_batch
       ↓
shipment_import_service.process_existing_shipment_lines
       ↓ for each ShipmentLine:
_finalize_shipment_line(共享辅助函数, Excel 路径也走它)
       ↓
  ensure_from_shipment(建/更新 SkuMaster)
  ↓
  governance_status?
    ├─ do_not_model    → 静默 + long_tail_fallback BomSnapshot(cogs = revenue × rate)
    ├─ pending_model   → 异常队列 reason=MODEL_PENDING
    ├─ unmanaged       → 默认路径(SKU_NOT_BOUND 或 BomSnapshot)
    └─ auto_bound      → 默认路径(产生 BomSnapshot)
```

**关键修正点**（Sprint 1-1/1-2）：

- mapper 里 batch.status 从 `'processing'` 改为 `'queued'`（之前 worker 永远跳过 Jackyun batch）
- mapper 末尾对每条 line 立即调 `ensure_from_shipment` 兜底（worker 会再调一次，幂等）
- `_finalize_shipment_line` 抽出来成共享函数，Excel 路径和 Jackyun 路径都走它

### 7.5.3 4 态字段约定

| 状态 | 字段值 | worker 行为 | UI 入口 |
|---|---|---|---|
| `unmanaged` | 默认 | 入异常 `SKU_NOT_BOUND` | 异常队列 Tab |
| `auto_bound` | — | 正常生成 BomSnapshot | 已就绪/快照 Tab |
| `pending_model` | — | 入异常 `MODEL_PENDING` | 建模 Backlog Tab + 异常队列保留 |
| `do_not_model` | — | 静默 + 长尾兜底快照 | 长尾 SKU Tab（只读+可撤回） |

`metadata_json` 里同时写：

```json
{
  "governance_status": "do_not_model",
  "governance_decided_at": "2026-05-06T13:52:18+00:00",
  "governance_decided_by": "ops-jane",
  "governance_note": "一年只卖一单",
  "governance_history": [
    {"at": "...", "by": "ops-jane", "from": "unmanaged", "to": "do_not_model", "note": "..."}
  ]
}
```

`governance_history` 自动 cap 到最后 20 条，避免 metadata bloat。

### 7.5.4 API 速览

| 路径 | 用途 | 参考实现 |
|---|---|---|
| `POST /api/planner/sku-master/governance` | 批量设置 4 态 | `routers/sku_master.py:set_sku_governance` |
| `GET /api/planner/sku-master/governance?status=...` | 列表（带销售统计排序） | `routers/sku_master.py:list_sku_governance` |
| `POST /api/planner/sku-master/governance/promote-from-model` | 模型发布后自动提升 pending → bound | `routers/sku_master.py:promote_governance_from_model` |

注：路径**必须**注册在 `GET /sku-master/{sku_id}` catch-all **之前**，否则会被当作 sku_id 抢路由（已踩过坑，文件里有醒目注释）。

### 7.5.5 长尾兜底成本（Sprint 3-2）

- 配置：
  - `LONG_TAIL_COGS_FALLBACK_ENABLED=True`（默认开启）
  - `LONG_TAIL_COGS_RATE=0.55`（默认 55%，财务一年校准）
- 行为：`do_not_model` SKU 跳过 BOM 生成，直接写入：
  - `BomSnapshot.trace_json.kind = 'long_tail_fallback'`
  - `ShipmentCostingResult.cost_total = revenue × rate`
  - `ShipmentCostingResult.metadata_json.kind = 'long_tail_fallback'`
- 报表可以按原方式累加 `cost_total`，无需特判长尾分支

如果 ops 想关掉兜底（"宁可没有数也不要错的数"）：

```bash
echo 'LONG_TAIL_COGS_FALLBACK_ENABLED=False' >> .env
# 重启后端
```

### 7.5.6 历史踩坑（Sprint 1-3 验收）

| 现象 | 真相 |
|---|---|
| 触发 Jackyun 同步后 `/costing/shipments/ops?batch_id=...` 看不到任何异常队列行 | mapper batch 是 `processing` 不是 `queued` → worker 直接跳过 |
| 一旦改成 queued，又报错 "preview cache 不存在" | worker 默认走 Excel 入口 `execute_shipment_xlsx_from_preview`，而 Jackyun 没有 xlsx；要按 `result_json.processor` 分发 |
| 端到端验收时发现 `total_rows=102 / shipment_lines=0` 的批次 | 是某个 mapper 早期 update 路径只更新计数没写 line 的旧 batch；用一个有真实 line 的新 batch（如 `b31fa102`）重跑即可 |
| 异常队列里同一个 SKU 反复出现，打扰运营 | 这正是要做 4 态的原因；运营在该 SKU 上点「标记为长尾·不建模」一次永久解决 |

---

## 8. 联系人 / 凭证位置

- 吉客云开放平台后台: <https://open.jackyun.com/>
- 当前测试 appKey: 见 `.env` 中 `JACKYUN_APP_KEY`(目前是 22258171)
- 切换正式应用 / 加新接口订阅: 在该后台「应用管理」→ 选应用 → 「API 订阅」勾选
- 后端服务管理: 这里没有 systemd 单元;手动用 §4.6 的命令组合重启
- 关联 PRD / 架构: `DOC/costing/architecture.md`、`DOC/agents/integration/`

---

更新本手册请同时更新:

- `tests/integrations/test_jackyun_*.py` 里对应的契约/策略测试
- `backend/src/integrations/jackyun/client.py` 顶部的 docstring(契约黄金来源)
- `backend/tests/planner/test_sku_governance*.py` 治理状态机测试
- `backend/tests/planner/test_shipment_import_governance_gating.py` worker 分支测试
