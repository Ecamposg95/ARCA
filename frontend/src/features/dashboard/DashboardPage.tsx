/** Inicio «Tablero del día»: cuánto dinero hay, qué hay que pagar esta semana,
 *  cómo van las sucursales y las ventas del año contra el anterior. Los filtros
 *  de unidad, contribuyente y semana viven en la URL: el tablero se comparte. */

import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { api } from '@/api/client'
import { DimensionFilterSelects, dimensionParams, type DimensionValues } from '@/components/ui/DimensionFields'
import { useDimensions } from '@/lib/hooks'
import { useAuthStore } from '@/stores/authStore'
import type { DashboardToday } from '@/types/api'
import { ApprovalStrip } from './ApprovalStrip'
import { BranchesPanel } from './BranchesPanel'
import { MoneyPanel } from './MoneyPanel'
import { SalesByMonthChart } from './SalesByMonthChart'
import { BranchesSkeleton, MoneySkeleton, WeekSkeleton } from './Skeletons'
import { WeekPayablesPanel } from './WeekPayablesPanel'

function weekLabel(start: string, end: string): string {
  const fmt = (iso: string) => {
    const [year, month, day] = iso.split('-').map(Number)
    return new Date(year, month - 1, day).toLocaleDateString('es-MX', { day: 'numeric', month: 'short' })
  }
  return `${fmt(start)} – ${fmt(end)}`
}

export function DashboardPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const userName = useAuthStore((state) => state.user?.name ?? '')
  const { hasUnits } = useDimensions()

  const dimensions: DimensionValues = {
    business_unit_id: searchParams.get('unidad') ?? '',
    fiscal_entity_id: searchParams.get('contribuyente') ?? '',
  }
  const weekOf = searchParams.get('semana') ?? ''
  const year = Number(searchParams.get('anio')) || new Date().getFullYear()

  const update = (changes: Record<string, string>) => {
    const params = new URLSearchParams(searchParams)
    for (const [key, value] of Object.entries(changes)) {
      if (value) params.set(key, value)
      else params.delete(key)
    }
    setSearchParams(params, { replace: true })
  }
  const setDimensions = (next: Partial<DimensionValues>) => {
    const merged = { ...dimensions, ...next }
    update({ unidad: merged.business_unit_id, contribuyente: merged.fiscal_entity_id })
  }

  const dims = dimensionParams(dimensions)
  const { data, isLoading, isError } = useQuery({
    queryKey: ['dashboard', 'today', dims, weekOf],
    queryFn: async () =>
      (await api.get<DashboardToday>('/dashboard/today', { params: { ...dims, ...(weekOf ? { week_of: weekOf } : {}) } })).data,
  })

  return (
    <div className="space-y-3">
      {/* Barra compacta: unidad · contribuyente · semana. Sólo lo que la empresa tiene. */}
      <div className="flex flex-wrap items-center gap-2">
        <DimensionFilterSelects value={dimensions} onChange={setDimensions} />
        <label className="flex items-center gap-2 text-xs text-muted">
          <span>Semana</span>
          <input
            type="date"
            aria-label="Semana"
            value={weekOf}
            onChange={(event) => update({ semana: event.target.value })}
            className="figures rounded-lg border border-border bg-surface px-2 py-1.5 text-sm text-ink"
          />
          {data ? <span className="figures hidden sm:inline">{weekLabel(data.week.start, data.week.end)}</span> : null}
        </label>
        {weekOf ? (
          <button type="button" className="text-xs text-accent hover:underline" onClick={() => update({ semana: '' })}>
            Hoy
          </button>
        ) : null}
      </div>

      {data ? <ApprovalStrip approvals={data.approvals} userName={userName} /> : null}

      {isError ? (
        <div className="panel px-4 py-6 text-center text-sm text-muted">No se pudo cargar el tablero. Intenta de nuevo en un momento.</div>
      ) : null}

      <div className="grid gap-3 lg:grid-cols-[300px_1.1fr_1.2fr]">
        {isLoading || !data ? (
          <>
            <MoneySkeleton />
            <WeekSkeleton />
            <BranchesSkeleton />
          </>
        ) : (
          <>
            <MoneyPanel money={data.money} />
            <WeekPayablesPanel week={data.week} />
            <BranchesPanel branches={data.branches} hasUnits={hasUnits} />
          </>
        )}
      </div>

      <SalesByMonthChart year={year} onYearChange={(next) => update({ anio: String(next) })} params={dims} />
    </div>
  )
}
