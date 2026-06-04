# Ops/Backend Ops 闭环任务单：上线“异常队列重试（Retry Exceptions）”到 47.99.89.206

> 角色：@Ops Agent / @Backend Ops  
> 目标：把“按批次重试未解决异常”的后端接口上线，并做最小 API 验收；若同时上线前端按钮，则补一次静态资源发布与页面点验。

## 1) 依赖（必须先合并代码）

- 后端需包含：`POST /api/planner/shipments/exceptions/retry`
- 建议后端已通过本地 pytest：`python -m pytest backend/tests/planner/test_shipment_exception_retry_mvp.py -q`

## 2) 目标机部署步骤（复用既有口径）

> Alembic 多 head/缺 revision、systemctl --user 的注意事项，复用：  
> - `DOC/agents/briefings/ops_deploy_shipment_import_bom_snapshots_to_4799.md`

### 2.1 拉取代码 + 迁移 + 重启

```bash
set -euo pipefail

cd /home/admin/ai-costing-system
git pull --ff-only
git log -5 --oneline

cd backend
. venv/bin/activate
alembic heads
alembic upgrade heads

export XDG_RUNTIME_DIR=/run/user/$(id -u)
systemctl --user restart planner-costing.service
systemctl --user status planner-costing.service --no-pager
curl -sS http://127.0.0.1:8800/api/planner/health
```

## 3) 最小 API 验收（必须）

### 3.1 OpenAPI 路由存在性

```bash
curl -sS http://127.0.0.1:8800/openapi.json | python -c 'import json,sys; s=json.load(sys.stdin)["paths"]; print("/api/planner/shipments/exceptions/retry" in s)'
```

预期输出：`True`

### 3.2 运行后端单测（强烈建议）

```bash
cd /home/admin/ai-costing-system/backend
. venv/bin/activate
python -m pytest tests/planner/test_shipment_exception_retry_mvp.py -q
```

## 4) 若同时上线前端（可选）

> 前端按钮在 `/costing/shipments`：重试异常 + SKU_NOT_BOUND 去绑定 CTA  
> 静态资源发布脚本与原子发布注意事项见 `frontend/scripts/deploy_static.sh` 与 `DOC/agents/known_issues.md` §9。

验收（只要能打开页面并点一次按钮即可）：
- 打开：`/costing/shipments`
- 选中一个批次
- 点击“重试本批未解决异常”：看到成功 toast，并刷新异常列表

## 5) 你需要贴回来的最小证据（用于闭环回填）

- OpenAPI 校验输出（应为 `True`）
- pytest 输出（应为 `1 passed` 或相应通过数）


