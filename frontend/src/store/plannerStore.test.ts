import { describe, expect, it } from 'vitest'
import { usePlannerStore } from './plannerStore'

describe('planner store', () => {
  it('sets initiative and resets correctly', () => {
    const { setSelectedInitiativeId, setSelectedPackageId, reset } = usePlannerStore.getState()

    setSelectedInitiativeId('init-1')
    setSelectedPackageId('pkg-1')

    expect(usePlannerStore.getState().selectedInitiativeId).toBe('init-1')
    expect(usePlannerStore.getState().selectedPackageId).toBe('pkg-1')

    reset()
    expect(usePlannerStore.getState().selectedInitiativeId).toBeUndefined()
    expect(usePlannerStore.getState().selectedPackageId).toBeUndefined()
    expect(usePlannerStore.getState().packageTree).toEqual([])
  })

  it('stores initiative entity for reuse', () => {
    const { setSelectedInitiative } = usePlannerStore.getState()
    setSelectedInitiative({
      id: 'foo',
      name: 'Test',
      code: 'FOO',
      description: 'demo',
      owner_id: 'ops',
      sponsor: null,
      currency: 'CNY',
      status: 'draft',
      tags: [],
      target_launch_date: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    })
    expect(usePlannerStore.getState().selectedInitiative?.name).toBe('Test')
  })

  it('updates scenario filters and resets pagination', () => {
    const { setScenarioFilters, scenarioFilters } = usePlannerStore.getState()
    expect(scenarioFilters.page).toBe(1)
    expect(scenarioFilters.page_size).toBe(20)

    setScenarioFilters({ page: 3, page_size: 50, status: 'approved' })
    expect(usePlannerStore.getState().scenarioFilters.page).toBe(3)
    expect(usePlannerStore.getState().scenarioFilters.page_size).toBe(50)
    expect(usePlannerStore.getState().scenarioFilters.status).toBe('approved')

    setScenarioFilters({ search: 'OPS' })
    expect(usePlannerStore.getState().scenarioFilters.page).toBe(1)
    expect(usePlannerStore.getState().scenarioFilters.search).toBe('OPS')
  })

  it('toggles favorites locally', () => {
    const { toggleScenarioFavoriteLocal, scenarioFavorites, reset } = usePlannerStore.getState()
    expect(scenarioFavorites).toEqual({})

    toggleScenarioFavoriteLocal('sc-1', true)
    expect(usePlannerStore.getState().scenarioFavorites['sc-1']).toBe(true)

    toggleScenarioFavoriteLocal('sc-1', false)
    expect(usePlannerStore.getState().scenarioFavorites['sc-1']).toBeUndefined()

    toggleScenarioFavoriteLocal('sc-2')
    expect(usePlannerStore.getState().scenarioFavorites['sc-2']).toBe(true)
    reset()
    expect(usePlannerStore.getState().scenarioFavorites['sc-2']).toBeUndefined()
  })

  it('stores benchmark favorite ids', () => {
    const { setBenchmarkFavorite } = usePlannerStore.getState()
    setBenchmarkFavorite('sug-1', 'fav-1')
    expect(usePlannerStore.getState().benchmarkFavorites['sug-1']).toBe('fav-1')
    setBenchmarkFavorite('sug-1')
    expect(usePlannerStore.getState().benchmarkFavorites['sug-1']).toBeUndefined()
  })
})

