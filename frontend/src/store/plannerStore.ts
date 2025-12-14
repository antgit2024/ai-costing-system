import { create } from 'zustand'
import type { Initiative, PackageNode, ScenarioListQueryParams } from '@/types/planner'

export interface PlannerSelectionState {
  selectedInitiativeId?: string
  selectedInitiative?: Initiative | null
  selectedPackageId?: string
  packageTree: PackageNode[]
  setSelectedInitiativeId: (id?: string) => void
  setSelectedInitiative: (initiative?: Initiative | null) => void
  setSelectedPackageId: (id?: string) => void
  setPackageTree: (tree: PackageNode[]) => void
  reset: () => void
}

export interface ScenarioFilterState {
  scenarioFilters: ScenarioListQueryParams
  setScenarioFilters: (filters: Partial<ScenarioListQueryParams>) => void
  scenarioFavorites: Record<string, boolean>
  toggleScenarioFavoriteLocal: (id: string, value?: boolean) => void
  benchmarkFavorites: Record<string, string>
  setBenchmarkFavorite: (suggestionId: string, favoriteId?: string) => void
}

export type PlannerStore = PlannerSelectionState & ScenarioFilterState

const initialScenarioFilters: ScenarioListQueryParams = {
  page: 1,
  page_size: 20,
}

export const usePlannerStore = create<PlannerStore>((set) => ({
  selectedInitiativeId: undefined,
  selectedInitiative: null,
  selectedPackageId: undefined,
  packageTree: [],
  scenarioFilters: initialScenarioFilters,
  scenarioFavorites: {},
  benchmarkFavorites: {},
  setSelectedInitiativeId: (id) => set({ selectedInitiativeId: id }),
  setSelectedInitiative: (initiative) => set({ selectedInitiative: initiative ?? null }),
  setSelectedPackageId: (id) => set({ selectedPackageId: id }),
  setPackageTree: (tree) => set({ packageTree: tree }),
  setScenarioFilters: (filters) =>
    set((state) => {
      const shouldResetPage =
        filters.page === undefined &&
        Object.keys(filters).some((key) => key !== 'page' && key !== 'page_size' && filters[key as keyof typeof filters] !== undefined)
      const nextPage =
        filters.page ??
        (shouldResetPage || filters.page_size !== undefined ? 1 : state.scenarioFilters.page)
      return {
        scenarioFilters: {
          ...state.scenarioFilters,
          ...filters,
          page: nextPage,
          page_size: filters.page_size ?? state.scenarioFilters.page_size,
        },
      }
    }),
  toggleScenarioFavoriteLocal: (id, value) =>
    set((state) => {
      const next = { ...state.scenarioFavorites }
      const nextValue = value ?? !next[id]
      if (!nextValue) {
        delete next[id]
      } else {
        next[id] = true
      }
      return { scenarioFavorites: next }
    }),
  setBenchmarkFavorite: (suggestionId, favoriteId) =>
    set((state) => {
      const next = { ...state.benchmarkFavorites }
      if (!favoriteId) {
        delete next[suggestionId]
      } else {
        next[suggestionId] = favoriteId
      }
      return { benchmarkFavorites: next }
    }),
  reset: () =>
    set({
      selectedInitiativeId: undefined,
      selectedInitiative: null,
      selectedPackageId: undefined,
      packageTree: [],
      scenarioFilters: initialScenarioFilters,
      scenarioFavorites: {},
      benchmarkFavorites: {},
    }),
}))

