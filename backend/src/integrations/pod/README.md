# POD Integration (待实现 · placeholder)

本目录是 POD 平台对接的占位。POD 与 ai-costing 共享 staff JWT（见 `POD_*` 环境变量），后续会通过开放接口完成数据双向流转。

## 计划接入

1. **拉取**
   - 设计稿/订单 → 我方 `shipment_lines` / `cost_initiatives`
   - 定制信息 / 工艺 → 我方 BOM / 商品配对

2. **回写**
   - 算价结果 / 生产工艺 / 打单备注 → POD 后台
   - 入队走通用 `integration_writeback_jobs`，复用 `BaseClient` 重试与日志能力

## 待补

- `client.py`：POD HTTPS 客户端（沿用 `base/client.py`，签名由 POD 提供）
- `api/`：每个 POD 接口一个轻量 wrapper
- `mappers/`：POD payload → 我方业务表
- `sync_jobs.py`：拉取/回写编排，复用 `base/sync_runner.py`

接入步骤参照 `backend/src/integrations/jackyun/`，保持目录结构一致即可。
