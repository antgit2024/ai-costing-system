import {
  Alert,
  Button,
  Drawer,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Spin,
  Switch,
  Typography,
  message,
} from 'antd'
import CloudSyncOutlined from '@ant-design/icons/lib/icons/CloudSyncOutlined'
import { useEffect, useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { isAxiosError } from 'axios'

import { fetchMaterial, fetchMaterialSyncJob, triggerMaterialSync, updateMaterial } from '@/services/planner'
import { MATERIAL_STATUS_OPTIONS } from '@/constants/planner'
import { BOM_UNIT_SELECT_OPTIONS } from '@/constants/calculationMethods'
import type { Material, MaterialStatusUpdatePayload } from '@/types/planner'

const { Text } = Typography

const formatRequestError = (err: unknown, fallback = '请求失败') => {
  if (isAxiosError(err)) {
    const data: any = err.response?.data
    return data?.detail ?? data?.message ?? err.message ?? fallback
  }
  return (err as any)?.message ?? fallback
}

interface MaterialDrawerProps {
  materialId: string | null
  open: boolean
  onClose: () => void
  onUpdated?: () => void
}

const MaterialDrawer = ({ materialId, open, onClose, onUpdated }: MaterialDrawerProps) => {
  const [form] = Form.useForm()
  const queryClient = useQueryClient()
  const materialQuery = useQuery({
    queryKey: ['material', materialId],
    queryFn: () => fetchMaterial(materialId as string),
    enabled: open && !!materialId,
  })
  const materialData = materialQuery.data as Material | undefined
  const conversionPurchaseValue = Form.useWatch('conversion_purchase_to_bom', form)
  const bomUnitValue = Form.useWatch('unit', form)

  const formatCurrency = (value?: number, currency?: string) => {
    if (value === undefined || value === null) return '-'
    try {
      return new Intl.NumberFormat('zh-CN', {
        style: 'currency',
        currency: currency || 'CNY',
        minimumFractionDigits: 2,
      }).format(Number(value))
    } catch {
      return `${value}`
    }
  }
  const materialMetadata = (materialData?.metadata_json as Record<string, any>) ?? {}
  const rawFormData = (materialMetadata.raw_form_data as Record<string, any>) ?? {}
  const purchaseSpec =
    rawFormData?.textField_lxo1y6ab ?? materialMetadata?.textField_lxo1y6ab ?? ''
  const purchaseUnitPrice = materialData?.unit_price !== undefined ? Number(materialData.unit_price) : undefined
  const yidaPurchaseUnit =
    (materialMetadata?.yida_purchase_unit ??
      rawFormData?.selectField_mjjgsdlp ??
      materialMetadata?.selectField_mjjgsdlp) ||
    ''
  const yidaPurchaseUnitPriceRaw =
    materialMetadata?.yida_purchase_unit_price ??
    rawFormData?.numberField_mjjgsdlr ??
    materialMetadata?.numberField_mjjgsdlr
  const yidaPurchaseUnitPrice =
    yidaPurchaseUnitPriceRaw !== undefined && yidaPurchaseUnitPriceRaw !== null && String(yidaPurchaseUnitPriceRaw).trim()
      ? Number(yidaPurchaseUnitPriceRaw)
      : undefined
  const purchaseToInboundFormula =
    materialMetadata?.purchase_to_inbound_formula ??
    rawFormData?.numberField_mjjgsdlq ??
    materialMetadata?.numberField_mjjgsdlq ??
    ''
  const computedBomUnitPrice = useMemo(() => {
    const basePrice = purchaseUnitPrice
    if (basePrice === undefined) {
      return undefined
    }
    const conversion = Number(conversionPurchaseValue || 0)
    if (!conversion) {
      return undefined
    }
    return basePrice / conversion
  }, [purchaseUnitPrice, conversionPurchaseValue])
  const bomUnitDisplay = bomUnitValue || materialData?.unit || materialData?.purchase_unit || '-'
  const sourceFormInstanceId =
    (materialMetadata?.source_form_instance_id as string | undefined) ||
    (materialMetadata?.form_instance_id as string | undefined) ||
    ''

  useEffect(() => {
    if (materialQuery.data) {
      const data = materialQuery.data as Material
      const metadata = (data.metadata_json as Record<string, any>) ?? {}
      form.setFieldsValue({
        is_bom_material: typeof data.is_bom_material === 'boolean' ? data.is_bom_material : false,
        unit: data.unit,
        inventory_unit: data.inventory_unit,
        conversion_purchase_to_bom: Number(data.conversion_purchase_to_bom) || 1,
        conversion_bom_to_inventory: Number(data.conversion_bom_to_inventory) || 1,
        status: data.status,
        local_description: (metadata.local_description as string) ?? '',
      })
    }
  }, [materialQuery.data, form])

  const mutation = useMutation({
    mutationFn: (payload: MaterialStatusUpdatePayload) =>
      updateMaterial(materialId as string, payload),
    onSuccess: () => {
      message.success('物料已保存')
      queryClient.invalidateQueries({ queryKey: ['material', materialId] })
      queryClient.invalidateQueries({ queryKey: ['materials'] })
      onUpdated?.()
      onClose()
    },
    onError: (error) => {
      message.error((error as Error).message || '保存失败')
    },
  })

  const handleSave = async () => {
    const values = await form.validateFields()
    const payload: MaterialStatusUpdatePayload = {
      is_bom_material: values.is_bom_material,
      unit: values.unit,
      inventory_unit: values.inventory_unit,
      conversion_purchase_to_bom: values.conversion_purchase_to_bom,
      conversion_bom_to_inventory: values.conversion_bom_to_inventory,
      status: values.status,
    }
    if (computedBomUnitPrice !== undefined && Number.isFinite(computedBomUnitPrice)) {
      payload.bom_unit_price = Number(Number(computedBomUnitPrice).toFixed(4))
    }
    const localDescription = (values.local_description ?? '').trim()
    payload.metadata_json = {
      local_description: localDescription || null,
    }
    mutation.mutate(payload)
  }

  const drawerTitle = useMemo(() => {
    if (!materialQuery.data) return '物料详情'
    return `物料详情 - ${materialQuery.data.material_name}`
  }, [materialQuery.data])

  return (
    <Drawer
      title={drawerTitle}
      width={520}
      open={open}
      onClose={onClose}
      destroyOnClose
      extra={
        materialData ? (
          <Button
            icon={<CloudSyncOutlined />}
            onClick={async () => {
              try {
                const job = await triggerMaterialSync({
                  requested_by: 'material_drawer',
                  limit: 5000,
                  material_codes: [materialData.material_code],
                })
                message.success('已触发同步任务，正在刷新…')
                const jobId = (job as any)?.id
                if (jobId) {
                  for (let i = 0; i < 20; i++) {
                    await new Promise((r) => setTimeout(r, 1000))
                    let current: any
                    try {
                      current = await fetchMaterialSyncJob(jobId)
                    } catch (e) {
                      message.error(formatRequestError(e, '查询同步任务失败'))
                      break
                    }
                    if (current?.status === 'succeeded' || current?.status === 'completed') {
                      break
                    }
                    if (current?.status === 'failed') {
                      message.error(current?.error_message || '同步失败')
                      break
                    }
                  }
                }
                queryClient.invalidateQueries({ queryKey: ['material', materialId] })
                queryClient.invalidateQueries({ queryKey: ['materials'] })
              } catch (err: any) {
                message.error(formatRequestError(err, '同步失败'))
              }
            }}
          >
            同步宜搭
          </Button>
        ) : null
      }
    >
      {materialQuery.isLoading ? (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <Spin />
        </div>
      ) : (
        <Form layout="vertical" form={form}>
          <Form.Item label="BOM 物料" name="is_bom_material" valuePropName="checked">
            <Switch />
          </Form.Item>
          {materialData && (
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
              message={
                <Space direction="vertical" size={0}>
                  <Text>
                    来源表单实例ID：
                    {sourceFormInstanceId ? (
                      <Text
                        code
                        copyable={{
                          text: sourceFormInstanceId,
                          tooltips: ['复制', '已复制'],
                        }}
                        style={{ marginLeft: 6 }}
                      >
                        {sourceFormInstanceId}
                      </Text>
                    ) : (
                      <Text type="secondary" style={{ marginLeft: 6 }}>
                        -
                      </Text>
                    )}
                  </Text>
                  <Text>
                    入库单价/单位：
                    <Text strong>
                      {formatCurrency(materialData.unit_price, materialData.currency)} /{' '}
                      {materialData.purchase_unit || materialData.unit || '-'}
                    </Text>
                  </Text>
                  <Text>
                    采购单价/单位：
                    <Text strong>
                      {yidaPurchaseUnitPrice != null
                        ? `${formatCurrency(yidaPurchaseUnitPrice, materialData.currency)} / ${yidaPurchaseUnit || '-'}`
                        : '-'}
                    </Text>
                  </Text>
                  <Text>
                    采购→入库 换算：
                    <Text strong>
                      {(() => {
                        if (!purchaseToInboundFormula) return '-'
                        const num = Number(purchaseToInboundFormula)
                        const val = Number.isFinite(num) ? num : purchaseToInboundFormula
                        const pu = yidaPurchaseUnit || '采购单位'
                        const iu = materialData.purchase_unit || materialData.unit || '-'
                        return `1${pu}=${val}${iu}`
                      })()}
                    </Text>
                  </Text>
                  {purchaseSpec && (
                    <Text>
                      采购规格：<Text strong>{purchaseSpec}</Text>
                    </Text>
                  )}
                </Space>
              }
            />
          )}
          <Form.Item label="本地描述" name="local_description">
            <Input.TextArea rows={3} placeholder="记录本地说明，仅在本系统内可见" />
          </Form.Item>
          <Form.Item label="BOM 单价/单位">
            <div style={{ lineHeight: 1.6 }}>
              <Text strong>{formatCurrency(computedBomUnitPrice, materialData?.currency)}</Text>
              <Text type="secondary" style={{ marginLeft: 8 }}>
                / {bomUnitDisplay}
              </Text>
              <div>
                <Text type="secondary">根据入库单价与换算系数实时计算，用于绑定虚拟物料</Text>
              </div>
            </div>
          </Form.Item>
          <Form.Item label="BOM 单位" name="unit" rules={[{ required: true, message: '请选择单位' }]}>
            <Select options={BOM_UNIT_SELECT_OPTIONS} />
          </Form.Item>
          <Form.Item
            label="入库→BOM 换算"
            name="conversion_purchase_to_bom"
            rules={[
              { required: true, message: '请输入转换系数' },
              { type: 'number', min: 0.00001, message: '需大于 0' },
            ]}
          >
            <InputNumber min={0.00001} step={0.0001} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="库存单位" name="inventory_unit" rules={[{ required: true, message: '请输入库存单位' }]}>
            <Input />
          </Form.Item>
          <Form.Item
            label="BOM→库存 换算"
            name="conversion_bom_to_inventory"
            rules={[
              { required: true, message: '请输入转换系数' },
              { type: 'number', min: 0.00001, message: '需大于 0' },
            ]}
          >
            <InputNumber min={0.00001} step={0.0001} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="状态" name="status" rules={[{ required: true }]}>
            <Select options={MATERIAL_STATUS_OPTIONS} />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button onClick={onClose}>取消</Button>
              <Button type="primary" loading={mutation.isPending} onClick={handleSave}>
                保存
              </Button>
            </Space>
          </Form.Item>
        </Form>
      )}
    </Drawer>
  )
}

export default MaterialDrawer

