import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { Modal } from '@/components/ui/Modal'
import { formatDate, formatMoney } from '@/lib/format'
import type { JournalEntry, LedgerAccount, Page } from '@/types/api'

/** "Así lo registró ARCA": la póliza de una operación, sin salir de la lista.
 *  Es el puente entre el lenguaje del empresario y la partida doble. */
export function JournalEntryModal({
  sourceType,
  sourceId,
  title,
  open,
  onClose,
}: {
  sourceType: string
  sourceId: string | null
  title: string
  open: boolean
  onClose: () => void
}) {
  const { data, isLoading } = useQuery({
    queryKey: ['journal-entry', sourceType, sourceId],
    queryFn: async () =>
      (
        await api.get<Page<JournalEntry>>('/accounting/journal-entries', {
          params: { source_type: sourceType, source_id: sourceId },
        })
      ).data,
    enabled: open && Boolean(sourceId),
  })

  const { data: accounts } = useQuery({
    queryKey: ['accounting', 'accounts'],
    queryFn: async () => (await api.get<LedgerAccount[]>('/accounting/accounts')).data,
    enabled: open,
  })

  const accountLabel = (id: string) => {
    const account = (accounts ?? []).find((item) => item.id === id)
    return account ? `${account.code} ${account.name}` : id
  }

  const entries = data?.items ?? []

  return (
    <Modal title={title} open={open} onClose={onClose}>
      {isLoading ? (
        <div className="h-24 animate-pulse rounded-lg bg-surface-2" />
      ) : entries.length === 0 ? (
        <p className="text-sm text-muted">
          Esta operación todavía no genera contabilidad. Las pólizas se crean cuando el dinero se
          mueve.
        </p>
      ) : (
        <div className="space-y-5">
          {entries.map((entry) => {
            const totalDebit = entry.lines.reduce((sum, line) => sum + Number(line.debit), 0)
            return (
              <div key={entry.id}>
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="figures text-sm font-semibold">{entry.folio}</span>
                  <span className="text-xs text-muted">{formatDate(entry.date)}</span>
                </div>
                <p className="mt-0.5 text-sm text-muted">{entry.description}</p>
                <table className="mt-3 w-full text-sm">
                  <thead>
                    <tr className="text-[11px] uppercase tracking-wider text-muted">
                      <th className="pb-1.5 text-left font-semibold">Cuenta</th>
                      <th className="pb-1.5 text-right font-semibold">Cargo</th>
                      <th className="pb-1.5 text-right font-semibold">Abono</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {entry.lines.map((line) => (
                      <tr key={line.id}>
                        <td className="py-1.5">{accountLabel(line.account_id)}</td>
                        <td className="figures py-1.5 text-right">
                          {Number(line.debit) > 0 ? formatMoney(line.debit) : '—'}
                        </td>
                        <td className="figures py-1.5 text-right">
                          {Number(line.credit) > 0 ? formatMoney(line.credit) : '—'}
                        </td>
                      </tr>
                    ))}
                    <tr className="border-t-2 border-ink/70 font-semibold">
                      <td className="py-1.5">
                        Cuadra
                        <span className="ml-2 text-xs font-medium text-pos">cargos = abonos ✓</span>
                      </td>
                      <td className="figures py-1.5 text-right">{formatMoney(totalDebit)}</td>
                      <td className="figures py-1.5 text-right">{formatMoney(totalDebit)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            )
          })}
        </div>
      )}
    </Modal>
  )
}
