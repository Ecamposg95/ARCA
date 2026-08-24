import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { Money } from '@/components/ui/Money'
import { PageHeader } from '@/components/ui/PageHeader'
import { Card } from '@/components/ui/Table'
import { formatMoney, monthStart, today } from '@/lib/format'
import type { BalanceSheet, CashFlow, ProfitLoss, ReportLine } from '@/types/api'

type Tab = 'pl' | 'balance' | 'flow'

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

function ReportSection({ title, lines, total, totalLabel }: { title: string; lines: ReportLine[]; total: number; totalLabel: string }) {
  return (
    <div>
      <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">{title}</h3>
      <div className="divide-y divide-border">
        {lines.length === 0 ? (
          <p className="py-2 text-sm text-muted">Sin movimientos en el periodo.</p>
        ) : (
          lines.map((line) => (
            <div key={line.code} className="flex items-center justify-between py-1.5 text-sm">
              <span>
                <span className="figures mr-2 text-xs text-muted">{line.code}</span>
                {line.name}
              </span>
              <span className="figures">{formatMoney(line.amount)}</span>
            </div>
          ))
        )}
      </div>
      <div className="mt-2 flex items-center justify-between border-t-2 border-ink/70 pt-2 text-sm font-semibold">
        <span>{totalLabel}</span>
        <Money value={total} />
      </div>
    </div>
  )
}

export function ReportsPage() {
  const [tab, setTab] = useState<Tab>('pl')
  const [period, setPeriod] = useState('current')
  const { start, end } = rangeForPeriod(period)

  const profitLossQuery = useQuery({
    queryKey: ['reports', 'pl', start, end],
    queryFn: async () => (await api.get<ProfitLoss>(`/reports/profit-loss?start=${start}&end=${end}`)).data,
    enabled: tab === 'pl',
  })
  const balanceQuery = useQuery({
    queryKey: ['reports', 'balance', end],
    queryFn: async () => (await api.get<BalanceSheet>(`/reports/balance-sheet?as_of=${end}`)).data,
    enabled: tab === 'balance',
  })
  const flowQuery = useQuery({
    queryKey: ['reports', 'flow', start, end],
    queryFn: async () => (await api.get<CashFlow>(`/reports/cash-flow?start=${start}&end=${end}`)).data,
    enabled: tab === 'flow',
  })

  const tabs: { key: Tab; label: string }[] = [
    { key: 'pl', label: 'Estado de resultados' },
    { key: 'balance', label: 'Balance general' },
    { key: 'flow', label: 'Flujo de efectivo' },
  ]

  return (
    <div>
      <PageHeader title="Reportes" description="Lo que dicen tus números, directo del libro contable.">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex gap-1 rounded-lg border border-border bg-surface p-1">
            {tabs.map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => setTab(item.key)}
                className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
                  tab === item.key ? 'bg-accent text-white font-medium' : 'text-muted hover:text-ink'
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
          {tab !== 'balance' ? (
            <select
              value={period}
              onChange={(event) => setPeriod(event.target.value)}
              className="rounded border border-border bg-surface px-3 py-1.5 text-sm"
              aria-label="Periodo"
            >
              <option value="current">Este mes</option>
              <option value="prev">Mes anterior</option>
              <option value="year">Este año</option>
            </select>
          ) : null}
        </div>
      </PageHeader>

      {tab === 'pl' && profitLossQuery.data ? (
        <Card className="max-w-2xl space-y-6">
          <ReportSection
            title="Ingresos"
            lines={profitLossQuery.data.revenue}
            total={profitLossQuery.data.total_revenue}
            totalLabel="Total de ingresos"
          />
          <ReportSection
            title="Gastos"
            lines={profitLossQuery.data.expenses}
            total={profitLossQuery.data.total_expenses}
            totalLabel="Total de gastos"
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
    </div>
  )
}
