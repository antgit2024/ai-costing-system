# Ops/Backend Ops 闭环任务单：部署“发货单导入→spec_cache→BOM快照”到 47.99.89.206（MVP）

> 角色：@Ops Agent / @Backend Ops  
> 目标：将后端发货导入 MVP 上线到 `47.99.89.206:8800`，并用最小命令完成验证。  
> 说明：本仓库可能存在 **多 head**（例如 `0016_line_variants_mvp` 与 `0754ad7d6c3f`），按既定口径使用 `alembic upgrade heads`。

## 1) 部署步骤（目标机上执行）

### 1.1 拉取代码

```bash
cd /home/admin/ai-costing-system
git pull --ff-only
git log -5 --oneline
```

确认包含提交：
- `71c35c6 feat: shipment import spec cache and bom snapshots mvp`
- `7e6ee41 docs: add shipment xlsx sample and sku binding note`

### 1.2 数据库迁移

```bash
cd /home/admin/ai-costing-system/backend
. venv/bin/activate
alembic heads
alembic upgrade heads
```

### 1.3 重启服务

```bash
systemctl --user restart planner-costing.service
systemctl --user status planner-costing.service --no-pager
```

健康检查：

```bash
curl -sS http://127.0.0.1:8800/api/planner/health
```

## 2) 最小 API 验收（必须）

### 2.1 OpenAPI 校验路由已暴露

```bash
curl -sS http://127.0.0.1:8800/openapi.json | python -c 'import json,sys; s=json.load(sys.stdin)["paths"]; print("/api/planner/shipments/import" in s and "/api/planner/shipments/exceptions" in s and "/api/planner/shipments/bom-snapshots" in s)'
```

预期输出：`True`

### 2.2 运行后端验收单测（强烈建议）

> 说明：目标机跑一次能最大化保证“迁移 + 依赖 + 环境一致”。

```bash
cd /home/admin/ai-costing-system/backend
. venv/bin/activate
pytest tests/planner/test_shipment_import_bom_snapshots_mvp.py -q
```

## 3) 关键风险提示（仅记录，不在本轮扩范围）

- 若发货 Excel 出现 **列名漂移/多 sheet/表头变体**，当前实现有“猜测 spec_text”的兜底，但仍可能产生 `MISSING_HEADERS` warning；需下一轮单独增强容错。
- 若出现迁移冲突/多 head 治理：按既定策略后续补一个 merge revision（不要在本轮临时手改版本表）。


