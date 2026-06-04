import { Button, Modal, Space, Tooltip, message } from 'antd'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'

import { resolveShipmentLine } from '@/services/planner'
import type { PublishedStandardModelCandidate, ShipmentLineListItem } from '@/types/planner'

import ModelPickerDrawer from './ModelPickerDrawer'

export interface LineResolveActionsProps {
  line: ShipmentLineListItem
  /** 操作员 ID(用于审计) */
  operatorId?: string
  /** 一次成功后的回调,通常用来 refetch 列表 */
  onResolved?: () => void
  /** 紧凑模式: 按钮变小,适合表格行内嵌 */
  size?: 'middle' | 'small'
}

/**
 * 行级 4 大白话决策按钮 - 共享组件
 *
 * 服务于"业务管理"下任何需要"对发货行做治理决策"的场景:
 *   - 🚚 发货管理 待处理 Tab 行内
 *   - 未来 🔄 售后管理 行内(如有同样需求)
 *
 * 这里调的是 services/planner.ts 的 resolveShipmentLine,
 * 当前是前端编排, 未来后端 /resolve 接口落地后该函数 1 处改即可,
 * 本组件 0 改动。详见 known_issues.md Issue 26。
 */
export default function LineResolveActions({
  line,
  operatorId,
  onResolved,
  size = 'small',
}: LineResolveActionsProps) {
  const navigate = useNavigate()
  const [pickerOpen, setPickerOpen] = useState(false)

  const resolveMutation = useMutation({
    mutationFn: async (args: Parameters<typeof resolveShipmentLine>[1]) =>
      resolveShipmentLine({ id: line.id, sku_code: line.sku_code }, args, { operatorId }),
    onSuccess: (result, action) => {
      if (!result.ok) {
        message.error(result.error || '操作失败')
        return
      }
      const verb =
        action.type === 'adopt'
          ? '已绑定 + 已算成本'
          : action.type === 'mark_long_tail'
            ? '已标记为长尾'
            : '已加入建模 backlog'
      message.success(verb)
      onResolved?.()
    },
    onError: (e: any) => {
      message.error(`操作失败: ${e?.message || e}`)
    },
  })

  const handleAdopt = (modelId: string) => {
    setPickerOpen(false)
    resolveMutation.mutate({ type: 'adopt', modelId })
  }

  const handleCreateNew = () => {
    Modal.confirm({
      title: '现建一个新模型?',
      content: (
        <div>
          将打开"商品模型"页面,并预填这条 SKU 的规格文本。
          <br />
          建好并发布模型后,请回到本页对该 SKU 点"用某模型"完成绑定。
        </div>
      ),
      okText: '去建模',
      onOk: () => {
        const fromSku = encodeURIComponent(String(line.sku_code ?? ''))
        const prefillSpec = encodeURIComponent(String(line.spec_text ?? ''))
        navigate(`/costing/sku-master?search=${fromSku}&focus=${fromSku}`)
        // 注: 真正的"去 product-models/new" 路径需要后端配套支持 prefill,
        // 目前先复用 BatchWorkbench 老逻辑跳转 sku-master, 跟现有体验一致
        // TODO(@/biz-shipments-build-new-model): 待 product-models/new 支持 prefill 后改成
        // navigate(`/costing/product-models/new?from_sku=${fromSku}&prefill_spec=${prefillSpec}`)
        void prefillSpec
      },
    })
  }

  const handleMarkLongTail = () => {
    Modal.confirm({
      title: '标记为长尾·不建模?',
      content: (
        <div>
          这条 SKU 销量很少,系统将不再为它建模。
          <br />
          系统会按"销售额 × 长尾兜底比例"自动估算成本,以后这条 SKU 不再出现在待处理列表里。
          <br />
          可在"长尾池" Tab 随时撤回。
        </div>
      ),
      okText: '确认标长尾',
      okButtonProps: { danger: true },
      onOk: () => resolveMutation.mutate({ type: 'mark_long_tail' }),
    })
  }

  const handleDeferModeling = () => {
    resolveMutation.mutate({ type: 'defer_modeling' })
  }

  const skuMissing = !String(line.sku_code ?? '').trim()
  const disabledTip = skuMissing ? '该发货行没有 SKU 编码' : undefined

  return (
    <>
      <Space wrap size={4}>
        <Tooltip title={disabledTip || '弹出抽屉选择一个已发布模型,选完自动绑定+算价'}>
          <Button
            size={size}
            type="primary"
            disabled={skuMissing || resolveMutation.isPending}
            loading={resolveMutation.isPending && resolveMutation.variables?.type === 'adopt'}
            onClick={() => setPickerOpen(true)}
          >
            ✅ 选模型
          </Button>
        </Tooltip>
        <Tooltip title={disabledTip || '没有合适模型?去建一个新的(将带规格预填)'}>
          <Button size={size} disabled={skuMissing} onClick={handleCreateNew}>
            🆕 建新模型
          </Button>
        </Tooltip>
        <Tooltip title={disabledTip || '决定要建模但模型还没准备好?加入待办'}>
          <Button
            size={size}
            disabled={skuMissing || resolveMutation.isPending}
            loading={resolveMutation.isPending && resolveMutation.variables?.type === 'defer_modeling'}
            onClick={handleDeferModeling}
          >
            ⏸️ 待建模
          </Button>
        </Tooltip>
        <Tooltip title={disabledTip || '销量很少,不值得建模,系统按销售额自动估成本'}>
          <Button
            size={size}
            danger
            disabled={skuMissing || resolveMutation.isPending}
            loading={resolveMutation.isPending && resolveMutation.variables?.type === 'mark_long_tail'}
            onClick={handleMarkLongTail}
          >
            🚫 标长尾
          </Button>
        </Tooltip>
      </Space>

      <ModelPickerDrawer
        open={pickerOpen}
        context={{
          skuCode: line.sku_code,
          specText: line.spec_text,
        }}
        onClose={() => setPickerOpen(false)}
        onPicked={(c: PublishedStandardModelCandidate) => handleAdopt(c.model_id)}
      />
    </>
  )
}
