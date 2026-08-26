import type { ReactNode } from 'react'

export function Table({
  headers,
  children,
  footer,
  secondary,
}: {
  headers: (string | ReactNode)[]
  children: ReactNode
  footer?: ReactNode
  /** Columnas (índice base 1) que se ocultan en pantallas chicas: en un teléfono
   *  vale más ver cinco columnas legibles que nueve tras un scroll lateral. */
  secondary?: number[]
}) {
  return (
    <div className="rounded-xl border border-border bg-surface shadow-card">
      <div className="overflow-x-auto">
        <table className="w-full text-sm" data-secondary={secondary?.join(' ')}>
          <thead>
            <tr className="border-b border-border text-left">
              {headers.map((header, index) => (
                <th
                  key={index}
                  className="whitespace-nowrap px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-muted"
                >
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">{children}</tbody>
        </table>
      </div>
      {footer}
    </div>
  )
}

export function Card({
  children,
  className = '',
  onClick,
}: {
  children: ReactNode
  className?: string
  onClick?: () => void
}) {
  return (
    <div
      className={`rounded-xl border border-border bg-surface p-5 shadow-card ${className}`}
      onClick={onClick}
      // Una tarjeta clicable también se abre con teclado; una estática no roba el tab.
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={
        onClick
          ? (event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                onClick()
              }
            }
          : undefined
      }
    >
      {children}
    </div>
  )
}
