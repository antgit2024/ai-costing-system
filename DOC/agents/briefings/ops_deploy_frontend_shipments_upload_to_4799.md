# Ops 闭环任务单：部署前端“发货单上传导入入口”到 47.99.89.206（/costing/shipments）

> 角色：@Ops Agent / @Backend Ops  
> 目标：让线上 `/costing/shipments` 页面出现“上传发货单（xlsx 导入）”入口，并能成功调用后端 `POST /api/planner/shipments/import`。

## 0) 前置确认（必须）

- 代码需包含提交：`37e91b9 frontend: add shipment xlsx upload to /costing/shipments`

```bash
cd /home/admin/ai-costing-system
git pull --ff-only
git log -5 --oneline
```

## 1) 构建前端静态资源

```bash
cd /home/admin/ai-costing-system/frontend
npm ci
npm run build
```

## 2) 发布静态资源（按现有生产口径）

> 注意：本项目生产静态目录以你们既有脚本为准（例如 `PLANNER_STATIC_DIR=/var/www/html/ai-costing/dist ./scripts/deploy_static.sh`）。

示例（若该脚本存在且你们一直在用）：

```bash
cd /home/admin/ai-costing-system
PLANNER_STATIC_DIR=/var/www/html/ai-costing/dist ./scripts/deploy_static.sh
```

## 3) 最小验收（必须）

### 3.1 页面验收（人工）

- 访问：`http://47.99.89.206/costing/shipments`
- 预期：页面顶部出现 **“上传发货单（xlsx 导入）”**，可选择 `.xlsx` 并点击“上传并导入”

### 3.2 API 验收（机器）

确认后端路由存在（应为 True）：

```bash
curl -sS http://127.0.0.1:8800/openapi.json | python -c 'import json,sys; s=json.load(sys.stdin)["paths"]; print("/api/planner/shipments/import" in s)'
```

## 4) 你需要贴回的最小证据（用于闭环回填）

- `git log -5 --oneline`（能看到 `37e91b9`）
- “页面顶部出现上传入口”的一句确认（或截图文件名）
- OpenAPI 校验输出（True/False）


