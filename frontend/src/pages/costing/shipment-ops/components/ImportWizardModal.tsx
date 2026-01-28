import { Alert, Button, DatePicker, Modal, Segmented, Space, Typography, Upload, Input, message } from 'antd'
import dayjs from 'dayjs'
import { useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { executeShipmentsFromPreview, previewShipmentsXlsx } from '@/services/planner'
import type { ShipmentImportBatch } from '@/types/planner'

type ShipmentImportPreviewResponse = Awaited<ReturnType<typeof previewShipmentsXlsx>>

const { Text } = Typography

const MB = 1024 * 1024

const formatBytes = (bytes: number): string => {
  const b = Number(bytes || 0)
  if (!Number.isFinite(b) || b <= 0) return '0B'
  if (b < 1024) return `${b}B`
  if (b < MB) return `${(b / 1024).toFixed(1)}KB`
  return `${(b / MB).toFixed(2)}MB`
}

const tryGetHttpStatus = (err: any): number | null => {
  const n = Number(err?.response?.status)
  return Number.isFinite(n) ? n : null
}

export default function ImportWizardModal(props: {
  open: boolean
  onClose: () => void
  onImported: (batchId?: string) => void
}) {
  const queryClient = useQueryClient()
  const [file, setFile] = useState<any>(null)
  const [exportDate, setExportDate] = useState<string | undefined>(undefined)
  const [requestedBy, setRequestedBy] = useState<string>('planner_user')
  const [mode, setMode] = useState<'2026' | '2025'>('2026')
  const [preview, setPreview] = useState<ShipmentImportPreviewResponse | null>(null)

  const fileSizeHint = useMemo(() => {
    const size = Number(file?.size ?? 0)
    if (!Number.isFinite(size) || size <= 0) return null
    return `文件大小：${formatBytes(size)}`
  }, [file])

  const previewMutation = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error('请先选择文件')
      const resp = await previewShipmentsXlsx({
        file,
        export_date: exportDate,
        requested_by: requestedBy?.trim() || undefined,
      })
      return resp
    },
    onSuccess: (res) => {
      setPreview(res)
      message.success('预览完成')
    },
    onError: (err: any) => {
      const status = tryGetHttpStatus(err)
      if (status === 413) {
        message.error('预览失败：文件过大（413）。建议拆分文件或让运维调大网关/Nginx client_max_body_size。')
      } else {
        message.error(`预览失败：${err?.response?.data?.detail ?? err?.message ?? 'unknown error'}`)
      }
    },
  })

  const executeMutation = useMutation({
    mutationFn: async () => {
      if (!preview?.preview_id) throw new Error('请先预览')
      const resp = await executeShipmentsFromPreview(
        {
          preview_id: preview.preview_id,
          file_name: preview.file_name,
          export_date: preview.export_date ?? exportDate,
          requested_by: requestedBy?.trim() || undefined,
          mode,
        },
        { timeoutMs: 60000 },
      )
      return resp
    },
    onSuccess: (batch: ShipmentImportBatch) => {
      message.success('执行完成：已生成导入单据')
      queryClient.invalidateQueries({ queryKey: ['shipments', 'import-batches'] })
      props.onImported(String((batch as any)?.id ?? '') || undefined)
      setPreview(null)
      setFile(null)
    },
    onError: (err: any) => {
      message.error(`执行失败：${err?.response?.data?.detail ?? err?.message ?? 'unknown error'}`)
    },
  })

  return (
    <Modal
      title="导入发货单（预览→执行）"
      open={props.open}
      onCancel={props.onClose}
      footer={null}
      width={920}
      destroyOnClose={false}
    >
      <Space direction="vertical" style={{ width: '100%' }} size={12}>
        <Alert
          type="info"
          showIcon
          message="操作建议"
          description="先预览看“未绑定/缺规格”等问题数，再执行导入。导入后到“待处理/成本快照”查看结果。"
        />

        <Space wrap>
          <Upload
            accept=".xlsx"
            maxCount={1}
            beforeUpload={(f) => {
              setFile(f as any)
              setPreview(null)
              return false
            }}
            onRemove={() => {
              setFile(null)
              setPreview(null)
            }}
          >
            <Button>选择文件（.xlsx）</Button>
          </Upload>
          <Text type="secondary">{file ? String(file.name) : '未选择'}</Text>
          {fileSizeHint ? <Text type="secondary">（{fileSizeHint}）</Text> : null}
        </Space>

        <Space wrap>
          <Space>
            <Text>导出日期</Text>
            <DatePicker
              allowClear
              value={exportDate ? dayjs(exportDate) : null}
              format="YYYY-MM-DD"
              onChange={(d) => setExportDate(d ? d.format('YYYY-MM-DD') : undefined)}
            />
          </Space>
          <Input
            style={{ width: 220 }}
            placeholder="operator/requested_by（可空）"
            value={requestedBy}
            onChange={(e) => setRequestedBy(e.target.value)}
          />
          <Segmented
            value={mode}
            onChange={(v) => setMode(v as any)}
            options={[
              { label: '2026（落快照）', value: '2026' },
              { label: '2025（不落快照）', value: '2025' },
            ]}
          />
          <Button type="primary" onClick={() => previewMutation.mutate()} loading={previewMutation.isPending} disabled={!file}>
            预览
          </Button>
          <Button
            type="primary"
            danger
            onClick={() => executeMutation.mutate()}
            loading={executeMutation.isPending}
            disabled={!preview?.preview_id}
          >
            执行导入
          </Button>
        </Space>

        {preview ? (
          <Alert
            type="info"
            showIcon
            message={`预览结果：总行${preview.total_rows}，可执行${preview.ready_rows}，未绑定${preview.unbound_sku_rows}，缺条码${preview.missing_sku_rows}，缺规格${preview.missing_spec_rows}`}
            description={<Text type="secondary">预览编号（preview_id）：{preview.preview_id}</Text>}
          />
        ) : null}
      </Space>
    </Modal>
  )
}

