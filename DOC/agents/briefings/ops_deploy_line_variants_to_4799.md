# Ops/Backend Ops 闭环任务单：部署“行级变体（overlay）”到 47.99.89.206

> 角色：@Ops Agent（若无独立 Ops，则由 @Backend Agent 兼任）  
> 目标：把“行级变体后端 MVP + 前端 Overlay Drawer”部署到 `47.99.89.206`，并完成最小验证。

## 1) 本轮范围（必须很小）

- 仅做：拉取最新代码 → 后端迁移 → 重启服务 → 前端 build/部署静态资源 → curl 验证关键接口存在
- 不做：新增功能、重构、改环境架构

## 2) 需要上线的关键提交（用于对照）

- 后端核心（line_variants/spec/parse/bom）：`a7ee7ac`  
- 后端修复（audit payload json_safe + items 回填）：`f58162a`  
- 前端 UI（LineVariantDrawer overlay + 预演）：`73f4996`

> 实际部署以 `git pull` 后的 HEAD 为准；以上仅用于“是否已包含”的对照。

## 3) 部署步骤（建议顺序）

### 3.1 后端（8800）

在服务器代码目录（本仓）执行：

1. `git pull --ff-only`
2. 进入后端并激活 venv（按你们现有方式）：
   - `cd backend && . venv/bin/activate`
3. 数据库迁移：
   - `alembic upgrade head`
4. 重启服务（你们当前是 user-level systemd）：
   - `systemctl --user restart planner-costing.service`
5. 快速确认服务存活：
   - `curl -sS http://127.0.0.1:8800/api/planner/health`

### 3.2 前端（静态资源）

在仓库根目录执行：

1. `git pull --ff-only`（若上一步已 pull 可跳过）
2. `npm -C frontend ci`
3. `npm -C frontend run build`
4. 按现有脚本/路径部署 `frontend/dist`（例如已有 `deploy_static.sh` 或 rsync/cp）

## 4) 验收命令（只给 1 条）

在服务器上执行下面这一条（验证 OpenAPI 路由已包含 spec/bom/line-variants）：

`curl -sS http://127.0.0.1:8800/openapi.json | python -c "import json,sys; p=json.load(sys.stdin)['paths']; print('spec/parse' in str(p) and 'bom/generate' in str(p) and 'line-variants' in str(p))"`

期望输出：`True`

## 5) 回填要求（强制）

- 更新 `DOC/agents/state.md`：写明部署完成时间（北京时间）、目标机验证结果、验收命令
- 更新 `DOC/agents/task_log.md`：追加一行（部署/验收/风险）
- 小步提交：仅包含 `DOC/agents/*` 的回填（不提交 venv/cache/media）


