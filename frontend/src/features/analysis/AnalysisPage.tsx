/** Análisis — el terminal financiero de ARCA, en modo mercado.
 *
 *  Superficie deliberadamente negra en ambos temas (scope .terminal), velas
 *  semanales del efectivo con verde/rojo de mercado, volumen bajo la curva,
 *  watchlist con sparklines y la agenda de compromisos como "libro de órdenes".
 *  La estética es Binance; la honestidad es contable: cada número sale del
 *  libro y el tramo punteado no es pronóstico — son compromisos ya registrados.
 */

import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Area,
  Bar,
  Brush,
  CartesianGrid,
  Cell,
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

/* Verde/rojo de mercado para DIRECCIÓN (sube/baja); teal/oro de ARCA para
 * NATURALEZA (entra/sale). Dos lenguajes, nunca revueltos en el mismo trazo. */
const MKT = { up: '#0ecb81', down: '#f6465d' }
const C = { in: '#2c9aa6', out: '#c29938', risk: '#f6465d' }

const CATEGORY_PALETTE = [
  '#2c9aa6',
  '#c29938',
  '#7c6bd6',
  '#5b8ff9',
  '#3d8c66',
  '#b8618f',
  '#f6465d',
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

interface Candle {
  date: string
  open: number
  close: number
  high: number
  low: number
  range: [number, number]
  volume: number
  up: boolean
}

/** Velas semanales desde la serie diaria: apertura, cierre, máximo y mínimo
 *  del efectivo. Verde si la semana cerró arriba de donde abrió. */
function toCandles(points: SeriesPoint[]): Candle[] {
  const candles: Candle[] = []
  for (let i = 0; i < points.length; i += 7) {
    const chunk = points.slice(i, i + 7)
    const values = chunk.map((p) => Number(p.balance))
    const open = values[0]
    const close = values[values.length - 1]
    candles.push({
      date: chunk[chunk.length - 1].date,
      open,
      close,
      high: Math.max(...values),
      low: Math.min(...values),
      range: [Math.min(...values), Math.max(...values)],
      volume: chunk.reduce((sum, p) => sum + Number(p.inflow) + Number(p.outflow), 0),
      up: close >= open,
    })
  }
  return candles
}

/** El cuerpo y la mecha de la vela, dibujados dentro del rango [low, high]
 *  que recharts ya posicionó: interpolar evita depender de la escala. */
function CandleShape(props: {
  x?: number
  y?: number
  width?: number
  height?: number
  payload?: Candle
}) {
  const { x = 0, y = 0, width = 0, height = 0, payload } = props
  if (!payload) return <g />
  const { open, close, high, low, up } = payload
  const span = high - low
  const color = up ? MKT.up : MKT.down
  const cx = x + width / 2
  // Semana plana (sin movimientos): un guion al nivel del saldo.
  if (span <= 0 || height <= 0) {
    return <line x1={x + width * 0.2} y1={y} x2={x + width * 0.8} y2={y} stroke={color} strokeWidth={2} />
  }
  const yOf = (value: number) => y + ((high - value) / span) * height
  const bodyTop = yOf(Math.max(open, close))
  const bodyBottom = yOf(Math.min(open, close))
  const bodyHeight = Math.max(bodyBottom - bodyTop, 1.5)
  const bodyWidth = Math.max(width * 0.62, 3)
  return (
    <g>
      <line x1={cx} y1={y} x2={cx} y2={y + height} stroke={color} strokeWidth={1} />
      <rect x={cx - bodyWidth / 2} y={bodyTop} width={bodyWidth} height={bodyHeight} fill={color} rx={1} />
    </g>
  )
}

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
  const toneClass =
    tone === 'pos' ? 'text-pos' : tone === 'neg' ? 'text-neg' : tone === 'warn' ? 'text-warn' : ''
  return (
    <div className="flex min-w-[7rem] flex-col gap-0.5 border-l border-border px-3 first:border-l-0 first:pl-1">
      <span className="figures text-[9px] uppercase tracking-[0.18em] text-muted">{label}</span>
      <span className={`figures text-[13px] font-semibold ${toneClass}`}>{value}</span>
      {hint ? <span className="figures text-[10px] text-muted">{hint}</span> : null}
    </div>
  )
}

function PanelTitle({ children, right }: { children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="mb-2 flex items-center justify-between gap-2">
      <span className="figures text-[10px] font-semibold uppercase tracking-[0.18em] text-muted">
        {children}
      </span>
      {right}
    </div>
  )
}

function Sparkline({ values, positive }: { values: number[]; positive: boolean }) {
  const data = values.map((v, i) => ({ i, v }))
  const color = positive ? MKT.up : MKT.down
  return (
    <div className="h-8 w-24">
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
  color: 'var(--color-ink)',
}

function CashTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: { payload: Record<string, number | null> }[]
  label?: string
}) {
  if (!active || !payload?.length) return null
  const row = payload[0].payload
  const projected = row.projected != null && row.balance == null
  return (
    <div style={tooltipBox} className="figures">
      <div className="mb-1 font-semibold">
        {formatDate(String(label))}
        {projected ? (
          <span className="ml-2 text-[10px] uppercase tracking-wider" style={{ color: 'var(--color-muted)' }}>
            proyectado
          </span>
        ) : null}
      </div>
      <div>Saldo {formatMoney(projected ? row.projected : row.balance)}</div>
      {!projected && Number(row.inflow) > 0 ? (
        <div style={{ color: MKT.up }}>+ {formatMoney(row.inflow)}</div>
      ) : null}
      {!projected && Number(row.outflow) > 0 ? (
        <div style={{ color: C.out }}>− {formatMoney(row.outflow)}</div>
      ) : null}
    </div>
  )
}

function CandleTooltip({ active, payload }: { active?: boolean; payload?: { payload: Candle }[] }) {
  if (!active || !payload?.length) return null
  const candle = payload[0].payload
  return (
    <div style={tooltipBox} className="figures">
      <div className="mb-1 font-semibold">Semana al {formatDate(candle.date)}</div>
      <div>Abre {formatMoney(candle.open)}</div>
      <div style={{ color: candle.up ? MKT.up : MKT.down }}>Cierra {formatMoney(candle.close)}</div>
      <div style={{ color: 'var(--color-muted)' }}>
        Máx {formatCompact(candle.high)} · Mín {formatCompact(candle.low)}
      </div>
      <div style={{ color: 'var(--color-muted)' }}>Movió {formatCompact(candle.volume)}</div>
    </div>
  )
}

export function AnalysisPage() {
  const [days, setDays] = useState(90)
  const [mode, setMode] = useState<'curva' | 'velas'>('curva')

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

  const candles = useMemo(() => (series ? toCandles(series.points) : []), [series])

  const shortfall = projectionQuery.data?.shortfall_date ?? null
  const shortfallPoint = shortfall ? chartData.find((p) => p.date === shortfall) : null

  /* La agenda de compromisos: los próximos vencimientos con nombre y monto —
   * el "libro de órdenes" de un negocio real. */
  const commitments = useMemo(() => {
    const points = projectionQuery.data?.points ?? []
    return points.filter((p) => p.description).slice(0, 8)
  }, [projectionQuery.data])

  const margin =
    summary && Number(summary.monthly_revenue) > 0
      ? ((Number(summary.monthly_profit) / Number(summary.monthly_revenue)) * 100).toFixed(1)
      : null

  const flowMax = useMemo(
    () => Math.max(1, ...chartData.map((p) => Math.max(p.inflow, p.outflow))),
    [chartData],
  )

  const runway = series?.runway_months != null ? Number(series.runway_months) : null

  const rangeStats = useMemo(() => {
    if (!series || series.points.length === 0) return null
    const values = series.points.map((p) => Number(p.balance))
    const first = values[0]
    const last = values[values.length - 1]
    return {
      high: Math.max(...values),
      low: Math.min(...values),
      change: last - first,
      pct: first !== 0 ? ((last - first) / Math.abs(first)) * 100 : null,
    }
  }, [series])

  return (
    <div className="terminal -mx-4 -my-6 min-h-full bg-bg px-4 py-4 sm:-mx-6 sm:-my-8 sm:px-6 sm:py-5 lg:-mx-10 lg:px-10">
      {/* ── Listón: el estado del negocio en una línea de terminal ── */}
      <div className="flex flex-wrap gap-y-2 overflow-x-auto rounded-lg border border-border bg-surface px-3 py-2">
        <Tick label="Disponible" value={summary ? formatMoney(summary.cash) : '—'} />
        {rangeStats ? (
          <Tick
            label={`Cambio ${days}d`}
            value={`${rangeStats.change >= 0 ? '+' : '−'}${formatCompact(Math.abs(rangeStats.change))}${
              rangeStats.pct != null && Math.abs(rangeStats.pct) < 1000
                ? ` (${Math.abs(rangeStats.pct).toFixed(1)}%)`
                : ''
            }`}
            tone={rangeStats.change >= 0 ? 'pos' : 'neg'}
          />
        ) : null}
        <Tick
          label="Resultado mes"
          value={summary ? formatMoney(summary.monthly_profit) : '—'}
          tone={summary && Number(summary.monthly_profit) < 0 ? 'neg' : 'pos'}
        />
        <Tick label="Margen" value={margin != null ? `${margin}%` : '—'} />
        <Tick
          label="Te pagan en"
          value={aging ? `${aging.average_days}d` : '—'}
          tone={aging && aging.average_days > 30 ? 'warn' : undefined}
        />
        <Tick
          label="Runway"
          value={runway != null ? `${runway.toFixed(1)}m` : '∞'}
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

      <div className="mt-3 grid gap-3 xl:grid-cols-3">
        {/* ── La gráfica principal ── */}
        <div className="rounded-lg border border-border bg-surface p-3 xl:col-span-2">
          <PanelTitle
            right={
              <div className="flex items-center gap-2">
                <div className="flex overflow-hidden rounded border border-border">
                  {(['curva', 'velas'] as const).map((option) => (
                    <button
                      key={option}
                      type="button"
                      onClick={() => setMode(option)}
                      className={`figures px-2.5 py-0.5 text-[11px] font-semibold capitalize transition-colors ${
                        mode === option
                          ? 'bg-accent text-on-accent'
                          : 'text-muted hover:bg-surface-2 hover:text-ink'
                      }`}
                    >
                      {option}
                    </button>
                  ))}
                </div>
                <div className="flex gap-1">
                  {RANGES.map((range) => (
                    <button
                      key={range.days}
                      type="button"
                      onClick={() => setDays(range.days)}
                      className={`figures rounded px-2 py-0.5 text-[11px] font-semibold transition-colors ${
                        days === range.days ? 'bg-surface-2 text-ink' : 'text-muted hover:text-ink'
                      }`}
                    >
                      {range.label}
                    </button>
                  ))}
                </div>
              </div>
            }
          >
            Efectivo
            {rangeStats ? (
              <span className="ml-3 normal-case tracking-normal">
                <span style={{ color: MKT.up }}>Máx {formatCompact(rangeStats.high)}</span>
                <span className="mx-1">·</span>
                <span style={{ color: MKT.down }}>Mín {formatCompact(rangeStats.low)}</span>
              </span>
            ) : null}
          </PanelTitle>

          <div style={{ height: 330 }}>
            {chartData.length === 0 ? (
              <div className="h-full animate-pulse rounded bg-surface-2" />
            ) : mode === 'velas' ? (
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={candles} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 10 }}
                    stroke="var(--color-muted)"
                    tickFormatter={(value: string) => formatDate(value).replace(' 2026', '')}
                    minTickGap={40}
                  />
                  <YAxis
                    yAxisId="cash"
                    orientation="right"
                    tick={{ fontSize: 10 }}
                    stroke="var(--color-muted)"
                    tickFormatter={(value: number) => formatCompact(value)}
                    width={52}
                    domain={[(min: number) => Math.min(0, min), 'auto']}
                  />
                  <YAxis
                    yAxisId="vol"
                    hide
                    domain={[0, Math.max(1, ...candles.map((c) => c.volume)) * 3.2]}
                  />
                  <Tooltip
                    content={<CandleTooltip />}
                    cursor={{ fill: 'var(--color-border)', fillOpacity: 0.25 }}
                  />
                  <Bar yAxisId="vol" dataKey="volume" isAnimationActive={false} fillOpacity={0.45}>
                    {candles.map((candle) => (
                      <Cell key={candle.date} fill={candle.up ? MKT.up : MKT.down} />
                    ))}
                  </Bar>
                  <Bar yAxisId="cash" dataKey="range" shape={<CandleShape />} isAnimationActive={false} />
                </ComposedChart>
              </ResponsiveContainer>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                  <defs>
                    <linearGradient id="cashfill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={C.in} stopOpacity={0.3} />
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
                    domain={[(min: number) => Math.min(0, min), 'auto']}
                  />
                  <YAxis yAxisId="flow" hide domain={[0, flowMax * 3.2]} />
                  <Tooltip
                    content={<CashTooltip />}
                    cursor={{ stroke: 'var(--color-muted)', strokeDasharray: '2 3' }}
                  />
                  <Bar yAxisId="flow" dataKey="inflow" fill={MKT.up} fillOpacity={0.5} isAnimationActive={false} />
                  <Bar yAxisId="flow" dataKey="outflow" fill={C.out} fillOpacity={0.5} isAnimationActive={false} />
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
                    height={24}
                    travellerWidth={8}
                    stroke="var(--color-muted)"
                    fill="var(--color-surface)"
                    tickFormatter={(value: string) => formatDate(value).replace(' 2026', '')}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            )}
          </div>
          <p className="mt-2 text-[11px] text-muted">
            {mode === 'velas'
              ? 'Cada vela es una semana de tu efectivo: abre, cierra, máximo y mínimo. Verde si terminó arriba de donde empezó.'
              : 'Línea sólida: tu efectivo, día a día, desde el libro. Punteada: compromisos ya registrados en su fecha — no es un pronóstico.'}
            {shortfall ? (
              <span className="ml-1 font-medium text-neg">
                El {formatDate(shortfall)} el saldo cruzaría a cero.
              </span>
            ) : null}
          </p>
        </div>

        {/* ── Columna derecha: watchlist + agenda de compromisos ── */}
        <div className="flex flex-col gap-3">
          <div className="rounded-lg border border-border bg-surface p-3">
            <PanelTitle>Cuentas · 30 días</PanelTitle>
            <div className="divide-y divide-border">
              {(series?.accounts ?? []).map((account) => {
                const change = Number(account.change)
                const first = Number(account.series[0])
                const pct = first !== 0 ? (change / Math.abs(first)) * 100 : null
                return (
                  <div key={account.id} className="flex items-center justify-between gap-2 py-1.5">
                    <div className="min-w-0">
                      <p className="truncate text-[13px] font-medium">{account.name}</p>
                      <p className="figures text-[11px] text-muted">
                        {formatMoney(account.balance)}
                        <span className={`ml-2 ${change < 0 ? 'text-neg' : 'text-pos'}`}>
                          {change < 0 ? '▼' : '▲'} {formatCompact(Math.abs(change))}
                          {pct != null && Math.abs(pct) < 1000
                            ? ` (${Math.abs(pct).toFixed(1)}%)`
                            : ''}
                        </span>
                      </p>
                    </div>
                    <Sparkline values={account.series.slice(-30).map(Number)} positive={change >= 0} />
                  </div>
                )
              })}
              {summary && Number(summary.card_debt) > 0 ? (
                <div className="flex items-center justify-between gap-2 py-1.5">
                  <div>
                    <p className="text-[13px] font-medium">Tarjetas de crédito</p>
                    <p className="figures text-[11px] text-muted">deuda viva</p>
                  </div>
                  <span className="figures text-[13px] font-semibold text-neg">
                    −{formatMoney(summary.card_debt)}
                  </span>
                </div>
              ) : null}
            </div>
          </div>

          <div className="flex-1 rounded-lg border border-border bg-surface p-3">
            <PanelTitle
              right={
                projectionQuery.data ? (
                  <span className="figures text-[10px] text-muted">próximos 90 días</span>
                ) : null
              }
            >
              Agenda de compromisos
            </PanelTitle>
            {commitments.length === 0 ? (
              <p className="py-3 text-[12px] text-muted">
                Sin cobros ni pagos comprometidos por delante.
              </p>
            ) : (
              <div className="divide-y divide-border">
                {commitments.map((point, index) => {
                  const change = Number(point.change)
                  const inflow = change > 0
                  return (
                    <div
                      key={`${point.date}-${index}`}
                      className="flex items-center justify-between gap-2 py-1.5"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-[12px]">{point.description}</p>
                        <p className="figures text-[10px] text-muted">{formatDate(point.date)}</p>
                      </div>
                      <div className="shrink-0 text-right">
                        <p
                          className="figures text-[12px] font-semibold"
                          style={{ color: inflow ? MKT.up : MKT.down }}
                        >
                          {inflow ? '+' : '−'}
                          {formatCompact(Math.abs(change))}
                        </p>
                        <p className="figures text-[10px] text-muted">
                          → {formatCompact(Number(point.balance))}
                        </p>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Fila de contexto ── */}
      <div className="mt-3 grid gap-3 lg:grid-cols-3">
        <div className="rounded-lg border border-border bg-surface p-3">
          <PanelTitle>Gasto por categoría · 6 meses</PanelTitle>
          <div style={{ height: 185 }}>
            {categoryQuery.data ? (
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart
                  data={categoryQuery.data.points.map((p) => ({
                    ...Object.fromEntries(
                      Object.entries(p).map(([k, v]) => [k, k === 'month' ? v : Number(v)]),
                    ),
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
              <div className="h-full animate-pulse rounded bg-surface-2" />
            )}
          </div>
        </div>

        <div className="rounded-lg border border-border bg-surface p-3">
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
                      <div className="h-1.5 overflow-hidden rounded-full bg-surface-2">
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${Math.max((amount / total) * 100, amount > 0 ? 3 : 0)}%`,
                            background: isRisk ? MKT.down : MKT.up,
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
              Te pagan en{' '}
              <span className="figures font-semibold text-ink">{aging.average_days} días</span>
              {aging.previous_average_days != null ? (
                <span
                  className={
                    aging.average_days <= aging.previous_average_days ? 'text-pos' : 'text-neg'
                  }
                >
                  {' '}
                  {aging.average_days <= aging.previous_average_days ? '▼' : '▲'} vs hace un mes
                </span>
              ) : null}
            </p>
          ) : null}
        </div>

        <div className="rounded-lg border border-border bg-surface p-3">
          <PanelTitle
            right={
              worth ? (
                <span
                  className={`figures text-[11px] ${
                    Number(worth.change_vs_previous_month) >= 0 ? 'text-pos' : 'text-neg'
                  }`}
                >
                  {Number(worth.change_vs_previous_month) >= 0 ? '▲' : '▼'}{' '}
                  {formatCompact(Math.abs(Number(worth.change_vs_previous_month)))} este mes
                </span>
              ) : null
            }
          >
            Patrimonio · 12 meses
          </PanelTitle>
          <div style={{ height: 185 }}>
            {worth ? (
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart
                  data={worth.series.map((p) => ({ ...p, net_worth: Number(p.net_worth) }))}
                  margin={{ top: 4, right: 4, bottom: 0, left: 0 }}
                >
                  <defs>
                    <linearGradient id="worthfill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={MKT.up} stopOpacity={0.25} />
                      <stop offset="100%" stopColor={MKT.up} stopOpacity={0.02} />
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
                    stroke={MKT.up}
                    strokeWidth={2}
                    fill="url(#worthfill)"
                    isAnimationActive={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full animate-pulse rounded bg-surface-2" />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
