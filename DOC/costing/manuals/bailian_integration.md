## 百炼（DashScope）接入说明（本项目：工艺模块描述生成）

### 安全提醒（重要）
- **不要把 API Key / AccessKeySecret / AgentKey 等敏感信息提交到 Git 或发到群里/工单里。**
- 如果密钥已经在外部渠道暴露，建议你们尽快在阿里云控制台 **轮换/作废并重建**。

---

## 当前系统里百炼用于哪里？
目前百炼用于：**工艺模块 → 基础信息 → 描述 → “生成”按钮**  
后端会把当前模块的物料组+工序组汇总成结构化 JSON，调用 LLM 生成一段自然语言描述并回填。

接口：
- `POST /api/planner/ai/process-modules/describe`

---

## 配置方式（推荐：环境变量）
后端进程（8800）读取以下环境变量（不写死在代码里）：
- `PLANNER_LLM_PROVIDER`（`dashscope` / `openai_compatible`）
- `PLANNER_LLM_BASE_URL`
- `PLANNER_LLM_API_KEY`
- `PLANNER_LLM_MODEL`（默认：`qwen-plus`）
- `PLANNER_LLM_TIMEOUT_SECONDS`（默认：20）

### 兼容模式说明
本项目当前实现的是 **OpenAI 兼容协议**（`POST {base_url}/v1/chat/completions`）。
如果你们的百炼网关提供 OpenAI 兼容模式，请把 `PLANNER_LLM_BASE_URL` 配成对应的兼容前缀。

> 备注：你提供的 `base_url=https://dashscope.aliyuncs.com` 是百炼根域名，实际兼容模式路径可能需要额外前缀（由你们的主项目/网关决定）。

### 百炼原生模式（DashScope）
如果你希望本项目直接调用百炼原生接口：
- 设置 `PLANNER_LLM_PROVIDER=dashscope`
- 设置 `PLANNER_LLM_BASE_URL=https://dashscope.aliyuncs.com`

后端会调用：
- `POST https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation`
并使用 `Authorization: Bearer <PLANNER_LLM_API_KEY>` 鉴权。

---

## 与主项目 AI 统一的合并策略（后续）
当前做法的优点是：**后端只依赖一个“LLM 兼容接口”**，未来要和主项目统一时，只需要：
- 把 `PLANNER_LLM_BASE_URL` 指向主项目的 AI 网关（由主项目转发到百炼/知识库/Agent）。
- 保持返回协议不变（OpenAI compatible），本项目无需再改代码。

如果你们确定要用百炼的 **Agent/知识库**（`agent_key / workspace_id / app_id / knowledge_base`），建议由主项目 AI 网关封装：
- 统一鉴权
- 统一日志/限流/缓存
- 统一 Prompt 模板与版本管理


