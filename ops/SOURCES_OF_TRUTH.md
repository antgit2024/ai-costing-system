# Sources of Truth — 哪些文件在 git，哪些是孤本

> 2026-05-12 那次"无形批量删除"事件之后做的总账。
>
> 所有"在生产里跑、但不在 git 里"的文件都是**潜在的永久丢失风险**。
> 这个文档列出全部已知的此类文件，并标注当前治理状态。

---

## ✅ 已纳入 git（被删都能 `git restore` 救回）

### Backend / Frontend 代码
- `backend/src/**` — FastAPI 后端（含 27 万行业务代码）
- `frontend/src/**` — React 前端
- `backend/scripts/**` — 离线脚本（cron_snapshot_sweep, backfill, jackyun sync 等）

### Systemd user units（symlink 到 git 内）
| Unit | 用途 | install.sh 处理 |
|---|---|---|
| `ai-costing-snapshot-sweep.service/.timer` | nightly 05:30 BomSnapshot 补扫 | symlink |
| `ai-costing-data-quality.service/.timer` | nightly 05:50 SPU 冲突重算 | symlink |
| `ai-costing-nightly-refresh.service/.timer` | nightly 04:00 insights 缓存预热 | symlink |
| `costing-workspace-health.service/.timer` | hourly 工作区健康巡检 | symlink |
| `costing-audit-summary.service/.timer` | daily 08:00 删除事件汇总 | symlink |
| `jackyun-shipment-sync.service/.timer` | nightly 02:30 ERP 发货增量同步 | symlink |
| `jackyun-refund-sync.service/.timer` | nightly 03:00 ERP 售后增量同步 (omsapi-business.refund.listrefund) | symlink |
| `planner-costing.service` | backend API 主服务 | symlink |
| `planner-costing.service.d/llm.conf` | LLM 非 secret 配置 | symlink |

### Audit / 防御机制
- `/etc/audit/rules.d/99-costing-files.rules` ← 源在 `ops/audit/99-costing-files.rules`
- `ops/audit/who-deleted.sh` — 友好查询封装
- `ops/audit/daily_summary.sh` — 每日汇总
- `ops/audit/workspace-health.sh` — 工作区健康巡检
- `ops/audit/cron-restore-audit-acl.sh` ← 部署到 `/etc/cron.daily/restore-audit-acl`

### Nginx 配置（git 内备份，手动同步到 /etc）
- `ops/nginx/ai-costing.conf` ← 生产文件 `/etc/nginx/conf.d/ai-costing.conf`
- 部署方法见 `ops/nginx/README.md`（不能 symlink 到 root 目录）

### 一键恢复
```bash
ops/systemd/user/install.sh           # 复活所有 user-mode unit (symlink + enable timer)
ops/systemd/user/install.sh --check   # 仅检查整体一致性，不改任何东西
```

---

## ❌ 不在 git 但**故意**不在（敏感信息）

这些文件**包含密钥/密码**，绝不能 commit。
**部署时必须从安全备份手动放置**，install.sh 只检查存在不覆盖。

| 文件 | 内容 | 模板 |
|---|---|---|
| `~/.config/systemd/user/planner-costing.service.d/dingtalk.conf` | 钉钉 APP_KEY / APP_SECRET | `ops/systemd/user/planner-costing.service.d/dingtalk.conf.example` |
| `~/.config/systemd/user/planner-costing.service.d/llm_key.conf` | DashScope LLM API_KEY | `ops/systemd/user/planner-costing.service.d/llm_key.conf.example` |
| `/home/admin/ai-costing-system/.env` | DB 连接 / 各种 secret | `.env.example`（在 backend/） |

**强烈建议**：把这 3 个文件用 `tar -cz` 加密备份到一个安全位置（钉钉云盘 / 阿里云 OSS 加密桶 / 1Password），定期更新。

---

## ⚠ 不归我们管，但也是孤本（建议在对应 repo 治理）

这些 service 跑在同一台机器，但属于其他项目，应该在那个项目的 git repo 里治理：

| Unit | 项目 | 风险 |
|---|---|---|
| `vector-index-sync.service/.timer` | agents-platform | ZNMA 向量索引同步 |
| `vector-search.service` | agents-platform | ZNMA 向量搜索 API |
| `generate-live-index.service/.timer` | agents-platform | 知识库分片索引 |
| `znma-slash.service` | agents-platform | Mattermost /znma 网关 |
| `openclaw-gateway.service` | npm 全局 openclaw | 第三方工具 |

**建议**：到 `/home/admin/agents-platform/` 那个仓库做同样的 `ops/systemd/user/` 治理。

---

## 🟡 孤本但可重建（不重要，删了就重新生成）

| 文件 | 重建方法 |
|---|---|
| `backend/.venv/` | `python -m venv .venv && pip install -r requirements.txt` |
| `frontend/node_modules/` | `pnpm install` / `npm install` |
| `~/storage/logs/ai-costing/` | 自动 logrotate |
| `~/.local/share/costing-audit/` | workspace-health 自动重建 |

---

## 检测漂移

```bash
# 此刻有没有任何 git tracked 文件不见了？
ops/audit/workspace-health.sh --check

# 此刻所有 systemd unit 是不是都正确指向 git？
ops/systemd/user/install.sh --check

# 此刻 nginx 实际配置 vs git 备份有没有 drift？
sudo diff -u ops/nginx/ai-costing.conf /etc/nginx/conf.d/ai-costing.conf
```

如果某个 `--check` 报错，说明发生了漂移，按 `install.sh` / `cp` 恢复即可。

---

## 防御层次回顾

```
┌──────────────────────────────────────────────────────────────────────┐
│ 层 1: 工作区健康巡检 (hourly :05)                                      │
│   workspace-health.sh: tracked-but-missing → auto git checkout        │
├──────────────────────────────────────────────────────────────────────┤
│ 层 2: auditd syscall 取证                                              │
│   who-deleted.sh: 谁/何时/exe/cwd/target 全记录                       │
├──────────────────────────────────────────────────────────────────────┤
│ 层 3: 远程 git (origin/backup/20251214-1535)                          │
│   终极真相，本地任何 IDE/进程都删不掉                                  │
├──────────────────────────────────────────────────────────────────────┤
│ 层 4: 本文档 (这份 SOURCES_OF_TRUTH.md)                                │
│   持续维护"哪些在 git / 哪些是孤本"，让漏纳入的文件无处遁形             │
└──────────────────────────────────────────────────────────────────────┘
```
