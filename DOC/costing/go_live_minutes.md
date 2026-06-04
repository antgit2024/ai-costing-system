---
title: AI Costing Planner Go-live 审批纪要（草稿）
version: v0.1 (2025-12-14)
owner: Docs Agent
---

## 1. 已完成验证

| 类别 | 内容 | 证据 |
| --- | --- | --- |
| Backend Smoke | CSV 导入、场景克隆、审批、导出、AI 收藏均在 2025-12-14 00:05–00:45 完成 | Jobs: `ac7c0c44-1de4-4ea9-8a60-2c4c83d1b8f1`, `3d0f0d4a-c1d1-4d58-8bfc-6d5d5f1c1c44`, `4b22a9c1-6d08-4a6b-938a-8cb8d4ee18e4`; Trace `TRACE-LIVE-CSV-01`, `TRACE-LIVE-CLONE-01`, `TRACE-LIVE-EXPORT-01`; Favorite `fav-a0f52c5f-2af7-4b21-b1d9-84de9946a2de` |
| Frontend Smoke | 场景列表、导出历史提示、AI 收藏、Job/Audit Drawer（提示 Audit API 未开放） | Trace `TRACE-LIVE-AI-01`, `TRACE-LIVE-FE-01`；Sentry 无新增错误；前端 console 截图见 go_live_package 附录 |
| 回归结果 | `DOC/costing/qa/phase4_regression.md`（Q-001/Q-002 复测 Pass） | Trace `TRACE-AI-FALLBACK-02`, `TRACE-APPROVE-02` |
| 监控 | Prometheus、Kafka Lag、SSE/Sentry 报警 | 00:00–01:00 无异常；fallback/通知延迟指标保持绿色 |
| 文档 | 架构、手册、Runbook、Go-live 索引 | 见 `DOC/costing/architecture.md`、`handovers/rd_handoff_phase3.md`、`go_live_index.md` |

## 2. 剩余风险

| 风险 | 说明 | 缓解/监控 |
| --- | --- | --- |
| Audit API 未开放 | `/api/planner/audit` 尚未 GA，Audit Drawer / 导出历史仍展示“功能即将上线”提示 | 已在手册、go_live_package、runbook 标注；上线后优先排期接口实现；审批需审计记录时由 Backend 导出 `audit_logs` |
| 消息总线 fallback | Benchmark/Executor 故障仍依赖 fallback → 日志持续输出 `message_bus_fallback` | Prometheus + Kafka Lag + fallback 告警已开启；连续触发>3 次立即通知 Zhang Wei / Liu Fang / Chen Qiao 并按回滚脚本切换 mock |
| 前端 preview | 收藏需要正式部署 build；preview/老版本可能无法写入 favorites | 部署流程必须 `npm run build` + 正式同步；如在 preview 操作收藏需重新部署后再使用 |

## 3. 上线窗口 & 联系人

- **窗口**：2025-12-14 00:00–02:00 CST（已执行，当前状态：稳定）
- **回滚窗口**：02:00–03:00 CST，保留上一版镜像与 `PLANNER_FEATURE_FLAG_MOCK_INTEGRATIONS=true`
- **联系人**：Zhang Wei（架构 +86-138****0001）、Liu Fang（DevOps +86-139****0002）、Chen Qiao（QA +86-137****0003）
- **沟通渠道**：钉钉群「AI Costing Go-live」、紧急电话表

> 如需正式纪要，请在审批会后将本草稿更新为最终版并在 `go_live_package.md` 引用。


