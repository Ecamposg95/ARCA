import type { ReactNode } from 'react'

export function Table({
  headers,
  children,
  footer,
}: {
  headers: (string | ReactNode)[]
  children: ReactNode
  footer?: ReactNode
}) {
  return (
    <div className="rounded-xl border border-border bg-surface shadow-card">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
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

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-border bg-surface p-5 shadow-card ${className}`}>{children}</div>
  )
}
