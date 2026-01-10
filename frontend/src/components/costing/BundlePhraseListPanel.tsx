import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Collapse, Input, Radio, Space, Table, Tag, Typography, message } from 'antd'
import { CheckCircleFilled, CloseCircleFilled, CopyOutlined } from '@ant-design/icons'

const { Text } = Typography

type PhrasePresetLite = {
  selector?: string
  phrase?: string
  enabled?: boolean
  components?: any[]
}

type PhraseWriteMode = 'prefix' | 'suffix'

const toSelector2 = (idx: number): string => {
  if (idx < 0 || idx >= 26 * 26) return ''
  const a = Math.floor(idx / 26)
  const b = idx % 26
  return String.fromCharCode('A'.charCodeAt(0) + a) + String.fromCharCode('A'.charCodeAt(0) + b)
}

const normalizeBundleCode = (raw?: string | null): string => {
  let s = String(raw ?? '')
    .trim()
    .toUpperCase()
    .replace(/^BUNDLE:/, 'B:')
    .replace(/^B-/, '')
  if (s.startsWith('B:')) s = s.slice(2)
  // allow "B-CODE-AA" or "B-XXXXAA"
  s = s.replace(/^[A-Z0-9]{4,16}-[A-Z]{1,2}$/, (x) => x.split('-')[0])
  if (/^[A-Z0-9]{4}[A-Z]{2}$/.test(s) && s.length === 6) {
    // could be B-XXXXAA short; keep first 4 as code
    return s.slice(0, 4)
  }
  return s
}

const toBundleTokenDash = (code: string, selector?: string | null): string => {
  const c = String(code ?? '').trim().toUpperCase().replace(/^B:/, '').replace(/^BUNDLE:/, '').replace(/^B-/, '')
  const sel = String(selector ?? '').trim().toUpperCase()
  if (sel) {
    if (c.length === 4 && sel.length === 2) return `B-${c}${sel}`
    return `B-${c}-${sel}`
  }
  return `B-${c}`
}

const stripBraces = (s: string) => String(s ?? '').replace(/[{}]/g, '').replace(/\s+/g, ' ').trim()

const normalizePhraseForMatch = (s: string): string => {
  return String(s ?? '')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '')
    .replace(/[×xX]/g, '*')
}

const extractRequiredSegments = (phraseExample: string): string[] => {
  const n = normalizePhraseForMatch(phraseExample)
  if (!n) return []
  // Prefer segments containing qty: 45*45*3个 / 30*50*1个
  const segsQty = Array.from(n.matchAll(/\d{1,4}\*\d{1,4}\*\d{1,4}个/g)).map((m) => m[0])
  if (segsQty.length) return Array.from(new Set(segsQty))
  // Fallback: keep size segments (less strict)
  const segs = Array.from(n.matchAll(/\d{1,4}\*\d{1,4}/g)).map((m) => m[0])
  return Array.from(new Set(segs))
}

export default function BundlePhraseListPanel(props: {
  bundleCode?: string | null
  phrasePresets: PhrasePresetLite[]
  defaultMode?: PhraseWriteMode
  activeSelector?: string | null
  title?: string
  defaultOpen?: boolean
}) {
  const {
    bundleCode,
    phrasePresets,
    defaultMode = 'prefix',
    activeSelector,
    title = '短语生成器（可复制/可校验）',
    defaultOpen = true,
  } = props

  const [mode, setMode] = useState<PhraseWriteMode>(defaultMode)
  const [draftBySelector, setDraftBySelector] = useState<Record<string, string>>({})

  const codeOnly = useMemo(() => normalizeBundleCode(bundleCode), [bundleCode])

  const rows = useMemo(() => {
    const out = (phrasePresets ?? []).map((p, idx) => {
      const selector = String(p?.selector ?? '').trim().toUpperCase() || toSelector2(idx)
      const phraseRaw = String(p?.phrase ?? '')
      const phraseExample = stripBraces(phraseRaw)
      const tokenDash = codeOnly ? toBundleTokenDash(codeOnly, selector) : selector
      const enabled = p?.enabled !== false
      const requiredSegments = extractRequiredSegments(phraseExample)
      return { idx, selector, enabled, phraseRaw, phraseExample, tokenDash, requiredSegments, components: p?.components ?? [] }
    })
    return out.filter((r) => !!String(r.selector).trim())
  }, [codeOnly, phrasePresets])

  useEffect(() => {
    // Seed drafts for new selectors
    if (!rows.length) return
    setDraftBySelector((prev) => {
      const next = { ...(prev ?? {}) }
      let changed = false
      for (const r of rows) {
        if (next[r.selector] === undefined) {
          next[r.selector] = r.phraseExample || ''
          changed = true
        }
      }
      return changed ? next : prev
    })
  }, [rows])

  const validateRow = (r: any) => {
    const phrase = String(draftBySelector[r.selector] ?? '').trim()
    const missing: string[] = []
    if (!phrase) {
      missing.push('短语不能为空')
      return { ok: false, missing }
    }
    const pn = normalizePhraseForMatch(phrase)
    for (const seg of r.requiredSegments ?? []) {
      if (seg && !pn.includes(String(seg))) {
        missing.push(`缺少必含片段：${seg}`)
      }
    }
    return { ok: missing.length === 0, missing }
  }

  const buildOutput = (r: any) => {
    const phrase = String(draftBySelector[r.selector] ?? '').trim()
    const token = String(r.tokenDash)
    if (!phrase) return token
    if (mode === 'prefix') return `${token} ${phrase}`
    return `${phrase} (${token})`
  }

  const copyText = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      message.success('已复制')
    } catch {
      message.error('复制失败：请检查浏览器权限')
    }
  }

  const copyAll = async () => {
    const lines = rows.map((r) => buildOutput(r)).filter(Boolean)
    await copyText(lines.join('\n'))
  }

  return (
    <Collapse
      defaultActiveKey={defaultOpen ? ['panel'] : []}
      items={[
        {
          key: 'panel',
          label: title,
          children: (
            <Space direction="vertical" style={{ width: '100%' }} size={10}>
              <Alert
                type="info"
                showIcon
                message="运营可在“可变短语”里改词；系统会校验必含片段（例如尺寸/数量），并固定 B码 不可被改掉。"
                description="提示：遇到“同一规格里出现多个面料词”的混搭，建议用【筛选 → 指定（强制命中）】把组件钉死，否则解析命中可能不稳定。"
              />
              <Space wrap size={8} style={{ justifyContent: 'space-between', width: '100%' }}>
                <Space wrap size={8}>
                  <Text type="secondary">写法：</Text>
                  <Radio.Group
                    value={mode}
                    onChange={(e) => setMode(e.target.value)}
                    options={[
                      { label: 'B码前置', value: 'prefix' },
                      { label: 'B码后置（括号）', value: 'suffix' },
                    ]}
                    optionType="button"
                  />
                  <Text type="secondary">
                    当前B码：{codeOnly ? <Text code>{`B-${codeOnly}`}</Text> : <Tag color="orange">未选择套装模板</Tag>}
                  </Text>
                </Space>
                <Button icon={<CopyOutlined />} onClick={copyAll} disabled={!rows.length}>
                  复制全部（每行一条）
                </Button>
              </Space>

              <Card size="small" bodyStyle={{ padding: 0 }}>
                <Table
                  size="small"
                  pagination={false}
                  rowKey={(r) => String((r as any).selector)}
                  dataSource={rows}
                  rowClassName={(r: any) =>
                    activeSelector && String(activeSelector).trim().toUpperCase() === String(r.selector).trim().toUpperCase()
                      ? 'row-active'
                      : ''
                  }
                  columns={[
                    {
                      title: 'selector',
                      width: 110,
                      render: (_: any, r: any) => (
                        <Space size={6} wrap>
                          <Text code>{String(r.selector)}</Text>
                          {r.enabled ? <Tag color="green">启用</Tag> : <Tag color="red">停用</Tag>}
                        </Space>
                      ),
                    },
                    {
                      title: '固定B码',
                      width: 150,
                      render: (_: any, r: any) => (
                        <Space size={6} wrap>
                          <Tag color="blue">{String(r.tokenDash)}</Tag>
                          <Button size="small" type="link" onClick={() => copyText(String(r.tokenDash))}>
                            复制
                          </Button>
                        </Space>
                      ),
                    },
                    {
                      title: '可变短语（可编辑）',
                      render: (_: any, r: any) => (
                        <Space direction="vertical" size={6} style={{ width: '100%' }}>
                          <Input
                            value={String(draftBySelector[r.selector] ?? '')}
                            onChange={(e) =>
                              setDraftBySelector((prev) => ({ ...(prev ?? {}), [String(r.selector)]: e.target.value }))
                            }
                            placeholder="运营可改词（例如把“黄金绒”改成更对客的描述）"
                          />
                          {(r.requiredSegments ?? []).length ? (
                            <Space wrap size={6}>
                              <Text type="secondary">必含片段：</Text>
                              {(r.requiredSegments ?? []).slice(0, 6).map((seg: string) => (
                                <Tag key={`${r.selector}-seg-${seg}`}>{seg}</Tag>
                              ))}
                              {(r.requiredSegments ?? []).length > 6 ? <Text type="secondary">…</Text> : null}
                            </Space>
                          ) : (
                            <Text type="secondary">必含片段：-</Text>
                          )}
                        </Space>
                      ),
                    },
                    {
                      title: '验证',
                      width: 220,
                      render: (_: any, r: any) => {
                        const v = validateRow(r)
                        return (
                          <Space direction="vertical" size={4}>
                            {v.ok ? (
                              <Space size={6}>
                                <CheckCircleFilled style={{ color: '#52c41a' }} />
                                <Text>通过</Text>
                              </Space>
                            ) : (
                              <Space size={6}>
                                <CloseCircleFilled style={{ color: '#ff4d4f' }} />
                                <Text type="danger">未通过</Text>
                              </Space>
                            )}
                            {!v.ok ? (
                              <Text type="secondary" style={{ fontSize: 12 }}>
                                {v.missing.slice(0, 2).join('；')}
                                {v.missing.length > 2 ? '…' : ''}
                              </Text>
                            ) : null}
                          </Space>
                        )
                      },
                    },
                    {
                      title: '可复制写法（输出）',
                      width: 360,
                      render: (_: any, r: any) => {
                        const out = buildOutput(r)
                        return (
                          <Space direction="vertical" size={6} style={{ width: '100%' }}>
                            <Text code ellipsis={{ tooltip: true }}>
                              {out}
                            </Text>
                            <Space size={8}>
                              <Button size="small" icon={<CopyOutlined />} onClick={() => copyText(out)}>
                                复制
                              </Button>
                            </Space>
                          </Space>
                        )
                      },
                    },
                  ]}
                />
              </Card>

              <style>
                {`
                .row-active td { background: #fffbe6 !important; }
              `}
              </style>
            </Space>
          ),
        },
      ]}
    />
  )
}


