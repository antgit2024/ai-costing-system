# 智能成本核算系统 - Cursor 终极开发指南

## 1.0 系统概述

### 1.1 核心目标

本系统旨在替代传统的、基于静态BOM的成本核算模式，通过“公式化计算”和“变体规则”实现对大规模SKU的敏捷、精准、自动化的成本核算与物料消耗统计。

### 1.2 最终架构

-   **核心**：所有业务逻辑、数据存储、计算任务均在**本地阿里云服务器**上完成。
-   **数据源**：
    -   **宜搭**：作为“基础物料信息”（编码、名称、最新采购价）的只读数据源。
    -   **吉客云ERP / Excel**：作为“销售订单”和“退货单”的业务数据源。

### 1.3 技术栈建议

-   **后端**：Python (FastAPI / Flask)
-   **数据库**：MySQL / PostgreSQL
-   **缓存**：Redis (可选，用于缓存常用配置)
-   **前端**：Vue / React (用于开发管理后台)

---

## 2.0 数据库设计 (for Cursor)

请根据以下设计在数据库中创建相应的表。所有表建议使用`InnoDB`引擎，`utf8mb4`字符集。

| 表名 | 描述 |
| :--- | :--- |
| `materials` | 物料基础信息表（从宜搭同步） |
| `processes` | 工序表（本地维护） |
| `process_materials` | 工序-物料关联表 |
| `process_labors` | 工序-人工关联表 |
| `product_models` | 产品模型表 |
| `model_processes` | 模型-工序关联表 |
| `variant_rules` | 变体规则表（极简版） |
| `sku_model_mapping` | SKU-模型映射表 |
| `sales_orders` | 销售订单表（从ERP/Excel导入） |
| `order_items` | 订单行项目表 |
| `order_costs` | 订单成本表 |
| `order_material_consumption` | 订单物料消耗明细表 |

### 2.1 `materials` 表

| 字段名 | 类型 | 描述 |
| :--- | :--- | :--- |
| `material_id` | INT, PK, AI | 物料ID |
| `material_code` | VARCHAR(50), UNIQUE | 物料编码 |
| `material_name` | VARCHAR(255) | 物料名称 |
| `unit_price` | DECIMAL(10, 2) | 最新采购单价 |
| `unit` | VARCHAR(10) | 单位（如：米, 平方, 个） |
| `updated_at` | DATETIME | 更新时间 |

### 2.2 `processes` 表

| 字段名 | 类型 | 描述 |
| :--- | :--- | :--- |
| `process_id` | INT, PK, AI | 工序ID |
| `process_code` | VARCHAR(50), UNIQUE | 工序编码 |
| `process_name` | VARCHAR(255) | 工序名称 |

### 2.3 `process_materials` 表

| 字段名 | 类型 | 描述 |
| :--- | :--- | :--- |
| `id` | INT, PK, AI | 主键 |
| `process_id` | INT, FK | 工序ID |
| `material_id` | INT, FK | 物料ID |
| `calc_method` | ENUM('周长', '面积', '数量') | 计量方式 |
| `default_quantity` | DECIMAL(10, 4) | 默认用量（基于1x1米标准尺寸） |
| `loss_rate` | DECIMAL(5, 2) | 耗损率（%） |

### 2.4 `process_labors` 表

| 字段名 | 类型 | 描述 |
| :--- | :--- | :--- |
| `id` | INT, PK, AI | 主键 |
| `process_id` | INT, FK | 工序ID |
| `labor_name` | VARCHAR(255) | 人工项目名称 |
| `calc_method` | ENUM('周长', '面积', '数量') | 计量方式 |
| `unit_price` | DECIMAL(10, 2) | 人工单价 |
| `default_quantity` | DECIMAL(10, 4) | 默认用量（基于1x1米标准尺寸） |

### 2.5 `product_models` 表

| 字段名 | 类型 | 描述 |
| :--- | :--- | :--- |
| `model_id` | INT, PK, AI | 模型ID |
| `model_code` | VARCHAR(50), UNIQUE | 模型编码 |
| `model_name` | VARCHAR(255) | 模型名称 |
| `calc_mode` | ENUM('比例', '一口价', '独立') | 计算模式 |
| `fixed_price` | DECIMAL(10, 2) | 一口价模式下的固定价格 |

### 2.6 `model_processes` 表

| 字段名 | 类型 | 描述 |
| :--- | :--- | :--- |
| `id` | INT, PK, AI | 主键 |
| `model_id` | INT, FK | 模型ID |
| `process_id` | INT, FK | 工序ID |

### 2.7 `variant_rules` 表

| 字段名 | 类型 | 描述 |
| :--- | :--- | :--- |
| `rule_id` | INT, PK, AI | 规则ID |
| `model_id` | INT, FK | 模型ID |
| `trigger_type` | ENUM('字符匹配', '面积计算', '周长计算') | 触发类型 |
| `trigger_operator` | ENUM('包含', '等于', '大于', '小于') | 运算符 |
| `trigger_value` | VARCHAR(255) | 触发值 |
| `action_type` | ENUM('替换物料', '添加物料') | 执行动作 |
| `target_material_id` | INT, FK | 目标物料ID |
| `new_material_id` | INT, FK | 新物料ID |

### 2.8 `sku_model_mapping` 表

| 字段名 | 类型 | 描述 |
| :--- | :--- | :--- |
| `id` | INT, PK, AI | 主键 |
| `sku_code` | VARCHAR(50), UNIQUE | SKU编码 |
| `model_id` | INT, FK | 模型ID |

---

## 3.0 核心模块与开发任务 (for Cursor)

### 3.1 模块一：数据输入与同步中心

-   **Task 1: 实现ERP/Excel订单导入**
    -   在管理后台提供Excel上传界面，并编写后端逻辑解析文件，存入`sales_orders`和`order_items`表。
    -   编写API同步逻辑，定时从吉客云ERP拉取订单，存入上述表。

-   **Task 2: 实现宜搭物料同步**
    -   编写定时任务，调用宜搭API，将物料信息更新到本地`materials`表。

### 3.2 模块二：管理后台 (Web UI)

-   **Task 3: 开发工序管理模块**
    -   实现对`processes`, `process_materials`, `process_labors`三张表的CRUD操作。

-   **Task 4: 开发产品模型管理模块**
    -   实现对`product_models`和`model_processes`两张表的CRUD操作。

-   **Task 5: 开发变体规则管理模块**
    -   在产品模型详情页下，实现对`variant_rules`表的CRUD操作。

-   **Task 6: 开发SKU-模型映射模块**
    -   实现对`sku_model_mapping`表的CRUD操作，支持批量绑定。

### 3.3 模块三：核心成本计算引擎

-   **Task 7: 编写核心计算算法 (Pseudo-code for Cursor)**

```python
def calculate_batch_order_costs(orders):
    for order in orders:
        # 1. 获取订单行项目
        order_items = db.query("SELECT * FROM order_items WHERE order_id = ?", order.id)
        total_order_cost = 0

        for item in order_items:
            # 2. 加载模型和基础物料/人工清单
            mapping = db.query("SELECT * FROM sku_model_mapping WHERE sku_code = ?", item.sku_code)[0]
            model = db.query("SELECT * FROM product_models WHERE model_id = ?", mapping.model_id)[0]

            # 如果是"一口价"或"独立"模式，直接使用固定价格或预设成本
            if model.calc_mode in ['一口价', '独立']:
                # ... (处理逻辑)
                continue

            # 3. 获取基础物料和人工清单
            base_materials = get_materials_for_model(model.id)
            base_labors = get_labors_for_model(model.id)

            # 4. 应用变体规则
            final_materials = apply_variant_rules(base_materials, model.id, item.sku_attributes, item.width, item.height)
            final_labors = base_labors # 极简版不变人工

            # 5. 计算单个SKU的成本
            material_cost = 0
            for material in final_materials:
                if material.calc_method == '周长':
                    consumed = (item.width + item.height) * 2 * material.default_quantity * (1 + material.loss_rate / 100)
                elif material.calc_method == '面积':
                    consumed = item.width * item.height * material.default_quantity * (1 + material.loss_rate / 100)
                else: # 数量
                    consumed = material.default_quantity
                
                material_cost += consumed * material.unit_price
                # 6. 记录物料消耗
                db.insert("order_material_consumption", {
                    'order_id': order.id,
                    'item_id': item.id,
                    'material_id': material.id,
                    'consumed_quantity': consumed * item.quantity,
                    'cost_at_consumption': consumed * material.unit_price * item.quantity
                })

            labor_cost = 0
            for labor in final_labors:
                # ... (类似逻辑计算人工成本)
            
            # 7. 计算总成本（含管理费）
            sub_total_cost = material_cost + labor_cost
            management_fee = sub_total_cost * 0.30
            total_sku_cost = sub_total_cost + management_fee
            total_order_cost += total_sku_cost * item.quantity

        # 8. 存储订单总成本
        db.insert("order_costs", {
            'order_id': order.id,
            'total_cost': total_order_cost
        })
```

### 3.4 模块四：统计分析中心

-   **Task 8: 开发物料消耗统计报表**
    -   编写SQL查询，按时间范围和`material_id`对`order_material_consumption`表进行GROUP BY汇总。

-   **Task 9: 开发成本差异分析报表**
    -   提供界面，让财务输入实际消耗，后端通过SQL查询理论消耗，计算差异。

-   **Task 10: 开发经营分析驾驶舱**
    -   编写复杂的JOIN查询，关联`sales_orders`, `order_items`, `order_costs`等多张表，按不同维度进行统计分析。

---

## 4.0 实施路线图

**第一阶段：基础架构与核心功能（4周）**
-   完成数据库设计 (Task: `2.0`)
-   开发管理后台核心功能 (Task: `3.2`)
-   开发数据同步服务 (Task: `3.1`)

**第二阶段：计算引擎与订单处理（3周）**
-   开发成本计算引擎 (Task: `3.3`)

**第三阶段：统计分析（2周）**
-   开发统计分析中心 (Task: `3.4`)

**第四阶段：数据初始化与试运行（2周）**
-   协助业务团队完成初始数据录入。
-   系统与现有流程并行试运行。

**第五阶段：全面上线与优化**
-   正式切换到新系统。
-   根据用户反馈，持续优化。

---

## 5.0 总结

这份终极开发指南整合了我们所有的讨论成果，为您提供了一个清晰、完整、详尽且可执行的开发蓝图。您可以将这份指南和相应的任务模块交给Cursor，让AI辅助您高效地完成开发工作。
