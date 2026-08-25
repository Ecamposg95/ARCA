import type { Page } from '@/types/api'

/** Pie de tabla: sin esto, una lista con más de `limit` registros se corta en
 *  silencio y el usuario nunca se entera de que hay más. */
export function TableFooter<T>({
  page,
  onOffsetChange,
  noun,
}: {
  page: Page<T>
  onOffsetChange: (offset: number) => void
  /** Plural de lo que se lista: "movimientos", "ingresos"… */
  noun: string
}) {
  const { total, limit, offset } = page
  const from = total === 0 ? 0 : offset + 1
  const to = Math.min(offset + limit, total)
  const hasPrev = offset > 0
  const hasNext = to < total

  if (total <= limit) {
    return (
      <div className="border-t border-border px-4 py-2.5 text-xs text-muted">
        <span className="figures">{total}</span> {noun}
      </div>
    )
  }

  return (
    <div className="flex items-center justify-between gap-3 border-t border-border px-4 py-2.5 text-xs text-muted">
      <span>
        <span className="figures">
          {from}–{to}
        </span>{' '}
        de <span className="figures">{total}</span> {noun}
      </span>
      <div className="flex gap-1">
        <button
          type="button"
          disabled={!hasPrev}
          onClick={() => onOffsetChange(Math.max(offset - limit, 0))}
          className="rounded border border-border px-2.5 py-1 font-medium transition-colors hover:text-ink disabled:opacity-40 disabled:hover:text-muted"
        >
          Anterior
        </button>
        <button
          type="button"
          disabled={!hasNext}
          onClick={() => onOffsetChange(offset + limit)}
          className="rounded border border-border px-2.5 py-1 font-medium transition-colors hover:text-ink disabled:opacity-40 disabled:hover:text-muted"
        >
          Siguiente
        </button>
      </div>
    </div>
  )
}
