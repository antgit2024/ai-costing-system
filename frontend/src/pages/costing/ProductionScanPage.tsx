import { Alert, Button, Card, Col, Descriptions, Image, Input, List, Modal, Row, Space, Tabs, Tag, Typography } from 'antd'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { BrowserMultiFormatReader, type IScannerControls } from '@zxing/browser'
import SearchOutlined from '@ant-design/icons/lib/icons/SearchOutlined'

import {
  fetchMaterial,
  fetchProductModelVersionLines,
  fetchPublishedStandardModels,
  fetchSkuMasterByBarcode,
  fetchVirtualMaterial,
  previewProductModelVersion,
} from '@/services/planner'
import type {
  Material,
  ProductModelMaterialLineInput,
  ProductModelPreviewMaterialLine,
  SkuMaster,
  SkuMasterScanResponse,
  VirtualMaterial,
} from '@/types/planner'

const { Title, Text } = Typography

const safe = (v: unknown): string => (v === null || v === undefined ? '' : String(v))

const parseDimsFromText = (raw: string): { width_cm: string; height_cm: string } | null => {
  const s = safe(raw).toUpperCase().replace(/\s+/g, '')
  if (!s) return null

  // 竖140CM*横200CM / 横200CM*竖140CM
  let m = s.match(/竖(\d+(?:\.\d+)?)CM[*X×]横(\d+(?:\.\d+)?)CM/)
  if (m) return { height_cm: m[1], width_cm: m[2] }
  m = s.match(/横(\d+(?:\.\d+)?)CM[*X×]竖(\d+(?:\.\d+)?)CM/)
  if (m) return { width_cm: m[1], height_cm: m[2] }

  // fallback: 140CM*200CM / 140*200CM
  m = s.match(/(\d+(?:\.\d+)?)CM?[*X×](\d+(?:\.\d+)?)CM?/)
  if (m) {
    // 无方向信息：默认“更大的是宽”
    const a = Number(m[1])
    const b = Number(m[2])
    if (Number.isFinite(a) && Number.isFinite(b)) {
      return a >= b ? { width_cm: String(a), height_cm: String(b) } : { width_cm: String(b), height_cm: String(a) }
    }
    return { width_cm: m[1], height_cm: m[2] }
  }
  return null
}

const ProductionScanPage = () => {
  const [searchParams] = useSearchParams()
  const [barcode, setBarcode] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string>('')
  const [data, setData] = useState<SkuMasterScanResponse | null>(null)
  const [materialLines, setMaterialLines] = useState<ProductModelMaterialLineInput[] | null>(null)
  const [materialPreview, setMaterialPreview] = useState<ProductModelPreviewMaterialLine[]>([])
  const [materialModalOpen, setMaterialModalOpen] = useState(false)
  const [materialModalLoading, setMaterialModalLoading] = useState(false)
  const [materialModalError, setMaterialModalError] = useState<string>('')
  const [materialModalTitle, setMaterialModalTitle] = useState<string>('')
  const [materialModalMaterial, setMaterialModalMaterial] = useState<Material | null>(null)
  const [materialModalVirtual, setMaterialModalVirtual] = useState<VirtualMaterial | null>(null)
  const [cameraOpen, setCameraOpen] = useState(false)
  const [cameraError, setCameraError] = useState<string>('')
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const rafRef = useRef<number | null>(null)
  const zxingReaderRef = useRef<BrowserMultiFormatReader | null>(null)
  const zxingControlsRef = useRef<IScannerControls | null>(null)
  const startAfterOpenRef = useRef<null | (() => void)>(null)
  const lastScanAtRef = useRef<number>(0)
  const specSectionRef = useRef<HTMLDivElement | null>(null)
  const processSectionRef = useRef<HTMLDivElement | null>(null)

  const sku = data?.sku_master as SkuMaster | undefined

  // Prefer same-origin proxy (on-demand cached) to avoid direct 3rd-party image dependency in factory.
  const specImage =
    sku?.id ? `/api/planner/sku-master/${encodeURIComponent(String(sku.id))}/images/spec` : safe((sku?.images_json as any)?.spec_image)

  const shopSkus = data?.shop_skus ?? []

  const dims = useMemo(() => {
    const d =
      (sku as any)?.erp_dimensions ||
      (sku as any)?.preparse_dimensions ||
      (sku as any)?.metadata_json?.erp_dimensions ||
      (sku as any)?.metadata_json?.preparse_dimensions ||
      null
    const w = safe(d?.width_cm).trim()
    const h = safe(d?.height_cm).trim()
    if (w || h) return { width_cm: w, height_cm: h }

    // 没有结构化dimensions时，兜底从交易规格/预解析文本里提取
    const parsed =
      parseDimsFromText((sku as any)?.spec_text) ||
      parseDimsFromText((sku as any)?.preparse_spec_text) ||
      parseDimsFromText((sku as any)?.metadata_json?.preparse_spec_text)
    if (parsed) return parsed

    return { width_cm: '', height_cm: '' }
  }, [sku])

  // moduleSummary/materialSummary removed (工艺模块/工艺列表隐藏，物料清单无需汇总Tag)

  // (mobile view) shop sku rows are rendered as List instead of Table

  const doSearch = async () => {
    const code = barcode.trim()
    if (!code) return
    setLoading(true)
    setError('')
    setData(null)
    setMaterialLines(null)
    setMaterialPreview([])
    try {
      const res = await fetchSkuMasterByBarcode(code)
      setData(res)

      const sku0 = res.sku_master as any
      const boundModelCode = safe(sku0?.bound_model_code).trim()
      const boundModelName = safe(sku0?.bound_model_name).trim()
      // 扣库/生产口径：计算不“绑死版本号”，永远优先用该模型最新已发布标准版做预览
      // （绑定区仍可展示当时绑定的版本标签，用于追溯）
      let targetVid = ''
      if (boundModelCode || boundModelName) {
        try {
          const candidates = await fetchPublishedStandardModels({
            search: boundModelCode || boundModelName,
            limit: 20,
          })
          const items = candidates.items ?? []
          const exact = boundModelCode
            ? items.find((it) => String(it.model_code || '').trim() === boundModelCode)
            : undefined
          targetVid = safe((exact || items[0])?.published_version_id).trim()
        } catch {
          // ignore
        }
      }
      // fallback: 如果没找到发布版，才退回当前绑定版本，避免页面空
      if (!targetVid) targetVid = safe(sku0?.active_model_version_id).trim()

      if (targetVid) {
        const lines = await fetchProductModelVersionLines(targetVid)
        setMaterialLines(lines.materials ?? [])
        // Use preview to get "扣库口径" used_quantity (more accurate than raw lines)
        const wmm = Number((res.sku_master as any)?.metadata_json?.preparse_dimensions?.width_cm || (res.sku_master as any)?.metadata_json?.erp_dimensions?.width_cm || (res.sku_master as any)?.erp_dimensions?.width_cm || 0) * 10
        const hmm = Number((res.sku_master as any)?.metadata_json?.preparse_dimensions?.height_cm || (res.sku_master as any)?.metadata_json?.erp_dimensions?.height_cm || (res.sku_master as any)?.erp_dimensions?.height_cm || 0) * 10
        const width_mm = Number.isFinite(wmm) && wmm > 0 ? wmm : 0
        const height_mm = Number.isFinite(hmm) && hmm > 0 ? hmm : 0
        if (width_mm > 0 && height_mm > 0) {
          const preview = await previewProductModelVersion(targetVid, { width_mm, height_mm, quantity: 1, sku_hint: code })
          setMaterialPreview(preview.material_lines ?? [])
        }
      }
    } catch (e: any) {
      setError(e?.message || '查询失败')
    } finally {
      setLoading(false)
    }
  }

  const openMaterialModal = async (line: any) => {
    const code = safe(line?.material_code || line?.virtual_code).trim()
    const name = safe(line?.material_name || line?.name).trim()
    setMaterialModalTitle([code, name].filter(Boolean).join(' '))
    setMaterialModalError('')
    setMaterialModalMaterial(null)
    setMaterialModalVirtual(null)
    setMaterialModalOpen(true)
    setMaterialModalLoading(true)
    try {
      const kind = String(line?.source_kind || line?.resolved_kind || '').toLowerCase()
      const materialId = safe(line?.material_id || '').trim()
      const virtualId = safe(line?.source_ref_id || '').trim()

      // 真实/可解析为真实：优先取 material_id
      if (materialId) {
        const m = await fetchMaterial(materialId)
        setMaterialModalMaterial(m)
        return
      }

      // 虚拟/占位符：取 virtual material（展示其 bindings 的图片）
      if ((kind === 'virtual' || kind === 'placeholder' || /^vm/i.test(code)) && virtualId) {
        const vm = await fetchVirtualMaterial(virtualId)
        setMaterialModalVirtual(vm)
        return
      }

      setMaterialModalError('该物料暂无可用图片（缺少物料ID/虚拟物料ID）')
    } catch (e: any) {
      setMaterialModalError(e?.message || '加载物料图片失败')
    } finally {
      setMaterialModalLoading(false)
    }
  }

  const scrollTo = (target: 'spec' | 'process') => {
    const el = target === 'spec' ? specSectionRef.current : processSectionRef.current
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  // Support deep-link from 3rd-party apps (e.g. 宜搭扫码后打开外链):
  // /costing/production-scan?barcode=xxxx
  useEffect(() => {
    const b = (searchParams.get('barcode') || '').trim()
    if (!b) return
    // only auto-fill when user hasn't typed anything yet, or when param changed
    setBarcode(b)
    // trigger search
    setTimeout(() => {
      void doSearch()
    }, 0)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams])

  const stopCamera = () => {
    try {
      // @zxing/browser: use controls.stop() (handled in callback) and drop reader
    } catch {
      // ignore
    }
    try {
      zxingControlsRef.current?.stop()
    } catch {
      // ignore
    }
    zxingControlsRef.current = null
    zxingReaderRef.current = null

    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
    const s = streamRef.current
    if (s) {
      for (const t of s.getTracks()) t.stop()
      streamRef.current = null
    }
    if (videoRef.current) {
      ;(videoRef.current as any).srcObject = null
    }
  }

  useEffect(() => {
    if (!cameraOpen) {
      stopCamera()
      setCameraError('')
      startAfterOpenRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cameraOpen])

  // When modal opens, start scanning after video element is mounted.
  useEffect(() => {
    if (!cameraOpen) return
    const fn = startAfterOpenRef.current
    if (!fn) return
    startAfterOpenRef.current = null
    // delay 1 tick to ensure Modal content mounted
    setTimeout(() => {
      fn()
    }, 0)
  }, [cameraOpen])

  const startCameraScan = async () => {
    setCameraError('')
    if (!window.isSecureContext) {
      setCameraError('浏览器禁止在非HTTPS环境调用摄像头：请使用HTTPS域名或在localhost访问。')
      setCameraOpen(true)
      return
    }
    const BarcodeDetectorCtor = (window as any).BarcodeDetector as any
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError('当前环境不支持 getUserMedia。可先手动输入条码查询。')
      setCameraOpen(true)
      return
    }

    // Open modal first; actual start will run after modal mounts.
    setCameraOpen(true)

    startAfterOpenRef.current = async () => {
      try {
        // iOS/Safari may mount modal content slower; wait for ref to be ready.
        const waitStart = Date.now()
        let v: HTMLVideoElement | null = videoRef.current
        while (!v && Date.now() - waitStart < 3000) {
          await new Promise((r) => setTimeout(r, 50))
          v = videoRef.current
        }
        if (!v) {
          setCameraError('摄像头初始化较慢，请稍后重试（建议刷新页面后再试）。')
          return
        }

        // Prefer native BarcodeDetector when available (fast), otherwise fallback to ZXing.
        if (BarcodeDetectorCtor) {
          const stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: { ideal: 'environment' } },
            audio: false,
          })
          streamRef.current = stream
          ;(v as any).srcObject = stream
          await v.play()

          const detector = new BarcodeDetectorCtor({
            formats: [
              'code_128',
              'ean_13',
              'ean_8',
              'code_39',
              'upc_a',
              'upc_e',
              'itf',
              'qr_code',
            ],
          })

          const tick = async () => {
            const vv = videoRef.current
            if (!vv) return
            try {
              const results = await detector.detect(vv)
              const raw = results?.[0]?.rawValue ? String(results[0].rawValue).trim() : ''
              if (raw) {
                setBarcode(raw)
                setCameraOpen(false)
                setTimeout(() => {
                  void doSearch()
                }, 0)
                return
              }
            } catch {
              // ignore single-frame errors
            }
            rafRef.current = requestAnimationFrame(() => {
              void tick()
            })
          }

          await tick()
          return
        }

        // ZXing fallback (works in more webviews / iOS)
        const reader = new BrowserMultiFormatReader()
        zxingReaderRef.current = reader
        // request higher resolution when possible to improve recognition
        const p = reader.decodeFromConstraints(
          {
            video: {
              facingMode: { ideal: 'environment' },
              width: { ideal: 1280 },
              height: { ideal: 720 },
            },
          },
          v,
          (res, err, controls) => {
            zxingControlsRef.current = controls
            // on first callback, stream should be attached to video
            const s = (videoRef.current as any)?.srcObject as MediaStream | null
            if (s) streamRef.current = s
            if (res?.getText) {
              const raw = String(res.getText() || '').trim()
              if (raw) {
                const now = Date.now()
                if (now - lastScanAtRef.current < 1200) return
                lastScanAtRef.current = now
                try {
                  controls?.stop()
                } catch {
                  // ignore
                }
                setBarcode(raw)
                setCameraOpen(false)
                setTimeout(() => {
                  void doSearch()
                }, 0)
              }
            }
            // ignore err; it fires frequently while scanning
            void err
          },
        )
        void p
      } catch (e: any) {
        setCameraError(e?.message || '打开摄像头失败：请检查浏览器权限/HTTPS环境')
      }
    }
  }

  return (
    <div className="production-scan-page">
      <Title level={3} style={{ marginBottom: 8 }}>
        <Space size={8}>
          <SearchOutlined />
          <span>商品查询</span>
        </Space>
      </Title>

      <Card>
        <Space direction="vertical" style={{ width: '100%' }} size={10}>
          <Input
            value={barcode}
            onChange={(e) => setBarcode(e.target.value)}
            placeholder="扫码或输入：货品条码（系统）"
            allowClear
            size="large"
            onPressEnter={() => doSearch()}
          />
          <Row gutter={10}>
            <Col span={12}>
              <Button type="primary" block loading={loading} onClick={() => doSearch()}>
                条码查询
              </Button>
            </Col>
            <Col span={12}>
              <Button type="primary" block onClick={() => void startCameraScan()}>
                拍照扫码
              </Button>
            </Col>
          </Row>
          {error ? <Alert type="error" showIcon message={error} /> : null}
        </Space>
      </Card>

      <Modal
        title="摄像头扫码"
        open={cameraOpen}
        onCancel={() => setCameraOpen(false)}
        footer={null}
        destroyOnClose
        width={520}
      >
        {cameraError ? <Alert type="warning" showIcon message={cameraError} /> : null}
        <div style={{ marginTop: 12 }}>
          <video
            ref={videoRef}
            style={{
              width: '100%',
              aspectRatio: '1 / 1',
              borderRadius: 8,
              background: '#111',
              objectFit: 'cover',
            }}
            playsInline
            muted
          />
          <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
            提示：尽量用手机后摄、对准条码，识别到会自动填入并查询。
          </Text>
        </div>
      </Modal>

      {sku ? (
        <div style={{ marginTop: 12 }}>
          <Tabs
            activeKey="spec"
            onChange={(k) => scrollTo(k as 'spec' | 'process')}
            items={[
              { key: 'spec', label: '规格信息' },
              { key: 'process', label: '工艺列表' },
            ]}
          />

          <div ref={specSectionRef} style={{ scrollMarginTop: 12 }}>
            <Space direction="vertical" style={{ width: '100%' }} size={12}>
              <Card size="small">
                <Text strong>规格图片</Text>
                <div style={{ marginTop: 8 }}>
                  {specImage ? (
                    <Image src={specImage} style={{ width: '100%', maxWidth: 520, borderRadius: 12 }} />
                  ) : (
                    <Text type="secondary">无</Text>
                  )}
                </div>
              </Card>

              <Card size="small">
                <Descriptions bordered size="small" column={1}>
                  <Descriptions.Item
                    label={<span style={{ display: 'inline-block', minWidth: '4em' }}>交易规格</span>}
                  >
                    {sku.spec_text ?? '-'}
                  </Descriptions.Item>
                  <Descriptions.Item label="规格尺寸">
                    <Space size={10} wrap>
                      <span>宽：{dims.width_cm ? `${dims.width_cm}cm` : '-'}</span>
                      <span>高：{dims.height_cm ? `${dims.height_cm}cm` : '-'}</span>
                      <span>数量：1</span>
                    </Space>
                  </Descriptions.Item>
                  <Descriptions.Item label="商品编码">{sku.product_code ?? '-'}</Descriptions.Item>
                  <Descriptions.Item label="绑定模型">
                    {sku.active_model_version_id ? (
                      <Space size={6} wrap>
                        {sku.bound_model_code ? <Tag color="blue">{sku.bound_model_code}</Tag> : null}
                        <Tag
                          style={{
                            fontSize: 12,
                            color: '#14532d',
                            background: '#dcfce7',
                            borderColor: '#86efac',
                            borderRadius: 999,
                          }}
                        >
                          {sku.bound_model_name || '已绑定'}
                        </Tag>
                      </Space>
                    ) : (
                      <Tag color="red">未绑定</Tag>
                    )}
                  </Descriptions.Item>
                  <Descriptions.Item label="更新时间">{safe(sku.source_updated_at) || '-'}</Descriptions.Item>
                </Descriptions>
              </Card>

              {shopSkus.length ? (
                <Card size="small" title="网店SKU（平台规格Id维度）">
                  <List
                    dataSource={shopSkus}
                    renderItem={(it) => (
                      <List.Item>
                        <Space direction="vertical" size={2} style={{ width: '100%' }}>
                          <Space wrap size={6}>
                            {it.channel ? <Tag>{it.channel}</Tag> : null}
                            <Tag color="blue">{it.platform_sku_id}</Tag>
                          </Space>
                          <Text type="secondary">
                            平台商品Id：{it.platform_product_id || '-'}；规格编码：{it.shop_spec_code || '-'}
                          </Text>
                          <Text type="secondary">更新时间：{it.source_updated_at || '-'}</Text>
                        </Space>
                      </List.Item>
                    )}
                  />
                </Card>
              ) : null}
            </Space>
          </div>

          <div ref={processSectionRef} style={{ marginTop: 12, scrollMarginTop: 12 }}>
            <Space direction="vertical" style={{ width: '100%' }} size={12}>
              <Card size="small" title="物料清单">
                <List
                  dataSource={
                    ((materialPreview.length ? materialPreview : (materialLines ?? [])) as unknown[]) as any[]
                  }
                  locale={{ emptyText: '暂无（需要先绑定模型版本并配置物料/BOM）' }}
                  renderItem={(r: any, idx) => {
                    const code = safe(r.material_code).trim()
                    const name = safe(r.material_name).trim()
                    // 扣库/成本口径：优先使用含损耗用量
                    const qty =
                      r.used_quantity_with_loss ??
                      r.used_quantity ??
                      r.standard_used_quantity ??
                      r.sample_used_quantity ??
                      r.base_quantity ??
                      null
                    const unit = safe(r.unit).trim()
                    const kind = String(r.source_kind || r.resolved_kind || '').toLowerCase()
                    // preview 接口当前更偏“解析后/兜底后”的结果（resolved_kind），可能导致虚拟/占位符被解析成 real；
                    // 这里用编码前缀 VM* 作为兜底判断，确保 VMxxxx 统一按虚拟物料展示。
                    const isVirtual =
                      /^vm/i.test(code) || kind === 'virtual' || kind === 'placeholder'
                    const tagColor = isVirtual ? 'purple' : 'blue'
                    return (
                      <List.Item
                        onClick={() => void openMaterialModal(r)}
                        style={{ cursor: 'pointer' }}
                      >
                        <Space wrap size={8} style={{ width: '100%' }}>
                          <Text type="secondary" style={{ minWidth: 18, fontSize: 12 }}>
                            {idx + 1}.
                          </Text>
                          {code ? (
                            <Tag
                              color={tagColor}
                              style={{
                                fontSize: 12,
                                lineHeight: '18px',
                                padding: '0 6px',
                                borderRadius: 999,
                              }}
                            >
                              {code}
                            </Tag>
                          ) : (
                            <Tag
                              style={{
                                fontSize: 12,
                                lineHeight: '18px',
                                padding: '0 6px',
                                borderRadius: 999,
                              }}
                            >
                              无编码
                            </Tag>
                          )}
                          <Text style={{ color: '#111' }}>{name || '物料'}</Text>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            用量：{qty === null ? '-' : String(qty)} {unit || ''}
                          </Text>
                        </Space>
                      </List.Item>
                    )
                  }}
                />
              </Card>
            </Space>
          </div>
        </div>
      ) : null}

      <Modal
        title={materialModalTitle || '物料图片'}
        open={materialModalOpen}
        onCancel={() => setMaterialModalOpen(false)}
        footer={null}
        destroyOnClose
        width={520}
      >
        {materialModalError ? <Alert type="warning" showIcon message={materialModalError} /> : null}

        {materialModalLoading ? (
          <Text type="secondary">正在加载...</Text>
        ) : materialModalMaterial ? (
          <div>
            {(materialModalMaterial.images || []).length ? (
              <Image.PreviewGroup>
                <Space direction="vertical" style={{ width: '100%' }} size={8}>
                  {(materialModalMaterial.images || []).map((url, i) => (
                    <Image key={String(i)} src={url} style={{ width: '100%', borderRadius: 10 }} />
                  ))}
                </Space>
              </Image.PreviewGroup>
            ) : (
              <Text type="secondary">该物料主数据暂无图片</Text>
            )}
          </div>
        ) : materialModalVirtual ? (
          <div>
            {materialModalVirtual.bindings?.some((b) => !!safe(b.image_url).trim()) ? (
              <Image.PreviewGroup>
                <Space direction="vertical" style={{ width: '100%' }} size={8}>
                  {materialModalVirtual.bindings
                    .filter((b) => !!safe(b.image_url).trim())
                    .map((b, i) => (
                      <Card
                        key={String(i)}
                        size="small"
                        style={{ borderRadius: 12 }}
                        title={`${b.material_code || ''} ${b.material_name || ''}`.trim()}
                      >
                        <Image src={safe(b.image_url)} style={{ width: '100%', borderRadius: 10 }} />
                      </Card>
                    ))}
                </Space>
              </Image.PreviewGroup>
            ) : (
              <Text type="secondary">该虚拟物料暂无绑定图片</Text>
            )}
          </div>
        ) : null}
      </Modal>
    </div>
  )
}

export default ProductionScanPage


