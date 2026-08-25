import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { Money } from '@/components/ui/Money'
import { Card } from '@/components/ui/Table'
import { formatCompact, formatMoney, formatMonth, formatMonthYear } from '@/lib/format'
import type { DashboardSummary } from '@/types/api'

/** Sistema de color del tablero: teal = dinero que entra, ámbar = dinero que sale.
 *  El rojo queda reservado para problemas (vencido, pérdida), nunca para un gasto normal. */
const IN = '#2c9aa6'
const OUT = '#c29938'
const LOSS = '#e05252'
const GRID = '#8fa0a8'

/** Variación contra el mismo tramo del mes anterior. Sin base previa no se
 *  inventa un porcentaje: se dice que no hay con qué comparar. */
function DeltaChip({ current, previous, goodWhenUp = true }: { current: number; previous: number; goodWhenUp?: boolean }) {
  if (!previous) return null
  const change = ((current - previous) / Math.abs(previous)) * 100
  if (!Number.isFinite(change)) return null
  const up = change >= 0
  const good = goodWhenUp ? up : !up
  return (
    <span
      className={`figures block text-[11px] font-medium ${good ? 'text-pos' : 'text-neg'}`}
      title={`Mismo tramo del mes anterior: ${formatMoney(previous)}`}
    >
      {up ? '▲' : '▼'} {Math.abs(change).toFixed(0)}% vs. mes anterior
    </span>
  )
}

function MetricLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted">{children}</div>
  )
}

function ChartLegend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <div className="flex items-center gap-4">
      {items.map((item) => (
        <span key={item.label} className="flex items-center gap-1.5 text-xs text-muted">
          <span className="h-2 w-2 rounded-full" style={{ background: item.color }} />
          {item.label}
        </span>
      ))}
    </div>
  )
}

function ChartCard({
  title,
  legend,
  children,
}: {
  title: string
  legend?: { label: string; color: string }[]
  children: React.ReactNode
}) {
  return (
    <Card>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">{title}</h2>
        {legend ? <ChartLegend items={legend} /> : null}
      </div>
      {children}
    </Card>
  )
}

export function DashboardPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['dashboard'],
    queryFn: async () => (await api.get<DashboardSummary>('/dashboard/summary')).data,
  })

  if (isLoading || !data) {
    return (
      <div className="space-y-4">
        <div className="h-24 w-72 animate-pulse rounded-xl bg-surface-2" />
        <div className="h-28 animate-pulse rounded-xl bg-surface-2" />
        <div className="h-28 animate-pulse rounded-xl bg-surface-2" />
      </div>
    )
  }

  const hasMovement =
    data.cash_flow.some((row) => row.inflows > 0 || row.outflows > 0) || data.cash !== 0

  const flowData = data.cash_flow.map((row) => ({ ...row, month: formatMonth(row.month) }))
  const resultData = data.revenue_vs_expenses.map((row) => ({
    month: formatMonth(row.month),
    profit: row.revenue - row.expenses,
  }))
  const topCategory = data.expense_categories[0]?.amount ?? 0

  const axisProps = { tickLine: false, axisLine: false, fontSize: 11, stroke: GRID } as const

  return (
    <div>
      {/* Lo primero que importa: cuánto dinero hay. */}
      <header className="mb-7">
        <MetricLabel>Disponible</MetricLabel>
        <div className="mt-1.5">
          <Money value={data.cash} size="xl" />
        </div>
      </header>

      {/* Dos paneles en vez de cinco tarjetas: menos ruido, misma información. */}
      <div className="grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <div className="mb-4 flex items-baseline justify-between">
            <MetricLabel>Este mes</MetricLabel>
            <span className="text-xs text-muted">{formatMonthYear(new Date())}</span>
          </div>
          <div className="grid divide-y divide-border sm:grid-cols-3 sm:divide-x sm:divide-y-0">
            <div className="pb-3 sm:pb-0 sm:pr-4">
              <div className="text-xs text-muted">Ingresos</div>
              <div className="mt-1">
                <Money value={data.monthly_revenue} size="lg" />
                <DeltaChip current={data.monthly_revenue} previous={data.previous_revenue} />
              </div>
            </div>
            <div className="py-3 sm:px-4 sm:py-0">
              <div className="text-xs text-muted">Gastos</div>
              <div className="mt-1">
                <Money value={data.monthly_expenses} size="lg" />
                <DeltaChip current={data.monthly_expenses} previous={data.previous_expenses} goodWhenUp={false} />
              </div>
            </div>
            <div className="pt-3 sm:pl-4 sm:pt-0">
              <div className="text-xs text-muted">Resultado</div>
              <div className="mt-1">
                <Money
                  value={data.monthly_profit}
                  size="lg"
                  tone={data.monthly_profit >= 0 ? 'pos' : 'neg'}
                />
                <DeltaChip current={data.monthly_profit} previous={data.previous_profit} />
              </div>
            </div>
          </div>
        </Card>

        <Card className="lg:col-span-2">
          <MetricLabel>Cartera</MetricLabel>
          <div className="mt-4 grid divide-y divide-border sm:grid-cols-2 sm:divide-x sm:divide-y-0">
            <Link to="/por-cobrar" className="group pb-3 sm:pb-0 sm:pr-4">
              <div className="text-xs text-muted group-hover:text-accent">Por cobrar</div>
              <div className="mt-1">
                <Money value={data.receivables} size="lg" />
              </div>
              {data.overdue_receivables > 0 ? (
                <div className="mt-1 text-xs font-medium text-neg">
                  Vencido {formatMoney(data.overdue_receivables)}
                </div>
              ) : null}
            </Link>
            <Link to="/por-pagar" className="group pt-3 sm:pl-4 sm:pt-0">
              <div className="text-xs text-muted group-hover:text-accent">Por pagar</div>
              <div className="mt-1">
                <Money value={data.payables} size="lg" />
              </div>
            </Link>
          </div>
        </Card>
      </div>

      {!hasMovement ? (
        <div className="mt-4 rounded-xl border border-dashed border-border bg-surface px-6 py-12 text-center">
          <h3 className="font-display text-lg font-semibold">Registra tu primera operación</h3>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted">
            Captura una venta o un gasto y ARCA irá armando tus números, tus reportes y tu
            contabilidad por ti.
          </p>
          <div className="mt-5 flex justify-center gap-3">
            <Link to="/ingresos?nuevo=1">
              <Button>Registrar ingreso</Button>
            </Link>
            <Link to="/gastos?nuevo=1">
              <Button variant="secondary">Registrar gasto</Button>
            </Link>
          </div>
        </div>
      ) : (
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <ChartCard
            title="Entradas y salidas de dinero"
            legend={[
              { label: 'Entradas', color: IN },
              { label: 'Salidas', color: OUT },
            ]}
          >
            <ResponsiveContainer width="100%" height={210}>
              <BarChart data={flowData} barGap={3} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="2 4" vertical={false} stroke={GRID} strokeOpacity={0.25} />
                <XAxis dataKey="month" {...axisProps} />
                <YAxis {...axisProps} tickFormatter={formatCompact} width={52} />
                <Tooltip
                  cursor={{ fill: GRID, fillOpacity: 0.08 }}
                  formatter={(value) => formatMoney(Number(value))}
                />
                <Bar dataKey="inflows" name="Entradas" fill={IN} radius={[3, 3, 0, 0]} isAnimationActive={false} />
                <Bar dataKey="outflows" name="Salidas" fill={OUT} radius={[3, 3, 0, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>

          {/* Distinta pregunta que el flujo de efectivo: ¿gané o perdí cada mes? */}
          <ChartCard title="Resultado por mes">
            <ResponsiveContainer width="100%" height={210}>
              <BarChart data={resultData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="2 4" vertical={false} stroke={GRID} strokeOpacity={0.25} />
                <XAxis dataKey="month" {...axisProps} />
                <YAxis {...axisProps} tickFormatter={formatCompact} width={52} />
                <Tooltip
                  cursor={{ fill: GRID, fillOpacity: 0.08 }}
                  formatter={(value) => formatMoney(Number(value))}
                />
                <Bar dataKey="profit" name="Resultado" radius={[3, 3, 0, 0]} isAnimationActive={false}>
                  {resultData.map((row) => (
                    <Cell key={row.month} fill={row.profit >= 0 ? IN : LOSS} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>

          {data.expense_categories.length > 0 ? (
            <Card className="lg:col-span-2">
              <div className="mb-4 flex items-baseline justify-between">
                <h2 className="text-sm font-semibold">En qué se va el gasto</h2>
                <span className="text-xs text-muted">{formatMonthYear(new Date())}</span>
              </div>
              {/* Barras horizontales en vez de dona: ocho categorías se comparan de un vistazo. */}
              <ul className="space-y-2.5">
                {data.expense_categories.map((row) => (
                  <li key={row.category} className="grid grid-cols-[9rem_1fr_auto] items-center gap-3 text-sm">
                    <span className="truncate text-muted">{row.category}</span>
                    <span className="h-2 rounded-full bg-surface-2">
                      <span
                        className="block h-2 rounded-full"
                        style={{
                          width: topCategory > 0 ? `${Math.max((row.amount / topCategory) * 100, 2)}%` : '2%',
                          background: OUT,
                        }}
                      />
                    </span>
                    <span className="figures tabular-nums text-right font-medium">
                      {formatMoney(row.amount)}
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          ) : null}
        </div>
      )}
    </div>
  )
}
