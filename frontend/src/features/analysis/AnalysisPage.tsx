/** Análisis — el terminal financiero de ARCA.
 *
 *  La estética es de trading (densidad, crosshair, volumen bajo la curva,
 *  sparklines) pero la honestidad es contable: la curva es el efectivo REAL
 *  reconstruido del libro, y el tramo punteado no es un pronóstico — son los
 *  compromisos ya registrados, en su fecha. Donde un exchange te enseña velas,
 *  ARCA te enseña si vas a poder pagar la nómina.
 */

import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Area,
  Bar,
  Brush,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from '@/api/client'
import { formatCompact, formatDate, formatMoney } from '@/lib/format'
import type { AgingReport, CashProjection, DashboardSummary, NetWorth } from '@/types/api'

/* Lenguaje de color del terminal: teal = entra/tienes, oro = sale,
 * rojo = riesgo. Nunca se mezcla con la semántica pos/neg de la app. */
const C = {
  in: '#2c9aa6',
  out: '#c29938',
  risk: '#e05252',
}

const CATEGORY_PALETTE = [
  '#2c9aa6',
  '#c29938',
  '#7c6bd6',
  '#5b8ff9',
  '#3d8c66',
  '#b8618f',
  '#e05252',
  '#8a97a0',
]

const RANGES = [
  { days: 30, label: '1M' },
  { days: 90, label: '3M' },
  { days: 180, label: '6M' },
  { days: 365, label: '1A' },
]

interface SeriesPoint {
  date: string
  balance: string
  inflow: string
  outflow: string
}

interface SeriesAccount {
  id: string
  name: string
  type: string
  balance: string
  series: string[]
  change: string
}

interface CashSeries {
  start: string
  end: string
  points: SeriesPoint[]
  accounts: SeriesAccount[]
  avg_monthly_burn: string | null
  runway_months: string | null
}

/** Celda del listón superior: la cifra manda, la etiqueta susurra. */
function Tick({
  label,
  value,
  hint,
  tone,
}: {
  label: string
  value: string
  hint?: string
  tone?: 'pos' | 'neg' | 'warn'
}) {
  const toneClass = tone === 'pos' ? 'text-pos' : tone === 'neg' ? 'text-neg' : tone === 'warn' ? 'text-warn' : ''
  return (
    <div className="flex min-w-[7.5rem] flex-col gap-0.5 border-l border-border px-3 first:border-l-0 first:pl-0">
      <span className="figures text-[9px] uppercase tracking-[0.18em] text-muted">{label}</span>
      <span className={`figures text-sm font-semibold ${toneClass}`}>{value}</span>
      {hint ? <span className="figures text-[10px] text-muted">{hint}</span> : null}
    </div>
  )
}

function PanelTitle({ children, right }: { children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="mb-2 flex items-center justify-between gap-2">
      <span className="figures text-[10px] font-semibold uppercase tracking-[0.18em] tracking-wider text-muted">
        {children}
      </span>
      {right}
    </div>
  )
}

/** Sparkline de una cuenta: 30 días en 120×30 px, sin ejes ni ruido. */
function Sparkline({ values, positive }: { values: number[]; positive: boolean }) {
  const data = values.map((v, i) => ({ i, v }))
  const color = positive ? C.in : C.risk
  return (
    <div className="h-8 w-28">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id={`spark-${positive}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.35} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <YAxis hide domain={['dataMin', 'dataMax']} />
          <Area
            type="monotone"
            dataKey="v"
            stroke={color}
            strokeWidth={1.5}
            fill={`url(#spark-${positive})`}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

const tooltipBox = {
  background: 'var(--color-surface)',
  border: '1px solid var(--color-border)',
  borderRadius: 8,
  fontSize: 12,
  padding: '8px 10px',
}

function CashTooltip({ active, payload, label }: { active?: boolean; payload?: { payload: Record<string, number | null> }[]; label?: string }) {
  if (!active || !payload?.length) return null
  const row = payload[0].payload
  const projected = row.projected != null && row.balance == null
  return (
    <div style={tooltipBox} className="figures">
      <div className="mb-1 font-semibold">
        {formatDate(String(label))}
        {projected ? <span className="ml-2 text-[10px] uppercase tracking-wider text-muted">proyectado</span> : null}
      </div>
      <div>Saldo {formatMoney(projected ? row.projected : row.balance)}</div>
      {!projected && Number(row.inflow) > 0 ? (
        <div style={{ color: C.in }}>+ {formatMoney(row.inflow)}</div>
      ) : null}
      {!projected && Number(row.outflow) > 0 ? (
        <div style={{ color: C.out }}>− {formatMoney(row.outflow)}</div>
      ) : null}
    </div>
  )
}

export function AnalysisPage() {
  const [days, setDays] = useState(90)

  const seriesQuery = useQuery({
    queryKey: ['analysis', 'cash-series', days],
    queryFn: async () => (await api.get<CashSeries>(`/reports/cash-series?days=${days}`)).data,
  })
  const projectionQuery = useQuery({
    queryKey: ['analysis', 'projection'],
    queryFn: async () => (await api.get<CashProjection>('/reports/cash-projection?days=90')).data,
  })
  const summaryQuery = useQuery({
    queryKey: ['dashboard'],
    queryFn: async () => (await api.get<DashboardSummary>('/dashboard/summary')).data,
  })
  const agingQuery = useQuery({
    queryKey: ['reports', 'aging', 'receivable'],
    queryFn: async () => (await api.get<AgingReport>('/reports/aging?kind=receivable')).data,
  })
  const netWorthQuery = useQuery({
    queryKey: ['reports', 'net-worth'],
    queryFn: async () => (await api.get<NetWorth>('/reports/net-worth?months=12')).data,
  })
  const categoryQuery = useQuery({
    queryKey: ['analysis', 'category-series'],
    queryFn: async () =>
      (
        await api.get<{ categories: string[]; points: Record<string, string>[] }>(
          '/reports/category-series?months=6',
        )
      ).data,
  })

  const series = seriesQuery.data
  const summary = summaryQuery.data
  const aging = agingQuery.data
  const worth = netWorthQuery.data

  /* Historia sólida + compromisos punteados en un solo eje de tiempo.
   * El primer punto proyectado duplica el último real para que la línea
   * punteada nazca de la curva, no flotando. */
  const chartData = useMemo(() => {
    if (!series) return []
    const past = series.points.map((p) => ({
      date: p.date,
      balance: Number(p.balance),
      inflow: Number(p.inflow),
      outflow: Number(p.outflow),
      projected: null as number | null,
    }))
    const projection = projectionQuery.data
    if (!projection || past.length === 0) return past
    const last = past[past.length - 1]
    last.projected = last.balance
    const future = projection.points
      .filter((p) => p.date > last.date)
      .map((p) => ({
        date: p.date,
        balance: null as number | null,
        inflow: 0,
        outflow: 0,
        projected: Number(p.balance),
      }))
    return [...past, ...future]
  }, [series, projectionQuery.data])

  const shortfall = projectionQuery.data?.shortfall_date ?? null
  const shortfallPoint = shortfall ? chartData.find((p) => p.date === shortfall) : null

  const margin =
    summary && Number(summary.monthly_revenue) > 0
      ? ((Number(summary.monthly_profit) / Number(summary.monthly_revenue)) * 100).toFixed(1)
      : null

  const flowMax = useMemo(
    () => Math.max(1, ...chartData.map((p) => Math.max(p.inflow, p.outflow))),
    [chartData],
  )

  const runway = series?.runway_months != null ? Number(series.runway_months) : null

  return (
    <div className="space-y-3">
      {/* ── Listón de indicadores: el estado del negocio en una línea ── */}
      <div className="flex flex-wrap gap-y-2 overflow-x-auto rounded-xl border border-border bg-surface px-4 py-2.5 shadow-card">
        <Tick label="Disponible" value={summary ? formatMoney(summary.cash) : '—'} />
        <Tick
          label="Resultado mes"
          value={summary ? formatMoney(summary.monthly_profit) : '—'}
          tone={summary && Number(summary.monthly_profit) < 0 ? 'neg' : 'pos'}
        />
        <Tick label="Margen" value={margin != null ? `${margin}%` : '—'} />
        <Tick
          label="Te pagan en"
          value={aging ? `${aging.average_days} días` : '—'}
          tone={aging && aging.average_days > 30 ? 'warn' : undefined}
        />
        <Tick
          label="Runway"
          value={runway != null ? `${runway.toFixed(1)} meses` : '∞'}
          hint={runway != null ? 'a la quema actual' : 'flujo positivo'}
          tone={runway != null && runway < 3 ? 'neg' : undefined}
        />
        <Tick
          label="Deuda tarjetas"
          value={summary ? formatMoney(summary.card_debt) : '—'}
          tone={summary && Number(summary.card_debt) > 0 ? 'warn' : undefined}
        />
        <Tick label="Patrimonio" value={worth ? formatMoney(worth.net_worth) : '—'} />
        <Tick
          label="Vencido"
          value={aging ? formatMoney(aging.overdue) : '—'}
          tone={aging && Number(aging.overdue) > 0 ? 'neg' : undefined}
        />
      </div>

      <div className="grid gap-3 xl:grid-cols-3">
        {/* ── La curva: efectivo real + compromisos, con volumen debajo ── */}
        <div className="rounded-xl border border-border bg-surface p-4 shadow-card xl:col-span-2">
          <PanelTitle
            right={
              <div className="flex gap-1">
                {RANGES.map((range) => (
                  <button
                    key={range.days}
                    type="button"
                    onClick={() => setDays(range.days)}
                    className={`figures rounded px-2 py-0.5 text-[11px] font-semibold transition-colors ${
                      days === range.days
                        ? 'bg-accent text-on-accent'
                        : 'text-muted hover:bg-surface-2 hover:text-ink'
                    }`}
                  >
                    {range.label}
                  </button>
                ))}
              </div>
            }
          >
            Efectivo · historia y compromisos
          </PanelTitle>

          <div style={{ height: 340 }}>
            {chartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                  <defs>
                    <linearGradient id="cashfill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={C.in} stopOpacity={0.28} />
                      <stop offset="100%" stopColor={C.in} stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 10 }}
                    stroke="var(--color-muted)"
                    tickFormatter={(value: string) => formatDate(value).replace(' 2026', '')}
                    minTickGap={48}
                  />
                  <YAxis
                    yAxisId="cash"
                    orientation="right"
                    tick={{ fontSize: 10 }}
                    stroke="var(--color-muted)"
                    tickFormatter={(value: number) => formatCompact(value)}
                    width={52}
                    // El piso es 0 salvo que haya sobregiro real: un eje que baja
                    // a −400k "por estética" hace ver deuda donde no la hay.
                    domain={[(min: number) => Math.min(0, min), 'auto']}
                  />
                  {/* Volumen estilo trader: las barras viven pegadas al piso. */}
                  <YAxis yAxisId="flow" hide domain={[0, flowMax * 3.2]} />
                  <Tooltip
                    content={<CashTooltip />}
                    cursor={{ stroke: 'var(--color-muted)', strokeDasharray: '2 3' }}
                  />
                  <Bar yAxisId="flow" dataKey="inflow" fill={C.in} fillOpacity={0.55} isAnimationActive={false} />
                  <Bar yAxisId="flow" dataKey="outflow" fill={C.out} fillOpacity={0.55} isAnimationActive={false} />
                  <Area
                    yAxisId="cash"
                    type="monotone"
                    dataKey="balance"
                    stroke={C.in}
                    strokeWidth={2}
                    fill="url(#cashfill)"
                    isAnimationActive={false}
                    connectNulls={false}
                  />
                  <Line
                    yAxisId="cash"
                    type="monotone"
                    dataKey="projected"
                    stroke={C.in}
                    strokeWidth={1.5}
                    strokeDasharray="5 4"
                    dot={false}
                    isAnimationActive={false}
                    connectNulls={false}
                  />
                  {shortfallPoint ? (
                    <ReferenceDot
                      yAxisId="cash"
                      x={shortfallPoint.date}
                      y={shortfallPoint.projected ?? 0}
                      r={5}
                      fill={C.risk}
                      stroke="var(--color-surface)"
                      strokeWidth={2}
                    />
                  ) : null}
                  <Brush
                    dataKey="date"
                    height={26}
                    travellerWidth={8}
                    stroke="var(--color-muted)"
                    fill="var(--color-surface)"
                    tickFormatter={(value: string) => formatDate(value).replace(' 2026', '')}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full animate-pulse rounded-lg bg-surface-2" />
            )}
          </div>
          <p className="mt-2 text-[11px] text-muted">
            Línea sólida: tu efectivo, día a día, desde el libro. Punteada: compromisos ya
            registrados en su fecha de vencimiento — no es un pronóstico.
            {shortfall ? (
              <span className="ml-1 font-medium text-neg">
                El {formatDate(shortfall)} el saldo cruzaría a cero.
              </span>
            ) : null}
          </p>
        </div>

        {/* ── Watchlist de cuentas ── */}
        <div className="rounded-xl border border-border bg-surface p-4 shadow-card">
          <PanelTitle>Cuentas · 30 días</PanelTitle>
          <div className="divide-y divide-border">
            {(series?.accounts ?? []).map((account) => {
              const change = Number(account.change)
              const first = Number(account.series[0])
              const pct = first !== 0 ? (change / Math.abs(first)) * 100 : null
              return (
                <div key={account.id} className="flex items-center justify-between gap-2 py-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{account.name}</p>
                    <p className="figures text-xs text-muted">
                      {formatMoney(account.balance)}
                      <span className={`ml-2 ${change < 0 ? 'text-neg' : 'text-pos'}`}>
                        {change < 0 ? '▼' : '▲'} {formatCompact(Math.abs(change))}
                        {pct != null ? ` (${Math.abs(pct).toFixed(1)}%)` : ''}
                      </span>
                    </p>
                  </div>
                  <Sparkline
                    values={account.series.slice(-30).map(Number)}
                    positive={change >= 0}
                  />
                </div>
              )
            })}
            {summary && Number(summary.card_debt) > 0 ? (
              <div className="flex items-center justify-between gap-2 py-2">
                <div>
                  <p className="text-sm font-medium">Tarjetas de crédito</p>
                  <p className="figures text-xs text-muted">deuda viva</p>
                </div>
                <span className="figures text-sm font-semibold text-neg">
                  −{formatMoney(summary.card_debt)}
                </span>
              </div>
            ) : null}
          </div>

          {series?.avg_monthly_burn ? (
            <div className="mt-3 rounded-lg bg-surface-2/60 px-3 py-2 text-xs">
              <span className="text-muted">Quema neta promedio </span>
              <span className="figures font-semibold">
                {formatMoney(series.avg_monthly_burn)}/mes
              </span>
            </div>
          ) : null}
        </div>
      </div>

      {/* ── Fila de contexto: en qué se va, quién debe, cuánto vales ── */}
      <div className="grid gap-3 lg:grid-cols-3">
        <div className="rounded-xl border border-border bg-surface p-4 shadow-card">
          <PanelTitle>Gasto por categoría · 6 meses</PanelTitle>
          <div style={{ height: 190 }}>
            {categoryQuery.data ? (
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart
                  data={categoryQuery.data.points.map((p) => ({
                    ...Object.fromEntries(Object.entries(p).map(([k, v]) => [k, k === 'month' ? v : Number(v)])),
                  }))}
                  margin={{ top: 4, right: 4, bottom: 0, left: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
                  <XAxis
                    dataKey="month"
                    tick={{ fontSize: 10 }}
                    stroke="var(--color-muted)"
                    tickFormatter={(value: string) => value.slice(5)}
                  />
                  <YAxis
                    tick={{ fontSize: 10 }}
                    stroke="var(--color-muted)"
                    tickFormatter={(value: number) => formatCompact(value)}
                    width={44}
                  />
                  <Tooltip
                    contentStyle={tooltipBox}
                    formatter={(value: number, name: string) => [formatMoney(value), name]}
                    cursor={{ fill: 'var(--color-border)', fillOpacity: 0.3 }}
                  />
                  {categoryQuery.data.categories.map((name, index) => (
                    <Bar
                      key={name}
                      dataKey={name}
                      stackId="gasto"
                      fill={CATEGORY_PALETTE[index % CATEGORY_PALETTE.length]}
                      isAnimationActive={false}
                    />
                  ))}
                </ComposedChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full animate-pulse rounded-lg bg-surface-2" />
            )}
          </div>
        </div>

        <div className="rounded-xl border border-border bg-surface p-4 shadow-card">
          <PanelTitle
            right={
              aging ? (
                <span className="figures text-[11px] text-muted">
                  {formatMoney(aging.total)} en la calle
                </span>
              ) : null
            }
          >
            Cartera por antigüedad
          </PanelTitle>
          <div className="space-y-2 pt-1">
            {aging
              ? aging.buckets.map((bucket) => {
                  const amount = Number(aging.totals[bucket] ?? 0)
                  const total = Number(aging.total) || 1
                  const isRisk = bucket !== 'Por vencer'
                  return (
                    <div key={bucket}>
                      <div className="mb-0.5 flex justify-between text-[11px]">
                        <span className="text-muted">{bucket}</span>
                        <span className="figures">{amount > 0 ? formatMoney(amount) : '—'}</span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-surface-2">
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${Math.max((amount / total) * 100, amount > 0 ? 3 : 0)}%`,
                            background: isRisk ? C.risk : C.in,
                            opacity: bucket === '+90' ? 1 : isRisk ? 0.75 : 0.9,
                          }}
                        />
                      </div>
                    </div>
                  )
                })
              : null}
          </div>
          {aging ? (
            <p className="mt-3 text-[11px] text-muted">
              Te pagan en <span className="figures font-semibold text-ink">{aging.average_days} días</span>
              {aging.previous_average_days != null ? (
                <span className={aging.average_days <= aging.previous_average_days ? 'text-pos' : 'text-neg'}>
                  {' '}
                  {aging.average_days <= aging.previous_average_days ? '▼' : '▲'} vs hace un mes
                </span>
              ) : null}
            </p>
          ) : null}
        </div>

        <div className="rounded-xl border border-border bg-surface p-4 shadow-card">
          <PanelTitle
            right={
              worth ? (
                <span
                  className={`figures text-[11px] ${Number(worth.change_vs_previous_month) >= 0 ? 'text-pos' : 'text-neg'}`}
                >
                  {Number(worth.change_vs_previous_month) >= 0 ? '▲' : '▼'}{' '}
                  {formatCompact(Math.abs(Number(worth.change_vs_previous_month)))} este mes
                </span>
              ) : null
            }
          >
            Patrimonio · 12 meses
          </PanelTitle>
          <div style={{ height: 190 }}>
            {worth ? (
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart
                  data={worth.series.map((p) => ({ ...p, net_worth: Number(p.net_worth) }))}
                  margin={{ top: 4, right: 4, bottom: 0, left: 0 }}
                >
                  <defs>
                    <linearGradient id="worthfill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={C.in} stopOpacity={0.25} />
                      <stop offset="100%" stopColor={C.in} stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
                  <XAxis
                    dataKey="month"
                    tick={{ fontSize: 10 }}
                    stroke="var(--color-muted)"
                    tickFormatter={(value: string) => value.slice(5)}
                    minTickGap={24}
                  />
                  <YAxis
                    tick={{ fontSize: 10 }}
                    stroke="var(--color-muted)"
                    tickFormatter={(value: number) => formatCompact(value)}
                    width={48}
                  />
                  <Tooltip
                    contentStyle={tooltipBox}
                    formatter={(value: number) => [formatMoney(value), 'Patrimonio']}
                    cursor={{ stroke: 'var(--color-muted)', strokeDasharray: '2 3' }}
                  />
                  <Area
                    type="monotone"
                    dataKey="net_worth"
                    stroke={C.in}
                    strokeWidth={2}
                    fill="url(#worthfill)"
                    isAnimationActive={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full animate-pulse rounded-lg bg-surface-2" />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
