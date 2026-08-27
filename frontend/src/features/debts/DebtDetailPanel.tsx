/** Detalle de una cuenta por cobrar/pagar: días, historial y sus pólizas.
 *
 *  El patrón FINNOVA: la fila abre un panel lateral y el contexto de la lista
 *  no se pierde. Aquí viven las tres preguntas de una factura: ¿hace cuánto
 *  venció?, ¿qué cobros lleva?, ¿cómo quedó asentada?
 */

import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { Money } from '@/components/ui/Money'
import { formatDate, formatMoney } from '@/lib/format'
import { useAccounts } from '@/lib/hooks'
import type { Debt, JournalEntry, LedgerAccount, Page, Transaction } from '@/types/api'

function daysBetween(iso: string): number {
  const due = new Date(`${iso}T00:00:00`)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return Math.round((today.getTime() - due.getTime()) / 86_400_000)
}

export function DebtDetailPanel({
  debt,
  kind,
  contactName,
  onClose,
  onPay,
  payLabel,
}: {
  debt: Debt
  kind: 'receivables' | 'payables'
  contactName: string
  onClose: () => void
  onPay: () => void
  payLabel: string
}) {
  const sourceType = kind === 'receivables' ? 'receivable' : 'payable'

  const { data: accounts } = useAccounts()
  const movementsQuery = useQuery({
    queryKey: ['transactions', 'source', sourceType, debt.id],
    queryFn: async () =>
      (
        await api.get<Page<Transaction>>('/transactions', {
          params: { source_type: sourceType, source_id: debt.id },
        })
      ).data,
  })
  const entriesQuery = useQuery({
    queryKey: ['journal-entry', sourceType, debt.id],
    queryFn: async () =>
      (
        await api.get<Page<JournalEntry>>('/accounting/journal-entries', {
          params: { source_type: sourceType, source_id: debt.id },
        })
      ).data,
  })
  const { data: ledgerAccounts } = useQuery({
    queryKey: ['accounting', 'accounts'],
    queryFn: async () => (await api.get<LedgerAccount[]>('/accounting/accounts')).data,
  })

  const accountName = useMemo(() => {
    const map = new Map((accounts ?? []).map((account) => [account.id, account.name]))
    return (id: string) => map.get(id) ?? '—'
  }, [accounts])
  const ledgerLabel = useMemo(() => {
    const map = new Map(
      (ledgerAccounts ?? []).map((account) => [account.id, `${account.code} ${account.name}`]),
    )
    return (id: string) => map.get(id) ?? id
  }, [ledgerAccounts])

  const days = daysBetween(debt.due_date)
  const open = ['OPEN', 'PARTIAL', 'OVERDUE'].includes(debt.display_status)
  const movements = movementsQuery.data?.items ?? []
  const entries = entriesQuery.data?.items ?? []

  return (
    <div className="fixed inset-0 z-40">
      <div className="absolute inset-0 bg-black/45" onClick={onClose} aria-hidden />
      <aside
        role="dialog"
        aria-label={`Detalle de ${debt.description}`}
        className="absolute inset-y-0 right-0 flex w-full max-w-md flex-col border-l border-border bg-surface shadow-2xl"
      >
        <div className="flex items-start justify-between gap-3 border-b border-border px-5 py-4">
          <div className="min-w-0">
            <p className="text-xs text-muted">{contactName}</p>
            <h2 className="mt-0.5 font-medium">{debt.description}</h2>
            <p className={`mt-1 text-sm ${debt.is_overdue ? 'font-medium text-neg' : 'text-muted'}`}>
              {debt.is_overdue
                ? `Vencida hace ${days} día${days === 1 ? '' : 's'}`
                : days >= 0
                  ? `Venció ${formatDate(debt.due_date)}`
                  : `Vence en ${-days} día${days === -1 ? '' : 's'} (${formatDate(debt.due_date)})`}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar detalle"
            className="rounded-lg p-1.5 text-muted transition-colors hover:bg-surface-2 hover:text-ink"
          >
            ✕
          </button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto px-5 py-4">
          <div className="grid grid-cols-3 gap-3 text-center">
            <div className="rounded-lg bg-surface-2/60 px-2 py-2.5">
              <p className="text-[10px] uppercase tracking-wider text-muted">Total</p>
              <p className="figures mt-0.5 text-sm font-semibold">{formatMoney(debt.amount)}</p>
            </div>
            <div className="rounded-lg bg-surface-2/60 px-2 py-2.5">
              <p className="text-[10px] uppercase tracking-wider text-muted">
                {kind === 'receivables' ? 'Cobrado' : 'Pagado'}
              </p>
              <p className="figures mt-0.5 text-sm font-semibold">{formatMoney(debt.amount_paid)}</p>
            </div>
            <div className="rounded-lg bg-surface-2/60 px-2 py-2.5">
              <p className="text-[10px] uppercase tracking-wider text-muted">Saldo</p>
              <p className="mt-0.5">
                <Money value={debt.balance} tone={debt.is_overdue ? 'neg' : 'ink'} />
              </p>
            </div>
          </div>

          <section>
            <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted">
              {kind === 'receivables' ? 'Cobros registrados' : 'Pagos registrados'}
            </h3>
            {movementsQuery.isLoading ? (
              <div className="h-12 animate-pulse rounded-lg bg-surface-2" />
            ) : movements.length === 0 ? (
              <p className="text-sm text-muted">
                {kind === 'receivables' ? 'Todavía no te pagan nada.' : 'Todavía no pagas nada.'}
              </p>
            ) : (
              <ul className="divide-y divide-border text-sm">
                {movements.map((movement) => (
                  <li key={movement.id} className="flex items-center justify-between gap-3 py-2">
                    <span className="text-muted">
                      {formatDate(movement.date)}
                      <span className="ml-2 text-xs">
                        {kind === 'receivables' ? 'entró a' : 'salió de'}{' '}
                        {accountName(movement.financial_account_id)}
                      </span>
                    </span>
                    <span className="figures font-medium">{formatMoney(movement.amount)}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted">
              Así lo registró ARCA
            </h3>
            {entriesQuery.isLoading ? (
              <div className="h-16 animate-pulse rounded-lg bg-surface-2" />
            ) : entries.length === 0 ? (
              <p className="text-sm text-muted">Aún sin pólizas.</p>
            ) : (
              <div className="space-y-4">
                {entries.map((entry) => (
                  <div key={entry.id} className="rounded-lg border border-border px-3 py-2.5">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="figures text-xs font-semibold">{entry.folio}</span>
                      <span className="text-xs text-muted">{formatDate(entry.date)}</span>
                    </div>
                    <table className="mt-2 w-full text-xs">
                      <tbody className="divide-y divide-border">
                        {entry.lines.map((line) => (
                          <tr key={line.id}>
                            <td className="py-1 pr-2">{ledgerLabel(line.account_id)}</td>
                            <td className="figures py-1 text-right">
                              {Number(line.debit) > 0 ? formatMoney(line.debit) : '—'}
                            </td>
                            <td className="figures py-1 pl-3 text-right">
                              {Number(line.credit) > 0 ? formatMoney(line.credit) : '—'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>

        {open ? (
          <div className="border-t border-border px-5 py-3">
            <Button className="w-full" onClick={onPay}>
              {payLabel}
            </Button>
          </div>
        ) : null}
      </aside>
    </div>
  )
}
