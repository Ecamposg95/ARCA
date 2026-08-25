import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { Money } from '@/components/ui/Money'
import { Card } from '@/components/ui/Table'
import { formatMoney, formatMonth } from '@/lib/format'
import { useAuthStore } from '@/stores/authStore'
import type { DashboardSummary } from '@/types/api'

const CHART_COLORS = ['#0E6E5C', '#3E8E7E', '#6FAE9F', '#A3CEC3', '#C2402A', '#B07C10', '#5E6B64']

function StatCard({
  label,
  value,
  tone,
  to,
  footnote,
}: {
  label: string
  value: number
  tone?: 'pos' | 'neg'
  to?: string
  footnote?: string
}) {
  const body = (
    <Card className="h-full transition-shadow hover:shadow-float">
      <div className="text-xs font-medium uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-2">
        <Money value={value} size="lg" tone={tone ?? 'ink'} />
      </div>
      {footnote ? <div className="mt-1 text-xs text-neg">{footnote}</div> : null}
    </Card>
  )
  return to ? <Link to={to}>{body}</Link> : body
}

export function DashboardPage() {
  const organization = useAuthStore((state) => state.organization)
  const { data, isLoading } = useQuery({
    queryKey: ['dashboard'],
    queryFn: async () => (await api.get<DashboardSummary>('/dashboard/summary')).data,
  })

  if (isLoading || !data) {
    return (
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, index) => (
          <div key={index} className="h-28 animate-pulse rounded-xl bg-surface-2" />
        ))}
      </div>
    )
  }

  const hasMovement =
    data.cash_flow.some((row) => row.inflows > 0 || row.outflows > 0) || data.cash !== 0

  const flowData = data.cash_flow.map((row) => ({ ...row, month: formatMonth(row.month) }))
  const rveData = data.revenue_vs_expenses.map((row) => ({ ...row, month: formatMonth(row.month) }))

  return (
    <div>
      <div className="mb-6">
        <div className="text-sm text-muted">{organization?.name}</div>
        <div className="mt-1 flex items-end gap-3">
          <Money value={data.cash} size="xl" />
          <span className="pb-1.5 text-sm text-muted">disponible en tus cuentas</span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
        <StatCard label="Ingresos este mes" value={data.monthly_revenue} tone="pos" to="/ingresos" />
        <StatCard label="Gastos este mes" value={data.monthly_expenses} tone="neg" to="/gastos" />
        <StatCard
          label="Resultado del mes"
          value={data.monthly_profit}
          tone={data.monthly_profit >= 0 ? 'pos' : 'neg'}
          to="/reportes"
        />
        <StatCard
          label="Por cobrar"
          value={data.receivables}
          to="/por-cobrar"
          footnote={
            data.overdue_receivables > 0 ? `Vencido: ${formatMoney(data.overdue_receivables)}` : undefined
          }
        />
        <StatCard label="Por pagar" value={data.payables} to="/por-pagar" />
      </div>

      {!hasMovement ? (
        <div className="mt-6 rounded-xl border border-dashed border-border bg-surface px-6 py-12 text-center">
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
        <div className="mt-6 grid gap-4 lg:grid-cols-2">
          <Card>
            <h3 className="mb-4 text-sm font-medium text-muted">Entradas y salidas de dinero</h3>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={flowData} barGap={2}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(150 8% 90%)" />
                <XAxis dataKey="month" tickLine={false} axisLine={false} fontSize={12} />
                <YAxis tickLine={false} axisLine={false} fontSize={12} tickFormatter={(v) => formatMoney(v).replace('.00', '')} width={90} />
                <Tooltip formatter={(value) => formatMoney(Number(value))} />
                <Bar dataKey="inflows" name="Entradas" fill="#0E6E5C" radius={[3, 3, 0, 0]} />
                <Bar dataKey="outflows" name="Salidas" fill="#C2402A" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>
          <Card>
            <h3 className="mb-4 text-sm font-medium text-muted">Ingresos vs gastos</h3>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={rveData} barGap={2}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(150 8% 90%)" />
                <XAxis dataKey="month" tickLine={false} axisLine={false} fontSize={12} />
                <YAxis tickLine={false} axisLine={false} fontSize={12} tickFormatter={(v) => formatMoney(v).replace('.00', '')} width={90} />
                <Tooltip formatter={(value) => formatMoney(Number(value))} />
                <Bar dataKey="revenue" name="Ingresos" fill="#0E6E5C" radius={[3, 3, 0, 0]} />
                <Bar dataKey="expenses" name="Gastos" fill="#B07C10" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>
          {data.expense_categories.length > 0 ? (
            <Card className="lg:col-span-2">
              <h3 className="mb-4 text-sm font-medium text-muted">En qué se va el gasto (este mes)</h3>
              <div className="flex flex-wrap items-center gap-8">
                <ResponsiveContainer width={220} height={220}>
                  <PieChart>
                    <Pie
                      data={data.expense_categories}
                      dataKey="amount"
                      nameKey="category"
                      innerRadius={60}
                      outerRadius={95}
                      paddingAngle={2}
                    >
                      {data.expense_categories.map((_, index) => (
                        <Cell key={index} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(value) => formatMoney(Number(value))} />
                  </PieChart>
                </ResponsiveContainer>
                <ul className="space-y-2">
                  {data.expense_categories.map((row, index) => (
                    <li key={row.category} className="flex items-center gap-2.5 text-sm">
                      <span
                        className="h-2.5 w-2.5 rounded-full"
                        style={{ background: CHART_COLORS[index % CHART_COLORS.length] }}
                      />
                      <span className="text-muted">{row.category}</span>
                      <span className="figures ml-auto pl-6 font-medium">{formatMoney(row.amount)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </Card>
          ) : null}
        </div>
      )}
    </div>
  )
}
