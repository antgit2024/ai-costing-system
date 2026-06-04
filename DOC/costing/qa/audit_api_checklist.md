# Audit API Checklist

## Purpose
QA 用于验证 `/api/planner/audit` 接口的联调情况，确保 Drawer/导出历史页可以通过 trace_id 追溯审批/导出操作。

## 预备条件
- Planner 后端已部署最新 Phase4 代码。
- 数据库中存在 `audit_logs` 记录（可通过执行审批/导出操作产生）。
- 若使用 VPN/网关，请确认该路由已放通。

## 验证步骤
1. **过滤分页检查**
   ```bash
   curl -G https://planner.example.com/api/planner/audit \
     --data-urlencode target_type=scenario \
     --data-urlencode target_id=SC-123456 \
     --data-urlencode action=scenario_export \
     --data-urlencode actor_id=planner_user \
     --data-urlencode trace_id=TRACE-EXPORT-01 \
     --data-urlencode page=1 \
     --data-urlencode page_size=10
   ```
2. **预期响应**
   ```json
   {
     "total": 1,
     "page": 1,
     "page_size": 10,
     "items": [
       {
         "id": "b6f1a4bf-8b2f-4a64-9b8f-632c9d0d7c1b",
         "target_type": "scenario",
         "target_id": "SC-123456",
         "action": "scenario_export",
         "actor_id": "planner_user",
         "payload": {"job_id": "90435dac-6d08-4a6b-938a-8cb8d4ee18e4"},
         "trace_id": "TRACE-EXPORT-01",
         "created_at": "2025-12-14T01:22:34.912345+00:00"
       }
     ]
   }
   ```
3. **结果记录**
   - 如果响应码为 200 且数据与 trace 对齐，则标记为通过。
   - 若出现 4xx/5xx 或 trace 不匹配，保存请求/响应、trace_id，并通知 Backend Agent；同时在 `DOC/agents/task_log.md` 新增条目说明问题与修复。

## 指标/日志监控
- `/api/planner/audit` 访问异常时，结合 `audit_logs` 表与 `trace_id` 比对请求链路。
- `/api/planner/benchmarks/*`、消息总线（Kafka/RabbitMQ 或 fallback 日志）需要在 Smoke/UAT 期间持续观察：
  - 出现 4xx/5xx 或 fallback 告警时，记录 trace_id、事件类型，并在 task log 中跟进。
  - 若 Kafka lag > 阈值（默认 5s 或由 Ops 配置），及时告警并评估是否启用 fail-open 模式。

## 参考
- `DOC/agents/task_log.md`：实时记录 QA/Ops 发现的问题与修复。
- `DOC/costing/manuals/trace_runbook.md`：trace_id → audit → job → 日志 的排查流程。









