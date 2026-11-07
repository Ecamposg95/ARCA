import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { formatMoney, formatWhole } from '@/lib/format'
import type { DashboardWeek, DashboardWeekItem } from '@/types/api'
import { useGrowOnce } from './useCountUp'

const WEEKDAY = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb']

function dayParts(iso: string): { weekday: string; day: string } {
  const [year, month, day] = iso.split('-').map(Number)
  const date = new Date(year, month - 1, day)
  return {
    weekday: WEEKDAY[date.getDay()],
    day: date.toLocaleDateString('es-MX', { day: 'numeric', month: 'short' }),
  }
}

function ApprovalTag({ approval }: { approval: DashboardWeekItem['approval'] }) {
  if (approval === 'PENDING') {
    return <span className="ml-1 rounded bg-warn/15 px-1 text-[10.5px] text-warn">Por autorizar</span>
  }
  if (approval === 'REQUIRED') {
    return <span className="ml-1 rounded bg-muted/15 px-1 text-[10.5px] text-muted">Requiere autorización</span>
  }
  return null
}

export function WeekPayablesPanel({ week }: { week: DashboardWeek }) {
  const grown = useGrowOnce()
  const amounts = week.days.map((day) => Number(day.amount))
  const max = Math.max(...amounts, 0)
  const count = week.items.length

  return (
    <section className="panel flex min-w-0 flex-col overflow-hidden p-4" aria-label={`Por pagar esta semana: ${formatMoney(week.total)} en ${count} pagos`}>
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-[13px] font-medium text-ink-soft">Por pagar esta semana</h2>
        {count > 0 ? (
          <span className="figures whitespace-nowrap text-xs text-muted">
            {formatWhole(week.total)} · {count} {count === 1 ? 'pago' : 'pagos'}
          </span>
        ) : null}
      </div>

      {count === 0 ? (
        <div className="mt-4 flex flex-1 flex-col items-center justify-center rounded-lg border border-dashed border-border px-4 py-8 text-center">
          <p className="text-sm text-ink">No hay pagos programados esta semana</p>
          <p className="mt-1 text-xs text-muted">Lo que registres con fecha de vencimiento aparece aquí, día por día.</p>
          <Link to="/por-pagar?nueva=1" className="mt-4">
            <Button variant="secondary">Registrar cuenta por pagar</Button>
          </Link>
        </div>
      ) : (
        <>
          <div className="mt-3 flex h-[112px] items-end gap-1.5 border-b border-border" role="img" aria-label="Pagos por día de la semana">
            {week.days.map((day, index) => {
              const amount = amounts[index]
              const pending = Number(day.pending_approval_amount)
              const height = max > 0 && amount > 0 ? Math.max((amount / max) * 62, 6) : 3
              const parts = dayParts(day.date)
              return (
                <div key={day.date} className="flex flex-1 flex-col items-center justify-end gap-1">
                  <span className="figures text-[10.5px] text-ink-soft">{amount > 0 ? formatWhole(amount) : ''}</span>
                  <span
                    className={`w-[70%] rounded-t-[3px] transition-[height] duration-500 ease-out ${
                      amount === 0 ? 'bg-border' : pending > 0 ? 'bg-warn' : 'bg-neg/85'
                    }`}
                    style={{ height: grown ? height : 3 }}
                    title={`${parts.weekday} ${parts.day}: ${formatMoney(amount)}`}
                  />
                  <span className="pb-1 text-center text-[11px] leading-tight text-ink-soft">
                    {parts.weekday}
                    <br />
                    <span className="text-[10px] text-muted">{parts.day}</span>
                  </span>
                </div>
              )
            })}
          </div>

          <ul className="mt-1 divide-y divide-border">
            {week.items.map((item) => {
              const parts = dayParts(item.due_date)
              return (
                <li key={item.payable_id}>
                  <Link
                    to={`/por-pagar?open=${item.payable_id}`}
                    className="grid grid-cols-[56px_minmax(0,1fr)_auto] items-center gap-2.5 py-1.5 text-[13px] hover:bg-surface-2/60 sm:grid-cols-[62px_minmax(0,1fr)_auto_72px]"
                  >
                    <span className={`whitespace-nowrap text-xs ${item.overdue ? 'text-neg' : 'text-muted'}`}>
                      {item.overdue ? (
                        'vencida'
                      ) : (
                        <>
                          <b className="font-medium text-ink-soft">{parts.weekday}</b> {parts.day}
                        </>
                      )}
                    </span>
                    <span className="truncate text-ink">
                      {item.description} · <span className="text-ink-soft">{item.vendor}</span>
                      <ApprovalTag approval={item.approval} />
                    </span>
                    <span className="figures whitespace-nowrap text-neg">−{formatWhole(item.amount)}</span>
                    <span className="figures hidden text-right text-xs text-muted sm:block" title="Lo que queda después de este pago">
                      {formatWhole(item.running_balance)}
                    </span>
                  </Link>
                </li>
              )
            })}
          </ul>
        </>
      )}
    </section>
  )
}
