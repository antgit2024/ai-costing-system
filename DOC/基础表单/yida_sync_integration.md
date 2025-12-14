# 咨询：宜搭（YiDa）主数据同步指引

本文汇总当前“基础配置”页所依赖的宜搭 V5 应用及凭证，方便你在其它项目或实例中复用同一套数据采集入口。

---

## 1. 目标与范围

- **主数据**：公司、店铺、银行/渠道账户（`master_*` 表）
- **会计科目**：`chart_accounts`（含一级/二级分类、借贷方向）
- **触发方式**：可通过 API (`POST /api/v1/base-config/sync-yida`) 或离线脚本（`scripts/sync_yida_form_v5.py` / `scripts/sync_yida_chart_accounts.py`）完成同步

---

## 2. 凭证与配置文件

| 配置 | 说明 | 文件路径 |
| --- | --- | --- |
| `yida_form_v5.json` | 主数据表单凭证 + 字段映射 | `backend/config/yida_form_v5.json` |
| `yida_chart_accounts.json` | 会计科目表单凭证 + 字段映射 | `backend/config/yida_chart_accounts.json` |

两个配置文件当前内容（同一个钉钉/宜搭实例，可直接复制至其它工程）：

```json
{
  "app_key": "dingyu3knj1chgjdlqhv",
  "app_secret": "rl7E1li2tehbCb0NHcBF4pWOg7XmpqW3C0-N-17VvQdbmh6PM986zpogTCi7FvjB",
  "system_token": "TH866OD15OL40Y1ADOZO17K4VRR53RUXQQ29LV5",
  "app_type": "APP_Z2UDZOCIAGBS51HPDCPE",
  "user_id": "manager6133",
  "form_uuid": "<见下表>",
  "page_size": 50,
  "field_mapping": { ... }
}
```

| 文件 | `form_uuid` | 主要字段映射 |
| --- | --- | --- |
| `yida_form_v5.json` | `FORM-SI866WA1C06525ST6KWLS52PJQF62FZ3UKT9LG` | `enabled_flag`, `code`, `company_name`, `account_value`, `store_name`, `store_identifier` 等 |
| `yida_chart_accounts.json` | `FORM-843D1D58660C44FDBDA706542B97D78DBGXS` | `code`, `primary_category`, `secondary_category`, `balance_type`, `description` |

> **安全提示**：请勿把上述 JSON 直接提交到公开仓库。复制到其它项目时，建议放在 `.gitignore` 管理的 `config/` 或 `.env` 目录。

---

## 3. 后端脚本用法（适用于任意项目）

```bash
# 主数据（公司/店铺/账户）
PYTHONPATH=. /home/admin/.venvs/finance/bin/python backend/scripts/sync_yida_form_v5.py \
  --config backend/config/yida_form_v5.json \
  --dump data/uploads/yida_form_snapshot.json

# 会计科目
PYTHONPATH=. /home/admin/.venvs/finance/bin/python backend/scripts/sync_yida_chart_accounts.py \
  --config backend/config/yida_chart_accounts.json \
  --dump data/uploads/yida_chart_accounts_snapshot.json
```

参数说明：

- `--config`：指向上述 JSON 凭证文件
- `--dump`：可选；若提供会把原始宜搭响应保存为 JSON，便于排查
- `--limit` / `--dry_run`：脚本自带，可在测试环境先演练

脚本内部会通过 `YidaConfig -> DingTalkYidaClient` 调用钉钉开放平台的 `oauth2.getToken` + `yida.forms.instances.query`，再调用 `BaseConfigService` 写入数据库。

---

## 4. 在线 API

若项目已经运行 FastAPI，可以直接复用现有路由：

| Endpoint | 说明 |
| --- | --- |
| `POST /api/v1/base-config/sync-yida` | 同步主数据（使用 `yida_form_v5.json`） |
| `POST /api/v1/base-config/chart-accounts/sync-yida` | 同步会计科目（使用 `yida_chart_accounts.json`） |

前端“基础配置 → 同步宜搭”按钮已对接上述接口，你只需把配置文件放好并重启服务即可。

---

## 5. 接入其它项目的建议步骤

1. **复制配置**：将 `backend/config/yida_form_v5.json` 与 `yida_chart_accounts.json` 拷贝到新项目（仍可使用相同凭证）。
2. **加载路径**：在新项目的 `settings` 中设置 `yida_config_path` / `yida_chart_config_path` 指向这两个文件。
3. **复用服务**：直接引用 `app.services.yida_sync_service` 或 `app/api/routes/base_config.py` 的实现；若项目结构不同，也可复制 `scripts/sync_yida_*.py` 中的示例。
4. **验证**：先在测试库运行 `--dry_run`，确认行数与宜搭数据一致，再去掉 `dry_run`。
5. **权限**：保证钉钉 V5 应用对目标宜搭表单拥有“系统 token + 管理员 user_id”访问权。

---

## 6. 常见问题

1. **返回空数据？** 检查 `system_token` 是否过期或表单被迁移；必要时在宜搭后台重新生成 token 并更新 JSON。
2. **字段映射新增**？只需在 `field_mapping` 中补字段 ID，同时在 `AccountImportRow` / `ChartAccountImportRow` 中添加处理逻辑。
3. **多租户/多实例**？可以创建多份 JSON，每个实例在 `settings` 指向不同路径，实现隔离。

如需我代为复制配置或接入其它项目，只要告诉我新的仓库目录即可。

---

## 7. 成本核算：宜搭物料 / 工序同步规范（新增）

本章节面向“智能成本核算”主项目 Phase1，覆盖 `materials` + `processes` + `process_modules` + `model_variant_rules` 等表所需的源数据。字段来源自宜搭表单（UUID 已在下方列出）与《产品模型 基础表单》Excel 样例。

### 7.1 物料表单（FORM-0X966971PURFOJA97LNHJBBLKUK1234Z6COOLZ）

| 宜搭字段 | 控件 ID（宜搭） | 说明 & 用途 | 必填 | 对应表字段 |
| --- | --- | --- | --- | --- |
| 子表实例ID | _待抄录_ | 唯一行实例，写入 `metadata.instance_id` 以便增量对比 | ✅ | `materials.metadata.instance_id` |
| 货品编号 | _待抄录_ | 物料唯一编码 | ✅ | `materials.material_code` |
| 货品名称 | _待抄录_ | 中文名称 | ✅ | `materials.material_name` |
| 规格 | _待抄录_ | 规格名称（默认/自定义） | ✅ | `materials.metadata.spec_name` |
| 规格编号 | _待抄录_ | 规格唯一标识 | ✅ | `materials.metadata.spec_code` |
| 单价（价格） | _待抄录_ | 采购或核价单价（元） | ✅ | `materials.unit_price` |
| 单位 | _待抄录_ | BOM/核价单位（米/平方/个/元） | ✅ | `materials.unit` |
| 本品用量 | _待抄录_ | 基准模型用量（同单位） | ✅ | `model_materials.base_quantity` |
| 平方用量 | _待抄录_ | 归一化到 1㎡ 的用量 | 选填 | `model_materials.metadata.square_quantity` |
| 用量标准 | _待抄录_ | 实际 vs 标准尺寸切换用参考值 | 选填 | `model_materials.metadata.quantity_standard` |
| 计算方式 | _待抄录_ | `数量` / `周长` / `面积` → 映射 `calculation_method` (`count` / `perimeter` / `area`) | ✅ | `model_materials.calculation_method` |
| 耗损% | _待抄录_ | 损耗率（0-100） | ✅ | `model_materials.loss_rate` |
| 默认用量 | _待抄录_ | 当变体或尺寸缺失时的 fallback | 选填 | `model_materials.metadata.default_quantity` |
| 替换物料 | _待抄录_ | 变体候选（含 FINST ID） | 选填 | `model_variant_rules.target_material_ref_id` |
| 工艺标准 | _待抄录_ | 文本说明 | 选填 | `materials.bom_notes` |
| 小计 | _待抄录_ | 仅用于宜搭展示，可记录在 `metadata.subtotal` | 选填 | `materials.metadata.subtotal` |

> **控件 ID 说明**：需由 Planner/Ops 登录宜搭 V5 → 表单设计器 → 选择字段 → “高级配置”复制控件 ID（如 `textField_xxx`）。填写后保存为 `backend/config/yida_materials.json` 的 `field_mapping`。

#### 物料同步过滤 & 校验

- 仅同步 `enabled_flag = true`（若存在启用字段）且 `货品编号` 非空的行。
- `计算方式` 必须映射到 `count/perimeter/area`，否则写入 `metadata.invalid_reason` 并在 job 报告。
- `平方用量` / `用量标准` 未填写时，系统自动以 `本品用量`、`standard_width_mm`/`standard_height_mm` 推导。
- `替换物料` 字段包含 YiDa 子表引用（如 `WH01002-默认规格[FINST-...]`），解析后写入 `model_variant_rules` 的 `target_material_ref_id`，动作默认 `replace`。

#### 同步频率与责任

- **责任人**：Planner 拥有配置、Ops 执行定时任务，Backend 维护脚本。
- **频率**：每天 02:30 自动跑（systemd timer），手动触发 `POST /api/v1/base-config/materials/sync-yida` 作为补救。
- **日志**：`materials_sync_jobs`（待建）记录批次，失败行写入 `material_sync_audit`。

### 7.2 工序/人工子表（示例文件：`产品模型-人工_20251212203643.xlsx`）

该子表目前仍在宜搭主表中，以“人工”页签导出；待宜搭确认独立 form_uuid（建议新建 FORM）。暂按以下字段准备 `processes`/`model_processes`。

| 宜搭字段 | 控件 ID（宜搭） | 说明 | 必填 | 对应字段 |
| --- | --- | --- | --- | --- |
| 子表实例ID | _待抄录_ | 唯一实例 | ✅ | `processes.metadata.instance_id` |
| 工序名称 | _待抄录_ | 例如“材料分切” | ✅ | `processes.process_name` |
| 工序代码 | _待抄录_ | 例如 `H0025` | ✅ | `processes.process_code` |
| 班组 | _待抄录_ | 下料组/包装组等 | 选填 | `processes.metadata.team` |
| 工价 | _待抄录_ | 单位工价（元） | ✅ | 映射到 `hourly_rate` 或 `piece_rate`（见计算方式） |
| 工时(分) / 本品用时 | _待抄录_ | 单次作业工时 | ✅ | `model_processes.metadata.base_minutes` |
| 平方用时 / 用时标准 | _待抄录_ | 1㎡ 标准工时 | 选填 | `model_processes.metadata.square_minutes` |
| 单位 | _待抄录_ | 个 / 平方 / 元 | ✅ | `processes.metadata.unit` |
| 计算方式 | _待抄录_ | 与物料相同三种策略 | ✅ | `model_processes.metadata.calculation_method` |
| 小计 | _待抄录_ | 展示用 | 选填 | `processes.metadata.subtotal` |
| 工序标准 | _待抄录_ | 工艺说明 | 选填 | `processes.description` |
| 替换工序 | _待抄录_ | 变体候选 | 选填 | `model_variant_rules`（action=`replace_process`） |

> **人工同步策略**：若 `计算方式=数量` → `piece_rate`; 若为 `面积/周长` → 将 `工价` 视为系数，`工时(分)` 作为固定时间，加总为 `processes.fixed_time_minutes`。

### 7.3 实际 vs 标准尺寸 & 变体规则落地

1. **尺寸换算**  
   - 录入时要求提供 `本品用量`（针对当前尺寸）与 `平方用量`/`用量标准`（1m×1m 指标）。  
   - 当运营输入任意尺寸核价时，计算引擎依据 `calculation_method`：  
     - `count`：直接使用 `base_quantity`；  
     - `perimeter`：`(width + height) × 2 ÷ 用量标准 × base_quantity`;  
     - `area`：`width × height ÷ 用量标准 × base_quantity`.  
   - 若 `平方用量` 未填，默认 `用量标准 = standard_width_mm × standard_height_mm`。

2. **变体规则**  
   - 物料行允许配置多条规则：`trigger_type`（文本/面积/周长）、`trigger_operator` (`equals`, `gte`, `lte`)、`action_type` (`replace`, `append`)。  
   - 所有规则写入 `model_variant_rules` 并在 UI 中展开显示（见 `frontend-product-model-ui` 任务）。  
   - `替换物料` 字段解析 FINST ID 并与 `materials` 对应；若未找到匹配，记录在审计表并 fallback 至默认物料。

3. **虚拟物料**  
   - 易耗品（墨水、套件等）可在宜搭表单中以“虚拟物料”分类维护；同步后写入 `virtual_materials` + `virtual_material_bindings`，并在 `model_materials.material_type = virtual`。  
   - 绑定比例 `quantity_ratio` 由脚本根据 `平方用量`/`默认用量` 自动推算，运营可在 UI 修正。

### 7.4 同步接口与脚本（待开发）

- `backend/config/yida_materials.json`：结构与现有 config 相同，新增 `form_uuid: "FORM-0X966971PURFOJA97LNHJBBLKUK1234Z6COOLZ"`。
- `scripts/sync_yida_materials.py`：继承 `scripts/sync_yida_form_v5.py`，支持 `--limit/--dry_run/--dump`，并可写入 `materials`/`processes`/`model_variant_rules`。
- API：`POST /api/v1/base-config/materials/sync-yida`（需鉴权 + 审计日志，Planner/Ops 可调用）。
- 运行负责人：  
  - **Planner**：维护字段映射、同步策略。  
  - **Backend Agent**：实现脚本与 API。  
  - **Ops**：部署 systemd timer，监控 `/metrics`（`yida_material_sync_total`、`failed_rows_total`）。  
  - **Docs**：在 `go_live_package.md` 追加运行/回滚说明。


