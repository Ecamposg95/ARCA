import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '@/api/client'
import { Money } from '@/components/ui/Money'
import { PageHeader } from '@/components/ui/PageHeader'
import { Card, Table } from '@/components/ui/Table'
import { formatCompact, formatDate, formatMonth, formatMoney, monthStart, today } from '@/lib/format'
import type {
  AgingReport,
  BalanceSheet,
  CashFlow,
  NetWorth,
  ProfitLoss,
  ReportLine,
  VatReport,
} from '@/types/api'

type Tab = 'pl' | 'balance' | 'flow' | 'iva' | 'cartera' | 'patrimonio'

function rangeForPeriod(period: string): { start: string; end: string } {
  const now = new Date()
  if (period === 'prev') {
    const start = new Date(now.getFullYear(), now.getMonth() - 1, 1)
    const end = new Date(now.getFullYear(), now.getMonth(), 0)
    const iso = (d: Date) =>
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    return { start: iso(start), end: iso(end) }
  }
  if (period === 'year') {
    return { start: `${now.getFullYear()}-01-01`, end: today() }
  }
  return { start: monthStart(), end: today() }
}

/** Variación contra el periodo anterior de la misma duración. Sin base previa
 *  no se inventa un porcentaje: la línea se marca como nueva. */
function LineDelta({
  current,
  previous,
  goodWhenUp,
}: {
  current: number
  previous: number | undefined
  goodWhenUp: boolean
}) {
  // Un código ausente en el periodo anterior significa cero, no "sin dato".
  const base = previous ?? 0
  if (base === 0) {
    return current !== 0 ? (
      <span className="text-[10px] font-medium uppercase tracking-wider text-muted">nuevo</span>
    ) : null
  }
  const change = ((current - base) / Math.abs(base)) * 100
  if (!Number.isFinite(change) || Math.abs(change) < 0.5) return null
  const up = change >= 0
  const good = goodWhenUp ? up : !up
  return (
    <span
      className={`figures text-[11px] font-medium ${good ? 'text-pos' : 'text-neg'}`}
      title={`Periodo anterior: ${formatMoney(base)}`}
    >
      {up ? '▲' : '▼'} {Math.abs(change).toFixed(0)}%
    </span>
  )
}

function ReportSection({
  title,
  lines,
  total,
  totalLabel,
  previous,
  previousTotal,
  goodWhenUp = true,
}: {
  title: string
  lines: ReportLine[]
  total: number
  totalLabel: string
  /** Importes del periodo anterior por código de cuenta, para el delta por línea. */
  previous?: Map<string, number>
  previousTotal?: number
  goodWhenUp?: boolean
}) {
  return (
    <div>
      <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">{title}</h3>
      <div className="divide-y divide-border">
        {lines.length === 0 ? (
          <p className="py-2 text-sm text-muted">Sin movimientos en el periodo.</p>
        ) : (
          lines.map((line) => (
            <div key={line.code} className="flex items-center justify-between gap-3 py-1.5 text-sm">
              <span>
                <span className="figures mr-2 text-xs text-muted">{line.code}</span>
                {line.name}
              </span>
              <span className="flex items-baseline gap-2.5">
                {previous ? (
                  <LineDelta
                    current={line.amount}
                    previous={previous.get(line.code)}
                    goodWhenUp={goodWhenUp}
                  />
                ) : null}
                <span className="figures">{formatMoney(line.amount)}</span>
              </span>
            </div>
          ))
        )}
      </div>
      <div className="mt-2 flex items-center justify-between border-t-2 border-ink/70 pt-2 text-sm font-semibold">
        <span>{totalLabel}</span>
        <span className="flex items-baseline gap-2.5">
          {previous && previousTotal !== undefined ? (
            <LineDelta current={total} previous={previousTotal} goodWhenUp={goodWhenUp} />
          ) : null}
          <Money value={total} />
        </span>
      </div>
    </div>
  )
}

/** El patrimonio sin comparación es un número suelto: importa hacia dónde va. */
function DeltaSinceLastMonth({ value }: { value: number | string }) {
  const amount = Number(value)
  if (!amount) return <span className="text-sm text-muted">Sin cambio desde el mes pasado</span>
  const up = amount > 0
  return (
    <span className={`figures text-sm font-medium ${up ? 'text-pos' : 'text-neg'}`}>
      {up ? '▲' : '▼'} {formatMoney(Math.abs(amount))} desde el mes pasado
    </span>
  )
}

/** Delta del DSO: en cobranza, bajar días es bueno; en pagos el dato se
 *  muestra neutro — pagar más lento no es una virtud que celebrar. */
function DsoDelta({
  current,
  previous,
  kind,
}: {
  current: number
  previous: number | null
  kind: 'receivable' | 'payable'
}) {
  // null = hace un mes no había cartera; 0 = existía y no llevaba atraso.
  if (previous === null) {
    return <span className="text-xs text-muted">sin cartera hace un mes</span>
  }
  const change = current - previous
  if (change === 0) {
    return <span className="text-xs text-muted">igual que hace un mes</span>
  }
  const down = change < 0
  const tone =
    kind === 'receivable' ? (down ? 'text-pos' : 'text-neg') : 'text-muted'
  return (
    <span className={`figures text-sm font-semibold ${tone}`}>
      {down ? '▼' : '▲'} {Math.abs(change)} {Math.abs(change) === 1 ? 'día' : 'días'} vs hace un mes
    </span>
  )
}

/** Qué reporte sabe exportarse y con qué nombre lo pide el backend. */
const CSV_REPORTS: Partial<Record<Tab, string>> = {
  pl: 'profit-loss',
  balance: 'balance-sheet',
  cartera: 'aging',
}

const TAB_KEYS: Tab[] = ['pl', 'balance', 'flow', 'iva', 'cartera', 'patrimonio']

export function ReportsPage() {
  // La pestaña vive en la URL: compartible con el contador y sobrevive a recargar.
  const [searchParams, setSearchParams] = useSearchParams()
  const requested = searchParams.get('vista') as Tab | null
  const tab: Tab = requested && TAB_KEYS.includes(requested) ? requested : 'pl'
  const setTab = (next: Tab) => setSearchParams(next === 'pl' ? {} : { vista: next })
  const [period, setPeriod] = useState('current')
  const [customRange, setCustomRange] = useState({ start: monthStart(), end: today() })
  const { start, end } =
    period === 'custom' && customRange.start && customRange.end
      ? customRange
      : rangeForPeriod(period)

  // El periodo anterior de la misma duración, pegado al inicio del actual:
  // comparar contra un tramo de otro tamaño diría mentiras con porcentajes.
  const previousRange = (() => {
    const startDate = new Date(`${start}T00:00:00`)
    const endDate = new Date(`${end}T00:00:00`)
    const days = Math.max(Math.round((endDate.getTime() - startDate.getTime()) / 86400000), 0)
    const prevEnd = new Date(startDate.getTime() - 86400000)
    const prevStart = new Date(prevEnd.getTime() - days * 86400000)
    const iso = (d: Date) =>
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    return { start: iso(prevStart), end: iso(prevEnd) }
  })()

  const profitLossQuery = useQuery({
    queryKey: ['reports', 'pl', start, end],
    queryFn: async () => (await api.get<ProfitLoss>(`/reports/profit-loss?start=${start}&end=${end}`)).data,
    enabled: tab === 'pl',
  })
  const previousProfitLossQuery = useQuery({
    queryKey: ['reports', 'pl-prev', previousRange.start, previousRange.end],
    queryFn: async () =>
      (
        await api.get<ProfitLoss>(
          `/reports/profit-loss?start=${previousRange.start}&end=${previousRange.end}`,
        )
      ).data,
    enabled: tab === 'pl',
  })
  const balanceQuery = useQuery({
    queryKey: ['reports', 'balance', end],
    queryFn: async () => (await api.get<BalanceSheet>(`/reports/balance-sheet?as_of=${end}`)).data,
    enabled: tab === 'balance',
  })
  const vatQuery = useQuery({
    queryKey: ['reports', 'iva', start, end],
    queryFn: async () => (await api.get<VatReport>(`/reports/iva?start=${start}&end=${end}`)).data,
    enabled: tab === 'iva',
  })
  const flowQuery = useQuery({
    queryKey: ['reports', 'flow', start, end],
    queryFn: async () => (await api.get<CashFlow>(`/reports/cash-flow?start=${start}&end=${end}`)).data,
    enabled: tab === 'flow',
  })
  const [agingKind, setAgingKind] = useState<'receivable' | 'payable'>('receivable')
  const agingQuery = useQuery({
    queryKey: ['reports', 'aging', agingKind],
    queryFn: async () => (await api.get<AgingReport>(`/reports/aging?kind=${agingKind}`)).data,
    enabled: tab === 'cartera',
  })
  const netWorthQuery = useQuery({
    queryKey: ['reports', 'net-worth'],
    queryFn: async () => (await api.get<NetWorth>('/reports/net-worth?months=12')).data,
    enabled: tab === 'patrimonio',
  })

  const previousByCode = previousProfitLossQuery.data
    ? {
        revenue: new Map(
          previousProfitLossQuery.data.revenue.map((line) => [line.code, line.amount]),
        ),
        expenses: new Map(
          previousProfitLossQuery.data.expenses.map((line) => [line.code, line.amount]),
        ),
      }
    : undefined

  const tabs: { key: Tab; label: string }[] = [
    { key: 'pl', label: 'Estado de resultados' },
    { key: 'balance', label: 'Balance general' },
    { key: 'flow', label: 'Flujo de efectivo' },
    { key: 'iva', label: 'IVA' },
    { key: 'cartera', label: 'Cartera' },
    { key: 'patrimonio', label: 'Patrimonio' },
  ]

  return (
    <div>
      <PageHeader
        title="Reportes"
        description="Lo que dicen tus números, directo del libro contable."
        actions={
          CSV_REPORTS[tab] ? (
            <div className="flex gap-2">
              <a
                href={`/api/reports/${CSV_REPORTS[tab]}/csv?start=${start}&end=${end}`}
                className="rounded-lg border border-border bg-surface px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:text-ink"
                download
              >
                Descargar Excel
              </a>
              <button
                type="button"
                onClick={() => window.print()}
                className="rounded-lg border border-border bg-surface px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:text-ink"
              >
                Imprimir o PDF
              </button>
            </div>
          ) : null
        }
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          {/* max-w-full + scroll: con seis pestañas, en un teléfono "Cartera" y
              "Patrimonio" quedaban fuera del viewport sin forma de llegar. */}
          <div className="flex max-w-full gap-1 overflow-x-auto rounded-lg border border-border bg-surface p-1">
            {tabs.map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => setTab(item.key)}
                className={`whitespace-nowrap rounded-md px-3 py-1.5 text-sm transition-colors ${
                  tab === item.key ? 'bg-accent text-white font-medium' : 'text-muted hover:text-ink'
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
          {tab !== 'balance' ? (
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={period}
                onChange={(event) => setPeriod(event.target.value)}
                className="rounded border border-border bg-surface px-3 py-1.5 text-sm"
                aria-label="Periodo"
              >
                <option value="current">Este mes</option>
                <option value="prev">Mes anterior</option>
                <option value="year">Este año</option>
                <option value="custom">Rango personalizado</option>
              </select>
              {period === 'custom' ? (
                <div className="flex items-center gap-1.5 text-xs text-muted">
                  <span>Del</span>
                  <input
                    type="date"
                    value={customRange.start}
                    max={customRange.end}
                    onChange={(event) =>
                      setCustomRange({ ...customRange, start: event.target.value })
                    }
                    className="rounded border border-border bg-surface px-2 py-1.5 text-sm text-ink"
                  />
                  <span>al</span>
                  <input
                    type="date"
                    value={customRange.end}
                    min={customRange.start}
                    onChange={(event) =>
                      setCustomRange({ ...customRange, end: event.target.value })
                    }
                    className="rounded border border-border bg-surface px-2 py-1.5 text-sm text-ink"
                  />
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      </PageHeader>

      {tab === 'pl' && profitLossQuery.data ? (
        <Card className="max-w-2xl space-y-6">
          <p className="text-xs text-muted">
            Comparado contra el periodo anterior de la misma duración (
            {formatDate(previousRange.start)} – {formatDate(previousRange.end)}).
          </p>
          <ReportSection
            title="Ingresos"
            lines={profitLossQuery.data.revenue}
            total={profitLossQuery.data.total_revenue}
            totalLabel="Total de ingresos"
            previous={previousByCode?.revenue}
            previousTotal={previousProfitLossQuery.data?.total_revenue}
          />
          <ReportSection
            title="Gastos"
            lines={profitLossQuery.data.expenses}
            total={profitLossQuery.data.total_expenses}
            totalLabel="Total de gastos"
            previous={previousByCode?.expenses}
            previousTotal={previousProfitLossQuery.data?.total_expenses}
            goodWhenUp={false}
          />
          <div className="flex items-center justify-between rounded-lg bg-accent-soft px-4 py-3">
            <span className="font-display font-semibold">
              {profitLossQuery.data.net_profit >= 0 ? 'Ganancia del periodo' : 'Pérdida del periodo'}
            </span>
            <Money
              value={profitLossQuery.data.net_profit}
              size="lg"
              tone={profitLossQuery.data.net_profit >= 0 ? 'pos' : 'neg'}
            />
          </div>
        </Card>
      ) : null}

      {tab === 'balance' && balanceQuery.data ? (
        <Card className="max-w-2xl space-y-6">
          <ReportSection
            title="Lo que tienes (activos)"
            lines={balanceQuery.data.assets}
            total={balanceQuery.data.total_assets}
            totalLabel="Total activos"
          />
          <ReportSection
            title="Lo que debes (pasivos)"
            lines={balanceQuery.data.liabilities}
            total={balanceQuery.data.total_liabilities}
            totalLabel="Total pasivos"
          />
          <ReportSection
            title="Tu capital"
            lines={balanceQuery.data.equity}
            total={balanceQuery.data.total_equity}
            totalLabel="Total capital"
          />
          <p className="text-xs text-muted">
            {balanceQuery.data.balanced
              ? 'El balance cuadra: activos = pasivos + capital.'
              : 'Atención: el balance no cuadra. Contacta a soporte.'}
          </p>
        </Card>
      ) : null}

      {tab === 'iva' && vatQuery.data ? (
        <Card className="max-w-2xl">
          <div className="divide-y divide-border text-sm">
            <div className="flex items-center justify-between py-3">
              <span>IVA que cobraste a tus clientes</span>
              <Money value={vatQuery.data.vat_charged} />
            </div>
            <div className="flex items-center justify-between py-3">
              <span>− IVA que pagaste a proveedores</span>
              <Money value={vatQuery.data.vat_creditable} />
            </div>
            <div className="flex items-center justify-between py-3 font-semibold">
              <span>
                {vatQuery.data.in_favor > 0 ? 'IVA a favor' : 'IVA a pagar'}
              </span>
              <Money
                value={vatQuery.data.in_favor > 0 ? vatQuery.data.in_favor : vatQuery.data.to_pay}
                size="lg"
                tone={vatQuery.data.in_favor > 0 ? 'pos' : 'ink'}
              />
            </div>
          </div>
          <div className="mt-4 rounded-lg bg-surface-2 p-3 text-xs text-muted">
            <p className="font-medium text-ink">Todavía no se declara</p>
            <p className="mt-1">
              En México el IVA se causa al cobrar y al pagar, no al facturar. Estos montos
              esperan a que el dinero se mueva:
            </p>
            <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1">
              <span>
                Por cobrar:{' '}
                <span className="figures text-ink">
                  {formatMoney(vatQuery.data.vat_pending_collection)}
                </span>
              </span>
              <span>
                Por pagar:{' '}
                <span className="figures text-ink">
                  {formatMoney(vatQuery.data.vat_pending_payment)}
                </span>
              </span>
            </div>
          </div>
        </Card>
      ) : null}

      {tab === 'flow' && flowQuery.data ? (
        <Card className="max-w-2xl">
          <div className="divide-y divide-border text-sm">
            <div className="flex items-center justify-between py-3">
              <span>Dinero al inicio del periodo</span>
              <Money value={flowQuery.data.opening_cash} />
            </div>
            <div className="flex items-center justify-between py-3">
              <span>+ Entradas</span>
              <Money value={flowQuery.data.inflows} tone="pos" />
            </div>
            <div className="flex items-center justify-between py-3">
              <span>− Salidas</span>
              <Money value={flowQuery.data.outflows} tone="neg" />
            </div>
            <div className="flex items-center justify-between py-3 font-semibold">
              <span>Dinero al cierre</span>
              <Money value={flowQuery.data.closing_cash} size="lg" />
            </div>
          </div>
        </Card>
      ) : null}

      {tab === 'cartera' && agingQuery.data ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            {[
              { key: 'receivable' as const, label: 'Quién me debe' },
              { key: 'payable' as const, label: 'A quién le debo' },
            ].map((option) => (
              <button
                key={option.key}
                type="button"
                onClick={() => setAgingKind(option.key)}
                className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                  agingKind === option.key
                    ? 'bg-accent text-on-accent'
                    : 'border border-border bg-surface text-muted hover:text-ink'
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>

          <div className="grid gap-4 lg:grid-cols-5">
            {/* La métrica estrella: cuánto tarda tu dinero. Con comparación,
                porque un número solo no dice si vas mejor o peor. */}
            <Card className="lg:col-span-3">
              <p className="text-xs uppercase tracking-wider text-muted">
                {agingKind === 'receivable' ? 'Te pagan en' : 'Pagas en'}
              </p>
              <div className="mt-1 flex flex-wrap items-baseline gap-3">
                <p className="figures text-4xl font-bold tracking-tight">
                  {agingQuery.data.average_days}
                  <span className="ml-1.5 text-base font-normal text-muted">días</span>
                </p>
                <DsoDelta
                  current={agingQuery.data.average_days}
                  previous={agingQuery.data.previous_average_days}
                  kind={agingKind}
                />
              </div>
              <p className="mt-1.5 text-xs text-muted">
                Antigüedad promedio ponderada por saldo, comparada con hace 30 días.
              </p>
            </Card>
            <Card>
              <p className="text-xs uppercase tracking-wider text-muted">Saldo total</p>
              <Money value={agingQuery.data.total} size="lg" />
            </Card>
            <Card>
              <p className="text-xs uppercase tracking-wider text-muted">Vencido</p>
              <Money
                value={agingQuery.data.overdue}
                size="lg"
                tone={Number(agingQuery.data.overdue) > 0 ? 'neg' : 'ink'}
              />
            </Card>
          </div>

          {agingQuery.data.contacts.length === 0 ? (
            <Card>
              <p className="text-sm text-muted">
                {agingKind === 'receivable'
                  ? 'Nadie te debe nada por ahora.'
                  : 'No tienes cuentas por pagar abiertas.'}
              </p>
            </Card>
          ) : (
            <Table
              headers={[
                agingKind === 'receivable' ? 'Cliente' : 'Proveedor',
                ...agingQuery.data.buckets.map((bucket) => (
                  <span key={bucket} className="block text-right">
                    {bucket === 'Por vencer' ? bucket : `${bucket} días`}
                  </span>
                )),
                <span key="t" className="block text-right">
                  Total
                </span>,
              ]}
              secondary={[2, 3, 4]}
            >
              {agingQuery.data.contacts.map((contact) => (
                <tr key={contact.contact_id} className="hover:bg-surface-2/50">
                  <td className="px-4 py-2.5 font-medium">{contact.name}</td>
                  {agingQuery.data!.buckets.map((bucket) => {
                    const amount = Number(contact[bucket] ?? 0)
                    return (
                      <td key={bucket} className="figures px-4 py-2.5 text-right">
                        {amount > 0 ? (
                          <span className={bucket === '+90' ? 'text-neg' : undefined}>
                            {formatMoney(amount)}
                          </span>
                        ) : (
                          <span className="text-muted">—</span>
                        )}
                      </td>
                    )
                  })}
                  <td className="px-4 py-2.5 text-right">
                    <Money value={contact.total} />
                  </td>
                </tr>
              ))}
              <tr className="border-t-2 border-ink/70 font-semibold">
                <td className="px-4 py-2.5">Total</td>
                {agingQuery.data.buckets.map((bucket) => (
                  <td key={bucket} className="figures px-4 py-2.5 text-right">
                    {formatMoney(agingQuery.data!.totals[bucket] ?? 0)}
                  </td>
                ))}
                <td className="px-4 py-2.5 text-right">
                  <Money value={agingQuery.data.total} />
                </td>
              </tr>
            </Table>
          )}
        </div>
      ) : null}

      {tab === 'patrimonio' && netWorthQuery.data ? (
        <div className="space-y-4">
          <Card>
            <p className="text-xs uppercase tracking-wider text-muted">Patrimonio neto</p>
            <div className="mt-1 flex flex-wrap items-baseline gap-4">
              <Money value={netWorthQuery.data.net_worth} size="xl" />
              <DeltaSinceLastMonth value={netWorthQuery.data.change_vs_previous_month} />
            </div>
            <p className="mt-2 text-sm text-muted">
              Lo que tienes menos lo que debes. Sale del mismo libro que el Balance general.
            </p>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <ReportSection
                title="Lo que tienes"
                lines={netWorthQuery.data.assets}
                total={netWorthQuery.data.total_assets}
                totalLabel="Total de activos"
              />
            </Card>
            <Card>
              <ReportSection
                title="Lo que debes"
                lines={netWorthQuery.data.liabilities}
                total={netWorthQuery.data.total_liabilities}
                totalLabel="Total de deudas"
              />
            </Card>
          </div>

          <Card>
            <h3 className="mb-3 text-xs font-medium uppercase tracking-wide text-muted">
              Cómo ha evolucionado
            </h3>
            <div style={{ height: 260 }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={netWorthQuery.data.series}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
                  <XAxis
                    dataKey="month"
                    tickFormatter={(value: string) => formatMonth(value)}
                    tick={{ fontSize: 11 }}
                    stroke="var(--color-muted)"
                  />
                  <YAxis
                    tickFormatter={(value: number) => formatCompact(value)}
                    tick={{ fontSize: 11 }}
                    stroke="var(--color-muted)"
                    width={64}
                  />
                  <Tooltip
                    formatter={(value: number) => formatMoney(value)}
                    labelFormatter={(value: string) => formatMonth(value)}
                    contentStyle={{
                      background: 'var(--color-surface)',
                      border: '1px solid var(--color-border)',
                      borderRadius: 8,
                      fontSize: 12,
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="net_worth"
                    name="Patrimonio"
                    stroke="#2c9aa6"
                    fill="#2c9aa6"
                    fillOpacity={0.14}
                    strokeWidth={2}
                    isAnimationActive={false}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </div>
      ) : null}
    </div>
  )
}
