# Frontend 闭环任务单：SKU 主档工作台（导入/查询/命中率）MVP

> 角色：@Frontend Agent  
> 目标：提供一个你能“看得见、用得上”的 SKU 主档工作台，用来先导入一部分 ERP 的 SKU 主档并验证匹配可行性；后续发货导入会优先命中该主档。  
> 核心口径：**发货关联键=货品条码（系统）**；`平台规格Id` 仅展示/追溯。

## 1) 页面与入口

- 新增页面：`/costing/sku-master`
- 菜单位置：“成本核算”下新增入口：`SKU 主档 / 商品关联`

## 2) 页面结构（只读+导入即可）

### 2.1 顶部导入卡片
- 上传：`ERP 理 平台商品列表.xlsx`
- 传参：`requested_by`（可选）
- 调用后端：`POST /api/planner/sku-master/import`
- 导入成功后自动刷新列表，并提示统计（inserted/updated/skipped/errors）

### 2.2 SKU 主档列表（分页）
列建议（Excel 列优先）：
- 货品条码（系统）（主键）
- 销售渠道
- 商品名称（网店）
- 商品编码（网店）
- 商品规格（网店）（spec_text，长文本省略）
- 平台商品Id（网店）
- 平台规格Id（网店）（仅展示）
- 匹配状态
- 最后更新时间
- 操作：查看详情抽屉（显示原始字段 + 图片预览地址 + metadata_json）

### 2.3 验证视角（MVP 可用 UI）
- 搜索框（按条码/名称/规格关键字）
- 简单筛选：渠道/匹配状态
- 显示“总数/本页/更新时间”

## 3) 前端契约（需要你新增到 planner.ts/types）

- `POST /api/planner/sku-master/import`（multipart：file + requested_by）
- `GET /api/planner/sku-master?page=&page_size=&search=&channel=&match_status=`

## 4) 验收命令（只给 1 条）

`npm -C frontend run build`


