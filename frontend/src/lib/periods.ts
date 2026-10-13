/** Periodos compartidos por Contabilidad y Reportes: una sola definición. */

export type PeriodKey = 'current' | 'prev' | 'year' | 'all'

export const PERIOD_OPTIONS: { key: PeriodKey; label: string }[] = [
  { key: 'current', label: 'Este mes' },
  { key: 'prev', label: 'Mes anterior' },
  { key: 'year', label: 'Este año' },
  { key: 'all', label: 'Todo' },
]

function iso(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

export function rangeForPeriod(period: PeriodKey): { start?: string; end?: string } {
  const now = new Date()
  if (period === 'all') return {}
  if (period === 'prev') {
    return {
      start: iso(new Date(now.getFullYear(), now.getMonth() - 1, 1)),
      end: iso(new Date(now.getFullYear(), now.getMonth(), 0)),
    }
  }
  if (period === 'year') {
    return { start: `${now.getFullYear()}-01-01`, end: iso(now) }
  }
  return { start: iso(new Date(now.getFullYear(), now.getMonth(), 1)), end: iso(now) }
}

/** El periodo más angosto (en el orden de PERIOD_OPTIONS) que contiene la fecha ISO:
 *  sirve para que una póliza recién creada, aun fechada atrás, quede visible en la lista. */
export function periodContaining(dateIso: string): PeriodKey {
  for (const { key } of PERIOD_OPTIONS) {
    const { start, end } = rangeForPeriod(key)
    if ((!start || dateIso >= start) && (!end || dateIso <= end)) return key
  }
  return 'all'
}

export function periodLabel(period: PeriodKey): string {
  return PERIOD_OPTIONS.find((option) => option.key === period)?.label ?? ''
}
