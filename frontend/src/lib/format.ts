const mxn = new Intl.NumberFormat('es-MX', {
  style: 'currency',
  currency: 'MXN',
  minimumFractionDigits: 2,
})

export function formatMoney(value: string | number | null | undefined): string {
  const numeric = typeof value === 'string' ? Number(value) : (value ?? 0)
  return mxn.format(Number.isFinite(numeric) ? numeric : 0)
}

/** Divide una cifra en entero y centavos para la tipografía de ledger. */
export function splitMoney(value: string | number | null | undefined): { main: string; cents: string } {
  const formatted = formatMoney(value)
  const dot = formatted.lastIndexOf('.')
  if (dot === -1) return { main: formatted, cents: '' }
  return { main: formatted.slice(0, dot), cents: formatted.slice(dot) }
}

/** Cifra compacta para ejes de gráficas: $180k, $1.2M. */
export function formatCompact(value: number): string {
  const abs = Math.abs(value)
  if (abs >= 1_000_000) return `$${(value / 1_000_000).toFixed(abs >= 10_000_000 ? 0 : 1)}M`
  if (abs >= 1_000) return `$${Math.round(value / 1_000)}k`
  return `$${value}`
}

/** "agosto de 2026" → "Agosto de 2026" (sólo la inicial; `capitalize` de CSS rompe el "de"). */
export function formatMonthYear(date: Date): string {
  const label = date.toLocaleDateString('es-MX', { month: 'long', year: 'numeric' })
  return label.charAt(0).toUpperCase() + label.slice(1)
}

export function formatDate(iso: string): string {
  const [year, month, day] = iso.split('T')[0].split('-').map(Number)
  return new Date(year, month - 1, day).toLocaleDateString('es-MX', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

/** "12 ago" — etiqueta corta de día para ejes de gráficas semanales. */
export function formatShortDay(iso: string): string {
  const [year, month, day] = iso.split('T')[0].split('-').map(Number)
  return new Date(year, month - 1, day).toLocaleDateString('es-MX', {
    day: 'numeric',
    month: 'short',
  })
}

export function formatMonth(yearMonth: string): string {
  const [year, month] = yearMonth.split('-').map(Number)
  return new Date(year, month - 1, 1).toLocaleDateString('es-MX', { month: 'short' })
}

export function today(): string {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

export function monthStart(): string {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  return `${now.getFullYear()}-${month}-01`
}
