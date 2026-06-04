import { describe, expect, it } from 'vitest'
import { sanitizeParams, normalizeLineItems } from './planner'

describe('planner api helpers', () => {
  it('removes empty values from params', () => {
    const params = {
      status: 'draft',
      owner: '',
      tag: null,
      search: undefined,
      page: 2,
      cost: Number.NaN,
    }

    expect(sanitizeParams(params)).toEqual({ status: 'draft', page: 2 })
  })

  it('normalizes metadata json to metadata key', () => {
      const raw = [
        {
          id: 'line-1',
          package_id: 'pkg-1',
          type: 'material',
          description: 'Item',
          unit_of_measure: 'pcs',
          quantity: '10',
          unit_cost_estimate: '5',
          currency: 'CNY',
          status: 'draft',
          metadata_json: { foo: 'bar' },
          supplier_quotes: [],
          created_at: '',
          updated_at: '',
        },
      ] as any

    const normalized = normalizeLineItems(raw)
    expect(normalized[0].metadata).toEqual({ foo: 'bar' })
  })
})

