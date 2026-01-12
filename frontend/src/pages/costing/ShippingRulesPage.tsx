import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Button,
  Card,
  Checkbox,
  Col,
  Drawer,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'

import type { Material, ShippingRule, ShippingRuleEvaluateResponse } from '@/types/planner'
import { archiveShippingRule, createShippingRule, evaluateShippingRules, fetchShippingRules, updateShippingRule } from '@/services/planner'
import MaterialPickerDrawer from '@/components/costing/MaterialPickerDrawer'

const { Text } = Typography

type OutputRow = {
  key: string
  material_id?: string
  material_code?: string
  material_name?: string
  quantity?: number
  multiplier?: 'per_order' | 'per_package'
}

type EditorValues = {
  rule_name: string
  priority: number
  is_active: boolean
  shop_codes?: string
  shipping_methods?: string
  is_merge?: 'any' | 'true' | 'false'
  province_in?: string
  min_weight_kg?: number
  max_weight_kg?: number
  min_volume_m3?: number
  max_volume_m3?: number
  has_tokens_any?: string
  has_tokens_all?: string
  stop_on_hit?: boolean
  notes?: string
}

const splitCsv = (s?: string) =>
  String(s || '')
    .split(/[，,;\n]/g)
    .map((x) => x.trim())
    .filter(Boolean)

const summarizeConditions = (c: Record<string, any>) => {
  const parts: string[] = []
  if (Array.isArray(c.shop_codes) && c.shop_codes.length) parts.push(`店铺=${c.shop_codes.join('/')}`)
  if (Array.isArray(c.shipping_methods) && c.shipping_methods.length) parts.push(`物流=${c.shipping_methods.join('/')}`)
  if (c.is_merge === true) parts.push('合单=是')
  if (c.is_merge === false) parts.push('合单=否')
  if (Array.isArray(c.province_in) && c.province_in.length) parts.push(`省=${c.province_in.join('/')}`)
  if (c.min_weight_kg != null || c.max_weight_kg != null) parts.push(`重量kg=${c.min_weight_kg ?? '-'}~${c.max_weight_kg ?? '-'}`)
  if (c.min_volume_m3 != null || c.max_volume_m3 != null) parts.push(`体积m³=${c.min_volume_m3 ?? '-'}~${c.max_volume_m3 ?? '-'}`)
  if (Array.isArray(c.has_tokens_all) && c.has_tokens_all.length) parts.push(`tokens(all)=${c.has_tokens_all.join('+')}`)
  if (Array.isArray(c.has_tokens_any) && c.has_tokens_any.length) parts.push(`tokens(any)=${c.has_tokens_any.join('|')}`)
  if (c.stop_on_hit) parts.push('命中即停止')
  return parts.length ? parts.join('；') : '（无条件）'
}

const ShippingRulesPage = () => {
  const qc = useQueryClient()
  const [filters, setFilters] = useState({ search: '', is_active: undefined as undefined | boolean })
  const [page, setPage] = useState({ current: 1, pageSize: 20 })

  const [editing, setEditing] = useState<ShippingRule | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [form] = Form.useForm<EditorValues>()

  const [outputs, setOutputs] = useState<OutputRow[]>([])
  const [pickerOpen, setPickerOpen] = useState(false)

  // test bench
  const [testForm] = Form.useForm()
  const [testResp, setTestResp] = useState<ShippingRuleEvaluateResponse | null>(null)

  const queryParams = useMemo(
    () => ({
      search: filters.search.trim() || undefined,
      is_active: filters.is_active,
      page: page.current,
      page_size: page.pageSize,
    }),
    [filters.is_active, filters.search, page.current, page.pageSize],
  )

  const listQuery = useQuery({
    queryKey: ['shipping-rules', queryParams],
    queryFn: () => fetchShippingRules(queryParams),
  })

  const createMutation = useMutation({
    mutationFn: () =>
      createShippingRule({
        rule_name: '新发货规则',
        priority: 100,
        is_active: true,
        conditions: {},
        outputs: [],
      }),
    onSuccess: (r) => {
      message.success('已创建')
      qc.invalidateQueries({ queryKey: ['shipping-rules'] })
      openEditor(r)
    },
    onError: (e: any) => message.error(e?.message || '创建失败'),
  })

  const saveMutation = useMutation({
    mutationFn: async () => {
      const values = await form.validateFields()
      if (!editing) throw new Error('no editing')
      const conditions: Record<string, any> = {
        shop_codes: splitCsv(values.shop_codes),
        shipping_methods: splitCsv(values.shipping_methods),
        province_in: splitCsv(values.province_in),
        min_weight_kg: values.min_weight_kg ?? null,
        max_weight_kg: values.max_weight_kg ?? null,
        min_volume_m3: values.min_volume_m3 ?? null,
        max_volume_m3: values.max_volume_m3 ?? null,
        has_tokens_any: splitCsv(values.has_tokens_any),
        has_tokens_all: splitCsv(values.has_tokens_all),
        stop_on_hit: !!values.stop_on_hit,
      }
      if (values.is_merge === 'true') conditions.is_merge = true
      else if (values.is_merge === 'false') conditions.is_merge = false

      const payload = {
        rule_name: values.rule_name,
        priority: values.priority,
        is_active: values.is_active,
        notes: values.notes || null,
        conditions,
        outputs: outputs
          .filter((x) => x.material_id && (x.quantity ?? 0) > 0)
          .map((x) => ({
            material_id: x.material_id,
            quantity: x.quantity ?? 0,
            multiplier: x.multiplier ?? 'per_order',
          })),
      }
      return updateShippingRule(editing.id, payload)
    },
    onSuccess: (r) => {
      message.success('已保存')
      setEditing(r)
      qc.invalidateQueries({ queryKey: ['shipping-rules'] })
    },
    onError: (e: any) => message.error(e?.message || '保存失败'),
  })

  const archiveMutation = useMutation({
    mutationFn: async (rule: ShippingRule) => archiveShippingRule(rule.id),
    onSuccess: () => {
      message.success('已删除')
      qc.invalidateQueries({ queryKey: ['shipping-rules'] })
      if (drawerOpen) {
        setDrawerOpen(false)
        setEditing(null)
      }
    },
    onError: (e: any) => message.error(e?.message || '删除失败'),
  })

  const testMutation = useMutation({
    mutationFn: async () => {
      const values = await testForm.validateFields()
      const resp = await evaluateShippingRules({
        shop_code: values.shop_code || undefined,
        shipping_method: values.shipping_method || undefined,
        is_merge: values.is_merge === 'true' ? true : values.is_merge === 'false' ? false : undefined,
        province: values.province || undefined,
        weight_kg: values.weight_kg ?? undefined,
        volume_m3: values.volume_m3 ?? undefined,
        package_count: values.package_count ?? undefined,
        tokens: splitCsv(values.tokens),
      })
      return resp
    },
    onSuccess: (resp) => setTestResp(resp),
    onError: (e: any) => message.error(e?.message || '测试失败'),
  })

  const openEditor = (rule: ShippingRule) => {
    setEditing(rule)
    setDrawerOpen(true)
    const c = (rule.conditions || {}) as any
    form.setFieldsValue({
      rule_name: rule.rule_name || '',
      priority: rule.priority ?? 100,
      is_active: !!rule.is_active,
      shop_codes: Array.isArray(c.shop_codes) ? c.shop_codes.join(',') : '',
      shipping_methods: Array.isArray(c.shipping_methods) ? c.shipping_methods.join(',') : '',
      province_in: Array.isArray(c.province_in) ? c.province_in.join(',') : '',
      is_merge: c.is_merge === true ? 'true' : c.is_merge === false ? 'false' : 'any',
      min_weight_kg: c.min_weight_kg ?? undefined,
      max_weight_kg: c.max_weight_kg ?? undefined,
      min_volume_m3: c.min_volume_m3 ?? undefined,
      max_volume_m3: c.max_volume_m3 ?? undefined,
      has_tokens_any: Array.isArray(c.has_tokens_any) ? c.has_tokens_any.join(',') : '',
      has_tokens_all: Array.isArray(c.has_tokens_all) ? c.has_tokens_all.join(',') : '',
      stop_on_hit: !!c.stop_on_hit,
      notes: rule.notes || '',
    })
    const out = (rule.outputs || []) as any[]
    setOutputs(
      out.map((x, idx) => ({
        key: String(idx),
        material_id: x.material_id,
        quantity: Number(x.quantity ?? 0),
        multiplier: (x.multiplier as any) || 'per_order',
      })),
    )
  }

  const outputColumns: ColumnsType<OutputRow> = [
    {
      title: '条件物料',
      dataIndex: 'material_code',
      render: (_: any, row) => (
        <Space>
          <Button size="small" onClick={() => setPickerOpen(true)}>
            选择
          </Button>
          {row.material_id ? (
            <Text>
              {row.material_code} {row.material_name}
            </Text>
          ) : (
            <Text type="secondary">未选择</Text>
          )}
        </Space>
      ),
    },
    {
      title: '数量',
      dataIndex: 'quantity',
      width: 140,
      render: (_: any, row, idx) => (
        <InputNumber
          min={0}
          step={1}
          value={row.quantity}
          style={{ width: 120 }}
          onChange={(v) => {
            setOutputs((prev) => {
              const next = prev.slice()
              next[idx] = { ...next[idx], quantity: v ?? 0 }
              return next
            })
          }}
        />
      ),
    },
    {
      title: '口径',
      dataIndex: 'multiplier',
      width: 160,
      render: (_: any, row, idx) => (
        <Select
          value={row.multiplier || 'per_order'}
          style={{ width: 140 }}
          options={[
            { label: '每单', value: 'per_order' },
            { label: '每包裹', value: 'per_package' },
          ]}
          onChange={(v) => {
            setOutputs((prev) => {
              const next = prev.slice()
              next[idx] = { ...next[idx], multiplier: v }
              return next
            })
          }}
        />
      ),
    },
    {
      title: '操作',
      width: 80,
      render: (_: any, _row, idx) => (
        <Button
          size="small"
          danger
          icon={<DeleteOutlined />}
          onClick={() => setOutputs((prev) => prev.filter((_, i) => i !== idx))}
        />
      ),
    },
  ]

  const columns: ColumnsType<ShippingRule> = [
    {
      title: '启用',
      dataIndex: 'is_active',
      width: 80,
      render: (v) => (v ? <Tag color="green">启用</Tag> : <Tag>停用</Tag>),
    },
    {
      title: '规则名称',
      dataIndex: 'rule_name',
      render: (v, r) => (
        <Space direction="vertical" size={0}>
          <Text strong>{v}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {summarizeConditions((r.conditions || {}) as any)}
          </Text>
        </Space>
      ),
    },
    { title: '优先级', dataIndex: 'priority', width: 90 },
    {
      title: '产出行数',
      width: 90,
      render: (_: any, r) => <Text>{(r.outputs || []).length}</Text>,
    },
    {
      title: '操作',
      width: 160,
      render: (_: any, r) => (
        <Space>
          <Button size="small" type="link" onClick={() => openEditor(r)}>
            编辑
          </Button>
          <Button
            size="small"
            type="link"
            danger
            onClick={() => {
              Modal.confirm({
                title: '删除规则？',
                content: '删除后不可恢复（会归档）。',
                okText: '删除',
                okButtonProps: { danger: true },
                cancelText: '取消',
                onOk: () => archiveMutation.mutate(r),
              })
            }}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ]

  const items = (listQuery.data?.items ?? []) as ShippingRule[]

  return (
    <div style={{ padding: 16 }}>
      <Card
        title="发货规则（条件物料）"
        extra={
          <Space>
            <Input
              allowClear
              placeholder="搜索规则名"
              value={filters.search}
              onChange={(e) => setFilters((p) => ({ ...p, search: e.target.value }))}
              style={{ width: 220 }}
            />
            <Select
              allowClear
              placeholder="启用状态"
              value={filters.is_active}
              style={{ width: 140 }}
              options={[
                { label: '启用', value: true },
                { label: '停用', value: false },
              ]}
              onChange={(v) => setFilters((p) => ({ ...p, is_active: v }))}
            />
            <Button type="primary" icon={<PlusOutlined />} loading={createMutation.isPending} onClick={() => createMutation.mutate()}>
              新增规则
            </Button>
          </Space>
        }
      >
        <Table
          rowKey="id"
          columns={columns}
          dataSource={items}
          loading={listQuery.isFetching}
          pagination={{
            current: page.current,
            pageSize: page.pageSize,
            total: listQuery.data?.total ?? 0,
            showSizeChanger: true,
            onChange: (current, pageSize) => setPage({ current, pageSize }),
          }}
        />
      </Card>

      <Card title="规则测试台（MVP）" style={{ marginTop: 16 }}>
        <Form
          form={testForm}
          layout="inline"
          initialValues={{ is_merge: 'any', package_count: 1 }}
          onFinish={() => testMutation.mutate()}
        >
          <Form.Item label="店铺" name="shop_code">
            <Input style={{ width: 120 }} />
          </Form.Item>
          <Form.Item label="物流" name="shipping_method">
            <Input style={{ width: 120 }} />
          </Form.Item>
          <Form.Item label="合单" name="is_merge">
            <Select
              style={{ width: 110 }}
              options={[
                { label: '不限', value: 'any' },
                { label: '是', value: 'true' },
                { label: '否', value: 'false' },
              ]}
            />
          </Form.Item>
          <Form.Item label="省" name="province">
            <Input style={{ width: 120 }} />
          </Form.Item>
          <Form.Item label="重量kg" name="weight_kg">
            <InputNumber style={{ width: 110 }} min={0} step={0.01} />
          </Form.Item>
          <Form.Item label="体积m³" name="volume_m3">
            <InputNumber style={{ width: 110 }} min={0} step={0.0001} />
          </Form.Item>
          <Form.Item label="包裹数" name="package_count">
            <InputNumber style={{ width: 90 }} min={1} step={1} />
          </Form.Item>
          <Form.Item label="tokens" name="tokens">
            <Input placeholder="逗号分隔" style={{ width: 200 }} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={testMutation.isPending}>
              计算
            </Button>
          </Form.Item>
        </Form>

        {testResp ? (
          <div style={{ marginTop: 12 }}>
            <Space direction="vertical" style={{ width: '100%' }}>
              <div>
                <Text strong>命中规则：</Text>{' '}
                {(testResp.matched_rules || []).length ? (
                  <Space wrap>
                    {testResp.matched_rules.map((x) => (
                      <Tag key={x.rule_id}>
                        {x.rule_name}（{x.priority}）
                      </Tag>
                    ))}
                  </Space>
                ) : (
                  <Text type="secondary">无</Text>
                )}
              </div>
              <div>
                <Text strong>追加物料：</Text>
                <Table
                  size="small"
                  rowKey="material_id"
                  pagination={false}
                  dataSource={testResp.lines || []}
                  columns={[
                    { title: '编码', dataIndex: 'material_code', width: 120 },
                    { title: '名称', dataIndex: 'material_name' },
                    { title: '数量', dataIndex: 'quantity', width: 120 },
                    { title: '单位', dataIndex: 'unit_of_measure', width: 90 },
                  ]}
                  style={{ marginTop: 8 }}
                />
              </div>
              {(testResp.warnings || []).length ? (
                <div>
                  <Text strong>告警：</Text>
                  <ul style={{ marginTop: 6 }}>
                    {testResp.warnings.map((w, i) => (
                      <li key={i}>
                        <Text type="danger">{w}</Text>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </Space>
          </div>
        ) : null}
      </Card>

      <Drawer
        open={drawerOpen}
        onClose={() => {
          setDrawerOpen(false)
          setEditing(null)
          setOutputs([])
          form.resetFields()
        }}
        width={980}
        title="编辑发货规则"
        extra={
          <Space>
            <Button onClick={() => setOutputs((prev) => prev.concat([{ key: String(Date.now()), quantity: 1, multiplier: 'per_order' }]))}>
              + 产出行
            </Button>
            <Button type="primary" loading={saveMutation.isPending} onClick={() => saveMutation.mutate()}>
              保存
            </Button>
          </Space>
        }
      >
        <Row gutter={16}>
          <Col span={12}>
            <Card size="small" title="规则基础">
              <Form form={form} layout="vertical" initialValues={{ priority: 100, is_active: true, is_merge: 'any' }}>
                <Form.Item label="规则名称" name="rule_name" rules={[{ required: true, message: '请输入规则名称' }]}>
                  <Input />
                </Form.Item>
                <Row gutter={12}>
                  <Col span={12}>
                    <Form.Item label="优先级" name="priority" rules={[{ required: true, message: '请输入优先级' }]}>
                      <InputNumber min={0} step={1} style={{ width: '100%' }} />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item label="启用" name="is_active" valuePropName="checked">
                      <Switch />
                    </Form.Item>
                  </Col>
                </Row>
                <Form.Item label="店铺编码（多个用逗号）" name="shop_codes">
                  <Input placeholder="QM1,QH2..." />
                </Form.Item>
                <Form.Item label="物流方式（多个用逗号）" name="shipping_methods">
                  <Input placeholder="顺丰,京东..." />
                </Form.Item>
                <Form.Item label="合单" name="is_merge">
                  <Select
                    options={[
                      { label: '不限', value: 'any' },
                      { label: '是', value: 'true' },
                      { label: '否', value: 'false' },
                    ]}
                  />
                </Form.Item>
                <Form.Item label="省份（多个用逗号）" name="province_in">
                  <Input placeholder="浙江,江苏..." />
                </Form.Item>
                <Row gutter={12}>
                  <Col span={12}>
                    <Form.Item label="最小重量kg" name="min_weight_kg">
                      <InputNumber min={0} step={0.01} style={{ width: '100%' }} />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item label="最大重量kg" name="max_weight_kg">
                      <InputNumber min={0} step={0.01} style={{ width: '100%' }} />
                    </Form.Item>
                  </Col>
                </Row>
                <Row gutter={12}>
                  <Col span={12}>
                    <Form.Item label="最小体积m³" name="min_volume_m3">
                      <InputNumber min={0} step={0.0001} style={{ width: '100%' }} />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item label="最大体积m³" name="max_volume_m3">
                      <InputNumber min={0} step={0.0001} style={{ width: '100%' }} />
                    </Form.Item>
                  </Col>
                </Row>
                <Form.Item label="tokens(any)（多个用逗号）" name="has_tokens_any">
                  <Input placeholder="礼盒,赠品..." />
                </Form.Item>
                <Form.Item label="tokens(all)（多个用逗号）" name="has_tokens_all">
                  <Input placeholder="必须同时满足的tokens" />
                </Form.Item>
                <Form.Item name="stop_on_hit" valuePropName="checked">
                  <Checkbox>命中即停止（少用，一般包装是叠加规则）</Checkbox>
                </Form.Item>
                <Form.Item label="备注" name="notes">
                  <Input.TextArea rows={3} />
                </Form.Item>
              </Form>
            </Card>
          </Col>
          <Col span={12}>
            <Card
              size="small"
              title={
                <Space>
                  <span>产出物料行（仅条件物料）</span>
                  <Tag color="blue">usage_class=conditional</Tag>
                </Space>
              }
              extra={
                <Button size="small" onClick={() => setPickerOpen(true)}>
                  选择条件物料
                </Button>
              }
            >
              <Table rowKey="key" size="small" pagination={false} columns={outputColumns} dataSource={outputs} />
              <div style={{ marginTop: 8 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  说明：这里不做“产品模型变体”，只追加发货侧条件物料，未来用于按单扣库/发货成本。
                </Text>
              </div>
            </Card>
          </Col>
        </Row>
      </Drawer>

      <MaterialPickerDrawer
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        title="选择条件物料"
        initialTab="real"
        defaultOnlyBom={true}
        maxSelection={1}
        realQueryOverrides={{ usage_class: 'conditional', is_bom_material: true, status: 'active', is_active: true }}
        onConfirm={(res) => {
          if (res.kind !== 'bom' && res.kind !== 'real') return
          const m = (res.materials?.[0] as Material | undefined) || null
          if (!m) return
          setOutputs((prev) => {
            const next = prev.slice()
            // pick first empty row, otherwise append
            const idx = next.findIndex((x) => !x.material_id)
            const row: OutputRow = {
              key: idx >= 0 ? next[idx].key : String(Date.now()),
              material_id: m.id,
              material_code: m.material_code,
              material_name: m.material_name,
              quantity: idx >= 0 ? next[idx].quantity ?? 1 : 1,
              multiplier: idx >= 0 ? next[idx].multiplier ?? 'per_order' : 'per_order',
            }
            if (idx >= 0) next[idx] = row
            else next.push(row)
            return next
          })
        }}
      />
    </div>
  )
}

export default ShippingRulesPage


