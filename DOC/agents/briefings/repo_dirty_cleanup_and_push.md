# 仓库 Dirty 清理 + Push 上线 — 全栈大任务单

> **派单类型**：全栈大任务（git 清理 + 分类 commit + push），按 `task_distribution_standard.md` v2.0 §3.1 模板
> **派单日期**：2026-05-09 19:30 北京时间
> **派单人**：Hub Agent（commit `9bd42648` 已先行归集 Hub 自身规则修订）
> **承接 Agent 角色**：`@DevOps Agent` / `@Fullstack Agent`（scope = git 仓库根目录全部 + push 远程，**完整自主权限**）
> **预估工作量**：1 人天（AI Agent 跑约 4~6 小时）

---

## 0. 30 秒摘要

把仓库累积的 dirty 状态清理掉并 push 上线：

1. 当前**领先 origin 825 个 commit**（含我刚 commit 的 `9bd42648`），**8 个 migration（0030~0037）+ 大量 PnL/Hub 文档 + integrations 模块 + scripts** 都从未被 git 追踪
2. 工作区还有 **51 个 modified + 102 个 untracked**，跨 backend/frontend/docs 多个域
3. 你的任务：**把 153 个 dirty 文件按主题拆成 8~12 个有意义的 commit**（用项目历史的 `feat/fix/ui/docs/chore + scope:` 中文风格），然后 `git push origin HEAD` 把全部本地 commit（约 825 + 你新加的）推到远程
4. **绝对不准**：force push / amend 已有 commit / 改 git config / 删除任何历史 commit / 创建新分支

**用户验收**：`git status` 完全干净；`git log @{u}..HEAD` 为空（即所有本地 commit 都已 push）；远程 `origin/backup/20251214-1535` 与本地 HEAD 一致。

---

## 1. 任务范围（你拥有完整自主权限）

### 1.1 清理范围（全部）

**Modified（51 个）**：
- backend/src 14 个（router/service/dependencies/upstream_actions/config）
- backend/tests 2 个（test_bom_runtime_tokens / test_sku_master_binding_workbench）
- frontend/src 31 个（pages/components/services/theme/utils）
- frontend/scripts 1 个（deploy_static.sh）
- DOC/costing 1 个（manuals/guides/price_calculation_guide.md）
- DOC/agents 1 个（known_issues.md，+540 行）
- .env.sample 1 个

**Untracked（102 个）**：
- backend/migrations 8 个（0030~0037 — **必须提交，否则下次 alembic 会断链**）
- backend/scripts 15 个（backfill / cron / probe / reset / diag）
- backend/src 6 个（integrations 整目录 + binding_targets / integrations / data_quality_service / shipment_import_worker / binding_target_service）
- backend/tests 14 个（test_binding/derive/long_tail/shipment/sku_governance/snapshot 等）
- DOC/costing 12 个（blueprints/handovers/manuals/runbooks 全部 PnL/Hub 文档体系）
- DOC/基础表单 14 个（PDF + xlsx + md 评审材料）
- frontend/src 11 个（common/TargetPicker + ShopSpecCodeCell + IntegrationsHubPage + pages/biz + pages/dev + utils/beijingTime + utils/shopSpecCode + GovernanceBacklogTab）
- tools 1 个（export_md_pdf.py）

### 1.2 完整自主权范围

**你完全自主**：
- 自由 git add / git commit / git diff / git log / git push 等所有 git 操作（除 §1.3 禁令外）
- 自主决定 commit 主题分类（建议 8~12 个，少于 6 个或多于 18 个都需在最终汇报里给出理由）
- 自主决定 commit 顺序（建议：迁移 → 后端代码 → 后端测试 → 后端脚本 → 前端代码 → 前端组件 → 文档 → 杂项；但你可以按你的判断调整）
- 自主决定每个 commit 的 message（按项目风格写中文 + scope）
- 自主选择 push 时机（一次性还是多批，但最终必须全 push）
- 在 git 操作上不需要请示

**你仅在 3 种情况必须立即回 Hub**：
- (a) 发现 git 仓库本身有损坏（如 .git 目录异常 / submodule 冲突 / refs 损坏）
- (b) 发现某个 dirty 文件涉及敏感信息（API key / 密码 / `.env` 真实值，**不是** `.env.sample`）
- (c) push 时被 origin 拒绝（如远程有冲突、无权限、需要鉴权）

### 1.3 绝对禁令（违反 = 任务失败）

按 `agent_rules.md` v2.0 + `task_distribution_standard.md` v2.0 + Cursor Git Safety Protocol：

- ❌ **不准 force push**（`git push -f` / `--force` / `--force-with-lease` 都不准）
- ❌ **不准 amend 任何已有 commit**（`9bd42648` / `f9e5bf43` / `8c7349cd` 等本地 825 commit 任何一个都不能改）
- ❌ **不准 rebase / cherry-pick / reset --hard**
- ❌ **不准动 git config**（`git config` 任何形式）
- ❌ **不准创建新分支**（保持在 `backup/20251214-1535`）
- ❌ **不准删除任何 commit / 任何 reflog**
- ❌ **不准跳过 hooks**（`--no-verify` 不准用，除非 hook 本身报错且确认是 hook bug 再回 Hub 申请）
- ❌ **不准 commit 含真实 secret 的文件**（`.env` / `credentials.json` / API key 等 — 如果发现立即停下回报，**只**允许 commit `.env.sample` 这种模板文件）

### 1.4 必须做的（不做 = 未交付）

- ✅ 把 8 个 migration（0030~0037）commit 到一起或拆分（你决定）— **不允许漏**
- ✅ 把 known_issues.md +540 行 commit（这是 Hub 历史累积，归到 docs 类）
- ✅ push 全部本地 commit 到 `origin/backup/20251214-1535`
- ✅ 完成后 `git status` 完全干净（除非有你判定不应 commit 的文件，需在汇报里说明）
- ✅ 完成后 `git log @{u}..HEAD` 为空

---

## 2. 必读上下文（10 分钟内可掌握）

### 2.1 必读 3 步

```
[ ] 1. DOC/agents/agent_rules.md（v2.0 — §2 任务粒度 + §7 交接成本约束）
[ ] 2. DOC/agents/task_distribution_standard.md（v2.0 — §0.2 完整自主权 + §3 大任务模板）
[ ] 3. 本任务单 §3 的主题分类建议
```

### 2.2 按需扩读

- 如果对某个 dirty 文件的归属不确定 → 用 `git log --all -- <file>` 看历史 commit 风格
- 想看子 Agent 之前的 commit 风格 → `git log -3 --stat`（看 8c7349cd / f9e5bf43 / 9bd42648 的 message 和文件清单）
- 项目整体上下文 → `DOC/agents/state.md`（按需 grep，不要全读）

### 2.3 关键事实（不需要再调研）

| 事实 | 来源 |
|---|---|
| 当前分支 `backup/20251214-1535` 比 `origin/backup/20251214-1535` 领先 825 commit | `git status -sb` |
| 这是项目常态（用户 2026-05-09 19:25 确认 — 项目本地为主，origin 只作备份点）| 用户确认 |
| 8 个 migration 0030~0037 是 untracked 但本地 PG 数据库已经 upgrade 过 | 子 Agent commit 8c7349cd 跑通 alembic 时确认 |
| `data_quality_service.py` 是雏形子系统，现有 `known_issues.md §0.0j` 已记录 | known_issues.md +540 行的内容 |
| `integrations` 模块（吉客云/宜搭）是另一条线的工作 | `backend/src/integrations/` + `backend/scripts/cron_sync_jackyun.py` |
| `data_quality_service` / `binding_targets` / `shipment_import_worker` 都是 known_issues.md 提到的雏形 | 见 known_issues.md §0.0j 等 |

---

## 3. 主题分类建议（8~12 个 commit）

> 这是建议，不是强制。你可以按自己的判断调整。但每个 commit 必须主题清晰、范围合理。

### 建议拆法 A — 12 个 commit（粒度细一点）

| # | 主题 | 大致包含 | 建议 commit message |
|---|---|---|---|
| 1 | Migration 0030-0037 补 git 追踪 | `backend/migrations/versions/0030~0037` | `chore(db): 补提 0030-0037 历史 migration（早期未追踪）` |
| 2 | integrations 模块（吉客云/宜搭/上游集成）| `backend/src/integrations/` + `routers/integrations.py` + `services/integration*.py` + `services/upstream_actions.py` modified + `frontend/services/integrations.ts` + `frontend/pages/IntegrationsHubPage.tsx` + `cron_sync_jackyun.py` | `feat(integrations): 引入吉客云/宜搭集成层 + IntegrationsHub 入口` |
| 3 | data_quality_service 雏形（SKU 数据质量）| `backend/services/data_quality_service.py` + `scripts/backfill_data_quality_status.py` + 相关测试 + `services/sku_master_service.py` modified（如涉及）| `feat(governance): data_quality_service 雏形 + SPU 属性冲突检测（含 only_real_order 守卫）` |
| 4 | SKU 治理 4 态 + GovernanceBacklogTab | `frontend/.../GovernanceBacklogTab.tsx` + `backend/.../sku_governance` 相关 + 治理测试 | `feat(governance): SKU 治理 4 态状态机 + 长尾兜底面板` |
| 5 | binding_targets + TargetPicker / ShopSpecCodeCell 公共组件 | `routers/binding_targets.py` + `services/binding_target_service.py` + 相关 tests + `frontend/.../TargetPicker.tsx` + `ShopSpecCodeCell.tsx` + `utils/shopSpecCode.ts` + `services/sku_master_service.py` 部分 | `feat(sku): binding targets API + TargetPicker/ShopSpecCodeCell 公共组件` |
| 6 | shipment_import_worker + 异常队列重试 + bulk resolve | `services/shipment_import_worker.py` + `services/shipment_import_service.py` modified + `routers/shipments.py` + 相关 test_shipment_* | `feat(shipment): shipment_import_worker + 异常队列 bulk resolve` |
| 7 | 后端 tests 补全 | 剩余 untracked test_*.py（cogs / derive / governance / long_tail / sku_master_shop_spec / snapshot 等）| `test(planner): 补充 14 个 service / router 测试` |
| 8 | 后端 scripts（backfill / probe / reset / diag）| `backend/scripts/` 中除已归类外的剩余 | `chore(scripts): backfill/probe/reset 运维脚本 12 个` |
| 9 | 前端页面/抽屉/编辑器 modified（跨主题，按需进一步细分）| frontend/src/pages 31 个 modified + frontend/src/components 5 个 modified — 你判断要不要再细分到 ui/feat | `ui: 多看板/编辑器/抽屉跨任务累积细节优化` 或拆 2~3 个子 commit |
| 10 | 前端 utils（beijingTime / shopSpecCode）+ pages/dev + pages/biz | 上述 untracked frontend 杂项 | `chore(frontend): beijingTime/shopSpecCode utils + dev/biz 占位页面` |
| 11 | PnL/Hub 文档体系（blueprints + handovers + manuals + runbooks）| DOC/costing 12 个 untracked + 1 个 modified（price_calculation_guide.md）+ DOC/基础表单 14 个 | `docs(costing): PnL/Hub 全文档体系 + 评审材料归档（基础表单 PDF/xlsx）` |
| 12 | known_issues.md +540 行 + tools/export_md_pdf.py + 杂项 | `DOC/agents/known_issues.md` + `tools/export_md_pdf.py` + `.env.sample` + `frontend/scripts/deploy_static.sh` | `docs(agents): known_issues.md 累积更新（含 §0.0j data_quality 真相） + 杂项工具` |

### 建议拆法 B — 8 个 commit（粒度粗一点，更省时间）

合并 #2+#3+#4+#5+#6 = "后端业务模块累积"；合并 #9+#10 = "前端 UI/utils 累积"。

### 通用约束

- 每个 commit 必须用 HEREDOC 写中文 message
- message 第一行 ≤ 60 字符（含 `feat(xxx):`）
- 多行 message 第二行起可以详细列改了什么子目录/模块
- 不要把不相关的修改塞进同一个 commit（如 integrations + data_quality 不要合并）
- 如果某个 modified 文件你判断不该 commit（如纯本地调试残留），在最终汇报里说明并保留 dirty

---

## 4. 完成标准（用户能验收的 5 条 — 缺一不可）

```
[ ] 1. git status 完全干净（或只剩你判定不应 commit 的少数文件，已在汇报里说明）
[ ] 2. git log @{u}..HEAD 为空（所有本地 commit 都 push 到了 origin）
[ ] 3. 你新加的所有 commit 都用了 feat/fix/ui/docs/chore + 中文 scope 的项目风格
[ ] 4. 8 个 migration 0030~0037 都进了某个 commit（可以分开也可以合并）
[ ] 5. 没有任何禁令被违反（无 force push / 无 amend / 无 git config / 无新分支 / 无 secret commit）
```

---

## 5. 验收命令（自主选 1~3 条）

```bash
# (1) git 状态
git status
git log --oneline -20
git log @{u}..HEAD  # 应该为空

# (2) push 后 verify 远程同步
git fetch
git log origin/backup/20251214-1535..HEAD  # 应该为空

# (3) 检查没有 force / amend 痕迹
git reflog | head -20  # 应该只看到正常的 commit/checkout，不应有 reset --hard / amend
```

---

## 6. 完成后归集（任务交付时 3 件）

```
[ ] DOC/agents/state.md：末尾加一段「2026-05-XX 仓库 dirty 清理 + push 完成快照」（含每个新 commit 的 hash + 主题）
[ ] DOC/agents/task_log.md：追加 1 行（按现有表格格式）
[ ] DOC/agents/known_issues.md（如果你做了第 12 个 commit）：把它本身的 commit hash 标注在 task_log.md 里
[ ] 不要再 add/commit 这次归集 — 这次归集本身在 push 之后做，作为下一轮的 dirty（或者你也可以做完归集再多一个 commit + push 一次）
```

---

## 7. 你最终回复给 Hub 的内容（5 件事）

1. **每个新 commit 的 hash + 一句话主题**（表格形式，方便我汇报给用户）
2. **push 是否成功**（`git push` 输出片段）
3. **是否有任何文件你判断不该 commit + 理由**（如有）
4. **是否触发任何 hook / 任何告警**（如有）
5. **遗留 / 建议的下一步**（如某个 commit 内含临时调试代码建议后续清理）

---

## 8. 关键风险

| 风险 | 规避 |
|---|---|
| 825 commit 一次 push 失败 / 网络断 | git push 有 resume 机制，断了重跑即可；如果反复失败，回 Hub 不要 force |
| 某个 modified 文件其实是 .gitignore 应该忽略的（如 .pyc / __pycache__）| `git status` 不会显示 ignored 的；如果显示出来说明 .gitignore 有 bug，你可以先更新 .gitignore 再 commit |
| `.env.sample` modified 可能被误认为含 secret | `.env.sample` 是模板文件，按名称约定不含真实 secret；diff 一下确认是 placeholder 即可 commit |
| 某个 untracked 文件其实是个人临时文件不该 commit | 用判断：如果文件名带 `_local_`/`_tmp_`/`_debug_`/`my_`/个人姓名 → 不 commit；其他默认 commit |
| commit message 风格不一致 | 第一句话遵循 `feat/fix/ui/docs/chore(scope): 中文`，多行可详细 |

---

## 9. 元信息

| 项 | 值 |
|---|---|
| 任务单版本 | v1.0 |
| 派单日期 | 2026-05-09 19:30 北京时间 |
| 派单人 | Hub Agent |
| 承接 Agent | `@DevOps Agent` 或 `@Fullstack Agent` |
| 预估工作量 | 1 人天（AI 4~6 小时）|
| 关联 commit | 9bd42648（Hub 自身归集，已先 commit）|
| 派单规则版本 | task_distribution_standard.md v2.0 |

---

## 10. 一句话给执行 Agent

读完 §0 + §1.3 禁令 + §3 主题分类建议（共约 10 分钟），就开始动手。把 153 个 dirty 拆成 8~12 个主题 commit，全部 push，4~6 小时后回报。绝对不准 force / amend / reset / 改 config。
