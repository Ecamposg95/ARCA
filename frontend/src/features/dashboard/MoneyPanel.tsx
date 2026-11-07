import { Link } from 'react-router-dom'
import { formatMoney, formatWeekday, splitMoney } from '@/lib/format'
import type { DashboardMoney, DashboardMoneyRow } from '@/types/api'
import { useCountUp, useGrowOnce } from './useCountUp'

const STATUS_LABEL: Record<NonNullable<DashboardMoneyRow['status']>, string> = {
  CONFIRMED: 'Confirmado',
  PROVISIONAL: 'Provisional',
  TO_COLLECT: 'Por recolectar',
  TO_DEPOSIT: 'Por depositar',
}

/** Colores de la barra apilada y de su leyenda, por grupo. Todos tokens. */
const SWATCH: Record<DashboardMoneyRow['key'], string> = {
  central: 'bg-accent',
  branches: 'bg-accent-strong',
  banks: 'bg-muted',
  processor: 'bg-warn',
}

/** "vs ayer" entre semana, "vs viernes" en lunes: el cierre de referencia es el día hábil anterior. */
function previousDayLabel(): string {
  const weekday = new Date().getDay()
  if (weekday === 1 || weekday === 0 || weekday === 6) return 'vs viernes'
  return 'vs ayer'
}

export function DeltaChip({ value, basis }: { value: number; basis: string }) {
  if (!Number.isFinite(value) || value === 0) {
    return <span className="text-xs text-muted">Sin cambio {basis}</span>
  }
  const up = value > 0
  return (
    <span className="text-xs text-ink-soft">
      <span
        className={`figures rounded px-1.5 py-0.5 font-medium ${up ? 'bg-accent/10 text-accent' : 'bg-neg/10 text-neg'}`}
      >
        {up ? '+' : '−'}
        {formatMoney(Math.abs(value))}
      </span>{' '}
      {basis}
    </span>
  )
}

export function MoneyPanel({ money }: { money: DashboardMoney }) {
  const total = Number(money.total)
  const animated = useCountUp(total)
  const grown = useGrowOnce()
  const { main, cents } = splitMoney(animated)
  const positive = money.rows.filter((row) => Number(row.amount) > 0)
  const sum = positive.reduce((acc, row) => acc + Number(row.amount), 0)
  const delta = Number(money.delta)
  const settlement = money.next_settlement

  return (
    <section className="panel flex min-w-0 flex-col overflow-hidden p-4" aria-label={`Dinero hoy: ${formatMoney(money.total)}`}>
      <h2 className="text-[13px] font-medium text-ink-soft">Dinero hoy</h2>
      <div className="figure-hero mt-1 text-ink" aria-hidden>
        {main}
        <span className="text-xl text-muted">{cents}</span>
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
        <DeltaChip value={delta} basis={previousDayLabel()} />
        {settlement ? (
          <span className="text-xs text-muted">
            · {formatMoney(settlement.amount)} llega de {settlement.account} el {formatWeekday(settlement.expected_on)}
          </span>
        ) : null}
      </div>

      {sum > 0 ? (
        <div className="mt-3 flex h-2 gap-0.5 overflow-hidden rounded" role="img" aria-label="Partición del dinero">
          {positive.map((row) => (
            <span
              key={row.key}
              title={`${row.label} ${formatMoney(row.amount)}`}
              className={`${SWATCH[row.key]} transition-[flex-grow] duration-500 ease-out`}
              style={{ flexGrow: grown ? Number(row.amount) / sum : 0, flexBasis: 0 }}
            />
          ))}
        </div>
      ) : null}

      <ul className="mt-2 divide-y divide-border">
        {money.rows.map((row) => (
          <li key={row.key} className="grid grid-cols-[10px_minmax(0,1fr)_auto] items-center gap-2 py-1.5 text-[13px] sm:grid-cols-[10px_minmax(0,1fr)_auto_auto]">
            <span className={`h-2 w-2 rounded-sm ${SWATCH[row.key]}`} />
            <span className="min-w-0">
              <span className="block truncate text-ink">{row.label}</span>
              {row.status ? (
                <span className={`block text-[11px] sm:hidden ${row.status === 'PROVISIONAL' ? 'text-warn' : 'text-muted'}`}>
                  {STATUS_LABEL[row.status]}
                </span>
              ) : null}
            </span>
            <span className={`hidden text-[11.5px] sm:inline ${row.status === 'PROVISIONAL' ? 'text-warn' : 'text-muted'}`}>
              {row.status ? STATUS_LABEL[row.status] : ''}
            </span>
            <span className="figures whitespace-nowrap text-right text-ink">{formatMoney(row.amount)}</span>
          </li>
        ))}
      </ul>

      {money.needs_opening ? (
        <div className="mt-auto rounded-lg border border-dashed border-border bg-surface-2/60 px-3 py-2.5 text-xs">
          <p className="text-ink-soft">Los bancos siguen en cero provisional: el total aún no es el real.</p>
          <Link to="/configuracion/apertura" className="mt-1 inline-block font-medium text-accent hover:underline">
            Captura el saldo de tus bancos →
          </Link>
        </div>
      ) : null}
    </section>
  )
}
