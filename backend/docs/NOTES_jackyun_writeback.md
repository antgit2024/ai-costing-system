# 吉客云反写接口探索结论 (2026-05-17)

> 历时一周的 7 次 trial-and-error + 直接抓官方 schema 后,
> 给"sku 4 字段反写"找到的最终架构. 写给后人省时间.

## 业务诉求

把本地 `sku_master` 4 个字段推回吉客云:

| 内部字段 | 吉客云中文名 | 吉客云 API 字段 | 是否自定义 |
|---|---|---|---|
| `spec_text` | 规格 | `skuName` | ❌ 内置 |
| `model_code_reg` | 模型编码(规) | `skuField1` | ✅ 自定义 |
| `process_instructions_reg` | 工艺说明(规) | `skuField8` | ✅ 自定义 |
| `sku_flag` | 规格标记 | `flagDataName` | ❌ 内置 |

`skuField1/8` 的映射通过 `erp.goods.customfield` 接口动态确认 (dump 见
`scripts/dump_customfield.py`), 商家 tenant 可能不同, 部署新商家时复查.

## API 选型 (走过的坑)

### ❌ erp.goods.update — goods 维度, 静默丢 sku 字段

- 官方 schema 103 字段, **没有任何 sku 字段**, 全是 goods 维度
- 我们试着塞 `skuList:[{skuName, skuField1, ...}]` → 接口返回 success
  但 **实际没更新任何 sku 字段** (用 `erp.storage.goodslist` 回读验证)
- 探针: `scripts/probe_erp_goods_update.py` 7 个 case 全失败
- 旧默认值 `erp.storage.goods.update` 实际是同一个东西的拼写, 也是不订阅就报
  `0130020310 未查询到应用或应用未订阅此 API`

### ❌ erp-goods-online.item.batchupdateitem — OMS 维度, schema 过重

- 用户已订阅, 但要求传 **完整商品档案**: `itemCode + specOptionList +
  itemSkuImageList` 全套
- 简化测试时报 `0038010001 无效的更新方式` / `规格属性名称不能为空`
- 对"轻量改 sku 字段"场景不合适

### ✅ erp.goods.skuimportbatch — sku 维度 UPSERT (主力)

- 官方文档 2026-05-11 更新明确写: "outSkuCode 是 2 个系统之间的货品匹配
  关系的唯一依据, 如果货品没有 outSkuCode 则无法用此接口更新货品"
- biz 顶层是 **flat array of sku items**, 单次最多 200
- 必填: `goodsNo / goodsName / unitName / outSkuCode`
- 支持: `skuName / skuField1..30 / goodsField1..50` 全套
- 行级结果: `result.data[*].success: bool, errorMessage, subCode` —
  **必须二次校验**, 框架 sub_code=0030000004 ≠ 单行业务成功
- **★关键约束**: 现有 sku 在吉客云那侧 `outSkuCode = null` 时, 本接口走"创建"
  路径, 撞到 `goodsNo+skuName` 重复就报 `0031310483 规格名称已存在` 拒绝
- 解决方案: **一次性 cold-start 补码** — 见下面"运营 cold-start"

### ✅ erp-goods.goods.batchupdateflagbyskubarcode — 规格标记专用

- biz: `[{skuBarcode, flagDataName}]`, `flagDataName` 是逗号分隔字符串
- 不依赖 outSkuCode, 直接可用
- 前置条件: 吉客云后台先创建好对应标记名称 (例如"科技皮")

### ✅ erp.goods.customfield — 自定义字段元数据

- 输入: `fieldName` 或 `fieldCaption` (二选一)
- 返回字段中文名/类型/长度. 用于动态确认 `skuField1` 这种"1" 对应哪个业务字段
- 写一次 `scripts/dump_customfield.py` 把全表 dump 到本地, 不要 hardcode

## 最终架构: 分流推送

`backend/src/planner/services/erp_writeback_service.py::push_one_job` 把一个 job
拆成 2 个 step 并行/串行推:

```
job (4 字段)
  ├── step "flag"      → erp-goods.goods.batchupdateflagbyskubarcode
  │     biz: [{skuBarcode, flagDataName: "科技皮"}]
  │     依赖: sku.erp_sku_barcode (一直都有)
  │
  └── step "skuimport" → erp.goods.skuimportbatch
        biz: [{
          goodsNo, goodsName, unitName, outSkuCode,  # 必填
          skuName, skuField1, skuField8              # 想改的
        }]
        依赖: sku.out_sku_code (★冷启动必须先补)
```

汇总规则:
- 全 step succeeded → mark_job_done
- 任一 step retry → mark_job_failed(retry=True)
- 任一 step failed (非重试) → mark_job_failed(retry=False)
- 全 skip + 原因是 needs_outsku_code → 返回 `status: "needs_outsku_code"`
  (UI 用这个状态展示补码引导)
- 部分 ok + 部分 needs_outsku_code → 也返回 needs_outsku_code, 标 last_error
  "PART OK: flag 推送成功, skuimport 跳过"

## 运营 cold-start (一次性)

1. 进入 `/costing/product-info` 页面 → 顶部「反写队列」按钮
2. 在 Drawer 顶部点「下载补码 Excel」 → 自动导出全部 `out_sku_code` 为空的 sku
   (字段映射: 外部编码 = 条码, 一一对应稳定)
3. 拿这个 Excel 到吉客云后台「货品资料 → Excel 导入 → 选『更新已有货品』 → 上传」
4. 完成后跑一次本地 `erp.storage.goodslist` 增量同步, `sku_master.out_sku_code`
   自动刷新
5. 之后所有 4 字段 API 反写一律走通

如果运营拒绝补码: 仍可单走 flag step (规格标记 1 字段) — 反写队列分流后会
独立推送 flag, 其他 3 字段会显式提示"需补外部编码"而不是静默失败.

## 接口订阅 checklist (吉客云应用市场)

部署到新商家时, 确保这 3 个 API 都已订阅:

- ✅ `erp.goods.skuimportbatch` (批量创建/更新货品 - 主力)
- ✅ `erp-goods.goods.batchupdateflagbyskubarcode` (规格标记)
- ✅ `erp.goods.customfield` (自定义字段元数据, 用于初次部署)

不订阅会返回 `0130020310 未查询到应用或应用未订阅此 API`.

## 调试脚本

| 脚本 | 用途 |
|---|---|
| `scripts/probe_erp_goods_update.py` | 任意 method + biz 探针, 改 METHOD_CASES |
| `scripts/verify_writeback.py` | 用 `erp.storage.goodslist` 回读验证反写是否落库 |
| `scripts/dump_customfield.py` | dump 所有自定义字段 → 确认 skuField1/8 映射 |

环境变量: `JACKYUN_APP_KEY` / `JACKYUN_APP_SECRET` 从 settings 注入.

## 历史踩坑时间线

- D-7: 用 `erp.storage.goods.update`, 报 0130020310 未订阅
- D-5: 改成 `erp.goods.update`, 报 0030099001 JSON 解析错 (biz 不是 list)
- D-4: biz 改成 list, 框架返回 0031300000 "成功", 但回读没更新
- D-3: 实测确认 `erp.goods.update` 是 goods 维度, 完全丢 sku 字段
- D-2: 试 `erp-goods-online.item.batchupdateitem` (OMS), schema 过重
- D-1: 试 `erp.goods.skuimportbatch`, 报 0031310400 条码重复 (INSERT 路径)
- D0: 用户提供 2026-05-11 新文档明确 outSkuCode 是 UPSERT 锚, 闭环
