# YiDa 同步定时任务配置

本指南说明如何自动化执行 YiDa 物料/工序同步，包括：

1. 通过 Planner API 触发材料同步 Job（写入 `material_sync_jobs` 表）
2. systemd timer 每天 02:30 调度，并将执行日志写入 `/home/admin/ai-costing-system/logs/yida_material_sync.log`
3. 可选：使用 Cron 或自定义告警脚本

> **前提条件**
>
> - Backend 服务运行在本机 `http://127.0.0.1:8800`
> - `backend/.venv` 已安装依赖并完成 `alembic upgrade head`
> - `/home/admin/ai-costing-system/logs/` 对当前用户可写

---

## 1. 使用 systemd timer（推荐）

1. 将仓库中的示例 unit/timer 拷贝到 systemd 目录：

```bash
sudo cp /home/admin/ai-costing-system/ops/systemd/yida-material-sync.service /etc/systemd/system/
sudo cp /home/admin/ai-costing-system/ops/systemd/yida-material-sync.timer /etc/systemd/system/
```

2. 按需调整 service 中的环境变量：
   - `PLANNER_API`：Planner API 地址（内网可保持 127.0.0.1）
   - `PAYLOAD`：JSON 字符串，可设置 `limit`、`dry_run`、`config_path`

3. 启用并立即执行一次验证：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now yida-material-sync.timer
sudo systemctl start yida-material-sync.service   # 手动触发一次
sudo journalctl -u yida-material-sync.service -n 50
```

4. 失败告警：
   - 可在 service 单元添加 `OnFailure=notify-material-sync@%i.service`
   - 或在 `/home/admin/ai-costing-system/logs/yida_material_sync.log` 由 Promtail/Filebeat 收集并对 `status":"failed"` 触发告警

---

## 2. Cron 备选方案

若环境无法使用 systemd，可在 `crontab -e` 中加入：

```
30 2 * * * /usr/bin/curl -sS -X POST \
  http://127.0.0.1:8800/api/planner/base-config/materials/sync-yida \
  -H 'Content-Type: application/json' \
  -d '{"requested_by":"cron","limit":500}' \
  >> /home/admin/ai-costing-system/logs/yida_material_sync.log 2>&1
```

> 建议依旧将输出重定向到同一个 log 文件，以便排查/比对 systemd 日志。

---

## 3. 手动检查同步结果

1. 查看最新 Job 状态：

```bash
curl -s http://127.0.0.1:8800/api/planner/base-config/materials/sync-jobs/<JOB_ID>
```

2. 验证 `materials` / `processes` 记录：

```sql
SELECT material_code, updated_at FROM materials ORDER BY updated_at DESC LIMIT 5;
SELECT process_code, updated_at FROM processes ORDER BY updated_at DESC LIMIT 5;
```

3. 若 Job 失败，可在 `material_sync_jobs.error_message` 找到堆栈，并检查日志：

```bash
tail -n 100 /home/admin/ai-costing-system/logs/yida_material_sync.log
```

---

## 4. 常见问题

| 情况 | 处理方式 |
| --- | --- |
| `curl` 返回 401 | 确保内网仅限可信用户访问，或在 API 层增加鉴权 Token。 |
| Job status 一直 `running` | Backend 进程可能意外退出；查看 `planner-api.service` 日志并重启。 |
| systemd timer 未触发 | 检查 `systemctl list-timers | grep yida`，确认 `OnCalendar` 设置与本地时区一致。 |
| 需要多租户配置 | 复制 service/timer，分别指向不同的配置文件与 payload。 |

---

更多字段映射与脚本说明，请参阅：
- `backend/config/yida_materials.json`
- `backend/config/yida_processes.json`
- `backend/scripts/sync_yida_materials.py`
- `backend/scripts/sync_yida_processes.py`

