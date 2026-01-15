import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Divider, Input, message, Select, Space, Switch, Table, Tag, Typography, Upload } from 'antd'
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

const normalizeAttrValue = (v: unknown) => {
  // Normalize for stability when matching:
  // - collapse whitespace
  // - trim
  // - do NOT change punctuation/case (keep user intent)
  return String(v ?? '').replace(/\s+/g, ' ').trim()
}

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

type MainPatternOption = { key: string; label: string }

type PersistedConfigV1 = {
  merchantSkuPrefix: string
  merchantSkuSuffix: string
  sizes: TmallSizeOption[]
  colors: Array<TmallColorOption & { enabledSizes?: Record<string, boolean> }>
  mainPatternTypes: MainPatternOption[]
}

const STORAGE_KEY = 'tmall_sku_generator_config_v1'

const downloadText = (text: string, filename: string) => {
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  downloadBlob(blob, filename)
}

const copyText = async (text: string) => {
  try {
    await navigator.clipboard.writeText(text)
    message.success('已复制')
  } catch {
    // Fallback for environments without clipboard permission
    const el = document.createElement('textarea')
    el.value = text
    el.style.position = 'fixed'
    el.style.left = '-9999px'
    document.body.appendChild(el)
    el.focus()
    el.select()
    document.execCommand('copy')
    el.remove()
    message.success('已复制')
  }
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
  const [mainPatternTypes, setMainPatternTypes] = useState<MainPatternOption[]>([
    { key: 'p1', label: '无' },
  ])

  // Persist config in browser storage (MVP; makes it usable as "系统主体" without backend yet)
  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (!raw) return
      const parsed = JSON.parse(raw) as PersistedConfigV1
      if (parsed?.merchantSkuPrefix) setMerchantSkuPrefix(parsed.merchantSkuPrefix)
      if (parsed?.merchantSkuSuffix !== undefined) setMerchantSkuSuffix(parsed.merchantSkuSuffix)
      if (Array.isArray(parsed?.sizes) && parsed.sizes.length) setSizes(parsed.sizes)
      if (Array.isArray(parsed?.colors) && parsed.colors.length) {
        setColors(
          parsed.colors.map((c) => ({
            key: c.key,
            label: c.label,
            width_cm: c.width_cm,
            height_cm: c.height_cm,
            thickness_cm: c.thickness_cm,
            length_cm: c.length_cm,
            main_pattern_type: c.main_pattern_type,
            enabledSizes: c.enabledSizes ?? {},
          })),
        )
      }
      if (Array.isArray(parsed?.mainPatternTypes) && parsed.mainPatternTypes.length) setMainPatternTypes(parsed.mainPatternTypes)
    } catch {
      // ignore storage corruption
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    try {
      const data: PersistedConfigV1 = {
        merchantSkuPrefix,
        merchantSkuSuffix,
        sizes,
        colors,
        mainPatternTypes,
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
    } catch {
      // ignore quota/disabled storage
    }
  }, [merchantSkuPrefix, merchantSkuSuffix, sizes, colors, mainPatternTypes])

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

  const exportAttributeBuildListXlsx = () => {
    const wb = XLSX.utils.book_new()
    const rows: Array<{ attribute: string; value: string }> = []
    for (const c of colors) rows.push({ attribute: '颜色分类', value: normalizeAttrValue(c.label) })
    for (const s of sizes) rows.push({ attribute: '尺寸', value: normalizeAttrValue(s.label) })
    for (const p of mainPatternTypes) rows.push({ attribute: '主图案类型', value: normalizeAttrValue(p.label) })

    const ws = XLSX.utils.json_to_sheet(rows, { header: ['attribute', 'value'] })
    // Friendly headers
    XLSX.utils.sheet_add_aoa(ws, [['属性名', '属性值']], { origin: 'A1' })
    XLSX.utils.book_append_sheet(wb, ws, 'build_attributes')

    const out = XLSX.write(wb, { bookType: 'xlsx', type: 'array' })
    downloadBlob(new Blob([out], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }), 'tmall_build_attributes.xlsx')
  }

  const exportConfigJson = () => {
    const data: PersistedConfigV1 = {
      merchantSkuPrefix,
      merchantSkuSuffix,
      sizes,
      colors,
      mainPatternTypes,
    }
    downloadText(JSON.stringify(data, null, 2), 'tmall_sku_generator_config.json')
  }

  const importConfigJson = async (file: File) => {
    try {
      const buf = await file.text()
      const parsed = JSON.parse(buf) as Partial<PersistedConfigV1>
      if (parsed.merchantSkuPrefix !== undefined) setMerchantSkuPrefix(String(parsed.merchantSkuPrefix))
      if (parsed.merchantSkuSuffix !== undefined) setMerchantSkuSuffix(String(parsed.merchantSkuSuffix))
      if (Array.isArray(parsed.sizes)) setSizes(parsed.sizes as any)
      if (Array.isArray(parsed.colors)) {
        setColors(
          (parsed.colors as any[]).map((c) => ({
            key: String(c.key ?? `c_${uid()}`),
            label: String(c.label ?? '').trim(),
            width_cm: c.width_cm ?? null,
            height_cm: c.height_cm ?? null,
            thickness_cm: c.thickness_cm ?? null,
            length_cm: c.length_cm ?? null,
            main_pattern_type: c.main_pattern_type ?? null,
            enabledSizes: (c.enabledSizes && typeof c.enabledSizes === 'object' ? c.enabledSizes : {}) as Record<string, boolean>,
          })),
        )
      }
      if (Array.isArray(parsed.mainPatternTypes)) {
        setMainPatternTypes(
          (parsed.mainPatternTypes as any[]).map((p) => ({
            key: String(p.key ?? `p_${uid()}`),
            label: String(p.label ?? '').trim(),
          })),
        )
      }
      message.success('已导入配置')
    } catch (e: any) {
      message.error(String(e?.message ?? e ?? '导入失败'))
    }
  }

  const attributeText = useMemo(() => {
    const lines: string[] = []
    lines.push('【颜色分类】')
    for (const c of colors) lines.push(`- ${normalizeAttrValue(c.label)}`)
    lines.push('')
    lines.push('【尺寸】')
    for (const s of sizes) lines.push(`- ${normalizeAttrValue(s.label)}`)
    lines.push('')
    lines.push('【主图案类型】')
    for (const p of mainPatternTypes) lines.push(`- ${normalizeAttrValue(p.label)}`)
    lines.push('')
    return lines.join('\n')
  }, [colors, sizes, mainPatternTypes])

  const dupSummary = useMemo(() => {
    const countDup = (vals: string[]) => {
      const m = new Map<string, number>()
      for (const v of vals) {
        const k = normalizeAttrValue(v)
        if (!k) continue
        m.set(k, (m.get(k) ?? 0) + 1)
      }
      return Array.from(m.entries())
        .filter(([, n]) => n > 1)
        .map(([k, n]) => ({ k, n }))
    }
    return {
      colors: countDup(colors.map((c) => c.label)),
      sizes: countDup(sizes.map((s) => s.label)),
      patterns: countDup(mainPatternTypes.map((p) => p.label)),
    }
  }, [colors, sizes, mainPatternTypes])

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
          title="销售属性配置器（先在系统里编辑 → 复制到天猫后台建立属性）"
          extra={
            <Space wrap size={8}>
              <Upload
                accept=".json"
                maxCount={1}
                showUploadList={false}
                beforeUpload={(file) => {
                  void importConfigJson(file)
                  return false
                }}
              >
                <Button>导入配置(JSON)</Button>
              </Upload>
              <Button onClick={exportConfigJson}>导出配置(JSON)</Button>
              <Button onClick={() => void copyText(attributeText)}>一键复制建属性清单</Button>
              <Button icon={<DownloadOutlined />} onClick={exportAttributeBuildListXlsx}>
                导出建属性清单(xlsx)
              </Button>
            </Space>
          }
        >
          <Space direction="vertical" style={{ width: '100%' }} size={10}>
            <Alert
              type="warning"
              showIcon
              message="关键口径：销售属性在模板里不可编辑"
              description={
                <div>
                  <div>我们这里的目标是：把“颜色分类/尺寸/主图案类型”等属性值先按你们 TOKEN 口径整理成可复制清单。</div>
                  <div>你在天猫后台按清单建立属性后，再下载官方模板，用上面的“一键填充并下载”回填编码/上架即可。</div>
                </div>
              }
            />

            {(dupSummary.colors.length || dupSummary.sizes.length || dupSummary.patterns.length) ? (
              <Alert
                type="error"
                showIcon
                message="检测到重复属性值（会导致天猫侧歧义/回填匹配不稳定）"
                description={
                  <div>
                    {dupSummary.colors.length ? (
                      <div>
                        <b>颜色分类重复</b>：{dupSummary.colors.map((x) => `${x.k}×${x.n}`).join('；')}
                      </div>
                    ) : null}
                    {dupSummary.sizes.length ? (
                      <div>
                        <b>尺寸重复</b>：{dupSummary.sizes.map((x) => `${x.k}×${x.n}`).join('；')}
                      </div>
                    ) : null}
                    {dupSummary.patterns.length ? (
                      <div>
                        <b>主图案类型重复</b>：{dupSummary.patterns.map((x) => `${x.k}×${x.n}`).join('；')}
                      </div>
                    ) : null}
                  </div>
                }
              />
            ) : (
              <Alert type="success" showIcon message="属性值去重校验通过" />
            )}

            <Card size="small" title="主图案类型（可选，值域清单）" extra={<Tag>用于天猫后台建立“主图案类型”属性</Tag>}>
              <Space direction="vertical" style={{ width: '100%' }} size={8}>
                {mainPatternTypes.map((p, i) => (
                  <Space key={p.key} wrap size={8} style={{ width: '100%' }}>
                    <Text type="secondary">值</Text>
                    <Input
                      style={{ width: 360 }}
                      value={p.label}
                      onChange={(e) => setMainPatternTypes((prev) => prev.map((x, idx) => (idx === i ? { ...x, label: e.target.value } : x)))}
                    />
                    <Button danger onClick={() => setMainPatternTypes((prev) => prev.filter((_, idx) => idx !== i))}>
                      删除
                    </Button>
                  </Space>
                ))}
                <Button onClick={() => setMainPatternTypes((prev) => [...prev, { key: `p_${uid()}`, label: '新类型' }])}>
                  添加主图案类型
                </Button>
              </Space>
            </Card>

            <Card size="small" title="建属性清单（预览，可直接复制）">
              <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace' }}>
                {attributeText}
              </pre>
            </Card>
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
                title: '主图案类型（可选）',
                width: 200,
                render: (_: any, r: ColorRow, idx: number) => (
                  <Select
                    allowClear
                    placeholder="可选"
                    style={{ width: '100%' }}
                    value={r.main_pattern_type ?? undefined}
                    options={mainPatternTypes.map((p) => ({ label: p.label, value: p.label }))}
                    onChange={(v) =>
                      setColors((prev) =>
                        prev.map((x, i) => (i === idx ? { ...x, main_pattern_type: v ?? null } : x)),
                      )
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

