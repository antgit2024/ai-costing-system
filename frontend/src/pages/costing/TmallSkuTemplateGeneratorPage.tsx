import { useMemo, useState } from 'react'
import { Alert, Button, Card, Divider, Input, message, Space, Switch, Table, Tag, Typography, Upload } from 'antd'
import { DownloadOutlined, EyeOutlined, PlusOutlined, UploadOutlined } from '@ant-design/icons'
import * as XLSX from 'xlsx'

import {
  exportTmallSkuTemplateXlsx,
  previewTmallSkuTemplate,
  type TmallColorOption,
  type TmallSizeOption,
  type TmallSkuCell,
  type TmallSkuRow,
} from '@/services/planner'

const { Text } = Typography

const uid = () => Math.random().toString(36).slice(2, 10)

const downloadBlob = (blob: Blob, filename: string) => {
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(url)
}

type ColorRow = TmallColorOption & { enabledSizes: Record<string, boolean> }

const readFileAsArrayBuffer = (file: File): Promise<ArrayBuffer> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as ArrayBuffer)
    reader.onerror = () => reject(reader.error ?? new Error('读取文件失败'))
    reader.readAsArrayBuffer(file)
  })

const normalizeCellText = (v: unknown) => String(v ?? '').replace(/\s+/g, ' ').trim()

type HeaderIndex = {
  headerRowIndex: number
  colorCol: number
  sizeCol: number
  merchantSkuCol: number
  statusCol: number
}

const findHeaderIndex = (ws: XLSX.WorkSheet): HeaderIndex | null => {
  const ref = ws['!ref']
  if (!ref) return null
  const range = XLSX.utils.decode_range(ref)
  for (let r = range.s.r; r <= Math.min(range.e.r, range.s.r + 50); r++) {
    const rowValues: string[] = []
    for (let c = range.s.c; c <= range.e.c; c++) {
      const addr = XLSX.utils.encode_cell({ r, c })
      rowValues.push(normalizeCellText((ws as any)[addr]?.v))
    }
    const idx = (label: string) => rowValues.findIndex((x) => x === label)
    const colorCol = idx('颜色分类')
    const sizeCol = idx('尺寸')
    const merchantSkuCol = idx('商家编码')
    const statusCol = idx('是否上架')
    if ([colorCol, sizeCol, merchantSkuCol, statusCol].every((x) => x >= 0)) {
      return {
        headerRowIndex: r,
        colorCol: range.s.c + colorCol,
        sizeCol: range.s.c + sizeCol,
        merchantSkuCol: range.s.c + merchantSkuCol,
        statusCol: range.s.c + statusCol,
      }
    }
  }
  return null
}

export default function TmallSkuTemplateGeneratorPage() {
  const [merchantSkuPrefix, setMerchantSkuPrefix] = useState('BZPB008XXXXX-')
  const [merchantSkuSuffix, setMerchantSkuSuffix] = useState('')

  const [sizes, setSizes] = useState<TmallSizeOption[]>([
    { key: 'size_1', label: '枕芯+枕套', size_code: 'C1' },
    { key: 'size_2', label: '枕套', size_code: 'C2' },
  ])

  const [colors, setColors] = useState<ColorRow[]>([
    { key: 'c1', label: 'Q25122501A黄金绒背面纯色（红色毛球） 45X45', width_cm: 45, height_cm: 45, enabledSizes: { size_1: true, size_2: true } },
  ])

  const [previewRows, setPreviewRows] = useState<TmallSkuRow[]>([])
  const [previewTotal, setPreviewTotal] = useState(0)
  const [loadingPreview, setLoadingPreview] = useState(false)
  const [loadingExport, setLoadingExport] = useState(false)
  const [templateFile, setTemplateFile] = useState<File | null>(null)
  const [loadingFill, setLoadingFill] = useState(false)
  const [overwriteExisting, setOverwriteExisting] = useState(true)

  const cells: TmallSkuCell[] = useMemo(() => {
    const out: TmallSkuCell[] = []
    for (const c of colors) {
      for (const s of sizes) {
        out.push({
          color_key: c.key,
          size_key: s.key,
          enabled: c.enabledSizes?.[s.key] !== false,
        })
      }
    }
    return out
  }, [colors, sizes])

  const payload = useMemo(
    () => ({
      sizes,
      colors: colors.map(({ enabledSizes, ...rest }) => rest),
      cells,
      merchant_sku_prefix: merchantSkuPrefix,
      merchant_sku_suffix: merchantSkuSuffix,
    }),
    [sizes, colors, cells, merchantSkuPrefix, merchantSkuSuffix],
  )

  const doPreview = async () => {
    setLoadingPreview(true)
    try {
      const resp = await previewTmallSkuTemplate(payload)
      setPreviewRows(resp.rows ?? [])
      setPreviewTotal(resp.total_rows ?? 0)
      message.success(`已生成预览：${resp.total_rows ?? 0} 行`)
    } catch (e: any) {
      message.error(String(e?.message ?? e))
    } finally {
      setLoadingPreview(false)
    }
  }

  const doExport = async () => {
    setLoadingExport(true)
    try {
      const blob = await exportTmallSkuTemplateXlsx(payload)
      downloadBlob(blob, 'tmall_buyi_sku_template.xlsx')
      message.success('已导出 xlsx')
    } catch (e: any) {
      message.error(String(e?.message ?? e))
    } finally {
      setLoadingExport(false)
    }
  }

  const doFillTemplateAndDownload = async () => {
    if (!templateFile) {
      message.warning('请先上传天猫官方模板（xls/xlsx）')
      return
    }
    setLoadingFill(true)
    try {
      const [buf, resp] = await Promise.all([readFileAsArrayBuffer(templateFile), previewTmallSkuTemplate(payload)])

      // Build lookup: (color_label, size_label) -> row
      const lookup = new Map<string, TmallSkuRow>()
      for (const r of resp.rows ?? []) {
        const k = `${normalizeCellText(r.color_label)}||${normalizeCellText(r.size_label)}`
        lookup.set(k, r)
      }

      const wb = XLSX.read(buf, { type: 'array', cellStyles: true })
      const firstSheetName = wb.SheetNames?.[0]
      if (!firstSheetName) throw new Error('模板无工作表（Sheet）')
      const ws = wb.Sheets[firstSheetName]
      if (!ws) throw new Error('模板工作表读取失败')

      const header = findHeaderIndex(ws)
      if (!header) {
        throw new Error('未在模板中找到表头列：颜色分类/尺寸/商家编码/是否上架（请确认上传的是天猫官方SKU模板）')
      }

      const range = XLSX.utils.decode_range(ws['!ref'] as string)
      let filled = 0
      let skipped = 0
      let unmatched = 0

      for (let r = header.headerRowIndex + 1; r <= range.e.r; r++) {
        const colorAddr = XLSX.utils.encode_cell({ r, c: header.colorCol })
        const sizeAddr = XLSX.utils.encode_cell({ r, c: header.sizeCol })
        const colorVal = normalizeCellText((ws as any)[colorAddr]?.v)
        const sizeVal = normalizeCellText((ws as any)[sizeAddr]?.v)

        // stop early on trailing empty rows
        if (!colorVal && !sizeVal) continue

        const k = `${colorVal}||${sizeVal}`
        const target = lookup.get(k)
        if (!target) {
          unmatched++
          continue
        }

        const merchantAddr = XLSX.utils.encode_cell({ r, c: header.merchantSkuCol })
        const statusAddr = XLSX.utils.encode_cell({ r, c: header.statusCol })

        const existingMerchant = normalizeCellText((ws as any)[merchantAddr]?.v)
        const existingStatus = normalizeCellText((ws as any)[statusAddr]?.v)
        if (!overwriteExisting && (existingMerchant || existingStatus)) {
          skipped++
          continue
        }

        const merchantSku = String(target.merchant_sku ?? '').trim()
        const skuStatus = Number(target.sku_status ?? 0)

        if (merchantSku) {
          const cell: any = (ws as any)[merchantAddr] ?? {}
          cell.t = 's'
          cell.v = merchantSku
          ;(ws as any)[merchantAddr] = cell
        }
        {
          const cell: any = (ws as any)[statusAddr] ?? {}
          cell.t = 'n'
          cell.v = skuStatus
          ;(ws as any)[statusAddr] = cell
        }
        filled++
      }

      const out = XLSX.write(wb, { bookType: 'xlsx', type: 'array' })
      const blob = new Blob([out], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })
      const base = templateFile.name.replace(/\.(xlsx|xls)$/i, '')
      downloadBlob(blob, `${base}_filled.xlsx`)
      message.success(`已填充并导出：填充 ${filled} 行；未匹配 ${unmatched} 行；跳过 ${skipped} 行`)
    } catch (e: any) {
      message.error(String(e?.message ?? e))
    } finally {
      setLoadingFill(false)
    }
  }

  return (
    <div style={{ padding: 16 }}>
      <Space direction="vertical" style={{ width: '100%' }} size={12}>
        <Card
          title="天猫布艺 SKU规格生成器（MVP）"
          extra={<Tag color="gold">颜色分类=图案/工艺款式；尺寸可按款式禁用</Tag>}
        >
          <Space direction="vertical" style={{ width: '100%' }} size={10}>
            <Space wrap size={8}>
              <Text type="secondary">商家编码前缀</Text>
              <Input style={{ width: 260 }} value={merchantSkuPrefix} onChange={(e) => setMerchantSkuPrefix(e.target.value)} />
              <Text type="secondary">后缀</Text>
              <Input style={{ width: 160 }} value={merchantSkuSuffix} onChange={(e) => setMerchantSkuSuffix(e.target.value)} />
            </Space>

            <Divider style={{ margin: '8px 0' }} />

            <Space wrap size={8} style={{ width: '100%', justifyContent: 'space-between' }}>
              <Space wrap size={8}>
                <Button icon={<EyeOutlined />} loading={loadingPreview} onClick={doPreview}>
                  生成预览
                </Button>
                <Button icon={<DownloadOutlined />} type="primary" loading={loadingExport} onClick={doExport}>
                  导出 xlsx
                </Button>
                <Text type="secondary">（导出包含 sheet1 数据 + sheet2 字段映射）</Text>
              </Space>
              <Text type="secondary">预览行数：{previewTotal}</Text>
            </Space>

            <Divider style={{ margin: '8px 0' }} />

            <Alert
              type="info"
              showIcon
              message="天猫模板填充（推荐流程）"
              description={
                <div>
                  <div>销售属性（颜色分类/尺寸）需要先在天猫后台建立，模板里不可编辑。</div>
                  <div>本工具用于把你配置好的“商家编码 / 是否上架(0/1)”批量回填到天猫官方模板，再下载回传。</div>
                </div>
              }
            />

            <Space wrap size={8} style={{ marginTop: 8 }}>
              <Upload
                accept=".xlsx,.xls"
                maxCount={1}
                showUploadList={false}
                beforeUpload={(file) => {
                  setTemplateFile(file)
                  message.success(`已选择模板：${file.name}`)
                  return false
                }}
              >
                <Button icon={<UploadOutlined />}>上传天猫官方模板</Button>
              </Upload>
              <Text type="secondary">{templateFile ? templateFile.name : '未选择文件'}</Text>
              <Divider type="vertical" />
              <Text type="secondary">覆盖已有值</Text>
              <Switch checked={overwriteExisting} onChange={setOverwriteExisting} />
              <Button type="primary" loading={loadingFill} disabled={!templateFile} onClick={doFillTemplateAndDownload}>
                一键填充并下载
              </Button>
            </Space>
          </Space>
        </Card>

        <Card
          title="尺寸选项（全局并集）"
          extra={
            <Button
              icon={<PlusOutlined />}
              onClick={() => setSizes((prev) => [...prev, { key: `size_${uid()}`, label: '新尺寸', size_code: '' }])}
            >
              添加尺寸
            </Button>
          }
        >
          <Space direction="vertical" style={{ width: '100%' }} size={8}>
            {sizes.map((s, i) => (
              <Space key={s.key} wrap size={8} style={{ width: '100%' }}>
                <Text type="secondary">尺寸</Text>
                <Input
                  style={{ width: 240 }}
                  value={s.label}
                  onChange={(e) =>
                    setSizes((prev) => prev.map((x, idx) => (idx === i ? { ...x, label: e.target.value } : x)))
                  }
                />
                <Text type="secondary">编码段</Text>
                <Input
                  style={{ width: 120 }}
                  value={s.size_code ?? ''}
                  onChange={(e) =>
                    setSizes((prev) => prev.map((x, idx) => (idx === i ? { ...x, size_code: e.target.value } : x)))
                  }
                />
              </Space>
            ))}
          </Space>
        </Card>

        <Card
          title="颜色分类（图案/工艺款式）+ 是否上架矩阵"
          extra={
            <Button
              icon={<PlusOutlined />}
              onClick={() =>
                setColors((prev) => [
                  ...prev,
                  {
                    key: `c_${uid()}`,
                    label: '新款式',
                    width_cm: 45,
                    height_cm: 45,
                    enabledSizes: Object.fromEntries(sizes.map((s) => [s.key, true])),
                  },
                ])
              }
            >
              添加款式
            </Button>
          }
        >
          <Table
            size="small"
            pagination={false}
            rowKey="key"
            dataSource={colors}
            columns={[
              {
                title: '颜色分类（图案/工艺）',
                dataIndex: 'label',
                render: (_: any, r: ColorRow, idx: number) => (
                  <Input
                    value={r.label}
                    onChange={(e) =>
                      setColors((prev) => prev.map((x, i) => (i === idx ? { ...x, label: e.target.value } : x)))
                    }
                  />
                ),
              },
              {
                title: '宽*高(cm)',
                width: 140,
                render: (_: any, r: ColorRow, idx: number) => (
                  <Space size={6}>
                    <Input
                      style={{ width: 54 }}
                      value={String(r.width_cm ?? '')}
                      onChange={(e) =>
                        setColors((prev) =>
                          prev.map((x, i) => (i === idx ? { ...x, width_cm: Number(e.target.value || 0) } : x)),
                        )
                      }
                    />
                    <Text type="secondary">*</Text>
                    <Input
                      style={{ width: 54 }}
                      value={String(r.height_cm ?? '')}
                      onChange={(e) =>
                        setColors((prev) =>
                          prev.map((x, i) => (i === idx ? { ...x, height_cm: Number(e.target.value || 0) } : x)),
                        )
                      }
                    />
                  </Space>
                ),
              },
              ...sizes.map((s) => ({
                title: s.label,
                width: 110,
                align: 'center' as const,
                render: (_: any, r: ColorRow, idx: number) => (
                  <Switch
                    checked={r.enabledSizes?.[s.key] !== false}
                    onChange={(v) =>
                      setColors((prev) =>
                        prev.map((x, i) =>
                          i === idx ? { ...x, enabledSizes: { ...(x.enabledSizes ?? {}), [s.key]: v } } : x,
                        ),
                      )
                    }
                  />
                ),
              })),
            ]}
          />
          <div style={{ marginTop: 8 }}>
            <Text type="secondary">说明：每个开关对应导出表格里的“是否上架”（开=1，关=0，平台显示为灰色不可选但可重新启用）。</Text>
          </div>
        </Card>

        <Card title="预览（前 50 行）" extra={<Text type="secondary">共 {previewTotal} 行</Text>}>
          <Table
            size="small"
            pagination={false}
            rowKey={(_, i) => `r-${i}`}
            dataSource={(previewRows ?? []).slice(0, 50)}
            columns={[
              { title: '颜色分类', dataIndex: 'color_label' },
              { title: '尺寸', dataIndex: 'size_label', width: 160 },
              { title: '商家编码', dataIndex: 'merchant_sku', width: 220 },
              { title: '是否上架', dataIndex: 'sku_status', width: 90 },
            ]}
          />
        </Card>
      </Space>
    </div>
  )
}

