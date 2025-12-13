# AI Costing System

独立的“智能成本核算”项目根目录。推荐结构：

```
ai-costing-system/
  backend/    # FastAPI/业务层
  frontend/   # React/Vite 页面
  DOC/        # 需求、架构、操作手册
    agents/   # Planner / Executor 说明、task log
```

- 与 `ai-material-system` 并列，但业务逻辑、Git 历史、部署流程完全独立。
- 若需要与主系统共享某些依赖，可在 DOC 中记录跨项目接口。


