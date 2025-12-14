---
title: AI Costing Planner 上线资料索引
version: v1.0 (2025-12-13)
owner: Docs Agent
---

| 文件 | 路径 | 简要说明 |
| --- | --- | --- |
| 架构白皮书 | `DOC/costing/architecture.md` | Planner 全阶段架构、Mermaid 模块/流程、生产部署 checklist、Trace 协作说明 |
| Planner 使用手册 | `DOC/costing/manuals/planner_user_guide.md` | 终端用户操作指南（项目/包/行、CSV 导入、场景克隆/差异/审批/导出、AI Benchmark 收藏、Job/Audit Drawer、Known Issues、Audit 限制） |
| 导出/AI/审计专题手册 | `DOC/costing/manuals/export_ai_audit_manual.md` | 场景导出、AI 建议与审计日志的单项操作说明及截图 |
| 运行手册 / 回滚指南 | `DOC/costing/handovers/rd_handoff_phase3.md` | Phase3.5/4 运行注意事项、监控/告警、回滚策略、QA 结果纪要（含 Trace、消息总线说明） |
| Phase 4 回归报告 | `DOC/costing/qa/phase4_regression.md` | Staging 回归脚本、执行结果、缺陷记录（含 Trace/日志链接、再验证结论） |
| 需求总览 | `DOC/costing/requirements.md` | 业务背景、范围、数据模型、阶段计划与分支策略 |
| 任务日志 | `DOC/agents/task_log.md` | 各阶段交付记录、风险、Go-live 结论 |

## 上线审批结果 & 时间线

| 上线窗口 | 审批结论 | 回滚联系人 |
| --- | --- | --- |
| 2025-12-14 00:00–02:00 CST | 审批通过（业务/架构/QA 于 2025-12-13 20:30 共同签字） | 架构：Zhang Wei / +86-138****0001；DevOps：Liu Fang / +86-139****0002；QA：Chen Qiao / +86-137****0003 |

### 执行回执（2025-12-14）

| 环节 | 描述 | 监控结果 |
| --- | --- | --- |
| Backend 发布 | 00:05–00:35 滚动重启（feature flags 切换至 `real`），Smoke：CSV 导入、场景克隆、导出均成功（Trace `TRACE-BE-SMOKE-01`) | Prometheus `planner_job_duration_seconds` 稳定，Kafka Lag=0，未触发告警 |
| Frontend 发布 | 00:20–00:45 部署新构建（bundle < 400 kB），Smoke：场景列表、导出历史、AI 收藏、Job/Audit Drawer 正常 | 浏览器 console 无报错；Sentry 未新增错误；AI fallback/通知延迟监控保持绿色；截图/日志见 `go_live_package` 附录（包括 `cli-smoke-log-20251214.txt`） |
| Audit API 验证 | `/api/planner/audit` 新增分页/过滤接口已通过 `pytest` 与 `curl`，但生产尚未放通 | Drawer 仍显示“接口即将开放”；日志 `logs/frontend/smoke-20251214.txt`，截图 `screenshots/go-live-20251214/03-export-history.png` |

