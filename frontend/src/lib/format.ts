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

export function formatDate(iso: string): string {
  const [year, month, day] = iso.split('T')[0].split('-').map(Number)
  return new Date(year, month - 1, day).toLocaleDateString('es-MX', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
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
