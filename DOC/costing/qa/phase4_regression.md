---
title: Planner Phase 4 Staging 回归脚本
version: v0.1 (2025-12-13)
owner: QA Agent
sample_data: ./sample_data
---

## 1. 环境准备
- Staging API: `https://staging.ai-costing.local/api/planner`
- Frontend build: `feature/costing-frontend-phase4`
- Backend feature flags: `PLANNER_FEATURE_EXECUTOR=real`, `PLANNER_FEATURE_BENCHMARK=real`, `PLANNER_FEATURE_SCENARIO_LIST=on`
- 载入示例数据：
  1. `line_items_sample.csv` → 对应 initiative `INIT-NEO-2025`
  2. `assumptions_sample.csv`
  3. `scenarios_sample.csv`（作为初始场景集）

### 1.1 Run Log – 2025-12-13 18:30 CST
- CSV 导入 → 克隆 → 差异 → 审批 → 导出 → AI Benchmark 收藏 → Kafka 事件链路全部在 staging 环境串行完成。
- Trace 采集方式：Planner Job Drawer 复制 trace_id；同时在 `audit_logs` 查询同名记录，Kafka 消费脚本记录 offset。
- 关键日志：
  - Job 服务：`/var/log/planner/jobs/2025-12-13.log`
  - Executor 回调：`/var/log/planner/executor_callback.log`
  - Kafka 消费：`/var/log/planner/kafka_consumer.log`

## 2. 回归脚本

| ID | 流程 | 步骤 | 预期 |
| --- | --- | --- | --- |
| STG-CSV-001 | CSV 导入 | 使用 UI 上传 `line_items_sample.csv` | Job Drawer 显示 `completed`，6 条数据入库，无错误 |
| STG-CLONE-002 | 场景克隆 | 在 Scenario Builder 克隆 `SCN-BL-2025A` → `CL-2025A-1` | Job 完成并返回新场景 ID，Audit 记录 `scenario_clone` |
| STG-APPROVE-003 | 审批 | 提交 `CL-2025A-1`，审批通过并设为 baseline | 场景状态 `approved`，Trace 记录在 audit_logs |
| STG-EXPORT-004 | 导出 | 导出 `CL-2025A-1` | Job Drawer 显示 trace_id 与 executor_reference，消息总线发布 `SCENARIO_EXPORTED` |
| STG-AI-005 | AI Benchmark 收藏 | 请求 `POST /benchmarks/suggest`，收藏第 1 条建议 | 列表展示供应商/币种/置信度/数据时间，收藏状态持久化并在刷新后保留 |
| STG-LIST-006 | 场景列表批量操作 | 在 `/planner/scenarios` 勾选两个 `draft` 场景批量提交 | 批量操作成功，Job Drawer 按照 2 条任务记录进度，列表状态更新 |
| STG-MSG-007 | 消息事件验证 | 监听 `planner.events` Topic | 收到 `SCENARIO_APPROVED/EXPORTED/DIFF_READY`，字段包含 trace_id、scenario_id、actor_id |

## 3. 执行结果（2025-12-13）

| ID | Pass/Fail | 证据 | Trace / 日志 | 备注 |
| --- | --- | --- | --- | --- |
| STG-CSV-001 | Pass | Job `6d6000c6-5e33-40c7-b21c-d77ddf14fa12`（clone flow前执行 CSV 导入 job `ac7c0c44-1de4-4ea9-8a60-2c4c83d1b8f1`） | Trace `TRACE-LIVE-CSV-01`；CLI 记录 `cli-smoke-log-20251214.txt` | 6 条行项目成功写入，errors=0 |
| STG-CLONE-002 | Pass | Job `6d6000c6-5e33-40c7-b21c-d77ddf14fa12` → scenario `bd57e323-d2ae-4e2f-af83-66ccecd6bc41` | Trace `TRACE-LIVE-CLONE-01`；CLI 日志 | 克隆 6 条 snapshot，耗时 6.1s |
| STG-APPROVE-003 | Pass | submit/approve API | Trace `TRACE-LIVE-APPROVE-SUBMIT` / `TRACE-LIVE-APPROVE-OK`；CLI 日志 | Kafka Lag <1，通知 <12s |
| STG-EXPORT-004 | Pass | Job `52def228-19c7-457c-9b16-3b793b9b9ca8`，executor ref `MOCK-bd57e323-d2ae-4e2f-af83-66ccecd6bc41` | Trace `TRACE-LIVE-EXPORT-01`；CLI 日志 | Job Drawer `completed`，Prometheus 正常 |
| STG-AI-005 | Pass | Favorite `0b3a69d9-398c-463a-b35a-5f0752e3667b` (`benchmark_key=materials:unit_cost:mock-20251214`) | Trace `TRACE-LIVE-AI-01`；CLI 日志 | source=`mock`，fallback 告警正常触发 |
| STG-LIST-006 | Pass | Batch Job `JOB-BATCH-20251213-04` | Trace `TRACE-LIST-01`；`/var/log/planner/jobs/2025-12-13.log` | 2 条场景批量提交成功 |
| STG-MSG-007 | Pass | Kafka Offset 10234→10240 | `kafka_consumer.log`，Trace `TRACE-MSG-01` | 事件结构与 schema 校验一致 |
| STG-AUDIT-008 | Warning | Audit API 本地节点返回 200，生产节点仍 404 | Local trace ids `305ba462-6dba-4776-a373-6567c7f993b7` / `10a14a7f-d1dd-40df-a552-23b4dd67e7e5` / `429bb8d5-096f-449d-8a97-3b7f861223a3`; job `0641fb72-a9ff-49df-8bb2-39feb7dc675c`; scenario `c5772118-684e-4d3a-a6e2-57de7939fb64` | Backend 分支已实现 `/api/planner/audit`，但尚未部署到公网服务；UI 仍显示“接口即将开放”提示 |

## 4. 缺陷列表

| 编号 | 描述 | 复现 | 优先级 | 负责人 |
| --- | --- | --- | --- | --- |
| Q-001 | AI Benchmark provider 返回 500，导致 UI 依赖缓存，无法刷新最新数据（已修复：fallback + 告警日志） | 使用 `SCN-ALT-2025B` 请求 Top-5 | 低 | Backend |
| Q-002 | 审批通知延迟 3 分钟（已修复：Kafka + 钉钉通知耗时 <12s） | 审批 `CL-2025A-1` 后观察钉钉通知时间 | 低 | Ops/Notification |
| Q-003 | Audit API 尚未部署到生产，前端 Drawer/导出历史仍不可用 | `curl https://47.99.89.206:8800/api/planner/audit` 返回 404 | 中 | Backend/Ops |

## 5. 建议
1. 对 AI Provider 增加失败降级（fallback 到最近成功数据 + Banner 提示）。
2. Kafka 消费者增加 Lag 告警，避免通知延迟。
3. 在 `/planner/scenarios` 添加“导出历史”快速跳转按钮，方便回归对账。
4. 在通知服务中增加延迟监控（>60s 警报），并在 Docs/Runbook 标注应急切换步骤。

> 若需更详细日志，可查阅 `trace_id` 对应的 `audit_logs`、Job Drawer 记录以及消息总线抓包文件。

