# 方案派单简报：POD 个性化定制（先印布）Phase0（以抱枕为例）

> 背景：你们系统已有“标准模型版本化 + spec 解析 + 动态 BOM + BOM 快照/异常队列/重试”。现在要新增 POD：用户上传图片→效果图→确稿→印刷稿→工厂下载生产→回传 ERP。  
> 本 Phase0 明确：**先印布**、工厂需要**裁切线/定位标（可预留 CMYK/ICC）**、**先不做 AI**、生产包结果通过 **API 回传 ERP**。

---

## 1) Phase0 目标（最小可验收闭环）

- **用户侧**：上传图片 + 简单编辑（缩放/旋转/裁剪）+ 生成效果图预览 + 确稿
- **后台**：确稿后生成 **印刷稿（print-ready）**（含裁切线/定位标/出血/安全区）+ 生成 BOM 快照 + 生成生产包下载链接
- **工厂侧**：下载生产包（至少包含印刷稿 + 生产指令）
- **ERP 回传**：回传 production_pack_id + 下载链接 + trace_id（可选回传成本摘要）

---

## 2) 口径必须“版本化/快照化”的东西（不可省）

- **模型版本**：确稿时必须锁定 `product_model_version_id`（只允许 published standard 参与生产）
- **印刷模板**（按结构 slot）：成品尺寸、裁片外框、出血、安全区、缝边吃进、裁切线、定位标、镜像规则、ICC/输出参数
- **设计稿参数**：用户素材 hash + transform（裁剪框/缩放/旋转/对齐）
- **产物文件**：效果图与印刷稿必须可重跑（job 记录 input/output + workflow_version）

参考蓝图（已新增）：`DOC/costing/blueprints/pod_personalization_print_pipeline_phase0.md`

---

## 3) 小程序接入结论（你问的“本地服务器能用吗”）

### 3.1 结论
- **仅内网/本地IP**：小程序端基本不可用（小程序请求必须命中“合法域名”且公网 HTTPS）
- **本地服务器通过公网域名反代暴露 + HTTPS + 鉴权**：可用性很高

### 3.2 最小建议
- 上传图片：优先直传对象存储（OSS/S3），后端只拿 `storage_key` 拉取渲染
- 生成任务：必须异步 job（小程序请求时长/并发受限），小程序轮询 job 状态
- 工厂下载：建议 PC/Web/企业微信承载，不建议在小程序里下载大文件

---

## 4) Phase0 任务拆解（按角色）

> 你们可按现有 Agent 体系拆：@Backend Agent / @Frontend Agent / @Ops Agent / @Docs Agent。

### A. Backend（新增 POD 领域最小接口，先不碰 AI）
- **新增对象/存储**：
  - ArtworkAsset（素材元数据 + 存储 key + hash）
  - PrintTemplate（按 `product_model_version_id + structure_slot` 版本化）
  - ArtworkJob（mockup_render / print_export）
  - ProductionPack（订单行引用 + 印刷文件列表 + bom_snapshot_id + trace）
- **新增接口（建议最小）**：
  - 上传素材（或换成“拿 storage_key 注册素材”）
  - 生成效果图 job + 查询 job
  - 确稿：创建 ProductionPack + 触发印刷稿 job
  - 生产包下载（鉴权 + 可审计）
  - ERP 回传：`POST /erp/writeback/production-pack`（或先用 webhook 回调表）
- **验收要点**：
  - 1 个订单行：确稿→印刷稿生成成功→生产包可下载→BOM 快照可查→回传 ERP 成功

### A.1（下一阶段建议 / Phase1）AI「人人都设计师」的正确落点（别把生产几何交给 AI）
- **AI 应该负责**：生成/风格化“素材图”（RGB），以及去背景/扩图/高清化/构图建议
- **系统必须确定性负责**：出血/安全区/缝边吃进/裁切线/定位标/镜像规则/ICC 转换/尺寸标注（全部来自 PrintTemplate）
- **硬门槛**：确稿前必须通过“像素不足/违规内容/版权声明/色彩 profile”检查

### B. Frontend（先做 Web/H5，UI 只要可用）
- **页面最小**：
  - 选标准模型版本（只显示 published standard）
  - 上传图片（显示分辨率提示）
  - 简单编辑（裁剪框/缩放/旋转/居中；先不做复杂滤镜）
  - 生成预览/确稿（展示 job 状态与最终印刷稿缩略图）
- **验收要点**：
  - 上传→预览→确稿全流程可走通；失败能看到错误并可重试

### C. Ops（域名/存储/权限）
- **必须具备**：
  - 公网 HTTPS 域名（小程序合法域名）
  - 对象存储（图片/印刷稿），带权限控制（短期签名 URL 或受控下载）
  - 后端异步任务 worker（可先用内置 BackgroundTasks，后续再上队列）

### D. Docs（把“工厂要什么文件”写成模板）
- 印刷稿规范：出血/安全区/裁切线/定位标/色彩配置（ICC）
- 生产包字段与追溯ID规范：订单行→production_pack_id→bom_snapshot_id→文件列表

---

## 5) 本 Phase0 的唯一验收命令（文档存在性）

`grep -nF "POD 个性化定制（先印布）— Phase0 落地蓝图（以抱枕为例）" DOC/costing/blueprints/pod_personalization_print_pipeline_phase0.md`

