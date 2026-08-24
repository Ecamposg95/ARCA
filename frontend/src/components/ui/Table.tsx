import type { ReactNode } from 'react'

export function Table({ headers, children }: { headers: (string | ReactNode)[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-border bg-surface shadow-card">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left">
            {headers.map((header, index) => (
              <th key={index} className="px-4 py-2.5 text-xs font-medium uppercase tracking-wide text-muted">
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border">{children}</tbody>
      </table>
    </div>
  )
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-border bg-surface p-5 shadow-card ${className}`}>{children}</div>
  )
}
