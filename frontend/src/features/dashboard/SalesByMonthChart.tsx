import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { formatCompact, formatMoney } from '@/lib/format'
import type { AnalyticsSeries } from '@/types/api'
import { ChartSkeleton } from './Skeletons'

const MONTHS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']

interface Row {
  month: string
  index: number
  hist: number | null
  live: number | null
  prev: number | null
  target: number | null
  partial: boolean
  origin: 'historical' | 'live' | null
}

function monthIndex(iso: string): number {
  return Number(iso.slice(5, 7)) - 1
}

/** Doce renglones, uno por mes. El mes frontera (primer punto vivo tras uno
 *  histórico) se repite en ambas líneas para que no quede hueco entre la
 *  punteada y la sólida. */
function buildRows(series: AnalyticsSeries): Row[] {
  const rows: Row[] = MONTHS.map((month, index) => ({
    month,
    index,
    hist: null,
    live: null,
    prev: null,
    target: null,
    partial: false,
    origin: null,
  }))
  for (const point of series.points) {
    const row = rows[monthIndex(point.period)]
    const value = Number(point.value)
    row.origin = point.origin
    row.partial = point.partial
    if (point.origin === 'historical') row.hist = value
    else row.live = value
  }
  const firstLive = rows.findIndex((row) => row.live !== null)
  if (firstLive > 0 && rows.slice(0, firstLive).some((row) => row.hist !== null)) {
    rows[firstLive].hist = rows[firstLive].live
  }
  for (const point of series.previous ?? []) rows[monthIndex(point.period)].prev = Number(point.value)
  for (const point of series.target ?? []) rows[monthIndex(point.period)].target = Number(point.value)
  return rows
}

function openingLabel(iso: string): string {
  const [year, month, day] = iso.split('-').map(Number)
  const date = new Date(year, month - 1, day)
  return `${date.getDate()} ${MONTHS[date.getMonth()]} · inicia ONE Finance`
}

function SeriesTooltip({ active, payload, year }: { active?: boolean; payload?: { payload: Row }[]; year: number }) {
  if (!active || !payload?.length) return null
  const row = payload[0].payload
  const current = row.live ?? row.hist
  const originLabel = row.partial ? 'en curso' : row.origin === 'historical' ? 'histórico' : row.origin === 'live' ? 'en ONE Finance' : null
  const delta = current !== null && row.prev ? ((current - row.prev) / row.prev) * 100 : null
  return (
    <div className="rounded-lg border border-border bg-surface-2 px-3 py-2 text-xs shadow-none">
      <div className="text-muted">
        {row.month} {year}
        {originLabel ? ` · ${originLabel}` : ''}
      </div>
      {current !== null ? (
        <div className="figures mt-0.5 text-sm font-medium text-ink">
          {formatMoney(current)}
          {delta !== null ? (
            <span className={`ml-2 text-xs ${delta >= 0 ? 'text-accent' : 'text-neg'}`}>
              {delta >= 0 ? '+' : '−'}
              {Math.abs(delta).toFixed(0)}% vs {year - 1}
            </span>
          ) : null}
        </div>
      ) : null}
      {row.prev !== null ? (
        <div className="figures mt-0.5 text-muted">
          {year - 1}: {formatMoney(row.prev)}
        </div>
      ) : null}
      {row.target !== null ? (
        <div className="figures mt-0.5 text-warn">Meta: {formatMoney(row.target)}</div>
      ) : null}
    </div>
  )
}

function LegendKey({ kind, label }: { kind: 'hist' | 'live' | 'prev' | 'target'; label: string }) {
  const style =
    kind === 'hist'
      ? 'border-t-2 border-dashed border-accent'
      : kind === 'live'
        ? 'border-t-[3px] border-accent'
        : kind === 'prev'
          ? 'border-t-2 border-muted'
          : 'border-t-2 border-dotted border-warn'
  return (
    <span className="flex items-center gap-1.5 text-[11.5px] text-muted">
      <span className={`inline-block w-4 ${style}`} />
      {label}
    </span>
  )
}

export function SalesByMonthChart({
  year,
  onYearChange,
  params,
}: {
  year: number
  onYearChange: (year: number) => void
  params: Record<string, string>
}) {
  const { data, isLoading } = useQuery({
    queryKey: ['analytics', 'series', year, params],
    queryFn: async () =>
      (
        await api.get<AnalyticsSeries>('/analytics/series', {
          params: {
            dataset: 'sales',
            metric: 'net_sales',
            grain: 'month',
            from: `${year}-01-01`,
            to: `${year}-12-31`,
            compare: 'previous_year',
            ...params,
          },
        })
      ).data,
  })
  if (isLoading || !data) return <ChartSkeleton />

  const rows = buildRows(data)
  const hasCurrent = data.points.length > 0
  const hasAnything = hasCurrent || (data.previous?.length ?? 0) > 0 || (data.target?.length ?? 0) > 0
  const last = [...data.points].reverse()[0]
  const openingIndex = data.opening_date && data.opening_date.slice(0, 4) === String(year) ? monthIndex(data.opening_date) : null
  const hasHist = rows.some((row) => row.origin === 'historical')
  const hasLive = rows.some((row) => row.origin === 'live')
  const axis = { tickLine: false, axisLine: false, fontSize: 10.5, stroke: 'var(--color-muted)' } as const

  return (
    <section
      className="panel min-w-0 p-4"
      aria-label={
        last
          ? `Ventas por mes ${year}: ${MONTHS[monthIndex(last.period)]} ${formatMoney(last.value)}`
          : `Ventas por mes ${year}: sin datos`
      }
    >
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div className="flex items-center gap-2">
          <h2 className="text-[13px] font-medium text-ink-soft">Ventas por mes</h2>
          <div className="flex items-center rounded-md border border-border text-xs">
            <button type="button" className="px-2 py-0.5 text-muted hover:text-ink" onClick={() => onYearChange(year - 1)} aria-label="Año anterior">
              ‹
            </button>
            <span className="figures px-1 text-ink">{year}</span>
            <button type="button" className="px-2 py-0.5 text-muted hover:text-ink" onClick={() => onYearChange(year + 1)} aria-label="Año siguiente">
              ›
            </button>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-x-3.5 gap-y-1">
          {hasHist ? <LegendKey kind="hist" label={`${year} histórico`} /> : null}
          {hasLive ? <LegendKey kind="live" label={`${year} en ONE Finance`} /> : null}
          {rows.some((row) => row.prev !== null) ? <LegendKey kind="prev" label={String(year - 1)} /> : null}
          {rows.some((row) => row.target !== null) ? <LegendKey kind="target" label="Meta" /> : null}
        </div>
      </div>
      {data.historical_note ? <p className="mt-1 text-xs text-muted">{data.historical_note}.</p> : null}

      {!hasAnything ? (
        <div className="mt-4 flex flex-col items-center justify-center rounded-lg border border-dashed border-border px-4 py-10 text-center">
          <p className="text-sm text-ink">Sin ventas registradas en {year}</p>
          <p className="mt-1 text-xs text-muted">Registra un ingreso de ventas o importa el reporte del punto de venta y la línea aparece aquí.</p>
          <div className="mt-4 flex gap-2">
            <Link to="/ingresos?nuevo=1">
              <Button variant="secondary">Registrar ingreso</Button>
            </Link>
            <Link to="/importar">
              <Button variant="secondary">Importar ventas</Button>
            </Link>
          </div>
        </div>
      ) : (
        <div className="mt-3 min-w-0 overflow-x-auto">
          <div className="min-w-[640px]">
            <ResponsiveContainer width="100%" height={240}>
              <ComposedChart data={rows} margin={{ top: 18, right: 12, bottom: 0, left: 0 }}>
                <CartesianGrid vertical={false} stroke="var(--color-border)" />
                <XAxis dataKey="month" {...axis} interval={0} />
                <YAxis {...axis} tickFormatter={formatCompact} width={54} />
                <Tooltip content={<SeriesTooltip year={year} />} cursor={{ stroke: 'var(--color-border)' }} />
                {openingIndex !== null ? (
                  <ReferenceLine
                    x={MONTHS[openingIndex]}
                    stroke="var(--color-muted)"
                    strokeDasharray="2 3"
                    label={{
                      value: openingLabel(data.opening_date!),
                      position: openingIndex >= 7 ? 'insideTopRight' : 'insideTopLeft',
                      fill: 'var(--color-ink-soft)',
                      fontSize: 10.5,
                    }}
                  />
                ) : null}
                <Line type="linear" dataKey="target" stroke="var(--color-warn)" strokeWidth={1.2} strokeDasharray="2 4" dot={false} isAnimationActive={false} connectNulls />
                <Line type="linear" dataKey="prev" stroke="var(--color-muted)" strokeWidth={1.5} dot={false} isAnimationActive={false} connectNulls />
                <Line type="linear" dataKey="hist" stroke="var(--color-accent)" strokeWidth={2} strokeDasharray="4 3" dot={false} isAnimationActive={false} />
                <Line
                  type="linear"
                  dataKey="live"
                  stroke="var(--color-accent)"
                  strokeWidth={2.5}
                  isAnimationActive={false}
                  dot={(props: { cx?: number; cy?: number; payload?: Row }) => {
                    const { cx, cy, payload } = props
                    if (!payload?.partial || cx === undefined || cy === undefined) return <g key={payload?.index} />
                    return (
                      <g key={payload.index}>
                        <circle cx={cx} cy={cy} r={4.5} fill="var(--color-surface)" stroke="var(--color-accent)" strokeWidth={2} />
                        <text x={cx} y={cy - 10} textAnchor="middle" fontSize={10.5} fill="var(--color-ink-soft)">
                          {payload.month} en curso
                        </text>
                      </g>
                    )
                  }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </section>
  )
}
