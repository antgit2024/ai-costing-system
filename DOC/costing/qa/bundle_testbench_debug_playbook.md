# 套装测试台 Debug 自助排障手册

适用页面：`/costing/product-listing` → **套装测试**

目标：不依赖任何 AGENT/上下文，你自己就能定位“为什么没替换/为什么命中错了”。

## 1) 怎么开启 Debug

- 打开 **Debug**（按钮显示“已开启（返回组件明细）”）
- 点击 **套装：预演 BOM（B:编码）**
- 点击 **复制诊断**：会把本次 debug 的完整 JSON 复制到剪贴板（可发给任何人/新 AGENT）

## 2) 你要看哪三块

### A. 组件的 runtime_tokens

路径：`components[i].trace.runtime_tokens`

- **缺 token**：说明短语/筛选没有把词注入到组件里（或短语不匹配）
- **有 token 但仍未替换**：继续看 B

### B. matched_variants（命中链路）

路径：`components[i].trace.matched_variants[]`

重点字段：
- `base_line_id`：哪条基准物料行
- `variant_id`：哪条变体规则
- `matched`：是否命中
- `reason`：未命中原因（常见：`disabled`）
- `effect`：命中后的效果（replace/remove/add）

常见情况：
- **reason=disabled**：规则存在但被禁用 → 去“物料变体”面板启用该规则
- **matched=false 且无 reason**：条件不满足（token/尺寸/面积/周长/直径）→ 看 token/尺寸是否正确
- **reason=forced_by_bundle**：说明强制模式已生效（按套装强制指定）

### C. 最终 BOM 与 “你以为应该没有的物料”

路径：`merged.final_material_lines`

如果你看到“不该出现”的物料：
- 回到 `matched_variants` 找同一个 `base_line_id` 是否有命中的替换规则
- 若替换规则存在但 `disabled`，则就是“规则被禁用导致兜底生效”

## 3) 典型问题对照表

- **套装模板找不到（400 未找到套装模板）**
  - 以前可能是 `B-XXXX` 后面跟了空格文本导致编码被带尾巴（已修复）
  - 建议写法：`xxx(B-XXXXAA)` 或在短码后加括号

- **某个布料没被替换（仍显示兜底黄金绒）**
  - 99% 是 `matched_variants` 里该替换规则 `reason=disabled`
  - 处理：启用对应变体规则

- **尺寸 30×50 仍命中 50×50**
  - 强制模式下检查是否存在 `forced_by_bundle`
  - 解析模式下检查二级规则区间是否重叠/priority 是否正确


